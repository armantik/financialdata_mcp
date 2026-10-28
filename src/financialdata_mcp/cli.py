import argparse
import asyncio
import sys
from datetime import date

from .config import load_settings
from .service import get_snapshot
from .summary import build_report


def main() -> None:
    parser = argparse.ArgumentParser(description="FinancialData.net daily closing-price report")
    parser.add_argument("--config", help="TOML settings file")
    parser.add_argument("--demo", action="store_true", help="Use labeled synthetic fixtures")
    parser.add_argument("--as-of", type=date.fromisoformat, help="Report cutoff (YYYY-MM-DD)")
    parser.add_argument("--symbols", nargs="+", help="Subset of configured symbols")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = parser.parse_args()
    try:
        settings = load_settings(args.config)
        snapshot = asyncio.run(
            get_snapshot(settings, symbols=args.symbols, as_of=args.as_of, demo=args.demo)
        )
    except (ValueError, OSError):
        print("Invalid configuration, date, symbols, or unreadable config file.", file=sys.stderr)
        raise SystemExit(2) from None
    report = build_report(snapshot)
    print(
        report.model_dump_json(indent=2) if args.format == "json" else report.markdown,
        end="\n" if args.format == "json" else "",
    )
    raise SystemExit({"ok": 0, "partial": 3, "error": 1}[snapshot.status])


if __name__ == "__main__":
    main()
