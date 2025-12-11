"""Synchronize database playlists with Rekordbox collections."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Protocol, Sequence, Set

from ...config import Config
from ...database import DatabaseService
from ...database.models import Playlist, Track
from .service import RekordboxService

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

    def create_playlist(self, name: str) -> Any: ...  # pragma: no cover

    def flush(self) -> None: ...  # pragma: no cover

    def get_playlist(self, **filters: Any) -> Any: ...  # pragma: no cover


class RekordboxSnapshotService:
    """Synchronize playlists stored in the database with Rekordbox."""

    def __init__(
        self,
        rekordbox_service: Optional[RekordboxService],
        db_service: DatabaseService,
        config: Config,
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
        playlists = self._select_playlists(playlist_name)
        summary = RekordboxSyncSummary()

        if not playlists:
            logger.info("No playlists found to sync to Rekordbox")
            return summary.to_dict()

        for playlist in playlists:

            try:
                stats = self._sync_playlist(
                    playlist, dry_run=dry_run, prune=prune_extra
                )
                summary.add_playlist_stats(stats)
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

        return summary.to_dict()

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

        playlist_tracks = self.db_service.get_playlist_track_associations(playlist.id)
        rb_playlist = self._ensure_target_playlist(playlist, dry_run, stats)
        index = self._build_track_index(rb_playlist)

        retained_content_ids = self._sync_tracks_for_playlist(
            playlist,
            playlist_tracks,
            rb_playlist,
            index,
            stats,
            dry_run,
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

    def _sync_tracks_for_playlist(
        self,
        playlist: Playlist,
        playlist_tracks: Sequence[Any],
        rb_playlist: Optional[Any],
        index: RekordboxTrackIndex,
        stats: PlaylistSyncStats,
        dry_run: bool,
    ) -> Set[str]:
        retained_content_ids: Set[str] = set()
        resolved_paths: dict[int, Optional[Path]] = {}

        for association in playlist_tracks:
            track = association.track
            if track is None:
                stats.tracks_skipped += 1
                continue

            resolved_paths[track.id] = self._resolve_track_path(track, association)
            match_id = self._match_existing_content(
                track, index, resolved_paths[track.id]
            )

            if match_id:
                retained_content_ids.add(match_id)
                if not dry_run and track.rekordbox_content_id != match_id:
                    self.db_service.set_track_rekordbox_id(track.id, match_id)
                if not dry_run:
                    self.db_service.update_track_sync_state(
                        playlist.id, track.id, in_rekordbox=True
                    )
                continue

            if dry_run:
                stats.tracks_added += 1
                continue

            track_path = resolved_paths[track.id]
            if not track_path or not track_path.exists():
                logger.warning(
                    "Skipping track '%s - %s' (missing file path) for playlist '%s'",
                    track.artist,
                    track.title,
                    playlist.name,
                )
                stats.tracks_skipped += 1
                continue

            content = self._ensure_content(track_path)
            if not content or rb_playlist is None:
                stats.tracks_skipped += 1
                continue

            self._db.add_to_playlist(rb_playlist, content)
            retained_content_ids.add(str(content.ID))
            stats.tracks_added += 1
            self.db_service.set_track_rekordbox_id(track.id, str(content.ID))
            self.db_service.update_track_sync_state(
                playlist.id, track.id, in_rekordbox=True
            )

            index.by_id[str(content.ID)] = SimpleNamespace(Content=content)
            index.by_path[str(track_path)] = SimpleNamespace(Content=content)

        return retained_content_ids

    def _ensure_target_playlist(
        self,
        playlist: Playlist,
        dry_run: bool,
        stats: PlaylistSyncStats,
    ) -> Optional[Any]:
        if playlist.rekordbox_playlist_id:
            rb_playlist = self._get_playlist_by_id(playlist.rekordbox_playlist_id)
            if rb_playlist:
                return rb_playlist

        rb_playlist = self._get_playlist_by_name(playlist.name)
        if rb_playlist and not dry_run:
            self.db_service.set_playlist_rekordbox_id(playlist.id, str(rb_playlist.ID))
            return rb_playlist

        if dry_run:
            stats.created = True
            return None

        rb_playlist = self._db.create_playlist(playlist.name)
        self._db.flush()
        stats.created = True
        self.db_service.set_playlist_rekordbox_id(playlist.id, str(rb_playlist.ID))
        logger.info("Created Rekordbox playlist '%s'", playlist.name)
        return rb_playlist

    def _get_playlist_by_id(self, playlist_id: str) -> Optional[Any]:
        try:
            result = self._db.get_playlist(ID=playlist_id)
            return result.first()
        except Exception:
            return None

    def _get_playlist_by_name(self, name: str) -> Optional[Any]:
        try:
            return self._db.get_playlist(Name=name).first()
        except Exception:
            return None

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

    def _resolve_symlink_path(self, path: Optional[Path]) -> Optional[Path]:
        if path is None:
            return None

        try:
            return path.resolve()
        except OSError:
            return path

    def _ensure_content(self, track_path: Path) -> Optional[Any]:
        return self.rekordbox_service.get_or_create_content(track_path)

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
