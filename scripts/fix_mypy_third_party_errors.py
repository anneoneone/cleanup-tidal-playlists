#!/usr/bin/env python3
"""Fix mypy errors from third-party libraries without type stubs."""

import re
from pathlib import Path


def fix_mutagen_imports(file_path: Path) -> bool:
    """Add type: ignore for mutagen.File imports."""
    with open(file_path, "r") as f:
        content = f.read()

    original = content

    # Fix: from mutagen import File as MutagenFile
    content = re.sub(
        r"^from mutagen import File as (\w+)$",
        r"from mutagen import File as \1  # type: ignore[attr-defined]",
        content,
        flags=re.MULTILINE,
    )

    if content != original:
        with open(file_path, "w") as f:
            f.write(content)
        return True
    return False


def fix_tidalapi_imports(file_path: Path) -> bool:
    """Add type: ignore for tidalapi imports."""
    with open(file_path, "r") as f:
        content = f.read()

    original = content

    # Fix: from tidalapi import Playlist, Session
    content = re.sub(
        r"^from tidalapi import (.*?)$",
        r"from tidalapi import \1  # type: ignore[attr-defined]",
        content,
        flags=re.MULTILINE,
    )

    if content != original:
        with open(file_path, "w") as f:
            f.write(content)
        return True
    return False


def fix_id3_calls(file_path: Path) -> bool:
    """Add type: ignore for ID3 and .get() calls on ID3 objects."""
    with open(file_path, "r") as f:
        lines = f.readlines()

    modified = False
    new_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check if this is an ID3() call that needs fixing
        if "ID3(" in line and "type: ignore" not in line:
            # Add type: ignore to this line
            line = line.rstrip() + "  # type: ignore[no-untyped-call]\n"
            modified = True
            new_lines.append(line)

            # Check next few lines for .get() calls
            j = i + 1
            while j < len(lines) and j < i + 5:  # Look ahead up to 5 lines
                next_line = lines[j]
                # If it's a .get() call without type: ignore
                if ".get(" in next_line and "type: ignore" not in next_line:
                    next_line = (
                        next_line.rstrip() + "  # type: ignore[no-untyped-call]\n"
                    )
                    modified = True
                new_lines.append(next_line)
                j += 1
                # Stop if we hit a blank line or new statement
                if next_line.strip() == "" or (
                    not next_line.startswith(" " * 8) and next_line.strip()
                ):
                    break
            i = j
            continue

        new_lines.append(line)
        i += 1

    if modified:
        with open(file_path, "w") as f:
            f.writelines(new_lines)
        return True
    return False


def fix_playlist_track_kwargs(file_path: Path) -> bool:
    """Add type: ignore for Playlist/Track constructor calls with extra kwargs."""
    with open(file_path, "r") as f:
        lines = f.readlines()

    modified = False
    new_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for Playlist( or Track( constructor calls
        if ("Playlist(" in line or "Track(" in line) and "type: ignore" not in line:
            # Check if this is a multi-line call
            if line.rstrip().endswith(",") or "(" in line and ")" not in line:
                # Multi-line constructor - find the closing paren
                constructor_lines = [line]
                j = i + 1
                while j < len(lines):
                    constructor_lines.append(lines[j])
                    if ")" in lines[j]:
                        # Found closing paren - add type: ignore before it
                        last_line = constructor_lines[-1]
                        # Add comment on the line with closing paren
                        if "type: ignore" not in last_line:
                            last_line = last_line.rstrip()
                            if last_line.endswith(")"):
                                last_line = (
                                    last_line[:-1]
                                    + "  # type: ignore[call-arg]\n"
                                    + last_line[-1]
                                    + "\n"
                                )
                            else:
                                last_line = last_line + "  # type: ignore[call-arg]\n"
                            constructor_lines[-1] = last_line
                            modified = True

                        new_lines.extend(constructor_lines)
                        i = j + 1
                        break
                    j += 1
                continue

        new_lines.append(line)
        i += 1

    if modified:
        with open(file_path, "w") as f:
            f.writelines(new_lines)
        return True
    return False


def main():
    """Fix all third-party library type errors."""
    src_dir = Path("src/tidal_cleanup")

    files_to_fix = {
        "mutagen": [
            src_dir / "core/filesystem/file_scanner.py",
            src_dir / "core/rekordbox/service.py",
            src_dir / "legacy/file_service.py",
        ],
        "tidalapi": [
            src_dir / "core/tidal/api_client.py",
            src_dir / "core/tidal/download_service.py",
        ],
        "id3": [
            src_dir / "core/rekordbox/playlist_sync.py",
        ],
        "kwargs": [
            src_dir / "core/tidal/api_client.py",
        ],
    }

    fixed_count = 0

    print("Fixing mutagen imports...")
    for file_path in files_to_fix["mutagen"]:
        if file_path.exists():
            if fix_mutagen_imports(file_path):
                print(f"  ✓ {file_path.name}")
                fixed_count += 1

    print("\nFixing tidalapi imports...")
    for file_path in files_to_fix["tidalapi"]:
        if file_path.exists():
            if fix_tidalapi_imports(file_path):
                print(f"  ✓ {file_path.name}")
                fixed_count += 1

    print("\nFixing ID3 calls...")
    for file_path in files_to_fix["id3"]:
        if file_path.exists():
            if fix_id3_calls(file_path):
                print(f"  ✓ {file_path.name}")
                fixed_count += 1

    print("\nFixing Playlist/Track constructor kwargs...")
    for file_path in files_to_fix["kwargs"]:
        if file_path.exists():
            if fix_playlist_track_kwargs(file_path):
                print(f"  ✓ {file_path.name}")
                fixed_count += 1

    print(f"\nFixed {fixed_count} files")


if __name__ == "__main__":
    main()
