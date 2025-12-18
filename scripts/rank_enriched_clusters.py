#!/usr/bin/env python
"""
Rank and filter enriched cluster exports to find 'Tier A' High Conviction setups.
Focuses on Relative Conviction (Cluster Value % of Market Cap).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any

def rank_clusters(
    data: Dict[str, Any],
    min_mcap_millions: float = 50.0,
    min_conviction_bps: float = 5.0,
    max_pe: float | None = None,
    max_pb: float | None = None,
    max_peg: float | None = None,
):
    """
    Filter and rank clusters based on fundamental relative conviction.
    min_conviction_bps: Minimum basis points (1 bp = 0.01%) of Market Cap bought.
                        5 bps = 0.05%. 10 bps = 0.1%.
    """
    rows = data.get("rows", [])
    if not rows:
        print("No rows found in data.")
        return

    print(f"Total Clusters: {len(rows)}")
    
    # FILTER
    qualified = []
    skipped_small_cap = 0
    skipped_low_conviction = 0
    skipped_no_data = 0
    skipped_valuation = 0
    
    for r in rows:
        mcap = r.get("market_cap_at_entry", r.get("market_cap_at_window_end"))
        rel_val_pct = r.get("cluster_value_vs_mcap_pct")
        pe = r.get("pe_ratio_at_entry", r.get("pe_ratio_at_window_end"))
        pb = r.get("pb_ratio_at_entry", r.get("pb_ratio_at_window_end"))
        peg = r.get("trailing_peg_ratio_at_entry", r.get("trailing_peg_ratio_at_window_end"))
        
        if mcap is None or rel_val_pct is None:
            skipped_no_data += 1
            continue
            
        # Mcap Filter (e.g. > $50M)
        # Alpha Vantage mcap is usually in raw units (dollars), not millions.
        # Let's assume raw dollars.
        if mcap < (min_mcap_millions * 1_000_000):
            skipped_small_cap += 1
            continue
            
        # Relative Conviction Filter (e.g. > 0.05%)
        # rel_val_pct is already a percentage (0.1 = 0.1%).
        # min_conviction_bps = 5 -> 0.05%
        threshold_pct = min_conviction_bps / 100.0
        
        if rel_val_pct < threshold_pct:
            skipped_low_conviction += 1
            continue

        if max_pe is not None:
            if pe is None or pe <= 0 or pe > max_pe:
                skipped_valuation += 1
                continue
        if max_pb is not None:
            if pb is None or pb <= 0 or pb > max_pb:
                skipped_valuation += 1
                continue
        if max_peg is not None:
            if peg is None or peg <= 0 or peg > max_peg:
                skipped_valuation += 1
                continue
            
        # Enriched Object
        r["_rank_score"] = (rel_val_pct * 100) + (r.get("cluster_score", 0) / 10.0) 
        # Simple heuristic: heavily weight relative conviction, plus some credit for the algo score.
        
        qualified.append(r)

    valuation_part = (
        f", {skipped_valuation} (Valuation Filters)"
        if any(v is not None for v in (max_pe, max_pb, max_peg))
        else ""
    )
    print(
        f"Skipped: {skipped_no_data} (No Data), {skipped_small_cap} (<${min_mcap_millions}M Cap), {skipped_low_conviction} (<{min_conviction_bps} bps Conviction){valuation_part}"
    )
    print(f"Qualified: {len(qualified)} Tier A Candidates")
    print("-" * 80)

    # SORT
    # Sort by Relative Conviction descending
    qualified.sort(key=lambda x: x.get("cluster_value_vs_mcap_pct", 0), reverse=True)
    
    # PRINT
    # Format: Ticker | Date | Score | Insiders | Total $ | MCap | % of Cap | 3m Rtn
    header = f"{'TICKER':<6} | {'ENTRY':<10} | {'SCORE':<5} | {'INS':<3} | {'VALUE ($M)':<10} | {'MCAP ($M)':<10} | {'% MCAP':<8} | {'PE':<8} | {'PB':<8} | {'PEG':<8} | {'1M RTN':<8} | {'2M RTN':<8} | {'3M RTN':<8}"
    print(header)
    print("-" * len(header))
    
    for q in qualified:
        ticker = q.get("ticker")
        date = q.get("entry_date") or q.get("signal_filing_date") or q.get("signal_date") or q.get("window_end")
        score = round(q.get("cluster_score", 0), 1)
        ins = q.get("unique_insiders") or q.get("num_insiders")
        val_millions = round(q.get("total_value", 0) / 1_000_000, 2)
        mcap_millions = round((q.get("market_cap_at_entry", q.get("market_cap_at_window_end", 0)) or 0) / 1_000_000, 0)
        pct_cap = q.get("cluster_value_vs_mcap_pct")
        pe = q.get("pe_ratio_at_entry", q.get("pe_ratio_at_window_end"))
        pb = q.get("pb_ratio_at_entry", q.get("pb_ratio_at_window_end"))
        peg = q.get("trailing_peg_ratio_at_entry", q.get("trailing_peg_ratio_at_window_end"))
        rtn_1m = q.get("return_1m")
        rtn_2m = q.get("return_2m")
        rtn_3m = q.get("return_3m")
        
        rtn_1m_str = f"{rtn_1m}%" if rtn_1m is not None else "-"
        rtn_2m_str = f"{rtn_2m}%" if rtn_2m is not None else "-"
        rtn_3m_str = f"{rtn_3m}%" if rtn_3m is not None else "-"

        pe_str = f"{round(pe, 2)}" if pe is not None else "-"
        pb_str = f"{round(pb, 3)}" if pb is not None else "-"
        peg_str = f"{round(peg, 2)}" if peg is not None else "-"
        
        print(
            f"{ticker:<6} | {date:<10} | {score:<5} | {ins:<3} | ${val_millions:<9} | ${mcap_millions:<9} | {pct_cap:<8} | {pe_str:<8} | {pb_str:<8} | {peg_str:<8} | {rtn_1m_str:<8} | {rtn_2m_str:<8} | {rtn_3m_str:<8}"
        )

def main():
    parser = argparse.ArgumentParser(description="Rank clusters by relative conviction")
    parser.add_argument("file_path", type=str, help="Path to enriched JSON file")
    parser.add_argument("--min-mcap", type=float, default=50.0, help="Min Market Cap in Millions (default: 50)")
    parser.add_argument("--min-bps", type=float, default=5.0, help="Min Relative Conviction in Basis Points (default: 5 = 0.05%)")
    parser.add_argument("--max-pe", type=float, default=None, help="Max PE ratio at window end (filters out missing/<=0 as well)")
    parser.add_argument("--max-pb", type=float, default=None, help="Max PB ratio at window end (filters out missing/<=0 as well)")
    parser.add_argument("--max-peg", type=float, default=None, help="Max PEG ratio at window end (filters out missing/<=0 as well)")
    
    args = parser.parse_args()
    
    path = Path(args.file_path)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)
        
    try:
        data = json.loads(path.read_text())
        rank_clusters(data, args.min_mcap, args.min_bps, args.max_pe, args.max_pb, args.max_peg)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
