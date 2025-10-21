# Pipeline and Pre-commit Synchronization

This document outlines how the CI/CD pipeline and pre-commit hooks are synchronized to ensure consistent code quality enforcement.

## Synchronized Tools

### Code Formatting

- **Pipeline**: `black --check --diff src/ tests/`
- **Pre-commit**: `black` (runs on all Python files)
- **Status**: ✅ Synchronized

### Import Sorting

- **Pipeline**: `isort --check-only --diff src/ tests/`
- **Pre-commit**: `isort --profile black` (runs on all Python files)
- **Status**: ✅ Synchronized

### Linting (Flake8)

- **Pipeline**: `flake8 src/ tests/`
- **Pre-commit**: `flake8` (runs on all Python files)
- **Configuration**: Shared via `setup.cfg`
- **Status**: ✅ Synchronized

### Type Checking (MyPy)

- **Pipeline**: `mypy src/ --config-file=pyproject.toml`
- **Pre-commit**: `mypy` with `files: ^src/` and `exclude: ^tests/`
- **Configuration**: Shared via `pyproject.toml`
- **Test Exclusion**: Tests are excluded from strict type checking in both environments
- **Status**: ✅ Synchronized

## Configuration Files

### pyproject.toml

Contains shared mypy configuration with specific overrides:

```toml
[tool.mypy]
# Strict type checking for production code

[[tool.mypy.overrides]]
module = ["tests.*"]
ignore_errors = true
disallow_untyped_calls = false
disallow_untyped_defs = false
```

### setup.cfg

Contains shared flake8 configuration:

```ini
[flake8]
max-line-length = 88
# Additional flake8 settings
```

### .pre-commit-config.yaml

Pre-commit hooks configured to match pipeline behavior:

```yaml
- id: mypy
  files: ^src/
  exclude: ^tests/
  additional_dependencies: [pydantic, click, rich, tidalapi, mutagen]
```

## Test Type Annotation Policy

**Tests are excluded from strict type checking in both environments:**

1. **Pipeline**: Only runs `mypy src/`, excludes `tests/` directory
2. **Pre-commit**: Uses `files: ^src/` and `exclude: ^tests/` patterns
3. **Configuration**: `pyproject.toml` has override for `tests.*` modules

This ensures that:

- Test functions don't require return type annotations
- Test code can use more flexible typing practices
- Production code (`src/`) maintains strict type safety
- Both environments apply identical policies

## Verification

To verify synchronization:

```bash
# Test pipeline commands locally
mypy src/ --config-file=pyproject.toml
flake8 src/ tests/
black --check --diff src/ tests/
isort --check-only --diff src/ tests/

# Test pre-commit hooks
pre-commit run --all-files
```

Both should produce identical results.
