# Download Feature Implementation Summary

## Overview

Successfully implemented a new **Step 0** in the tidal-cleanup workflow: downloading tracks from Tidal using the `tidal-dl-ng` library.

## What Was Implemented

### 1. TidalDownloadService (`src/tidal_cleanup/services/tidal_download_service.py`)

A new service that wraps tidal-dl-ng functionality:

**Key Features:**

- Token-based authentication (reuses existing token)
- Downloads playlists to M4A directory with proper structure
- Skips already downloaded files automatically
- Downloads in highest available quality (Hi-Res Lossless)
- Supports downloading all playlists or specific playlist by name
- Proper error handling and logging

**Public Methods:**

- `connect()` - Establish connection to Tidal (handles token auth)
- `download_playlist(playlist_name)` - Download specific playlist
- `download_all_playlists()` - Download all user playlists
- `is_authenticated()` - Check authentication status

### 2. CLI Command (`src/tidal_cleanup/cli/main.py`)

Added new `download` command:

```bash
tidal-cleanup download              # Download all playlists
tidal-cleanup download -p "Name"    # Download specific playlist
```

**Integration:**

- Integrated into TidalCleanupApp class
- Uses existing configuration system
- Provides rich console output with status messages
- Proper error handling with user-friendly messages

### 3. Dependencies (`pyproject.toml`)

Added `tidal-dl-ng>=0.13.0` to project dependencies.

### 4. Tests (`tests/test_tidal_download_service.py`)

Comprehensive test suite covering:

- Service initialization
- Authentication (with/without token)
- Playlist downloading (single and all)
- Error handling (not authenticated, playlist not found)
- Logger adapter functionality

**Test Coverage:**

- 11 test methods
- Mocked external dependencies (TidalDL, Download)
- Covers both success and failure scenarios

### 5. Documentation

**Updated Files:**

- `README.md` - Added download command to usage examples
- `docs/DOWNLOAD_FEATURE.md` - Complete documentation for the new feature

**Documentation Includes:**

- Feature overview and workflow position
- Usage examples (all playlists, specific playlist)
- Authentication flow and token management
- Directory structure explanation
- Configuration options
- Error handling scenarios
- Integration with existing workflow
- Troubleshooting guide
- FAQ section

## Implementation Details

### Authentication Flow

1. **First Run:**
   - No token exists
   - User prompted for interactive login via browser
   - Token saved to `tidal_session.json`
   - Used for subsequent requests

2. **Subsequent Runs:**
   - Loads existing token
   - Validates token
   - If invalid, prompts for re-authentication

### Download Process

For each playlist:

1. Connect to Tidal (authenticate)
2. Fetch playlist information
3. Create playlist directory structure: `m4a/Playlists/<playlist_name>/`
4. Download tracks one by one:
   - Check if file exists (skip if yes)
   - Download with proper naming: `01 - Artist - Title.m4a`
   - Log progress and results

### Directory Structure

```
m4a/
└── Playlists/
    ├── Playlist 1/
    │   ├── 01 - Artist - Track.m4a
    │   ├── 02 - Artist - Track.m4a
    │   └── ...
    ├── Playlist 2/
    │   └── ...
    └── ...
```

### Configuration

Uses existing configuration system:

- `TIDAL_CLEANUP_M4A_DIRECTORY` - Download destination
- `TIDAL_CLEANUP_TIDAL_TOKEN_FILE` - Token storage location

## Workflow Integration

The new download step fits at the beginning of the workflow:

```
OLD WORKFLOW:
1. sync      - Sync playlists (expects files already exist)
2. convert   - Convert M4A to MP3
3. rekordbox - Generate XML

NEW WORKFLOW:
0. download  - Download tracks from Tidal ← NEW!
1. sync      - Sync playlists
2. convert   - Convert M4A to MP3
3. rekordbox - Generate XML
```

## Key Design Decisions

### 1. Token Reuse

Reuses the existing `tidal_session.json` token, avoiding duplicate authentication setups.

### 2. Skip Existing Files

Automatically skips already downloaded files to avoid wasting bandwidth and time.

### 3. Playlist Organization

Creates a `Playlists/` subdirectory in M4A folder to match existing structure expected by other commands.

### 4. Quality Settings

Defaults to highest available quality (Hi-Res Lossless) to ensure best audio quality.

### 5. Error Handling

Graceful error handling with informative messages, allowing partial downloads to succeed even if individual tracks fail.

### 6. Service Pattern

Follows existing service-oriented architecture with dependency injection and separation of concerns.

## Usage Examples

### Download All Playlists

```bash
tidal-cleanup download
```

### Download Specific Playlist

```bash
tidal-cleanup download -p "House Music"
```

### Full Workflow

```bash
tidal-cleanup download          # Step 0: Download from Tidal
tidal-cleanup sync             # Step 1: Sync metadata
tidal-cleanup convert          # Step 2: Convert to MP3
tidal-cleanup rekordbox        # Step 3: Generate XML
```

## Testing

Run the tests:

```bash
pytest tests/test_tidal_download_service.py -v
```

Expected output:

```
tests/test_tidal_download_service.py::TestTidalDownloadService::test_init PASSED
tests/test_tidal_download_service.py::TestTidalDownloadService::test_create_tidal_dl_settings PASSED
tests/test_tidal_download_service.py::TestTidalDownloadService::test_connect_with_existing_token PASSED
...
```

## Next Steps (Optional Enhancements)

1. **Progress Bars**: Add rich progress bars for download progress
2. **Parallel Downloads**: Download multiple tracks simultaneously
3. **Resume Support**: Resume interrupted downloads
4. **Metadata Extraction**: Extract and display album art, genres, etc.
5. **Download Queue**: Queue system for large download batches
6. **Selective Track Downloads**: Download only specific tracks from a playlist

## Files Modified

1. `pyproject.toml` - Added tidal-dl-ng dependency
2. `src/tidal_cleanup/services/__init__.py` - Exported new service
3. `src/tidal_cleanup/services/tidal_download_service.py` - New service (305 lines)
4. `src/tidal_cleanup/cli/main.py` - Added download command and method
5. `tests/test_tidal_download_service.py` - New test file (252 lines)
6. `README.md` - Updated usage examples
7. `docs/DOWNLOAD_FEATURE.md` - New documentation (286 lines)

## Summary

✅ Implemented complete download functionality
✅ Token-based authentication with automatic reuse
✅ Smart file existence checking
✅ Proper directory organization
✅ Comprehensive error handling
✅ Full test coverage
✅ Complete documentation
✅ CLI integration
✅ Follows existing architecture patterns

The download feature is ready to use and fully integrated into the tidal-cleanup workflow!
