"""
Shared cluster detection and CIK-ticker resolution functions.

Extracted from scripts/fast_scan_for_backtest.py and
scripts/fast_enrich_backtest.py to avoid importing from scripts.
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine


def detect_clusters_fast(
    engine: Engine,
    start_date: date,
    end_date: date,
    window_days: int = 10,
    min_insiders: int = 2,
    min_total_value: float = 50000,
) -> list[dict]:
    """
    Detect insider buy clusters using the insider_buy_signals view
    and a fast self-join approach.
    """
    sql = text("""
    WITH buys AS (
        SELECT
            ticker,
            issuer_cik,
            issuer_name,
            insider_cik,
            insider_name,
            insider_title,
            transaction_date AS trade_date,
            filing_date,
            shares,
            total_value
        FROM insider_buy_signals
        WHERE filing_date >= :start_date
          AND filing_date <= :end_date
          AND ticker IS NOT NULL
          AND LENGTH(TRIM(ticker)) > 0
          AND ticker NOT IN ('N/A', 'NA', 'NONE')
          AND shares > 0
          AND total_value > 0
    ),
    insider_daily AS (
        SELECT
            ticker, issuer_cik, MAX(issuer_name) AS issuer_name,
            insider_cik, MAX(insider_name) AS insider_name,
            MAX(insider_title) AS insider_title,
            trade_date, MAX(filing_date) AS filing_date,
            SUM(shares) AS shares, SUM(total_value) AS total_value
        FROM buys
        GROUP BY ticker, issuer_cik, insider_cik, trade_date
    ),
    pairs AS (
        SELECT
            a.ticker,
            a.issuer_cik,
            LEAST(a.trade_date, b.trade_date) AS window_start,
            GREATEST(a.trade_date, b.trade_date) AS window_end,
            GREATEST(a.filing_date, b.filing_date) AS last_filing
        FROM insider_daily a
        JOIN insider_daily b
            ON a.ticker = b.ticker
            AND a.insider_cik < b.insider_cik
            AND ABS(a.trade_date - b.trade_date) <= :window_days
    ),
    windows AS (
        SELECT
            ticker, issuer_cik,
            MIN(window_start) AS window_start,
            MAX(window_end) AS window_end,
            MAX(last_filing) AS signal_filing_date
        FROM pairs
        GROUP BY ticker, issuer_cik,
                 DATE_TRUNC('quarter', window_start)
    )
    SELECT
        w.ticker,
        w.issuer_cik,
        MAX(d.issuer_name) AS issuer_name,
        w.window_start,
        w.window_end,
        w.signal_filing_date,
        w.signal_filing_date + 1 AS entry_date,
        COUNT(DISTINCT d.insider_cik) AS num_insiders,
        COUNT(*) AS num_trades,
        SUM(d.shares) AS total_shares,
        SUM(d.total_value) AS total_value,
        STRING_AGG(
            DISTINCT d.insider_name || COALESCE(' (' || d.insider_title || ')', ''),
            ', '
        ) AS top_insiders
    FROM windows w
    JOIN insider_daily d
        ON d.ticker = w.ticker
        AND d.trade_date BETWEEN w.window_start AND w.window_end
    GROUP BY w.ticker, w.issuer_cik, w.window_start, w.window_end, w.signal_filing_date
    HAVING COUNT(DISTINCT d.insider_cik) >= :min_insiders
       AND SUM(d.total_value) >= :min_total_value
    ORDER BY w.signal_filing_date, w.ticker
    """)

    with engine.connect() as conn:
        rows = conn.execute(sql, {
            "start_date": str(start_date),
            "end_date": str(end_date),
            "window_days": window_days,
            "min_insiders": min_insiders,
            "min_total_value": min_total_value,
        }).fetchall()

    results = []
    for row in rows:
        results.append({
            "ticker": row.ticker,
            "issuer_cik": row.issuer_cik,
            "issuer_name": row.issuer_name,
            "window_start": str(row.window_start),
            "window_end": str(row.window_end),
            "signal_filing_date": str(row.signal_filing_date),
            "entry_date": str(row.entry_date),
            "num_insiders": int(row.num_insiders),
            "num_trades": int(row.num_trades),
            "total_shares": float(row.total_shares),
            "total_value": float(row.total_value),
            "value_per_insider": round(float(row.total_value) / max(int(row.num_insiders), 1), 2),
            "top_insiders": row.top_insiders or "",
        })

    return results


def load_cik_ticker_map(engine: Engine) -> dict[str, str]:
    """Load CIK -> ticker mapping from the database."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT issuer_cik, ticker FROM issuer_cik_ticker_map"
        )).fetchall()
    return {r[0]: r[1] for r in rows}


def resolve_ticker(row: dict, cik_map: dict[str, str]) -> str:
    """Resolve the best ticker for a cluster row. CIK map takes priority."""
    cik = row.get("issuer_cik", "")
    mapped = cik_map.get(cik)
    if mapped:
        return mapped
    return row.get("ticker", "")
