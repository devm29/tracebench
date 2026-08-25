import time
from dataclasses import dataclass

import httpx
from pydantic import JsonValue


@dataclass(frozen=True, slots=True)
class TargetResponse:
    output: JsonValue | None
    latency_ms: float
    error: str | None = None


class TargetClient:
    """Calls the application under test.

    Contract: POST the dataset item's input as the JSON body; the app answers with JSON.
    If the body is an object with an "output" key that value is scored, otherwise the
    whole body is.
    """

    def __init__(self, url: str, client: httpx.AsyncClient, *, timeout: float, include_error_body: bool = True) -> None:
        self._url = url
        self._client = client
        self._timeout = timeout
        # The API must not reflect arbitrary response bodies back to its callers, the CLI may.
        self._include_error_body = include_error_body

    @property
    def url(self) -> str:
        return self._url

    async def invoke(self, payload: JsonValue) -> TargetResponse:
        started = time.perf_counter()
        try:
            response = await self._client.post(self._url, json=payload, timeout=self._timeout)
        except httpx.TimeoutException:
            return TargetResponse(None, self._elapsed(started), f"timed out after {self._timeout:.0f}s")
        except httpx.HTTPError as exc:
            reason = f"{type(exc).__name__}: {exc}" if self._include_error_body else type(exc).__name__
            return TargetResponse(None, self._elapsed(started), f"request failed: {reason}")
        latency = self._elapsed(started)
        if response.is_redirect:
            return TargetResponse(None, latency, f"HTTP {response.status_code}: redirects are not followed")
        if response.status_code >= 400:
            detail = f": {response.text[:300]}" if self._include_error_body else ""
            return TargetResponse(None, latency, f"HTTP {response.status_code}{detail}")
        try:
            body: JsonValue = response.json()
        except ValueError:
            return TargetResponse(response.text, latency)
        if isinstance(body, dict) and "output" in body:
            return TargetResponse(body["output"], latency)
        return TargetResponse(body, latency)

    @staticmethod
    def _elapsed(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 2)
