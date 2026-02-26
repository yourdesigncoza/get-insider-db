#!/usr/bin/env python
"""
Fast batch enrichment for backtest clusters using yfinance bulk downloads.

Uses issuer_cik as the stable primary key. Resolves CIK -> ticker via the
issuer_cik_ticker_map table (falls back to the ticker in the scan data).
Downloads price history in bulk, then computes forward returns in memory.
"""

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yfinance as yf
import pandas as pd
from src.config import get_engine
from src.services.cluster_detection_fast import load_cik_ticker_map, resolve_ticker


def get_price_on_or_after(
    prices_df: pd.DataFrame, ticker: str, target_date: date, max_gap: int = 7
) -> Optional[float]:
    """Get close price on or after target_date, within max_gap days."""
    if ticker not in prices_df.columns:
        return None
    series = prices_df[ticker].dropna()
    target = pd.Timestamp(target_date)
    future = series[series.index >= target]
    if future.empty:
        return None
    first_date = future.index[0]
    if (first_date - target).days > max_gap:
        return None
    return float(future.iloc[0])


def main():
    parser = argparse.ArgumentParser(description="Fast batch enrichment for backtest")
    parser.add_argument("input_file", help="Cluster JSON from fast_scan_for_backtest.py")
    parser.add_argument("--min-total-value", type=float, default=100000,
                        help="Only enrich clusters above this value")
    parser.add_argument("--min-value-per-insider", type=float, default=0,
                        help="Min $/insider filter")
    parser.add_argument("--horizons", default="30,60,90",
                        help="Comma-separated return horizons in days")
    parser.add_argument("--max-gap", type=int, default=7,
                        help="Max days gap for price lookup")
    args = parser.parse_args()

    horizons = [int(h.strip()) for h in args.horizons.split(",")]
    max_horizon = max(horizons)

    # Load CIK -> ticker mapping
    engine = get_engine()
    cik_map = load_cik_ticker_map(engine)
    print(f"Loaded {len(cik_map)} CIK-ticker mappings")

    # Load clusters
    input_path = Path(args.input_file)
    data = json.loads(input_path.read_text())
    all_rows = data["rows"]

    # Filter
    rows = [r for r in all_rows
            if r["total_value"] >= args.min_total_value
            and r.get("value_per_insider", 0) >= args.min_value_per_insider]
    print(f"Loaded {len(all_rows)} clusters, {len(rows)} pass filters")

    if not rows:
        print("No clusters to enrich.")
        return

    # Resolve tickers via CIK map
    resolved_count = 0
    fallback_count = 0
    for r in rows:
        cik = r.get("issuer_cik", "")
        mapped_ticker = cik_map.get(cik)
        if mapped_ticker:
            r["_download_ticker"] = mapped_ticker
            resolved_count += 1
        else:
            r["_download_ticker"] = r.get("ticker", "")
            fallback_count += 1
    print(f"Ticker resolution: {resolved_count} via CIK map, {fallback_count} fallback to filing ticker")

    # Get unique download tickers and date range
    tickers = sorted(set(r["_download_ticker"] for r in rows if r["_download_ticker"]))
    entry_dates = [datetime.strptime(r["entry_date"], "%Y-%m-%d").date() for r in rows]
    earliest = min(entry_dates) - timedelta(days=5)
    latest = max(entry_dates) + timedelta(days=max_horizon + 10)

    print(f"Downloading prices for {len(tickers)} tickers ({earliest} to {latest})...")

    # Batch download in chunks
    chunk_size = 50
    all_prices = pd.DataFrame()
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        ticker_str = " ".join(chunk)
        attempt = 0
        while attempt < 3:
            try:
                df = yf.download(
                    ticker_str,
                    start=str(earliest),
                    end=str(latest),
                    progress=False,
                    auto_adjust=True,
                    threads=True,
                )
                break
            except Exception as e:
                attempt += 1
                if attempt >= 3:
                    print(f"  Failed chunk {i // chunk_size + 1} after 3 attempts: {e}")
                    df = pd.DataFrame()
                    break
                time.sleep(2)

        if df.empty:
            continue

        # yfinance returns MultiIndex columns for multiple tickers: (Price, Ticker)
        if isinstance(df.columns, pd.MultiIndex):
            close = df.get("Close", pd.DataFrame())
            if not close.empty:
                all_prices = pd.concat([all_prices, close], axis=1)
        else:
            # Single ticker case
            if "Close" in df.columns and len(chunk) == 1:
                all_prices[chunk[0]] = df["Close"]

        done = min(i + chunk_size, len(tickers))
        print(f"  Downloaded {done}/{len(tickers)} tickers")

    print(f"Price data: {len(all_prices)} trading days, {len(all_prices.columns)} tickers with data")
    tickers_with_data = set(all_prices.columns)
    tickers_missing = set(tickers) - tickers_with_data
    if tickers_missing:
        print(f"  Missing price data for {len(tickers_missing)} tickers (delisted/OTC)")

    # Compute returns for each cluster
    enriched = []
    ok_count = 0
    skip_count = 0

    for r in rows:
        dl_ticker = r["_download_ticker"]
        entry_date = datetime.strptime(r["entry_date"], "%Y-%m-%d").date()

        entry_price = get_price_on_or_after(all_prices, dl_ticker, entry_date, args.max_gap)
        if entry_price is None or entry_price <= 0:
            r["enrichment_status"] = "no_price"
            r["price_at_entry"] = None
            for h in horizons:
                r[f"return_{h}d"] = None
                r[f"price_{h}d"] = None
                r[f"max_drawdown_{h}d"] = None
            enriched.append(r)
            skip_count += 1
            continue

        r["enrichment_status"] = "ok"
        r["price_at_entry"] = round(entry_price, 2)

        for h in horizons:
            target_date = entry_date + timedelta(days=h)
            exit_price = get_price_on_or_after(all_prices, dl_ticker, target_date, args.max_gap)

            if exit_price is not None and exit_price > 0:
                ret = (exit_price - entry_price) / entry_price * 100
                r[f"return_{h}d"] = round(ret, 2)
                r[f"price_{h}d"] = round(exit_price, 2)

                # Max drawdown: worst close between entry and horizon
                series = all_prices[dl_ticker].dropna()
                entry_ts = pd.Timestamp(entry_date)
                target_ts = pd.Timestamp(target_date)
                window = series[(series.index >= entry_ts) & (series.index <= target_ts)]
                if not window.empty:
                    min_price = float(window.min())
                    dd = (min_price - entry_price) / entry_price * 100
                    r[f"max_drawdown_{h}d"] = round(dd, 2)
                else:
                    r[f"max_drawdown_{h}d"] = None
            else:
                r[f"return_{h}d"] = None
                r[f"price_{h}d"] = None
                r[f"max_drawdown_{h}d"] = None

        # Clean up internal field
        del r["_download_ticker"]
        enriched.append(r)
        ok_count += 1

    # Also remove _download_ticker from skipped rows
    for r in enriched:
        r.pop("_download_ticker", None)

    print(f"\nEnriched: {ok_count} OK, {skip_count} skipped (no price data)")

    # Write output
    out_name = input_path.stem + "_enriched"
    out_path = input_path.parent / f"{out_name}.json"

    payload = {
        "metadata": {
            **data.get("metadata", {}),
            "enriched_at": datetime.now(timezone.utc).isoformat(),
            "enrichment_filters": {
                "min_total_value": args.min_total_value,
                "min_value_per_insider": args.min_value_per_insider,
                "horizons": horizons,
            },
            "enrichment_stats": {
                "total": len(enriched),
                "ok": ok_count,
                "no_price": skip_count,
            },
        },
        "rows": enriched,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
