"""Triage a support ticket and export the span to Tracebench.

python -m demo_apps.ticket_triage "My jacket arrived with a ripped seam"
DEMO_PROVIDER=anthropic ANTHROPIC_API_KEY=... python -m demo_apps.ticket_triage "..."
"""

import asyncio
import sys

import anthropic

from demo_apps.clock import RealClock
from demo_apps.config import DemoSettings, Provider
from demo_apps.telemetry import create_tracer_provider
from demo_apps.ticket_triage.app import TicketTriager


async def main(ticket: str) -> None:
    settings = DemoSettings()
    provider = create_tracer_provider("ticket-triage", settings.otlp_endpoint)
    client = None
    if settings.provider is Provider.ANTHROPIC:
        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        client = anthropic.AsyncAnthropic(api_key=key)
    triager = TicketTriager(
        provider.get_tracer("demo_apps.ticket_triage"),
        RealClock(),
        model=settings.triage_model,
        client=client,
        capture_content=settings.capture_content,
    )
    try:
        result, trace_id = await triager.triage(ticket)
    finally:
        provider.shutdown()
    print(result.model_dump_json(indent=2))
    print(f"trace: {trace_id}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(" ".join(sys.argv[1:])))
