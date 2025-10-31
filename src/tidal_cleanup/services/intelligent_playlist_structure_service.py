"""Service for creating intelligent playlist structure in Rekordbox.

This service handles Step 1 of the sync algorithm:
- Creates folder structure based on genre hierarchy
- Creates intelligent playlists with MyTag queries
- Handles event folders
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from pyrekordbox import db6
    from pyrekordbox.db6.smartlist import (
        LogicalOperator,
        Operator,
        Property,
        SmartList,
    )

    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    db6 = None
    SmartList = None
    Property = None
    Operator = None
    LogicalOperator = None

from .mytag_manager import MyTagManager

logger = logging.getLogger(__name__)

try:
    from pyrekordbox import db6

    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    db6 = None

logger = logging.getLogger(__name__)


class IntelligentPlaylistStructureService:
    """Service for managing intelligent playlist folder structure in Rekordbox."""

    def __init__(self, db: Any, mytag_mapping_path: Path) -> None:
        """Initialize the service.

        Args:
            db: Rekordbox6Database instance
            mytag_mapping_path: Path to rekordbox_mytag_mapping.json
        """
        if not PYREKORDBOX_AVAILABLE:
            raise RuntimeError("pyrekordbox is not available")

        self.db = db
        self.mytag_mapping_path = mytag_mapping_path
        self.mytag_mapping: Dict[str, Any] = {}
        self._load_mytag_mapping()

        # Cache for folders - key: "parent_id:folder_name"
        self._folder_cache: Dict[str, Any] = {}

        # Initialize folder mapping from existing database
        self._initialize_folder_mapping()

    def _load_mytag_mapping(self) -> None:
        """Load the MyTag mapping configuration."""
        try:
            with open(self.mytag_mapping_path, "r", encoding="utf-8") as f:
                self.mytag_mapping = json.load(f)
            logger.info(f"Loaded MyTag mapping from {self.mytag_mapping_path}")
        except Exception as e:
            logger.error(f"Failed to load MyTag mapping: {e}")
            raise

    def _initialize_folder_mapping(self) -> None:
        """Build initial folder mapping from existing database folders.

        This prevents duplicate folder creation by caching all existing folders with
        their parent relationships.
        """
        try:
            # Query all folders (Attribute=1) from database
            all_folders = (
                self.db.query(db6.DjmdPlaylist)
                .filter(db6.DjmdPlaylist.Attribute == 1)
                .all()
            )

            logger.info(f"Found {len(all_folders)} existing folders in database")

            # Build cache with key: "parent_id:folder_name"
            # Normalize empty ParentID to None for consistency
            for folder in all_folders:
                parent_id = folder.ParentID
                # Normalize various "root" representations to None
                if not parent_id or parent_id == "" or parent_id == "root":
                    parent_id = None
                cache_key = f"{parent_id}:{folder.Name}"
                self._folder_cache[cache_key] = folder
                logger.debug(
                    f"Cached folder: {folder.Name} "
                    f"(ID: {folder.ID}, Parent: {parent_id}, Key: {cache_key})"
                )

            logger.info(
                f"Initialized folder cache with {len(self._folder_cache)} entries"
            )
        except Exception as e:
            logger.warning(f"Failed to initialize folder mapping: {e}")
            # Not fatal - will create folders as needed

    def _get_genre_hierarchy(self) -> Dict[str, Dict[str, str]]:
        """Extract genre hierarchy from mytag_mapping.

        Returns:
            Dictionary mapping top-level genres to their sub-genres:
            {
                "House": {"🏃🏼‍♂️": "House Progressive", "🥊": "House Ghetto", ...},
                "Deep House": {"🧘🏼‍♂️": "House Chill", ...},
                ...
            }
        """
        track_metadata = self.mytag_mapping.get("Track-Metadata", {})
        genre_data: Dict[str, Dict[str, str]] = track_metadata.get("Genre", {})
        return genre_data

    def _scan_genre_folders(self, parent_id: str) -> Dict[str, Dict[str, Any]]:
        """Scan existing genre folders and their playlists.

        Args:
            parent_id: The ID of the parent "Genres" folder

        Returns:
            Dictionary mapping top-level genre names to their folder and playlists:
            {
                "House": {
                    "folder": <DjmdPlaylist object>,
                    "playlists": {
                        "🏃🏼‍♂️ House Progressive": <DjmdPlaylist object>,
                        "🥊 House Ghetto": <DjmdPlaylist object>
                    }
                }
            }
        """
        result: Dict[str, Dict[str, Any]] = {}

        # Query all top-level genre folders under the Genres folder
        genre_folders = (
            self.db.query(db6.DjmdPlaylist)
            .filter(
                (db6.DjmdPlaylist.ParentID == parent_id)
                & (db6.DjmdPlaylist.Attribute == 1)
            )
            .all()
        )

        for genre_folder in genre_folders:
            genre_name = genre_folder.Name
            result[genre_name] = {"folder": genre_folder, "playlists": {}}

            # Query all intelligent playlists under this top-level genre folder
            playlists = (
                self.db.query(db6.DjmdPlaylist)
                .filter(
                    (db6.DjmdPlaylist.ParentID == genre_folder.ID)
                    & (db6.DjmdPlaylist.Attribute == 4)
                )
                .all()
            )

            for playlist in playlists:
                result[genre_name]["playlists"][playlist.Name] = playlist

        return result

    def _remove_orphaned_top_level_folders(
        self,
        existing_folders: Dict[str, Dict[str, Any]],
        expected_folders: set[str],
        results: Dict[str, int],
    ) -> None:
        """Remove top-level genre folders that are not in the configuration.

        Args:
            existing_folders: Current folder structure from Rekordbox
            expected_folders: Set of folder names from JSON config
            results: Results dictionary to update with counts
        """
        for folder_name in existing_folders:
            if folder_name not in expected_folders:
                logger.info(f"Removing orphaned top-level folder: {folder_name}")
                folder_data = existing_folders[folder_name]
                # Remove all playlists in this folder first
                for playlist in folder_data["playlists"].values():
                    self.db.delete(playlist)
                    results["playlists_removed"] += 1
                # Remove the folder
                self.db.delete(folder_data["folder"])
                results["removed"] += 1

    def _sync_genre_playlists_in_folder(
        self,
        genre_folder: Any,
        genre_tags: Dict[str, str],
        existing_playlists: Dict[str, Any],
        results: Dict[str, int],
    ) -> None:
        """Sync intelligent playlists within a genre folder.

        Args:
            genre_folder: The parent genre folder object
            genre_tags: Dictionary mapping emoji to genre tag value
            existing_playlists: Existing playlists in this folder
            results: Results dictionary to update with counts
        """
        # Build expected playlists: emoji + genre_tag_name
        expected_playlists = {}
        for emoji, genre_tag_value in genre_tags.items():
            playlist_name = f"{emoji} {genre_tag_value}"
            expected_playlists[playlist_name] = genre_tag_value

        # Remove orphaned playlists
        for playlist_name in existing_playlists:
            if playlist_name not in expected_playlists:
                logger.info(f"  Removing orphaned playlist: {playlist_name}")
                self.db.delete(existing_playlists[playlist_name])
                results["playlists_removed"] += 1

        # Create/update playlists for each genre tag
        for playlist_name, genre_tag_value in expected_playlists.items():
            if playlist_name in existing_playlists:
                # Update existing playlist
                logger.info(f"  Updating intelligent playlist: {playlist_name}")
                self._create_or_update_intelligent_playlist(
                    playlist_name=playlist_name,
                    parent_id=genre_folder.ID,
                    mytag_group="Genre",
                    mytag_value=genre_tag_value,
                )
                results["playlists_updated"] += 1
            else:
                # Create new playlist
                logger.info(f"  Creating intelligent playlist: {playlist_name}")
                self._create_or_update_intelligent_playlist(
                    playlist_name=playlist_name,
                    parent_id=genre_folder.ID,
                    mytag_group="Genre",
                    mytag_value=genre_tag_value,
                )
                results["playlists_created"] += 1

    def _scan_playlists_in_folder(self, folder_id: str) -> Dict[str, Any]:
        """Scan all intelligent playlists in a folder.

        Args:
            folder_id: ID of the folder to scan

        Returns:
            Dictionary mapping playlist name to playlist object
        """
        playlists = (
            self.db.query(db6.DjmdPlaylist)
            .filter(
                (db6.DjmdPlaylist.ParentID == folder_id)
                & (db6.DjmdPlaylist.Attribute == 4)  # Intelligent playlist
            )
            .all()
        )
        return {playlist.Name: playlist for playlist in playlists}

    def _sync_genre_playlists_in_status_folder(
        self,
        status_folder: Any,
        status_name: str,
        genre_tags: Dict[str, str],
        existing_playlists: Dict[str, Any],
        results: Dict[str, int],
    ) -> None:
        """Sync intelligent playlists within a status subfolder.

        Creates playlists that match BOTH the genre AND the status.
        For "Current" status, creates playlists with NO status tag.

        Args:
            status_folder: The parent status folder object
            status_name: Name of the status (Archived, Old, Recherche, Current)
            genre_tags: Dictionary mapping emoji to genre tag value
            existing_playlists: Existing playlists in this folder
            results: Results dictionary to update with counts
        """
        # Build expected playlists: emoji + genre_tag_name
        expected_playlists = {}
        for emoji, genre_tag_value in genre_tags.items():
            playlist_name = f"{emoji} {genre_tag_value}"
            expected_playlists[playlist_name] = genre_tag_value

        # Remove orphaned playlists
        for playlist_name in existing_playlists:
            if playlist_name not in expected_playlists:
                logger.info(
                    f"    Removing orphaned playlist: {status_name}/{playlist_name}"
                )
                self.db.delete(existing_playlists[playlist_name])
                results["playlists_removed"] += 1

        # Create/update playlists for each genre tag
        for playlist_name, genre_tag_value in expected_playlists.items():
            if playlist_name in existing_playlists:
                # Update existing playlist
                logger.info(
                    f"    Updating intelligent playlist: {status_name}/{playlist_name}"
                )
                self._create_or_update_status_playlist(
                    playlist_name=playlist_name,
                    parent_id=status_folder.ID,
                    genre_value=genre_tag_value,
                    status_value=status_name if status_name != "Current" else None,
                )
                results["playlists_updated"] += 1
            else:
                # Create new playlist
                logger.info(
                    f"    Creating intelligent playlist: {status_name}/{playlist_name}"
                )
                self._create_or_update_status_playlist(
                    playlist_name=playlist_name,
                    parent_id=status_folder.ID,
                    genre_value=genre_tag_value,
                    status_value=status_name if status_name != "Current" else None,
                )
                results["playlists_created"] += 1

    def sync_intelligent_playlist_structure(self) -> Dict[str, Any]:
        """Create/update the intelligent playlist structure.

        This method compares the existing Rekordbox structure with the JSON
        configuration and:
        - Creates missing folders and playlists
        - Updates existing playlists if needed
        - Removes orphaned folders/playlists not in config

        Returns:
            Dictionary with sync results
        """
        logger.info("Starting intelligent playlist structure sync...")

        results = {
            "genres_created": 0,
            "genres_updated": 0,
            "genres_removed": 0,
            "events_folders_created": 0,
            "playlists_created": 0,
            "playlists_updated": 0,
            "playlists_removed": 0,
            "total_playlists": 0,
        }

        try:
            # Step 1: Create or get "Genres" top-level directory
            genres_folder = self._get_or_create_folder("Genres", parent_id=None)
            logger.info(
                f"✓ Genres folder: {genres_folder.Name} (ID: {genres_folder.ID})"
            )

            # Step 2: Sync genre structure under "Genres"
            genre_results = self._sync_genre_structure(genres_folder.ID)
            results["genres_created"] = genre_results["created"]
            results["genres_updated"] = genre_results["updated"]
            results["genres_removed"] = genre_results["removed"]
            results["playlists_created"] = genre_results["playlists_created"]
            results["playlists_updated"] = genre_results["playlists_updated"]
            results["playlists_removed"] = genre_results["playlists_removed"]
            results["total_playlists"] = genre_results["playlists_created"]

            # Step 3: Create or get "Events" top-level directory
            events_folder = self._get_or_create_folder("Events", parent_id=None)
            logger.info(
                f"✓ Events folder: {events_folder.Name} (ID: {events_folder.ID})"
            )

            # Step 4: Sync event subdirectories and store folder IDs
            event_results = self._sync_event_folders(events_folder.ID)
            results["events_folders_created"] = event_results.get("created", 0)

            # Store Events folder IDs for TrackTagSyncService to use
            results["events_folder_id"] = events_folder.ID
            results["events_subfolders"] = event_results.get("folder_ids", {})

            self.db.commit()
            logger.info("✓ Intelligent playlist structure sync completed")

            return results

        except Exception as e:
            logger.error(f"Failed to sync intelligent playlist structure: {e}")
            self.db.rollback()
            raise

    def _sync_genre_structure(self, parent_id: str) -> Dict[str, int]:
        """Sync genre folders and intelligent playlists under Genres.

        The JSON structure is nested:
        - Track-Metadata → Genre → Top-Level Genres (House, Disco, etc.)
        - Each top-level genre contains actual genre tags

        Creates:
        - Top-level genre folders (House, Disco, Techno, etc.) under "Genres"
        - Status subfolders (Archived, Old, Recherche, Current) under each genre
        - Intelligent playlists for each actual genre tag inside status folders

        Example:
        Genres/
          House/
            Archived/
              🇮🇹 House Italo (smart playlist for Genre:House Italo AND Status:Archived)
              ☀️ House House (smart playlist for Genre:House House AND Status:Archived)
            Current/
              🪇 House Groove (smart playlist for Genre:House Groove, no status tag)
          Disco/
            Recherche/
              🎈 Disco Nu (smart playlist for Genre:Disco Nu AND Status:Recherche)

        Compares existing structure with JSON configuration:
        - Creates missing folders and playlists
        - Updates existing playlists if queries changed
        - Removes orphaned folders/playlists not in config

        Args:
            parent_id: The ID of the parent "Genres" folder

        Returns:
            Dictionary with counts of created/updated/removed items
        """
        logger.info("Syncing genre structure...")
        results = {
            "created": 0,
            "updated": 0,
            "removed": 0,
            "playlists_created": 0,
            "playlists_updated": 0,
            "playlists_removed": 0,
        }

        # Get the nested genre structure from JSON
        track_metadata = self.mytag_mapping.get("Track-Metadata", {})
        genre_structure = track_metadata.get("Genre", {})

        # Scan existing top-level genre folders
        existing_top_level = self._scan_genre_folders(parent_id)
        expected_top_level = set(genre_structure.keys())

        # Remove orphaned top-level genre folders
        self._remove_orphaned_top_level_folders(
            existing_top_level, expected_top_level, results
        )

        # Get Status values from config
        status_values = list(
            self.mytag_mapping.get("Track-Metadata", {}).get("Status", {}).values()
        )
        status_folders = status_values + ["Current"]  # Add "Current" for no status

        # Create/update top-level genre folders with status subfolders
        for top_level_genre, genre_tags in genre_structure.items():
            logger.info(f"Processing top-level genre: {top_level_genre}")

            # Create or get top-level genre folder (e.g., "House", "Disco")
            genre_folder = self._get_or_create_folder(
                top_level_genre, parent_id=parent_id
            )
            is_new_folder = top_level_genre not in existing_top_level

            if is_new_folder:
                results["created"] += 1

            # Create Status subfolders under this genre
            for status_name in status_folders:
                status_folder = self._get_or_create_folder(
                    status_name, parent_id=genre_folder.ID
                )
                logger.info(
                    f"  Status folder: {top_level_genre}/{status_name} "
                    f"(ID: {status_folder.ID})"
                )

                # Get existing playlists in this status folder
                existing_playlists = self._scan_playlists_in_folder(status_folder.ID)

                # Sync playlists within this status folder
                # For each genre tag, create playlist in appropriate status folder
                self._sync_genre_playlists_in_status_folder(
                    status_folder,
                    status_name,
                    genre_tags,
                    existing_playlists,
                    results,
                )

        logger.info(
            f"✓ Genre structure synced: "
            f"{results['created']} top-level folders created, "
            f"{results['removed']} folders removed, "
            f"{results['playlists_created']} playlists created, "
            f"{results['playlists_updated']} playlists updated, "
            f"{results['playlists_removed']} playlists removed"
        )
        return results

    def _sync_event_folders(self, events_parent_id: str) -> Dict[str, Any]:
        """Sync event folder structure.

        Compares existing structure with expected folders:
        - Creates missing event folders
        - Removes orphaned event folders not in expected list

        Args:
            events_parent_id: Parent ID of the "Events" folder

        Returns:
            Dictionary with count of created/removed folders and folder IDs
        """
        expected_folders = ["Partys", "Sets", "Radio Moafunk"]
        results: Dict[str, Any] = {"created": 0, "removed": 0, "folder_ids": {}}

        # Scan existing event folders
        existing_folders = (
            self.db.query(db6.DjmdPlaylist)
            .filter(
                (db6.DjmdPlaylist.ParentID == events_parent_id)
                & (db6.DjmdPlaylist.Attribute == 1)
            )
            .all()
        )
        existing_names = {folder.Name: folder for folder in existing_folders}

        # Remove orphaned folders
        for folder_name, folder in existing_names.items():
            if folder_name not in expected_folders:
                logger.info(f"  Removing orphaned event folder: {folder_name}")
                self.db.delete(folder)
                results["removed"] += 1

        # Create missing folders or get existing ones
        for folder_name in expected_folders:
            if folder_name not in existing_names:
                folder = self._get_or_create_folder(
                    folder_name, parent_id=events_parent_id
                )
                logger.info(
                    f"  ✓ Created event folder: {folder_name} (ID: {folder.ID})"
                )
                results["created"] += 1
                results["folder_ids"][folder_name] = folder.ID
            else:
                folder = existing_names[folder_name]
                logger.info(f"  ✓ Event folder exists: {folder_name}")
                results["folder_ids"][folder_name] = folder.ID

        logger.info(
            f"✓ Event structure synced: "
            f"{results['created']} folders created, "
            f"{results['removed']} folders removed"
        )
        return results

    def _get_or_create_folder(
        self, folder_name: str, parent_id: Optional[str] = None
    ) -> Any:
        """Get existing folder or create new one.

        Args:
            folder_name: Name of the folder
            parent_id: Parent folder ID (None for root)

        Returns:
            DjmdPlaylist instance with Attribute=1 (folder)
        """
        # Check cache first
        cache_key = f"{parent_id}:{folder_name}"
        if cache_key in self._folder_cache:
            folder = self._folder_cache[cache_key]
            logger.info(f"Found cached folder: {folder_name} (ID: {folder.ID})")
            return folder

        # Try to find existing folder in database
        query = self.db.get_playlist(Name=folder_name, Attribute=1)

        if parent_id:
            folder = query.filter(db6.DjmdPlaylist.ParentID == parent_id).first()
        else:
            folder = query.filter(
                (db6.DjmdPlaylist.ParentID == "")
                | (db6.DjmdPlaylist.ParentID.is_(None))
            ).first()

        if folder:
            logger.info(f"Using existing folder: {folder_name} (ID: {folder.ID})")
            self._folder_cache[cache_key] = folder
            return folder

        # Create new folder
        logger.info(f"Creating new folder: {folder_name} (parent: {parent_id})")
        folder = self.db.create_playlist_folder(folder_name, parent=parent_id)
        self.db.flush()

        self._folder_cache[cache_key] = folder
        return folder

    def _create_or_update_intelligent_playlist(
        self,
        playlist_name: str,
        parent_id: str,
        mytag_group: str,
        mytag_value: str,
    ) -> Any:
        """Create or update an intelligent playlist with MyTag query.

        Args:
            playlist_name: Name of the intelligent playlist
            parent_id: Parent folder ID
            mytag_group: MyTag group name (e.g., "Genre")
            mytag_value: MyTag value (e.g., "House Italo")

        Returns:
            DjmdPlaylist instance with Attribute=4 (smart playlist)
        """
        # Try to find existing smart playlist
        query = self.db.get_playlist(Name=playlist_name, Attribute=4)
        playlist = query.filter(db6.DjmdPlaylist.ParentID == parent_id).first()

        if playlist:
            logger.debug(f"Found existing smart playlist: {playlist_name}")
            return playlist

        # Create new smart playlist
        logger.info(f"Creating smart playlist: {playlist_name}")

        # Get the MyTag ID for the specified group and value
        mytag_manager = MyTagManager(self.db)
        mytag = mytag_manager.create_or_get_tag(mytag_value, mytag_group)

        # Create SmartList with MyTag condition
        smart_list = SmartList(logical_operator=LogicalOperator.ALL)

        # Add condition: MyTag contains the specified value
        # The value needs to be the MyTag ID as a POSITIVE number
        # MyTag only supports CONTAINS and NOT_CONTAINS operators
        mytag_id_str = str(mytag.ID)

        smart_list.add_condition(
            prop=Property.MYTAG,
            operator=Operator.CONTAINS,
            value_left=mytag_id_str,
        )

        # Create the smart playlist with the condition
        playlist = self.db.create_smart_playlist(
            name=playlist_name,
            smart_list=smart_list,
            parent=parent_id,
        )

        self.db.flush()
        logger.debug(
            f"Created smart playlist '{playlist_name}' with "
            f"MyTag condition: {mytag_group}={mytag_value} (ID: {mytag.ID})"
        )

        return playlist

    def _create_or_update_status_playlist(
        self,
        playlist_name: str,
        parent_id: str,
        genre_value: str,
        status_value: Optional[str] = None,
    ) -> Any:
        """Create or update an intelligent playlist with Genre AND Status query.

        Args:
            playlist_name: Name of the intelligent playlist
            parent_id: Parent folder ID
            genre_value: Genre tag value (e.g., "House Italo")
            status_value: Status tag value (e.g., "Archived", "Old", None for Current)

        Returns:
            DjmdPlaylist instance with Attribute=4 (smart playlist)
        """
        # Try to find existing smart playlist
        query = self.db.get_playlist(Name=playlist_name, Attribute=4)
        playlist = query.filter(db6.DjmdPlaylist.ParentID == parent_id).first()

        if playlist:
            logger.debug(f"Found existing smart playlist: {playlist_name}")
            return playlist

        # Create new smart playlist
        logger.info(f"Creating smart playlist: {playlist_name}")

        # Get the MyTag IDs
        mytag_manager = MyTagManager(self.db)
        genre_tag = mytag_manager.create_or_get_tag(genre_value, "Genre")

        # Create SmartList with ALL conditions (Genre AND Status)
        smart_list = SmartList(logical_operator=LogicalOperator.ALL)

        # Add Genre condition
        smart_list.add_condition(
            prop=Property.MYTAG,
            operator=Operator.CONTAINS,
            value_left=str(genre_tag.ID),
        )

        # Add Status condition if specified (not "Current")
        if status_value:
            status_tag = mytag_manager.create_or_get_tag(status_value, "Status")
            smart_list.add_condition(
                prop=Property.MYTAG,
                operator=Operator.CONTAINS,
                value_left=str(status_tag.ID),
            )

        # Create the smart playlist with the conditions
        playlist = self.db.create_smart_playlist(
            name=playlist_name,
            smart_list=smart_list,
            parent=parent_id,
        )

        self.db.flush()

        status_info = f" AND Status={status_value}" if status_value else ""
        logger.debug(
            f"Created smart playlist '{playlist_name}' with "
            f"Genre={genre_value}{status_info}"
        )

        return playlist
