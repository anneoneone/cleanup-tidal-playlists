# Implementation Roadmap for Unified Sync

## Current Status

✅ **Documentation Complete**:

- `UNIFIED_SYNC_ARCHITECTURE.md` - Complete architecture design
- `MODEL_CHANGES_FOR_SYNC.md` - Detailed model changes needed
- Todo list updated with 12 specific tasks

## Implementation Phases

### Phase 1: Database Schema Updates (Tasks 1-4)

**Goal**: Update database models to support unified sync with deduplication

**Tasks**:

1. Add enums for status fields (`DownloadStatus`, `PlaylistSyncStatus`, `TrackSyncStatus`)
2. Add fields to `Track` model: `download_status`, `download_error`, `downloaded_at`, `last_verified_at`
3. Add fields to `Playlist` model: `sync_status`, `last_updated_tidal`, `last_synced_filesystem`
4. Add fields to `PlaylistTrack` model: `is_primary`, `symlink_path`, `symlink_valid`, `sync_status`, `synced_at`

**Deliverables**:

- Updated `src/tidal_cleanup/database/models.py`
- Alembic migration script
- Data migration script for existing databases

**Estimated Time**: 2-3 hours

---

### Phase 2: Tidal State Fetcher (Task 5)

**Goal**: Service to fetch current Tidal state and update database

**Implementation**:

```
src/tidal_cleanup/database/tidal_state_fetcher.py
```

**Key Methods**:

- `fetch_all_playlists()` - Get all playlists from Tidal API
- `update_playlist(playlist_data)` - Update database with playlist metadata
- `update_tracks(track_list)` - Update database with track metadata
- `detect_changes()` - Compare with previous snapshot, mark what changed

**Dependencies**:

- Existing `TidalApiService` for API calls
- Updated models from Phase 1

**Deliverables**:

- `TidalStateFetcher` service class
- Integration tests
- CLI command: `tidal-fetch`

**Estimated Time**: 4-5 hours

---

### Phase 3: Filesystem State Scanner (Task 6)

**Goal**: Service to scan local filesystem and update database

**Implementation**:

```
src/tidal_cleanup/database/filesystem_scanner.py
```

**Key Methods**:

- `scan_playlists_directory(base_path)` - Scan `mp3/Playlists/*`
- `scan_playlist(playlist_path)` - Scan single playlist directory
- `identify_file(file_path)` - Match file to track (by path, metadata, hash)
- `check_symlinks()` - Verify symlink validity
- `update_file_status()` - Update database with current filesystem state

**Dependencies**:

- `mutagen` for audio metadata extraction
- Updated models from Phase 1

**Deliverables**:

- `FilesystemScanner` service class
- Integration tests
- CLI command: `filesystem-scan`

**Estimated Time**: 4-5 hours

**Note**: Can reuse logic from `FileScannerService` created earlier, but refocus on playlist-centric scanning

---

### Phase 4: Sync Decision Engine (Task 7)

**Goal**: Compare Tidal vs filesystem state, generate sync plan

**Implementation**:

```
src/tidal_cleanup/database/sync_decision_engine.py
```

**Key Methods**:

- `generate_sync_plan()` - Main entry point
- `find_tracks_to_download()` - Tracks missing from filesystem
- `find_playlists_to_create()` - New playlists from Tidal
- `find_files_to_move()` - Playlist/track name changes
- `find_files_to_delete()` - Removed from Tidal
- `calculate_storage_impact()` - Estimate download size

**Data Structures**:

```python
SyncPlan = {
    'playlists_to_create': List[Playlist],
    'tracks_to_download': List[Tuple[Track, Path]],
    'symlinks_to_create': List[Tuple[Path, Path]],
    'files_to_move': List[Tuple[Path, Path]],
    'files_to_delete': List[Path],
    'storage_impact': {
        'downloads_bytes': int,
        'deletions_bytes': int,
        'net_change_bytes': int,
    }
}
```

**Deliverables**:

- `SyncDecisionEngine` service class
- Unit tests for decision logic
- CLI command: `sync-check` (dry-run)

**Estimated Time**: 6-8 hours

---

### Phase 5: Track Deduplication Logic (Task 8)

**Goal**: Determine primary file locations, identify duplicates

**Implementation**:

- Integrated into `SyncDecisionEngine`
- Add method: `determine_primary_locations()`

**Key Logic**:

```python
def determine_primary_locations(tracks_in_multiple_playlists):
    """For each track in multiple playlists, pick primary location."""
    for track, playlists in tracks_in_multiple_playlists.items():
        # Strategy: Use alphabetically first playlist as primary
        # (or use priority system: Favorites > Genre > Event)
        primary_playlist = sorted(playlists, key=lambda p: p.name)[0]

        # Mark primary
        primary_pt = get_playlist_track(primary_playlist, track)
        primary_pt.is_primary = True

        # Set track's primary file path
        track.file_path = f"mp3/Playlists/{primary_playlist.name}/{track.filename}"

        # Mark others as symlinks
        for playlist in playlists:
            if playlist != primary_playlist:
                pt = get_playlist_track(playlist, track)
                pt.is_primary = False
                pt.symlink_path = f"mp3/Playlists/{playlist.name}/{track.filename}"
```

**Deliverables**:

- Deduplication logic in `SyncDecisionEngine`
- Tests for primary location selection
- Reports showing shared tracks

**Estimated Time**: 3-4 hours

---

### Phase 6: Download Orchestrator (Task 9)

**Goal**: Execute sync plan, perform actual file operations

**Implementation**:

```
src/tidal_cleanup/database/download_orchestrator.py
```

**Key Methods**:

- `execute_sync_plan(plan)` - Main executor
- `download_track(track, destination)` - Download single track
- `create_symlink(target, link)` - Create symlink
- `move_file(source, dest)` - Move/rename file
- `delete_file(path)` - Remove orphaned file
- `update_database_status()` - Update download/sync status
- `handle_errors()` - Retry logic, error reporting

**Error Handling**:

- Retry downloads with exponential backoff
- Mark failed downloads with error message
- Skip broken symlinks, log for manual review
- Atomic operations (rollback on failure)

**Progress Reporting**:

- Progress bars for downloads
- Real-time status updates
- Summary at end

**Deliverables**:

- `DownloadOrchestrator` service class
- Integration tests (mocked downloads)
- CLI command: `sync-execute`

**Estimated Time**: 6-8 hours

---

### Phase 7: CLI Commands (Task 10)

**Goal**: User-facing commands for sync operations

**Commands to Implement**:

1. **`sync-check`** - Show what would change (dry-run)

   ```bash
   $ python -m tidal_cleanup sync-check
   # Shows: playlists to create, tracks to download, symlinks to create, etc.
   ```

2. **`sync-execute`** - Perform sync

   ```bash
   $ python -m tidal_cleanup sync-execute [--force] [--playlist NAME]
   # Executes sync plan with progress bars
   ```

3. **`sync-status`** - Show current state

   ```bash
   $ python -m tidal_cleanup sync-status
   # Shows: playlists in/out of sync, download status, errors
   ```

4. **`dedupe-report`** - Show shared tracks

   ```bash
   $ python -m tidal_cleanup dedupe-report
   # Shows: which tracks appear in multiple playlists, savings
   ```

5. **`tidal-fetch`** - Fetch Tidal state (standalone)

   ```bash
   $ python -m tidal_cleanup tidal-fetch
   # Updates database with current Tidal state
   ```

6. **`filesystem-scan`** - Scan filesystem (standalone)

   ```bash
   $ python -m tidal_cleanup filesystem-scan
   # Updates database with current filesystem state
   ```

**Implementation**:

- Add to `src/tidal_cleanup/cli.py` (or create new `cli_sync.py`)
- Use `click` for command-line interface
- Add colorized output with `rich` library

**Deliverables**:

- 6 new CLI commands
- CLI tests
- Updated documentation

**Estimated Time**: 4-5 hours

---

### Phase 8: Testing (Task 11)

**Goal**: Comprehensive test coverage

**Test Categories**:

1. **Model Tests** (`tests/test_models_unified_sync.py`)
   - Test new fields
   - Test enum values
   - Test relationships

2. **Tidal Fetcher Tests** (`tests/test_tidal_state_fetcher.py`)
   - Mock Tidal API responses
   - Test change detection
   - Test metadata updates

3. **Filesystem Scanner Tests** (`tests/test_filesystem_scanner.py`)
   - Test file discovery
   - Test symlink detection
   - Test metadata extraction

4. **Sync Decision Tests** (`tests/test_sync_decision_engine.py`)
   - Test sync plan generation
   - Test deduplication logic
   - Test edge cases

5. **Download Orchestrator Tests** (`tests/test_download_orchestrator.py`)
   - Mock file operations
   - Test error handling
   - Test progress tracking

6. **Integration Tests** (`tests/integration/test_full_sync_workflow.py`)
   - End-to-end workflow
   - Real filesystem operations (in temp dir)
   - Multiple sync cycles

**Target Coverage**: >80%

**Estimated Time**: 8-10 hours

---

### Phase 9: Documentation (Task 12)

**Goal**: User and developer documentation

**Documents to Create/Update**:

1. **User Documentation**:
   - `docs/SYNC_WORKFLOW.md` - How to use sync commands
   - `docs/TROUBLESHOOTING_SYNC.md` - Common issues and solutions
   - Update `README.md` with sync feature overview

2. **Developer Documentation**:
   - Update `UNIFIED_SYNC_ARCHITECTURE.md` with implementation notes
   - Add docstrings to all new classes/methods
   - Create flowcharts for sync decision logic

3. **Migration Guide**:
   - `docs/MIGRATION_TO_UNIFIED_SYNC.md` - For existing users
   - Database migration instructions
   - Handling existing files during migration

**Estimated Time**: 3-4 hours

---

## Total Estimated Time

- **Phase 1**: 2-3 hours
- **Phase 2**: 4-5 hours
- **Phase 3**: 4-5 hours
- **Phase 4**: 6-8 hours
- **Phase 5**: 3-4 hours
- **Phase 6**: 6-8 hours
- **Phase 7**: 4-5 hours
- **Phase 8**: 8-10 hours
- **Phase 9**: 3-4 hours

**Total**: ~40-52 hours (1-2 weeks of focused work)

---

## Quick Start (Minimal Viable Product)

For a faster MVP, implement core phases first:

1. **Phase 1** (Database) - Required foundation
2. **Phase 2** (Tidal Fetcher) - Get Tidal state
3. **Phase 3** (Filesystem Scanner) - Get filesystem state
4. **Phase 4** (Sync Decision) - Generate plan
5. **Phase 6** (Download Orchestrator) - Execute plan

Skip Phase 5 (deduplication) initially - can add later. Minimal CLI for testing.

**MVP Time**: ~25-35 hours

---

## Dependencies to Install

```bash
# For audio metadata extraction
pip install mutagen

# For CLI (if not already installed)
pip install click rich

# For progress bars
pip install tqdm

# For testing
pip install pytest pytest-cov pytest-mock
```

---

## Next Immediate Steps

Based on your requirements, here's what to do next:

1. **Update database models** (Phase 1)
   - Add new fields to Track, Playlist, PlaylistTrack
   - Create Alembic migration
   - Test with existing database

2. **Start Phase 2** (Tidal Fetcher)
   - Fetch playlists from Tidal
   - Update database with current state
   - Mark changes since last fetch

Would you like me to start implementing Phase 1 (database schema updates)?
