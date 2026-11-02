"""The local web server: JSON API under ``/api`` plus the built web UI."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from collections.abc import AsyncIterator, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from importlib import resources
from pathlib import Path
from typing import Annotated, Any, BinaryIO, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import ValidationError

from ..app import App
from ..backups import BackupError, get_backup, list_backups
from ..db import repository as repo
from ..jobs import TERMINAL_EVENTS, JobBusyError, JobEvent, held_lock
from ..music.library_import import (
    FileNameError,
    ImportedTrack,
    import_library_track,
    import_target,
)
from ..music.paths import FolderMissingError
from ..pipeline import (
    PlanClosedError,
    SyncOptions,
    apply,
    check_plan_open,
    load_plan,
    restore,
    sync,
)
from ..settings import Settings
from ..sticks import scan
from .picker import InvalidPickError, PickerBusyError, PickerError, pick_path
from .schemas import (
    ApplyIn,
    BackupOut,
    CancelOut,
    ImportedTrackOut,
    JobOut,
    PickPathIn,
    PickPathOut,
    PlanOut,
    PlaylistDetailOut,
    PlaylistOut,
    RunOut,
    SettingsOut,
    StatusOut,
    StickOut,
    StickScanOut,
    SyncIn,
    TidalLoginOut,
)
from .security import LocalOnlyGuard
from .views import (
    backup_out,
    job_out,
    playlist_detail_out,
    playlists_out,
    run_out,
    status_out,
    sticks_out,
)

logger = logging.getLogger(__name__)

KEEPALIVE_SECONDS = 15.0
_NO_UI = """<!doctype html><title>Cratekeeper</title>
<body style="font-family:system-ui;margin:3rem;max-width:40rem">
<h1>Cratekeeper</h1><p>The web UI is not built yet. Run <code>make ui</code> in the
repository, then start <code>cratekeeper ui</code> again. The API is running at
<a href="/api/docs">/api/docs</a>.</p></body>"""


def web_dist() -> Path:
    """Return the folder with the built web UI."""
    return Path(str(resources.files("cratekeeper") / "web" / "dist"))


def create_app(
    core: App,
    port: int,
    extra_origins: Iterable[str] = (),
    extra_hosts: Iterable[str] = (),
) -> FastAPI:
    """Build the FastAPI app around one :class:`App`."""
    api = FastAPI(
        title="Cratekeeper",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    api.middleware("http")(LocalOnlyGuard(port, extra_origins, extra_hosts))
    api.state.core = core
    api.include_router(_router(), prefix="/api")
    _mount_ui(api)
    return api


def _core(request: Request) -> App:
    core: App = request.app.state.core
    return core


Core = Annotated[App, Depends(_core)]


def _start(core: App, kind: str, label: str, fn: Any) -> JobOut:
    try:
        job = core.runner.start(kind, fn, label=label)
    except JobBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return job_out(job)


def _router() -> APIRouter:  # noqa: C901 - one place lists every route
    router = APIRouter()

    @router.get("/status", response_model=StatusOut)
    def get_status(core: Core) -> StatusOut:
        return status_out(core)

    @router.get("/playlists", response_model=list[PlaylistOut])
    def get_playlists(core: Core) -> list[PlaylistOut]:
        return playlists_out(core)

    @router.get("/playlists/{playlist_id}", response_model=PlaylistDetailOut)
    def get_playlist(core: Core, playlist_id: int) -> PlaylistDetailOut:
        detail = playlist_detail_out(core, playlist_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Playlist not found")
        return detail

    @router.post(
        "/playlists/{playlist_id}/files",
        response_model=ImportedTrackOut,
        status_code=201,
        openapi_extra=_FILE_BODY,
    )
    async def post_playlist_file(
        core: Core, playlist_id: int, name: str, request: Request
    ) -> ImportedTrackOut:
        """Copy the audio file in the body into the Playlist's Music folder sub-folder.

        ``name`` is the file name. The file becomes a Library track (or the file of
        one of the Playlist's Tidal tracks, if it matches one).
        """
        music_folder = core.settings.music_folder
        with _import_errors():  # fail before the upload if we can
            await run_in_threadpool(
                import_target, core.db, music_folder, playlist_id, name
            )
            _check_no_job(core)
        with tempfile.TemporaryFile() as upload:
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                await run_in_threadpool(upload.write, chunk)
            if size == 0:
                raise HTTPException(status_code=422, detail="The file is empty")
            upload.seek(0)
            with _import_errors():
                imported = await run_in_threadpool(
                    _import_file, core, playlist_id, name, upload
                )
        return ImportedTrackOut(**asdict(imported))

    @router.post("/sync", response_model=JobOut, status_code=202)
    def post_sync(core: Core, body: SyncIn) -> JobOut:
        options = SyncOptions(**body.model_dump())
        label = f"Sync {body.playlist}" if body.playlist else "Sync"
        return _start(core, "sync", label, lambda ctx: sync(core, ctx, options))

    @router.get("/jobs/current", response_model=Optional[JobOut])
    def get_current_job(core: Core) -> Optional[JobOut]:
        job = core.runner.current()
        return job_out(job) if job is not None else None

    @router.get("/jobs/{job_id}", response_model=JobOut)
    def get_job(core: Core, job_id: str) -> JobOut:
        job = core.runner.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job_out(job)

    @router.get("/jobs/{job_id}/events")
    async def job_events(
        core: Core, job_id: str, request: Request, after: int = 0
    ) -> StreamingResponse:
        job = core.runner.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return StreamingResponse(
            _event_stream(job, request, after),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/jobs/{job_id}/cancel", response_model=CancelOut)
    def cancel_job(core: Core, job_id: str) -> CancelOut:
        return CancelOut(cancelled=core.runner.cancel(job_id))

    @router.get("/runs", response_model=list[RunOut])
    def get_runs(core: Core, limit: int = 50, offset: int = 0) -> list[RunOut]:
        with core.db.session() as session:
            runs = repo.list_runs(session, limit=min(limit, 200), offset=offset)
            return [run_out(r) for r in runs]

    @router.get("/runs/{run_id}", response_model=RunOut)
    def get_run(core: Core, run_id: int) -> RunOut:
        with core.db.session() as session:
            run = repo.get_run(session, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="Run not found")
            return run_out(run)

    @router.get("/plans/{run_id}", response_model=PlanOut)
    def get_plan(core: Core, run_id: int) -> PlanOut:
        try:
            plan = load_plan(core, run_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        with core.db.session() as session:
            return PlanOut(
                run_id=run_id,
                plan=plan,
                applied_by_run=repo.plan_apply_run(session, run_id),
                superseded_by=repo.newer_sync_run(session, run_id),
            )

    @router.post("/plans/{run_id}/apply", response_model=JobOut, status_code=202)
    def post_apply(core: Core, run_id: int, body: ApplyIn) -> JobOut:
        try:
            plan = load_plan(core, run_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        unknown = set(body.groups) - {g.key for g in plan.groups}
        if unknown:
            raise HTTPException(
                status_code=422, detail=f"Unknown groups: {sorted(unknown)}"
            )
        if not body.groups:
            raise HTTPException(status_code=422, detail="No groups selected")
        try:
            check_plan_open(core, run_id)
        except PlanClosedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        groups = set(body.groups)
        return _start(
            core, "apply", "Apply", lambda ctx: apply(core, ctx, run_id, groups)
        )

    @router.get("/settings", response_model=SettingsOut)
    def get_settings(core: Core) -> SettingsOut:
        return _settings_out(core)

    @router.put("/settings", response_model=SettingsOut)
    def put_settings(core: Core, values: dict[str, Any]) -> SettingsOut:
        try:
            settings = Settings.model_validate(
                {k: v for k, v in values.items() if v not in (None, "")}
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        settings.save(core.home)
        core.reload_settings()
        return _settings_out(core)

    @router.post("/settings/pick-path", response_model=PickPathOut)
    def post_pick_path(body: PickPathIn) -> PickPathOut:
        try:
            path = pick_path(body.field, body.start)
        except PickerBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PickerError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except InvalidPickError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if path is None:
            return PickPathOut(path=None)
        try:
            Settings.model_validate({body.field: str(path)})
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        return PickPathOut(path=str(path))

    @router.get("/settings/tag-mapping")
    def get_tag_mapping(core: Core) -> dict[str, Any]:
        path = core.settings.tag_mapping_path(core.home)
        mapping: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return mapping

    @router.put("/settings/tag-mapping")
    def put_tag_mapping(core: Core, mapping: dict[str, Any]) -> dict[str, Any]:
        groups = mapping.get("emoji_to_mytag_mapping")
        folders = mapping.get("folder_structure")
        if not isinstance(groups, dict) or not isinstance(folders, dict):
            raise HTTPException(
                status_code=422,
                detail="Mapping needs 'emoji_to_mytag_mapping' and 'folder_structure'",
            )
        target = core.settings.tag_mapping or core.home.tag_mapping_file
        target.write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + "\n")
        return mapping

    @router.get("/auth/tidal", response_model=TidalLoginOut)
    def get_tidal_login(core: Core) -> TidalLoginOut:
        state, error = core.auth.login_state()
        start = core.auth.pending_login()
        return TidalLoginOut(
            logged_in=core.auth.has_stored_login(),
            state=state,
            error=error,
            url=start.url if start else None,
            user_code=start.user_code if start else None,
            expires_at=start.expires_at if start else None,
        )

    @router.post("/auth/tidal", response_model=TidalLoginOut)
    def start_tidal_login(core: Core) -> TidalLoginOut:
        start = core.auth.start_login()
        return TidalLoginOut(
            logged_in=core.auth.has_stored_login(),
            state="pending",
            url=start.url,
            user_code=start.user_code,
            expires_at=start.expires_at,
        )

    @router.get("/backups", response_model=list[BackupOut])
    def get_backups(core: Core) -> list[BackupOut]:
        return [backup_out(b) for b in list_backups(core.home)]

    @router.post("/backups/{backup_id}/restore", response_model=JobOut, status_code=202)
    def post_restore(core: Core, backup_id: str) -> JobOut:
        try:
            get_backup(core.home, backup_id)
        except BackupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _start(
            core, "restore", "Restore", lambda ctx: restore(core, ctx, backup_id)
        )

    @router.get("/sticks", response_model=list[StickOut])
    def get_sticks(core: Core) -> list[StickOut]:
        return sticks_out(core)

    @router.post("/sticks/scan", response_model=StickScanOut)
    def post_stick_scan(core: Core) -> StickScanOut:
        try:
            result = _scan_sticks(core)
        except JobBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return StickScanOut(
            scanned=result.scanned, problems=result.problems, sticks=sticks_out(core)
        )

    return router


_FILE_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/octet-stream": {
                "schema": {"type": "string", "format": "binary"}
            }
        },
    }
}


@contextmanager
def _import_errors() -> Iterator[None]:
    """Turn errors of a file import into HTTP errors."""
    try:
        yield
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNameError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (FileExistsError, FolderMissingError, JobBusyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _check_no_job(core: App) -> None:
    job = core.runner.current()
    if job is not None and not job.done:
        raise JobBusyError(f"A job is already running: {job.label or job.kind}")


def _import_file(
    core: App, playlist_id: int, name: str, data: BinaryIO
) -> ImportedTrack:
    # The job lock keeps syncs (here or in the CLI) out while the folder changes.
    with held_lock(core.home.lock_file):
        return import_library_track(
            core.db, core.settings.music_folder, playlist_id, name, data
        )


def _scan_sticks(core: App) -> scan.ScanResult:
    # The job lock keeps syncs (here or in the CLI) out while stick data changes.
    with held_lock(core.home.lock_file):
        return scan.scan_sticks(core.db, core.settings.music_folder)


def _settings_out(core: App) -> SettingsOut:
    values = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in core.settings.model_dump().items()
    }
    return SettingsOut(
        values=values,
        tag_mapping_in_use=str(core.settings.tag_mapping_path(core.home)),
        config_file=str(core.home.config_file),
    )


async def _event_stream(job: Any, request: Request, after: int) -> AsyncIterator[str]:
    """Send job events as SSE; ends after the job's last event."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[JobEvent] = asyncio.Queue()

    def push(event: JobEvent) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    backlog, unsubscribe = job.subscribe(push, after_seq=after)
    try:
        for event in backlog:
            yield _sse(event)
            if event.kind in TERMINAL_EVENTS:
                return
        while True:
            if await request.is_disconnected():
                return
            try:
                event = await asyncio.wait_for(queue.get(), KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield _sse(event)
            if event.kind in TERMINAL_EVENTS:
                return
    finally:
        unsubscribe()


def _sse(event: JobEvent) -> str:
    return (
        f"id: {event.seq}\nevent: {event.kind}\ndata: {json.dumps(event.to_dict())}\n\n"
    )


def _mount_ui(api: FastAPI) -> None:
    dist = web_dist()

    @api.get("/{path:path}", include_in_schema=False, response_model=None)
    def ui(path: str) -> FileResponse | HTMLResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        index = dist / "index.html"
        if not index.is_file():
            return HTMLResponse(_NO_UI)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)
