"""Configuration management for the Tidal cleanup application."""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Load .env file from config directory or project root
    config_env = Path(__file__).parent.parent.parent / "config" / ".env"
    if config_env.exists():
        load_dotenv(config_env)
    else:
        # Fallback to project root .env
        load_dotenv()
except ImportError:
    # python-dotenv not available, skip loading
    pass


class Config:
    """Application configuration."""

    def __init__(self) -> None:
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
        self.target_audio_format = (
            os.getenv("TIDAL_CLEANUP_TARGET_FORMAT", "mp3").lower().replace(".", "")
        )

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

        # Database settings
        default_db_path = str(Path.home() / ".tidal-cleanup" / "sync.db")
        self.database_path = Path(
            os.getenv("TIDAL_CLEANUP_DATABASE_PATH", default_db_path)
        )

        # Ensure directories exist
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Ensure required directories exist."""
        for directory in [self.mp3_directory, self.mp3_directory]:
            directory.mkdir(parents=True, exist_ok=True)

        # Ensure output file directory exists
        self.rekordbox_output_file.parent.mkdir(parents=True, exist_ok=True)

        # Ensure database directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


def get_config() -> Config:
    """Get application configuration."""
    return Config()
