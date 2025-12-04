"""
Helpers for generating insider buy signals from loaded Form 3/4/5 data.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy.engine import Engine

from src.config import get_engine

NONDERIV_TABLE = "form345_nonderiv_trans"


def fetch_buy_transactions(engine: Engine | None = None) -> pd.DataFrame:
    """
    Return a DataFrame of buy-side non-derivative transactions.

    Filters on transaction_code of common buy indicators (P = purchase,
    M = conversion of derivative security).
    """
    engine = engine or get_engine()
    query = f"""
        select *
        from {NONDERIV_TABLE}
        where transaction_code in ('P', 'M')
    """
    return pd.read_sql_query(query, engine)


def cluster_buys(df: pd.DataFrame, window_days: int = 14) -> pd.DataFrame:
    """
    Create simple cluster buy signals by grouping insider purchases within a window.

    Expects columns: reporting_owner_cik, issuer_cik, transaction_date.
    """
    working = df.copy()
    working["transaction_date"] = pd.to_datetime(working["transaction_date"])
    working.sort_values(["issuer_cik", "transaction_date"], inplace=True)

    # Group consecutive buys for the same issuer within the specified window.
    working["cluster_id"] = (
        working.groupby("issuer_cik")["transaction_date"]
        .diff()
        .gt(pd.Timedelta(days=window_days))
        .cumsum()
    )

    agg = (
        working.groupby(["issuer_cik", "cluster_id"])
        .agg(
            start_date=("transaction_date", "min"),
            end_date=("transaction_date", "max"),
            filings=("transaction_date", "count"),
            insiders=("reporting_owner_cik", pd.Series.nunique),
        )
        .reset_index(drop=True)
    )
    agg["cluster_span_days"] = (agg["end_date"] - agg["start_date"]).dt.days + 1
    return agg
