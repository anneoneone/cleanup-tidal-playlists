# Phase 1 Complete: Database Models Updated for Unified Sync

## Summary

Phase 1 of the unified sync implementation is complete! The database models have been updated to support Tidal↔Filesystem synchronization with automatic deduplication.

## What Was Done

### ✅ 1. Added Status Enums

Three new enum classes in `models.py`:

- **`DownloadStatus`**: `not_downloaded`, `downloading`, `downloaded`, `error`
- **`PlaylistSyncStatus`**: `in_sync`, `needs_download`, `needs_update`, `needs_removal`, `unknown`
- **`TrackSyncStatus`**: `synced`, `needs_symlink`, `needs_move`, `needs_removal`, `unknown`

### ✅ 2. Updated Track Model

New fields added:

- `download_status` (str, default='not_downloaded', indexed)
- `download_error` (text, nullable)
- `downloaded_at` (datetime, nullable)
- `last_verified_at` (datetime, nullable)

Updated documentation:

- `file_path` now clearly documented as "primary file location"

### ✅ 3. Updated Playlist Model

New fields added:

- `sync_status` (str, default='unknown', indexed)
- `last_updated_tidal` (datetime, nullable) - from Tidal API
- `last_synced_filesystem` (datetime, nullable) - when we last synced

Updated documentation:

- `local_folder_path` now documents pattern: `mp3/Playlists/{sanitized_name}/`

### ✅ 4. Updated PlaylistTrack Model

New fields for deduplication and symlink tracking:

- `is_primary` (bool, default=False) - True if actual file, False if symlink
- `symlink_path` (str, nullable) - Full path to symlink
- `symlink_valid` (bool, nullable) - False if symlink broken
- `sync_status` (str, default='unknown', indexed)
- `synced_at` (datetime, nullable)

### ✅ 5. Installed and Configured Alembic

- Added `alembic>=1.13.0` to `pyproject.toml` dependencies
- Initialized Alembic with `alembic init alembic`
- Configured `alembic/env.py` to import our models
- Set default database URL: `sqlite:///tidal_cleanup.db`
- Created comprehensive `alembic/README.md` documentation

### ✅ 6. Created Initial Migration

Generated migration: `987ed04d1693_add_unified_sync_fields_for_tidal_.py`

This migration creates all tables with the new unified sync fields included.

### ✅ 7. Exported New Enums

Updated `__init__.py` to export:

- `DownloadStatus`
- `PlaylistSyncStatus`
- `TrackSyncStatus`

### ✅ 8. Passed All Quality Checks

- ✅ Black formatting
- ✅ isort imports
- ✅ flake8 linting
- ✅ mypy type checking
- ✅ All pre-commit hooks

## Files Changed

1. `src/tidal_cleanup/database/models.py` - Added enums and updated models
2. `src/tidal_cleanup/database/__init__.py` - Exported new enums
3. `pyproject.toml` - Added alembic dependency
4. `alembic/` - New directory with Alembic configuration
5. `alembic.ini` - Alembic configuration file
6. `alembic/env.py` - Configured to use our models
7. `alembic/README.md` - Alembic usage documentation
8. `alembic/versions/987ed04d1693_*.py` - Initial migration

## How to Use

### For New Databases

Apply the migration to create tables with unified sync fields:

```bash
alembic upgrade head
```

### For Existing Databases

The migration will add new columns to existing tables:

```bash
# Backup your database first!
cp tidal_cleanup.db tidal_cleanup.db.backup

# Apply migration
alembic upgrade head
```

### Manual Migration Script

Alternative to Alembic, use the manual migration script:

```bash
python -m scripts.migrations.add_unified_sync_fields
```

This script:

- Checks which fields need to be added
- Adds missing columns with proper defaults
- Migrates existing data (sets download_status based on file_path)
- Marks all existing playlist-tracks as primary initially

## Next Steps (Phase 2)

With the database models ready, we can now implement:

1. **Tidal State Fetcher** - Fetch playlists from Tidal and update database
2. **Filesystem Scanner** - Scan `mp3/Playlists/*` and update database
3. **Sync Decision Engine** - Compare states and generate sync plan
4. **Deduplication Logic** - Determine primary files and symlinks
5. **Download Orchestrator** - Execute sync plan
6. **CLI Commands** - User-facing sync commands

## Architecture Benefits

With these model changes, we now have:

✅ **Single source of truth** - One database tracking Tidal and filesystem state
✅ **Deduplication ready** - Track which files are primary vs symlinks
✅ **Sync status tracking** - Know exactly what needs syncing
✅ **Error tracking** - Capture download failures for debugging
✅ **Audit trail** - Timestamps for all sync operations
✅ **Schema versioning** - Alembic for future migrations

## Testing

To test the models:

```bash
# Import test
python -c "from tidal_cleanup.database import Track, Playlist, PlaylistTrack, DownloadStatus, PlaylistSyncStatus, TrackSyncStatus; print('✓ All imports successful')"

# Create test database
alembic upgrade head

# Run tests
pytest tests/test_models.py -v
```

## Documentation

See comprehensive architecture documentation:

- `docs/UNIFIED_SYNC_ARCHITECTURE.md` - Complete sync architecture
- `docs/MODEL_CHANGES_FOR_SYNC.md` - Detailed model changes
- `docs/IMPLEMENTATION_ROADMAP.md` - Full implementation plan
- `alembic/README.md` - Database migration guide

## What's Different from Before

**Old approach**: Separate tracking for Tidal, filesystem, and Rekordbox

**New unified approach**:

- Database knows both Tidal state AND filesystem state
- Status fields indicate what needs syncing
- Deduplication via primary files + symlinks
- Single workflow: fetch Tidal → scan filesystem → compare → sync

This sets the foundation for intelligent sync that prevents duplicate downloads and keeps everything in sync automatically.

---

**Status**: Phase 1 complete ✅
**Next**: Begin Phase 2 - Tidal State Fetcher implementation
**Branch**: `19-add-database-to-maintain-tracks`
