# Model Changes for Unified Sync Architecture

## Summary

Based on your requirements for unified Tidal↔Filesystem sync with deduplication, here are the changes needed to the existing database models.

## Changes to Track Model

### Add Download State Fields

```python
# Add to Track model around line 85-95

# Download state
download_status: Mapped[str] = mapped_column(
    String(20),
    nullable=False,
    default='not_downloaded',
    index=True
)  # Enum: not_downloaded, downloading, downloaded, error

download_error: Mapped[Optional[str]] = mapped_column(
    Text,
    nullable=True
)  # Error message if download failed

downloaded_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime,
    nullable=True
)  # When file was successfully downloaded

last_verified_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime,
    nullable=True
)  # Last integrity verification
```

### Clarify file_path as Primary Location

The existing `file_path` field (line 86) should represent the **primary file location** (the actual audio file). All other occurrences are symlinks tracked in PlaylistTrack.

**No code change needed** - just update docstring:

```python
file_path: Mapped[Optional[str]] = mapped_column(
    String(1000), nullable=True, index=True
)  # Primary file location (actual audio data) - relative to MP3 directory
```

## Changes to Playlist Model

### Add Sync Status Fields

```python
# Add to Playlist model around line 190-195

# Sync state for unified Tidal↔Filesystem tracking
sync_status: Mapped[str] = mapped_column(
    String(20),
    nullable=False,
    default='unknown',
    index=True
)  # Enum: in_sync, needs_download, needs_update, needs_removal, unknown

last_updated_tidal: Mapped[Optional[datetime]] = mapped_column(
    DateTime,
    nullable=True
)  # When playlist was last modified in Tidal (from API)

last_synced_filesystem: Mapped[Optional[datetime]] = mapped_column(
    DateTime,
    nullable=True
)  # When we last synced this playlist to filesystem
```

### Update local_folder_path Docstring

The existing `local_folder_path` (line 175) should always follow pattern `mp3/Playlists/{playlist_name}/`:

```python
local_folder_path: Mapped[Optional[str]] = mapped_column(
    String(1000), nullable=True
)  # Filesystem location: always mp3/Playlists/{sanitized_name}/
```

## Changes to PlaylistTrack Model

### Add Deduplication & Symlink Fields

```python
# Add to PlaylistTrack model around line 240-250

# Deduplication and symlink tracking
is_primary: Mapped[bool] = mapped_column(
    Boolean,
    nullable=False,
    default=False
)  # True if this playlist has the primary file (actual audio data)

symlink_path: Mapped[Optional[str]] = mapped_column(
    String(1000),
    nullable=True
)  # Full path to symlink if is_primary=False

symlink_valid: Mapped[Optional[bool]] = mapped_column(
    Boolean,
    nullable=True
)  # False if symlink exists but target missing/broken

sync_status: Mapped[str] = mapped_column(
    String(20),
    nullable=False,
    default='unknown',
    index=True
)  # Enum: synced, needs_symlink, needs_move, needs_removal, unknown

synced_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime,
    nullable=True
)  # When this playlist-track relationship was last synced to filesystem
```

## Enum Definitions

Create enum classes for type safety (add to models.py):

```python
from enum import Enum

class DownloadStatus(str, Enum):
    """Track download status."""
    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    ERROR = "error"

class PlaylistSyncStatus(str, Enum):
    """Playlist sync status."""
    IN_SYNC = "in_sync"
    NEEDS_DOWNLOAD = "needs_download"
    NEEDS_UPDATE = "needs_update"
    NEEDS_REMOVAL = "needs_removal"
    UNKNOWN = "unknown"

class TrackSyncStatus(str, Enum):
    """PlaylistTrack sync status."""
    SYNCED = "synced"
    NEEDS_SYMLINK = "needs_symlink"
    NEEDS_MOVE = "needs_move"
    NEEDS_REMOVAL = "needs_removal"
    UNKNOWN = "unknown"
```

## Migration Script

After updating models, create Alembic migration:

```bash
# Generate migration
alembic revision --autogenerate -m "Add unified sync fields for deduplication"

# Review migration file in alembic/versions/
# Apply migration
alembic upgrade head
```

## Data Migration for Existing Databases

If you have existing data:

```python
# Migration script pseudocode
for track in db.query(Track).all():
    # Set initial download status based on file_path
    if track.file_path and Path(track.file_path).exists():
        track.download_status = DownloadStatus.DOWNLOADED
        track.downloaded_at = track.file_last_modified or datetime.utcnow()
    else:
        track.download_status = DownloadStatus.NOT_DOWNLOADED

for playlist in db.query(Playlist).all():
    # Set initial sync status
    if playlist.last_synced_at:
        playlist.sync_status = PlaylistSyncStatus.UNKNOWN  # Need to verify
        playlist.last_synced_filesystem = playlist.last_synced_at
    else:
        playlist.sync_status = PlaylistSyncStatus.NEEDS_DOWNLOAD

for playlist_track in db.query(PlaylistTrack).all():
    # Initially mark all as primary (dedupe logic will fix later)
    playlist_track.is_primary = True
    playlist_track.sync_status = TrackSyncStatus.UNKNOWN
```

## Benefits of These Changes

1. **Unified State Tracking**: Single database tracks both Tidal and filesystem
2. **Deduplication Support**: `is_primary` + `symlink_path` enable track sharing
3. **Precise Sync Status**: Know exactly what needs syncing at playlist and track level
4. **Error Tracking**: `download_error` helps debug download failures
5. **Audit Trail**: Timestamps for download, sync, verification
6. **Broken Symlink Detection**: `symlink_valid` flag

## Next Steps

1. Update models with these fields
2. Create Alembic migration
3. Update TidalSnapshotService to populate new fields
4. Create FilesystemScanService to scan `mp3/Playlists/*`
5. Create SyncDecisionEngine to compare states
6. Implement deduplication logic with symlink creation
7. Add CLI commands: `sync-check`, `sync-execute`, `sync-status`, `dedupe-report`

See `docs/UNIFIED_SYNC_ARCHITECTURE.md` for complete architecture details.
