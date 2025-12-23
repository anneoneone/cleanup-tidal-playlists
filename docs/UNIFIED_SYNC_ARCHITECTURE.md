# Unified Sync Architecture

## Overview

This document describes the unified sync architecture where the database maintains a single source of truth combining Tidal state and filesystem state, enabling efficient synchronization with automatic deduplication.

## Core Principles

1. **Tidal as Source of Truth**: Tidal playlists and tracks define what *should* exist
2. **Filesystem State Tracking**: Database tracks what *actually* exists locally
3. **Unified State Model**: Single set of tables tracks both Tidal and filesystem state
4. **Automatic Deduplication**: Tracks appearing in multiple playlists share one file with symlinks
5. **Deterministic Sync**: Compare Tidal vs filesystem to generate precise sync actions

## Database Schema

### Track Table

Represents tracks from Tidal with their download and filesystem state:

```python
class Track:
    # Tidal Identity
    tidal_id: str              # Unique Tidal track ID

    # Metadata (from Tidal API)
    title: str
    artist: str
    album: str
    duration: int
    isrc: str
    # ... (21+ metadata fields)

    # Download State
    download_status: str       # Enum: not_downloaded, downloading, downloaded, error
    download_error: str        # Error message if download failed

    # Filesystem Location
    primary_file_path: str     # Where actual file lives (first playlist to use it)
    file_hash: str            # SHA256 for integrity verification
    file_size: int            # File size in bytes

    # Timestamps
    tidal_updated_at: datetime # Last updated in Tidal
    downloaded_at: datetime    # When file was downloaded
    last_verified_at: datetime # Last integrity check
```

**Key Points**:

- Each track has ONE primary file location (the first playlist that needs it)
- Other playlists reference via symlinks
- `download_status` tracks whether file exists and is valid

### Playlist Table

Represents playlists from Tidal with sync state:

```python
class Playlist:
    # Tidal Identity
    tidal_id: str              # Unique Tidal playlist ID (UUID)

    # Metadata (from Tidal API)
    name: str                  # Playlist name
    description: str
    num_tracks: int
    duration: int
    # ... (17+ metadata fields)

    # Filesystem Location
    filesystem_path: str       # Always: mp3/Playlists/{name}/

    # Sync State
    sync_status: str          # Enum: in_sync, needs_download, needs_update, needs_removal
    last_updated_tidal: datetime    # Last modified in Tidal
    last_synced_filesystem: datetime  # Last sync to filesystem

    # Timestamps
    created_at: datetime
    updated_at: datetime
```

**Filesystem Path Pattern**:

- All playlists live in: `mp3/Playlists/{playlist_name}/`
- Playlist name sanitized for filesystem (remove special chars)
- If name changes in Tidal, files moved to new directory

### PlaylistTrack Junction Table

Represents track membership in playlists with symlink information:

```python
class PlaylistTrack:
    # Relationships
    playlist_id: int          # FK to Playlist
    track_id: int             # FK to Track

    # Position in Playlist
    position: int             # Track order (from Tidal)

    # Symlink State
    is_primary: bool          # True if this is the primary file location
    symlink_path: str         # Path to symlink (if not primary)
    symlink_valid: bool       # False if symlink broken

    # Sync State
    sync_status: str          # Enum: synced, needs_symlink, needs_move, needs_removal

    # Timestamps
    added_to_playlist_at: datetime  # When added to Tidal playlist
    synced_at: datetime             # When synced to filesystem
```

**Key Points**:

- `is_primary=True`: This playlist has the actual file (track.primary_file_path points here)
- `is_primary=False`: This playlist has a symlink to the primary file
- `symlink_path`: Full path to the symlink in this playlist's directory

## Sync Workflow

### 1. Fetch Tidal State

```python
# Pseudocode
for playlist in tidal_api.get_user_playlists():
    db_playlist = db.get_or_create_playlist(playlist.id)

    if playlist.last_updated > db_playlist.last_updated_tidal:
        # Playlist changed in Tidal
        db_playlist.update_metadata(playlist)
        db_playlist.sync_status = 'needs_update'

        for position, track in enumerate(playlist.tracks):
            db_track = db.get_or_create_track(track.id)
            db_track.update_metadata(track)

            db.add_playlist_track(
                playlist_id=db_playlist.id,
                track_id=db_track.id,
                position=position
            )
```

**Result**: Database now reflects current Tidal state with timestamps

### 2. Scan Filesystem State

```python
# Pseudocode
for playlist_dir in Path('mp3/Playlists').iterdir():
    db_playlist = db.get_playlist_by_filesystem_path(playlist_dir)

    for file_path in playlist_dir.glob('*.mp3'):
        # Check if file or symlink
        if file_path.is_symlink():
            target = file_path.resolve()
            # Find track by symlink
            db_track = db.get_track_by_file_path(target)
            if db_track:
                # Update symlink status
                playlist_track = db.get_playlist_track(db_playlist.id, db_track.id)
                playlist_track.symlink_path = str(file_path)
                playlist_track.symlink_valid = target.exists()
        else:
            # Primary file
            db_track = db.get_track_by_file_path(file_path)
            if db_track:
                db_track.download_status = 'downloaded'
                db_track.last_verified_at = datetime.now()
```

**Result**: Database knows which files/symlinks actually exist

### 3. Generate Sync Decisions

Compare Tidal state vs filesystem state:

```python
# Pseudocode
sync_plan = {
    'tracks_to_download': [],
    'symlinks_to_create': [],
    'files_to_move': [],
    'files_to_delete': [],
}

for playlist in db.get_playlists():
    for playlist_track in playlist.tracks:
        track = playlist_track.track

        # Determine if this should be primary location
        if track.primary_file_path is None:
            # First playlist to need this track
            playlist_track.is_primary = True
            track.primary_file_path = f"mp3/Playlists/{playlist.name}/{track.filename}"

            if track.download_status != 'downloaded':
                sync_plan['tracks_to_download'].append({
                    'track': track,
                    'destination': track.primary_file_path
                })
        else:
            # Track already has primary location
            playlist_track.is_primary = False
            symlink_path = f"mp3/Playlists/{playlist.name}/{track.filename}"

            if not Path(symlink_path).exists():
                sync_plan['symlinks_to_create'].append({
                    'target': track.primary_file_path,
                    'link': symlink_path,
                    'playlist_track': playlist_track
                })
```

**Result**: Precise list of actions needed to sync filesystem with Tidal

### 4. Execute Sync Plan

```python
# Download missing tracks
for item in sync_plan['tracks_to_download']:
    try:
        download_track(item['track'], item['destination'])
        item['track'].download_status = 'downloaded'
        item['track'].downloaded_at = datetime.now()
    except Exception as e:
        item['track'].download_status = 'error'
        item['track'].download_error = str(e)

# Create symlinks for duplicates
for item in sync_plan['symlinks_to_create']:
    target = Path(item['target'])
    link = Path(item['link'])
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target.resolve())

    item['playlist_track'].symlink_path = str(link)
    item['playlist_track'].symlink_valid = True
    item['playlist_track'].synced_at = datetime.now()
```

**Result**: Filesystem matches Tidal with deduplication via symlinks

## Deduplication Strategy

### Primary File Location

When a track appears in multiple playlists, the **first playlist** (alphabetically or by priority) gets the actual file:

```
mp3/Playlists/
├── Playlist A/
│   └── Artist - Title.mp3        ← Primary file (actual audio data)
├── Playlist B/
│   └── Artist - Title.mp3 → ../Playlist A/Artist - Title.mp3  ← Symlink
└── Playlist C/
    └── Artist - Title.mp3 → ../Playlist A/Artist - Title.mp3  ← Symlink
```

### Symlink Creation

All non-primary occurrences become symlinks:

```python
# Example
track = Track(title="Amazing Song", artist="Great Artist")
playlists = ["Deep House", "Favorites", "Road Trip"]

# Determine primary (first alphabetically)
primary_playlist = sorted(playlists)[0]  # "Deep House"

# Primary file
primary_path = "mp3/Playlists/Deep House/Great Artist - Amazing Song.mp3"
download(track, primary_path)

# Create symlinks in other playlists
for playlist in ["Favorites", "Road Trip"]:
    symlink_path = f"mp3/Playlists/{playlist}/Great Artist - Amazing Song.mp3"
    symlink_path.symlink_to("../Deep House/Great Artist - Amazing Song.mp3")
```

### Benefits

1. **Disk Space**: Only one copy of each track (important for large collections)
2. **Integrity**: Single file to verify/update
3. **Consistency**: All playlists see same file version
4. **Maintainability**: Easy to track which tracks are shared

## Sync Status Values

### Track.download_status

- `not_downloaded`: Track exists in Tidal but not downloaded
- `downloading`: Download in progress
- `downloaded`: File exists and verified
- `error`: Download failed or file corrupted

### Playlist.sync_status

- `in_sync`: Filesystem matches Tidal (all tracks present)
- `needs_download`: New playlist or has undownloaded tracks
- `needs_update`: Tracks added/removed/reordered in Tidal
- `needs_removal`: Playlist deleted from Tidal

### PlaylistTrack.sync_status

- `synced`: File or symlink exists and is valid
- `needs_symlink`: Symlink needs creation
- `needs_move`: File needs moving to different playlist
- `needs_removal`: Track removed from playlist in Tidal

## CLI Commands

### sync-check

Show what would change without making changes:

```bash
$ python -m tidal_cleanup sync-check

Sync Analysis:
==============
Tidal State: 15 playlists, 432 tracks
Filesystem State: 12 playlists, 387 tracks

Changes Required:
- 3 new playlists to create
- 45 tracks to download (2.3 GB)
- 12 symlinks to create (track deduplication)
- 5 tracks to remove (deleted from Tidal)

Deduplication Savings: 8 tracks shared across playlists (saved 67 MB)
```

### sync-execute

Perform the sync:

```bash
$ python -m tidal_cleanup sync-execute

Syncing Tidal → Filesystem:
===========================
✓ Fetched Tidal state (15 playlists, 432 tracks)
✓ Scanned filesystem (12 playlists, 387 tracks)
✓ Generated sync plan (45 downloads, 12 symlinks)

Downloading tracks:
[##########        ] 45/45 - Artist - Title.mp3 (2.3 GB)

Creating symlinks:
✓ Created 12 symlinks for duplicate tracks

Sync complete!
- Downloaded: 45 tracks (2.3 GB)
- Created: 12 symlinks (saved 67 MB)
- Updated: 3 playlists
```

### sync-status

Show current sync state:

```bash
$ python -m tidal_cleanup sync-status

Sync Status:
============
Playlists: 15 total
  - 12 in sync
  - 2 need update (tracks added in Tidal)
  - 1 need download (new playlist)

Tracks: 432 total
  - 387 downloaded
  - 45 not downloaded
  - 0 errors

Deduplication: 34 tracks shared across playlists
  - 102 symlinks (saved 876 MB)
```

### dedupe-report

Show which tracks are shared:

```bash
$ python -m tidal_cleanup dedupe-report

Track Deduplication Report:
===========================
34 tracks appear in multiple playlists:

"Artist - Popular Song.mp3" (87.2 MB)
  Primary: mp3/Playlists/Deep House/Artist - Popular Song.mp3
  Symlinks:
    - mp3/Playlists/Favorites/ →
    - mp3/Playlists/Road Trip/ →
    - mp3/Playlists/Summer Vibes/ →
  Saved: 261.6 MB

Total deduplication savings: 876 MB
```

## Migration Path

For existing codebases without unified sync:

1. **Run initial scan**: Populate database with current Tidal and filesystem state
2. **Deduplicate existing files**: Find duplicates, keep one, create symlinks
3. **First sync**: Validate everything is tracked correctly
4. **Regular syncs**: Use sync-check/sync-execute workflow

## Implementation Order

1. ✅ Database models (Track, Playlist, PlaylistTrack with new fields)
2. ✅ Tidal state fetcher (fetch and store current Tidal state)
3. ✅ Filesystem scanner (scan mp3/Playlists/* and update database)
4. Sync decision engine (compare states, generate plan)
5. Deduplication logic (determine primary files, plan symlinks)
6. Download orchestrator (execute sync plan)
7. CLI commands (sync-check, sync-execute, sync-status, dedupe-report)
8. Tests and documentation

## Edge Cases

### Playlist Renamed in Tidal

```python
# Old: mp3/Playlists/Deep House/
# New: mp3/Playlists/Deep House 2024/

# Solution: Move entire directory, update all database paths
```

### Track Removed from Primary Playlist

```python
# Track in: Playlist A (primary), Playlist B (symlink), Playlist C (symlink)
# User removes from Playlist A in Tidal

# Solution:
# 1. Pick new primary from remaining playlists (Playlist B)
# 2. Move file from A to B
# 3. Update symlinks in C to point to B
# 4. Remove file from A
```

### Symlink Broken

```python
# Symlink exists but target deleted/moved

# Detection: playlist_track.symlink_valid = False
# Solution: Re-create symlink to current primary_file_path
```

### Download Failed

```python
# Network error, API rate limit, etc.

# track.download_status = 'error'
# track.download_error = "Network timeout"

# Retry logic in sync-execute with exponential backoff
```

## Future Enhancements

1. **Smart primary selection**: Use most important/frequently used playlist
2. **Hardlink support**: For filesystems supporting hardlinks (same benefits as symlinks)
3. **Dry-run mode**: Show detailed file operations before executing
4. **Incremental sync**: Only process changed playlists (using timestamps)
5. **Conflict resolution**: Handle edge cases like renamed tracks with same ISRC
