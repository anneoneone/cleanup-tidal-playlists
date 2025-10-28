# Quick Start: Rekordbox Playlist Sync

## What This Does

Synchronizes MP3 playlist folders with Rekordbox database, automatically managing MyTags based on emojis in playlist names.

## Prerequisites

```bash
pip install pyrekordbox
```

## Quick Example

```python
from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = get_config()
service = RekordboxService(config)

# Sync a playlist
result = service.sync_playlist_with_mytags("Jazzz D 🎷💾")

print(f"Added: {result['tracks_added']}, Removed: {result['tracks_removed']}")
service.close()
```

## Playlist Name Format

`PLAYLIST NAME [GENRE or PARTY] [ENERGY] [STATUS]`

Example: `House Party 🎉⚡✅`

- Party: Party
- Energy: High Energy
- Status: Completed

## What It Does

1. ✅ Validates MP3 folder exists
2. ✅ Parses playlist name for emojis → MyTags
3. ✅ Creates/updates Rekordbox playlist
4. ✅ Adds missing tracks (+ MyTags)
5. ✅ Removes extra tracks (- MyTags)
6. ✅ Deletes empty playlists
7. ✅ Manages NoGenre tag automatically

## MyTag Groups

- **Genre**: 🎷 Jazz, 🎸 Rock, 🎹 Electronic, etc.
- **Party**: 🎉 Party, 🕺 Dance, 🪩 Disco, etc.
- **Energy**: ⚡ High Energy, ❄️ Cool/Chill, 🔥 Fire, etc.
- **Status**: 💾 Archived, 🆕 New, ✅ Completed, etc.

Edit `config/rekordbox_mytag_mapping.json` to add/modify emojis.

## Testing

```bash
# Interactive test menu
python tests/test_rekordbox_sync.py

# Or test specific components
python tests/test_rekordbox_sync.py parser  # Test name parser
python tests/test_rekordbox_sync.py mytag   # Test MyTag manager
python tests/test_rekordbox_sync.py sync    # List playlists
```

## CLI Examples

```bash
# List available playlists
python scripts/example_rekordbox_sync.py --list

# Sync one playlist
python scripts/example_rekordbox_sync.py "Jazzz D 🎷💾"

# Sync multiple playlists
python scripts/example_rekordbox_sync.py --batch "Playlist 1" "Playlist 2"
```

## Documentation

- 📖 **Full Documentation**: [`docs/REKORDBOX_SYNC.md`](docs/REKORDBOX_SYNC.md)
- 📝 **Refactoring Summary**: [`docs/REFACTORING_SUMMARY.md`](docs/REFACTORING_SUMMARY.md)

## Key Features

- ✨ Automatic MyTag creation from emojis
- 🔄 Bidirectional sync (MP3 ↔ Rekordbox)
- 🏷️ Multiple tags per track supported
- 🎯 Smart NoGenre fallback
- 🧹 Automatic empty playlist cleanup
- ⚡ Batch processing support
- 🛡️ Robust error handling

## Architecture

```
RekordboxService
  └─ RekordboxPlaylistSynchronizer
       ├─ PlaylistNameParser (emoji → MyTag mapping)
       └─ MyTagManager (create/link/unlink MyTags)
```

## Support

- See spike implementation: `spikes/spike_rekordbox_playlist_test.py`
- Run tests: `tests/test_rekordbox_sync.py`
- Check examples: `scripts/example_rekordbox_sync.py`
