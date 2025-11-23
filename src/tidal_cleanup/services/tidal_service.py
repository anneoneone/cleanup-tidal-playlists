"""Tidal API service with modern error handling and session management."""

import json
import logging
import time
from pathlib import Path
from typing import Any, List, Optional

import tidalapi
from tidalapi.exceptions import AuthenticationError

from ..database.models import Playlist, Track

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
        self.session.login_oauth_simple()
        print("Please follow the authentication instructions in your browser.")

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
        if self.session is None:
            raise TidalConnectionError("No active session to save")

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
        """Get all user playlists from Tidal with complete metadata.

        Returns:
            List of Playlist objects with all Tidal metadata

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
                # Extract creator information
                creator_name = None
                creator_id = None
                if hasattr(tidal_playlist, "creator") and tidal_playlist.creator:
                    creator = tidal_playlist.creator
                    if hasattr(creator, "name"):
                        creator_name = creator.name
                    if hasattr(creator, "id"):
                        creator_id = str(creator.id)

                # Extract picture URLs
                picture_url = None
                square_picture_url = None
                if hasattr(tidal_playlist, "picture") and tidal_playlist.picture:
                    picture_url = tidal_playlist.picture
                if (
                    hasattr(tidal_playlist, "square_picture")
                    and tidal_playlist.square_picture
                ):
                    square_picture_url = tidal_playlist.square_picture

                playlist = Playlist(
                    name=tidal_playlist.name,
                    description=tidal_playlist.description,
                    tidal_id=str(tidal_playlist.id),
                    creator_name=creator_name,
                    creator_id=creator_id,
                    duration=getattr(tidal_playlist, "duration", None),
                    num_tracks=getattr(tidal_playlist, "num_tracks", None),
                    num_videos=getattr(tidal_playlist, "num_videos", None),
                    popularity=getattr(tidal_playlist, "popularity", None),
                    public=getattr(tidal_playlist, "public", None),
                    picture_url=picture_url,
                    square_picture_url=square_picture_url,
                    created=getattr(tidal_playlist, "created", None),
                    last_updated=getattr(tidal_playlist, "last_updated", None),
                    last_item_added_at=getattr(
                        tidal_playlist, "last_item_added_at", None
                    ),
                    share_url=getattr(tidal_playlist, "share_url", None),
                    listen_url=getattr(tidal_playlist, "listen_url", None),
                )
                playlists.append(playlist)

            logger.info(f"Retrieved {len(playlists)} playlists from Tidal")
            return playlists

        except Exception as e:
            logger.error(f"Failed to retrieve playlists: {e}")
            raise TidalConnectionError(f"Cannot retrieve playlists: {e}")

    def get_playlist_tracks(self, playlist_id: str) -> List[Track]:
        """Get tracks for a specific playlist with complete metadata.

        Args:
            playlist_id: Tidal playlist ID

        Returns:
            List of Track objects with all Tidal metadata

        Raises:
            TidalConnectionError: If not authenticated or API error
        """
        if not self._authenticated or not self.session:
            raise TidalConnectionError("Not authenticated with Tidal")

        try:
            # Get playlist by ID
            playlist = self.session.playlist(playlist_id)
            tidal_tracks = playlist.tracks()

            tracks = [self._extract_track_metadata(t) for t in tidal_tracks]

            logger.info(f"Retrieved {len(tracks)} tracks from playlist {playlist_id}")
            return tracks

        except Exception as e:
            logger.error(f"Failed to retrieve tracks for playlist {playlist_id}: {e}")
            raise TidalConnectionError(
                f"Cannot retrieve tracks for playlist {playlist_id}: {e}"
            )

    def _extract_track_metadata(self, tidal_track: Any) -> Track:
        """Extract all metadata from a Tidal track.

        Args:
            tidal_track: Tidal track object from tidalapi

        Returns:
            Track object with all metadata
        """
        # Extract album metadata
        album_metadata = self._extract_album_metadata(tidal_track.album)

        # Extract artist name (primary artist)
        artist_name = "Unknown Artist"
        if tidal_track.artist:
            artist_name = getattr(tidal_track.artist, "name", "Unknown Artist")

        # Extract audio quality information
        audio_quality = getattr(tidal_track, "audio_quality", None)
        audio_modes = None
        if hasattr(tidal_track, "audio_modes"):
            audio_modes_list = getattr(tidal_track, "audio_modes", None)
            if audio_modes_list:
                audio_modes = ", ".join(audio_modes_list)

        return Track(
            # Basic metadata
            title=tidal_track.name,
            artist=artist_name,
            album=album_metadata["name"],
            album_artist=album_metadata["artist"],
            year=album_metadata["year"],
            duration=getattr(tidal_track, "duration", None),
            tidal_id=str(tidal_track.id),
            # Tidal-specific metadata
            track_number=getattr(tidal_track, "track_num", None),
            volume_number=getattr(tidal_track, "volume_num", None),
            explicit=getattr(tidal_track, "explicit", None),
            popularity=getattr(tidal_track, "popularity", None),
            copyright=getattr(tidal_track, "copyright", None),
            tidal_release_date=getattr(tidal_track, "tidal_release_date", None),
            audio_quality=audio_quality,
            audio_modes=audio_modes,
            version=getattr(tidal_track, "version", None),
            isrc=getattr(tidal_track, "isrc", None),
            # Album metadata
            album_upc=album_metadata["upc"],
            album_release_date=album_metadata["release_date"],
            album_cover_url=album_metadata["cover_url"],
        )

    def _extract_album_metadata(self, album: Optional[Any]) -> dict[str, Optional[Any]]:
        """Extract album metadata from Tidal album object.

        Args:
            album: Tidal album object

        Returns:
            Dictionary with album metadata
        """
        if not album:
            return {
                "name": None,
                "artist": None,
                "year": None,
                "upc": None,
                "release_date": None,
                "cover_url": None,
            }

        # Extract year
        year = None
        release_date = None
        if hasattr(album, "year") and album.year:
            year = album.year
        elif hasattr(album, "release_date") and album.release_date:
            release_date = album.release_date
            year = release_date.year if release_date else None

        # Extract album artist
        album_artist = None
        if hasattr(album, "artist") and album.artist:
            album_artist = getattr(album.artist, "name", None)

        return {
            "name": getattr(album, "name", None),
            "artist": album_artist,
            "year": year,
            "upc": getattr(album, "upc", None),
            "release_date": release_date,
            "cover_url": getattr(album, "image", None),
        }

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
