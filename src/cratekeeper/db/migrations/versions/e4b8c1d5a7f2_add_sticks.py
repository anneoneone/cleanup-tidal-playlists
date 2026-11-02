"""Add sticks and stick_tracks.

Revision ID: e4b8c1d5a7f2
Revises: d3f1a7b2c6e8
Create Date: 2026-11-02 23:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4b8c1d5a7f2"
down_revision: Union[str, None] = "d3f1a7b2c6e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sticks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("volume_id", sa.String(length=100), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scanned_at", sa.DateTime(), nullable=False),
        sa.Column("tracks_total", sa.Integer(), nullable=False),
        sa.Column("tracks_matched", sa.Integer(), nullable=False),
    )
    op.create_table(
        "stick_tracks",
        sa.Column(
            "stick_id",
            sa.Integer(),
            sa.ForeignKey("sticks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "track_id",
            sa.Integer(),
            sa.ForeignKey("tracks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("idx_stick_track", "stick_tracks", ["track_id"])


def downgrade() -> None:
    op.drop_index("idx_stick_track", table_name="stick_tracks")
    op.drop_table("stick_tracks")
    op.drop_table("sticks")
