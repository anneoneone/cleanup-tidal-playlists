"""Synchronize database playlists with Rekordbox collections."""

from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Protocol, Sequence, Set

from ...config import Config
from ...database import DatabaseService
from ...database.models import Playlist, Track
from .playlist_parser import PlaylistNameParser
from .service import RekordboxService

try:
    from pyrekordbox import db6

    PYREKORDBOX_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    PYREKORDBOX_AVAILABLE = False
    db6 = None

logger = logging.getLogger(__name__)


@dataclass
class RekordboxTrackIndex:
    """Holds fast lookup maps for playlist content."""

    by_id: dict[str, Any] = field(default_factory=dict)
    by_path: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaylistSyncStats:
    """Per-playlist synchronization statistics."""

    playlist_id: int
    playlist_name: str
    created: bool = False
    tracks_added: int = 0
    tracks_removed: int = 0
    tracks_skipped: int = 0

    def has_changes(self) -> bool:
        return self.created or self.tracks_added > 0 or self.tracks_removed > 0


@dataclass
class RekordboxSyncSummary:
    """Aggregate synchronization summary for reporting."""

    playlists_processed: int = 0
    playlists_created: int = 0
    playlists_changed: int = 0
    tracks_added: int = 0
    tracks_removed: int = 0
    tracks_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def add_playlist_stats(self, stats: PlaylistSyncStats) -> None:
        self.playlists_processed += 1
        if stats.created:
            self.playlists_created += 1
        if stats.has_changes():
            self.playlists_changed += 1
        self.tracks_added += stats.tracks_added
        self.tracks_removed += stats.tracks_removed
        self.tracks_skipped += stats.tracks_skipped

    def to_dict(self) -> Dict[str, Any]:
        return {
            "playlists_processed": self.playlists_processed,
            "playlists_created": self.playlists_created,
            "playlists_changed": self.playlists_changed,
            "tracks_added": self.tracks_added,
            "tracks_removed": self.tracks_removed,
            "tracks_skipped": self.tracks_skipped,
            "errors": self.errors,
        }


class RekordboxDatabaseProtocol(Protocol):
    """Minimal protocol for the pyrekordbox database object we rely on."""

    def commit(self) -> None: ...  # pragma: no cover - protocol definition

    def rollback(self) -> None: ...  # pragma: no cover - protocol definition

    def add_to_playlist(self, playlist: Any, content: Any) -> None: ...

    def remove_from_playlist(self, playlist: Any, song: Any) -> None: ...

    def create_playlist(
        self, name: str, parent: Optional[str] = None
    ) -> Any: ...  # pragma: no cover

    def create_playlist_folder(
        self, name: str, parent: Optional[str] = None
    ) -> Any: ...  # pragma: no cover

    def move_playlist(self, playlist: Any, parent: Optional[str] = None) -> None: ...

    def delete_playlist(self, playlist: Any) -> None: ...  # pragma: no cover

    def flush(self) -> None: ...  # pragma: no cover

    def get_playlist(self, **filters: Any) -> Any: ...  # pragma: no cover

    def get_content(self, **filters: Any) -> Any: ...  # pragma: no cover


class RekordboxSnapshotService:
    """Synchronize playlists stored in the database with Rekordbox."""

    def __init__(
        self,
        rekordbox_service: Optional[RekordboxService],
        db_service: DatabaseService,
        config: Config,
        emoji_config_path: Optional[Path] = None,
    ) -> None:
        """Create a new Rekordbox snapshot service."""
        if rekordbox_service is None:
            raise RuntimeError("Rekordbox service is not available")

        self.rekordbox_service = rekordbox_service
        self.db_service = db_service
        self.config = config
        db = rekordbox_service.db

        if db is None:
            raise RuntimeError("Rekordbox database connection is not available")

        self._db: RekordboxDatabaseProtocol = db

        self._mp3_root = Path(config.mp3_directory)

        # Folder/path helpers - removed in-memory cache, now using database
        self._emoji_config_path = self._resolve_emoji_config_path(emoji_config_path)
        self._name_parser = PlaylistNameParser(self._emoji_config_path)
        self._genre_root: str = str(
            self._name_parser.folder_structure.get("genre_root", "Genre")
        )
        self._events_root: str = str(
            self._name_parser.folder_structure.get("events_root", "Events")
        )
        self._genre_uncategorized = getattr(
            self._name_parser, "genre_uncategorized", "Uncategorized"
        )
        self._events_misc = getattr(self._name_parser, "events_misc", "Misc")
        genre_cats: Any = self._name_parser.folder_structure.get("genre_categories", {})
        self._genre_categories: Dict[str, Any] = (
            genre_cats if isinstance(genre_cats, dict) else {}
        )
        self._genre_default_status: str = str(
            self._name_parser.folder_structure.get("genre_default_status", "Archived")
        )

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def sync_database_to_rekordbox(
        self,
        playlist_name: Optional[str] = None,
        dry_run: bool = False,
        prune_extra: bool = True,
    ) -> Dict[str, Any]:
        """Ensure Rekordbox playlists mirror the database state."""
        # If syncing all playlists, first drop any DB playlists whose local
        # folders are gone
        if playlist_name is None:
            self._prune_missing_local_playlists(dry_run=dry_run)

        playlists = self._select_playlists(playlist_name)
        summary = RekordboxSyncSummary()
        folder_tree: Dict[str, Any] = {"name": "Root", "playlists": [], "children": {}}

        if not playlists:
            logger.info("No playlists found to sync to Rekordbox")
            return summary.to_dict()

        # Ensure top-level roots exist so Events/Genre are always present
        self._ensure_root_folders(dry_run)

        for playlist in playlists:

            try:
                stats = self._sync_playlist(
                    playlist, dry_run=dry_run, prune=prune_extra
                )
                summary.add_playlist_stats(stats)

                # Build folder tree for display
                self._add_to_folder_tree(folder_tree, playlist)

            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception(
                    "Failed to sync playlist '%s' to Rekordbox", playlist.name
                )
                summary.errors.append(f"{playlist.name}: {exc}")
                if not dry_run:
                    self._db.rollback()

        if not dry_run:
            self._db.commit()
        else:
            # Ensure nothing sticks if the caller calls dry-run repeatedly
            self._db.rollback()

        result = summary.to_dict()
        result["folder_tree"] = folder_tree
        return result

    # ------------------------------------------------------------------
    # Cleanup helpers
    # ------------------------------------------------------------------
    def _prune_missing_local_playlists(self, dry_run: bool) -> None:
        """Remove playlists from DB and Rekordbox if their local folders are missing."""
        playlists_root = self._mp3_root / "Playlists"
        if not playlists_root.exists():
            logger.warning("Playlists root does not exist: %s", playlists_root)
            return

        fs_playlists = {p.name for p in playlists_root.iterdir() if p.is_dir()}
        db_playlists = {p.name for p in self.db_service.get_all_playlists()}

        # Pass 1: Remove DB playlists whose folders are missing
        missing_from_fs = [
            p for p in self.db_service.get_all_playlists() if p.name not in fs_playlists
        ]

        if missing_from_fs:
            logger.info(
                "Pruning %d DB playlists missing from filesystem", len(missing_from_fs)
            )

            for playlist in missing_from_fs:
                if dry_run:
                    logger.info(
                        "(dry-run) Would remove DB playlist missing locally: %s",
                        playlist.name,
                    )
                    continue

                self._remove_playlist_from_rekordbox_and_db(playlist)

            if not dry_run:
                self._commit_with_error_handling(
                    "Failed to commit after pruning missing playlists"
                )

        # Pass 2: Remove Rekordbox orphan playlists (not in DB, not on disk)
        self._prune_rekordbox_orphans(fs_playlists, db_playlists, dry_run)

    def _remove_playlist_from_rekordbox_and_db(self, playlist: Playlist) -> None:
        """Remove a playlist from both Rekordbox and our database."""
        # Remove from Rekordbox if present
        try:
            rb_pl = None
            playlist_id = getattr(playlist, "rekordbox_playlist_id", None)
            if playlist_id:
                rb_pl = self._get_playlist_by_id(playlist_id)
            if rb_pl is None:
                rb_pl = self._get_playlist_by_name(playlist.name)

            if rb_pl:
                self._db.delete_playlist(rb_pl)
                self._db.flush()
                logger.info(
                    "Removed Rekordbox playlist missing locally: %s",
                    playlist.name,
                )
        except Exception as exc:
            logger.warning(
                "Failed to delete Rekordbox playlist %s: %s", playlist.name, exc
            )

        # Remove from our database
        self.db_service.delete_playlist(playlist.id)

    def _prune_rekordbox_orphans(
        self, fs_playlists: set[str], db_playlists: set[str], dry_run: bool
    ) -> None:
        """Remove Rekordbox playlists that exist in neither DB nor filesystem."""
        try:
            orphans = self._collect_rekordbox_orphans(fs_playlists, db_playlists)
            if not orphans:
                return

            logger.info(
                "Pruning %d Rekordbox orphan playlists (not in DB or filesystem)",
                len(orphans),
            )

            for rb_pl in orphans:
                self._delete_rekordbox_orphan(rb_pl, dry_run)

            if not dry_run:
                self._commit_with_error_handling(
                    "Failed to commit after pruning Rekordbox orphans"
                )

        except Exception as exc:
            logger.warning("Failed to prune Rekordbox orphans: %s", exc)

    def _collect_rekordbox_orphans(
        self, fs_playlists: set[str], db_playlists: set[str]
    ) -> list[Any]:
        """Collect Rekordbox playlists that don't exist in DB or filesystem."""
        if not PYREKORDBOX_AVAILABLE or db6 is None:
            return []

        query = self._db.get_playlist(Attribute=0)  # 0 = playlist (not folder)
        rb_playlists = query.all()

        orphans = []
        for rb_pl in rb_playlists:
            name = getattr(rb_pl, "Name", "")
            if name and name not in fs_playlists and name not in db_playlists:
                orphans.append(rb_pl)

        return orphans

    def _commit_with_error_handling(self, error_message: str) -> None:
        """Commit database changes with error logging."""
        try:
            self._db.commit()
        except Exception:
            logger.warning(error_message)

    def _delete_rekordbox_orphan(self, rb_pl: Any, dry_run: bool) -> None:
        """Delete a single orphan playlist from Rekordbox."""
        name = getattr(rb_pl, "Name", "")
        if dry_run:
            logger.info("(dry-run) Would remove Rekordbox orphan: %s", name)
            return

        try:
            self._db.delete_playlist(rb_pl)
            self._db.flush()
            logger.info("Removed Rekordbox orphan playlist: %s", name)
        except Exception as exc:
            logger.warning("Failed to delete Rekordbox orphan %s: %s", name, exc)

    # ------------------------------------------------------------------
    # Playlist synchronization helpers
    # ------------------------------------------------------------------
    def _sync_playlist(
        self,
        playlist: Playlist,
        dry_run: bool,
        prune: bool,
    ) -> PlaylistSyncStats:
        stats = PlaylistSyncStats(playlist.id, playlist.name)

        metadata = self._name_parser.parse_playlist_name(playlist.name)

        playlist_tracks = self.db_service.get_playlist_track_associations(playlist.id)
        rb_playlist = self._ensure_target_playlist(playlist, dry_run, stats, metadata)
        index = self._build_track_index(rb_playlist)

        retained_content_ids = self._sync_tracks_for_playlist(
            playlist,
            playlist_tracks,
            rb_playlist,
            index,
            stats,
            dry_run,
            metadata,
        )

        if not dry_run and rb_playlist and prune:
            stats.tracks_removed += self._remove_extra_tracks(
                rb_playlist, retained_content_ids
            )

        if not dry_run and rb_playlist:
            final_index = self._build_track_index(
                self.rekordbox_service.refresh_playlist(rb_playlist)
            )
            final_count = len(final_index.by_id)
            self.db_service.update_playlist(
                playlist.id,
                {
                    "track_count_rekordbox": final_count,
                    "last_synced_at": datetime.now(timezone.utc),
                },
            )

        return stats

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _select_playlists(self, playlist_name: Optional[str]) -> Sequence[Playlist]:
        if playlist_name:
            playlist = self.db_service.get_playlist_by_name(playlist_name)
            if playlist:
                return [playlist]
            logger.warning("Playlist '%s' was not found in database", playlist_name)
            return []
        return self.db_service.get_all_playlists()

    def _ensure_root_folders(self, dry_run: bool) -> None:
        """Guarantee that top-level Genre and Events folders exist."""
        for root_name in {self._genre_root, self._events_root}:
            try:
                # Prefer a direct lookup to avoid stale cache
                existing = self._find_folder(root_name, parent_id=None)
                if existing:
                    self.db_service.set_rekordbox_folder_id(root_name, str(existing.ID))
                    logger.debug(
                        "Root folder '%s' already exists (ID=%s)",
                        root_name,
                        existing.ID,
                    )
                    continue

                if dry_run:
                    logger.debug("(dry-run) Would create root folder '%s'", root_name)
                    continue

                # Rekordbox root folders are created with parent=None;
                # RB sets ParentID="root"
                created = self._db.create_playlist_folder(root_name, parent=None)
                self._db.flush()
                self.db_service.set_rekordbox_folder_id(root_name, str(created.ID))
                logger.info("Created root folder '%s' (ID=%s)", root_name, created.ID)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to ensure root folder '%s': %s", root_name, exc)

    def _sync_tracks_for_playlist(
        self,
        playlist: Playlist,
        playlist_tracks: Sequence[Any],
        rb_playlist: Optional[Any],
        index: RekordboxTrackIndex,
        stats: PlaylistSyncStats,
        dry_run: bool,
        metadata: Any,
    ) -> Set[str]:
        retained_content_ids: Set[str] = set()
        resolved_paths: dict[int, Optional[Path]] = {}
        genre = self._derive_genre_from_metadata(metadata)

        for association in playlist_tracks:
            track = association.track
            if track is None:
                stats.tracks_skipped += 1
                continue

            resolved_paths[track.id] = self._resolve_track_path(track, association)
            self._process_track_for_sync(
                playlist,
                track,
                resolved_paths[track.id],
                rb_playlist,
                index,
                genre,
                metadata,
                retained_content_ids,
                stats,
                dry_run,
            )

        return retained_content_ids

    def _process_track_for_sync(
        self,
        playlist: Playlist,
        track: Track,
        resolved_path: Optional[Path],
        rb_playlist: Optional[Any],
        index: RekordboxTrackIndex,
        genre: Optional[str],
        metadata: Any,
        retained_content_ids: Set[str],
        stats: PlaylistSyncStats,
        dry_run: bool,
    ) -> None:
        """Process a single track for playlist sync."""
        match_id = self._match_existing_content(track, index, resolved_path)

        if match_id:
            retained_content_ids.add(match_id)
            if genre and not dry_run:
                self._maybe_update_genre(match_id, genre, index=index)
            if not dry_run and track.rekordbox_content_id != match_id:
                self.db_service.set_track_rekordbox_id(track.id, match_id)
            if not dry_run:
                self.db_service.update_track_sync_state(
                    playlist.id, track.id, in_rekordbox=True
                )
            return

        if dry_run:
            stats.tracks_added += 1
            return

        if not resolved_path or not resolved_path.exists():
            logger.warning(
                "Skipping track '%s - %s' (missing file path) for playlist '%s'",
                track.artist,
                track.title,
                playlist.name,
            )
            stats.tracks_skipped += 1
            return

        content = self._ensure_content(track, resolved_path, metadata, genre)
        if not content or rb_playlist is None:
            stats.tracks_skipped += 1
            return

        if genre and not dry_run:
            self._maybe_update_genre(str(content.ID), genre)

        self._db.add_to_playlist(rb_playlist, content)
        retained_content_ids.add(str(content.ID))
        stats.tracks_added += 1
        self.db_service.set_track_rekordbox_id(track.id, str(content.ID))
        self.db_service.update_track_sync_state(
            playlist.id, track.id, in_rekordbox=True
        )

        index.by_id[str(content.ID)] = SimpleNamespace(Content=content)
        index.by_path[str(resolved_path)] = SimpleNamespace(Content=content)

    def _ensure_target_playlist(
        self,
        playlist: Playlist,
        dry_run: bool,
        stats: PlaylistSyncStats,
        metadata: Any,
    ) -> Optional[Any]:
        parent_folder_id = self._get_folder_for_metadata(metadata, dry_run=dry_run)

        # Get clean display name with energy; append status only when non-default
        clean_name = self._get_clean_display_name(metadata, include_status=True)
        legacy_name = self._get_clean_display_name(metadata, include_status=False)

        # Try to find existing playlist
        rb_playlist = self._find_existing_rekordbox_playlist(
            playlist, clean_name, legacy_name, parent_folder_id, dry_run
        )
        if rb_playlist:
            return rb_playlist

        if dry_run:
            stats.created = True
            return None

        try:
            rb_playlist = self._db.create_playlist(clean_name, parent=parent_folder_id)
            self._db.flush()
            stats.created = True
            self.db_service.set_playlist_rekordbox_id(playlist.id, str(rb_playlist.ID))
            logger.info("Created Rekordbox playlist '%s'", clean_name)
            return rb_playlist
        except ValueError as e:
            # If parent folder doesn't exist or is invalid, clear cache and retry
            if "Parent does not exist" in str(e) or "is not a folder" in str(e):
                logger.warning(
                    "Parent folder missing for playlist '%s' - clearing cache",
                    clean_name,
                )
                self.db_service.clear_rekordbox_folder_cache()
                # Retry with fresh cache
                parent_folder_id = self._get_folder_for_metadata(
                    metadata, dry_run=False
                )
                rb_playlist = self._db.create_playlist(
                    clean_name, parent=parent_folder_id
                )
                self._db.flush()
                stats.created = True
                self.db_service.set_playlist_rekordbox_id(
                    playlist.id, str(rb_playlist.ID)
                )
                logger.info("Created Rekordbox playlist '%s' (refreshed)", clean_name)
                return rb_playlist
            raise

    def _find_existing_rekordbox_playlist(
        self,
        playlist: Playlist,
        clean_name: str,
        legacy_name: str,
        parent_folder_id: Optional[str],
        dry_run: bool,
    ) -> Optional[Any]:
        """Find existing Rekordbox playlist by ID, name, or legacy name."""
        # Try by stored ID first
        if playlist.rekordbox_playlist_id:
            rb_playlist = self._get_playlist_by_id(playlist.rekordbox_playlist_id)
            if rb_playlist:
                return self._update_existing_playlist(
                    rb_playlist, clean_name, parent_folder_id, dry_run
                )

        # Try by current name
        rb_playlist = self._get_playlist_by_name(clean_name)
        if rb_playlist and not dry_run:
            self.db_service.set_playlist_rekordbox_id(playlist.id, str(rb_playlist.ID))
            return self._update_existing_playlist(
                rb_playlist, clean_name, parent_folder_id, dry_run
            )

        # Fallback: migrate legacy playlists created without status in the name
        if legacy_name != clean_name:
            legacy_rb_playlist = self._get_playlist_by_name(legacy_name)
            if legacy_rb_playlist and not dry_run:
                self.db_service.set_playlist_rekordbox_id(
                    playlist.id, str(legacy_rb_playlist.ID)
                )
                legacy_rb_playlist = self._update_existing_playlist(
                    legacy_rb_playlist, clean_name, parent_folder_id, dry_run
                )
                return legacy_rb_playlist

        return None

    def _update_existing_playlist(
        self,
        rb_playlist: Any,
        clean_name: str,
        parent_folder_id: Optional[str],
        dry_run: bool,
    ) -> Any:
        """Update an existing Rekordbox playlist's location and name."""
        rb_playlist = self._move_playlist_if_needed(
            rb_playlist, parent_folder_id, dry_run
        )
        if not dry_run and getattr(rb_playlist, "Name", None) != clean_name:
            rb_playlist.Name = clean_name
            self._db.flush()
            logger.info("Renamed Rekordbox playlist to '%s'", clean_name)
        return rb_playlist

    def _get_playlist_by_id(self, playlist_id: str) -> Optional[Any]:
        try:
            result = self._db.get_playlist(ID=playlist_id)
            return result.first()
        except Exception:
            return None

    def _get_playlist_by_name(self, name: str) -> Optional[Any]:
        try:
            # Get normal playlists (Attribute=0), not folders (Attribute=1)
            query = self._db.get_playlist(Name=name, Attribute=0)
            return query.first()
        except Exception:
            return None

    def _get_clean_display_name(
        self, metadata: Any, include_status: bool = True
    ) -> str:
        """Create clean playlist name for Rekordbox.

        Creates a name with no emojis, including energy/status words.

        Args:
            metadata: PlaylistMetadata from parser
            include_status: Whether to append non-default status to the name

        Returns:
            Clean name with energy level word appended (if present), and status
            when non-default.
        """
        clean_name: str = str(
            metadata.playlist_name
        )  # Already has emojis stripped by parser

        if metadata.energy_tags:
            energy_word: str = str(sorted(metadata.energy_tags)[0])
            clean_name = f"{clean_name} {energy_word}"

        if include_status:
            status_word: str = (
                str(sorted(metadata.status_tags)[0])
                if metadata.status_tags
                else self._genre_default_status
            )
            # Only append status when it is not the default to avoid noisy names
            if status_word != self._genre_default_status:
                clean_name = f"{clean_name} {status_word}".strip()

        return clean_name.strip()

    def _build_track_index(self, playlist: Optional[Any]) -> RekordboxTrackIndex:
        index = RekordboxTrackIndex()
        if not playlist:
            return index

        for song in getattr(playlist, "Songs", []):
            content = getattr(song, "Content", None)
            if not content:
                continue
            content_id = str(content.ID)
            index.by_id[content_id] = song
            path = getattr(content, "FolderPath", None)
            if path:
                index.by_path[path] = song

        return index

    def _add_to_folder_tree(self, tree: Dict[str, Any], playlist: Playlist) -> None:
        """Add playlist to the folder tree structure for display.

        Args:
            tree: Root tree dictionary
            playlist: Playlist to add
        """
        # Parse playlist name to get folder path
        metadata = self._name_parser.parse_playlist_name(playlist.name)
        segments = self._get_folder_path_segments(metadata)

        # Navigate/create tree structure - ALL segments are folders
        current = tree
        for segment in segments:
            if segment not in current["children"]:
                current["children"][segment] = {
                    "name": segment,
                    "playlists": [],
                    "children": {},
                }
            current = current["children"][segment]

        # Add playlist to the deepest folder
        current["playlists"].append(playlist.name)

    def _match_existing_content(
        self,
        track: Track,
        index: RekordboxTrackIndex,
        resolved_path: Optional[Path],
    ) -> Optional[str]:
        if track.rekordbox_content_id and track.rekordbox_content_id in index.by_id:
            return track.rekordbox_content_id

        if resolved_path is None:
            return None

        track_path_str = str(resolved_path)
        song = index.by_path.get(track_path_str)
        if song and getattr(song, "Content", None):
            return str(song.Content.ID)

        return None

    def _resolve_track_path(
        self, track: Track, association: Optional[Any]
    ) -> Optional[Path]:
        # Prefer playlist-specific file paths stored in the database.
        candidate_paths: List[Path] = []
        for raw_path in track.file_paths or []:
            candidate = self._build_absolute_path(raw_path)
            if candidate:
                candidate_paths.append(candidate)

        for candidate in candidate_paths:
            if candidate.exists():
                return candidate

        for candidate in candidate_paths:
            try:
                resolved = candidate.resolve()
                if resolved.exists():
                    return resolved
            except OSError:
                continue

        return candidate_paths[0] if candidate_paths else None

    def _build_absolute_path(self, raw_path: Optional[str]) -> Optional[Path]:
        if not raw_path:
            return None

        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = self._mp3_root / candidate
        return candidate

    def _ensure_content(
        self, track: Track, track_path: Path, metadata: Any, genre: Optional[str]
    ) -> Optional[Any]:
        # Prefer Tidal-enriched creation using DB Track metadata
        return self.rekordbox_service.get_or_create_content_from_track(
            track, track_path, genre=genre
        )

    def _maybe_update_genre(
        self,
        content_id: str,
        genre: str,
        index: Optional[RekordboxTrackIndex] = None,
        content: Optional[Any] = None,
    ) -> None:
        """Update Rekordbox content genre if different, with robust lookup."""
        try:
            content = self._lookup_content(content_id, index, content)
            if content is None:
                logger.debug("Genre update skipped; content %s not found", content_id)
                return

            current = getattr(content, "Genre", None)
            if current == genre:
                return

            # Content must support genre to proceed
            if not (hasattr(content, "GenreID") or hasattr(content, "Genre")):
                logger.debug("Genre update skipped; content lacks Genre fields")
                return

            self._apply_genre_to_content(content, genre)
            self._db.flush()
            logger.info("Updated genre for content %s -> %s", content_id, genre)
        except Exception:
            logger.debug("Could not update genre for content %s", content_id)

    def _lookup_content(
        self,
        content_id: str,
        index: Optional[RekordboxTrackIndex],
        content: Optional[Any],
    ) -> Optional[Any]:
        """Lookup content by ID using multiple strategies."""
        if content is not None:
            return content

        if index is not None:
            song = index.by_id.get(content_id)
            content = getattr(song, "Content", None) if song else None
            if content is not None:
                return content

        cid: Any = int(content_id) if str(content_id).isdigit() else content_id
        content = self._db.get_content(ID=cid).first()
        if content is not None:
            return content

        with suppress(Exception):
            content = self._db.get_content(ContentID=cid).first()

        return content

    def _apply_genre_to_content(self, content: Any, genre: str) -> None:
        """Apply genre to content using DjmdGenre table."""
        genre_entry = None
        if hasattr(self._db, "get_genre"):
            with suppress(Exception):
                genre_entry = self._db.get_genre(Name=genre).first()

        if genre_entry is None and hasattr(self._db, "add_genre"):
            with suppress(Exception):
                genre_entry = self._db.add_genre(name=genre)

        # Assign all genre fields
        if genre_entry and hasattr(genre_entry, "ID") and hasattr(content, "GenreID"):
            content.GenreID = genre_entry.ID

        if hasattr(content, "Genre"):
            content.Genre = genre

        if (
            genre_entry
            and hasattr(genre_entry, "Name")
            and hasattr(content, "GenreName")
        ):
            content.GenreName = genre_entry.Name

    def _derive_genre_from_metadata(self, metadata: Any) -> Optional[str]:
        """Pick a genre tag from playlist metadata, ignoring energy/status/events."""
        try:
            genre_tags = set(getattr(metadata, "genre_tags", set()))
        except Exception:
            genre_tags = set()

        if not genre_tags:
            return None

        cleaned = [tag for tag in genre_tags if tag != self._genre_uncategorized]
        if not cleaned:
            return None

        genre: str = str(sorted(cleaned)[0])
        playlist_name = getattr(metadata, "playlist_name", "")
        logger.info("Derived genre '%s' from playlist '%s'", genre, playlist_name)
        return genre

    def _remove_extra_tracks(self, playlist: Any, allowed_content_ids: Set[str]) -> int:
        removed = 0
        refreshed = self.rekordbox_service.refresh_playlist(playlist)
        for song in getattr(refreshed, "Songs", []):
            content = getattr(song, "Content", None)
            if not content:
                continue
            content_id = str(content.ID)
            if content_id in allowed_content_ids:
                continue
            self._db.remove_from_playlist(refreshed, song)
            removed += 1
        return removed

    # ------------------------------------------------------------------
    # Folder helpers (Genre/Events hierarchy from emoji mapping)
    # ------------------------------------------------------------------
    def _resolve_emoji_config_path(self, emoji_config_path: Optional[Path]) -> Path:
        if emoji_config_path:
            return emoji_config_path

        service_dir = Path(__file__).resolve().parent
        tidal_cleanup_dir = service_dir.parent
        src_dir = tidal_cleanup_dir.parent
        project_root = src_dir.parent

        default_path = project_root / "config" / "rekordbox_mytag_mapping.json"
        if default_path.exists():
            return default_path

        cwd_config = Path.cwd() / "config" / "rekordbox_mytag_mapping.json"
        if cwd_config.exists():
            return cwd_config

        raise RuntimeError(
            f"Cannot find emoji config at {default_path} or {cwd_config}"
        )

    def _get_genre_category(self, genre: str) -> str:
        """Determine which category a genre belongs to.

        Args:
            genre: Genre name (e.g., "House Deep")

        Returns:
            Category name (e.g., "Deep House") or genre itself if no category found
        """
        for category, genres in self._genre_categories.items():
            if genre in genres:
                return category
        # If no category found, return "Other Genres" as default
        return "Other Genres" if self._genre_categories else genre

    def _get_folder_path_segments(self, metadata: Any) -> List[str]:
        genre_tags = getattr(metadata, "genre_tags", None)

        # Check if playlist has actual genre tags (not just "Uncategorized")
        if (
            genre_tags
            and genre_tags != {self._genre_uncategorized}
            and self._genre_uncategorized not in genre_tags
        ):
            genre = sorted(genre_tags)[0]
            status = (
                sorted(metadata.status_tags)[0]
                if getattr(metadata, "status_tags", None)
                else self._genre_default_status
            )
            # Include genre category in path - always include status folder
            category = self._get_genre_category(genre)
            segments = [self._genre_root, category, status]
            return segments

        if getattr(metadata, "party_tags", None):
            event = sorted(metadata.party_tags)[0]
            year = getattr(metadata, "event_year", None) or self._events_misc
            return [self._events_root, event, year]

        # No genre or party tags (or only has "Uncategorized")
        if getattr(metadata, "status_tags", None):
            status = sorted(metadata.status_tags)[0]
            return [self._genre_root, self._genre_uncategorized, status]

        return [self._genre_root, self._genre_uncategorized, self._genre_default_status]

    def _get_folder_for_metadata(
        self, metadata: Any, dry_run: bool = False
    ) -> Optional[str]:
        segments = self._get_folder_path_segments(metadata)
        if not segments:
            return None
        return self._resolve_folder_path(segments, create=not dry_run)

    def _resolve_folder_path(
        self, segments: Sequence[str], create: bool = True
    ) -> Optional[str]:
        parent_id: Optional[str] = None
        path_parts: List[str] = []

        for segment in segments:
            path_parts.append(segment)
            path_key = "/".join(path_parts)

            # Check database cache first
            cached_id = self.db_service.get_rekordbox_folder_id(path_key)
            if cached_id:
                # Validate cached folder still exists
                try:
                    folder = self._db.get_playlist(ID=cached_id).first()
                    if (
                        folder and getattr(folder, "Attribute", None) == 1
                    ):  # Is a folder
                        parent_id = cached_id
                        continue
                    else:
                        # Cached ID is invalid, clear it from cache
                        logger.debug(
                            "Cached folder ID %s is invalid, clearing cache", cached_id
                        )
                        self.db_service.clear_rekordbox_folder_cache(path_key)
                except Exception:
                    # Cached ID lookup failed, clear it
                    logger.debug("Failed to validate cached folder ID %s", cached_id)
                    self.db_service.clear_rekordbox_folder_cache(path_key)

            folder = self._find_folder(segment, parent_id)
            if not folder and not create:
                return None

            if not folder and create:
                target_parent = parent_id or None
                folder = self._db.create_playlist_folder(segment, parent=target_parent)
                self._db.flush()

            if not folder:
                return None

            parent_id = str(folder.ID)
            # Cache in database for future syncs
            self.db_service.set_rekordbox_folder_id(path_key, parent_id)

        return parent_id

    def _find_folder(self, name: str, parent_id: Optional[str]) -> Optional[Any]:
        try:
            query = self._db.get_playlist(Name=name, Attribute=1)
            if PYREKORDBOX_AVAILABLE and db6 is not None:
                if parent_id:
                    query = query.filter(db6.DjmdPlaylist.ParentID == parent_id)
                else:
                    # Root folders have ParentID == "root"
                    query = query.filter(db6.DjmdPlaylist.ParentID == "root")
            return query.first()
        except Exception:
            return None

    def _move_playlist_if_needed(
        self, playlist: Any, parent_folder_id: Optional[str], dry_run: bool
    ) -> Any:
        if parent_folder_id and getattr(playlist, "ParentID", None) != parent_folder_id:
            if dry_run:
                return playlist
            try:
                self._db.move_playlist(playlist, parent=parent_folder_id)
                self._db.flush()
                logger.info(
                    "Moved Rekordbox playlist '%s' to folder %s",
                    getattr(playlist, "Name", ""),
                    parent_folder_id,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to move playlist '%s' to folder %s: %s",
                    getattr(playlist, "Name", ""),
                    parent_folder_id,
                    exc,
                )
        return playlist
