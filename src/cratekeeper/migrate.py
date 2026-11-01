"""Import a v1 (tidal-cleanup) install into the Cratekeeper home, once.

v1 files are only read, never changed. Steps:
1. copy ``~/.tidal-cleanup/sync.db`` with SQLite's backup API and upgrade it
2. clean up v1 data: local tracks in no playlist, file paths shared by several
   tracks, and Tidal timestamps (so the first Tidal refresh is a full one)
3. write ``config.toml`` from the v1 settings (env file and environment)
4. copy the Tidal login and the Playlist tag mapping
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .db.engine import Database
from .db.models import Playlist, PlaylistTrack, Track
from .home import Home
from .settings import Settings

logger = logging.getLogger(__name__)

V1_BANDCAMP_DEFAULT = Path("/Volumes/HDD1TB/Music/DJing/Bandcamp/Playlists/PLAYLISTS")


def v1_db_path() -> Path:
    """Return where v1 kept its database."""
    return Path.home() / ".tidal-cleanup" / "sync.db"


def _v1_token_path() -> Path:
    return Path.home() / "Documents" / "tidal_session.json"


def _v1_tidal_dl_settings() -> Path:
    return Path.home() / ".config" / "tidal_dl_ng" / "settings.json"


QUALITIES = {"LOW", "HIGH", "LOSSLESS", "HI_RES_LOSSLESS"}


class MigrateError(RuntimeError):
    """Raised when the import cannot run."""


@dataclass
class MigrateReport:
    """What the import did."""

    database: str = ""
    playlists: int = 0
    tracks: int = 0
    orphan_tracks_removed: int = 0
    shared_paths_fixed: int = 0
    settings: dict[str, Any] = field(default_factory=dict)
    copied: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def migrate(
    home: Home,
    *,
    v1_db: Optional[Path] = None,
    env_file: Optional[Path] = None,
    mapping: Optional[Path] = None,
    tidal_session: Optional[Path] = None,
    force: bool = False,
) -> MigrateReport:
    """Import v1 into ``home``."""
    v1_db = v1_db or v1_db_path()
    if not v1_db.is_file():
        raise MigrateError(f"No v1 database at {v1_db}")
    home.ensure()
    if home.db_file.exists() and not force and _has_playlists(home.db_file):
        raise MigrateError(
            f"{home.db_file} already has data. Use --force to replace it."
        )
    for suffix in ("", "-wal", "-shm"):
        Path(f"{home.db_file}{suffix}").unlink(missing_ok=True)

    report = MigrateReport(database=str(home.db_file))
    source_url = f"file:{v1_db}?mode=ro"
    with (
        closing(sqlite3.connect(source_url, uri=True)) as source,
        closing(sqlite3.connect(home.db_file)) as target,
    ):
        source.backup(target)
    db = Database(home.db_file)
    db.prepare()
    with db.session() as session:
        report.orphan_tracks_removed = _remove_orphan_local_tracks(session)
        report.shared_paths_fixed = _fix_shared_paths(session)
        session.execute(update(Playlist).values(last_updated_tidal=None))
        report.playlists = int(session.scalar(select(func.count(Playlist.id))) or 0)
        report.tracks = int(session.scalar(select(func.count(Track.id))) or 0)
    db.dispose()

    v1_env = _read_v1_env(env_file)
    settings = _settings_from_v1(v1_env, report)
    settings.save(home)
    report.settings = {
        k: str(v) for k, v in settings.model_dump().items() if v is not None
    }

    token = (
        tidal_session
        or Path(
            v1_env.get("TIDAL_CLEANUP_TIDAL_TOKEN_FILE", str(_v1_token_path()))
        ).expanduser()
    )
    if token.is_file():
        shutil.copy2(token, home.tidal_session_file)
        home.tidal_session_file.chmod(0o600)
        report.copied.append(f"Tidal login from {token}")
    else:
        report.notes.append("No v1 Tidal login found: run 'cratekeeper login'")
    if mapping is not None:
        shutil.copy2(mapping, home.tag_mapping_file)
        report.copied.append(f"Playlist tag mapping from {mapping}")
    report.notes.append(
        "Playlist folders are matched by name during the first refresh. Run it "
        "before renaming playlists on Tidal."
    )
    return report


def _has_playlists(path: Path) -> bool:
    try:
        with closing(sqlite3.connect(path)) as conn:
            row = conn.execute("SELECT count(*) FROM playlists").fetchone()
    except sqlite3.DatabaseError:
        return False
    return bool(row and row[0])


def _remove_orphan_local_tracks(session: Session) -> int:
    """Delete tracks without Tidal ID that are in no playlist (v1 created many)."""
    in_playlist = select(PlaylistTrack.track_id).distinct()
    result = session.execute(
        delete(Track).where(Track.tidal_id.is_(None), Track.id.not_in(in_playlist))
    )
    return int(getattr(result, "rowcount", 0) or 0)


def _fix_shared_paths(session: Session) -> int:
    """Give every file path one owner: Tidal track, then one in a playlist, then ID."""
    in_playlist = set(session.scalars(select(PlaylistTrack.track_id).distinct()))
    owners: dict[str, list[Track]] = {}
    for track in session.scalars(select(Track).where(Track.file_paths.is_not(None))):
        for path in track.file_paths or []:
            owners.setdefault(path, []).append(track)
    fixed = 0
    for path, tracks in owners.items():
        if len(tracks) < 2:
            continue
        tracks.sort(key=lambda t: (t.tidal_id is None, t.id not in in_playlist, t.id))
        for other in tracks[1:]:
            other.file_paths = [p for p in other.file_paths or [] if p != path]
        fixed += 1
    session.flush()
    return fixed


def _read_v1_env(env_file: Optional[Path]) -> dict[str, str]:
    values: dict[str, str] = {}
    if env_file is not None:
        if not env_file.is_file():
            raise MigrateError(f"Env file not found: {env_file}")
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key, value in os.environ.items():
        if key.startswith("TIDAL_CLEANUP_"):
            values[key] = value
    return values


def _settings_from_v1(env: dict[str, str], report: MigrateReport) -> Settings:
    data: dict[str, Any] = {}
    if music := env.get("TIDAL_CLEANUP_MP3_DIRECTORY"):
        data["music_folder"] = music
    else:
        report.notes.append(
            "TIDAL_CLEANUP_MP3_DIRECTORY was not set: check music_folder in Settings"
        )
    data["bandcamp_folder"] = env.get(
        "TIDAL_CLEANUP_BANDCAMP_PLAYLISTS_DIR", str(V1_BANDCAMP_DEFAULT)
    )
    if fmt := env.get("TIDAL_CLEANUP_TARGET_FORMAT"):
        data["target_format"] = fmt.lower().lstrip(".")
    if quality := env.get("TIDAL_CLEANUP_FFMPEG_QUALITY"):
        data["ffmpeg_quality"] = quality
    download_quality = _v1_download_quality()
    if download_quality:
        data["download_quality"] = download_quality
    return Settings.model_validate(data)


def _v1_download_quality() -> Optional[str]:
    """Read the audio quality v1 actually used (tidal-dl-ng's own settings)."""
    try:
        quality = json.loads(_v1_tidal_dl_settings().read_text()).get("quality_audio")
    except (OSError, ValueError):
        return None
    return quality if quality in QUALITIES else None
