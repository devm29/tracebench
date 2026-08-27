from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Response, status

from tracebench.api.auth import require_api_token
from tracebench.api.deps import DatasetsDep
from tracebench.datasets.models import (
    MAX_ITEMS_PER_REQUEST,
    Dataset,
    DatasetCreate,
    DatasetItem,
    DatasetItemCreate,
    DatasetItemUpdate,
    DatasetUpdate,
    DatasetVersionItems,
)
from tracebench.errors import NotFoundError

router = APIRouter(prefix="/api/datasets", tags=["datasets"], dependencies=[Depends(require_api_token)])


@router.get("", response_model=list[Dataset])
async def list_datasets(datasets: DatasetsDep) -> list[Dataset]:
    return await datasets.list_datasets()


@router.post("", response_model=Dataset, status_code=status.HTTP_201_CREATED)
async def create_dataset(payload: DatasetCreate, datasets: DatasetsDep) -> Dataset:
    return await datasets.create(payload)


@router.get("/by-name/{name}", response_model=Dataset)
async def get_by_name(name: str, datasets: DatasetsDep) -> Dataset:
    found = await datasets.get_by_name(name)
    if found is None:
        raise NotFoundError(f"dataset {name!r} not found")
    return found


@router.get("/{dataset_id}", response_model=Dataset)
async def get_dataset(dataset_id: UUID, datasets: DatasetsDep) -> Dataset:
    return await datasets.get(dataset_id)


@router.patch("/{dataset_id}", response_model=Dataset)
async def update_dataset(dataset_id: UUID, payload: DatasetUpdate, datasets: DatasetsDep) -> Dataset:
    return await datasets.update(dataset_id, payload)


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_dataset(dataset_id: UUID, datasets: DatasetsDep) -> Response:
    await datasets.delete(dataset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{dataset_id}/items", response_model=DatasetVersionItems)
async def list_items(
    dataset_id: UUID,
    datasets: DatasetsDep,
    version: Annotated[int | None, Query(ge=0)] = None,
) -> DatasetVersionItems:
    return await datasets.items(dataset_id, version)


@router.post("/{dataset_id}/items", response_model=list[DatasetItem], status_code=status.HTTP_201_CREATED)
async def add_items(
    dataset_id: UUID,
    payload: Annotated[list[DatasetItemCreate], Body(min_length=1, max_length=MAX_ITEMS_PER_REQUEST)],
    datasets: DatasetsDep,
) -> list[DatasetItem]:
    return await datasets.add_items(dataset_id, payload)


@router.patch("/{dataset_id}/items/{item_key}", response_model=DatasetItem)
async def update_item(
    dataset_id: UUID, item_key: UUID, payload: DatasetItemUpdate, datasets: DatasetsDep
) -> DatasetItem:
    return await datasets.update_item(dataset_id, item_key, payload)


@router.delete("/{dataset_id}/items/{item_key}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_item(dataset_id: UUID, item_key: UUID, datasets: DatasetsDep) -> Response:
    await datasets.delete_item(dataset_id, item_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
