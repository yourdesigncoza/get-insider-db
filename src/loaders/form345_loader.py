"""
Utilities for loading SEC Form 3/4/5 TSV files into Postgres.

The main entry point is `load_quarter`, which accepts either a TSV file path
or a directory containing multiple TSV files. Files are appended into the
target table, defaulting to `form345_raw`.
"""

from __future__ import annotations

import pathlib
import io
import csv
from typing import Iterable, Optional

import pandas as pd
from sqlalchemy.engine import Engine

from src.config import DATA_DIR, get_engine

DEFAULT_TABLE = "form345_raw"


def discover_tsvs(path: pathlib.Path) -> Iterable[pathlib.Path]:
    """Yield TSV files from a single file or every TSV in a directory."""
    if path.is_file():
        yield path
        return

    for candidate in path.glob("*.tsv"):
        if candidate.is_file():
            yield candidate


def load_file(file_path: pathlib.Path, engine: Engine, table: str = DEFAULT_TABLE) -> int:
    """
    Load a single TSV file into the specified Postgres table using the efficient COPY command.

    Returns the number of rows written.
    """
    # Read using pandas for robust parsing
    df = pd.read_csv(file_path, sep="\t", dtype=str)
    
    # Normalize column names: strip whitespace and uppercase to match schema
    df.columns = [col.strip().upper() for col in df.columns]

    # Convert to CSV buffer for COPY
    output = io.StringIO()
    df.to_csv(
        output, 
        sep="\t", 
        header=False, 
        index=False, 
        quoting=csv.QUOTE_MINIMAL,
        escapechar="\\"
    )
    output.seek(0)

    # Construct columns string for the COPY command
    # We quote columns to ensure case sensitivity is respected if needed, 
    # though standard SQL is case-insensitive, the schema defined quoted identifiers.
    columns = ",".join([f'"{c}"' for c in df.columns])

    sql = f"COPY public.{table} ({columns}) FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '')"

    # Execute COPY using a raw psycopg2 cursor
    # SQLAlchemy 1.4/2.0+ engine.raw_connection() returns a pool-proxied DBAPI connection
    with engine.connect() as conn:
        # We need to access the underlying psycopg2 connection
        # usage might vary by sqlalchemy version, but this is generally safe for psycopg2
        dbapi_conn = conn.connection
        with dbapi_conn.cursor() as cur:
            cur.copy_expert(sql, output)
        dbapi_conn.commit()

    return len(df.index)


def load_quarter(
    path: str,
    *,
    engine: Optional[Engine] = None,
    table: str = DEFAULT_TABLE,
) -> int:
    """
    Load all TSVs found at `path` (file or directory) into Postgres.

    Returns total rows inserted across all files.
    """
    base = pathlib.Path(path)
    if not base.exists():
        default_dir = pathlib.Path(DATA_DIR) / path
        if not default_dir.exists():
            raise FileNotFoundError(f"No TSVs found at {path} or {default_dir}")
        base = default_dir

    engine = engine or get_engine()
    total_rows = 0
    for tsv in discover_tsvs(base):
        total_rows += load_file(tsv, engine, table=table)
    return total_rows
