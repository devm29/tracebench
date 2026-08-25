import json
import uuid
from dataclasses import dataclass
from typing import Any

from anthropic.types import Message, MessageParam, ToolResultBlockParam
from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer

from demo_apps.clock import Clock
from demo_apps.llm import ChatModel, TransientModelError
from demo_apps.spans import clocked_span, current_trace_id
from demo_apps.support_agent.prompts import AGENT_SYSTEM, INTENTS, ROUTER_SYSTEM
from demo_apps.support_agent.tools import TOOLS, ToolError, ToolRuntime
from demo_apps.telemetry import PROVIDER, dumps, record_chat_request, record_chat_response

AGENT_NAME = "support-agent"
MAX_TURNS = 5
MAX_MODEL_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class AgentResult:
    output: str
    trace_id: str
    intent: str
    ok: bool


@dataclass(frozen=True, slots=True)
class AgentConfig:
    agent_model: str
    router_model: str
    variant: str = "v1"
    capture_content: bool = True


class SupportAgent:
    """Customer-support agent: a cheap router call, then a tool-use loop on the main model."""

    def __init__(self, model: ChatModel, tools: ToolRuntime, tracer: Tracer, clock: Clock, config: AgentConfig) -> None:
        self._model = model
        self._tools = tools
        self._tracer = tracer
        self._clock = clock
        self._config = config

    async def run(self, conversation: list[dict[str, str]], session_id: str | None = None) -> AgentResult:
        session_id = session_id or uuid.uuid4().hex[:16]
        messages: list[MessageParam] = [
            {"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]} for m in conversation
        ]
        with clocked_span(self._tracer, f"invoke_agent {AGENT_NAME}", self._clock, kind=SpanKind.SERVER) as root:
            root.set_attributes(
                {
                    "gen_ai.operation.name": "invoke_agent",
                    "gen_ai.agent.name": AGENT_NAME,
                    "gen_ai.provider.name": PROVIDER,
                    "gen_ai.request.model": self._config.agent_model,
                    "gen_ai.conversation.id": session_id,
                    "app.prompt_variant": self._config.variant,
                }
            )
            if self._config.capture_content:
                root.set_attribute(
                    "gen_ai.input.messages",
                    dumps(
                        [
                            {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]}
                            for m in conversation
                        ]
                    ),
                )
            trace_id = current_trace_id()
            intent = await self._route(messages[-1])
            root.set_attribute("app.intent", intent)
            output, ok = await self._loop(messages)
            if not ok:
                root.set_status(Status(StatusCode.ERROR, "agent could not complete the request"))
                root.set_attribute("error.type", "AgentGaveUp")
            if self._config.capture_content:
                root.set_attribute(
                    "gen_ai.output.messages",
                    dumps(
                        [
                            {
                                "role": "assistant",
                                "parts": [{"type": "text", "content": output}],
                                "finish_reason": "stop",
                            }
                        ]
                    ),
                )
        return AgentResult(output=output, trace_id=trace_id, intent=intent, ok=ok)

    async def _chat(
        self, *, model: str, system: str, messages: list[MessageParam], tools: bool, max_tokens: int
    ) -> Message:
        last_error: TransientModelError | None = None
        for _ in range(MAX_MODEL_ATTEMPTS):
            try:
                with clocked_span(self._tracer, f"chat {model}", self._clock, kind=SpanKind.CLIENT) as span:
                    record_chat_request(
                        span,
                        model=model,
                        max_tokens=max_tokens,
                        system=system,
                        messages=messages,
                        capture_content=self._config.capture_content,
                    )
                    response = await self._model.create(
                        model=model,
                        max_tokens=max_tokens,
                        system=system,
                        messages=messages,
                        tools=TOOLS if tools else None,
                    )
                    record_chat_response(span, response, capture_content=self._config.capture_content)
                    return response
            except TransientModelError as exc:
                last_error = exc
                await self._clock.sleep_ms(400)
        assert last_error is not None
        raise last_error

    async def _route(self, message: MessageParam) -> str:
        try:
            response = await self._chat(
                model=self._config.router_model,
                system=ROUTER_SYSTEM,
                messages=[message],
                tools=False,
                max_tokens=16,
            )
        except TransientModelError:
            return "other"
        text = "".join(b.text for b in response.content if b.type == "text").strip().lower()
        return text if text in INTENTS else "other"

    async def _loop(self, messages: list[MessageParam]) -> tuple[str, bool]:
        system = AGENT_SYSTEM[self._config.variant]
        for _ in range(MAX_TURNS):
            try:
                response = await self._chat(
                    model=self._config.agent_model,
                    system=system,
                    messages=messages,
                    tools=True,
                    max_tokens=1024,
                )
            except TransientModelError:
                return "Sorry, I'm unable to answer right now. Please try again in a moment.", False
            if response.stop_reason == "refusal":
                return "Sorry, I can't help with that request.", False
            messages.append({"role": "assistant", "content": response.content})
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_uses:
                text = "\n".join(b.text for b in response.content if b.type == "text").strip()
                gave_up = "trouble reaching" in text or "didn't go through" in text
                return text, not gave_up
            results: list[ToolResultBlockParam] = []
            for block in tool_uses:
                results.append(await self._execute(block.id, block.name, dict(block.input)))
            messages.append({"role": "user", "content": results})
        return "Sorry, I couldn't finish that request. A teammate will follow up by email.", False

    async def _execute(self, call_id: str, name: str, arguments: dict[str, Any]) -> ToolResultBlockParam:
        try:
            with clocked_span(self._tracer, f"execute_tool {name}", self._clock) as span:
                span.set_attributes(
                    {
                        "gen_ai.operation.name": "execute_tool",
                        "gen_ai.tool.name": name,
                        "gen_ai.tool.call.id": call_id,
                        "gen_ai.tool.type": "function",
                        "gen_ai.tool.call.arguments": dumps(arguments),
                    }
                )
                result = await self._tools.call(name, arguments)
                content = json.dumps(result)
                span.set_attribute("gen_ai.tool.call.result", content)
                return {"type": "tool_result", "tool_use_id": call_id, "content": content}
        except ToolError as exc:
            return {
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": f"{exc.error_type}: {exc}",
                "is_error": True,
            }
