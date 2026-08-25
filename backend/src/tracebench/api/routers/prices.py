from fastapi import APIRouter, Depends, status

from tracebench.api.auth import require_api_token
from tracebench.api.deps import PricesDep
from tracebench.errors import NotFoundError
from tracebench.pricing.models import PriceVersion, PriceVersionCreate, PriceVersionSummary

router = APIRouter(prefix="/api/prices", tags=["prices"], dependencies=[Depends(require_api_token)])


@router.get("/current", response_model=PriceVersion)
async def current(prices: PricesDep) -> PriceVersion:
    version = prices.current()
    if version is None:
        raise NotFoundError("no price version is in effect")
    return version


@router.get("/versions", response_model=list[PriceVersionSummary])
async def versions(prices: PricesDep) -> list[PriceVersionSummary]:
    return await prices.versions()


@router.get("/versions/{version_id}", response_model=PriceVersion)
async def version(version_id: int, prices: PricesDep) -> PriceVersion:
    found = await prices.version(version_id)
    if found is None:
        raise NotFoundError(f"price version {version_id} not found")
    return found


@router.post("/versions", response_model=PriceVersion, status_code=status.HTTP_201_CREATED)
async def create_version(payload: PriceVersionCreate, prices: PricesDep) -> PriceVersion:
    return await prices.create_version(payload)
