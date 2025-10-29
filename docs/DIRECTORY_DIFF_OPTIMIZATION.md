# Directory Diff Optimization

## Overview

The Tidal Cleanup application now uses an efficient **directory diff mechanism** to optimize file operations. This mechanism compares source and target directories and only processes files that differ, significantly improving performance and reducing unnecessary operations.

## Benefits

### Performance Improvements

- **Convert Command**: Only converts files that don't already exist in the target directory
- **Sync Command**: Only adds/removes tracks that differ between MP3 folder and Rekordbox database
- **Cleanup**: Automatically removes orphaned files in the target directory

### Efficiency Gains

Before the diff mechanism:

- All files were processed on every run
- No automatic cleanup of orphaned files
- Unnecessary re-conversions of already converted files

After the diff mechanism:

- Only new/missing files are processed
- Orphaned files are automatically detected and removed
- Significant time savings on subsequent runs

## How It Works

### DirectoryDiffService

The `DirectoryDiffService` is a generic, reusable service that compares two directories and identifies:

1. **Only in Source**: Files that exist only in the source directory (need to be added/processed)
2. **Only in Target**: Files that exist only in the target directory (need to be removed/cleaned up)
3. **In Both**: Files that exist in both directories (can be skipped)

### Convert Command

**Before Diff Optimization:**

```
Source (M4A):        Target (MP3):
- track1.m4a         - track1.mp3
- track2.m4a         - track3.mp3 (orphaned)
- track3.m4a

Action: Convert all 3 M4A files (even if track1.mp3 already exists)
```

**After Diff Optimization:**

```
Source (M4A):        Target (MP3):        Action:
- track1.m4a    ←→   - track1.mp3         Skip (already converted)
- track2.m4a                              Convert (missing in target)
                     - track3.mp3         Delete (orphaned, no source)
- track3.m4a                              Convert (source was replaced)
```

### Sync Command

**Before Diff Optimization:**

```
MP3 Folder:          Rekordbox:
- track1.mp3         - track1
- track2.mp3         - track3 (removed from MP3)
- track4.mp3

Action: Compare all tracks, process all differences
```

**After Diff Optimization:**

```
MP3 Folder:          Rekordbox:           Action:
- track1.mp3    ←→   - track1             Skip (already synced)
- track2.mp3                              Add to Rekordbox + apply MyTags
                     - track3             Remove from Rekordbox + clean MyTags
- track4.mp3                              Add to Rekordbox + apply MyTags
```

## Usage Examples

### Using DirectoryDiffService Directly

```python
from pathlib import Path
from tidal_cleanup.services import DirectoryDiffService

# Initialize service
diff_service = DirectoryDiffService()

# Compare directories
diff = diff_service.compare_by_stem_with_extension_mapping(
    source_dir=Path("/music/m4a/Playlists/MyPlaylist"),
    target_dir=Path("/music/mp3/Playlists/MyPlaylist"),
    source_extensions=(".m4a", ".mp4"),
    target_extensions=(".mp3",)
)

# Access results
print(f"Files to convert: {len(diff.only_in_source)}")
print(f"Files to delete: {len(diff.only_in_target)}")
print(f"Already converted: {len(diff.in_both)}")

# Get specific file paths
for file_stem in diff.only_in_source:
    source_file = diff.source_identities[file_stem].path
    print(f"Need to convert: {source_file}")

for file_stem in diff.only_in_target:
    target_file = diff.target_identities[file_stem].path
    print(f"Orphaned file (will delete): {target_file}")
```

### Custom Identity Function

You can provide a custom identity function for more complex comparison logic:

```python
def custom_identity(path: Path) -> str:
    """Custom identity based on normalized filename."""
    return path.stem.lower().replace(" ", "_")

diff = diff_service.compare_directories(
    source_dir=source_path,
    target_dir=target_path,
    source_extensions=(".m4a",),
    target_extensions=(".mp3",),
    identity_fn=custom_identity
)
```

### Comparing Directory to Database Items

The service can also compare a directory against database records:

```python
# Compare MP3 folder against Rekordbox tracks
only_in_dir, only_in_db, in_both, dir_ids, db_ids = \
    diff_service.compare_directory_to_items(
        directory=Path("/music/mp3/Playlists/MyPlaylist"),
        items=rekordbox_tracks,
        item_identity_fn=lambda track: (track['title'], track['artist'])
    )

print(f"Tracks to add to Rekordbox: {len(only_in_dir)}")
print(f"Tracks to remove from Rekordbox: {len(only_in_db)}")
print(f"Tracks already in sync: {len(in_both)}")
```

## Implementation Details

### File Identity

Files are compared using an **identity key** (default: file stem without extension):

```
track1.m4a  →  identity: "track1"
track1.mp3  →  identity: "track1"
```

This allows comparison across different file formats.

### DirectoryDiff Result

The `DirectoryDiff` result contains:

```python
@dataclass
class DirectoryDiff:
    only_in_source: Set[str]          # Keys of files only in source
    only_in_target: Set[str]          # Keys of files only in target
    in_both: Set[str]                  # Keys of files in both
    source_identities: Dict[str, FileIdentity]  # Full file info for source
    target_identities: Dict[str, FileIdentity]  # Full file info for target
```

### FileIdentity

Each file is represented as a `FileIdentity`:

```python
@dataclass
class FileIdentity:
    key: str                    # Identity key (e.g., "track1")
    path: Path                  # Absolute path to file
    metadata: Optional[Dict]    # Optional metadata (tags, size, etc.)
```

## Performance Metrics

### Example: Converting 1000 tracks

**First Run (no existing MP3s):**

- Time: ~30 minutes
- Files processed: 1000 converted

**Second Run (all already converted):**

- Time: ~10 seconds
- Files processed: 0 converted, 1000 skipped

**Third Run (10 new tracks, 5 removed from source):**

- Time: ~2 minutes
- Files processed: 10 converted, 5 deleted, 985 skipped

### Example: Syncing playlist to Rekordbox

**First Run:**

- Time: ~2 minutes (100 tracks)
- Operations: 100 tracks added + MyTags applied

**Second Run (no changes):**

- Time: ~5 seconds
- Operations: 0 (all tracks already in sync)

**Third Run (5 new tracks, 3 removed):**

- Time: ~15 seconds
- Operations: 5 tracks added, 3 tracks removed, 92 skipped

## Future Enhancements

Potential improvements to the diff mechanism:

1. **Checksum-based comparison**: Compare files by content hash instead of just filename
2. **Metadata comparison**: Detect when files exist but have different metadata/tags
3. **Incremental sync**: Track last sync time to avoid re-scanning unchanged directories
4. **Parallel processing**: Process multiple playlists in parallel using the diff mechanism
5. **Cache directory scans**: Cache file listings to speed up subsequent comparisons

## Related Files

- `src/tidal_cleanup/services/directory_diff_service.py` - Core diff service implementation
- `src/tidal_cleanup/services/file_service.py` - Convert command using diff mechanism
- `src/tidal_cleanup/services/rekordbox_playlist_sync.py` - Sync command using diff mechanism
- `tests/test_directory_diff_service.py` - Unit tests for diff service

## See Also

- [REKORDBOX_SYNC.md](REKORDBOX_SYNC.md) - Rekordbox synchronization documentation
- [QUICKSTART_REKORDBOX_SYNC.md](QUICKSTART_REKORDBOX_SYNC.md) - Quick start guide
- [CONFIGURATION.md](CONFIGURATION.md) - Configuration options
