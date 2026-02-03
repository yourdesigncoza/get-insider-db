# Codebase Structure

**Analysis Date:** 2026-02-03

## Directory Layout

```
get-insider-db/
├── src/                           # Core library modules
│   ├── analytics/                 # Cluster detection, feature engineering, window search
│   ├── loaders/                   # SEC Form 345 TSV ingestion
│   ├── scoring_config/            # Centralized weights and thresholds
│   ├── config.py                  # Database connection, environment config
│   ├── models.py                  # SQLAlchemy ORM (InsiderEntity)
│   ├── cluster_scoring.py         # Composite conviction score calculation
│   ├── insider_classification.py  # Person vs. fund classification
│   ├── insider_roles.py           # Title-to-weight mapping
│   └── classification_config.py   # Fund token list and confidence thresholds
├── scripts/                       # CLI entry points for analysis, export, enrichment
├── tests/                         # Unit tests for scoring and classification
├── sql/                           # SQL helper scripts (supplementary)
├── schema.sql                     # PostgreSQL DDL for all tables and views
├── data/                          # Extracted SEC TSV files (not tracked)
├── exports/                       # Saved cluster run exports as JSON
├── docs/                          # Design notes and analytical documentation
├── .env                           # Environment variables (DATABASE_URL, API keys)
├── .gitignore                     # Excludes data, exports, venv, __pycache__
├── requirements.txt               # Python dependencies
└── README.md                      # Project overview and usage guide
```

## Directory Purposes

**src/**
- Purpose: Production library code shared across scripts and tests
- Contains: Core analytics, classification, scoring, data loading logic
- Key files: `cluster_scoring.py`, `insider_classification.py`, `analytics/cluster_buys.py`

**src/analytics/**
- Purpose: Cluster detection algorithm, feature engineering, window search utilities
- Contains:
  - `cluster_buys.py`: Main `find_cluster_buys()` and `find_tradeable_cluster_signals()` functions
  - `cluster_service.py`: High-level cluster operations
  - `feature_engineering.py`: `calculate_days_to_file()`, `calculate_sale_to_purchase_ratio()`
  - `window_detection.py`: `best_qualifying_window_indices()` sliding-window search
  - `buy_signals.py`: Helpers for deriving buy signal features
- Key files: `src/analytics/cluster_buys.py` (main detection logic, 982 lines)

**src/loaders/**
- Purpose: SEC Form 345 TSV file discovery and bulk loading into PostgreSQL
- Contains:
  - `form345_loader.py`: `load_file()`, `load_quarter()`, `discover_tsvs()` utilities
- Used by: `scripts/load_form345_quarter.py`, `scripts/load_quarter.py`

**src/scoring_config/**
- Purpose: Single source of truth for all tunable scoring weights and thresholds
- Contains:
  - `scoring_weights.py`: `RoleWeights`, `ClusterScoringWeights`, `ClusterThresholds` dataclasses
- Used by: `src/cluster_scoring.py`, `src/insider_roles.py`, all scoring/filtering logic

**scripts/**
- Purpose: CLI entry points for end-to-end pipeline operations
- Key files:
  - `load_form345_quarter.py`: Discover and ingest all quarterly TSVs from data/extracted/
  - `load_quarter.py`: Load a single quarter directory
  - `show_cluster_buys.py`: Display top clusters in console with configurable filters
  - `export_top_clusters.py`: Persist ranked clusters to JSON export with timestamp
  - `enrich_clusters_with_price.py`: Fetch price data from Financial Datasets API, append returns/drawdowns
  - `backtest_cluster_strategy.py`: Evaluate cluster signals over historical date ranges
  - `rank_enriched_clusters.py`: Re-rank enriched clusters by performance metrics

**tests/**
- Purpose: Unit and integration tests for core modules
- Contains: Test modules for `cluster_scoring`, `insider_classification`, `insider_roles`
- Pattern: Tests co-located with test discovery convention (pytest)

**sql/**
- Purpose: Supplementary SQL helper scripts (not core to pipeline)
- Contains: Diagnostic queries, data exploration, manual maintenance scripts

**data/**
- Purpose: Input directory for extracted SEC Form 3/4/5 TSV files
- Structure:
  - `data/extracted/{PERIOD}_form345/` subdirectories (e.g., `2025q1_form345/`, `2024q4_form345/`)
  - Each contains: `SUBMISSION.tsv`, `REPORTINGOWNER.tsv`, `NONDERIV_TRANS.tsv`, `DERIV_TRANS.tsv`
- Generated: No (source data, downloaded externally)
- Committed: No (excluded by .gitignore)

**exports/**
- Purpose: Output directory for saved cluster runs
- Structure: `cluster_runs/` subdirectory with JSON files named `cluster_run_{TIMESTAMP}.json`
- Generated: Yes (by `export_top_clusters.py`)
- Committed: No (excluded by .gitignore)

**docs/**
- Purpose: Design documentation and analytical rationale
- Key files: `CLUSTER_SCORING.md` (scoring methodology), architecture and feature notes

**.env**
- Purpose: Environment variable configuration (DATABASE_URL, API keys)
- Not tracked by git
- Example content: `DATABASE_URL=postgresql://user:pass@localhost:5432/insider_data`

**schema.sql**
- Purpose: Complete PostgreSQL DDL for all tables, views, sequences, indexes
- Contains:
  - Raw tables: `form345_submission`, `form345_reportingowner`, `form345_nonderiv_trans`, `form345_deriv_trans`
  - Classification cache: `insider_entities`, `insider_exclusions`
  - Results tables: `cluster_events`, `cluster_event_members`
  - Derived views: `insider_buy_signals`, `insider_trades_with_title`, `cluster_events_active_window`

## Key File Locations

**Entry Points:**
- `scripts/load_form345_quarter.py`: Ingest all quarterly data
- `scripts/show_cluster_buys.py`: Display clusters in console
- `scripts/export_top_clusters.py`: Export clusters to JSON
- `scripts/enrich_clusters_with_price.py`: Add price enrichment
- `scripts/backtest_cluster_strategy.py`: Backtest performance

**Configuration:**
- `.env`: Database URL, API keys
- `src/config.py`: Programmatic database/data directory configuration
- `src/scoring_config/scoring_weights.py`: All weights and thresholds

**Core Logic:**
- `src/analytics/cluster_buys.py`: Main cluster detection algorithm
- `src/cluster_scoring.py`: Conviction score formula
- `src/insider_classification.py`: Person vs. fund classification
- `src/insider_roles.py`: Title-to-weight mapping

**Data Models:**
- `src/models.py`: SQLAlchemy ORM (InsiderEntity only; most schema driven by raw SQL)
- `schema.sql`: Complete database schema

**Testing:**
- `tests/`: pytest-discoverable test modules

## Naming Conventions

**Files:**
- `snake_case.py`: Python module files
- `UPPERCASE.md`: Documentation
- `schema.sql`: Database DDL
- `*_loader.py`: Data ingestion modules
- `*_scoring.py`, `*_classification.py`, `*_roles.py`: Domain-specific logic modules

**Directories:**
- `src/`: Production code (non-executable)
- `scripts/`: Executable CLI entry points
- `src/analytics/`: Analytical algorithms sub-package
- `src/loaders/`: Data ingestion sub-package
- `src/scoring_config/`: Configuration sub-package
- `data/extracted/`: Input TSV staging area
- `exports/cluster_runs/`: Output JSON staging area

**Functions:**
- `snake_case()`: All functions use snake_case
- `compute_*()`: Functions that calculate metrics (e.g., `compute_cluster_score()`)
- `find_*()`: Functions that query/search (e.g., `find_cluster_buys()`)
- `get_*()`: Functions that fetch cached/stored data (e.g., `get_engine()`)
- `calculate_*()`: Functions that derive features (e.g., `calculate_days_to_file()`)
- `normalize_*()`: Functions that standardize input (e.g., `normalize_insider_name()`)
- `classify_*()`: Functions that categorize (e.g., `classify_insider_by_rules()`)

**Variables:**
- `snake_case`: All variables, column names, database identifiers
- `UPPERCASE`: Module-level constants (e.g., `DATABASE_URL`, `FUND_TOKENS`, `ROLE_WEIGHTS`)
- Prefixes for clarity:
  - `is_*`: Boolean flags (e.g., `is_fund_like`, `is_officer`)
  - `*_date`: Date columns (e.g., `transaction_date`, `filing_date`, `signal_filing_date`)
  - `*_score`: Numeric scoring fields (e.g., `role_score`, `cluster_score`)

**Database Identifiers:**
- `snake_case`: Table and column names (PostgreSQL convention)
- `insider_buy_signals`: Derived view of open-market buys
- `insider_entities`: Insider classification cache table
- `form345_*`: Raw SEC filing tables (prefixed by form type)

## Where to Add New Code

**New Feature (e.g., new scoring factor):**
- Add weight to `src/scoring_config/scoring_weights.py` (ClusterScoringWeights dataclass)
- Update formula in `src/cluster_scoring.py` (compute_cluster_score function)
- Add feature calculation to `src/analytics/feature_engineering.py` if temporal
- Add tests in `tests/test_cluster_scoring.py`

**New Component/Module (e.g., new classifier):**
- Create `src/new_domain_name.py` with public functions
- Import dependencies from `src/config.py`, `src/models.py` as needed
- Add type hints and docstrings
- Create corresponding test file `tests/test_new_domain_name.py`

**New Script/CLI Tool:**
- Create `scripts/new_tool_name.py` with argparse CLI
- Import from `src/` modules
- Include sys.path hack if needed for direct execution
- Add to README.md usage section

**Utilities (shared helpers):**
- Add to `src/analytics/` if algorithmic (e.g., window search, feature calculation)
- Add to `src/` root if cross-cutting (e.g., classification, config)
- Prefer functions over classes; use dataclasses only for value objects

**Database Changes:**
- Update `schema.sql` with new tables/views/indexes
- Migrate using raw SQL: `psql $DATABASE_URL -f migration.sql`
- Document breaking changes in README.md setup section

**Tests:**
- Co-locate with source: Create `tests/test_<module_name>.py` for `src/<module_name>.py`
- Use pytest fixtures for common setup (database sessions, mock data)
- Test public functions; private functions (_prefixed) tested implicitly
- Aim for >80% coverage on critical paths (scoring, classification, window detection)

## Special Directories

**data/extracted/**
- Purpose: Input staging for SEC Form 345 TSV files
- Generated: No (downloaded from SEC, unzipped locally)
- Committed: No (excluded by .gitignore)
- Structure: Expects subdirectories like `2025q1_form345/`, `2024q4_form345/` with TSV files

**exports/cluster_runs/**
- Purpose: Output staging for JSON cluster exports
- Generated: Yes (by scripts/export_top_clusters.py)
- Committed: No (excluded by .gitignore)
- Format: JSON files with timestamp: `cluster_run_20250203_143022.json`

**.pytest_cache/**
- Purpose: pytest cache for test collection speedup
- Generated: Yes (automatically by pytest)
- Committed: No (excluded by .gitignore)

**.venv/**
- Purpose: Python virtual environment
- Generated: Yes (by `python -m venv .venv`)
- Committed: No (excluded by .gitignore)
- Activate: `source .venv/bin/activate`

**.planning/codebase/**
- Purpose: GSD codebase mapping documents
- Generated: Yes (by `/gsd:map-codebase` command)
- Committed: Yes (planning docs tracked)
- Consumed by: `/gsd:plan-phase` and `/gsd:execute-phase` commands
