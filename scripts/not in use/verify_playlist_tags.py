#!/usr/bin/env python3
"""Verify MyTags on tracks in a playlist."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pyrekordbox import Rekordbox6Database, db6


def check_playlist_tags(playlist_name: str):
    """Check what MyTags are on tracks in a playlist."""

    db = Rekordbox6Database()

    # Get playlist
    playlist = db.get_playlist(Name=playlist_name).first()
    if not playlist:
        print(f"❌ Playlist '{playlist_name}' not found")
        return

    print(f"📋 Playlist: {playlist_name}")
    print(f"   Tracks: {len(playlist.Songs)}")
    print()

    # Check each track's tags
    for i, song in enumerate(playlist.Songs, 1):
        content = song.Content
        print(f"Track {i}: {content.Title} - {content.ArtistName}")

        # Get MyTag links for this content
        tag_links = (
            db.query(db6.DjmdSongMyTag)
            .filter(db6.DjmdSongMyTag.ContentID == content.ID)
            .all()
        )

        if not tag_links:
            print("   ⚠️  No MyTags")
        else:
            # Get tag details
            tags_by_group = {}
            for link in tag_links:
                tag = (
                    db.query(db6.DjmdMyTag)
                    .filter(db6.DjmdMyTag.ID == link.MyTagID)
                    .first()
                )
                if tag:
                    # Get parent group
                    parent = (
                        db.query(db6.DjmdMyTag)
                        .filter(db6.DjmdMyTag.ID == tag.ParentID)
                        .first()
                    )
                    if parent:
                        group_name = parent.Name
                        if group_name not in tags_by_group:
                            tags_by_group[group_name] = []
                        tags_by_group[group_name].append(tag.Name)

            for group, tags in sorted(tags_by_group.items()):
                print(f"   {group}: {', '.join(tags)}")

        print()

    db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_playlist_tags.py 'Playlist Name'")
        sys.exit(1)

    playlist_name = sys.argv[1]
    check_playlist_tags(playlist_name)
