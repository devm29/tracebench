import secrets

from fastapi import Request
from pydantic import SecretStr

from tracebench.api.deps import ContainerDep
from tracebench.errors import UnauthorizedError

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def check_bearer(request: Request, expected: SecretStr | None) -> None:
    if expected is None:
        return
    scheme, _, presented = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        presented.strip().encode(), expected.get_secret_value().encode()
    ):
        raise UnauthorizedError("a valid bearer token is required")


async def require_api_token(request: Request, container: ContainerDep) -> None:
    """Guards mutations when TRACEBENCH_API_TOKEN is set; reads stay open for the dashboard."""
    if request.method not in _SAFE_METHODS:
        check_bearer(request, container.settings.api_token)
