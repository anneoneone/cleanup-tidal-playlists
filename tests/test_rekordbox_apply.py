from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pytest
from pyrekordbox.db6 import tables

import cratekeeper.rekordbox.connection as connection
from cratekeeper.db import Database, Playlist, PlaylistTrack, Track
from cratekeeper.db import repository as repo
from cratekeeper.music.paths import FolderMissingError
from cratekeeper.rekordbox.applier import PlanStaleError, apply_plan
from cratekeeper.rekordbox.connection import (
    RekordboxLocation,
    RekordboxRunningError,
    commit_changes,
    open_library,
    planning_copy,
)
from cratekeeper.rekordbox.naming import NameRules
from cratekeeper.rekordbox.plan import DELETE_GROUP, ChangeKind, Plan
from cratekeeper.rekordbox.planner import Planner
from cratekeeper.settings import default_tag_mapping_path


class World:
    """Cratekeeper DB + Music folder + Rekordbox library for one test."""

    def __init__(self, tmp_path: Path, library: Path, make_mp3: Any) -> None:
        self.db = Database(tmp_path / "ck.db")
        self.db.prepare()
        self.music = tmp_path / "music"
        (self.music / "Playlists").mkdir(parents=True)
        self.location = RekordboxLocation(db_path=library)
        self.make_mp3 = make_mp3
        self.rules = NameRules.from_file(default_tag_mapping_path())
        self.bandcamp: Optional[Path] = None
        self.prune = True

    def playlist(self, name: str, **kw: Any) -> int:
        with self.db.session() as s:
            playlist = Playlist(
                name=name, tidal_id=kw.pop("tidal_id", name), in_tidal=True, **kw
            )
            s.add(playlist)
            s.flush()
            return playlist.id

    def track(
        self,
        playlist_id: int,
        artist: str,
        title: str,
        added: datetime,
        *,
        in_tidal: bool = True,
        with_file: bool = True,
    ) -> int:
        stored = f"Playlists/P{playlist_id}/{artist} - {title}.mp3"
        if with_file:
            self.make_mp3(self.music / stored, title=title, artist=artist)
        with self.db.session() as s:
            track = repo.track_by_stored_path(s, stored)
            if track is None:
                track = Track(
                    tidal_id=f"{artist}-{title}",
                    title=title,
                    artist=artist,
                    normalized_name="x",
                    file_paths=[stored],
                )
                s.add(track)
                s.flush()
            s.add(
                PlaylistTrack(
                    playlist_id=playlist_id,
                    track_id=track.id,
                    in_tidal=in_tidal,
                    added_to_tidal=added,
                )
            )
            return track.id

    def add_to_playlist(self, playlist_id: int, track_id: int) -> None:
        with self.db.session() as s:
            s.add(
                PlaylistTrack(playlist_id=playlist_id, track_id=track_id, in_tidal=True)
            )

    def plan(self, playlist_name: Optional[str] = None) -> Plan:
        planner = Planner(self.db, self.rules, self.music, self.bandcamp, self.prune)
        with planning_copy(self.location) as copy:
            return planner.build(copy, str(self.location.db_path), playlist_name)

    def apply(self, plan: Plan, selected: Optional[set[str]] = None) -> Any:
        keys = (
            selected
            if selected is not None
            else {g.key for g in plan.groups if g.selected_by_default}
        )
        return apply_plan(self.db, self.location, plan, keys)

    def rekordbox(self) -> Any:
        return open_library(self.location.db_path)

    def songs(self, name: str) -> list[tuple[int, str]]:
        rb = self.rekordbox()
        try:
            playlist = rb.get_playlist(Name=name, Attribute=0).one()
            rows = (
                rb.session.query(tables.DjmdSongPlaylist)
                .filter_by(PlaylistID=playlist.ID)
                .order_by(tables.DjmdSongPlaylist.TrackNo)
            )
            return [(s.TrackNo, Path(s.Content.FolderPath).stem) for s in rows]
        finally:
            rb.close()

    def folder_path(self, name: str) -> list[str]:
        rb = self.rekordbox()
        try:
            playlist = rb.get_playlist(Name=name, Attribute=0).one()
            path = []
            parent = playlist.ParentID
            while parent != "root":
                folder = rb.get_playlist(ID=parent)
                path.insert(0, folder.Name)
                parent = folder.ParentID
            return path
        finally:
            rb.close()


@pytest.fixture
def world(tmp_path: Path, rekordbox_library: Path, make_mp3: Any) -> World:
    return World(tmp_path, rekordbox_library, make_mp3)


def kinds(plan: Plan) -> list[str]:
    return [c.kind.value for g in plan.groups for c in g.changes]


def test_new_playlist_is_created_in_its_folder_in_date_order(world: World) -> None:
    pid = world.playlist("Peak Time 🏢⬆️")
    world.track(pid, "B", "Second", datetime(2025, 2, 1))
    world.track(pid, "A", "First", datetime(2025, 1, 1))

    plan = world.plan()

    assert kinds(plan) == [
        "create_playlist",
        "import_track",
        "import_track",
        "add_track",
        "add_track",
    ]
    assert plan.new_folders == ["Genre/Techno/Archived"]
    result = world.apply(plan)
    assert (result.applied, result.failed) == (1, 0)
    assert world.songs("Peak Time High") == [(1, "A - First"), (2, "B - Second")]
    assert world.folder_path("Peak Time High") == ["Genre", "Techno", "Archived"]

    with world.db.session() as s:
        playlist = s.get(Playlist, pid)
        assert playlist is not None and playlist.rekordbox_playlist_id
        assert playlist.track_count_rekordbox == 2
        rows = repo.playlist_rows(s, pid).values()
        assert all(r.in_rekordbox for r in rows)
    assert world.plan().is_empty


def test_status_emoji_change_moves_and_renames_without_duplicate(world: World) -> None:
    pid = world.playlist("Peak 🏢❓")
    world.track(pid, "A", "T", datetime(2025, 1, 1))
    world.apply(world.plan())
    with world.db.session() as s:
        playlist = s.get(Playlist, pid)
        assert playlist is not None
        playlist.name = "Peak 🏢💾"

    plan = world.plan()

    assert kinds(plan) == ["rename_playlist", "move_playlist"]
    world.apply(plan)
    assert world.folder_path("Peak") == ["Genre", "Techno", "Archived"]
    rb = world.rekordbox()
    try:
        names = [p.Name for p in rb.get_playlist(Attribute=0)]
    finally:
        rb.close()
    assert names == ["Peak"]


def test_removed_tidal_track_leaves_playlist_and_numbers_stay_contiguous(
    world: World,
) -> None:
    pid = world.playlist("Mix 🏢")
    world.track(pid, "A", "One", datetime(2025, 1, 1))
    gone = world.track(pid, "B", "Two", datetime(2025, 1, 2))
    world.track(pid, "C", "Three", datetime(2025, 1, 3))
    world.apply(world.plan())
    with world.db.session() as s:
        repo.playlist_rows(s, pid)[gone].in_tidal = False

    plan = world.plan()

    assert kinds(plan) == ["remove_track"]
    world.apply(plan)
    assert world.songs("Mix") == [(1, "A - One"), (2, "C - Three")]
    with world.db.session() as s:
        assert repo.playlist_rows(s, pid)[gone].in_rekordbox is False


def test_hand_added_song_is_removed_only_when_pruning(world: World) -> None:
    pid = world.playlist("Mix 🏢")
    world.track(pid, "A", "One", datetime(2025, 1, 1))
    world.apply(world.plan())
    extra = world.music / "manual.mp3"
    world.make_mp3(extra)
    rb = world.rekordbox()
    try:
        playlist = rb.get_playlist(Name="Mix", Attribute=0).one()
        rb.add_to_playlist(playlist, rb.add_content(str(extra), Title="Manual"))
        commit_changes(rb)
    finally:
        rb.close()

    world.prune = False
    assert world.plan().is_empty
    world.prune = True
    assert kinds(world.plan()) == ["remove_track"]


def test_vanished_playlist_goes_to_unselected_delete_group(world: World) -> None:
    pid = world.playlist("Old 🏢")
    world.track(pid, "A", "One", datetime(2025, 1, 1))
    world.apply(world.plan())
    with world.db.session() as s:
        playlist = s.get(Playlist, pid)
        assert playlist is not None
        playlist.in_tidal = False

    plan = world.plan()

    assert [g.key for g in plan.groups] == [DELETE_GROUP]
    assert plan.groups[0].selected_by_default is False
    world.apply(plan)  # default selection: nothing
    assert world.songs("Old") == [(1, "A - One")]
    world.apply(world.plan(), {DELETE_GROUP})
    rb = world.rekordbox()
    try:
        assert rb.get_playlist(Name="Old", Attribute=0).count() == 0
    finally:
        rb.close()
    with world.db.session() as s:
        playlist = s.get(Playlist, pid)
        assert playlist is not None and playlist.rekordbox_playlist_id is None


def test_genre_is_the_same_in_every_playlist(world: World) -> None:
    techno = world.playlist("T 🏢")
    house = world.playlist("H ☀️")
    track_id = world.track(techno, "A", "Shared", datetime(2025, 1, 1))
    world.add_to_playlist(house, track_id)

    plan = world.plan()
    world.apply(plan)

    rb = world.rekordbox()
    try:
        content = rb.get_content().one()
        assert content.Genre.Name == "House House"  # sorted first of both genres
    finally:
        rb.close()
    assert world.plan().is_empty


def test_changed_library_makes_plan_stale(world: World) -> None:
    pid = world.playlist("Mix 🏢")
    world.track(pid, "A", "One", datetime(2025, 1, 1))
    plan = world.plan()
    rb = world.rekordbox()
    try:
        rb.create_playlist("Made in Rekordbox")
        commit_changes(rb)
    finally:
        rb.close()
    with pytest.raises(PlanStaleError):
        world.apply(plan)


def test_refuses_while_rekordbox_runs(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = world.playlist("Mix 🏢")
    world.track(pid, "A", "One", datetime(2025, 1, 1))
    plan = world.plan()
    monkeypatch.setattr(connection, "get_rekordbox_pid", lambda: 4242)
    with pytest.raises(RekordboxRunningError):
        world.apply(plan)


def test_failed_group_rolls_back_and_others_apply(world: World) -> None:
    good = world.playlist("Good 🏢")
    world.track(good, "A", "One", datetime(2025, 1, 1))
    bad = world.playlist("Bad 🏢")
    world.track(bad, "B", "Two", datetime(2025, 1, 1))
    plan = world.plan()
    (world.music / f"Playlists/P{bad}/B - Two.mp3").unlink()  # vanishes before apply

    result = world.apply(plan)

    assert {g.title: g.status for g in result.groups} == {
        "Good 🏢": "applied",
        "Bad 🏢": "failed",
    }
    rb = world.rekordbox()
    try:
        names = sorted(p.Name for p in rb.get_playlist(Attribute=0))
        xml_ids = {n.attrib["Id"] for n in rb.playlist_xml.playlists}
    finally:
        rb.close()
    assert names == ["Good"]
    assert len(xml_ids) == len(names) + 3  # Good + its three folders
    with world.db.session() as s:
        bad_playlist = s.get(Playlist, bad)
        assert bad_playlist is not None and bad_playlist.rekordbox_playlist_id is None


def test_missing_folders_stop_planning(world: World, tmp_path: Path) -> None:
    pid = world.playlist("Mix 🏢")
    world.track(pid, "A", "One", datetime(2025, 1, 1))
    with world.db.session() as s:
        repo.playlist_rows(s, pid).popitem()[1].in_bandcamp = True
    world.bandcamp = tmp_path / "unplugged-bandcamp"
    with pytest.raises(FolderMissingError, match="Bandcamp folder"):
        world.plan()
    world.music = tmp_path / "unplugged-music"
    with pytest.raises(FolderMissingError, match="Music folder"):
        world.plan()


def test_playlists_without_files_are_not_created(world: World) -> None:
    pid = world.playlist("Pending 🏢")
    world.track(pid, "A", "One", datetime(2025, 1, 1), with_file=False)
    plan = world.plan()
    assert plan.is_empty
    assert plan.warnings == [
        "1 playlists have no files yet and are not created in Rekordbox"
    ]


def test_v1_playlist_in_target_folder_is_adopted(world: World) -> None:
    rb = world.rekordbox()
    try:
        genre = rb.create_playlist_folder("Genre")
        techno = rb.create_playlist_folder("Techno", parent=genre)
        archived = rb.create_playlist_folder("Archived", parent=techno)
        rb.create_playlist("Mix", parent=archived)
        commit_changes(rb)
    finally:
        rb.close()
    pid = world.playlist("Mix 🏢")
    world.track(pid, "A", "One", datetime(2025, 1, 1))

    plan = world.plan()

    assert ChangeKind.CREATE_PLAYLIST.value not in kinds(plan)
    assert plan.new_folders == []
