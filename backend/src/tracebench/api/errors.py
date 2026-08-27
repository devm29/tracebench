from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tracebench.errors import BackpressureError, TracebenchError, UnauthorizedError
from tracebench.logging import get_logger

log = get_logger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, object] = {}


class ErrorResponse(BaseModel):
    error: ErrorBody


def _response(status: int, body: ErrorBody, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(ErrorResponse(error=body).model_dump(mode="json"), status_code=status, headers=headers)


async def _app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, TracebenchError)
    headers: dict[str, str] | None = None
    if isinstance(exc, BackpressureError):
        headers = {"Retry-After": str(exc.retry_after_seconds)}
    elif isinstance(exc, UnauthorizedError):
        headers = {"WWW-Authenticate": "Bearer"}
    return _response(exc.status_code, ErrorBody(code=exc.code, message=exc.message, details=exc.details), headers)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    problems = [{"loc": ".".join(str(p) for p in err["loc"]), "message": err["msg"]} for err in exc.errors()]
    return _response(
        422,
        ErrorBody(code="validation_failed", message="request validation failed", details={"errors": problems}),
    )


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error", path=request.url.path, exc_info=exc)
    return _response(500, ErrorBody(code="internal_error", message="an unexpected error occurred"))


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(TracebenchError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
