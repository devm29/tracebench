import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tracebench.datasets.models import Dataset, DatasetCreate, DatasetItem, DatasetItemCreate, DatasetUpdate
from tracebench.errors import ConflictError, NotFoundError
from tracebench.evals.models import ScorerSpec
from tracebench.store.postgres.engine import SessionFactory
from tracebench.store.postgres.tables import DatasetItemRow, DatasetRow

_scorers = TypeAdapter(list[ScorerSpec])


def _visible_at(version: int) -> Any:
    return and_(
        DatasetItemRow.valid_from <= version,
        or_(DatasetItemRow.valid_to.is_(None), DatasetItemRow.valid_to > version),
    )


def _dataset(row: DatasetRow, item_count: int) -> Dataset:
    return Dataset(
        id=row.id,
        name=row.name,
        description=row.description,
        version=row.version,
        item_count=item_count,
        default_scorers=_scorers.validate_python(row.default_scorers),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _item(row: DatasetItemRow) -> DatasetItem:
    return DatasetItem(
        id=row.id,
        item_key=row.item_key,
        dataset_id=row.dataset_id,
        revision=row.valid_from,
        input=row.input,
        expected_output=row.expected_output,
        metadata=row.item_metadata,
        source_trace_id=row.source_trace_id,
        source_span_id=row.source_span_id,
        created_at=row.created_at,
    )


class DatasetRepository:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    @staticmethod
    def _with_counts() -> Select[DatasetRow, int]:
        current_items = (
            select(func.count(DatasetItemRow.id))
            .where(DatasetItemRow.dataset_id == DatasetRow.id, DatasetItemRow.valid_to.is_(None))
            .correlate(DatasetRow)
            .scalar_subquery()
        )
        return select(DatasetRow, current_items)

    async def list_all(self) -> list[Dataset]:
        async with self._sessions() as session:
            result = await session.execute(self._with_counts().order_by(DatasetRow.updated_at.desc()))
            return [_dataset(row, count) for row, count in result]

    async def get(self, dataset_id: uuid.UUID) -> Dataset:
        async with self._sessions() as session:
            result = await session.execute(self._with_counts().where(DatasetRow.id == dataset_id))
            found = result.first()
        if found is None:
            raise NotFoundError(f"dataset {dataset_id} not found")
        return _dataset(*found)

    async def find_by_name(self, name: str) -> Dataset | None:
        async with self._sessions() as session:
            result = await session.execute(self._with_counts().where(DatasetRow.name == name))
            found = result.first()
        return _dataset(*found) if found else None

    async def create(self, payload: DatasetCreate) -> Dataset:
        try:
            async with self._sessions() as session, session.begin():
                row = DatasetRow(
                    name=payload.name,
                    description=payload.description,
                    version=0,
                    default_scorers=_scorers.dump_python(payload.default_scorers, mode="json", by_alias=True),
                )
                session.add(row)
                await session.flush()
                await session.refresh(row)
                return _dataset(row, 0)
        except IntegrityError as exc:
            raise ConflictError(f"dataset {payload.name!r} already exists") from exc

    async def get_or_create(self, payload: DatasetCreate) -> Dataset:
        found = await self.find_by_name(payload.name)
        if found is not None:
            return found
        try:
            return await self.create(payload)
        except ConflictError:
            # Lost a race with a concurrent create of the same name.
            found = await self.find_by_name(payload.name)
            if found is None:
                raise
            return found

    async def update(self, dataset_id: uuid.UUID, payload: DatasetUpdate) -> Dataset:
        async with self._sessions() as session, session.begin():
            row = await self._lock(session, dataset_id)
            if payload.description is not None:
                row.description = payload.description
            if payload.default_scorers is not None:
                row.default_scorers = _scorers.dump_python(payload.default_scorers, mode="json", by_alias=True)
        return await self.get(dataset_id)

    async def delete(self, dataset_id: uuid.UUID) -> None:
        async with self._sessions() as session, session.begin():
            row = await self._lock(session, dataset_id)
            await session.delete(row)

    async def items(self, dataset_id: uuid.UUID, version: int | None = None) -> tuple[int, list[DatasetItem]]:
        async with self._sessions() as session:
            row = await session.get(DatasetRow, dataset_id)
            if row is None:
                raise NotFoundError(f"dataset {dataset_id} not found")
            at = row.version if version is None else version
            if at > row.version:
                raise NotFoundError(f"dataset {row.name} has no version {at} (latest is {row.version})")
            items = await session.scalars(
                select(DatasetItemRow)
                .where(DatasetItemRow.dataset_id == dataset_id, _visible_at(at))
                .order_by(DatasetItemRow.created_at, DatasetItemRow.item_key)
            )
            return at, [_item(i) for i in items]

    async def add_items(
        self, dataset_id: uuid.UUID, payloads: list[DatasetItemCreate], *, unique_source: bool = False
    ) -> list[DatasetItem]:
        """Appends items as one new dataset version.

        With unique_source, an item whose source trace is already in the dataset raises
        ConflictError; the check runs under the dataset row lock, so concurrent promotes of
        the same trace cannot both succeed.
        """
        async with self._sessions() as session, session.begin():
            dataset = await self._lock(session, dataset_id)
            if unique_source:
                await self._reject_duplicate_sources(session, dataset, payloads)
            dataset.version += 1
            # One timestamp for the whole version keeps insertion order stable and saves a
            # refresh round trip per row.
            created_at = datetime.now(UTC)
            rows = [
                DatasetItemRow(
                    id=uuid.uuid4(),
                    item_key=uuid.uuid4(),
                    dataset_id=dataset_id,
                    valid_from=dataset.version,
                    valid_to=None,
                    input=p.input,
                    expected_output=p.expected_output,
                    item_metadata=p.metadata,
                    source_trace_id=p.source_trace_id,
                    source_span_id=p.source_span_id,
                    created_at=created_at,
                )
                for p in payloads
            ]
            session.add_all(rows)
            await session.flush()
            return [_item(r) for r in rows]

    @staticmethod
    async def _reject_duplicate_sources(
        session: AsyncSession, dataset: DatasetRow, payloads: list[DatasetItemCreate]
    ) -> None:
        sources = {(p.source_trace_id, p.source_span_id) for p in payloads if p.source_trace_id}
        if not sources:
            return
        candidates = await session.scalars(
            select(DatasetItemRow).where(
                DatasetItemRow.dataset_id == dataset.id,
                DatasetItemRow.source_trace_id.in_({trace for trace, _ in sources}),
                DatasetItemRow.valid_to.is_(None),
            )
        )
        existing = next((r for r in candidates if (r.source_trace_id, r.source_span_id) in sources), None)
        if existing is not None:
            raise ConflictError(
                f"trace {existing.source_trace_id} is already in dataset {dataset.name}",
                details={"item_key": str(existing.item_key)},
            )

    async def revise_item(
        self,
        dataset_id: uuid.UUID,
        item_key: uuid.UUID,
        *,
        new_input: Any | None,
        expected_output: Any | None,
        metadata: dict[str, Any] | None,
        clear_expected: bool,
    ) -> DatasetItem:
        async with self._sessions() as session, session.begin():
            dataset = await self._lock(session, dataset_id)
            current = await self._current_item(session, dataset_id, item_key)
            dataset.version += 1
            current.valid_to = dataset.version
            revised = DatasetItemRow(
                item_key=item_key,
                dataset_id=dataset_id,
                valid_from=dataset.version,
                valid_to=None,
                input=current.input if new_input is None else new_input,
                expected_output=None
                if clear_expected
                else (current.expected_output if expected_output is None else expected_output),
                item_metadata=current.item_metadata if metadata is None else metadata,
                source_trace_id=current.source_trace_id,
                source_span_id=current.source_span_id,
            )
            # Close the old revision first so the partial unique index on open revisions holds.
            await session.flush()
            session.add(revised)
            await session.flush()
            await session.refresh(revised, attribute_names=["created_at"])
            return _item(revised)

    async def remove_item(self, dataset_id: uuid.UUID, item_key: uuid.UUID) -> int:
        async with self._sessions() as session, session.begin():
            dataset = await self._lock(session, dataset_id)
            await self._current_item(session, dataset_id, item_key)
            dataset.version += 1
            await session.execute(
                update(DatasetItemRow)
                .where(DatasetItemRow.item_key == item_key, DatasetItemRow.valid_to.is_(None))
                .values(valid_to=dataset.version)
            )
            return dataset.version

    @staticmethod
    async def _lock(session: AsyncSession, dataset_id: uuid.UUID) -> DatasetRow:
        row = await session.scalar(select(DatasetRow).where(DatasetRow.id == dataset_id).with_for_update())
        if row is None:
            raise NotFoundError(f"dataset {dataset_id} not found")
        return row

    @staticmethod
    async def _current_item(session: AsyncSession, dataset_id: uuid.UUID, item_key: uuid.UUID) -> DatasetItemRow:
        row = await session.scalar(
            select(DatasetItemRow).where(
                DatasetItemRow.dataset_id == dataset_id,
                DatasetItemRow.item_key == item_key,
                DatasetItemRow.valid_to.is_(None),
            )
        )
        if row is None:
            raise NotFoundError(f"item {item_key} not found in dataset {dataset_id}")
        return row
