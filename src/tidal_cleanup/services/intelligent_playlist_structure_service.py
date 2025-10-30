"""Service for creating intelligent playlist structure in Rekordbox.

This service handles Step 1 of the sync algorithm:
- Creates folder structure based on genre hierarchy
- Creates intelligent playlists with MyTag queries
- Handles event folders
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

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

        # Cache for folders
        self._folder_cache: Dict[str, Any] = {}

    def _load_mytag_mapping(self) -> None:
        """Load the MyTag mapping configuration."""
        try:
            with open(self.mytag_mapping_path, "r", encoding="utf-8") as f:
                self.mytag_mapping = json.load(f)
            logger.info(f"Loaded MyTag mapping from {self.mytag_mapping_path}")
        except Exception as e:
            logger.error(f"Failed to load MyTag mapping: {e}")
            raise

    def sync_intelligent_playlist_structure(self) -> Dict[str, Any]:
        """Create/update the intelligent playlist structure.

        Returns:
            Dictionary with sync results
        """
        logger.info("Starting intelligent playlist structure sync...")

        results = {
            "genres_created": 0,
            "genres_updated": 0,
            "events_folders_created": 0,
            "total_playlists": 0,
        }

        try:
            # Step 1: Create "Genres" top-level directory
            genres_folder = self._get_or_create_folder("Genres", parent_id=None)
            logger.info(
                f"✓ Genres folder: {genres_folder.Name} (ID: {genres_folder.ID})"
            )

            # Step 2: Create genre structure under "Genres"
            genre_results = self._sync_genre_structure(genres_folder.ID)
            results["genres_created"] = genre_results["created"]
            results["genres_updated"] = genre_results["updated"]
            results["total_playlists"] += genre_results["playlists"]

            # Step 3: Create "Events" top-level directory
            events_folder = self._get_or_create_folder("Events", parent_id=None)
            logger.info(
                f"✓ Events folder: {events_folder.Name} (ID: {events_folder.ID})"
            )

            # Step 4: Create event subdirectories (Partys, Sets, Radio Moafunk)
            event_folders = self._sync_event_folders(events_folder.ID)
            results["events_folders_created"] = len(event_folders)

            self.db.commit()
            logger.info("✓ Intelligent playlist structure sync completed")

            return results

        except Exception as e:
            logger.error(f"Failed to sync intelligent playlist structure: {e}")
            self.db.rollback()
            raise

    def _sync_genre_structure(self, genres_parent_id: str) -> Dict[str, int]:
        """Create genre folder structure with intelligent playlists.

        Args:
            genres_parent_id: Parent ID of the "Genres" folder

        Returns:
            Dictionary with creation statistics
        """
        results = {"created": 0, "updated": 0, "playlists": 0}

        # Get genre configuration
        track_metadata = self.mytag_mapping.get("Track-Metadata", {})
        genre_config = track_metadata.get("Genre", {})

        if not genre_config:
            logger.warning("No Genre configuration found in MyTag mapping")
            return results

        logger.info(f"Processing {len(genre_config)} top-level genres...")

        # Iterate through top-level genres
        for top_level_genre, sub_genres in genre_config.items():
            logger.info(f"Processing top-level genre: {top_level_genre}")

            # Create top-level genre folder
            top_level_folder = self._get_or_create_folder(
                top_level_genre, parent_id=genres_parent_id
            )
            results["created"] += 1

            # Create intelligent playlists for each sub-genre
            if isinstance(sub_genres, dict):
                for emoji, genre_name in sub_genres.items():
                    logger.info(
                        f"  Creating intelligent playlist for: {genre_name} ({emoji})"
                    )

                    # Create intelligent playlist with MyTag query
                    self._create_or_update_intelligent_playlist(
                        playlist_name=genre_name,
                        parent_id=top_level_folder.ID,
                        mytag_group="Genre",
                        mytag_value=genre_name,
                    )
                    results["playlists"] += 1

        return results

    def _sync_event_folders(self, events_parent_id: str) -> List[str]:
        """Create event folder structure.

        Args:
            events_parent_id: Parent ID of the "Events" folder

        Returns:
            List of created folder names
        """
        event_folders = ["Partys", "Sets", "Radio Moafunk"]
        created_folders = []

        for folder_name in event_folders:
            folder = self._get_or_create_folder(folder_name, parent_id=events_parent_id)
            created_folders.append(folder_name)
            logger.info(f"  ✓ Event folder: {folder_name} (ID: {folder.ID})")

        return created_folders

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
            return self._folder_cache[cache_key]

        # Try to find existing folder
        query = self.db.get_playlist(Name=folder_name, Attribute=1)

        if parent_id:
            folder = query.filter(db6.DjmdPlaylist.ParentID == parent_id).first()
        else:
            folder = query.filter(
                (db6.DjmdPlaylist.ParentID == "")
                | (db6.DjmdPlaylist.ParentID.is_(None))
            ).first()

        if folder:
            logger.debug(f"Found existing folder: {folder_name}")
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

    def cleanup_orphaned_folders(self) -> int:
        """Remove empty folders that are not in the configuration.

        Returns:
            Number of folders removed
        """
        # TODO: Implement cleanup logic
        # This would scan existing folders and remove those that:
        # 1. Are empty (no playlists)
        # 2. Are not in the current mytag_mapping configuration
        logger.info("Cleanup of orphaned folders not yet implemented")
        return 0
