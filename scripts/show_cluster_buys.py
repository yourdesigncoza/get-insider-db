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

from src.analytics.cluster_buys import get_top_cluster_buys


def format_rows(rows: List[Any]) -> None:
    if tabulate:
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
            print(
                f"{row['ticker']:5} "
                f"{row['window_start']}–{row['window_end']}  "
                f"insiders={row['num_insiders']:2d}  "
                f"trades={row['num_trades']:3d}  "
                f"value=${row['total_value']:,.0f}  "
                f"top={row['top_insiders']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Show top insider cluster buy events")
    parser.add_argument("--window-days", type=int, default=10, help="Window size in days")
    parser.add_argument("--lookback-days", type=int, default=120, help="Lookback period in days")
    parser.add_argument("--min-insiders", type=int, default=2, help="Minimum distinct insiders")
    parser.add_argument("--min-total-value", type=float, default=0, help="Minimum total value")
    parser.add_argument("--min-trade-value", type=float, default=0, help="Minimum per-trade value")
    parser.add_argument("--ticker", type=str, default=None, help="Optional ticker filter")
    parser.add_argument("--limit", type=int, default=20, help="Number of rows to display")
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
    )

    if df.empty:
        print("No cluster buys found with the given filters.")
        return

    format_rows(df.to_dict(orient="records"))


if __name__ == "__main__":
    main()
