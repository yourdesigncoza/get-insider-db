Here you go, Big Boss — a full `README.md` you can drop straight into the repo and tweak as you like:

```markdown
# Insider Cluster Buys DB (`get-insider-db`)

A small, focused data pipeline and query layer for **SEC Form 3/4/5 (Form 345) insider transactions**, built around one goal:

> Find **meaningful clustered insider buying** by real operators (CEOs, CFOs, directors, founders) – and **filter out noisy fund / PE / hedge-fund flow**.

---

## 🚀 Quickstart

```bash
# 1) Install dependencies (adjust for your environment)
pip install -r requirements.txt

# 2) Create the database
createdb insider_data
psql insider_data -f schema.sql

# 3) Set your connection string (example)
export DATABASE_URL=postgresql://user:password@localhost:5432/insider_data

# 4) Load SEC Form 345 quarters from ./data/extracted/*
python scripts/load_quarters_from_disk.py

# 5) Run the cluster buy scanner
python scripts/show_cluster_buys.py --window-days 10 --lookback-days 120 --min-insiders 2 --limit 20
```

The project:

- Ingests the official **SEC Form 345 quarterly TSV datasets** (Form 3/4/5).
- Loads them into a **PostgreSQL** schema (`form345_*` tables).
- Exposes a clean view of **insider buy signals**.
- Adds an **exclusion list** for big funds & complexes (RA Capital, Baker Bros, Berkshire, etc.).
- Provides a script to surface **clustered buy windows** (multi-insider, multi-trade, value-filtered).

It’s designed as a backend “engine” that you can plug into other tools (Obsidian, websites, dashboards, etc.).

---

## 1. Data & Concepts

### 1.1 Source data

Data comes from the SEC’s **Form 345 structured datasets**:

Each quarter’s ZIP contains TSV files such as:

- `SUBMISSION.tsv` – one row per filing.  
- `REPORTINGOWNER.tsv` – one row per reporting owner per filing.  
- `NONDERIV_TRANS.tsv` – non-derivative transactions (common shares etc.).  
- `DERIV_TRANS.tsv` – derivative transactions (options, RSUs, etc.).  
- (plus `*_HOLDING.tsv`, `FOOTNOTES.tsv`, metadata, readme, etc.)

You manually download & unzip these into:

```

data/
extracted/
2020q1_form345/
SUBMISSION.tsv
REPORTINGOWNER.tsv
NONDERIV_TRANS.tsv
DERIV_TRANS.tsv
...
2020q2_form345/
...
2025q3_form345/

````

> The ETL scripts assume one subfolder per quarter under `data/extracted/`.

---

### 1.2 Core tables (PostgreSQL)

The schema is created from `schema.sql` and includes the main working tables:

- **`form345_submission`**  
  Parsed from `SUBMISSION.tsv`.  
  Key fields:
  - `"ACCESSION_NUMBER"` (PK per filing)
  - `"FILING_DATE"`
  - `"PERIOD_OF_REPORT"`
  - `"ISSUERTRADINGSYMBOL"` (ticker)
  - `"ISSUERNAME"` (company name)

- **`form345_reportingowner`**  
  Parsed from `REPORTINGOWNER.tsv`.  
  One row per reporting owner per filing.
  - `"ACCESSION_NUMBER"`
  - `"RPTOWNERNAME"` (owner name as filed)
  - `"RPTOWNER_RELATIONSHIP"` (e.g. Officer, Director, 10% Owner)
  - `"RPTOWNER_TITLE"`

- **`form345_nonderiv_trans`**  
  Parsed from `NONDERIV_TRANS.tsv`.  
  This is where **cash share transactions** live.
  - `"ACCESSION_NUMBER"`
  - `"SECURITY_TITLE"`
  - `"TRANS_DATE"`
  - `"TRANS_CODE"` (e.g. P = open-market purchase, S = sale, etc.)
  - `"TRANS_SHARES"`
  - `"TRANS_PRICEPERSHARE"`
  - `"DIRECT_INDIRECT_OWNERSHIP"`
  - `"NATURE_OF_OWNERSHIP"`

- **`form345_deriv_trans`**  
  Parsed from `DERIV_TRANS.tsv`.  
  Currently not used in the cluster signal, but available for future work.

Indexes are created on the key join/filter columns (accession number, ticker, filing date, transaction code, etc.) so queries stay fast even with many years of data.

---

### 1.3 Insider buy view

To normalize and simplify analysis, we define:

```sql
CREATE OR REPLACE VIEW insider_buy_signals AS
SELECT
    s."ACCESSION_NUMBER"                        AS accession_number,
    s."FILING_DATE"::date                       AS filing_date,
    s."PERIOD_OF_REPORT"::date                  AS period_of_report,
    s."ISSUERTRADINGSYMBOL"                     AS ticker,
    s."ISSUERNAME"                              AS issuer_name,

    r."RPTOWNERCIK"                             AS insider_cik,
    r."RPTOWNERNAME"                            AS insider_name,
    r."RPTOWNER_RELATIONSHIP"                   AS insider_relationship,
    r."RPTOWNER_TITLE"                          AS insider_title,

    t."SECURITY_TITLE"                          AS security_title,
    t."TRANS_DATE"::date                        AS transaction_date,
    t."TRANS_CODE"                              AS transaction_code,

    NULLIF(t."TRANS_SHARES", '')::numeric        AS shares,
    NULLIF(t."TRANS_PRICEPERSHARE", '')::numeric AS price_per_share,

    (NULLIF(t."TRANS_SHARES", '')::numeric *
     NULLIF(t."TRANS_PRICEPERSHARE", '')::numeric) AS total_value,

    t."DIRECT_INDIRECT_OWNERSHIP"               AS direct_indirect,
    t."NATURE_OF_OWNERSHIP"                     AS nature_of_ownership
FROM form345_nonderiv_trans t
JOIN form345_submission s
  ON s."ACCESSION_NUMBER" = t."ACCESSION_NUMBER"
LEFT JOIN form345_reportingowner r
  ON r."ACCESSION_NUMBER" = s."ACCESSION_NUMBER"
WHERE t."TRANS_CODE" = 'P';  -- open-market purchases
````

This gives you one row per **insider purchase line-item**, with:

* clean numeric `shares`, `price_per_share`, and `total_value`
* joined issuer + insider metadata.

---

### 1.4 Exclusion list (filter out funds / complexes)

To avoid floods of hedge-fund and PE activity, we maintain:

```sql
CREATE TABLE insider_exclusions (
    id      serial primary key,
    pattern text    not null,
    reason  text    not null,
    active  boolean not null default true
);
```

Each row is a **substring pattern** that, if found in `insider_name`, flags that row as “ignore for cluster signals”.

Examples (seed set):

```sql
INSERT INTO insider_exclusions (pattern, reason) VALUES
  ('RA CAPITAL',              'Healthcare fund complex'),
  ('BAKER BROS',              'Biotech hedge fund'),
  ('DEERFIELD MANAGEMENT',    'Healthcare fund'),
  ('SILVER LAKE',             'PE fund'),
  ('GAP COINVESTMENTS',       'General Atlantic co-invest vehicles'),
  ('ICONIQ STRATEGIC PARTNERS','Tech growth fund'),
  ('BERKSHIRE HATHAWAY',      'Buffett / Berkshire entity'),
  ('COLISEUM CAPITAL',        'Activist fund'),
  ('DEEP TRACK CAPITAL',      'Biotech fund'),
  ('IMPACTIVE CAPITAL',       'Activist fund'),
  ('AIC HOLDING',             'Investment strategies / private investments');
```

The Python query layer joins against this table and excludes any active pattern that matches the `insider_name` in a cluster.

This gives you a **curated feed** focused on genuine operators and strategic buyers.

---

## 2. Project Layout

A typical layout looks like:

```
.
├── README.md
├── schema.sql
├── .env
├── data/
│   └── extracted/
│       ├── 2020q1_form345/
│       ├── 2020q2_form345/
│       └── ...
├── scripts/
│   ├── load_quarters_from_disk.py   # ETL: TSV → Postgres tables
│   ├── debug_quarter_2020q1.py      # sanity check a sample quarter
│   └── show_cluster_buys.py         # main cluster query CLI
└── ...
```

> Script names may vary slightly in your repo; the important bit is *what* they do:
>
> * ETL into `form345_*` tables
> * Debug prints
> * Cluster-buy reporting

---

## 3. Setup

### 3.1 Requirements

* Python **3.10+** (tested with 3.11 / 3.13)
* PostgreSQL **13+** (tested with 16)
* Recommended Python packages:

  * `psycopg2-binary` or `psycopg2`
  * `SQLAlchemy`
  * `pandas`
  * `python-dotenv` (optional, for `.env`)

### 3.2 Create and configure the database

Create a database, e.g.:

```bash
createdb insider_data
```

Set your `DATABASE_URL` (in `.env` or shell):

```bash
export DATABASE_URL=postgresql://user:password@localhost:5432/insider_data
```

Run the schema:

```bash
psql "$DATABASE_URL" -f schema.sql
```

This will:

* Create the `form345_*` tables
* Create indexes on key fields
* Create the `insider_exclusions` table
* Create the `insider_buy_signals` view

You can inspect the tables with your DB tool of choice (Beekeeper Studio, psql, etc.).

---

## 4. Loading SEC quarters

1. **Download Form 345 quarterly ZIPs** from the SEC website (Form 3/4/5 “insider transactions data sets”).

2. **Extract each ZIP** into its own folder:

   * Example: `data/extracted/2020q1_form345/` containing `SUBMISSION.tsv`, `REPORTINGOWNER.tsv`, `NONDERIV_TRANS.tsv`, `DERIV_TRANS.tsv`, etc.

3. Run the ETL loader script (name may differ; adjust accordingly):

   ```bash
   python scripts/load_quarters_from_disk.py
   ```

   This script typically:

   * Scans `data/extracted/*_form345/`
   * Reads each TSV with `pandas`
   * Writes into the matching `form345_*` tables
   * Skips quarters it has already loaded (based on a log table or metadata)

During development you can sanity-check a single quarter with:

```bash
python scripts/debug_quarter_2020q1.py
```

which prints the first few rows of each TSV and basic stats like value counts of `TRANS_CODE`.

---

## 5. Cluster Buy CLI

The main “product” of this pipeline is the **cluster buy report**:

```bash
python scripts/show_cluster_buys.py \
  --window-days 10 \
  --lookback-days 120 \
  --min-insiders 2 \
  --min-total-value 0 \
  --min-trade-value 50000 \
  --limit 20
```

### 5.1 Arguments

* `--window-days`
  Size of the rolling window (e.g. 10 days). Trades within the same window are grouped into a cluster.

* `--lookback-days`
  How far back from “today” to look (e.g. 120 days).

* `--min-insiders`
  Minimum distinct insiders required in a window (e.g. 2).

* `--min-total-value`
  Minimum **total cluster value** in USD to show a row.

* `--min-trade-value`
  Minimum value per individual transaction to count towards the cluster (filters out tiny / symbolic buys).

* `--limit`
  Maximum number of cluster rows to return, ordered by `total_value` descending.

### 5.2 Output

The script prints a Markdown-ready table like:

```text
| ticker | window_start | window_end | num_trades | num_insiders | total_shares | total_value | top_insiders                                        |
|--------|--------------|------------|------------|--------------|-------------:|------------:|-----------------------------------------------------|
| TKO    | 2025-05-25   | 2025-06-05 |          3 |            3 |   3159140.00 | 500166089.40| Durban Egon, Endeavor Group Holdings, Inc., Bynoe…  |
| PTN    | 2025-06-04   | 2025-06-13 |          3 |            3 |      3200.00 | 454000000.00| Spana Carl, Wills Stephen T, Dunton Alan W          |
| ...    | ...          | ...        |        ... |          ... |         ...  |        ...  | ...                                                 |
```

You can paste this directly into Obsidian, Notion, or a newsletter.

Behind the scenes, it:

1. Pulls candidate insider buys from `insider_buy_signals`.
2. Filters out any rows whose `insider_name` matches an active pattern in `insider_exclusions`.
3. Applies the transaction-level filters (`min-trade-value`, etc.).
4. Slides a `window_days` window over `transaction_date` to find clusters.
5. Groups by `(ticker, window_start, window_end)` to compute:

   * `num_trades`
   * `num_insiders`
   * `total_shares`
   * `total_value`
   * `top_insiders` (a concatenated list of the most relevant insider names)

---

## 6. Managing the exclusion list

Most of the “craft” in this project lives in **curating `insider_exclusions`**.

### 6.1 Add a new fund / complex

When you see noisy clusters dominated by a fund, add a pattern:

```sql
INSERT INTO insider_exclusions (pattern, reason)
VALUES ('MUDRICK ', 'Mudrick distressed funds');
```

Re-run `show_cluster_buys.py` and the feed will tighten.

### 6.2 Deactivate instead of deleting

If you want to temporarily allow a fund back in for experiments:

```sql
UPDATE insider_exclusions
SET active = false
WHERE pattern = 'BERKSHIRE HATHAWAY';
```

You can always flip it back to `true`.

---

## 7. Extending the project

Ideas for next iterations:

* **Derivatives support**
  Incorporate `form345_deriv_trans` (options, RSUs) into the signal with a configurable weighting or flag.

* **Cluster notes / tags**
  Add a `cluster_notes` table where you can manually annotate tickers or clusters, e.g.:

  * Sector / theme
  * “Follow-up done” flags
  * Personal conviction ratings.

* **Obsidian / markdown export script**
  A script like `scripts/show_cluster_buys_md.py` that:

  * Runs the cluster query
  * Writes out a `.md` note per day/week with embedded tables.

* **Web API layer**
  A thin FastAPI / Flask wrapper exposing endpoints like `/clusters`, `/insiders/:ticker`, etc., for frontend experiments.

---

## 8. Troubleshooting

* **Slow queries**

  * Ensure indexes from `schema.sql` are created (especially on `ACCESSION_NUMBER`, `ISSUERTRADINGSYMBOL`, `FILING_DATE`, `TRANS_CODE`, `TRANS_DATE`).
  * Use `EXPLAIN ANALYZE` on the main cluster query if needed.

* **No recent results**

  * Check that you have data covering the relevant date range.
  * Verify `FILING_DATE` range in `form345_submission`:

    ```sql
    SELECT min("FILING_DATE"), max("FILING_DATE")
    FROM form345_submission;
    ```
  * Confirm `--lookback-days` and `--min-trade-value` aren’t overly strict.

* **Unexpected fund names in `top_insiders`**

  * Add another `insider_exclusions` pattern.
  * Keep patterns fairly short but distinctive (e.g. `'BASSWOOD '` instead of the full legal name).

---

## 9. License / Usage

This project is intended for personal research and educational use.
Replace this section with your preferred license (MIT, proprietary, etc.) once you decide.

---

## 10. Summary

This repo gives you:

* A **clean database** of SEC insider trading data.
* A curated **view of genuine insider purchases**.
* A flexible **cluster engine** to surface high-conviction buying windows.
* A simple but powerful **exclusion mechanism** so you stay focused on the *people* you care about, not hedge-fund noise.

From here you can plug the output into:

* Your trading workflow
* Obsidian / Notion notes
* A web app or email newsletter
* Any other analytics layer you want to build on top.

Happy hunting. 🕵️‍♂️📈

