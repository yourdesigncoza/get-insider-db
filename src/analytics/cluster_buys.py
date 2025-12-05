from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.config import DATABASE_URL, get_engine
from src.cluster_scoring import compute_cluster_score
from src.insider_classification import get_or_create_insider_entity, normalize_insider_name
from src.insider_roles import compute_insider_role_weight


def _first_nonempty(series: pd.Series) -> str:
    """
    Helper for groupby aggregations to pull the first non-blank string.
    """
    for value in series:
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                return trimmed
    return ""


def _format_insider_label(
    name: str, relationship: str | None, title: str | None
) -> str:
    rel = (relationship or "").strip()
    role = (title or "").strip()

    if rel.lower() == "officer":
        descriptor = f"Officer, {role}" if role else "Officer"
    elif rel and role:
        descriptor = f"{rel}, {role}"
    else:
        descriptor = rel or role

    return f"{name} ({descriptor})" if descriptor else name


def _flag_value(value: object) -> bool:
    """
    Normalize truthy values that may arrive as strings/ints/bools.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def _derive_flags(row: pd.Series) -> Dict[str, bool]:
    """
    Derive insider flags from row metadata.
    """
    relationship = str(row.get("insider_relationship", "") or "").lower()
    return {
        "is_director": _flag_value(row.get("is_director")) or "director" in relationship,
        "is_officer": _flag_value(row.get("is_officer")) or "officer" in relationship,
        "is_ten_percent_owner": _flag_value(row.get("is_ten_percent_owner"))
        or "ten percent" in relationship
        or "10%" in relationship,
        "is_other": _flag_value(row.get("is_other")) or "other" in relationship,
    }


def _classify_insiders(base_df: pd.DataFrame, engine: Engine) -> Dict[str, Dict[str, Any]]:
    """
    Ensure each normalized insider name has a cached classification in the DB.
    Returns a map of normalized_name -> InsiderEntity.
    """
    if base_df.empty or "normalized_name" not in base_df:
        return {}

    unique_rows = base_df.drop_duplicates(subset=["normalized_name"])
    classifications: Dict[str, Dict[str, Any]] = {}
    with Session(bind=engine, expire_on_commit=False) as session:
        for _, row in unique_rows.iterrows():
            normalized = row.get("normalized_name") or ""
            if not normalized:
                continue
            flags = _derive_flags(row)
            insider_id = None
            if "insider_cik" in row and pd.notna(row.get("insider_cik")):
                insider_id = str(row.get("insider_cik"))
            entity = get_or_create_insider_entity(
                session=session,
                insider_name=row.get("insider_name", normalized),
                officer_title=row.get("insider_title"),
                flags=flags,
                insider_id=insider_id,
            )
            classifications[normalized] = {
                "is_fund_like": bool(entity.is_fund_like),
                "entity_type": entity.entity_type,
            }
    return classifications


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
        return get_engine()
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
    min_role_score: int = 0,
    min_people: Optional[int] = None,
    max_fund_ratio: Optional[float] = None,
    min_cluster_score: Optional[float] = None,
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
                    SELECT string_agg(
                        CASE
                            WHEN LOWER(COALESCE(insider_relationship, '')) = 'officer' AND COALESCE(insider_title, '') <> ''
                                THEN insider_name || ' (Officer, ' || insider_title || ')'
                            WHEN LOWER(COALESCE(insider_relationship, '')) = 'officer'
                                THEN insider_name || ' (Officer)'
                            WHEN COALESCE(insider_relationship, '') <> '' AND COALESCE(insider_title, '') <> ''
                                THEN insider_name || ' (' || insider_relationship || ', ' || insider_title || ')'
                            WHEN COALESCE(insider_relationship, '') <> ''
                                THEN insider_name || ' (' || insider_relationship || ')'
                            WHEN COALESCE(insider_title, '') <> ''
                                THEN insider_name || ' (' || insider_title || ')'
                            ELSE insider_name
                        END,
                        ', ' ORDER BY sum_total_value DESC
                    )
                    FROM (
                        SELECT
                            insider_name,
                            SUM(total_value) AS sum_total_value,
                            MIN(insider_relationship) AS insider_relationship,
                            MIN(insider_title) AS insider_title
                        FROM base b3
                        WHERE b3.ticker = b.ticker
                          AND b3.transaction_date BETWEEN b.transaction_date - INTERVAL '{window_interval} day' AND b.transaction_date
                        GROUP BY insider_name
                        ORDER BY sum_total_value DESC
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
        SELECT
            ticker,
            transaction_date,
            insider_name,
            insider_relationship,
            insider_title,
            shares,
            total_value
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
    if "insider_name" not in base_df.columns:
        base_df["insider_name"] = ""
    else:
        base_df["insider_name"] = base_df["insider_name"].fillna("").astype(str)
    for col in ("insider_relationship", "insider_title"):
        if col not in base_df.columns:
            base_df[col] = ""
        else:
            base_df[col] = base_df[col].fillna("").astype(str)
    base_df["normalized_name"] = base_df["insider_name"].fillna("").astype(str).map(normalize_insider_name)
    flags_df = base_df.apply(_derive_flags, axis=1, result_type="expand")
    for flag_col in ("is_director", "is_officer", "is_ten_percent_owner", "is_other"):
        if flag_col in flags_df:
            base_df[flag_col] = flags_df[flag_col].fillna(False).astype(bool)
        elif flag_col not in base_df.columns:
            base_df[flag_col] = False

    classifications = _classify_insiders(base_df, engine)
    if classifications:
        base_df["is_fund_like"] = base_df["normalized_name"].map(
            lambda n: bool(classifications[n]["is_fund_like"]) if n in classifications else False
        )
        base_df["entity_type"] = base_df["normalized_name"].map(
            lambda n: classifications[n]["entity_type"] if n in classifications else ""
        )
    else:
        base_df["is_fund_like"] = False
        base_df["entity_type"] = ""

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
            total_shares = subset["shares"].sum()
            total_value = subset["total_value"].sum()
            grouped = (
                subset.groupby("normalized_name")
                .agg(
                    insider_name=("insider_name", _first_nonempty),
                    total_value=("total_value", "sum"),
                    relationship=("insider_relationship", _first_nonempty),
                    title=("insider_title", _first_nonempty),
                    is_fund_like=("is_fund_like", "max"),
                    is_director=("is_director", "max"),
                    is_officer=("is_officer", "max"),
                )
                .sort_values("total_value", ascending=False)
            )
            people: list[str] = []
            fund_like_labels: list[str] = []
            role_score = 0
            num_key_officers = 0
            has_cfo = False
            has_gc = False
            has_ceo = False
            for _, row in grouped.iterrows():
                label = _format_insider_label(
                    row.get("insider_name") or "",
                    row.get("relationship"),
                    row.get("title"),
                )
                if row.get("is_fund_like"):
                    fund_like_labels.append(label)
                else:
                    people.append(label)
                    weight = compute_insider_role_weight(
                        officer_title=row.get("title"),
                        is_director=bool(row.get("is_director")),
                        is_officer=bool(row.get("is_officer")),
                    )
                    role_score += weight
                    if weight >= 3:
                        num_key_officers += 1
                    title_u = str(row.get("title") or "").upper()
                    if "CFO" in title_u or "CHIEF FINANCIAL OFFICER" in title_u:
                        has_cfo = True
                    if "GENERAL COUNSEL" in title_u or "CHIEF LEGAL OFFICER" in title_u:
                        has_gc = True
                    if "CEO" in title_u or "CHIEF EXECUTIVE OFFICER" in title_u:
                        has_ceo = True

            num_people = len(people)
            num_fund_like = len(fund_like_labels)
            total_unique_insiders = len(grouped.index)
            top_insiders = ", ".join(people)
            fund_like_insiders = ", ".join(fund_like_labels)
            key_roles = []
            if has_cfo:
                key_roles.append("CFO")
            if has_gc:
                key_roles.append("GC")
            if has_ceo:
                key_roles.append("CEO")
            cluster_score = compute_cluster_score(
                people=num_people,
                role_score=role_score,
                total_value_usd=total_value,
                funds=num_fund_like,
                all_insiders=total_unique_insiders,
            )
            merged_records.append(
                {
                    "ticker": ticker_value,
                    "window_start": start,
                    "window_end": end,
                    "num_trades": int(num_trades),
                    "num_insiders": int(num_people),
                    "num_total_insiders": int(total_unique_insiders),
                    "num_fund_like": int(num_fund_like),
                    "total_shares": float(total_shares),
                    "total_value": float(total_value),
                    "top_insiders": top_insiders,
                    "fund_like_insiders": fund_like_insiders,
                    "role_score": int(role_score),
                    "num_key_officers": int(num_key_officers),
                    "has_cfo": has_cfo,
                    "has_gc": has_gc,
                    "has_ceo": has_ceo,
                    "key_roles": ", ".join(key_roles),
                    "cluster_score": float(cluster_score),
                }
            )

    if not merged_records:
        return pd.DataFrame(columns=df.columns)

    merged_df = pd.DataFrame(merged_records)
    if min_insiders:
        merged_df = merged_df[merged_df["num_insiders"] >= min_insiders]
    if min_people is not None:
        merged_df = merged_df[merged_df["num_insiders"] >= min_people]
    if min_role_score is not None:
        merged_df = merged_df[merged_df["role_score"] >= min_role_score]
    if min_cluster_score is not None:
        merged_df = merged_df[merged_df["cluster_score"] >= min_cluster_score]
    if max_fund_ratio is not None:
        denom = merged_df["num_total_insiders"].replace(0, 1)
        merged_df = merged_df[(merged_df["num_fund_like"] / denom) <= max_fund_ratio]

    merged_df = merged_df.sort_values(
        by=["cluster_score", "role_score", "num_insiders", "total_value", "num_fund_like"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)
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
    return df.head(limit).reset_index(drop=True)
