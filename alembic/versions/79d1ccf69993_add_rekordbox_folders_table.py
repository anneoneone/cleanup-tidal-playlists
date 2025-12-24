"""add_rekordbox_folders_table

Revision ID: 79d1ccf69993
Revises: 5042779864de
Create Date: 2025-12-23 04:31:56.581052

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "79d1ccf69993"
down_revision: Union[str, None] = "5042779864de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rekordbox_folders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("folder_path", sa.String(length=500), nullable=False),
        sa.Column("rekordbox_folder_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("folder_path"),
    )
    op.create_index(
        "ix_rekordbox_folders_folder_path", "rekordbox_folders", ["folder_path"]
    )


def downgrade() -> None:
    op.drop_index("ix_rekordbox_folders_folder_path", table_name="rekordbox_folders")
    op.drop_table("rekordbox_folders")
