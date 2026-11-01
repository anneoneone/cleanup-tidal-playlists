"""Test isolation: no test may touch real user data or the network.

Also builds small real audio files, so tag code runs against mutagen itself.
"""

import os
import socket
import struct
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TALB, TIT2, TPE1, TSRC, TXXX

AudioMaker = Callable[..., Path]

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
