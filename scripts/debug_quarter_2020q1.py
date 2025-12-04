#!/usr/bin/env python
"""
Quick sanity check for the 2020q1 Form 3/4/5 TSVs (no DB involved).
"""

import sys
from pathlib import Path

import pandas as pd

# Allow running the script directly without installing the package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import DATA_DIR

BASE = Path(DATA_DIR) / "2020q1_form345"


def show_head(name: str, n: int = 5) -> None:
    path = BASE / name
    print(f"\n=== {path.name} ===")
    df = pd.read_csv(path, sep="\t", dtype=str, na_filter=False)
    print(df.head(n))


def main() -> None:
    show_head("SUBMISSION.tsv")
    show_head("REPORTINGOWNER.tsv")  # note: no underscore in filename
    show_head("NONDERIV_TRANS.tsv")
    show_head("DERIV_TRANS.tsv")

    nonderiv = pd.read_csv(BASE / "NONDERIV_TRANS.tsv", sep="\t", dtype=str, na_filter=False)
    print("\nNONDERIV_TRANS – TRANS_CODE value_counts:")
    print(nonderiv["TRANS_CODE"].value_counts().head(20))


if __name__ == "__main__":
    main()
