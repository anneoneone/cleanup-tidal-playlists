# Rekordbox Database Structure & pyrekordbox Research

## Executive Summary

**Rekordbox 6/7** uses a SQLite database (`master.db`) as its primary data store. **pyrekordbox** provides Python bindings to directly read and modify this database. It also supports XML format for imports/exports.

---

## 1. Database Location

### macOS

```
~/Library/Pioneer/rekordbox/master.db
```

### Windows

```
C:\Users\<username>\AppData\Roaming\Pioneer\rekordbox\master.db
```

### Linux

```
~/.rekordbox/master.db
```

**Important**: The database is typically locked while Rekordbox is running. Syncing requires Rekordbox to be closed or running in a compatible mode.

---

## 2. Main Database Files & Structure

### Core Files

| File | Location | Format | Purpose | Modifiable by pyrekordbox |
|------|----------|--------|---------|--------------------------|
| **master.db** | `Library/Pioneer/rekordbox/` | SQLite 3 | Main Rekordbox database containing all tracks, playlists, metadata | ✅ **YES** |
| **rekordbox.xml** | Various locations | XML | Export/import format for backup and interchange | ✅ YES (via RekordboxXml class) |
| **.rekordbox-backup** | `Library/Pioneer/rekordbox/` | SQLite | Automatic backups (if enabled) | ⚠️ Read-only |

### Database Directory Structure

```
~/Library/Pioneer/rekordbox/
├── master.db                    # Main database
├── master.db-wal               # Write-Ahead Log (temp)
├── master.db-shm               # Shared Memory file (temp)
├── local.db                     # Local metadata (macOS specific)
├── cache/                       # Artwork & metadata cache
├── logs/                        # Application logs
└── share/                       # Shared database (if Cloud sync enabled)
```

---

## 3. Database Schema: Key Tables Modified by pyrekordbox

### Main Tables

#### **DjmdContent** (Tracks)

Contains all track metadata. **This is what gets modified when syncing**.

| Column | Type | Purpose |
|--------|------|---------|
| ID | TEXT | Unique content identifier (primary key) |
| Title | TEXT | Track title |
| Artist | Foreign Key → DjmdArtist | Artist reference |
| Album | Foreign Key → DjmdAlbum | Album reference |
| Genre | Foreign Key → DjmdGenre | Genre reference |
| FolderPath | TEXT | Absolute file path to MP3 |
| FileSize | INTEGER | File size in bytes |
| BPM | INTEGER | Beats per minute (stored as integer × 100) |
| TrackNo | INTEGER | Track number on album |
| DiscNo | INTEGER | Disc number |
| Rating | INTEGER | User rating (0-5) |
| DJPlayCount | INTEGER | Play count in DJ sets |
| DateAdded | TIMESTAMP | When added to Rekordbox |
| Commnt | TEXT | Comments/notes |
| ISRC | TEXT | International Standard Recording Code |

**pyrekordbox method**: `db.add_content(track_path, **metadata)`, `db.get_content()`, `db.delete(content)`

#### **DjmdPlaylist** (Playlists/Folders)

Stores playlist and folder structure.

| Column | Type | Purpose |
|--------|------|---------|
| ID | TEXT | Unique playlist ID |
| Name | TEXT | Playlist name |
| Attribute | INTEGER | 0=Playlist, 1=Folder, 4=Smart Playlist |
| ParentID | TEXT | Parent folder ID (for hierarchy) |
| Seq | INTEGER | Sort sequence |
| Songs | Relationship → DjmdSong | Tracks in this playlist |

**pyrekordbox method**: `db.create_playlist(name, attribute=0)`, `db.get_playlist()`, `playlist.Songs.append(track)`

#### **DjmdSong** (Playlist-Track Relationships)

Junction table linking tracks to playlists.

| Column | Type | Purpose |
|--------|------|---------|
| ID | TEXT | Unique link ID |
| PlaylistID | TEXT | Playlist FK |
| ContentID | TEXT | Track/Content FK |
| TrackNo | INTEGER | Position in playlist |

**pyrekordbox method**: Auto-managed when adding tracks to playlists

#### **DjmdMyTag** (Custom Tags/Categories)

Stores user-defined tags (My Tags) and groupings.

| Column | Type | Purpose |
|--------|------|---------|
| ID | TEXT | Tag ID |
| Name | TEXT | Tag name (e.g., "Jazz", "High Energy") |
| Attribute | INTEGER | 1=Group/Folder, 0=Tag Value |
| ParentID | TEXT | Parent group ID ("root" for top-level) |
| Seq | INTEGER | Display order |

**pyrekordbox method**: `db.query(db6.DjmdMyTag)`, `db.add(tag_object)`, `db.flush()`

#### **DjmdSongMyTag** (Track-Tag Links)

Junction table linking tracks to My Tags.

| Column | Type | Purpose |
|--------|------|---------|
| ID | TEXT | Link ID |
| ContentID | TEXT | Track/Content FK |
| MyTagID | TEXT | MyTag FK |
| TrackNo | INTEGER | Sequence position |

**pyrekordbox method**: `db.query(db6.DjmdSongMyTag)`, create and `db.add()` new links

#### **DjmdArtist, DjmdAlbum, DjmdGenre** (Lookups)

Master lookup tables for artists, albums, genres.

---

## 4. What pyrekordbox Modifies When Syncing

### Direct Modifications

When this project syncs playlists:

1. **Add Track to Database**
   - ✅ Inserts new row in `DjmdContent` with metadata
   - ✅ Updates `DateAdded` timestamp
   - ✅ Creates or updates artist/album/genre lookups

2. **Add Track to Playlist**
   - ✅ Creates `DjmdSong` relationship
   - ✅ Updates playlist track count

3. **Apply MyTags**
   - ✅ Creates `DjmdMyTag` groups if they don't exist
   - ✅ Creates/retrieves `DjmdMyTag` values (e.g., "Jazz", "High Energy")
   - ✅ Links tracks via `DjmdSongMyTag`

4. **Remove Track from Playlist**
   - ✅ Deletes corresponding `DjmdSong` entry
   - ✅ Cleans up empty playlists
   - ✅ Manages MyTag cleanup (removes NoGenre if needed)

### What Is NOT Modified

- ❌ Play counts (`DJPlayCount`) - preserved
- ❌ Ratings - preserved
- ❌ User comments - preserved (unless explicitly overwritten)
- ❌ Other system tables
- ❌ Rekordbox configuration/settings

---

## 5. XML Format Support

### RekordboxXml Class

pyrekordbox also supports XML format for import/export:

```
File: *.xml (custom location)
Format: Rekordbox 6.0+ XML format
Root Element: <DJ_PLAYLISTS>
Encoding: UTF-8
```

**Key XML Elements**:

- `<PRODUCT>` - Rekordbox metadata
- `<COLLECTION>` - Tracks database
- `<PLAYLISTS>` - Playlist tree structure
- `<TRACK>` - Individual track data

**pyrekordbox method**: `RekordboxXml(filepath)` for reading, `xml.save()` for writing

**Use case**: Easier for backup/export but slower than direct database access.

---

## 6. Metadata & Config Files for Backup

### Critical Files (MUST BACKUP)

| Path | Format | Contents | Importance |
|------|--------|----------|-----------|
| `master.db` | SQLite | **All tracks, playlists, metadata** | 🔴 **CRITICAL** |
| `master.db-wal` | SQLite | Transaction log (temporary, auto-deleted) | 🟡 Keep with DB |
| `master.db-shm` | SQLite | Shared memory file (temporary) | 🟡 Keep with DB |

### Important Metadata (SHOULD BACKUP)

| Path | Format | Contents | Importance |
|------|--------|----------|-----------|
| `local.db` (macOS) | SQLite | Local sync settings, ratings, play counts | 🟠 **HIGH** |
| `Library/Pioneer/rekordbox/` (full dir) | Mixed | Complete Rekordbox state | 🟠 **HIGH** |
| `~/Music/rekordbox` (custom paths) | Audio | Actual music files referenced by DB | 🟠 **HIGH** |

### Optional for Recovery

| Path | Format | Contents | Importance |
|------|--------|----------|-----------|
| `cache/` | Binary | Artwork cache (can be regenerated) | 🟡 Optional |
| `logs/` | Text | Application logs | 🟡 Optional |

### Backup Strategy

**Recommended Backup Structure**:

```
backup/
├── master.db                    # Database
├── local.db                      # (macOS) Metadata
├── rekordbox.xml                 # Full export (human-readable)
├── rekordbox_pytag_config.json   # Custom tag mappings
└── mp3-playlists/               # Your actual MP3 files
    ├── Playlist 1/
    ├── Playlist 2/
    └── ...
```

**Backup Frequency**: Before major sync operations, daily for production

---

## 7. Key Integration Points in This Project

### From Project Code Analysis

**Files Using pyrekordbox**:

- [src/tidal_cleanup/core/rekordbox/service.py](../src/tidal_cleanup/core/rekordbox/service.py) - Main Rekordbox service
- [src/tidal_cleanup/core/rekordbox/snapshot_service.py](../src/tidal_cleanup/core/rekordbox/snapshot_service.py) - Playlist sync
- [spikes/spike_rekordbox_playlist_test.py](../spikes/spike_rekordbox_playlist_test.py) - MyTag management examples

**Key Operations**:

1. **Connect**: `Rekordbox6Database()` - Auto-detects default location
2. **Query**: `db.get_content()`, `db.get_playlist()`, `db.query(db6.DjmdMyTag)`
3. **Add Tracks**: `db.add_content(path, **metadata)`
4. **Create Playlists**: `db.create_playlist(name)`
5. **Manage Tags**: Create `DjmdMyTag` entries, link via `DjmdSongMyTag`
6. **Commit**: `db.commit()` or use context manager

**Configuration**:

- [config/rekordbox_mytag_mapping.json](../config/rekordbox_mytag_mapping.json) - Emoji→MyTag mapping

---

## 8. Database Queries: Common Operations

### Track Management

```python
from pyrekordbox import Rekordbox6Database, db6

db = Rekordbox6Database()

# Get all tracks
all_tracks = db.get_content().all()

# Find specific track by path
track = db.get_content(FolderPath="/path/to/file.mp3").first()

# Add new track with metadata
new_content = db.add_content(
    "/path/to/file.mp3",
    Title="Song Title",
    TrackNo=1,
    Commnt="Added via sync"
)

# Get track by ID
track = db.query(db6.DjmdContent).filter(
    db6.DjmdContent.ID == "track_id"
).first()
```

### Playlist Management

```python
# Get all playlists
playlists = db.get_playlist().all()

# Find playlist by name
playlist = db.query(db6.DjmdPlaylist).filter(
    db6.DjmdPlaylist.Name == "Playlist Name"
).first()

# Get playlists only (not folders)
regular_playlists = db.query(db6.DjmdPlaylist).filter(
    db6.DjmdPlaylist.Attribute == 0
).all()

# Get tracks in a playlist
if playlist:
    tracks = playlist.Songs  # Relationship attribute
```

### MyTag Management

```python
# Get all tag groups
groups = db.query(db6.DjmdMyTag).filter(
    db6.DjmdMyTag.Attribute == 1,  # Groups/Folders
    db6.DjmdMyTag.ParentID == "root"
).all()

# Get tags within a group
tags = db.query(db6.DjmdMyTag).filter(
    db6.DjmdMyTag.Attribute == 0,  # Tag values
    db6.DjmdMyTag.ParentID == group.ID
).all()

# Find track's tags
content_tags = db.query(db6.DjmdSongMyTag).filter(
    db6.DjmdSongMyTag.ContentID == track.ID
).all()

# Create new tag (must have proper ID, Seq, and ParentID)
new_tag = db6.DjmdMyTag(
    ID=db.generate_unused_id(db6.DjmdMyTag),
    Name="New Tag",
    Attribute=0,
    ParentID=parent_group.ID,
    Seq=max_seq + 1
)
db.add(new_tag)
db.flush()
```

---

## 9. Critical Considerations for Safe Syncing

### Before Syncing

1. ✅ **Close Rekordbox** - Database must not be locked
2. ✅ **Backup `master.db`** - Create safety copy
3. ✅ **Verify Database Integrity** - Run Rekordbox integrity check if available
4. ✅ **Check Disk Space** - Ensure room for temporary files

### During Sync

1. ✅ **Use Transactions** - `db.commit()` only after validation
2. ✅ **Validate Data** - Check metadata before inserting
3. ✅ **Generate IDs Properly** - Use `db.generate_unused_id()`
4. ✅ **Maintain Referential Integrity** - Parent IDs must exist before creating children

### After Sync

1. ✅ **Commit Changes** - Call `db.commit()`
2. ✅ **Close Connection** - `db.close()` or use context manager
3. ✅ **Test in Rekordbox** - Open and verify playlists
4. ✅ **Keep Backup** - Archive backup of pre-sync database

---

## 10. File Paths & Conventions

### Rekordbox Database Paths by OS

**macOS**: `~/Library/Pioneer/rekordbox/master.db`
**Windows**: `C:\Users\<user>\AppData\Roaming\Pioneer\rekordbox\master.db`
**Linux**: `~/.rekordbox/master.db`

### Project Config Paths

**Main DB Config**: `config/rekordbox_mytag_mapping.json`
**Backup Location**: `config/` or user-specified

### Track Reference Format

In `DjmdContent.FolderPath`:

- Stored as **absolute paths**
- Example: `/Volumes/HDD1TB/Music/Tidal/mp3/Playlists/Jazz/Track.mp3`
- Updating requires careful path validation

---

## Summary Table: File Criticality

| File | Format | Critical | Recoverable | Sync Impact |
|------|--------|----------|-------------|------------|
| master.db | SQLite | 🔴 YES | ❌ NO | Primary |
| local.db | SQLite | 🟠 HIGH | 🟡 Partial | Secondary |
| Playlist folders | MP3 | 🔴 YES | ❌ NO | Data source |
| rekordbox.xml | XML | 🟠 Backup only | ✅ YES | Import/export |
| Cache files | Binary | ⚪ NO | ✅ YES | UI only |
| Logs | Text | ⚪ NO | ✅ YES | Debug only |

---

## References

- **pyrekordbox Documentation**: <https://pyrekordbox.readthedocs.io/>
- **Project Code**: `src/tidal_cleanup/core/rekordbox/`
- **Spike Scripts**: `spikes/spike_rekordbox_playlist_test.py`
- **Related Docs**: [REKORDBOX_SYNC.md](REKORDBOX_SYNC.md), [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md)
