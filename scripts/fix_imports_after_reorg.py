#!/usr/bin/env python3
"""Script to fix imports after reorganization."""

import re
from pathlib import Path

# Define the replacements needed
REPLACEMENTS = [
    # Core/sync module - internal references
    {
        "pattern": r"from \.sync_decision_engine import",
        "replacement": "from .decision_engine import",
        "files": ["src/tidal_cleanup/core/sync/*.py"],
    },
    {
        "pattern": r"from \.sync_orchestrator import",
        "replacement": "from .orchestrator import",
        "files": ["src/tidal_cleanup/core/sync/*.py"],
    },
    {
        "pattern": r"from \.sync_state import",
        "replacement": "from .state import",
        "files": ["src/tidal_cleanup/core/sync/*.py"],
    },
    {
        "pattern": r"from \.deduplication_logic import",
        "replacement": "from .deduplication import",
        "files": ["src/tidal_cleanup/core/sync/*.py"],
    },
    # Database references from core/sync
    {
        "pattern": r"from \.service import DatabaseService",
        "replacement": "from ...database.service import DatabaseService",
        "files": ["src/tidal_cleanup/core/sync/*.py"],
    },
    {
        "pattern": r"from \.models import",
        "replacement": "from ...database.models import",
        "files": ["src/tidal_cleanup/core/sync/*.py"],
    },
    # Core/rekordbox module
    {
        "pattern": r"from \.rekordbox_playlist_sync import",
        "replacement": "from .playlist_sync import",
        "files": ["src/tidal_cleanup/core/rekordbox/*.py"],
    },
    {
        "pattern": r"from \.playlist_name_parser import",
        "replacement": "from .playlist_parser import",
        "files": ["src/tidal_cleanup/core/rekordbox/*.py"],
    },
    {
        "pattern": r"from \.\.config import",
        "replacement": "from ...config import",
        "files": ["src/tidal_cleanup/core/rekordbox/*.py"],
    },
    # Legacy module
    {
        "pattern": r"from \.\.config import",
        "replacement": "from ..config import",
        "files": ["src/tidal_cleanup/legacy/*.py"],
    },
    {
        "pattern": r"from \.\.models\.models import",
        "replacement": "from ..models.models import",
        "files": ["src/tidal_cleanup/legacy/*.py"],
    },
    {
        "pattern": r"from \.directory_diff_service import",
        "replacement": "from .directory_diff import",
        "files": ["src/tidal_cleanup/legacy/*.py"],
    },
    {
        "pattern": r"from \.track_comparison_service import",
        "replacement": "from .track_comparison import",
        "files": ["src/tidal_cleanup/legacy/*.py"],
    },
]


def fix_imports_in_file(file_path: Path):
    """Fix imports in a single file."""
    content = file_path.read_text()
    modified = False

    for replacement_rule in REPLACEMENTS:
        # Check if this rule applies to this file
        applies = False
        for pattern in replacement_rule["files"]:
            if file_path.match(pattern.replace("src/", "")):
                applies = True
                break

        if not applies:
            continue

        # Apply the replacement
        old_content = content
        content = re.sub(
            replacement_rule["pattern"], replacement_rule["replacement"], content
        )
        if content != old_content:
            modified = True
            print(f"  ✓ Applied: {replacement_rule['pattern']}")

    if modified:
        file_path.write_text(content)
        return True
    return False


def main():
    """Main entry point."""
    base_path = Path("src/tidal_cleanup")

    # Process all Python files in core/ and legacy/
    directories = [
        base_path / "core" / "sync",
        base_path / "core" / "rekordbox",
        base_path / "legacy",
    ]

    total_files = 0
    modified_files = 0

    for directory in directories:
        if not directory.exists():
            continue

        for py_file in directory.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue

            total_files += 1
            print(f"\nProcessing: {py_file.relative_to(base_path)}")
            if fix_imports_in_file(py_file):
                modified_files += 1
                print(f"  → Modified")

    print(f"\n{'='*60}")
    print(f"Total files processed: {total_files}")
    print(f"Files modified: {modified_files}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
