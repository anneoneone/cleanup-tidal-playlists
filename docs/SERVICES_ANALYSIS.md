# Services Directory Analysis & Reorganization Plan

## Current Structure

```
src/tidal_cleanup/services/
├── __init__.py                      (26 lines)
├── directory_diff_service.py        (284 lines)
├── file_service.py                  (812 lines)
├── mytag_manager.py                 (307 lines)
├── playlist_name_parser.py          (235 lines)
├── playlist_synchronizer.py         (644 lines)
├── rekordbox_playlist_sync.py       (907 lines)
├── rekordbox_service.py             (841 lines)
├── tidal_download_service.py        (461 lines)
├── tidal_service.py                 (347 lines)
└── track_comparison_service.py      (255 lines)

Total: 5,119 lines
```

## Usage Analysis

### ACTIVE Services (Used by Modern Database Layer or Rekordbox)

#### 1. **rekordbox_service.py** (841 lines)

- **Used by**:
  - `cli/commands/rekordbox.py` - Modern rekordbox sync command
- **Purpose**: Rekordbox database integration with MyTag management
- **Dependencies**:
  - `rekordbox_playlist_sync.py`
  - `mytag_manager.py`
  - `playlist_name_parser.py`
- **Status**: ✅ KEEP - Active modern functionality

#### 2. **rekordbox_playlist_sync.py** (907 lines)

- **Used by**: `rekordbox_service.py`
- **Purpose**: Orchestrates playlist synchronization with Rekordbox database
- **Dependencies**: `mytag_manager.py`, `playlist_name_parser.py`
- **Status**: ✅ KEEP - Core rekordbox functionality

#### 3. **mytag_manager.py** (307 lines)

- **Used by**: `rekordbox_playlist_sync.py`
- **Purpose**: Manages Rekordbox MyTags
- **Dependencies**: None
- **Status**: ✅ KEEP - Core rekordbox functionality

#### 4. **playlist_name_parser.py** (235 lines)

- **Used by**: `rekordbox_playlist_sync.py`
- **Purpose**: Parses emoji patterns from playlist names
- **Dependencies**: None
- **Status**: ✅ KEEP - Core rekordbox functionality

#### 5. **tidal_service.py** (347 lines)

- **Used by**:
  - `cli/commands/legacy.py` (TidalCleanupApp)
  - `cli/commands/download.py` (fetch helper)
  - `database/tidal_snapshot_service.py`
- **Purpose**: Tidal API integration (session, playlists, tracks)
- **Dependencies**: tidalapi library
- **Status**: ✅ KEEP - Active in both legacy and modern systems

#### 6. **tidal_download_service.py** (461 lines)

- **Used by**:
  - `cli/commands/legacy.py` (TidalCleanupApp)
  - `cli/commands/download.py`
  - `database/download_orchestrator.py`
  - `database/sync_orchestrator.py`
- **Purpose**: Downloads tracks from Tidal using tidal-dl-ng
- **Dependencies**: tidal-dl-ng library
- **Status**: ✅ KEEP - Active in both legacy and modern systems

### LEGACY Services (Only Used by Legacy CLI Commands)

#### 7. **playlist_synchronizer.py** (644 lines)

- **Used by**: `cli/commands/legacy.py` (TidalCleanupApp only)
- **Purpose**: Legacy playlist synchronization logic
- **Dependencies**:
  - `tidal_service.py`
  - `file_service.py`
  - `track_comparison_service.py`
- **Status**: 🟡 LEGACY - Only used by sync/convert/full commands
- **Modern Alternative**: Database-driven sync in `database/sync_orchestrator.py`

#### 8. **file_service.py** (812 lines)

- **Used by**:
  - `cli/commands/legacy.py` (TidalCleanupApp only)
  - Tests
- **Purpose**: File operations, metadata extraction, conversion
- **Dependencies**:
  - `directory_diff_service.py`
- **Status**: 🟡 LEGACY - Large service with mixed functionality
- **Modern Alternative**: Split between `database/filesystem_scanner.py` and `database/file_scanner_service.py`

#### 9. **track_comparison_service.py** (255 lines)

- **Used by**:
  - `cli/commands/legacy.py` (TidalCleanupApp only)
  - Tests (test_basic.py)
- **Purpose**: Fuzzy track matching between Tidal and local files
- **Dependencies**: thefuzz library
- **Status**: 🟡 LEGACY - Only used by legacy sync
- **Modern Alternative**: Database-based matching logic

#### 10. **directory_diff_service.py** (284 lines)

- **Used by**:
  - `file_service.py`
  - Tests
- **Purpose**: Compare source/target directories for conversion
- **Dependencies**: None
- **Status**: 🟡 LEGACY - Only used by legacy file service
- **Modern Alternative**: Database tracks file state

## Dependency Map

```
MODERN STACK (Rekordbox):
rekordbox_service.py
└── rekordbox_playlist_sync.py
    ├── mytag_manager.py
    └── playlist_name_parser.py

MODERN STACK (Download):
database/download_orchestrator.py
└── tidal_download_service.py

database/tidal_snapshot_service.py
└── tidal_service.py

LEGACY STACK:
TidalCleanupApp (legacy.py)
├── tidal_service.py (✅ shared)
├── tidal_download_service.py (✅ shared)
├── playlist_synchronizer.py (🟡 legacy-only)
│   ├── tidal_service.py
│   ├── file_service.py
│   └── track_comparison_service.py
├── file_service.py (🟡 legacy-only)
│   └── directory_diff_service.py
├── track_comparison_service.py (🟡 legacy-only)
└── rekordbox_service.py (✅ shared - but XML generation is legacy)
```

## Reorganization Recommendation

### Option 1: Split by Usage (Recommended)

```
src/tidal_cleanup/services/
├── __init__.py
├── active/              # Modern functionality
│   ├── __init__.py
│   ├── rekordbox/
│   │   ├── __init__.py
│   │   ├── service.py              (from rekordbox_service.py)
│   │   ├── playlist_sync.py        (from rekordbox_playlist_sync.py)
│   │   ├── mytag_manager.py        (from mytag_manager.py)
│   │   └── playlist_name_parser.py (from playlist_name_parser.py)
│   ├── tidal_service.py            (from tidal_service.py)
│   └── tidal_download_service.py   (from tidal_download_service.py)
└── legacy/              # Legacy functionality (to be removed)
    ├── __init__.py
    ├── playlist_synchronizer.py
    ├── file_service.py
    ├── track_comparison_service.py
    └── directory_diff_service.py
```

### Option 2: Keep Flat, Mark Legacy

```
src/tidal_cleanup/services/
├── __init__.py
├── rekordbox_service.py            # ✅ KEEP
├── rekordbox_playlist_sync.py      # ✅ KEEP
├── mytag_manager.py                # ✅ KEEP
├── playlist_name_parser.py         # ✅ KEEP
├── tidal_service.py                # ✅ KEEP
├── tidal_download_service.py       # ✅ KEEP
├── playlist_synchronizer_LEGACY.py # 🟡 LEGACY
├── file_service_LEGACY.py          # 🟡 LEGACY
├── track_comparison_service_LEGACY.py  # 🟡 LEGACY
└── directory_diff_service_LEGACY.py    # 🟡 LEGACY
```

## Migration Path

### Phase 1: Mark Legacy (Immediate)

1. Rename legacy files to include `_LEGACY` suffix
2. Update imports in `cli/commands/legacy.py`
3. Add deprecation warnings to legacy services
4. Update `services/__init__.py` to clearly separate exports

### Phase 2: Extract Rekordbox (Optional)

1. Create `services/rekordbox/` subdirectory
2. Move rekordbox-related files
3. Update imports
4. Keep backward compatibility in `services/__init__.py`

### Phase 3: Remove Legacy (When Ready)

1. Remove or archive legacy CLI commands
2. Delete `TidalCleanupApp` class
3. Delete legacy services
4. Update documentation

## Summary

**Active Services to Keep (6 files, 3,098 lines):**

- rekordbox_service.py (841 lines)
- rekordbox_playlist_sync.py (907 lines)
- mytag_manager.py (307 lines)
- playlist_name_parser.py (235 lines)
- tidal_service.py (347 lines)
- tidal_download_service.py (461 lines)

**Legacy Services (4 files, 1,995 lines):**

- playlist_synchronizer.py (644 lines) - only in TidalCleanupApp
- file_service.py (812 lines) - only in TidalCleanupApp
- track_comparison_service.py (255 lines) - only in TidalCleanupApp
- directory_diff_service.py (284 lines) - only in file_service.py

**Shared Dependencies:**

- tidal_service.py and tidal_download_service.py are used by both modern and legacy systems
- These should remain accessible until legacy is fully removed

## Recommended Actions

1. **Immediately**: Rename legacy files to `*_LEGACY.py` for clarity
2. **Short-term**: Move rekordbox services to subdirectory for better organization
3. **Long-term**: Remove legacy CLI commands and associated services
