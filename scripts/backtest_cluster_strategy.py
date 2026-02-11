#!/usr/bin/env python
"""
Backtest tradable insider cluster signals over a filing-date range.

Uses:
  - `insider_buy_signals` view for events
  - `market_prices` table for EOD close prices (no network required)
"""

import argparse
import json
import statistics
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from sqlalchemy import text

from src.config import get_engine
from src.analytics.cluster_buys import find_tradeable_cluster_signals
from src.exceptions import EnrichmentError, DataAccessError
from src.logging_config import configure_logging, get_logger
from src.scoring_config.scoring_weights import CLUSTER_THRESHOLDS

configure_logging()
logger = get_logger(__name__)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()

def _load_enrichment_index(path: Path) -> tuple[Dict[tuple[str, date], Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """
    Load an enriched cluster export JSON and index it by (ticker, entry_date) and by ticker.

    Returns:
      - by_event: (ticker, entry_date) -> row
      - by_ticker: ticker -> row (only when unambiguous)
    """
    payload = json.loads(path.read_text())
    rows = payload.get("rows", [])
    by_event: Dict[tuple[str, date], Dict[str, Any]] = {}
    by_ticker_candidates: Dict[str, List[Dict[str, Any]]] = {}

    for row in rows:
        ticker = row.get("ticker")
        entry_date = row.get("entry_date")
        if not ticker:
            continue
        if isinstance(entry_date, str):
            try:
                entry_date = _parse_date(entry_date)
            except ValueError:
                entry_date = None
        if isinstance(entry_date, date):
            by_event[(ticker, entry_date)] = row
        by_ticker_candidates.setdefault(ticker, []).append(row)

    by_ticker: Dict[str, Dict[str, Any]] = {}
    for ticker, candidates in by_ticker_candidates.items():
        if len(candidates) == 1:
            by_ticker[ticker] = candidates[0]

    return by_event, by_ticker


def _get_price_on_or_after(
    ticker: str, d: date, *, max_forward_gap_days: Optional[int] = None
) -> Optional[Tuple[date, float]]:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT price_date, close_price
                FROM market_prices
                WHERE ticker = :ticker
                  AND price_date >= :d
                ORDER BY price_date
                LIMIT 1
                """
            ),
            {"ticker": ticker, "d": d},
        ).fetchone()
    if not row or row[1] is None:
        return None
    price_date, price = row[0], float(row[1])
    if max_forward_gap_days is not None:
        gap = (price_date - d).days
        if gap > max_forward_gap_days:
            return None
    return price_date, price


def _compute_returns(
    signals: List[Dict[str, Any]],
    *,
    entry_date_field: str,
    horizons_days: Iterable[int],
    max_forward_gap_days: Optional[int] = None,
    debug: bool = False,
    debug_limit: int = 10,
    entry_delay_days: int = 0,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for idx, sig in enumerate(signals):
        status = sig.get("enrichment_status")
        if status is not None and status != "ok":
            if debug and idx < debug_limit:
                print(f"DEBUG {sig.get('ticker')}: skipped due to enrichment_status={status}")
            continue

        ticker = sig.get("ticker")
        entry_date = sig.get(entry_date_field)
        if not ticker or not entry_date:
            continue
        if isinstance(entry_date, str):
            entry_date = _parse_date(entry_date)

        effective_entry_date = entry_date + timedelta(days=int(entry_delay_days or 0))

        entry_px = _get_price_on_or_after(ticker, effective_entry_date, max_forward_gap_days=max_forward_gap_days)
        if not entry_px:
            continue
        entry_px_date, entry_price = entry_px
        if entry_price <= 0:
            continue

        out: Dict[str, Any] = {
            "ticker": ticker,
            "signal_filing_date": sig.get("signal_filing_date"),
            "entry_date": entry_date,
            "entry_delay_days": int(entry_delay_days or 0),
            "effective_entry_date": effective_entry_date,
            "entry_px_date": entry_px_date,
            "entry_price": entry_price,
            "entry_px_gap_days": (entry_px_date - effective_entry_date).days,
        }

        for h in horizons_days:
            target_date = effective_entry_date + timedelta(days=int(h))
            exit_px = _get_price_on_or_after(ticker, target_date, max_forward_gap_days=max_forward_gap_days)
            if not exit_px:
                out[f"exit_{h}d_px_date"] = None
                out[f"exit_{h}d_price"] = None
                out[f"exit_{h}d_px_gap_days"] = None
                out[f"ret_{h}d_pct"] = None
                continue
            exit_px_date, exit_price = exit_px
            out[f"exit_{h}d_px_date"] = exit_px_date
            out[f"exit_{h}d_price"] = exit_price
            out[f"exit_{h}d_px_gap_days"] = (exit_px_date - target_date).days
            out[f"ret_{h}d_pct"] = (exit_price - entry_price) / entry_price * 100.0

        if debug and idx < debug_limit:
            gaps = ", ".join(
                f"{h}d_gap={out.get(f'exit_{h}d_px_gap_days')}"
                for h in horizons_days
            )
            rets = ", ".join(
                f"{h}d_ret={out.get(f'ret_{h}d_pct')}"
                for h in horizons_days
            )
            print(
                f"DEBUG {ticker}: entry={effective_entry_date} px_date={entry_px_date} gap={out['entry_px_gap_days']}  "
                f"{gaps}  {rets}"
            )

        rows.append(out)
    return rows


def _summarize(returns_df: pd.DataFrame, horizons_days: List[int]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"n": int(len(returns_df))}
    for h in horizons_days:
        col = f"ret_{h}d_pct"
        coverage = int(returns_df[col].notna().sum()) if col in returns_df else 0
        summary[f"{h}d_coverage"] = coverage
        vals = [float(v) for v in returns_df[col].dropna().tolist()] if col in returns_df else []
        if not vals:
            summary[f"{h}d_mean_pct"] = None
            summary[f"{h}d_median_pct"] = None
            summary[f"{h}d_win_rate"] = None
            continue
        summary[f"{h}d_mean_pct"] = statistics.fmean(vals)
        summary[f"{h}d_median_pct"] = statistics.median(vals)
        summary[f"{h}d_win_rate"] = sum(1 for v in vals if v > 0) / len(vals)
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="Backtest tradable cluster signals using cached market_prices")
    p.add_argument("--start-filing-date", required=True, help="YYYY-MM-DD")
    p.add_argument("--end-filing-date", required=True, help="YYYY-MM-DD")
    p.add_argument("--window-days", type=int, default=10)
    p.add_argument("--min-insiders", type=int, default=3)
    p.add_argument("--min-total-value", type=float, default=CLUSTER_THRESHOLDS.min_total_value_usd, help="Minimum total value (default: from config)")
    p.add_argument("--min-trade-value", type=float, default=CLUSTER_THRESHOLDS.min_trade_value_usd, help="Minimum per-trade value (default: from config)")
    p.add_argument("--min-role-score", type=int, default=None)
    p.add_argument("--min-people", type=int, default=None)
    p.add_argument("--min-cluster-score", type=float, default=None)
    p.add_argument("--max-fund-ratio", type=float, default=CLUSTER_THRESHOLDS.max_fund_ratio)
    p.add_argument("--cooldown-days", type=int, default=0)
    p.add_argument("--ticker", type=str, default=None)
    p.add_argument("--no-exclusions", action="store_true")
    p.add_argument(
        "--horizons",
        type=str,
        default="30,60,90",
        help="Comma-separated horizon days (e.g. 21,63,126)",
    )
    p.add_argument(
        "--entry-delay-days",
        type=str,
        default="0",
        help="Comma-separated calendar-day delays applied to entry date (e.g. 0,1,2,5)",
    )
    p.add_argument(
        "--max-forward-gap-days",
        type=int,
        default=7,
        help="Max days to accept a forward-filled price (larger gaps treated as missing); set -1 to disable",
    )
    p.add_argument("--debug", action="store_true", help="Print per-signal price gaps/returns")
    p.add_argument("--debug-limit", type=int, default=10, help="Max debug lines per strategy")
    p.add_argument(
        "--out-csv",
        type=str,
        default=None,
        help="Optional CSV path for per-signal returns",
    )
    p.add_argument(
        "--enriched-export",
        type=str,
        default=None,
        help="Optional enriched cluster export JSON; if provided, signals with enrichment_status != ok are skipped",
    )
    args = p.parse_args()

    horizons_days = [int(x.strip()) for x in args.horizons.split(",") if x.strip()]
    entry_delays = [int(x.strip()) for x in args.entry_delay_days.split(",") if x.strip()]
    start = _parse_date(args.start_filing_date)
    end = _parse_date(args.end_filing_date)
    max_gap = None if args.max_forward_gap_days < 0 else int(args.max_forward_gap_days)

    signals_df = find_tradeable_cluster_signals(
        start_filing_date=start,
        end_filing_date=end,
        window_days=args.window_days,
        min_insiders=args.min_insiders,
        min_total_value=args.min_total_value,
        min_trade_value=args.min_trade_value,
        ticker=args.ticker,
        use_exclusions=not args.no_exclusions,
        min_role_score=args.min_role_score,
        min_people=args.min_people,
        max_fund_ratio=args.max_fund_ratio,
        min_cluster_score=args.min_cluster_score,
        cooldown_days=args.cooldown_days,
        signal_mode="first_qualify",
    )
    if signals_df.empty:
        print("No signals found for the given filters.")
        return

    rows = signals_df.to_dict(orient="records")
    if args.enriched_export:
        by_event, by_ticker = _load_enrichment_index(Path(args.enriched_export))
        for r in rows:
            ticker = r.get("ticker")
            entry_date = r.get("entry_date")
            if isinstance(entry_date, str):
                try:
                    entry_date = _parse_date(entry_date)
                except ValueError:
                    entry_date = None
            enriched = None
            if ticker and isinstance(entry_date, date):
                enriched = by_event.get((ticker, entry_date))
            if enriched is None and ticker:
                enriched = by_ticker.get(ticker)
            if enriched:
                r["enrichment_status"] = enriched.get("enrichment_status")
                r["enrichment_errors"] = enriched.get("enrichment_errors")
    # Compare entry policies using fields already included in the signal output.
    for entry_delay_days in entry_delays:
        label = f"first_qualify_delay{entry_delay_days}d"
        ret_rows = _compute_returns(
            rows,
            entry_date_field="entry_date",
            horizons_days=horizons_days,
            max_forward_gap_days=max_gap,
            debug=args.debug,
            debug_limit=args.debug_limit,
            entry_delay_days=entry_delay_days,
        )
        ret_df = pd.DataFrame(ret_rows)
        summary = _summarize(ret_df, horizons_days)
        print(f"\n== {label} ==")
        print(f"signals: {summary['n']}")
        for h in horizons_days:
            mean_v = summary.get(f"{h}d_mean_pct")
            med_v = summary.get(f"{h}d_median_pct")
            win_v = summary.get(f"{h}d_win_rate")
            cov_v = summary.get(f"{h}d_coverage", 0)
            if mean_v is None:
                print(f"{h}d: coverage={cov_v}/{summary['n']} (no usable prices)")
            else:
                print(
                    f"{h}d: coverage={cov_v}/{summary['n']}  mean={mean_v:.2f}%  "
                    f"median={med_v:.2f}%  win_rate={win_v:.1%}"
                )

        if args.out_csv:
            out_path = Path(args.out_csv)
            ret_df.insert(0, "strategy", label)
            mode = "a" if out_path.exists() else "w"
            header = not out_path.exists()
            ret_df.to_csv(out_path, mode=mode, header=header, index=False)

    # Still print the non-tradable benchmark as a reference.
    for r in rows:
        fr = r.get("full_reveal_filing_date")
        r["entry_date_full_reveal"] = (fr + timedelta(days=1)) if isinstance(fr, date) else None
    ret_rows = _compute_returns(
        rows,
        entry_date_field="entry_date_full_reveal",
        horizons_days=horizons_days,
        max_forward_gap_days=max_gap,
        debug=args.debug,
        debug_limit=args.debug_limit,
        entry_delay_days=0,
    )
    ret_df = pd.DataFrame(ret_rows)
    summary = _summarize(ret_df, horizons_days)
    print("\n== full_reveal_benchmark (not tradable) ==")
    print(f"signals: {summary['n']}")
    for h in horizons_days:
        mean_v = summary.get(f"{h}d_mean_pct")
        med_v = summary.get(f"{h}d_median_pct")
        win_v = summary.get(f"{h}d_win_rate")
        cov_v = summary.get(f"{h}d_coverage", 0)
        if mean_v is None:
            print(f"{h}d: coverage={cov_v}/{summary['n']} (no usable prices)")
        else:
            print(
                f"{h}d: coverage={cov_v}/{summary['n']}  mean={mean_v:.2f}%  "
                f"median={med_v:.2f}%  win_rate={win_v:.1%}"
            )

    if args.out_csv:
        out_path = Path(args.out_csv)
        ret_df.insert(0, "strategy", "full_reveal_benchmark")
        mode = "a" if out_path.exists() else "w"
        header = not out_path.exists()
        ret_df.to_csv(out_path, mode=mode, header=header, index=False)


if __name__ == "__main__":
    main()
