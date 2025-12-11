"""Tests for SyncDecisionEngine."""

import tempfile
from pathlib import Path

import pytest

from tidal_cleanup.core.sync.decision_engine import SyncAction, SyncDecisionEngine
from tidal_cleanup.database import DatabaseService, DownloadStatus


# Helper functions
def create_test_track(
    db_service: DatabaseService,
    tidal_id: str = "123456",
    title: str = "Test Track",
    artist: str = "Test Artist",
    download_status: DownloadStatus = DownloadStatus.NOT_DOWNLOADED,
    file_path: str | None = None,
    normalized_name: str | None = None,
) -> int:
    """Create a test track and return its ID."""
    track_data = {
        "tidal_id": tidal_id,
        "title": title,
        "artist": artist,
        "duration": 180,
        "normalized_name": normalized_name or f"{artist} - {title}",
        "download_status": download_status,
    }
    if file_path:
        track_data["file_path"] = file_path

    track = db_service.create_track(track_data)
    return track.id


def create_test_playlist(
    db_service: DatabaseService,
    tidal_uuid: str = "playlist-uuid",
    name: str = "Test Playlist",
) -> int:
    """Create a test playlist and return its ID."""
    playlist = db_service.create_playlist({"tidal_id": tidal_uuid, "name": name})
    return playlist.id


def add_track_to_playlist(
    db_service: DatabaseService,
    playlist_id: int,
    track_id: int,
    is_primary: bool = False,
    symlink_path: str | None = None,
    symlink_valid: bool | None = None,
    in_tidal: bool = True,
) -> int:
    """Add track to playlist and return PlaylistTrack ID."""
    pt = db_service.add_track_to_playlist(
        playlist_id=playlist_id,
        track_id=track_id,
        position=1,
        in_tidal=in_tidal,
    )
    pt_id = pt.id

    # Update is_primary and symlink info if needed
    if is_primary or symlink_path:
        with db_service.get_session() as session:
            # Query for the PlaylistTrack we just created
            from tidal_cleanup.database.models import PlaylistTrack

            pt_obj = session.query(PlaylistTrack).filter_by(id=pt_id).first()
            if pt_obj:
                pt_obj.is_primary = is_primary
                if symlink_path:
                    pt_obj.symlink_path = symlink_path
                    valid = symlink_valid if symlink_valid is not None else True
                    pt_obj.symlink_valid = valid
                session.commit()

    return pt_id


def update_playlist_track(
    db_service: DatabaseService, pt_id: int, **fields: object
) -> None:
    """Update arbitrary PlaylistTrack fields for testing."""

    with db_service.get_session() as session:
        from tidal_cleanup.database.models import PlaylistTrack

        pt_obj = session.query(PlaylistTrack).filter_by(id=pt_id).first()
        if pt_obj:
            for key, value in fields.items():
                setattr(pt_obj, key, value)
            session.commit()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db_service(temp_dir):
    """Create a DatabaseService with a temporary database."""
    db_path = temp_dir / "test.db"
    service = DatabaseService(db_path=str(db_path))
    service.init_db()
    yield service
    service.close()


@pytest.fixture
def music_root(temp_dir):
    """Create a music root directory with Playlists/ subdirectory."""
    music_root = temp_dir / "music"
    music_root.mkdir()
    playlists_dir = music_root / "Playlists"
    playlists_dir.mkdir()
    return music_root


@pytest.fixture
def decision_engine(db_service, music_root):
    """Create a SyncDecisionEngine instance."""
    return SyncDecisionEngine(
        db_service=db_service, music_root=music_root, target_format="mp3"
    )


class TestSyncDecisionEngineInit:
    """Test SyncDecisionEngine initialization."""

    def test_init_with_path(self, db_service, music_root):
        """Test initialization with Path object."""
        engine = SyncDecisionEngine(db_service=db_service, music_root=music_root)
        assert engine.db_service is db_service
        assert engine.music_root == music_root
        assert engine.playlists_root == music_root / "Playlists"

    def test_init_with_string(self, db_service, music_root):
        """Test initialization with string path."""
        engine = SyncDecisionEngine(db_service=db_service, music_root=str(music_root))
        assert engine.db_service is db_service
        assert engine.music_root == music_root
        assert engine.playlists_root == music_root / "Playlists"


class TestDecideDownloadAction:
    """Test download action decisions."""

    def test_track_not_downloaded(self, decision_engine, db_service, music_root):
        """Test decision for track that needs downloading."""
        # Create track and playlist
        track_id = create_test_track(
            db_service,
            download_status=DownloadStatus.NOT_DOWNLOADED,
        )
        playlist_id = create_test_playlist(db_service, name="MyPlaylist")
        pt_id = add_track_to_playlist(db_service, playlist_id, track_id)

        # Analyze
        decisions = decision_engine.analyze_playlist_sync(playlist_id)

        # Should have one download decision
        assert len(decisions.decisions) == 1
        decision = decisions.decisions[0]
        assert decision.action == SyncAction.DOWNLOAD_TRACK
        assert decision.track_id == track_id
        assert decision.playlist_id == playlist_id
        assert decision.playlist_track_id == pt_id
        assert "not yet downloaded" in decision.reason.lower()
        assert decision.target_path is not None
        assert "MyPlaylist" in decision.target_path

        # Check statistics
        assert decisions.tracks_to_download == 1

    def test_track_download_error(self, decision_engine, db_service):
        """Test decision for track with download error."""
        track_id = create_test_track(
            db_service,
            download_status=DownloadStatus.ERROR,
        )
        playlist_id = create_test_playlist(db_service)
        add_track_to_playlist(db_service, playlist_id, track_id)

        decisions = decision_engine.analyze_playlist_sync(playlist_id)

        assert len(decisions.decisions) == 1
        decision = decisions.decisions[0]
        assert decision.action == SyncAction.DOWNLOAD_TRACK
        assert "retry" in decision.reason.lower()
        assert decision.priority == 5

    def test_track_downloaded_but_missing(self, decision_engine, db_service, temp_dir):
        """Test decision for downloaded track with missing file."""
        track_id = create_test_track(
            db_service,
            download_status=DownloadStatus.DOWNLOADED,
            file_path=str(temp_dir / "missing.mp3"),  # File doesn't exist
        )
        playlist_id = create_test_playlist(db_service)
        add_track_to_playlist(db_service, playlist_id, track_id)

        decisions = decision_engine.analyze_playlist_sync(playlist_id)

        assert len(decisions.decisions) == 1
        decision = decisions.decisions[0]
        assert decision.action == SyncAction.DOWNLOAD_TRACK
        assert "missing" in decision.reason.lower()
        assert decision.priority == 8  # Higher priority for missing files

    def test_target_format_used_for_download_path(self, db_service, music_root):
        """Ensure download decisions respect configured target format."""

        track_id = create_test_track(
            db_service,
            download_status=DownloadStatus.NOT_DOWNLOADED,
        )
        playlist_id = create_test_playlist(db_service, name="FormatPlaylist")
        add_track_to_playlist(db_service, playlist_id, track_id)

        engine = SyncDecisionEngine(
            db_service=db_service,
            music_root=music_root,
            target_format="flac",
        )

        decisions = engine.analyze_playlist_sync(playlist_id)
        assert decisions.decisions
        decision = decisions.decisions[0]
        assert decision.target_path is not None
        assert decision.target_path.endswith(".flac")


class TestDecideSymlinkAction:
    """Test symlink action decisions."""

    def test_track_downloaded_is_primary_no_symlink(
        self, decision_engine, db_service, temp_dir
    ):
        """Test no action needed for primary file without symlink."""
        # Create actual file
        file_path = temp_dir / "track.mp3"
        file_path.write_text("audio data")

        track_id = create_test_track(
            db_service,
            download_status=DownloadStatus.DOWNLOADED,
            file_path=str(file_path),
        )
        playlist_id = create_test_playlist(db_service)
        add_track_to_playlist(
            db_service, playlist_id, track_id, is_primary=True  # Primary file
        )

        decisions = decision_engine.analyze_playlist_sync(playlist_id)

        assert len(decisions.decisions) == 1
        decision = decisions.decisions[0]
        assert decision.action == SyncAction.NO_ACTION
        assert "primary file exists" in decision.reason.lower()
        assert decision.priority == 0

    def test_track_primary_has_symlink_should_remove(
        self, decision_engine, db_service, temp_dir
    ):
        """Test removal of symlink from primary file location."""
        file_path = temp_dir / "track.mp3"
        file_path.write_text("audio data")

        track_id = create_test_track(
            db_service,
            download_status=DownloadStatus.DOWNLOADED,
            file_path=str(file_path),
        )
        playlist_id = create_test_playlist(db_service)
        symlink_path = temp_dir / "symlink.mp3"
        add_track_to_playlist(
            db_service,
            playlist_id,
            track_id,
            is_primary=True,
            symlink_path=str(symlink_path),
        )

        decisions = decision_engine.analyze_playlist_sync(playlist_id)

        assert len(decisions.decisions) == 1
        decision = decisions.decisions[0]
        assert decision.action == SyncAction.REMOVE_SYMLINK
        assert "shouldn't have symlink" in decision.reason.lower()
        assert decision.source_path == str(symlink_path)

    def test_track_not_primary_no_symlink_create(
        self, decision_engine, db_service, temp_dir, music_root
    ):
        """Test creation of symlink for non-primary track."""
        file_path = temp_dir / "track.mp3"
        file_path.write_text("audio data")

        track_id = create_test_track(
            db_service,
            download_status=DownloadStatus.DOWNLOADED,
            file_path=str(file_path),
        )
        playlist_id = create_test_playlist(db_service, name="MyPlaylist")
        add_track_to_playlist(
            db_service,
            playlist_id,
            track_id,
            is_primary=False,  # Not primary
            symlink_path=None,  # No symlink yet
        )

        decisions = decision_engine.analyze_playlist_sync(playlist_id)

        assert len(decisions.decisions) == 1
        decision = decisions.decisions[0]
        assert decision.action == SyncAction.CREATE_SYMLINK
        assert "needs symlink" in decision.reason.lower()
        assert decision.source_path is not None
        assert decision.target_path == str(file_path)
        assert "MyPlaylist" in decision.source_path

    def test_track_not_primary_broken_symlink(
        self, decision_engine, db_service, temp_dir
    ):
        """Test update of broken symlink."""
        file_path = temp_dir / "track.mp3"
        file_path.write_text("audio data")

        track_id = create_test_track(
            db_service,
            download_status=DownloadStatus.DOWNLOADED,
            file_path=str(file_path),
        )
        playlist_id = create_test_playlist(db_service)
        symlink_path = temp_dir / "broken_symlink.mp3"
        add_track_to_playlist(
            db_service,
            playlist_id,
            track_id,
            is_primary=False,
            symlink_path=str(symlink_path),
            symlink_valid=False,  # Broken
        )

        decisions = decision_engine.analyze_playlist_sync(playlist_id)

        assert len(decisions.decisions) == 1
        decision = decisions.decisions[0]
        assert decision.action == SyncAction.UPDATE_SYMLINK
        assert "broken" in decision.reason.lower()
        assert decision.source_path == str(symlink_path)
        assert decision.target_path == str(file_path)

    def test_track_not_primary_valid_symlink(
        self, decision_engine, db_service, temp_dir
    ):
        """Test no action needed for valid symlink."""
        file_path = temp_dir / "track.mp3"
        file_path.write_text("audio data")

        track_id = create_test_track(
            db_service,
            download_status=DownloadStatus.DOWNLOADED,
            file_path=str(file_path),
        )
        playlist_id = create_test_playlist(db_service)
        symlink_path = temp_dir / "symlink.mp3"
        add_track_to_playlist(
            db_service,
            playlist_id,
            track_id,
            is_primary=False,
            symlink_path=str(symlink_path),
            symlink_valid=True,  # Valid
        )

        decisions = decision_engine.analyze_playlist_sync(playlist_id)

        assert len(decisions.decisions) == 1
        decision = decisions.decisions[0]
        assert decision.action == SyncAction.NO_ACTION
        assert "valid" in decision.reason.lower()


class TestRemovalDecisions:
    """Test removal actions when tracks leave playlists."""

    def test_remove_symlink_when_not_in_tidal(
        self, decision_engine, db_service, temp_dir, music_root
    ):
        """Symlink entries should be removed when playlist entry disappears."""

        file_path = temp_dir / "source.mp3"
        file_path.write_text("audio data")

        playlist_id = create_test_playlist(db_service, name="RemovedSymlink")
        track_id = create_test_track(
            db_service,
            download_status=DownloadStatus.DOWNLOADED,
            file_path=str(file_path),
        )

        playlist_dir = music_root / "Playlists" / "RemovedSymlink"
        playlist_dir.mkdir(parents=True, exist_ok=True)
        symlink_path = playlist_dir / file_path.name
        symlink_path.symlink_to(file_path)

        pt_id = add_track_to_playlist(
            db_service,
            playlist_id,
            track_id,
            is_primary=False,
            symlink_path=str(symlink_path),
        )
        update_playlist_track(db_service, pt_id, in_tidal=False)

        decisions = decision_engine.analyze_playlist_sync(playlist_id)
        assert decisions.decisions
        decision = decisions.decisions[0]
        assert decision.action == SyncAction.REMOVE_SYMLINK
        assert decision.source_path == str(symlink_path)

    def test_remove_file_when_track_removed_everywhere(
        self, decision_engine, db_service, temp_dir
    ):
        """Primary files should be deleted when no playlists reference them."""

        file_path = temp_dir / "orphan.mp3"
        file_path.write_text("audio data")

        track_id = create_test_track(
            db_service,
            download_status=DownloadStatus.DOWNLOADED,
            file_path=str(file_path),
        )
        playlist_id = create_test_playlist(db_service, name="RemovedFile")
        pt_id = add_track_to_playlist(
            db_service, playlist_id, track_id, is_primary=True
        )

        update_playlist_track(db_service, pt_id, in_tidal=False)

        decisions = decision_engine.analyze_playlist_sync(playlist_id)
        assert decisions.decisions
        decision = decisions.decisions[0]
        assert decision.action == SyncAction.REMOVE_FILE
        assert decision.source_path == str(file_path)


class TestAnalyzeAllPlaylists:
    """Test analyzing all playlists."""

    def test_analyze_multiple_playlists(
        self, decision_engine, db_service, temp_dir, music_root
    ):
        """Test analyzing multiple playlists with different states."""
        # Create two tracks
        file1 = temp_dir / "track1.mp3"
        file1.write_text("audio1")
        track1_id = create_test_track(
            db_service,
            tidal_id="111",
            title="Track 1",
            download_status=DownloadStatus.DOWNLOADED,
            file_path=str(file1),
        )

        track2_id = create_test_track(
            db_service,
            tidal_id="222",
            title="Track 2",
            download_status=DownloadStatus.NOT_DOWNLOADED,
        )

        # Create two playlists
        playlist1_id = create_test_playlist(
            db_service, tidal_uuid="pl1", name="Playlist1"
        )
        playlist2_id = create_test_playlist(
            db_service, tidal_uuid="pl2", name="Playlist2"
        )

        # Add tracks to playlists
        # Playlist 1: track1 (primary, no symlink needed)
        add_track_to_playlist(db_service, playlist1_id, track1_id, is_primary=True)
        # Playlist 2: track1 (not primary, needs symlink) and track2 (needs download)
        add_track_to_playlist(db_service, playlist2_id, track1_id, is_primary=False)
        add_track_to_playlist(db_service, playlist2_id, track2_id, is_primary=True)

        decisions = decision_engine.analyze_all_playlists()

        # Should have 3 decisions
        assert len(decisions.decisions) == 3

        # Check statistics
        summary = decisions.get_summary()
        assert summary["total_decisions"] == 3
        assert summary["tracks_to_download"] == 1  # track2
        assert summary["symlinks_to_create"] == 1  # track1 in playlist2
        assert summary["no_action_needed"] == 1  # track1 in playlist1

    def test_analyze_empty_playlists(self, decision_engine, db_service):
        """Test analyzing when no playlists exist."""
        decisions = decision_engine.analyze_all_playlists()
        assert len(decisions.decisions) == 0
        assert decisions.tracks_to_download == 0


class TestDecisionPrioritization:
    """Test decision prioritization and filtering."""

    def test_get_prioritized_decisions(self, decision_engine, db_service, temp_dir):
        """Test getting decisions sorted by priority."""
        # Create tracks with different priorities
        file_path = temp_dir / "track.mp3"
        file_path.write_text("audio")

        # Track 1: needs download (priority 10)
        track1_id = create_test_track(
            db_service,
            tidal_id="111",
            download_status=DownloadStatus.NOT_DOWNLOADED,
        )

        # Track 2: downloaded but missing (priority 8)
        track2_id = create_test_track(
            db_service,
            tidal_id="222",
            download_status=DownloadStatus.DOWNLOADED,
            file_path=str(temp_dir / "missing.mp3"),
        )

        # Track 3: needs symlink (priority 6)
        track3_id = create_test_track(
            db_service,
            tidal_id="333",
            download_status=DownloadStatus.DOWNLOADED,
            file_path=str(file_path),
        )

        playlist_id = create_test_playlist(db_service)
        add_track_to_playlist(db_service, playlist_id, track1_id)
        add_track_to_playlist(db_service, playlist_id, track2_id)
        add_track_to_playlist(db_service, playlist_id, track3_id, is_primary=False)

        decisions = decision_engine.analyze_playlist_sync(playlist_id)
        prioritized = decision_engine.get_prioritized_decisions(decisions)

        # Should be sorted by priority descending
        assert len(prioritized) == 3
        assert prioritized[0].priority == 10  # download
        assert prioritized[1].priority == 8  # missing file
        assert prioritized[2].priority == 6  # create symlink

    def test_filter_decisions_by_action(self, decision_engine, db_service, temp_dir):
        """Test filtering decisions by action type."""
        # Create mixed scenario
        file_path = temp_dir / "track.mp3"
        file_path.write_text("audio")

        track1_id = create_test_track(
            db_service,
            tidal_id="111",
            download_status=DownloadStatus.NOT_DOWNLOADED,
        )
        track2_id = create_test_track(
            db_service,
            tidal_id="222",
            download_status=DownloadStatus.DOWNLOADED,
            file_path=str(file_path),
        )

        playlist_id = create_test_playlist(db_service)
        add_track_to_playlist(db_service, playlist_id, track1_id)
        add_track_to_playlist(db_service, playlist_id, track2_id, is_primary=False)

        decisions = decision_engine.analyze_playlist_sync(playlist_id)

        # Filter downloads
        downloads = decision_engine.filter_decisions_by_action(
            decisions, SyncAction.DOWNLOAD_TRACK
        )
        assert len(downloads) == 1
        assert all(d.action == SyncAction.DOWNLOAD_TRACK for d in downloads)

        # Filter symlinks
        symlinks = decision_engine.filter_decisions_by_action(
            decisions, SyncAction.CREATE_SYMLINK
        )
        assert len(symlinks) == 1
        assert all(d.action == SyncAction.CREATE_SYMLINK for d in symlinks)


class TestSyncDecisionsDataclass:
    """Test SyncDecisions dataclass functionality."""

    def test_add_decision_updates_statistics(self, db_service, music_root):
        """Test that adding decisions updates statistics correctly."""
        from tidal_cleanup.core.sync.decision_engine import (
            DecisionResult,
            SyncDecisions,
        )

        decisions = SyncDecisions()

        # Add various actions
        decisions.add_decision(
            DecisionResult(action=SyncAction.DOWNLOAD_TRACK, track_id=1)
        )
        decisions.add_decision(
            DecisionResult(action=SyncAction.CREATE_SYMLINK, track_id=2)
        )
        decisions.add_decision(
            DecisionResult(action=SyncAction.UPDATE_SYMLINK, track_id=3)
        )
        decisions.add_decision(
            DecisionResult(action=SyncAction.REMOVE_FILE, track_id=4)
        )
        decisions.add_decision(
            DecisionResult(action=SyncAction.UPDATE_METADATA, track_id=5)
        )
        decisions.add_decision(DecisionResult(action=SyncAction.NO_ACTION, track_id=6))

        # Check statistics
        assert decisions.tracks_to_download == 1
        assert decisions.symlinks_to_create == 1
        assert decisions.symlinks_to_update == 1
        assert decisions.files_to_remove == 1
        assert decisions.metadata_updates == 1
        assert decisions.no_action_needed == 1

    def test_get_summary(self):
        """Test getting summary statistics."""
        from tidal_cleanup.core.sync.decision_engine import (
            DecisionResult,
            SyncDecisions,
        )

        decisions = SyncDecisions()
        decisions.add_decision(
            DecisionResult(action=SyncAction.DOWNLOAD_TRACK, track_id=1)
        )
        decisions.add_decision(
            DecisionResult(action=SyncAction.CREATE_SYMLINK, track_id=2)
        )

        summary = decisions.get_summary()
        assert summary["total_decisions"] == 2
        assert summary["tracks_to_download"] == 1
        assert summary["symlinks_to_create"] == 1
        assert summary["symlinks_to_update"] == 0
