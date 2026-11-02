"""Test isolation: no test may touch real user data or the network.

Also builds small real audio files, so tag code runs against mutagen itself, and
small Rekordbox USB exports (``export.pdb``).
"""

import os
import socket
import struct
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Optional

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TALB, TIT2, TPE1, TSRC, TXXX

from cratekeeper.sticks import scan
from cratekeeper.sticks.export_pdb import ExportTrack

AudioMaker = Callable[..., Path]
ExportMaker = Callable[..., Path]

# One silent MPEG-1 Layer III frame (128 kbit/s, 44.1 kHz, 417 bytes).
_MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413


def _write_mp3(
    path: Path,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    isrc: Optional[str] = None,
    url: Optional[str] = None,
    album: Optional[str] = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_MP3_FRAME * 20)
    tags = ID3()
    if title:
        tags.add(TIT2(encoding=3, text=title))
    if artist:
        tags.add(TPE1(encoding=3, text=artist))
    if album:
        tags.add(TALB(encoding=3, text=album))
    if isrc:
        tags.add(TSRC(encoding=3, text=isrc))
    if url:
        tags.add(TXXX(encoding=3, desc="URL", text=url))
    tags.save(path)
    return path


def _write_flac(
    path: Path,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    isrc: Optional[str] = None,
    url: Optional[str] = None,
    album: Optional[str] = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # STREAMINFO: block sizes, frame sizes, 44.1 kHz, 2 channels, 16 bit, 0 samples.
    info = struct.pack(">HH", 4096, 4096) + b"\x00" * 6
    packed = (44100 << 44) | (1 << 41) | (15 << 36)
    info += packed.to_bytes(8, "big") + b"\x00" * 16
    path.write_bytes(b"fLaC" + bytes([0x80, 0, 0, len(info)]) + info)
    audio = FLAC(path)
    for key, value in (
        ("title", title),
        ("artist", artist),
        ("album", album),
        ("isrc", isrc),
        ("url", url),
    ):
        if value:
            audio[key] = value
    audio.save()
    return path


_EMPTY_PLAYLIST_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<MASTER_PLAYLIST Version="1.0.0" AutomaticSync="0">'
    '<PRODUCT Name="rekordbox" Version="6.8.0" Company="AlphaTheta"/>'
    "<PLAYLISTS/></MASTER_PLAYLIST>\n"
)


def _build_rekordbox_library(folder: Path) -> Path:
    """Create an empty, unencrypted Rekordbox library that pyrekordbox can open."""
    from datetime import datetime

    from pyrekordbox.db6 import tables
    from sqlalchemy import MetaData, create_engine
    from sqlalchemy.orm import Session

    folder.mkdir(parents=True, exist_ok=True)
    db_path = folder / "master.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    for table in tables.Base.metadata.sorted_tables:
        copy = table.to_metadata(metadata)
        for column in copy.columns:  # the real schema allows NULL here
            if not column.primary_key:
                column.nullable = True
    metadata.create_all(engine)
    now = datetime.now()

    def filled(row: Any) -> Any:
        for column in row.__table__.columns:
            if getattr(row, column.key) is None and type(column.type).__name__ == (
                "DateTime"
            ):
                setattr(row, column.key, now)
        return row

    with Session(engine) as session:
        session.add(
            filled(tables.AgentRegistry(registry_id="localUpdateCount", int_1=1))
        )
        session.add(filled(tables.DjmdMenuItems(ID="1", Class=0, Name="TRACK")))
        session.add(filled(tables.DjmdDevice(ID="dev1", MasterDBID="m1", Name="test")))
        session.commit()
    engine.dispose()
    (folder / "masterPlaylists6.xml").write_text(_EMPTY_PLAYLIST_XML)
    return db_path


@pytest.fixture(autouse=True)
def rekordbox_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend Rekordbox is not running (tests flip this to test the guard)."""
    import cratekeeper.rekordbox.connection as connection

    monkeypatch.setattr(connection, "get_rekordbox_pid", lambda: 0)


@pytest.fixture
def rekordbox_library(tmp_path: Path) -> Path:
    """Return the path of a fresh, empty Rekordbox ``master.db``."""
    return _build_rekordbox_library(tmp_path / "rekordbox")


@pytest.fixture
def make_mp3() -> AudioMaker:
    """Return a function that writes a tagged MP3 file."""
    return _write_mp3


@pytest.fixture
def make_flac() -> AudioMaker:
    """Return a function that writes a tagged FLAC file."""
    return _write_flac


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME and CRATEKEEPER_HOME at temporary folders."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CRATEKEEPER_HOME", str(tmp_path / "cratekeeper-home"))
    for key in list(os.environ):
        if key.startswith(("CRATEKEEPER_", "TIDAL_CLEANUP_")) and key != (
            "CRATEKEEPER_HOME"
        ):
            monkeypatch.delenv(key)
    return home


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that opens a network connection."""

    def guarded_connect(self: socket.socket, address: Any) -> None:
        if self.family == socket.AF_UNIX:
            return original_connect(self, address)
        raise RuntimeError(f"Network access in tests is not allowed: {address}")

    original_connect = socket.socket.connect
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


# ------------------------------------------------------- Rekordbox USB exports

_PAGE = 512


def _pdb_string(text: str) -> bytes:
    """Encode a DeviceSQL string: short ASCII, or long UTF-16."""
    if text.isascii() and len(text) < 126:
        return bytes([(len(text) + 1) << 1 | 1]) + text.encode("ascii")
    raw = text.encode("utf-16-le")
    return bytes([0x90]) + struct.pack("<H", len(raw) + 4) + b"\0" + raw


def _pdb_isrc(code: str) -> bytes:
    raw = b"\x03" + code.encode("ascii") + b"\0"
    return bytes([0x90]) + struct.pack("<H", len(raw) + 4) + b"\0" + raw


def _track_row(track: ExportTrack, artist_id: int) -> bytes:
    row = bytearray(0x5E + 2 * 21)
    struct.pack_into("<H", row, 0, 0x24)
    struct.pack_into("<I", row, 0x10, track.file_size)
    struct.pack_into("<I", row, 0x44, artist_id)
    strings = [b"\x03"] * 21  # empty strings
    strings[0] = _pdb_isrc(track.isrc) if track.isrc else b"\x03"
    strings[17] = _pdb_string(track.title)
    strings[19] = _pdb_string(track.file_name)
    strings[20] = _pdb_string(track.file_path)
    for index, value in enumerate(strings):
        struct.pack_into("<H", row, 0x5E + 2 * index, len(row))
        row += value
    return bytes(row)


def _artist_row(artist_id: int, name: str) -> bytes:
    if artist_id % 2:  # name offset in one byte
        return struct.pack("<HHIBB", 0x60, 0, artist_id, 3, 10) + _pdb_string(name)
    return struct.pack("<HHIBBH", 0x64, 0, artist_id, 3, 0, 12) + _pdb_string(name)


def _data_pages(rows: list[tuple[bytes, bool]]) -> list[list[tuple[bytes, bool]]]:
    """Split (row, present) pairs into pages that fit."""
    pages: list[list[tuple[bytes, bool]]] = [[]]
    used = 0
    for row in rows:
        groups = len(pages[-1]) // 16 + 1
        if pages[-1] and 0x28 + used + len(row[0]) + groups * 0x24 > _PAGE:
            pages.append([])
            used = 0
        pages[-1].append(row)
        used += len(row[0])
    return pages


def _page(
    index: int, kind: int, next_page: int, rows: list[tuple[bytes, bool]]
) -> bytes:
    page = bytearray(_PAGE)
    struct.pack_into("<3I", page, 4, index, kind, next_page)
    if not rows:  # an index page, like the first page of every real table
        page[0x1B] = 0x64
        return bytes(page)
    present = sum(1 for _, keep in rows if keep)
    page[0x18:0x1B] = (len(rows) | present << 13).to_bytes(3, "little")
    page[0x1B] = 0x34
    heap = 0
    for slot, (row, keep) in enumerate(rows):
        page[0x28 + heap : 0x28 + heap + len(row)] = row
        base = _PAGE - (slot // 16) * 0x24
        struct.pack_into("<H", page, base - 6 - 2 * (slot % 16), heap)
        if keep:
            (flags,) = struct.unpack_from("<H", page, base - 4)
            struct.pack_into("<H", page, base - 4, flags | 1 << slot % 16)
        heap += len(row)
    return bytes(page)


def _write_export(
    path: Path, tracks: Sequence[ExportTrack], deleted: Sequence[ExportTrack] = ()
) -> Path:
    """Write an export.pdb with a tracks and an artists table.

    ``deleted`` tracks are in the file, but marked as removed.
    """
    names = sorted({t.artist for t in [*tracks, *deleted]})
    ids = {name: index + 1 for index, name in enumerate(names)}
    track_rows = [(_track_row(t, ids[t.artist]), True) for t in tracks]
    track_rows += [(_track_row(t, ids[t.artist]), False) for t in deleted]
    artist_rows = [(_artist_row(ids[n], n), True) for n in names]
    pages: list[bytes] = [b""]  # page 0: the file header
    tables = []
    for kind, rows in ((0, track_rows), (2, artist_rows)):
        chain = [[], *_data_pages(rows)]
        first = len(pages)
        for offset, page_rows in enumerate(chain):
            index = first + offset
            pages.append(_page(index, kind, index + 1, page_rows))
        tables.append((kind, first, first + len(chain) - 1))
    header = bytearray(_PAGE)
    struct.pack_into("<7I", header, 0, 0, _PAGE, len(tables), len(pages), 5, 1, 0)
    for index, (kind, first, last) in enumerate(tables):
        struct.pack_into("<4I", header, 0x1C + 16 * index, kind, last + 1, first, last)
    pages[0] = bytes(header)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(pages))
    return path


@pytest.fixture
def write_export() -> ExportMaker:
    """Return a function that writes a small Rekordbox ``export.pdb``."""
    return _write_export


@pytest.fixture(autouse=True)
def no_mounted_sticks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Look for USB sticks in an empty temporary folder, never in /Volumes."""
    volumes = tmp_path / "volumes"
    volumes.mkdir()
    monkeypatch.setattr(scan, "VOLUMES", volumes)
    monkeypatch.setattr(scan, "volume_id", lambda mount: f"uuid-{mount.name}")
    return volumes
