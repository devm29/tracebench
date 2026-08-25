from collections.abc import Sequence
from typing import Any
from uuid import UUID

import httpx
from pydantic import TypeAdapter

from tracebench.api.schemas import Health
from tracebench.datasets.models import (
    Dataset,
    DatasetCreate,
    DatasetItem,
    DatasetItemCreate,
    DatasetItemUpdate,
    DatasetVersionItems,
)
from tracebench.evals.models import CaseResult, EvalRun, EvalRunRecord, RecordedGate, RunDiff, ScorerSpec
from tracebench.pricing.models import PriceVersion, PriceVersionCreate, PriceVersionSummary


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


_datasets = TypeAdapter(list[Dataset])
_results = TypeAdapter(list[CaseResult])
_runs = TypeAdapter(list[EvalRun])
_price_versions = TypeAdapter(list[PriceVersionSummary])


def api_client(base_url: str, token: str | None = None, *, timeout: float = 30.0) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else None
    return httpx.AsyncClient(base_url=base_url, headers=headers, timeout=timeout)


class TracebenchClient:
    """Thin typed client for the Tracebench REST API, used by the CLI and the demo seeder."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(0, f"cannot reach Tracebench at {self._http.base_url}: {exc}") from exc
        if response.status_code >= 400:
            try:
                message = response.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = response.text[:300]
            raise ApiError(response.status_code, str(message))
        return response

    async def list_datasets(self) -> list[Dataset]:
        return _datasets.validate_json((await self._request("GET", "/api/datasets")).content)

    async def dataset_by_name(self, name: str) -> Dataset | None:
        try:
            response = await self._request("GET", f"/api/datasets/by-name/{name}")
        except ApiError as exc:
            if exc.status == 404:
                return None
            raise
        return Dataset.model_validate_json(response.content)

    async def create_dataset(
        self, name: str, description: str = "", scorers: Sequence[ScorerSpec] | None = None
    ) -> Dataset:
        body = DatasetCreate(name=name, description=description, default_scorers=list(scorers or []))
        response = await self._request("POST", "/api/datasets", json=body.model_dump(mode="json", by_alias=True))
        return Dataset.model_validate_json(response.content)

    async def items(self, dataset_id: UUID, version: int | None = None) -> DatasetVersionItems:
        params = {"version": version} if version is not None else None
        response = await self._request("GET", f"/api/datasets/{dataset_id}/items", params=params)
        return DatasetVersionItems.model_validate_json(response.content)

    async def add_items(self, dataset_id: UUID, items: list[DatasetItemCreate]) -> None:
        body = [i.model_dump(mode="json") for i in items]
        await self._request("POST", f"/api/datasets/{dataset_id}/items", json=body)

    async def update_item(self, dataset_id: UUID, item_key: UUID, update: DatasetItemUpdate) -> DatasetItem:
        body = update.model_dump(mode="json", exclude_unset=True)
        response = await self._request("PATCH", f"/api/datasets/{dataset_id}/items/{item_key}", json=body)
        return DatasetItem.model_validate_json(response.content)

    async def health(self) -> Health:
        return Health.model_validate_json((await self._request("GET", "/api/health")).content)

    async def record_run(self, record: EvalRunRecord) -> EvalRun:
        body = record.model_dump(mode="json", by_alias=True)
        return EvalRun.model_validate_json((await self._request("POST", "/api/eval-runs", json=body)).content)

    async def baseline(self, dataset_id: UUID) -> EvalRun | None:
        try:
            response = await self._request("GET", "/api/eval-runs/baseline", params={"dataset_id": str(dataset_id)})
        except ApiError as exc:
            if exc.status == 404:
                return None
            raise
        return EvalRun.model_validate_json(response.content)

    async def run(self, run_id: UUID) -> EvalRun:
        return EvalRun.model_validate_json((await self._request("GET", f"/api/eval-runs/{run_id}")).content)

    async def results(self, run_id: UUID) -> list[CaseResult]:
        return _results.validate_json((await self._request("GET", f"/api/eval-runs/{run_id}/results")).content)

    async def set_baseline(self, run_id: UUID) -> EvalRun:
        response = await self._request("POST", f"/api/eval-runs/{run_id}/baseline")
        return EvalRun.model_validate_json(response.content)

    async def set_gate(self, run_id: UUID, gate: RecordedGate) -> EvalRun:
        response = await self._request("PUT", f"/api/eval-runs/{run_id}/gate", json=gate.model_dump(mode="json"))
        return EvalRun.model_validate_json(response.content)

    async def runs(self, dataset_id: UUID, *, limit: int = 50) -> list[EvalRun]:
        params = {"dataset_id": str(dataset_id), "limit": limit}
        return _runs.validate_json((await self._request("GET", "/api/eval-runs", params=params)).content)

    async def price_versions(self) -> list[PriceVersionSummary]:
        return _price_versions.validate_json((await self._request("GET", "/api/prices/versions")).content)

    async def current_prices(self) -> PriceVersion:
        return PriceVersion.model_validate_json((await self._request("GET", "/api/prices/current")).content)

    async def create_price_version(self, payload: PriceVersionCreate) -> PriceVersion:
        response = await self._request("POST", "/api/prices/versions", json=payload.model_dump(mode="json"))
        return PriceVersion.model_validate_json(response.content)

    async def compare(self, base: UUID, head: UUID) -> RunDiff:
        response = await self._request("GET", "/api/eval-runs/compare", params={"base": str(base), "head": str(head)})
        return RunDiff.model_validate_json(response.content)

    async def promote(self, trace_id: str, dataset_name: str) -> DatasetItem:
        response = await self._request("POST", f"/api/traces/{trace_id}/promote", json={"dataset_name": dataset_name})
        return DatasetItem.model_validate_json(response.content)
