from types import SimpleNamespace

from tidal_cleanup.core.rekordbox.snapshot_service import RekordboxSnapshotService


def make_service():
    svc = object.__new__(RekordboxSnapshotService)
    svc._genre_root = "Genre"
    svc._events_root = "Events"
    svc._genre_uncategorized = "Uncategorized"
    svc._events_misc = "Misc"
    svc._genre_default_status = "Archived"
    svc._genre_categories = {}
    return svc


def test_status_only_goes_to_discogs_folder():
    svc = make_service()
    metadata = SimpleNamespace(
        genre_tags=set(),
        party_tags=set(),
        status_tags={"Discogs"},
        event_year=None,
    )

    segments = svc._get_folder_path_segments(metadata)

    assert segments == ["Genre", "Uncategorized", "Discogs"]


def test_no_tags_defaults_to_archived_uncategorized():
    svc = make_service()
    metadata = SimpleNamespace(
        genre_tags=set(),
        party_tags=set(),
        status_tags=set(),
        event_year=None,
    )

    segments = svc._get_folder_path_segments(metadata)

    assert segments == ["Genre", "Uncategorized", "Archived"]
