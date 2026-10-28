from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from financialdata_mcp.client import DataError, normalize
from financialdata_mcp.config import Settings, load_settings
from financialdata_mcp.demo import DemoClient
from financialdata_mcp.service import collect, select_assets
from financialdata_mcp.summary import build_report

ASSET = Settings().assets[0]
DAY = date(2025, 1, 7)


def rows(previous=100, latest=105):
    return [
        {"trading_symbol": "AAPL", "date": "2025-01-06", "close": previous},
        {"trading_symbol": "AAPL", "date": "2025-01-07", "close": latest},
    ]


def test_decimal_changes_and_order():
    q = normalize(ASSET, rows("0.1", "0.3")[::-1], DAY, 4)
    assert q.change == Decimal("0.2")
    assert q.change_pct == Decimal(200)
    assert q.previous_session_date == date(2025, 1, 6)
    assert not q.stale


def test_zero_base():
    q = normalize(ASSET, rows(0, 1), DAY, 4)
    assert q.change_pct is None
    assert q.warnings


def test_negative_futures():
    asset = Settings().assets[-1]
    data = [dict(r, trading_symbol="CL") for r in rows(-10, -5)]
    q = normalize(asset, data, DAY, 4)
    assert q.change == 5 and q.change_pct is None


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        [None],
        [{"date": "bad"}],
        rows(None),
        rows("NaN"),
        rows("Infinity"),
        rows("1e999"),
        rows("1e-999"),
        rows(True),
        rows(-1),
        [dict(rows()[0], trading_symbol="WRONG"), rows()[1]],
        rows() + [dict(rows()[1], close=999)],
    ],
)
def test_invalid_rows(data):
    with pytest.raises(DataError) as exc:
        normalize(ASSET, data, DAY, 4)
    assert exc.value.code == "invalid_response"


def test_duplicate_and_cutoff():
    q = normalize(ASSET, rows() + [rows()[0]], DAY, 4)
    assert q.change == 5
    with pytest.raises(DataError, match="two distinct"):
        normalize(ASSET, rows(), date(2025, 1, 6), 4)


def test_stale_and_weekend():
    assert not normalize(ASSET, rows(), date(2025, 1, 11), 4).stale
    assert normalize(ASSET, rows(), date(2025, 1, 12), 4).stale


def test_config():
    assert load_settings("config.example.toml") == Settings()
    with pytest.raises(ValidationError):
        Settings(timezone="not/a/timezone")
    with pytest.raises(ValidationError):
        Settings(assets=[ASSET, ASSET])
    with pytest.raises(ValidationError):
        Settings(timeout_seconds=0)


@pytest.mark.parametrize("symbols", [[], ["BAD"], ["AAPL", "AAPL"]])
def test_invalid_selection(symbols):
    with pytest.raises(ValueError):
        select_assets(Settings(), symbols)


async def test_demo_summary():
    snapshot = await collect(Settings(), DemoClient(), as_of=DAY, demo=True)
    report = build_report(snapshot)
    assert snapshot.status == "ok" and snapshot.mode == "demo"
    assert report.summary.available == 7
    assert (report.summary.advancing, report.summary.declining, report.summary.unchanged) == (
        4,
        2,
        1,
    )
    assert "SYNTHETIC" in report.markdown
    assert '"close":"101"' in report.model_dump_json()


async def test_partial_failure_and_mixed_sessions():
    class Partial:
        async def prices(self, asset):
            if asset.symbol == "AAPL":
                raise DataError("network_error", "Request failed", True)
            data = await DemoClient().prices(asset)
            if asset.symbol == "MSFT":
                data[1]["date"] = "2025-01-08"
            return data

    result = await collect(Settings(), Partial(), as_of=date(2025, 1, 8))
    assert result.status == "partial" and len(result.quotes) == 6
    assert result.errors[0].retryable
    assert any("Mixed session" in w for w in result.warnings)


async def test_auth_failure_stops_more_requests():
    class Denied:
        count = 0

        async def prices(self, asset):
            self.count += 1
            raise DataError("access_denied", "Denied")

    provider = Denied()
    result = await collect(Settings(), provider, as_of=DAY)
    assert result.status == "error" and len(result.errors) == 7
    assert provider.count == 1


async def test_future_rejected():
    with pytest.raises(ValueError):
        await collect(Settings(), DemoClient(), as_of=date(9999, 1, 1))
