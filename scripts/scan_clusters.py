#!/usr/bin/env python
"""
Scan for insider cluster buy events — detect, score, and output to
disk (JSON) so runs are nameable, repeatable, and easy to analyze later.

Use --print to also display a formatted table in the console.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Allow running the script directly without installing the package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from tabulate import tabulate
except ImportError:
    tabulate = None
try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
except ImportError:
    Console = None
    Table = None

from src.analytics.cluster_buys import get_top_cluster_buys
from src.scoring_config.scoring_weights import CLUSTER_THRESHOLDS


def format_rows(rows: List[Any]) -> None:
    """Print cluster rows as a Rich table, tabulate table, or plain text."""
    has_total_insiders = any("num_total_insiders" in row for row in rows)
    has_fund_list = any(row.get("fund_like_insiders") for row in rows)
    has_role_score = any("role_score" in row for row in rows)
    has_key_roles = any(row.get("key_roles") for row in rows)
    has_cluster_score = any("cluster_score" in row for row in rows)
    has_signal_filing_date = any("signal_filing_date" in row for row in rows)
    has_entry_date = any("entry_date" in row for row in rows)
    has_avg_percent_change = any("avg_percent_change" in row for row in rows)
    has_avg_days_to_file = any("avg_days_to_file" in row for row in rows)
    has_avg_sale_to_purchase_ratio = any("avg_sale_to_purchase_ratio" in row for row in rows)
    if Console and Table:
        console = Console()
        table = Table(show_header=True, header_style="bold cyan", box=box.MARKDOWN)
        columns = [
            ("ticker", "Ticker", "left"),
            ("window_start", "Start", "center"),
            ("window_end", "End", "center"),
        ]
        if has_signal_filing_date:
            columns.append(("signal_filing_date", "Filed", "center"))
        if has_entry_date:
            columns.append(("entry_date", "Entry", "center"))
        columns.append(("num_insiders", "People", "right"))
        if has_total_insiders:
            columns.append(("num_total_insiders", "All", "right"))
        if has_role_score:
            columns.append(("role_score", "RoleScore", "right"))
        if has_cluster_score:
            columns.append(("cluster_score", "ClusterScore", "right"))
        if has_avg_percent_change:
            columns.append(("avg_percent_change", "Avg % Chg", "right"))
        if has_avg_days_to_file:
            columns.append(("avg_days_to_file", "Avg Days to File", "right"))
        if has_avg_sale_to_purchase_ratio:
            columns.append(("avg_sale_to_purchase_ratio", "Avg S/P Ratio", "right"))
        columns.extend([
            ("num_trades", "Trades", "right"),
            ("total_value", "Total Value", "right"),
            ("total_shares", "Shares", "right"),
            ("top_insiders", "Insiders", "left"),
        ])
        if has_key_roles:
            columns.append(("key_roles", "Key Roles", "left"))
        if has_fund_list:
            columns.append(("fund_like_insiders", "Funds", "left"))
        for _, title, justify in columns:
            table.add_column(title, justify=justify)
        for row in rows:
            table.add_row(
                str(row.get("ticker", "")),
                str(row.get("window_start", "")),
                str(row.get("window_end", "")),
                *([str(row.get("signal_filing_date", ""))] if has_signal_filing_date else []),
                *([str(row.get("entry_date", ""))] if has_entry_date else []),
                f"{int(row.get('num_insiders', 0)):,}",
                *([f"{int(row.get('num_total_insiders', 0)):,}"] if has_total_insiders else []),
                *([f"{int(row.get('role_score', 0)):,}"] if has_role_score else []),
                *([f"{float(row.get('cluster_score', 0.0)):.1f}"] if has_cluster_score else []),
                *([f"{float(row.get('avg_percent_change', 0.0)):.1%}"] if has_avg_percent_change else []),
                *([f"{float(row.get('avg_days_to_file', 0.0)):.0f}"] if has_avg_days_to_file else []),
                *([f"{float(row.get('avg_sale_to_purchase_ratio', 0.0)):.1f}"] if has_avg_sale_to_purchase_ratio else []),
                f"{int(row.get('num_trades', 0)):,}",
                f"${float(row.get('total_value', 0.0)):,.0f}",
                f"{float(row.get('total_shares', 0.0)):,.0f}",
                row.get("top_insiders", "") or "—",
                *([row.get("key_roles", "") or "—"] if has_key_roles else []),
                *([row.get("fund_like_insiders", "") or "—"] if has_fund_list else []),
            )
        console.print(table)
    elif tabulate:
        print(
            tabulate(
                rows,
                headers="keys",
                tablefmt="github",
                floatfmt=".2f",
            )
        )
    else:
        for row in rows:
            parts = [
                f"{row.get('ticker',''):5}",
                f"{row.get('window_start','')}–{row.get('window_end','')}",
                f"people={int(row.get('num_insiders', 0)):2d}",
                f"trades={int(row.get('num_trades', 0)):3d}",
                f"value=${float(row.get('total_value', 0.0)):,.0f}",
                f"top={row.get('top_insiders','') or '—'}",
            ]
            if has_role_score:
                parts.insert(3, f"role_score={int(row.get('role_score', 0)):2d}")
            if has_cluster_score:
                parts.insert(4, f"cluster_score={float(row.get('cluster_score', 0.0)):.1f}")
            if has_avg_percent_change:
                parts.insert(5, f"avg_pct_chg={float(row.get('avg_percent_change', 0.0)):.1%}")
            if has_avg_days_to_file:
                parts.insert(6, f"avg_days_to_file={float(row.get('avg_days_to_file', 0.0)):.0f}")
            if has_avg_sale_to_purchase_ratio:
                parts.insert(7, f"avg_s_p_ratio={float(row.get('avg_sale_to_purchase_ratio', 0.0)):.1f}")
            if has_key_roles:
                parts.append(f"key_roles={row.get('key_roles','') or '—'}")
            if has_fund_list:
                parts.append(f"funds={row.get('fund_like_insiders','') or '—'}")
            print("  ".join(parts))


def _build_slug(args: argparse.Namespace, ts: datetime) -> str:
    """
    Build a descriptive filename fragment from the filters + timestamp.
    Example: clusters_wd10_lb120_minins3_minrole15_minscore60_maxfund0.25_20240305T131500
    """

    def _fmt(value: Any) -> str:
        if value is None:
            return "none"
        if isinstance(value, float):
            # Keep dots for readability; replace minus/space just in case.
            return f"{value}".replace(" ", "")
        return str(value).replace(" ", "")

    parts = [
        f"wd{_fmt(args.window_days)}",
        f"lb{_fmt(args.lookback_days)}",
        f"minins{_fmt(args.min_insiders)}",
        f"minrole{_fmt(args.min_role_score)}",
        f"minval{_fmt(args.min_total_value)}",
        f"mintrade{_fmt(args.min_trade_value)}",
        f"limit{_fmt(args.limit)}",
    ]
    if args.min_cluster_score is not None:
        parts.append(f"minscore{_fmt(args.min_cluster_score)}")
    if args.min_people is not None:
        parts.append(f"minpeople{_fmt(args.min_people)}")
    if args.max_fund_ratio is not None:
        parts.append(f"maxfund{_fmt(args.max_fund_ratio)}")
    if args.ticker:
        parts.append(f"ticker{_fmt(args.ticker)}")
    if not args.use_exclusions:
        parts.append("noexclusions")

    stamp = ts.strftime("%Y%m%dT%H%M%S")
    return "clusters_" + "_".join(parts) + f"_{stamp}"


def _write_outputs(
    df,
    output_dir: Path,
    base_name: str,
    metadata: Dict[str, Any],
) -> Dict[str, Path]:
    """
    Write JSON version of the data to disk.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"{base_name}.json"

    payload = {
        "metadata": metadata,
        "rows": df.to_dict(orient="records"),
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str))

    return {"json": json_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan for insider cluster buy events")
    parser.add_argument("--window-days", type=int, default=10, help="Window size in days")
    parser.add_argument("--lookback-days", type=int, default=120, help="Lookback period in days")
    parser.add_argument("--min-insiders", type=int, default=2, help="Minimum distinct insiders")
    parser.add_argument("--min-total-value", type=float, default=CLUSTER_THRESHOLDS.min_total_value_usd, help="Minimum total value (default: from config)")
    parser.add_argument("--min-trade-value", type=float, default=CLUSTER_THRESHOLDS.min_trade_value_usd, help="Minimum per-trade value (default: from config)")
    parser.add_argument("--ticker", type=str, default=None, help="Optional ticker filter")
    parser.add_argument("--limit", type=int, default=20, help="Number of rows to return")
    parser.add_argument("--min-role-score", type=int, default=0, help="Minimum RoleScore filter")
    parser.add_argument("--min-people", type=int, default=None, help="Minimum people insiders filter")
    parser.add_argument(
        "--as-of-filing-date",
        type=str,
        default=None,
        help="As-of filing date (YYYY-MM-DD) for backtests; defaults to latest filing_date in DB",
    )
    parser.add_argument(
        "--max-fund-ratio",
        type=float,
        default=CLUSTER_THRESHOLDS.max_fund_ratio,
        help="Maximum fund ratio (default: from config)",
    )
    parser.add_argument(
        "--min-cluster-score",
        type=float,
        default=None,
        help="Minimum composite ClusterScore (higher is better)",
    )
    parser.add_argument(
        "--no-exclusions",
        action="store_true",
        help="Disable insider_exclusions filter (include fund/inst insiders)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="exports/cluster_runs",
        help="Directory to write exports into",
    )
    parser.add_argument(
        "--basename",
        type=str,
        default=None,
        help="Optional base filename (without extension); if omitted, a slug is generated from filters",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_table",
        help="Also print a formatted table to the console",
    )
    args = parser.parse_args()
    args.use_exclusions = not args.no_exclusions

    as_of_filing_date = None
    if args.as_of_filing_date:
        as_of_filing_date = datetime.strptime(args.as_of_filing_date, "%Y-%m-%d").date()

    df = get_top_cluster_buys(
        limit=args.limit,
        window_days=args.window_days,
        lookback_days=args.lookback_days,
        min_insiders=args.min_insiders,
        min_total_value=args.min_total_value,
        min_trade_value=args.min_trade_value,
        ticker=args.ticker,
        use_exclusions=args.use_exclusions,
        min_role_score=args.min_role_score,
        min_people=args.min_people,
        max_fund_ratio=args.max_fund_ratio,
        min_cluster_score=args.min_cluster_score,
        as_of_filing_date=as_of_filing_date,
    )

    if df.empty:
        print("No cluster buys found with the given filters.")
        return

    if args.print_table:
        format_rows(df.to_dict(orient="records"))

    out_df = df.copy()
    for col in ("cluster_score", "avg_percent_change"):
        if col in out_df.columns:
            out_df[col] = out_df[col].round(2)

    now = datetime.now(timezone.utc)
    base_name = args.basename or _build_slug(args, now)

    metadata = {
        "generated_at": now.isoformat(),
        "row_count": len(out_df),
        "filters": {
            "window_days": args.window_days,
            "lookback_days": args.lookback_days,
            "min_insiders": args.min_insiders,
            "min_people": args.min_people,
            "min_role_score": args.min_role_score,
            "min_cluster_score": args.min_cluster_score,
            "min_total_value": args.min_total_value,
            "min_trade_value": args.min_trade_value,
            "max_fund_ratio": args.max_fund_ratio,
            "ticker": args.ticker,
            "use_exclusions": args.use_exclusions,
            "excluded_ticker_patterns": ["NULL", "", "NONE", "N/A", "NA"],
            "limit": args.limit,
            "as_of_filing_date": args.as_of_filing_date,
        },
    }

    paths = _write_outputs(
        df=out_df,
        output_dir=Path(args.output_dir),
        base_name=base_name,
        metadata=metadata,
    )

    print(
        f"Wrote {len(df)} rows -> "
        f"{paths['json'].resolve().relative_to(Path.cwd())}"
    )


if __name__ == "__main__":
    main()
