# Database Quick Start Guide

## Overview

The Tidal Cleanup tool now includes a powerful database system to track and synchronize your playlists and tracks across Tidal, local MP3 files, and Rekordbox.

## Installation

The database feature is included by default. Install/update dependencies:

```bash
pip install -e .
# or
pip install sqlalchemy>=2.0.0
```

## Quick Start

### 1. Initialize Database

The database is automatically created when you first use database features:

```python
from tidal_cleanup.database import DatabaseService

db = DatabaseService()  # Creates ~/.tidal-cleanup/sync.db
db.init_db()           # Creates tables
```

### 2. Basic Operations

```python
# Create a track
track = db.create_track({
    "tidal_id": "123456789",
    "title": "Amazing Track",
    "artist": "Great Artist",
    "album": "Best Album",
    "year": 2024,
})

# Create a playlist
playlist = db.create_playlist({
    "tidal_id": "pl_abc123",
    "name": "My Playlist",
})

# Add track to playlist
db.add_track_to_playlist(
    playlist.id,
    track.id,
    position=1,
    in_tidal=True
)

# Get statistics
stats = db.get_statistics()
print(f"Tracks: {stats['tracks']}, Playlists: {stats['playlists']}")
```

### 3. Find Tracks

```python
# By Tidal ID
track = db.get_track_by_tidal_id("123456789")

# By file path
track = db.get_track_by_path("Playlists/House/track.mp3")

# By metadata
track = db.find_track_by_metadata("Track Title", "Artist Name")
```

## Configuration

### Database Location

**Default**: `~/.tidal-cleanup/sync.db`

**Custom location**:

```bash
export TIDAL_CLEANUP_DATABASE_PATH="/path/to/custom/sync.db"
```

## Key Features

- ✅ Track all playlists and tracks across sources
- ✅ Detect changes (new tracks, removed tracks, moved tracks)
- ✅ Smart duplicate detection
- ✅ Historical snapshots
- ✅ Sync operation tracking
- ✅ Fast lookups with indexes

## Documentation

For complete documentation, see:

- `docs/DATABASE_ARCHITECTURE.md` - Full architecture and design
- `docs/DATABASE_IMPLEMENTATION_SUMMARY.md` - Implementation details
- `tests/test_database.py` - Usage examples

## Next Steps

The database foundation is complete. Upcoming features:

- [ ] CLI commands for database inspection
- [ ] Automatic Tidal sync detection
- [ ] File system reconciliation
- [ ] Integration with existing services

## Support

For issues or questions, please open an issue on GitHub.

---

**Status**: ✅ Phase 1 Complete
**Version**: 1.0
**Date**: November 21, 2024
