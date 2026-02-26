#!/usr/bin/env python
"""
Populate sector_lookup table by fetching SIC codes from SEC EDGAR.

For each distinct issuer_cik in form345_submission, fetches the company JSON
from https://data.sec.gov/submissions/CIK{cik_padded}.json and extracts
the SIC code, SIC description, and ticker.

Rate-limited to respect SEC's 10 req/sec guideline.
Idempotent — safe to re-run (upserts on issuer_cik).
"""

import os
import sys
import time
from pathlib import Path

import requests
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_engine
from src.logging_config import get_logger

logger = get_logger(__name__)

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
# SEC requires a descriptive User-Agent with contact info
SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "insider-db-pipeline admin@example.com",
)
RATE_LIMIT_SECONDS = float(os.getenv("RATE_LIMIT_SECONDS", "0.12"))  # ~8 req/sec


def get_missing_ciks(engine) -> list[str]:
    """Get issuer_cik values from form345_submission not yet in sector_lookup."""
    query = text("""
        SELECT DISTINCT s."ISSUERCIK"
        FROM form345_submission s
        LEFT JOIN sector_lookup sl ON s."ISSUERCIK" = sl.issuer_cik
        WHERE s."ISSUERCIK" IS NOT NULL
          AND s."ISSUERCIK" != ''
          AND sl.issuer_cik IS NULL
    """)
    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()
    return [row[0] for row in rows]


def fetch_sic_from_edgar(cik: str, session: requests.Session) -> dict | None:
    """Fetch SIC code + description from SEC EDGAR for a given CIK."""
    padded = cik.zfill(10)
    url = SEC_SUBMISSIONS_URL.format(cik=padded)
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 404:
            logger.warning("cik_not_found", cik=cik)
            return None
        resp.raise_for_status()
        data = resp.json()
        return {
            "sic_code": data.get("sic"),
            "sic_description": data.get("sicDescription"),
            "ticker": (data.get("tickers") or [None])[0],
        }
    except requests.RequestException as e:
        logger.error("edgar_fetch_failed", cik=cik, error=str(e))
        return None


def upsert_sector_lookup(engine, cik: str, info: dict) -> None:
    """Upsert a single row into sector_lookup."""
    query = text("""
        INSERT INTO sector_lookup (issuer_cik, ticker, sic_code, sic_description, updated_at)
        VALUES (:cik, :ticker, :sic_code, :sic_desc, now())
        ON CONFLICT (issuer_cik) DO UPDATE SET
            ticker = EXCLUDED.ticker,
            sic_code = EXCLUDED.sic_code,
            sic_description = EXCLUDED.sic_description,
            updated_at = now()
    """)
    with engine.begin() as conn:
        conn.execute(query, {
            "cik": cik,
            "ticker": info.get("ticker"),
            "sic_code": info.get("sic_code"),
            "sic_desc": info.get("sic_description"),
        })


def main() -> None:
    engine = get_engine()

    # Ensure table exists
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sector_lookup (
                issuer_cik  TEXT PRIMARY KEY,
                ticker      TEXT,
                sic_code    TEXT,
                sic_description TEXT,
                sector      TEXT,
                updated_at  TIMESTAMPTZ DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_sector_lookup_sic ON sector_lookup(sic_code)"
        ))

    ciks = get_missing_ciks(engine)
    if not ciks:
        print("All CIKs already have sector_lookup entries.")
        return

    print(f"Fetching SIC codes for {len(ciks)} CIKs from SEC EDGAR...")

    session = requests.Session()
    session.headers.update({"User-Agent": SEC_USER_AGENT})

    success = 0
    skipped = 0
    for i, cik in enumerate(ciks, 1):
        info = fetch_sic_from_edgar(cik, session)
        if info is None:
            skipped += 1
        else:
            upsert_sector_lookup(engine, cik, info)
            success += 1

        if i % 100 == 0:
            print(f"  Progress: {i}/{len(ciks)} ({success} ok, {skipped} skipped)")

        time.sleep(RATE_LIMIT_SECONDS)

    print(f"Done. {success} upserted, {skipped} skipped out of {len(ciks)} CIKs.")


if __name__ == "__main__":
    main()
