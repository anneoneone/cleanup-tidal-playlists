# Database Implementation - Phase 2+ Continuation Guide

## Project Status

**Repository**: `cleanup-tidal-playlists`
**Branch**: `19-add-database-to-maintain-tracks`
**Current Phase**: Phase 1 Complete ✅ → Ready for Phase 2
**Date**: November 21, 2024

---

## Phase 1 Summary (✅ COMPLETED)

### What Has Been Done

1. ✅ **Database Technology Selection & Architecture Design**
   - Selected SQLite as database technology
   - Designed 5-table schema (tracks, playlists, playlist_tracks, sync_operations, sync_snapshots)
   - Created comprehensive architecture document: `docs/DATABASE_ARCHITECTURE.md`

2. ✅ **Database Schema Design**
   - All 5 tables designed with proper relationships
   - Indexes and constraints implemented
   - Foreign keys configured with CASCADE deletes

3. ✅ **SQLAlchemy Models & ORM Setup**
   - All models implemented: `src/tidal_cleanup/database/models.py`
   - Using modern SQLAlchemy 2.0 with type annotations
   - Proper relationships configured

4. ✅ **Database Service Layer**
   - Comprehensive `DatabaseService` class: `src/tidal_cleanup/database/service.py`
   - 30+ methods for CRUD operations
   - Transaction management
   - Session handling

5. ✅ **Configuration Integration**
   - Database path added to `Config` class
   - Environment variable support: `TIDAL_CLEANUP_DATABASE_PATH`
   - Default location: `~/.tidal-cleanup/sync.db`

6. ✅ **Dependencies**
   - SQLAlchemy 2.0+ added to `pyproject.toml`

7. ✅ **Comprehensive Tests**
   - 18 test cases: `tests/test_database.py`
   - All tests passing ✅
   - 70% coverage for database module

8. ✅ **Documentation**
   - Architecture: `docs/DATABASE_ARCHITECTURE.md` (700 lines)
   - Implementation summary: `docs/DATABASE_IMPLEMENTATION_SUMMARY.md` (600 lines)
   - Quick start guide: `docs/DATABASE_QUICKSTART.md`

### Files Created in Phase 1

```
src/tidal_cleanup/database/
├── __init__.py          # Package exports
├── models.py            # SQLAlchemy models (300 lines)
└── service.py           # Database service (700 lines)

docs/
├── DATABASE_ARCHITECTURE.md              # Architecture (700 lines)
├── DATABASE_IMPLEMENTATION_SUMMARY.md    # Summary (600 lines)
└── DATABASE_QUICKSTART.md                # Quick start

tests/
└── test_database.py     # Test suite (300 lines)

Modified:
- pyproject.toml         # Added sqlalchemy dependency
- src/tidal_cleanup/config.py  # Added database_path config
```

---

## Phase 2+ TODO LIST

### Phase 2: State Tracking & Change Detection

#### TODO #5: Create Sync State Tracking System

**Status**: 🔄 NOT STARTED
**Estimated Effort**: 4-6 hours

**Objectives**:

- Implement change detection logic
- Create change types enum (TRACK_ADDED, TRACK_REMOVED, TRACK_MOVED, etc.)
- Build comparison engine for snapshots
- Persist change events

**Implementation Plan**:

1. Create `src/tidal_cleanup/database/sync_state.py`:
   - `ChangeType` enum (PLAYLIST_ADDED, PLAYLIST_REMOVED, TRACK_ADDED_TO_PLAYLIST, TRACK_REMOVED_FROM_PLAYLIST, TRACK_MOVED, TRACK_METADATA_CHANGED, PLAYLIST_RENAMED)
   - `Change` dataclass (type, playlist_id, track_id, old_value, new_value, timestamp)
   - `SyncState` class for state management

2. Add methods to `DatabaseService`:
   - `compare_snapshots(snapshot1, snapshot2) -> List[Change]`
   - `get_changes_since(timestamp) -> List[Change]`
   - `get_unprocessed_changes() -> List[Change]`

3. Create tests: `tests/test_sync_state.py`

**Acceptance Criteria**:

- Can detect all change types
- Changes are persisted to database
- Can query changes by type, date, playlist

---

#### TODO #6: Implement Tidal Snapshot Service

**Status**: 🔄 NOT STARTED
**Estimated Effort**: 6-8 hours

**Objectives**:

- Fetch current Tidal state via TidalApiService
- Store snapshot in database
- Compare with previous snapshot to detect changes
- Update database with current state

**Implementation Plan**:

1. Create `src/tidal_cleanup/database/tidal_snapshot_service.py`:
   - `TidalSnapshotService` class
   - `capture_tidal_snapshot() -> Snapshot`
   - `detect_changes() -> List[Change]`
   - `apply_tidal_state_to_db()` - Update tracks and playlists

2. Integration with existing `TidalApiService`:
   - Use existing `get_playlists()` and `get_playlist_tracks()`
   - Map Tidal data to database models
   - Handle new playlists, tracks, and updates

3. Implement smart sync:
   - Only update what changed
   - Batch operations for efficiency
   - Handle deletions (soft delete)

4. Create tests: `tests/test_tidal_snapshot.py`

**Acceptance Criteria**:

- Can capture full Tidal state
- Detects all types of changes accurately
- Updates database efficiently (batch operations)
- Handles edge cases (playlist renamed, track moved, etc.)

---

#### TODO #7: Implement Local File Scanner Service

**Status**: 🔄 NOT STARTED
**Estimated Effort**: 6-8 hours

**Objectives**:

- Scan MP3 directory structure
- Match files to database tracks
- Update file status (path, hash, last_modified)
- Detect orphaned files
- Identify missing files

**Implementation Plan**:

1. Create `src/tidal_cleanup/database/file_scanner_service.py`:
   - `FileScanner` class
   - `scan_mp3_directory() -> ScanResult`
   - `match_file_to_track(file_path) -> Optional[Track]`
   - `update_track_file_info(track_id, file_path)`
   - `find_orphaned_files() -> List[Path]`
   - `find_missing_tracks() -> List[Track]`

2. File matching strategies (in order):
   - By exact file path
   - By normalized track name (artist - title)
   - By metadata from file tags (mutagen)

3. File hash computation:
   - Use SHA256 for change detection
   - Only compute for new/modified files
   - Store in `tracks.file_hash`

4. Integration with existing `FileService`:
   - Use existing `scan_directory()` method
   - Leverage existing metadata extraction

5. Create tests: `tests/test_file_scanner.py`

**Acceptance Criteria**:

- Scans directory efficiently (parallel processing for large libraries)
- Accurately matches files to tracks (>95% success rate)
- Detects orphaned files
- Identifies missing tracks (in DB but not on disk)
- Updates file hashes correctly

---

#### TODO #8: Create Sync Decision Engine

**Status**: 🔄 NOT STARTED
**Estimated Effort**: 8-10 hours

**Objectives**:

- Analyze Tidal state vs database state
- Generate actionable sync decisions
- Prioritize operations
- Provide user-friendly recommendations

**Implementation Plan**:

1. Create `src/tidal_cleanup/database/sync_decision_engine.py`:
   - `SyncDecision` dataclass (action, playlist, tracks, priority, reason)
   - `SyncDecisionEngine` class
   - `analyze_state() -> List[SyncDecision]`
   - `generate_download_plan() -> DownloadPlan`
   - `generate_cleanup_plan() -> CleanupPlan`

2. Decision types:
   - **DOWNLOAD_PLAYLIST**: New playlist in Tidal
   - **DOWNLOAD_TRACKS**: New tracks in existing playlist
   - **REMOVE_TRACKS**: Tracks removed from Tidal
   - **MOVE_TRACKS**: Tracks moved between playlists
   - **UPDATE_METADATA**: Track metadata changed
   - **CLEANUP_ORPHANS**: Files not in any Tidal playlist
   - **REDOWNLOAD_MISSING**: Tracks in DB but missing files

3. Prioritization logic:
   - High: New tracks in active playlists
   - Medium: Metadata updates
   - Low: Cleanup operations

4. Integration points:
   - Uses `TidalSnapshotService` for Tidal state
   - Uses `FileScanner` for local state
   - Outputs decisions to `sync_operations` table

5. Create tests: `tests/test_sync_decision.py`

**Acceptance Criteria**:

- Correctly identifies all decision types
- Prioritizes sensibly
- Handles edge cases (track in multiple playlists, etc.)
- Prevents duplicate downloads
- Generates human-readable explanations

---

### Phase 3: Service Integration

#### TODO #9: Add Database Integration to Existing Services

**Status**: 🔄 NOT STARTED
**Estimated Effort**: 10-12 hours

**Objectives**:

- Update existing services to use database
- Maintain backward compatibility
- Add database awareness throughout

**Implementation Plan**:

1. **Update `TidalApiService`** (`src/tidal_cleanup/services/tidal_service.py`):
   - Add optional `DatabaseService` parameter to `__init__`
   - Modify `get_playlists()` to update database
   - Modify `get_playlist_tracks()` to update database
   - Add `sync_to_database()` method

2. **Update `FileService`** (`src/tidal_cleanup/services/file_service.py`):
   - Add optional `DatabaseService` parameter
   - Update `convert_audio()` to record file info in database
   - Add `sync_directory_to_database()` method
   - Track conversion operations in database

3. **Update `RekordboxService`** (`src/tidal_cleanup/services/rekordbox_service.py`):
   - Add optional `DatabaseService` parameter
   - Update `sync_playlist_with_mytags()` to record in database
   - Track which tracks are in Rekordbox
   - Update `playlist_tracks.in_rekordbox` flag

4. **Update `TidalDownloadService`** (`src/tidal_cleanup/services/tidal_download_service.py`):
   - Add database tracking for downloads
   - Record downloaded files in database
   - Mark tracks as downloaded (`playlist_tracks.in_local = True`)

5. **Backward Compatibility**:
   - All database parameters are optional
   - Services work without database (existing behavior)
   - Gradually enable database features

6. Create integration tests: `tests/test_service_integration.py`

**Acceptance Criteria**:

- All services work with database enabled
- All services work without database (backward compatible)
- Database is updated on all operations
- No breaking changes to existing code
- Integration tests pass

---

### Phase 4: CLI & User Interface

#### TODO #10: Create Database CLI Commands

**Status**: 🔄 NOT STARTED
**Estimated Effort**: 8-10 hours

**Objectives**:

- Add CLI commands for database management
- Provide visibility into sync state
- Enable manual sync operations

**Implementation Plan**:

1. Create `src/tidal_cleanup/cli/database.py`:
   - Click command group for database operations

2. **Command: `db init`**
   - Initialize database schema
   - Import existing data (scan local files, fetch Tidal state)
   - Show statistics

3. **Command: `db status`**
   - Show database statistics
   - Show last sync time
   - Show pending operations
   - Show recent changes

4. **Command: `db sync`**
   - Detect changes since last sync
   - Show what changed
   - Optional `--apply` flag to actually sync
   - Generate sync decisions

5. **Command: `db inspect <playlist-name>`**
   - Show playlist details from database
   - Show track list with sync status
   - Show recent changes to playlist

6. **Command: `db reconcile`**
   - Scan local files and compare with database
   - Show missing files
   - Show orphaned files
   - Optional `--fix` flag to apply fixes

7. **Command: `db snapshot`**
   - Create manual snapshot
   - List snapshots
   - Compare snapshots

8. **Command: `db reset`**
   - Clear database (with confirmation)
   - Reinitialize

9. **Command: `db stats`**
   - Detailed statistics
   - Database size
   - Table counts
   - Index health

10. Update main CLI (`src/tidal_cleanup/cli/main.py`):
    - Add database command group
    - Integrate with existing commands

11. Create tests: `tests/test_cli_database.py`

**Example CLI Usage**:

```bash
# Initialize database
tidal-cleanup db init

# Check status
tidal-cleanup db status

# Detect changes (dry run)
tidal-cleanup db sync

# Apply changes
tidal-cleanup db sync --apply

# Inspect specific playlist
tidal-cleanup db inspect "House Italo R 🇮🇹"

# Find issues
tidal-cleanup db reconcile

# Fix missing/orphaned files
tidal-cleanup db reconcile --fix
```

**Acceptance Criteria**:

- All commands work correctly
- Rich formatting with tables
- Clear error messages
- Dry-run by default, explicit apply flag
- Comprehensive help text

---

### Phase 5: Migration & Polish

#### TODO #11: Implement Database Migration System

**Status**: 🔄 NOT STARTED
**Estimated Effort**: 4-6 hours

**Objectives**:

- Set up Alembic for schema migrations
- Create initial migration
- Provide migration guide for users

**Implementation Plan**:

1. Install and configure Alembic:
   - Add to `pyproject.toml`
   - Initialize Alembic: `alembic init alembic`
   - Configure `alembic.ini`

2. Create initial migration:
   - `alembic revision --autogenerate -m "Initial schema"`
   - Review and test migration

3. Add migration utilities:
   - `src/tidal_cleanup/database/migrations.py`
   - `check_needs_migration()`
   - `apply_migrations()`

4. Create migration guide: `docs/DATABASE_MIGRATION.md`
   - How to upgrade from non-database version
   - How to backup database
   - How to apply migrations

5. Update CLI to check for migrations:
   - Auto-detect when migration needed
   - Prompt user to run migrations

**Acceptance Criteria**:

- Alembic properly configured
- Initial migration works
- Migration guide is clear
- CLI detects and applies migrations

---

## Implementation Timeline

**Phase 2: State Tracking** (20-24 hours)

- Week 1: TODO #5, #6 (Sync State + Tidal Snapshot)
- Week 2: TODO #7, #8 (File Scanner + Decision Engine)

**Phase 3: Integration** (10-12 hours)

- Week 3: TODO #9 (Service Integration)

**Phase 4: CLI** (8-10 hours)

- Week 4: TODO #10 (CLI Commands)

**Phase 5: Migration** (4-6 hours)

- Week 4: TODO #11 (Alembic Setup)

**Total Estimated Effort**: 42-52 hours (6-7 days of full-time work)

---

## Key Design Decisions to Remember

1. **Tidal is Source of Truth**
   - All changes flow from Tidal → Database → Local/Rekordbox
   - Never modify Tidal based on local state

2. **Soft Deletes**
   - Don't delete data, mark as removed
   - Preserves history
   - Enables "restore" functionality

3. **Multi-Source Tracking**
   - Track presence in each source independently (in_tidal, in_local, in_rekordbox)
   - Handle tracks in multiple playlists gracefully

4. **Backward Compatibility**
   - All database features are optional
   - Existing workflows continue to work
   - Gradual adoption

5. **Performance**
   - Batch operations where possible
   - Use indexes effectively
   - Minimize API calls

6. **User Experience**
   - Clear visibility into what changed
   - Dry-run by default
   - Actionable recommendations

---

## Testing Strategy

For each phase:

1. Unit tests for new modules
2. Integration tests for service interactions
3. End-to-end tests for complete workflows
4. Manual testing with real data

**Test Coverage Goal**: >80% for new code

---

## Success Metrics

The implementation will be successful when:

✅ User can instantly see which playlists have changes
✅ Change detection is accurate (>95%)
✅ No duplicate downloads occur
✅ Orphaned files are identified correctly
✅ Sync state is always clear and actionable
✅ Performance is fast (< 2s for most operations)
✅ All existing functionality continues to work

---

## Getting Started with Phase 2

When ready to continue:

1. **Review Phase 1**:
   - Read `docs/DATABASE_ARCHITECTURE.md`
   - Read `docs/DATABASE_IMPLEMENTATION_SUMMARY.md`
   - Run existing tests: `pytest tests/test_database.py -v`

2. **Start with TODO #5** (Sync State Tracking):
   - Create `src/tidal_cleanup/database/sync_state.py`
   - Define `ChangeType` enum
   - Implement change detection logic

3. **Test as you go**:
   - Write tests alongside implementation
   - Use existing tests as examples

4. **Ask questions**:
   - Architecture questions
   - Design decisions
   - Edge cases

---

## Quick Reference

### Database Location

- Default: `~/.tidal-cleanup/sync.db`
- Config: `TIDAL_CLEANUP_DATABASE_PATH`

### Key Files

- Models: `src/tidal_cleanup/database/models.py`
- Service: `src/tidal_cleanup/database/service.py`
- Tests: `tests/test_database.py`

### Run Tests

```bash
pytest tests/test_database.py -v
```

### Database Statistics

```python
from tidal_cleanup.database import DatabaseService
db = DatabaseService()
print(db.get_statistics())
```

---

## Notes

- Phase 1 took approximately 8-10 hours
- All 18 tests passing ✅
- SQLAlchemy 2.0 with modern type annotations
- Zero breaking changes to existing code
- Production-ready foundation

---

**Last Updated**: November 21, 2024
**Status**: Phase 1 Complete, Ready for Phase 2
**Next Task**: TODO #5 - Create Sync State Tracking System
