import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


class PriceVersionRow(Base):
    __tablename__ = "price_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(120))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    prices: Mapped[list["ModelPriceRow"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ModelPriceRow.model",
    )


class ModelPriceRow(Base):
    __tablename__ = "model_prices"
    __table_args__ = (UniqueConstraint("version_id", "model", "match", name="uq_model_prices_version_model"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("price_versions.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(200))
    match: Mapped[str] = mapped_column(String(16))
    input_per_mtok: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    output_per_mtok: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    cache_read_per_mtok: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    cache_write_per_mtok: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    version: Mapped[PriceVersionRow] = relationship(back_populates="prices")


class DatasetRow(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=0)
    default_scorers: Mapped[list[Any]] = mapped_column(default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DatasetItemRow(Base):
    """One immutable revision of a dataset item.

    A revision is visible in dataset versions [valid_from, valid_to). Editing an item
    closes the current revision and opens a new one, so any historical version (and any
    eval run pinned to it) can be reproduced exactly.
    """

    __tablename__ = "dataset_items"
    __table_args__ = (
        Index("ix_dataset_items_visible", "dataset_id", "valid_from", "valid_to"),
        Index(
            "uq_dataset_items_current_key",
            "item_key",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    item_key: Mapped[uuid.UUID] = mapped_column(index=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    valid_from: Mapped[int] = mapped_column(Integer)
    valid_to: Mapped[int | None] = mapped_column(Integer)
    input: Mapped[Any] = mapped_column(JSONB)
    expected_output: Mapped[Any | None] = mapped_column(JSONB)
    item_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)
    source_trace_id: Mapped[str | None] = mapped_column(String(32), index=True)
    source_span_id: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalRunRow(Base):
    __tablename__ = "eval_runs"
    __table_args__ = (
        Index("ix_eval_runs_dataset_created", "dataset_id", "created_at"),
        Index(
            "uq_eval_runs_one_baseline",
            "dataset_id",
            unique=True,
            postgresql_where=text("is_baseline"),
        ),
        Index("ix_eval_runs_unfinished", "status", postgresql_where=text("status IN ('pending', 'running')")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    dataset_version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String(200))
    target_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    scorers: Mapped[list[Any]] = mapped_column(default=list)
    git_sha: Mapped[str | None] = mapped_column(String(64))
    git_ref: Mapped[str | None] = mapped_column(String(255))
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    embedder: Mapped[str | None] = mapped_column(String(200))
    gate: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dataset: Mapped[DatasetRow] = relationship(lazy="joined", innerjoin=True)


class EvalResultRow(Base):
    __tablename__ = "eval_results"
    __table_args__ = (UniqueConstraint("run_id", "item_key", name="uq_eval_results_run_item"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True)
    item_key: Mapped[uuid.UUID]
    item_id: Mapped[uuid.UUID]
    input: Mapped[Any] = mapped_column(JSONB)
    expected_output: Mapped[Any | None] = mapped_column(JSONB)
    output: Mapped[Any | None] = mapped_column(JSONB)
    passed: Mapped[bool] = mapped_column(Boolean)
    scores: Mapped[list[Any]] = mapped_column(default=list)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
