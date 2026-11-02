"""Apply chosen groups of a Plan to the Rekordbox library.

Each group is one unit: it is fully committed or fully rolled back. After a
failed group the library is reopened, so nothing (not even the playlist XML)
leaks into the next group. Cratekeeper's own database is only updated after the
group's Rekordbox commit succeeded.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pyrekordbox.db6 import tables

from ..db import repository as repo
from ..db.engine import Database
from ..db.models import Playlist, Track
from ..jobs import JobContext
from .connection import (
    RekordboxError,
    RekordboxLocation,
    commit_changes,
    fingerprint,
    open_library,
    require_closed,
)
from .content import ensure_genre, import_content
from .plan import DELETE_GROUP, Change, ChangeKind, Plan, PlanGroup

logger = logging.getLogger(__name__)

ROOT = "root"


class PlanStaleError(RekordboxError):
    """Raised when Rekordbox changed after the Plan was made."""


@dataclass
class GroupResult:
    """Outcome of one group."""

    key: str
    title: str
    status: str  # applied | failed
    error: Optional[str] = None
    warning: Optional[str] = None
    changes: int = 0


@dataclass
class ApplyResult:
    """Outcome of an Apply."""

    groups: list[GroupResult] = field(default_factory=list)

    @property
    def applied(self) -> int:
        """Return the number of applied groups."""
        return sum(1 for g in self.groups if g.status == "applied")

    @property
    def failed(self) -> int:
        """Return the number of failed groups."""
        return sum(1 for g in self.groups if g.status == "failed")


Opener = Callable[[Path], Any]


def apply_plan(
    db: Database,
    location: RekordboxLocation,
    plan: Plan,
    selected: set[str],
    ctx: Optional[JobContext] = None,
    *,
    open_db: Opener = open_library,
) -> ApplyResult:
    """Apply the selected groups.

    The caller takes a Backup before calling this.
    """
    require_closed()
    unknown = selected - {g.key for g in plan.groups}
    if unknown:
        raise ValueError(f"Unknown plan groups: {sorted(unknown)}")
    database = open_db(location.db_path)
    result = ApplyResult()
    try:
        if fingerprint(database) != plan.fingerprint:
            raise PlanStaleError(
                "Rekordbox changed after this plan was made. Make a new plan."
            )
        groups = [g for g in plan.groups if g.key in selected]
        groups.sort(key=lambda g: g.key == DELETE_GROUP)  # deletions last
        for index, group in enumerate(groups, start=1):
            if ctx is not None:
                ctx.check_cancelled()
                ctx.progress(index, len(groups), group.title)
            outcome, database = _apply_one(db, database, location, group, open_db)
            result.groups.append(outcome)
        _record_links(db, plan)
    finally:
        database.close()
    return result


def _apply_one(
    db: Database,
    database: Any,
    location: RekordboxLocation,
    group: PlanGroup,
    open_db: Opener,
) -> tuple[GroupResult, Any]:
    outcome = GroupResult(key=group.key, title=group.title, status="applied")
    try:
        applied = _GroupApplier(database, db).apply(group)
        outcome.warning = commit_changes(database)
        outcome.changes = len(group.changes)
    except Exception as exc:
        logger.warning("Group %r failed, rolled back: %s", group.title, exc)
        outcome.status = "failed"
        outcome.error = str(exc) or exc.__class__.__name__
        try:
            database.rollback()
        finally:
            database.close()
        return outcome, open_db(location.db_path)

    try:
        _record_group(db, group, applied)
    except Exception as exc:  # Rekordbox is already changed
        logger.exception("Cratekeeper could not record group %r", group.title)
        outcome.warning = (
            f"Rekordbox was updated, but Cratekeeper could not record it ({exc}). "
            "The next plan will show the current state."
        )
    return outcome, database


@dataclass
class _Applied:
    rekordbox_playlist_id: Optional[str] = None
    content_by_track: dict[int, str] = field(default_factory=dict)
    final_count: int = 0
    deleted_playlist_ids: list[int] = field(default_factory=list)


class _GroupApplier:
    """Runs the changes of one group inside the open library session."""

    def __init__(self, database: Any, db: Database) -> None:
        self.rb = database
        self.db = db

    def apply(self, group: PlanGroup) -> _Applied:
        applied = _Applied(rekordbox_playlist_id=group.rekordbox_playlist_id)
        if group.key == DELETE_GROUP:
            for change in group.changes:
                self._delete(change)
                if change.playlist_id is not None:
                    applied.deleted_playlist_ids.append(change.playlist_id)
            return applied

        changes = {k: [c for c in group.changes if c.kind is k] for k in ChangeKind}
        playlist = self._target_playlist(group, changes)
        applied.rekordbox_playlist_id = str(playlist.ID)
        tracks = self._load_tracks(group)
        self._import_tracks(changes[ChangeKind.IMPORT_TRACK], tracks, applied)
        self._set_genres(changes[ChangeKind.SET_GENRE])
        for change in changes[ChangeKind.REMOVE_TRACK]:
            self._remove_song(str(playlist.ID), _require(change.song_id))
        for change in changes[ChangeKind.ADD_TRACK]:
            content = self._content_for_add(change, applied)
            self.rb.add_to_playlist(playlist, content)
            if change.track_id is not None:
                applied.content_by_track[change.track_id] = str(content.ID)
        for track_id in group.member_track_ids:
            track = tracks.get(track_id)
            known = track.rekordbox_content_id if track is not None else None
            if track_id not in applied.content_by_track and known:
                applied.content_by_track[track_id] = known
        self.rb.flush()
        applied.final_count = (
            self.rb.session.query(tables.DjmdSongPlaylist)
            .filter_by(PlaylistID=str(playlist.ID))
            .count()
        )
        return applied

    def _import_tracks(
        self, changes: list[Change], tracks: dict[int, Track], applied: _Applied
    ) -> None:
        for change in changes:
            track = tracks[_require(change.track_id)]
            content = import_content(
                self.rb, track, Path(_require(change.file_path)), change.genre
            )
            applied.content_by_track[track.id] = str(content.ID)

    def _set_genres(self, changes: list[Change]) -> None:
        for change in changes:
            content = self.rb.get_content(ID=change.content_id)
            if content is None:
                raise RekordboxError(
                    f"Track {change.content_id} is gone from Rekordbox"
                )
            content.GenreID = ensure_genre(self.rb, _require(change.genre)).ID

    def _target_playlist(
        self, group: PlanGroup, changes: dict[ChangeKind, list[Change]]
    ) -> Any:
        creates = changes[ChangeKind.CREATE_PLAYLIST]
        if creates:
            change = creates[0]
            parent = self._ensure_folder(_require(change.folder))
            return self.rb.create_playlist(_require(change.name), parent=parent)
        playlist = self.rb.get_playlist(ID=group.rekordbox_playlist_id)
        if playlist is None:
            raise RekordboxError(
                f"Playlist {group.target_name!r} is gone from Rekordbox"
            )
        for change in changes[ChangeKind.RENAME_PLAYLIST]:
            self.rb.rename_playlist(playlist, _require(change.name))
        for change in changes[ChangeKind.MOVE_PLAYLIST]:
            parent = self._ensure_folder(_require(change.folder))
            self.rb.move_playlist(playlist, parent=parent)
        return playlist

    def _ensure_folder(self, path: list[str]) -> Optional[str]:
        """Return the ID of the folder at ``path``, creating missing levels."""
        parent = ROOT
        for name in path:
            found = (
                self.rb.session.query(tables.DjmdPlaylist)
                .filter_by(Name=name, ParentID=parent, Attribute=1)
                .order_by(tables.DjmdPlaylist.Seq)
                .first()
            )
            if found is None:
                found = self.rb.create_playlist_folder(
                    name, parent=None if parent == ROOT else parent
                )
                self.rb.flush()
            parent = str(found.ID)
        return None if parent == ROOT else parent

    def _remove_song(self, playlist_id: str, song_id: str) -> None:
        """Remove one song and renumber the rest, without committing.

        pyrekordbox's ``remove_from_playlist`` commits on its own, which would
        break the all-or-nothing group, so this repeats its steps.
        """
        song = (
            self.rb.session.query(tables.DjmdSongPlaylist).filter_by(ID=song_id).first()
        )
        if song is None:
            return
        track_no = song.TrackNo
        self.rb.delete(song)
        self.rb.flush()
        now = datetime.now()
        moved = []
        with self.rb.registry.disabled():
            for other in (
                self.rb.session.query(tables.DjmdSongPlaylist)
                .filter(
                    tables.DjmdSongPlaylist.PlaylistID == playlist_id,
                    tables.DjmdSongPlaylist.TrackNo > track_no,
                )
                .order_by(tables.DjmdSongPlaylist.TrackNo)
            ):
                other.TrackNo -= 1
                other.updated_at = now
                moved.append(other)
        if moved:
            self.rb.registry.on_move(moved)

    def _content_for_add(self, change: Change, applied: _Applied) -> Any:
        if change.content_id:
            content = self.rb.get_content(ID=change.content_id)
            if content is not None:
                return content
        if change.track_id is not None and change.track_id in applied.content_by_track:
            content = self.rb.get_content(ID=applied.content_by_track[change.track_id])
            if content is not None:
                return content
        if change.file_path:
            content = self.rb.get_content(FolderPath=change.file_path).first()
            if content is not None:
                return content
        raise RekordboxError(f"No Rekordbox track for {change.summary}")

    def _delete(self, change: Change) -> None:
        playlist = self.rb.get_playlist(ID=change.rekordbox_playlist_id)
        if playlist is not None:
            self.rb.delete_playlist(playlist)

    def _load_tracks(self, group: PlanGroup) -> dict[int, Track]:
        ids = {c.track_id for c in group.changes if c.track_id is not None}
        ids |= set(group.member_track_ids)
        tracks: dict[int, Track] = {}
        with self.db.session() as session:
            for track_id in ids:
                track = session.get(Track, track_id)
                if track is not None:
                    tracks[track_id] = track
        return tracks


def _record_group(db: Database, group: PlanGroup, applied: _Applied) -> None:
    now = repo.utc_now()
    with db.session() as session:
        for playlist_id in applied.deleted_playlist_ids:
            playlist = session.get(Playlist, playlist_id)
            if playlist is None:
                continue
            playlist.rekordbox_playlist_id = None
            playlist.track_count_rekordbox = 0
            for row in repo.playlist_rows(session, playlist_id).values():
                row.in_rekordbox = False
        if group.playlist_id is None:
            return
        playlist = session.get(Playlist, group.playlist_id)
        if playlist is None:
            return
        playlist.rekordbox_playlist_id = applied.rekordbox_playlist_id
        playlist.track_count_rekordbox = applied.final_count
        playlist.last_synced_at = now
        _set_membership(session, playlist.id, group.member_track_ids, now)
        for track_id, content_id in applied.content_by_track.items():
            track = session.get(Track, track_id)
            if track is not None:
                track.rekordbox_content_id = content_id


def _record_links(db: Database, plan: Plan) -> None:
    """Store links for playlists that already matched (v1 left stale flags)."""
    if not plan.links:
        return
    now = repo.utc_now()
    with db.session() as session:
        for link in plan.links:
            playlist = session.get(Playlist, link.playlist_id)
            if playlist is None:
                continue
            playlist.rekordbox_playlist_id = link.rekordbox_playlist_id
            playlist.track_count_rekordbox = len(link.member_track_ids)
            _set_membership(session, playlist.id, link.member_track_ids, now)
            for track_id, content_id in link.content_ids.items():
                track = session.get(Track, track_id)
                if track is not None:
                    track.rekordbox_content_id = content_id


def _set_membership(
    session: Any, playlist_id: int, members: list[int], now: Any
) -> None:
    wanted = set(members)
    for track_id, row in repo.playlist_rows(session, playlist_id).items():
        in_rekordbox = track_id in wanted
        if in_rekordbox and not row.in_rekordbox:
            row.added_to_rekordbox = now
        row.in_rekordbox = in_rekordbox


def _require(value: Any) -> Any:
    if value is None:
        raise RekordboxError("Plan change is missing a required field")
    return value
