"""Terminal output: live job progress and the Plan as tables."""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TaskID, TextColumn
from rich.table import Table

from ..jobs import JobEvent
from ..rekordbox.plan import ChangeKind, Plan, PlanGroup

console = Console()

KIND_LABELS = {
    ChangeKind.CREATE_PLAYLIST: "create",
    ChangeKind.RENAME_PLAYLIST: "rename",
    ChangeKind.MOVE_PLAYLIST: "move",
    ChangeKind.IMPORT_TRACK: "import",
    ChangeKind.ADD_TRACK: "add",
    ChangeKind.REMOVE_TRACK: "remove",
    ChangeKind.SET_GENRE: "genre",
    ChangeKind.DELETE_PLAYLIST: "delete",
}
LEVEL_STYLES = {"warning": "yellow", "error": "red", "critical": "red"}


class JobReporter:
    """Prints job events: one progress bar per step, log lines in between."""

    def __init__(self, out: Console = console) -> None:
        """Create a reporter writing to ``out``."""
        self.out = out
        self.progress = Progress(
            TextColumn("[bold]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("[dim]{task.fields[item]}"),
            console=out,
            transient=False,
        )
        self.task: Optional[TaskID] = None

    def __call__(self, event: JobEvent) -> None:
        """Handle one event."""
        if event.kind == "step":
            self._start_step(event.step or event.message)
        elif event.kind == "progress" and self.task is not None:
            self.progress.update(
                self.task,
                completed=event.current or 0,
                total=event.total,
                item=(event.message or "")[:60],
            )
        elif event.kind == "log":
            style = LEVEL_STYLES.get(event.level or "", "dim")
            self.progress.console.print(f"  {event.message}", style=style, markup=False)
        elif event.kind in ("finished", "failed", "cancelled"):
            self._stop()
            if event.kind == "failed":
                self.out.print(f"[red]Failed:[/red] {event.message}", markup=True)
            elif event.kind == "cancelled":
                self.out.print("[yellow]Cancelled[/yellow]")

    def _start_step(self, name: str) -> None:
        if self.task is None:
            self.progress.start()
        else:
            task = self.progress.tasks[self.task]
            if task.total is None:
                self.progress.update(self.task, total=1, completed=1)
        self.task = self.progress.add_task(name, total=None, item="")

    def _stop(self) -> None:
        if self.task is not None:
            self.progress.stop()
            self.task = None


def print_plan(plan: Plan, include_deletions: bool, limit: int = 12) -> None:
    """Print the Plan, one table per group."""
    if plan.is_empty:
        console.print("[green]Rekordbox is up to date. Nothing to change.[/green]")
    for group in plan.groups:
        _print_group(group, include_deletions, limit)
    totals = {k: v for k, v in plan.totals().items() if v}
    if totals:
        parts = ", ".join(
            f"{count} {KIND_LABELS[ChangeKind(kind)]}" for kind, count in totals.items()
        )
        console.print(f"[bold]Total:[/bold] {parts}")
    if plan.new_folders:
        console.print("New folders: " + ", ".join(plan.new_folders))
    for warning in plan.warnings:
        console.print(f"[yellow]Note:[/yellow] {warning}")


def _print_group(group: PlanGroup, include_deletions: bool, limit: int) -> None:
    if not group.changes:
        return
    chosen = group.selected_by_default or include_deletions
    mark = "[green]✔[/green]" if chosen else "[dim]✘ (skipped)[/dim]"
    target = "/".join(group.folder + ([group.target_name] if group.target_name else []))
    table = Table(
        title=f"{mark} {group.title}" + (f"  →  {target}" if target else ""),
        title_justify="left",
        show_header=False,
        box=None,
        padding=(0, 2),
    )
    for change in group.changes[:limit]:
        table.add_row(f"[cyan]{KIND_LABELS[change.kind]}[/cyan]", change.summary)
    if len(group.changes) > limit:
        table.add_row("", f"[dim]… and {len(group.changes) - limit} more[/dim]")
    console.print(table)
