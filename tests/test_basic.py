"""Basic tests for the refactored Tidal cleanup application."""

from unittest.mock import Mock, patch

import pytest

from src.tidal_cleanup.config import Config
from src.tidal_cleanup.models.models import Playlist, Track
from src.tidal_cleanup.services.track_comparison_service import TrackComparisonService


class TestConfig:
    """Test configuration management."""

    def test_config_creation(self):
        """Test that config can be created with defaults."""
        config = Config()
        assert config.fuzzy_match_threshold == 80
        assert config.interactive_mode is True

    def test_config_validation(self):
        """Test config validation."""
        # This would test directory creation and validation
        pass


class TestTrackModel:
    """Test Track model."""

    def test_track_creation(self):
        """Test track creation."""
        track = Track(title="Test Song", artist="Test Artist", album="Test Album")
        assert track.title == "Test Song"
        assert track.artist == "Test Artist"
        assert track.normalized_name == "test artist - test song"

    def test_track_normalization(self):
        """Test track name normalization."""
        track = Track(
            title="Song Title (Remix)",
            artist="Artist Name feat. Someone",
        )
        # The normalized name should remove extras
        assert "remix" not in track.normalized_name
        assert "feat" not in track.normalized_name


class TestTrackComparisonService:
    """Test track comparison logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = TrackComparisonService(fuzzy_threshold=80)

    def test_normalize_track_name(self):
        """Test track name normalization."""
        # Test basic normalization
        result = self.service.normalize_track_name("Artist - Song Title")
        assert result == "artist - song title"

        # Test remix removal
        result = self.service.normalize_track_name("Artist - Song (Remix)")
        assert "remix" not in result

        # Test feat removal
        result = self.service.normalize_track_name("Artist feat. Someone - Song")
        assert "feat" not in result

    def test_compare_track_sets(self):
        """Test track set comparison."""
        local_tracks = {"artist1 - song1", "artist2 - song2", "artist3 - song3"}
        tidal_tracks = {"artist1 - song1", "artist2 - song2", "artist4 - song4"}

        result = self.service.compare_track_sets(
            local_tracks, tidal_tracks, "Test Playlist"
        )

        assert len(result.matched) == 2  # artist1 and artist2 songs
        assert len(result.local_only) == 1  # artist3 song
        assert len(result.tidal_only) == 1  # artist4 song

    def test_fuzzy_matching(self):
        """Test fuzzy matching functionality."""
        candidates = ["The Beatles - Hey Jude", "Beatles - Let It Be"]

        result = self.service.find_best_match("Beatles - Hey Jude", candidates)

        assert result is not None
        match, score = result
        assert "Hey Jude" in match
        assert score >= 80


class TestPlaylistModel:
    """Test Playlist model."""

    def test_playlist_creation(self):
        """Test playlist creation."""
        tracks = [
            Track(title="Song 1", artist="Artist 1"),
            Track(title="Song 2", artist="Artist 2"),
        ]

        playlist = Playlist(name="Test Playlist", tracks=tracks)

        assert playlist.name == "Test Playlist"
        assert playlist.track_count == 2
        assert len(playlist.get_track_names()) == 2


@pytest.fixture
def mock_tidal_session():
    """Mock Tidal session for testing."""
    session = Mock()
    session.check_login.return_value = True
    return session


class TestTidalService:
    """Test Tidal service integration."""

    @patch("src.tidal_cleanup.services.tidal_service.tidalapi.Session")
    def test_connection_success(self, mock_session_class, tmp_path):
        """Test successful Tidal connection."""
        from src.tidal_cleanup.services.tidal_service import TidalService

        # Create a temporary token file
        token_file = tmp_path / "token.json"
        token_file.write_text(
            '{"token_type": "Bearer", "access_token": "test", "refresh_token": "test"}'
        )

        mock_session = Mock()
        mock_session.check_login.return_value = True
        mock_session_class.return_value = mock_session

        TidalService(token_file)
        # This would test the actual connection logic
        # service.connect()


if __name__ == "__main__":
    pytest.main([__file__])
