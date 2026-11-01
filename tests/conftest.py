"""Test isolation: no test may touch real user data or the network."""

import os
import socket
from pathlib import Path
from typing import Any

import pytest


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
