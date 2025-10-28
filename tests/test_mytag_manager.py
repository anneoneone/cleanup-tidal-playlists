"""Tests for MyTag manager service."""

from unittest.mock import Mock, patch

import pytest

from src.tidal_cleanup.services.mytag_manager import MyTagManager


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = Mock()
    db.query = Mock()
    db.add = Mock()
    db.flush = Mock()
    db.commit = Mock()
    return db


@pytest.fixture
def mytag_manager(mock_db):
    """Create MyTagManager instance with mocked database."""
    with patch(
        "src.tidal_cleanup.services.mytag_manager.PYREKORDBOX_AVAILABLE", True
    ), patch("src.tidal_cleanup.services.mytag_manager.db6") as mock_db6:
        # Mock the db6 module
        mock_db6.DjmdMyTag = Mock
        manager = MyTagManager(mock_db)
        return manager


class TestMyTagManager:
    """Test MyTag manager functionality."""

    def test_init_requires_pyrekordbox(self, mock_db):
        """Test initialization fails without pyrekordbox."""
        with patch(
            "src.tidal_cleanup.services.mytag_manager.PYREKORDBOX_AVAILABLE", False
        ), pytest.raises(RuntimeError, match="pyrekordbox is not available"):
            MyTagManager(mock_db)

    def test_create_or_get_group_existing(self, mytag_manager, mock_db):
        """Test getting an existing group."""
        # Setup mock group
        mock_group = Mock()
        mock_group.Name = "Genre"
        mock_group.ID = "123"

        # Mock query chain
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_group
        mock_db.query.return_value = mock_query

        result = mytag_manager.create_or_get_group("Genre")

        assert result == mock_group
        assert not mock_db.add.called

    def test_create_or_get_group_new(self, mytag_manager, mock_db):
        """Test creating a new group."""
        # Mock query returns None (group doesn't exist)
        mock_group_query = Mock()
        mock_group_query.filter.return_value = mock_group_query
        mock_group_query.first.return_value = None

        # Mock count query for Seq
        mock_count_query = Mock()
        mock_count_query.filter.return_value = mock_count_query
        mock_count_query.count.return_value = 5

        mock_db.query.side_effect = [mock_group_query, mock_count_query]

        # Mock ID generation
        mock_db.generate_unused_id = Mock(return_value="group456")

        # Mock new group creation
        with patch("src.tidal_cleanup.services.mytag_manager.db6") as mock_db6:
            mock_new_group = Mock()
            mock_new_group.Name = "Party"
            mock_new_group.ID = "group456"
            mock_db6.DjmdMyTag.return_value = mock_new_group

            result = mytag_manager.create_or_get_group("Party")

            mock_db.add.assert_called_once()
            mock_db.flush.assert_called_once()
            assert result == mock_new_group

    def test_get_content_tags(self, mytag_manager, mock_db):
        """Test getting all tags linked to content."""
        mock_content = Mock()
        mock_content.ID = "content123"

        # Mock tag relationships
        mock_rel1 = Mock()
        mock_rel1.MyTagID = "tag1"
        mock_rel2 = Mock()
        mock_rel2.MyTagID = "tag2"

        mock_tag1 = Mock()
        mock_tag1.Name = "Jazz"
        mock_tag1.ID = "tag1"
        mock_tag2 = Mock()
        mock_tag2.Name = "House"
        mock_tag2.ID = "tag2"

        # Mock query sequence
        mock_links_query = Mock()
        mock_links_query.filter.return_value = mock_links_query
        mock_links_query.all.return_value = [mock_rel1, mock_rel2]

        mock_tag1_query = Mock()
        mock_tag1_query.filter.return_value = mock_tag1_query
        mock_tag1_query.first.return_value = mock_tag1

        mock_tag2_query = Mock()
        mock_tag2_query.filter.return_value = mock_tag2_query
        mock_tag2_query.first.return_value = mock_tag2

        mock_db.query.side_effect = [
            mock_links_query,
            mock_tag1_query,
            mock_tag2_query,
        ]

        with patch("src.tidal_cleanup.services.mytag_manager.db6") as mock_db6:
            mock_db6.DjmdSongMyTag.ContentID = "ContentID"
            mock_db6.DjmdMyTag.ID = "ID"

            result = mytag_manager.get_content_tags(mock_content)

            assert len(result) == 2
            assert mock_tag1 in result
            assert mock_tag2 in result

    def test_create_or_get_tag_existing(self, mytag_manager, mock_db):
        """Test getting an existing tag."""
        # Mock group
        mock_group = Mock()
        mock_group.ID = "123"

        # Mock existing tag
        mock_tag = Mock()
        mock_tag.Name = "Jazz"
        mock_tag.ID = "789"

        # Mock query for group
        mock_group_query = Mock()
        mock_group_query.filter.return_value = mock_group_query
        mock_group_query.first.return_value = mock_group

        # Mock query for tag
        mock_tag_query = Mock()
        mock_tag_query.filter.return_value = mock_tag_query
        mock_tag_query.first.return_value = mock_tag

        mock_db.query.side_effect = [mock_group_query, mock_tag_query]

        result = mytag_manager.create_or_get_tag("Jazz", "Genre")

        assert result == mock_tag
        assert not mock_db.add.called

    def test_create_or_get_tag_new(self, mytag_manager, mock_db):
        """Test creating a new tag."""
        # Mock group (exists)
        mock_group = Mock()
        mock_group.ID = "group123"

        # Mock queries
        # First: group query (exists)
        mock_group_query = Mock()
        mock_group_query.filter.return_value = mock_group_query
        mock_group_query.first.return_value = mock_group

        # Second: tag query (doesn't exist)
        mock_tag_query = Mock()
        mock_tag_query.filter.return_value = mock_tag_query
        mock_tag_query.first.return_value = None

        # Third: count query for Seq
        mock_count_query = Mock()
        mock_count_query.filter.return_value = mock_count_query
        mock_count_query.count.return_value = 3

        mock_db.query.side_effect = [
            mock_group_query,
            mock_tag_query,
            mock_count_query,
        ]
        mock_db.generate_unused_id = Mock(return_value="tag999")

        # Mock new tag
        with patch("src.tidal_cleanup.services.mytag_manager.db6") as mock_db6:
            mock_new_tag = Mock()
            mock_new_tag.Name = "Techno"
            mock_new_tag.ID = "tag999"
            mock_db6.DjmdMyTag.return_value = mock_new_tag

            result = mytag_manager.create_or_get_tag("Techno", "Genre")

            # Should have added the new tag
            assert mock_db.add.call_count >= 1
            assert result == mock_new_tag

    def test_link_content_to_tag(self, mytag_manager, mock_db):
        """Test linking content to tags."""
        mock_content = Mock()
        mock_content.ID = "content123"

        # Mock tags
        mock_tag1 = Mock()
        mock_tag1.ID = "tag1"
        mock_tag1.Name = "Jazz"
        mock_tag2 = Mock()
        mock_tag2.ID = "tag2"
        mock_tag2.Name = "Party"

        # Mock query for existing relationships (none exist)
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query
        mock_db.generate_unused_id = Mock(side_effect=["rel1", "rel2"])

        # Mock relationship creation
        with patch("src.tidal_cleanup.services.mytag_manager.db6") as mock_db6:
            mock_rel = Mock()
            mock_db6.DjmdSongMyTag.return_value = mock_rel

            result1 = mytag_manager.link_content_to_tag(mock_content, mock_tag1)
            result2 = mytag_manager.link_content_to_tag(mock_content, mock_tag2)

            assert result1 is True
            assert result2 is True
            assert mock_db.add.call_count == 2

    def test_unlink_content_from_tag(self, mytag_manager, mock_db):
        """Test unlinking a tag from content."""
        mock_content = Mock()
        mock_content.ID = "content123"

        # Mock tag
        mock_tag = Mock()
        mock_tag.ID = "tag1"
        mock_tag.Name = "Jazz"

        # Mock existing relationship
        mock_relationship = Mock()
        mock_relationship.ID = "rel123"

        # Mock query for relationship
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_relationship
        mock_db.query.return_value = mock_query

        result = mytag_manager.unlink_content_from_tag(mock_content, mock_tag)

        assert result is True
        mock_db.delete.assert_called_once_with(mock_relationship)

    def test_unlink_content_from_tag_not_found(self, mytag_manager, mock_db):
        """Test unlinking a tag that doesn't exist on content."""
        mock_content = Mock()
        mock_content.ID = "content123"

        mock_tag = Mock()
        mock_tag.ID = "tag1"

        # Mock query returns no relationship
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        result = mytag_manager.unlink_content_from_tag(mock_content, mock_tag)

        assert result is False
        assert not mock_db.delete.called

    def test_get_content_tag_names(self, mytag_manager, mock_db):
        """Test getting content tag names as a set."""
        mock_content = Mock()
        mock_content.ID = "content123"

        # Mock tag relationships
        mock_rel1 = Mock()
        mock_rel1.MyTagID = "tag1"
        mock_rel2 = Mock()
        mock_rel2.MyTagID = "tag2"

        mock_tag1 = Mock()
        mock_tag1.Name = "Jazz"
        mock_tag1.ID = "tag1"
        mock_tag2 = Mock()
        mock_tag2.Name = "House"
        mock_tag2.ID = "tag2"

        # Mock query sequence for get_content_tags
        mock_links_query = Mock()
        mock_links_query.filter.return_value = mock_links_query
        mock_links_query.all.return_value = [mock_rel1, mock_rel2]

        mock_tag1_query = Mock()
        mock_tag1_query.filter.return_value = mock_tag1_query
        mock_tag1_query.first.return_value = mock_tag1

        mock_tag2_query = Mock()
        mock_tag2_query.filter.return_value = mock_tag2_query
        mock_tag2_query.first.return_value = mock_tag2

        mock_db.query.side_effect = [
            mock_links_query,
            mock_tag1_query,
            mock_tag2_query,
        ]

        with patch("src.tidal_cleanup.services.mytag_manager.db6") as mock_db6:
            mock_db6.DjmdSongMyTag.ContentID = "ContentID"
            mock_db6.DjmdMyTag.ID = "ID"

            result = mytag_manager.get_content_tag_names(mock_content)

            assert isinstance(result, set)
            assert "Jazz" in result
            assert "House" in result
            assert len(result) == 2
