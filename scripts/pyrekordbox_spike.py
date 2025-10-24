#!/usr/bin/env python3
"""Spike script to test pyrekordbox integration and understand how it works.

This script will:
1. Try to read an existing Rekordbox XML file if available
2. Create a new XML file and test basic operations
3. Test track deduplication and playlist management
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pyrekordbox.rbxml import RekordboxXml, XmlDuplicateError

from src.tidal_cleanup.config import Config


def explore_existing_xml(xml_path: Path) -> None:
    """Explore an existing Rekordbox XML file to understand its structure."""
    print(f"\n🔍 Exploring existing XML file: {xml_path}")

    if not xml_path.exists():
        print(f"❌ File does not exist: {xml_path}")
        return

    try:
        xml = RekordboxXml(xml_path)

        print(f"📊 XML Info:")
        print(
            f"  - Product: {xml.product_name} v{xml.product_version} ({xml.product_company})"
        )
        print(f"  - Format Version: {xml.frmt_version}")
        print(f"  - Number of tracks: {xml.num_tracks}")

        if xml.num_tracks > 0:
            print(f"\n🎵 Sample tracks:")
            tracks = xml.get_tracks()
            for i, track in enumerate(tracks[:3]):  # Show first 3 tracks
                print(f"  Track {i+1}:")
                print(f"    - TrackID: {track.TrackID}")
                print(f"    - Name: {track.Name}")
                print(f"    - Artist: {track.Artist}")
                print(f"    - Location: {track.Location}")
                print(f"    - Size: {track.Size}")
                print(f"    - PlayCount: {track.PlayCount}")
                print(f"    - Rating: {track.Rating}")
                print(f"    - Comments: {track.Comments}")

        # Explore playlists
        try:
            root_playlist = xml.root_playlist_folder
            print(f"\n📁 Root playlist structure:")
            print(f"  - Name: {root_playlist.name}")
            print(
                f"  - Type: {root_playlist.type} ({'folder' if root_playlist.is_folder else 'playlist'})"
            )
            print(f"  - Count: {root_playlist.count}")
        except Exception as e:
            print(f"❌ Error exploring playlists: {e}")

    except Exception as e:
        print(f"❌ Error reading XML file: {e}")


def test_new_xml_creation() -> None:
    """Test creating a new XML file with pyrekordbox."""
    print(f"\n🆕 Testing new XML creation...")

    # Create a new XML file
    xml = RekordboxXml(
        name="tidal-cleanup", version="2.0.0", company="Anton's DJ Tools"
    )

    print(f"✅ Created new XML with {xml.num_tracks} tracks")

    # Test adding a sample track (using a dummy path for now)
    sample_track_path = "/Users/anton/Music/test_track.mp3"
    try:
        track = xml.add_track(
            location=sample_track_path,
            Name="Test Track",
            Artist="Test Artist",
            Album="Test Album",
            Size=1234567,
            TotalTime=180,
            AverageBpm=128.0,
            PlayCount=5,
            Rating=4,
            Comments="Added by tidal-cleanup",
        )
        print(f"✅ Added track: {track.Name} (ID: {track.TrackID})")

        # Try adding the same track again (should fail with duplicate error)
        try:
            xml.add_track(location=sample_track_path, Name="Duplicate Track")
            print("❌ ERROR: Should have failed with duplicate error!")
        except XmlDuplicateError as e:
            print(f"✅ Correctly caught duplicate error: {e}")

    except Exception as e:
        print(f"❌ Error adding track: {e}")

    # Test creating playlists
    try:
        playlist1 = xml.add_playlist("Techno Hits", keytype="TrackID")
        playlist2 = xml.add_playlist("House Classics", keytype="TrackID")

        print(f"✅ Created playlists: {playlist1.name}, {playlist2.name}")

        # Add track to playlists
        if xml.num_tracks > 0:
            track = xml.get_track(0)
            playlist1.add_track(track.TrackID)
            playlist2.add_track(track.TrackID)
            print(f"✅ Added track to both playlists")

    except Exception as e:
        print(f"❌ Error creating playlists: {e}")

    # Save to temporary file
    temp_xml_path = PROJECT_ROOT / "temp_test.xml"
    try:
        xml.save(temp_xml_path)
        print(f"✅ Saved XML to: {temp_xml_path}")

        # Read it back to verify
        xml_reloaded = RekordboxXml(temp_xml_path)
        print(f"✅ Reloaded XML with {xml_reloaded.num_tracks} tracks")

        # Clean up
        temp_xml_path.unlink()
        print(f"✅ Cleaned up temp file")

    except Exception as e:
        print(f"❌ Error saving/reloading XML: {e}")


def analyze_file_structure() -> None:
    """Analyze the current file structure to understand mp3 directories."""
    print(f"\n📁 Analyzing current file structure...")

    config = Config()
    mp3_dir = config.mp3_directory

    print(f"MP3 Directory: {mp3_dir}")

    if not mp3_dir.exists():
        print(f"❌ MP3 directory does not exist: {mp3_dir}")
        return

    # Look for playlist subdirectories
    playlist_dirs = [d for d in mp3_dir.iterdir() if d.is_dir()]
    print(f"Found {len(playlist_dirs)} potential playlist directories:")

    track_info = {}
    total_tracks = 0

    for playlist_dir in playlist_dirs[:5]:  # Limit to first 5 for testing
        print(f"\n  📂 {playlist_dir.name}:")

        audio_files = []
        for ext in [".mp3", ".wav", ".flac", ".aac", ".m4a"]:
            audio_files.extend(playlist_dir.glob(f"*{ext}"))

        print(f"    - {len(audio_files)} audio files")
        total_tracks += len(audio_files)

        # Sample a few files to understand structure
        for audio_file in audio_files[:3]:  # First 3 files
            size = audio_file.stat().st_size
            print(f"      • {audio_file.name} ({size:,} bytes)")

            # Track file by size for deduplication testing
            if size in track_info:
                track_info[size].append(
                    {"path": audio_file, "playlist": playlist_dir.name}
                )
            else:
                track_info[size] = [{"path": audio_file, "playlist": playlist_dir.name}]

    print(f"\n📊 Summary:")
    print(f"  - Total playlists: {len(playlist_dirs)}")
    print(f"  - Total tracks analyzed: {total_tracks}")

    # Check for potential duplicates (same file size)
    potential_duplicates = {
        size: files for size, files in track_info.items() if len(files) > 1
    }
    if potential_duplicates:
        print(f"  - Potential duplicates (same size): {len(potential_duplicates)}")
        for size, files in list(potential_duplicates.items())[:3]:  # Show first 3
            print(f"    Size {size:,} bytes:")
            for file_info in files:
                print(f"      - {file_info['path'].name} (in {file_info['playlist']})")
    else:
        print(f"  - No obvious duplicates found by file size")


def test_track_identification_logic() -> None:
    """Test logic for identifying tracks by filesize and avoiding duplicates."""
    print(f"\n🔍 Testing track identification logic...")

    # This will be the core logic for your requirements
    print("Key insights for implementation:")
    print("1. Use file size + filename as primary track identifier")
    print("2. pyrekordbox handles TrackID auto-increment automatically")
    print("3. XmlDuplicateError is raised for exact Location duplicates")
    print("4. Tracks can be added to multiple playlists via TrackID")
    print("5. PlayCount, Rating, Comments can be preserved during updates")
    print("6. Location field uses file:// URI format automatically")


def main():
    """Main spike function to test pyrekordbox integration."""
    print("🚀 Starting pyrekordbox spike test...")

    # Check for existing Rekordbox XML files
    config = Config()
    existing_xml = config.rekordbox_output_file

    # Test with existing XML if available
    explore_existing_xml(existing_xml)

    # Test creating new XML
    test_new_xml_creation()

    # Analyze current file structure
    analyze_file_structure()

    # Test track identification logic
    test_track_identification_logic()

    print(f"\n✅ Spike test completed!")
    print(f"\nNext steps:")
    print(f"1. Implement RekordboxService using pyrekordbox")
    print(f"2. Add track deduplication by file size")
    print(f"3. Implement playlist synchronization")
    print(f"4. Add track movement detection")


if __name__ == "__main__":
    main()
