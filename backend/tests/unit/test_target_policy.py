import pytest

from tracebench.config import Settings
from tracebench.errors import ValidationFailedError
from tracebench.evals.target_policy import TargetPolicy


def policy(**settings: object) -> TargetPolicy:
    return TargetPolicy.from_settings(Settings.model_validate({"env": "development", **settings}))


def test_development_allows_loopback_but_never_the_data_stores() -> None:
    dev = policy()
    assert dev.check("http://localhost:6405/support") == "http://localhost:6405/support"
    for url in ("http://127.0.0.1:27105/", "http://localhost:5505", "http://[::1]:27105/"):
        with pytest.raises(ValidationFailedError, match="data stores"):
            dev.check(url)
    with pytest.raises(ValidationFailedError, match="ALLOWLIST"):
        dev.check("http://169.254.169.254/latest/meta-data/")


def test_production_without_an_allowlist_disables_server_side_runs() -> None:
    with pytest.raises(ValidationFailedError, match="disabled"):
        policy(env="production").check("http://localhost:6405/")


def test_allowlist_entries_match_host_and_optional_port() -> None:
    prod = policy(env="production", eval_target_allowlist=["app.internal:8080", "staging.example.com"])
    assert prod.check("http://app.internal:8080/invoke")
    assert prod.check("https://staging.example.com/a")
    for url in ("http://app.internal:9000/", "http://localhost:6405/", "gopher://staging.example.com/"):
        with pytest.raises(ValidationFailedError):
            prod.check(url)
