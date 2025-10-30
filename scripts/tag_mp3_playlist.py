#!/usr/bin/env python3
"""Tag MP3 playlist tracks in Rekordbox using MyTag mapping.

This script will:
- accept a playlist name (folder name under MP3 Playlists root) or a full path
- parse the playlist name using the project's emoji->MyTag mapping
- find tracks in the playlist folder, add missing tracks to Rekordbox, and apply the playlist's MyTags

Example:
  scripts/tag_mp3_playlist.py "House Progressive 🏃🏼‍♂️❓"
  scripts/tag_mp3_playlist.py --path /Users/anton/Music/Tidal/mp3/Playlists/House\ Progressive\ 🏃🏼‍♂️❓

The script reuses the existing RekordboxService.sync_playlist_with_mytags implementation.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Tag MP3 playlist tracks in Rekordbox using project's MyTag mapping"
        )
    )
    p.add_argument(
        "playlist",
        nargs="?",
        help="Playlist folder name under the MP3 Playlists root (e.g. 'House Progressive 🏃🏼‍♂️❓')",
    )
    p.add_argument(
        "--path",
        help="Full path to a playlist folder (alternative to playlist name)",
    )
    p.add_argument("--debug", action="store_true", help="Enable debug logging")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    config = get_config()

    service = RekordboxService(config=config)

    if not service.db:
        logging.error(
            "Rekordbox database not available (pyrekordbox missing or DB connection failed)"
        )
        return 2

    mp3_playlists_root = config.mp3_directory / "Playlists"

    if args.path:
        playlist_path = Path(args.path).resolve()
        if not playlist_path.exists() or not playlist_path.is_dir():
            logging.error(
                f"Provided path does not exist or is not a directory: {playlist_path}"
            )
            return 2

        try:
            # Derive playlist name relative to MP3 playlists root if possible
            playlist_name = str(playlist_path.relative_to(mp3_playlists_root))
        except Exception:
            # Fall back to folder name
            playlist_name = playlist_path.name
    else:
        if not args.playlist:
            logging.error("Specify a playlist name or --path to the playlist folder")
            return 2
        playlist_name = args.playlist

    logging.info(f"Syncing playlist: {playlist_name}")

    try:
        result = service.sync_playlist_with_mytags(playlist_name)
        logging.info(f"Sync result: {result}")
        # print concise output for convenience
        print(result)
        return 0
    except Exception:
        logging.exception("Failed to sync playlist")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
