"""Add playlists.in_tidal.

Revision ID: d3f1a7b2c6e8
Revises: c7a1f3e2d9b4
Create Date: 2026-11-01 14:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3f1a7b2c6e8"
down_revision: Union[str, None] = "c7a1f3e2d9b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "playlists",
        sa.Column("in_tidal", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Until the first Tidal refresh, assume every playlist with a Tidal ID exists.
    op.execute("UPDATE playlists SET in_tidal = 1 WHERE tidal_id IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table("playlists") as batch_op:
        batch_op.drop_column("in_tidal")
