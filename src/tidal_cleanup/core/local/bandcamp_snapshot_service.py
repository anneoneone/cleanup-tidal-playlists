"""Sync Bandcamp/local playlists from filesystem into the database."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple

from tidal_cleanup.core.filesystem.file_scanner import FileScannerService
from tidal_cleanup.database.models import Playlist, PlaylistSource
from tidal_cleanup.database.service import DatabaseService

logger = logging.getLogger(__name__)


@dataclass
class BandcampSyncStats:
    """Aggregate counters for a Bandcamp playlist sync run."""

    playlists_seen: int = 0
    playlists_created: int = 0
    playlists_merged: int = 0
    tracks_added_or_updated: int = 0
    tracks_removed: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "playlists_seen": self.playlists_seen,
            "playlists_created": self.playlists_created,
            "playlists_merged": self.playlists_merged,
            "tracks_added_or_updated": self.tracks_added_or_updated,
            "tracks_removed": self.tracks_removed,
        }


class BandcampSnapshotService:
    """Import playlists and tracks from a Bandcamp-style folder tree."""

    def __init__(
        self,
        db_service: DatabaseService,
        root_dir: Path,
        audio_extensions: Optional[Sequence[str]] = None,
    ) -> None:
        """Configure Bandcamp/local sync with root directory and extensions."""
        self.db_service = db_service
        self.root_dir = Path(root_dir)
        self.audio_extensions = tuple(
            audio_extensions
            or (
                ".mp3",
                ".flac",
                ".wav",
                ".aac",
                ".m4a",
                ".mp4",
            )
        )
        self._scanner = FileScannerService(
            db_service=self.db_service, supported_extensions=self.audio_extensions
        )

    def sync_filesystem_to_db(
        self, playlist_name: Optional[str] = None
    ) -> Dict[str, int]:
        """Scan the Bandcamp playlist directory and upsert into the database."""
        stats = BandcampSyncStats()

        if not self.root_dir.exists():
            logger.warning("Bandcamp root does not exist: %s", self.root_dir)
            return stats.to_dict()

        playlist_dirs = self._collect_playlist_dirs(playlist_name)
        stats.playlists_seen = len(playlist_dirs)

        for playlist_dir in playlist_dirs:
            self._sync_single_playlist(playlist_dir, stats)

        return stats.to_dict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _collect_playlist_dirs(self, playlist_name: Optional[str]) -> list[Path]:
        candidates: Iterable[Path] = (
            self.root_dir.iterdir() if self.root_dir.exists() else []
        )
        playlist_dirs = [p for p in candidates if p.is_dir()]

        if playlist_name:
            playlist_dirs = [p for p in playlist_dirs if p.name == playlist_name]

        return sorted(playlist_dirs)

    def _sync_single_playlist(
        self, playlist_dir: Path, stats: BandcampSyncStats
    ) -> None:
        playlist, created = self._get_or_create_playlist(playlist_dir.name)
        if playlist is None:
            return

        if created:
            stats.playlists_created += 1
        else:
            stats.playlists_merged += 1

        existing_associations = self.db_service.get_playlist_track_associations(
            playlist.id
        )
        existing_track_ids = {pt.track_id for pt in existing_associations}

        current_local_track_ids: set[int] = set()
        files = list(self._list_audio_files(playlist_dir))

        for position, file_path in enumerate(files, start=1):
            track_data = self._build_track_data(file_path)
            track = self.db_service.create_or_update_track(track_data)

            position_arg = None if track.id in existing_track_ids else position
            self.db_service.add_track_to_playlist(
                playlist.id,
                track.id,
                position=position_arg,
                in_local=True,
            )
            current_local_track_ids.add(track.id)
            stats.tracks_added_or_updated += 1

        for association in existing_associations:
            if (
                association.track_id not in current_local_track_ids
                and association.in_local
            ):
                self.db_service.remove_track_from_playlist(
                    playlist.id, association.track_id, source="local"
                )
                stats.tracks_removed += 1

    def _get_or_create_playlist(self, name: str) -> Tuple[Optional[Playlist], bool]:
        existing = self.db_service.get_playlist_by_name(name)
        if existing:
            return existing, False

        try:
            created = self.db_service.create_playlist(
                {"name": name, "source": PlaylistSource.LOCAL.value}
            )
            return created, True
        except Exception as exc:
            logger.warning("Failed to create playlist %s: %s", name, exc)
            return None, False

    def _list_audio_files(self, playlist_dir: Path) -> Iterable[Path]:
        files: set[Path] = set()
        for ext in self.audio_extensions:
            files.update(playlist_dir.rglob(f"*{ext}"))
        return sorted(files)

    def _build_track_data(self, file_path: Path) -> Dict[str, object]:
        metadata = self._scanner._extract_file_metadata(file_path) or {}

        title = (metadata.get("title") or file_path.stem).strip()
        artist = (metadata.get("artist") or "Unknown Artist").strip()
        duration_raw = metadata.get("duration")

        stat_result = file_path.stat()

        return {
            "title": title,
            "artist": artist,
            "album": metadata.get("album"),
            "isrc": metadata.get("isrc"),
            "duration": int(duration_raw) if duration_raw else None,
            "file_path": str(file_path),
            "file_size_bytes": stat_result.st_size,
            "file_format": file_path.suffix.lstrip(".").lower(),
            "file_last_modified": datetime.fromtimestamp(
                stat_result.st_mtime, tz=timezone.utc
            ),
        }
