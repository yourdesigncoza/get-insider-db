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
    load_sector_map,
    resolve_ticker,
)
from src.scoring_config.sector_blocklist import is_sic_blocked
from src.analytics.historical_rates import (
    load_historical_rates,
    get_bucket_for_cluster,
)


def build_dashboard_rows(clusters, cik_map, rates, sector_map):
    """Enrich cluster rows with resolved tickers and historical context."""
    rows = []
    for c in clusters:
        resolved = resolve_ticker(c, cik_map)
        sector_info = sector_map.get(c["issuer_cik"], {})
        sector_label = sector_info.get("sic_description", "")
        vpi = c["value_per_insider"]

        bucket = get_bucket_for_cluster(rates, vpi)
        if bucket and bucket["n"] > 0:
            hist_label = f"{bucket['win_rate_90d']:.0%} (n={bucket['n']})"
        else:
            hist_label = "N/A"

        rows.append({
            **c,
            "display_ticker": resolved if resolved != c["ticker"] else c["ticker"],
            "sector": sector_label,
            "sec_url": _sec_edgar_url(c["issuer_cik"]),
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
    table.add_column("Sector", justify="left", no_wrap=True)
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
            _truncate(r.get("sector", ""), 25),
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


def _sec_edgar_url(issuer_cik: str) -> str:
    """Build SEC EDGAR Form 4 filing search URL for a CIK."""
    padded = issuer_cik.zfill(10)
    return (
        f"https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcompany&CIK={padded}&type=4"
        f"&dateb=&owner=include&count=10"
    )


def print_sec_links(rows):
    """Print SEC EDGAR filing links for each cluster."""
    console = Console()
    console.print()
    console.rule("[bold]SEC Filing Links[/bold]")
    console.print()
    for r in rows:
        ticker = r["display_ticker"]
        url = _sec_edgar_url(r["issuer_cik"])
        console.print(f"  {ticker:8s} {url}")
    console.print()


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
        "--max-value-per-insider", type=float, default=0,
        help="Maximum $/insider filter (default: 0 = no cap)",
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
    parser.add_argument(
        "--no-sector-filter", action="store_true",
        help="Disable sector blocklist filtering (blocked sectors hidden by default)",
    )
    parser.add_argument(
        "--links", action="store_true",
        help="Print SEC EDGAR filing links below the table",
    )
    args = parser.parse_args()

    engine = get_engine()

    # 1. Load CIK-ticker map
    cik_map = load_cik_ticker_map(engine)
    sector_map = load_sector_map(engine)

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
    if args.max_value_per_insider > 0:
        clusters = [
            c for c in clusters
            if c["value_per_insider"] <= args.max_value_per_insider
        ]

    # 3b. Filter blocked sectors (unless --no-sector-filter)
    #     Also filters out issuers with no SIC code (funds, SPACs, etc.)
    if not args.no_sector_filter:
        filtered = []
        for c in clusters:
            sector_info = sector_map.get(c["issuer_cik"])
            if not sector_info or not sector_info["sic_code"]:
                continue  # no SIC data → skip
            try:
                blocked, _ = is_sic_blocked(int(sector_info["sic_code"]))
            except (ValueError, TypeError):
                blocked = False
            if blocked:
                continue
            filtered.append(c)
        clusters = filtered

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
    rows = build_dashboard_rows(clusters, cik_map, rates, sector_map)

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
        if args.links:
            print_sec_links(rows)


if __name__ == "__main__":
    main()
