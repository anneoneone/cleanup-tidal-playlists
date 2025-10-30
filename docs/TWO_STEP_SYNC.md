# Two-Step Rekordbox Sync Algorithm

This document describes the refactored two-step sync algorithm for synchronizing MP3 playlists with Rekordbox.

## Overview

The new sync algorithm separates structure creation from tag synchronization, providing a more systematic and maintainable approach.

### Step 1: Intelligent Playlist Structure

Creates and maintains the folder structure and intelligent playlists in Rekordbox based on `rekordbox_mytag_mapping.json`.

### Step 2: Track Tag Synchronization

Syncs track tags from MP3 playlist directories, applying proper MyTag combinations based on parsed metadata.

## Architecture

```
RekordboxService
  ├─ sync_all_with_two_step_algorithm()
  │
  ├─ Step 1: IntelligentPlaylistStructureService
  │   ├─ Creates "Genres" top-level directory
  │   ├─ Creates genre hierarchy (top-level → sub-genres)
  │   ├─ Creates intelligent playlists for each genre
  │   ├─ Creates "Events" top-level directory
  │   └─ Creates event subdirectories (Partys, Sets, Radio Moafunk)
  │
  └─ Step 2: TrackTagSyncService
      ├─ Iterates MP3 playlist directories
      ├─ Parses directory names for metadata
      ├─ Extracts tags with defaults
      ├─ Queries Rekordbox tracks with matching tags
      ├─ Compares MP3 vs Rekordbox
      └─ Adds/updates/removes tags accordingly
```

## Step 1: Intelligent Playlist Structure

### Genre Structure

Based on the nested structure in `rekordbox_mytag_mapping.json`:

```
Genres/
  ├─ House/
  │   ├─ House Progressive (intelligent playlist)
  │   ├─ House Ghetto (intelligent playlist)
  │   ├─ House Italo (intelligent playlist)
  │   ├─ House Groove (intelligent playlist)
  │   └─ ... (more sub-genres)
  │
  ├─ Deep House/
  │   ├─ House Chill (intelligent playlist)
  │   ├─ House LoFi (intelligent playlist)
  │   └─ ... (more sub-genres)
  │
  ├─ Techno/
  │   ├─ Techhouse (intelligent playlist)
  │   ├─ Techno (intelligent playlist)
  │   └─ ... (more sub-genres)
  │
  └─ ... (more top-level genres)
```

Each intelligent playlist is configured with a MyTag query:

- **Query**: `MyTag:Genre:{genre_name}`
- **Example**: Playlist "House Italo" shows all tracks with `Genre:House Italo` tag

### Event Structure

```
Events/
  ├─ Partys/
  ├─ Sets/
  └─ Radio Moafunk/
```

Event playlists will be created in Step 2 (future implementation).

### Implementation

```python
from tidal_cleanup.services.rekordbox_service import RekordboxService

service = RekordboxService(config)

# Execute Step 1 only
from tidal_cleanup.services.intelligent_playlist_structure_service import (
    IntelligentPlaylistStructureService,
)

structure_service = IntelligentPlaylistStructureService(
    db=service.db,
    mytag_mapping_path=Path("config/rekordbox_mytag_mapping.json"),
)

results = structure_service.sync_intelligent_playlist_structure()
```

## Step 2: Track Tag Synchronization

### Tag Extraction from Directory Names

Directory names are parsed to extract metadata with the following rules:

#### Track Metadata

- **Genre**: Extracted from emoji mapping (e.g., 🏃🏼‍♂️ → "House Progressive")
- **Status**: Extracted from emoji or defaults to "Archived"
  - 💾 → Archived (default)
  - ❓ → Recherche
  - 👵🏻 → Old
- **Energy**: Optional, extracted from emoji
  - ⬆️ → High
  - ↗️ → Up
  - ➡️ → Medium
  - ↘️ → Low
- **Source**: Defaults to "Tidal"
  - 🪴 → Tidal (default)
  - 💻 → External
  - 💿 → Discogs

#### Event Metadata

Currently skipped. Will be implemented later for:

- 🎉 → Party
- 🎶 → Set
- 🎙️ → Radio Moafunk

### Examples

| Directory Name | Genre | Energy | Status | Source | Event |
|---|---|---|---|---|---|
| `House Groove Low 🪇↘️💾` | House Groove | Low | Archived | Tidal | None |
| `Breaks 🧱❓` | Breaks | None | Recherche | Tidal | None |
| `House House ☀️` | House House | None | Archived | Tidal | None |
| `25-04-05 Brunchtime 🎙️` | None | None | None | Tidal | Radio Moafunk (skipped) |

### Sync Logic

For each MP3 playlist directory:

1. **Parse directory name** → Extract actual tags with defaults
2. **Query Rekordbox** → Get tracks with ALL actual tags (logical AND)
3. **Compare tracks**:
   - Only in MP3 → Add track or add tags if track exists
   - Only in Rekordbox → Remove tags if track has `Source:Tidal`
4. **Skip** event playlists (for now)

### Implementation

```python
from tidal_cleanup.services.track_tag_sync_service import TrackTagSyncService

track_sync_service = TrackTagSyncService(
    db=service.db,
    mp3_playlists_root=Path("/path/to/mp3/Playlists"),
    mytag_mapping_path=Path("config/rekordbox_mytag_mapping.json"),
)

# Sync all playlists
results = track_sync_service.sync_all_playlists()

# Or sync single playlist
result = track_sync_service.sync_playlist("House Groove Low 🪇↘️💾")
```

## Complete Two-Step Sync

### Command Line

```bash
# Execute complete two-step sync
tidal-cleanup rekordbox sync-all-two-step
```

### Python API

```python
from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = get_config()
service = RekordboxService(config)

# Execute both steps
results = service.sync_all_with_two_step_algorithm()

# Results structure
{
    "step1": {
        "genres_created": 5,
        "genres_updated": 0,
        "events_folders_created": 3,
        "total_playlists": 30
    },
    "step2": {
        "playlists_processed": 25,
        "tracks_added": 10,
        "tracks_updated": 5,
        "tracks_removed": 3,
        "skipped_playlists": 2
    }
}
```

### Test Script

```bash
python scripts/test_two_step_sync.py
```

## Configuration

### rekordbox_mytag_mapping.json

```json
{
  "Track-Metadata": {
    "Genre": {
      "House": {
        "🏃🏼‍♂️": "House Progressive",
        "🥊": "House Ghetto",
        "🇮🇹": "House Italo",
        ...
      },
      "Deep House": {
        "🧘🏼‍♂️": "House Chill",
        ...
      },
      ...
    },
    "Energy": {
      "⬆️": "High",
      "↗️": "Up",
      ...
    },
    "Status": {
      "💾": "Archived",
      "❓": "Recherche",
      ...
    }
  },
  "Event-Metadata": {
    "🎉": "Party",
    "🎶": "Set",
    "🎙️": "Radio Moafunk"
  },
  "Source": {
    "🪴": "Tidal",
    "💻": "External",
    "💿": "Discogs"
  }
}
```

## Differences from Old Sync

| Aspect | Old Sync | New Two-Step Sync |
|---|---|---|
| Structure | Created folders per playlist | Creates complete structure upfront |
| Playlists | Regular playlists | Intelligent playlists with MyTag queries |
| Organization | Flat or simple hierarchy | Nested genre hierarchy |
| Tags | Applied per playlist | Applied per track with defaults |
| Defaults | None | Status=Archived, Source=Tidal |
| Events | Mixed with genres | Separate Events directory |
| Maintenance | Manual per playlist | Systematic structure management |

## Future Enhancements

1. **Event Playlist Support**: Implement intelligent playlists for Partys, Sets, and Radio Moafunk
2. **Smart Playlist Queries**: Use actual Rekordbox SmartList XML format
3. **Track Import**: Implement actual track import for new files
4. **Cleanup**: Remove orphaned folders and playlists
5. **Validation**: Verify tag consistency across playlists
6. **Performance**: Optimize batch operations

## Migration from Old Sync

To migrate from the old sync approach:

1. **Backup**: Export your Rekordbox database
2. **Run Step 1**: Create the new structure
3. **Run Step 2**: Sync all track tags
4. **Verify**: Check that all tracks have correct tags
5. **Cleanup**: Optionally remove old flat playlists

## Troubleshooting

### Issue: Tracks not appearing in intelligent playlists

**Solution**: Verify that tracks have the correct MyTag applied. Use Rekordbox's tag browser to check.

### Issue: Duplicate genres

**Solution**: Check `rekordbox_mytag_mapping.json` for duplicate entries in the genre hierarchy.

### Issue: Event playlists being skipped

**Expected**: Event playlists are intentionally skipped in the current implementation.

## Support

For issues or questions:

1. Check the logs for detailed error messages
2. Review the configuration files
3. Run the test script to validate setup
4. Consult the main documentation

## See Also

- [REKORDBOX_SYNC.md](REKORDBOX_SYNC.md) - Original sync documentation
- [QUICKSTART_REKORDBOX_SYNC.md](QUICKSTART_REKORDBOX_SYNC.md) - Quick start guide
- [CONFIGURATION.md](CONFIGURATION.md) - Configuration reference
