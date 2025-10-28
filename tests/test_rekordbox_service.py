"""Tests for Rekordbox service."""

from pathlib import Path
from unittest.mock import Mock, PropertyMock, patch

import pytest

from src.tidal_cleanup.services.rekordbox_service import RekordboxService


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = Mock()
    config.mp3_directory = Path("/music")
    return config


@pytest.fixture
def mock_db():
    """Create a mock Rekordbox database."""
    db = Mock()
    return db


@pytest.fixture
def rekordbox_service(mock_config):
    """Create RekordboxService with mocked config."""
    with patch(
        "src.tidal_cleanup.services.rekordbox_service.PYREKORDBOX_AVAILABLE", True
    ):
        service = RekordboxService(config=mock_config)
        return service


class TestRekordboxService:
    """Test Rekordbox service functionality."""

    def test_init_without_config(self):
        """Test initialization without config."""
        with patch(
            "src.tidal_cleanup.services.rekordbox_service.PYREKORDBOX_AVAILABLE", True
        ):
            service = RekordboxService()
            assert service.config is None
            assert service.track_id_counter == 1

    def test_init_with_config(self, mock_config):
        """Test initialization with config."""
        with patch(
            "src.tidal_cleanup.services.rekordbox_service.PYREKORDBOX_AVAILABLE", True
        ):
            service = RekordboxService(config=mock_config)
            assert service.config == mock_config

    def test_db_property_creates_connection(self, rekordbox_service):
        """Test database property creates connection lazily."""
        with patch(
            "src.tidal_cleanup.services.rekordbox_service.Rekordbox6Database"
        ) as mock_db_class:
            mock_db_instance = Mock()
            mock_db_class.return_value = mock_db_instance

            db = rekordbox_service.db

            assert db == mock_db_instance
            mock_db_class.assert_called_once()

    def test_db_property_without_pyrekordbox(self, mock_config):
        """Test database property returns None without pyrekordbox."""
        with patch(
            "src.tidal_cleanup.services.rekordbox_service.PYREKORDBOX_AVAILABLE", False
        ):
            service = RekordboxService(config=mock_config)
            db = service.db

            assert db is None

    def test_sync_playlist_with_mytags_success(self, rekordbox_service):
        """Test successful playlist sync with MyTags."""
        playlist_name = "Jazz Mix"
        emoji_config = Path("/config/emoji.yaml")

        # Mock database and synchronizer
        mock_db = Mock()
        mock_synchronizer = Mock()
        mock_synchronizer.sync_playlist.return_value = {
            "tracks_added": 5,
            "tracks_removed": 2,
        }

        # Mock the _db attribute directly (db is a property)
        rekordbox_service._db = mock_db

        with patch(
            "src.tidal_cleanup.services.rekordbox_service."
            "RekordboxPlaylistSynchronizer",
            return_value=mock_synchronizer,
        ):
            result = rekordbox_service.sync_playlist_with_mytags(
                playlist_name, emoji_config
            )

            assert result["tracks_added"] == 5
            assert result["tracks_removed"] == 2
            mock_synchronizer.sync_playlist.assert_called_once()

    def test_sync_playlist_requires_database(self, rekordbox_service):
        """Test sync fails without database."""
        # Set _db to None and prevent auto-creation by mocking the property
        rekordbox_service._db = None
        with patch.object(
            type(rekordbox_service), "db", new_callable=PropertyMock, return_value=None
        ), pytest.raises(RuntimeError, match="Database connection not available"):
            rekordbox_service.sync_playlist_with_mytags("Jazz Mix")

    def test_sync_playlist_requires_config(self, rekordbox_service):
        """Test sync fails without config."""
        rekordbox_service.config = None
        rekordbox_service._db = Mock()

        with pytest.raises(RuntimeError, match="Config not available"):
            rekordbox_service.sync_playlist_with_mytags("Jazz Mix")

    def test_ensure_genre_party_folders(self, rekordbox_service):
        """Test folder pre-creation."""
        emoji_config = Path("/config/emoji.yaml")

        mock_db = Mock()
        mock_synchronizer = Mock()
        rekordbox_service._db = mock_db

        with patch(
            "src.tidal_cleanup.services.rekordbox_service."
            "RekordboxPlaylistSynchronizer",
            return_value=mock_synchronizer,
        ):
            rekordbox_service.ensure_genre_party_folders(emoji_config)

            mock_synchronizer.ensure_folders_exist.assert_called_once()

    def test_close_database(self, rekordbox_service):
        """Test database closure."""
        mock_db = Mock()
        rekordbox_service._db = mock_db

        rekordbox_service.close()

        mock_db.close.assert_called_once()

    def test_close_without_database(self, rekordbox_service):
        """Test closing without active database connection."""
        rekordbox_service._db = None

        # Should not raise exception
        rekordbox_service.close()
