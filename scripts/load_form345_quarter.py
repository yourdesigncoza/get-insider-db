#!/usr/bin/env python
"""
Load all Form 3/4/5 quarter folders under DATA_DIR into Postgres staging tables.

Keeps a log file (loaded_to_db.txt) in DATA_DIR to skip quarters already loaded.
"""

import sys
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.inspection import inspect

# Allow running the script directly without installing the package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import DATA_DIR, DATABASE_URL

TABLE_MAP = {
    "SUBMISSION.tsv": "form345_submission",
    "REPORTINGOWNER.tsv": "form345_reportingowner",
    "NONDERIV_TRANS.tsv": "form345_nonderiv_trans",
    "DERIV_TRANS.tsv": "form345_deriv_trans",
    # Optional: uncomment/add as needed
    # "NONDERIV_HOLDING.tsv": "form345_nonderiv_holding",
    # "DERIV_HOLDING.tsv": "form345_deriv_holding",
    # "FOOTNOTES.tsv": "form345_footnotes",
    # "OWNER_SIGNATURE.tsv": "form345_owner_signature",
}

LOG_PATH = Path(DATA_DIR) / "loaded_to_db.txt"


def load_log() -> set[str]:
    if not LOG_PATH.exists():
        return set()
    return {line.strip() for line in LOG_PATH.read_text().splitlines() if line.strip()}


def save_log(entries: set[str]) -> None:
    LOG_PATH.write_text("\n".join(sorted(entries)) + "\n")


def read_tsv(path: Path) -> pd.DataFrame:
    print(f"Reading {path} ...")
    return pd.read_csv(path, sep="\t", dtype=str, na_filter=False)


def quarter_dirs(base: Path) -> Iterable[Path]:
    return sorted(p for p in base.glob("*_form345") if p.is_dir())


def ensure_columns(table: str, df: pd.DataFrame, engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table(table):
        return  # table will be created by to_sql

    existing_cols = {col["name"] for col in inspector.get_columns(table)}
    missing = [col for col in df.columns if col not in existing_cols]
    if not missing:
        return

    with engine.begin() as conn:
        for col in missing:
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{col}" TEXT'))


def refresh_cik_ticker_mapping(engine: Engine) -> None:
    """
    Refresh CIK-ticker mapping from form345_submission.
    Uses most recent filing date per CIK to determine current ticker.
    """
    with engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO issuer_cik_ticker_map (issuer_cik, ticker, issuer_name, last_seen_date, updated_at)
            SELECT
                sub.issuer_cik,
                sub.ticker,
                sub.issuer_name,
                sub.last_seen_date,
                NOW()
            FROM (
                SELECT DISTINCT ON (s."ISSUERCIK")
                    s."ISSUERCIK" AS issuer_cik,
                    TRIM(SPLIT_PART(s."ISSUERTRADINGSYMBOL", ',', 1)) AS ticker,
                    s."ISSUERNAME" AS issuer_name,
                    MAX(s."FILING_DATE"::date) AS last_seen_date
                FROM form345_submission s
                WHERE s."ISSUERCIK" IS NOT NULL
                  AND s."ISSUERCIK" != ''
                  AND s."ISSUERTRADINGSYMBOL" IS NOT NULL
                  AND s."ISSUERTRADINGSYMBOL" != ''
                GROUP BY s."ISSUERCIK", s."ISSUERTRADINGSYMBOL", s."ISSUERNAME"
                ORDER BY s."ISSUERCIK", MAX(s."FILING_DATE"::date) DESC
            ) sub
            ON CONFLICT (issuer_cik)
            DO UPDATE SET
                ticker = EXCLUDED.ticker,
                issuer_name = EXCLUDED.issuer_name,
                last_seen_date = EXCLUDED.last_seen_date,
                updated_at = NOW()
            WHERE EXCLUDED.last_seen_date > issuer_cik_ticker_map.last_seen_date
        """))
        count = result.rowcount
    print(f"Refreshed CIK-ticker mapping: {count} rows upserted")


def load_quarter(dir_path: Path, engine: Engine) -> None:
    for filename, table in TABLE_MAP.items():
        path = dir_path / filename
        if not path.exists():
            raise FileNotFoundError(f"Expected file missing: {path}")
        df = read_tsv(path)
        print(f"Writing {len(df):,} rows from {path.name} to {table} ...")
        ensure_columns(table, df, engine)
        df.to_sql(table, engine, if_exists="append", index=False)


def main() -> None:
    engine = create_engine(DATABASE_URL)
    already_loaded = load_log()

    quarters = list(quarter_dirs(Path(DATA_DIR)))
    if not quarters:
        print(f"No quarter folders found in {DATA_DIR}")
        return

    new_loads = 0
    for qdir in quarters:
        name = qdir.name
        if name in already_loaded:
            print(f"Skipping already loaded quarter: {name}")
            continue

        print(f"\n=== Loading quarter: {name} ===")
        load_quarter(qdir, engine)
        already_loaded.add(name)
        save_log(already_loaded)  # persist incrementally in case of later failures
        new_loads += 1

    print("\nRefreshing CIK-ticker mapping...")
    refresh_cik_ticker_mapping(engine)

    print(f"\nDone. New quarters loaded: {new_loads}, total logged: {len(already_loaded)}")


if __name__ == "__main__":
    main()
