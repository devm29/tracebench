"""record the embedder and CI gate verdict on eval runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04 19:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("eval_runs", sa.Column("embedder", sa.String(length=200), nullable=True))
    op.add_column("eval_runs", sa.Column("gate", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index(
        "ix_eval_runs_unfinished",
        "eval_runs",
        ["status"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("ix_eval_runs_unfinished", table_name="eval_runs")
    op.drop_column("eval_runs", "gate")
    op.drop_column("eval_runs", "embedder")
