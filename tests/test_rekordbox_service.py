"""Tests for Rekordbox service."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tidal_cleanup.core.rekordbox.service import RekordboxService


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
    with patch("tidal_cleanup.core.rekordbox.service.PYREKORDBOX_AVAILABLE", True):
        service = RekordboxService(config=mock_config)
        return service


class TestRekordboxService:
    """Test Rekordbox service functionality."""

    def test_init_without_config(self):
        """Test initialization without config."""
        with patch("tidal_cleanup.core.rekordbox.service.PYREKORDBOX_AVAILABLE", True):
            service = RekordboxService()
            assert service.config is None

    def test_init_with_config(self, mock_config):
        """Test initialization with config."""
        with patch("tidal_cleanup.core.rekordbox.service.PYREKORDBOX_AVAILABLE", True):
            service = RekordboxService(config=mock_config)
            assert service.config == mock_config

    def test_db_property_creates_connection(self, rekordbox_service):
        """Test database property creates connection lazily."""
        with patch(
            "tidal_cleanup.core.rekordbox.service.Rekordbox6Database"
        ) as mock_db_class:
            mock_db_instance = Mock()
            mock_db_class.return_value = mock_db_instance

            db = rekordbox_service.db

            assert db == mock_db_instance
            mock_db_class.assert_called_once()

    def test_db_property_without_pyrekordbox(self, mock_config):
        """Test database property returns None without pyrekordbox."""
        with patch("tidal_cleanup.core.rekordbox.service.PYREKORDBOX_AVAILABLE", False):
            service = RekordboxService(config=mock_config)
            db = service.db

            assert db is None

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
