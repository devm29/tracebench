from uuid import UUID

from tracebench.datasets.extract import extract_case
from tracebench.datasets.models import (
    Dataset,
    DatasetCreate,
    DatasetItem,
    DatasetItemCreate,
    DatasetItemUpdate,
    DatasetUpdate,
    DatasetVersionItems,
    PromoteRequest,
)
from tracebench.errors import ValidationFailedError
from tracebench.query.traces import TraceService
from tracebench.store.postgres.datasets import DatasetRepository


class DatasetService:
    def __init__(self, repository: DatasetRepository, traces: TraceService) -> None:
        self._repository = repository
        self._traces = traces

    async def list_datasets(self) -> list[Dataset]:
        return await self._repository.list_all()

    async def get(self, dataset_id: UUID) -> Dataset:
        return await self._repository.get(dataset_id)

    async def get_by_name(self, name: str) -> Dataset | None:
        return await self._repository.find_by_name(name)

    async def create(self, payload: DatasetCreate) -> Dataset:
        return await self._repository.create(payload)

    async def update(self, dataset_id: UUID, payload: DatasetUpdate) -> Dataset:
        return await self._repository.update(dataset_id, payload)

    async def delete(self, dataset_id: UUID) -> None:
        await self._repository.delete(dataset_id)

    async def items(self, dataset_id: UUID, version: int | None = None) -> DatasetVersionItems:
        at, items = await self._repository.items(dataset_id, version)
        return DatasetVersionItems(dataset=await self._repository.get(dataset_id), version=at, items=items)

    async def add_items(self, dataset_id: UUID, payloads: list[DatasetItemCreate]) -> list[DatasetItem]:
        if not payloads:
            raise ValidationFailedError("at least one item is required")
        return await self._repository.add_items(dataset_id, payloads)

    async def update_item(self, dataset_id: UUID, item_key: UUID, payload: DatasetItemUpdate) -> DatasetItem:
        fields = payload.model_fields_set
        if not fields:
            raise ValidationFailedError("nothing to update")
        return await self._repository.revise_item(
            dataset_id,
            item_key,
            new_input=payload.input if "input" in fields else None,
            expected_output=payload.expected_output,
            metadata=payload.metadata,
            clear_expected="expected_output" in fields and payload.expected_output is None,
        )

    async def delete_item(self, dataset_id: UUID, item_key: UUID) -> int:
        return await self._repository.remove_item(dataset_id, item_key)

    async def promote(self, trace_id: str, request: PromoteRequest) -> DatasetItem:
        detail = await self._traces.get_trace(trace_id)
        case_input, observed, metadata = extract_case(detail, request.span_id)
        explicit = "expected_output" in request.model_fields_set
        if not explicit and observed is None:
            raise ValidationFailedError(
                "the trace has no captured output to use as the expected answer; "
                "pass expected_output (null for reference-free scorers such as json_schema)"
            )
        dataset = await self._resolve(request)
        [item] = await self._repository.add_items(
            dataset.id,
            [
                DatasetItemCreate(
                    input=case_input,
                    expected_output=request.expected_output if explicit else observed,
                    metadata=metadata,
                    source_trace_id=detail.trace_id,
                    source_span_id=request.span_id or detail.roots[0].span_id,
                )
            ],
            unique_source=True,
        )
        return item

    async def _resolve(self, request: PromoteRequest) -> Dataset:
        if request.dataset_id is not None:
            return await self._repository.get(request.dataset_id)
        if request.dataset_name:
            return await self._repository.get_or_create(DatasetCreate(name=request.dataset_name))
        raise ValidationFailedError("provide dataset_id or dataset_name")
