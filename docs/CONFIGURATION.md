# Configuration Guide

This guide explains how to configure the Tidal Cleanup project for your environment.

## Quick Start

1. **Copy the example configuration:**

   ```bash
   cp config/.env.example config/.env
   ```

2. **Edit your personal configuration:**

   ```bash
   nano config/.env
   # or use your preferred editor
   code config/.env
   ```

3. **Update the settings** to match your system paths and preferences.

## Configuration Options

### Tidal API Settings

```bash
# Where to store your Tidal session token
TIDAL_CLEANUP_TIDAL_TOKEN_FILE=~/Documents/tidal_session.json
```

### Audio Directories

```bash
# Directory containing M4A files from Tidal
TIDAL_CLEANUP_M4A_DIRECTORY=/Volumes/HDD1TB/Music/DJing/Tidal/m4a

# Directory for converted MP3 files
TIDAL_CLEANUP_MP3_DIRECTORY=/Volumes/HDD1TB/Music/DJing/Tidal/mp3
```

### Rekordbox Integration

```bash
# Input folder for rekordbox playlist generation
TIDAL_CLEANUP_REKORDBOX_INPUT_FOLDER=/Volumes/HDD1TB/Music/DJing/Tidal/mp3/Playlists

# Output XML file for rekordbox
TIDAL_CLEANUP_REKORDBOX_OUTPUT_FILE=~/Documents/rekordbox/antons_music.xml
```

### Audio Conversion

```bash
# FFMPEG quality setting (0-9, lower is better quality)
TIDAL_CLEANUP_FFMPEG_QUALITY=2
```

### Track Matching

```bash
# Fuzzy matching threshold for track comparison (0-100)
TIDAL_CLEANUP_FUZZY_MATCH_THRESHOLD=80
```

### Logging

```bash
# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
TIDAL_CLEANUP_LOG_LEVEL=INFO

# Optional: Log to file (comment out to log to console only)
# TIDAL_CLEANUP_LOG_FILE=/path/to/logfile.log
```

### CLI Behavior

```bash
# Enable interactive prompts (true/false)
TIDAL_CLEANUP_INTERACTIVE_MODE=true
```

## Configuration Methods

### Method 1: .env File (Recommended)

The easiest way is to use the `.env` file in the `config/` directory:

```bash
# Edit your configuration
code config/.env
```

The application will automatically load this file when it starts.

### Method 2: Environment Variables

Set environment variables in your shell:

```bash
# For current session
export TIDAL_CLEANUP_LOG_LEVEL=DEBUG

# Permanent (add to ~/.zshrc or ~/.bash_profile)
echo 'export TIDAL_CLEANUP_LOG_LEVEL=DEBUG' >> ~/.zshrc
```

### Method 3: Command-line Override

You can override settings for a single command:

```bash
TIDAL_CLEANUP_LOG_LEVEL=DEBUG tidal-cleanup status
```

## Path Configuration Examples

### macOS Examples

```bash
TIDAL_CLEANUP_M4A_DIRECTORY=/Users/yourusername/Music/Tidal/m4a
TIDAL_CLEANUP_MP3_DIRECTORY=/Users/yourusername/Music/Tidal/mp3
TIDAL_CLEANUP_REKORDBOX_OUTPUT_FILE=/Users/yourusername/Documents/rekordbox/music.xml
```

### Linux Examples

```bash
TIDAL_CLEANUP_M4A_DIRECTORY=/home/yourusername/Music/Tidal/m4a
TIDAL_CLEANUP_MP3_DIRECTORY=/home/yourusername/Music/Tidal/mp3
TIDAL_CLEANUP_REKORDBOX_OUTPUT_FILE=/home/yourusername/Documents/rekordbox/music.xml
```

### Windows Examples

```bash
TIDAL_CLEANUP_M4A_DIRECTORY=C:/Users/yourusername/Music/Tidal/m4a
TIDAL_CLEANUP_MP3_DIRECTORY=C:/Users/yourusername/Music/Tidal/mp3
TIDAL_CLEANUP_REKORDBOX_OUTPUT_FILE=C:/Users/yourusername/Documents/rekordbox/music.xml
```

## Verification

To verify your configuration is working:

```bash
# Check current settings
tidal-cleanup status

# Test with debug logging
TIDAL_CLEANUP_LOG_LEVEL=DEBUG tidal-cleanup status
```

## Security Notes

- The `.env` file is automatically ignored by git to prevent accidental commits
- Keep your `tidal_session.json` file secure and don't commit it to version control
- The `.env.example` file shows the structure but doesn't contain sensitive data

## Troubleshooting

### Path Issues

- Use absolute paths to avoid confusion
- On macOS/Linux, use `~` for home directory
- On Windows, use forward slashes or escape backslashes
- Ensure directories exist or the app will create them

### Permission Issues

- Make sure the application can read/write to configured directories
- Check that output file directories are writable

### Environment Variables Not Loading

- Verify `.env` file is in the `config/` directory
- Check for syntax errors in the `.env` file
- Restart your terminal/application after making changes
