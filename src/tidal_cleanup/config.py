"""Configuration management for the Tidal cleanup application."""

import os
from pathlib import Path
from typing import Optional


class Config:
    """Application configuration."""

    def __init__(self):
        """Initialize configuration from environment variables."""
        # Tidal API settings
        self.tidal_token_file = Path(
            os.getenv(
                "TIDAL_CLEANUP_TIDAL_TOKEN_FILE",
                str(Path.home() / "Documents" / "tidal_session.json"),
            )
        )

        # Audio directories
        self.m4a_directory = Path(
            os.getenv(
                "TIDAL_CLEANUP_M4A_DIRECTORY",
                str(Path.home() / "Music" / "Tidal" / "m4a"),
            )
        )
        self.mp3_directory = Path(
            os.getenv(
                "TIDAL_CLEANUP_MP3_DIRECTORY",
                str(Path.home() / "Music" / "Tidal" / "mp3"),
            )
        )

        # Rekordbox settings
        self.rekordbox_input_folder = Path(
            os.getenv(
                "TIDAL_CLEANUP_REKORDBOX_INPUT_FOLDER",
                str(self.mp3_directory / "Playlists"),
            )
        )
        self.rekordbox_output_file = Path(
            os.getenv(
                "TIDAL_CLEANUP_REKORDBOX_OUTPUT_FILE",
                str(Path.home() / "Documents" / "rekordbox" / "antons_music.xml"),
            )
        )

        # Audio conversion settings
        self.ffmpeg_quality = os.getenv("TIDAL_CLEANUP_FFMPEG_QUALITY", "2")
        self.audio_extensions = (".mp3", ".flac", ".wav", ".aac", ".m4a", ".mp4")

        # Track matching settings
        self.fuzzy_match_threshold = int(
            os.getenv("TIDAL_CLEANUP_FUZZY_MATCH_THRESHOLD", "80")
        )

        # Logging settings
        self.log_level = os.getenv("TIDAL_CLEANUP_LOG_LEVEL", "INFO")
        log_file_env = os.getenv("TIDAL_CLEANUP_LOG_FILE")
        self.log_file = Path(log_file_env) if log_file_env else None

        # CLI settings
        self.interactive_mode = os.getenv(
            "TIDAL_CLEANUP_INTERACTIVE_MODE", "true"
        ).lower() in ("true", "1", "yes")

        # Ensure directories exist
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure required directories exist."""
        for directory in [self.m4a_directory, self.mp3_directory]:
            directory.mkdir(parents=True, exist_ok=True)

        # Ensure output file directory exists
        self.rekordbox_output_file.parent.mkdir(parents=True, exist_ok=True)


def get_config() -> Config:
    """Get application configuration."""
    return Config()
