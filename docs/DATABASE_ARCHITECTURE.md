# Database Architecture for Playlist & Track Sync

## Executive Summary

This document outlines the architecture for implementing a database system to track and synchronize playlists and tracks across three sources:

- **Tidal** (source of truth)
- **Local MP3 files** (downloaded audio files)
- **Rekordbox database** (DJ software library)

## 1. Database Technology Selection

### Recommendation: **SQLite**

**Rationale:**

- ✅ **Zero-configuration**: No separate database server required
- ✅ **Portability**: Single file database, easy to backup and share
- ✅ **Performance**: More than adequate for ~10,000-100,000 tracks
- ✅ **Reliability**: ACID-compliant, battle-tested
- ✅ **Python integration**: Excellent SQLAlchemy support
- ✅ **Lightweight**: Minimal dependencies, no memory overhead
- ✅ **Perfect for desktop applications**: Designed for local data storage

**When to consider PostgreSQL instead:**

- Multiple users need concurrent access
- Dataset grows beyond 1M tracks
- Need for advanced features (full-text search, JSON operations)
- Remote database access required

**Database Location:** `~/.tidal-cleanup/sync.db` or configurable via environment variable

---

## 2. Database Schema Design

### 2.1 Core Tables

#### **tracks** - Central track registry

```sql
CREATE TABLE tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Tidal identifiers
    tidal_id TEXT UNIQUE,  -- Tidal's track ID (can be NULL for local-only tracks)

    -- Track metadata
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT,
    year INTEGER,
    genre TEXT,
    duration_seconds INTEGER,
    isrc TEXT,  -- International Standard Recording Code

    -- Computed fields for matching
    normalized_name TEXT NOT NULL,  -- For fuzzy matching

    -- File information
    file_path TEXT,  -- Relative to MP3 directory
    file_size_bytes INTEGER,
    file_format TEXT,
    file_hash TEXT,  -- SHA256 hash for change detection
    file_last_modified TIMESTAMP,

    -- Rekordbox integration
    rekordbox_content_id TEXT,  -- pyrekordbox Content ID

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_in_tidal TIMESTAMP,

    -- Indexes
    INDEX idx_tidal_id (tidal_id),
    INDEX idx_normalized_name (normalized_name),
    INDEX idx_file_path (file_path),
    INDEX idx_artist_title (artist, title)
);
```

#### **playlists** - Playlist registry

```sql
CREATE TABLE playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Tidal identifiers
    tidal_id TEXT UNIQUE NOT NULL,

    -- Playlist metadata
    name TEXT NOT NULL,
    description TEXT,

    -- Local mapping
    local_folder_path TEXT,  -- Relative to MP3/Playlists directory

    -- Rekordbox integration
    rekordbox_playlist_id TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_synced_at TIMESTAMP,
    last_seen_in_tidal TIMESTAMP,

    -- Metadata
    track_count_tidal INTEGER DEFAULT 0,
    track_count_local INTEGER DEFAULT 0,
    track_count_rekordbox INTEGER DEFAULT 0,

    INDEX idx_tidal_id (tidal_id),
    INDEX idx_name (name)
);
```

#### **playlist_tracks** - Many-to-many relationship

```sql
CREATE TABLE playlist_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    playlist_id INTEGER NOT NULL,
    track_id INTEGER NOT NULL,

    -- Ordering and metadata
    position INTEGER,  -- Track position in playlist (Tidal order)

    -- Source tracking
    in_tidal BOOLEAN DEFAULT FALSE,
    in_local BOOLEAN DEFAULT FALSE,
    in_rekordbox BOOLEAN DEFAULT FALSE,

    -- Timestamps
    added_to_tidal TIMESTAMP,
    added_to_local TIMESTAMP,
    added_to_rekordbox TIMESTAMP,
    removed_from_tidal TIMESTAMP,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE,

    UNIQUE(playlist_id, track_id),
    INDEX idx_playlist (playlist_id),
    INDEX idx_track (track_id),
    INDEX idx_sync_state (in_tidal, in_local, in_rekordbox)
);
```

#### **sync_operations** - Sync history and pending operations

```sql
CREATE TABLE sync_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    operation_type TEXT NOT NULL,  -- 'snapshot', 'download', 'sync_rekordbox', 'cleanup'
    status TEXT NOT NULL,  -- 'pending', 'running', 'completed', 'failed'

    -- Target information
    playlist_id INTEGER,
    track_id INTEGER,

    -- Operation details
    action TEXT,  -- 'add', 'remove', 'update', 'move'
    source TEXT,  -- 'tidal', 'local', 'rekordbox'
    target TEXT,  -- 'tidal', 'local', 'rekordbox'

    -- Results
    details TEXT,  -- JSON with operation details
    error_message TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE,

    INDEX idx_status (status),
    INDEX idx_operation_type (operation_type),
    INDEX idx_created_at (created_at)
);
```

#### **sync_snapshots** - Point-in-time state captures

```sql
CREATE TABLE sync_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    snapshot_type TEXT NOT NULL,  -- 'tidal', 'local', 'rekordbox'
    snapshot_data TEXT NOT NULL,  -- JSON dump of state

    -- Statistics
    playlist_count INTEGER,
    track_count INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_type_created (snapshot_type, created_at)
);
```

### 2.2 Entity Relationships

```
playlists (1) ←→ (N) playlist_tracks (N) ←→ (1) tracks
    ↓                                            ↓
sync_operations                          sync_operations
    ↓                                            ↓
sync_snapshots                           (file system)
                                                 ↓
                                          Rekordbox DB
```

---

## 3. Sync Workflow Design

### 3.1 Core Concepts

**Source of Truth Hierarchy:**

1. **Tidal** - Primary source (user's curated playlists)
2. **Database** - Current known state
3. **Local Files** - Physical audio files
4. **Rekordbox** - DJ library (receives updates)

### 3.2 Change Detection Algorithm

```python
def detect_changes():
    """
    1. Fetch current Tidal state (all playlists + tracks)
    2. Load last known state from database
    3. Compare and identify:
       - New playlists
       - Deleted playlists
       - New tracks in existing playlists
       - Tracks removed from playlists
       - Tracks moved between playlists
       - Playlist metadata changes (name, description)
    4. Update database with new state
    5. Mark operations as 'pending'
    """
```

**Change Types:**

- `PLAYLIST_ADDED` - New playlist in Tidal
- `PLAYLIST_REMOVED` - Playlist deleted from Tidal
- `TRACK_ADDED_TO_PLAYLIST` - Track added to playlist
- `TRACK_REMOVED_FROM_PLAYLIST` - Track removed from playlist
- `TRACK_MOVED` - Track appears in different playlist (or additional playlist)
- `TRACK_METADATA_CHANGED` - Track info updated
- `PLAYLIST_RENAMED` - Playlist name changed

### 3.3 Sync Decision Engine

```python
def generate_sync_decisions(changes):
    """
    For each change, determine required actions:

    PLAYLIST_ADDED:
      → Download all tracks via tidal-dl-ng
      → Create local directory structure
      → Add to database

    PLAYLIST_REMOVED:
      → Mark as deleted in database (soft delete)
      → Optionally: cleanup local files
      → Optionally: remove from Rekordbox

    TRACK_ADDED_TO_PLAYLIST:
      → Download track if not in library
      → Update database
      → Queue for Rekordbox sync

    TRACK_REMOVED_FROM_PLAYLIST:
      → Update playlist_tracks.in_tidal = FALSE
      → Optionally: remove from local if not in other playlists
      → Queue Rekordbox MyTag update

    TRACK_MOVED:
      → Update playlist_tracks for both playlists
      → May require file move/copy
      → Update Rekordbox playlists
    """
```

### 3.4 File System Reconciliation

```python
def reconcile_local_files():
    """
    Scan MP3 directory and reconcile with database:

    1. For each file in MP3/Playlists/*:
       - Check if exists in database (by path or metadata)
       - If not: Add as 'local-only' track
       - If yes: Verify file hash, update last_modified

    2. For each track in database with file_path:
       - Check if file exists
       - If not: Mark as 'missing', trigger re-download decision

    3. Identify orphaned files (in filesystem but not in any Tidal playlist)
       - Provide cleanup report
    """
```

---

## 4. Service Layer Architecture

### 4.1 DatabaseService

**Responsibilities:**

- CRUD operations for all entities
- Transaction management
- Query optimization
- Data integrity enforcement

**Key Methods:**

```python
class DatabaseService:
    # Track operations
    def get_track_by_tidal_id(tidal_id: str) -> Optional[Track]
    def get_track_by_path(file_path: Path) -> Optional[Track]
    def create_or_update_track(track_data: dict) -> Track
    def find_track_by_metadata(title: str, artist: str) -> Optional[Track]

    # Playlist operations
    def get_playlist_by_tidal_id(tidal_id: str) -> Optional[Playlist]
    def get_all_playlists() -> List[Playlist]
    def create_or_update_playlist(playlist_data: dict) -> Playlist

    # Playlist-Track relationships
    def add_track_to_playlist(playlist_id: int, track_id: int, position: int)
    def remove_track_from_playlist(playlist_id: int, track_id: int)
    def get_playlist_tracks(playlist_id: int) -> List[Track]
    def get_track_playlists(track_id: int) -> List[Playlist]

    # Sync state
    def get_pending_operations() -> List[SyncOperation]
    def mark_operation_complete(operation_id: int)
    def create_snapshot(snapshot_type: str, data: dict)
```

### 4.2 SyncStateService

**Responsibilities:**

- Detect changes between Tidal and database
- Generate sync decisions
- Track sync progress
- Provide sync statistics

**Key Methods:**

```python
class SyncStateService:
    def capture_tidal_snapshot() -> dict
    def detect_changes() -> List[Change]
    def generate_sync_plan(changes: List[Change]) -> SyncPlan
    def execute_sync_plan(plan: SyncPlan) -> SyncResult
    def get_sync_status() -> SyncStatus
    def get_playlists_needing_download() -> List[Playlist]
```

### 4.3 Integration with Existing Services

**TidalApiService Enhancement:**

```python
# Add database awareness
def get_playlist_tracks(playlist_id: str):
    # 1. Fetch from Tidal API
    # 2. Update database with current state
    # 3. Return tracks
```

**FileService Enhancement:**

```python
# Add database tracking
def convert_audio(source, target):
    # 1. Perform conversion
    # 2. Update database with file info (path, hash, size)
    # 3. Return result
```

**RekordboxService Enhancement:**

```python
# Sync with database state
def sync_playlist_with_mytags(playlist_name: str):
    # 1. Load playlist from database
    # 2. Sync with Rekordbox
    # 3. Update database sync state
```

---

## 5. Implementation Phases

### Phase 1: Database Foundation ✓

- ✅ Select SQLite as database technology
- ⏳ Set up SQLAlchemy models
- ⏳ Create database initialization script
- ⏳ Implement DatabaseService with basic CRUD

### Phase 2: State Tracking

- ⏳ Implement snapshot capture from Tidal
- ⏳ Build change detection algorithm
- ⏳ Create sync operation tracking
- ⏳ Add file system reconciliation

### Phase 3: Integration

- ⏳ Update TidalApiService to use database
- ⏳ Update FileService to track files in database
- ⏳ Update RekordboxService to sync via database
- ⏳ Maintain backward compatibility

### Phase 4: CLI & User Experience

- ⏳ Add `db init` command
- ⏳ Add `db status` command (show sync state)
- ⏳ Add `db sync` command (detect changes, show decisions)
- ⏳ Add `db reconcile` command (scan local files)
- ⏳ Add reporting and statistics

### Phase 5: Testing & Documentation

- ⏳ Unit tests for database operations
- ⏳ Integration tests for sync workflow
- ⏳ User documentation
- ⏳ Migration guide

---

## 6. Key Benefits

### For Your Use Case

1. **Change Detection**
   - Instantly see which playlists have new tracks
   - Track when tracks were added/removed
   - Historical record of playlist evolution

2. **Smart Downloads**
   - Only download what's new or changed
   - Skip tracks already in library
   - Efficient bandwidth usage

3. **Orphan Detection**
   - Find local files not in any Tidal playlist
   - Clean up removed tracks
   - Maintain disk space

4. **Multi-Playlist Tracking**
   - Know which playlists contain a track
   - Prevent duplicate downloads
   - Smart cleanup (only delete if not in other playlists)

5. **Sync State Visibility**
   - See what's pending sync
   - Track sync history
   - Troubleshoot sync issues

6. **Rekordbox Integration**
   - Coordinate updates to Rekordbox
   - Track MyTag assignments
   - Ensure consistency

---

## 7. Example Workflows

### Workflow 1: Daily Sync Check

```bash
# Check for changes
$ tidal-cleanup db sync --check

📊 Sync Status
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Playlists: 45 tracked
Tracks: 2,347 tracked

Changes detected:
  ✨ 3 new tracks in "House Italo R 🇮🇹"
  ✨ 2 new tracks in "Minimal Deep 💎"
  ❌ 1 track removed from "Party Mix 🎉"

Recommended actions:
  → Download "House Italo R 🇮🇹" (3 new tracks)
  → Download "Minimal Deep 💎" (2 new tracks)
  → Review removed tracks

$ tidal-cleanup download --playlist "House Italo R 🇮🇹"
```

### Workflow 2: Find Missing Files

```bash
$ tidal-cleanup db reconcile

🔍 Reconciling local files with database...

Found issues:
  ⚠️  15 tracks in database but missing from filesystem
  ⚠️  3 orphaned files (not in any Tidal playlist)

Missing tracks:
  • Artist - Track 1 (from playlist "Deep House")
  • Artist - Track 2 (from playlist "Techno Mix")
  ...

Orphaned files:
  • /path/to/old_track.mp3

Actions:
  [1] Re-download missing tracks
  [2] Remove orphaned files
  [3] Show detailed report
```

### Workflow 3: Playlist Analysis

```bash
$ tidal-cleanup db inspect --playlist "House Italo R 🇮🇹"

📋 Playlist: House Italo R 🇮🇹
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tidal ID: abc123xyz
Created: 2024-01-15
Last synced: 2024-11-20 14:30

Tracks: 45
  • In Tidal: 45
  • Downloaded: 43
  • In Rekordbox: 43
  • Missing: 2

Recent changes:
  [2024-11-20] Added: "Artist - New Track"
  [2024-11-18] Removed: "Artist - Old Track"
  [2024-11-15] Added: "Artist - Another Track"
```

---

## 8. Configuration

### Database Settings in Config

```python
# config/.env
TIDAL_CLEANUP_DB_PATH=~/.tidal-cleanup/sync.db
TIDAL_CLEANUP_DB_BACKUP_DIR=~/.tidal-cleanup/backups
TIDAL_CLEANUP_DB_AUTO_BACKUP=true
```

### CLI Environment Variables

```bash
export TIDAL_CLEANUP_DB_PATH="/custom/path/sync.db"
export TIDAL_CLEANUP_LOG_SQL=false  # Log SQL queries
```

---

## 9. Migration Strategy

For existing users without database:

1. **Initial Setup**
   - Create database with schema
   - Scan existing MP3 files
   - Import into database as baseline

2. **Tidal Sync**
   - Fetch current Tidal state
   - Match with imported files
   - Fill in Tidal IDs and metadata

3. **Rekordbox Link**
   - Scan Rekordbox database
   - Link tracks by file path
   - Store Rekordbox IDs

4. **Verification**
   - Show import statistics
   - Highlight any issues
   - Provide cleanup suggestions

---

## 10. Future Enhancements

- **Web UI**: View sync status in browser
- **Automatic sync**: Background daemon for auto-sync
- **Conflict resolution**: Handle edge cases (duplicate tracks, etc.)
- **Export/Import**: Share database between computers
- **Analytics**: Track listening patterns, playlist evolution
- **Multi-user**: Support multiple Tidal accounts
- **Cloud backup**: Auto-backup database to cloud storage

---

## 11. Technical Considerations

### Performance

- Indexes on frequently queried columns
- Batch operations for bulk updates
- Connection pooling for concurrent access
- Query optimization with EXPLAIN

### Data Integrity

- Foreign key constraints
- Transactions for multi-step operations
- Soft deletes (keep historical data)
- Checksums for data validation

### Security

- Database file permissions
- No sensitive data storage (tokens handled separately)
- Input validation and sanitization
- Parameterized queries (SQL injection prevention)

### Maintenance

- Auto-vacuum for SQLite optimization
- Periodic integrity checks
- Backup automation
- Schema migration tools (Alembic)

---

## 12. Success Metrics

The database implementation will be successful when:

✅ You can instantly see which playlists need downloading
✅ Change detection is accurate and reliable
✅ No duplicate downloads occur
✅ Orphaned files are easily identified
✅ Sync state is always clear and actionable
✅ Performance is fast (< 1 second for most operations)
✅ Data integrity is maintained across all syncs
✅ Migration from non-database version is smooth

---

**Document Version:** 1.0
**Date:** November 21, 2024
**Status:** Architecture Approved, Ready for Implementation
