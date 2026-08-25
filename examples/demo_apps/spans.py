from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer

from demo_apps.clock import Clock


@contextmanager
def clocked_span(tracer: Tracer, name: str, clock: Clock, *, kind: SpanKind = SpanKind.INTERNAL) -> Iterator[Span]:
    """Like start_as_current_span, but timestamps come from `clock` so backfilled traffic is consistent."""
    with tracer.start_as_current_span(
        name, kind=kind, start_time=clock.now_ns(), end_on_exit=False, record_exception=False,
        set_status_on_exception=False,
    ) as span:  # fmt: skip
        try:
            yield span
        except BaseException as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.set_attribute("error.type", getattr(exc, "error_type", type(exc).__name__))
            span.record_exception(exc, timestamp=clock.now_ns())
            raise
        finally:
            span.end(end_time=clock.now_ns())


def current_trace_id() -> str:
    return format(trace.get_current_span().get_span_context().trace_id, "032x")
