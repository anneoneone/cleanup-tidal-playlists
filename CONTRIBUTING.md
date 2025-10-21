# Contributing to Tidal Cleanup

Thank you for your interest in contributing to Tidal Cleanup! This document provides guidelines and information for contributors.

## Development Setup

### Prerequisites

- Python 3.8 or higher
- Git
- FFmpeg (for audio conversion functionality)

### Quick Setup

```bash
# Clone the repository
git clone https://github.com/anneoneone/cleanup-tidal-playlists.git
cd cleanup-tidal-playlists

# Set up development environment
make dev-setup

# Or manually:
pip install -e ".[dev]"
pre-commit install
```

## Development Workflow

### Code Quality Standards

We maintain high code quality through automated tools:

- **Code Formatting**: Black (line length 88)
- **Import Sorting**: isort (Black profile)
- **Linting**: flake8 with plugins
- **Type Checking**: mypy (strict mode)
- **Security**: bandit + safety
- **Testing**: pytest with 80%+ coverage

### Before You Commit

Run the pre-commit checks:

```bash
make pr-check
```

Or use the individual commands:

```bash
make format    # Format code
make lint      # Run linting
make test-cov  # Run tests with coverage
make security  # Security checks
```

### Pre-commit Hooks

Pre-commit hooks run automatically on every commit. To run them manually:

```bash
pre-commit run --all-files
```

## Pull Request Process

1. **Fork and Branch**: Create a feature branch from `main`
2. **Develop**: Make your changes following our coding standards
3. **Test**: Ensure all tests pass and coverage is maintained
4. **Document**: Update documentation if needed
5. **Commit**: Use conventional commit messages
6. **Push**: Push to your fork
7. **PR**: Create a pull request with a clear description

### Commit Message Format

We use conventional commits:

```
type(scope): description

- feat: new feature
- fix: bug fix
- docs: documentation changes
- style: formatting changes
- refactor: code refactoring
- test: adding tests
- chore: maintenance tasks
```

Examples:
```
feat(cli): add new sync command
fix(tidal): handle authentication timeout
docs(readme): update installation instructions
```

## Code Style Guide

### Python Style

- Follow PEP 8 (enforced by flake8)
- Use Black for formatting (88 character line limit)
- Type hints required (mypy strict mode)
- Docstrings required for public APIs (Google style)

### Example Code Style

```python
"""Module docstring describing the module purpose."""

from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class ExampleClass:
    """Class docstring describing the class purpose.
    
    Args:
        param1: Description of parameter 1.
        param2: Description of parameter 2.
    """
    
    def __init__(self, param1: str, param2: Optional[int] = None) -> None:
        self.param1 = param1
        self.param2 = param2
    
    def example_method(self, data: List[str]) -> bool:
        """Method docstring describing what it does.
        
        Args:
            data: List of strings to process.
            
        Returns:
            True if successful, False otherwise.
            
        Raises:
            ValueError: If data is empty.
        """
        if not data:
            raise ValueError("Data cannot be empty")
        
        logger.info(f"Processing {len(data)} items")
        return True
```

## Testing Guidelines

### Test Structure

- Tests are in the `tests/` directory
- Use pytest with descriptive test names
- Maintain 80%+ code coverage
- Include unit tests, integration tests, and CLI tests

### Writing Tests

```python
"""Test module for example functionality."""

import pytest
from unittest.mock import Mock, patch

from tidal_cleanup.services.example_service import ExampleService


class TestExampleService:
    """Test cases for ExampleService."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = ExampleService()
    
    def test_example_method_success(self):
        """Test successful operation."""
        result = self.service.example_method(["test"])
        assert result is True
    
    def test_example_method_empty_data(self):
        """Test handling of empty data."""
        with pytest.raises(ValueError, match="Data cannot be empty"):
            self.service.example_method([])
    
    @patch('tidal_cleanup.services.example_service.external_api')
    def test_example_method_with_mock(self, mock_api):
        """Test with mocked external dependency."""
        mock_api.return_value = Mock(success=True)
        result = self.service.example_method(["test"])
        assert result is True
        mock_api.assert_called_once()
```

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
pytest tests/test_specific.py

# Run tests across all Python versions
make test-all
```

## Documentation

### Code Documentation

- All public APIs must have docstrings
- Use Google-style docstrings
- Include type hints for all function parameters and return values
- Document exceptions that can be raised

### User Documentation

- Update README.md for user-facing changes
- Update migration guide if breaking changes
- Add examples for new features

## Security Considerations

- Never commit secrets or API keys
- Use environment variables for configuration
- Run security scans before merging
- Follow principle of least privilege

## Architecture Guidelines

### Service-Oriented Design

- Keep services focused on single responsibilities
- Use dependency injection for testability
- Implement proper error handling and logging
- Use Pydantic models for data validation

### Adding New Features

1. **Models**: Add/update Pydantic models if needed
2. **Services**: Implement business logic in appropriate service
3. **CLI**: Add CLI commands if user-facing
4. **Tests**: Write comprehensive tests
5. **Documentation**: Update relevant documentation

## Release Process

Releases are automated through GitHub Actions:

1. **Version Bump**: Update version in `pyproject.toml` and `__init__.py`
2. **Changelog**: Update CHANGELOG.md
3. **Tag**: Create and push a git tag
4. **CI/CD**: GitHub Actions handles building and publishing

## Getting Help

- **Issues**: Use GitHub Issues for bug reports and feature requests
- **Discussions**: Use GitHub Discussions for questions
- **Code Review**: Maintainers will review pull requests

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Follow the golden rule

Thank you for contributing to Tidal Cleanup!
