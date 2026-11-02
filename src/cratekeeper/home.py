"""Locations of Cratekeeper's own files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

HOME_ENV = "CRATEKEEPER_HOME"


@dataclass(frozen=True)
class Home:
    """The Cratekeeper home directory and the files inside it."""

    root: Path

    @classmethod
    def resolve(cls) -> Home:
        """Return the home from ``CRATEKEEPER_HOME`` or ``~/.cratekeeper``."""
        raw = os.environ.get(HOME_ENV, "").strip()
        root = Path(raw).expanduser() if raw else Path.home() / ".cratekeeper"
        return cls(root=root)

    def ensure(self) -> Home:
        """Create the home directory and its sub-folders."""
        for path in (self.root, self.backups_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def config_file(self) -> Path:
        """Return the settings file."""
        return self.root / "config.toml"

    @property
    def db_file(self) -> Path:
        """Return Cratekeeper's database."""
        return self.root / "cratekeeper.db"

    @property
    def tidal_session_file(self) -> Path:
        """Return the stored Tidal login."""
        return self.root / "tidal_session.json"

    @property
    def tag_mapping_file(self) -> Path:
        """Return the user's Playlist tag mapping."""
        return self.root / "tag_mapping.json"

    @property
    def tidal_dl_dir(self) -> Path:
        """Return the config folder used for tidal-dl-ng."""
        return self.root / "tidal-dl-ng"

    @property
    def backups_dir(self) -> Path:
        """Return the folder that holds Backups."""
        return self.root / "backups"

    @property
    def logs_dir(self) -> Path:
        """Return the folder that holds log files."""
        return self.root / "logs"

    @property
    def lock_file(self) -> Path:
        """Return the lock file that allows one running job per home."""
        return self.root / "cratekeeper.lock"
