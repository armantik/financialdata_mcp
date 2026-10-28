import json
import os
import subprocess
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_cli_demo():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "financialdata_mcp.cli",
            "--demo",
            "--as-of",
            "2025-01-07",
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["snapshot"]["mode"] == "demo" and data["summary"]["available"] == 7


def test_cli_missing_key():
    env = dict(os.environ, FINANCIALDATA_API_KEY="")
    env.pop("FINANCIALDATA_CONFIG", None)
    result = subprocess.run(
        [sys.executable, "-m", "financialdata_mcp.cli", "--format", "json"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["snapshot"]["errors"][0]["code"] == "missing_api_key"
    assert "Traceback" not in result.stderr


async def test_mcp_stdio_protocol():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "financialdata_mcp.server"],
        env={"FINANCIALDATA_DEMO": "true"},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        listing = await session.list_tools()
        assert {t.name for t in listing.tools} == {
            "list_assets",
            "get_quotes",
            "daily_market_report",
        }
        assert all(t.annotations.readOnlyHint for t in listing.tools)
        result = await session.call_tool("daily_market_report", {"as_of": "2025-01-07"})
        assert not result.isError
        assert result.structuredContent["snapshot"]["mode"] == "demo"
        assert result.structuredContent["summary"]["available"] == 7
        bad = await session.call_tool("get_quotes", {"symbols": ["UNKNOWN"]})
        assert bad.isError
