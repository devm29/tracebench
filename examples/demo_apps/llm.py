import itertools
from typing import Any, Protocol

import anthropic
from anthropic.types import Message, MessageParam, TextBlock, ToolParam, ToolUseBlock, Usage

_ids = itertools.count(1)


class TransientModelError(RuntimeError):
    """A retryable provider failure (rate limit, overload, network)."""

    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type


class ChatModel(Protocol):
    async def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[MessageParam],
        tools: list[ToolParam] | None = None,
    ) -> Message: ...


class AnthropicChatModel:
    def __init__(self, client: anthropic.AsyncAnthropic) -> None:
        self._client = client

    async def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[MessageParam],
        tools: list[ToolParam] | None = None,
    ) -> Message:
        try:
            if tools:
                return await self._client.messages.create(
                    model=model, max_tokens=max_tokens, system=system, messages=messages, tools=tools
                )
            return await self._client.messages.create(
                model=model, max_tokens=max_tokens, system=system, messages=messages
            )
        except anthropic.RateLimitError as exc:
            raise TransientModelError("rate_limit_error", "rate limited by the Anthropic API") from exc
        except anthropic.InternalServerError as exc:
            raise TransientModelError("overloaded_error", f"Anthropic API returned {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise TransientModelError("connection_error", "could not reach the Anthropic API") from exc


def estimate_tokens(value: Any) -> int:
    return max(1, len(str(value)) // 4)


def build_message(
    *,
    model: str,
    text: str | None = None,
    tool_calls: list[tuple[str, dict[str, Any]]] | None = None,
    input_tokens: int,
    cache_read_tokens: int = 0,
) -> Message:
    """Builds a real SDK Message so mock and live providers flow through identical code."""
    content: list[Any] = []
    if text:
        content.append(TextBlock(type="text", text=text))
    for name, arguments in tool_calls or []:
        content.append(ToolUseBlock(type="tool_use", id=f"toolu_mock_{next(_ids):06d}", name=name, input=arguments))
    output_tokens = estimate_tokens(text or "") + sum(estimate_tokens(a) + 12 for _, a in tool_calls or [])
    return Message(
        id=f"msg_mock_{next(_ids):08d}",
        type="message",
        role="assistant",
        model=model,
        content=content,
        stop_reason="tool_use" if tool_calls else "end_turn",
        stop_sequence=None,
        usage=Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read_tokens,
            cache_creation_input_tokens=0,
        ),
    )


def latency_ms(model: str, output_tokens: int, input_tokens: int) -> float:
    if "haiku" in model:
        base, per_token = 220.0, 5.5
    elif "opus" in model:
        base, per_token = 850.0, 21.0
    else:
        base, per_token = 520.0, 12.5
    return base + per_token * output_tokens + input_tokens * 0.04
