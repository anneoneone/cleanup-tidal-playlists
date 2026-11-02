"""User settings, stored in ``config.toml`` inside the home directory."""

from __future__ import annotations

import os
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any, Literal, Optional

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .home import Home

ENV_PREFIX = "CRATEKEEPER_"

DownloadQuality = Literal["LOW", "HIGH", "LOSSLESS", "HI_RES_LOSSLESS"]


class SettingsError(ValueError):
    """Raised when the settings file or an override is invalid."""


class Settings(BaseModel):
    """All user settings.

    Unset optional paths mean "auto" or "not used".
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    music_folder: Path = Field(
        default_factory=lambda: Path.home() / "Music" / "Tidal" / "mp3"
    )
    bandcamp_folder: Optional[Path] = None
    rekordbox_db: Optional[Path] = None
    tag_mapping: Optional[Path] = None
    target_format: Literal["mp3", "flac", "m4a", "aiff", "wav"] = "mp3"
    ffmpeg_quality: int = Field(default=2, ge=0, le=9)
    download_quality: DownloadQuality = "LOSSLESS"
    prune_tracks: bool = True
    backups_keep_full: int = Field(default=20, ge=1)
    backups_keep_db: int = Field(default=10, ge=1)
    port: int = Field(default=8765, ge=1024, le=65535)

    @field_validator("music_folder", "bandcamp_folder", "rekordbox_db", "tag_mapping")
    @classmethod
    def _expand_user(cls, value: Optional[Path]) -> Optional[Path]:
        return value.expanduser() if value is not None else None

    @classmethod
    def load(cls, home: Home) -> Settings:
        """Read ``config.toml`` and apply ``CRATEKEEPER_*`` environment overrides."""
        data: dict[str, Any] = {}
        if home.config_file.exists():
            try:
                data = tomllib.loads(home.config_file.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as exc:
                raise SettingsError(f"{home.config_file}: {exc}") from exc

        for name in cls.model_fields:
            raw = os.environ.get(ENV_PREFIX + name.upper())
            if raw is not None:
                data[name] = raw

        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise SettingsError(_format_validation_error(exc)) from exc

    def save(self, home: Home) -> None:
        """Write the settings to ``config.toml``.

        Unset optional values are left out.
        """
        home.root.mkdir(parents=True, exist_ok=True)
        data = {
            key: str(value) if isinstance(value, Path) else value
            for key, value in self.model_dump().items()
            if value is not None
        }
        home.config_file.write_text(tomli_w.dumps(data), encoding="utf-8")

    def tag_mapping_path(self, home: Home) -> Path:
        """Return the Playlist tag mapping file in use.

        Order: the ``tag_mapping`` setting, then ``tag_mapping.json`` in the home,
        then the mapping shipped with Cratekeeper.
        """
        if self.tag_mapping is not None:
            return self.tag_mapping
        if home.tag_mapping_file.exists():
            return home.tag_mapping_file
        return default_tag_mapping_path()


def default_tag_mapping_path() -> Path:
    """Return the Playlist tag mapping shipped with Cratekeeper."""
    return Path(str(resources.files("cratekeeper") / "defaults" / "tag_mapping.json"))


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"]) or "settings"
        parts.append(f"{field}: {error['msg']}")
    return "Invalid settings: " + "; ".join(parts)
