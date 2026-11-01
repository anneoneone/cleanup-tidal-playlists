"""Run the Download step: fetch missing Tidal tracks and convert them."""

from __future__ import annotations

import logging
import shutil
import subprocess  # noqa: S404 - runs ffmpeg with a fixed argument list
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from ..db import repository as repo
from ..db.engine import Database
from ..db.models import DownloadStatus, Playlist, Track
from ..jobs import JobContext
from ..music.paths import require_folder, to_stored_path
from .candidates import DownloadCandidate, find_candidates
from .tidal_dl import DownloadError, TrackUnavailableError, downloader_available

logger = logging.getLogger(__name__)


class Downloader(Protocol):
    """What the runner needs from a downloader (``TidalDownloader`` or a fake)."""

    def download(self, tidal_id: str, target_dir: Path) -> Path:
        """Download one track and return the file."""
        ...


DownloaderFactory = Callable[[], Downloader]


class ConversionError(DownloadError):
    """Raised when ffmpeg fails."""


@dataclass
class DownloadStats:
    """Counters of one Download step."""

    skipped: Optional[str] = None
    candidates: int = 0
    downloaded: int = 0
    failed: int = 0
    unavailable: int = 0
    errors: list[str] = field(default_factory=list)


def run_downloads(
    db: Database,
    music_folder: Path,
    target_format: str,
    ffmpeg_quality: int,
    make_downloader: DownloaderFactory,
    ctx: Optional[JobContext] = None,
    playlist_name: Optional[str] = None,
    *,
    check_installed: bool = True,
) -> DownloadStats:
    """Download every Tidal track that has no file yet."""
    stats = DownloadStats()
    require_folder(music_folder, "Music folder")
    with db.session() as session:
        candidates = find_candidates(session, music_folder, playlist_name)
    stats.candidates = len(candidates)
    if not candidates:
        return stats
    if check_installed and not downloader_available():
        stats.skipped = (
            f"{len(candidates)} tracks need a download, but tidal-dl-ng is not "
            "installed"
        )
        logger.warning(stats.skipped)
        return stats
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ConversionError(
            "ffmpeg is not installed; it is needed to convert downloads to "
            f"{target_format}"
        )

    downloader = make_downloader()
    for index, candidate in enumerate(candidates, start=1):
        if ctx is not None:
            ctx.check_cancelled()
            ctx.progress(
                index, len(candidates), f"{candidate.artist} - {candidate.title}"
            )
        _download_one(
            db,
            downloader,
            candidate,
            music_folder,
            target_format,
            ffmpeg_quality,
            ffmpeg,
            stats,
        )
    return stats


def _download_one(
    db: Database,
    downloader: Downloader,
    candidate: DownloadCandidate,
    music_folder: Path,
    target_format: str,
    ffmpeg_quality: int,
    ffmpeg: str,
    stats: DownloadStats,
) -> None:
    target_dir = music_folder / candidate.folder
    label = f"{candidate.artist} - {candidate.title}"
    try:
        raw = downloader.download(candidate.tidal_id, target_dir)
        final = convert(raw, target_format, ffmpeg_quality, ffmpeg)
    except TrackUnavailableError as exc:
        _record_failure(db, candidate.track_id, str(exc), unavailable=True)
        stats.unavailable += 1
        stats.errors.append(f"{label}: not available on Tidal")
        return
    except DownloadError as exc:
        _record_failure(db, candidate.track_id, str(exc), unavailable=False)
        stats.failed += 1
        stats.errors.append(f"{label}: {exc}")
        logger.warning("Download failed: %s: %s", label, exc)
        return

    with db.session() as session:
        track = session.get(Track, candidate.track_id)
        playlist = session.get(Playlist, candidate.playlist_id)
        if track is None or playlist is None:
            return
        repo.add_file_path(track, to_stored_path(final, music_folder))
        stat = final.stat()
        track.download_status = DownloadStatus.DOWNLOADED.value
        track.download_error = None
        track.downloaded_at = repo.utc_now()
        track.file_size_bytes = stat.st_size
        track.file_format = final.suffix.lstrip(".").lower()
        track.file_last_modified = datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).replace(tzinfo=None)
        if playlist.local_folder_path is None:
            playlist.local_folder_path = candidate.folder
    stats.downloaded += 1
    logger.info("Downloaded %s", label)


def _record_failure(db: Database, track_id: int, error: str, unavailable: bool) -> None:
    with db.session() as session:
        track = session.get(Track, track_id)
        if track is None:
            return
        track.download_status = DownloadStatus.ERROR.value
        track.download_error = error[:2000]
        if unavailable:
            track.tidal_unavailable = True


def convert(source: Path, target_format: str, quality: int, ffmpeg: str) -> Path:
    """Convert ``source`` to ``target_format`` with ffmpeg; delete the original.

    Tags are kept (``-map_metadata 0``), so the ISRC stays in the file.
    """
    extension = f".{target_format.lower().lstrip('.')}"
    if source.suffix.lower() == extension:
        return source
    target = source.with_suffix(extension)
    command: list[str] = [
        ffmpeg,
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-map_metadata",
        "0",
    ]
    if extension == ".mp3":
        command += ["-id3v2_version", "3", "-q:a", str(quality)]
    command.append(str(target))
    result: Any = subprocess.run(  # noqa: S603 - fixed command, no shell
        command, capture_output=True, text=True, check=False
    )
    if result.returncode != 0 or not target.is_file():
        target.unlink(missing_ok=True)
        tail = (result.stderr or "").strip().splitlines()[-3:]
        raise ConversionError(f"ffmpeg failed for {source.name}: {' '.join(tail)}")
    source.unlink()
    return target
