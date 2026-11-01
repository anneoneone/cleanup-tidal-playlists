"""Build a Plan: compare the wanted Rekordbox state with the library. Writes nothing.

Wanted state per Playlist:
- Rekordbox membership (see CONTEXT.md): tracks in the Tidal playlist with a
  file, plus Bandcamp files, plus Local tracks; new tracks ordered by date added
- the emoji-free name and Folder placement from the Playlist tag mapping
- one genre per track, the same in every playlist (first genre, sorted)

Existing track order in Rekordbox is never changed; new tracks are appended.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from pyrekordbox.db6 import tables
from sqlalchemy import select

from ..db import repository as repo
from ..db.engine import Database
from ..db.models import Playlist, PlaylistTrack, Track
from ..music.paths import first_existing_file, nfc, require_folder
from .connection import fingerprint
from .naming import NameRules, added_date
from .plan import DELETE_GROUP, Change, ChangeKind, Plan, PlanGroup, PlaylistLink

logger = logging.getLogger(__name__)

ROOT = "root"


@dataclass
class _Member:
    track: Track
    path: Path
    order: Any


@dataclass
class _Library:
    """Read-only index of the Rekordbox library."""

    playlists: dict[str, Any] = field(default_factory=dict)  # ID -> row
    folders: dict[tuple[str, ...], str] = field(default_factory=dict)
    paths: dict[str, tuple[str, ...]] = field(default_factory=dict)  # ID -> path
    songs: dict[str, list[tuple[str, str, int]]] = field(default_factory=dict)
    content_by_path: dict[str, str] = field(default_factory=dict)
    content_path: dict[str, str] = field(default_factory=dict)
    content_genre: dict[str, Optional[str]] = field(default_factory=dict)
    content_by_isrc: dict[str, list[str]] = field(default_factory=dict)
    content_by_title_artist: dict[tuple[str, str], list[str]] = field(
        default_factory=dict
    )

    def folder_of(self, playlist_id: str) -> tuple[str, ...]:
        row = self.playlists.get(playlist_id)
        if row is None:
            return ()
        return self.paths.get(str(row.ParentID), ())


def load_library(database: Any) -> _Library:
    """Index playlists, folders, songs and contents of an open library."""
    lib = _Library()
    _index_playlists(database, lib)
    _index_songs(database, lib)
    _index_contents(database, lib)
    return lib


def _index_playlists(database: Any, lib: _Library) -> None:
    for row in database.session.query(tables.DjmdPlaylist):
        lib.playlists[str(row.ID)] = row

    def path_of(pid: str, seen: frozenset[str] = frozenset()) -> tuple[str, ...]:
        if pid == ROOT or pid not in lib.playlists or pid in seen:
            return ()
        row = lib.playlists[pid]
        return (*path_of(str(row.ParentID), seen | {pid}), str(row.Name))

    for pid, row in lib.playlists.items():
        if row.Attribute == 1:
            folder = path_of(pid)
            lib.paths[pid] = folder
            lib.folders.setdefault(folder, pid)


def _index_songs(database: Any, lib: _Library) -> None:
    columns = (
        tables.DjmdSongPlaylist.ID,
        tables.DjmdSongPlaylist.PlaylistID,
        tables.DjmdSongPlaylist.ContentID,
        tables.DjmdSongPlaylist.TrackNo,
    )
    for sid, pid, cid, track_no in database.session.query(*columns):
        lib.songs.setdefault(str(pid), []).append((str(sid), str(cid), track_no or 0))
    for songs in lib.songs.values():
        songs.sort(key=lambda s: s[2])


def _index_contents(database: Any, lib: _Library) -> None:
    query = database.session.query
    genres = {str(i): n for i, n in query(tables.DjmdGenre.ID, tables.DjmdGenre.Name)}
    artists = {
        str(i): (n or "").casefold()
        for i, n in query(tables.DjmdArtist.ID, tables.DjmdArtist.Name)
    }
    columns = (
        tables.DjmdContent.ID,
        tables.DjmdContent.FolderPath,
        tables.DjmdContent.GenreID,
        tables.DjmdContent.ISRC,
        tables.DjmdContent.Title,
        tables.DjmdContent.ArtistID,
    )
    for raw_id, folder_path, genre_id, isrc, title, artist_id in query(*columns):
        cid = str(raw_id)
        file_path = nfc(str(folder_path or ""))
        lib.content_path[cid] = file_path
        if file_path:
            lib.content_by_path.setdefault(file_path, cid)
        lib.content_genre[cid] = genres.get(str(genre_id)) if genre_id else None
        if isrc:
            lib.content_by_isrc.setdefault(str(isrc).upper(), []).append(cid)
        if title and artist_id:
            key = (str(title).casefold(), artists.get(str(artist_id), ""))
            lib.content_by_title_artist.setdefault(key, []).append(cid)


class Planner:
    """Builds Plans for one Cratekeeper database."""

    def __init__(
        self,
        db: Database,
        rules: NameRules,
        music_folder: Path,
        bandcamp_folder: Optional[Path],
        prune_tracks: bool = True,
    ) -> None:
        """Configure the planner."""
        self.db = db
        self.rules = rules
        self.music_folder = music_folder
        self.bandcamp_folder = bandcamp_folder
        self.prune_tracks = prune_tracks

    def build(
        self, database: Any, rekordbox_db: str, playlist_name: Optional[str] = None
    ) -> Plan:
        """Return the Plan for ``database`` (an open library, ideally a copy)."""
        require_folder(self.music_folder, "Music folder")
        lib = load_library(database)
        plan = Plan(
            created_at=repo.utc_now(),
            fingerprint=fingerprint(database),
            rekordbox_db=rekordbox_db,
            scope=playlist_name,
        )
        with self.db.session() as session:
            playlists, rows = self._load(session, playlist_name)
        self._check_bandcamp(rows)

        members = {p.id: self._members(rows.get(p.id, [])) for p in playlists}
        genres = self._track_genres(playlists, members)
        active = [p for p in playlists if not is_vanished(p, rows.get(p.id, []))]
        matches = self._match_all(active, lib)
        claimed: set[str] = set(matches.values())
        genre_done: set[str] = set()
        deletions: list[Change] = []
        empty = 0

        for playlist in playlists:
            if playlist not in active:
                change = self._deletion(playlist, lib, claimed)
                if change is not None:
                    deletions.append(change)
                continue
            group, link = self._plan_playlist(
                playlist,
                members[playlist.id],
                lib,
                matches.get(playlist.id),
                genres,
                genre_done,
            )
            if group is None and link is None:
                empty += 1
            if group is not None:
                plan.groups.append(group)
            elif link is not None:
                plan.links.append(link)
                plan.unchanged_playlists += 1

        if deletions:
            plan.groups.append(
                PlanGroup(
                    key=DELETE_GROUP,
                    title="Delete playlists that no Source has any more",
                    selected_by_default=False,
                    changes=deletions,
                )
            )
        plan.new_folders = sorted(
            {
                "/".join(c.folder)
                for g in plan.groups
                for c in g.changes
                if c.folder and tuple(c.folder) not in lib.folders
            }
        )
        if empty:
            plan.warnings.append(
                f"{empty} playlists have no files yet and are not created in Rekordbox"
            )
        return plan

    # -------------------------------------------------------------- loading

    def _load(
        self, session: Any, playlist_name: Optional[str]
    ) -> tuple[list[Playlist], dict[int, list[PlaylistTrack]]]:
        playlists = list(repo.all_playlists(session))
        if playlist_name is not None:
            key = repo.name_key(playlist_name)
            playlists = [p for p in playlists if repo.name_key(p.name) == key]
            if not playlists:
                raise LookupError(f"No playlist named {playlist_name!r}")
        ids = [p.id for p in playlists]
        rows: dict[int, list[PlaylistTrack]] = defaultdict(list)
        if ids:
            stmt = (
                select(PlaylistTrack, Track)
                .join(Track, Track.id == PlaylistTrack.track_id)
                .where(PlaylistTrack.playlist_id.in_(ids))
            )
            for row, track in session.execute(stmt):
                row.track = track
                rows[row.playlist_id].append(row)
        return playlists, rows

    def _check_bandcamp(self, rows: dict[int, list[PlaylistTrack]]) -> None:
        uses_bandcamp = any(r.in_bandcamp for group in rows.values() for r in group)
        if uses_bandcamp:
            if self.bandcamp_folder is None:
                return
            require_folder(self.bandcamp_folder, "Bandcamp folder")

    def _members(self, rows: list[PlaylistTrack]) -> list[_Member]:
        members = []
        for row in rows:
            if not (row.in_tidal or row.in_bandcamp or row.in_local):
                continue
            path = first_existing_file(row.track.file_paths, self.music_folder)
            if path is None:
                continue
            order = added_date(
                row.added_to_tidal if row.in_tidal else None,
                row.added_to_local,
                row.track.created_at,
            )
            members.append(_Member(track=row.track, path=path, order=order))
        members.sort(key=lambda m: (m.order, m.track.id))
        return members

    def _track_genres(
        self, playlists: list[Playlist], members: dict[int, list[_Member]]
    ) -> dict[int, str]:
        candidates: dict[int, set[str]] = defaultdict(set)
        for playlist in playlists:
            genre = self.rules.genre(self.rules.parse(playlist.name))
            if genre is None:
                continue
            for member in members.get(playlist.id, []):
                candidates[member.track.id].add(genre)
        return {tid: sorted(names)[0] for tid, names in candidates.items()}

    # ------------------------------------------------------------ matching

    def _match_all(self, playlists: list[Playlist], lib: _Library) -> dict[int, str]:
        """Match Playlists to Rekordbox playlists: exact rules first, then fallbacks.

        Exact: stored ID, then the clean (or v1 legacy) name inside the target
        folder. Fallback: the emoji name, then the clean name, anywhere, if unique.
        """
        matcher = _Matcher(lib)
        names = {}
        for playlist in playlists:
            tags = self.rules.parse(playlist.name)
            names[playlist.id] = (
                self.rules.rekordbox_name(tags, include_status=True),
                self.rules.rekordbox_name(tags, include_status=False),
                tuple(self.rules.folder_path(tags)),
            )
        for playlist in playlists:
            if playlist.rekordbox_playlist_id in matcher.free:
                matcher.claim(playlist.id, playlist.rekordbox_playlist_id)
        for playlist in matcher.pending(playlists):
            clean, legacy, folder = names[playlist.id]
            found = matcher.find(clean, folder) or matcher.find(legacy, folder)
            matcher.claim(playlist.id, found)
        for playlist in matcher.pending(playlists):
            clean = names[playlist.id][0]
            found = matcher.find(playlist.name, None) or matcher.find(clean, None)
            matcher.claim(playlist.id, found)
        return matcher.matches

    def _content_for(self, member: _Member, lib: _Library) -> Optional[str]:
        path = nfc(str(member.path))
        if path in lib.content_by_path:
            return lib.content_by_path[path]
        track = member.track
        stored = track.rekordbox_content_id
        if stored and stored in lib.content_path:
            stored_path = lib.content_path[stored]
            own_paths = {
                nfc(str(first_existing_file([p], self.music_folder) or ""))
                for p in track.file_paths or []
            }
            if stored_path and stored_path in own_paths:
                return stored
        if track.isrc:
            hits = lib.content_by_isrc.get(track.isrc.upper(), [])
            if len(hits) == 1:
                return hits[0]
        hits = lib.content_by_title_artist.get(
            ((track.title or "").casefold(), (track.artist or "").casefold()), []
        )
        return hits[0] if len(hits) == 1 else None

    # ------------------------------------------------------------- planning

    def _plan_playlist(
        self,
        playlist: Playlist,
        members: list[_Member],
        lib: _Library,
        rb_id: Optional[str],
        genres: dict[int, str],
        genre_done: set[str],
    ) -> tuple[Optional[PlanGroup], Optional[PlaylistLink]]:
        tags = self.rules.parse(playlist.name)
        clean = self.rules.rekordbox_name(tags, include_status=True)
        folder = tuple(self.rules.folder_path(tags))
        if rb_id is None and not members:
            return None, None

        group = PlanGroup(
            key=f"playlist:{playlist.id}",
            title=playlist.name,
            playlist_id=playlist.id,
            rekordbox_playlist_id=rb_id,
            target_name=clean,
            folder=list(folder),
            member_track_ids=[m.track.id for m in members],
        )
        if rb_id is None:
            group.changes.append(
                Change(
                    kind=ChangeKind.CREATE_PLAYLIST,
                    summary=f"Create playlist {clean!r} in {'/'.join(folder)}",
                    name=clean,
                    folder=list(folder),
                )
            )
        else:
            row = lib.playlists[rb_id]
            if row.Name != clean:
                group.changes.append(
                    Change(
                        kind=ChangeKind.RENAME_PLAYLIST,
                        summary=f"Rename {row.Name!r} to {clean!r}",
                        name=clean,
                        old_name=str(row.Name),
                        rekordbox_playlist_id=rb_id,
                    )
                )
            current_folder = lib.folder_of(rb_id)
            if current_folder != folder:
                group.changes.append(
                    Change(
                        kind=ChangeKind.MOVE_PLAYLIST,
                        summary=(
                            f"Move from {'/'.join(current_folder) or 'top level'} "
                            f"to {'/'.join(folder)}"
                        ),
                        folder=list(folder),
                        old_folder=list(current_folder),
                        rekordbox_playlist_id=rb_id,
                    )
                )

        content_ids = self._track_changes(
            group, members, lib, rb_id, genres, genre_done
        )
        if group.changes:
            return group, None
        if rb_id is None:
            return None, None
        link = PlaylistLink(
            playlist_id=playlist.id,
            rekordbox_playlist_id=rb_id,
            member_track_ids=group.member_track_ids,
            content_ids=content_ids,
        )
        return None, link

    def _track_changes(
        self,
        group: PlanGroup,
        members: list[_Member],
        lib: _Library,
        rb_id: Optional[str],
        genres: dict[int, str],
        genre_done: set[str],
    ) -> dict[int, str]:
        current = lib.songs.get(rb_id, []) if rb_id else []
        wanted = [(m, self._content_for(m, lib)) for m in members]
        content_ids = {m.track.id: cid for m, cid in wanted if cid is not None}
        group.changes += self._import_and_genre_changes(wanted, lib, genres, genre_done)
        if self.prune_tracks:
            wanted_ids = set(content_ids.values())
            group.changes += _removal_changes(current, wanted_ids, lib)
        group.changes += _add_changes(wanted, {cid for _, cid, _ in current})
        return content_ids

    def _import_and_genre_changes(
        self,
        wanted: list[tuple[_Member, Optional[str]]],
        lib: _Library,
        genres: dict[int, str],
        genre_done: set[str],
    ) -> list[Change]:
        changes = []
        for member, cid in wanted:
            genre = genres.get(member.track.id)
            if cid is None:
                changes.append(
                    Change(
                        kind=ChangeKind.IMPORT_TRACK,
                        summary=f"Import {member.path.name}",
                        track_id=member.track.id,
                        file_path=str(member.path),
                        genre=genre,
                    )
                )
            elif (
                genre and lib.content_genre.get(cid) != genre and cid not in genre_done
            ):
                genre_done.add(cid)
                label = f"{member.track.artist} - {member.track.title}"
                changes.append(
                    Change(
                        kind=ChangeKind.SET_GENRE,
                        summary=f"Set genre of {label} to {genre}",
                        track_id=member.track.id,
                        content_id=cid,
                        genre=genre,
                    )
                )
        return changes

    def _deletion(
        self, playlist: Playlist, lib: _Library, claimed: set[str]
    ) -> Optional[Change]:
        rb_id = playlist.rekordbox_playlist_id
        if not rb_id or rb_id not in lib.playlists or rb_id in claimed:
            return None
        row = lib.playlists[rb_id]
        if row.Attribute != 0:
            return None
        claimed.add(rb_id)
        return Change(
            kind=ChangeKind.DELETE_PLAYLIST,
            summary=f"Delete {row.Name!r} ({playlist.name} is gone from all Sources)",
            playlist_id=playlist.id,
            rekordbox_playlist_id=rb_id,
            name=str(row.Name),
        )


class _Matcher:
    """Hands out each Rekordbox playlist to at most one Playlist."""

    def __init__(self, lib: _Library) -> None:
        self.lib = lib
        self.free = {pid for pid, row in lib.playlists.items() if row.Attribute == 0}
        self.matches: dict[int, str] = {}

    def pending(self, playlists: list[Playlist]) -> list[Playlist]:
        return [p for p in playlists if p.id not in self.matches]

    def claim(self, playlist_id: int, rb_id: Optional[str]) -> None:
        if rb_id is not None:
            self.matches[playlist_id] = rb_id
            self.free.discard(rb_id)

    def find(self, name: str, folder: Optional[tuple[str, ...]]) -> Optional[str]:
        hits = sorted(
            pid
            for pid in self.free
            if self.lib.playlists[pid].Name == name
            and (folder is None or self.lib.folder_of(pid) == folder)
        )
        if len(hits) == 1 or (hits and folder is not None):
            return hits[0]
        return None


def _removal_changes(
    current: list[tuple[str, str, int]], wanted_ids: set[str], lib: _Library
) -> list[Change]:
    changes = []
    seen: set[str] = set()
    for song_id, cid, _ in current:
        duplicate = cid in seen
        seen.add(cid)
        if cid in wanted_ids and not duplicate:
            continue
        name = Path(lib.content_path.get(cid, "")).name or cid
        why = "duplicate" if duplicate else "no longer in the playlist"
        changes.append(
            Change(
                kind=ChangeKind.REMOVE_TRACK,
                summary=f"Remove {name} ({why})",
                content_id=cid,
                song_id=song_id,
            )
        )
    return changes


def _add_changes(
    wanted: list[tuple[_Member, Optional[str]]], present: set[str]
) -> list[Change]:
    changes = []
    for member, cid in wanted:
        if cid is not None and cid in present:
            continue
        changes.append(
            Change(
                kind=ChangeKind.ADD_TRACK,
                summary=f"Add {member.track.artist} - {member.track.title}",
                track_id=member.track.id,
                content_id=cid,
                file_path=str(member.path),
            )
        )
        if cid is not None:
            present.add(cid)
    return changes


def is_vanished(playlist: Playlist, rows: list[PlaylistTrack]) -> bool:
    """Return whether no Source has the playlist any more."""
    if playlist.in_tidal:
        return False
    return not any(r.in_bandcamp or r.in_local for r in rows)
