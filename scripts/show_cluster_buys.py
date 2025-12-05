#!/usr/bin/env python
"""
CLI to display top insider cluster buy events.
"""

import argparse
import sys
from pathlib import Path
from typing import Any, List

# Allow running the script directly without installing the package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from tabulate import tabulate
except Exception:  # pragma: no cover - optional dependency
    tabulate = None
try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
except Exception:  # pragma: no cover - optional dependency
    Console = None
    Table = None

from src.analytics.cluster_buys import get_top_cluster_buys


def format_rows(rows: List[Any]) -> None:
    has_total_insiders = any("num_total_insiders" in row for row in rows)
    has_fund_list = any(row.get("fund_like_insiders") for row in rows)
    has_role_score = any("role_score" in row for row in rows)
    has_key_roles = any(row.get("key_roles") for row in rows)
    has_cluster_score = any("cluster_score" in row for row in rows)
    if Console and Table:
        console = Console()
        table = Table(show_header=True, header_style="bold cyan", box=box.MARKDOWN)
        columns = [
            ("ticker", "Ticker", "left"),
            ("window_start", "Start", "center"),
            ("window_end", "End", "center"),
            ("num_insiders", "People", "right"),
        ]
        if has_total_insiders:
            columns.append(("num_total_insiders", "All", "right"))
        if has_role_score:
            columns.append(("role_score", "RoleScore", "right"))
        if has_cluster_score:
            columns.append(("cluster_score", "ClusterScore", "right"))
        columns.extend(
            [
            ("num_trades", "Trades", "right"),
            ("total_value", "Total Value", "right"),
            ("total_shares", "Shares", "right"),
            ("top_insiders", "Insiders", "left"),
            ]
        )
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
                f"{int(row.get('num_insiders', 0)):,}",
                *( [f"{int(row.get('num_total_insiders', 0)):,}"] if has_total_insiders else [] ),
                *( [f"{int(row.get('role_score', 0)):,}"] if has_role_score else [] ),
                *( [f"{float(row.get('cluster_score', 0.0)):.1f}"] if has_cluster_score else [] ),
                f"{int(row.get('num_trades', 0)):,}",
                f"${float(row.get('total_value', 0.0)):,.0f}",
                f"{float(row.get('total_shares', 0.0)):,.0f}",
                row.get("top_insiders", "") or "—",
                *( [row.get("key_roles", "") or "—"] if has_key_roles else [] ),
                *( [row.get("fund_like_insiders", "") or "—"] if has_fund_list else [] ),
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
            if has_key_roles:
                parts.append(f"key_roles={row.get('key_roles','') or '—'}")
            if has_fund_list:
                parts.append(f"funds={row.get('fund_like_insiders','') or '—'}")
            print("  ".join(parts))


def main() -> None:
    parser = argparse.ArgumentParser(description="Show top insider cluster buy events")
    parser.add_argument("--window-days", type=int, default=10, help="Window size in days")
    parser.add_argument("--lookback-days", type=int, default=120, help="Lookback period in days")
    parser.add_argument("--min-insiders", type=int, default=2, help="Minimum distinct insiders")
    parser.add_argument("--min-total-value", type=float, default=0, help="Minimum total value")
    parser.add_argument("--min-trade-value", type=float, default=0, help="Minimum per-trade value")
    parser.add_argument("--ticker", type=str, default=None, help="Optional ticker filter")
    parser.add_argument("--limit", type=int, default=20, help="Number of rows to display")
    parser.add_argument("--min-role-score", type=int, default=0, help="Minimum RoleScore filter")
    parser.add_argument("--min-people", type=int, default=None, help="Minimum people insiders filter")
    parser.add_argument(
        "--max-fund-ratio",
        type=float,
        default=None,
        help="Maximum Funds/All ratio (e.g., 0.5 keeps clusters with <=50% funds)",
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
    args = parser.parse_args()

    df = get_top_cluster_buys(
        limit=args.limit,
        window_days=args.window_days,
        lookback_days=args.lookback_days,
        min_insiders=args.min_insiders,
        min_total_value=args.min_total_value,
        min_trade_value=args.min_trade_value,
        ticker=args.ticker,
        use_exclusions=not args.no_exclusions,
        min_role_score=args.min_role_score,
        min_people=args.min_people,
        max_fund_ratio=args.max_fund_ratio,
        min_cluster_score=args.min_cluster_score,
    )

    if df.empty:
        print("No cluster buys found with the given filters.")
        return

    format_rows(df.to_dict(orient="records"))


if __name__ == "__main__":
    main()
