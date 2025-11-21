"""Tests for the Tidal download service."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.tidal_cleanup.config import Config
from src.tidal_cleanup.services.tidal_download_service import (
    TidalDownloadError,
    TidalDownloadService,
)


@pytest.fixture
def mock_config(tmp_path):
    """Create a mock configuration."""
    config = Mock(spec=Config)
    config.m4a_directory = tmp_path / "m4a"
    config.m4a_directory.mkdir(parents=True)
    config.tidal_token_file = tmp_path / "tidal_token.json"
    return config


@pytest.fixture
def download_service(mock_config):
    """Create a TidalDownloadService instance."""
    return TidalDownloadService(mock_config)


class TestTidalDownloadService:
    """Test cases for TidalDownloadService."""

    def test_init(self, download_service, mock_config):
        """Test service initialization."""
        assert download_service.config == mock_config
        assert not download_service.is_authenticated()
        assert download_service.tidal_dl is None

    def test_create_tidal_dl_settings(self, download_service, mock_config):
        """Test creation of tidal-dl-ng settings."""
        settings = download_service._create_tidal_dl_settings()

        assert settings.download_base_path == str(mock_config.m4a_directory)
        assert settings.skip_existing is True
        assert settings.video_download is False
        assert "Playlists" in settings.format_playlist

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    def test_connect_with_existing_token(self, mock_tidal_dl, download_service):
        """Test connection with existing valid token."""
        mock_instance = Mock()
        mock_instance.login_token.return_value = True
        mock_tidal_dl.return_value = mock_instance

        download_service.connect()

        assert download_service.is_authenticated()
        mock_instance.login_token.assert_called_once()

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    def test_connect_without_token(self, mock_tidal_dl, download_service):
        """Test connection requiring interactive login."""
        mock_instance = Mock()
        mock_instance.login_token.return_value = False
        mock_instance.login.return_value = True
        mock_tidal_dl.return_value = mock_instance

        download_service.connect()

        assert download_service.is_authenticated()
        mock_instance.login_token.assert_called_once()
        mock_instance.login.assert_called_once()

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    def test_connect_failure(self, mock_tidal_dl, download_service):
        """Test connection failure."""
        mock_instance = Mock()
        mock_instance.login_token.return_value = False
        mock_instance.login.return_value = False
        mock_tidal_dl.return_value = mock_instance

        with pytest.raises(TidalDownloadError, match="Failed to authenticate"):
            download_service.connect()

        assert not download_service.is_authenticated()

    def test_download_playlist_not_authenticated(self, download_service):
        """Test download fails when not authenticated."""
        with pytest.raises(TidalDownloadError, match="Not authenticated"):
            download_service.download_playlist("Test Playlist")

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    @patch("src.tidal_cleanup.services.tidal_download_service.Download")
    def test_download_playlist_success(
        self, mock_download, mock_tidal_dl, download_service, mock_config
    ):
        """Test successful playlist download."""
        # Setup mocks
        mock_tidal_instance = Mock()
        mock_tidal_dl.return_value = mock_tidal_instance

        mock_playlist = Mock()
        mock_playlist.name = "Test Playlist"
        mock_playlist.id = "12345"
        mock_playlist.num_tracks = 2

        mock_track1 = Mock()
        mock_track1.name = "Track 1"
        mock_track1.artist = Mock(name="Artist 1")

        mock_track2 = Mock()
        mock_track2.name = "Track 2"
        mock_track2.artist = Mock(name="Artist 2")

        mock_playlist.tracks.return_value = [mock_track1, mock_track2]

        mock_user = Mock()
        mock_user.playlists.return_value = [mock_playlist]
        mock_tidal_instance.session.user = mock_user

        # Setup download instance
        mock_dl_instance = Mock()
        mock_dl_instance.item.return_value = (True, Path("/path/to/track"))
        mock_download.return_value = mock_dl_instance

        # Authenticate and download
        download_service.connect()
        playlist_dir = download_service.download_playlist("Test Playlist")

        # Verify
        expected_dir = mock_config.m4a_directory / "Playlists" / "Test Playlist"
        assert playlist_dir == expected_dir
        assert playlist_dir.exists()
        assert mock_dl_instance.item.call_count == 2

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    def test_download_playlist_not_found(self, mock_tidal_dl, download_service):
        """Test download fails when playlist not found."""
        # Setup mocks
        mock_tidal_instance = Mock()
        mock_tidal_dl.return_value = mock_tidal_instance

        mock_playlist = Mock()
        mock_playlist.name = "Other Playlist"
        mock_playlist.id = "12345"

        mock_user = Mock()
        mock_user.playlists.return_value = [mock_playlist]
        mock_tidal_instance.session.user = mock_user

        # Authenticate and attempt download
        download_service.connect()

        with pytest.raises(TidalDownloadError, match="not found"):
            download_service.download_playlist("Test Playlist")

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    @patch("src.tidal_cleanup.services.tidal_download_service.Download")
    def test_download_all_playlists(
        self, mock_download, mock_tidal_dl, download_service, mock_config
    ):
        """Test downloading all playlists."""
        # Setup mocks
        mock_tidal_instance = Mock()
        mock_tidal_dl.return_value = mock_tidal_instance

        mock_playlist1 = Mock()
        mock_playlist1.name = "Playlist 1"
        mock_playlist1.id = "1"
        mock_playlist1.num_tracks = 1
        mock_playlist1.tracks.return_value = [Mock()]

        mock_playlist2 = Mock()
        mock_playlist2.name = "Playlist 2"
        mock_playlist2.id = "2"
        mock_playlist2.num_tracks = 1
        mock_playlist2.tracks.return_value = [Mock()]

        mock_user = Mock()
        mock_user.playlists.return_value = [mock_playlist1, mock_playlist2]
        mock_tidal_instance.session.user = mock_user

        # Setup download instance
        mock_dl_instance = Mock()
        mock_dl_instance.item.return_value = (True, Path("/path/to/track"))
        mock_download.return_value = mock_dl_instance

        # Authenticate and download
        download_service.connect()
        playlist_dirs = download_service.download_all_playlists()

        # Verify
        assert len(playlist_dirs) == 2
        assert all(d.exists() for d in playlist_dirs)


class TestLoggerAdapter:
    """Test the logger adapter."""

    def test_logger_adapter_debug(self):
        """Test debug logging."""
        import logging

        from src.tidal_cleanup.services.tidal_download_service import _LoggerAdapter

        mock_logger = Mock(spec=logging.Logger)
        adapter = _LoggerAdapter(mock_logger)

        adapter.debug("test message")
        mock_logger.debug.assert_called_once_with("test message")

    def test_logger_adapter_info(self):
        """Test info logging."""
        import logging

        from src.tidal_cleanup.services.tidal_download_service import _LoggerAdapter

        mock_logger = Mock(spec=logging.Logger)
        adapter = _LoggerAdapter(mock_logger)

        adapter.info("test message")
        mock_logger.info.assert_called_once_with("test message")

    def test_logger_adapter_warning(self):
        """Test warning logging."""
        import logging

        from src.tidal_cleanup.services.tidal_download_service import _LoggerAdapter

        mock_logger = Mock(spec=logging.Logger)
        adapter = _LoggerAdapter(mock_logger)

        adapter.warning("test message")
        mock_logger.warning.assert_called_once_with("test message")

    def test_logger_adapter_error(self):
        """Test error logging."""
        import logging

        from src.tidal_cleanup.services.tidal_download_service import _LoggerAdapter

        mock_logger = Mock(spec=logging.Logger)
        adapter = _LoggerAdapter(mock_logger)

        adapter.error("test message")
        mock_logger.error.assert_called_once_with("test message")

    def test_logger_adapter_exception(self):
        """Test exception logging."""
        import logging

        from src.tidal_cleanup.services.tidal_download_service import _LoggerAdapter

        mock_logger = Mock(spec=logging.Logger)
        adapter = _LoggerAdapter(mock_logger)

        adapter.exception("test message")
        mock_logger.exception.assert_called_once_with("test message")
