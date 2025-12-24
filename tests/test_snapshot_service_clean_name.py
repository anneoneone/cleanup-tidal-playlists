from types import SimpleNamespace

from tidal_cleanup.core.rekordbox.snapshot_service import RekordboxSnapshotService


def make_service(default_status: str = "Archived") -> RekordboxSnapshotService:
    svc = object.__new__(RekordboxSnapshotService)
    svc._genre_default_status = default_status
    return svc


def test_clean_name_includes_status_when_present():
    svc = make_service()
    metadata = SimpleNamespace(
        playlist_name="House House",
        energy_tags=set(),
        status_tags={"Recherche"},
    )

    clean = svc._get_clean_display_name(metadata, include_status=True)

    assert clean == "House House Recherche"


def test_clean_name_uses_default_status_when_missing():
    svc = make_service(default_status="Archived")
    metadata = SimpleNamespace(
        playlist_name="House House",
        energy_tags={"Up"},
        status_tags=set(),
    )

    clean = svc._get_clean_display_name(metadata, include_status=True)

    # Default status should not be appended
    assert clean == "House House Up"


def test_legacy_clean_name_excludes_status():
    svc = make_service(default_status="Archived")
    metadata = SimpleNamespace(
        playlist_name="House House",
        energy_tags={"Up"},
        status_tags={"Recherche"},
    )

    clean = svc._get_clean_display_name(metadata, include_status=False)

    assert clean == "House House Up"


def test_non_default_status_is_appended():
    svc = make_service(default_status="Archived")
    metadata = SimpleNamespace(
        playlist_name="House Italo",
        energy_tags=set(),
        status_tags={"Recherche"},
    )

    clean = svc._get_clean_display_name(metadata, include_status=True)

    assert clean == "House Italo Recherche"
