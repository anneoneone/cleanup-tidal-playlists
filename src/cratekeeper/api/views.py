"""Turn database rows and core objects into API models."""

from __future__ import annotations

import shutil
from collections import defaultdict
from dataclasses import asdict
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import __version__
from ..app import App
from ..backups import BackupInfo
from ..db import repository as repo
from ..db.models import Playlist, PlaylistTrack, Run, RunKind, Track
from ..download.tidal_dl import downloader_available
from ..jobs import Job
from ..migrate import v1_db_path
from ..music.paths import first_existing_file
from ..rekordbox.connection import RekordboxError, rekordbox_running
from ..rekordbox.naming import NameRules, added_date
from ..rekordbox.planner import is_vanished
from .schemas import (
    BackupOut,
    Check,
    JobOut,
    PlaylistDetailOut,
    PlaylistOut,
    RunOut,
    Source,
    StatusOut,
    TrackOut,
)


def run_out(run: Run) -> RunOut:
    """Convert a run (plan is not included; see ``/api/plans``)."""
    totals: Optional[dict[str, int]] = None
    if run.plan is not None:
        totals = {}
        for group in run.plan.get("groups", []):
            for change in group.get("changes", []):
                totals[change["kind"]] = totals.get(change["kind"], 0) + 1
    return RunOut(
        id=run.id,
        kind=run.kind,
        status=run.status,
        scope=run.scope,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        plan_run_id=run.plan_run_id,
        has_plan=run.plan is not None,
        totals=totals,
        summary=run.summary,
    )


def job_out(job: Job) -> JobOut:
    """Convert a job, with a small summary of its result."""
    snapshot = job.snapshot()
    return JobOut(**snapshot, result=job_result(job.result))


def job_result(result: Any) -> Optional[dict[str, Any]]:
    """Summarize what a job returned (sync, apply or restore)."""
    if result is None:
        return None
    if isinstance(result, BackupInfo):
        return {"backup": result.id}
    data: dict[str, Any] = {"run_id": getattr(result, "run_id", None)}
    apply_result = getattr(result, "result", None)
    if apply_result is not None:
        data["applied"] = apply_result.applied
        data["failed"] = apply_result.failed
        data["backup"] = result.backup.id
    plan = getattr(result, "plan", None)
    if plan is not None:
        data["empty"] = plan.is_empty
    return data


def backup_out(info: BackupInfo) -> BackupOut:
    """Convert a Backup."""
    return BackupOut(**asdict(info))


def status_out(app: App) -> StatusOut:
    """Build the dashboard status."""
    settings = app.settings
    checks = [
        Check(
            key="music_folder",
            label="Music folder",
            ok=settings.music_folder.is_dir(),
            detail=str(settings.music_folder),
        )
    ]
    if settings.bandcamp_folder is not None:
        checks.append(
            Check(
                key="bandcamp_folder",
                label="Bandcamp folder",
                ok=settings.bandcamp_folder.is_dir(),
                detail=str(settings.bandcamp_folder),
            )
        )
    try:
        checks.append(
            Check(
                key="rekordbox_library",
                label="Rekordbox library",
                ok=True,
                detail=str(app.rekordbox().db_path),
            )
        )
    except RekordboxError as exc:
        checks.append(
            Check(
                key="rekordbox_library",
                label="Rekordbox library",
                ok=False,
                detail=str(exc),
            )
        )
    running = rekordbox_running()
    checks += [
        Check(
            key="rekordbox_app",
            label="Rekordbox app",
            ok=None,
            detail="running (close it before Apply)" if running else "closed",
        ),
        Check(
            key="tidal_login",
            label="Tidal login",
            ok=app.auth.has_stored_login(),
            detail="stored" if app.auth.has_stored_login() else "not logged in",
        ),
        Check(
            key="downloader",
            label="Downloader",
            ok=downloader_available(),
            detail=(
                "tidal-dl-ng installed"
                if downloader_available()
                else "tidal-dl-ng not installed"
            ),
        ),
        Check(
            key="ffmpeg",
            label="ffmpeg",
            ok=shutil.which("ffmpeg") is not None,
            detail=shutil.which("ffmpeg") or "not found",
        ),
    ]
    with app.db.session() as session:
        counts = repo.library_counts(session)
        last_sync = repo.latest_run(session, RunKind.SYNC)
        last_apply = repo.latest_run(session, RunKind.APPLY)
        result = StatusOut(
            version=__version__,
            home=str(app.home.root),
            checks=checks,
            counts=counts,
            last_sync=run_out(last_sync) if last_sync else None,
            last_apply=run_out(last_apply) if last_apply else None,
            rekordbox_running=running,
            v1_import_available=counts["playlists"] == 0 and v1_db_path().is_file(),
        )
    job = app.runner.current()
    if job is not None:
        result.current_job = job_out(job)
    return result


def _load_rows(
    session: Session, playlist_ids: Optional[list[int]] = None
) -> dict[int, list[tuple[PlaylistTrack, Track]]]:
    stmt = select(PlaylistTrack, Track).join(Track, Track.id == PlaylistTrack.track_id)
    if playlist_ids is not None:
        stmt = stmt.where(PlaylistTrack.playlist_id.in_(playlist_ids))
    rows: dict[int, list[tuple[PlaylistTrack, Track]]] = defaultdict(list)
    for row, track in session.execute(stmt):
        rows[row.playlist_id].append((row, track))
    return rows


def playlist_out(
    playlist: Playlist, rows: list[tuple[PlaylistTrack, Track]], rules: NameRules
) -> PlaylistOut:
    """Convert a Playlist with counts (file presence = stored path, fast)."""
    sources: list[Source] = []
    if playlist.in_tidal:
        sources.append("tidal")
    if any(r.in_bandcamp for r, _ in rows):
        sources.append("bandcamp")
    if any(r.in_local for r, _ in rows):
        sources.append("local")
    tidal_rows = [(r, t) for r, t in rows if r.in_tidal]
    tags = rules.parse(playlist.name)
    return PlaylistOut(
        id=playlist.id,
        name=playlist.name,
        sources=sources,
        gone=is_vanished(playlist, [r for r, _ in rows]),
        folder=rules.folder_path(tags),
        rekordbox_name=rules.rekordbox_name(tags),
        in_rekordbox=playlist.rekordbox_playlist_id is not None,
        tracks_tidal=len(tidal_rows),
        tracks_bandcamp=sum(1 for r, _ in rows if r.in_bandcamp),
        tracks_local=sum(1 for r, _ in rows if r.in_local),
        tracks_with_file=sum(
            1
            for r, t in rows
            if (r.in_tidal or r.in_bandcamp or r.in_local) and t.file_paths
        ),
        tracks_without_file=sum(1 for _, t in tidal_rows if not t.file_paths),
        tracks_in_rekordbox=sum(1 for r, _ in rows if r.in_rekordbox),
        last_synced_at=playlist.last_synced_at,
    )


def playlists_out(app: App) -> list[PlaylistOut]:
    """Return all Playlists with counts."""
    rules = app.rules()
    with app.db.session() as session:
        rows = _load_rows(session)
        return [
            playlist_out(p, rows.get(p.id, []), rules)
            for p in repo.all_playlists(session)
        ]


def playlist_detail_out(app: App, playlist_id: int) -> Optional[PlaylistDetailOut]:
    """Return one Playlist with its Tracks (file presence checked on disk)."""
    rules = app.rules()
    music = app.settings.music_folder
    with app.db.session() as session:
        playlist = session.get(Playlist, playlist_id)
        if playlist is None:
            return None
        rows = _load_rows(session, [playlist_id]).get(playlist_id, [])
        base = playlist_out(playlist, rows, rules)
        tracks = []
        for row, track in rows:
            path = first_existing_file(track.file_paths, music)
            tracks.append(
                TrackOut(
                    id=track.id,
                    title=track.title,
                    artist=track.artist,
                    album=track.album,
                    version=track.version,
                    isrc=track.isrc,
                    position=row.position,
                    added_at=added_date(
                        row.added_to_tidal, row.added_to_local, track.created_at
                    ),
                    in_tidal=row.in_tidal,
                    in_bandcamp=row.in_bandcamp,
                    in_local=row.in_local,
                    in_rekordbox=row.in_rekordbox,
                    removed_from_tidal=row.removed_from_tidal,
                    file_path=str(path) if path else None,
                    has_file=path is not None,
                    download_status=track.download_status,
                    download_error=track.download_error,
                    tidal_unavailable=track.tidal_unavailable,
                )
            )
        tracks.sort(key=lambda t: (t.added_at is None, t.added_at, t.id))
        return PlaylistDetailOut(**base.model_dump(), tracks=tracks)
