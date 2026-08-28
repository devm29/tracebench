from enum import StrEnum

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Provider(StrEnum):
    ANTHROPIC = "anthropic"
    MOCK = "mock"


class DemoSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEMO_", env_file=(".env", "../.env"), extra="ignore")

    provider: Provider = Provider.MOCK
    otlp_endpoint: str = "http://localhost:8105/v1/traces"
    capture_content: bool = True
    agent_model: str = "claude-sonnet-5-5"
    router_model: str = "claude-haiku-4-5"
    triage_model: str = "claude-haiku-4-5"
    agent_variant: str = Field(default="v1", pattern=r"^v[12]$")
    mock_latency_scale: float = Field(default=0.05, ge=0, le=1)
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
