"""Tests that sync does not delete Rekordbox playlists as false orphans."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from tidal_cleanup.core.rekordbox import snapshot_service as snapshot_module
from tidal_cleanup.core.rekordbox.snapshot_service import RekordboxSnapshotService


def make_service(db_names, rekordbox_names=()):
    svc = object.__new__(RekordboxSnapshotService)
    svc.db_service = MagicMock()
    svc.db_service.get_all_playlists.return_value = [
        SimpleNamespace(name=name) for name in db_names
    ]
    svc._db = MagicMock()
    svc._db.get_playlist.return_value.all.return_value = [
        SimpleNamespace(Name=name) for name in rekordbox_names
    ]
    return svc


def test_name_match_ignores_emojis_and_case():
    svc = make_service([])

    assert svc._is_potential_name_match("House Up ↗️", "house up")
    assert svc._is_potential_name_match("Disco 🪩", "Disco")


def test_name_match_rejects_different_core_names():
    svc = make_service([])

    assert not svc._is_potential_name_match("House Up ↗️", "Techno Up")


def test_collect_orphans_skips_emoji_variants_of_db_playlists(monkeypatch):
    monkeypatch.setattr(snapshot_module, "PYREKORDBOX_AVAILABLE", True)
    monkeypatch.setattr(snapshot_module, "db6", object())
    svc = make_service(["House Up"], rekordbox_names=["House Up ↗️", "Old Stuff"])

    orphans = svc._collect_rekordbox_orphans(set(), {"House Up"})

    assert [pl.Name for pl in orphans] == ["Old Stuff"]


def test_prune_missing_local_playlists_keeps_rekordbox_orphans(tmp_path):
    (tmp_path / "Playlists" / "House Up").mkdir(parents=True)
    svc = make_service(["House Up"])
    rb_db = MagicMock()
    rb_db.get_playlist.return_value.all.return_value = [
        SimpleNamespace(Name="House Up ↗️"),
        SimpleNamespace(Name="Old Stuff"),
    ]
    prune_orphans = MagicMock()
    remove_playlist = MagicMock()
    svc._db = rb_db
    svc._mp3_root = tmp_path
    svc._prune_rekordbox_orphans = prune_orphans
    svc._remove_playlist_from_rekordbox_and_db = remove_playlist

    svc._prune_missing_local_playlists(dry_run=False)

    prune_orphans.assert_not_called()
    remove_playlist.assert_not_called()
    rb_db.delete_playlist.assert_not_called()
