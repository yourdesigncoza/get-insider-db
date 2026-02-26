# Insider Cluster Buys DB (`get-insider-db`)

When multiple corporate insiders buy their own company's stock within the same short window, it often signals genuine conviction about the company's prospects. This pipeline detects those **cluster buy** events from SEC Form 3/4/5 filings, scores them by conviction strength, and tracks forward price performance.

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
- Scan scripts that detect and persist top-ranked clusters to JSON for downstream analysis or dashboards.

## Analytics Logic
- **Cluster identification:** Groups open-market `P` transactions by ticker within a rolling 10-day window (configurable) and flags a cluster when the third unique insider appears. Windows carry `signal_date`, `window_start/window_end`, and expire after a configurable horizon.
- **Conviction scoring:** `compute_cluster_score` blends role score, people count, log-scaled total value, fund ratio penalty, average percent holdings increase, filing speed (`days_to_file`), and sale-to-purchase ratio. Role weights come from `insider_roles.py`; classification pulls from `insider_entities` and `insider_exclusions`.
- **Feature engineering:** `feature_engineering.py` adds `days_to_file` and `sale_to_purchase_ratio`; cluster detection tracks ownership deltas to reward insiders increasing stake materially.

## Typical Workflow

```
Load SEC data → Dashboard (daily screening) → Deep-dive with scan/enrich/backtest
```

1. **Load** quarterly SEC Form 345 TSVs into the database
2. **Dashboard** — check recent insider cluster activity with historical context
3. **Scan** for cluster buy events — detects, scores, and writes JSON
4. **Enrich** the JSON with forward price data (returns, drawdowns) via Alpha Vantage
5. **Backtest** cluster signals across a date range to evaluate strategy performance

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
   - Download bulk Form 345 TSVs from [SEC EDGAR Full-Text Search](https://efts.sec.gov/LATEST/search-index?q=%22form345%22&dateRange=custom) or the [EDGAR bulk archives](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets).
   - Extract into `data/extracted/` with the naming convention `<year>q<quarter>_form345/` (e.g., `2025q3_form345/`). Each folder should contain `SUBMISSION.tsv`, `REPORTINGOWNER.tsv`, `NONDERIV_TRANS.tsv`, etc.
   - Ingest:
     ```bash
     python scripts/load_form345_quarter.py
     ```
5. **Dashboard** — quick daily screening
   ```bash
   python scripts/dashboard.py --days-back 30
   ```
   Shows recent insider cluster buys ranked by $/insider, with historical win rate context from 5 years of backtest data (4,000+ signals).

   Key flags:
   - `--days-back` (30) — lookback window
   - `--min-insiders` (2) — minimum distinct insiders
   - `--min-total-value` (100K) — minimum cluster dollar value
   - `--min-value-per-insider` (0) — floor for $/insider
   - `--max-value-per-insider` (0 = no cap) — ceiling for $/insider
   - `--window-days` (10) — rolling window size
   - `--limit` (20) — max rows to display
   - `--json` — output JSON instead of Rich table
   - `--no-sector-filter` — disable sector blocklist (blocked sectors hidden by default)
   - `--links` — print SEC EDGAR filing links below the table

   **Backtest insight:** The "Hist 90d Win%" column shows historical win rates by $/insider bucket. Signals under $50K/insider have historically outperformed (56% win rate) vs the 50% baseline. Filter for these with:
   ```bash
   python scripts/dashboard.py --days-back 90 --max-value-per-insider 50000
   ```

6. **Run cluster analysis**

   **6a. Scan clusters (JSON)**
   Scan for cluster events and output to JSON for downstream analysis or enrichment. Add `--print` to also display a formatted table in the console.
   ```bash
   python scripts/scan_clusters.py \
     --limit 50 --min-total-value 500000 --min-trade-value 50000 \
     --output-dir exports/cluster_runs --basename my_run --print
   ```
   Key flags: `--limit` (20), `--min-insiders` (2), `--min-total-value` (500K, config-driven), `--min-trade-value` (50K, config-driven), `--output-dir` (`exports/cluster_runs`), `--basename` (auto-generated slug from filter params when omitted), `--print` (console table).

   Sample JSON row:
   ```json
   {
     "ticker": "BLNE",
     "issuer_name": "Beeline Holdings, Inc.",
     "window_start": "2025-08-25",
     "window_end": "2025-09-03",
     "signal_filing_date": "2025-09-04",
     "entry_date": "2025-09-05",
     "num_insiders": 2,
     "total_value": 48765.53,
     "role_score": 5,
     "key_roles": "CFO",
     "cluster_score": 100.0,
     "avg_percent_change": 556.39,
     "avg_days_to_file": 0.83,
     "avg_sale_to_purchase_ratio": 0.0,
     "top_insiders": "Moe Christopher R. (CFO), Milton Tiffany (CAO)"
   }
   ```

   **6b. Backtest strategy**
   Backtest tradeable cluster signals over a date range using cached market prices.
   ```bash
   python scripts/backtest_cluster_strategy.py \
     --start-filing-date 2024-01-01 --end-filing-date 2025-01-01 \
     --min-total-value 500000 --min-trade-value 50000 \
     --horizons 30,60,90 --entry-delay-days 0,1,2 \
     --out-csv results.csv
   ```
   Required: `--start-filing-date`, `--end-filing-date`. Key optional flags: `--horizons` (`30,60,90`), `--entry-delay-days` (`0`), `--min-insiders` (3), `--min-total-value` (500K, config-driven), `--min-trade-value` (50K, config-driven), `--out-csv`, `--cooldown-days` (0).
7. **Enrich with Alpha Vantage prices**
   ```bash
   python scripts/enrich_clusters_with_price.py exports/cluster_runs/<export>.json
   ```

## Interpreting Results

| Column | What it means |
|--------|---------------|
| `cluster_score` | Composite conviction score (0-100). **60+** = high conviction, worth investigating. |
| `role_score` | Sum of role weights across insiders. CFO/GC = 4, VP/COO = 3, CEO = 2, Director = 1. Higher = more senior buyers. |
| `avg_percent_change` | Average % increase in each insider's holdings. Large increases (e.g., 100%+) suggest real commitment, not token buys. |
| `avg_days_to_file` | Average days between transaction and SEC filing. Lower = faster filing = more confidence. |
| `avg_sale_to_purchase_ratio` | Historical sell-vs-buy ratio for these insiders. 0.0 = pure buyers (best). High values = insiders who frequently sell. |
| `num_insiders` / `num_fund_like` | People count vs fund-like entities. Clusters dominated by funds (`max_fund_ratio` > 0.25) are filtered by default. |
| `entry_date` | First tradeable date after the signal becomes public (filing date + 1 business day). |

## Tuning Parameters

All weights and thresholds live in `src/scoring_config/scoring_weights.py` — the single source of truth.

**Key levers:**
- `ClusterThresholds.window_days` (default 10) — wider windows catch more clusters but dilute timing signal
- `ClusterThresholds.min_unique_insiders` (default 3) — raise to filter for stronger consensus
- `ClusterThresholds.min_total_value_usd` (default 500K) — dollar floor to exclude trivial buys
- `ClusterThresholds.max_fund_ratio` (default 0.25) — cap fund-like entity participation
- `ClusterScoringWeights.w_percent_change` (default 5.0) — highest-weighted factor; rewards large stake increases
- `ClusterScoringWeights.saturation_k` (default 65) — controls how quickly scores approach 100

CLI flags (`--min-cluster-score`, `--max-fund-ratio`, etc.) override config defaults per run without editing the file.

## Project Structure
- `src/` — core library (config, classification, role weighting, cluster scoring).
- `src/analytics/` — cluster detection, feature engineering, buy signal helpers, historical win rate computation.
- `src/services/` — shared service modules (CIK-ticker mapping, fast SQL cluster detection).
- `scripts/` — CLI entrypoints: `dashboard.py` (daily screening), `scan_clusters.py` (detailed analysis), `fast_scan_for_backtest.py` / `fast_enrich_backtest.py` (backtesting pipeline), data loading, and price enrichment.
- `docs/` — design notes and analytical rationale.
- `schema.sql`, `sql/` — database DDL and helper SQL.
- `data/` — extracted SEC TSVs (not tracked); `exports/` — saved cluster runs and backtest results.
- `tests/` — unit tests for scoring, classification, and historical rate computation.
