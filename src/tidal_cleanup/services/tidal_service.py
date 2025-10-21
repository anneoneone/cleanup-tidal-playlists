"""Tidal API service with modern error handling and session management."""

import json
import logging
import time
from pathlib import Path
from typing import Any, List, Optional

import tidalapi
from tidalapi.exceptions import AuthenticationError

from ..models.models import Playlist, Track

logger = logging.getLogger(__name__)


class TidalConnectionError(Exception):
    """Custom exception for Tidal connection issues."""

    pass


class TidalService:
    """Service for interacting with the Tidal API."""

    def __init__(self, token_file: Path) -> None:
        """Initialize Tidal service.

        Args:
            token_file: Path to the token file for session persistence
        """
        self.token_file = token_file
        self.session: Optional[Any] = None  # tidalapi.Session
        self._authenticated = False

    def connect(self) -> None:
        """Establish connection to Tidal API."""
        try:
            self._load_existing_session()
            if not self._authenticated:
                self._create_new_session()
        except Exception as e:
            logger.error(f"Failed to connect to Tidal: {e}")
            raise TidalConnectionError(f"Cannot connect to Tidal API: {e}")

    def _load_existing_session(self) -> None:
        """Load existing session from token file."""
        if not self.token_file.exists():
            logger.info("No existing token file found")
            return

        try:
            logger.info("Loading existing Tidal session...")
            with open(self.token_file, "r") as file:
                data = json.load(file)

            self.session = tidalapi.Session()
            self.session.load_oauth_session(
                data["token_type"], data["access_token"], data["refresh_token"]
            )

            if self.session.check_login():
                logger.info("Successfully authenticated with existing session")
                self._authenticated = True
            else:
                logger.warning("Existing session is invalid")
                self._remove_invalid_token()

        except (AuthenticationError, KeyError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load existing session: {e}")
            self._remove_invalid_token()
        except Exception as e:
            logger.error(f"Unexpected error loading session: {e}")
            self._remove_invalid_token()

    def _create_new_session(self) -> None:
        """Create new Tidal session with OAuth."""
        logger.info("Creating new Tidal session...")
        self.session = tidalapi.Session()

        print("Please scan the QR code or open the link to authenticate:")
        auth_url = self.session.login_oauth_simple()
        print(auth_url)

        # Wait for authentication
        max_wait_time = 60
        wait_interval = 1

        for _ in range(max_wait_time):
            if self.session.check_login():
                logger.info("Successfully authenticated with new session")
                self._authenticated = True
                self._save_session()
                return
            time.sleep(wait_interval)

        raise TidalConnectionError(
            f"Authentication timeout after {max_wait_time} seconds"
        )

    def _save_session(self) -> None:
        """Save session data to token file."""
        try:
            session_data = {
                "token_type": self.session.token_type,
                "access_token": self.session.access_token,
                "refresh_token": self.session.refresh_token,
            }

            # Ensure parent directory exists
            self.token_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.token_file, "w") as file:
                json.dump(session_data, file, indent=2)

            logger.info(f"Session saved to {self.token_file}")

        except Exception as e:
            logger.error(f"Failed to save session: {e}")

    def _remove_invalid_token(self) -> None:
        """Remove invalid token file."""
        if self.token_file.exists():
            try:
                self.token_file.unlink()
                logger.info("Removed invalid token file")
            except Exception as e:
                logger.error(f"Failed to remove invalid token file: {e}")

    def get_playlists(self) -> List[Playlist]:
        """Get all user playlists from Tidal.

        Returns:
            List of Playlist objects

        Raises:
            TidalConnectionError: If not authenticated or API error
        """
        if not self._authenticated or not self.session:
            raise TidalConnectionError("Not authenticated with Tidal")

        try:
            user = self.session.user
            tidal_playlists = user.playlists()

            playlists = []
            for tidal_playlist in tidal_playlists:
                playlist = Playlist(
                    name=tidal_playlist.name,
                    description=tidal_playlist.description,
                    tidal_id=str(tidal_playlist.id),
                )
                playlists.append(playlist)

            logger.info(f"Retrieved {len(playlists)} playlists from Tidal")
            return playlists

        except Exception as e:
            logger.error(f"Failed to retrieve playlists: {e}")
            raise TidalConnectionError(f"Cannot retrieve playlists: {e}")

    def get_playlist_tracks(self, playlist_id: str) -> List[Track]:
        """Get tracks for a specific playlist.

        Args:
            playlist_id: Tidal playlist ID

        Returns:
            List of Track objects

        Raises:
            TidalConnectionError: If not authenticated or API error
        """
        if not self._authenticated or not self.session:
            raise TidalConnectionError("Not authenticated with Tidal")

        try:
            # Get playlist by ID
            playlist = self.session.playlist(playlist_id)
            tidal_tracks = playlist.tracks()

            tracks = []
            for tidal_track in tidal_tracks:
                track = Track(
                    title=tidal_track.name,
                    artist=tidal_track.artist.name,
                    album=tidal_track.album.name if tidal_track.album else None,
                    duration=tidal_track.duration,
                    tidal_id=str(tidal_track.id),
                )
                tracks.append(track)

            logger.info(f"Retrieved {len(tracks)} tracks from playlist {playlist_id}")
            return tracks

        except Exception as e:
            logger.error(f"Failed to retrieve tracks for playlist {playlist_id}: {e}")
            raise TidalConnectionError(
                f"Cannot retrieve tracks for playlist {playlist_id}: {e}"
            )

    def get_playlist_by_name(self, name: str) -> Optional[Playlist]:
        """Get playlist by name.

        Args:
            name: Playlist name

        Returns:
            Playlist object if found, None otherwise
        """
        playlists = self.get_playlists()
        for playlist in playlists:
            if playlist.name == name:
                return playlist
        return None

    def is_authenticated(self) -> bool:
        """Check if service is authenticated."""
        return self._authenticated and self.session is not None
