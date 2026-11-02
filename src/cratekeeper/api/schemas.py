"""Request and response models of the web API (the contract for the UI)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from ..rekordbox.plan import Plan
from .picker import PickField

Source = Literal["tidal", "bandcamp", "library"]
# Where a track stands for one target (its file, Rekordbox):
# present = there and wanted, absent = not there, unsynced = there but removed
# from every Source, missing = wanted and was there, but is gone now.
TargetState = Literal["present", "absent", "unsynced", "missing"]
# A track in a USB stick's copy of a Playlist: present = wanted, unsynced = removed
# from every Source of the Playlist
StickState = Literal["present", "unsynced"]


class Check(BaseModel):
    """One health check on the dashboard."""

    key: str
    label: str
    ok: Optional[bool] = None  # None: informational
    detail: str


class RunOut(BaseModel):
    """One sync, apply or restore."""

    id: int
    kind: str
    status: str
    scope: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    plan_run_id: Optional[int] = None
    has_plan: bool = False
    totals: Optional[dict[str, int]] = None
    summary: Optional[dict[str, Any]] = None


class JobOut(BaseModel):
    """A running or recent background job."""

    id: str
    kind: str
    label: str
    status: Literal["running", "succeeded", "failed", "cancelled"]
    step: Optional[str] = None
    error: Optional[str] = None
    started_at: float
    finished_at: Optional[float] = None
    last_seq: int
    result: Optional[dict[str, Any]] = None


class JobEventOut(BaseModel):
    """One event of a job (also the SSE ``data`` payload)."""

    seq: int
    job_id: str
    kind: Literal[
        "started", "step", "progress", "log", "finished", "failed", "cancelled"
    ]
    message: str = ""
    step: Optional[str] = None
    current: Optional[int] = None
    total: Optional[int] = None
    level: Optional[str] = None
    time: float


class StatusOut(BaseModel):
    """Everything the dashboard shows."""

    version: str
    home: str
    checks: list[Check]
    counts: dict[str, int]
    last_sync: Optional[RunOut] = None
    last_apply: Optional[RunOut] = None
    current_job: Optional[JobOut] = None
    rekordbox_running: bool = False
    v1_import_available: bool = False


class PlaylistOut(BaseModel):
    """A Playlist row in the Playlists table."""

    id: int
    name: str
    sources: list[Source]
    gone: bool
    folder: list[str]
    rekordbox_name: str
    in_rekordbox: bool
    tracks_tidal: int
    tracks_bandcamp: int
    tracks_library: int
    tracks_with_file: int
    tracks_without_file: int
    tracks_missing: int
    tracks_in_rekordbox: int
    tracks_unsynced: int
    last_synced_at: Optional[datetime] = None


class TrackStickOut(BaseModel):
    """A USB stick whose copy of the Playlist holds a Track (as of its last scan)."""

    id: int
    name: str
    state: StickState


class TrackOut(BaseModel):
    """A Track inside a Playlist, with its presence per Source and target."""

    id: int
    title: str
    artist: str
    album: Optional[str] = None
    version: Optional[str] = None
    isrc: Optional[str] = None
    position: Optional[int] = None
    added_at: Optional[datetime] = None
    sources: list[Source]
    tidal_track: bool
    removed_from_tidal: Optional[datetime] = None
    download: TargetState
    rekordbox: TargetState
    sticks: list[TrackStickOut]
    file_path: Optional[str] = None
    download_status: str
    download_error: Optional[str] = None
    tidal_unavailable: bool


class PlaylistDetailOut(PlaylistOut):
    """A Playlist with its Tracks."""

    tracks: list[TrackOut]


class ImportedTrackOut(BaseModel):
    """An audio file added to a Playlist's Music folder sub-folder."""

    track_id: int
    file_path: str
    library_track: bool  # False: the file matched one of the Playlist's Tidal tracks


class SyncIn(BaseModel):
    """Start a sync."""

    playlist: Optional[str] = None
    download: bool = True
    offline: bool = False
    full: bool = False
    allow_shrink: bool = False


class ApplyIn(BaseModel):
    """Which Plan groups to apply."""

    groups: list[str] = Field(default_factory=list)


class PlanOut(BaseModel):
    """A stored Plan and whether it was applied already."""

    run_id: int
    plan: Plan
    applied_by_run: Optional[int] = None  # changed Rekordbox with this Plan
    superseded_by: Optional[int] = None  # a newer sync run


class SettingsOut(BaseModel):
    """Current settings plus derived information."""

    values: dict[str, Any]
    tag_mapping_in_use: str
    config_file: str


class TidalLoginOut(BaseModel):
    """State of the Tidal login."""

    logged_in: bool
    state: Literal["idle", "pending", "done", "failed"]
    url: Optional[str] = None
    user_code: Optional[str] = None
    expires_at: Optional[float] = None
    error: Optional[str] = None


class BackupOut(BaseModel):
    """A Backup."""

    id: str
    kind: Literal["full", "db"]
    label: str
    created_at: str
    rekordbox_dir: Optional[str] = None
    files: list[str]
    size_bytes: int


class CancelOut(BaseModel):
    """Result of a cancel request."""

    cancelled: bool


class PickPathIn(BaseModel):
    """Open the Finder dialog for one Settings path."""

    field: PickField
    start: Optional[str] = None  # current value; the dialog opens next to it


class PickPathOut(BaseModel):
    """The chosen path, or null when the dialog was cancelled."""

    path: Optional[str] = None


class StickOut(BaseModel):
    """A USB stick with a Rekordbox export, as of its last scan."""

    id: int
    name: str
    mounted: bool
    scanned_at: datetime
    tracks_total: int  # tracks in the export
    tracks_matched: int  # of these, the ones that match a Cratekeeper Track
    playlists_total: int  # playlists in the export (folders not counted)
    playlists_matched: int  # of these, the ones that match a Playlist


class StickScanOut(BaseModel):
    """Result of a stick scan."""

    scanned: list[int]  # IDs of the sticks read in this scan
    problems: list[str]  # mounted sticks that could not be read
    sticks: list[StickOut]  # every known stick
