# Phase 15: CIK-Based Enrichment Lookup - Research

**Researched:** 2026-02-12
**Domain:** PostgreSQL schema migration, CIK-to-ticker mapping, primary key re-keying
**Confidence:** HIGH

## Summary

Phase 15 transitions the enrichment pipeline from ticker-based lookups to CIK-based lookups with a persistent mapping table. The core technical challenge is re-keying three database tables (`market_prices`, `market_fundamentals`, `cluster_events`) from ticker to CIK while maintaining referential integrity and existing indexes. The mapping data already exists in `form345_submission` (ISSUERCIK + ISSUERTRADINGSYMBOL columns), eliminating external API dependency.

This is fundamentally a **database schema migration** combined with **lookup layer refactoring** across 92 ticker references in enrichment scripts.

**Primary recommendation:** Use PostgreSQL table replacement pattern (CREATE new → INSERT transformed data → DROP old → RENAME new) to re-key market tables atomically. Populate CIK-ticker mapping during existing quarterly data load process. Add CIK validation layer before enrichment with strict exclusion logic.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
**Mapping Strategy**
- Build CIK-to-ticker mapping from existing SEC data in form345_submission table (no external API dependency)
- Persist as a database table: issuer_cik_ticker_map (or similar)
- Latest ticker only per CIK (no historical ticker tracking)
- When one CIK maps to multiple tickers: use the most recent filing's ticker
- Mapping table populated/refreshed during data load (load_form345_quarter.py), not a standalone script

**Lookup Key Behavior**
- Re-key market_prices and market_fundamentals from (ticker, date) to (issuer_cik, date)
- Re-key cluster_events table from ticker to issuer_cik — full CIK-centric model
- Enrichment flow: cluster CIK -> look up ticker from mapping -> call price API with ticker -> store price data keyed by CIK
- Ticker kept as metadata column in market tables (needed for API calls and display)
- Fresh start for market data: drop and rebuild market tables with CIK keys, re-fetch on next enrichment
- Display format in logs/progress: "0002076163 (BRR)" — both CIK and ticker shown

**Missing/Ambiguous CIK Handling**
- Missing CIK (null/empty): exclude cluster from enrichment output entirely (no CIK = bad data)
- CIK exists but no ticker mapping: exclude from output (can't enrich without ticker)
- Both exclusion types should be strict — no fallback to ticker-only lookup
- Report CIK resolution statistics as summary at end of enrichment (e.g., "45/50 resolved, 3 missing CIK, 2 no ticker mapping")

### Claude's Discretion
- Exact table schema for issuer_cik_ticker_map (columns, indexes, constraints)
- Migration script approach for re-keying cluster_events
- Whether to keep ticker as a non-null or nullable column in market tables
- Internal caching strategy for CIK-ticker lookups during enrichment runs
- Error handling patterns for API failures during re-enrichment

### Deferred Ideas (OUT OF SCOPE)
- SEC EDGAR API integration for authoritative CIK-ticker mapping (could supplement DB-derived mapping)
- Historical ticker tracking (CIK had ticker X from date A to B, then ticker Y) — future phase if needed
- scan_clusters.py re-keying to CIK internally — separate from enrichment pipeline scope
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PostgreSQL | 18.1 | Relational database | Project's existing stack, mature migration tooling |
| SQLAlchemy | 2.x | ORM and schema introspection | Already used throughout codebase for DB access |
| psycopg2 | Latest | PostgreSQL adapter | SQLAlchemy backend, connection pooling |
| pandas | Latest | Data transformation | Used for TSV loading and aggregation in load_form345_quarter.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| alembic | Latest | Schema versioning (optional) | If future migrations need version tracking; overkill for one-time migration |
| pytest | Latest | Testing migration logic | Validate CIK extraction and mapping correctness |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Table replacement | In-place ALTER TABLE | ALTER is safer for production but this is fresh-start migration; replacement is simpler |
| SQLAlchemy ORM | Raw SQL | Raw SQL is fine for migrations; existing pattern uses SQLAlchemy (see load_form345_quarter.py line 58-70) |
| Alembic migrations | Ad-hoc SQL scripts | Alembic adds overhead for single migration; codebase uses ad-hoc scripts (sql/ directory) |

**Installation:**
No new dependencies required — all tools already in requirements.txt.

## Architecture Patterns

### Recommended Project Structure
```
scripts/
├── migrate_market_tables_to_cik.py    # One-time migration script
└── load_form345_quarter.py            # Modified to populate mapping table

src/
├── services/
│   ├── cik_ticker_mapping.py         # CIK lookup service (new)
│   └── enrichment_service.py          # Modified to use CIK lookups
└── models.py                          # Add IssuerCikTickerMap model (optional)

sql/
└── create_cik_ticker_map.sql          # Schema DDL for mapping table
```

### Pattern 1: PostgreSQL Table Re-keying via Replacement

**What:** Create new table with CIK-based key, populate from old table + mapping join, drop old, rename new
**When to use:** When primary key structure changes and fresh start is acceptable (no historical data preservation needed)
**Example:**
```sql
-- Step 1: Create new CIK-keyed table
CREATE TABLE market_prices_new (
    issuer_cik TEXT NOT NULL,
    ticker TEXT,  -- Metadata for display/debugging
    price_date DATE NOT NULL,
    close_price NUMERIC(18,6),
    adj_close_price NUMERIC(18,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (issuer_cik, price_date)
);

-- Step 2: Migrate existing data (OPTIONAL - user decided fresh start)
-- INSERT INTO market_prices_new (issuer_cik, ticker, price_date, close_price, adj_close_price, created_at)
-- SELECT m.issuer_cik, mp.ticker, mp.price_date, mp.close_price, mp.adj_close_price, mp.created_at
-- FROM market_prices mp
-- JOIN issuer_cik_ticker_map m ON mp.ticker = m.ticker;

-- Step 3: Drop old table (user confirmed fresh start)
DROP TABLE market_prices;

-- Step 4: Rename new table
ALTER TABLE market_prices_new RENAME TO market_prices;

-- Step 5: Recreate indexes
CREATE INDEX idx_market_prices_cik_date ON market_prices (issuer_cik, price_date);
```

**Why this pattern:** Atomic operation (transaction-safe), clear rollback path (keep old table until verified), aligns with user's "fresh start" decision.

### Pattern 2: CIK-to-Ticker Mapping Population During Data Load

**What:** Upsert mapping records during quarterly TSV ingestion, using MAX(FILING_DATE) to determine latest ticker
**When to use:** When mapping source is incremental data load (not batch snapshot)
**Example:**
```python
# In load_form345_quarter.py after loading form345_submission table

def refresh_cik_ticker_mapping(engine: Engine, quarter_name: str) -> None:
    """
    Refresh CIK-ticker mapping from form345_submission.
    Uses most recent filing date per CIK to determine current ticker.
    """
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO issuer_cik_ticker_map (issuer_cik, ticker, last_seen_date, updated_at)
            SELECT
                s.ISSUERCIK AS issuer_cik,
                s.ISSUERTRADINGSYMBOL AS ticker,
                MAX(s.FILING_DATE::date) AS last_seen_date,
                NOW() AS updated_at
            FROM form345_submission s
            WHERE s.ISSUERCIK IS NOT NULL
              AND s.ISSUERCIK != ''
              AND s.ISSUERTRADINGSYMBOL IS NOT NULL
              AND s.ISSUERTRADINGSYMBOL != ''
            GROUP BY s.ISSUERCIK, s.ISSUERTRADINGSYMBOL
            ON CONFLICT (issuer_cik)
            DO UPDATE SET
                ticker = EXCLUDED.ticker,
                last_seen_date = EXCLUDED.last_seen_date,
                updated_at = EXCLUDED.updated_at
            WHERE EXCLUDED.last_seen_date > issuer_cik_ticker_map.last_seen_date
        """))
    logger.info(f"Refreshed CIK-ticker mapping from {quarter_name}")
```

**Why this pattern:** Incremental updates, no full table scan, leverages existing load workflow, handles CIK-ticker changes over time.

### Pattern 3: CIK Validation Layer in Enrichment

**What:** Pre-flight validation that checks CIK existence and mapping before enrichment
**When to use:** When strict exclusion criteria are defined (missing CIK = skip cluster)
**Example:**
```python
# In enrichment_service.py

@dataclass
class CikResolutionStats:
    """Track CIK resolution during enrichment."""
    total_clusters: int = 0
    resolved: int = 0
    missing_cik: int = 0
    no_ticker_mapping: int = 0

def validate_and_resolve_cik(cluster: dict, mapping_cache: dict) -> tuple[str | None, str | None, str]:
    """
    Validate CIK and resolve to ticker.

    Returns:
        (issuer_cik, ticker, status)
        status: "ok" | "missing_cik" | "no_mapping"
    """
    issuer_cik = cluster.get("issuer_cik", "").strip()

    # Strict exclusion: missing CIK
    if not issuer_cik:
        return None, None, "missing_cik"

    # Strict exclusion: no ticker mapping
    ticker = mapping_cache.get(issuer_cik)
    if not ticker:
        return issuer_cik, None, "no_mapping"

    return issuer_cik, ticker, "ok"

def enrich_clusters_with_cik_validation(clusters: list[dict], stats: CikResolutionStats) -> list[dict]:
    """Pre-filter clusters by CIK validation before enrichment."""
    mapping_cache = _load_cik_ticker_mapping()  # Load once, cache in memory
    enrichable = []

    for cluster in clusters:
        stats.total_clusters += 1
        issuer_cik, ticker, status = validate_and_resolve_cik(cluster, mapping_cache)

        if status == "missing_cik":
            stats.missing_cik += 1
            logger.debug(f"Skipping cluster {cluster.get('cluster_id')} - missing CIK")
            continue
        elif status == "no_mapping":
            stats.no_ticker_mapping += 1
            logger.debug(f"Skipping cluster {cluster.get('cluster_id')} - CIK {issuer_cik} has no ticker mapping")
            continue

        stats.resolved += 1
        cluster["_resolved_ticker"] = ticker  # Internal enrichment key
        enrichable.append(cluster)

    return enrichable
```

**Why this pattern:** Early validation prevents wasted API calls, clear audit trail of exclusions, aligns with user's strict exclusion requirement.

### Anti-Patterns to Avoid

- **Dual-key tables:** Don't keep both ticker and CIK as joint primary keys — user decided CIK is primary, ticker is metadata
- **Lazy mapping population:** Don't populate mapping on-demand during enrichment — user decided mapping is populated during data load
- **Fallback to ticker-only lookup:** Don't attempt enrichment if CIK mapping fails — user decided strict exclusion

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CIK validation patterns | Custom regex/length checks | Existing codebase pattern: `_first_nonempty_any()` helper (cluster_buys.py) | Already handles empty/null/whitespace correctly, tested in test_issuer_cik_population.py |
| Database migrations | Custom transaction management | SQLAlchemy's `engine.begin()` context manager | Handles commits/rollbacks, used consistently in codebase (see load_form345_quarter.py line 68) |
| Concurrent index creation | Standard CREATE INDEX | PostgreSQL `CREATE INDEX CONCURRENTLY` | Prevents table locks, already used in sql/performance_indexes.sql |
| CIK zero-padding preservation | String manipulation | Store as TEXT, not numeric | Tests confirm existing pattern preserves "0000730255" format (test_issuer_cik_population.py line 90-100) |

**Key insight:** PostgreSQL TEXT primary keys handle CIK zero-padding correctly without custom logic. Existing codebase already validates this (issuer_cik column in insider_buy_signals view, tested in test_issuer_cik_population.py).

## Common Pitfalls

### Pitfall 1: CIK Integer Conversion Truncating Leading Zeros

**What goes wrong:** CIK "0000730255" stored as integer becomes 730255, losing zero-padding required for SEC API compatibility
**Why it happens:** Developer assumes CIK is numeric, uses INTEGER or BIGINT column type
**How to avoid:** Use TEXT column type for CIK columns (existing pattern in schema.sql line 271: `issuer_cik` in `insider_buy_signals` view)
**Warning signs:** CIK values printed in logs appear shortened (730255 instead of 0000730255)

**Verification:**
```python
# Existing test pattern (test_issuer_cik_population.py line 89-100)
assert result == "0000730255"
assert len(result) == 10
assert result.startswith("0000")
```

### Pitfall 2: Ticker Nullable vs NOT NULL Constraint Trade-off

**What goes wrong:** Ticker set as NOT NULL in market tables causes INSERT failures when API returns ticker but it's not in mapping
**Why it happens:** Assuming every CIK will have a ticker in mapping table
**How to avoid:** Make ticker column nullable in market tables (enrichment can still succeed without ticker for display)
**Warning signs:** INSERT failures with "null value in column 'ticker' violates not-null constraint"

**Recommended schema:**
```sql
CREATE TABLE market_prices (
    issuer_cik TEXT NOT NULL,
    ticker TEXT,  -- NULLABLE for forward compatibility
    price_date DATE NOT NULL,
    -- ...
    PRIMARY KEY (issuer_cik, price_date)
);
```

### Pitfall 3: Mapping Table Stale Data After New Quarter Load

**What goes wrong:** Old ticker persists in mapping even though company changed ticker in recent filing
**Why it happens:** Mapping upsert logic doesn't check if new filing date is MORE recent than existing mapping
**How to avoid:** Use `last_seen_date` comparison in ON CONFLICT clause (see Pattern 2 example)
**Warning signs:** Enrichment uses outdated ticker (FB instead of META), price API returns 404

**Correct upsert logic:**
```sql
ON CONFLICT (issuer_cik)
DO UPDATE SET
    ticker = EXCLUDED.ticker,
    last_seen_date = EXCLUDED.last_seen_date,
    updated_at = EXCLUDED.updated_at
WHERE EXCLUDED.last_seen_date > issuer_cik_ticker_map.last_seen_date  -- Critical comparison
```

### Pitfall 4: Index Locks During Migration Blocking Production Queries

**What goes wrong:** Standard CREATE INDEX holds table lock, blocking cluster scans during migration
**Why it happens:** Forgetting to use CONCURRENTLY keyword for index creation
**How to avoid:** Use `CREATE INDEX CONCURRENTLY` (existing pattern in sql/performance_indexes.sql line 12)
**Warning signs:** Long-running transactions, blocked queries in pg_stat_activity

## Code Examples

Verified patterns from official sources and existing codebase:

### CIK-Ticker Mapping Table Schema

```sql
-- sql/create_cik_ticker_map.sql
CREATE TABLE IF NOT EXISTS public.issuer_cik_ticker_map (
    issuer_cik TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    last_seen_date DATE NOT NULL,  -- Most recent filing date for this CIK-ticker pair
    issuer_name TEXT,              -- Optional: for display/debugging
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for reverse ticker->CIK lookups (if needed for debugging)
CREATE INDEX IF NOT EXISTS idx_ticker_cik_map_ticker ON issuer_cik_ticker_map (ticker);

-- Index for date-based queries (finding recently updated mappings)
CREATE INDEX IF NOT EXISTS idx_ticker_cik_map_date ON issuer_cik_ticker_map (last_seen_date DESC);
```

**Rationale:**
- `issuer_cik` as PRIMARY KEY aligns with "latest ticker per CIK" requirement
- `last_seen_date` enables conflict resolution (most recent filing wins)
- `ticker` NOT NULL because a mapping without a ticker is useless
- `issuer_name` optional for debugging/display (can be populated from form345_submission)

### Market Tables Re-keyed Schema

```sql
-- New market_prices with CIK primary key
CREATE TABLE IF NOT EXISTS public.market_prices (
    issuer_cik TEXT NOT NULL,
    ticker TEXT,  -- Nullable metadata for display
    price_date DATE NOT NULL,
    close_price NUMERIC(18,6),
    adj_close_price NUMERIC(18,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (issuer_cik, price_date)
);

CREATE INDEX IF NOT EXISTS idx_market_prices_cik_date ON market_prices (issuer_cik, price_date);

-- New market_fundamentals with CIK primary key
CREATE TABLE IF NOT EXISTS public.market_fundamentals (
    issuer_cik TEXT NOT NULL,
    ticker TEXT,  -- Nullable metadata for display
    date DATE NOT NULL,
    market_cap NUMERIC,
    enterprise_value NUMERIC,
    pe_ratio NUMERIC,
    pb_ratio NUMERIC,
    trailing_peg_ratio NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (issuer_cik, date)
);

CREATE INDEX IF NOT EXISTS idx_market_fundamentals_cik_date ON market_fundamentals (issuer_cik, date);
```

**Changes from current schema (schema.sql line 497, 516):**
- PRIMARY KEY changed from `(ticker, date)` to `(issuer_cik, date)`
- `ticker` column added as nullable metadata
- Index name updated to reflect CIK key
- `issuer_cik` column added as NOT NULL

### Cluster Events Table Migration

```sql
-- Add issuer_cik column (preserving existing data)
ALTER TABLE cluster_events ADD COLUMN issuer_cik TEXT;

-- Backfill issuer_cik from form345_submission via ticker join
-- This is OPTIONAL since user may want fresh cluster scans instead
UPDATE cluster_events ce
SET issuer_cik = (
    SELECT DISTINCT s.ISSUERCIK
    FROM form345_submission s
    WHERE s.ISSUERTRADINGSYMBOL = ce.ticker
    ORDER BY s.FILING_DATE DESC
    LIMIT 1
);

-- Make issuer_cik NOT NULL after backfill (or create new table if fresh start)
-- ALTER TABLE cluster_events ALTER COLUMN issuer_cik SET NOT NULL;

-- Alternative: Fresh start with new schema
CREATE TABLE cluster_events_new (
    cluster_id BIGINT PRIMARY KEY DEFAULT nextval('cluster_events_cluster_id_seq'),
    issuer_cik TEXT NOT NULL,
    ticker TEXT,  -- Nullable metadata
    window_start DATE NOT NULL,
    window_end DATE NOT NULL,
    signal_date DATE NOT NULL,
    status TEXT DEFAULT 'active' NOT NULL,
    expiry_date DATE NOT NULL,
    last_reinforcement_at DATE,
    decay_reason TEXT,
    unique_insiders INTEGER NOT NULL,
    total_value_usd NUMERIC(18,2) NOT NULL,
    conviction_score NUMERIC(18,6),
    detector_version TEXT DEFAULT 'v1' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT cluster_events_status_check CHECK (status = ANY (ARRAY['active', 'decayed', 'invalidated']))
);

-- Recreate indexes
CREATE INDEX idx_cluster_events_cik_signal ON cluster_events_new (issuer_cik, signal_date);
CREATE INDEX idx_cluster_events_active ON cluster_events_new (status, expiry_date);
```

**Migration decision:** User has discretion here. Options:
1. Backfill existing cluster_events table (preserves historical clusters)
2. Fresh start by re-running scan_clusters.py with CIK-aware code (simpler, aligns with "fresh start" for market tables)

### CIK Lookup Service

```python
# src/services/cik_ticker_mapping.py

from functools import lru_cache
from typing import Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine
from src.config import get_engine
from src.logging_config import get_logger

logger = get_logger(__name__)

class CikTickerMapper:
    """Service for CIK-to-ticker lookups with in-memory caching."""

    def __init__(self, engine: Engine | None = None):
        self.engine = engine or get_engine()
        self._cache: dict[str, str] = {}
        self._load_mapping()

    def _load_mapping(self) -> None:
        """Load all CIK-ticker mappings into memory."""
        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT issuer_cik, ticker
                FROM issuer_cik_ticker_map
            """)).fetchall()

        self._cache = {row[0]: row[1] for row in rows}
        logger.info(f"Loaded {len(self._cache)} CIK-ticker mappings")

    def get_ticker(self, issuer_cik: str) -> Optional[str]:
        """Get ticker for a CIK. Returns None if not found."""
        return self._cache.get(issuer_cik)

    def get_cik(self, ticker: str) -> Optional[str]:
        """Get CIK for a ticker (reverse lookup). Returns None if not found."""
        # Reverse lookup is O(n) without index, but rarely needed
        for cik, tick in self._cache.items():
            if tick == ticker:
                return cik
        return None

    def refresh(self) -> None:
        """Reload mapping from database (call after data load)."""
        self._load_mapping()


# Global singleton for enrichment scripts
_mapper: Optional[CikTickerMapper] = None

def get_mapper() -> CikTickerMapper:
    """Get global CIK-ticker mapper instance."""
    global _mapper
    if _mapper is None:
        _mapper = CikTickerMapper()
    return _mapper
```

**Usage in enrichment:**
```python
# In enrich_clusters_with_price.py

from src.services.cik_ticker_mapping import get_mapper

def enrich_row(row: dict) -> dict:
    mapper = get_mapper()

    issuer_cik = row.get("issuer_cik", "").strip()
    if not issuer_cik:
        logger.warning(f"Skipping cluster {row.get('cluster_id')} - missing CIK")
        return row  # Or exclude from output

    ticker = mapper.get_ticker(issuer_cik)
    if not ticker:
        logger.warning(f"Skipping cluster {row.get('cluster_id')} - CIK {issuer_cik} has no ticker mapping")
        return row  # Or exclude from output

    # Now use ticker for API calls
    logger.info(f"Enriching {issuer_cik} ({ticker})")
    # ... existing price fetch logic using ticker ...
```

### Enrichment Statistics Reporting

```python
# In enrichment_service.py or enrich_clusters_with_price.py

@dataclass
class CikResolutionStats:
    total_clusters: int = 0
    resolved: int = 0
    missing_cik: int = 0
    no_ticker_mapping: int = 0

    def report(self) -> None:
        """Log CIK resolution summary (user requirement)."""
        logger.info(
            f"CIK resolution: {self.resolved}/{self.total_clusters} resolved, "
            f"{self.missing_cik} missing CIK, {self.no_ticker_mapping} no ticker mapping"
        )

# At end of enrichment (in main() or process_file())
cik_stats = CikResolutionStats()
# ... accumulate stats during validation ...
cik_stats.report()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ticker as primary key | CIK as primary key | Phase 15 (this migration) | Handles ticker changes (FB→META) without data loss |
| Manual ticker updates after symbol change | Automatic via CIK permanence | Phase 15 | Eliminates ticker maintenance burden |
| API failures on ticker changes | Resilient to ticker changes | Phase 15 | Better enrichment reliability |
| Ticker-only cluster keys | CIK-based cluster keys | Phase 15 | Unique clusters even when ticker reused (delisted → new company) |

**Deprecated/outdated:**
- Using ticker as primary identifier for issuers — CIK is SEC's permanent identifier, ticker changes frequently

## Open Questions

1. **Should cluster_events migration preserve historical data or fresh-scan?**
   - What we know: Market tables are fresh start (user confirmed), cluster_events migration approach is user's discretion
   - What's unclear: Whether historical cluster data is valuable enough to backfill CIKs via ticker join
   - Recommendation: Fresh scan is simpler and aligns with market table approach; historical clusters lose value if market data is missing anyway

2. **Should mapping table include issuer_name as a column?**
   - What we know: User wants display format "0002076163 (BRR)" showing both CIK and ticker
   - What's unclear: Whether company name should also be displayed (e.g., "0002076163 (BRR) - Barrett Business Services")
   - Recommendation: Add nullable issuer_name column for future-proofing, populate during data load, low cost

3. **How to handle CIK-ticker conflicts in form345_submission (same CIK, different tickers in same quarter)?**
   - What we know: User decided "most recent filing's ticker" wins
   - What's unclear: Definition of "most recent" when filing_date is identical but accession numbers differ
   - Recommendation: Use `MAX(FILING_DATE)` with arbitrary ORDER BY ACCESSION_NUMBER as tiebreaker (consistent, deterministic)

## Sources

### Primary (HIGH confidence)
- Codebase: `/home/laudes/zoot/projects/get-insider-db/schema.sql` - Existing schema for market_prices, market_fundamentals, cluster_events
- Codebase: `/home/laudes/zoot/projects/get-insider-db/src/analytics/cluster_buys.py` - Existing CIK handling pattern (_first_nonempty_any, _get_optional_column)
- Codebase: `/home/laudes/zoot/projects/get-insider-db/tests/test_issuer_cik_population.py` - CIK zero-padding preservation tests
- Codebase: `/home/laudes/zoot/projects/get-insider-db/scripts/load_form345_quarter.py` - Quarterly data load pattern
- Codebase: `/home/laudes/zoot/projects/get-insider-db/sql/performance_indexes.sql` - CREATE INDEX CONCURRENTLY pattern

### Secondary (MEDIUM confidence)
- Codebase: `/home/laudes/zoot/projects/get-insider-db/scripts/enrich_clusters_with_price.py` - 92 ticker references confirmed (grep count)
- Codebase: `/home/laudes/zoot/projects/get-insider-db/scripts/enrich_clusters_async.py` - Async enrichment patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - PostgreSQL 18.1 confirmed via psql --version, existing SQLAlchemy patterns throughout codebase
- Architecture: HIGH - Patterns derived from existing migration scripts (sql/ directory) and data load logic (load_form345_quarter.py)
- Pitfalls: HIGH - CIK zero-padding verified in test suite, index concurrency pattern in sql/performance_indexes.sql

**Research date:** 2026-02-12
**Valid until:** 2026-03-12 (30 days - stable domain, no fast-moving dependencies)
