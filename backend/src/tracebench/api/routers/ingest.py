from typing import Annotated

from fastapi import APIRouter, Header, Request, Response

from tracebench.api.auth import check_bearer
from tracebench.api.deps import ContainerDep, IngestDep
from tracebench.errors import (
    BackpressureError,
    PayloadTooLargeError,
    TracebenchError,
    UnauthorizedError,
    UnsupportedMediaTypeError,
    ValidationFailedError,
)
from tracebench.ingest.otlp import (
    OtlpEncoding,
    decompress,
    encode_response,
    encode_status,
    negotiate_encoding,
    response_encoding,
)
from tracebench.logging import get_logger

router = APIRouter(tags=["ingest"])
log = get_logger(__name__)

# OTLP/HTTP failures carry a google.rpc.Status whose code is a gRPC status code.
_GRPC_INVALID_ARGUMENT = 3
_GRPC_RESOURCE_EXHAUSTED = 8
_GRPC_INTERNAL = 13
_GRPC_UNAVAILABLE = 14
_GRPC_UNAUTHENTICATED = 16


async def read_limited(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise PayloadTooLargeError(f"payload exceeds {limit} bytes")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise PayloadTooLargeError(f"payload exceeds {limit} bytes")
    return bytes(body)


def _error_reply(exc: TracebenchError, encoding: OtlpEncoding) -> Response:
    status, grpc_code, headers = exc.status_code, _GRPC_INTERNAL, {}
    match exc:
        case ValidationFailedError():
            status, grpc_code = 400, _GRPC_INVALID_ARGUMENT
        case UnsupportedMediaTypeError():
            grpc_code = _GRPC_INVALID_ARGUMENT
        case PayloadTooLargeError():
            grpc_code = _GRPC_RESOURCE_EXHAUSTED
        case BackpressureError():
            grpc_code = _GRPC_UNAVAILABLE
            headers["Retry-After"] = str(exc.retry_after_seconds)
        case UnauthorizedError():
            grpc_code = _GRPC_UNAUTHENTICATED
            headers["WWW-Authenticate"] = "Bearer"
    return Response(
        content=encode_status(grpc_code, exc.message, encoding),
        media_type=encoding.value,
        status_code=status,
        headers=headers,
    )


@router.post(
    "/v1/traces",
    summary="OTLP/HTTP trace export",
    description=(
        "Accepts ExportTraceServiceRequest as application/x-protobuf or application/json, optionally gzip. "
        "Errors are google.rpc.Status messages in the request's encoding, as the OTLP/HTTP spec requires."
    ),
    response_class=Response,
)
async def export_traces(
    request: Request,
    ingest: IngestDep,
    container: ContainerDep,
    content_type: Annotated[str | None, Header()] = None,
    content_encoding: Annotated[str | None, Header()] = None,
) -> Response:
    reply_encoding = response_encoding(content_type)
    limit = container.settings.ingest_max_body_bytes
    try:
        check_bearer(request, container.settings.ingest_token)
        encoding = negotiate_encoding(content_type)
        body = decompress(await read_limited(request, limit), content_encoding, max_bytes=limit)
        result = await ingest.ingest(body, encoding)
    except TracebenchError as exc:
        if exc.status_code >= 500 and not isinstance(exc, BackpressureError):
            log.error("ingest failed", error=exc.message)
        return _error_reply(exc, reply_encoding)
    return Response(
        content=encode_response(result.rejected, "; ".join(result.errors), encoding),
        media_type=encoding.value,
        status_code=200,
    )
