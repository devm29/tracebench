"""Normalizes the message shapes found in the wild into semconv-style role/parts messages.

Handles the GenAI semconv format ({"role", "parts": [{"type": "text", "content"}]}),
OpenAI/Anthropic-style ({"role", "content": str | blocks}) and bare strings.
"""

import json
from typing import Any

from tracebench.query.models import ChatMessage, MessagePart


def _part_from_block(block: Any) -> MessagePart:
    if isinstance(block, str):
        return MessagePart(type="text", content=block)
    if not isinstance(block, dict):
        return MessagePart(type="text", content=json.dumps(block, default=str))
    kind = str(block.get("type", "text"))
    match kind:
        case "text":
            return MessagePart(type="text", content=str(block.get("content", block.get("text", ""))))
        case "tool_call" | "tool_use":
            return MessagePart(
                type="tool_call",
                name=block.get("name"),
                id=block.get("id"),
                arguments=block.get("arguments", block.get("input")),
            )
        case "tool_call_response" | "tool_result":
            return MessagePart(
                type="tool_call_response",
                id=block.get("id", block.get("tool_use_id")),
                response=block.get("response", block.get("result", block.get("content"))),
            )
        case "reasoning" | "thinking":
            return MessagePart(type="reasoning", content=str(block.get("content", block.get("thinking", ""))))
        case _:
            return MessagePart(type=kind, content=json.dumps(block, default=str))


def _message(raw: Any, default_role: str) -> ChatMessage:
    if isinstance(raw, str):
        return ChatMessage(role=default_role, parts=[MessagePart(type="text", content=raw)])
    if not isinstance(raw, dict):
        return ChatMessage(role=default_role, parts=[_part_from_block(raw)])
    role = str(raw.get("role", default_role))
    finish_reason = raw.get("finish_reason")
    if isinstance(raw.get("parts"), list):
        parts = [_part_from_block(p) for p in raw["parts"]]
    else:
        content = raw.get("content", "")
        parts = [_part_from_block(b) for b in content] if isinstance(content, list) else [_part_from_block(content)]
        if isinstance(raw.get("tool_calls"), list):
            parts.extend(
                MessagePart(
                    type="tool_call",
                    id=call.get("id"),
                    name=(call.get("function") or {}).get("name"),
                    arguments=(call.get("function") or {}).get("arguments"),
                )
                for call in raw["tool_calls"]
                if isinstance(call, dict)
            )
    return ChatMessage(
        role=role,
        parts=[p for p in parts if p.type != "text" or p.content],
        finish_reason=str(finish_reason) if finish_reason else None,
    )


def parse_messages(raw: str, *, default_role: str = "user") -> list[ChatMessage]:
    if not raw:
        return []
    try:
        decoded: Any = json.loads(raw)
    except json.JSONDecodeError:
        return [ChatMessage(role=default_role, parts=[MessagePart(type="text", content=raw)])]
    if isinstance(decoded, dict) and isinstance(decoded.get("messages"), list):
        decoded = decoded["messages"]
    items = decoded if isinstance(decoded, list) else [decoded]
    return [_message(item, default_role) for item in items]


def last_text(messages: list[ChatMessage], role: str | None = None) -> str:
    for message in reversed(messages):
        if role is None or message.role == role:
            text = message.text
            if text:
                return text
    return ""


def parse_json_or_text(raw: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw
