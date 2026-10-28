"""Read-only stdio MCP entry point. stdout is reserved for the protocol."""

import logging
import os
from datetime import date

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .config import Settings, load_settings
from .models import Asset, Report, Snapshot
from .service import get_snapshot
from .summary import build_report


def create_server(settings: Settings, demo: bool = False) -> FastMCP:
    server = FastMCP("FinancialData daily market report")
    hints = ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=not demo
    )

    @server.tool(annotations=hints)
    def list_assets() -> list[Asset]:
        """List configured symbols, units, and instrument types; makes no provider requests."""
        return settings.assets

    @server.tool(annotations=hints)
    async def get_quotes(symbols: list[str] | None = None, as_of: date | None = None) -> Snapshot:
        """Get EOD closes and previous-session changes; errors stay attached to each asset."""
        return await get_snapshot(settings, symbols=symbols, as_of=as_of, demo=demo)

    @server.tool(annotations=hints)
    async def daily_market_report(
        symbols: list[str] | None = None, as_of: date | None = None
    ) -> Report:
        """Build a deterministic daily report with JSON, Markdown, freshness and coverage."""
        return build_report(await get_snapshot(settings, symbols=symbols, as_of=as_of, demo=demo))

    return server


def main() -> None:
    # httpx INFO logs otherwise include URLs containing the provider API key.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        settings = load_settings()
    except (ValueError, OSError):
        raise SystemExit("Invalid configuration; check FINANCIALDATA_CONFIG.") from None
    create_server(settings, demo=os.getenv("FINANCIALDATA_DEMO", "").lower() == "true").run(
        transport="stdio"
    )


if __name__ == "__main__":
    main()
