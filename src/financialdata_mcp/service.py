"""One report pipeline shared by CLI and MCP, with per-asset failures."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import httpx

from .client import DataError, FinancialDataClient, Provider, normalize
from .config import Settings, api_key
from .demo import DemoClient
from .models import AssetError, Snapshot


def select_assets(settings: Settings, symbols: list[str] | None):
    if symbols is None:
        return settings.assets
    if not symbols or len(symbols) > 30 or len(set(symbols)) != len(symbols):
        raise ValueError("Provide 1–30 unique configured symbols.")
    lookup = {a.symbol: a for a in settings.assets}
    if any(s not in lookup for s in symbols):
        raise ValueError("Unknown symbol; use list_assets to see configured symbols.")
    return [lookup[s] for s in symbols]


async def collect(
    settings: Settings,
    provider: Provider,
    *,
    symbols: list[str] | None = None,
    as_of: date | None = None,
    demo: bool = False,
) -> Snapshot:
    assets = select_assets(settings, symbols)
    now = datetime.now(UTC)
    today = now.astimezone(ZoneInfo(settings.timezone)).date()
    report_date = as_of or today
    if report_date > today:
        raise ValueError("Future report dates are not supported.")
    quotes, errors = [], []
    terminal_error = None
    # Sequential calls avoid bursts; stop live requests after auth/quota failures.
    for asset in assets:
        try:
            if terminal_error is not None:
                raise terminal_error
            rows = await provider.prices(asset)
            quotes.append(normalize(asset, rows, report_date, settings.stale_after_days))
        except DataError as exc:
            errors.append(
                AssetError(
                    symbol=asset.symbol, code=exc.code, message=exc.message, retryable=exc.retryable
                )
            )
            if exc.code in {"missing_api_key", "access_denied", "rate_limited"}:
                terminal_error = exc
    warnings = ["SYNTHETIC DEMO DATA — not market prices."] if demo else []
    if len({q.session_date for q in quotes}) > 1:
        warnings.append("Mixed session dates: assets are not synchronized to a common close.")
    return Snapshot(
        mode="demo" if demo else "live",
        source="synthetic fixtures" if demo else "financialdata.net",
        generated_at=now,
        report_date=report_date,
        status="ok" if not errors else ("partial" if quotes else "error"),
        quotes=quotes,
        errors=errors,
        warnings=warnings,
    )


async def get_snapshot(
    settings: Settings,
    *,
    symbols: list[str] | None = None,
    as_of: date | None = None,
    demo: bool = False,
) -> Snapshot:
    if demo:
        return await collect(settings, DemoClient(), symbols=symbols, as_of=as_of, demo=True)
    async with httpx.AsyncClient() as http:
        return await collect(
            settings, FinancialDataClient(http, api_key(), settings), symbols=symbols, as_of=as_of
        )
