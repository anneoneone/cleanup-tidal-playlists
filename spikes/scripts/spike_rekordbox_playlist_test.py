#!/usr/bin/env python3
"""Spike script to test adding tracks and playlists to Rekordbox database.

This script demonstrates:
1. Creating a new playlist
2. Adding tracks to the playlist with metadata
3. Validating the results by querying the database
4. Cleaning up test data

Based on pyrekordbox documentation:
https://pyrekordbox.readthedocs.io/en/latest/tutorial/db6.html
"""

import logging
from pathlib import Path

try:
    from pyrekordbox import Rekordbox6Database
    from pyrekordbox import db6

    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    print("❌ pyrekordbox not available - install with: pip install pyrekordbox")
    exit(1)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_or_get_my_tag(db, tag_name, group_name="Tidal Tags"):
    """Create or get a My-Tag entry in the database.

    Args:
        db: Rekordbox6Database instance
        tag_name: Name of the tag value (e.g., "Tidal Sync")
        group_name: Name of the tag group/section (e.g., "Tidal Tags")

    Returns:
        DjmdMyTag: The tag value instance
    """
    # Check if group exists, create if not
    group = (
        db.query(db6.DjmdMyTag)
        .filter(
            db6.DjmdMyTag.Name == group_name,
            db6.DjmdMyTag.Attribute == 1,  # 1 = section/group
        )
        .first()
    )

    if group is None:
        logger.info(f"   ➕ Creating My-Tag group: {group_name}")

        # Get the highest Seq number for root-level groups
        max_seq = (
            db.query(db6.DjmdMyTag)
            .filter(db6.DjmdMyTag.Attribute == 1, db6.DjmdMyTag.ParentID == "root")
            .count()
        )

        group = db6.DjmdMyTag(
            ID=db.generate_unused_id(db6.DjmdMyTag),
            Seq=max_seq + 1,  # Next sequence number
            Name=group_name,
            Attribute=1,  # 1 = section/group
            ParentID="root",  # Must be "root" string, not None
        )
        db.add(group)
        db.flush()  # Ensure ID is available

    # Check if tag value exists under this group, create if not
    tag = (
        db.query(db6.DjmdMyTag)
        .filter(
            db6.DjmdMyTag.Name == tag_name,
            db6.DjmdMyTag.ParentID == group.ID,
            db6.DjmdMyTag.Attribute == 0,  # 0 = value
        )
        .first()
    )

    if tag is None:
        logger.info(f"   ➕ Creating My-Tag value: {tag_name}")

        # Get the highest Seq number for values in this group
        max_seq = (
            db.query(db6.DjmdMyTag)
            .filter(db6.DjmdMyTag.Attribute == 0, db6.DjmdMyTag.ParentID == group.ID)
            .count()
        )

        tag = db6.DjmdMyTag(
            ID=db.generate_unused_id(db6.DjmdMyTag),
            Seq=max_seq + 1,  # Next sequence number within group
            Name=tag_name,
            Attribute=0,  # 0 = value
            ParentID=group.ID,
        )
        db.add(tag)
        db.flush()

    return tag


def link_content_to_my_tag(db, content, tag):
    """Link a content (track) to a My-Tag value.

    Args:
        db: Rekordbox6Database instance
        content: DjmdContent instance
        tag: DjmdMyTag instance (must be a value, not a group)
    """
    # Check if link already exists
    existing_link = (
        db.query(db6.DjmdSongMyTag)
        .filter(
            db6.DjmdSongMyTag.ContentID == content.ID,
            db6.DjmdSongMyTag.MyTagID == tag.ID,
        )
        .first()
    )

    if existing_link is None:
        logger.info(f"   🔗 Linking content to My-Tag: {tag.Name}")
        song_tag = db6.DjmdSongMyTag(
            ID=db.generate_unused_id(db6.DjmdSongMyTag),
            MyTagID=tag.ID,
            ContentID=content.ID,
            TrackNo=1,
        )
        db.add(song_tag)
    else:
        logger.info(f"   ✓ Content already linked to My-Tag: {tag.Name}")


def test_rekordbox_playlist_operations():
    """Test adding tracks and playlists to Rekordbox database."""

    if not PYREKORDBOX_AVAILABLE:
        logger.error("pyrekordbox not available")
        return False

    try:
        # Connect to Rekordbox database
        logger.info("🔌 Connecting to Rekordbox database...")
        db = Rekordbox6Database()
        logger.info("✅ Connected successfully")

        # Test data - using your existing MP3 files
        test_playlist_name = "🧪 PyRekordbox Test Playlist"
        test_tracks = [
            "/Users/anton/Music/Tidal-test-dev/mp3/Playlists/Jazzz D 🎷💾/Muriel Grossmann - Absolute Truth.mp3",
            "/Users/anton/Music/Tidal-test-dev/mp3/Playlists/Jazzz D 🎷💾/Muriel Grossmann - All Heart.mp3",
            "/Users/anton/Music/Tidal-test-dev/mp3/Playlists/Jazzz D 🎷💾/Muriel Grossmann - Calm.mp3",
        ]

        # Validate test files exist
        logger.info("📁 Validating test files...")
        valid_tracks = []
        for track_path in test_tracks:
            if Path(track_path).exists():
                valid_tracks.append(track_path)
                logger.info(f"✅ Found: {Path(track_path).name}")
            else:
                logger.warning(f"❌ Not found: {track_path}")

        if not valid_tracks:
            logger.error("No valid test tracks found!")
            return False

        # 1. Check if test playlist already exists and delete it
        logger.info(f"🧹 Cleaning up any existing test playlist: {test_playlist_name}")
        existing_playlist = db.get_playlist(Name=test_playlist_name).first()
        if existing_playlist:
            logger.info("🗑️ Deleting existing test playlist...")
            db.delete_playlist(existing_playlist)
            db.commit()
            logger.info("✅ Cleaned up existing playlist")

        # 2. Create new test playlist
        logger.info(f"🎵 Creating new playlist: {test_playlist_name}")
        playlist = db.create_playlist(test_playlist_name)
        logger.info(f"✅ Created playlist with ID: {playlist.ID}")

        # 3. Add tracks to playlist with metadata
        logger.info("🎶 Adding tracks to playlist...")
        added_tracks = []

        for i, track_path in enumerate(valid_tracks, 1):
            logger.info(f"📀 Adding track {i}: {Path(track_path).name}")

            try:
                # Check if track already exists in database
                existing_content = db.get_content(FolderPath=track_path).first()

                if existing_content:
                    logger.info(
                        f"   📋 Track already in database: {existing_content.Title}"
                    )
                    content = existing_content

                    # Link existing content to My-Tag
                    my_tag_name = "Tidal Sync"
                    my_tag = create_or_get_my_tag(db, my_tag_name)
                    link_content_to_my_tag(db, content, my_tag)
                else:
                    # Add new track with metadata directly (no Reload Tag needed)
                    logger.info(f"   ➕ Adding track with metadata...")

                    # Read metadata from file
                    try:
                        from mutagen.id3 import ID3

                        audio = ID3(track_path)
                        title = str(audio.get("TIT2", Path(track_path).stem))
                        artist_name = str(audio.get("TPE1", "Unknown Artist"))
                        album_name = str(audio.get("TALB", "Unknown Album"))
                        year_str = str(audio.get("TDRC", ""))
                        release_year = int(year_str[:4]) if year_str else None
                    except Exception as e:
                        logger.warning(f"   ⚠️ Could not read tags: {e}")
                        title = Path(track_path).stem
                        artist_name = "Unknown Artist"
                        album_name = "Unknown Album"
                        release_year = None

                    logger.info(f"   📋 Title: {title}")
                    logger.info(f"   📋 Artist: {artist_name}")
                    logger.info(f"   📋 Album: {album_name}")

                    # Create or get Artist
                    artist = db.get_artist(Name=artist_name).first()
                    if artist is None:
                        logger.info(f"   ➕ Creating artist: {artist_name}")
                        artist = db.add_artist(name=artist_name)

                    # Create or get Album
                    album = db.get_album(Name=album_name).first()
                    if album is None:
                        logger.info(f"   ➕ Creating album: {album_name}")
                        album = db.add_album(name=album_name)

                    # Create or get Genre
                    genre_name = "Jazz Fusion"
                    genre = db.get_genre(Name=genre_name).first()
                    if genre is None:
                        logger.info(f"   ➕ Creating genre: {genre_name}")
                        genre = db.add_genre(name=genre_name)

                    # Add content with all metadata via foreign keys
                    content = db.add_content(
                        track_path,
                        Title=title,
                        ArtistID=artist.ID,
                        AlbumID=album.ID,
                        GenreID=genre.ID,
                        ReleaseYear=release_year,
                    )
                    logger.info(f"   ✅ Added content with full metadata")
                    logger.info(f"   ✅ Content ID: {content.ID}")

                    # Create/get My-Tag and link to content
                    my_tag_name = "Tidal Sync"
                    my_tag = create_or_get_my_tag(db, my_tag_name)
                    link_content_to_my_tag(db, content, my_tag)
                    logger.info(f"   ✅ My Tag: {my_tag_name}")

                # Add track to playlist
                song_playlist = db.add_to_playlist(playlist, content)
                added_tracks.append((content, song_playlist))
                logger.info(
                    f"   ✅ Added to playlist at position {song_playlist.TrackNo}"
                )

            except Exception as e:
                logger.error(f"   ❌ Failed to add track: {e}")
                continue

        # Commit all changes
        logger.info("💾 Committing changes...")
        db.commit()
        logger.info("✅ Changes committed")

        # 4. Validate the playlist and track metadata
        logger.info("🔍 Validating playlist and track metadata...")

        # Re-query the playlist to get fresh data
        validated_playlist = db.get_playlist(Name=test_playlist_name).first()
        if not validated_playlist:
            logger.error("❌ Could not find playlist after creation!")
            return False

        logger.info(f"📋 Playlist validation:")
        logger.info(f"   Name: {validated_playlist.Name}")
        logger.info(f"   ID: {validated_playlist.ID}")
        logger.info(f"   Songs count: {len(validated_playlist.Songs)}")
        logger.info(
            f"   Parent: {validated_playlist.Parent.Name if validated_playlist.Parent else 'Root'}"
        )

        # Validate each track in the playlist
        logger.info("🎵 Track validation:")
        for i, song in enumerate(validated_playlist.Songs, 1):
            content = song.Content
            logger.info(f"   Track {i}:")
            logger.info(f"     Title: {content.Title}")
            logger.info(f"     Artist: {content.ArtistName}")
            logger.info(f"     Album: {content.AlbumName}")
            logger.info(f"     Genre: {content.GenreName}")

            # Check My-Tag links
            my_tag_links = (
                db.query(db6.DjmdSongMyTag)
                .filter(db6.DjmdSongMyTag.ContentID == content.ID)
                .all()
            )
            if my_tag_links:
                for link in my_tag_links:
                    tag = (
                        db.query(db6.DjmdMyTag)
                        .filter(db6.DjmdMyTag.ID == link.MyTagID)
                        .first()
                    )
                    if tag:
                        parent = None
                        if tag.ParentID:
                            parent = (
                                db.query(db6.DjmdMyTag)
                                .filter(db6.DjmdMyTag.ID == tag.ParentID)
                                .first()
                            )
                        tag_path = f"{parent.Name}/{tag.Name}" if parent else tag.Name
                        logger.info(f"     My Tag: {tag_path}")
            else:
                logger.info(f"     My Tag: None")

            logger.info(f"     Comments: {content.Commnt}")
            logger.info(f"     Release Year: {content.ReleaseYear}")
            logger.info(f"     Track No: {content.TrackNo}")
            logger.info(f"     BPM: {content.BPM}")
            logger.info(f"     Length: {content.Length} seconds")
            logger.info(f"     File Size: {content.FileSize} bytes")
            logger.info(f"     File Path: {content.FolderPath}")
            logger.info(f"     Playlist Position: {song.TrackNo}")
            logger.info(f"     Song ID: {song.ID}")
            logger.info("     " + "-" * 50)

        # 5. Test playlist operations
        logger.info("🔧 Testing playlist operations...")

        # Test removing a track from playlist
        if validated_playlist.Songs:
            first_song = validated_playlist.Songs[0]
            logger.info(
                f"🗑️ Removing first track from playlist: {first_song.Content.Title}"
            )
            db.remove_from_playlist(validated_playlist, first_song)
            db.commit()
            logger.info("✅ Track removed from playlist")

            # Re-validate playlist after removal
            updated_playlist = db.get_playlist(Name=test_playlist_name).first()
            logger.info(f"📊 Playlist now has {len(updated_playlist.Songs)} songs")

        # 6. Optional: Clean up test data
        cleanup = (
            input("\n🧹 Clean up test playlist and tracks? (y/N): ").lower().strip()
        )
        if cleanup == "y":
            logger.info("🗑️ Cleaning up test playlist and tracks...")
            final_playlist = db.get_playlist(Name=test_playlist_name).first()
            if final_playlist:
                # Get content objects before deleting playlist
                content_objects = [
                    song.Content for song in final_playlist.Songs if song.Content
                ]
                track_paths = [
                    content.FolderPath for content in content_objects if content
                ]

                logger.info(
                    f"📋 Found {len(content_objects)} tracks to remove from database"
                )

                # Delete playlist first
                db.delete_playlist(final_playlist)
                logger.info("✅ Test playlist deleted")

                # Delete tracks from database
                for i, (content, track_path) in enumerate(
                    zip(content_objects, track_paths), 1
                ):
                    try:
                        logger.info(f"🗑️ Removing track {i}: {Path(track_path).name}")
                        db.delete(content)  # Use generic delete() method
                        logger.info(f"✅ Track {i} removed from database")
                    except Exception as e:
                        logger.error(f"❌ Failed to remove track {i}: {e}")

                db.commit()
                logger.info("✅ All test data cleaned up")
        else:
            logger.info(f"📋 Test playlist '{test_playlist_name}' left in database")

        # Close database connection
        db.close()
        logger.info("🔌 Database connection closed")

        logger.info("🎉 Spike test completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Spike test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def analyze_existing_playlists():
    """Analyze existing playlists in the database."""
    try:
        db = Rekordbox6Database()

        logger.info("📊 Analyzing existing playlists...")

        # Get all playlists
        playlists = db.get_playlist().all()
        logger.info(f"Found {len(playlists)} playlists total")

        # Show playlist hierarchy
        for playlist in playlists:
            indent = "  " * (playlist.Seq if playlist.Seq else 0)
            playlist_type = "📁 Folder" if playlist.Type == 0 else "🎵 Playlist"
            song_count = len(playlist.Songs) if hasattr(playlist, "Songs") else 0

            logger.info(
                f"{indent}{playlist_type}: {playlist.Name} (ID: {playlist.ID}, Songs: {song_count})"
            )

        db.close()

    except Exception as e:
        logger.error(f"❌ Failed to analyze playlists: {e}")


def main():
    """Main function to run the spike test."""
    print("🧪 Rekordbox Playlist Operations Spike Test")
    print("=" * 50)

    # First analyze existing playlists
    analyze_existing_playlists()

    print("\n" + "=" * 50)

    # Run the main test
    success = test_rekordbox_playlist_operations()

    if success:
        print("\n🎉 All tests passed!")
    else:
        print("\n❌ Tests failed!")
        exit(1)


if __name__ == "__main__":
    main()
