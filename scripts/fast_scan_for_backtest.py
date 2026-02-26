#!/usr/bin/env python
"""
Fast cluster scanner for backtesting — pure SQL approach.

Bypasses the slow Python window processing and N+1 insider classification.
Detects clusters directly in SQL using window functions and outputs
JSON compatible with enrich_clusters_with_price.py.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_engine
from src.services.cluster_detection_fast import detect_clusters_fast


def main():
    parser = argparse.ArgumentParser(description="Fast cluster scan for backtesting")
    parser.add_argument("--start-date", required=True, help="Start filing date YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End filing date YYYY-MM-DD")
    parser.add_argument("--window-days", type=int, default=10)
    parser.add_argument("--min-insiders", type=int, default=2)
    parser.add_argument("--min-total-value", type=float, default=50000)
    parser.add_argument("--basename", required=True, help="Output filename (without .json)")
    parser.add_argument("--output-dir", default="exports/backtest")
    args = parser.parse_args()

    start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end = datetime.strptime(args.end_date, "%Y-%m-%d").date()

    engine = get_engine()
    print(f"Scanning {args.start_date} to {args.end_date}...")

    clusters = detect_clusters_fast(
        engine, start, end,
        window_days=args.window_days,
        min_insiders=args.min_insiders,
        min_total_value=args.min_total_value,
    )

    print(f"Found {len(clusters)} clusters")

    # Deduplicate: keep highest-value cluster per ticker
    best_per_ticker = {}
    for c in clusters:
        key = c["ticker"]
        if key not in best_per_ticker or c["total_value"] > best_per_ticker[key]["total_value"]:
            best_per_ticker[key] = c
    deduped = sorted(best_per_ticker.values(), key=lambda c: c["signal_filing_date"])

    print(f"After dedup: {len(deduped)} unique tickers")

    # Write output
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.basename}.json"

    payload = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "row_count": len(deduped),
            "filters": {
                "start_date": args.start_date,
                "end_date": args.end_date,
                "window_days": args.window_days,
                "min_insiders": args.min_insiders,
                "min_total_value": args.min_total_value,
            },
        },
        "rows": deduped,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
