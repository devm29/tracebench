import pytest
from pydantic import SecretStr

from tracebench.config import Settings


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_tokens_from_the_environment_leave_auth_off(monkeypatch: pytest.MonkeyPatch, blank: str) -> None:
    monkeypatch.setenv("TRACEBENCH_API_TOKEN", blank)
    monkeypatch.setenv("TRACEBENCH_INGEST_TOKEN", blank)
    monkeypatch.setenv("ANTHROPIC_API_KEY", blank)

    settings = Settings(_env_file=None)

    assert settings.api_token is None
    assert settings.ingest_token is None
    assert settings.anthropic_api_key is None


def test_a_real_token_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACEBENCH_API_TOKEN", "local-test-token")

    settings = Settings(_env_file=None)

    assert isinstance(settings.api_token, SecretStr)
    assert settings.api_token.get_secret_value() == "local-test-token"
