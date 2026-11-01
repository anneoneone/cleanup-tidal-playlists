"""The Plan: every change a sync would make to Rekordbox, grouped per Playlist."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

DELETE_GROUP = "delete"


class ChangeKind(str, Enum):
    """What one change does."""

    CREATE_PLAYLIST = "create_playlist"
    RENAME_PLAYLIST = "rename_playlist"
    MOVE_PLAYLIST = "move_playlist"
    IMPORT_TRACK = "import_track"  # add a file to the Rekordbox collection
    ADD_TRACK = "add_track"
    REMOVE_TRACK = "remove_track"
    SET_GENRE = "set_genre"
    DELETE_PLAYLIST = "delete_playlist"


class Change(BaseModel):
    """One change.

    Fields that do not apply to the kind stay empty.
    """

    kind: ChangeKind
    summary: str
    track_id: Optional[int] = None
    file_path: Optional[str] = None
    content_id: Optional[str] = None
    song_id: Optional[str] = None
    name: Optional[str] = None
    old_name: Optional[str] = None
    folder: Optional[list[str]] = None
    old_folder: Optional[list[str]] = None
    genre: Optional[str] = None
    playlist_id: Optional[int] = None
    rekordbox_playlist_id: Optional[str] = None


class PlanGroup(BaseModel):
    """Changes for one Playlist (or the playlist deletions).

    Applied as one unit.
    """

    key: str
    title: str
    playlist_id: Optional[int] = None
    rekordbox_playlist_id: Optional[str] = None
    target_name: Optional[str] = None
    folder: list[str] = Field(default_factory=list)
    selected_by_default: bool = True
    changes: list[Change] = Field(default_factory=list)
    # Track IDs that should be in the Rekordbox playlist after apply (in order)
    member_track_ids: list[int] = Field(default_factory=list)

    def count(self, kind: ChangeKind) -> int:
        """Return how many changes of ``kind`` the group has."""
        return sum(1 for c in self.changes if c.kind is kind)


class PlaylistLink(BaseModel):
    """A Playlist that already matches its Rekordbox playlist (bookkeeping only)."""

    playlist_id: int
    rekordbox_playlist_id: str
    member_track_ids: list[int] = Field(default_factory=list)
    content_ids: dict[int, str] = Field(default_factory=dict)


class Plan(BaseModel):
    """A complete Plan.

    Applying it is only allowed while the fingerprint matches.
    """

    created_at: datetime
    fingerprint: str
    rekordbox_db: str
    scope: Optional[str] = None
    groups: list[PlanGroup] = Field(default_factory=list)
    links: list[PlaylistLink] = Field(default_factory=list)
    new_folders: list[str] = Field(default_factory=list)
    unchanged_playlists: int = 0
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return whether there is nothing to change."""
        return not any(g.changes for g in self.groups)

    def totals(self) -> dict[str, int]:
        """Return change counts by kind across all groups."""
        totals = {kind.value: 0 for kind in ChangeKind}
        for group in self.groups:
            for change in group.changes:
                totals[change.kind.value] += 1
        return totals

    def group(self, key: str) -> Optional[PlanGroup]:
        """Return the group with ``key``."""
        return next((g for g in self.groups if g.key == key), None)
