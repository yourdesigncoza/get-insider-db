#!/usr/bin/env python
"""
Enrich cluster export JSON with historical price data from Tiingo.
Adds price at window_end, and 1, 2, 3 months forward, plus returns.
Caches prices in local `market_prices` table to minimize API calls.
Also fetches Market Cap to calculate Relative Conviction.
Uses concurrent.futures for parallel fetching.
Includes yfinance fallback for Market Cap.
"""

import argparse
import concurrent.futures
import json
import os
import sys
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
import yfinance as yf
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Import project config
# Ensure root is in pythonpath if running as script
sys.path.append(os.getcwd())
from src.config import get_engine

# Load environment variables
load_dotenv()

TIINGO_API_KEY = os.getenv("TIINGO_API_KEY")

class TiingoError(Exception):
    pass


@retry(
    stop=stop_after_attempt(3), # Reduced retries for faster failure
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(requests.exceptions.RequestException)
)
def _make_request(url, headers, params):
    response = requests.get(url, headers=headers, params=params, timeout=10)
    if response.status_code == 429:
        print("Rate limit hit, retrying...", file=sys.stderr)
        response.raise_for_status() # Trigger retry
    response.raise_for_status()
    return response

# -------------------------------------------------------------------------
# PRICE CACHE LOGIC
# -------------------------------------------------------------------------

def _fetch_prices_from_db(ticker: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    """Fetch cached prices from DB."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT price_date, close_price 
            FROM market_prices 
            WHERE ticker = :ticker 
              AND price_date BETWEEN :start AND :end
            ORDER BY price_date
        """), {
            "ticker": ticker,
            "start": start_date.date(),
            "end": end_date.date()
        }).fetchall()
        
    return [{"date": datetime.combine(row[0], datetime.min.time()), "close": float(row[1])} for row in rows]

def _save_prices_to_db(ticker: str, prices: List[Dict[str, Any]]):
    """Batch insert prices into DB."""
    if not prices:
        return
        
    engine = get_engine()
    with engine.begin() as conn:
        for p in prices:
            conn.execute(text("""
                INSERT INTO market_prices (ticker, price_date, close_price)
                VALUES (:ticker, :date, :price)
                ON CONFLICT (ticker, price_date) DO NOTHING
            """), {
                "ticker": ticker,
                "date": p["date"].date(),
                "price": p["close"]
            })

@lru_cache(maxsize=1024)
def _get_price_history(ticker: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    """
    Fetch daily price history.
    1. Check DB.
    2. Fetch missing from Tiingo.
    3. Save to DB.
    """
    if not TIINGO_API_KEY:
        raise ValueError("TIINGO_API_KEY not found in environment variables.")

    try:
        # 1. Try DB
        # Look back 7 days to ensure we capture the start date price if it falls on a weekend
        fetch_start = start_date - timedelta(days=7)
        db_prices = _fetch_prices_from_db(ticker, fetch_start, end_date)
        
        days_needed = (end_date - start_date).days
        
        # Heuristic for missing data
        needs_fetch = False
        if days_needed > 5:
            if len(db_prices) == 0:
                needs_fetch = True
            elif len(db_prices) < (days_needed * 0.5):
                needs_fetch = True
            else:
                 # Check edges
                first_db = db_prices[0]['date']
                last_db = db_prices[-1]['date']
                if first_db > (start_date + timedelta(days=7)):
                    needs_fetch = True
                if last_db < (end_date - timedelta(days=7)):
                     needs_fetch = True
        elif not db_prices and days_needed > 0:
             needs_fetch = True

        if not needs_fetch:
            return db_prices

        # 2. Fetch from Tiingo
        # fetch_start is already calculated above
        
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

        response = _make_request(url, headers, params)
        data = response.json()
        
        if not data:
            return db_prices
            
        cleaned_data = []
        for record in data:
            d_str = record['date'].rstrip('Z')
            if '.' in d_str:
                d_str = d_str.split('.')[0]
            dt = datetime.strptime(d_str, "%Y-%m-%dT%H:%M:%S")
            cleaned_data.append({
                'date': dt,
                'close': float(record['close'])
            })
            
        # 3. Save to DB
        _save_prices_to_db(ticker, cleaned_data)
        
        return sorted(cleaned_data, key=lambda x: x['date'])

    except Exception as e:
        print(f"Warning: Error fetching history for {ticker}: {e}", file=sys.stderr)
        return []

# -------------------------------------------------------------------------
# FUNDAMENTALS CACHE LOGIC
# -------------------------------------------------------------------------

def _fetch_fundamentals_from_db(ticker: str, target_date: datetime) -> Optional[Dict[str, Any]]:
    """Fetch cached fundamentals for a specific date (or closest before)."""
    engine = get_engine()
    start_search = target_date - timedelta(days=10)
    
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT date, market_cap, enterprise_value, pe_ratio, pb_ratio
            FROM market_fundamentals 
            WHERE ticker = :ticker 
              AND date BETWEEN :start AND :target
            ORDER BY date DESC
            LIMIT 1
        """), {
            "ticker": ticker,
            "start": start_search.date(),
            "target": target_date.date()
        }).fetchone()
        
    if row:
        return {
            "date": datetime.combine(row[0], datetime.min.time()),
            "marketCap": float(row[1]) if row[1] else None,
            "enterpriseVal": float(row[2]) if row[2] else None,
            "peRatio": float(row[3]) if row[3] else None,
            "pbRatio": float(row[4]) if row[4] else None
        }
    return None

def _save_fundamentals_to_db(ticker: str, data: List[Dict[str, Any]]):
    """Batch insert fundamentals."""
    if not data:
        return
    
    engine = get_engine()
    with engine.begin() as conn:
        for d in data:
            conn.execute(text("""
                INSERT INTO market_fundamentals (
                    ticker, date, market_cap, enterprise_value, pe_ratio, pb_ratio
                ) VALUES (
                    :ticker, :date, :mc, :ev, :pe, :pb
                ) ON CONFLICT (ticker, date) DO NOTHING
            """), {
                "ticker": ticker,
                "date": d["date"].date(),
                "mc": d.get("marketCap"),
                "ev": d.get("enterpriseVal"),
                "pe": d.get("peRatio"),
                "pb": d.get("pbRatio")
            })

def _fetch_fundamentals_yfinance(ticker: str, price_at_date: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """
    Fallback: fetch current shares outstanding from Yahoo Finance 
    and calc Market Cap based on historical price.
    """
    try:
        t = yf.Ticker(ticker)
        # Suppress prints from yfinance (it can be chatty)
        # Note: yfinance fetching is blocking and can be slow.
        info = t.info
        
        shares = info.get("sharesOutstanding")
        
        if not shares:
            # Try implied shares from MarketCap / Price?
            curr_mcap = info.get("marketCap")
            curr_price = info.get("currentPrice") or info.get("regularMarketPreviousClose")
            if curr_mcap and curr_price:
                shares = curr_mcap / curr_price
        
        if not shares:
            return None
            
        # Calculate Historical Market Cap Proxy
        # If we have the historical price, use it.
        # If not, we can't really give a historical mcap, but we can return current as a worst-case fallback?
        # No, better to be strict for "Backtest" logic, but lax for "Ranking".
        
        mcap = None
        if price_at_date:
            mcap = shares * price_at_date
        else:
            mcap = info.get("marketCap") # Fallback to current
            
        return {
            "date": datetime.now(), # It's "current" metadata applied historically
            "marketCap": mcap,
            "enterpriseVal": info.get("enterpriseValue"),
            "peRatio": info.get("trailingPE"),
            "pbRatio": info.get("priceToBook")
        }
    except Exception:
        return None

def _get_fundamental_at_date(ticker: str, target_date: datetime, price_at_date: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """
    Get fundamentals for a specific date.
    1. Check DB.
    2. If missing, fetch window from Tiingo.
    3. If Tiingo fails, try YFinance fallback.
    4. Save & Return.
    """
    try:
        # 1. Try DB
        cached = _fetch_fundamentals_from_db(ticker, target_date)
        if cached:
            return cached
            
        # 2. Fetch from Tiingo
        fetch_start = target_date - timedelta(days=10)
        fetch_end = target_date 
        
        url = f"https://api.tiingo.com/tiingo/fundamentals/{ticker}/daily"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Token {TIINGO_API_KEY}'
        }
        params = {
            'startDate': fetch_start.strftime('%Y-%m-%d'),
            'endDate': fetch_end.strftime('%Y-%m-%d')
        }
        
        data = None
        tiingo_failed = False
        
        try:
            response = _make_request(url, headers, params)
            data = response.json()
        except Exception:
            tiingo_failed = True
        
        if not data:
            tiingo_failed = True
            
        if not tiingo_failed:
            cleaned_data = []
            for record in data:
                d_str = record['date'].rstrip('Z')
                if '.' in d_str:
                    d_str = d_str.split('.')[0]
                dt = datetime.strptime(d_str, "%Y-%m-%dT%H:%M:%S")
                cleaned_data.append({
                    "date": dt,
                    "marketCap": record.get("marketCap"),
                    "enterpriseVal": record.get("enterpriseVal"),
                    "peRatio": record.get("peRatio"),
                    "pbRatio": record.get("pbRatio")
                })
                
            # Save Tiingo data
            _save_fundamentals_to_db(ticker, cleaned_data)
            
            cleaned_data.sort(key=lambda x: x['date'], reverse=True)
            return cleaned_data[0] if cleaned_data else None

        # 3. Fallback to YFinance
        # Only if Tiingo failed or returned no data
        yf_data = _fetch_fundamentals_yfinance(ticker, price_at_date)
        if yf_data:
            # We don't save YF data to DB as 'market_fundamentals' because it's a proxy/hybrid
            # and might mess up the purity of the cache. We just return it.
            # Or we could save it with a flag? For now, just return.
            return yf_data
            
        return None

    except Exception as e:
        print(f"Error in fundamental logic for {ticker}: {e}", file=sys.stderr)
        return None

# -------------------------------------------------------------------------
# CALCS & ENRICHMENT
# -------------------------------------------------------------------------

def _calculate_max_drawdown(prices: List[float], base_price: float) -> Optional[float]:
    if not prices or base_price is None or base_price == 0:
        return None
    min_price = min(prices)
    if min_price >= base_price:
        return 0.0
    drawdown = (min_price - base_price) / base_price
    return round(drawdown * 100.0, 2)

def _get_closest_price_record(history: List[Dict], target_date: datetime) -> Optional[Dict]:
    candidate = None
    for record in history:
        if record['date'] <= target_date:
            candidate = record
        else:
            break
    return candidate

def enrich_row(row: Dict[str, Any]) -> Dict[str, Any]:
    ticker = row.get("ticker")
    window_end_str = row.get("window_end")
    total_value = row.get("total_value", 0)
    
    if not ticker or not window_end_str:
        return row

    try:
        window_end_date = datetime.strptime(window_end_str, "%Y-%m-%d")
        trading_start_date = window_end_date + timedelta(days=1)
    except ValueError:
        return row

    date_1m = window_end_date + relativedelta(months=1)
    date_2m = window_end_date + relativedelta(months=2)
    date_3m = window_end_date + relativedelta(months=3)
    
    # ---------------------------------------------------------
    # PARALLEL FETCHING
    # ---------------------------------------------------------
    history = []
    fund_data = None
    
    # We fetch prices FIRST because YFinance fallback might need the base price
    # So we can't fully parallelize the dependency chain if we want that robust fallback.
    # But we can still fetch standard Tiingo fundamentals in parallel.
    
    # Revised flow:
    # 1. Fetch Prices (Blocking or Async)
    # 2. Extract Base Price
    # 3. Fetch Fundamentals (passing base price for YF fallback)
    
    # To keep parallel speed for the main API calls:
    # We can fetch Tiingo Fundamentals in parallel with Prices.
    # If Tiingo Funds fails, THEN we do YF (sequentially).
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_prices = executor.submit(_get_price_history, ticker, trading_start_date, date_3m)
        # We don't pass price_at_date here yet, effectively disabling YF inside this parallel call if Tiingo fails
        # We will handle YF fallback explicitly after if needed.
        future_fundamentals = executor.submit(_get_fundamental_at_date, ticker, window_end_date, None)
        
        try:
            history = future_prices.result()
        except Exception as e:
             print(f"Price fetch fatal error for {ticker}: {e}", file=sys.stderr)
        
        try:
            fund_data = future_fundamentals.result()
        except Exception:
            pass

    # --- PRICE ENRICHMENT ---
    base_record = _get_closest_price_record(history, trading_start_date)
    base_price = base_record['close'] if base_record else None
    
    results = {}
    
    for suffix, end_date in [("1m", date_1m), ("2m", date_2m), ("3m", date_3m)]:
        end_record = _get_closest_price_record(history, end_date)
        end_price = end_record['close'] if end_record else None
        
        ret_val = None
        if base_price and end_price:
            ret_val = round(((end_price - base_price) / base_price) * 100.0, 2)
            
        results[f"price_{suffix}_after"] = end_price
        results[f"return_{suffix}"] = ret_val
        
        if base_record and end_record:
            period_prices = [
                r['close'] for r in history 
                if base_record['date'] <= r['date'] <= end_record['date']
            ]
            mdd = _calculate_max_drawdown(period_prices, base_price)
            results[f"max_drawdown_{suffix}"] = mdd
        else:
            results[f"max_drawdown_{suffix}"] = None

    # --- FUNDAMENTALS ENRICHMENT (Fallback Check) ---
    if not fund_data and base_price:
        # Tiingo failed, but we have a price. Try YFinance now.
        fund_data = _fetch_fundamentals_yfinance(ticker, base_price)

    market_cap = fund_data.get("marketCap") if fund_data else None
    
    cluster_vs_mcap_pct = None
    if market_cap and total_value and market_cap > 0:
        cluster_vs_mcap_pct = round((total_value / market_cap) * 100.0, 4)

    new_row = row.copy()
    new_row.update({
        "price_at_window_end": base_price,
        "market_cap_at_window_end": market_cap,
        "cluster_value_vs_mcap_pct": cluster_vs_mcap_pct,
        **results
    })
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
    
    if "metadata" in data:
        data["metadata"]["enriched_at"] = datetime.now().isoformat()

    output_path = file_path.with_name(f"{file_path.stem}_enriched{file_path.suffix}")
    output_path.write_text(json.dumps(data, indent=2, default=str))
    print(f"Done! Enriched data written to: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Enrich cluster JSON with Tiingo prices and fundamentals")
    parser.add_argument("file_path", type=str, help="Path to the JSON file to enrich")
    args = parser.parse_args()

    if not TIINGO_API_KEY:
        print("Error: TIINGO_API_KEY environment variable is not set. Please add it to your .env file.", file=sys.stderr)
        sys.exit(1)

    process_file(Path(args.file_path))

if __name__ == "__main__":
    main()