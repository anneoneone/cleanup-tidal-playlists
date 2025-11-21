"""Tests for the Tidal download service."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

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

        # Settings object has a .data attribute that holds the actual config
        assert settings is not None
        assert hasattr(settings, "data")
        # The actual values depend on whether config files exist,
        # so we just verify the settings object is properly created

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

        # Setup download instance - uses items() method for playlists
        mock_dl_instance = Mock()
        mock_dl_instance.items.return_value = None  # items() returns None
        mock_download.return_value = mock_dl_instance

        # Authenticate and download
        download_service.connect()
        playlist_dir = download_service.download_playlist("Test Playlist")

        # Verify
        expected_dir = mock_config.m4a_directory / "Playlists" / "Test Playlist"
        assert playlist_dir == expected_dir
        assert playlist_dir.exists()
        # Verify items() was called once for the playlist download
        assert mock_dl_instance.items.call_count == 1

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


class TestRetryLogic:
    """Test retry logic for API calls."""

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    def test_retry_api_call_success_first_attempt(
        self, mock_tidal_dl, download_service
    ):
        """Test successful API call on first attempt."""
        mock_func = Mock(return_value="success")
        result = download_service._retry_api_call(mock_func)
        assert result == "success"
        assert mock_func.call_count == 1

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    @patch("src.tidal_cleanup.services.tidal_download_service.time.sleep")
    def test_retry_api_call_success_after_retry(
        self, mock_sleep, mock_tidal_dl, download_service
    ):
        """Test successful API call after retries."""
        mock_response = Mock()
        mock_response.status_code = 500

        error = requests.exceptions.HTTPError(response=mock_response)
        mock_func = Mock(side_effect=[error, error, "success"])

        result = download_service._retry_api_call(
            mock_func, max_retries=3, base_delay=1.0
        )
        assert result == "success"
        assert mock_func.call_count == 3
        assert mock_sleep.call_count == 2  # Slept twice before success

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    @patch("src.tidal_cleanup.services.tidal_download_service.time.sleep")
    def test_retry_api_call_exhausted_retries(
        self, mock_sleep, mock_tidal_dl, download_service
    ):
        """Test API call fails after exhausting all retries."""
        mock_response = Mock()
        mock_response.status_code = 503

        error = requests.exceptions.HTTPError(response=mock_response)
        mock_func = Mock(side_effect=error)

        with pytest.raises(TidalDownloadError):
            download_service._retry_api_call(mock_func, max_retries=2, base_delay=0.1)

        assert mock_func.call_count == 3  # Initial + 2 retries
        assert mock_sleep.call_count == 2

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    def test_retry_api_call_non_retryable_error(self, mock_tidal_dl, download_service):
        """Test non-5xx errors are not retried."""
        mock_response = Mock()
        mock_response.status_code = 404

        error = requests.exceptions.HTTPError(response=mock_response)
        mock_func = Mock(side_effect=error)

        with pytest.raises(TidalDownloadError):
            download_service._retry_api_call(mock_func)

        assert mock_func.call_count == 1  # No retries for 4xx

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    def test_retry_api_call_generic_exception(self, mock_tidal_dl, download_service):
        """Test generic exceptions are not retried."""
        mock_func = Mock(side_effect=ValueError("test error"))

        with pytest.raises(TidalDownloadError, match="test error"):
            download_service._retry_api_call(mock_func)

        assert mock_func.call_count == 1


class TestConfigLoading:
    """Test configuration loading priority."""

    def test_create_settings_with_project_config(self, download_service, tmp_path):
        """Test loading from project config file."""
        settings = download_service._create_tidal_dl_settings()

        # If project config exists, it should be loaded
        assert settings is not None
        assert hasattr(settings, "data")

    def test_create_settings_returns_none_when_not_installed(self, mock_config):
        """Test settings creation when tidal-dl-ng is not installed."""
        with patch(
            "src.tidal_cleanup.services.tidal_download_service.TidalDLSettings",
            None,
        ):
            service = TidalDownloadService(mock_config)
            settings = service._create_tidal_dl_settings()
            assert settings is None


class TestDownloadEdgeCases:
    """Test edge cases in download methods."""

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    @patch("src.tidal_cleanup.services.tidal_download_service.Download")
    def test_download_playlist_with_slash_in_name(
        self, mock_download, mock_tidal_dl, download_service, mock_config
    ):
        """Test playlist name with forward slash is sanitized."""
        mock_tidal_instance = Mock()
        mock_tidal_dl.return_value = mock_tidal_instance

        mock_playlist = Mock()
        mock_playlist.name = "2025/11 Tech House"
        mock_playlist.id = "12345"
        mock_playlist.num_tracks = 1
        mock_playlist.tracks.return_value = [Mock()]

        mock_user = Mock()
        mock_user.playlists.return_value = [mock_playlist]
        mock_tidal_instance.session.user = mock_user

        mock_dl_instance = Mock()
        mock_dl_instance.items.return_value = None
        mock_download.return_value = mock_dl_instance

        download_service.connect()
        playlist_dir = download_service.download_playlist("2025/11 Tech House")

        # Verify slash was replaced with dash
        expected_dir = mock_config.m4a_directory / "Playlists" / "2025-11 Tech House"
        assert playlist_dir == expected_dir

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    def test_download_all_playlists_partial_failure(
        self, mock_tidal_dl, download_service, mock_config
    ):
        """Test downloading all playlists continues after individual failures."""
        mock_tidal_instance = Mock()
        mock_tidal_dl.return_value = mock_tidal_instance

        mock_playlist1 = Mock()
        mock_playlist1.name = "Good Playlist"
        mock_playlist2 = Mock()
        mock_playlist2.name = "Bad Playlist"

        mock_user = Mock()
        mock_user.playlists.return_value = [mock_playlist1, mock_playlist2]
        mock_tidal_instance.session.user = mock_user

        download_service.connect()

        # Make download_playlist fail for second playlist
        call_count = [0]

        def side_effect_download(name, create_directory=False):
            call_count[0] += 1
            if call_count[0] == 2:
                raise TidalDownloadError("Simulated failure")
            return mock_config.m4a_directory / "Playlists" / name

        with patch.object(
            download_service,
            "download_playlist",
            side_effect=side_effect_download,
        ):
            result = download_service.download_all_playlists()

        # Should have one successful download despite one failure
        assert len(result) == 1

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    def test_download_all_playlists_not_authenticated(
        self, mock_tidal_dl, download_service
    ):
        """Test download_all_playlists fails when not authenticated."""
        with pytest.raises(TidalDownloadError, match="Not authenticated"):
            download_service.download_all_playlists()

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    @patch("src.tidal_cleanup.services.tidal_download_service.Download")
    def test_download_playlist_without_creating_directory(
        self, mock_download, mock_tidal_dl, download_service, mock_config
    ):
        """Test downloading without creating directory."""
        mock_tidal_instance = Mock()
        mock_tidal_dl.return_value = mock_tidal_instance

        mock_playlist = Mock()
        mock_playlist.name = "Test Playlist"
        mock_playlist.id = "12345"
        mock_playlist.num_tracks = 1
        mock_playlist.tracks.return_value = [Mock()]

        mock_user = Mock()
        mock_user.playlists.return_value = [mock_playlist]
        mock_tidal_instance.session.user = mock_user

        mock_dl_instance = Mock()
        mock_dl_instance.items.return_value = None
        mock_download.return_value = mock_dl_instance

        download_service.connect()

        # Pre-create the directory
        expected_dir = mock_config.m4a_directory / "Playlists" / "Test Playlist"
        expected_dir.mkdir(parents=True, exist_ok=True)

        playlist_dir = download_service.download_playlist(
            "Test Playlist", create_directory=True
        )

        assert playlist_dir == expected_dir
        assert playlist_dir.exists()

    @patch("src.tidal_cleanup.services.tidal_download_service.TidalDL")
    @patch("src.tidal_cleanup.services.tidal_download_service.Download")
    def test_download_playlist_tracks_raises_on_error(
        self, mock_download, mock_tidal_dl, download_service, mock_config
    ):
        """Test _download_playlist_tracks handles errors."""
        mock_tidal_instance = Mock()
        mock_tidal_dl.return_value = mock_tidal_instance

        mock_playlist = Mock()
        mock_playlist.name = "Test Playlist"
        mock_playlist.id = "12345"
        mock_playlist.num_tracks = 1
        mock_playlist.tracks.return_value = [Mock()]

        mock_user = Mock()
        mock_user.playlists.return_value = [mock_playlist]
        mock_tidal_instance.session.user = mock_user

        # Make Download.items() raise an exception
        mock_dl_instance = Mock()
        mock_dl_instance.items.side_effect = Exception("Download failed")
        mock_download.return_value = mock_dl_instance

        download_service.connect()

        with pytest.raises(TidalDownloadError, match="Track download failed"):
            download_service.download_playlist("Test Playlist")


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
