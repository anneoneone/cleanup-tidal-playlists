"""Add stick_playlists and stick_playlist_tracks.

Revision ID: f7c2a9e4b3d1
Revises: e4b8c1d5a7f2
Create Date: 2026-11-02 23:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7c2a9e4b3d1"
down_revision: Union[str, None] = "e4b8c1d5a7f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stick_playlists",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "stick_id",
            sa.Integer(),
            sa.ForeignKey("sticks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("folder", sa.JSON(), nullable=False),
        sa.Column(
            "playlist_id",
            sa.Integer(),
            sa.ForeignKey("playlists.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_stick_playlist_stick", "stick_playlists", ["stick_id"])
    op.create_index("idx_stick_playlist_playlist", "stick_playlists", ["playlist_id"])
    op.create_table(
        "stick_playlist_tracks",
        sa.Column(
            "stick_playlist_id",
            sa.Integer(),
            sa.ForeignKey("stick_playlists.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "track_id",
            sa.Integer(),
            sa.ForeignKey("tracks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("idx_stick_playlist_track", "stick_playlist_tracks", ["track_id"])


def downgrade() -> None:
    op.drop_index("idx_stick_playlist_track", table_name="stick_playlist_tracks")
    op.drop_table("stick_playlist_tracks")
    op.drop_index("idx_stick_playlist_playlist", table_name="stick_playlists")
    op.drop_index("idx_stick_playlist_stick", table_name="stick_playlists")
    op.drop_table("stick_playlists")
