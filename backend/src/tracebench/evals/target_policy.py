from collections.abc import Iterable

import httpx
from sqlalchemy.engine import make_url

from tracebench.config import Settings
from tracebench.errors import ValidationFailedError

_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _parse_entry(entry: str) -> tuple[str, int | None]:
    url = httpx.URL(f"http://{entry.strip()}")
    return url.host.lower(), url.port


class TargetPolicy:
    """Decides which URLs the API itself may call when it executes an eval run.

    Server-side execution turns the API into an HTTP client on behalf of whoever can reach
    it, so targets are restricted to an explicit allowlist and the API's own backing
    stores are never reachable through it, whatever the allowlist says.
    """

    def __init__(
        self,
        allowlist: Iterable[str],
        *,
        allow_loopback: bool = False,
        blocked: Iterable[tuple[str, int]] = (),
    ) -> None:
        self._allowed = [_parse_entry(e) for e in allowlist if e.strip()]
        self._allow_loopback = allow_loopback
        self._blocked = {(host.lower(), port) for host, port in blocked}

    @classmethod
    def from_settings(cls, settings: Settings) -> "TargetPolicy":
        blocked = [(settings.clickhouse_host, settings.clickhouse_port)]
        database = make_url(settings.database_url)
        blocked.append((database.host or "localhost", database.port or 5432))
        if any(host in _LOOPBACK for host, _ in blocked):
            blocked.extend((alias, port) for _, port in list(blocked) for alias in _LOOPBACK)
        return cls(
            settings.eval_target_allowlist,
            allow_loopback=not settings.eval_target_allowlist and settings.env != "production",
            blocked=blocked,
        )

    @property
    def enabled(self) -> bool:
        return bool(self._allowed) or self._allow_loopback

    def check(self, raw: str) -> str:
        if not self.enabled:
            raise ValidationFailedError(
                "server-side eval execution is disabled; set TRACEBENCH_EVAL_TARGET_ALLOWLIST or run the CLI"
            )
        try:
            url = httpx.URL(raw)
        except httpx.InvalidURL as exc:
            raise ValidationFailedError(f"invalid target url: {exc}") from exc
        if url.scheme not in _DEFAULT_PORTS or not url.host:
            raise ValidationFailedError("target url must be an absolute http(s) url")
        host = url.host.lower()
        port = url.port or _DEFAULT_PORTS[url.scheme]
        if (host, port) in self._blocked:
            raise ValidationFailedError(f"target {host}:{port} is one of Tracebench's own data stores")
        if self._allow_loopback and host in _LOOPBACK:
            return str(url)
        if any(host == h and (p is None or p == port) for h, p in self._allowed):
            return str(url)
        raise ValidationFailedError(
            f"target host {host}:{port} is not in TRACEBENCH_EVAL_TARGET_ALLOWLIST",
            details={"host": host, "port": port},
        )
