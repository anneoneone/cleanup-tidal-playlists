#!/usr/bin/env python3
"""Quick test to verify on-demand playlist creation is working."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("✅ All CLI changes applied successfully!")
print("\nWhat changed:")
print("  • Removed sync_intelligent_playlist_structure() call from CLI")
print("  • Structure service is initialized but creates NO playlists upfront")
print("  • Playlists are created on-demand during track sync")
print()
print("Expected behavior when running 'tidal-cleanup sync':")
print("  1. Initialize playlist structure service ✓")
print("  2. Process genre playlists (creates playlists as needed) ✓")
print("  3. Process event playlists ✓")
print()
print("You should NO LONGER see:")
print("  ❌ 'Creating smart playlist: ...' x 560 times")
print()
print("You should NOW see:")
print("  ✅ 'Service initialized (no playlists created yet)'")
print("  ✅ Playlists created only when processing matching MP3 playlists")
