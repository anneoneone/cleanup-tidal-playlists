"""Command-line interface for Rekordbox playlist management."""

import logging
import os
from pathlib import Path
from typing import Any, List, Optional

import click
from thefuzz import fuzz, process

from ..config import Config
from ..services.rekordbox_service import RekordboxService
from ..services.tidal_service import TidalService
from ..utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


@click.command()
@click.argument("playlist_name", type=str)
@click.option(
    "--fuzzy-threshold",
    default=80,
    help="Minimum fuzzy match score for playlist search (0-100)",
    type=int,
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making changes",
)
@click.option(
    "--force",
    is_flag=True,
    help="Force update even if playlist already exists",
)
@click.pass_context
def sync_playlist(
    ctx: click.Context,
    playlist_name: str,
    fuzzy_threshold: int,
    dry_run: bool,
    force: bool,
) -> None:
    """Sync a Tidal playlist to Rekordbox.

    Finds a playlist in Tidal using fuzzy search, locates the corresponding
    MP3 directory, and creates or updates the playlist in Rekordbox.

    PLAYLIST_NAME: Name of the playlist to sync (supports fuzzy matching)
    """
    # Setup logging
    setup_logging()

    config = Config()

    try:
        # Initialize services
        tidal_service = TidalService(config.tidal_token_file)
        rekordbox_service = RekordboxService(config)

        logger.info(f"🎵 Syncing playlist: {playlist_name}")

        # Step 1: Find playlist in Tidal using fuzzy search
        playlist_name_to_use = _find_playlist_name(
            tidal_service, playlist_name, fuzzy_threshold
        )

        # Step 2: Find MP3 directory for the playlist
        mp3_directory = _find_mp3_directory(config, playlist_name_to_use)
        if not mp3_directory:
            logger.error(
                f"❌ No MP3 directory found for playlist " f"'{playlist_name_to_use}'"
            )
            raise click.Abort()

        logger.info(f"📁 Found MP3 directory: {mp3_directory}")

        # Step 3: Get MP3 tracks from the directory
        mp3_tracks = _get_mp3_tracks(mp3_directory)
        logger.info(f"🎵 Found {len(mp3_tracks)} MP3 tracks")

        # Step 4: Sync playlist to Rekordbox
        _sync_to_rekordbox(rekordbox_service, playlist_name_to_use, mp3_tracks, dry_run)

    except Exception as e:
        logger.error(f"❌ Error syncing playlist: {e}")
        import traceback

        traceback.print_exc()
        raise click.Abort()


def _find_playlist_name(
    tidal_service: TidalService,
    playlist_name: str,
    fuzzy_threshold: int,
) -> str:
    """Find playlist name from Tidal or use provided name."""
    try:
        tidal_playlist = _find_tidal_playlist(
            tidal_service, playlist_name, fuzzy_threshold
        )
        if not tidal_playlist:
            logger.warning(f"⚠️ No Tidal playlist found matching '{playlist_name}'")
            logger.info("Will look for MP3 directory directly...")
            return str(playlist_name)
        else:
            logger.info(f"✅ Found Tidal playlist: {tidal_playlist.name}")
            return str(tidal_playlist.name)
    except Exception as e:
        logger.warning(f"⚠️ Could not connect to Tidal: {e}")
        logger.info("Will look for MP3 directory directly...")
        return str(playlist_name)


def _find_tidal_playlist(
    tidal_service: TidalService,
    playlist_name: str,
    fuzzy_threshold: int,
) -> Optional[Any]:
    """Find a Tidal playlist using fuzzy search."""
    playlists = tidal_service.get_playlists()
    if not playlists:
        logger.warning("No Tidal playlists found")
        return None

    # Find the best match using fuzzy search
    best_match = process.extractOne(
        playlist_name, [(p.name, p) for p in playlists], score_cutoff=fuzzy_threshold
    )

    if best_match:
        return best_match[0][1]  # Return the playlist object
    return None


def _find_mp3_directory(config: Config, playlist_name: str) -> Optional[str]:
    """Find an MP3 directory matching the playlist name."""
    music_dir = config.mp3_directory
    if not music_dir or not music_dir.exists():
        logger.error(f"MP3 directory not found: {music_dir}")
        return None

    # Look in the Playlists subdirectory first
    playlists_dir = music_dir / "Playlists"
    if playlists_dir.exists():
        for item in playlists_dir.iterdir():
            if item.is_dir():
                # Use fuzzy matching to find directory
                ratio = fuzz.ratio(playlist_name.lower(), item.name.lower())
                logger.debug(f"Comparing '{playlist_name}' vs '{item.name}': {ratio}%")
                if ratio >= 80:  # 80% similarity threshold
                    return str(item)

    # Fallback: look in the main mp3 directory
    for item in music_dir.iterdir():
        if item.is_dir() and item.name != "Playlists":
            # Use fuzzy matching to find directory
            ratio = fuzz.ratio(playlist_name.lower(), item.name.lower())
            logger.debug(f"Comparing '{playlist_name}' vs '{item.name}': {ratio}%")
            if ratio >= 80:  # 80% similarity threshold
                return str(item)

    return None


def _get_mp3_tracks(directory: str) -> List[str]:
    """Get all MP3 tracks from a directory."""
    tracks = []

    # Common audio file extensions
    audio_extensions = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"}

    for file_name in os.listdir(directory):
        file_path = os.path.join(directory, file_name)
        if os.path.isfile(file_path):
            _, ext = os.path.splitext(file_name)
            if ext.lower() in audio_extensions:
                tracks.append(file_path)

    # Sort tracks by name for consistent ordering
    return sorted(tracks, key=lambda x: os.path.basename(x).lower())


def _sync_to_rekordbox(
    rekordbox_service: RekordboxService,
    playlist_name: str,
    mp3_tracks: List[str],
    dry_run: bool,
) -> None:
    """Sync playlist to Rekordbox database."""
    # Convert string paths to Path objects for the service
    track_paths = [Path(track) for track in mp3_tracks]

    existing_playlist = rekordbox_service.find_playlist(playlist_name)

    if existing_playlist:
        logger.info(
            f"📋 Playlist already exists in Rekordbox: " f"{existing_playlist.Name}"
        )

        if dry_run:
            _show_dry_run_update(playlist_name, mp3_tracks)
        else:
            updated_playlist = rekordbox_service.update_playlist(
                existing_playlist, track_paths
            )
            if updated_playlist:
                logger.info(
                    f"✅ Updated playlist '{updated_playlist.Name}' "
                    f"with {len(mp3_tracks)} tracks"
                )
            else:
                logger.error("Failed to update playlist")
                raise click.ClickException("Failed to update playlist")
    else:
        if dry_run:
            _show_dry_run_create(playlist_name, mp3_tracks)
        else:
            new_playlist = rekordbox_service.create_playlist(playlist_name, track_paths)
            if new_playlist:
                logger.info(
                    f"✅ Created new playlist '{new_playlist.Name}' "
                    f"with {len(mp3_tracks)} tracks"
                )
            else:
                logger.error("Failed to create playlist")
                raise click.ClickException("Failed to create playlist")


def _show_dry_run_update(playlist_name: str, mp3_tracks: List[str]) -> None:
    """Show what would be updated in dry run mode."""
    logger.info("🔄 Dry run mode - changes that would be made:")
    for track in mp3_tracks[:5]:  # Show first 5 tracks
        track_name = os.path.basename(track)
        logger.info(f"   - Would add: {track_name}")
    if len(mp3_tracks) > 5:
        logger.info(f"   - ... and {len(mp3_tracks) - 5} more tracks")
    logger.info(
        f"   - Update playlist '{playlist_name}' " f"with {len(mp3_tracks)} tracks"
    )


def _show_dry_run_create(playlist_name: str, mp3_tracks: List[str]) -> None:
    """Show what would be created in dry run mode."""
    logger.info(
        f"🔄 Would create new playlist '{playlist_name}' "
        f"with {len(mp3_tracks)} tracks"
    )
    for track in mp3_tracks[:5]:  # Show first 5 tracks
        track_name = os.path.basename(track)
        logger.info(f"   - Would add: {track_name}")
    if len(mp3_tracks) > 5:
        logger.info(f"   - ... and {len(mp3_tracks) - 5} more tracks")


if __name__ == "__main__":
    sync_playlist()
