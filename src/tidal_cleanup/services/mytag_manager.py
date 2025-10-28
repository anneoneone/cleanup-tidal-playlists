"""MyTag management utilities for Rekordbox database operations."""

import logging
from typing import Any, List, Optional, Set

try:
    from pyrekordbox import db6

    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    db6 = None

logger = logging.getLogger(__name__)


class MyTagManager:
    """Manager for Rekordbox MyTag operations."""

    def __init__(self, db: Any) -> None:
        """Initialize MyTag manager.

        Args:
            db: Rekordbox6Database instance
        """
        if not PYREKORDBOX_AVAILABLE:
            raise RuntimeError("pyrekordbox is not available")
        self.db = db

    def create_or_get_group(self, group_name: str) -> Any:
        """Create or get a MyTag group (section).

        Args:
            group_name: Name of the group/section

        Returns:
            DjmdMyTag instance for the group
        """
        # Check if group exists
        group = (
            self.db.query(db6.DjmdMyTag)
            .filter(
                db6.DjmdMyTag.Name == group_name,
                db6.DjmdMyTag.Attribute == 1,  # 1 = section/group
            )
            .first()
        )

        if group is None:
            logger.info(f"Creating MyTag group: {group_name}")

            # Get the highest Seq number for root-level groups
            max_seq = (
                self.db.query(db6.DjmdMyTag)
                .filter(db6.DjmdMyTag.Attribute == 1, db6.DjmdMyTag.ParentID == "root")
                .count()
            )

            group = db6.DjmdMyTag(
                ID=self.db.generate_unused_id(db6.DjmdMyTag),
                Seq=max_seq + 1,
                Name=group_name,
                Attribute=1,  # 1 = section/group
                ParentID="root",  # Must be "root" string, not None
            )
            self.db.add(group)
            self.db.flush()  # Ensure ID is available

        return group

    def create_or_get_tag(self, tag_name: str, group_name: str) -> Any:
        """Create or get a MyTag value within a group.

        Args:
            tag_name: Name of the tag value
            group_name: Name of the parent group

        Returns:
            DjmdMyTag instance for the tag value
        """
        # Ensure group exists
        group = self.create_or_get_group(group_name)

        # Check if tag value exists under this group
        tag = (
            self.db.query(db6.DjmdMyTag)
            .filter(
                db6.DjmdMyTag.Name == tag_name,
                db6.DjmdMyTag.ParentID == group.ID,
                db6.DjmdMyTag.Attribute == 0,  # 0 = value
            )
            .first()
        )

        if tag is None:
            logger.info(f"Creating MyTag value: {group_name}/{tag_name}")

            # Get the highest Seq number for values in this group
            max_seq = (
                self.db.query(db6.DjmdMyTag)
                .filter(
                    db6.DjmdMyTag.Attribute == 0, db6.DjmdMyTag.ParentID == group.ID
                )
                .count()
            )

            tag = db6.DjmdMyTag(
                ID=self.db.generate_unused_id(db6.DjmdMyTag),
                Seq=max_seq + 1,
                Name=tag_name,
                Attribute=0,  # 0 = value
                ParentID=group.ID,
            )
            self.db.add(tag)
            self.db.flush()

        return tag

    def link_content_to_tag(self, content: Any, tag: Any) -> bool:
        """Link a content (track) to a MyTag value.

        Args:
            content: DjmdContent instance
            tag: DjmdMyTag instance (must be a value, not a group)

        Returns:
            True if linked (new or existing), False on error
        """
        try:
            # Check if link already exists
            existing_link = (
                self.db.query(db6.DjmdSongMyTag)
                .filter(
                    db6.DjmdSongMyTag.ContentID == content.ID,
                    db6.DjmdSongMyTag.MyTagID == tag.ID,
                )
                .first()
            )

            if existing_link is None:
                logger.debug(f"Linking content {content.ID} to MyTag: {tag.Name}")
                song_tag = db6.DjmdSongMyTag(
                    ID=self.db.generate_unused_id(db6.DjmdSongMyTag),
                    MyTagID=tag.ID,
                    ContentID=content.ID,
                    TrackNo=1,
                )
                self.db.add(song_tag)
                self.db.flush()
            else:
                logger.debug(
                    f"Content {content.ID} already linked to MyTag: {tag.Name}"
                )

            return True

        except Exception as e:
            logger.error(f"Failed to link content to tag: {e}")
            return False

    def unlink_content_from_tag(self, content: Any, tag: Any) -> bool:
        """Unlink a content (track) from a MyTag value.

        Args:
            content: DjmdContent instance
            tag: DjmdMyTag instance

        Returns:
            True if unlinked, False if not found or error
        """
        try:
            # Find the link
            link = (
                self.db.query(db6.DjmdSongMyTag)
                .filter(
                    db6.DjmdSongMyTag.ContentID == content.ID,
                    db6.DjmdSongMyTag.MyTagID == tag.ID,
                )
                .first()
            )

            if link:
                logger.debug(f"Unlinking content {content.ID} from MyTag: {tag.Name}")
                self.db.delete(link)
                self.db.flush()
                return True
            else:
                logger.debug(
                    f"No link found between content {content.ID} and MyTag: {tag.Name}"
                )
                return False

        except Exception as e:
            logger.error(f"Failed to unlink content from tag: {e}")
            return False

    def get_content_tags(
        self, content: Any, group_name: Optional[str] = None
    ) -> List[Any]:
        """Get all MyTag values linked to a content.

        Args:
            content: DjmdContent instance
            group_name: Optional group name to filter by

        Returns:
            List of DjmdMyTag instances
        """
        try:
            # Get all tag links for this content
            links = (
                self.db.query(db6.DjmdSongMyTag)
                .filter(db6.DjmdSongMyTag.ContentID == content.ID)
                .all()
            )

            tags = []
            for link in links:
                tag = (
                    self.db.query(db6.DjmdMyTag)
                    .filter(db6.DjmdMyTag.ID == link.MyTagID)
                    .first()
                )
                if tag:
                    # Filter by group if specified
                    if group_name:
                        parent = (
                            self.db.query(db6.DjmdMyTag)
                            .filter(db6.DjmdMyTag.ID == tag.ParentID)
                            .first()
                        )
                        if parent and parent.Name == group_name:
                            tags.append(tag)
                    else:
                        tags.append(tag)

            return tags

        except Exception as e:
            logger.error(f"Failed to get content tags: {e}")
            return []

    def get_content_tag_names(
        self, content: Any, group_name: Optional[str] = None
    ) -> Set[str]:
        """Get names of all MyTag values linked to a content.

        Args:
            content: DjmdContent instance
            group_name: Optional group name to filter by

        Returns:
            Set of tag names
        """
        tags = self.get_content_tags(content, group_name)
        return {tag.Name for tag in tags}

    def ensure_no_genre_tag(self, content: Any) -> bool:
        """Ensure NoGenre tag is present when no other Genre tags exist.

        This should be called after removing Genre tags from a track.

        Args:
            content: DjmdContent instance

        Returns:
            True if NoGenre tag was added, False if Genre tags exist
        """
        # Check if content has any Genre tags
        genre_tags = self.get_content_tags(content, group_name="Genre")

        if not genre_tags:
            # No genre tags, add NoGenre
            no_genre_tag = self.create_or_get_tag("NoGenre", "Genre")
            self.link_content_to_tag(content, no_genre_tag)
            logger.info(f"Added NoGenre tag to content {content.ID}")
            return True

        return False

    def remove_no_genre_tag_if_needed(self, content: Any) -> bool:
        """Remove NoGenre tag if other Genre tags are present.

        This should be called after adding Genre tags to a track.

        Args:
            content: DjmdContent instance

        Returns:
            True if NoGenre tag was removed, False otherwise
        """
        # Check if content has Genre tags other than NoGenre
        genre_tags = self.get_content_tags(content, group_name="Genre")
        non_no_genre_tags = [tag for tag in genre_tags if tag.Name != "NoGenre"]

        if non_no_genre_tags:
            # Has real genre tags, remove NoGenre if it exists
            no_genre_tags = [tag for tag in genre_tags if tag.Name == "NoGenre"]
            if no_genre_tags:
                for tag in no_genre_tags:
                    self.unlink_content_from_tag(content, tag)
                logger.info(f"Removed NoGenre tag from content {content.ID}")
                return True

        return False
