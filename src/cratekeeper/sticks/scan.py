"""Scan mounted USB sticks and record which Tracks each one holds.

Sticks are only read, never written. A stick that is not mounted keeps its last scan.
"""

from __future__ import annotations

import logging
import plistlib
import subprocess  # noqa: S404 - runs diskutil with a fixed argument list
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from ..db import Database, Stick, StickTrack, Track
from ..db.repository import utc_now
from ..music.paths import resolve_stored_path, simplify
from .export_pdb import ExportError, ExportTrack, read_export

logger = logging.getLogger(__name__)

VOLUMES = Path("/Volumes")
DISKUTIL = "/usr/sbin/diskutil"


class VolumeIdError(RuntimeError):
    """Raised when the volume ID of a mounted stick cannot be read."""


@dataclass(frozen=True)
class MountedStick:
    """A mounted volume with a ``PIONEER/rekordbox`` folder."""

    name: str
    mount: Path
    export: Optional[Path]  # export.pdb, if the stick has one
    one_library: bool  # exportLibrary.db is there


@dataclass
class ScanResult:
    """The sticks one scan read, and the ones it could not read."""

    scanned: list[int] = field(default_factory=list)  # Stick IDs
    problems: list[str] = field(default_factory=list)


def find_sticks(volumes: Optional[Path] = None) -> list[MountedStick]:
    """Return the mounted volumes (in ``volumes``) that hold a Rekordbox export."""
    volumes = volumes or VOLUMES
    found = []
    try:
        mounts = sorted(p for p in volumes.iterdir() if not p.name.startswith("."))
    except OSError as exc:
        logger.warning("Cannot list %s: %s", volumes, exc)
        return []
    for mount in mounts:
        folder = mount / "PIONEER" / "rekordbox"
        try:
            # FAT sticks may store upper-case names (EXPORT.PDB)
            files = {p.name.casefold(): p for p in folder.iterdir()}
        except OSError:
            continue
        found.append(
            MountedStick(
                name=mount.name,
                mount=mount,
                export=files.get("export.pdb"),
                one_library="exportlibrary.db" in files,
            )
        )
    return found


def volume_id(mount: Path) -> str:
    """Return the volume UUID of ``mount``.

    Returns ``name:<volume name>`` when the volume has no UUID or the system has no
    diskutil (not macOS).

    Raises:
        VolumeIdError: diskutil failed. Using the name then would add the stick twice.
    """
    try:
        result = subprocess.run(  # noqa: S603 - fixed command, no shell
            [DISKUTIL, "info", "-plist", str(mount)],
            capture_output=True,
            timeout=10,
            check=True,
        )
        uuid = plistlib.loads(result.stdout).get("VolumeUUID")
    except FileNotFoundError:
        uuid = None
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise VolumeIdError(f"cannot read the volume ID ({exc})") from exc
    return str(uuid) if uuid else f"name:{mount.name}"


def _name_key(artist: str, title: str) -> str:
    artist_key, title_key = simplify(artist), simplify(title)
    return f"{artist_key}|{title_key}" if artist_key and title_key else ""


class TrackIndex:
    """Finds the Tracks a stick track belongs to.

    A Track matches by the same file (name and size) or the same ISRC, so duplicate
    Tracks of one recording all match. Artist and title (with the version) are only used
    when neither matches.
    """

    def __init__(self, music_folder: Path) -> None:
        """Create an empty index for files under ``music_folder``."""
        self.music_folder = music_folder
        self.by_file: dict[tuple[str, int], set[int]] = defaultdict(set)
        self.by_isrc: dict[str, set[int]] = defaultdict(set)
        self.by_name: dict[str, set[int]] = defaultdict(set)

    def add(self, track: Track) -> None:
        """Add one Track."""
        for raw in track.file_paths or []:
            path = resolve_stored_path(raw, self.music_folder)
            try:
                size: Optional[int] = path.stat().st_size
            except OSError:
                size = track.file_size_bytes
            if size:
                self.by_file[(simplify(path.name), size)].add(track.id)
        if track.isrc and track.isrc.strip():
            self.by_isrc[track.isrc.strip().upper()].add(track.id)
        title = f"{track.title} ({track.version})" if track.version else track.title
        key = _name_key(track.artist, title)
        if key:
            self.by_name[key].add(track.id)

    def match(self, item: ExportTrack) -> set[int]:
        """Return the IDs of the Tracks that ``item`` is (may be empty)."""
        found = set(self.by_file.get((simplify(item.file_name), item.file_size), ()))
        if item.isrc.strip():
            found |= self.by_isrc.get(item.isrc.strip().upper(), set())
        if not found:
            found = set(self.by_name.get(_name_key(item.artist, item.title), ()))
        return found


def scan_sticks(
    db: Database,
    music_folder: Path,
    volumes: Optional[Path] = None,
    read_volume_id: Optional[Callable[[Path], str]] = None,
) -> ScanResult:
    """Read every mounted stick and replace its stored Tracks."""
    read_volume_id = read_volume_id or volume_id
    result = ScanResult()
    mounted = find_sticks(volumes)
    if not mounted:
        return result
    with db.session() as session:
        index = TrackIndex(music_folder)
        for track in session.scalars(select(Track)):
            index.add(track)
        for stick in mounted:
            if stick.export is None:
                result.problems.append(_no_export(stick))
                continue
            try:
                stick_id = read_volume_id(stick.mount)
                items = read_export(stick.export)
            except (VolumeIdError, ExportError) as exc:
                result.problems.append(f"{stick.name}: {exc}")
                continue
            matches = [index.match(item) for item in items]
            row = _save(
                session,
                volume_id=stick_id,
                name=stick.name,
                total=len(items),
                matched=sum(1 for m in matches if m),
                track_ids=set().union(*matches),
            )
            logger.info(
                "Stick %s: %d tracks, %d matched",
                row.name,
                row.tracks_total,
                row.tracks_matched,
            )
            result.scanned.append(row.id)
    return result


def _no_export(stick: MountedStick) -> str:
    if stick.one_library:
        return (
            f"{stick.name}: only exportLibrary.db (One Library) found, "
            "which Cratekeeper cannot read yet"
        )
    return f"{stick.name}: no export.pdb in PIONEER/rekordbox"


def _save(
    session: Session,
    *,
    volume_id: str,
    name: str,
    total: int,
    matched: int,
    track_ids: Iterable[int],
) -> Stick:
    stick = session.scalars(
        select(Stick).where(Stick.volume_id == volume_id)
    ).one_or_none()
    if stick is None:
        stick = Stick(volume_id=volume_id, name=name, scanned_at=utc_now())
        session.add(stick)
    stick.name = name
    stick.scanned_at = utc_now()
    stick.tracks_total = total
    stick.tracks_matched = matched
    session.flush()
    session.execute(delete(StickTrack).where(StickTrack.stick_id == stick.id))
    rows = [{"stick_id": stick.id, "track_id": t} for t in sorted(track_ids)]
    if rows:
        session.execute(insert(StickTrack), rows)
    return stick
