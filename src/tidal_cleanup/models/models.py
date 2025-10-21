"""Data models for the Tidal cleanup application."""

from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

from pydantic import BaseModel, ConfigDict, field_validator


class Track(BaseModel):
    """Represents a music track."""

    title: str
    artist: str
    album: Optional[str] = None
    genre: Optional[str] = None
    duration: Optional[int] = None  # Duration in seconds
    file_path: Optional[Path] = None
    file_size: Optional[int] = None
    file_format: Optional[str] = None
    tidal_id: Optional[str] = None

    @property
    def normalized_name(self) -> str:
        """Get normalized track name for comparison."""
        import re

        # Normalize artist name - remove feat. parts and extra text
        artist = re.sub(
            r"\s*(feat\.?|featuring|ft\.?)\s+.*", "", self.artist, flags=re.IGNORECASE
        )
        # Normalize title - remove remix, version, etc.
        title = re.sub(r"\s*\([^)]*\)\s*", "", self.title)
        title = re.sub(r"\s*\[[^\]]*\]\s*", "", title)
        return f"{artist.lower().strip()} - {title.lower().strip()}"

    @field_validator("file_path", mode="before")
    @classmethod
    def validate_file_path(cls, v):
        """Validate file path."""
        if v is not None:
            return Path(v)
        return v

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Playlist(BaseModel):
    """Represents a playlist."""

    name: str
    description: Optional[str] = None
    tracks: List[Track] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tidal_id: Optional[str] = None
    local_folder: Optional[Path] = None

    @property
    def track_count(self) -> int:
        """Get number of tracks in playlist."""
        return len(self.tracks)

    @property
    def total_duration(self) -> int:
        """Get total duration of all tracks in seconds."""
        return sum(track.duration or 0 for track in self.tracks)

    def get_track_names(self) -> Set[str]:
        """Get set of normalized track names."""
        return {track.normalized_name for track in self.tracks}

    @field_validator("local_folder", mode="before")
    @classmethod
    def validate_local_folder(cls, v):
        """Validate local folder path."""
        if v is not None:
            return Path(v)
        return v

    model_config = ConfigDict(arbitrary_types_allowed=True)


class FileInfo(BaseModel):
    """Represents information about a local audio file."""

    path: Path
    name: str
    size: int
    format: str
    duration: Optional[int] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    metadata: Optional[dict] = None

    @property
    def stem(self) -> str:
        """Get file stem (name without extension)."""
        return self.path.stem

    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, v):
        """Validate file path."""
        return Path(v)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ComparisonResult(BaseModel):
    """Represents the result of comparing local and Tidal tracks."""

    playlist_name: str
    local_only: Set[str] = set()  # Tracks only in local folder
    tidal_only: Set[str] = set()  # Tracks only in Tidal playlist
    matched: Set[str] = set()  # Tracks present in both

    @property
    def local_count(self) -> int:
        """Get count of local-only tracks."""
        return len(self.local_only)

    @property
    def tidal_count(self) -> int:
        """Get count of Tidal-only tracks."""
        return len(self.tidal_only)

    @property
    def matched_count(self) -> int:
        """Get count of matched tracks."""
        return len(self.matched)

    @property
    def total_tracks(self) -> int:
        """Get total unique tracks."""
        return len(self.local_only | self.tidal_only | self.matched)


class ConversionJob(BaseModel):
    """Represents an audio conversion job."""

    source_path: Path
    target_path: Path
    source_format: str
    target_format: str
    quality: str = "2"
    status: str = "pending"  # pending, processing, completed, failed
    error_message: Optional[str] = None
    created_at: datetime = datetime.now()
    completed_at: Optional[datetime] = None

    @field_validator("source_path", "target_path", mode="before")
    @classmethod
    def validate_paths(cls, v):
        """Validate file paths."""
        return Path(v)

    model_config = ConfigDict(arbitrary_types_allowed=True)
