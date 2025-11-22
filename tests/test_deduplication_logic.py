"""Tests for DeduplicationLogic."""

import tempfile
from pathlib import Path

import pytest

from tidal_cleanup.database import DatabaseService, DeduplicationLogic


# Helper functions (reuse from other tests)
def create_test_track(
    db_service: DatabaseService,
    tidal_id: str = "123456",
    title: str = "Test Track",
    artist: str = "Test Artist",
) -> int:
    """Create a test track and return its ID."""
    track_data = {
        "tidal_id": tidal_id,
        "title": title,
        "artist": artist,
        "duration": 180,
        "normalized_name": f"{artist} - {title}",
    }
    track = db_service.create_track(track_data)
    return track.id


def create_test_playlist(
    db_service: DatabaseService,
    tidal_id: str = "playlist-uuid",
    name: str = "Test Playlist",
    num_tracks: int = 0,
) -> int:
    """Create a test playlist and return its ID."""
    playlist = db_service.create_playlist(
        {"tidal_id": tidal_id, "name": name, "num_tracks": num_tracks}
    )
    return playlist.id


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
    return service


@pytest.fixture
def dedup_logic(db_service):
    """Create a DeduplicationLogic instance."""
    return DeduplicationLogic(db_service=db_service)


class TestDeduplicationLogicInit:
    """Test DeduplicationLogic initialization."""

    def test_init_with_default_strategy(self, db_service):
        """Test initialization with default strategy."""
        dedup = DeduplicationLogic(db_service=db_service)
        assert dedup.db_service is db_service
        assert dedup.strategy == "first_alphabetically"

    def test_init_with_custom_strategy(self, db_service):
        """Test initialization with custom strategy."""
        dedup = DeduplicationLogic(db_service=db_service, strategy="largest_playlist")
        assert dedup.strategy == "largest_playlist"


class TestAnalyzeTrackDistribution:
    """Test track distribution analysis."""

    def test_track_in_single_playlist(self, dedup_logic, db_service):
        """Test analysis for track in one playlist."""
        # Create track and playlist
        track_id = create_test_track(db_service)
        playlist_id = create_test_playlist(db_service, name="MyPlaylist")
        db_service.add_track_to_playlist(playlist_id, track_id, position=1)

        # Analyze
        decision = dedup_logic.analyze_track_distribution(track_id)

        assert decision.track_id == track_id
        assert decision.primary_playlist_id == playlist_id
        assert decision.primary_playlist_name == "MyPlaylist"
        assert decision.symlink_playlist_ids == []

    def test_track_in_multiple_playlists_alphabetical(self, dedup_logic, db_service):
        """Test track in multiple playlists - first alphabetically wins."""
        track_id = create_test_track(db_service)

        # Create playlists in non-alphabetical order
        playlist_c = create_test_playlist(db_service, tidal_id="c", name="Zebra")
        playlist_a = create_test_playlist(db_service, tidal_id="a", name="Alpha")
        playlist_b = create_test_playlist(db_service, tidal_id="b", name="Beta")

        # Add track to all playlists
        db_service.add_track_to_playlist(playlist_c, track_id, position=1)
        db_service.add_track_to_playlist(playlist_a, track_id, position=1)
        db_service.add_track_to_playlist(playlist_b, track_id, position=1)

        # Analyze
        decision = dedup_logic.analyze_track_distribution(track_id)

        # Should choose "Alpha" (first alphabetically)
        assert decision.primary_playlist_id == playlist_a
        assert decision.primary_playlist_name == "Alpha"
        assert set(decision.symlink_playlist_ids) == {playlist_b, playlist_c}

    def test_track_not_in_any_playlist(self, dedup_logic, db_service):
        """Test error when track not in any playlist."""
        track_id = create_test_track(db_service)

        with pytest.raises(ValueError, match="not found in any playlists"):
            dedup_logic.analyze_track_distribution(track_id)

    def test_track_nonexistent(self, dedup_logic, db_service):
        """Test error with nonexistent track ID."""
        with pytest.raises(ValueError):
            dedup_logic.analyze_track_distribution(99999)


class TestAnalyzeAllTracks:
    """Test analyzing all tracks."""

    def test_analyze_empty_database(self, dedup_logic, db_service):
        """Test analysis with no tracks."""
        result = dedup_logic.analyze_all_tracks()

        assert result.tracks_analyzed == 0
        assert result.tracks_with_primary == 0
        assert result.tracks_needing_primary == 0
        assert len(result.decisions) == 0

    def test_analyze_tracks_in_single_playlists(self, dedup_logic, db_service):
        """Test tracks that are each in only one playlist."""
        # Create 3 tracks, each in one playlist
        for i in range(3):
            track_id = create_test_track(
                db_service, tidal_id=f"track{i}", title=f"Track {i}"
            )
            playlist_id = create_test_playlist(
                db_service, tidal_id=f"pl{i}", name=f"Playlist{i}"
            )
            db_service.add_track_to_playlist(playlist_id, track_id, position=1)

        result = dedup_logic.analyze_all_tracks()

        # All tracks in single playlists, so all have primary, none need deduplication
        assert result.tracks_analyzed == 3
        assert result.tracks_with_primary == 3
        assert result.tracks_needing_primary == 0
        assert len(result.decisions) == 0  # No deduplication needed

    def test_analyze_tracks_needing_deduplication(self, dedup_logic, db_service):
        """Test tracks that need deduplication."""
        # Create 2 tracks
        track1 = create_test_track(db_service, tidal_id="t1", title="Track 1")
        track2 = create_test_track(db_service, tidal_id="t2", title="Track 2")

        # Create 2 playlists
        pl1 = create_test_playlist(db_service, tidal_id="pl1", name="Playlist A")
        pl2 = create_test_playlist(db_service, tidal_id="pl2", name="Playlist B")

        # Track 1 in both playlists
        db_service.add_track_to_playlist(pl1, track1, position=1)
        db_service.add_track_to_playlist(pl2, track1, position=1)

        # Track 2 in only one playlist
        db_service.add_track_to_playlist(pl1, track2, position=1)

        result = dedup_logic.analyze_all_tracks()

        # Track 1 needs deduplication, Track 2 doesn't
        assert result.tracks_analyzed == 2
        assert result.tracks_with_primary == 1  # Track 2
        assert result.tracks_needing_primary == 1  # Track 1
        assert len(result.decisions) == 1  # Only track1 needs deduplication
        assert result.symlinks_needed == 1  # Track 1 in one other playlist


class TestDeduplicationStrategies:
    """Test different deduplication strategies."""

    def test_strategy_first_alphabetically(self, db_service):
        """Test first_alphabetically strategy."""
        dedup = DeduplicationLogic(db_service, strategy="first_alphabetically")

        track_id = create_test_track(db_service)
        pl_zebra = create_test_playlist(db_service, tidal_id="z", name="Zebra")
        pl_alpha = create_test_playlist(db_service, tidal_id="a", name="Alpha")

        db_service.add_track_to_playlist(pl_zebra, track_id, position=1)
        db_service.add_track_to_playlist(pl_alpha, track_id, position=1)

        decision = dedup.analyze_track_distribution(track_id)

        # Should choose Alpha (first alphabetically)
        assert decision.primary_playlist_name == "Alpha"
        assert decision.primary_playlist_id == pl_alpha

    def test_strategy_largest_playlist(self, db_service):
        """Test largest_playlist strategy."""
        dedup = DeduplicationLogic(db_service, strategy="largest_playlist")

        track_id = create_test_track(db_service)

        # Create playlists with different sizes
        pl_small = create_test_playlist(
            db_service, tidal_id="s", name="Small", num_tracks=5
        )
        pl_large = create_test_playlist(
            db_service, tidal_id="l", name="Large", num_tracks=50
        )

        db_service.add_track_to_playlist(pl_small, track_id, position=1)
        db_service.add_track_to_playlist(pl_large, track_id, position=1)

        decision = dedup.analyze_track_distribution(track_id)

        # Should choose Large (has more tracks)
        assert decision.primary_playlist_name == "Large"
        assert decision.primary_playlist_id == pl_large

    def test_strategy_prefer_existing_no_primary(self, db_service):
        """Test prefer_existing strategy when no primary exists."""
        dedup = DeduplicationLogic(db_service, strategy="prefer_existing")

        track_id = create_test_track(db_service)
        pl_b = create_test_playlist(db_service, tidal_id="b", name="Beta")
        pl_a = create_test_playlist(db_service, tidal_id="a", name="Alpha")

        db_service.add_track_to_playlist(pl_b, track_id, position=1)
        db_service.add_track_to_playlist(pl_a, track_id, position=1)

        decision = dedup.analyze_track_distribution(track_id)

        # Should fall back to alphabetical (Alpha)
        assert decision.primary_playlist_name == "Alpha"

    def test_strategy_unknown_falls_back(self, db_service):
        """Test unknown strategy falls back to first_alphabetically."""
        dedup = DeduplicationLogic(db_service, strategy="unknown_strategy")

        track_id = create_test_track(db_service)
        pl_z = create_test_playlist(db_service, tidal_id="z", name="Zebra")
        pl_a = create_test_playlist(db_service, tidal_id="a", name="Alpha")

        db_service.add_track_to_playlist(pl_z, track_id, position=1)
        db_service.add_track_to_playlist(pl_a, track_id, position=1)

        decision = dedup.analyze_track_distribution(track_id)

        # Should fall back to alphabetical
        assert decision.primary_playlist_name == "Alpha"


class TestHelperMethods:
    """Test helper methods."""

    def test_get_primary_playlist_for_track(self, dedup_logic, db_service):
        """Test getting primary playlist ID."""
        track_id = create_test_track(db_service)
        pl1 = create_test_playlist(db_service, tidal_id="pl1", name="Playlist A")
        pl2 = create_test_playlist(db_service, tidal_id="pl2", name="Playlist B")

        db_service.add_track_to_playlist(pl1, track_id, position=1)
        db_service.add_track_to_playlist(pl2, track_id, position=1)

        primary_id = dedup_logic.get_primary_playlist_for_track(track_id)

        # Should be pl1 (alphabetically first)
        assert primary_id == pl1

    def test_get_primary_playlist_track_not_found(self, dedup_logic, db_service):
        """Test getting primary playlist for nonexistent track."""
        primary_id = dedup_logic.get_primary_playlist_for_track(99999)
        assert primary_id is None

    def test_should_be_primary(self, dedup_logic, db_service):
        """Test checking if playlist should be primary."""
        track_id = create_test_track(db_service)
        pl1 = create_test_playlist(db_service, tidal_id="pl1", name="Playlist A")
        pl2 = create_test_playlist(db_service, tidal_id="pl2", name="Playlist B")

        db_service.add_track_to_playlist(pl1, track_id, position=1)
        db_service.add_track_to_playlist(pl2, track_id, position=1)

        # pl1 should be primary (alphabetically first)
        assert dedup_logic.should_be_primary(track_id, pl1) is True
        assert dedup_logic.should_be_primary(track_id, pl2) is False

    def test_get_symlink_playlists_for_track(self, dedup_logic, db_service):
        """Test getting symlink playlist IDs."""
        track_id = create_test_track(db_service)
        pl1 = create_test_playlist(db_service, tidal_id="pl1", name="Playlist A")
        pl2 = create_test_playlist(db_service, tidal_id="pl2", name="Playlist B")
        pl3 = create_test_playlist(db_service, tidal_id="pl3", name="Playlist C")

        db_service.add_track_to_playlist(pl1, track_id, position=1)
        db_service.add_track_to_playlist(pl2, track_id, position=1)
        db_service.add_track_to_playlist(pl3, track_id, position=1)

        symlink_ids = dedup_logic.get_symlink_playlists_for_track(track_id)

        # pl1 is primary, pl2 and pl3 should be symlinks
        assert set(symlink_ids) == {pl2, pl3}

    def test_get_symlink_playlists_track_not_found(self, dedup_logic, db_service):
        """Test getting symlink playlists for nonexistent track."""
        symlink_ids = dedup_logic.get_symlink_playlists_for_track(99999)
        assert symlink_ids == []


class TestDeduplicationResultDataclass:
    """Test DeduplicationResult dataclass."""

    def test_add_decision_updates_stats(self):
        """Test that adding decisions updates statistics."""
        from tidal_cleanup.database.deduplication_logic import (
            DeduplicationResult,
            PrimaryFileDecision,
        )

        result = DeduplicationResult()

        decision1 = PrimaryFileDecision(
            track_id=1,
            primary_playlist_id=10,
            primary_playlist_name="Playlist A",
            symlink_playlist_ids=[11, 12],
            reason="Test",
        )

        decision2 = PrimaryFileDecision(
            track_id=2,
            primary_playlist_id=20,
            primary_playlist_name="Playlist B",
            symlink_playlist_ids=[21],
            reason="Test",
        )

        result.add_decision(decision1)
        result.add_decision(decision2)

        assert result.tracks_analyzed == 2
        assert result.symlinks_needed == 3  # 2 + 1
        assert len(result.decisions) == 2

    def test_get_summary(self):
        """Test getting summary statistics."""
        from tidal_cleanup.database.deduplication_logic import DeduplicationResult

        result = DeduplicationResult()
        result.tracks_analyzed = 10
        result.tracks_with_primary = 7
        result.tracks_needing_primary = 3
        result.symlinks_needed = 5

        summary = result.get_summary()

        assert summary["tracks_analyzed"] == 10
        assert summary["tracks_with_primary"] == 7
        assert summary["tracks_needing_primary"] == 3
        assert summary["symlinks_needed"] == 5
