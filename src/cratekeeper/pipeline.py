"""Sync = Refresh → Download → Plan. Apply and Restore are separate steps.

Each function runs inside a job (see ``jobs.py``) and records a run, so the
History screen can show what happened and the Plan can be applied later.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Optional

from .app import App
from .backups import BackupInfo, create_backup, restore_backup
from .bandcamp.refresh import refresh_bandcamp
from .db import repository as repo
from .db.models import RunKind, RunStatus
from .download.runner import run_downloads
from .download.tidal_dl import TidalDownloader
from .jobs import JobCancelled, JobContext
from .music.refresh import refresh_music_folder
from .rekordbox.applier import ApplyResult, apply_plan
from .rekordbox.connection import RekordboxLocation, planning_copy, require_closed
from .rekordbox.plan import Plan
from .rekordbox.planner import Planner
from .tidal.client import TidalClient
from .tidal.refresh import refresh_tidal

logger = logging.getLogger(__name__)


class PlanNotFoundError(LookupError):
    """Raised when a run has no Plan to apply."""


@dataclass(frozen=True)
class SyncOptions:
    """What a sync should do."""

    playlist: Optional[str] = None
    download: bool = True
    offline: bool = False  # skip Tidal refresh and Download
    full: bool = False  # fetch every Tidal playlist again
    allow_shrink: bool = False


@dataclass(frozen=True)
class SyncOutcome:
    """Result of a sync run."""

    run_id: int
    plan: Plan
    summary: dict[str, Any]


@dataclass(frozen=True)
class ApplyOutcome:
    """Result of an apply run."""

    run_id: int
    result: ApplyResult
    backup: BackupInfo


def sync(app: App, ctx: JobContext, options: SyncOptions) -> SyncOutcome:
    """Refresh the Sources, download missing tracks and build a Plan."""
    settings = app.settings
    with app.db.session() as session:
        run_id = repo.start_run(
            session, RunKind.SYNC, scope=options.playlist, options=asdict(options)
        ).id
    summary: dict[str, Any] = {}
    try:
        ctx.step("Backup")
        backup = create_backup(
            app.home,
            app.db,
            "before refresh",
            keep_full=settings.backups_keep_full,
            keep_db=settings.backups_keep_db,
        )
        summary["backup"] = backup.id
        if not options.offline:
            ctx.step("Refresh Tidal")
            tidal = refresh_tidal(
                app.db,
                TidalClient(app.auth.session()),
                ctx,
                options.playlist,
                full=options.full,
                allow_shrink=options.allow_shrink,
            )
            app.auth.persist()
            summary["tidal"] = asdict(tidal)
        ctx.step("Refresh Bandcamp")
        summary["bandcamp"] = asdict(
            refresh_bandcamp(app.db, settings.bandcamp_folder, ctx, options.playlist)
        )
        ctx.step("Refresh Music folder")
        summary["music"] = asdict(
            refresh_music_folder(app.db, settings.music_folder, ctx, options.playlist)
        )
        if options.download and not options.offline:
            ctx.step("Download")
            summary["download"] = asdict(_download(app, ctx, options.playlist))
        ctx.step("Plan")
        plan = build_plan(app, options.playlist)
        summary["plan"] = plan.totals()
    except JobCancelled:
        _finish(app, run_id, RunStatus.CANCELLED, summary)
        raise
    except Exception as exc:
        _finish(app, run_id, RunStatus.FAILED, summary, error=str(exc))
        raise
    _finish(app, run_id, RunStatus.SUCCEEDED, summary, plan=plan)
    return SyncOutcome(run_id=run_id, plan=plan, summary=summary)


def build_plan(app: App, playlist: Optional[str] = None) -> Plan:
    """Build a Plan from the current database and library (writes nothing)."""
    location = app.rekordbox()
    planner = Planner(
        app.db,
        app.rules(),
        app.settings.music_folder,
        app.settings.bandcamp_folder,
        app.settings.prune_tracks,
    )
    with planning_copy(location) as copy:
        return planner.build(copy, str(location.db_path), playlist)


def load_plan(app: App, run_id: int) -> Plan:
    """Return the Plan stored with a sync run."""
    with app.db.session() as session:
        run = repo.get_run(session, run_id)
        if run is None or run.plan is None:
            raise PlanNotFoundError(f"Run {run_id} has no plan")
        return Plan.model_validate(run.plan)


def default_groups(plan: Plan) -> set[str]:
    """Return the groups that are selected unless the user changes it."""
    return {g.key for g in plan.groups if g.selected_by_default and g.changes}


def apply(
    app: App, ctx: JobContext, plan_run_id: int, groups: Optional[set[str]] = None
) -> ApplyOutcome:
    """Back up, then apply the chosen groups of a stored Plan."""
    plan = load_plan(app, plan_run_id)
    selected = default_groups(plan) if groups is None else groups
    with app.db.session() as session:
        run_id = repo.start_run(
            session,
            RunKind.APPLY,
            scope=plan.scope,
            options={"groups": sorted(selected)},
            plan_run_id=plan_run_id,
        ).id
    summary: dict[str, Any] = {}
    try:
        require_closed()
        location = RekordboxLocation(db_path=app.rekordbox().db_path)
        ctx.step("Backup")
        backup = create_backup(
            app.home,
            app.db,
            "before apply",
            location,
            keep_full=app.settings.backups_keep_full,
            keep_db=app.settings.backups_keep_db,
        )
        summary["backup"] = backup.id
        ctx.step("Apply")
        result = apply_plan(app.db, location, plan, selected, ctx)
        summary["groups"] = [asdict(g) for g in result.groups]
        summary["applied"], summary["failed"] = result.applied, result.failed
    except JobCancelled:
        _finish(app, run_id, RunStatus.CANCELLED, summary)
        raise
    except Exception as exc:
        _finish(app, run_id, RunStatus.FAILED, summary, error=str(exc))
        raise
    status = RunStatus.SUCCEEDED if result.failed == 0 else RunStatus.FAILED
    error = f"{result.failed} groups failed" if result.failed else None
    _finish(app, run_id, status, summary, error=error)
    return ApplyOutcome(run_id=run_id, result=result, backup=backup)


def restore(app: App, ctx: JobContext, backup_id: str) -> BackupInfo:
    """Restore a Backup (a Backup of the current state is taken first)."""
    ctx.step("Restore")
    info = restore_backup(
        app.home,
        app.db,
        backup_id,
        keep_full=app.settings.backups_keep_full,
        keep_db=app.settings.backups_keep_db,
    )
    with app.db.session() as session:
        # A Backup taken during a sync holds that sync as "running".
        repo.mark_interrupted_runs(
            session, "Not finished when the restored Backup was taken"
        )
        run = repo.start_run(session, RunKind.RESTORE, scope=backup_id)
        repo.finish_run(
            session, run.id, RunStatus.SUCCEEDED, summary={"backup": backup_id}
        )
    return info


def _download(app: App, ctx: JobContext, playlist: Optional[str]) -> Any:
    settings = app.settings

    def make_downloader() -> TidalDownloader:
        return TidalDownloader(
            app.home.tidal_dl_dir,
            app.auth.session(),
            settings.download_quality,
            ctx.abort_event,
        )

    stats = run_downloads(
        app.db,
        settings.music_folder,
        settings.target_format,
        settings.ffmpeg_quality,
        make_downloader,
        ctx,
        playlist,
    )
    app.auth.persist()
    return stats


def _finish(
    app: App,
    run_id: int,
    status: RunStatus,
    summary: dict[str, Any],
    *,
    plan: Optional[Plan] = None,
    error: Optional[str] = None,
) -> None:
    with app.db.session() as session:
        repo.finish_run(
            session,
            run_id,
            status,
            summary=summary,
            plan=plan.model_dump(mode="json") if plan is not None else None,
            error=error,
        )
