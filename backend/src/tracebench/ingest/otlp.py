"""OTLP/HTTP trace payload decoding for both protobuf and JSON encodings."""

import base64
import gzip
import json
import zlib
from enum import StrEnum
from typing import Any

from google.protobuf import json_format
from google.protobuf.message import DecodeError
from google.rpc.status_pb2 import Status
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from tracebench.errors import PayloadTooLargeError, UnsupportedMediaTypeError, ValidationFailedError


class OtlpEncoding(StrEnum):
    PROTOBUF = "application/x-protobuf"
    JSON = "application/json"


_ID_FIELDS = ("traceId", "spanId", "parentSpanId")


_MEDIA_TYPES = {
    "application/x-protobuf": OtlpEncoding.PROTOBUF,
    "application/protobuf": OtlpEncoding.PROTOBUF,
    "application/json": OtlpEncoding.JSON,
}


def response_encoding(content_type: str | None) -> OtlpEncoding:
    """Encoding for an error reply; falls back to JSON when the request's type is unusable."""
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    return _MEDIA_TYPES.get(media_type, OtlpEncoding.JSON)


def negotiate_encoding(content_type: str | None) -> OtlpEncoding:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    found = _MEDIA_TYPES.get(media_type)
    if found is not None:
        return found
    raise UnsupportedMediaTypeError(
        f"unsupported content type {media_type or '<none>'!r}; use application/x-protobuf or application/json"
    )


def decompress(body: bytes, content_encoding: str | None, *, max_bytes: int) -> bytes:
    encoding = (content_encoding or "identity").strip().lower()
    if encoding in {"", "identity"}:
        return body
    if encoding not in {"gzip", "deflate"}:
        raise UnsupportedMediaTypeError(f"unsupported content encoding {encoding!r}")
    wbits = 16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS
    decompressor = zlib.decompressobj(wbits)
    try:
        out = decompressor.decompress(body, max_bytes + 1)
    except (zlib.error, gzip.BadGzipFile) as exc:
        raise ValidationFailedError(f"invalid {encoding} body") from exc
    if len(out) > max_bytes or decompressor.unconsumed_tail:
        raise PayloadTooLargeError(f"decompressed payload exceeds {max_bytes} bytes")
    return out


def _hex_ids_to_base64(document: dict[str, Any]) -> None:
    # OTLP/JSON deviates from proto3 JSON: trace and span ids are hex, not base64. Only the
    # known span and link paths are walked, iteratively, so hostile nesting cannot recurse.
    nodes: list[Any] = [
        node
        for resource in _children(document, "resourceSpans")
        for scope in _children(resource, "scopeSpans")
        for node in _children(scope, "spans")
    ]
    nodes.extend(link for node in list(nodes) for link in _children(node, "links"))
    for node in nodes:
        for key in _ID_FIELDS:
            value = node.get(key)
            if isinstance(value, str) and value:
                try:
                    node[key] = base64.b64encode(bytes.fromhex(value)).decode("ascii")
                except ValueError as exc:
                    raise ValidationFailedError(f"{key} must be hex encoded, got {value[:64]!r}") from exc


def _children(node: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        return []
    value = node.get(key)
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def decode_request(body: bytes, encoding: OtlpEncoding) -> ExportTraceServiceRequest:
    request = ExportTraceServiceRequest()
    if encoding is OtlpEncoding.PROTOBUF:
        try:
            request.ParseFromString(body)
        except DecodeError as exc:
            raise ValidationFailedError("malformed OTLP protobuf payload") from exc
        return request
    try:
        document = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationFailedError("malformed OTLP JSON payload") from exc
    except RecursionError as exc:
        raise ValidationFailedError("OTLP JSON payload is nested too deeply") from exc
    if not isinstance(document, dict):
        raise ValidationFailedError("OTLP JSON payload must be an object")
    _hex_ids_to_base64(document)
    try:
        json_format.ParseDict(document, request, ignore_unknown_fields=True)
    except json_format.ParseError as exc:
        raise ValidationFailedError(f"invalid OTLP JSON payload: {str(exc)[:300]}") from exc
    except RecursionError as exc:
        raise ValidationFailedError("OTLP JSON payload is nested too deeply") from exc
    return request


def encode_status(code: int, message: str, encoding: OtlpEncoding) -> bytes:
    """Error body required by OTLP/HTTP: a google.rpc.Status in the request's encoding."""
    status = Status(code=code, message=message)
    if encoding is OtlpEncoding.PROTOBUF:
        payload: bytes = status.SerializeToString()
        return payload
    return json.dumps(json_format.MessageToDict(status)).encode()


def encode_response(rejected_spans: int, error_message: str, encoding: OtlpEncoding) -> bytes:
    response = ExportTraceServiceResponse()
    if rejected_spans:
        response.partial_success.rejected_spans = rejected_spans
        response.partial_success.error_message = error_message
    if encoding is OtlpEncoding.PROTOBUF:
        return response.SerializeToString()
    return json.dumps(json_format.MessageToDict(response)).encode()
