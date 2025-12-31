"""Backup Rekordbox database files with version history.

This script backs up critical Rekordbox database files to a local backup directory.
Rekordbox must be closed before running this script.

Critical files backed up:
- master.db (main SQLite database with all tracks, playlists, metadata)
- master.db-wal (write-ahead log, must be kept with master.db)
- local.db (local metadata and sync settings)

Usage:
    python scripts/backup_rekordbox_db.py
    python scripts/backup_rekordbox_db.py --dry-run
    python scripts/backup_rekordbox_db.py --restore <backup_date>
    python scripts/backup_rekordbox_db.py --list
"""

import argparse
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional


class RekordboxBackup:
    """Manage Rekordbox database backups."""

    CRITICAL_FILES = [
        "master.db",
        "master.db-wal",
        "local.db",
    ]

    def __init__(
        self, backup_dir: Optional[Path] = None, rekordbox_dir: Optional[Path] = None
    ):
        """Initialize backup manager.

        Args:
            backup_dir: Directory to store backups (defaults to ~/backups/rekordbox)
            rekordbox_dir: Custom Rekordbox database directory (auto-detected if None)
        """
        self.backup_dir = backup_dir or Path.home() / "backups" / "rekordbox"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Find Rekordbox database directory
        if rekordbox_dir:
            self.rekordbox_dir = Path(rekordbox_dir)
        else:
            self.rekordbox_dir = self._find_rekordbox_dir()

        if not self.rekordbox_dir.exists():
            raise RuntimeError(
                f"Rekordbox directory not found: {self.rekordbox_dir}\n"
                f"Common locations:\n"
                f"  macOS: ~/Library/Pioneer/rekordbox or ~/Music/rekordbox\n"
                f"  Windows: ~/AppData/Local/Pioneer/rekordbox\n"
                f"Use --rekordbox-dir to specify custom location"
            )

    @staticmethod
    def _find_rekordbox_dir() -> Path:
        """Auto-detect Rekordbox database directory."""
        import platform

        candidates = []

        if sys.platform == "darwin":  # macOS
            candidates = [
                Path.home() / "Library" / "Pioneer" / "rekordbox",
                Path.home() / "Music" / "rekordbox",
                Path.home() / ".rekordbox",
            ]
        elif sys.platform == "win32":  # Windows
            candidates = [
                Path.home() / "AppData" / "Local" / "Pioneer" / "rekordbox",
                Path.home() / "AppData" / "Roaming" / "Pioneer" / "rekordbox",
            ]
        elif sys.platform == "linux":  # Linux
            candidates = [
                Path.home() / ".local" / "share" / "rekordbox",
                Path.home() / ".rekordbox",
            ]

        # Try each candidate
        for candidate in candidates:
            if candidate.exists():
                return candidate

        # Return the most likely path (first candidate)
        return (
            candidates[0]
            if candidates
            else Path.home() / "Library" / "Pioneer" / "rekordbox"
        )

    def get_backup_timestamp(self) -> str:
        """Generate backup timestamp."""
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    def get_existing_backups(self) -> List[tuple[str, Path]]:
        """Get list of existing backups sorted by date (newest first)."""
        backups = []

        if not self.backup_dir.exists():
            return backups

        for item in self.backup_dir.iterdir():
            if item.is_dir() and len(item.name) == 15:  # YYYYMMDD-HHMMSS format
                try:
                    datetime.strptime(item.name, "%Y%m%d-%H%M%S")
                    backups.append((item.name, item))
                except ValueError:
                    continue

        return sorted(backups, reverse=True)

    def find_backup(self, backup_id: str) -> Optional[Path]:
        """Find backup by ID or recent date pattern."""
        backups = self.get_existing_backups()

        for name, path in backups:
            if name.startswith(backup_id):
                return path

        return None

    def backup(self, dry_run: bool = False) -> bool:
        """Backup critical Rekordbox files.

        Args:
            dry_run: If True, show what would be backed up without doing it

        Returns:
            True if successful, False otherwise
        """
        timestamp = self.get_backup_timestamp()
        backup_path = self.backup_dir / timestamp

        print(f"🔄 Rekordbox Backup")
        print(f"   Source: {self.rekordbox_dir}")
        print(f"   Backup: {backup_path}")
        print(f"   Timestamp: {timestamp}\n")

        if dry_run:
            print("📋 [DRY-RUN] Files that would be backed up:")
        else:
            backup_path.mkdir(parents=True, exist_ok=True)

        backed_up = 0
        failed = 0

        for filename in self.CRITICAL_FILES:
            source = self.rekordbox_dir / filename

            if not source.exists():
                print(f"   ⚠️  {filename:<20} (not found, skipping)")
                continue

            size_mb = source.stat().st_size / (1024 * 1024)

            if dry_run:
                print(f"   ✓ {filename:<20} ({size_mb:.1f} MB)")
                backed_up += 1
            else:
                try:
                    dest = backup_path / filename
                    shutil.copy2(source, dest)
                    print(f"   ✓ {filename:<20} ({size_mb:.1f} MB)")
                    backed_up += 1
                except Exception as e:
                    print(f"   ✗ {filename:<20} (failed: {e})")
                    failed += 1

        if dry_run:
            print(f"\n📊 [DRY-RUN] Would back up {backed_up} files")
        else:
            if failed == 0:
                print(f"\n✅ Backup complete: {backed_up} files backed up")
                print(f"   Location: {backup_path}")
                return True
            else:
                print(f"\n⚠️  Backup completed with {failed} error(s)")
                return failed == 0

        return True

    def list_backups(self) -> bool:
        """List all existing backups."""
        backups = self.get_existing_backups()

        print(f"📁 Rekordbox Backups")
        print(f"   Directory: {self.backup_dir}\n")

        if not backups:
            print("   (no backups found)")
            return True

        for i, (name, path) in enumerate(backups, 1):
            # Parse timestamp
            dt = datetime.strptime(name, "%Y%m%d-%H%M%S")
            age = datetime.now() - dt

            # Count files
            files = list(path.iterdir())
            size_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)

            # Format age
            if age < timedelta(hours=1):
                age_str = f"{int(age.total_seconds() / 60)} minutes ago"
            elif age < timedelta(days=1):
                age_str = f"{int(age.total_seconds() / 3600)} hours ago"
            else:
                age_str = f"{age.days} days ago"

            print(f"   {i}. {name}  ({len(files)} files, {size_mb:.1f} MB) - {age_str}")

        return True

    def restore(self, backup_id: str, dry_run: bool = False) -> bool:
        """Restore from a backup.

        Args:
            backup_id: Backup ID (date prefix like 20231220 or full timestamp)
            dry_run: If True, show what would be restored without doing it

        Returns:
            True if successful, False otherwise
        """
        backup_path = self.find_backup(backup_id)

        if not backup_path:
            print(f"❌ Backup not found: {backup_id}")
            print("   Use --list to see available backups")
            return False

        print(f"🔄 Rekordbox Restore")
        print(f"   Source: {backup_path}")
        print(f"   Destination: {self.rekordbox_dir}\n")

        if dry_run:
            print("📋 [DRY-RUN] Files that would be restored:")
        else:
            print("⚠️  WARNING: This will overwrite your current Rekordbox database!")
            response = input("   Are you sure? Type 'yes' to continue: ")
            if response.lower() != "yes":
                print("   Cancelled.")
                return False

        restored = 0
        failed = 0

        for source_file in backup_path.iterdir():
            if source_file.is_file():
                size_mb = source_file.stat().st_size / (1024 * 1024)

                if dry_run:
                    print(f"   ✓ {source_file.name:<20} ({size_mb:.1f} MB)")
                    restored += 1
                else:
                    try:
                        dest = self.rekordbox_dir / source_file.name
                        shutil.copy2(source_file, dest)
                        print(f"   ✓ {source_file.name:<20} ({size_mb:.1f} MB)")
                        restored += 1
                    except Exception as e:
                        print(f"   ✗ {source_file.name:<20} (failed: {e})")
                        failed += 1

        if dry_run:
            print(f"\n📊 [DRY-RUN] Would restore {restored} files")
        else:
            if failed == 0:
                print(f"\n✅ Restore complete: {restored} files restored")
                print("   ⚠️  Restart Rekordbox to load the restored database")
                return True
            else:
                print(f"\n⚠️  Restore completed with {failed} error(s)")
                return False

        return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backup and restore Rekordbox database files"
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Custom backup directory (default: ~/backups/rekordbox)",
    )
    parser.add_argument(
        "--rekordbox-dir",
        type=Path,
        default=None,
        help="Custom Rekordbox database directory (auto-detected if not specified)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Backup command
    subparsers.add_parser(
        "backup", help="Create a backup of Rekordbox database"
    ).add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be backed up without doing it",
    )

    # List command
    subparsers.add_parser("list", help="List all existing backups")

    # Restore command
    restore_parser = subparsers.add_parser(
        "restore",
        help="Restore from a backup",
    )
    restore_parser.add_argument(
        "backup_id",
        help="Backup ID or date prefix (e.g., 20231220 or 20231220-143022)",
    )
    restore_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be restored without doing it",
    )

    args = parser.parse_args()

    try:
        backup_mgr = RekordboxBackup(
            backup_dir=args.backup_dir, rekordbox_dir=args.rekordbox_dir
        )

        if args.command == "backup" or not args.command:
            success = backup_mgr.backup(dry_run=getattr(args, "dry_run", False))
            sys.exit(0 if success else 1)
        elif args.command == "list":
            success = backup_mgr.list_backups()
            sys.exit(0 if success else 1)
        elif args.command == "restore":
            success = backup_mgr.restore(
                args.backup_id,
                dry_run=args.dry_run,
            )
            sys.exit(0 if success else 1)
        else:
            parser.print_help()
            sys.exit(0)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
