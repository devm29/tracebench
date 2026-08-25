from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MatchKind(StrEnum):
    EXACT = "exact"
    PREFIX = "prefix"


class ModelPrice(BaseModel):
    """USD per million tokens for one model within a price version."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=200)
    match: MatchKind = MatchKind.EXACT
    input_per_mtok: Decimal = Field(ge=0)
    output_per_mtok: Decimal = Field(ge=0)
    cache_read_per_mtok: Decimal | None = Field(default=None, ge=0)
    cache_write_per_mtok: Decimal | None = Field(default=None, ge=0)

    def matches(self, model: str) -> bool:
        if self.match is MatchKind.EXACT:
            return model == self.model
        return model.startswith(self.model)


class PriceVersion(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    label: str
    effective_from: datetime
    created_at: datetime
    prices: list[ModelPrice]


class PriceVersionCreate(BaseModel):
    """A new price version. It only needs to list the models whose prices change: every model
    it omits keeps the price from the version before it."""

    label: str = Field(min_length=1, max_length=120)
    effective_from: datetime
    prices: list[ModelPrice] = Field(min_length=1)

    @field_validator("prices")
    @classmethod
    def _unique_models(cls, prices: list[ModelPrice]) -> list[ModelPrice]:
        keys = [(p.model, p.match) for p in prices]
        if len(keys) != len(set(keys)):
            raise ValueError("each model/match pair may appear once per version")
        return prices


class PriceVersionSummary(BaseModel):
    id: int
    label: str
    effective_from: datetime
    created_at: datetime
    model_count: int
