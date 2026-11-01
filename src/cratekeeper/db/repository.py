"""Queries and small write helpers shared by the pipeline steps.

Every function takes the caller's session, so a step decides its own unit of work.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Playlist, PlaylistTrack, Run, RunKind, RunStatus, Track


def utc_now() -> datetime:
    """Return the current time as naive UTC (how SQLite stores datetimes)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- runs


def start_run(
    session: Session,
    kind: RunKind,
    *,
    scope: Optional[str] = None,
    options: Optional[dict[str, Any]] = None,
    plan_run_id: Optional[int] = None,
) -> Run:
    """Insert a running run and return it with its ID."""
    run = Run(
        kind=kind.value,
        status=RunStatus.RUNNING.value,
        scope=scope,
        options=options,
        plan_run_id=plan_run_id,
        started_at=utc_now(),
    )
    session.add(run)
    session.flush()
    return run


def finish_run(
    session: Session,
    run_id: int,
    status: RunStatus,
    *,
    summary: Optional[dict[str, Any]] = None,
    plan: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Run:
    """Store the outcome of a run."""
    run = session.get(Run, run_id)
    if run is None:
        raise LookupError(f"Run {run_id} does not exist")
    run.status = status.value
    run.finished_at = utc_now()
    if summary is not None:
        run.summary = summary
    if plan is not None:
        run.plan = plan
    if error is not None:
        run.error = error
    return run


def get_run(session: Session, run_id: int) -> Optional[Run]:
    """Return one run."""
    return session.get(Run, run_id)


def list_runs(session: Session, *, limit: int = 50, offset: int = 0) -> Sequence[Run]:
    """Return runs, newest first."""
    stmt = select(Run).order_by(Run.id.desc()).limit(limit).offset(offset)
    return session.scalars(stmt).all()


def latest_run(session: Session, kind: Optional[RunKind] = None) -> Optional[Run]:
    """Return the newest run, optionally of one kind."""
    stmt = select(Run).order_by(Run.id.desc()).limit(1)
    if kind is not None:
        stmt = stmt.where(Run.kind == kind.value)
    return session.scalars(stmt).first()


def mark_interrupted_runs(session: Session) -> int:
    """Mark runs left "running" by a crashed process as failed."""
    runs = session.scalars(
        select(Run).where(Run.status == RunStatus.RUNNING.value)
    ).all()
    for run in runs:
        run.status = RunStatus.FAILED.value
        run.finished_at = utc_now()
        run.error = run.error or "Interrupted: the process stopped during the run"
    return len(runs)


# ------------------------------------------------------------------------- counts


def library_counts(session: Session) -> dict[str, int]:
    """Return headline counts for the dashboard."""

    def count(stmt: Any) -> int:
        return int(session.scalar(stmt) or 0)

    return {
        "playlists": count(select(func.count(Playlist.id))),
        "tracks": count(select(func.count(Track.id))),
        "tidal_tracks": count(
            select(func.count(Track.id)).where(Track.tidal_id.is_not(None))
        ),
        "tracks_in_rekordbox": count(
            select(func.count(func.distinct(PlaylistTrack.track_id))).where(
                PlaylistTrack.in_rekordbox.is_(True)
            )
        ),
    }
