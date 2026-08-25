"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-04 14:51:26.743785
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("default_scorers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
        sa.UniqueConstraint("name", name=op.f("uq_datasets_name")),
    )
    op.create_table(
        "price_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_versions")),
    )
    op.create_index(op.f("ix_price_versions_effective_from"), "price_versions", ["effective_from"], unique=False)
    op.create_table(
        "dataset_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("item_key", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("valid_from", sa.Integer(), nullable=False),
        sa.Column("valid_to", sa.Integer(), nullable=True),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expected_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_trace_id", sa.String(length=32), nullable=True),
        sa.Column("source_span_id", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_dataset_items_dataset_id_datasets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_items")),
    )
    op.create_index(op.f("ix_dataset_items_item_key"), "dataset_items", ["item_key"], unique=False)
    op.create_index(op.f("ix_dataset_items_source_trace_id"), "dataset_items", ["source_trace_id"], unique=False)
    op.create_index("ix_dataset_items_visible", "dataset_items", ["dataset_id", "valid_from", "valid_to"], unique=False)
    op.create_index(
        "uq_dataset_items_current_key",
        "dataset_items",
        ["item_key"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("scorers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("git_sha", sa.String(length=64), nullable=True),
        sa.Column("git_ref", sa.String(length=255), nullable=True),
        sa.Column("is_baseline", sa.Boolean(), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name=op.f("fk_eval_runs_dataset_id_datasets"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_runs")),
    )
    op.create_index("ix_eval_runs_dataset_created", "eval_runs", ["dataset_id", "created_at"], unique=False)
    op.create_index(
        "uq_eval_runs_one_baseline",
        "eval_runs",
        ["dataset_id"],
        unique=True,
        postgresql_where=sa.text("is_baseline"),
    )
    op.create_table(
        "model_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("match", sa.String(length=16), nullable=False),
        sa.Column("input_per_mtok", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("output_per_mtok", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("cache_read_per_mtok", sa.Numeric(precision=14, scale=6), nullable=True),
        sa.Column("cache_write_per_mtok", sa.Numeric(precision=14, scale=6), nullable=True),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["price_versions.id"],
            name=op.f("fk_model_prices_version_id_price_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_prices")),
        sa.UniqueConstraint("version_id", "model", "match", name="uq_model_prices_version_model"),
    )
    op.create_table(
        "eval_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("item_key", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expected_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["eval_runs.id"], name=op.f("fk_eval_results_run_id_eval_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_results")),
        sa.UniqueConstraint("run_id", "item_key", name="uq_eval_results_run_item"),
    )
    op.create_index(op.f("ix_eval_results_run_id"), "eval_results", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_eval_results_run_id"), table_name="eval_results")
    op.drop_table("eval_results")
    op.drop_table("model_prices")
    op.drop_index("uq_eval_runs_one_baseline", table_name="eval_runs", postgresql_where=sa.text("is_baseline"))
    op.drop_index("ix_eval_runs_dataset_created", table_name="eval_runs")
    op.drop_table("eval_runs")
    op.drop_index(
        "uq_dataset_items_current_key",
        table_name="dataset_items",
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.drop_index("ix_dataset_items_visible", table_name="dataset_items")
    op.drop_index(op.f("ix_dataset_items_source_trace_id"), table_name="dataset_items")
    op.drop_index(op.f("ix_dataset_items_item_key"), table_name="dataset_items")
    op.drop_table("dataset_items")
    op.drop_index(op.f("ix_price_versions_effective_from"), table_name="price_versions")
    op.drop_table("price_versions")
    op.drop_table("datasets")
