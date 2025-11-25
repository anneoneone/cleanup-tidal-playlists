# Logging Improvements - Summary & Implementation Guide

## What We Changed

### 1. Logging Format Enhancement
Updated `src/tidal_cleanup/utils/logging_config.py` to include filename and function name in all log messages:

**Before:**
```python
fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

**After:**
```python
fmt="%(asctime)s - %(filename)s:%(funcName)s - %(levelname)s - %(message)s"
```

This applies to both console and file logging handlers.

### 2. Logging Best Practices Applied

#### Use %-formatting (Lazy Evaluation)
**❌ Bad (f-strings - evaluates even if not logged):**
```python
logger.info(f"Processing {count} items from playlist {name}")
logger.error(f"Failed to process {item}: {error}")
```

**✅ Good (%-formatting - lazy evaluation):**
```python
logger.info("Processing %d items from playlist %s", count, name)
logger.error("Failed to process %s: %s", item, error)
```

#### Log Levels
- **DEBUG**: Detailed diagnostic information for troubleshooting
- **INFO**: Confirmation things are working, general progress/counts
- **WARNING**: Unexpected but recoverable situations
- **ERROR**: Serious problems that prevented a function from completing
- **CRITICAL**: Very serious errors that may cause application failure

#### Message Structure
- Start with clear action verb or state
- Include relevant context (what, where, counts)
- Make messages grep-able
- Be specific

**Examples:**
```python
# Good - actionable, clear context
logger.info("Tidal fetch complete: %d playlists created, %d updated", created, updated)
logger.error("Cannot write to directory (reason: %r): %r", error, homedir)
logger.warning("Playlist %s not found in Tidal", playlist_id)

# Bad - vague, no context
logger.info("Done")
logger.error("Error occurred")
logger.warning("Something wrong")
```

## Files Already Updated

1. ✅ `src/tidal_cleanup/utils/logging_config.py` - Format and initialization messages
2. ✅ `src/tidal_cleanup/database/tidal_state_fetcher.py` - Partial (3 statements)
3. ✅ `src/tidal_cleanup/services/tidal_service.py` - Partial (6 statements)

## Files That Need Updating

Based on grep analysis, the following files have f-string logging that needs conversion:

### High Priority (Core Services)
- `src/tidal_cleanup/services/file_service.py` (24 instances)
- `src/tidal_cleanup/services/rekordbox_playlist_sync.py` (43 instances)
- `src/tidal_cleanup/services/rekordbox_service.py` (16 instances)
- `src/tidal_cleanup/services/playlist_synchronizer.py` (7 instances)
- `src/tidal_cleanup/services/tidal_download_service.py` (13 instances)

### Medium Priority (Database Layer)
- `src/tidal_cleanup/database/download_orchestrator.py` (19 instances)
- `src/tidal_cleanup/database/tidal_snapshot_service.py` (15 instances)
- `src/tidal_cleanup/database/file_scanner_service.py` (8 instances)
- `src/tidal_cleanup/database/filesystem_scanner.py` (6 instances)
- `src/tidal_cleanup/database/sync_orchestrator.py` (4 instances)

### Lower Priority
- `src/tidal_cleanup/services/mytag_manager.py` (8 instances)
- `src/tidal_cleanup/services/playlist_name_parser.py` (2 instances)
- `src/tidal_cleanup/services/track_comparison_service.py` (3 instances)
- `src/tidal_cleanup/services/directory_diff_service.py` (2 instances)
- `src/tidal_cleanup/cli/main.py` (3 instances)
- `src/tidal_cleanup/cli/rekordbox.py` (2 instances)
- `src/tidal_cleanup/database/deduplication_logic.py` (2 instances)
- `src/tidal_cleanup/database/sync_decision_engine.py` (2 instances)
- `src/tidal_cleanup/database/conflict_resolver.py` (1 instance)
- `src/tidal_cleanup/database/progress_tracker.py` (1 instance)

## Conversion Patterns

### Pattern 1: Simple variable substitution
```python
# Before
logger.info(f"Processing {count} items")
# After
logger.info("Processing %d items", count)
```

### Pattern 2: Multiple variables
```python
# Before
logger.error(f"Failed to delete {file_path}: {e}")
# After
logger.error("Failed to delete %s: %s", file_path, e)
```

### Pattern 3: With repr()
```python
# Before
logger.error(f"Cannot write to home directory, $HOME={homedir}")
# After
logger.error("Cannot write to home directory, $HOME=%r", homedir)
```

### Pattern 4: Long messages (split for readability)
```python
# Before
logger.info(f"Tidal fetch complete: {created} playlists created, {updated} updated")

# After
logger.info(
    "Tidal fetch complete: %d playlists created, %d updated",
    created,
    updated
)
```

## Testing the Changes

After updating logging, test with different log levels:

```bash
# Test with DEBUG level to see all messages
tidal-cleanup --log-level DEBUG status

# Test with file logging
tidal-cleanup --log-level INFO --log-file test.log status

# Verify format includes filename and function
grep -E "\.py:\w+" test.log
```

## Semi-Automated Conversion

You can use sed or a Python script to help with conversion:

```bash
# Example: Find all f-string logging in a file
grep -n 'logger\.\(info\|debug\|warning\|error\).*f["'\'']' file.py

# Manual review required for each case to ensure:
# 1. Correct format specifier (%s, %d, %r, %f)
# 2. Proper line length (max 88 chars)
# 3. Context is preserved
```

## Common Format Specifiers

- `%s` - String (most common, works for str(), Path, etc.)
- `%d` - Integer (for counts, IDs)
- `%r` - Repr (for showing exact values including quotes)
- `%f` - Float
- `%i` - Integer (alternative to %d)

## Benefits of These Changes

1. **Performance**: Lazy evaluation means log message formatting only happens if the log level is enabled
2. **Debugging**: Filename and function name make it easier to find where logs originate
3. **Consistency**: All logs follow the same best practices
4. **Searchability**: Structured messages are easier to grep and analyze
5. **Production-ready**: Proper logging for production monitoring and debugging

## Next Steps

1. Convert remaining files file by file, starting with high-priority services
2. Test each file after conversion
3. Run the full test suite to ensure no regressions
4. Update any documentation that shows logging examples
