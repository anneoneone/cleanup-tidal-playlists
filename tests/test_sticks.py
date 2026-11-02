import plistlib
import shutil
import struct
import subprocess  # noqa: S404 - only to fake diskutil results
from pathlib import Path
from typing import Any, Optional

import pytest
from sqlalchemy import select

from cratekeeper.db import Database, Stick, StickTrack, Track
from cratekeeper.sticks import scan
from cratekeeper.sticks.export_pdb import ExportError, ExportTrack, read_export
from cratekeeper.sticks.scan import (
    VolumeIdError,
    find_sticks,
    scan_sticks,
    volume_id,
)


def item(
    title: str,
    artist: str = "Artist",
    *,
    isrc: str = "",
    file_name: Optional[str] = None,
    size: int = 1000,
) -> ExportTrack:
    name = file_name or f"{artist} - {title}.mp3"
    return ExportTrack(
        title=title,
        artist=artist,
        isrc=isrc,
        file_name=name,
        file_path=f"/Contents/{artist}/Album/{name}",
        file_size=size,
    )


def stick(volumes: Path, name: str, write_export: Any, *items: ExportTrack) -> Path:
    return write_export(volumes / name / "PIONEER" / "rekordbox" / "export.pdb", items)


# --------------------------------------------------------------------- reader


def test_read_export_returns_present_tracks(tmp_path: Path, write_export: Any) -> None:
    # Track rows fill many pages; 26 artists need two row groups in one page
    tracks = [item(f"Track {n}", f"Artist {n % 25}", size=n) for n in range(40)]
    tracks.append(item("Pátio – Ñ", "Beltrán", isrc="DEK602512307", size=7))
    path = write_export(tmp_path / "export.pdb", tracks, [item("Deleted")])

    assert read_export(path) == tracks


def test_read_export_rejects_other_files(tmp_path: Path, write_export: Any) -> None:
    data = write_export(
        tmp_path / "export.pdb", [item("One"), item("Two")]
    ).read_bytes()
    bad = tmp_path / "bad.pdb"

    for content in [b"\0" * 8, b"not an export " * 80, data[: len(data) // 2]]:
        bad.write_bytes(content)
        with pytest.raises(ExportError):
            read_export(bad)
    with pytest.raises(ExportError, match="Cannot open"):
        read_export(tmp_path / "missing.pdb")


def test_read_export_rejects_strings_outside_the_file(
    tmp_path: Path, write_export: Any
) -> None:
    path = write_export(tmp_path / "export.pdb", [item("One")])
    data = bytearray(path.read_bytes())
    row = 2 * 512 + 0x28  # first track row: page 2 (512-byte pages), after the header
    struct.pack_into("<H", data, row + 0x5E + 2 * 17, 0xFFF0)  # title offset
    path.write_bytes(bytes(data))

    with pytest.raises(ExportError, match="damaged"):
        read_export(path)


# ----------------------------------------------------------------------- scan


def test_find_sticks(no_mounted_sticks: Path, write_export: Any) -> None:
    volumes = no_mounted_sticks
    write_export(volumes / "S1" / "PIONEER" / "rekordbox" / "EXPORT.PDB", [])
    (volumes / "S2" / "PIONEER" / "rekordbox").mkdir(parents=True)
    (volumes / "S2" / "PIONEER" / "rekordbox" / "exportLibrary.db").write_bytes(b"x")
    (volumes / "Backup").mkdir()

    found = find_sticks()

    assert [(s.name, s.export is not None, s.one_library) for s in found] == [
        ("S1", True, False),
        ("S2", False, True),
    ]


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "cratekeeper.db")
    database.prepare()
    return database


def add_track(db: Database, **fields: Any) -> int:
    with db.session() as session:
        track = Track(**{"artist": "Artist", "normalized_name": "", **fields})
        session.add(track)
        session.flush()
        return track.id


def stick_tracks(db: Database) -> dict[str, set[int]]:
    with db.session() as session:
        rows = session.execute(
            select(Stick.name, StickTrack.track_id).join(
                StickTrack, StickTrack.stick_id == Stick.id
            )
        )
        found: dict[str, set[int]] = {}
        for name, track_id in rows:
            found.setdefault(name, set()).add(track_id)
        return found


def test_scan_matches_by_file_or_isrc_then_by_name(
    tmp_path: Path, db: Database, no_mounted_sticks: Path, write_export: Any
) -> None:
    music = tmp_path / "music"
    (music / "Playlists" / "House").mkdir(parents=True)
    (music / "Playlists" / "House" / "Artist - By File.mp3").write_bytes(b"a" * 1234)
    by_file = add_track(
        db, title="Other title", file_paths=["Playlists/House/Artist - By File.mp3"]
    )
    by_isrc = add_track(db, title="Other title", isrc="GBAAA0000001")
    same_recording = add_track(db, title="Compilation copy", isrc="GBAAA0000002")
    by_name = add_track(db, title="By Name", version="Extended Mix")
    other_mix = add_track(db, title="Bare", version="Dub")
    same_size_other_name = add_track(
        db, title="X", file_paths=["Playlists/House/gone.mp3"], file_size_bytes=999
    )
    stick(
        no_mounted_sticks,
        "S1",
        write_export,
        item(
            "Ignored", file_name="Artist - By File.mp3", size=1234, isrc="GBAAA0000002"
        ),
        item("Ignored", isrc="gbaaa0000001"),
        item("By Name (Extended Mix)"),
        item("Bare"),  # another mix than the Track's
        item("Not in Cratekeeper", file_name="other.mp3", size=999),
    )

    result = scan_sticks(db, music)

    assert result.problems == []
    on_stick = stick_tracks(db)["S1"]
    assert on_stick == {by_file, same_recording, by_isrc, by_name}
    assert not on_stick & {other_mix, same_size_other_name}
    with db.session() as session:
        row = session.scalars(select(Stick)).one()
        assert (row.volume_id, row.tracks_total, row.tracks_matched) == (
            "uuid-S1",
            5,
            3,
        )
        assert result.scanned == [row.id]


def test_rescan_replaces_tracks_and_keeps_unmounted_sticks(
    tmp_path: Path, db: Database, no_mounted_sticks: Path, write_export: Any
) -> None:
    one = add_track(db, title="One")
    two = add_track(db, title="Two")
    stick(no_mounted_sticks, "S1", write_export, item("One"))
    stick(no_mounted_sticks, "S2", write_export, item("One"), item("Two"))
    scan_sticks(db, tmp_path)

    # S2 is unplugged, S1 now holds Two only
    stick(no_mounted_sticks, "S1", write_export, item("Two"))
    shutil.rmtree(no_mounted_sticks / "S2")
    result = scan_sticks(db, tmp_path)

    assert len(result.scanned) == 1
    assert stick_tracks(db) == {"S1": {two}, "S2": {one, two}}


def test_scan_without_sticks_changes_nothing(tmp_path: Path, db: Database) -> None:
    result = scan_sticks(db, tmp_path)

    assert (result.scanned, result.problems) == ([], [])
    assert stick_tracks(db) == {}


def test_scan_reports_unreadable_sticks(
    tmp_path: Path, db: Database, no_mounted_sticks: Path
) -> None:
    folder = no_mounted_sticks / "NEW" / "PIONEER" / "rekordbox"
    folder.mkdir(parents=True)
    (folder / "exportLibrary.db").write_bytes(b"x")
    broken = no_mounted_sticks / "OLD" / "PIONEER" / "rekordbox"
    broken.mkdir(parents=True)
    (broken / "export.pdb").write_bytes(b"\0" * 100)
    (no_mounted_sticks / "EMPTY" / "PIONEER" / "rekordbox").mkdir(parents=True)

    result = scan_sticks(db, tmp_path)

    assert result.scanned == []
    assert len(result.problems) == 3
    assert "EMPTY: no export.pdb" in result.problems[0]
    assert "NEW: only exportLibrary.db" in result.problems[1]
    assert result.problems[2].startswith("OLD: ")


def test_stick_tracks_go_with_their_track(
    tmp_path: Path, db: Database, no_mounted_sticks: Path, write_export: Any
) -> None:
    track_id = add_track(db, title="One")
    stick(no_mounted_sticks, "S1", write_export, item("One"))
    scan_sticks(db, tmp_path)

    with db.session() as session:
        session.delete(session.get(Track, track_id))

    assert stick_tracks(db) == {}


def test_volume_id_uses_the_volume_uuid(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    results = {
        "S1": {"VolumeName": "S1", "VolumeUUID": "5C4D-940C"},
        "NOUUID": {"VolumeName": "NOUUID"},
    }

    def run(args: list[str], **kwargs: Any) -> Any:
        calls.append(args)
        name = Path(args[-1]).name
        if name in results:
            out = plistlib.dumps(results[name])
            return subprocess.CompletedProcess(args, 0, out, b"")
        raise subprocess.TimeoutExpired(args, 10)

    monkeypatch.setattr(scan.subprocess, "run", run)

    assert volume_id(Path("/Volumes/S1")) == "5C4D-940C"
    assert calls[0] == ["/usr/sbin/diskutil", "info", "-plist", "/Volumes/S1"]
    assert volume_id(Path("/Volumes/NOUUID")) == "name:NOUUID"
    # diskutil failed: no name fallback, it would add the stick a second time
    with pytest.raises(VolumeIdError):
        volume_id(Path("/Volumes/SLOW"))


def test_volume_id_without_diskutil_uses_the_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(args: list[str], **kwargs: Any) -> Any:
        raise FileNotFoundError(args[0])

    monkeypatch.setattr(scan.subprocess, "run", run)

    assert volume_id(Path("/media/S1")) == "name:S1"


def test_scan_skips_sticks_without_a_volume_id(
    tmp_path: Path,
    db: Database,
    no_mounted_sticks: Path,
    write_export: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    add_track(db, title="One")
    stick(no_mounted_sticks, "S1", write_export, item("One"))

    def fail(mount: Path) -> str:
        raise VolumeIdError("cannot read the volume ID (timeout)")

    monkeypatch.setattr(scan, "volume_id", fail)
    result = scan_sticks(db, tmp_path)

    assert result.problems == ["S1: cannot read the volume ID (timeout)"]
    assert stick_tracks(db) == {}
