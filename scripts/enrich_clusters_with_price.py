#!/usr/bin/env python
"""
Enrich cluster export JSON with historical price data from Tiingo.
Adds price at window_end, and 1, 2, 3 months forward, plus returns.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Load environment variables
load_dotenv()

TIINGO_API_KEY = os.getenv("TIINGO_API_KEY")

class TiingoError(Exception):
    pass


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException)
)
def _make_request(url, headers, params):
    response = requests.get(url, headers=headers, params=params, timeout=10)
    if response.status_code == 429:
        print("Rate limit hit, retrying...", file=sys.stderr)
        response.raise_for_status() # Trigger retry
    response.raise_for_status()
    return response

@lru_cache(maxsize=1024)
def _get_price_history(ticker: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    """
    Fetch daily price history (date, close) between start and end dates.
    Returns list of dicts: [{'date': datetime, 'close': float}, ...] sorted by date.
    """
    if not TIINGO_API_KEY:
        raise ValueError("TIINGO_API_KEY not found in environment variables.")

    # Look back 7 days to ensure we capture the start date price if it falls on a weekend
    fetch_start = start_date - timedelta(days=7)
    
    url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Token {TIINGO_API_KEY}'
    }
    params = {
        'startDate': fetch_start.strftime('%Y-%m-%d'),
        'endDate': end_date.strftime('%Y-%m-%d'),
        'columns': 'date,close'
    }

    try:
        response = _make_request(url, headers, params)
        data = response.json()
        
        if not data:
            return []
            
        # Parse dates and convert to simple list of dicts
        # Tiingo date format: "2025-07-27T00:00:00.000Z"
        cleaned_data = []
        for record in data:
            d_str = record['date'].rstrip('Z')
            # Handle potential fractional seconds
            if '.' in d_str:
                d_str = d_str.split('.')[0]
                
            dt = datetime.strptime(d_str, "%Y-%m-%dT%H:%M:%S")
            cleaned_data.append({
                'date': dt,
                'close': float(record['close'])
            })
            
        return sorted(cleaned_data, key=lambda x: x['date'])

    except Exception as e:
        print(f"Error fetching history for {ticker}: {e}", file=sys.stderr)
        return []

def _calculate_max_drawdown(prices: List[float]) -> Optional[float]:
    """
    Calculate Maximum Drawdown (MDD) from a list of prices.
    Returns the max drawdown as a percentage (e.g. -15.5 for 15.5% drop).
    Returns None if list is empty.
    """
    if not prices:
        return None
        
    peak = prices[0]
    max_dd = 0.0
    
    for p in prices:
        if p > peak:
            peak = p
        
        dd = (p - peak) / peak
        if dd < max_dd:
            max_dd = dd
            
    return round(max_dd * 100.0, 2)

def _get_closest_price_record(history: List[Dict], target_date: datetime) -> Optional[Dict]:
    """Find the last price record on or before target_date."""
    # Since history is sorted
    candidate = None
    for record in history:
        if record['date'] <= target_date:
            candidate = record
        else:
            # We went past the target date
            break
    
    # Check if the candidate is too stale (e.g. > 10 days old)? 
    # For now, we trust the caller provided a reasonable fetch range.
    return candidate

def enrich_row(row: Dict[str, Any]) -> Dict[str, Any]:
    ticker = row.get("ticker")
    window_end_str = row.get("window_end")
    
    if not ticker or not window_end_str:
        return row

    try:
        window_end_date = datetime.strptime(window_end_str, "%Y-%m-%d")
    except ValueError:
        return row

    # Define the horizons
    date_1m = window_end_date + relativedelta(months=1)
    date_2m = window_end_date + relativedelta(months=2)
    date_3m = window_end_date + relativedelta(months=3)
    
    # Fetch all data in one go
    # We fetch up to 3m out.
    history = _get_price_history(ticker, window_end_date, date_3m)
    
    # Small delay to be polite
    time.sleep(0.1)

    # 1. Base Price (at window_end)
    base_record = _get_closest_price_record(history, window_end_date)
    base_price = base_record['close'] if base_record else None
    
    results = {}
    
    for suffix, end_date in [("1m", date_1m), ("2m", date_2m), ("3m", date_3m)]:
        # Filter history for this period: window_end <= date <= end_date
        # Note: MDD includes the path from start to end.
        
        # Find endpoint price
        end_record = _get_closest_price_record(history, end_date)
        end_price = end_record['close'] if end_record else None
        
        # Calculate Return
        ret_val = None
        if base_price and end_price:
            ret_val = round(((end_price - base_price) / base_price) * 100.0, 2)
            
        results[f"price_{suffix}_after"] = end_price
        results[f"return_{suffix}"] = ret_val
        
        # Calculate Max Drawdown for this period
        # Slice history: from base_record (inclusive) to end_record (inclusive)
        if base_record and end_record:
            # We want prices starting from the base date up to the cut-off date
            period_prices = [
                r['close'] for r in history 
                if base_record['date'] <= r['date'] <= end_record['date']
            ]
            mdd = _calculate_max_drawdown(period_prices)
            results[f"max_drawdown_{suffix}"] = mdd
        else:
            results[f"max_drawdown_{suffix}"] = None

    # Reconstruct row
    new_row = {}
    inserted = False
    target_key = "avg_sale_to_purchase_ratio"
    
    # Fields to insert
    fields_to_add = [
        "price_at_window_end",
        "price_1m_after", "return_1m", "max_drawdown_1m",
        "price_2m_after", "return_2m", "max_drawdown_2m",
        "price_3m_after", "return_3m", "max_drawdown_3m"
    ]
    
    # Prepare values
    values = {
        "price_at_window_end": base_price,
        **results
    }
    
    if target_key not in row:
        new_row = row.copy()
        new_row.update(values)
        return new_row

    for k, v in row.items():
        new_row[k] = v
        if k == target_key:
            for field in fields_to_add:
                new_row[field] = values.get(field)
            inserted = True

    return new_row

def process_file(file_path: Path):
    if not file_path.exists():
        print(f"File not found: {file_path}", file=sys.stderr)
        return

    print(f"Processing {file_path}...")
    try:
        content = file_path.read_text()
        data = json.loads(content)
    except Exception as e:
        print(f"Error reading/parsing JSON: {e}", file=sys.stderr)
        return

    if "rows" not in data:
        print("Invalid JSON format: 'rows' key missing.", file=sys.stderr)
        return

    enriched_rows = []
    total = len(data["rows"])
    for i, row in enumerate(data["rows"], 1):
        print(f"  [{i}/{total}] Enriching {row.get('ticker')}...")
        enriched_rows.append(enrich_row(row))

    data["rows"] = enriched_rows
    
    # Update metadata if exists
    if "metadata" in data:
        data["metadata"]["enriched_at"] = datetime.now().isoformat()

    # Create output path
    output_path = file_path.with_name(f"{file_path.stem}_enriched{file_path.suffix}")
    
    output_path.write_text(json.dumps(data, indent=2, default=str))
    print(f"Done! Enriched data written to: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Enrich cluster JSON with Tiingo prices")
    parser.add_argument("file_path", type=str, help="Path to the JSON file to enrich")
    args = parser.parse_args()

    if not TIINGO_API_KEY:
        print("Error: TIINGO_API_KEY environment variable is not set. Please add it to your .env file.", file=sys.stderr)
        sys.exit(1)

    process_file(Path(args.file_path))

if __name__ == "__main__":
    main()
