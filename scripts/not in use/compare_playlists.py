#!/usr/bin/env python3
"""Compare test playlist with generated ones."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import db6

from tidal_cleanup.config import get_config
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = get_config()
service = RekordboxService(config)

# Compare test playlist with generated
test_playlist = (
    service.db.query(db6.DjmdPlaylist)
    .filter(db6.DjmdPlaylist.Name == "testplaylist")
    .first()
)

generated_playlist = (
    service.db.query(db6.DjmdPlaylist)
    .filter(db6.DjmdPlaylist.Name == "House Progressive")
    .first()
)

print("=" * 80)
print("TEST PLAYLIST (created manually in Rekordbox):")
print("=" * 80)
if test_playlist and test_playlist.SmartList:
    print(f"SmartList: {test_playlist.SmartList}\n")
    root = ET.fromstring(test_playlist.SmartList)
    print(f"Root attributes: {root.attrib}")
    for condition in root.iter("CONDITION"):
        print(f"Condition attributes: {condition.attrib}")
else:
    print("Not found or no SmartList")

print("\n" + "=" * 80)
print("GENERATED PLAYLIST (House Progressive):")
print("=" * 80)
if generated_playlist and generated_playlist.SmartList:
    print(f"SmartList: {generated_playlist.SmartList}\n")
    root = ET.fromstring(generated_playlist.SmartList)
    print(f"Root attributes: {root.attrib}")
    for condition in root.iter("CONDITION"):
        print(f"Condition attributes: {condition.attrib}")
else:
    print("Not found or no SmartList")

print("\n" + "=" * 80)
print("DIFFERENCES:")
print("=" * 80)

# Look for any structural differences
if test_playlist and generated_playlist:
    test_root = ET.fromstring(test_playlist.SmartList)
    gen_root = ET.fromstring(generated_playlist.SmartList)

    test_cond = list(test_root.iter("CONDITION"))[0]
    gen_cond = list(gen_root.iter("CONDITION"))[0]

    print("\nAttribute comparison:")
    all_attrs = set(test_cond.attrib.keys()) | set(gen_cond.attrib.keys())
    for attr in sorted(all_attrs):
        test_val = test_cond.get(attr, "MISSING")
        gen_val = gen_cond.get(attr, "MISSING")
        match = "✓" if test_val == gen_val else "✗"
        print(f"{match} {attr}:")
        print(f"    Test: {test_val}")
        print(f"    Generated: {gen_val}")

service.close()
