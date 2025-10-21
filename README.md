# Tidal Playlist Cleanup Tool

A modern, professional tool for synchronizing Tidal playlists with local audio files, featuring audio conversion, Rekordbox XML generation, and enterprise-grade development practices.

## Features

- **Tidal Integration**: Secure OAuth authentication with session persistence
- **Smart Track Matching**: Fuzzy matching algorithms to handle track name variations
- **Audio Conversion**: Batch conversion from M4A/MP4 to MP3 using FFmpeg
- **Rekordbox Support**: Generate XML files for Rekordbox DJ software
- **Modern CLI**: Rich terminal interface with progress bars and colored output
- **Configurable**: Environment-based configuration with sensible defaults
- **Logging**: Comprehensive logging with file rotation and colored console output
- **Error Handling**: Robust error handling with detailed error messages
- **Quality Assurance**: Comprehensive testing, linting, and security scanning
- **Modern Development**: Professional development workflow with automated quality gates

## Development Standards

This project follows modern Python development best practices:

- **📦 Modern Packaging**: pyproject.toml with PEP 517/518 build system
- **🔍 Code Quality**: Black, isort, flake8, mypy with strict configuration
- **🛡️ Security**: Bandit, Safety, and automated vulnerability scanning
- **🧪 Testing**: pytest with 80%+ coverage requirement
- **🔄 CI/CD**: GitHub Actions with matrix testing across Python 3.9-3.12
- **📝 Documentation**: Comprehensive guides and API documentation
- **🪝 Pre-commit**: 15+ automated quality checks before every commit

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

- Python 3.9 or higher
- FFmpeg (for audio conversion)
- Git (for development)

### Quick Install

```bash
# Install from source
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

### Development Setup

For contributors and developers:

```bash
# Clone and setup development environment
git clone https://github.com/anneoneone/cleanup-tidal-playlists.git
cd cleanup-tidal-playlists
make dev-setup
```

This installs all dependencies, sets up pre-commit hooks, and prepares the development environment.

## Environment Configuration

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

The CLI provides several commands for different workflows:

```bash
# Show help and available commands
tidal-cleanup --help

# Show current configuration and status
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

# Run non-interactively (no prompts)
tidal-cleanup --no-interactive sync

# Log to file
tidal-cleanup --log-file app.log full
```

### Development Commands

For developers working on the project:

```bash
# Development setup
make dev-setup  # Complete development environment setup
make help  # Show all available commands

# Code quality
make format  # Format code with Black and isort
make lint  # Run all linting (flake8, mypy, bandit)
make security  # Run security checks
make pr-check  # Full validation before creating PR

# Testing
make test  # Run tests
make test-cov  # Run tests with coverage report
make test-all  # Run tests across all Python versions

# Building and releasing
make build  # Build package
make clean  # Clean build artifacts
```

### Python API

### Programmatic Usage

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

# Process specific playlist
for playlist in playlists:
    if playlist.name == "My Favorites":
        tracks = tidal_service.get_tracks(playlist.id)
        print(f"Playlist has {len(tracks)} tracks")

        # Convert tracks
        for track in tracks:
            file_path = file_service.convert_track(track)
            print(f"Converted: {file_path}")
```

## Architecture & Migration

The modern version maintains compatibility with your existing workflow while providing significant improvements:

### Key Improvements

1. **Modular Architecture**: Code is organized into logical modules
2. **Configuration Management**: Hard-coded paths replaced with configurable settings
3. **Error Handling**: Comprehensive error handling throughout
4. **Logging**: Structured logging with different levels
5. **CLI Interface**: Rich terminal interface with progress indicators
6. **Type Safety**: Pydantic models for data validation
7. **Testing**: Comprehensive test coverage with pytest
8. **Quality Assurance**: Pre-commit hooks and CI/CD pipeline
9. **Security**: Automated vulnerability scanning
10. **Documentation**: Complete API documentation and examples

### Backward Compatibility

1. **Core Functionality**: All original features are maintained
2. **File Formats**: Same audio format support
3. **Tidal Integration**: Compatible with existing Tidal sessions
4. **Rekordbox Output**: Same XML format for Rekordbox

## Advanced Configuration

The application uses a configuration file that can be customized:

```python
# Default configuration (can be overridden)
{
    "tidal_token_file": "tidal_session.json",
    "output_directory": "./output",
    "rekordbox_xml_path": "./rekordbox.xml",
    "log_level": "INFO",
    "max_workers": 4
}
```

You can customize settings by creating a `config.yaml` file or using environment variables.

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

## Contributing

We welcome contributions! Please read `CONTRIBUTING.md` for guidelines on:

- Setting up the development environment
- Running tests and quality checks
- Submitting pull requests
- Code style and standards

### Security

For security concerns, please see `SECURITY.md` for reporting guidelines.

## License

MIT License — see LICENSE file for details.
