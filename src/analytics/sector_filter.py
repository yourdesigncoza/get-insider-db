"""
Post-filter that removes clusters whose issuer falls in a blocked SIC sector.

Unknown SIC policy: permissive — clusters without a sector_lookup row pass through.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.scoring_config.sector_blocklist import is_sic_blocked


def apply_sector_blocklist(
    df: pd.DataFrame,
    engine: Engine,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Filter out clusters whose issuer_cik maps to a blocked SIC code.

    Returns (filtered_df, list_of_blocked_clusters_with_reasons).
    Clusters without a sector_lookup row are kept (permissive unknown policy).
    """
    if df.empty or "issuer_cik" not in df.columns:
        return df, []

    ciks = df["issuer_cik"].dropna().unique().tolist()
    if not ciks:
        return df, []

    # Batch-lookup SIC codes
    placeholders = ", ".join([f":cik{i}" for i in range(len(ciks))])
    params = {f"cik{i}": cik for i, cik in enumerate(ciks)}
    query = text(
        f"SELECT issuer_cik, sic_code, ticker "
        f"FROM sector_lookup "
        f"WHERE issuer_cik IN ({placeholders})"
    )

    with engine.connect() as conn:
        rows = conn.execute(query, params).fetchall()

    sic_map: dict[str, tuple[int | None, str | None]] = {}
    for row in rows:
        try:
            sic = int(row[1]) if row[1] else None
        except (ValueError, TypeError):
            sic = None
        sic_map[row[0]] = (sic, row[2])

    blocked: list[dict[str, Any]] = []
    blocked_ciks: set[str] = set()

    for cik in ciks:
        if cik not in sic_map:
            continue  # permissive: no data → pass through
        sic, ticker = sic_map[cik]
        if sic is None:
            continue
        is_blocked, reason = is_sic_blocked(sic)
        if is_blocked:
            blocked_ciks.add(cik)
            blocked.append({
                "issuer_cik": cik,
                "ticker": ticker,
                "sic_code": sic,
                "reason": reason,
            })

    if not blocked_ciks:
        return df, []

    filtered = df[~df["issuer_cik"].isin(blocked_ciks)].copy()
    return filtered, blocked
