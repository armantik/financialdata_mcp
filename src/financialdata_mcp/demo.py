"""Fixed, deliberately synthetic fixture data. Never relabeled as live or today's prices."""

from .client import DataError
from .models import Asset

VALUES = {
    "AAPL": (100, 101),
    "MSFT": (200, 198),
    "^GSPC": (5000, 5050),
    "^IXIC": (16000, 16000),
    "GC": (2000, 2020),
    "SI": (25, 24),
    "CL": (70, 71),
}


class DemoClient:
    async def prices(self, asset: Asset) -> list[dict]:
        if asset.symbol not in VALUES:
            raise DataError("demo_unavailable", "No synthetic fixture for this symbol.")
        previous, latest = VALUES[asset.symbol]
        return [
            {"trading_symbol": asset.symbol, "date": day, "close": price}
            for day, price in [("2025-01-06", previous), ("2025-01-07", latest)]
        ]
