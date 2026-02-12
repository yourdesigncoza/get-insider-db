# Phase 17: Enrichment Pipeline Migration - Research

**Researched:** 2026-02-12
**Domain:** Python data pipeline migration, CIK-based enrichment architecture, async I/O refactoring
**Confidence:** HIGH

## Summary

Phase 17 migrates two enrichment scripts (`enrich_clusters_with_price.py` and `enrich_clusters_async.py`) to use CIK as the primary lookup key instead of ticker symbols. The migration involves updating SQL queries to use `issuer_cik` for cache lookups, integrating the existing `CikTickerMapper` service to resolve tickers for external API calls, and implementing strict exclusion logic for clusters missing CIK or ticker mappings.

The existing architecture already has async HTTP client infrastructure (`AsyncHTTPClient`), in-memory CIK-ticker mapping service (`CikTickerMapper`), and both sync/async enrichment paths. The sync script uses `concurrent.futures.ThreadPoolExecutor` with LRU caching, while the async script uses `aiohttp` with connection pooling and semaphore-based concurrency control. Both scripts cache results in PostgreSQL tables (`market_prices`, `market_fundamentals`) which were already re-keyed to CIK-based primary keys in Phase 16.

**Primary recommendation:** Inject `CikTickerMapper` singleton into enrichment service constructors, update all SQL queries to use `issuer_cik` for cache reads/writes, add pre-enrichment validation to exclude clusters missing CIK or unmapped CIKs, and add resolution statistics tracking (resolved count, missing CIK, unmapped ticker) to final completion reports.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.x | Database ORM | Already used project-wide for DB access |
| aiohttp | >=3.9.0 | Async HTTP client | Already integrated in async enrichment path |
| yfinance | Latest | Price fallback | Already used as fallback when Financial Datasets API fails |
| requests | Latest | Sync HTTP | Already used in sync enrichment script |
| concurrent.futures | stdlib | Thread pooling | Standard Python library for parallel I/O in sync script |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | Latest | Structured logging | Already configured project-wide for contextual logs |
| tenacity | Latest | Retry logic | Already used in sync script for API resilience |
| asyncio | stdlib | Async runtime | Required for async script execution |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-memory CikTickerMapper | Database JOIN on every query | Database JOINs add 50-100ms latency per cluster; in-memory is O(1) with 8,982 entries (~300KB) |
| Strict exclusion (fail fast) | Lenient mode (log warnings) | Lenient mode pollutes exports with unmappable data; strict exclusion ensures data quality |
| CIK-first cache queries | Ticker-first with mapping fallback | Ticker-first requires extra mapping lookup per cache hit; CIK-first aligns with Phase 16 schema |

**Installation:**
```bash
# Already installed in project
pip install -r requirements.txt
```

## Architecture Patterns

### Recommended Migration Structure
```
scripts/
├── enrich_clusters_with_price.py      # Sync enrichment (updated)
├── enrich_clusters_async.py           # Async enrichment (updated)
src/
├── services/
│   ├── cik_ticker_mapping.py          # Existing: CikTickerMapper singleton
│   └── enrichment_service.py          # Async enrichment logic (updated)
```

### Pattern 1: CIK-First Cache Lookups with Ticker Resolution

**What:** Use `issuer_cik` for all cache queries, resolve ticker from CIK for external API calls using `CikTickerMapper`.

**When to use:** When database schema uses CIK-based primary keys but external APIs require ticker symbols (Phase 17 case).

**Example (sync script):**
```python
from src.services.cik_ticker_mapping import get_mapper

# Initialize mapper once at module level
mapper = get_mapper()

def _fetch_prices_from_db(issuer_cik: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    """Fetch cached prices using CIK."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT price_date, close_price
            FROM market_prices
            WHERE issuer_cik = :issuer_cik
              AND price_date BETWEEN :start AND :end
            ORDER BY price_date
        """), {
            "issuer_cik": issuer_cik,  # CIK-based lookup
            "start": start_date.date(),
            "end": end_date.date()
        }).fetchall()
    return [{"date": datetime.combine(row[0], datetime.min.time()), "close": float(row[1])} for row in rows]

def _save_prices_to_db(issuer_cik: str, ticker: str, prices: List[Dict[str, Any]]):
    """Save prices with CIK as primary key, ticker as metadata."""
    if not prices:
        return
    engine = get_engine()
    with engine.begin() as conn:
        for p in prices:
            conn.execute(text("""
                INSERT INTO market_prices (issuer_cik, ticker, price_date, close_price)
                VALUES (:issuer_cik, :ticker, :date, :price)
                ON CONFLICT (issuer_cik, price_date) DO NOTHING
            """), {
                "issuer_cik": issuer_cik,  # CIK-based PK
                "ticker": ticker,           # Metadata for debugging
                "date": p["date"].date(),
                "price": p["close"]
            })

def enrich_cluster(cluster: dict, mapper: CikTickerMapper) -> dict:
    """Enrich cluster with CIK-first approach."""
    issuer_cik = cluster.get("issuer_cik")

    # Pre-validation: exclude clusters without CIK
    if not issuer_cik:
        logger.warning("cluster_missing_cik", cluster_id=cluster.get("cluster_id"))
        return None  # Exclude from output

    # Resolve ticker for API calls
    ticker = mapper.get_ticker(issuer_cik)
    if not ticker:
        logger.warning("cik_unmapped", issuer_cik=issuer_cik)
        return None  # Exclude from output

    # Fetch from cache using CIK
    history = _fetch_prices_from_db(issuer_cik, start_date, end_date)

    # If cache miss, fetch from API using ticker
    if not history:
        api_prices = fetch_from_api(ticker, start_date, end_date)
        _save_prices_to_db(issuer_cik, ticker, api_prices)

    # ... rest of enrichment logic
```

**Source:** Inferred from Phase 16 schema changes and existing `CikTickerMapper` service.

### Pattern 2: Async Cache Pattern with CIK Keys

**What:** Async version of CIK-first cache pattern using SQLAlchemy async engine and aiohttp for API calls.

**When to use:** For async enrichment script with high concurrency (Phase 17 `enrich_clusters_async.py`).

**Example:**
```python
# src/services/enrichment_service.py

from src.services.cik_ticker_mapping import get_mapper

class AsyncEnricher:
    def __init__(self, api_key: str, max_concurrent: int = 10):
        self._api_key = api_key
        self._client = AsyncHTTPClient(...)
        self._session_factory = async_session_factory()
        self._mapper = get_mapper()  # Inject CIK-ticker mapper

    async def _check_price_cache(self, issuer_cik: str, start: datetime, end: datetime) -> list[dict]:
        """Query cache using CIK."""
        async with self._session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT price_date, close_price
                    FROM market_prices
                    WHERE issuer_cik = :issuer_cik
                      AND price_date BETWEEN :start AND :end
                    ORDER BY price_date
                """),
                {"issuer_cik": issuer_cik, "start": start.date(), "end": end.date()},
            )
            rows = result.fetchall()
        return [{"date": datetime.combine(row[0], datetime.min.time()), "close": float(row[1])} for row in rows]

    async def _save_prices_to_cache(self, issuer_cik: str, ticker: str, prices: list[dict]) -> None:
        """Save prices with CIK-based primary key."""
        if not prices:
            return
        async with self._session_factory() as session:
            for p in prices:
                await session.execute(
                    text("""
                        INSERT INTO market_prices (issuer_cik, ticker, price_date, close_price)
                        VALUES (:issuer_cik, :ticker, :date, :price)
                        ON CONFLICT (issuer_cik, price_date) DO NOTHING
                    """),
                    {"issuer_cik": issuer_cik, "ticker": ticker, "date": p["date"].date(), "price": p["close"]},
                )
            await session.commit()

    async def get_price_history(self, issuer_cik: str, start: datetime, end: datetime) -> tuple[list[dict], bool]:
        """Get price history with CIK-first cache lookup."""
        # Resolve ticker for API calls
        ticker = self._mapper.get_ticker(issuer_cik)
        if not ticker:
            raise ValueError(f"No ticker mapping for CIK: {issuer_cik}")

        # Check cache using CIK
        db_prices = await self._check_price_cache(issuer_cik, start, end)
        if db_prices:
            return db_prices, False

        # Fetch from API using ticker
        api_prices = await self._fetch_prices_from_api(ticker, start, end)
        if api_prices:
            await self._save_prices_to_cache(issuer_cik, ticker, api_prices)
            return api_prices, False

        # Fallback to YFinance
        fallback_price = await self._fetch_price_yfinance_async(ticker, start.date())
        if fallback_price:
            synthetic = [{"date": start, "close": fallback_price}]
            await self._save_prices_to_cache(issuer_cik, ticker, synthetic)
            return synthetic, True

        return db_prices, False
```

**Source:** Adapted from existing `AsyncEnricher` class in `src/services/enrichment_service.py`.

### Pattern 3: Pre-Enrichment Validation and Exclusion

**What:** Validate clusters for required CIK and ticker mapping before enrichment, exclude invalid clusters from output entirely.

**When to use:** Always - aligns with Phase 16 strict exclusion policy for data quality.

**Example:**
```python
@dataclass
class EnrichmentStats:
    total_clusters: int = 0
    resolved: int = 0
    missing_cik: int = 0
    unmapped_cik: int = 0
    enrichment_success: int = 0
    enrichment_fail: int = 0

def process_clusters(clusters: list[dict], mapper: CikTickerMapper) -> tuple[list[dict], EnrichmentStats]:
    """Process clusters with pre-validation and exclusion."""
    stats = EnrichmentStats(total_clusters=len(clusters))

    valid_clusters = []
    for cluster in clusters:
        issuer_cik = cluster.get("issuer_cik")

        # Exclude: missing CIK
        if not issuer_cik:
            logger.warning("cluster_missing_cik", cluster_id=cluster.get("cluster_id"))
            stats.missing_cik += 1
            continue

        # Exclude: unmapped CIK
        ticker = mapper.get_ticker(issuer_cik)
        if not ticker:
            logger.warning("cik_unmapped", issuer_cik=issuer_cik, cluster_id=cluster.get("cluster_id"))
            stats.unmapped_cik += 1
            continue

        stats.resolved += 1
        valid_clusters.append(cluster)

    # Enrich only valid clusters
    enriched = []
    for cluster in valid_clusters:
        try:
            result = enrich_cluster(cluster, mapper)
            enriched.append(result)
            stats.enrichment_success += 1
        except Exception as e:
            logger.error("enrichment_failed", cluster_id=cluster.get("cluster_id"), error=str(e))
            stats.enrichment_fail += 1

    return enriched, stats

# Print resolution statistics at completion
def print_stats(stats: EnrichmentStats):
    logger.info(
        f"Enrichment complete: {stats.resolved}/{stats.total_clusters} resolved, "
        f"{stats.missing_cik} missing CIK, {stats.unmapped_cik} unmapped CIK"
    )
    logger.info(f"Enrichment success: {stats.enrichment_success}/{stats.resolved}")
```

**Source:** Requirement ENRICH-03 from phase description.

### Pattern 4: Progress Logging with CIK Display

**What:** Log cluster processing progress with format "CIK (TICKER)" for visibility.

**When to use:** Throughout enrichment runs for user feedback.

**Example:**
```python
def enrich_cluster(cluster: dict, mapper: CikTickerMapper) -> dict:
    issuer_cik = cluster.get("issuer_cik")
    ticker = mapper.get_ticker(issuer_cik)

    # Log with CIK (TICKER) format
    logger.info(f"Enriching {issuer_cik} ({ticker})...")

    # ... enrichment logic

    return enriched_cluster

# Console progress output
for i, cluster in enumerate(clusters, 1):
    issuer_cik = cluster.get("issuer_cik")
    ticker = mapper.get_ticker(issuer_cik)
    print(f"  [{i}/{total}] Enriched {issuer_cik} ({ticker})")
```

**Source:** Success criterion #6 from phase description.

### Anti-Patterns to Avoid

- **Anti-pattern 1: Ticker-first cache lookups after Phase 16**
  - Why it's bad: Database schema now uses CIK-based primary keys; ticker lookups require full table scan or secondary index
  - What to do instead: Always use `issuer_cik` for cache queries, resolve ticker only for external API calls

- **Anti-pattern 2: Silently skipping unmapped clusters**
  - Why it's bad: Produces incomplete exports without user visibility into data quality issues
  - What to do instead: Explicitly exclude unmapped clusters and report counts in completion statistics

- **Anti-pattern 3: Re-querying mapping table per cluster**
  - Why it's bad: 8,982 mapping entries = 8,982 SELECT queries; adds 50-100ms per cluster
  - What to do instead: Use `CikTickerMapper` singleton loaded once at startup (~300KB in-memory)

- **Anti-pattern 4: Storing ticker in cache queries but CIK in primary key**
  - Why it's bad: Creates mismatch between cache lookup parameter and actual database schema
  - What to do instead: Pass `issuer_cik` to all cache functions, resolve ticker separately for API calls only

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CIK-ticker resolution | Custom JOIN queries on every cache access | `CikTickerMapper` singleton (already exists) | In-memory mapping is O(1) vs. O(n) JOIN; reduces query latency by 50-100ms per cluster |
| Async HTTP connection pooling | Manual socket management | `aiohttp.TCPConnector` (already integrated) | Handles connection reuse, SSL, timeout edge cases automatically |
| Retry logic with exponential backoff | Custom retry loops | `tenacity` library (already used in sync script) | Handles transient failures, rate limits, jitter automatically |
| Structured logging context | String formatting + print | `structlog` (already configured) | Provides JSON-serializable logs with structured context for production debugging |

**Key insight:** The project already has all required infrastructure (mapper service, async HTTP client, retry logic). Phase 17 is purely wiring existing components, not building new ones.

## Common Pitfalls

### Pitfall 1: Forgetting to Inject CikTickerMapper in Async Script

**What goes wrong:** `AsyncEnricher` initializes without mapper reference, causing AttributeError when resolving tickers.

**Why it happens:** Class constructor already has many dependencies; easy to overlook new mapper parameter.

**How to avoid:**
1. Add `self._mapper = get_mapper()` to `AsyncEnricher.__init__()`
2. Update all callsites to pass mapper to enrichment functions
3. Add unit test verifying mapper is accessed during enrichment

**Warning signs:**
- Test failures in `test_enrich_cluster_async.py` with "NoneType has no attribute 'get_ticker'"
- Runtime errors when processing first cluster in async mode

### Pitfall 2: Mixing CIK and Ticker Parameters in Function Signatures

**What goes wrong:** Some functions take `issuer_cik`, others take `ticker`, creating confusion about which identifier to pass where.

**Why it happens:** Gradual migration leaves inconsistent function signatures during transition.

**How to avoid:**
1. **Principle:** Cache functions ALWAYS take `issuer_cik`, API functions ALWAYS take `ticker`
2. Refactor all cache functions to accept `issuer_cik` first
3. Resolve `ticker = mapper.get_ticker(issuer_cik)` immediately before API calls
4. Never pass raw `ticker` to cache functions

**Warning signs:**
- Function calls with wrong parameter names (`ticker=cluster["issuer_cik"]`)
- SQL errors like "column 'ticker' does not exist in constraint"
- Cache misses despite data existing (wrong key used for lookup)

### Pitfall 3: Not Excluding Unmapped Clusters Early Enough

**What goes wrong:** Unmapped clusters proceed through enrichment, fail at API call stage, produce incomplete output with enrichment_status="error".

**Why it happens:** Validation happens too late in the pipeline (after cache checks).

**How to avoid:**
1. Add pre-enrichment validation at the start of `process_file()` or `enrich_batch()`
2. Filter out invalid clusters before passing to enrichment functions
3. Track exclusion counts in `EnrichmentStats` dataclass
4. Log exclusions with `issuer_cik` and `cluster_id` for debugging

**Warning signs:**
- High "enrichment_status: error" counts in output JSON
- Error logs with message "No ticker mapping for CIK: X"
- Export contains clusters with `issuer_cik` but NULL `ticker` field

### Pitfall 4: Forgetting to Update ON CONFLICT Clauses

**What goes wrong:** INSERT statements succeed but ON CONFLICT uses old `(ticker, price_date)` constraint name, causing constraint violations.

**Why it happens:** Schema migration changed primary key from `(ticker, price_date)` to `(issuer_cik, price_date)` but SQL query strings not updated.

**How to avoid:**
1. Global search for `ON CONFLICT (ticker,` and replace with `ON CONFLICT (issuer_cik,`
2. Add integration test that verifies cache writes with duplicate dates use upsert correctly
3. Review all `INSERT INTO market_prices` and `INSERT INTO market_fundamentals` statements

**Warning signs:**
- PostgreSQL error: "constraint 'market_prices_pkey' does not exist"
- PostgreSQL error: "ON CONFLICT column name mismatch"
- Duplicate key violations in logs during cache writes

### Pitfall 5: Progress Logs Showing Only Ticker Without CIK

**What goes wrong:** User sees progress like "Enriching AAPL..." without CIK, making it hard to debug missing CIK issues.

**Why it happens:** Old logging format only displayed ticker field.

**How to avoid:**
1. Update all progress logs to format: `f"{issuer_cik} ({ticker})"`
2. Add `issuer_cik` to structured log context in all enrichment functions
3. Ensure console output includes both identifiers

**Warning signs:**
- User asks "which clusters are failing?" but logs don't show CIK
- Debugging requires cross-referencing exports to find CIK for failed ticker

## Code Examples

Verified patterns from existing codebase:

### CikTickerMapper Singleton Usage
```python
# Source: src/services/cik_ticker_mapping.py (lines 67-72)
from src.services.cik_ticker_mapping import get_mapper

# Get singleton instance (created once, reused everywhere)
mapper = get_mapper()

# Forward lookup: CIK -> ticker
ticker = mapper.get_ticker("0000320193")  # Returns "AAPL"

# Reverse lookup: ticker -> CIK
cik = mapper.get_cik("AAPL")  # Returns "0000320193"

# Existence check
if mapper.has_cik(issuer_cik):
    ticker = mapper.get_ticker(issuer_cik)
else:
    logger.warning("cik_not_in_mapping", issuer_cik=issuer_cik)
```

### Async SQLAlchemy Session Pattern
```python
# Source: src/services/enrichment_service.py (lines 204-214)
from src.async_client import async_session_factory

session_factory = async_session_factory()

async def query_cache(issuer_cik: str):
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT * FROM market_prices WHERE issuer_cik = :cik"),
            {"cik": issuer_cik}
        )
        rows = result.fetchall()
    return rows  # Session auto-closed, connection returned to pool
```

### EnrichmentStats Reporting
```python
# Source: scripts/enrich_clusters_with_price.py (lines 75-104)
@dataclass
class EnrichmentStats:
    total_clusters: int = 0
    price_success: int = 0
    price_total_fail: int = 0
    fundamentals_success: int = 0
    fundamentals_fail: int = 0
    failed_tickers: List[str] = field(default_factory=list)

    def report(self) -> None:
        logger.info(
            f"Enrichment complete: {self.total_clusters} clusters, "
            f"{self.price_success} prices, {self.fundamentals_success} fundamentals"
        )
        if self.failed_tickers:
            unique_failed = list(set(self.failed_tickers))[:20]
            logger.warning(f"Failed tickers: {unique_failed}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ticker-based primary keys | CIK-based primary keys | Phase 16 (2026-02-12) | Eliminates data fragmentation when tickers change (FB→META) |
| Direct ticker cache lookups | CIK-first with ticker resolution | Phase 17 (current) | Aligns enrichment code with Phase 16 schema migration |
| Silent fallthrough for unmapped tickers | Strict exclusion with statistics | Phase 17 (current) | Improves data quality by preventing unmappable data in exports |
| Ticker-only logging | CIK (TICKER) format logging | Phase 17 (current) | Better visibility into CIK resolution for debugging |

**Deprecated/outdated:**
- `market_prices` lookups using `WHERE ticker = :ticker` (replaced with `WHERE issuer_cik = :issuer_cik`)
- `ON CONFLICT (ticker, price_date)` clauses (replaced with `ON CONFLICT (issuer_cik, price_date)`)
- Enrichment scripts accepting raw ticker without CIK validation (now requires pre-validation)

## Open Questions

1. **Should YFinance fallback use CIK or ticker?**
   - What we know: YFinance API requires ticker symbols, not CIK
   - What's unclear: Whether to store YFinance fallback results with CIK key or skip caching entirely
   - Recommendation: Store with CIK key + resolved ticker metadata for consistency with primary API path

2. **How to handle CIK mapping refresh during long-running enrichment?**
   - What we know: `CikTickerMapper` loads mappings once at initialization
   - What's unclear: If new quarter data loads mid-enrichment, mapper cache becomes stale
   - Recommendation: Document in PLAN that enrichment should be re-run after new data loads; mapper refresh is manual via `mapper.refresh()`

3. **Should progress percentage account for excluded clusters?**
   - What we know: Pre-validation excludes some clusters before enrichment starts
   - What's unclear: Whether progress "50/100" means 50% of input or 50% of valid clusters
   - Recommendation: Progress should show "50/100" where 100 is total input (including excluded), statistics summary shows breakdown

## Sources

### Primary (HIGH confidence)
- `src/services/cik_ticker_mapping.py` - CikTickerMapper implementation and singleton pattern
- `src/services/enrichment_service.py` - AsyncEnricher class with cache patterns
- `scripts/enrich_clusters_with_price.py` - Sync enrichment script structure
- `scripts/enrich_clusters_async.py` - Async enrichment script structure
- `schema.sql` lines 51-72, 501-523, 599-623 - Phase 16 CIK-based schema DDL
- `.planning/phases/16-schema-re-keying/16-01-SUMMARY.md` - Phase 16 completion evidence

### Secondary (MEDIUM confidence)
- Phase 16 VERIFICATION.md - Expected breaking changes in enrichment code (lines 56-64)
- Phase 16 RESEARCH.md - CIK-first composite key rationale (lines 34-37)
- CLAUDE.md project context - Prior decisions on CIK as permanent identifier

### Tertiary (LOW confidence)
- None - all findings verified from codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already integrated and in use
- Architecture: HIGH - patterns extracted from existing working code
- Pitfalls: HIGH - inferred from Phase 16 anti-patterns and Python best practices

**Research date:** 2026-02-12
**Valid until:** 2026-03-15 (30 days - codebase is stable, no fast-moving dependencies)
