"""Genre hierarchy manager for organizing Rekordbox playlists."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


class GenreHierarchyManager:
    """Manages genre hierarchy mapping for organizing playlists."""

    def __init__(self, config_path: Path):
        """Initialize genre hierarchy manager.

        Args:
            config_path: Path to genre hierarchy JSON configuration file
        """
        self.config_path = config_path
        self.genre_to_category: Dict[str, str] = {}
        self.categories: Set[str] = set()
        self.default_category: str = "etc"

        self._load_config()

    def _load_config(self) -> None:
        """Load genre hierarchy configuration from JSON file."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            genre_hierarchy = config.get("genre_hierarchy", {})
            self.default_category = config.get("default_category", "etc")

            # Build reverse mapping: genre -> top-level category
            for category, genres in genre_hierarchy.items():
                self.categories.add(category)
                for genre in genres:
                    self.genre_to_category[genre] = category

            # Add default category
            self.categories.add(self.default_category)

            logger.info(
                f"Loaded genre hierarchy with {len(self.categories)} categories "
                f"and {len(self.genre_to_category)} genre mappings"
            )

        except FileNotFoundError:
            logger.error(f"Genre hierarchy config not found: {self.config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in genre hierarchy config: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load genre hierarchy config: {e}")
            raise

    def get_top_level_category(
        self, genre_tags: List[str], party_tags: List[str]
    ) -> str:
        """Determine the top-level category for a playlist based on tags.

        Logic:
        1. Check if any genre tag maps to a specific category
        2. Check if any party tag maps to a specific category
        3. If multiple matches, return the first one (genre priority)
        4. If no match, return the default category ("etc")

        Args:
            genre_tags: List of genre tags from playlist metadata
            party_tags: List of party tags from playlist metadata

        Returns:
            Top-level category name
        """
        # First check genre tags (higher priority)
        for genre in sorted(genre_tags):  # Sorted for consistency
            category = self.genre_to_category.get(genre)
            if category:
                logger.debug(f"Genre '{genre}' maps to category '{category}'")
                return category

        # Then check party tags
        for party in sorted(party_tags):
            category = self.genre_to_category.get(party)
            if category:
                logger.debug(f"Party tag '{party}' maps to category '{category}'")
                return category

        # No match found, use default
        logger.debug(
            f"No category match for genres={genre_tags}, parties={party_tags}, "
            f"using default '{self.default_category}'"
        )
        return self.default_category

    def get_all_categories(self) -> Set[str]:
        """Get all top-level category names.

        Returns:
            Set of category names
        """
        return self.categories.copy()

    def is_valid_category(self, category: str) -> bool:
        """Check if a category name is valid.

        Args:
            category: Category name to check

        Returns:
            True if valid, False otherwise
        """
        return category in self.categories
