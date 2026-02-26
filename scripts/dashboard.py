#!/usr/bin/env python
"""
Insider Cluster Dashboard — shows recent cluster buy signals ranked by
dollar-per-insider, with historical win rate context from backtest data.

Single command that answers: "What insider clusters happened recently,
and what does history say about signals like these?"
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.table import Table
from rich import box

from src.config import get_engine
from src.services.cluster_detection_fast import (
    detect_clusters_fast,
    load_cik_ticker_map,
    resolve_ticker,
)
from src.analytics.historical_rates import (
    load_historical_rates,
    get_bucket_for_cluster,
)


def build_dashboard_rows(clusters, cik_map, rates):
    """Enrich cluster rows with resolved tickers and historical context."""
    rows = []
    for c in clusters:
        resolved = resolve_ticker(c, cik_map)
        vpi = c["value_per_insider"]

        bucket = get_bucket_for_cluster(rates, vpi)
        if bucket and bucket["n"] > 0:
            hist_label = f"{bucket['win_rate_90d']:.0%} (n={bucket['n']})"
        else:
            hist_label = "N/A"

        rows.append({
            **c,
            "display_ticker": resolved if resolved != c["ticker"] else c["ticker"],
            "hist_90d": hist_label,
        })

    # Rank by value_per_insider DESC
    rows.sort(key=lambda r: r["value_per_insider"], reverse=True)
    return rows


def print_rich_table(rows, days_back, rates):
    """Render the dashboard as a Rich table."""
    console = Console()

    overall = rates.get("overall", {})
    baseline = f"{overall.get('win_rate_90d', 0):.0%}" if overall.get("n", 0) > 0 else "N/A"

    console.print()
    console.print(
        f"[bold]INSIDER CLUSTER DASHBOARD[/bold] — Last {days_back} days",
        style="bold cyan",
    )
    console.rule()
    console.print(
        f"Found [bold]{len(rows)}[/bold] clusters | "
        f"Historical baseline: [bold]{baseline}[/bold] win rate at 90d "
        f"(n={overall.get('n', 0):,})"
    )
    console.print()

    if not rows:
        console.print("[yellow]No clusters found in date range.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE_HEAVY)
    table.add_column("Ticker", justify="left", no_wrap=True)
    table.add_column("CIK", justify="left", no_wrap=True)
    table.add_column("Insiders", justify="right", no_wrap=True)
    table.add_column("$/Insider", justify="right", no_wrap=True)
    table.add_column("Total Value", justify="right", no_wrap=True)
    table.add_column("Signal Date", justify="center", no_wrap=True)
    table.add_column("Hist 90d Win%", justify="right", no_wrap=True)
    table.add_column("Top Insiders", justify="left", no_wrap=True)

    for r in rows:
        table.add_row(
            r["display_ticker"],
            r["issuer_cik"],
            str(r["num_insiders"]),
            f"${r['value_per_insider']:,.0f}",
            f"${r['total_value']:,.0f}",
            r["signal_filing_date"],
            r["hist_90d"],
            _truncate(r.get("top_insiders", ""), 60),
        )

    console.print(table)


def _truncate(s, max_len):
    """Truncate string with ellipsis if too long."""
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "\u2026"


def main():
    parser = argparse.ArgumentParser(
        description="Insider cluster dashboard with historical context"
    )
    parser.add_argument(
        "--days-back", type=int, default=30,
        help="How far back to look for clusters (default: 30)",
    )
    parser.add_argument(
        "--min-insiders", type=int, default=2,
        help="Minimum distinct insiders in a cluster (default: 2)",
    )
    parser.add_argument(
        "--min-total-value", type=float, default=100000,
        help="Minimum total cluster value in USD (default: 100000)",
    )
    parser.add_argument(
        "--min-value-per-insider", type=float, default=0,
        help="Minimum $/insider filter (default: 0)",
    )
    parser.add_argument(
        "--window-days", type=int, default=10,
        help="Rolling window size in days (default: 10)",
    )
    parser.add_argument(
        "--limit", type=int, default=20,
        help="Maximum clusters to display (default: 20)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output JSON instead of Rich table",
    )
    args = parser.parse_args()

    engine = get_engine()

    # 1. Load CIK-ticker map
    cik_map = load_cik_ticker_map(engine)

    # 2. Run cluster detection
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=args.days_back)

    clusters = detect_clusters_fast(
        engine,
        start_date=start_date,
        end_date=end_date,
        window_days=args.window_days,
        min_insiders=args.min_insiders,
        min_total_value=args.min_total_value,
    )

    # 3. Filter by value_per_insider
    if args.min_value_per_insider > 0:
        clusters = [
            c for c in clusters
            if c["value_per_insider"] >= args.min_value_per_insider
        ]

    # 4. Deduplicate: keep highest-value cluster per ticker
    best_per_ticker = {}
    for c in clusters:
        key = c["ticker"]
        if key not in best_per_ticker or c["total_value"] > best_per_ticker[key]["total_value"]:
            best_per_ticker[key] = c
    clusters = list(best_per_ticker.values())

    # 5. Load historical rates
    rates = load_historical_rates()

    # 6. Build enriched rows
    rows = build_dashboard_rows(clusters, cik_map, rates)

    # 7. Apply limit
    rows = rows[: args.limit]

    # 8. Output
    if args.json_output:
        output = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "days_back": args.days_back,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "filters": {
                    "min_insiders": args.min_insiders,
                    "min_total_value": args.min_total_value,
                    "min_value_per_insider": args.min_value_per_insider,
                    "window_days": args.window_days,
                    "limit": args.limit,
                },
                "historical_baseline": rates.get("overall", {}),
            },
            "rows": rows,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print_rich_table(rows, args.days_back, rates)


if __name__ == "__main__":
    main()
