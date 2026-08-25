from sqlalchemy import func, select

from tracebench.pricing.models import (
    MatchKind,
    ModelPrice,
    PriceVersion,
    PriceVersionCreate,
    PriceVersionSummary,
)
from tracebench.store.postgres.engine import SessionFactory
from tracebench.store.postgres.tables import ModelPriceRow, PriceVersionRow


def _to_model(row: PriceVersionRow) -> PriceVersion:
    return PriceVersion(
        id=row.id,
        label=row.label,
        effective_from=row.effective_from,
        created_at=row.created_at,
        prices=[
            ModelPrice(
                provider=p.provider,
                model=p.model,
                match=MatchKind(p.match),
                input_per_mtok=p.input_per_mtok,
                output_per_mtok=p.output_per_mtok,
                cache_read_per_mtok=p.cache_read_per_mtok,
                cache_write_per_mtok=p.cache_write_per_mtok,
            )
            for p in row.prices
        ],
    )


class PriceRepository:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def all_versions(self) -> list[PriceVersion]:
        async with self._sessions() as session:
            rows = await session.scalars(select(PriceVersionRow).order_by(PriceVersionRow.effective_from))
            return [_to_model(r) for r in rows]

    async def summaries(self) -> list[PriceVersionSummary]:
        stmt = (
            select(PriceVersionRow, func.count(ModelPriceRow.id))
            .join(ModelPriceRow, ModelPriceRow.version_id == PriceVersionRow.id, isouter=True)
            .group_by(PriceVersionRow.id)
            .order_by(PriceVersionRow.effective_from.desc())
        )
        async with self._sessions() as session:
            result = await session.execute(stmt)
            return [
                PriceVersionSummary(
                    id=row.id,
                    label=row.label,
                    effective_from=row.effective_from,
                    created_at=row.created_at,
                    model_count=count,
                )
                for row, count in result
            ]

    async def get(self, version_id: int) -> PriceVersion | None:
        async with self._sessions() as session:
            row = await session.get(PriceVersionRow, version_id)
            return _to_model(row) if row else None

    async def create(self, payload: PriceVersionCreate) -> PriceVersion:
        async with self._sessions() as session, session.begin():
            row = PriceVersionRow(
                label=payload.label,
                effective_from=payload.effective_from,
                prices=[
                    ModelPriceRow(
                        provider=p.provider,
                        model=p.model,
                        match=p.match.value,
                        input_per_mtok=p.input_per_mtok,
                        output_per_mtok=p.output_per_mtok,
                        cache_read_per_mtok=p.cache_read_per_mtok,
                        cache_write_per_mtok=p.cache_write_per_mtok,
                    )
                    for p in payload.prices
                ],
            )
            session.add(row)
            await session.flush()
            await session.refresh(row, attribute_names=["created_at", "prices"])
            return _to_model(row)
