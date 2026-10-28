# FinancialData MCP

Small end-of-day market reporting service for FinancialData.net. Python 3.11+;
read-only MCP over stdio plus a CLI that produces JSON or Markdown. No LLM dependency.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
market-report --demo --as-of 2025-01-07
market-report --demo --as-of 2025-01-07 --format json
pytest -q
ruff check .
```

Windows: activate with `.venv\Scripts\Activate.ps1` in PowerShell.
Demo prices are synthetic, fixed to January 6–7, 2025, and labeled in every report.
Running demo without `--as-of` deliberately shows stale data, never fabricated current prices.

For live data, set `FINANCIALDATA_API_KEY` in the process environment using your local
secret manager or shell. Do not commit it or put it in tool arguments. `.env.example`
is documentation only; `.env` files are **not** automatically loaded.

```bash
market-report --config config.example.toml
market-report --symbols AAPL '^GSPC' GC SI CL --format json
mkdir -p reports
market-report --format markdown > reports/daily.md
```

Exit codes: 0 = all requested assets available (possibly stale); 1 = all failed;
2 = invalid configuration/input; 3 = partial success. Even on provider failure, a
structured report is written to stdout. Configuration errors go to stderr.

## Scope and structure

| Module | Responsibility |
|---|---|
| `models.py` | Validated assets, quotes, errors, snapshot, summary and report |
| `config.py` | TOML settings, seven default assets, environment secret lookup |
| `client.py` | FinancialData.net HTTP adapter, retries, schema validation, changes |
| `demo.py` | Fixed synthetic fixture provider |
| `service.py` | Asset selection, partial failures, session freshness |
| `summary.py` | Deterministic counts, coverage and Markdown table |
| `server.py` | Three read-only MCP tools, stdio transport |
| `cli.py` | One-shot report generation and exit statuses |
| `tests/` | Offline HTTP, calculations, service, CLI and MCP protocol tests |

Dependencies: official `mcp` Python SDK **v1**, Pydantic v2, HTTPX. Major versions
are bounded. `requirements-lock.txt` records the tested Python 3.12 environment;
the package constraints/CI matrix remain the portable install path.

## MCP

Adapt `examples/mcp-config.json` to your MCP client's server configuration and use
absolute paths. It starts in demo mode. For live data, remove `FINANCIALDATA_DEMO`
and inject `FINANCIALDATA_API_KEY` through your client's secret/environment mechanism.
No HTTP listener, remote authentication, orders, or trading actions are exposed.

| Tool | Inputs | Result |
|---|---|---|
| `list_assets` | none | Configured assets, units, instrument types |
| `get_quotes` | optional `symbols`, `as_of` | Structured snapshot, prices and per-asset errors |
| `daily_market_report` | optional `symbols`, `as_of` | Snapshot, deterministic summary, Markdown |

`symbols` must contain 1–30 unique configured symbols; omission selects all.
`as_of` is an ISO date cutoff, not a guarantee of historical coverage. Future dates
are rejected. Each call fetches fresh data; there is no persistent cache or scheduler.
Avoid calling both report tools for the same report because that doubles API use.

## Data contract and interpretation

The seven defaults are AAPL, MSFT, S&P 500 (`^GSPC`), Nasdaq Composite (`^IXIC`),
gold futures (`GC`), silver futures (`SI`), and WTI oil futures (`CL`). Symbols,
currency and units are configuration metadata, not independently verified provider
metadata. Check `commodity-symbols` / `index-symbols` and your subscription before
production use. These are futures series, **not spot metal or spot oil prices**.

Routes: `/api/v1/stock-prices`, `/index-prices`, `/commodity-prices`, each with
`identifier` and secret `key` query parameters. They return daily `trading_symbol`,
`date`, `close` rows. The latest two distinct dates on/before the cutoff determine:

- `change = close - previous_close`
- `change_pct = 100 * change / previous_close`, rounded to four decimal places
- Percentage is null when previous close <= 0; negative futures closes are retained.

Decimal monetary values serialize as JSON strings. Rows are sorted; conflicting
duplicate dates, mismatched symbols, non-finite prices and malformed rows fail that
asset rather than silently using suspect data. Same-date identical rows are deduplicated.
The API's latest page (up to 300 rows) is used; arbitrary historical backfill and
pagination are outside this MVP. Fewer than two eligible rows yields `insufficient_history`.

Report date uses Europe/Stockholm by default; generation timestamp is UTC. Provider
session dates are preserved without inventing intraday timestamps or exchange timezones.
Freshness uses a configurable **calendar-day** threshold (default 4), not an exchange
holiday calendar. `ok` means complete coverage, not necessarily fresh data. Mixed dates
and large gaps are flagged. Summary counts include stale rows and disclose their count;
there is no cross-market performance ranking or fabricated causal market commentary.
Daily changes are price changes, not dividend/split-adjusted investment returns.

## Failure handling and security

Per-request timeout: 15 seconds. Maximum three attempts, with exponential backoff;
network errors, 429 and 5xx are retried. Retry-After seconds and HTTP dates are honored
up to 30 seconds. Other HTTP errors are not retried. Calls are sequential and stop
requesting remaining assets after missing-key, access-denied or exhausted quota errors.
Partial reports preserve successful assets. Error codes include `missing_api_key`,
`access_denied`, `rate_limited`, `upstream_unavailable`, `network_error`, `http_error`,
`invalid_response`, `insufficient_history`, and `demo_unavailable`.

Provider host/routes are fixed, redirects disabled, symbols allowlisted in local config.
Raw response bodies, request URLs and exception strings never enter report errors.
The server suppresses HTTPX/httpcore INFO logs because the vendor authenticates via
query strings. Do not enable HTTP debug logging with live credentials. Secrets are
read from the environment only; no key is needed for demo or offline tests.

## Running daily

The CLI is one-shot; schedule it externally after the markets you follow have closed
and the vendor has published EOD data. For example, a local cron entry can invoke:

```text
0 8 * * 1-5 /absolute/path/.venv/bin/market-report --format json > /absolute/path/reports/daily.json
```

Cron uses the host timezone and does not load your interactive shell environment.
Provision the key securely for the job, choose the timezone explicitly in your scheduler,
create the output directory first, and alert on exit 1/2/3. This example overwrites the
latest file, runs on weekday mornings (including Monday for Friday data), and is not
installed automatically. Holiday-aware scheduling, atomic output and archival are follow-ups.

## Validation and remaining decisions

Offline tests cover calculations, stale/mixed dates, malformed data, partial failure,
HTTP retry/access errors, configuration, CLI and an actual stdio MCP client handshake.
Live provider access has **not** been verified without your API key. Tests are not proof
that your subscription covers every endpoint or that commodity roll/units are correct.

Before live use: provide your FinancialData.net key locally, confirm endpoint entitlements,
choose the final watchlist, and confirm futures vs spot plus WTI vs Brent. Choose a delivery
time/timezone and destination if you want automated delivery. No OpenAI key is required.

Suggested next commits, in order:

1. `test: add opt-in live provider contract checks` — verify symbols, units, entitlements,
   freshness and futures roll methodology with a real account; keep secrets out of fixtures.
2. `feat: add exchange calendars and explicit stale-data policy` — choose handling for
   holidays, publication lag, split/roll discontinuities and mixed sessions.
3. `feat: add quota-aware cache and historical pagination` — retain provenance and dates;
   add shared rate limiting before any concurrency.
4. `feat: add scheduled delivery and report archive` — timezone, destination, atomic files,
   deduplication, alerting and retention after user decisions.

Main risks: subscription restrictions, provider schema changes, EOD publication delays,
commodity roll discontinuities, unadjusted stock splits, uneven sessions and repeated
requests exhausting quota. API licensing and redistribution terms also need review for
public distribution. No purchase or paid subscription is performed by this project.

## References

Implementation follows the provider's [documentation](https://financialdata.net/documentation),
[stock prices](https://financialdata.net/stock-prices-api),
[index prices](https://financialdata.net/index-prices-api),
[commodity prices](https://financialdata.net/commodity-prices-api), and the official
[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x).
Consulted October 28, 2026; provider contracts can change. Apache-2.0 license retained.
