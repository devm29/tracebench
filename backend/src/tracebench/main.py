import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from tracebench import __version__
from tracebench.api.errors import install_error_handlers
from tracebench.api.routers import datasets, evals, health, ingest, metrics, prices, traces
from tracebench.config import Settings, get_settings
from tracebench.container import Container
from tracebench.logging import configure_logging, get_logger

log = get_logger("tracebench.http")


def create_app(settings: Settings | None = None, *, eval_http: httpx.AsyncClient | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = await Container.build(settings, eval_http=eval_http)
        await container.start()
        app.state.container = container
        log.info("tracebench started", version=__version__, env=settings.env)
        try:
            yield
        finally:
            await container.close()

    app = FastAPI(
        title="Tracebench",
        version=__version__,
        summary="OpenTelemetry-native LLM observability and regression testing",
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        response.headers["X-Request-ID"] = request_id
        elapsed = (time.perf_counter() - started) * 1000
        if request.url.path != "/api/health":
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(elapsed, 1),
                request_id=request_id,
            )
        return response

    install_error_handlers(app)
    for router in (
        ingest.router,
        health.router,
        traces.router,
        metrics.router,
        datasets.router,
        evals.router,
        prices.router,
    ):
        app.include_router(router)
    return app
