"""Add tidal_unavailable flag to Track model

Revision ID: 879cb3821a06
Revises: 79d1ccf69993
Create Date: 2025-12-24 04:37:36.085777

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "879cb3821a06"
down_revision: Union[str, None] = "79d1ccf69993"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tidal_unavailable column to tracks table
    op.add_column(
        "tracks",
        sa.Column(
            "tidal_unavailable", sa.Boolean(), nullable=False, server_default="0"
        ),
    )
    op.create_index(
        op.f("ix_tracks_tidal_unavailable"),
        "tracks",
        ["tidal_unavailable"],
        unique=False,
    )


def downgrade() -> None:
    # Remove tidal_unavailable column
    op.drop_index(op.f("ix_tracks_tidal_unavailable"), table_name="tracks")
    op.drop_column("tracks", "tidal_unavailable")
