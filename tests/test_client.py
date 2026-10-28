from unittest.mock import AsyncMock

import httpx
import pytest

from financialdata_mcp.client import DataError, FinancialDataClient, retry_delay
from financialdata_mcp.config import Settings


async def invoke(handler, monkeypatch, key="secret-test-key", attempts=3):
    monkeypatch.setattr("financialdata_mcp.client.asyncio.sleep", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        return await FinancialDataClient(http, key, Settings(max_attempts=attempts)).prices(
            Settings().assets[0]
        )


async def test_route_and_key(monkeypatch):
    def handler(request):
        assert request.url.host == "financialdata.net"
        assert request.url.path == "/api/v1/stock-prices"
        assert request.url.params["identifier"] == "AAPL"
        assert request.url.params["key"] == "secret-test-key"
        return httpx.Response(200, json=[])

    assert await invoke(handler, monkeypatch) == []


@pytest.mark.parametrize(
    "status,code,calls",
    [
        (401, "access_denied", 1),
        (403, "access_denied", 1),
        (404, "http_error", 1),
        (302, "http_error", 1),
        (429, "rate_limited", 3),
        (500, "upstream_unavailable", 3),
    ],
)
async def test_http_errors(monkeypatch, status, code, calls):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, text="secret-test-key", headers={"Retry-After": "0"})

    with pytest.raises(DataError) as exc:
        await invoke(handler, monkeypatch)
    assert exc.value.code == code and len(seen) == calls
    assert "secret-test-key" not in str(exc.value)


async def test_retry_recovers(monkeypatch):
    responses = iter([httpx.Response(503), httpx.Response(200, json=[])])
    assert await invoke(lambda _: next(responses), monkeypatch) == []


async def test_timeout_bounded_and_redacted(monkeypatch):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        raise httpx.ReadTimeout("secret-test-key", request=request)

    with pytest.raises(DataError) as exc:
        await invoke(handler, monkeypatch)
    assert count == 3 and exc.value.code == "network_error"
    assert "secret-test-key" not in str(exc.value)


@pytest.mark.parametrize(
    "response",
    [httpx.Response(200, text="not-json"), httpx.Response(200, json={"error": "secret-test-key"})],
)
async def test_bad_payload(monkeypatch, response):
    with pytest.raises(DataError) as exc:
        await invoke(lambda _: response, monkeypatch)
    assert exc.value.code == "invalid_response"
    assert "secret-test-key" not in str(exc.value)


async def test_missing_key_never_requests(monkeypatch):
    def handler(_):
        pytest.fail("Should not contact provider")

    with pytest.raises(DataError) as exc:
        await invoke(handler, monkeypatch, key="")
    assert exc.value.code == "missing_api_key"


def test_retry_after():
    assert retry_delay("100", 0) == 30
    assert retry_delay("-1", 0) == 0
    assert retry_delay("invalid", 2) == 4
    assert retry_delay("Wed, 21 Oct 2015 07:28:00 GMT", 0) == 0
