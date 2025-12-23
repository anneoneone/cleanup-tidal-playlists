#!/usr/bin/env python3
"""Fix remaining test import errors after reorganization."""

import re
from pathlib import Path


def fix_test_file(file_path: Path) -> bool:
    """Fix imports in a single test file."""
    with open(file_path, "r") as f:
        content = f.read()

    original_content = content

    # Fix monkeypatch/mock references to src.tidal_cleanup.services modules
    # Pattern: monkeypatch.setattr("src.tidal_cleanup.services.X", ...)
    replacements = {
        # Services that moved to core.tidal
        r"src\.tidal_cleanup\.services\.tidal_service": "tidal_cleanup.core.tidal.api_client",
        r"src\.tidal_cleanup\.services\.tidal_download_service": "tidal_cleanup.core.tidal.download_service",
        # Services that moved to core.rekordbox
        r"src\.tidal_cleanup\.services\.mytag_manager": "tidal_cleanup.core.rekordbox.mytag_manager",
        r"src\.tidal_cleanup\.services\.rekordbox_playlist_sync": "tidal_cleanup.core.rekordbox.playlist_sync",
        r"src\.tidal_cleanup\.services\.rekordbox_service": "tidal_cleanup.core.rekordbox.service",
        # Services that moved to legacy
        r"tidal_cleanup\.services\.file_service": "tidal_cleanup.legacy.file_service",
        # Database modules that moved to core
        r"tidal_cleanup\.database\.file_scanner_service": "tidal_cleanup.core.filesystem.file_scanner",
    }

    for old_pattern, new_path in replacements.items():
        # Replace in string literals (monkeypatch, mock paths, etc.)
        content = re.sub(old_pattern, new_path, content)

    if content != original_content:
        with open(file_path, "w") as f:
            f.write(content)
        return True
    return False


def main():
    """Fix all test files with import errors."""
    tests_dir = Path("tests")
    fixed_count = 0

    # Target specific files that have errors
    error_files = [
        "test_basic.py",
        "test_file_scanner_service.py",
        "test_file_service.py",
        "test_mytag_manager.py",
        "test_rekordbox_playlist_sync.py",
        "test_rekordbox_service.py",
        "test_tidal_download_service.py",
    ]

    for filename in error_files:
        test_file = tests_dir / filename
        if not test_file.exists():
            print(f"⚠ {filename} not found")
            continue

        print(f"Processing {filename}...", end=" ")
        if fix_test_file(test_file):
            print("✓ Fixed")
            fixed_count += 1
        else:
            print("No changes needed")

    print(f"\n✓ Fixed {fixed_count} test files")
    print("\nRun: pytest tests/ -v --tb=short")


if __name__ == "__main__":
    main()
