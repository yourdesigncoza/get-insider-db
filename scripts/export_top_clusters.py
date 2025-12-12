#!/usr/bin/env python
"""
Export top insider cluster buy events to disk (JSON) so runs are
nameable, repeatable, and easy to analyze later (including via LLMs).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

# Allow running the script directly without installing the package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analytics.cluster_buys import get_top_cluster_buys


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
    parser = argparse.ArgumentParser(description="Export top insider cluster buy events")
    parser.add_argument("--window-days", type=int, default=10, help="Window size in days")
    parser.add_argument("--lookback-days", type=int, default=120, help="Lookback period in days")
    parser.add_argument("--min-insiders", type=int, default=2, help="Minimum distinct insiders")
    parser.add_argument("--min-total-value", type=float, default=0, help="Minimum total value")
    parser.add_argument("--min-trade-value", type=float, default=0, help="Minimum per-trade value")
    parser.add_argument("--ticker", type=str, default=None, help="Optional ticker filter")
    parser.add_argument("--limit", type=int, default=20, help="Number of rows to export")
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
    args = parser.parse_args()
    args.use_exclusions = not args.no_exclusions

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
    )

    if df.empty:
        print("No cluster buys found with the given filters.")
        return

    export_df = df.copy()
    for col in ("cluster_score", "avg_percent_change"):
        if col in export_df.columns:
            export_df[col] = export_df[col].round(2)

    now = datetime.now(timezone.utc)
    base_name = args.basename or _build_slug(args, now)

    metadata = {
        "generated_at": now.isoformat(),
        "row_count": len(export_df),
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
            "limit": args.limit,
        },
    }

    paths = _write_outputs(
        df=export_df,
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
