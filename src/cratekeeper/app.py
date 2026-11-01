"""The objects one Cratekeeper process shares (CLI and web server alike)."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import Optional

from .db import repository as repo
from .db.engine import Database
from .home import Home
from .jobs import JobBusyError, JobRunner, held_lock
from .rekordbox.connection import RekordboxLocation, locate
from .rekordbox.naming import NameRules
from .settings import Settings
from .tidal.auth import TidalAuth


@dataclass
class App:
    """Home, settings, database, Tidal login and job runner."""

    home: Home
    settings: Settings
    db: Database
    auth: TidalAuth
    runner: JobRunner

    @classmethod
    def open(cls, home: Optional[Home] = None) -> App:
        """Load the settings and prepare the database (created if missing)."""
        home = (home or Home.resolve()).ensure()
        settings = Settings.load(home)
        db = Database(home.db_file)
        db.prepare()
        # While another process runs a job, its "running" run is not stale.
        with suppress(JobBusyError), held_lock(home.lock_file), db.session() as s:
            repo.mark_interrupted_runs(s)
        return cls(
            home=home,
            settings=settings,
            db=db,
            auth=TidalAuth(home.tidal_session_file),
            runner=JobRunner(lock_path=home.lock_file),
        )

    def rules(self) -> NameRules:
        """Return the Playlist tag rules from the mapping file in use."""
        return NameRules.from_file(self.settings.tag_mapping_path(self.home))

    def rekordbox(self) -> RekordboxLocation:
        """Return the Rekordbox library location (raises if not found)."""
        return locate(self.settings.rekordbox_db)

    def reload_settings(self) -> Settings:
        """Read ``config.toml`` again (after the UI saved it)."""
        self.settings = Settings.load(self.home)
        return self.settings

    def close(self) -> None:
        """Release database connections."""
        self.db.dispose()
