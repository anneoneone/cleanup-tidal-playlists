# Intelligent Playlist Structure Update Behavior

## Overview

Updated `IntelligentPlaylistStructureService` to implement proper update behavior that:

- Compares existing Rekordbox structure with JSON configuration
- Only creates missing folders and playlists
- Updates existing playlists if needed
- Removes orphaned folders/playlists not in config
- Is idempotent (can be run multiple times without creating duplicates)

## Changes Made

### 1. Enhanced `sync_intelligent_playlist_structure()`

- Added tracking for removed items (folders and playlists)
- Now returns counts for: created, updated, removed folders and playlists
- Improved logging for better visibility

### 2. New Helper Method: `_scan_genre_folders()`

- Scans existing genre folders and their playlists
- Returns structured dictionary mapping genre names to folders and playlists
- Enables comparison with JSON configuration

### 3. Updated `_sync_genre_structure()`

**Before:**

- Always created new folders/playlists
- No comparison with existing structure
- Would create duplicates on subsequent runs

**After:**

- Scans existing genre folders first
- Compares with expected genres from JSON
- Removes orphaned genre folders not in config
- For each genre:
  - Creates missing playlists
  - Updates existing playlists
  - Removes orphaned playlists not in config
- Returns detailed counts of all operations

### 4. Updated `_sync_event_folders()`

**Before:**

- Always created event folders
- Returned list of folder names

**After:**

- Scans existing event folders first
- Compares with expected folders ("Partys", "Sets", "Radio Moafunk")
- Removes orphaned event folders not in list
- Only creates missing folders
- Returns dictionary with created/removed counts

### 5. Removed `cleanup_orphaned_folders()`

- Obsolete stub method with TODO
- Cleanup now integrated into sync methods

## Usage Example

```python
from pathlib import Path
from pyrekordbox import Rekordbox6Database
from tidal_cleanup.services.intelligent_playlist_structure_service import (
    IntelligentPlaylistStructureService,
)

# Setup
rekordbox_db = Path.home() / "Library/Pioneer/rekordbox/master.db"
mytag_mapping_path = Path("config/rekordbox_mytag_mapping.json")

with Rekordbox6Database(rekordbox_db) as db:
    service = IntelligentPlaylistStructureService(
        db=db,
        mytag_mapping_path=mytag_mapping_path
    )

    # Run sync (idempotent)
    results = service.sync_intelligent_playlist_structure()

    print(f"Genres: {results['genres_created']} created, "
          f"{results['genres_removed']} removed")
    print(f"Playlists: {results['playlists_created']} created, "
          f"{results['playlists_updated']} updated, "
          f"{results['playlists_removed']} removed")
```

## Testing

Use `scripts/test_update_behavior.py` to verify:

1. First run creates structure
2. Second run doesn't create duplicates (update behavior)
3. Structure matches JSON configuration

```bash
python scripts/test_update_behavior.py
```

## Benefits

1. **Idempotent Operations**: Can be run multiple times safely
2. **Configuration Sync**: Automatically reflects changes in JSON config
3. **Cleanup**: Removes outdated folders/playlists automatically
4. **Better Monitoring**: Detailed counts of all operations
5. **No Manual Cleanup**: Structure stays in sync with config

## Implementation Pattern

The update pattern follows these steps:

1. **Scan**: Query existing structure from Rekordbox
2. **Compare**: Identify differences with JSON config
3. **Sync**: Add missing items, update existing, remove orphaned
4. **Report**: Return detailed operation counts

This pattern is now consistently applied to:

- Genre folders and playlists
- Event folders
