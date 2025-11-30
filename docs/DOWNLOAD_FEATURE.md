# Tidal Download Feature

## Overview

The download feature enables you to download tracks directly from Tidal to your local M4A directory using the `tidal-dl-ng` library. This is the new **Step 0** in the workflow, occurring before playlist synchronization and conversion.

## Workflow Position

```
Step 0: tidal-cleanup download     ← NEW! Download tracks from Tidal
Step 1: tidal-cleanup sync          (Connect to Tidal, sync playlists)
Step 2: tidal-cleanup convert       (Convert M4A to MP3)
Step 3: tidal-cleanup rekordbox     (Generate Rekordbox XML)
```

## Features

- ✅ **Token-based authentication** - Login once, reuse token automatically
- ✅ **Smart downloads** - Skip already downloaded files
- ✅ **Playlist organization** - Create playlist directories in M4A folder
- ✅ **High quality** - Downloads in highest available quality (Hi-Res Lossless)
- ✅ **Selective downloads** - Download all playlists or just one

## Usage

### Download All Playlists

Download all playlists from your Tidal account:

```bash
tidal-cleanup download
```

This will:

1. Connect to Tidal (login if needed)
2. Fetch all your playlists
3. Download tracks to `m4a/Playlists/<playlist_name>/`
4. Skip files that already exist

### Download Specific Playlist

Download only one playlist by name:

```bash
tidal-cleanup download -p "My Favorites"
tidal-cleanup download --playlist "House Music"
```

## Authentication

### First Time Setup

On your first run, you'll be prompted to login:

```bash
$ tidal-cleanup download
Connecting to Tidal...
No valid token found, initiating new login...

Please scan the QR code or open the link to authenticate:
https://link.tidal.com/XXXXX

After completing authentication in your browser, press Enter...
```

### Subsequent Runs

The token is saved and reused automatically:

```bash
$ tidal-cleanup download
Connecting to Tidal...
✓ Connected to Tidal
Successfully authenticated with existing token
```

### Token Location

The Tidal token is stored at:

- Default: `~/Documents/tidal_session.json`
- Configurable via: `TIDAL_CLEANUP_TIDAL_TOKEN_FILE`

**Note:** This is the same token used by the existing sync functionality.

## Directory Structure

Downloaded tracks are organized in the M4A directory under a `Playlists` subdirectory:

```
~/Music/Tidal/m4a/
└── Playlists/
    ├── My Favorites/
    │   ├── 01 - Artist Name - Track Title.m4a
    │   ├── 02 - Artist Name - Track Title.m4a
    │   └── ...
    ├── House Music/
    │   ├── 01 - DJ Name - House Track.m4a
    │   └── ...
    └── Jazz Classics/
        └── ...
```

## Configuration

The download feature uses your existing configuration:

```bash
# M4A directory where files are downloaded
TIDAL_CLEANUP_M4A_DIRECTORY=~/Music/Tidal/m4a

# Token file for authentication
TIDAL_CLEANUP_TIDAL_TOKEN_FILE=~/Documents/tidal_session.json
```

## Download Settings

The download service is configured with:

- **Quality**: Hi-Res Lossless (highest available)
- **Skip existing**: Yes (avoids re-downloading)
- **Video downloads**: Disabled (audio only)
- **Format**: M4A files with proper metadata

## Intelligent Behavior

### File Existence Check

The service checks if a track already exists before downloading:

```
Downloading track 1/50: Artist - Track Name
✓ Downloaded: /path/to/track.m4a

Downloading track 2/50: Artist - Another Track
✓ Skipped (already exists): /path/to/track.m4a
```

### Playlist Directory Creation

Playlist directories are created automatically if they don't exist:

```bash
# First download
$ tidal-cleanup download -p "New Playlist"
Created/verified playlist directory: ~/Music/Tidal/m4a/Playlists/New Playlist
Downloading 25 tracks...

# Subsequent download
$ tidal-cleanup download -p "New Playlist"
Created/verified playlist directory: ~/Music/Tidal/m4a/Playlists/New Playlist
Downloading 25 tracks...
✓ Skipped (already exists): ...  (all 25 tracks)
```

## Error Handling

### Playlist Not Found

```bash
$ tidal-cleanup download -p "NonExistent"
✗ Download failed: Playlist 'NonExistent' not found in your Tidal account
```

### Authentication Failure

```bash
$ tidal-cleanup download
✗ Download failed: Failed to authenticate with Tidal
```

### Network Issues

```bash
$ tidal-cleanup download
✗ Download failed: Cannot connect to Tidal: Connection timeout
```

## Integration with Existing Workflow

The download step integrates seamlessly with the existing workflow:

```bash
# Complete workflow with download
tidal-cleanup download          # Step 0: Download from Tidal
tidal-cleanup sync             # Step 1: Sync playlist metadata
tidal-cleanup convert          # Step 2: Convert M4A to MP3
tidal-cleanup rekordbox        # Step 3: Generate Rekordbox XML
```

Or download a specific playlist and convert it:

```bash
tidal-cleanup download -p "House Music"
tidal-cleanup convert -p "House Music"
```

## Dependencies

The download feature requires the `tidal-dl-ng` library:

```bash
pip install tidal-cleanup[dev]  # Installs all dependencies
```

Or manually:

```bash
pip install tidal-dl-ng>=0.13.0
```

## Troubleshooting

### "Import Error: No module named 'tidal_dl_ng'"

Install the required dependency:

```bash
pip install tidal-dl-ng
```

### Token Expired

If you get authentication errors, remove the old token and login again:

```bash
rm ~/Documents/tidal_session.json
tidal-cleanup download
```

### Download Stuck

If a download appears stuck, try:

1. Check your internet connection
2. Verify your Tidal subscription is active
3. Try downloading a smaller playlist first
4. Check logs with `--log-level DEBUG`

## Advanced Usage

### Programmatic Usage

You can also use the download service in Python:

```python
from tidal_cleanup.config import get_config
from tidal_cleanup.services import TidalDownloadService

# Initialize
config = get_config()
download_service = TidalDownloadService(config)

# Connect
download_service.connect()

# Download playlist
playlist_dir = download_service.download_playlist("My Favorites")
print(f"Downloaded to: {playlist_dir}")

# Download all playlists
playlist_dirs = download_service.download_all_playlists()
print(f"Downloaded {len(playlist_dirs)} playlists")
```

## Comparison with Existing Sync

| Feature | `download` (Step 0) | `sync` (Step 1) |
|---------|---------------------|-----------------|
| Purpose | Download tracks from Tidal | Sync playlist metadata |
| Library | tidal-dl-ng | tidalapi |
| Downloads files | ✅ Yes | ❌ No (expects files exist) |
| Creates playlists | ✅ Yes | ❌ No |
| Checks track existence | ✅ Yes (in M4A folder) | ✅ Yes (in Tidal) |

## Best Practices

1. **Run download before sync**: Always download tracks before syncing
2. **Use selective downloads**: Download specific playlists when testing
3. **Check disk space**: Ensure sufficient space before downloading all playlists
4. **Backup tokens**: Keep a backup of your `tidal_session.json`
5. **Monitor logs**: Use `--log-level INFO` to track download progress

## FAQ

**Q: Do I need to download tracks every time?**
A: No, the service skips already downloaded files automatically.

**Q: Can I download tracks from Tidal Hi-Fi Plus?**
A: Yes, the highest quality available with your subscription will be downloaded.

**Q: What happens if a download fails mid-way?**
A: The service continues with the next track. Re-run to retry failed downloads.

**Q: Can I cancel a download?**
A: Yes, press Ctrl+C. Already downloaded files are kept.

**Q: Does this replace the existing sync command?**
A: No, download is a new step before sync. Both are needed for the full workflow.

## See Also

- [QUICKSTART_REKORDBOX_SYNC.md](QUICKSTART_REKORDBOX_SYNC.md) - Complete workflow guide
- [CONFIGURATION.md](CONFIGURATION.md) - Configuration options
- [README.md](../README.md) - Main documentation
