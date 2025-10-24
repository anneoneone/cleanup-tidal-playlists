"""Data models for the Tidal cleanup application."""

from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Set, Union

from pydantic import BaseModel, ConfigDict, field_validator


class Track(BaseModel):
    """Represents a music track."""

    title: str
    artist: str
    album: Optional[str] = None
    year: Optional[int] = None
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

    @property
    def duration_formatted(self) -> str:
        """Get formatted duration string (mm:ss)."""
        if self.duration is None:
            return "Unknown"
        minutes = self.duration // 60
        seconds = self.duration % 60
        return f"{minutes}:{seconds:02d}"

    @property
    def mix_info(self) -> Optional[str]:
        """Extract mix/version information from title."""
        import re

        # Look for mix information in parentheses or brackets
        mix_patterns = [
            r"\(([^)]*(?:mix|remix|edit|version|dub|extended|radio|club|original)"
            r"[^)]*)\)",
            r"\[([^\]]*(?:mix|remix|edit|version|dub|extended|radio|club|original)"
            r"[^\]]*)\]",
        ]

        for pattern in mix_patterns:
            match = re.search(pattern, self.title, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def get_detailed_info(self) -> str:
        """Get detailed track information for display."""
        parts = [f"{self.artist} - {self.title}"]

        if self.album:
            album_str = self.album
            if self.year:
                album_str += f" ({self.year})"
            parts.append(f"Album: {album_str}")

        if self.duration:
            parts.append(f"Duration: {self.duration_formatted}")

        mix = self.mix_info
        if mix:
            parts.append(f"Mix: {mix}")

        return " | ".join(parts)

    @field_validator("file_path", mode="before")
    @classmethod
    def validate_file_path(cls, v: Union[str, Path, None]) -> Optional[Path]:
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
    def validate_local_folder(cls, v: Union[str, Path, None]) -> Optional[Path]:
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
    metadata: Optional[dict[str, Any]] = None

    @property
    def stem(self) -> str:
        """File name without extension."""
        return self.path.stem

    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, v: Union[str, Path]) -> Path:
        """Convert input to Path object."""
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
    was_skipped: bool = False  # True if conversion was skipped
    error_message: Optional[str] = None
    created_at: datetime = datetime.now()
    completed_at: Optional[datetime] = None

    @field_validator("source_path", "target_path", mode="before")
    @classmethod
    def validate_paths(cls, v: Union[str, Path]) -> Path:
        """Validate file paths."""
        return Path(v)

    model_config = ConfigDict(arbitrary_types_allowed=True)
