# Rekordbox Playlist Synchronization with MyTag Management

## Overview

This refactored service provides comprehensive playlist synchronization between MP3 folders and the Rekordbox database, with intelligent MyTag management based on playlist names.

## Features

### 1. **Playlist Name Parsing**

Playlist names follow the pattern: `PLAYLIST NAME [GENRE-EMOJI] or [PARTY-EMOJI] [ENERGY-EMOJI] [STATUS-EMOJI]`

- **Required**: Either Genre emoji OR Party emoji must be present
- **Optional**: Energy and Status emojis
- **Supports Multiple Tags**: Tracks can have multiple MyTags, even from the same group

Example: `Jazzz D 🎷💾` → Genre: Jazz, Status: Archived

### 2. **Automatic MyTag Creation**

The service automatically creates and manages MyTag groups:

- **Genre**: Musical genres (Jazz, Rock, Electronic, etc.)
- **Party**: Party types (Party, Dance, VIP Party, etc.)
- **Energy**: Energy levels (High Energy, Cool/Chill, Relaxed, etc.)
- **Status**: Playlist status (Archived, New, Active, etc.)

### 3. **Bidirectional Synchronization**

#### Adding Tracks (MP3 → Rekordbox)

1. Adds track to Rekordbox collection (if not exists)
2. Adds track to playlist
3. Applies playlist-related MyTags
4. Removes NoGenre tag if Genre tags are added

#### Removing Tracks (Rekordbox → MP3)

1. Removes track from playlist
2. Removes playlist-related MyTags
3. Adds NoGenre tag if all Genre tags are removed

### 4. **Smart Cleanup**

- Automatically deletes playlists that become empty after synchronization
- Ensures tracks always have at least one Genre tag (NoGenre fallback)

## Architecture

### Core Components

1. **`MyTagManager`** (`mytag_manager.py`)
   - Creates/retrieves MyTag groups and values
   - Links/unlinks content to MyTags
   - Manages NoGenre tag logic
   - Queries MyTags for content

2. **`PlaylistNameParser`** (`playlist_name_parser.py`)
   - Parses playlist names
   - Extracts emojis
   - Maps emojis to MyTag groups and values
   - Uses configurable emoji mapping

3. **`RekordboxPlaylistSynchronizer`** (`rekordbox_playlist_sync.py`)
   - Orchestrates the sync workflow
   - Compares MP3 and Rekordbox tracks
   - Adds/removes tracks with MyTag management
   - Handles empty playlist cleanup

4. **`RekordboxService`** (`rekordbox_service.py`)
   - Main service interface
   - Provides `sync_playlist_with_mytags()` method
   - Manages database connection
   - Integrates all components

### Configuration

**`config/rekordbox_mytag_mapping.json`**

- Maps emojis to MyTag groups and values
- Easily extensible
- Supports multiple emojis per group

Example:

```json
{
  "emoji_to_mytag_mapping": {
    "Genre": {
      "🎷": "Jazz",
      "🎸": "Rock",
      "🎹": "Electronic"
    },
    "Party": {
      "🎉": "Party",
      "🕺": "Dance"
    },
    "Energy": {
      "⚡": "High Energy",
      "❄️": "Cool/Chill"
    },
    "Status": {
      "💾": "Archived",
      "🆕": "New"
    }
  }
}
```

## Usage

### Basic Usage

```python
from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService

# Initialize service
config = get_config()
service = RekordboxService(config)

# Sync a playlist
result = service.sync_playlist_with_mytags("Jazzz D 🎷💾")

# Check results
print(f"Tracks added: {result['tracks_added']}")
print(f"Tracks removed: {result['tracks_removed']}")
print(f"Playlist deleted: {result['playlist_deleted']}")
```

### Advanced Usage

```python
from pathlib import Path
from pyrekordbox import Rekordbox6Database
from tidal_cleanup.services.rekordbox_playlist_sync import RekordboxPlaylistSynchronizer

# Direct synchronizer usage
db = Rekordbox6Database()
synchronizer = RekordboxPlaylistSynchronizer(
    db=db,
    mp3_playlists_root=Path("/path/to/mp3/Playlists"),
    emoji_config_path=Path("/path/to/config.json")
)

# Perform sync
result = synchronizer.sync_playlist("House Party 🎉⚡")
db.close()
```

## Testing

Run the test suite:

```bash
# Interactive mode
python tests/test_rekordbox_sync.py

# Test specific components
python tests/test_rekordbox_sync.py parser  # Test name parser
python tests/test_rekordbox_sync.py mytag   # Test MyTag manager
python tests/test_rekordbox_sync.py sync    # List playlists
python tests/test_rekordbox_sync.py sync "Jazzz D 🎷💾"  # Sync specific playlist

# Run all tests
python tests/test_rekordbox_sync.py all
```

## Workflow Example

**Scenario**: Syncing playlist "House Party 🎉⚡✅"

1. **Parse Name**:
   - Clean name: "House Party"
   - Party: Party
   - Energy: High Energy
   - Status: Completed

2. **Validate MP3 Folder**:
   - Check `mp3/Playlists/House Party 🎉⚡✅/` exists
   - Scan for MP3 files

3. **Get/Create Playlist**:
   - Find or create "House Party 🎉⚡✅" in Rekordbox

4. **Compare Tracks**:
   - MP3: [track1.mp3, track2.mp3, track3.mp3]
   - Rekordbox: [track2.mp3, track4.mp3]
   - To Add: [track1.mp3, track3.mp3]
   - To Remove: [track4.mp3]

5. **Add Tracks**:
   - Add track1.mp3 and track3.mp3 to collection
   - Add to playlist
   - Apply MyTags: Party/Party, Energy/High Energy, Status/Completed

6. **Remove Tracks**:
   - Remove track4.mp3 from playlist
   - Remove MyTags: Party/Party, Energy/High Energy, Status/Completed
   - Check if Genre tags remain, add NoGenre if empty

7. **Cleanup**:
   - If playlist empty → delete playlist
   - Otherwise → commit changes

8. **Result**:

   ```json
   {
     "playlist_name": "House Party 🎉⚡✅",
     "mp3_tracks_count": 3,
     "rekordbox_tracks_before": 2,
     "tracks_added": 2,
     "tracks_removed": 1,
     "playlist_deleted": false,
     "final_track_count": 3
   }
   ```

## MyTag Management Rules

### Genre Tags

- Tracks must always have at least one Genre tag
- If all Genre tags are removed → automatically add NoGenre
- If Genre tags are added → automatically remove NoGenre

### Multiple Tags

- Tracks can have multiple tags from the same group
- Example: A track can be tagged with both "Jazz" and "Electronic"

### Tag Lifecycle

- MyTags are created on-demand when first needed
- MyTag groups are created before values
- Tags are preserved across multiple playlists
- Removing a track from one playlist doesn't affect its tags from other playlists

## Error Handling

The service handles various error conditions gracefully:

- **Missing MP3 Folder**: Raises `PlaylistSyncError`
- **Database Connection Failed**: Raises `RuntimeError`
- **Invalid Config**: Raises `RuntimeError`
- **Track Add Failures**: Logs error, continues with other tracks
- **Track Remove Failures**: Logs error, continues with other tracks

## Benefits of Refactored Design

1. **Separation of Concerns**: Each component has a single responsibility
2. **Testability**: Each component can be tested independently
3. **Maintainability**: Clear code structure, easy to extend
4. **Configurability**: Emoji mappings in JSON, easy to modify
5. **Robustness**: Comprehensive error handling
6. **Flexibility**: Supports multiple tags per group
7. **Intelligence**: Automatic NoGenre management

## Future Enhancements

Potential improvements:

- Batch processing for multiple playlists
- Conflict resolution strategies
- Tag inheritance/propagation
- Custom tag rules/logic
- Dry-run mode
- Undo/rollback capability
- Tag statistics and reporting
