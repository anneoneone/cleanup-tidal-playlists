"""Tests for date-based track order in Rekordbox playlist sync."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from tidal_cleanup.core.rekordbox.snapshot_service import RekordboxSnapshotService


def make_service() -> RekordboxSnapshotService:
    return object.__new__(RekordboxSnapshotService)


def make_assoc(
    name, added_to_tidal=None, added_to_local=None, created_at=None, track=True
):
    return SimpleNamespace(
        name=name,
        added_to_tidal=added_to_tidal,
        added_to_local=added_to_local,
        track=(
            SimpleNamespace(id=name, title=name, created_at=created_at)
            if track
            else None
        ),
    )


def names(associations):
    return [assoc.name for assoc in associations]


def test_sort_uses_tidal_then_local_then_created_at():
    tidal = make_assoc("tidal", added_to_tidal=datetime(2024, 3, 1))
    local = make_assoc("local", added_to_local=datetime(2024, 1, 1))
    created = make_assoc("created", created_at=datetime(2024, 2, 1))

    result = make_service()._sort_tracks_by_date([tidal, created, local])

    assert names(result) == ["local", "created", "tidal"]


def test_sort_mixes_naive_and_aware_dates_and_missing_track():
    # Naive values come from SQLite; aware values come from Tidal or code.
    naive = make_assoc("naive", added_to_tidal=datetime(2024, 1, 2))
    aware = make_assoc(
        "aware", added_to_tidal=datetime(2024, 1, 1, tzinfo=timezone.utc)
    )
    no_date = make_assoc("no_date", track=False)

    result = make_service()._sort_tracks_by_date([naive, aware, no_date])

    assert names(result) == ["no_date", "aware", "naive"]


def test_sync_processes_tracks_in_date_order():
    process_track = MagicMock()
    svc = make_service()
    svc._derive_genre_from_metadata = MagicMock(return_value=None)
    svc._resolve_track_path = MagicMock(return_value=None)
    svc._process_track_for_sync = process_track
    newer = make_assoc("newer", added_to_tidal=datetime(2024, 5, 1))
    older = make_assoc("older", added_to_tidal=datetime(2024, 4, 1))

    svc._sync_tracks_for_playlist(
        MagicMock(), [newer, older], None, MagicMock(), MagicMock(), False, None
    )

    processed = [c.args[1].title for c in process_track.call_args_list]
    assert processed == ["older", "newer"]


def test_ensure_local_date_uses_file_creation_time(tmp_path):
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"")
    stat = audio.stat()
    expected = datetime.fromtimestamp(
        getattr(stat, "st_birthtime", stat.st_ctime), tz=timezone.utc
    )
    assoc = make_assoc("local")

    make_service()._ensure_local_track_date(assoc.track, assoc, audio, dry_run=False)

    assert assoc.added_to_local == expected


def test_ensure_local_date_does_not_write_in_dry_run(tmp_path):
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"")
    assoc = make_assoc("local")

    make_service()._ensure_local_track_date(assoc.track, assoc, audio, dry_run=True)

    assert assoc.added_to_local is None


def test_ensure_local_date_keeps_tidal_tracks_and_missing_files(tmp_path):
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"")
    tidal = make_assoc("tidal", added_to_tidal=datetime(2024, 1, 1))
    missing = make_assoc("missing")

    svc = make_service()
    svc._ensure_local_track_date(tidal.track, tidal, audio, dry_run=False)
    svc._ensure_local_track_date(
        missing.track, missing, tmp_path / "gone.mp3", dry_run=False
    )

    assert tidal.added_to_local is None
    assert missing.added_to_local is None
