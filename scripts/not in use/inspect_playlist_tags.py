#!/usr/bin/env python3
"""Inspect Rekordbox playlist and list tags on tracks.

This script will try to find a Rekordbox playlist matching the given name (first exact
match on name with emojis, then by clean name), and then print the MyTags attached to
the first few tracks.
"""
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: inspect_playlist_tags.py 'Playlist Name'")
    sys.exit(1)

playlist_name = sys.argv[1]

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from pyrekordbox import db6

from tidal_cleanup.config import get_config
from tidal_cleanup.services.playlist_name_parser import PlaylistNameParser
from tidal_cleanup.services.rekordbox_service import RekordboxService

config = get_config()
service = RekordboxService(config)
parser = PlaylistNameParser(
    Path(__file__).parent.parent / "config" / "rekordbox_mytag_mapping.json"
)

# Try exact match first
playlist = (
    service.db.query(db6.DjmdPlaylist)
    .filter(db6.DjmdPlaylist.Name == playlist_name)
    .first()
)

if not playlist:
    # Try clean name match
    clean = parser._extract_clean_name(playlist_name)
    playlist = (
        service.db.query(db6.DjmdPlaylist)
        .filter(db6.DjmdPlaylist.Name == clean)
        .first()
    )

if not playlist:
    print(
        f"Playlist not found in Rekordbox: '{playlist_name}' (tried clean name '{clean}')"
    )
    service.close()
    sys.exit(0)

print(f"Found playlist: {playlist.Name} (ID: {playlist.ID})")
print(f"Attribute: {playlist.Attribute}")
print(f"Total tracks in playlist: {len(playlist.Songs)}")

# Show expected tags derived from playlist name
metadata = parser.parse_playlist_name(playlist_name)
expected = []
for g, tags in metadata.all_tags.items():
    for t in tags:
        expected.append(f"{g}::{t}")
print("\nExpected tags to be applied to tracks:")
for e in expected:
    print(f"  - {e}")

# Inspect first 5 tracks
print("\nInspecting first up to 5 tracks and their actual MyTags:")
for i, s in enumerate(playlist.Songs[:5], 1):
    content = s.Content
    print(f"\nTrack {i}: {content.Title} - {getattr(content, 'ArtistName', 'Unknown')}")
    tag_links = (
        service.db.query(db6.DjmdSongMyTag)
        .filter(db6.DjmdSongMyTag.ContentID == content.ID)
        .all()
    )
    actual = []
    for link in tag_links:
        tag = (
            service.db.query(db6.DjmdMyTag)
            .filter(db6.DjmdMyTag.ID == link.MyTagID)
            .first()
        )
        if tag:
            parent = (
                service.db.query(db6.DjmdMyTag)
                .filter(db6.DjmdMyTag.ID == tag.ParentID)
                .first()
            )
            if parent:
                actual.append(f"{parent.Name}::{tag.Name}")
    if not actual:
        print("  ⚠️  No MyTags on this track")
    else:
        for a in actual:
            print(f"  - {a}")

service.close()
