"""Public, JSON-serializable contracts; decimals serialize as strings."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Asset(Model):
    symbol: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9^._=-]+$")
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["stock", "index", "commodity"]
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    unit: str = Field(min_length=1, max_length=80)
    instrument: Literal["equity", "index", "futures"]


class Quote(Model):
    asset: Asset
    session_date: date
    previous_session_date: date
    close: Decimal
    previous_close: Decimal
    change: Decimal
    change_pct: Decimal | None
    stale: bool
    warnings: list[str] = Field(default_factory=list)


class AssetError(Model):
    symbol: str
    code: str
    message: str
    retryable: bool = False


class Snapshot(Model):
    schema_version: str = "1.0"
    source: str = "financialdata.net"
    mode: Literal["live", "demo"]
    generated_at: datetime
    report_date: date
    status: Literal["ok", "partial", "error"]
    quotes: list[Quote]
    errors: list[AssetError]
    warnings: list[str] = Field(default_factory=list)


class Summary(Model):
    available: int
    failed: int
    advancing: int
    declining: int
    unchanged: int
    stale: int
    text: str


class Report(Model):
    snapshot: Snapshot
    summary: Summary
    markdown: str
