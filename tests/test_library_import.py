import io
from pathlib import Path

import pytest
from sqlalchemy import select

from cratekeeper.db import Database, Playlist, PlaylistTrack, Track
from cratekeeper.music.library_import import (
    FileNameError,
    _write_new_file,
    import_library_track,
)
from cratekeeper.music.paths import FolderMissingError
from cratekeeper.music.refresh import refresh_music_folder


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "ck.db")
    database.prepare()
    return database


@pytest.fixture
def music(tmp_path: Path) -> Path:
    folder = tmp_path / "music"
    (folder / "Playlists").mkdir(parents=True)
    return folder


def add_playlist(db: Database, name: str, **fields: object) -> int:
    with db.session() as s:
        playlist = Playlist(name=name, **fields)
        s.add(playlist)
        s.flush()
        return playlist.id


def library_rows(db: Database, playlist_id: int) -> list[tuple[str, bool]]:
    with db.session() as s:
        result = s.execute(
            select(Track.title, PlaylistTrack.in_local)
            .join(PlaylistTrack, PlaylistTrack.track_id == Track.id)
            .where(PlaylistTrack.playlist_id == playlist_id)
            .order_by(Track.title)
        )
        return [tuple(r) for r in result]


def test_file_is_copied_into_the_playlist_folder_as_library_track(
    db: Database, music: Path, tmp_path: Path, make_mp3
) -> None:
    make_mp3(music / "Playlists" / "Peak" / "A - One.mp3", title="One", artist="A")
    refresh_music_folder(db, music)
    with db.session() as s:
        pid = s.scalars(select(Playlist.id).where(Playlist.name == "Peak")).one()
    source = make_mp3(tmp_path / "Downloads" / "B - Two.mp3", title="Two", artist="B")
    data = source.read_bytes()

    with source.open("rb") as handle:
        result = import_library_track(db, music, pid, "B - Two.mp3", handle)

    target = music / "Playlists" / "Peak" / "B - Two.mp3"
    assert target.read_bytes() == data
    assert source.read_bytes() == data  # the source stays where it is
    assert (result.file_path, result.library_track) == (
        "Playlists/Peak/B - Two.mp3",
        True,
    )
    assert library_rows(db, pid) == [("One", True), ("Two", True)]
    assert sorted(p.name for p in target.parent.iterdir()) == [
        "A - One.mp3",
        "B - Two.mp3",
    ]


def test_playlist_without_folder_gets_one(
    db: Database, music: Path, tmp_path: Path, make_mp3
) -> None:
    pid = add_playlist(db, "Mix: A/B 🌃", tidal_id="pl-1", in_tidal=True)
    source = make_mp3(tmp_path / "x.mp3", title="Rain", artist="Kerri")

    with source.open("rb") as handle:
        result = import_library_track(db, music, pid, "Kerri - Rain.mp3", handle)

    assert result.file_path == "Playlists/Mix- A-B 🌃/Kerri - Rain.mp3"
    assert (music / result.file_path).is_file()
    with db.session() as s:
        playlist = s.get(Playlist, pid)
        assert playlist is not None
        assert playlist.local_folder_path == "Playlists/Mix- A-B 🌃"
        assert len(s.scalars(select(Playlist)).all()) == 1  # no extra Library playlist
    assert library_rows(db, pid) == [("Rain", True)]


def test_file_that_matches_a_tidal_track_is_linked_to_it(
    db: Database, music: Path, tmp_path: Path, make_mp3
) -> None:
    pid = add_playlist(db, "House", tidal_id="pl-1", in_tidal=True)
    with db.session() as s:
        track = Track(
            tidal_id="t1",
            title="Tune",
            artist="Main",
            isrc="ISRC1",
            normalized_name="x",
        )
        s.add(track)
        s.flush()
        s.add(PlaylistTrack(playlist_id=pid, track_id=track.id, in_tidal=True))
        track_id = track.id
    source = make_mp3(tmp_path / "tune.mp3", isrc="ISRC1")

    with source.open("rb") as handle:
        result = import_library_track(db, music, pid, "tune.mp3", handle)

    assert (result.track_id, result.library_track) == (track_id, False)
    assert library_rows(db, pid) == [("Tune", False)]


def test_existing_file_is_never_overwritten(
    db: Database, music: Path, make_mp3
) -> None:
    existing = make_mp3(music / "Playlists" / "Peak" / "A - One.mp3", title="One")
    before = existing.read_bytes()
    pid = add_playlist(db, "Peak", local_folder_path="Playlists/Peak")

    with pytest.raises(FileExistsError, match="already in the folder Playlists/Peak"):
        import_library_track(db, music, pid, "A - One.mp3", io.BytesIO(b"new"))

    assert existing.read_bytes() == before
    with pytest.raises(FileExistsError):  # the name appears after the first check
        _write_new_file(io.BytesIO(b"new"), existing)
    assert existing.read_bytes() == before
    assert [p.name for p in existing.parent.iterdir()] == ["A - One.mp3"]


@pytest.mark.parametrize(
    "name", ["", "../x.mp3", "sub/x.mp3", ".hidden.mp3", "notes.txt", "x"]
)
def test_bad_file_names_are_refused(db: Database, music: Path, name: str) -> None:
    pid = add_playlist(db, "Peak")
    with pytest.raises(FileNameError):
        import_library_track(db, music, pid, name, io.BytesIO(b"data"))
    assert list((music / "Playlists").iterdir()) == []


def test_unknown_playlist_and_missing_music_folder(
    db: Database, music: Path, tmp_path: Path
) -> None:
    with pytest.raises(LookupError):
        import_library_track(db, music, 99, "x.mp3", io.BytesIO(b"data"))
    pid = add_playlist(db, "Peak")
    with pytest.raises(FolderMissingError):
        import_library_track(db, tmp_path / "gone", pid, "x.mp3", io.BytesIO(b"data"))


def test_failed_copy_leaves_no_file(db: Database, music: Path) -> None:
    class Broken(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            raise OSError("disk full")

    pid = add_playlist(db, "Peak", local_folder_path="Playlists/Peak")
    with pytest.raises(OSError, match="disk full"):
        import_library_track(db, music, pid, "x.mp3", Broken())
    assert list((music / "Playlists" / "Peak").iterdir()) == []
    assert library_rows(db, pid) == []
