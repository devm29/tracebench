"""HTTP front door for the demo apps; this is the "target" that Tracebench evals replay against.

POST /support  {"messages": [{"role": "user", "content": "..."}]}  ->  {"output": "...", "trace_id": "..."}
POST /triage   {"messages": [{"role": "user", "content": "..."}]}  ->  {"output": "{...json...}", "trace_id": "..."}
"""

import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Literal

import anthropic
from fastapi import FastAPI, HTTPException, Request
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter
from pydantic import BaseModel, Field, StringConstraints

from demo_apps.clock import RealClock
from demo_apps.config import DemoSettings, Provider
from demo_apps.llm import AnthropicChatModel, ChatModel
from demo_apps.support_agent.agent import AgentConfig, SupportAgent
from demo_apps.support_agent.mock import MockSupportModel
from demo_apps.support_agent.tools import ToolRuntime
from demo_apps.telemetry import create_tracer_provider
from demo_apps.ticket_triage.app import TicketTriager


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(min_length=1, max_length=8000)]


class InvokeRequest(BaseModel):
    messages: list[Turn] = Field(min_length=1, max_length=40)
    session_id: str | None = Field(default=None, max_length=128)


class InvokeResponse(BaseModel):
    output: str
    trace_id: str


@dataclass(slots=True)
class DemoServices:
    providers: list[TracerProvider]
    agent: SupportAgent
    triager: TicketTriager


def build_services(settings: DemoSettings, exporter: SpanExporter | None = None) -> DemoServices:
    clock = RealClock(settings.mock_latency_scale if settings.provider is Provider.MOCK else 1.0)
    agent_provider = create_tracer_provider("support-agent", settings.otlp_endpoint, exporter=exporter)
    triage_provider = create_tracer_provider("ticket-triage", settings.otlp_endpoint, exporter=exporter)
    client: anthropic.AsyncAnthropic | None = None
    model: ChatModel
    if settings.provider is Provider.ANTHROPIC:
        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        client = anthropic.AsyncAnthropic(api_key=key)
        model = AnthropicChatModel(client)
    else:
        model = MockSupportModel(clock, variant=settings.agent_variant, rng=random.Random(11))
    agent = SupportAgent(
        model,
        ToolRuntime(clock),
        agent_provider.get_tracer("demo_apps.support_agent"),
        clock,
        AgentConfig(
            agent_model=settings.agent_model,
            router_model=settings.router_model,
            variant=settings.agent_variant,
            capture_content=settings.capture_content,
        ),
    )
    triager = TicketTriager(
        triage_provider.get_tracer("demo_apps.ticket_triage"),
        clock,
        model=settings.triage_model,
        client=client,
        capture_content=settings.capture_content,
    )
    return DemoServices(providers=[agent_provider, triage_provider], agent=agent, triager=triager)


def create_app(settings: DemoSettings | None = None, exporter: SpanExporter | None = None) -> FastAPI:
    settings = settings or DemoSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        services = build_services(settings, exporter)
        app.state.services = services
        try:
            yield
        finally:
            for provider in services.providers:
                provider.shutdown()

    app = FastAPI(title="Lumen Supply demo apps", lifespan=lifespan)

    def services(request: Request) -> DemoServices:
        found: DemoServices = request.app.state.services
        return found

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "provider": settings.provider.value, "variant": settings.agent_variant}

    @app.post("/support", response_model=InvokeResponse)
    async def support(payload: InvokeRequest, request: Request) -> InvokeResponse:
        result = await services(request).agent.run(
            [t.model_dump() for t in payload.messages], session_id=payload.session_id
        )
        return InvokeResponse(output=result.output, trace_id=result.trace_id)

    @app.post("/triage", response_model=InvokeResponse)
    async def triage(payload: InvokeRequest, request: Request) -> InvokeResponse:
        ticket = next((t.content for t in reversed(payload.messages) if t.role == "user"), None)
        if ticket is None:
            raise HTTPException(status_code=422, detail="messages must include a user turn")
        result, trace_id = await services(request).triager.triage(ticket)
        return InvokeResponse(output=result.model_dump_json(), trace_id=trace_id)

    return app
