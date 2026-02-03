# External Integrations

**Analysis Date:** 2026-02-03

## APIs & External Services

**Financial Data:**
- Financial Datasets AI (`https://api.financialdatasets.ai/`) - Primary data provider for historical prices and financial metrics
  - SDK/Client: `requests` library (HTTP client)
  - Auth: `X-API-KEY` header with `FINANCIAL_DATASETS_API_KEY` env var
  - Endpoints:
    - `/prices/` - Daily OHLCV data (GET, params: ticker, interval, interval_multiplier, start_date, end_date)
    - `/financial-metrics` - Financial ratios and fundamentals (GET, params: ticker, period, limit)
  - Rate limiting: Configurable via `--rate_limit` CLI flag (default 1.0s between calls)
  - Retry logic: 3 attempts with exponential backoff (1-5s), triggered by `requests.exceptions.RequestException` or HTTP 429

**SEC EDGAR Data:**
- SEC Form 3/4/5 filings (raw source, not direct API)
  - Data format: Tab-separated values (TSV files)
  - Loading: `src/loaders/form345_loader.py` reads extracted TSV files from `data/extracted/` directory
  - Loader uses pandas + SQLAlchemy COPY command for efficient bulk insertion

**Hugging Face Hub:**
- `datasets` library - Loads datasets from Hugging Face Hub
  - Client: `huggingface_hub` package
  - Used in: `scripts/explore_sovai_features.py` (experimental feature analysis)

## Data Storage

**Databases:**
- PostgreSQL 18.1+
  - Connection: `DATABASE_URL` env var (format: `postgresql://user:password@host:port/database`)
  - Client: SQLAlchemy with psycopg2-binary driver
  - Schema: `schema.sql` (defined in repository root)
  - Tables:
    - `cluster_events` - Detected insider cluster buy events
    - `cluster_event_members` - Individual participants in clusters
    - `form345_raw` - Raw SEC filing data
    - `form345_submission`, `form345_reportingowner`, `form345_nonderiv_trans`, `form345_deriv_trans` - Parsed SEC forms
    - `insider_entities` - Insider classification cache
    - `insider_exclusions` - Fund/entity filter rules
    - `market_prices` - Cached daily prices (primary key: ticker, price_date)
    - `market_fundamentals` - Cached valuation metrics (primary key: ticker, date)

**File Storage:**
- Local filesystem only
  - Extracted SEC data: `data/extracted/` (configured via `DATA_DIR` env var)
  - Export outputs: `exports/cluster_runs/` (JSON files with cluster analysis results)
  - Logs/debugging: stderr output from scripts

**Caching:**
- PostgreSQL tables (`market_prices`, `market_fundamentals`) serve as local cache
  - Reduces API calls to Financial Datasets AI
  - Uses `INSERT ... ON CONFLICT DO NOTHING` for idempotent updates
  - Cache lookup before API request; API only fetches if cache is insufficient

## Authentication & Identity

**Auth Provider:**
- API key based (single key for Financial Datasets AI)
  - Implementation: `X-API-KEY` header in HTTP requests
  - Key source: `FINANCIAL_DATASETS_API_KEY` environment variable (required for price enrichment)
  - Scope: Only Financial Datasets AI; no user/identity layer

**No User Authentication:**
- Codebase is backend pipeline/CLI tool; no user sessions or role-based access

## Monitoring & Observability

**Error Tracking:**
- None detected - errors logged to stderr/stdout

**Logs:**
- Console output via `print()` statements to stdout/stderr
- `rich` library used for formatted terminal output (e.g., progress indicators)
- Debug output to stderr prefixed with "DEBUG:" (see `scripts/enrich_clusters_with_price.py`)
- Retry logic logs rate limiting: "Rate limit hit, retrying..." to stderr

**Telemetry:**
- Not detected

## CI/CD & Deployment

**Hosting:**
- Not specified in codebase; data processing pipeline intended for local/on-premise deployment

**CI Pipeline:**
- pytest framework available (test files in `tests/`)
- No CI configuration files detected (no `.github/workflows/`, `.gitlab-ci.yml`, etc.)
- Tests run locally via `pytest`

**Deployment:**
- Manual deployment via scripts:
  - `scripts/load_form345_quarter.py` - Ingest SEC data
  - `scripts/show_cluster_buys.py` - Display clusters
  - `scripts/export_top_clusters.py` - Export results
  - `scripts/enrich_clusters_with_price.py` - Enrich with price/fundamentals
  - `scripts/backtest_cluster_strategy.py` - Backtest performance

## Environment Configuration

**Required env vars:**
- `FINANCIAL_DATASETS_API_KEY` - API key for Financial Datasets AI (required for enrichment; error if missing)

**Optional env vars:**
- `DATABASE_URL` - PostgreSQL connection (default: `postgresql://user:pass@localhost:5432/insider_data`)
- `DATA_DIR` - SEC data directory (default: `data/extracted`)
- `FINANCIAL_METRICS_PERIOD` - Fundamentals period type (default: `quarterly`)
- `FUNDAMENTALS_MAX_LOOKBACK_DAYS` - Historical window (default: `730`)
- `FUNDAMENTALS_MAX_FORWARD_DAYS` - Forward window (default: `120`)
- `FINANCIAL_METRICS_MAX_LIMIT` - API record limit (default: `200`)
- `PRICE_LOOKAHEAD_BUFFER_DAYS` - Price fetch buffer (default: `10`)

**Secrets location:**
- `.env` file at project root (loaded via `python-dotenv` in all entry points)
- `.env` is git-ignored (in `.gitignore`)

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

## API Error Handling

**Financial Datasets AI:**
- HTTP errors logged and re-raised
- HTTP 400 with "Invalid ticker" triggers `InvalidTickerError` (caught separately to skip unsupported tickers)
- HTTP 429 (rate limit) triggers automatic retry via tenacity
- Request timeout: 10 seconds
- Retry strategy: 3 attempts, exponential backoff (1-5s)
- Parallel fetching: ThreadPoolExecutor with max_workers=2 for concurrent price + fundamentals calls

**Invalid Ticker Handling:**
- `InvalidTickerError` caught in enrichment loop
- Ticker marked as `enrichment_status: "unsupported_ticker"`
- Row still exported with error details in `enrichment_errors` field

---

*Integration audit: 2026-02-03*
