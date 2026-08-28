"""Synthetic RAG traffic (embed -> retrieve -> generate) for a service built on a different provider.

It has no runnable app behind it; it exists so the dashboards show a second provider and the
retrieval/embeddings operations alongside the agent traffic.
"""

import random

from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer

from demo_apps.clock import VirtualClock
from demo_apps.llm import TransientModelError, estimate_tokens
from demo_apps.seed.scenarios import DOCS_QA, DOCS_SOURCES
from demo_apps.spans import clocked_span
from demo_apps.telemetry import dumps


async def docs_qa_trace(tracer: Tracer, start_ns: int, rng: random.Random) -> None:
    clock = VirtualClock(start_ns)
    question, answer = rng.choice(DOCS_QA)
    model = "gpt-4o" if rng.random() < 0.2 else "gpt-4o-mini"
    rate_limited = rng.random() < 0.025
    with clocked_span(tracer, "invoke_workflow docs-qa", clock, kind=SpanKind.SERVER) as root:
        root.set_attributes(
            {
                "gen_ai.operation.name": "invoke_workflow",
                "gen_ai.workflow.name": "docs-qa",
                "gen_ai.input.messages": dumps([{"role": "user", "parts": [{"type": "text", "content": question}]}]),
            }
        )
        with clocked_span(tracer, "embeddings text-embedding-3-small", clock, kind=SpanKind.CLIENT) as span:
            span.set_attributes(
                {
                    "gen_ai.operation.name": "embeddings",
                    "gen_ai.provider.name": "openai",
                    "gen_ai.request.model": "text-embedding-3-small",
                    "gen_ai.response.model": "text-embedding-3-small",
                    "gen_ai.usage.input_tokens": estimate_tokens(question),
                    "gen_ai.embeddings.dimension.count": 1536,
                }
            )
            await clock.sleep_ms(rng.uniform(60, 180))
        source = rng.choice(DOCS_SOURCES)
        with clocked_span(tracer, f"retrieval {source}", clock, kind=SpanKind.CLIENT) as span:
            span.set_attributes(
                {
                    "gen_ai.operation.name": "retrieval",
                    "gen_ai.data_source.id": source,
                    "gen_ai.retrieval.query.text": question,
                    "app.retrieval.top_k": 6,
                }
            )
            await clock.sleep_ms(rng.uniform(20, 90))
        context_tokens = rng.randint(900, 2600)
        try:
            with clocked_span(tracer, f"chat {model}", clock, kind=SpanKind.CLIENT) as span:
                span.set_attributes(
                    {
                        "gen_ai.operation.name": "chat",
                        "gen_ai.provider.name": "openai",
                        "gen_ai.request.model": model,
                        "gen_ai.request.temperature": 0.2,
                        "gen_ai.input.messages": dumps(
                            [{"role": "user", "parts": [{"type": "text", "content": question}]}]
                        ),
                    }
                )
                if rate_limited:
                    await clock.sleep_ms(rng.uniform(40, 120))
                    raise TransientModelError("rate_limit_error", "429 Too Many Requests")
                output_tokens = estimate_tokens(answer)
                await clock.sleep_ms((420 if model == "gpt-4o" else 260) + output_tokens * rng.uniform(8, 16))
                span.set_attributes(
                    {
                        "gen_ai.response.model": f"{model}-2024-08-06" if model == "gpt-4o" else f"{model}-2024-07-18",
                        "gen_ai.response.finish_reasons": ["stop"],
                        "gen_ai.usage.input_tokens": context_tokens + estimate_tokens(question),
                        "gen_ai.usage.output_tokens": output_tokens,
                        "gen_ai.output.messages": dumps(
                            [
                                {
                                    "role": "assistant",
                                    "parts": [{"type": "text", "content": answer}],
                                    "finish_reason": "stop",
                                }
                            ]
                        ),
                    }
                )
        except TransientModelError:
            root.set_status(Status(StatusCode.ERROR, "generation failed"))
            root.set_attribute("error.type", "RateLimitError")
            return
        root.set_attribute(
            "gen_ai.output.messages",
            dumps(
                [
                    {
                        "role": "assistant",
                        "parts": [{"type": "text", "content": answer}],
                        "finish_reason": "stop",
                    }
                ]
            ),
        )
