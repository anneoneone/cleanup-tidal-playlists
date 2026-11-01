"""Add runs table and playlist_tracks.in_bandcamp.

Revision ID: c7a1f3e2d9b4
Revises: 879cb3821a06
Create Date: 2026-11-01 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7a1f3e2d9b4"
down_revision: Union[str, None] = "879cb3821a06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("scope", sa.String(length=500), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("plan", sa.JSON(), nullable=True),
        sa.Column("plan_run_id", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_runs_kind", "runs", ["kind"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_started_at", "runs", ["started_at"])
    # Plain ADD COLUMN: no table rebuild, so no cascade risk on SQLite.
    op.add_column(
        "playlist_tracks",
        sa.Column(
            "in_bandcamp", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("playlist_tracks") as batch_op:
        batch_op.drop_column("in_bandcamp")
    op.drop_index("ix_runs_started_at", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_kind", table_name="runs")
    op.drop_table("runs")
