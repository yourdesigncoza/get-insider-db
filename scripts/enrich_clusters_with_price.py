#!/usr/bin/env python
"""
Enrich cluster export JSON with historical price data from Financial Datasets AI.
Adds price at window_end, and 1, 2, 3 months forward, plus returns.
Caches prices in local `market_prices` table to minimize API calls.
Also fetches fundamentals (market cap, EV, PE, PB, PEG) from Financial Datasets AI
and stores them in `market_fundamentals`.
Uses concurrent.futures for parallel fetching.
"""

import argparse
import concurrent.futures
import json
import os
import sys
import time
import threading
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
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

FINANCIAL_DATASETS_API_KEY = os.getenv("FINANCIAL_DATASETS_API_KEY")
FINANCIAL_METRICS_PERIOD = os.getenv("FINANCIAL_METRICS_PERIOD", "quarterly")
FUNDAMENTALS_MAX_LOOKBACK_DAYS = int(os.getenv("FUNDAMENTALS_MAX_LOOKBACK_DAYS", "730"))
FUNDAMENTALS_MAX_FORWARD_DAYS = int(os.getenv("FUNDAMENTALS_MAX_FORWARD_DAYS", "120"))
FINANCIAL_METRICS_MAX_LIMIT = int(os.getenv("FINANCIAL_METRICS_MAX_LIMIT", "200"))
PRICE_LOOKAHEAD_BUFFER_DAYS = int(os.getenv("PRICE_LOOKAHEAD_BUFFER_DAYS", "10"))

# Global Rate Limiting
RATE_LIMIT_SECONDS = 0.0
REQUEST_LOCK = threading.Lock()
LAST_REQUEST_TIME = 0.0

class AlphaVantageError(Exception):
    pass

class InvalidTickerError(Exception):
    pass


@retry(
    stop=stop_after_attempt(3), # Reduced retries for faster failure
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(requests.exceptions.RequestException)
)
def _make_request(url, params):
    global LAST_REQUEST_TIME
    
    if RATE_LIMIT_SECONDS > 0:
        with REQUEST_LOCK:
            now = time.time()
            elapsed = now - LAST_REQUEST_TIME
            if elapsed < RATE_LIMIT_SECONDS:
                sleep_time = RATE_LIMIT_SECONDS - elapsed
                time.sleep(sleep_time)
            LAST_REQUEST_TIME = time.time()
            
    headers = {
        'X-API-KEY': FINANCIAL_DATASETS_API_KEY
    }

    response = requests.get(url, headers=headers, params=params, timeout=10)
    if response.status_code == 429:
        print("Rate limit hit, retrying...", file=sys.stderr)
        response.raise_for_status() # Trigger retry
    
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if response.status_code == 400:
            text_body = response.text or ""
            if any(
                marker in text_body
                for marker in (
                    "Invalid ticker",
                    "Invalid TICKER",
                    "Please provide a valid ticker",
                    "company_tickers.json",
                )
            ):
                raise InvalidTickerError(f"Invalid ticker for provider: {params.get('ticker')}") from e
        print(f"HTTP Error {response.status_code} for URL: {url}", file=sys.stderr)
        print(f"Response: {response.text}", file=sys.stderr)
        raise e
        
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
        
    if rows: 
        print(f"DEBUG: Found {len(rows)} cached prices for {ticker} from DB.", file=sys.stderr)
    else:
        print(f"DEBUG: No cached prices for {ticker} in DB.", file=sys.stderr)
        
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
    2. Fetch missing from Financial Datasets AI.
    3. Save to DB.
    """
    if not FINANCIAL_DATASETS_API_KEY:
        raise ValueError("FINANCIAL_DATASETS_API_KEY not found in environment variables.")

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

        # 2. Fetch from Financial Datasets AI
        
        url = "https://api.financialdatasets.ai/prices/"
        params = {
            'ticker': ticker,
            'interval': 'day',
            'interval_multiplier': 1,
            'start_date': fetch_start.strftime("%Y-%m-%d"),
            'end_date': end_date.strftime("%Y-%m-%d")
        }

        response = _make_request(url, params=params)
        data = response.json()
        
        time_series_data = data.get("prices", [])

        if not time_series_data:
            return db_prices

        cleaned_data = []
        for item in time_series_data:
            # item = {"time": "2024-01-01T00:00:00Z", "close": 150.0, ...}
            # Handle ISO format by taking first 10 chars
            date_str = item["time"][:10]
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            close_val = item.get('close')
            if close_val is not None:
                cleaned_data.append({
                    'date': dt,
                    'close': float(close_val)
                })

        # Filter data to the requested date range after fetching all
        cleaned_data = [d for d in cleaned_data if fetch_start <= d['date'] <= end_date]

        # 3. Save to DB
        _save_prices_to_db(ticker, cleaned_data)

        return sorted(cleaned_data, key=lambda x: x['date'])

    except InvalidTickerError:
        raise
    except Exception as e:
        print(f"Warning: Error fetching history for {ticker}: {e}", file=sys.stderr)
        return []

# -------------------------------------------------------------------------
# FUNDAMENTALS CACHE LOGIC
# -------------------------------------------------------------------------

def _fetch_fundamentals_from_db(ticker: str, target_date: datetime) -> Optional[Dict[str, Any]]:
    """Fetch cached fundamentals for a specific date (closest to target_date)."""
    engine = get_engine()
    # Financial metrics are typically periodic (quarterly/TTM), not daily.
    # Search a wider window around the target date.
    start_search = target_date - timedelta(days=FUNDAMENTALS_MAX_LOOKBACK_DAYS)
    end_search = target_date + timedelta(days=FUNDAMENTALS_MAX_FORWARD_DAYS)
    
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT date, market_cap, enterprise_value, pe_ratio, pb_ratio, trailing_peg_ratio
            FROM market_fundamentals 
            WHERE ticker = :ticker 
              AND date BETWEEN :start AND :end
            ORDER BY date DESC
            LIMIT 40
        """), {
            "ticker": ticker,
            "start": start_search.date(),
            "end": end_search.date(),
        }).fetchall()
        
    if rows:
        candidates: List[Dict[str, Any]] = []
        for row in rows:
            candidates.append(
                {
                    "date": datetime.combine(row[0], datetime.min.time()),
                    "marketCap": float(row[1]) if row[1] else None,
                    "enterpriseVal": float(row[2]) if row[2] else None,
                    "peRatio": float(row[3]) if row[3] else None,
                    "pbRatio": float(row[4]) if row[4] else None,
                    "trailingPegRatio": float(row[5]) if row[5] else None,
                }
            )

        def _completeness_score(r: Dict[str, Any]) -> int:
            return sum(
                1
                for k in ("marketCap", "enterpriseVal", "peRatio", "pbRatio", "trailingPegRatio")
                if r.get(k) is not None
            )

        # Closest in absolute days; prefer <= target_date on ties; then more complete.
        candidates.sort(
            key=lambda r: (
                abs((r["date"].date() - target_date.date()).days),
                0 if r["date"].date() <= target_date.date() else 1,
                -_completeness_score(r),
                r["date"],
            )
        )
        best = candidates[0]
        print(f"DEBUG: Found cached fundamentals for {ticker} from DB.", file=sys.stderr)
        return best
    print(f"DEBUG: No cached fundamentals for {ticker} in DB.", file=sys.stderr)
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
                    ticker, date, market_cap, enterprise_value, pe_ratio, pb_ratio, trailing_peg_ratio
                ) VALUES (
                    :ticker, :date, :mc, :ev, :pe, :pb, :peg
                ) ON CONFLICT (ticker, date) DO NOTHING
            """), {
                "ticker": ticker,
                "date": d["date"].date(),
                "mc": d.get("marketCap"),
                "ev": d.get("enterpriseVal"),
                "pe": d.get("peRatio"),
                "pb": d.get("pbRatio"),
                "peg": d.get("trailingPegRatio"),
            })



def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str) and value.lower() == "none":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def _parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Accept "YYYY-MM-DD" or ISO strings; take first 10 chars if present.
        s = value[:10]
        try:
            return datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            return None
    return None

def _normalize_financial_metrics_record(record: Dict[str, Any], fallback_date: datetime) -> Dict[str, Any]:
    # Support both snake_case (schema) and existing camelCase used elsewhere in this script.
    mc = _parse_float(record.get("market_cap") if "market_cap" in record else record.get("marketCap"))
    ev = _parse_float(
        record.get("enterprise_value")
        if "enterprise_value" in record
        else record.get("enterpriseVal")
    )
    pe = _parse_float(
        record.get("price_to_earnings_ratio")
        if "price_to_earnings_ratio" in record
        else record.get("pe_ratio", record.get("peRatio"))
    )
    pb = _parse_float(
        record.get("price_to_book_ratio")
        if "price_to_book_ratio" in record
        else record.get("pb_ratio", record.get("pbRatio"))
    )
    peg = _parse_float(
        record.get("peg_ratio")
        if "peg_ratio" in record
        else record.get("trailing_peg_ratio", record.get("trailingPegRatio"))
    )

    record_date = (
        _parse_date(record.get("date"))
        or _parse_date(record.get("report_period"))
        or _parse_date(record.get("reportPeriod"))
        or _parse_date(record.get("period_end_date"))
        or _parse_date(record.get("periodEndDate"))
        or fallback_date
    )

    return {
        "date": record_date,
        "marketCap": mc,
        "enterpriseVal": ev,
        "peRatio": pe,
        "pbRatio": pb,
        "trailingPegRatio": peg,
    }

def _fetch_financial_metrics_from_api(ticker: str, period: str, limit: int = 12) -> List[Dict[str, Any]]:
    """
    Fetch valuation/financial metrics from Financial Datasets AI.

    The OpenAPI schema indicates an object response, but some deployments may return
    a list payload. This parser supports both to be resilient.
    """
    url = "https://api.financialdatasets.ai/financial-metrics"
    params = {"ticker": ticker, "period": period, "limit": limit}
    response = _make_request(url, params=params)
    payload = response.json()

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        # Common wrappers we may see.
        for key in ("financial_metrics", "metrics", "data"):
            val = payload.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                return [val]
        # Schema-style object.
        if "market_cap" in payload or "enterprise_value" in payload or "price_to_earnings_ratio" in payload:
            return [payload]

    return []

def _estimate_financial_metrics_limit(target_date: datetime, period: str) -> int:
    """
    Estimate how many records we need to request so the API response likely
    includes `target_date` (which may be years in the past).
    """
    now = datetime.utcnow()
    if target_date >= now:
        return 12

    days_back = (now.date() - target_date.date()).days
    if period == "annual":
        est = int(days_back / 365.25) + 3
    else:
        # quarterly + ttm are effectively "many-per-year" endpoints; over-fetch a bit.
        est = int((days_back / 365.25) * 4) + 8

    est = max(12, est)
    return min(est, FINANCIAL_METRICS_MAX_LIMIT)

def _get_fundamental_at_date(ticker: str, target_date: datetime, price_at_date: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """
    Get fundamentals for a specific date.
    1. Check DB.
    2. If missing, fetch from Financial Datasets AI financial metrics.
    3. Save & Return.
    """
    try:
        # 1. Try DB
        cached = _fetch_fundamentals_from_db(ticker, target_date)
        if cached:
            return cached
            
        # 2. Fetch from Financial Datasets AI
        # We only care about the metric record closest to window_end (target_date), so:
        # - fetch a small recent window from the API
        # - choose the closest record <= target_date
        # - store only that record in DB (avoid loading years of history)
        min_allowed_date = target_date - timedelta(days=FUNDAMENTALS_MAX_LOOKBACK_DAYS)
        max_allowed_date = target_date + timedelta(days=FUNDAMENTALS_MAX_FORWARD_DAYS)
        estimated_limit = _estimate_financial_metrics_limit(target_date, FINANCIAL_METRICS_PERIOD)
        limits_to_try = []
        for lim in (12, 40, estimated_limit, 80, 120, FINANCIAL_METRICS_MAX_LIMIT):
            if lim and lim not in limits_to_try:
                limits_to_try.append(lim)

        last_records_count = 0
        candidates: List[Dict[str, Any]] = []
        for lim in limits_to_try:
            try:
                records = _fetch_financial_metrics_from_api(ticker, FINANCIAL_METRICS_PERIOD, limit=lim)
            except Exception as e:
                print(f"Error fetching Financial Datasets AI financial metrics for {ticker}: {e}", file=sys.stderr)
                continue

            if not records:
                continue

            last_records_count = len(records)
            normalized = [_normalize_financial_metrics_record(r, fallback_date=target_date) for r in records]

            candidates = []
            for r in normalized:
                if not (min_allowed_date <= r["date"] <= max_allowed_date):
                    continue
                # Skip records with no useful values (API can return skeleton rows).
                if all(
                    r.get(k) is None
                    for k in ("marketCap", "enterpriseVal", "peRatio", "pbRatio", "trailingPegRatio")
                ):
                    continue
                candidates.append(r)

            if candidates:
                break

            if lim < FINANCIAL_METRICS_MAX_LIMIT:
                print(
                    f"DEBUG: Fundamentals returned {last_records_count} records for {ticker} but none near window_end "
                    f"(window_end={target_date.date()}); retrying with larger limit...",
                    file=sys.stderr,
                )

        if not last_records_count:
            print(f"DEBUG: No fundamentals records returned for {ticker} from API.", file=sys.stderr)
            return None

        if not candidates:
            print(
                f"DEBUG: Fundamentals returned but no usable record near window_end for {ticker} "
                f"(window_end={target_date.date()}, lookback_days={FUNDAMENTALS_MAX_LOOKBACK_DAYS}, forward_days={FUNDAMENTALS_MAX_FORWARD_DAYS}).",
                file=sys.stderr,
            )
            return None

        def _completeness_score(r: Dict[str, Any]) -> int:
            return sum(
                1
                for k in ("marketCap", "enterpriseVal", "peRatio", "pbRatio", "trailingPegRatio")
                if r.get(k) is not None
            )

        # Closest in absolute days; prefer <= target_date on ties; then more complete.
        candidates.sort(
            key=lambda r: (
                abs((r["date"].date() - target_date.date()).days),
                0 if r["date"].date() <= target_date.date() else 1,
                -_completeness_score(r),
                r["date"],
            )
        )
        best = candidates[0]
        if best["date"].date() > target_date.date():
            print(
                f"DEBUG: Using next-period fundamentals for {ticker}: {best['date'].date()} (window_end={target_date.date()}).",
                file=sys.stderr,
            )

        _save_fundamentals_to_db(ticker, [best])
        return best

    except InvalidTickerError:
        raise
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

def _get_first_price_record_on_or_after(history: List[Dict], target_date: datetime) -> Optional[Dict]:
    for record in history:
        if record["date"] >= target_date:
            return record
    return None

def enrich_row(row: Dict[str, Any]) -> Dict[str, Any]:
    ticker = row.get("ticker")
    window_end_str = row.get("window_end")
    total_value = row.get("total_value", 0)
    
    if not ticker or not window_end_str:
        return row

    try:
        window_end_date = datetime.strptime(window_end_str, "%Y-%m-%d")
    except ValueError:
        return row

    # Lookahead-safe backtest anchor:
    # - Prefer cluster_buys-provided entry_date (day after the last filing_date in the cluster).
    # - Otherwise fall back to day after window_end.
    entry_date_str = row.get("entry_date")
    filing_date_str = row.get("signal_filing_date")
    try:
        if entry_date_str:
            entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d")
        elif filing_date_str:
            entry_date = datetime.strptime(filing_date_str, "%Y-%m-%d") + timedelta(days=1)
        else:
            entry_date = window_end_date + timedelta(days=1)
    except ValueError:
        entry_date = window_end_date + timedelta(days=1)

    date_1m = entry_date + relativedelta(months=1)
    date_2m = entry_date + relativedelta(months=2)
    date_3m = entry_date + relativedelta(months=3)
    # `date_1m/2m/3m` can land on weekends/holidays; fetch a little extra so
    # "_on_or_after" lookup can find the next trading day.
    price_fetch_end = date_3m + timedelta(days=PRICE_LOOKAHEAD_BUFFER_DAYS)
    
    # ---------------------------------------------------------
    # PARALLEL FETCHING
    # ---------------------------------------------------------
    history = []
    fund_data = None
    
    # We fetch prices FIRST because YFinance fallback might need the base price
    # So we can't fully parallelize the dependency chain if we want that robust fallback.
    # But we can still fetch standard Alpha Vantage fundamentals in parallel.
    
    # Revised flow:
    # 1. Fetch Prices (Blocking or Async)
    # 2. Extract Base Price
    # 3. Fetch Fundamentals (passing base price for YF fallback)
    
    # To keep parallel speed for the main API calls:
    # We can fetch Alpha Vantage Fundamentals in parallel with Prices.
    # If Alpha Vantage Funds fails, THEN we do YF (sequentially).
    
    enrichment_status = "ok"
    enrichment_errors: List[str] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_prices = executor.submit(_get_price_history, ticker, entry_date, price_fetch_end)
        # We don't pass price_at_date here yet, effectively disabling YF inside this parallel call if Tiingo fails
        # We will handle YF fallback explicitly after if needed.
        future_fundamentals = executor.submit(_get_fundamental_at_date, ticker, entry_date, None)
        
        try:
            history = future_prices.result()
        except InvalidTickerError as e:
            enrichment_status = "unsupported_ticker"
            enrichment_errors.append(f"prices: {e}")
        except Exception as e:
            enrichment_status = "error"
            enrichment_errors.append(f"prices: {e}")
            print(f"Price fetch fatal error for {ticker}: {e}", file=sys.stderr)
        
        try:
            fund_data = future_fundamentals.result()
        except InvalidTickerError as e:
            if enrichment_status == "ok":
                enrichment_status = "unsupported_ticker"
            enrichment_errors.append(f"fundamentals: {e}")
        except Exception as e:
            if enrichment_status == "ok":
                enrichment_status = "partial"
            enrichment_errors.append(f"fundamentals: {e}")

    # --- PRICE ENRICHMENT ---
    base_record = _get_first_price_record_on_or_after(history, entry_date)
    base_price = base_record['close'] if base_record else None

    if enrichment_status == "ok" and not history:
        enrichment_status = "no_price_data"
    
    results = {}
    
    for suffix, end_date in [("1m", date_1m), ("2m", date_2m), ("3m", date_3m)]:
        end_record = _get_first_price_record_on_or_after(history, end_date)
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


    market_cap = fund_data.get("marketCap") if fund_data else None
    enterprise_value = fund_data.get("enterpriseVal") if fund_data else None
    pe_ratio = fund_data.get("peRatio") if fund_data else None
    pb_ratio = fund_data.get("pbRatio") if fund_data else None
    trailing_peg_ratio = fund_data.get("trailingPegRatio") if fund_data else None
    
    cluster_vs_mcap_pct = None
    if market_cap and total_value and market_cap > 0:
        cluster_vs_mcap_pct = round((total_value / market_cap) * 100.0, 4)

    new_row = row.copy()
    new_row.update({
        "enrichment_status": enrichment_status,
        "enrichment_errors": enrichment_errors,
        "price_at_entry": base_price,
        "market_cap_at_entry": market_cap,
        "enterprise_value_at_entry": enterprise_value,
        "pe_ratio_at_entry": pe_ratio,
        "pb_ratio_at_entry": pb_ratio,
        "trailing_peg_ratio_at_entry": trailing_peg_ratio,
        # Backward-compatible aliases (historically used for entry-next-day pricing).
        "price_at_window_end": base_price,
        "market_cap_at_window_end": market_cap,
        "enterprise_value_at_window_end": enterprise_value,
        "pe_ratio_at_window_end": pe_ratio,
        "pb_ratio_at_window_end": pb_ratio,
        "trailing_peg_ratio_at_window_end": trailing_peg_ratio,
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
    global RATE_LIMIT_SECONDS
    parser = argparse.ArgumentParser(description="Enrich cluster JSON with Tiingo prices and fundamentals")
    parser.add_argument("file_path", type=str, help="Path to the JSON file to enrich")
    parser.add_argument("--rate_limit", type=float, default=1.0, help="Minimum seconds between API calls (e.g. 2.0 for free tier)")
    args = parser.parse_args()

    if args.rate_limit > 0:
        RATE_LIMIT_SECONDS = args.rate_limit
        print(f"Rate limiting enabled: {RATE_LIMIT_SECONDS}s between calls.")

    if not FINANCIAL_DATASETS_API_KEY:
        print("Error: FINANCIAL_DATASETS_API_KEY environment variable is not set. Please add it to your .env file.", file=sys.stderr)
        sys.exit(1)

    process_file(Path(args.file_path))

if __name__ == "__main__":
    main()
