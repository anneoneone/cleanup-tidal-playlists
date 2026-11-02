from pathlib import Path

import pytest
from sqlalchemy import select

from cratekeeper.bandcamp.refresh import refresh_bandcamp
from cratekeeper.db import Database, Playlist, PlaylistTrack
from cratekeeper.db import repository as repo


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "ck.db")
    database.prepare()
    return database


def bandcamp_flags(db: Database, name: str) -> list[bool]:
    with db.session() as s:
        playlist = repo.playlist_by_name(s, name)
        assert playlist is not None
        return [
            r.in_bandcamp
            for r in s.scalars(
                select(PlaylistTrack)
                .where(PlaylistTrack.playlist_id == playlist.id)
                .order_by(PlaylistTrack.id)
            )
        ]


def test_folders_become_or_join_playlists(
    db: Database, tmp_path: Path, make_mp3, make_flac
) -> None:
    root = tmp_path / "bandcamp"
    make_mp3(root / "Deep Cuts" / "Artist - One.mp3")
    make_flac(root / "Deep Cuts" / "Album" / "Artist - Two.flac", title="Two")
    make_mp3(root / "House" / "X - Y.mp3")
    with db.session() as s:
        s.add(Playlist(name="house", tidal_id="t1", in_tidal=True))

    stats = refresh_bandcamp(db, root)

    assert (stats.folders, stats.playlists_created, stats.files) == (2, 1, 3)
    assert bandcamp_flags(db, "Deep Cuts") == [True, True]
    with db.session() as s:
        house = repo.playlist_by_name(s, "House")
        assert house is not None and house.tidal_id == "t1"


def test_removed_files_and_folders_clear_flags(
    db: Database, tmp_path: Path, make_mp3
) -> None:
    root = tmp_path / "bandcamp"
    keep = make_mp3(root / "P" / "A - Keep.mp3")
    drop = make_mp3(root / "P" / "A - Drop.mp3")
    gone = make_mp3(root / "Gone" / "B - C.mp3")
    refresh_bandcamp(db, root)
    drop.unlink()
    gone.unlink()
    gone.parent.rmdir()

    stats = refresh_bandcamp(db, root)

    assert stats.tracks_gone == 1
    assert stats.playlists_gone == 1
    assert sorted(bandcamp_flags(db, "P")) == [False, True]
    assert bandcamp_flags(db, "Gone") == [False]
    assert keep.exists()


def test_missing_folder_is_skipped_and_keeps_flags(
    db: Database, tmp_path: Path, make_mp3
) -> None:
    root = tmp_path / "bandcamp"
    make_mp3(root / "P" / "A - B.mp3")
    refresh_bandcamp(db, root)

    stats = refresh_bandcamp(db, tmp_path / "unplugged")

    assert stats.skipped and "not found" in stats.skipped
    assert bandcamp_flags(db, "P") == [True]


def test_not_configured_is_skipped(db: Database) -> None:
    assert refresh_bandcamp(db, None).skipped == "No Bandcamp folder configured"
