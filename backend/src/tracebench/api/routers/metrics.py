from typing import Annotated

from fastapi import APIRouter, Query

from tracebench.api.deps import MetricsDep, WindowDep
from tracebench.query.models import (
    CostBreakdown,
    CostDimension,
    ModelLatency,
    Overview,
    Timeseries,
    ToolHeatmap,
)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/overview", response_model=Overview)
async def overview(metrics: MetricsDep, window: WindowDep) -> Overview:
    return await metrics.overview(window)


@router.get("/timeseries", response_model=Timeseries)
async def timeseries(metrics: MetricsDep, window: WindowDep) -> Timeseries:
    return await metrics.timeseries(window)


@router.get("/models", response_model=list[ModelLatency])
async def models(metrics: MetricsDep, window: WindowDep) -> list[ModelLatency]:
    return await metrics.models(window)


@router.get("/cost", response_model=CostBreakdown)
async def cost(
    metrics: MetricsDep,
    window: WindowDep,
    group_by: Annotated[CostDimension, Query()] = "model",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> CostBreakdown:
    return await metrics.cost(window, group_by, limit)


@router.get("/tools", response_model=ToolHeatmap)
async def tools(metrics: MetricsDep, window: WindowDep) -> ToolHeatmap:
    return await metrics.tool_heatmap(window)
