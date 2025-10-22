# Migration Guide: Legacy to Modern Architecture

This guide helps you transition from the legacy monolithic code to the new modern architecture.

## Summary of Changes

### Before (Legacy)

- Single large files with mixed responsibilities
- Hardcoded file paths throughout the code
- No proper error handling or logging
- German comments mixed with English code
- No configuration management
- No tests or documentation
- Manual deletion confirmation loops

### After (Modern Architecture)

- Modular design with clear separation of concerns
- Environment-based configuration
- Comprehensive error handling and logging
- Professional CLI with progress bars
- Type safety with Pydantic models
- Extensive documentation and testing framework

## File Mapping

| Legacy File | New Architecture |
|-------------|------------------|
| `main.py` | `src/tidal_cleanup/cli/main.py` |
| `cleanup_tidal_playlists.py` | `src/tidal_cleanup/services/tidal_service.py` + `src/tidal_cleanup/services/track_comparison_service.py` |
| `create_rekordbox_xml.py` | `src/tidal_cleanup/services/rekordbox_service.py` |
| Hardcoded configs | `src/tidal_cleanup/config.py` + `config/.env.example` |

## Step-by-Step Migration

### 1. Backup Your Current Setup

```bash
# Backup your current working directory
cp -r cleanup-tidal-playlists cleanup-tidal-playlists-backup
```

### 2. Install New Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp config/.env.example .env
# Edit .env with your specific paths
```

### 4. Test the New System

```bash
# Test configuration
python -m src.tidal_cleanup.cli.main status

# Test Tidal connection (will prompt for authentication if needed)
python -m src.tidal_cleanup.cli.main sync --help
```

### 5. Run Side-by-Side Comparison

Before fully switching, you can run both versions to compare results:

```bash
# Legacy way
python main.py

# New way
python -m src.tidal_cleanup.cli.main full
```

## Key Behavioral Changes

### Authentication

- **Legacy**: Token saved to hardcoded path
- **New**: Configurable token file location

### File Operations

- **Legacy**: Immediate file operations with inline confirmations
- **New**: Batch operations with optional confirmation mode

### Error Handling

- **Legacy**: Crashes on errors
- **New**: Graceful error handling with detailed logging

### Logging

- **Legacy**: Print statements and colored console output
- **New**: Structured logging with file rotation and configurable levels

## Configuration Migration

### Legacy Hardcoded Paths

```python
M4A_DIR = Path("/Users/anton/Music/Tidal/m4a")
MP3_DIR = Path("/Users/anton/Music/Tidal/mp3")
TOKEN_FILE = Path("/Users/anton/Documents/tidal_session.json")
```

### New Environment Configuration

```bash
TIDAL_CLEANUP_M4A_DIRECTORY=/Users/anton/Music/Tidal/m4a
TIDAL_CLEANUP_MP3_DIRECTORY=/Users/anton/Music/Tidal/mp3
TIDAL_CLEANUP_TIDAL_TOKEN_FILE=/Users/anton/Documents/tidal_session.json
```

## Functionality Preservation

All core functionality is preserved:

✅ **Tidal API Integration**: Same authentication and playlist fetching
✅ **Track Normalization**: Enhanced version of the original algorithm
✅ **File Conversion**: Same FFmpeg-based conversion
✅ **Rekordbox XML**: Compatible output format
✅ **Interactive Deletion**: Optional confirmation mode

## New Features

🆕 **Rich CLI**: Beautiful terminal interface with progress bars
🆕 **Configurable Settings**: Environment-based configuration
🆕 **Better Error Handling**: Detailed error messages and recovery
🆕 **Logging**: File and console logging with rotation
🆕 **Fuzzy Matching**: Better track matching algorithms
🆕 **Type Safety**: Pydantic models for data validation

## Troubleshooting Migration

### Common Issues

1. **Import Errors**

   ```bash
   # Make sure you're in the project root
   export PYTHONPATH=$PWD:$PYTHONPATH
   ```

2. **Configuration Not Found**

   ```bash
   # Check your .env file exists and has correct values
   cat .env
   ```

3. **Permission Issues**

   ```bash
   # Check directory permissions
   ls -la ~/Music/Tidal/
   ```

### Rollback Plan

If you need to revert to the legacy system:

1. Use your backup: `cp -r cleanup-tidal-playlists-backup/* .`
2. Restore original requirements: `pip install tidalapi ffmpeg-python mutagen`
3. Run legacy version: `python main.py`

## Testing Your Migration

### Verification Checklist

- [ ] Configuration loads correctly (`tidal-cleanup status`)
- [ ] Tidal authentication works
- [ ] File scanning works for existing playlists
- [ ] Audio conversion produces same quality files
- [ ] Rekordbox XML has same structure as before
- [ ] All your playlists are processed correctly

### Validation Commands

```bash
# Check configuration
tidal-cleanup status

# Dry run (no actual changes)
tidal-cleanup --log-level DEBUG sync

# Compare XML output
diff old_rekordbox.xml new_rekordbox.xml
```

## Support

If you encounter issues during migration:

1. Check the logs: `tidal-cleanup --log-level DEBUG --log-file migration.log full`
2. Compare with legacy behavior
3. Check configuration values
4. Verify file permissions and paths

The new architecture is designed to be more reliable and maintainable while preserving all your existing workflows.
