# Phase 01: Security Hardening & Data Integrity - Research

**Researched:** 2026-02-05
**Domain:** Security (SQL injection, secrets management, API resilience)
**Confidence:** HIGH

## Summary

Phase 01 addresses critical security vulnerabilities and data integrity issues in the insider trading pipeline. The primary concerns are:

1. **SQL injection via f-string interpolation** in `cluster_buys.py` - The `window_interval` parameter is directly interpolated into SQL strings using f-strings, bypassing SQLAlchemy's parameterization
2. **Silent data fallthroughs** in `enrich_clusters_with_price.py` - API failures result in DEBUG prints rather than explicit error handling
3. **No YFinance fallback** - Single point of failure when Financial Datasets API is unavailable
4. **Rate limiting disabled by default** - `RATE_LIMIT_SECONDS = 0.0` allows API hammering
5. **No pre-commit hooks** - No protection against accidentally committing `.env` files

**Primary recommendation:** Fix SQL injection immediately using PostgreSQL's `INTERVAL` with bound parameters, add explicit error handling with structured logging, implement YFinance fallback, and set up pre-commit hooks with detect-secrets.

## Standard Stack

The established libraries/tools for this domain:

### Core (Already in Use)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.x | Database ORM/queries | Industry standard, parameterized query support |
| tenacity | 8.x | Retry logic | Already used, exponential backoff support |
| python-dotenv | 1.x | Environment management | Already used for secrets |

### Required Additions
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| yfinance | 0.2.x | Yahoo Finance API | Fallback when Financial Datasets API fails |
| pre-commit | 3.x | Git hooks framework | Development workflow, secret detection |
| detect-secrets | 1.5.x | Secret scanning | Pre-commit hook for .env detection |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| yfinance | alpha_vantage | yfinance is free, alpha_vantage has rate limits |
| detect-secrets | gitleaks | detect-secrets has better Python ecosystem integration |
| detect-secrets | trufflehog | detect-secrets lighter weight, sufficient for .env files |

**Installation:**
```bash
pip install yfinance pre-commit detect-secrets
```

## Architecture Patterns

### SQL Injection Fix Pattern

**What:** Replace f-string INTERVAL interpolation with parameterized queries
**When to use:** All dynamic SQL with user-controlled or config-controlled values
**Current problematic code:**
```python
# VULNERABLE - from cluster_buys.py:225
query = f"""
    (b.transaction_date - INTERVAL '{window_interval} day')::date AS window_start,
"""
```

**Fixed pattern:**
```python
# SECURE - parameterized query
# Source: https://docs.sqlalchemy.org/en/20/faq/sqlexpressions.html
from sqlalchemy import text

query = """
    (b.transaction_date - INTERVAL '1 day' * :window_interval)::date AS window_start,
"""
params = {"window_interval": window_interval}
df = pd.read_sql_query(text(query), engine, params=params)
```

**PostgreSQL INTERVAL with parameters:**
```sql
-- PostgreSQL allows multiplying interval by integer
-- These are equivalent:
INTERVAL '10 day'
INTERVAL '1 day' * 10
-- The second form allows parameterization
```

### YFinance Fallback Pattern

**What:** Try primary API, fallback to YFinance on failure
**When to use:** Any price/fundamental data fetching
**Example:**
```python
# Source: https://ranaroussi.github.io/yfinance/reference/index.html
import yfinance as yf
from typing import Optional
from datetime import date

def fetch_price_with_fallback(
    ticker: str,
    target_date: date,
    primary_api_key: Optional[str] = None
) -> Optional[float]:
    """Fetch price from primary API, fallback to YFinance."""

    # Try primary API first
    if primary_api_key:
        try:
            price = fetch_from_financial_datasets(ticker, target_date)
            if price is not None:
                return price
        except (InvalidTickerError, requests.exceptions.RequestException) as e:
            logger.warning(f"Primary API failed for {ticker}: {e}, trying YFinance")

    # Fallback to YFinance
    try:
        stock = yf.Ticker(ticker)
        # Fetch 5 days around target to handle weekends/holidays
        start = target_date - timedelta(days=5)
        end = target_date + timedelta(days=1)
        hist = stock.history(start=start, end=end, auto_adjust=True, repair=True)

        if hist.empty:
            logger.warning(f"YFinance returned no data for {ticker}")
            return None

        # Get closest date <= target_date
        hist.index = hist.index.date
        valid_dates = [d for d in hist.index if d <= target_date]
        if not valid_dates:
            return None
        closest = max(valid_dates)
        return float(hist.loc[closest, 'Close'])

    except Exception as e:
        logger.error(f"YFinance fallback failed for {ticker}: {e}")
        return None
```

### Explicit Error Handling Pattern

**What:** Replace silent DEBUG prints with explicit error tracking
**When to use:** Any API call that can fail
**Current problematic code:**
```python
# PROBLEMATIC - from enrich_clusters_with_price.py:499-509
if not last_records_count:
    print(f"DEBUG: No fundamentals records returned for {ticker} from API.", file=sys.stderr)
    return None
```

**Fixed pattern:**
```python
# EXPLICIT - with structured logging and metrics
import logging
from dataclasses import dataclass
from typing import Dict, List

logger = logging.getLogger(__name__)

@dataclass
class EnrichmentStats:
    total_clusters: int = 0
    price_success: int = 0
    price_primary_fail: int = 0
    price_fallback_success: int = 0
    price_total_fail: int = 0
    fundamentals_success: int = 0
    fundamentals_fail: int = 0
    failed_tickers: List[str] = None

    def __post_init__(self):
        self.failed_tickers = []

def fetch_fundamentals_with_tracking(
    ticker: str,
    target_date: date,
    stats: EnrichmentStats
) -> Optional[Dict]:
    """Fetch fundamentals with explicit tracking."""
    try:
        result = _fetch_fundamentals_internal(ticker, target_date)
        if result is None:
            stats.fundamentals_fail += 1
            stats.failed_tickers.append(ticker)
            logger.warning(
                f"No fundamentals data for {ticker} near {target_date}",
                extra={"ticker": ticker, "target_date": str(target_date)}
            )
        else:
            stats.fundamentals_success += 1
        return result
    except Exception as e:
        stats.fundamentals_fail += 1
        stats.failed_tickers.append(ticker)
        logger.error(
            f"Fundamentals fetch failed for {ticker}: {e}",
            extra={"ticker": ticker, "error": str(e)}
        )
        return None

# At end of enrichment run
def report_enrichment_stats(stats: EnrichmentStats) -> None:
    """Report final enrichment statistics."""
    total = stats.price_success + stats.price_total_fail
    success_rate = (stats.price_success / total * 100) if total > 0 else 0

    logger.info(
        f"Enrichment complete: {stats.price_success}/{total} prices ({success_rate:.1f}%), "
        f"{stats.fundamentals_success} fundamentals"
    )

    if stats.failed_tickers:
        logger.warning(f"Failed tickers: {stats.failed_tickers[:20]}...")  # First 20
```

### Pre-commit Hook Configuration

**What:** Git pre-commit hooks for secret detection
**When to use:** All repositories with secrets/credentials
**Example `.pre-commit-config.yaml`:**
```yaml
# Source: https://github.com/Yelp/detect-secrets
repos:
  # Standard hooks
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: check-added-large-files
      - id: check-yaml
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-merge-conflict

  # Secret detection
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
        exclude: package-lock.json

  # Additional .env protection
  - repo: local
    hooks:
      - id: check-env-files
        name: Check for .env files
        entry: bash -c 'git diff --cached --name-only | grep -E "^\.env" && echo "ERROR: .env file detected in commit" && exit 1 || exit 0'
        language: system
        pass_filenames: false
```

**Setup commands:**
```bash
# Install pre-commit
pip install pre-commit detect-secrets

# Create baseline (one-time)
detect-secrets scan > .secrets.baseline

# Install hooks
pre-commit install

# Test run
pre-commit run --all-files
```

### Rate Limiting Pattern

**What:** Enforce minimum delay between API requests
**When to use:** Any external API with rate limits
**Current code (needs fix):**
```python
# PROBLEMATIC - default is 0, easily bypassed
RATE_LIMIT_SECONDS = 0.0
```

**Fixed pattern:**
```python
# SECURE - enforce minimum rate limit
import os
from functools import wraps
import time
import threading

# Default to 0.5 seconds (2 req/sec) - conservative for most APIs
DEFAULT_RATE_LIMIT = 0.5
MIN_RATE_LIMIT = 0.1  # Never allow faster than 10 req/sec

def get_rate_limit() -> float:
    """Get rate limit with enforced minimum."""
    env_value = os.getenv("RATE_LIMIT_SECONDS", str(DEFAULT_RATE_LIMIT))
    try:
        value = float(env_value)
        return max(value, MIN_RATE_LIMIT)
    except ValueError:
        return DEFAULT_RATE_LIMIT

RATE_LIMIT_SECONDS = get_rate_limit()
_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_TIME = 0.0

def rate_limited(func):
    """Decorator to enforce rate limiting."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        global _LAST_REQUEST_TIME
        with _REQUEST_LOCK:
            now = time.time()
            elapsed = now - _LAST_REQUEST_TIME
            if elapsed < RATE_LIMIT_SECONDS:
                time.sleep(RATE_LIMIT_SECONDS - elapsed)
            _LAST_REQUEST_TIME = time.time()
        return func(*args, **kwargs)
    return wrapper
```

### Anti-Patterns to Avoid
- **F-string SQL:** Never use f-strings or `.format()` with SQL queries
- **Silent failures:** Never use `print()` for error conditions that affect data
- **Hardcoded rate limits:** Always use environment variables with safe defaults
- **Single API dependency:** Critical data paths need fallbacks

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rate limiting | Custom sleep logic | `ratelimit` or `tenacity` decorators | Thread-safe, tested edge cases |
| Secret detection | Regex patterns | `detect-secrets` | Handles entropy, multiple formats |
| Price data fallback | Custom scraping | `yfinance` | Handles splits, dividends, corporate actions |
| Pre-commit hooks | Shell scripts | `pre-commit` framework | Cross-platform, versioned, easy updates |
| SQL parameterization | Manual escaping | SQLAlchemy `text()` + params | Handles all edge cases, DB-specific |

**Key insight:** Security code is especially dangerous to hand-roll because edge cases are invisible until exploited.

## Common Pitfalls

### Pitfall 1: PostgreSQL INTERVAL Parameterization
**What goes wrong:** Directly using `:interval` placeholder doesn't work with PostgreSQL INTERVAL type
**Why it happens:** PostgreSQL INTERVAL requires special syntax, can't bind directly
**How to avoid:** Use `INTERVAL '1 day' * :days` pattern (multiply unit interval by integer)
**Warning signs:** SQL errors about type mismatch or invalid interval

### Pitfall 2: YFinance Data Gaps
**What goes wrong:** YFinance returns empty DataFrame for valid tickers on weekends/holidays
**Why it happens:** No trading data exists for those dates
**How to avoid:** Always request a date range (5-day buffer), find closest valid date
**Warning signs:** Intermittent None returns, especially Mondays

### Pitfall 3: Pre-commit Bypass
**What goes wrong:** Developers use `--no-verify` to skip hooks
**Why it happens:** Hooks are slow or blocking legitimate commits
**How to avoid:** Keep hooks fast (<5 seconds), use CI as backup layer
**Warning signs:** Secrets found in CI that weren't caught locally

### Pitfall 4: Rate Limit Race Conditions
**What goes wrong:** Concurrent threads exceed rate limit
**Why it happens:** Thread-local timing without locks
**How to avoid:** Use threading.Lock for shared rate limit state
**Warning signs:** 429 errors despite rate limiting code

### Pitfall 5: Silent API Failures Masquerading as "No Data"
**What goes wrong:** Network errors, auth failures return None same as "no data exists"
**Why it happens:** Broad exception handling conflates error types
**How to avoid:** Separate "data not found" from "request failed" with distinct exceptions
**Warning signs:** Sudden drops in enrichment success rates

## Code Examples

### SQL Injection Fix - Full Implementation

```python
# Source: SQLAlchemy 2.0 docs + PostgreSQL interval docs
from sqlalchemy import text
import pandas as pd

def get_cluster_signals_secure(
    engine,
    start_date,
    end_date,
    window_interval: int,  # Days as integer
    min_insiders: int,
    min_total_value: float,
    ticker: str = None,
):
    """Fetch cluster signals with parameterized queries."""

    # Build optional clauses safely
    ticker_filter = "AND s.ticker = :ticker" if ticker else ""

    # Note: window_interval is multiplied with INTERVAL, not interpolated
    query = f"""
        WITH base AS (
            SELECT s.*
            FROM insider_buy_signals s
            WHERE s.filing_date BETWEEN :start_date AND :end_date
              AND s.ticker IS NOT NULL
              {ticker_filter}
        ),
        computed AS (
            SELECT
                b.ticker,
                (b.transaction_date - INTERVAL '1 day' * :window_interval)::date AS window_start,
                b.transaction_date::date AS window_end,
                (
                    SELECT COUNT(DISTINCT b2.insider_name)
                    FROM base b2
                    WHERE b2.ticker = b.ticker
                      AND b2.transaction_date BETWEEN
                          b.transaction_date - INTERVAL '1 day' * :window_interval
                          AND b.transaction_date
                ) AS num_insiders,
                (
                    SELECT SUM(b2.total_value)
                    FROM base b2
                    WHERE b2.ticker = b.ticker
                      AND b2.transaction_date BETWEEN
                          b.transaction_date - INTERVAL '1 day' * :window_interval
                          AND b.transaction_date
                ) AS total_value
            FROM base b
        )
        SELECT * FROM computed
        WHERE num_insiders >= :min_insiders
          AND total_value >= :min_total_value
    """

    params = {
        "start_date": start_date,
        "end_date": end_date,
        "window_interval": window_interval,  # Passed as parameter, not interpolated
        "min_insiders": min_insiders,
        "min_total_value": min_total_value,
    }
    if ticker:
        params["ticker"] = ticker

    return pd.read_sql_query(text(query), engine, params=params)
```

### YFinance Integration

```python
# Source: https://ranaroussi.github.io/yfinance/reference/index.html
import yfinance as yf
from datetime import date, timedelta
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class PriceProvider:
    """Multi-source price provider with fallback."""

    def __init__(self, primary_api_key: Optional[str] = None):
        self.primary_api_key = primary_api_key
        self._yf_cache: Dict[str, yf.Ticker] = {}

    def get_yf_ticker(self, symbol: str) -> yf.Ticker:
        """Get cached YFinance Ticker object."""
        if symbol not in self._yf_cache:
            self._yf_cache[symbol] = yf.Ticker(symbol)
        return self._yf_cache[symbol]

    def fetch_price(
        self,
        ticker: str,
        target_date: date,
        use_fallback: bool = True
    ) -> Optional[float]:
        """
        Fetch closing price for ticker on target_date.

        Args:
            ticker: Stock symbol
            target_date: Date to fetch price for
            use_fallback: Whether to try YFinance on primary failure

        Returns:
            Closing price or None if unavailable
        """
        # Try primary API
        if self.primary_api_key:
            try:
                price = self._fetch_primary(ticker, target_date)
                if price is not None:
                    return price
                logger.debug(f"Primary API returned no data for {ticker}")
            except InvalidTickerError:
                logger.warning(f"Invalid ticker {ticker} in primary API")
                # Don't fallback for invalid tickers
                return None
            except Exception as e:
                logger.warning(f"Primary API error for {ticker}: {e}")

        # Fallback to YFinance
        if use_fallback:
            return self._fetch_yfinance(ticker, target_date)

        return None

    def _fetch_yfinance(self, ticker: str, target_date: date) -> Optional[float]:
        """Fetch from YFinance with date range handling."""
        try:
            stock = self.get_yf_ticker(ticker)

            # Request 7-day range to handle weekends/holidays
            start = target_date - timedelta(days=7)
            end = target_date + timedelta(days=1)

            hist = stock.history(
                start=start.isoformat(),
                end=end.isoformat(),
                auto_adjust=True,  # Adjust for splits/dividends
                repair=True,       # Fix known Yahoo data issues
            )

            if hist.empty:
                logger.warning(f"YFinance: No data for {ticker} in range")
                return None

            # Convert index to dates for comparison
            hist.index = hist.index.date

            # Find closest date <= target_date
            valid_dates = [d for d in hist.index if d <= target_date]
            if not valid_dates:
                logger.warning(f"YFinance: No data for {ticker} on or before {target_date}")
                return None

            closest_date = max(valid_dates)
            price = float(hist.loc[closest_date, 'Close'])

            if closest_date != target_date:
                logger.debug(f"YFinance: Used {closest_date} for {ticker} (requested {target_date})")

            return price

        except Exception as e:
            logger.error(f"YFinance fallback failed for {ticker}: {e}")
            return None
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| F-string SQL | Parameterized queries | Always was bad practice | Security critical |
| Single API source | Multi-source with fallback | Best practice 2020+ | Resilience |
| Print debugging | Structured logging | Python 3.2+ (logging) | Observability |
| Manual git hooks | pre-commit framework | 2017+ | Maintainability |

**Deprecated/outdated:**
- **String interpolation in SQL:** Never acceptable, always vulnerable
- **print() for errors:** Use logging module with levels
- **Shell-based git hooks:** pre-commit framework is standard

## Open Questions

Things that couldn't be fully resolved:

1. **YFinance rate limits**
   - What we know: YFinance uses Yahoo's public API, has unofficial limits
   - What's unclear: Exact rate limits, whether they vary by endpoint
   - Recommendation: Use conservative rate limiting (1 req/sec), cache aggressively

2. **Financial Datasets API error codes**
   - What we know: Returns 400 for invalid tickers
   - What's unclear: Full error code taxonomy
   - Recommendation: Log all non-200 responses for analysis

3. **Baseline secrets file management**
   - What we know: detect-secrets uses `.secrets.baseline` file
   - What's unclear: Whether baseline should be committed
   - Recommendation: Commit baseline (tracks known secrets), update on review

## Sources

### Primary (HIGH confidence)
- [SQLAlchemy 2.0 Documentation - SQL Expressions](https://docs.sqlalchemy.org/en/20/faq/sqlexpressions.html) - Parameterized query patterns
- [pre-commit official documentation](https://pre-commit.com/) - Hook configuration
- [detect-secrets GitHub](https://github.com/Yelp/detect-secrets) - Pre-commit integration
- [yfinance PyPI](https://pypi.org/project/yfinance/) - API reference
- [yfinance documentation](https://ranaroussi.github.io/yfinance/reference/index.html) - History method parameters

### Secondary (MEDIUM confidence)
- [Real Python - Prevent SQL Injection](https://realpython.com/prevent-python-sql-injection/) - Best practices
- [GitGuardian pre-commit setup](https://blog.gitguardian.com/setting-up-a-pre-commit-git-hook-with-gitguardian-shield-to-scan-for-secrets/) - Secret detection patterns
- [ratelimit PyPI](https://pypi.org/project/ratelimit/) - Rate limiting decorator

### Tertiary (LOW confidence)
- WebSearch findings on pre-commit bypass risks - needs validation in practice

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Well-documented libraries with clear APIs
- Architecture (SQL fix): HIGH - PostgreSQL INTERVAL math is documented
- Architecture (YFinance): MEDIUM - API behavior inferred from docs + issues
- Pitfalls: MEDIUM - Based on common patterns, not project-specific testing

**Research date:** 2026-02-05
**Valid until:** 2026-03-05 (30 days - stable domain)
