#!/usr/bin/env python
"""
CLI entry point to load Form 3/4/5 TSVs for a given quarter.
"""

import argparse

from src.loaders.form345_loader import load_quarter


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Form 3/4/5 TSVs into Postgres")
    parser.add_argument(
        "path",
        help="Path to TSV file or directory (relative paths are resolved against DATA_DIR)",
    )
    parser.add_argument(
        "--table",
        default=None,
        help="Destination table name (defaults to form345_raw)",
    )
    args = parser.parse_args()

    total = load_quarter(args.path, table=args.table or "form345_raw")
    print(f"Inserted {total} rows from {args.path}")


if __name__ == "__main__":
    main()
