#!/usr/bin/env python3
"""Helper script to identify and report on logging statements that need conversion.

Provides specific line numbers and context for manual review and conversion.
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def analyze_file(file_path: Path) -> List[Tuple[int, str, str]]:
    """Analyze a Python file for f-string logging statements.

    Args:
        file_path: Path to Python file

    Returns:
        List of (line_number, line_content, log_level) tuples
    """
    results = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                # Match logger.level(f"...") or logger.level(f'...')
                match = re.search(
                    r'logger\.(debug|info|warning|error|critical)\s*\(\s*f["\']', line
                )
                if match:
                    results.append((i, line.rstrip(), match.group(1)))
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)

    return results


def analyze_directory(directory: Path) -> Dict[Path, List[Tuple[int, str, str]]]:
    """Recursively analyze all Python files in directory.

    Args:
        directory: Root directory to search

    Returns:
        Dict mapping file paths to their f-string logging statements
    """
    results = {}

    for py_file in directory.rglob("*.py"):
        if "test_" in py_file.name or py_file.name.startswith("test"):
            # Skip test files for now
            continue

        findings = analyze_file(py_file)
        if findings:
            results[py_file] = findings

    return results


def print_report(results: Dict[Path, List[Tuple[int, str, str]]]) -> None:
    """Print a formatted report of findings.

    Args:
        results: Analysis results from analyze_directory
    """
    if not results:
        print("✅ No f-string logging found!")
        return

    total_instances = sum(len(findings) for findings in results.values())

    print(
        f"Found {total_instances} f-string logging statements in {len(results)} files"
    )
    print("=" * 80)
    print()

    # Sort by number of instances (descending)
    sorted_files = sorted(results.items(), key=lambda x: len(x[1]), reverse=True)

    for file_path, findings in sorted_files:
        try:
            rel_path = file_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = file_path
        print(f"📄 {rel_path} ({len(findings)} instances)")
        print("-" * 80)

        for line_num, line_content, log_level in findings:
            # Truncate long lines for display
            display_line = (
                line_content[:100] + "..." if len(line_content) > 100 else line_content
            )
            print(f"  Line {line_num:4d} [{log_level:8s}]: {display_line}")

        print()


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        target = Path("src")

    if not target.exists():
        print(f"Error: {target} does not exist")
        sys.exit(1)

    if target.is_file():
        results = {target: analyze_file(target)}
    else:
        results = analyze_directory(target)

    print_report(results)

    # Summary by priority
    print("\n" + "=" * 80)
    print("CONVERSION PRIORITY")
    print("=" * 80)

    high_priority = [
        "file_service.py",
        "rekordbox_playlist_sync.py",
        "rekordbox_service.py",
        "tidal_download_service.py",
    ]

    print("\n🔴 HIGH PRIORITY (Core Services):")
    for file_path, findings in results.items():
        if any(hp in file_path.name for hp in high_priority):
            print(f"  - {file_path.name}: {len(findings)} instances")

    print("\n🟡 MEDIUM PRIORITY (Database Layer):")
    for file_path, findings in results.items():
        if "database" in str(file_path) and not any(
            hp in file_path.name for hp in high_priority
        ):
            print(f"  - {file_path.name}: {len(findings)} instances")

    print("\n🟢 LOWER PRIORITY (Other):")
    for file_path, findings in results.items():
        is_high = any(hp in file_path.name for hp in high_priority)
        is_db = "database" in str(file_path)
        if not is_high and not is_db:
            print(f"  - {file_path.name}: {len(findings)} instances")


if __name__ == "__main__":
    main()
