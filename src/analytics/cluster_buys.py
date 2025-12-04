from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.config import DATABASE_URL


@dataclass
class ClusterBuyEvent:
    ticker: str
    window_start: date
    window_end: date
    num_trades: int
    num_insiders: int
    total_shares: float
    total_value: float
    top_insiders: list[str]


def _get_engine() -> Engine:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set; configure it in .env")
    try:
        return create_engine(DATABASE_URL)
    except Exception as exc:  # pragma: no cover - passthrough for clarity
        raise RuntimeError(f"Failed to create engine for DATABASE_URL: {exc}") from exc


def get_latest_filing_date() -> date:
    engine = _get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT MAX(filing_date) AS latest FROM insider_buy_signals;"))
        latest = result.scalar()
    if latest is None:
        raise RuntimeError("insider_buy_signals is empty; cannot determine latest filing date")
    return latest


def find_cluster_buys(
    window_days: int = 10,
    lookback_days: int = 90,
    min_insiders: int = 2,
    min_total_value: float = 0.0,
    min_trade_value: float = 0.0,
    ticker: Optional[str] = None,
    use_exclusions: bool = True,
) -> pd.DataFrame:
    latest_date = get_latest_filing_date()
    start_date = latest_date - timedelta(days=lookback_days)

    engine = _get_engine()
    window_interval = window_days - 1

    ticker_filter = "AND s.ticker = :ticker" if ticker else ""
    value_filter = "AND COALESCE(total_value, 0) >= :min_trade_value" if min_trade_value else ""
    exclusions_clause = """
              AND NOT EXISTS (
                  SELECT 1
                  FROM insider_exclusions e
                  WHERE e.active
                    AND s.insider_name ILIKE ('%' || e.pattern || '%')
              )
    """ if use_exclusions else ""
    query = f"""
        WITH base AS (
            SELECT s.*
            FROM insider_buy_signals s
            WHERE s.transaction_date BETWEEN :start_date AND :end_date
              AND s.ticker IS NOT NULL
              AND s.ticker <> 'NONE'
              {value_filter}
              {exclusions_clause}
            {ticker_filter}
        ),
        computed AS (
            SELECT
                b.ticker,
                (b.transaction_date - INTERVAL '{window_interval} day')::date AS window_start,
                b.transaction_date::date AS window_end,
                (
                    SELECT COUNT(*)
                    FROM base b2
                    WHERE b2.ticker = b.ticker
                      AND b2.transaction_date BETWEEN b.transaction_date - INTERVAL '{window_interval} day' AND b.transaction_date
                ) AS num_trades,
                (
                    SELECT COUNT(DISTINCT b2.insider_name)
                    FROM base b2
                    WHERE b2.ticker = b.ticker
                      AND b2.transaction_date BETWEEN b.transaction_date - INTERVAL '{window_interval} day' AND b.transaction_date
                ) AS num_insiders,
                (
                    SELECT SUM(b2.shares)
                    FROM base b2
                    WHERE b2.ticker = b.ticker
                      AND b2.transaction_date BETWEEN b.transaction_date - INTERVAL '{window_interval} day' AND b.transaction_date
                ) AS total_shares,
                (
                    SELECT SUM(b2.total_value)
                    FROM base b2
                    WHERE b2.ticker = b.ticker
                      AND b2.transaction_date BETWEEN b.transaction_date - INTERVAL '{window_interval} day' AND b.transaction_date
                ) AS total_value,
                (
                    SELECT string_agg(insider_name, ', ' ORDER BY sum_total_value DESC)
                    FROM (
                        SELECT insider_name, SUM(total_value) AS sum_total_value
                        FROM base b3
                        WHERE b3.ticker = b.ticker
                          AND b3.transaction_date BETWEEN b.transaction_date - INTERVAL '{window_interval} day' AND b.transaction_date
                        GROUP BY insider_name
                        ORDER BY sum_total_value DESC
                        LIMIT 3
                    ) top3
                ) AS top_insiders,
                b.transaction_date
            FROM base b
        ),
        filtered AS (
            SELECT *
            FROM computed
            WHERE num_insiders >= :min_insiders
              AND total_value >= :min_total_value
        )
        SELECT DISTINCT ON (ticker, window_start, window_end)
            ticker,
            window_start,
            window_end,
            num_trades,
            num_insiders,
            total_shares,
            total_value,
            COALESCE(top_insiders, '') AS top_insiders
        FROM filtered
        ORDER BY ticker, window_start, window_end, transaction_date DESC;
    """

    params = {
        "start_date": start_date,
        "end_date": latest_date,
        "min_insiders": min_insiders,
        "min_total_value": min_total_value,
        "min_trade_value": min_trade_value,
    }
    if ticker:
        params["ticker"] = ticker

    df = pd.read_sql_query(text(query), engine, params=params)

    # Ensure correct types.
    for col in ("window_start", "window_end"):
        if col in df:
            df[col] = pd.to_datetime(df[col]).dt.date
    if "top_insiders" in df:
        df["top_insiders"] = df["top_insiders"].fillna("")

    if df.empty:
        return df

    # Fetch base transactions to recompute metrics for merged windows.
    base_ticker_filter = "AND ticker = :ticker" if ticker else ""
    base_value_filter = "AND COALESCE(total_value, 0) >= :min_trade_value" if min_trade_value else ""
    base_exclusions = """
          AND NOT EXISTS (
              SELECT 1
              FROM insider_exclusions e
              WHERE e.active
                AND insider_name ILIKE ('%' || e.pattern || '%')
          )
    """ if use_exclusions else ""
    base_sql = f"""
        SELECT ticker, transaction_date, insider_name, shares, total_value
        FROM insider_buy_signals
        WHERE transaction_date BETWEEN :start_date AND :end_date
          AND ticker IS NOT NULL
          AND ticker <> 'NONE'
          {base_value_filter}
          {base_exclusions}
        {base_ticker_filter}
    """
    base_params = params.copy()
    base_params["min_trade_value"] = min_trade_value
    base_df = pd.read_sql_query(text(base_sql), engine, params=base_params)
    if base_df.empty:
        return pd.DataFrame(columns=df.columns)

    base_df["transaction_date"] = pd.to_datetime(base_df["transaction_date"]).dt.date
    base_df["shares"] = pd.to_numeric(base_df["shares"], errors="coerce").fillna(0.0)
    base_df["total_value"] = pd.to_numeric(base_df["total_value"], errors="coerce").fillna(0.0)

    merged_records = []
    for ticker_value, tdf in df.groupby("ticker"):
        intervals = sorted(zip(tdf["window_start"], tdf["window_end"]), key=lambda x: x[0])
        merged_intervals: list[tuple[date, date]] = []
        for start, end in intervals:
            if not merged_intervals:
                merged_intervals.append((start, end))
                continue
            last_start, last_end = merged_intervals[-1]
            if start <= last_end:  # overlap condition
                merged_intervals[-1] = (last_start, max(last_end, end))
            else:
                merged_intervals.append((start, end))

        ticker_rows = base_df[base_df["ticker"] == ticker_value]
        for start, end in merged_intervals:
            subset = ticker_rows[
                (ticker_rows["transaction_date"] >= start) & (ticker_rows["transaction_date"] <= end)
            ]
            if subset.empty:
                continue
            num_trades = len(subset)
            num_insiders = subset["insider_name"].nunique()
            total_shares = subset["shares"].sum()
            total_value = subset["total_value"].sum()
            top_series = (
                subset.groupby("insider_name")["total_value"]
                .sum()
                .sort_values(ascending=False)
                .head(3)
            )
            top_insiders = ", ".join(top_series.index)
            merged_records.append(
                {
                    "ticker": ticker_value,
                    "window_start": start,
                    "window_end": end,
                    "num_trades": int(num_trades),
                    "num_insiders": int(num_insiders),
                    "total_shares": float(total_shares),
                    "total_value": float(total_value),
                    "top_insiders": top_insiders,
                }
            )

    if not merged_records:
        return pd.DataFrame(columns=df.columns)

    merged_df = pd.DataFrame(merged_records)
    merged_df = merged_df.sort_values("total_value", ascending=False).reset_index(drop=True)
    return merged_df


def get_top_cluster_buys(
    limit: int = 20,
    **kwargs,
) -> pd.DataFrame:
    """
    Convenience wrapper around find_cluster_buys(...).

    Returns the top N cluster events ordered by total_value desc,
    with sensible defaults.
    """
    df = find_cluster_buys(**kwargs)
    if df.empty:
        return df
    return df.sort_values("total_value", ascending=False).head(limit).reset_index(drop=True)
