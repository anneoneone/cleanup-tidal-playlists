"""Show the macOS Finder dialog so the Settings page can pick a path.

A web page cannot get an absolute path from the browser. The server runs on
the same Mac, so it opens the dialog with ``osascript`` and returns the chosen
path. Nothing is read or written: only the path goes back to the page.
"""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404 - runs osascript with a fixed argument list
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

PickField = Literal["music_folder", "bandcamp_folder", "rekordbox_db", "tag_mapping"]

# The dialog blocks one server thread; close it after this many seconds.
TIMEOUT_SECONDS = 600
USER_CANCELLED = "(-128)"


@dataclass(frozen=True)
class PickTarget:
    """What the dialog asks for."""

    kind: Literal["folder", "file"]
    prompt: str
    extensions: tuple[str, ...] = ()


TARGETS: dict[PickField, PickTarget] = {
    "music_folder": PickTarget("folder", "Choose the Music folder"),
    "bandcamp_folder": PickTarget("folder", "Choose the Bandcamp folder"),
    "rekordbox_db": PickTarget(
        "file", "Choose the Rekordbox library (master.db)", ("db",)
    ),
    "tag_mapping": PickTarget(
        "file", "Choose the Playlist tag mapping file", ("json",)
    ),
}

_lock = threading.Lock()


class PickerError(RuntimeError):
    """The dialog could not be shown."""


class PickerBusyError(PickerError):
    """Another dialog is open already."""


class InvalidPickError(ValueError):
    """The chosen path does not fit the field."""


def pick_path(field: PickField, start: Optional[str] = None) -> Optional[Path]:
    """Show the dialog and return the chosen path, or ``None`` if cancelled.

    ``start`` is the current value of the field; the dialog opens next to it.
    """
    target = TARGETS[field]
    osascript = _osascript()
    if osascript is None:
        raise PickerError("The Finder dialog only works on macOS. Type the path.")
    if not _lock.acquire(blocking=False):
        raise PickerBusyError("A Finder dialog is open already. Close it first.")
    try:
        command = [
            osascript,
            *_script(target),
            target.prompt,
            _start_folder(field, start),
        ]
        result = subprocess.run(  # noqa: S603 - fixed command, no shell
            command,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PickerError("The Finder dialog was open too long.") from exc
    finally:
        _lock.release()
    if result.returncode != 0:
        if USER_CANCELLED in result.stderr:
            return None
        detail = result.stderr.strip() or f"exit code {result.returncode}"
        raise PickerError(f"Could not show the Finder dialog: {detail}")
    return check_pick(field, result.stdout)


def check_pick(field: PickField, raw: str) -> Path:
    """Return the dialog's answer as a path, if it fits ``field``."""
    target = TARGETS[field]
    text = raw.strip()
    if not text.startswith("/"):
        raise InvalidPickError(f"The dialog returned no absolute path: {text!r}")
    path = Path(text)
    if target.extensions and path.suffix.lower().lstrip(".") not in target.extensions:
        wanted = ", ".join(f".{e}" for e in target.extensions)
        raise InvalidPickError(f"Choose a {wanted} file, not {path.name}.")
    return path


def _osascript() -> Optional[str]:
    if sys.platform != "darwin":
        return None
    return shutil.which("osascript")


def _script(target: PickTarget) -> list[str]:
    """Return ``-e`` arguments. The prompt and folder come in as ``argv``.

    So no value from the request ends up in the script text.
    """
    if target.kind == "folder":
        choose = "choose folder with prompt thePrompt"
    else:
        types = ", ".join(f'"{e}"' for e in target.extensions)
        choose = f"choose file with prompt thePrompt of type {{{types}}}"
    lines = [
        "on run argv",
        "set thePrompt to item 1 of argv",
        "set startFolder to item 2 of argv",
        "activate",
        'if startFolder is "" then',
        f"set picked to ({choose})",
        "else",
        f"set picked to ({choose} default location (POSIX file startFolder))",
        "end if",
        "return POSIX path of picked",
        "end run",
    ]
    args: list[str] = []
    for line in lines:
        args += ["-e", line]
    return args


def _start_folder(field: PickField, start: Optional[str]) -> str:
    """Return the folder the dialog opens in, or ``""`` for the default."""
    candidates: list[Path] = []
    if start and start.strip():
        current = Path(start.strip()).expanduser()
        if current.is_absolute():
            candidates += [current, current.parent]
    if field == "rekordbox_db":
        candidates.append(Path.home() / "Library" / "Pioneer" / "rekordbox")
    for folder in candidates:
        if folder.is_dir():
            return str(folder)
    return ""
