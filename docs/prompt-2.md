Nice, this is the fun part 😎
You’ve basically got a mini-SEC warehouse sitting in `data/extracted/2020q1_form345`.

Here’s what I’d do *right now*, in order:

---

## 1. Install deps & set up config

In your new project venv:

```bash
pip install pandas sqlalchemy psycopg2-binary python-dotenv
```

Create a `.env` in the project root:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/insider_data
DATA_DIR=data/extracted
```

(Create the `insider_data` database in Postgres if you haven’t already.)

Then `src/config.py`:

```python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
DATA_DIR = Path(os.getenv("DATA_DIR", "data/extracted"))
```

---

## 2. Quick sanity check on the TSVs (no DB yet)

Make `scripts/debug_quarter_2020q1.py` to just peek at the files:

```python
#!/usr/bin/env python

from pathlib import Path
import pandas as pd

BASE = Path("data/extracted/2020q1_form345")

def show_head(name: str, n: int = 5):
    path = BASE / name
    print(f"\n=== {path.name} ===")
    df = pd.read_csv(path, sep="\t", dtype=str, na_filter=False)
    print(df.head(n))

def main():
    show_head("SUBMISSION.tsv")
    show_head("REPORTINGOWNER.tsv")     # note: no underscore in filename
    show_head("NONDERIV_TRANS.tsv")
    show_head("DERIV_TRANS.tsv")

    # Bonus: see what transaction codes exist
    nonderiv = pd.read_csv(BASE / "NONDERIV_TRANS.tsv",
                           sep="\t", dtype=str, na_filter=False)
    print("\nNONDERIV_TRANS – TRANS_CODE value_counts:")
    print(nonderiv["TRANS_CODE"].value_counts().head(20))

if __name__ == "__main__":
    main()
```

Run:

```bash
python scripts/debug_quarter_2020q1.py
```

This just confirms columns & codes line up with what we expect.

---

## 3. Load this quarter into Postgres (staging tables)

Now a loader script: `scripts/load_form345_quarter.py`

```python
#!/usr/bin/env python

from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine
from src.config import DATABASE_URL, DATA_DIR

# change this if you put different quarters in different folders
QUARTER_DIR = DATA_DIR / "2020q1_form345"

TABLE_MAP = {
    "SUBMISSION.tsv":        "form345_submission",
    "REPORTINGOWNER.tsv":    "form345_reportingowner",
    "NONDERIV_TRANS.tsv":    "form345_nonderiv_trans",
    "DERIV_TRANS.tsv":       "form345_deriv_trans",
    # add others later if you need them:
    # "NONDERIV_HOLDING.tsv": "form345_nonderiv_holding",
    # "DERIV_HOLDING.tsv":    "form345_deriv_holding",
    # "FOOTNOTES.tsv":        "form345_footnotes",
    # "OWNER_SIGNATURE.tsv":  "form345_owner_signature",
}

def read_tsv(path: Path) -> pd.DataFrame:
    print(f"Reading {path} ...")
    return pd.read_csv(
        path,
        sep="\t",
        dtype=str,     # keep everything as string for now
        na_filter=False,
    )

def main():
    engine = create_engine(DATABASE_URL)

    for filename, table in TABLE_MAP.items():
        path = QUARTER_DIR / filename
        df = read_tsv(path)
        print(f"Writing {len(df):,} rows to {table} ...")
        df.to_sql(table, engine, if_exists="append", index=False)

    print("✅ Finished loading 2020q1 into Postgres")

if __name__ == "__main__":
    main()
```

Run:

```bash
python scripts/load_form345_quarter.py
```

That gives you 4 staging tables:

* `form345_submission`
* `form345_reportingowner`
* `form345_nonderiv_trans`
* `form345_deriv_trans`

---

## 4. Next next step (after this runs)

Once this is in Postgres, the next logical move is:

* Create a **view** like `insider_buy_signals` that joins
  `nonderiv_trans + submission + reportingowner` and filters `TRANS_CODE` to BUY-ish codes (`P`, `M`, maybe `A`).

When you’re ready, I can give you the SQL for that view plus a small Python query that pulls “cluster buys” per ticker/insider/date window.
