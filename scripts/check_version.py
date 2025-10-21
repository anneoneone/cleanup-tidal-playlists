#!/usr/bin/env python3
"""Check version consistency across project files."""

import re
import sys
from pathlib import Path


def get_version_from_pyproject():
    """Get version from pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        return None
    
    content = pyproject_path.read_text()
    match = re.search(r'version = "([^"]+)"', content)
    return match.group(1) if match else None


def get_version_from_init():
    """Get version from __init__.py."""
    init_path = Path("src/tidal_cleanup/__init__.py")
    if not init_path.exists():
        return None
    
    content = init_path.read_text()
    match = re.search(r'__version__ = "([^"]+)"', content)
    return match.group(1) if match else None


def main():
    """Check version consistency."""
    pyproject_version = get_version_from_pyproject()
    init_version = get_version_from_init()
    
    print(f"pyproject.toml version: {pyproject_version}")
    print(f"__init__.py version: {init_version}")
    
    if pyproject_version != init_version:
        print("ERROR: Version mismatch!")
        sys.exit(1)
    
    if not pyproject_version:
        print("ERROR: No version found!")
        sys.exit(1)
    
    print("✓ Version consistency check passed")


if __name__ == "__main__":
    main()
