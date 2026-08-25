import base64
import gzip
import json

import pytest
from google.protobuf import json_format

from tests.factories import export_request, record_agent_trace
from tracebench.errors import PayloadTooLargeError, UnsupportedMediaTypeError, ValidationFailedError
from tracebench.ingest.otlp import OtlpEncoding, decode_request, decompress, encode_response, negotiate_encoding


def _otlp_json() -> bytes:
    request = export_request(record_agent_trace())
    document = json_format.MessageToDict(request)
    # Rewrite ids into the hex form OTLP/JSON mandates (proto3 JSON would emit base64).
    for rs in document["resourceSpans"]:
        for ss in rs["scopeSpans"]:
            for s in ss["spans"]:
                for key in ("traceId", "spanId", "parentSpanId"):
                    if key in s:
                        s[key] = base64.b64decode(s[key]).hex()
    return json.dumps(document).encode()


def test_negotiates_supported_content_types() -> None:
    assert negotiate_encoding("application/x-protobuf") is OtlpEncoding.PROTOBUF
    assert negotiate_encoding("application/json; charset=utf-8") is OtlpEncoding.JSON
    with pytest.raises(UnsupportedMediaTypeError):
        negotiate_encoding("text/plain")


def test_decodes_protobuf_round_trip() -> None:
    original = export_request(record_agent_trace())
    decoded = decode_request(original.SerializeToString(), OtlpEncoding.PROTOBUF)
    spans = decoded.resource_spans[0].scope_spans[0].spans
    assert len(spans) == 3
    assert {s.name for s in spans} == {
        "invoke_agent support-agent",
        "chat claude-sonnet-5-5",
        "execute_tool lookup_order",
    }


def test_decodes_json_with_hex_ids() -> None:
    decoded = decode_request(_otlp_json(), OtlpEncoding.JSON)
    spans = decoded.resource_spans[0].scope_spans[0].spans
    assert all(len(s.trace_id) == 16 and len(s.span_id) == 8 for s in spans)
    children = [s for s in spans if s.parent_span_id]
    assert len(children) == 2


def test_rejects_malformed_payloads() -> None:
    with pytest.raises(ValidationFailedError):
        decode_request(b"\xff\xff\xff", OtlpEncoding.PROTOBUF)
    with pytest.raises(ValidationFailedError):
        decode_request(b"{not json", OtlpEncoding.JSON)
    with pytest.raises(ValidationFailedError):
        decode_request(b'{"resourceSpans":[{"scopeSpans":[{"spans":[{"traceId":"zz"}]}]}]}', OtlpEncoding.JSON)


def test_gzip_bodies_are_decompressed_with_a_size_cap() -> None:
    body = b"x" * 5000
    assert decompress(gzip.compress(body), "gzip", max_bytes=10_000) == body
    with pytest.raises(PayloadTooLargeError):
        decompress(gzip.compress(body), "gzip", max_bytes=1000)
    with pytest.raises(UnsupportedMediaTypeError):
        decompress(body, "br", max_bytes=10_000)


def test_partial_success_response_is_encoded() -> None:
    raw = encode_response(2, "bad span", OtlpEncoding.JSON)
    assert json.loads(raw) == {"partialSuccess": {"rejectedSpans": "2", "errorMessage": "bad span"}}
    assert encode_response(0, "", OtlpEncoding.PROTOBUF) == b""
