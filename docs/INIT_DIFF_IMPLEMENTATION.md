# Program Flow Refactoring: Init and Diff Commands

## Overview

This document describes the implementation of the first two steps of the refactored program flow for the Tidal cleanup application. The refactoring introduces a modular, step-by-step workflow that prepares for a unified `run` command.

## Implemented Commands

### 1. `tidal-cleanup init` - Initialization & Preparation

**Purpose**: Check and initialize all required services before any operations.

**Location**: `src/tidal_cleanup/cli/commands/init.py`

**What it does**:

1. **Database**: Checks connection and creates schema if needed
2. **Tidal API**: Verifies OAuth authentication, initiates login if required
3. **Tidal Downloader**: Checks tidal-dl-ng setup and authentication
4. **Rekordbox** (optional): Validates Rekordbox database connection

**Key Features**:

- Interactive authentication flows when needed
- Detailed status display with colored output
- Reusable `check_all_services()` function for programmatic use
- `--skip-rekordbox` flag for optional Rekordbox checking
- `--verbose` flag for detailed information

**Usage**:

```bash
# Check and initialize all services
tidal-cleanup init

# Skip Rekordbox check
tidal-cleanup init --skip-rekordbox

# Show detailed information
tidal-cleanup init -v
```

**Public API**:

- `check_all_services(config, skip_rekordbox)` - Returns dict with service status
- `init_command()` - Click command for CLI usage

---

### 2. `tidal-cleanup diff` - Synchronization Status

**Purpose**: Fetch current state from all services and show differences.

**Location**: `src/tidal_cleanup/cli/commands/diff.py`

**What it does**:

1. Checks that all services are initialized (calls `check_all_services`)
2. Fetches state from each service:
   - **Tidal**: Fetches playlists and tracks via API
   - **Local**: Scans filesystem for audio files
   - **Rekordbox**: Checks tracks in Rekordbox database
3. Updates database with current locality information
4. Displays tracks that differ across services

**Key Features**:

- `--exclude` flag to skip services (can be used multiple times)
- `--skip-fetch` to use existing database state
- `--verbose` for detailed information
- Clear visual table showing presence/absence across services
- Summary statistics

**Usage**:

```bash
# Show full diff across all services
tidal-cleanup diff

# Exclude Rekordbox from comparison
tidal-cleanup diff --exclude rekordbox

# Skip fetching, use existing database
tidal-cleanup diff --skip-fetch

# Exclude multiple services
tidal-cleanup diff --exclude local --exclude rekordbox
```

**Locality Tracking**:
The diff command determines track locality based on:

- **in_tidal**: Track has `last_seen_in_tidal` within last 30 days
- **in_local**: Track has `file_path` and file exists
- **in_rekordbox**: Track has `rekordbox_content_id`

---

## Architecture

### Flow Diagram

```
tidal-cleanup init
├── check_database_connection()
│   ├── DatabaseService.is_initialized()
│   └── DatabaseService.init_db() [if needed]
├── check_tidal_api_connection()
│   ├── TidalApiService.is_authenticated()
│   └── TidalApiService.connect() [if needed]
├── check_tidal_downloader_connection()
│   ├── TidalDownloadService.is_authenticated()
│   └── TidalDownloadService.connect() [if needed]
└── check_rekordbox_connection()
    └── RekordboxService.db [if available]

tidal-cleanup diff
├── check_all_services() [unless --skip-fetch]
├── fetch_tidal_state()
│   ├── TidalApiService.connect()
│   └── TidalStateFetcher.fetch_all_playlists()
├── fetch_local_state()
│   └── FilesystemScanner.scan_all_playlists()
├── fetch_rekordbox_state()
│   └── RekordboxService.db.get_content().count()
├── compute_diff_status() [for each track]
└── display_diff_table()
```

### Database Schema Usage

The commands leverage existing database models without requiring schema changes:

**Track Model Fields Used**:

- `last_seen_in_tidal` - Timestamp of last Tidal fetch
- `file_path` - Local file location
- `rekordbox_content_id` - Rekordbox database ID
- `tidal_id` - Tidal track identifier

No new columns were added; existing fields provide all necessary locality information.

---

## Integration Points

### Reusable Components

Both commands export functions that can be used programmatically:

```python
from tidal_cleanup.cli.commands.init import check_all_services
from tidal_cleanup.cli.commands.diff import compute_diff_status

# Check all services
config = Config()
results = check_all_services(config, skip_rekordbox=False)
if results["all_ready"]:
    # Proceed with operations
    pass

# Compute diff for a track
diff_info = compute_diff_status(track, exclude_services=set())
if diff_info["has_diff"]:
    # Track needs synchronization
    pass
```

### Future `run` Command Integration

These commands form the foundation for the planned `run` command:

```python
# Pseudocode for future run command
def run_command():
    # Step 1: Init (already implemented)
    check_all_services(config)

    # Step 2: Diff (already implemented)
    fetch_all_services(config)
    tracks_with_diffs = get_tracks_with_diffs()

    # Step 3: Download & Convert (to be implemented)
    for track in tracks_with_diffs:
        if not track.in_local:
            download_and_convert(track)

    # Step 4: Sync (to be implemented)
    for track in tracks_with_diffs:
        if needs_symlink:
            create_symlink(track)
        if needs_rekordbox_update:
            update_rekordbox(track)
```

---

## Testing

### Manual Testing Commands

```bash
# 1. Test init command
tidal-cleanup init
tidal-cleanup init --skip-rekordbox
tidal-cleanup init -v

# 2. Test diff command (after init)
tidal-cleanup diff
tidal-cleanup diff --exclude rekordbox
tidal-cleanup diff --skip-fetch
tidal-cleanup diff -v

# 3. Test with exclusions
tidal-cleanup diff --exclude local --exclude rekordbox

# 4. Test error handling (with no auth)
# Remove token file and try commands
rm ~/Documents/tidal_session.json
tidal-cleanup init  # Should prompt for authentication
```

### Expected Behaviors

**Init Command**:

- First run: Prompts for Tidal authentication (OAuth flow)
- Subsequent runs: Shows "all services OK" instantly
- Creates database schema if missing
- Shows clear error messages for failures

**Diff Command**:

- Checks initialization first (can be skipped with `--skip-fetch`)
- Fetches from each service sequentially with progress
- Shows table with ✓/✗ indicators for each service
- Displays up to 50 tracks with differences
- Shows summary statistics

---

## Error Handling

Both commands include comprehensive error handling:

1. **InitializationError**: Raised when services can't be set up
2. **Click.ClickException**: For user-facing CLI errors
3. **Graceful degradation**: Rekordbox failures are warnings, not errors
4. **Detailed logging**: All exceptions logged for debugging

---

## Configuration

Both commands use the existing `Config` class which reads from environment variables:

- `TIDAL_CLEANUP_TIDAL_TOKEN_FILE`: OAuth token storage
- `TIDAL_CLEANUP_M4A_DIRECTORY`: Download directory
- `TIDAL_CLEANUP_MP3_DIRECTORY`: Converted files directory
- `TIDAL_CLEANUP_DATABASE_PATH`: SQLite database location

---

## Next Steps

### Phase 3: Download & Convert (Planned)

- Use `TidalDownloadService` to download missing tracks
- Convert M4A to MP3 if needed
- Update database with file information

### Phase 4: Sync (Planned)

- Create/update symlinks for playlists
- Sync with Rekordbox database
- Apply MyTags based on playlist names

### Future `run` Command

- Combine all steps into single workflow
- Add progress tracking
- Provide rollback capability
- Enable selective execution (e.g., skip download)

---

## Files Created/Modified

### New Files

- `src/tidal_cleanup/cli/commands/init.py` - Initialization command
- `src/tidal_cleanup/cli/commands/diff.py` - Diff command
- `docs/INIT_DIFF_IMPLEMENTATION.md` - This documentation

### Modified Files

- `src/tidal_cleanup/cli/commands/__init__.py` - Export new commands
- `src/tidal_cleanup/cli/main.py` - Register new commands

### No Schema Changes

- Database models remain unchanged
- Existing fields provide all needed functionality

---

## Advantages of This Approach

1. **Modularity**: Each step is independent and testable
2. **Debuggability**: Can run individual steps for troubleshooting
3. **Reusability**: Core functions can be used programmatically
4. **Progressive Enhancement**: Easy to add steps 3 and 4
5. **Clear State**: Database tracks locality across all services
6. **Flexible Execution**: Can exclude services as needed
7. **User-Friendly**: Clear output and progress indicators

---

## Summary

The init and diff commands provide a solid foundation for the refactored program flow. They:

✅ Check and initialize all required services
✅ Fetch state from Tidal, local filesystem, and Rekordbox
✅ Track locality information in the database
✅ Display clear visual diffs between services
✅ Provide both CLI and programmatic interfaces
✅ Support flexible execution with exclusions
✅ Include comprehensive error handling

Next phases will build on this foundation to implement download/convert and sync operations, eventually culminating in a unified `run` command that orchestrates all steps.
