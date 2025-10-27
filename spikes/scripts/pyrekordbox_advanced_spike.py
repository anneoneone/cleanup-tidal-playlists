#!/usr/bin/env python3
"""Advanced pyrekordbox spike script to explore the full potential of the library.

This script demonstrates:
1. Working with the Rekordbox 6/7 SQL database (master.db)
2. Reading and writing XML databases
3. Track management with deduplication
4. Playlist synchronization
5. Metadata preservation
6. Track movement detection
7. Advanced database operations
"""

import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from pyrekordbox import Rekordbox6Database, RekordboxXml

    from tidal_cleanup.config import Config
except ImportError as e:
    print(f"❌ Import error: {e}")
    print(
        "   This might be because pyrekordbox is not installed or config module not found"
    )
    sys.exit(1)


class AdvancedRekordboxManager:
    """Advanced Rekordbox database manager using the full potential of pyrekordbox."""

    def __init__(self, config: Config):
        self.config = config
        self.db: Optional[Rekordbox6Database] = None
        self.xml: Optional[RekordboxXml] = None
        self.track_signatures: Dict[str, str] = {}  # file_signature -> content_id

    def connect_to_sql_database(self) -> bool:
        """Connect to the Rekordbox SQL database (master.db)."""
        try:
            print("\n🔗 Connecting to Rekordbox SQL database...")

            # Try to connect to the Rekordbox database
            self.db = Rekordbox6Database()

            print("✅ Connected to Rekordbox database")
            print(f"   Database directory: {self.db.db_directory}")
            print(f"   Share directory: {self.db.share_directory}")

            # Get database info
            property_info = self.db.get_property().first()
            if property_info:
                print(f"   Database ID: {property_info.DBID}")
                print(f"   Database Version: {property_info.DBVersion}")

            # Get basic statistics
            content_count = self.db.get_content().count()
            playlist_count = self.db.get_playlist().count()
            print(f"   Total tracks: {content_count}")
            print(f"   Total playlists: {playlist_count}")

            return True

        except Exception as e:
            print(f"❌ Failed to connect to SQL database: {e}")
            print("   This might be because:")
            print("   - Rekordbox is not installed")
            print("   - Database key extraction failed")
            print("   - Rekordbox is currently running")
            return False

    def explore_sql_database_structure(self) -> None:
        """Explore the structure and content of the SQL database."""
        if not self.db:
            print("❌ No database connection")
            return

        print("\n🔍 Exploring SQL database structure...")

        try:
            # Explore tracks
            print("\n📀 Sample tracks:")
            tracks = self.db.get_content().limit(3).all()
            for i, track in enumerate(tracks, 1):
                print(f"   Track {i}:")
                print(f"     ID: {track.ID}")
                print(f"     Title: {track.Title}")
                print(
                    f"     Artist: {track.Artist.Name if track.Artist else 'Unknown'}"
                )
                print(f"     Album: {track.Album.Name if track.Album else 'Unknown'}")
                print(f"     File Path: {track.FolderPath}")
                print(f"     File Size: {track.FileSize:,} bytes")
                print(f"     Play Count: {track.DJPlayCount}")
                print(f"     Rating: {track.Rating}")
                print(f"     Date Added: {track.DateAdded}")
                print(f"     BPM: {track.Bpm}")

            # Explore playlists
            print("\n📁 Sample playlists:")
            playlists = self.db.get_playlist().limit(5).all()
            for i, playlist in enumerate(playlists, 1):
                print(f"   Playlist {i}:")
                print(f"     ID: {playlist.ID}")
                print(f"     Name: {playlist.Name}")
                print(
                    f"     Type: {'Folder' if playlist.Attribute == 1 else 'Playlist'}"
                )
                print(f"     Parent: {playlist.ParentID}")
                print(f"     Songs: {len(playlist.Songs)}")

        except Exception as e:
            print(f"❌ Error exploring database: {e}")

    def generate_track_signature(self, file_path: Path) -> str:
        """Generate a unique signature for a track based on file size and name."""
        try:
            size = file_path.stat().st_size
            name = file_path.stem.lower()
            # Create a simple signature combining size and normalized name
            signature = f"{size}_{hashlib.md5(name.encode()).hexdigest()[:8]}"
            return signature
        except Exception:
            return f"unknown_{file_path.name}"

    def scan_mp3_directories(self) -> Dict[str, List[Path]]:
        """Scan MP3 directories and group tracks by signature for deduplication."""
        print("\n📂 Scanning MP3 directories...")

        mp3_dir = self.config.mp3_directory
        if not mp3_dir.exists():
            print(f"❌ MP3 directory does not exist: {mp3_dir}")
            return {}

        track_groups: Dict[str, List[Path]] = {}
        total_files = 0

        # Scan all playlist directories
        for playlist_dir in mp3_dir.iterdir():
            if not playlist_dir.is_dir():
                continue

            print(f"   📁 {playlist_dir.name}")

            # Find audio files
            audio_files = []
            for ext in [".mp3", ".wav", ".flac", ".aac", ".m4a"]:
                audio_files.extend(playlist_dir.glob(f"*{ext}"))

            print(f"      Found {len(audio_files)} audio files")
            total_files += len(audio_files)

            # Group by signature
            for audio_file in audio_files:
                signature = self.generate_track_signature(audio_file)
                if signature not in track_groups:
                    track_groups[signature] = []
                track_groups[signature].append(audio_file)

        # Report duplicates
        duplicates = {
            sig: files for sig, files in track_groups.items() if len(files) > 1
        }
        print(f"\n📊 Scan results:")
        print(f"   Total files: {total_files}")
        print(f"   Unique tracks: {len(track_groups)}")
        print(f"   Potential duplicates: {len(duplicates)}")

        if duplicates:
            print(f"\n🔍 Sample duplicates:")
            for i, (signature, files) in enumerate(list(duplicates.items())[:3]):
                print(f"   Signature {signature}:")
                for file_path in files:
                    print(f"     - {file_path.relative_to(mp3_dir)}")

        return track_groups

    def normalize_path(self, path_str: str) -> Path:
        """Normalize path string by handling different path representations."""
        if not path_str:
            return None

        # Convert to Path and resolve to handle different representations
        try:
            # First try direct conversion
            path = Path(path_str)
            if path.exists():
                return path

            # Try unquoting for URL-encoded paths
            import urllib.parse

            unquoted = urllib.parse.unquote(path_str)
            path = Path(unquoted)
            if path.exists():
                return path

            # Try replacing escaped characters
            normalized = (
                path_str.replace("\\ ", " ")
                .replace("\\&", "&")
                .replace("\\(", "(")
                .replace("\\)", ")")
            )
            path = Path(normalized)
            if path.exists():
                return path

            # Return original path even if it doesn't exist (for comparison)
            return Path(path_str)
        except Exception:
            return Path(path_str)

    def paths_match(self, path1: str, path2: str) -> bool:
        """Check if two path strings refer to the same file."""
        if not path1 or not path2:
            return False

        try:
            p1 = self.normalize_path(path1)
            p2 = self.normalize_path(path2)

            # Compare resolved paths
            if p1.exists() and p2.exists():
                return p1.resolve() == p2.resolve()

            # Compare normalized string representations
            return str(p1) == str(p2)
        except Exception:
            return False

    def find_matching_files(
        self, db_path: str, local_files: Dict[str, List[Path]]
    ) -> List[Path]:
        """Find local files that match a database path."""
        matches = []
        db_path_normalized = self.normalize_path(db_path)

        # Direct path matching
        if db_path_normalized.exists():
            matches.append(db_path_normalized)

        # Search through all local files for matches
        for signature, file_paths in local_files.items():
            for file_path in file_paths:
                if self.paths_match(db_path, str(file_path)):
                    matches.append(file_path)
                elif db_path_normalized.name == file_path.name:
                    # Same filename, check if it's the same file by size
                    try:
                        if (
                            db_path_normalized.exists()
                            and file_path.exists()
                            and db_path_normalized.stat().st_size
                            == file_path.stat().st_size
                        ):
                            matches.append(file_path)
                    except Exception:
                        pass

        return list(set(matches))  # Remove duplicates

    def sync_with_sql_database(self, track_groups: Dict[str, List[Path]]) -> None:
        """Sync local tracks with the SQL database."""
        if not self.db:
            print("❌ No database connection")
            return

        print(f"\n🔄 Syncing with SQL database...")

        try:
            # Create a lookup of all local files by various criteria
            local_files_by_signature = track_groups
            local_files_by_name = {}
            local_files_by_path = {}

            for signature, file_paths in track_groups.items():
                for file_path in file_paths:
                    # By filename
                    filename = file_path.name
                    if filename not in local_files_by_name:
                        local_files_by_name[filename] = []
                    local_files_by_name[filename].append(file_path)

                    # By normalized path
                    normalized = str(file_path).replace(
                        " ", "\\ "
                    )  # Example normalization
                    local_files_by_path[str(file_path)] = file_path
                    local_files_by_path[normalized] = file_path

            # Get existing tracks from database and match with local files
            existing_tracks = {}
            matched_tracks = 0
            path_mismatches = 0

            all_db_tracks = self.db.get_content().all()
            print(f"   Processing {len(all_db_tracks)} database tracks...")

            for track in all_db_tracks:
                if not track.FolderPath:
                    continue

                # Find matching local files
                matching_files = self.find_matching_files(
                    track.FolderPath, local_files_by_signature
                )

                if matching_files:
                    matched_tracks += 1
                    # Use the first matching file for signature generation
                    signature = self.generate_track_signature(matching_files[0])
                    existing_tracks[signature] = track

                    # Check for path mismatches
                    canonical_path = str(matching_files[0])
                    if track.FolderPath != canonical_path:
                        path_mismatches += 1
                        if path_mismatches <= 5:  # Show only first 5 examples
                            print(f"   � Path mismatch found:")
                            print(f"      DB: {track.FolderPath}")
                            print(f"      FS: {canonical_path}")

            print(f"   Found {len(existing_tracks)} matched tracks in database")
            if path_mismatches > 5:
                print(f"   ... and {path_mismatches - 5} more path mismatches")

            # Count new tracks (in local files but not in database)
            new_tracks = 0
            for signature, file_paths in track_groups.items():
                if signature not in existing_tracks:
                    new_tracks += 1
                    if new_tracks <= 10:  # Show only first 10 examples
                        print(f"   ➕ New track: {file_paths[0].name}")

            # Count missing tracks (in database but not in local files)
            missing_tracks = 0
            for track in all_db_tracks:
                if not track.FolderPath:
                    continue

                matching_files = self.find_matching_files(
                    track.FolderPath, local_files_by_signature
                )
                if not matching_files:
                    missing_tracks += 1
                    if missing_tracks <= 10:  # Show only first 10 examples
                        print(
                            f"   ❌ Missing track: {track.Title} ({track.FolderPath})"
                        )

            if new_tracks > 10:
                print(f"   ... and {new_tracks - 10} more new tracks")
            if missing_tracks > 10:
                print(f"   ... and {missing_tracks - 10} more missing tracks")

            print(f"\n📈 Sync summary:")
            print(f"   Matched tracks: {matched_tracks}")
            print(f"   New tracks: {new_tracks}")
            print(f"   Missing tracks: {missing_tracks}")
            print(f"   Path mismatches: {path_mismatches}")

        except Exception as e:
            print(f"❌ Error during sync: {e}")
            import traceback

            traceback.print_exc()

    def demonstrate_playlist_operations(self) -> None:
        """Demonstrate advanced playlist operations."""
        if not self.db:
            print("❌ No database connection")
            return

        print(f"\n🎵 Demonstrating playlist operations...")

        try:
            # This is just a demonstration - we won't actually modify the database
            print(f"   Available operations:")
            print(f"   - Create playlists: db.create_playlist('My Playlist')")
            print(f"   - Create folders: db.create_playlist_folder('My Folder')")
            print(f"   - Add tracks: db.add_to_playlist(playlist, content)")
            print(f"   - Remove tracks: db.remove_from_playlist(playlist, song)")
            print(
                f"   - Move tracks: db.move_song_in_playlist(playlist, song, new_pos)"
            )
            print(f"   - Add new tracks: db.add_content('/path/to/track.mp3')")

            # Example of how to add a track (commented out to avoid modifying database)
            """
            # Add a new track to the database
            new_track = db.add_content(
                "/path/to/new/track.mp3",
                Title="New Track",
                Artist="New Artist"
            )

            # Get or create a playlist
            try:
                playlist = db.get_playlist(Name="My Test Playlist").one()
            except:
                playlist = db.create_playlist("My Test Playlist")

            # Add track to playlist
            song = db.add_to_playlist(playlist, new_track)

            # Commit changes
            db.commit()
            """

        except Exception as e:
            print(f"❌ Error in playlist operations: {e}")

    def work_with_xml_database(self) -> None:
        """Demonstrate XML database operations."""
        print(f"\n📄 Working with XML database...")

        try:
            xml_path = self.config.rekordbox_output_file

            # Try to read existing XML
            if xml_path.exists():
                print(f"   📖 Reading existing XML: {xml_path}")
                self.xml = RekordboxXml(xml_path)
                print(f"   Found {self.xml.num_tracks} tracks in XML")
            else:
                print(f"   📝 Creating new XML database")
                self.xml = RekordboxXml(
                    name="tidal-cleanup-advanced",
                    version="2.0.0",
                    company="Anton's Advanced DJ Tools",
                )

            # Demonstrate XML operations
            print(f"   Available XML operations:")
            print(f"   - Add tracks: xml.add_track(path, **metadata)")
            print(f"   - Create playlists: xml.add_playlist('Playlist Name')")
            print(f"   - Add to playlist: playlist.add_track(track_id)")
            print(f"   - Preserve metadata: PlayCount, Rating, Comments")
            print(f"   - Export to file: xml.save(path)")

        except Exception as e:
            print(f"❌ Error with XML database: {e}")

    def demonstrate_metadata_preservation(self) -> None:
        """Demonstrate how to preserve metadata during updates."""
        print(f"\n💾 Metadata preservation strategies...")

        print(f"   Key metadata to preserve:")
        print(f"   - Play counts (DJPlayCount in SQL, PlayCount in XML)")
        print(f"   - Ratings (Rating field)")
        print(f"   - Comments/Tags")
        print(f"   - Date added/modified")
        print(f"   - Hot cues and loop points")
        print(f"   - BPM analysis")
        print(f"   - Key detection")

        if self.db:
            try:
                # Example of preserving metadata when updating
                sample_track = self.db.get_content().first()
                if sample_track:
                    print(f"\n   Sample track metadata:")
                    print(f"   Title: {sample_track.Title}")
                    print(f"   Play Count: {sample_track.DJPlayCount}")
                    print(f"   Rating: {sample_track.Rating}")
                    print(f"   BPM: {sample_track.Bpm}")
                    print(
                        f"   Key: {sample_track.Key.ScaleName if sample_track.Key else 'Unknown'}"
                    )
                    print(f"   Date Added: {sample_track.DateAdded}")

                    # Show how to preserve when moving/updating
                    print(f"\n   Preservation strategy:")
                    print(f"   1. Read existing metadata before changes")
                    print(f"   2. Store key fields (play count, rating, etc.)")
                    print(f"   3. Apply updates while preserving important data")
                    print(f"   4. Use track signatures for duplicate detection")
            except Exception as e:
                print(f"   ❌ Error accessing metadata: {e}")

    def detect_track_movements(self, track_groups: Dict[str, List[Path]]) -> None:
        """Demonstrate track movement detection."""
        print(f"\n🔄 Track movement detection...")

        # Simulate track movement detection
        movements_detected = 0

        for signature, file_paths in track_groups.items():
            if len(file_paths) > 1:
                # Multiple locations for same track - potential movement
                print(f"   🔍 Track found in multiple playlists:")
                print(f"      Signature: {signature}")
                for path in file_paths:
                    playlist_name = path.parent.name
                    print(f"      - Playlist: {playlist_name}")
                    print(f"        File: {path.name}")
                movements_detected += 1

        if movements_detected == 0:
            print(f"   ✅ No obvious track movements detected")
        else:
            print(f"   📊 Found {movements_detected} potential track movements")
            print(
                f"   Strategy: Use file signatures to maintain single track in collection"
            )
            print(f"   while allowing presence in multiple playlists")

    def close_connections(self) -> None:
        """Close database connections."""
        if self.db:
            self.db.close()
            print(f"🔌 Database connection closed")


def main():
    """Main function to demonstrate advanced pyrekordbox capabilities."""
    print("🚀 Advanced pyrekordbox exploration starting...")

    try:
        config = Config()
        manager = AdvancedRekordboxManager(config)

        # Test SQL database connection
        sql_connected = manager.connect_to_sql_database()

        if sql_connected:
            # Explore SQL database
            manager.explore_sql_database_structure()
            manager.demonstrate_playlist_operations()

        # Work with XML regardless of SQL connection
        manager.work_with_xml_database()

        # Scan local files
        track_groups = manager.scan_mp3_directories()

        if track_groups:
            # Demonstrate advanced features
            if sql_connected:
                manager.sync_with_sql_database(track_groups)

            manager.detect_track_movements(track_groups)
            manager.demonstrate_metadata_preservation()

        print(f"\n✅ Advanced exploration completed!")

        # Summary of capabilities
        print(f"\n📋 Summary of pyrekordbox capabilities:")
        print(f"   🗄️  SQL Database (master.db):")
        print(f"      - Read/write Rekordbox 6/7 database")
        print(f"      - Full track metadata access")
        print(f"      - Playlist management (create/delete/modify)")
        print(f"      - Track operations (add/remove/move)")
        print(f"      - Relationship management (artists/albums/genres)")
        print(f"   📄 XML Database:")
        print(f"      - Import/export XML collections")
        print(f"      - Cross-platform compatibility")
        print(f"      - Metadata preservation")
        print(f"      - Playlist synchronization")
        print(f"   🔧 Advanced Features:")
        print(f"      - Automatic track deduplication")
        print(f"      - Metadata preservation during moves")
        print(f"      - Hot cues and loop points")
        print(f"      - Smart playlist support")
        print(f"      - Analysis file access (ANLZ)")

        print(f"\n🎯 Implementation recommendations:")
        print(f"   1. Use SQL database for real-time Rekordbox integration")
        print(f"   2. Use XML for backup/restore and cross-platform sharing")
        print(f"   3. Implement file signature-based deduplication")
        print(f"   4. Preserve play counts and ratings during sync")
        print(f"   5. Use track movement detection for smart updates")

    except Exception as e:
        print(f"❌ Error in main execution: {e}")
        import traceback

        traceback.print_exc()

    finally:
        if "manager" in locals():
            manager.close_connections()


if __name__ == "__main__":
    main()
