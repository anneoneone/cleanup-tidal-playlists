# Project Reorganization Proposal

## Goal

Create a modular structure for: **Tidal → MP3 (local files) → Rekordbox database**
Each step is tracked in a database for state management.

## Current State Analysis

### Current Structure

```
src/tidal_cleanup/
├── cli/                 # Command-line interface
├── config.py            # Configuration
├── database/            # Mixed: DB service + sync logic + orchestrators
├── models/              # Data models
├── services/            # Mixed: active + legacy services
└── utils/               # Utilities
```

### Current Workflow (from download command)

1. **Tidal Fetch**: `TidalStateFetcher` → fetches playlists/tracks from Tidal API
2. **File Scan**: `FileScannerService` → scans local MP3 directory
3. **Sync Decisions**: `SyncDecisionEngine` → compares Tidal vs Local, decides actions
4. **Download/Convert**: `DownloadOrchestrator` → downloads M4A, converts to MP3
5. **Rekordbox Sync**: `RekordboxService` → syncs MP3 playlists to Rekordbox DB

## Proposed Modular Structure

```
src/tidal_cleanup/
├── cli/                          # Command-line interface (KEEP AS IS)
│   ├── commands/
│   │   ├── database.py           # DB management commands
│   │   ├── download.py           # Download workflow command
│   │   ├── legacy.py             # Legacy commands (to be removed)
│   │   └── rekordbox.py          # Rekordbox sync command
│   ├── display/
│   │   └── formatters.py
│   └── main.py
│
├── core/                         # NEW: Core business logic modules
│   ├── __init__.py
│   │
│   ├── tidal/                    # Step 1: Tidal Integration
│   │   ├── __init__.py
│   │   ├── api_client.py         # FROM services/tidal_service.py
│   │   ├── download_service.py   # FROM services/tidal_download_service.py
│   │   ├── state_fetcher.py      # FROM database/tidal_state_fetcher.py
│   │   └── snapshot_service.py   # FROM database/tidal_snapshot_service.py
│   │
│   ├── filesystem/               # Step 2: Local File Management
│   │   ├── __init__.py
│   │   ├── scanner.py            # FROM database/filesystem_scanner.py
│   │   ├── file_scanner.py       # FROM database/file_scanner_service.py
│   │   └── models.py             # File-related models
│   │
│   ├── sync/                     # Step 3: Synchronization Logic
│   │   ├── __init__.py
│   │   ├── decision_engine.py    # FROM database/sync_decision_engine.py
│   │   ├── orchestrator.py       # FROM database/sync_orchestrator.py
│   │   ├── download_orchestrator.py  # FROM database/download_orchestrator.py
│   │   ├── state.py              # FROM database/sync_state.py
│   │   ├── conflict_resolver.py  # FROM database/conflict_resolver.py
│   │   └── deduplication.py      # FROM database/deduplication_logic.py
│   │
│   └── rekordbox/                # Step 4: Rekordbox Integration
│       ├── __init__.py
│       ├── service.py            # FROM services/rekordbox_service.py
│       ├── playlist_sync.py      # FROM services/rekordbox_playlist_sync.py
│       ├── mytag_manager.py      # FROM services/mytag_manager.py
│       └── playlist_parser.py    # FROM services/playlist_name_parser.py
│
├── database/                     # NEW: Pure database layer
│   ├── __init__.py
│   ├── service.py                # FROM database/service.py (DB operations only)
│   ├── models.py                 # FROM database/models.py
│   └── progress_tracker.py       # FROM database/progress_tracker.py
│
├── legacy/                       # NEW: Legacy code (to be removed later)
│   ├── __init__.py
│   ├── playlist_synchronizer.py  # FROM services/playlist_synchronizer.py
│   ├── file_service.py           # FROM services/file_service.py
│   ├── track_comparison.py       # FROM services/track_comparison_service.py
│   └── directory_diff.py         # FROM services/directory_diff_service.py
│
├── models/                       # Data models (KEEP AS IS)
│   ├── __init__.py
│   └── models.py
│
├── config.py                     # Configuration (KEEP AS IS)
└── utils/                        # Utilities (KEEP AS IS)
    ├── __init__.py
    └── logging_config.py
```

## Migration Map

### REMOVE (Directories)

- ❌ `database/` - Split into `core/` modules and `database/` (pure DB)
- ❌ `services/` - Split into `core/` modules and `legacy/`

### CREATE (New Directories)

- ✅ `core/` - Main business logic
- ✅ `core/tidal/` - Tidal integration (fetch, download, snapshot)
- ✅ `core/filesystem/` - Local file scanning and management
- ✅ `core/sync/` - Synchronization logic (decisions, orchestration, conflicts)
- ✅ `core/rekordbox/` - Rekordbox database integration
- ✅ `database/` - Pure database layer (service, models, tracker)
- ✅ `legacy/` - Legacy services (to be removed)

### File Moves

#### Core/Tidal Module (Step 1: Tidal → Database)

```
services/tidal_service.py              → core/tidal/api_client.py
services/tidal_download_service.py     → core/tidal/download_service.py
database/tidal_state_fetcher.py        → core/tidal/state_fetcher.py
database/tidal_snapshot_service.py     → core/tidal/snapshot_service.py
```

#### Core/Filesystem Module (Step 2: Local Files → Database)

```
database/filesystem_scanner.py         → core/filesystem/scanner.py
database/file_scanner_service.py       → core/filesystem/file_scanner.py
```

#### Core/Sync Module (Step 3: Sync Logic)

```
database/sync_decision_engine.py       → core/sync/decision_engine.py
database/sync_orchestrator.py          → core/sync/orchestrator.py
database/download_orchestrator.py      → core/sync/download_orchestrator.py
database/sync_state.py                 → core/sync/state.py
database/conflict_resolver.py          → core/sync/conflict_resolver.py
database/deduplication_logic.py        → core/sync/deduplication.py
```

#### Core/Rekordbox Module (Step 4: MP3 → Rekordbox)

```
services/rekordbox_service.py          → core/rekordbox/service.py
services/rekordbox_playlist_sync.py    → core/rekordbox/playlist_sync.py
services/mytag_manager.py              → core/rekordbox/mytag_manager.py
services/playlist_name_parser.py       → core/rekordbox/playlist_parser.py
```

#### Database Module (Pure DB operations)

```
database/service.py                    → database/service.py (keep)
database/models.py                     → database/models.py (keep)
database/progress_tracker.py           → database/progress_tracker.py (keep)
```

#### Legacy Module (To be removed later)

```
services/playlist_synchronizer.py      → legacy/playlist_synchronizer.py
services/file_service.py               → legacy/file_service.py
services/track_comparison_service.py   → legacy/track_comparison.py
services/directory_diff_service.py     → legacy/directory_diff.py
```

## Benefits

### 1. **Clear Pipeline Flow**

```
Tidal API → core/tidal → database
    ↓
Local Files → core/filesystem → database
    ↓
Sync Logic → core/sync → database
    ↓
Rekordbox DB → core/rekordbox
```

### 2. **Module Independence**

Each `core/` module can be:

- Tested independently
- Used independently
- Has clear responsibilities
- Single source of truth for each step

### 3. **Easy Navigation**

- Want Tidal logic? → `core/tidal/`
- Want file scanning? → `core/filesystem/`
- Want sync decisions? → `core/sync/`
- Want Rekordbox integration? → `core/rekordbox/`
- Want pure DB operations? → `database/`

### 4. **Clean Deprecation Path**

- Legacy code isolated in `legacy/`
- Easy to remove when ready
- No mixing with active code

## Import Updates Required

### CLI Commands

```python
# OLD
from ...database import TidalStateFetcher, DownloadOrchestrator
from ...services import TidalApiService, TidalDownloadService

# NEW
from ...core.tidal import TidalApiClient, TidalDownloadService, TidalStateFetcher
from ...core.sync import DownloadOrchestrator
```

### Cross-module imports

```python
# core/sync/download_orchestrator.py
# OLD
from ..services.tidal_download_service import TidalDownloadService

# NEW
from ..tidal.download_service import TidalDownloadService
```

## Migration Steps

### Phase 1: Create Structure (No breaking changes)

1. Create new directories: `core/`, `core/tidal/`, `core/filesystem/`, `core/sync/`, `core/rekordbox/`, `legacy/`
2. Create `__init__.py` files with proper exports

### Phase 2: Move Files & Update Imports

1. Move Tidal module files
2. Move Filesystem module files
3. Move Sync module files
4. Move Rekordbox module files
5. Move Legacy files
6. Update all imports in moved files
7. Update CLI command imports

### Phase 3: Update Exports

1. Update `core/__init__.py` with all exports
2. Update `database/__init__.py` with pure DB exports
3. Update `legacy/__init__.py` with legacy exports
4. Keep backward compatibility in root `__init__.py` if needed

### Phase 4: Clean Database Directory

1. Keep only: `service.py`, `models.py`, `progress_tracker.py`, `__init__.py`
2. Remove empty `services/` directory
3. Remove old `database/` files (already moved)

### Phase 5: Testing & Verification

1. Run all CLI commands to verify imports work
2. Run test suite
3. Update documentation
4. Update `docs/SERVICES_ANALYSIS.md`

## Recommendation

**Start with this proposal?**

- ✅ Clear module boundaries
- ✅ Follows your pipeline: Tidal → MP3 → Rekordbox
- ✅ Each step has its own module
- ✅ Database stays pure (just DB operations)
- ✅ Legacy code isolated for future removal
- ✅ Easy to understand and maintain

**Alternative: Less radical reorganization?**

- Just create `services/legacy/` and `services/active/` subdirectories
- Keep `database/` as-is
- Simpler but less clear separation

**What would you like me to do?**

1. Proceed with full reorganization as proposed?
2. Modify the proposal?
3. Start with a smaller change first?
