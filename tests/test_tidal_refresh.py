from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from cratekeeper.db import Database, Playlist, PlaylistTrack, Track
from cratekeeper.db import repository as repo
from cratekeeper.tidal.client import TidalPlaylist, TidalTrack, TrackListing
from cratekeeper.tidal.refresh import PlaylistShrinkError, refresh_tidal


class FakeTidal:
    def __init__(self) -> None:
        self.lists: list[TidalPlaylist] = []
        self.tracks: dict[str, list[TidalTrack]] = {}
        self.expected: dict[str, int] = {}
        self.fetches: list[str] = []

    def add(self, pid: str, name: str, tracks: list[TidalTrack], **kw) -> None:
        self.lists.append(
            TidalPlaylist(
                id=pid,
                name=name,
                last_updated=datetime(2026, 1, 1),
                num_tracks=len(tracks),
                **kw,
            )
        )
        self.tracks[pid] = tracks

    def playlists(self) -> list[TidalPlaylist]:
        return list(self.lists)

    def playlist_tracks(self, playlist_id: str) -> TrackListing:
        self.fetches.append(playlist_id)
        tracks = self.tracks[playlist_id]
        return TrackListing(
            tracks=tracks, expected_count=self.expected.get(playlist_id, len(tracks))
        )


def track(tid: str, title: str = "", **kw) -> TidalTrack:
    return TidalTrack(id=tid, title=title or f"Title {tid}", artist="Artist", **kw)


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "ck.db")
    database.prepare()
    return database


def rows(db: Database, name: str) -> dict[str, tuple[bool, int | None]]:
    with db.session() as s:
        playlist = repo.playlist_by_name(s, name)
        assert playlist is not None
        result = s.execute(
            select(Track.tidal_id, PlaylistTrack.in_tidal, PlaylistTrack.position)
            .join(Track, Track.id == PlaylistTrack.track_id)
            .where(PlaylistTrack.playlist_id == playlist.id)
        )
        return {tid: (in_tidal, pos) for tid, in_tidal, pos in result}


def test_first_refresh_creates_playlists_and_tracks(db: Database) -> None:
    fake = FakeTidal()
    added = datetime(2025, 5, 1, 12, 0)
    fake.add("p1", "House", [track("1", isrc="ISRC1", date_added=added), track("2")])

    stats = refresh_tidal(db, fake)

    assert (stats.playlists_created, stats.tracks_added) == (1, 2)
    assert rows(db, "House") == {"1": (True, 0), "2": (True, 1)}
    with db.session() as s:
        t1 = repo.track_by_tidal_id(s, "1")
        assert t1 is not None and t1.isrc == "ISRC1"
        assert t1.normalized_name == "artist - title 1"
        row = s.scalars(
            select(PlaylistTrack).where(PlaylistTrack.track_id == t1.id)
        ).one()
        assert row.added_to_tidal == added


def test_unchanged_playlist_is_not_fetched_again(db: Database) -> None:
    fake = FakeTidal()
    fake.add("p1", "House", [track("1")])
    refresh_tidal(db, fake)
    stats = refresh_tidal(db, fake)
    assert stats.playlists_unchanged == 1
    assert fake.fetches == ["p1"]
    refresh_tidal(db, fake, full=True)
    assert fake.fetches == ["p1", "p1"]


def test_removed_track_keeps_row_with_in_tidal_false(db: Database) -> None:
    fake = FakeTidal()
    fake.add("p1", "House", [track("1"), track("2")])
    refresh_tidal(db, fake)
    fake.lists = []
    fake.add("p1", "House", [track("2")], description="changed")
    fake.lists[0] = replace(fake.lists[0], last_updated=datetime(2026, 2, 1))

    stats = refresh_tidal(db, fake)

    assert stats.tracks_removed == 1
    assert rows(db, "House") == {"1": (False, 0), "2": (True, 0)}


def test_incomplete_listing_skips_removals(db: Database) -> None:
    fake = FakeTidal()
    fake.add("p1", "Big", [track("1"), track("2")])
    refresh_tidal(db, fake)
    fake.tracks["p1"] = [track("1")]
    fake.expected["p1"] = 2

    stats = refresh_tidal(db, fake, full=True)

    assert stats.incomplete == ["Big"]
    assert rows(db, "Big") == {"1": (True, 0), "2": (True, 1)}
    with db.session() as s:
        playlist = repo.playlist_by_name(s, "Big")
        assert playlist is not None and playlist.last_updated_tidal is None


def test_duplicates_in_one_playlist_keep_first_position(db: Database) -> None:
    fake = FakeTidal()
    fake.add("p1", "Dupes", [track("1"), track("2"), track("1")])
    stats = refresh_tidal(db, fake)
    assert stats.duplicates_dropped == 1
    assert rows(db, "Dupes") == {"1": (True, 0), "2": (True, 1)}


def test_rename_and_gone_playlists(db: Database) -> None:
    fake = FakeTidal()
    for i in range(5):
        fake.add(f"p{i}", f"List {i}", [track(f"t{i}")])
    refresh_tidal(db, fake)
    fake.lists = [replace(p, name=p.name + " 💾") for p in fake.lists[:4]]

    stats = refresh_tidal(db, fake)

    assert (stats.playlists_renamed, stats.playlists_gone) == (4, 1)
    with db.session() as s:
        gone = repo.playlist_by_tidal_id(s, "p4")
        assert gone is not None and gone.in_tidal is False
        renamed = repo.playlist_by_tidal_id(s, "p0")
        assert renamed is not None and renamed.name == "List 0 💾"
    assert rows(db, "List 4") == {"t4": (False, 0)}


def test_shrink_guard(db: Database) -> None:
    fake = FakeTidal()
    for i in range(6):
        fake.add(f"p{i}", f"L{i}", [])
    refresh_tidal(db, fake)
    fake.lists = fake.lists[:2]
    with pytest.raises(PlaylistShrinkError, match="--allow-shrink"):
        refresh_tidal(db, fake)
    fake.lists = []
    with pytest.raises(PlaylistShrinkError):
        refresh_tidal(db, fake)
    stats = refresh_tidal(db, fake, allow_shrink=True)
    assert stats.playlists_gone == 6


def test_adopts_local_playlist_with_same_name(db: Database) -> None:
    with db.session() as s:
        s.add(Playlist(name="Deep Cuts", source="local"))
    fake = FakeTidal()
    fake.add("p1", "deep cuts", [track("1")])
    stats = refresh_tidal(db, fake)
    assert stats.playlists_created == 0
    with db.session() as s:
        assert len(repo.all_playlists(s)) == 1


def test_single_playlist_scope(db: Database) -> None:
    fake = FakeTidal()
    fake.add("p1", "One", [track("1")])
    fake.add("p2", "Two", [track("2")])
    refresh_tidal(db, fake)
    fake.lists = fake.lists[:1]
    stats = refresh_tidal(db, fake, playlist_name="ONE", full=True)
    assert (stats.playlists, stats.playlists_gone) == (1, 0)
    with pytest.raises(LookupError):
        refresh_tidal(db, fake, playlist_name="Missing")
