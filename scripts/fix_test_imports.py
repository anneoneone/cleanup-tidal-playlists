#!/usr/bin/env python3
"""Fix test imports after reorganization."""

import re
from pathlib import Path

# Mapping of old imports to new imports
IMPORT_MAPPINGS = {
    # Services that moved to core modules
    "tidal_cleanup.services.track_comparison_service": "tidal_cleanup.legacy.track_comparison",
    "tidal_cleanup.services.directory_diff_service": "tidal_cleanup.legacy.directory_diff",
    "tidal_cleanup.services.file_service": "tidal_cleanup.legacy.file_service",
    "tidal_cleanup.services.playlist_synchronizer": "tidal_cleanup.legacy.playlist_synchronizer",
    # Rekordbox services moved to core.rekordbox
    "tidal_cleanup.services.mytag_manager": "tidal_cleanup.core.rekordbox.mytag_manager",
    "tidal_cleanup.services.rekordbox_playlist_sync": "tidal_cleanup.core.rekordbox.playlist_sync",
    "tidal_cleanup.services.rekordbox_service": "tidal_cleanup.core.rekordbox.service",
    "tidal_cleanup.services.playlist_name_parser": "tidal_cleanup.core.rekordbox.playlist_parser",
    # Tidal services moved to core.tidal
    "tidal_cleanup.services.tidal_download_service": "tidal_cleanup.core.tidal.download_service",
    "tidal_cleanup.services.tidal_service": "tidal_cleanup.core.tidal.api_client",
    # Database modules that moved to core
    "tidal_cleanup.database.tidal_state_fetcher": "tidal_cleanup.core.tidal.state_fetcher",
    "tidal_cleanup.database.tidal_snapshot_service": "tidal_cleanup.core.tidal.snapshot_service",
    "tidal_cleanup.database.filesystem_scanner": "tidal_cleanup.core.filesystem.scanner",
    "tidal_cleanup.database.file_scanner_service": "tidal_cleanup.core.filesystem.file_scanner",
    "tidal_cleanup.database.sync_orchestrator": "tidal_cleanup.core.sync.orchestrator",
    "tidal_cleanup.database.sync_decision_engine": "tidal_cleanup.core.sync.decision_engine",
    "tidal_cleanup.database.download_orchestrator": "tidal_cleanup.core.sync.download_orchestrator",
    "tidal_cleanup.database.sync_state": "tidal_cleanup.core.sync.state",
    "tidal_cleanup.database.conflict_resolver": "tidal_cleanup.core.sync.conflict_resolver",
    "tidal_cleanup.database.deduplication_logic": "tidal_cleanup.core.sync.deduplication",
    # Old src. prefix imports
    "src.tidal_cleanup.services": "tidal_cleanup.core.rekordbox",
    "src.tidal_cleanup.database": "tidal_cleanup.core.sync",
}

# Classes that need to be imported from new locations
CLASS_EXPORTS = {
    "DeduplicationLogic": "tidal_cleanup.core.sync.deduplication",
    "TidalSnapshotService": "tidal_cleanup.core.tidal.snapshot_service",
    "TidalStateFetcher": "tidal_cleanup.core.tidal.state_fetcher",
    "SyncOrchestrator": "tidal_cleanup.core.sync.orchestrator",
    "SyncDecisionEngine": "tidal_cleanup.core.sync.decision_engine",
    "DownloadOrchestrator": "tidal_cleanup.core.sync.download_orchestrator",
    "SyncAction": "tidal_cleanup.core.sync.decision_engine",
    "SyncResult": "tidal_cleanup.core.sync.orchestrator",
    "Change": "tidal_cleanup.core.sync.state",
    "ChangeType": "tidal_cleanup.core.sync.state",
    "ConflictResolver": "tidal_cleanup.core.sync.conflict_resolver",
    "FilesystemScanner": "tidal_cleanup.core.filesystem.scanner",
    "FileScannerService": "tidal_cleanup.core.filesystem.file_scanner",
}


def fix_imports_in_file(file_path: Path) -> bool:
    """Fix imports in a single test file."""
    with open(file_path, "r") as f:
        content = f.read()

    original_content = content

    # Fix direct module imports
    for old_import, new_import in IMPORT_MAPPINGS.items():
        # Handle 'from X import Y' style
        pattern = re.compile(rf"from {re.escape(old_import)} import")
        content = pattern.sub(f"from {new_import} import", content)

        # Handle 'import X' style
        pattern = re.compile(rf"^import {re.escape(old_import)}$", re.MULTILINE)
        content = pattern.sub(f"import {new_import}", content)

    # Fix imports from database that reference moved classes
    # Look for: from tidal_cleanup.database import X, Y, Z
    db_import_pattern = re.compile(
        r"from tidal_cleanup\.database import \(([^)]+)\)", re.MULTILINE | re.DOTALL
    )

    def fix_db_imports(match):
        imports_str = match.group(1)
        # Split by comma and clean up
        imports = [i.strip() for i in imports_str.split(",") if i.strip()]

        # Group by new module
        by_module = {}
        kept_in_database = []

        for imp in imports:
            if imp in CLASS_EXPORTS:
                new_module = CLASS_EXPORTS[imp]
                if new_module not in by_module:
                    by_module[new_module] = []
                by_module[new_module].append(imp)
            else:
                # Keep in database import (like DatabaseService)
                kept_in_database.append(imp)

        # Build new import statements
        result = []
        for module, classes in sorted(by_module.items()):
            result.append(f"from {module} import {', '.join(classes)}")

        if kept_in_database:
            result.append(
                f"from tidal_cleanup.database import {', '.join(kept_in_database)}"
            )

        return "\n".join(result)

    content = db_import_pattern.sub(fix_db_imports, content)

    # Also handle single-line database imports
    single_db_import = re.compile(
        r"from tidal_cleanup\.database import ([A-Za-z_, ]+)$", re.MULTILINE
    )

    def fix_single_db_imports(match):
        imports_str = match.group(1)
        imports = [i.strip() for i in imports_str.split(",")]

        by_module = {}
        kept_in_database = []

        for imp in imports:
            if imp in CLASS_EXPORTS:
                new_module = CLASS_EXPORTS[imp]
                if new_module not in by_module:
                    by_module[new_module] = []
                by_module[new_module].append(imp)
            else:
                kept_in_database.append(imp)

        result = []
        for module, classes in sorted(by_module.items()):
            result.append(f"from {module} import {', '.join(classes)}")

        if kept_in_database:
            result.append(
                f"from tidal_cleanup.database import {', '.join(kept_in_database)}"
            )

        return "\n".join(result)

    content = single_db_import.sub(fix_single_db_imports, content)

    if content != original_content:
        with open(file_path, "w") as f:
            f.write(content)
        return True
    return False


def main():
    """Fix all test files."""
    tests_dir = Path("tests")
    fixed_count = 0

    for test_file in tests_dir.glob("test_*.py"):
        print(f"Processing {test_file.name}...", end=" ")
        if fix_imports_in_file(test_file):
            print("✓ Fixed")
            fixed_count += 1
        else:
            print("No changes")

    print(f"\nFixed {fixed_count} test files")


if __name__ == "__main__":
    main()
