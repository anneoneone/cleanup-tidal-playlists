from pathlib import Path

import pytest
from sqlalchemy import select

from cratekeeper.db import Database, Playlist, PlaylistTrack, Track
from cratekeeper.db import repository as repo
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


def add_tidal_playlist(db: Database, name: str, tracks: list[dict]) -> int:
    with db.session() as s:
        playlist = Playlist(name=name, tidal_id=f"pl-{name}", in_tidal=True)
        s.add(playlist)
        s.flush()
        for i, data in enumerate(tracks):
            track = Track(
                tidal_id=data.pop("tidal_id", f"{name}-{i}"),
                normalized_name="x",
                **data,
            )
            s.add(track)
            s.flush()
            s.add(
                PlaylistTrack(
                    playlist_id=playlist.id,
                    track_id=track.id,
                    in_tidal=True,
                    position=i,
                )
            )
        return playlist.id


def rows_of(db: Database, playlist_id: int) -> list[tuple[str, bool, bool]]:
    with db.session() as s:
        result = s.execute(
            select(Track.title, PlaylistTrack.in_tidal, PlaylistTrack.in_local)
            .join(PlaylistTrack, PlaylistTrack.track_id == Track.id)
            .where(PlaylistTrack.playlist_id == playlist_id)
            .order_by(Track.title)
        )
        return [tuple(r) for r in result]


def test_files_link_to_tidal_tracks_and_leftovers_become_local(
    db: Database, music: Path, make_mp3
) -> None:
    pid = add_tidal_playlist(
        db,
        "House",
        [
            {"title": "Tune", "artist": "Main", "isrc": "ISRC1"},
            {"title": "Groove", "artist": "Duo", "version": "Dub"},
        ],
    )
    folder = music / "Playlists" / "House"
    make_mp3(folder / "whatever name.mp3", isrc="isrc1")
    make_mp3(folder / "Duo, Guest - Groove (Dub).mp3")
    make_mp3(folder / "Hand Picked - Extra.mp3", title="Extra", artist="Hand Picked")

    stats = refresh_music_folder(db, music)

    assert (stats.linked_to_tidal, stats.local_tracks) == (2, 1)
    assert rows_of(db, pid) == [
        ("Extra", False, True),
        ("Groove", True, False),
        ("Tune", True, False),
    ]
    with db.session() as s:
        tune = s.scalars(select(Track).where(Track.title == "Tune")).one()
        assert tune.file_paths == ["Playlists/House/whatever name.mp3"]
        playlist = s.get(Playlist, pid)
        assert playlist is not None
        assert playlist.local_folder_path == "Playlists/House"

    again = refresh_music_folder(db, music)
    assert (again.linked_to_tidal, again.local_tracks) == (2, 1)
    assert rows_of(db, pid) == [
        ("Extra", False, True),
        ("Groove", True, False),
        ("Tune", True, False),
    ]


def test_folder_without_tidal_playlist_is_local_playlist(
    db: Database, music: Path, make_mp3
) -> None:
    make_mp3(music / "Playlists" / "24-01-11 Kukumu 🎙️" / "A - B.mp3")
    stats = refresh_music_folder(db, music)
    assert stats.local_playlists_created == 1
    with db.session() as s:
        playlist = repo.playlist_by_name(s, "24-01-11 Kukumu 🎙️")
        assert playlist is not None
        assert playlist.tidal_id is None
        assert rows_of(db, playlist.id) == [("B", False, True)]


def test_renamed_tidal_playlist_keeps_its_folder(
    db: Database, music: Path, make_mp3
) -> None:
    pid = add_tidal_playlist(db, "Old ❓", [{"title": "T", "artist": "A"}])
    make_mp3(music / "Playlists" / "Old ❓" / "A - T.mp3")
    refresh_music_folder(db, music)
    with db.session() as s:
        playlist = s.get(Playlist, pid)
        assert playlist is not None
        playlist.name = "Old 💾"  # status emoji changed on Tidal
    stats = refresh_music_folder(db, music)
    assert stats.local_playlists_created == 0
    assert rows_of(db, pid) == [("T", True, False)]


def test_removed_files_drop_paths_and_local_tracks(
    db: Database, music: Path, make_mp3
) -> None:
    pid = add_tidal_playlist(db, "P", [{"title": "T", "artist": "A"}])
    folder = music / "Playlists" / "P"
    tidal_file = make_mp3(folder / "A - T.mp3")
    local_file = make_mp3(folder / "X - Y.mp3")
    refresh_music_folder(db, music)
    tidal_file.unlink()
    local_file.unlink()

    stats = refresh_music_folder(db, music)

    assert (stats.paths_dropped, stats.local_tracks_gone) == (2, 1)
    assert rows_of(db, pid) == [("T", True, False), ("Y", False, False)]


def test_file_of_removed_tidal_track_never_becomes_local(
    db: Database, music: Path, make_mp3
) -> None:
    pid = add_tidal_playlist(db, "P", [{"title": "T", "artist": "A"}])
    make_mp3(music / "Playlists" / "P" / "A - T.mp3")
    refresh_music_folder(db, music)
    with db.session() as s:
        for row in repo.playlist_rows(s, pid).values():
            row.in_tidal = False  # removed from Tidal
    refresh_music_folder(db, music)
    assert rows_of(db, pid) == [("T", False, False)]


def test_v1_duplicate_local_row_is_released(
    db: Database, music: Path, make_mp3
) -> None:
    pid = add_tidal_playlist(db, "P", [{"title": "T", "artist": "A", "isrc": "I1"}])
    make_mp3(music / "Playlists" / "P" / "file.mp3", isrc="I1")
    with db.session() as s:
        dup = Track(title="T", artist="A", normalized_name="a - t")
        dup.file_paths = ["Playlists/P/file.mp3"]
        s.add(dup)
        s.flush()
        s.add(PlaylistTrack(playlist_id=pid, track_id=dup.id, in_local=True))

    refresh_music_folder(db, music)

    with db.session() as s:
        owner = repo.track_by_stored_path(s, "Playlists/P/file.mp3")
        assert owner is not None and owner.tidal_id is not None
    assert ("T", False, False) in rows_of(db, pid)


def test_deleted_folder_clears_local_tracks(
    db: Database, music: Path, make_mp3
) -> None:
    file = make_mp3(music / "Playlists" / "Gone" / "A - B.mp3")
    refresh_music_folder(db, music)
    file.unlink()
    file.parent.rmdir()
    stats = refresh_music_folder(db, music)
    assert stats.local_tracks_gone == 1


def test_missing_music_folder_fails_loudly(db: Database, tmp_path: Path) -> None:
    with pytest.raises(FolderMissingError):
        refresh_music_folder(db, tmp_path / "unplugged")


def test_single_playlist_scope(db: Database, music: Path, make_mp3) -> None:
    make_mp3(music / "Playlists" / "One" / "A - B.mp3")
    make_mp3(music / "Playlists" / "Two" / "C - D.mp3")
    stats = refresh_music_folder(db, music, playlist_name="one")
    assert (stats.folders, stats.local_tracks) == (1, 1)
