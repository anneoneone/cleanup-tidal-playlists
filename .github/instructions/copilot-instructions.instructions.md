<!-- markdownlint-disable MD041 -->
---

applyTo: "**"
---

# Tidal Playlist Cleanup Project

## Overview

This is a **Python 3.12 CLI tool** for syncing Tidal playlists with Rekordbox DJ software. The project manages playlist synchronization, track downloads, emoji-based metadata parsing, and bidirectional state tracking between Tidal and Rekordbox databases.

**Core Workflow**: Tidal API → Local SQLite DB → Download Tracks → Parse Playlist Names → Sync to Rekordbox MyTags

## Tech Stack

### Core Dependencies

- **Python**: 3.12+ with strict type hints (mypy)
- **ORM**: SQLAlchemy 2.0 (modern `Mapped[]` syntax)
- **Migrations**: Alembic 1.13+
- **CLI**: Click 8.0+ with Rich 12.0+ for output
- **Validation**: Pydantic 2.0 for data models

### API Integrations

- **Tidal**: tidalapi 0.7+ (OAuth authentication, playlist fetching)
- **Downloads**: tidal-dl-ng 0.31+ (track downloads)
- **Rekordbox**: pyrekordbox 0.1+ (MyTag database operations)

### Code Quality

- **Formatting**: Black 24.0+ (88-char lines), isort (black profile)
- **Linting**: flake8 with plugins (bugbear, comprehensions, simplify)
- **Type Checking**: mypy (strict mode)
- **Security**: bandit for security scanning
- **Testing**: pytest 7.0+ with 80%+ coverage requirement

## Essential Commands

```bash
# Full pipeline check (used in CI/CD)
make pipeline-check    # Runs black, isort, flake8, mypy, pytest

# CLI Tool
tidal-cleanup sync                     # Full Tidal → Rekordbox sync
tidal-cleanup tidal login              # Authenticate with Tidal
tidal-cleanup rekordbox init-mytags    # Initialize MyTag structure

# Testing
pytest -v --cov=src                    # Run tests with coverage
pytest tests/test_playlist_name_parser.py  # Run specific test

# Code Quality
black src/ tests/                      # Format code
isort src/ tests/                      # Sort imports
flake8 src/ tests/                     # Lint code
mypy src/                              # Type check

# Database Migrations
alembic upgrade head                   # Apply all migrations
alembic revision --autogenerate -m "description"  # Create migration

# Pre-commit Hooks
pre-commit run --all-files             # Run all hooks
```

## Architecture Overview

### Domain Structure

```
src/tidal_cleanup/
├── cli/                    # Click commands (@cli-agent - future)
├── core/
│   ├── tidal/             # Tidal API integration (@tidal-agent)
│   ├── rekordbox/         # Rekordbox operations (3 agents)
│   │   ├── playlist_parser.py      (@rekordbox-parser-agent)
│   │   ├── playlist_sync.py        (@rekordbox-sync-agent)
│   │   ├── mytag_manager.py        (@rekordbox-database-agent)
│   │   └── service.py              (@rekordbox-database-agent)
│   └── sync/              # Orchestration (@sync-orchestrator-agent - future)
├── database/              # SQLAlchemy models & migrations (@database-agent)
└── utils/                 # Shared utilities
```

### Specialist Agents

We have **10 specialist agents** for different domains. Use `@agent-name` to invoke:

- **@analyzer**: Meta-agent for task routing and orchestration
- **@agent-writer**: Creates new agent.md files
- **@test-agent**: pytest testing (80%+ coverage)
- **@docs-agent**: Technical documentation (27 markdown files)
- **@lint-agent**: Code quality (Black, isort, flake8, mypy)
- **@rekordbox-parser-agent**: Emoji parsing, metadata extraction
- **@rekordbox-sync-agent**: Playlist sync workflows
- **@rekordbox-database-agent**: MyTag CRUD via pyrekordbox
- **@tidal-agent**: OAuth, API, downloads
- **@database-agent**: SQLAlchemy models, Alembic migrations

**Agent Coordination**: For complex tasks spanning multiple domains, start with `@analyzer` to coordinate specialist agents.

## Universal Coding Standards

### Code Style

- **Line length**: 88 characters (Black default)
- **Import order**: isort with black profile (stdlib → third-party → local)
- **Docstrings**: Google style for all public functions/classes
- **Type hints**: Required on all functions (strict mypy)
- **Naming**: snake_case for functions/variables, PascalCase for classes

### Testing Requirements

- **Coverage**: 80%+ required (`pytest --cov=src`)
- **Framework**: pytest with fixtures from existing test files
- **Mocking**: Use `unittest.mock` or `pytest-mock`
- **Organization**: One test file per module (`test_module_name.py`)

### Database Operations

- **ORM Only**: Use SQLAlchemy 2.0, not raw SQL
- **Migrations**: Always use Alembic for schema changes
- **Type Safety**: Use `Mapped[Type]` with `mapped_column()`
- **Transactions**: Wrap multi-statement operations

### Error Handling

- **Logging**: Use Python logging module (DEBUG, INFO, WARNING, ERROR)
- **Exceptions**: Raise specific exceptions, not generic `Exception`
- **Retry Logic**: Use tenacity for network operations (Tidal API)
- **Validation**: Pydantic models for data validation

## Git Workflow

When I give the command to commit changes, do:

- Use gitkraken
- Group related changes into a single commit
- Ensure each commit has a clear purpose
- Summarize the changes in the commit message
- Avoid including unrelated changes in a single commit

Before you commit changes, run pre-commit hooks to ensure code quality and consistency.

- If any hooks fail, fix the issues before committing.

## Key Project Files

- **pyproject.toml**: Dependencies, Black/isort config, pytest settings
- **alembic.ini**: Alembic migration configuration
- **config/rekordbox_mytag_mapping.json**: Emoji → MyTag mappings
- **.github/agents/**: Specialist agent definitions (10 files)
