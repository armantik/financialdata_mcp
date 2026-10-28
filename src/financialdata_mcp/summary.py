"""Deterministic descriptive summary; no LLM key, forecasts, or invented explanations."""

from .models import Report, Snapshot, Summary


def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def build_report(snapshot: Snapshot) -> Report:
    quotes = snapshot.quotes
    up = sum(q.change > 0 for q in quotes)
    down = sum(q.change < 0 for q in quotes)
    flat = sum(q.change == 0 for q in quotes)
    stale = sum(q.stale for q in quotes)
    text = (
        f"{len(quotes)} available, {len(snapshot.errors)} failed; "
        f"{up} advancing, {down} declining, {flat} unchanged. "
        f"{stale} stale. Changes compare each asset's latest two available sessions."
    )
    summary = Summary(
        available=len(quotes),
        failed=len(snapshot.errors),
        advancing=up,
        declining=down,
        unchanged=flat,
        stale=stale,
        text=text,
    )
    lines = [
        f"# Daily market report — {snapshot.report_date}",
        "",
        f"Mode: **{snapshot.mode.upper()}** | Status: **{snapshot.status}**",
        f"Source: {snapshot.source} | Generated: {snapshot.generated_at.isoformat()}",
        "",
        text,
        "",
        *[f"> {w}" for w in snapshot.warnings],
        "",
        "| Asset | Close | Unit | Change | Change % | Session | Previous session | Stale |",
        "|---|---:|---|---:|---:|---|---|---|",
    ]
    for q in quotes:
        pct = f"{q.change_pct:+.4f}%" if q.change_pct is not None else "N/A"
        lines.append(
            f"| {cell(q.asset.name)} ({cell(q.asset.symbol)}) | {q.close} | "
            f"{cell(q.asset.unit)} | {q.change:+} | {pct} | {q.session_date} | "
            f"{q.previous_session_date} | {'yes' if q.stale else 'no'} |"
        )
    for q in quotes:
        for warning in q.warnings:
            lines.append(f"\n> {cell(q.asset.symbol)}: {warning}\n")
    if snapshot.errors:
        lines.extend(["", "## Unavailable assets", ""])
        lines.extend(f"- {cell(e.symbol)}: `{e.code}` — {e.message}" for e in snapshot.errors)
    lines.extend(
        [
            "",
            (
                "End-of-day closes, not intraday quotes. Commodity instruments are futures; "
                "roll methodology is not verified. Prices are not adjusted total returns."
            ),
        ]
    )
    return Report(snapshot=snapshot, summary=summary, markdown="\n".join(lines) + "\n")
