"""The ``cratekeeper`` command."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Optional

import click
from rich.table import Table

from .. import __version__
from ..app import App
from ..backups import list_backups
from ..db import repository as repo
from ..download.tidal_dl import downloader_available
from ..jobs import JobBusyError, JobContext, JobStatus
from ..log import setup_logging
from ..migrate import MigrateError, migrate, v1_db_path
from ..pipeline import SyncOptions, apply, default_groups, restore, sync
from ..rekordbox.connection import RekordboxError, rekordbox_running
from ..rekordbox.plan import DELETE_GROUP
from ..settings import SettingsError
from .render import JobReporter, console, print_plan


def _open_app(level: str, console_logs: bool) -> App:
    try:
        app = App.open()
    except SettingsError as exc:
        raise click.ClickException(str(exc)) from exc
    setup_logging(level, app.home.logs_dir / "cratekeeper.log", console=console_logs)
    return app


def _run_job(app: App, kind: str, label: str, fn: Any) -> Any:
    try:
        job = app.runner.run(kind, fn, label=label, subscriber=JobReporter())
    except JobBusyError as exc:
        raise click.ClickException(str(exc)) from exc
    if job.status is JobStatus.FAILED:
        raise click.ClickException(job.error or "Failed")
    if job.status is JobStatus.CANCELLED:
        raise click.Abort()
    return job.result


@click.group()
@click.version_option(__version__, prog_name="cratekeeper")
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="How much to log.",
)
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    """Keep your Rekordbox library in line with Tidal and Bandcamp playlists."""
    ctx.obj = {"log_level": log_level}


@cli.command("sync")
@click.option("-p", "--playlist", help="Only this playlist (by name).")
@click.option("--plan-only", is_flag=True, help="Stop after showing the plan.")
@click.option("--yes", "-y", is_flag=True, help="Apply without asking.")
@click.option("--no-download", is_flag=True, help="Do not download missing tracks.")
@click.option("--offline", is_flag=True, help="Skip Tidal refresh and downloads.")
@click.option(
    "--delete-playlists",
    is_flag=True,
    help="Also delete Rekordbox playlists that no Source has any more.",
)
@click.option("--full", is_flag=True, help="Fetch every Tidal playlist again.")
@click.option(
    "--allow-shrink",
    is_flag=True,
    help="Accept that Tidal lists far fewer playlists than before.",
)
@click.pass_obj
def sync_command(
    obj: dict[str, Any],
    playlist: Optional[str],
    plan_only: bool,
    yes: bool,
    no_download: bool,
    offline: bool,
    delete_playlists: bool,
    full: bool,
    allow_shrink: bool,
) -> None:
    """Refresh, download, plan, then apply after you confirm."""
    app = _open_app(obj["log_level"], console_logs=False)
    options = SyncOptions(
        playlist=playlist,
        download=not no_download,
        offline=offline,
        full=full,
        allow_shrink=allow_shrink,
    )
    outcome = _run_job(app, "sync", "Sync", lambda ctx: sync(app, ctx, options))
    plan = outcome.plan
    console.rule("Plan")
    print_plan(plan, include_deletions=delete_playlists)
    groups = default_groups(plan)
    if delete_playlists and plan.group(DELETE_GROUP) is not None:
        groups.add(DELETE_GROUP)
    if plan_only or not groups:
        return
    if not yes and not click.confirm(f"Apply {len(groups)} groups to Rekordbox?"):
        console.print("Nothing applied. The plan is saved in the history.")
        return

    def run_apply(ctx: JobContext) -> Any:
        return apply(app, ctx, outcome.run_id, groups)

    result = _run_job(app, "apply", "Apply", run_apply)
    for group in result.result.groups:
        style = "green" if group.status == "applied" else "red"
        detail = f" – {group.error}" if group.error else ""
        console.print(f"[{style}]{group.status}[/{style}] {group.title}{detail}")
        if group.warning:
            console.print(f"  [yellow]{group.warning}[/yellow]")
    console.print(f"Backup: {result.backup.id}")
    if result.result.failed:
        raise click.ClickException(f"{result.result.failed} groups failed")


@cli.command("ui")
@click.option("--port", type=int, help="Port (default: setting 'port', 8765).")
@click.option("--no-browser", is_flag=True, help="Do not open the browser.")
@click.option(
    "--dev",
    is_flag=True,
    help="Allow the Vite dev server (http://localhost:5173) to call the API.",
)
@click.pass_obj
def ui_command(
    obj: dict[str, Any], port: Optional[int], no_browser: bool, dev: bool
) -> None:
    """Start the web UI on this computer and open it in the browser."""
    import socket
    import threading
    import webbrowser

    import uvicorn

    from ..api.app import create_app, web_dist

    app = _open_app(obj["log_level"], console_logs=True)
    port = port or app.settings.port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise click.ClickException(
                f"Port {port} is already in use. Is Cratekeeper already running? "
                "Use --port to pick another one."
            )
    origins = ("http://localhost:5173", "http://127.0.0.1:5173") if dev else ()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(app, port, extra_origins=origins),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    url = f"http://127.0.0.1:{port}"
    if not (web_dist() / "index.html").is_file():
        console.print("[yellow]The web UI is not built: run 'make ui'.[/yellow]")
    console.print(
        f"Cratekeeper is running at [link={url}]{url}[/link] (Ctrl+C stops it)"
    )
    if not no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    try:
        server.run()
    finally:
        if not app.runner.shutdown(timeout=0):
            console.print("Waiting for the running job to finish…")
            app.runner.shutdown()
        app.close()


@cli.command("status")
@click.pass_obj
def status_command(obj: dict[str, Any]) -> None:
    """Show settings, connections and library counts."""
    app = _open_app(obj["log_level"], console_logs=True)
    settings = app.settings
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column(overflow="fold")

    def row(label: str, value: str, ok: Optional[bool] = None) -> None:
        mark = "" if ok is None else ("[green]✔[/green]" if ok else "[red]✘[/red]")
        table.add_row(label, f"{mark} {value}".strip())

    row("Home", str(app.home.root))
    row("Music folder", str(settings.music_folder), settings.music_folder.is_dir())
    if settings.bandcamp_folder:
        row(
            "Bandcamp folder",
            str(settings.bandcamp_folder),
            settings.bandcamp_folder.is_dir(),
        )
    try:
        location = app.rekordbox()
        row("Rekordbox library", str(location.db_path), True)
    except RekordboxError as exc:
        row("Rekordbox library", str(exc), False)
    row("Rekordbox app", "running" if rekordbox_running() else "closed")
    row(
        "Tidal login",
        "stored" if app.auth.has_stored_login() else "missing",
        app.auth.has_stored_login(),
    )
    row(
        "Downloader",
        (
            "tidal-dl-ng installed"
            if downloader_available()
            else "tidal-dl-ng not installed"
        ),
        downloader_available(),
    )
    row("ffmpeg", shutil.which("ffmpeg") or "not found", bool(shutil.which("ffmpeg")))
    with app.db.session() as session:
        counts = repo.library_counts(session)
        last = repo.latest_run(session)
        last_text = (
            f"{last.kind} {last.status} at {last.started_at:%Y-%m-%d %H:%M}"
            if last
            else "never"
        )
    row("Library", ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items()))
    row("Last run", last_text)
    console.print(table)
    if counts["playlists"] == 0 and v1_db_path().is_file():
        console.print(
            "[yellow]Found a v1 database. Run 'cratekeeper migrate' to import it."
            "[/yellow]"
        )


@cli.group("backups", invoke_without_command=True)
@click.pass_context
def backups_command(ctx: click.Context) -> None:
    """List Backups, or restore one."""
    if ctx.invoked_subcommand is not None:
        return
    app = _open_app(ctx.obj["log_level"], console_logs=True)
    backups = list_backups(app.home)
    if not backups:
        console.print("No backups yet.")
        return
    table = Table("ID", "Kind", "Label", "Size")
    for info in backups:
        table.add_row(info.id, info.kind, info.label, f"{info.size_bytes / 1e6:.1f} MB")
    console.print(table)


@backups_command.command("restore")
@click.argument("backup_id")
@click.option("--yes", "-y", is_flag=True, help="Restore without asking.")
@click.pass_obj
def restore_command(obj: dict[str, Any], backup_id: str, yes: bool) -> None:
    """Restore BACKUP_ID (the current state is backed up first)."""
    app = _open_app(obj["log_level"], console_logs=False)
    if not yes and not click.confirm(f"Restore backup {backup_id}?"):
        return
    info = _run_job(app, "restore", "Restore", lambda ctx: restore(app, ctx, backup_id))
    console.print(f"[green]Restored[/green] {info.id}")


@cli.command("login")
@click.pass_obj
def login_command(obj: dict[str, Any]) -> None:
    """Log in to Tidal in the browser."""
    app = _open_app(obj["log_level"], console_logs=True)
    start = app.auth.start_login()
    console.print(
        f"Open [link={start.url}]{start.url}[/link] and confirm code "
        f"[bold]{start.user_code}[/bold]."
    )
    with console.status("Waiting for Tidal…"):
        state = app.auth.wait_for_login(timeout=max(start.expires_at - _now(), 1))
    if state != "done":
        raise click.ClickException(app.auth.login_state()[1] or "Login failed")
    console.print("[green]Logged in to Tidal.[/green]")


@cli.command("migrate")
@click.option("--from-db", type=click.Path(path_type=Path), help="v1 sync.db.")
@click.option(
    "--env-file",
    type=click.Path(path_type=Path),
    help="v1 settings file, e.g. config/.env-Tidal.",
)
@click.option(
    "--mapping",
    type=click.Path(path_type=Path, exists=True),
    help="Playlist tag mapping to use instead of the built-in one.",
)
@click.option("--force", is_flag=True, help="Replace an existing Cratekeeper database.")
@click.pass_obj
def migrate_command(
    obj: dict[str, Any],
    from_db: Optional[Path],
    env_file: Optional[Path],
    mapping: Optional[Path],
    force: bool,
) -> None:
    """Import v1 (tidal-cleanup) data and settings once.

    v1 files stay untouched.
    """
    from ..home import Home

    setup_logging(obj["log_level"], console=True)
    home = Home.resolve()
    try:
        report = migrate(
            home, v1_db=from_db, env_file=env_file, mapping=mapping, force=force
        )
    except MigrateError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(
        f"[green]Imported[/green] {report.playlists} playlists and "
        f"{report.tracks} tracks into {report.database}"
    )
    console.print(
        f"Removed {report.orphan_tracks_removed} Library tracks in no "
        f"playlist; fixed {report.shared_paths_fixed} shared file paths; "
        f"{report.library_flags_cleared} Tidal tracks are no longer marked as "
        "Library tracks."
    )
    for key, value in report.settings.items():
        console.print(f"  {key} = {value}")
    for line in report.copied:
        console.print(f"Copied {line}")
    for note in report.notes:
        console.print(f"[yellow]Note:[/yellow] {note}")
    console.print("Next: 'cratekeeper sync --plan-only' shows what would change.")


def _now() -> float:
    import time

    return time.time()


def main() -> None:
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
