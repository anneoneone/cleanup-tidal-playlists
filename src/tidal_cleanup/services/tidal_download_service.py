"""Service for downloading tracks from Tidal using tidal-dl-ng."""

import logging
import time
from pathlib import Path
from typing import Any, Callable, List, Optional

import requests
from tidalapi import Playlist as TidalPlaylist

try:
    from tidal_dl_ng.config import Settings as TidalDLSettings
    from tidal_dl_ng.config import Tidal as TidalDL
    from tidal_dl_ng.download import Download
except ImportError:
    # tidal-dl-ng not installed yet
    TidalDLSettings = None
    TidalDL = None
    Download = None

from ..config import Config

logger = logging.getLogger(__name__)


class TidalDownloadError(Exception):
    """Custom exception for Tidal download issues."""


class TidalDownloadService:
    """Service for downloading tracks from Tidal to local directory."""

    def __init__(self, config: Config) -> None:
        """Initialize Tidal download service.

        Args:
            config: Application configuration
        """
        self.config = config
        self.tidal_dl_settings = self._create_tidal_dl_settings()
        self.tidal_dl: Optional[TidalDL] = None
        self._authenticated = False

    def _create_tidal_dl_settings(self) -> TidalDLSettings:
        """Create tidal-dl-ng settings from available config.

        Priority order:
        1. Project config: <repo_root>/config/tidal_dl_ng.json
        2. User config: ~/.config/tidal_dl_ng/settings.json
        3. Defaults: Create new settings with sensible defaults

        Returns:
            TidalDLSettings configured for this application
        """
        if TidalDLSettings is None:
            return None

        # Check project config first
        repo_root = Path(__file__).resolve().parents[3]
        project_config = repo_root / "config" / "tidal_dl_ng.json"

        # Check user config second
        user_config = Path.home() / ".config" / "tidal_dl_ng" / "settings.json"

        settings = TidalDLSettings()

        if project_config.exists():
            # Use project config (highest priority)
            logger.debug(f"Loading project config: {project_config}")
            settings.read(str(project_config))
        elif user_config.exists():
            # Use user config as fallback
            logger.info(f"Loading user config: {user_config}")
            settings.read(str(user_config))
        else:
            # Use defaults (no config files found)
            logger.info("No config found, using defaults")
            settings.data.download_base_path = str(self.config.m4a_directory)
            settings.data.quality_audio = "HI_RES_LOSSLESS"
            settings.data.skip_existing = True
            settings.data.video_download = False
            settings.data.format_playlist = (
                "Playlists/{playlist_name}/{artist_name} - {track_title}"
            )

        return settings

    def _retry_api_call(
        self, func: Callable[[], Any], max_retries: int = 3, base_delay: float = 1.0
    ) -> Any:
        """Retry API calls with exponential backoff for transient errors.

        Args:
            func: Function to call (should return API result)
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds (doubles each retry)

        Returns:
            Result from the API call

        Raises:
            TidalDownloadError: If all retries fail
        """
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return func()
            except requests.exceptions.HTTPError as e:
                # Only retry on server errors (5xx)
                if e.response and 500 <= e.response.status_code < 600:
                    last_error = e
                    if attempt < max_retries:
                        delay = base_delay * (2**attempt)
                        logger.warning(
                            f"Tidal API error {e.response.status_code}, "
                            f"retrying in {delay:.1f}s... "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(delay)
                        continue
                # Non-retryable error, raise immediately
                raise TidalDownloadError(str(e)) from e
            except Exception as e:
                # Other exceptions are not retried
                raise TidalDownloadError(str(e)) from e

        # All retries exhausted
        raise TidalDownloadError(
            f"API call failed after {max_retries} retries: {last_error}"
        )

    def connect(self) -> None:
        """Establish connection to Tidal API using tidal-dl-ng.

        Uses token-based authentication to avoid repeated logins.

        Raises:
            TidalDownloadError: If connection fails
        """
        try:
            logger.info("Connecting to Tidal via tidal-dl-ng...")
            self.tidal_dl = TidalDL(self.tidal_dl_settings)

            # Try to login using existing token
            if self.tidal_dl.login_token():
                logger.info("Successfully authenticated with existing token")
                self._authenticated = True
            else:
                logger.info("No valid token found, initiating new login...")
                # Perform interactive login
                success = self.tidal_dl.login(fn_print=print)
                if not success:
                    raise TidalDownloadError("Failed to authenticate with Tidal")
                self._authenticated = True

        except Exception as e:
            logger.error(f"Failed to connect to Tidal: {e}")
            raise TidalDownloadError(f"Cannot connect to Tidal: {e}")

    def download_playlist(
        self, playlist_name: str, create_directory: bool = True
    ) -> Path:
        """Download a specific playlist by name.

        Args:
            playlist_name: Name of the playlist to download
            create_directory: Whether to create playlist directory

        Returns:
            Path to the downloaded playlist directory

        Raises:
            TidalDownloadError: If download fails
        """
        if not self._authenticated or not self.tidal_dl:
            raise TidalDownloadError("Not authenticated with Tidal")

        try:
            logger.info(f"Searching for playlist: {playlist_name}")

            # Get user's playlists with retry logic for transient errors
            user = self.tidal_dl.session.user
            playlists = self._retry_api_call(lambda: user.playlists())

            # Find matching playlist
            target_playlist = None
            for playlist in playlists:
                if playlist.name.lower() == playlist_name.lower():
                    target_playlist = playlist
                    break

            if not target_playlist:
                raise TidalDownloadError(
                    f"Playlist '{playlist_name}' not found in your Tidal account"
                )

            logger.info(
                f"Found playlist: {target_playlist.name} "
                f"(ID: {target_playlist.id}, {target_playlist.num_tracks} tracks)"
            )

            # Sanitize playlist name for filesystem (replace problematic characters)
            safe_playlist_name = target_playlist.name.replace("/", "-")

            # Calculate target directory
            playlist_dir: Path = (
                self.config.m4a_directory / "Playlists" / safe_playlist_name
            )

            if create_directory:
                # Only create the directory when it does not already exist.
                if not playlist_dir.exists():
                    playlist_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created playlist directory: {playlist_dir}")
                else:
                    logger.debug(f"Playlist directory already exists: {playlist_dir}")

            # Download the playlist using tidal-dl-ng
            self._download_playlist_tracks(target_playlist, playlist_dir)

            return playlist_dir

        except TidalDownloadError:
            raise
        except Exception as e:
            logger.error(f"Failed to download playlist '{playlist_name}': {e}")
            raise TidalDownloadError(f"Playlist download failed: {e}")

    def download_all_playlists(self) -> List[Path]:
        """Download all playlists from user's Tidal account.

        Returns:
            List of paths to downloaded playlist directories

        Raises:
            TidalDownloadError: If download fails
        """
        if not self._authenticated or not self.tidal_dl:
            raise TidalDownloadError("Not authenticated with Tidal")

        try:
            logger.info("Fetching all playlists from Tidal...")

            user = self.tidal_dl.session.user
            playlists = user.playlists()

            logger.info(f"Found {len(playlists)} playlists")

            downloaded_dirs = []

            for playlist in playlists:
                try:
                    playlist_dir = self.download_playlist(
                        playlist.name, create_directory=True
                    )
                    downloaded_dirs.append(playlist_dir)
                except Exception as e:
                    logger.error(f"Failed to download playlist '{playlist.name}': {e}")
                    # Continue with next playlist
                    continue

            logger.info(
                f"Successfully downloaded "
                f"{len(downloaded_dirs)}/{len(playlists)} playlists"
            )
            return downloaded_dirs

        except TidalDownloadError:
            raise
        except Exception as e:
            logger.error(f"Failed to download playlists: {e}")
            raise TidalDownloadError(f"Playlists download failed: {e}")

    def download_track(
        self, track_id: int, target_path: Path, quality: str | None = None
    ) -> Path:
        """Download a single track by ID to specified location.

        Args:
            track_id: Tidal track ID
            target_path: Target file path for the download
            quality: Audio quality (defaults to settings if None)

        Returns:
            Path to the downloaded track file

        Raises:
            TidalDownloadError: If download fails
        """
        if not self._authenticated or not self.tidal_dl:
            raise TidalDownloadError("Not authenticated with Tidal")

        try:
            logger.info(f"Downloading track {track_id} to {target_path}")

            # Get track from Tidal API (type narrowing for mypy)
            tidal_dl = self.tidal_dl
            track = self._retry_api_call(lambda: tidal_dl.session.track(track_id))

            if not track:
                raise TidalDownloadError(f"Track {track_id} not found on Tidal")

            # Ensure parent directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Create Download instance
            from threading import Event

            from rich.progress import Progress

            fn_logger = _LoggerAdapter(logger)
            progress = Progress()
            event_abort = Event()
            event_run = Event()
            event_run.set()

            dl = Download(
                session=self.tidal_dl.session,
                path_base=str(target_path.parent),
                fn_logger=fn_logger,
                skip_existing=True,
                progress=progress,
                event_abort=event_abort,
                event_run=event_run,
            )

            # Use simple file template (just filename)
            file_template = target_path.name

            # Download the track
            dl.items(
                media=track,
                file_template=file_template,
                video_download=False,
                download_delay=False,
                quality_audio=quality or self.tidal_dl_settings.data.quality_audio,
            )

            logger.info(f"Successfully downloaded track to {target_path}")
            return target_path

        except TidalDownloadError:
            raise
        except Exception as e:
            logger.error(f"Failed to download track {track_id}: {e}")
            raise TidalDownloadError(f"Track download failed: {e}")

    def _download_playlist_tracks(
        self, playlist: TidalPlaylist, target_dir: Path
    ) -> None:
        """Download tracks from a playlist one by one.

        Args:
            playlist: Tidal playlist object
            target_dir: Target directory for downloads

        Raises:
            TidalDownloadError: If download fails
        """
        if not self.tidal_dl:
            raise TidalDownloadError("Not authenticated with Tidal")

        try:
            # Create Download instance with required components
            from threading import Event

            from rich.progress import Progress

            fn_logger = _LoggerAdapter(logger)
            progress = Progress()  # Required by tidal-dl-ng
            event_abort = Event()  # For abort signaling
            event_run = Event()  # For run control
            event_run.set()  # Set to running state

            # Note: Download expects session (tidalapi.Session), not tidal_obj
            # self.tidal_dl is checked above to not be None
            dl = Download(
                session=self.tidal_dl.session,
                path_base=str(target_dir.parent.parent),  # Base path (m4a directory)
                fn_logger=fn_logger,
                skip_existing=True,
                progress=progress,
                event_abort=event_abort,
                event_run=event_run,
            )

            # Get tracks count for logging
            tracks = playlist.tracks()
            logger.info(f"Downloading {len(tracks)} tracks...")

            # Use tidal-dl-ng file template for playlists
            file_template = self.tidal_dl_settings.data.format_playlist

            # Download entire playlist using items() method
            # This properly handles playlist context and template substitution
            dl.items(
                media=playlist,
                file_template=file_template,
                video_download=False,
                download_delay=False,
                quality_audio=self.tidal_dl_settings.data.quality_audio,
            )

            logger.info("Download complete")

        except Exception as e:
            logger.error(f"Failed to download playlist tracks: {e}")
            raise TidalDownloadError(f"Track download failed: {e}")

    def is_authenticated(self) -> bool:
        """Check if service is authenticated.

        Returns:
            True if authenticated, False otherwise
        """
        return self._authenticated and self.tidal_dl is not None


class _LoggerAdapter:
    """Adapter to make standard logger compatible with tidal-dl-ng."""

    def __init__(self, logger_instance: logging.Logger) -> None:
        """Initialize logger adapter.

        Args:
            logger_instance: Python logger instance
        """
        self.logger = logger_instance

    def debug(self, msg: str) -> None:
        """Log debug message."""
        self.logger.debug(msg)

    def info(self, msg: str) -> None:
        """Log info message."""
        self.logger.info(msg)

    def warning(self, msg: str) -> None:
        """Log warning message."""
        self.logger.warning(msg)

    def error(self, msg: str) -> None:
        """Log error message."""
        self.logger.error(msg)

    def exception(self, msg: str) -> None:
        """Log exception message."""
        self.logger.exception(msg)
