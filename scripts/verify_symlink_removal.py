#!/usr/bin/env python
"""Quick verification script for symlink removal changes."""

import sys
from pathlib import Path


def test_imports():
    """Test that all modules import correctly."""
    print("Testing imports...")
    try:
        from tidal_cleanup.core.sync import (
            DeduplicationLogic,
            SyncAction,
            SyncDecisionEngine,
            TrackDistribution,
        )
        from tidal_cleanup.database.models import PlaylistTrack, Track, TrackSyncStatus
        from tidal_cleanup.database.service import DatabaseService

        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False


def test_enums():
    """Test that symlink-related enums are removed."""
    print("\nTesting enums...")
    from tidal_cleanup.core.sync import SyncAction
    from tidal_cleanup.database.models import TrackSyncStatus

    # Check SyncAction
    actions = [action.value for action in SyncAction]
    symlink_actions = [a for a in actions if "symlink" in a.lower()]
    if symlink_actions:
        print(f"❌ Found symlink actions: {symlink_actions}")
        return False
    print(f"✅ No symlink actions found. Available: {actions}")

    # Check TrackSyncStatus
    statuses = [status.value for status in TrackSyncStatus]
    if "needs_symlink" in statuses:
        print(f"❌ Found NEEDS_SYMLINK status")
        return False
    print(f"✅ NEEDS_SYMLINK removed. Available: {statuses}")

    return True


def test_database_model():
    """Test that Track model has file_paths field."""
    print("\nTesting database models...")
    from tidal_cleanup.database.models import PlaylistTrack, Track

    # Check Track has file_paths
    if not hasattr(Track, "file_paths"):
        print("❌ Track model missing file_paths field")
        return False
    print("✅ Track model has file_paths field")

    # Check PlaylistTrack doesn't have symlink fields
    symlink_fields = ["is_primary", "symlink_path", "symlink_valid"]
    found_fields = [f for f in symlink_fields if hasattr(PlaylistTrack, f)]
    if found_fields:
        print(f"❌ PlaylistTrack still has symlink fields: {found_fields}")
        return False
    print("✅ PlaylistTrack symlink fields removed")

    return True


def test_database_service():
    """Test DatabaseService methods."""
    print("\nTesting DatabaseService...")
    from tidal_cleanup.database.service import DatabaseService

    # Check removed methods don't exist
    removed_methods = [
        "get_primary_playlist_tracks",
        "get_symlink_playlist_tracks",
        "get_broken_symlinks",
        "mark_playlist_track_as_primary",
        "update_symlink_status",
    ]

    found_methods = [m for m in removed_methods if hasattr(DatabaseService, m)]
    if found_methods:
        print(f"❌ DatabaseService still has symlink methods: {found_methods}")
        return False
    print("✅ Symlink methods removed from DatabaseService")

    # Check new methods exist
    new_methods = ["add_file_path_to_track", "remove_file_path_from_track"]
    missing_methods = [m for m in new_methods if not hasattr(DatabaseService, m)]
    if missing_methods:
        print(f"❌ DatabaseService missing new methods: {missing_methods}")
        return False
    print(f"✅ New path management methods added: {new_methods}")

    return True


def test_deduplication():
    """Test DeduplicationLogic changes."""
    print("\nTesting DeduplicationLogic...")
    from tidal_cleanup.core.sync import DeduplicationLogic, TrackDistribution

    # Check removed methods
    removed_methods = [
        "get_primary_playlist_for_track",
        "should_be_primary",
        "get_symlink_playlists_for_track",
    ]

    found_methods = [m for m in removed_methods if hasattr(DeduplicationLogic, m)]
    if found_methods:
        print(f"❌ DeduplicationLogic still has symlink methods: {found_methods}")
        return False
    print("✅ Symlink methods removed from DeduplicationLogic")

    # Check new methods
    if not hasattr(DeduplicationLogic, "get_playlists_for_track"):
        print("❌ Missing get_playlists_for_track method")
        return False
    print("✅ New track distribution methods present")

    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Symlink Removal Verification Script")
    print("=" * 60)

    tests = [
        ("Imports", test_imports),
        ("Enums", test_enums),
        ("Database Models", test_database_model),
        ("Database Service", test_database_service),
        ("Deduplication Logic", test_deduplication),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} test crashed: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All verification tests passed!")
        print("\nNext steps:")
        print("1. Backup your database")
        print("2. Run: alembic upgrade head")
        print("3. Test with real data")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
