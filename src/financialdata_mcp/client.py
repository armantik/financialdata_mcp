"""Bounded HTTP retries and strict normalization of daily closing prices."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

import httpx

from .config import Settings
from .models import Asset, Quote

BASE_URL = "https://financialdata.net/api/v1"
ENDPOINTS = {"stock": "stock-prices", "index": "index-prices", "commodity": "commodity-prices"}


class DataError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


class Provider(Protocol):
    async def prices(self, asset: Asset) -> Any: ...


def retry_delay(value: str | None, attempt: int) -> float:
    """Honor Retry-After (seconds or HTTP date), bounded to 30 seconds."""
    try:
        seconds = float(value) if value is not None else 2**attempt
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            seconds = 2**attempt
    return max(0, min(seconds, 30))


class FinancialDataClient:
    def __init__(self, http: httpx.AsyncClient, key: str, settings: Settings):
        self.http, self.key, self.settings = http, key, settings

    async def prices(self, asset: Asset) -> Any:
        if not self.key:
            raise DataError("missing_api_key", "Set FINANCIALDATA_API_KEY for live data.")
        for attempt in range(self.settings.max_attempts):
            delay = 2**attempt
            try:
                response = await self.http.get(
                    f"{BASE_URL}/{ENDPOINTS[asset.kind]}",
                    params={"identifier": asset.symbol, "key": self.key},
                    timeout=self.settings.timeout_seconds,
                    follow_redirects=False,
                )
                status = response.status_code
                if status in (401, 403):
                    raise DataError(
                        "access_denied", "API key or subscription does not permit access."
                    )
                if status == 429 or 500 <= status < 600:
                    error = DataError(
                        "rate_limited" if status == 429 else "upstream_unavailable",
                        "Provider rate limit reached."
                        if status == 429
                        else "Provider unavailable.",
                        True,
                    )
                    delay = retry_delay(response.headers.get("Retry-After"), attempt)
                elif status != 200:
                    raise DataError("http_error", f"Provider returned HTTP {status}.")
                else:
                    try:
                        data = response.json()
                    except ValueError:
                        raise DataError(
                            "invalid_response", "Provider returned invalid JSON."
                        ) from None
                    if not isinstance(data, list):
                        raise DataError(
                            "invalid_response", "Expected a price array; check subscription."
                        )
                    return data
            except httpx.RequestError:
                # Never return URL, raw body, or exception text: query strings contain the key.
                error = DataError("network_error", "Provider request failed or timed out.", True)
            if attempt + 1 == self.settings.max_attempts:
                raise error
            await asyncio.sleep(delay)
        raise AssertionError("Unreachable")


def normalize(asset: Asset, rows: Any, as_of: date, stale_after_days: int) -> Quote:
    if not isinstance(rows, list):
        raise DataError("invalid_response", "Expected a price array.")
    closes: dict[date, Decimal] = {}
    try:
        for row in rows:
            if row["trading_symbol"] != asset.symbol:
                raise ValueError("Wrong symbol")
            session = date.fromisoformat(row["date"])
            raw_close = row["close"]
            if isinstance(raw_close, bool):
                raise TypeError("Boolean price")
            close = Decimal(str(raw_close))
            if (
                not close.is_finite()
                or abs(close) > Decimal("1e18")
                or close.as_tuple().exponent < -18
            ):
                raise ValueError("Non-finite price")
            if asset.kind != "commodity" and close < 0:
                raise ValueError("Negative non-commodity price")
            if session in closes and closes[session] != close:
                raise ValueError("Conflicting duplicate session")
            closes[session] = close
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise DataError(
            "invalid_response", "Invalid, mismatched, or conflicting price rows."
        ) from None
    sessions = sorted((d for d in closes if d <= as_of), reverse=True)
    if len(sessions) < 2:
        raise DataError(
            "insufficient_history", "Need two distinct closing sessions on or before report date."
        )
    latest, previous = sessions[:2]
    close, prior = closes[latest], closes[previous]
    change = close - prior
    # Negative/zero futures bases have no meaningful conventional percentage return.
    with localcontext() as context:
        context.prec = 64
        pct = (change / prior * 100).quantize(Decimal("0.0001")) if prior > 0 else None
    warnings = []
    if pct is None:
        warnings.append("Percentage unavailable: previous close is zero or negative.")
    stale = (as_of - latest).days > stale_after_days
    if stale:
        warnings.append("Latest session exceeds the configured calendar-day freshness threshold.")
    if (latest - previous).days > stale_after_days:
        warnings.append("Large gap between sessions; daily return may span missing data.")
    return Quote(
        asset=asset,
        session_date=latest,
        previous_session_date=previous,
        close=close,
        previous_close=prior,
        change=change,
        change_pct=pct,
        stale=stale,
        warnings=warnings,
    )
