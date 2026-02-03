# Architecture

**Analysis Date:** 2026-02-03

## Pattern Overview

**Overall:** Layered event-detection pipeline with rule-based scoring and feature engineering

**Key Characteristics:**
- SEC Form 3/4/5 insider trading data ingestion from raw TSV files into PostgreSQL
- Time-windowed cluster detection identifying coordinated insider buys
- Rule-based insider classification (person vs. fund-like entity) with caching
- Composite conviction scoring combining role density, participation, filing behavior, and market dynamics
- Support for temporal correctness (lookahead-bias prevention) and market-cap adjusted scoring

## Layers

**Data Ingestion Layer:**
- Purpose: Load raw SEC Form 345 TSV files into PostgreSQL, normalize formats, cache insider classifications
- Location: `src/loaders/form345_loader.py`, `scripts/load_form345_quarter.py`, `scripts/load_quarter.py`
- Contains: File discovery, pandas TSV parsing, COPY-based bulk insert to PostgreSQL, loaded file tracking
- Depends on: SQLAlchemy engine, pandas, psycopg2
- Used by: CLI scripts that populate `form345_submission`, `form345_reportingowner`, `form345_nonderiv_trans`, `form345_deriv_trans` tables

**Database Layer:**
- Purpose: Persist raw SEC filings, normalized trades, insider classifications, and cluster results
- Location: `schema.sql` (DDL), database views and triggers
- Contains:
  - Raw filing tables: `form345_submission`, `form345_reportingowner`, `form345_nonderiv_trans`, `form345_deriv_trans`
  - Normalized views: `insider_buy_signals` (clean open-market buys), `insider_trades_with_title` (derived titles/roles)
  - Classification cache: `insider_entities` (person/fund classification), `insider_exclusions` (fund filters)
  - Cluster results: `cluster_events`, `cluster_event_members`
- Used by: All analytics modules via SQLAlchemy ORM or raw SQL queries

**Classification Layer:**
- Purpose: Determine if an insider name represents a person or fund-like entity, cache results to avoid recomputation
- Location: `src/insider_classification.py`, `src/classification_config.py`, `src/models.py`
- Contains: Rule-based classifier (FUND_TOKENS heuristics), SQLAlchemy ORM model `InsiderEntity`, caching logic with conflict resolution
- Depends on: Token matching against standardized fund/entity keywords, database persistence
- Used by: Cluster detection module to filter out fund-like entities and weight real insiders

**Feature Engineering Layer:**
- Purpose: Compute derived metrics for individual trades and clusters: filing latency, sale/purchase behavior, percent holdings change
- Location: `src/analytics/feature_engineering.py`
- Contains:
  - `calculate_days_to_file()`: delta between transaction_date and filing_date
  - `calculate_sale_to_purchase_ratio()`: rolling window-based ratio of sales to purchases per insider/ticker
- Depends on: pandas DataFrames, temporal computations with lookahead-bias safeguards
- Used by: Cluster detection to calculate average features across cluster participants

**Window Detection Layer:**
- Purpose: Identify transaction-date windows where multiple insiders buy in unison, find best-qualifying windows
- Location: `src/analytics/window_detection.py`, `src/analytics/cluster_buys.py`
- Contains:
  - `best_qualifying_window_indices()`: sliding-window search (O(n) two-pointer) to find highest-value window meeting thresholds
  - `find_cluster_buys()`: main cluster detection function with SQL window aggregation and pandas-based post-processing
  - `find_tradeable_cluster_signals()`: temporal-aware signal generation for backtesting (first-qualify vs. full-reveal modes)
- Depends on: pandas, SQLAlchemy raw SQL for efficient window computation, transaction_date bounds checking
- Used by: Cluster analysis scripts and backtesting

**Insider Role Weighting Layer:**
- Purpose: Map insider titles to conviction weights (CFO/GC > CEO > Director) to prioritize institutional insiders
- Location: `src/insider_roles.py`, `src/scoring_config/scoring_weights.py`
- Contains:
  - `ROLE_WEIGHTS` dataclass: title-to-weight mapping (0-4 scale)
  - `compute_insider_role_weight()`: lookup title in weights, fallback to officer/director flags
- Depends on: Case-insensitive title matching, weight configuration
- Used by: Cluster scoring to calculate aggregate `role_score`

**Cluster Scoring Layer:**
- Purpose: Compute composite conviction score for a cluster window using weighted formula and exponential saturation
- Location: `src/cluster_scoring.py`, `src/scoring_config/scoring_weights.py`
- Contains:
  - `compute_cluster_score()`: raw score = w_role*role_score + w_people*people + w_value*log10(value) - w_fund*fund_ratio + w_percent_change*avg_percent_change + w_days_to_file*avg_days_to_file + w_sale_to_purchase_ratio*avg_sale_to_purchase_ratio; final score = 100*(1-exp(-raw_score/K))
  - `compute_market_cap_adjusted_score()`: post-enrichment bonus based on cluster value vs. market cap
  - `SCORING_WEIGHTS` and `CLUSTER_THRESHOLDS` configurations
- Depends on: Centralized weight config, logarithmic scaling, exponential saturation normalization
- Used by: Cluster detection to rank and filter results

**Export & Enrichment Layer:**
- Purpose: Persist ranked clusters to JSON, optionally enrich with price data from Financial Datasets API
- Location: `scripts/export_top_clusters.py`, `scripts/enrich_clusters_with_price.py`, `scripts/rank_enriched_clusters.py`
- Contains: JSON serialization, price enrichment logic, performance metric calculation (forward returns, max drawdown)
- Depends on: Financial Datasets API client, datetime calculations for return windows
- Used by: Downstream analysis, backtesting

## Data Flow

**Ingestion Flow:**

1. SEC Form 345 TSVs (from `data/extracted/{PERIOD}_form345/`) are discovered
2. `load_form345_quarter.py` reads each TSV with pandas, normalizes column names
3. Data is streamed via psycopg2 COPY to PostgreSQL `form345_*` tables
4. Loaded files are logged in `loaded_to_db.txt` to prevent re-ingestion
5. Database views (`insider_buy_signals`) filter to open-market buys and enrich with derived fields

**Cluster Detection Flow:**

1. `find_cluster_buys()` receives query parameters (window_days, lookback_days, min_insiders, min_cluster_score, etc.)
2. SQL query fetches `insider_buy_signals` within date range, applies exclusion rules, creates transaction-date windows
3. Base dataframe is normalized: insider names cleaned, transaction/filing dates converted, numeric types enforced
4. Feature engineering layer adds `days_to_file` and `sale_to_purchase_ratio` per insider
5. Filing-level percent change calculated: `(shares_bought) / (prior_holdings)` with cap at 1.0 for new positions
6. Insider classification fetched/created in `insider_entities` table (person vs. fund)
7. Windows merged by ticker to handle overlapping periods
8. For each merged window:
   - Grouped by normalized insider name
   - Role weights summed, key roles (CFO/GC/CEO) identified
   - Cluster score computed using `compute_cluster_score()`
   - Filters applied (min_role_score, min_cluster_score, max_fund_ratio)
9. Results sorted by cluster_score descending, returned as pandas DataFrame

**Tradeable Signal Flow:**

1. `find_tradeable_cluster_signals()` iterates by filing_date (chronologically)
2. For each filing_date, computes best-qualifying window using revealed data only (no lookahead)
3. `best_qualifying_window_indices()` finds sliding window with highest value meeting thresholds
4. If `signal_mode="first_qualify"`, signal_filing_date = first date cluster meets criteria (tradable)
5. If `signal_mode="full_reveal"`, signal_filing_date = max filing_date for window trades (benchmark, not tradable)
6. Cluster score/filters re-applied at signal time for temporal consistency
7. Cooldown logic prevents rapid re-signaling on same ticker
8. Records streamed to results DataFrame, sorted by signal_filing_date ascending

**State Management:**

- **Mutable State:** PostgreSQL tables (`insider_entities`, `insider_buy_signals`, `cluster_events`)
- **Immutable Pipeline:** TSV input → SQL aggregation → pandas transformation → scoring → export
- **Caching:** Insider classifications cached in `insider_entities` with conflict resolution (upsert on normalized_name)
- **Temporal Integrity:** Lookahead bias prevented by filtering to `filing_date <= signal_date` when computing features

## Key Abstractions

**ClusterBuyEvent:**
- Purpose: Lightweight dataclass representing a single cluster event
- Examples: `src/analytics/cluster_buys.py` line 146-155
- Pattern: Simple value object, used for type hints but results returned as DataFrame rows

**InsiderEntity (ORM Model):**
- Purpose: Persistent record of insider classification with confidence scores and audit trail
- Examples: `src/models.py` line 15-34
- Pattern: SQLAlchemy declarative base with unique constraint on normalized_name, timestamps for tracking updates

**RoleWeights & ScoringWeights (Dataclasses):**
- Purpose: Centralized, versioned configuration for weights and thresholds
- Examples: `src/scoring_config/scoring_weights.py`
- Pattern: Immutable dataclass with `.as_dict()` method for runtime lookups, enables A/B testing by swapping config

**FundTokens & ClassificationConfig:**
- Purpose: Curated list of fund entity indicators and confidence thresholds
- Examples: `src/classification_config.py`
- Pattern: Module-level constants imported by classifier, avoids hardcoding in logic

## Entry Points

**Data Loading:**
- Location: `scripts/load_form345_quarter.py`
- Triggers: `python scripts/load_form345_quarter.py` or `python scripts/load_quarter.py <path>`
- Responsibilities: Discover TSV files, parse, bulk-insert, log completion

**Cluster Analysis (Console):**
- Location: `scripts/show_cluster_buys.py`
- Triggers: CLI with args `--window-days`, `--lookback-days`, `--min-insiders`, `--min-cluster-score`, `--max-fund-ratio`
- Responsibilities: Call `get_top_cluster_buys()`, format results with rich/tabulate, display in terminal

**Cluster Export:**
- Location: `scripts/export_top_clusters.py`
- Triggers: CLI with `--limit` parameter
- Responsibilities: Call `find_cluster_buys()`, serialize top results to JSON with timestamp

**Price Enrichment:**
- Location: `scripts/enrich_clusters_with_price.py`
- Triggers: `python scripts/enrich_clusters_with_price.py <json_export_path>`
- Responsibilities: Load JSON, fetch OHLCV from Financial Datasets API, append price/return columns, save enriched JSON

**Backtesting:**
- Location: `scripts/backtest_cluster_strategy.py`
- Triggers: CLI with date ranges and strategy parameters
- Responsibilities: Call `find_tradeable_cluster_signals()`, fetch price data, compute returns, output performance metrics

## Error Handling

**Strategy:** Defensive data type coercion with sensible defaults (fillna, errors='coerce'), validation guardrails, graceful degradation

**Patterns:**

- **Type Coercion:** `pd.to_numeric(..., errors='coerce').fillna(0.0)` for numeric columns; `str(...).strip()` for text
- **Date Validation:** Malformed transaction dates (e.g., year "0024") filtered using min_transaction_date guardrail (1990-01-01)
- **Missing Data:** Insider_relationship/title default to empty strings; missing fields fillna with appropriate zero/empty values
- **Database Conflicts:** IntegrityError on duplicate normalized_name caught and resolved by querying existing record (upsert pattern)
- **SQL Parameter Binding:** All user input passed via parameterized queries (`:param` style) to prevent injection
- **Empty Result Sets:** Functions return empty DataFrames with matching schema rather than None or exceptions

## Cross-Cutting Concerns

**Logging:** Console output via `print()` in scripts, SQL queries logged via SQLAlchemy if echo=True enabled, no persistent logs

**Validation:**
- Insider names normalized to uppercase with whitespace stripped
- Numeric columns validated via pandas to_numeric with coercion
- Transaction dates bounded [1990-01-01, signal_date] to catch malformed SEC data
- Cluster filters applied post-scoring: min_insiders, min_role_score, min_cluster_score, max_fund_ratio

**Authentication:** Database connection via DATABASE_URL environment variable (PostgreSQL default or SQLite for lightweight runs)

**Temporal Consistency (Critical):**
- Feature calculations respect signal_filing_date boundary to prevent lookahead bias
- `calculate_sale_to_purchase_ratio()` applied within lookup window per insider
- Market cap adjustment applied only post-enrichment, not at signal time
- Cooldown logic in tradeable signals prevents rapid re-entry
