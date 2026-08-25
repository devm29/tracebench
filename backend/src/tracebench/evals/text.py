import json
import re
from typing import Any

_WORD = re.compile(r"[a-z0-9]+(?:['.-][a-z0-9]+)*")


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("output", "content", "text", "answer"):
            inner = value.get(key)
            if isinstance(inner, str):
                return inner
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def token_f1(expected: str, actual: str) -> float:
    exp, act = tokens(expected), tokens(actual)
    if not exp and not act:
        return 1.0
    if not exp or not act:
        return 0.0
    remaining: dict[str, int] = {}
    for t in exp:
        remaining[t] = remaining.get(t, 0) + 1
    overlap = 0
    for t in act:
        if remaining.get(t, 0) > 0:
            remaining[t] -= 1
            overlap += 1
    if overlap == 0:
        return 0.0
    precision, recall = overlap / len(act), overlap / len(exp)
    return 2 * precision * recall / (precision + recall)
