# PlantUML Sequence Diagrams

This directory contains PlantUML sequence diagrams documenting the tidal-cleanup sync architecture.

## Diagrams

### 1. [db-sync-flow.puml](db-sync-flow.puml)

Complete end-to-end flow of the `tidal-cleanup db sync` command, showing all 5 stages:

- Stage 1: Fetch Tidal State
- Stage 2: Scan Filesystem
- Stage 3: Analyze Deduplication
- Stage 4: Generate Decisions
- Stage 5: Execute Decisions

### 2. [tidal-fetch-flow.puml](tidal-fetch-flow.puml)

Detailed flow of `TidalStateFetcher.fetch_all_playlists()`:

- Fetching playlists from Tidal API
- Creating/updating playlists in database
- Fetching tracks for each playlist
- Setting `in_tidal` flags
- Creating sync snapshots

### 3. [decision-engine-flow.puml](decision-engine-flow.puml)

Detailed flow of `SyncDecisionEngine.analyze_playlist_sync()`:

- Comparing Tidal state (`in_tidal` flag) vs local files
- Generating DOWNLOAD_TRACK decisions
- Generating REMOVE_FILE decisions (with orphan detection)
- Active path tracking to prevent accidental removals

### 4. [download-execution-flow.puml](download-execution-flow.puml)

Detailed flow of `DownloadOrchestrator.execute_decisions()`:

- Processing DOWNLOAD_TRACK decisions
- Processing REMOVE_FILE decisions
- Updating database with file paths and download status
- Dry-run mode handling

### 5. [filesystem-scanner-flow.puml](filesystem-scanner-flow.puml)

Detailed flow of `FilesystemScanner.scan_all_playlists()`:

- Scanning playlist directories for audio files
- Matching files to tracks (exact and fuzzy matching)
- Setting `in_local` flags
- Detecting removed files

## Viewing Diagrams

### Online Viewers

- [PlantUML Online Server](http://www.plantuml.com/plantuml/uml/)
- [PlantText](https://www.planttext.com/)

### VS Code

Install the PlantUML extension:

```bash
code --install-extension jebbs.plantuml
```

Then open any `.puml` file and press `Alt+D` to preview.

### Command Line

```bash
# Install PlantUML
brew install plantuml

# Generate PNG
plantuml db-sync-flow.puml

# Generate SVG
plantuml -tsvg db-sync-flow.puml

# Generate all diagrams
plantuml *.puml
```

### Docker

```bash
docker run --rm -v $(pwd):/data plantuml/plantuml:latest -tsvg /data/*.puml
```

## Key Architecture Concepts

### Locality Flags

The system uses three boolean flags on `playlist_tracks`:

- `in_tidal`: Track is currently in Tidal playlist
- `in_local`: Track file exists locally
- `in_rekordbox`: Track is in Rekordbox database

These flags are reset and repopulated during each sync to detect changes.

### Decision Priority

Decisions are prioritized (higher = more urgent):

- **10**: DOWNLOAD_TRACK (new track not yet downloaded)
- **8**: REMOVE_FILE (track removed from Tidal)
- **7**: REMOVE_FILE (orphan file)
- **6**: DOWNLOAD_TRACK (track needs download to this playlist)
- **5**: DOWNLOAD_TRACK (retry after error)

### File Path Management

- Tracks can have multiple file paths (one per playlist copy)
- File paths are stored as JSON array in `tracks.file_paths`
- Scanner matches files to tracks using normalized names
- Removal decisions check if file is needed by other playlists

### Optimization

- TidalStateFetcher skips track fetching for unchanged playlists (compares `last_updated_tidal` timestamp)
- DecisionEngine caches active playlist paths to avoid redundant DB queries
- Scanner uses fuzzy matching as fallback when exact name match fails

## Related Documentation

- [UNIFIED_SYNC_ARCHITECTURE.md](../UNIFIED_SYNC_ARCHITECTURE.md) - High-level architecture overview
- [DATABASE_ARCHITECTURE.md](../DATABASE_ARCHITECTURE.md) - Database schema and models
- [DOWNLOAD_IMPLEMENTATION.md](../DOWNLOAD_IMPLEMENTATION.md) - Download service details
