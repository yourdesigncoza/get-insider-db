# Insider Cluster Buys DB (`get-insider-db`)

Pipeline for ingesting SEC Form 3/4/5 data, classifying insiders, detecting conviction-weighted **cluster buy** events, and exporting runs that can be enriched with price performance.

## Project Overview
- Loads raw SEC Form 345 TSVs into a relational database, normalizes transactions, and caches insider classifications.
- Detects windows where multiple real insiders buy in unison, scores conviction using role weights and behavior features, and exports ranked clusters.
- Optional Alpha Vantage enrichment adds post-signal returns and drawdowns to evaluate results.

## Architecture
- **Data ingestion:** `scripts/load_form345_quarter.py` scans `data/extracted/*_form345` folders, ingests TSVs into the DB, and keeps a `loaded_to_db.txt` log to avoid reprocessing. `scripts/load_quarter.py` is a thin wrapper for ad-hoc loads.
- **Database schema:** Default target is PostgreSQL via `DATABASE_URL`, but the logical schema (transactions, insiders, companies, clusters) is portable to SQLite for lightweight runs. `schema.sql` defines:
  - `form345_submission`, `form345_reportingowner`, `form345_nonderiv_trans`, `form345_deriv_trans` for raw filings and line items.
  - `insider_entities` (classification cache) and `insider_exclusions` (fund/entity filters).
  - `insider_trades` staging plus views `insider_buy_signals` (clean open-market buys) and `insider_trades_with_title` (derived titles/roles).
- **Analytics modules:** `src/analytics/cluster_buys.py` and `cluster_service.py` detect/merge cluster windows; `feature_engineering.py` and `buy_signals.py` derive behavior features; `src/cluster_scoring.py`, `src/insider_roles.py`, and `src/insider_classification.py` score clusters and classify insiders.

## Key Features
- Rule-based insider classification and role weighting (CFO/GC/CEO > Director) to prioritize real operators over funds.
- Sliding-window cluster buy detection with configurable insider counts, dollar thresholds, and fund exclusions.
- Composite conviction scoring that blends role density, participation, ticket size, filing timeliness, and historical buy/sell behavior.
- Alpha Vantage integration to append price at window end, forward returns (1/2/3m), and max drawdown.
- Export scripts that persist top-ranked clusters to JSON for downstream analysis or dashboards.

## Analytics Logic
- **Cluster identification:** Groups open-market `P` transactions by ticker within a rolling 10-day window (configurable) and flags a cluster when the third unique insider appears. Windows carry `signal_date`, `window_start/window_end`, and expire after a configurable horizon.
- **Conviction scoring:** `compute_cluster_score` blends role score, people count, log-scaled total value, fund ratio penalty, average percent holdings increase, filing speed (`days_to_file`), and sale-to-purchase ratio. Role weights come from `insider_roles.py`; classification pulls from `insider_entities` and `insider_exclusions`.
- **Feature engineering:** `feature_engineering.py` adds `days_to_file` and `sale_to_purchase_ratio`; cluster detection tracks ownership deltas to reward insiders increasing stake materially.

## Setup & Usage
1. **Install requirements**
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure environment**
   ```bash
   export DATABASE_URL=postgresql://user:pass@localhost:5432/insider_data
   export DATA_DIR=data/extracted          # optional; defaults to data/extracted
   export FINANCIAL_DATASETS_API_KEY=your_key_here     # needed for price enrichment
   ```
3. **Initialize the database**
   ```bash
   psql $DATABASE_URL -f schema.sql
   ```
4. **Load quarterly SEC data**
   - Place extracted quarters (e.g., `2025q3_form345/SUBMISSION.tsv`, `REPORTINGOWNER.tsv`, etc.) under `data/extracted/`.
   - Ingest:
     ```bash
     python scripts/load_form345_quarter.py
     ```
5. **Run cluster analysis**
   - Inspect clusters in the console:
     ```bash
     python scripts/show_cluster_buys.py \
       --window-days 10 --lookback-days 120 \
       --min-insiders 3 --min-role-score 15 \
       --min-cluster-score 60 --max-fund-ratio 0.25
     ```
   - Export the run to disk:
     ```bash
     python scripts/export_top_clusters.py --limit 50
     ```
6. **Enrich with Alpha Vantage prices**
   ```bash
   python scripts/enrich_clusters_with_price.py exports/cluster_runs/<export>.json
   ```

## Project Structure
- `src/` — core library (config, classification, role weighting, cluster scoring).
- `src/analytics/` — cluster detection, feature engineering, buy signal helpers.
- `scripts/` — CLI entrypoints for loading data, showing/exporting clusters, and price enrichment.
- `docs/` — design notes and analytical rationale.
- `schema.sql`, `sql/` — database DDL and helper SQL.
- `data/` — extracted SEC TSVs (not tracked); `exports/` — saved cluster runs.
- `tests/` — unit tests for scoring and classification utilities.
