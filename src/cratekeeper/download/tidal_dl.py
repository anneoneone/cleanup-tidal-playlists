"""Adapter around tidal-dl-ng (optional: it is no longer on PyPI).

tidal-dl-ng keeps process-wide singletons and writes its settings and token
files on every start. Cratekeeper points its config folder into the
Cratekeeper home, so the v1 files in ``~/.config/tidal_dl_ng`` are never
touched, and hands it the tokens of Cratekeeper's own Tidal login.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = (".flac", ".m4a", ".mp3", ".wav")


class DownloaderUnavailableError(RuntimeError):
    """Raised when tidal-dl-ng is not installed."""


class DownloadError(RuntimeError):
    """Raised when one track cannot be downloaded."""


class TrackUnavailableError(DownloadError):
    """Raised when Tidal says the track does not exist (404)."""


def downloader_available() -> bool:
    """Return whether tidal-dl-ng can be imported."""
    return importlib.util.find_spec("tidal_dl_ng") is not None


def redirect_config(config_dir: Path) -> None:
    """Make tidal-dl-ng read and write its files in ``config_dir``."""
    import tidal_dl_ng.config as tdl_config
    import tidal_dl_ng.helper.path as tdl_path

    config_dir.mkdir(parents=True, exist_ok=True)
    base = str(config_dir)

    def config_base() -> str:
        return base

    def settings_file() -> str:
        return os.path.join(base, "settings.json")

    def token_file() -> str:
        return os.path.join(base, "token.json")

    for module in (tdl_path, tdl_config):
        if hasattr(module, "path_config_base"):
            module.path_config_base = config_base
        if hasattr(module, "path_file_settings"):
            module.path_file_settings = settings_file
        if hasattr(module, "path_file_token"):
            module.path_file_token = token_file
    tdl_config.BaseConfig.path_base = base


def resolve_downloaded_file(reported: Path) -> Optional[Path]:
    """Find the real file when tidal-dl-ng reports a wrong extension (v1 fix)."""
    if reported.is_file():
        return reported
    if not reported.parent.is_dir():
        return None
    for ext in AUDIO_EXTENSIONS:
        candidate = reported.parent / f"{reported.stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


class _LoggerAdapter:
    """Tidal-dl-ng calls ``fn_logger.info(...)`` etc."""

    def __getattr__(self, name: str) -> Any:
        return getattr(logger, name)


class TidalDownloader:
    """Downloads single tracks with tidal-dl-ng, using our Tidal session."""

    def __init__(
        self,
        config_dir: Path,
        tidal_session: Any,
        quality: str,
        abort_event: Optional[threading.Event] = None,
    ) -> None:
        """Prepare tidal-dl-ng.

        Raises :class:`DownloaderUnavailableError`.
        """
        if not downloader_available():
            raise DownloaderUnavailableError(
                "tidal-dl-ng is not installed, so Cratekeeper cannot download "
                "tracks. Install tidal-dl-ng 0.31 into the same environment."
            )
        redirect_config(config_dir)
        from tidal_dl_ng.config import Settings, Tidal

        settings = Settings()
        data = settings.data
        data.quality_audio = quality
        data.download_dolby_atmos = False
        data.video_download = False
        data.skip_existing = True
        data.metadata_write_url = True
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            data.path_binary_ffmpeg = ffmpeg
        settings.save()

        self._tidal = Tidal(settings)
        session = self._tidal.session
        session.load_oauth_session(
            tidal_session.token_type,
            tidal_session.access_token,
            tidal_session.refresh_token,
            getattr(tidal_session, "expiry_time", None),
        )
        self._tidal.settings_apply(settings)
        self._quality = quality
        self._abort = abort_event or threading.Event()

    def download(self, tidal_id: str, target_dir: Path) -> Path:
        """Download one track into ``target_dir`` and return the real file."""
        from rich.progress import Progress
        from tidal_dl_ng.download import Download

        try:
            track = self._tidal.session.track(int(tidal_id))
        except Exception as exc:
            message = str(exc)
            if "404" in message or "Not Found" in message:
                raise TrackUnavailableError(f"Track {tidal_id}: {message}") from exc
            raise DownloadError(f"Track {tidal_id}: {message}") from exc

        target_dir.mkdir(parents=True, exist_ok=True)
        run = threading.Event()
        run.set()
        downloader = Download(
            self._tidal,
            path_base=str(target_dir),
            fn_logger=_LoggerAdapter(),
            skip_existing=True,
            progress=Progress(),
            event_abort=self._abort,
            event_run=run,
        )
        try:
            ok, reported = downloader.item(
                media=track,
                file_template="{artist_name} - {track_title}",
                video_download=False,
                download_delay=False,
                quality_audio=self._quality,
            )
        except Exception as exc:
            raise DownloadError(f"Track {tidal_id}: {exc}") from exc
        if not ok or not reported:
            raise DownloadError(f"Track {tidal_id}: tidal-dl-ng reported a failure")
        real = resolve_downloaded_file(Path(reported))
        if real is None:
            raise DownloadError(
                f"Track {tidal_id}: no file found at {reported} or with another "
                "audio extension"
            )
        return real
