"""Migration script to add unified sync fields to database models.

This script adds the following fields:

Track model:
- download_status (str, default='not_downloaded')
- download_error (text, nullable)
- downloaded_at (datetime, nullable)
- last_verified_at (datetime, nullable)

Playlist model:
- sync_status (str, default='unknown')
- last_updated_tidal (datetime, nullable)
- last_synced_filesystem (datetime, nullable)

PlaylistTrack model:
- is_primary (bool, default=False)
- symlink_path (str, nullable)
- symlink_valid (bool, nullable)
- sync_status (str, default='unknown')
- synced_at (datetime, nullable)

Usage:
    python -m scripts.migrations.add_unified_sync_fields
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import inspect, text

from tidal_cleanup.database.models import (
    Base,
    DownloadStatus,
    PlaylistSyncStatus,
    TrackSyncStatus,
)
from tidal_cleanup.database.service import DatabaseService


def check_column_exists(inspector, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def add_unified_sync_fields(db_service: DatabaseService) -> None:
    """Add unified sync fields to existing database."""
    with db_service.get_session() as session:
        inspector = inspect(session.bind)

        # Check if migrations are needed
        needs_migration = False

        # Check Track table
        if not check_column_exists(inspector, "tracks", "download_status"):
            needs_migration = True
            print("✓ Track.download_status needs to be added")
        else:
            print("- Track.download_status already exists")

        # Check Playlist table
        if not check_column_exists(inspector, "playlists", "sync_status"):
            needs_migration = True
            print("✓ Playlist.sync_status needs to be added")
        else:
            print("- Playlist.sync_status already exists")

        # Check PlaylistTrack table
        if not check_column_exists(inspector, "playlist_tracks", "is_primary"):
            needs_migration = True
            print("✓ PlaylistTrack.is_primary needs to be added")
        else:
            print("- PlaylistTrack.is_primary already exists")

        if not needs_migration:
            print("\n✓ All fields already exist. No migration needed.")
            return

        print("\n" + "=" * 60)
        print("APPLYING MIGRATION")
        print("=" * 60 + "\n")

        # Add columns to Track table
        if not check_column_exists(inspector, "tracks", "download_status"):
            print("Adding Track.download_status...")
            session.execute(
                text(
                    f"ALTER TABLE tracks ADD COLUMN download_status VARCHAR(20) "
                    f"NOT NULL DEFAULT '{DownloadStatus.NOT_DOWNLOADED.value}'"
                )
            )
            session.execute(
                text(
                    "CREATE INDEX idx_tracks_download_status ON tracks (download_status)"
                )
            )

        if not check_column_exists(inspector, "tracks", "download_error"):
            print("Adding Track.download_error...")
            session.execute(text("ALTER TABLE tracks ADD COLUMN download_error TEXT"))

        if not check_column_exists(inspector, "tracks", "downloaded_at"):
            print("Adding Track.downloaded_at...")
            session.execute(
                text("ALTER TABLE tracks ADD COLUMN downloaded_at DATETIME")
            )

        if not check_column_exists(inspector, "tracks", "last_verified_at"):
            print("Adding Track.last_verified_at...")
            session.execute(
                text("ALTER TABLE tracks ADD COLUMN last_verified_at DATETIME")
            )

        # Add columns to Playlist table
        if not check_column_exists(inspector, "playlists", "sync_status"):
            print("Adding Playlist.sync_status...")
            session.execute(
                text(
                    f"ALTER TABLE playlists ADD COLUMN sync_status VARCHAR(20) "
                    f"NOT NULL DEFAULT '{PlaylistSyncStatus.UNKNOWN.value}'"
                )
            )
            session.execute(
                text(
                    "CREATE INDEX idx_playlists_sync_status ON playlists (sync_status)"
                )
            )

        if not check_column_exists(inspector, "playlists", "last_updated_tidal"):
            print("Adding Playlist.last_updated_tidal...")
            session.execute(
                text("ALTER TABLE playlists ADD COLUMN last_updated_tidal DATETIME")
            )

        if not check_column_exists(inspector, "playlists", "last_synced_filesystem"):
            print("Adding Playlist.last_synced_filesystem...")
            session.execute(
                text("ALTER TABLE playlists ADD COLUMN last_synced_filesystem DATETIME")
            )

        # Add columns to PlaylistTrack table
        if not check_column_exists(inspector, "playlist_tracks", "is_primary"):
            print("Adding PlaylistTrack.is_primary...")
            session.execute(
                text(
                    "ALTER TABLE playlist_tracks ADD COLUMN is_primary BOOLEAN "
                    "NOT NULL DEFAULT 0"
                )
            )

        if not check_column_exists(inspector, "playlist_tracks", "symlink_path"):
            print("Adding PlaylistTrack.symlink_path...")
            session.execute(
                text(
                    "ALTER TABLE playlist_tracks ADD COLUMN symlink_path VARCHAR(1000)"
                )
            )

        if not check_column_exists(inspector, "playlist_tracks", "symlink_valid"):
            print("Adding PlaylistTrack.symlink_valid...")
            session.execute(
                text("ALTER TABLE playlist_tracks ADD COLUMN symlink_valid BOOLEAN")
            )

        if not check_column_exists(inspector, "playlist_tracks", "sync_status"):
            print("Adding PlaylistTrack.sync_status...")
            session.execute(
                text(
                    f"ALTER TABLE playlist_tracks ADD COLUMN sync_status VARCHAR(20) "
                    f"NOT NULL DEFAULT '{TrackSyncStatus.UNKNOWN.value}'"
                )
            )
            session.execute(
                text(
                    "CREATE INDEX idx_playlist_tracks_sync_status "
                    "ON playlist_tracks (sync_status)"
                )
            )

        if not check_column_exists(inspector, "playlist_tracks", "synced_at"):
            print("Adding PlaylistTrack.synced_at...")
            session.execute(
                text("ALTER TABLE playlist_tracks ADD COLUMN synced_at DATETIME")
            )

        # Commit the transaction
        session.commit()
        print("\n✓ Migration completed successfully!")


def migrate_existing_data(db_service: DatabaseService) -> None:
    """Migrate existing data to use new fields."""
    from datetime import datetime

    from tidal_cleanup.database.models import Playlist, PlaylistTrack, Track

    print("\n" + "=" * 60)
    print("MIGRATING EXISTING DATA")
    print("=" * 60 + "\n")

    with db_service.get_session() as session:
        # Update Track download_status based on file_path
        tracks = session.query(Track).all()
        updated_tracks = 0

        for track in tracks:
            if track.file_path and Path(track.file_path).exists():
                track.download_status = DownloadStatus.DOWNLOADED.value
                if track.file_last_modified:
                    track.downloaded_at = track.file_last_modified
                else:
                    track.downloaded_at = datetime.utcnow()
                updated_tracks += 1
            else:
                track.download_status = DownloadStatus.NOT_DOWNLOADED.value

        if updated_tracks > 0:
            print(f"✓ Updated {updated_tracks} tracks with DOWNLOADED status")

        # Update Playlist sync_status
        playlists = session.query(Playlist).all()
        updated_playlists = 0

        for playlist in playlists:
            if playlist.last_synced_at:
                playlist.sync_status = PlaylistSyncStatus.UNKNOWN.value
                playlist.last_synced_filesystem = playlist.last_synced_at
                updated_playlists += 1
            else:
                playlist.sync_status = PlaylistSyncStatus.NEEDS_DOWNLOAD.value

            # Copy last_updated to last_updated_tidal if available
            if hasattr(playlist, "last_updated") and playlist.last_updated:
                playlist.last_updated_tidal = playlist.last_updated

        if updated_playlists > 0:
            print(f"✓ Updated {updated_playlists} playlists with sync status")

        # Update PlaylistTrack - initially mark all as primary
        # (deduplication logic will fix this later)
        playlist_tracks = session.query(PlaylistTrack).all()
        for pt in playlist_tracks:
            pt.is_primary = True
            pt.sync_status = TrackSyncStatus.UNKNOWN.value

        if len(playlist_tracks) > 0:
            print(
                f"✓ Updated {len(playlist_tracks)} playlist-track relationships "
                "(all marked as primary initially)"
            )

        session.commit()
        print("\n✓ Data migration completed!")


def main():
    """Main migration function."""
    print("=" * 60)
    print("UNIFIED SYNC FIELDS MIGRATION")
    print("=" * 60 + "\n")

    # Get database path from config or use default
    db_path = Path("tidal_cleanup.db")
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        print("Please create the database first or specify the correct path.")
        return

    print(f"Database: {db_path.absolute()}\n")

    # Create database service
    db_service = DatabaseService(db_url=f"sqlite:///{db_path}")

    # Add new fields
    add_unified_sync_fields(db_service)

    # Migrate existing data
    migrate_existing_data(db_service)

    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Test the database with: python -m pytest tests/")
    print("2. Run sync-check to see what needs syncing")
    print("3. Review the unified sync architecture in docs/")


if __name__ == "__main__":
    main()
