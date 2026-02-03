# Technology Stack

**Analysis Date:** 2026-02-03

## Languages

**Primary:**
- Python 3.13.5 - All business logic, data processing, and analysis pipelines

## Runtime

**Environment:**
- Python 3.13.5
- Virtual environment: `.venv/` directory

**Package Manager:**
- pip
- Lockfile: `requirements.txt` (pinned versions)

## Frameworks

**Core Data Processing:**
- pandas - Data manipulation, transformation, and analysis across all pipelines
- SQLAlchemy 2.0+ - ORM and SQL abstraction layer for database operations

**Database:**
- psycopg2-binary - PostgreSQL adapter for Python

**Testing:**
- pytest - Test runner and framework (used in `tests/` directory)

**HTTP/API:**
- requests - HTTP client for external API calls (Financial Datasets AI)

**Retry & Resilience:**
- tenacity - Automatic retry logic with exponential backoff for API calls

**Utilities:**
- python-dotenv - Environment variable loading from `.env` files
- python-dateutil - Date/time utilities (relativedelta for month calculations)
- rich - Terminal formatting and progress output
- tabulate - Console table printing for display
- huggingface_hub - Hugging Face datasets library integration
- datasets - Dataset loading from Hugging Face Hub

## Key Dependencies

**Critical:**
- SQLAlchemy (2.0+) - Database abstraction; supports both PostgreSQL and SQLite
- pandas - Core data analysis and manipulation engine
- requests - External API communication with retry logic
- tenacity - Ensures resilient API calls with automatic exponential backoff

**Infrastructure:**
- psycopg2-binary - PostgreSQL connectivity
- python-dotenv - Configuration from environment files

## Configuration

**Environment:**
- `.env` file at project root with:
  - `DATABASE_URL` - PostgreSQL connection string (default: `postgresql://user:pass@localhost:5432/insider_data`)
  - `DATA_DIR` - Directory path for extracted SEC data (default: `data/extracted`)
  - `FINANCIAL_DATASETS_API_KEY` - API key for Financial Datasets AI price/fundamentals endpoint
  - `FINANCIAL_METRICS_PERIOD` - Period type for financial metrics (quarterly|annual|ttm, default: quarterly)
  - `FUNDAMENTALS_MAX_LOOKBACK_DAYS` - Historical lookback window for fundamentals (default: 730 days)
  - `FUNDAMENTALS_MAX_FORWARD_DAYS` - Forward-looking window for fundamentals (default: 120 days)
  - `FINANCIAL_METRICS_MAX_LIMIT` - Maximum records to fetch per API call (default: 200)
  - `PRICE_LOOKAHEAD_BUFFER_DAYS` - Buffer days beyond target date for price fetching (default: 10 days)

**Build/Runtime:**
- No build step required
- Scripts run via `python -m` or direct CLI invocation
- Database schema initialized via `schema.sql`

## Platform Requirements

**Development:**
- Python 3.13+
- PostgreSQL 18.1+ (or SQLite for lightweight testing)
- psycopg2 drivers installed
- Standard Unix tools (bash, grep, etc.)
- Network access to Financial Datasets AI API

**Production:**
- PostgreSQL 18.1+ database (as per schema version in `schema.sql`)
- Python 3.13+ runtime
- API key for Financial Datasets AI (`https://api.financialdatasets.ai/`)
- Extracted SEC Form 3/4/5 TSV files in `data/extracted/` directory

## Database

**Primary Database:**
- PostgreSQL 18.1+
  - Connection: via `DATABASE_URL` environment variable
  - ORM: SQLAlchemy declarative models in `src/models.py`
  - Schema: Defined in `schema.sql` (20KB dump with tables: `cluster_events`, `cluster_event_members`, `form345_raw`, `form345_submission`, `form345_reportingowner`, `form345_nonderiv_trans`, `form345_deriv_trans`, `insider_entities`, `insider_exclusions`, `market_prices`, `market_fundamentals`)

**Caching Tables:**
- `market_prices` - Cached historical daily price data (ticker, date, close_price)
- `market_fundamentals` - Cached financial metrics (ticker, date, market_cap, enterprise_value, pe_ratio, pb_ratio, trailing_peg_ratio)

**Fallback:**
- SQLite support available for development/testing (SQLAlchemy supports both dialects)

---

*Stack analysis: 2026-02-03*
