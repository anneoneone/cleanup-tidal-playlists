"""Queries and small write helpers shared by the pipeline steps.

Every function takes the caller's session, so a step decides its own unit of work.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import func, select, text
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


def plan_apply_run(session: Session, plan_run_id: int) -> Optional[int]:
    """Return the newest apply run that changed Rekordbox with this Plan."""
    runs = session.scalars(
        select(Run)
        .where(Run.kind == RunKind.APPLY.value, Run.plan_run_id == plan_run_id)
        .order_by(Run.id.desc())
    ).all()
    for run in runs:
        if run.status == RunStatus.SUCCEEDED.value or (run.summary or {}).get(
            "applied", 0
        ):
            return run.id
    return None


def newer_sync_run(session: Session, run_id: int) -> Optional[int]:
    """Return the newest sync run started after ``run_id``."""
    stmt = (
        select(Run.id)
        .where(Run.kind == RunKind.SYNC.value, Run.id > run_id)
        .order_by(Run.id.desc())
    )
    return session.scalars(stmt).first()


def mark_interrupted_runs(
    session: Session,
    reason: str = "Interrupted: the process stopped during the run",
) -> int:
    """Mark runs left "running" as failed.

    Only call this while holding the job lock, so no live run is hit.
    """
    runs = session.scalars(
        select(Run).where(Run.status == RunStatus.RUNNING.value)
    ).all()
    for run in runs:
        run.status = RunStatus.FAILED.value
        run.finished_at = utc_now()
        run.error = run.error or reason
    return len(runs)


# ---------------------------------------------------------------- playlists/tracks


def normalized_track_name(title: str, artist: str) -> str:
    """Return the v1 matching key: artist without "feat.", title without brackets."""
    artist_part = re.sub(
        r"\s*(feat\.?|featuring|ft\.?)\s+.*", "", artist, flags=re.IGNORECASE
    )
    title_part = re.sub(r"\s*\([^)]*\)\s*", "", title)
    title_part = re.sub(r"\s*\[[^\]]*\]\s*", "", title_part)
    return f"{artist_part.lower().strip()} - {title_part.lower().strip()}"


def name_key(value: str) -> str:
    """Return the key used to compare playlist names (NFC, case-folded)."""
    return unicodedata.normalize("NFC", value).casefold().strip()


def all_playlists(session: Session) -> Sequence[Playlist]:
    """Return all playlists ordered by name."""
    return session.scalars(select(Playlist).order_by(Playlist.name)).all()


def playlist_by_tidal_id(session: Session, tidal_id: str) -> Optional[Playlist]:
    """Return the playlist with this Tidal ID."""
    return session.scalars(
        select(Playlist).where(Playlist.tidal_id == tidal_id)
    ).first()


def playlist_by_name(
    session: Session, name: str, *, without_tidal_id: bool = False
) -> Optional[Playlist]:
    """Find a playlist by name, ignoring Unicode form and case."""
    key = name_key(name)
    stmt = select(Playlist).order_by(Playlist.id)
    if without_tidal_id:
        stmt = stmt.where(Playlist.tidal_id.is_(None))
    for playlist in session.scalars(stmt):
        if name_key(playlist.name) == key:
            return playlist
    return None


def track_by_tidal_id(session: Session, tidal_id: str) -> Optional[Track]:
    """Return the track with this Tidal ID."""
    return session.scalars(select(Track).where(Track.tidal_id == tidal_id)).first()


def track_by_stored_path(session: Session, stored_path: str) -> Optional[Track]:
    """Return the track that has ``stored_path`` in its file paths."""
    track_id = session.execute(
        text(
            "SELECT tracks.id FROM tracks, json_each(tracks.file_paths) AS f "
            "WHERE f.value = :path LIMIT 1"
        ),
        {"path": stored_path},
    ).scalar_one_or_none()
    return session.get(Track, track_id) if track_id is not None else None


def playlist_rows(session: Session, playlist_id: int) -> dict[int, PlaylistTrack]:
    """Return the playlist's rows keyed by track ID."""
    rows = session.scalars(
        select(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist_id)
    ).all()
    return {row.track_id: row for row in rows}


def ensure_row(
    session: Session,
    rows: dict[int, PlaylistTrack],
    playlist: Playlist,
    track: Track,
) -> PlaylistTrack:
    """Return the playlist's row for ``track``, creating it if needed."""
    row = rows.get(track.id)
    if row is None:
        row = PlaylistTrack(
            playlist_id=playlist.id,
            track_id=track.id,
            in_tidal=False,
            in_local=False,
            in_bandcamp=False,
            in_rekordbox=False,
        )
        session.add(row)
        rows[track.id] = row
    return row


def add_file_path(track: Track, stored_path: str) -> bool:
    """Add ``stored_path`` to the track's file paths.

    Returns True if it was new.
    """
    paths = list(track.file_paths or [])
    if stored_path in paths:
        return False
    track.file_paths = [*paths, stored_path]
    return True


def remove_file_path(track: Track, stored_path: str) -> bool:
    """Remove ``stored_path`` from the track's file paths.

    Returns True if removed.
    """
    paths = list(track.file_paths or [])
    if stored_path not in paths:
        return False
    track.file_paths = [p for p in paths if p != stored_path]
    return True


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
