Yeah, honestly… I think that’s **exactly the right move** for what you’re trying to do.

Use **edgartools** as a *nice helper* for ad-hoc / debugging…
…but for serious **backtests, sorting, scanning and clustering**, the **official SEC TSV dataset per quarter** is a much better foundation.

---

## Why the quarterly ZIP + your own DB is a good idea

**Pros:**

1. **Speed & control**

   * Once the TSVs are in Postgres (or DuckDB), all the heavy stuff (sort, filter, group, rolling windows) happens **locally**, not over HTTP.
   * You can build indexes exactly for your “cluster BUY” queries.

2. **Stable, complete dataset**

   * The quarterly Form 3/4/5 dataset is the SEC’s own curated, structured view.
   * Schema is explicit (that JSON you opened), and doesn’t change often. 

3. **Perfect for your use case**

   * You care about:

     * `NONDERIV_TRANS` → real share buys/sells
     * `DERIV_TRANS` → option exercises & derivative moves
     * `REPORTING_OWNER` → who they are (Director / Officer / 10% Owner)
     * `SUBMISSION` → issuer, ticker, filing date
   * Those 4 tables + a “buy signal” view give you everything for your playbook.

4. **You’re not fighting library bugs / versions**

   * No more “Form4 has no attribute X” / “to_dataframe missing column Y”.
   * Pandas + TSV + SQLAlchemy is boring, which is exactly what you want here.

**Cons (but manageable):**

* You manually grab a ZIP per quarter (or write a tiny downloader).
* You have to define a schema once (but we already have the SEC’s schema as a guide).

Given your style (you like owning the pipeline end-to-end), this fits you perfectly.

---

## Suggested architecture (V1)

**Data source:**
Quarterly ZIP → those 8 TSVs (SUBMISSION, REPORTING_OWNER, NONDERIV_TRANS, DERIV_TRANS, etc.). 

**DB tables (minimal):**

* `submissions` (from SUBMISSION.tsv)
* `reporting_owners` (from REPORTING_OWNER.tsv)
* `nonderiv_transactions` (from NONDERIV_TRANS.tsv)
* `deriv_transactions` (from DERIV_TRANS.tsv)

**Then one “analytics” layer:**

* A **view or materialized view** `insider_buy_signals` that:

  * joins `nonderiv_transactions` → `submissions` → `reporting_owners`
  * filters `TRANS_CODE` ∈ {P, M, A} (or your final mapping)
  * aggregates per (issuer, insider, date window) for your “cluster buys”.

---

## Concrete next step (you can run this today)

Here’s a simple loader script you can adapt, assuming:

* You unzip the SEC ZIP to `data/form345_2024q1/`
* You want to load into Postgres at `postgresql://user:password@localhost:5432/insider_data`

Save as e.g. `scripts/load_form345_quarter.py`:

```python
#!/usr/bin/env python
"""
Load SEC Form 3/4/5 structured dataset (one quarter) into Postgres.

Assumes you've unzipped the SEC ZIP so you have files like:
  SUBMISSION.tsv
  REPORTING_OWNER.tsv
  NONDERIV_TRANS.tsv
  DERIV_TRANS.tsv
in a target directory.
"""

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine


# TODO: set to your real DB URL
DATABASE_URL = "postgresql://user:password@localhost:5432/insider_data"

# Path to the folder containing the TSVs
DATA_DIR = Path("data/form345_2024q1")


def read_tsv(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    print(f"Reading {path} ...")
    return pd.read_csv(
        path,
        sep="\t",
        dtype=str,        # keep everything as string first; safer
        na_filter=False,  # empty strings instead of NaN
    )


def main() -> None:
    engine = create_engine(DATABASE_URL)

    # --- Core tables we care about for now ---
    submissions = read_tsv("SUBMISSION.tsv")
    reporting_owners = read_tsv("REPORTING_OWNER.tsv")
    nonderiv_trans = read_tsv("NONDERIV_TRANS.tsv")
    deriv_trans = read_tsv("DERIV_TRANS.tsv")

    # Optional: you can rename columns to snake_case here if you want
    # For V1, just store them as-is into staging tables.

    print("Writing tables to Postgres...")

    submissions.to_sql(
        "form345_submissions",
        engine,
        if_exists="append",
        index=False,
    )
    reporting_owners.to_sql(
        "form345_reporting_owners",
        engine,
        if_exists="append",
        index=False,
    )
    nonderiv_trans.to_sql(
        "form345_nonderiv_trans",
        engine,
        if_exists="append",
        index=False,
    )
    deriv_trans.to_sql(
        "form345_deriv_trans",
        engine,
        if_exists="append",
        index=False,
    )

    print("Done. Data loaded into Postgres.")


if __name__ == "__main__":
    main()
```

From your project root:

```bash
python scripts/load_form345_quarter.py
```

V1 is just **staging tables**. Once that works, we:

1. Add **indexes** (e.g. on `ACCESSION_NUMBER`, `ISSUERTRADINGSYMBOL`, `TRANS_DATE`, `TRANS_CODE`).
2. Design a **SQL view** for BUY-only signals (`TRANS_CODE` mapping + aggregation).
3. Hook your app / backtest code to query that instead of hitting edgartools.

---

## My recommendation

* **Yes**: keep edgartools for on-the-fly “what happened in MSFT last month?” type probes.
* But for your actual **cluster-buy engine + stats + backtests**, absolutely move to:

  > “Download ZIP per quarter → load TSVs → Postgres → query locally”

If you’re happy with that direction, I can next write:

* The **SQL for the `insider_buy_signals` view**,
* and a **Pandas query example** that mirrors your playbook (filter by officer/10% owner, cluster window, min $$, etc.).
