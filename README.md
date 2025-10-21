# Tidal Playlist Cleanup Tool

A modern, refactored tool for synchronizing Tidal playlists with local audio files, featuring audio conversion and Rekordbox XML generation.

## Features

- **Tidal Integration**: Secure OAuth authentication with session persistence
- **Smart Track Matching**: Fuzzy matching algorithms to handle track name variations
- **Audio Conversion**: Batch conversion from M4A/MP4 to MP3 using FFmpeg
- **Rekordbox Support**: Generate XML files for Rekordbox DJ software
- **Modern CLI**: Rich terminal interface with progress bars and colored output
- **Configurable**: Environment-based configuration with sensible defaults
- **Logging**: Comprehensive logging with file rotation and colored console output
- **Error Handling**: Robust error handling with detailed error messages

## Architecture

The application follows modern Python best practices:

```
src/tidal_cleanup/
├── __init__.py          # Package initialization
├── config.py            # Configuration management
├── models/              # Data models (Pydantic)
│   ├── __init__.py
│   └── models.py
├── services/            # Business logic services
│   ├── __init__.py
│   ├── tidal_service.py      # Tidal API integration
│   ├── file_service.py       # File operations
│   ├── track_comparison_service.py  # Track matching
│   └── rekordbox_service.py  # XML generation
├── utils/               # Utilities
│   ├── __init__.py
│   └── logging_config.py
└── cli/                 # Command-line interface
    ├── __init__.py
    └── main.py
```

## Installation

### Prerequisites

- Python 3.8 or higher
- FFmpeg (for audio conversion)

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Install as Package

```bash
pip install -e .
```

## Configuration

The application uses environment variables for configuration. Copy the example configuration:

```bash
cp config/.env.example .env
```

Edit `.env` to customize paths and settings:

```bash
# Tidal API settings
TIDAL_CLEANUP_TIDAL_TOKEN_FILE=~/Documents/tidal_session.json

# Audio directories
TIDAL_CLEANUP_M4A_DIRECTORY=~/Music/Tidal/m4a
TIDAL_CLEANUP_MP3_DIRECTORY=~/Music/Tidal/mp3

# Rekordbox settings
TIDAL_CLEANUP_REKORDBOX_INPUT_FOLDER=~/Music/Tidal/mp3/Playlists
TIDAL_CLEANUP_REKORDBOX_OUTPUT_FILE=~/Documents/rekordbox/antons_music.xml

# Other settings
TIDAL_CLEANUP_FUZZY_MATCH_THRESHOLD=80
TIDAL_CLEANUP_LOG_LEVEL=INFO
```

## Usage

### Command Line Interface

The new CLI provides several commands:

```bash
# Show help
tidal-cleanup --help

# Show current configuration
tidal-cleanup status

# Synchronize playlists only
tidal-cleanup sync

# Convert audio files only
tidal-cleanup convert

# Generate Rekordbox XML only
tidal-cleanup rekordbox

# Run full workflow (sync + convert + rekordbox)
tidal-cleanup full

# Run with debug logging
tidal-cleanup --log-level DEBUG full

# Run non-interactively
tidal-cleanup --no-interactive sync
```

### Python API

You can also use the services directly in Python:

```python
from tidal_cleanup.config import get_config
from tidal_cleanup.services import TidalService, FileService

# Initialize services
config = get_config()
tidal_service = TidalService(config.tidal_token_file)
file_service = FileService()

# Connect to Tidal
tidal_service.connect()

# Get playlists
playlists = tidal_service.get_playlists()
print(f"Found {len(playlists)} playlists")
```

## Migration from Legacy Code

The refactored version maintains compatibility with your existing workflow while providing significant improvements:

### What's Changed

1. **Modular Architecture**: Code is organized into logical modules
2. **Configuration Management**: Hardcoded paths replaced with configurable settings
3. **Error Handling**: Comprehensive error handling throughout
4. **Logging**: Structured logging with different levels
5. **CLI Interface**: Rich terminal interface with progress indicators
6. **Type Safety**: Pydantic models for data validation
7. **Testing**: Prepared for unit and integration tests

### What's Preserved

1. **Core Functionality**: All original features are maintained
2. **File Formats**: Same audio format support
3. **Tidal Integration**: Compatible with existing Tidal sessions
4. **Rekordbox Output**: Same XML format for Rekordbox

## Development

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black src/
```

### Linting

```bash
flake8 src/
```

### Type Checking

```bash
mypy src/
```

## Troubleshooting

### Common Issues

1. **Tidal Authentication**: If authentication fails, delete the token file and re-authenticate
2. **FFmpeg Not Found**: Ensure FFmpeg is installed and in your PATH
3. **Permission Errors**: Check file permissions for input/output directories
4. **Import Errors**: Make sure you've installed all dependencies

### Logging

Enable debug logging for detailed troubleshooting:

```bash
tidal-cleanup --log-level DEBUG --log-file debug.log full
```

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Acknowledgments

- Original codebase foundation
- Tidal API developers
- FFmpeg project
- Rich library for beautiful terminal output
