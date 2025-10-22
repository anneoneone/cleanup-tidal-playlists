# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Modern project management structure with pyproject.toml
- Comprehensive pre-commit hooks with 15+ quality checks
- GitHub Actions CI/CD pipeline with matrix testing
- Development tooling (Makefile, tox, utility scripts)
- Strict linting configuration (flake8, mypy, bandit)
- Security scanning with Safety and Bandit
- Contribution guidelines and security policy
- Automated dependency vulnerability scanning

### Changed

- Migrated from requirements.txt to pyproject.toml
- Enhanced development workflow with make targets
- Improved code quality standards and enforcement

## [2.0.0] - 2025-10-21

### Added

- Modern package architecture with service-oriented design
- Pydantic models for type safety and data validation
- Rich CLI interface with progress bars and colored output
- Environment-based configuration management
- Structured logging with file rotation
- Comprehensive error handling and recovery
- Fuzzy track matching with thefuzz
- Professional documentation (README, migration guide)
- Test framework with pytest
- Installable package with entry points

### Changed

- **BREAKING**: Complete architecture refactor from monolithic to modular
- **BREAKING**: Configuration moved from hardcoded paths to environment variables
- **BREAKING**: CLI interface completely redesigned with subcommands
- Improved track normalization and comparison algorithms
- Enhanced Rekordbox XML generation with better metadata handling
- Better audio conversion workflow with status tracking

### Removed

- Legacy monolithic main.py and cleanup_tidal_playlists.py
- Hardcoded file paths and German comments
- Basic print-based error handling

### Fixed

- Improved session management for Tidal API
- Better error handling for missing files and directories
- More robust audio file processing

### Security

- Added security scanning to CI/CD pipeline
- Implemented secure configuration management
- Added dependency vulnerability checking

## [1.0.0] - Legacy

### Added

- Basic Tidal playlist synchronization
- M4A to MP3 audio conversion
- Rekordbox XML generation
- Local file cleanup based on Tidal playlists

### Features

- Tidal API integration with OAuth
- Track name normalization
- File format conversion using FFmpeg
- Interactive file deletion confirmation
