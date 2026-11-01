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
