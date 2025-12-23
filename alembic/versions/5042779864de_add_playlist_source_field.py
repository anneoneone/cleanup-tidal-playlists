"""add_playlist_source_field

Revision ID: 5042779864de
Revises: remove_symlinks
Create Date: 2025-12-23 00:42:01.094748

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5042779864de"
down_revision: Union[str, None] = "remove_symlinks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use batch operations for SQLite compatibility
    # Ensure index doesn't already exist (idempotent reruns)
    conn = op.get_bind()
    # Clean up any leftover temp table from previous failed attempts
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_playlists"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_playlists_source"))
    with op.batch_alter_table("playlists", recreate="auto") as batch_op:
        # Add source column and index
        batch_op.add_column(
            sa.Column(
                "source", sa.String(length=20), nullable=False, server_default="tidal"
            )
        )
        batch_op.create_index("ix_playlists_source", ["source"])

        # Make tidal_id nullable to support local-only playlists
        batch_op.alter_column(
            "tidal_id", existing_type=sa.String(length=255), nullable=True
        )


def downgrade() -> None:
    # Use batch operations for SQLite compatibility
    with op.batch_alter_table("playlists", recreate="auto") as batch_op:
        # Drop index and column
        batch_op.drop_index("ix_playlists_source")
        batch_op.drop_column("source")

        # Revert tidal_id to non-nullable
        batch_op.alter_column(
            "tidal_id", existing_type=sa.String(length=255), nullable=False
        )
