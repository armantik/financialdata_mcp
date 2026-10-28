"""Local TOML configuration and secret lookup (never passed through MCP tools)."""

import os
import tomllib
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from .models import Asset, Model

DEFAULT_ASSETS = [
    Asset(symbol="AAPL", name="Apple", kind="stock", unit="USD/share", instrument="equity"),
    Asset(symbol="MSFT", name="Microsoft", kind="stock", unit="USD/share", instrument="equity"),
    Asset(symbol="^GSPC", name="S&P 500", kind="index", unit="points", instrument="index"),
    Asset(symbol="^IXIC", name="Nasdaq Composite", kind="index", unit="points", instrument="index"),
    Asset(
        symbol="GC", name="Gold futures", kind="commodity", unit="USD/troy oz", instrument="futures"
    ),
    Asset(
        symbol="SI",
        name="Silver futures",
        kind="commodity",
        unit="USD/troy oz",
        instrument="futures",
    ),
    Asset(
        symbol="CL",
        name="WTI crude futures",
        kind="commodity",
        unit="USD/barrel",
        instrument="futures",
    ),
]


class Settings(Model):
    timezone: str = "Europe/Stockholm"
    timeout_seconds: float = Field(default=15, gt=0, le=60)
    max_attempts: int = Field(default=3, ge=1, le=5)
    stale_after_days: int = Field(default=4, ge=1, le=30)
    assets: list[Asset] = Field(
        default_factory=lambda: list(DEFAULT_ASSETS), min_length=1, max_length=30
    )

    @model_validator(mode="after")
    def validate_settings(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Invalid IANA timezone") from exc
        symbols = [a.symbol for a in self.assets]
        if len(set(symbols)) != len(symbols):
            raise ValueError("Asset symbols must be unique")
        expected = {"stock": "equity", "index": "index", "commodity": "futures"}
        if any(a.instrument != expected[a.kind] for a in self.assets):
            raise ValueError("Asset kind and instrument do not match the supported endpoint")
        return self


def load_settings(path: str | None = None) -> Settings:
    selected = path or os.getenv("FINANCIALDATA_CONFIG")
    if not selected:
        return Settings()
    with Path(selected).open("rb") as stream:
        return Settings.model_validate(tomllib.load(stream))


def api_key() -> str:
    return os.getenv("FINANCIALDATA_API_KEY", "").strip()
