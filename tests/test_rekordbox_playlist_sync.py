"""Tests for Rekordbox playlist synchronizer."""

from unittest.mock import Mock, patch

import pytest

from tidal_cleanup.core.rekordbox.playlist_sync import (
    RekordboxPlaylistSynchronizer,
)


@pytest.fixture
def mock_db():
    """Create a mock Rekordbox database."""
    db = Mock()
    db.query = Mock()
    db.add = Mock()
    db.commit = Mock()
    db.flush = Mock()
    db.delete = Mock()
    db.get_playlist = Mock()
    return db


@pytest.fixture
def synchronizer(mock_db, tmp_path):
    """Create a synchronizer with mocked dependencies."""
    mp3_root = tmp_path / "playlists"
    mp3_root.mkdir()
    emoji_config = tmp_path / "emoji.yaml"
    emoji_config.write_text("genre:\n  🎷: Jazz\n", encoding="utf-8")

    with patch(
        "tidal_cleanup.core.rekordbox.playlist_sync." "PYREKORDBOX_AVAILABLE",
        True,
    ), patch(
        "tidal_cleanup.core.rekordbox.playlist_sync.MyTagManager"
    ) as mock_mgr_class, patch(
        "tidal_cleanup.core.rekordbox.playlist_sync.PlaylistNameParser"
    ) as mock_parser_class:
        mock_mgr_class.return_value = Mock()
        mock_parser = Mock()
        mock_parser.folder_structure = {
            "genre_root": "Genre",
            "events_root": "Events",
            "genre_default_status": "Archived",
        }
        mock_parser.genre_uncategorized = "Uncategorized"
        mock_parser.events_misc = "Misc"
        mock_parser_class.return_value = mock_parser

        sync = RekordboxPlaylistSynchronizer(mock_db, mp3_root, emoji_config)
        return sync


class TestRekordboxPlaylistSynchronizer:
    """Test playlist synchronizer functionality."""

    def test_init_requires_pyrekordbox(self, mock_db, tmp_path):
        """Test initialization fails without pyrekordbox."""
        with patch(
            "tidal_cleanup.core.rekordbox.playlist_sync." "PYREKORDBOX_AVAILABLE",
            False,
        ), pytest.raises(RuntimeError, match="pyrekordbox is not available"):
            RekordboxPlaylistSynchronizer(
                mock_db, tmp_path / "playlists", tmp_path / "emoji.yaml"
            )

    def test_ensure_folders_exist_creates_all_folders(self, synchronizer, mock_db):
        """Test pre-creation of all genre/party folders."""
        # Create playlist directories
        (synchronizer.mp3_playlists_root / "🎷 Jazz Playlist").mkdir()
        (synchronizer.mp3_playlists_root / "🎉 Party Mix").mkdir()

        # Mock metadata for playlists
        jazz_metadata = Mock()
        jazz_metadata.genre_tags = ["Jazz"]
        jazz_metadata.party_tags = []
        jazz_metadata.status_tags = []

        party_metadata = Mock()
        party_metadata.genre_tags = ["House"]
        party_metadata.party_tags = ["Party"]
        party_metadata.status_tags = []

        synchronizer.name_parser.parse_playlist_name.side_effect = [
            jazz_metadata,
            party_metadata,
        ]

        # Mock folder creation
        with patch.object(
            synchronizer, "_get_or_create_folder_path", return_value="folder123"
        ) as mock_create_path:
            synchronizer.ensure_folders_exist()

            # Should create 2 unique folder paths with default status:
            # Genre/Jazz/Archived and Genre/House/Archived
            assert mock_create_path.call_count == 2
            calls = [call.args[0] for call in mock_create_path.call_args_list]
            assert ["Genre", "House", "Archived"] in calls
            assert ["Genre", "Jazz", "Archived"] in calls
            mock_db.commit.assert_called_once()

    def test_get_or_create_folder_creates_new(self, synchronizer, mock_db):
        """Test creating a new folder."""
        # Mock no existing folder found
        mock_query = Mock()
        mock_query.first.return_value = None
        mock_db.get_playlist = Mock(return_value=mock_query)

        # Mock new folder creation
        mock_new_folder = Mock()
        mock_new_folder.ID = "folder123"
        mock_new_folder.Name = "Jazz"
        mock_db.create_playlist_folder = Mock(return_value=mock_new_folder)

        result = synchronizer._get_or_create_folder("Jazz")

        assert result == mock_new_folder
        mock_db.create_playlist_folder.assert_called_once_with("Jazz", parent=None)
        mock_db.flush.assert_called_once()

    def test_get_or_create_folder_retrieves_existing(self, synchronizer, mock_db):
        """Test retrieving an existing folder."""
        # Mock existing folder
        mock_existing_folder = Mock()
        mock_existing_folder.ID = "folder456"
        mock_existing_folder.Name = "Jazz"

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_existing_folder
        mock_db.get_playlist = Mock(return_value=mock_query)

        result = synchronizer._get_or_create_folder("Jazz")

        assert result == mock_existing_folder
        assert not mock_db.add.called

    def test_get_folder_for_playlist_uses_first_genre(self, synchronizer):
        """Test folder determination uses first genre tag."""
        metadata = Mock()
        metadata.genre_tags = {"Jazz", "House"}  # Set, not list
        metadata.party_tags = set()
        metadata.status_tags = set()

        # Mock folder in cache - "House" comes first alphabetically
        synchronizer._folder_cache["Genre/House/Archived"] = "folder123"

        result = synchronizer._get_folder_for_playlist(metadata)

        assert result == "folder123"

    def test_get_folder_for_playlist_fallback_to_party(self, synchronizer):
        """Test folder determination falls back to party tag."""
        metadata = Mock()
        metadata.genre_tags = set()
        metadata.party_tags = {"Party"}
        metadata.event_year = "2023"
        metadata.status_tags = set()

        synchronizer._folder_cache["Events/Party/2023"] = "folder456"

        result = synchronizer._get_folder_for_playlist(metadata)

        assert result == "folder456"

    def test_get_folder_for_playlist_returns_none_without_tags(self, synchronizer):
        """Test folder falls back to Uncategorized when no tags."""
        metadata = Mock()
        metadata.genre_tags = set()
        metadata.party_tags = set()
        metadata.status_tags = set()
        synchronizer._folder_cache["Genre/Uncategorized/Archived"] = "folder999"

        result = synchronizer._get_folder_for_playlist(metadata)

        assert result == "folder999"

    def test_get_or_create_playlist_creates_new(self, synchronizer, mock_db):
        """Test creating a new playlist."""
        # Mock no existing playlist
        mock_query = Mock()
        mock_query.filter = Mock(return_value=mock_query)
        mock_query.first.return_value = None
        mock_db.get_playlist = Mock(return_value=mock_query)

        # Mock new playlist
        mock_new_playlist = Mock()
        mock_new_playlist.ID = "playlist123"
        mock_new_playlist.Name = "Jazz Mix"
        mock_db.create_playlist = Mock(return_value=mock_new_playlist)

        result = synchronizer._get_or_create_playlist("Jazz Mix", "folder123")

        assert result == mock_new_playlist
        mock_db.create_playlist.assert_called_once_with("Jazz Mix", parent="folder123")
        mock_db.flush.assert_called_once()

    def test_get_or_create_playlist_retrieves_existing(self, synchronizer, mock_db):
        """Test retrieving existing playlist."""
        # Mock existing playlist
        mock_existing = Mock()
        mock_existing.ID = "playlist123"
        mock_existing.Name = "Jazz Mix"
        mock_existing.ParentID = "old_folder"

        mock_query = Mock()
        mock_query.filter = Mock(return_value=mock_query)
        mock_query.first.return_value = mock_existing
        mock_db.get_playlist = Mock(return_value=mock_query)
        mock_db.move_playlist = Mock()

        result = synchronizer._get_or_create_playlist("Jazz Mix", "new_folder")

        assert result == mock_existing
        # Should call move_playlist
        mock_db.move_playlist.assert_called_once_with(
            mock_existing, parent="new_folder"
        )
        mock_db.flush.assert_called_once()

    def test_scan_mp3_folder(self, synchronizer, tmp_path):
        """Test scanning MP3 folder for audio files."""
        folder = synchronizer.mp3_playlists_root / "test_playlist"
        folder.mkdir()

        # Create test files
        (folder / "track1.mp3").write_text("fake mp3")
        (folder / "track2.flac").write_text("fake flac")
        (folder / "readme.txt").write_text("not audio")

        results = synchronizer._scan_mp3_folder(folder)

        assert len(results) == 2
        assert any(p.name == "track1.mp3" for p in results)
        assert any(p.name == "track2.flac" for p in results)

    def test_find_content_by_path_or_metadata(self, synchronizer, mock_db):
        """Test finding content by path or metadata."""
        track_path = "/music/track.mp3"

        # Mock track found
        mock_track = Mock()
        mock_track.Title = "Track"
        mock_query = Mock()
        mock_query.first.return_value = mock_track
        mock_db.get_content = Mock(return_value=mock_query)

        result = synchronizer._find_content_by_path_or_metadata(track_path)

        assert result == mock_track

    def test_sync_playlist_full_workflow(self, synchronizer, mock_db, tmp_path):
        """Test complete sync workflow."""
        # Create playlist directory
        playlist_dir = synchronizer.mp3_playlists_root / "Jazz Mix"
        playlist_dir.mkdir()

        # Create test audio file
        track_file = playlist_dir / "track1.mp3"
        track_file.write_text("fake mp3")

        # Mock playlist and track
        mock_playlist = Mock()
        mock_playlist.ID = "playlist123"
        mock_playlist.Name = "Jazz Mix"
        mock_playlist.Songs = []

        mock_track = Mock()
        mock_track.ID = "track1"

        # Create proper PlaylistMetadata mock
        mock_metadata = Mock()
        mock_metadata.genre_tags = {"Jazz"}
        mock_metadata.party_tags = set()
        mock_metadata.energy_tags = set()
        mock_metadata.status_tags = set()
        # all_tags must return a dict
        mock_metadata.all_tags = {
            "Genre": {"Jazz"},
            "Party": set(),
            "Energy": set(),
            "Status": set(),
        }

        # Mock mytag_manager methods
        synchronizer.mytag_manager.get_content_tag_names = Mock(return_value={"Jazz"})
        synchronizer.mytag_manager.remove_no_genre_tag_if_needed = Mock()

        # Mock _refresh_playlist to return the same playlist
        with patch.object(
            synchronizer, "_refresh_playlist", return_value=mock_playlist
        ), patch.object(
            synchronizer, "_get_or_create_playlist", return_value=mock_playlist
        ), patch.object(
            synchronizer, "_get_folder_for_playlist", return_value=None
        ), patch.object(
            synchronizer,
            "_find_content_by_path_or_metadata",
            return_value=mock_track,
        ), patch.object(
            synchronizer, "_scan_mp3_folder", return_value=[track_file]
        ), patch.object(
            synchronizer.name_parser,
            "parse_playlist_name",
            return_value=mock_metadata,
        ), patch.object(
            synchronizer, "_apply_mytags_to_content"
        ):
            result = synchronizer.sync_playlist(playlist_dir.name)

            assert "tracks_added" in result
            assert "tracks_removed" in result

    def test_audio_extensions_property(self, synchronizer):
        """Test supported audio extensions."""
        assert ".mp3" in synchronizer.audio_extensions
        assert ".flac" in synchronizer.audio_extensions
        assert ".wav" in synchronizer.audio_extensions
