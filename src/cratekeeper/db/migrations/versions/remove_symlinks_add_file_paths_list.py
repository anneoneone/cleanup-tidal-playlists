"""Remove symlink fields and change file_path to file_paths JSON array.

Revision ID: remove_symlinks
Revises: 987ed04d1693
Create Date: 2025-12-11 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import JSON, String, text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "remove_symlinks"
down_revision: Union[str, None] = "987ed04d1693"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema to remove symlinks and use file_paths list."""

    # Step 1: Add new file_paths column to tracks table
    # For SQLite, JSON type is stored as TEXT
    op.add_column("tracks", sa.Column("file_paths", sa.Text(), nullable=True))

    # Step 2: Migrate data from file_path to file_paths
    # Convert single file_path string to a JSON array with one element
    connection = op.get_bind()
    connection.execute(
        text(
            """
            UPDATE tracks
            SET file_paths = json_array(file_path)
            WHERE file_path IS NOT NULL AND file_path != ''
        """
        )
    )

    # Step 3: Drop the old file_path column
    # Note: SQLite doesn't support dropping columns directly, so we need to recreate the table
    # For now, we'll keep the column but it won't be used
    # In production, you might want to recreate the table to fully remove it

    # Step 4: Remove symlink-related columns from playlist_tracks
    # SQLite doesn't support DROP COLUMN, so we need to recreate the table

    # Create new playlist_tracks table without symlink fields
    op.execute(
        """
        CREATE TABLE playlist_tracks_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            track_id INTEGER NOT NULL,
            position INTEGER,
            in_tidal BOOLEAN NOT NULL DEFAULT 0,
            in_local BOOLEAN NOT NULL DEFAULT 0,
            in_rekordbox BOOLEAN NOT NULL DEFAULT 0,
            sync_status VARCHAR(20) NOT NULL,
            synced_at DATETIME,
            added_to_tidal DATETIME,
            added_to_local DATETIME,
            added_to_rekordbox DATETIME,
            removed_from_tidal DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
            FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE,
            UNIQUE (playlist_id, track_id)
        )
    """
    )

    # Copy data from old table to new table
    op.execute(
        """
        INSERT INTO playlist_tracks_new (
            id, playlist_id, track_id, position,
            in_tidal, in_local, in_rekordbox,
            sync_status, synced_at,
            added_to_tidal, added_to_local, added_to_rekordbox,
            removed_from_tidal, created_at, updated_at
        )
        SELECT
            id, playlist_id, track_id, position,
            in_tidal, in_local, in_rekordbox,
            sync_status, synced_at,
            added_to_tidal, added_to_local, added_to_rekordbox,
            removed_from_tidal, created_at, updated_at
        FROM playlist_tracks
    """
    )

    # Drop old table and rename new one
    op.execute("DROP TABLE playlist_tracks")
    op.execute("ALTER TABLE playlist_tracks_new RENAME TO playlist_tracks")

    # Recreate indexes
    op.create_index("idx_playlist", "playlist_tracks", ["playlist_id"])
    op.create_index("idx_track", "playlist_tracks", ["track_id"])
    op.create_index(
        "idx_sync_state", "playlist_tracks", ["in_tidal", "in_local", "in_rekordbox"]
    )


def downgrade() -> None:
    """Downgrade database schema to restore symlinks and single file_path."""

    # This is a destructive migration - downgrade will lose data
    # We can't fully restore the symlink data

    # Step 1: Restore file_path from first element of file_paths array
    connection = op.get_bind()
    connection.execute(
        text(
            """
            UPDATE tracks
            SET file_path = json_extract(file_paths, '$[0]')
            WHERE file_paths IS NOT NULL
        """
        )
    )

    # Step 2: Recreate playlist_tracks table with symlink fields
    op.execute(
        """
        CREATE TABLE playlist_tracks_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            track_id INTEGER NOT NULL,
            position INTEGER,
            in_tidal BOOLEAN NOT NULL DEFAULT 0,
            in_local BOOLEAN NOT NULL DEFAULT 0,
            in_rekordbox BOOLEAN NOT NULL DEFAULT 0,
            is_primary BOOLEAN NOT NULL DEFAULT 0,
            symlink_path VARCHAR(1000),
            symlink_valid BOOLEAN,
            sync_status VARCHAR(20) NOT NULL,
            synced_at DATETIME,
            added_to_tidal DATETIME,
            added_to_local DATETIME,
            added_to_rekordbox DATETIME,
            removed_from_tidal DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
            FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE,
            UNIQUE (playlist_id, track_id)
        )
    """
    )

    # Copy data back
    op.execute(
        """
        INSERT INTO playlist_tracks_new (
            id, playlist_id, track_id, position,
            in_tidal, in_local, in_rekordbox,
            is_primary, sync_status, synced_at,
            added_to_tidal, added_to_local, added_to_rekordbox,
            removed_from_tidal, created_at, updated_at
        )
        SELECT
            id, playlist_id, track_id, position,
            in_tidal, in_local, in_rekordbox,
            0 as is_primary, sync_status, synced_at,
            added_to_tidal, added_to_local, added_to_rekordbox,
            removed_from_tidal, created_at, updated_at
        FROM playlist_tracks
    """
    )

    # Drop new table and rename
    op.execute("DROP TABLE playlist_tracks")
    op.execute("ALTER TABLE playlist_tracks_new RENAME TO playlist_tracks")

    # Recreate indexes
    op.create_index("idx_playlist", "playlist_tracks", ["playlist_id"])
    op.create_index("idx_track", "playlist_tracks", ["track_id"])
    op.create_index(
        "idx_sync_state", "playlist_tracks", ["in_tidal", "in_local", "in_rekordbox"]
    )

    # Step 3: Drop file_paths column (if using a database that supports it)
    # For SQLite, this would require recreating the tracks table
