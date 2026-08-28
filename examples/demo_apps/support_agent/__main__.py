"""Ask the support agent one question and export its trace to Tracebench.

python -m demo_apps.support_agent "Where is my order 48137?"
DEMO_PROVIDER=anthropic ANTHROPIC_API_KEY=... python -m demo_apps.support_agent "..."
"""

import asyncio
import sys

from demo_apps.config import DemoSettings
from demo_apps.server import build_services


async def main(question: str) -> None:
    services = build_services(DemoSettings())
    try:
        result = await services.agent.run([{"role": "user", "content": question}])
    finally:
        for provider in services.providers:
            provider.shutdown()
    print(result.output)
    print(f"intent: {result.intent}  trace: {result.trace_id}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(" ".join(sys.argv[1:])))
