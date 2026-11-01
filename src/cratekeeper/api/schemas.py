"""Request and response models of the web API (the contract for the UI)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from ..rekordbox.plan import Plan

Source = Literal["tidal", "bandcamp", "local"]


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
    tracks_local: int
    tracks_with_file: int
    tracks_without_file: int
    tracks_in_rekordbox: int
    last_synced_at: Optional[datetime] = None


class TrackOut(BaseModel):
    """A Track inside a Playlist, with its presence per Source and Rekordbox."""

    id: int
    title: str
    artist: str
    album: Optional[str] = None
    version: Optional[str] = None
    isrc: Optional[str] = None
    position: Optional[int] = None
    added_at: Optional[datetime] = None
    in_tidal: bool
    in_bandcamp: bool
    in_local: bool
    in_rekordbox: bool
    removed_from_tidal: Optional[datetime] = None
    file_path: Optional[str] = None
    has_file: bool
    download_status: str
    download_error: Optional[str] = None
    tidal_unavailable: bool


class PlaylistDetailOut(PlaylistOut):
    """A Playlist with its Tracks."""

    tracks: list[TrackOut]


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
