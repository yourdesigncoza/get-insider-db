# Phase 16: Schema Re-keying - Research

**Researched:** 2026-02-12
**Domain:** PostgreSQL schema migration, primary key redesign, data integrity
**Confidence:** HIGH

## Summary

Phase 16 involves migrating three core tables from ticker-based primary keys to CIK-based primary keys to establish permanent identifiers for market data. This is a foundational schema change that eliminates data fragmentation when tickers change (e.g., FB→META) and enables reliable historical tracking.

The migration requires dropping existing ticker-based primary keys on `market_prices`, `market_fundamentals`, and `cluster_events`, then recreating them with `issuer_cik` as the primary identifier. The ticker field is retained as a metadata column for API calls and display purposes. The "fresh start" approach means dropping existing market data and re-fetching during enrichment, simplifying the migration by avoiding complex data backfill.

**Primary recommendation:** Use a three-step migration per table - (1) drop constraints, (2) add CIK column and populate, (3) recreate constraints with new keys. For `cluster_events`, add strict CIK validation to exclude unmapped tickers entirely.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PostgreSQL | 18.x | RDBMS | Project database, already in use |
| SQLAlchemy | 2.x | ORM/migrations | Already used for database operations |
| psycopg2 | 2.x | PostgreSQL adapter | Standard Python PostgreSQL driver |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Alembic | 1.x | Schema versioning | Optional - for versioned migrations (not currently used in project) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQLAlchemy raw SQL | Alembic migration framework | Alembic adds version tracking overhead; raw SQL is simpler for one-time schema changes |
| Fresh start (drop data) | Backfill existing data | Backfill requires complex CIK resolution for old ticker values; fresh start is simpler and data is re-fetchable |

**Installation:**
```bash
# Already installed in project
pip install sqlalchemy psycopg2-binary
```

## Architecture Patterns

### Recommended Migration Structure
```
.planning/phases/16-schema-re-keying/
├── 16-RESEARCH.md          # This file
├── 16-01-PLAN.md           # Migration tasks
└── sql/
    ├── 01_market_prices_rekey.sql
    ├── 02_market_fundamentals_rekey.sql
    └── 03_cluster_events_rekey.sql
```

### Pattern 1: Drop and Recreate with Fresh Data

**What:** Drop existing primary key constraints, add CIK column, drop old data, recreate primary key with CIK.

**When to use:** When existing data can be easily re-fetched and avoiding complex backfill logic is preferred (Phase 16 case).

**Example:**
```sql
-- Step 1: Drop old constraint
ALTER TABLE market_prices
DROP CONSTRAINT market_prices_pkey;

-- Step 2: Add CIK column (nullable initially for safety)
ALTER TABLE market_prices
ADD COLUMN issuer_cik TEXT;

-- Step 3: Drop existing data (fresh start approach)
TRUNCATE TABLE market_prices;

-- Step 4: Recreate primary key with new columns
ALTER TABLE market_prices
ADD CONSTRAINT market_prices_pkey
PRIMARY KEY (issuer_cik, price_date);

-- Step 5: Adjust ticker to metadata-only (remove NOT NULL if present)
ALTER TABLE market_prices
ALTER COLUMN ticker DROP NOT NULL;
```

### Pattern 2: Multi-Step Migration with Data Preservation

**What:** Add CIK column, backfill from mapping table, validate completeness, then swap keys.

**When to use:** When existing data cannot be easily re-fetched and must be preserved.

**Example:**
```sql
-- Step 1: Add CIK column
ALTER TABLE market_prices
ADD COLUMN issuer_cik TEXT;

-- Step 2: Backfill CIK from mapping table
UPDATE market_prices mp
SET issuer_cik = m.issuer_cik
FROM issuer_cik_ticker_map m
WHERE mp.ticker = m.ticker;

-- Step 3: Validate completeness
SELECT COUNT(*) FROM market_prices WHERE issuer_cik IS NULL;
-- If non-zero, investigate and handle unmapped rows

-- Step 4: Make CIK NOT NULL (will fail if NULLs exist)
ALTER TABLE market_prices
ALTER COLUMN issuer_cik SET NOT NULL;

-- Step 5: Drop old primary key and create new one
ALTER TABLE market_prices
DROP CONSTRAINT market_prices_pkey,
ADD PRIMARY KEY (issuer_cik, price_date);
```

### Pattern 3: Foreign Key Cascade Handling

**What:** When changing a primary key referenced by foreign keys, use CASCADE to drop dependent constraints, then recreate them.

**When to use:** Tables with foreign key relationships (e.g., `cluster_events` referenced by `signal_history`).

**Example:**
```sql
-- Step 1: Drop foreign key constraints with CASCADE
ALTER TABLE signal_history
DROP CONSTRAINT signal_history_cluster_id_fkey CASCADE;

-- Step 2: Change primary key on parent table
ALTER TABLE cluster_events
DROP CONSTRAINT cluster_events_pkey,
ADD COLUMN issuer_cik TEXT NOT NULL,
ADD PRIMARY KEY (cluster_id);  -- cluster_id remains, add CIK as separate column

-- Step 3: Recreate foreign key
ALTER TABLE signal_history
ADD CONSTRAINT signal_history_cluster_id_fkey
FOREIGN KEY (cluster_id) REFERENCES cluster_events(cluster_id)
ON DELETE CASCADE;
```

### Anti-Patterns to Avoid

- **Renaming columns in place:** PostgreSQL RENAME COLUMN is metadata-only, but renaming a primary key column requires dropping and recreating constraints. Use explicit DROP/ADD for clarity.
- **Forgetting to handle indexes:** Dropping a primary key also drops its backing index. Secondary indexes on old columns may need to be recreated or adjusted.
- **Ignoring foreign key dependencies:** Changing a primary key referenced by foreign keys requires CASCADE on DROP CONSTRAINT and manual recreation of foreign keys.
- **Assuming zero downtime without planning:** Primary key changes require exclusive table locks. For production, consider maintenance windows or blue-green deployment patterns.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema versioning | Custom migration tracking | Alembic (optional) | Tracks applied migrations, handles rollbacks, prevents re-execution |
| CIK-ticker mapping resolution | Ad-hoc lookups in migration scripts | CikTickerMapper service (Phase 15) | Already implemented, tested, cached in-memory |
| Data validation post-migration | Manual SELECT queries | Automated tests | Ensures migration correctness, prevents regression |
| Concurrent migrations | Hand-rolled locking | PostgreSQL advisory locks | Prevents concurrent schema changes, built-in mechanism |

**Key insight:** Schema migrations involve subtle edge cases (foreign keys, indexes, constraints). PostgreSQL's ALTER TABLE handles most complexity, but migrations must be sequenced carefully (drop FKs first, change PKs, recreate FKs).

## Common Pitfalls

### Pitfall 1: Primary Key Change Locks Table

**What goes wrong:** Changing a primary key requires an ACCESS EXCLUSIVE lock, blocking all reads and writes during the operation.

**Why it happens:** PRIMARY KEY is both a constraint and an index. PostgreSQL must rebuild the index while holding the lock.

**How to avoid:**
- Schedule migration during low-traffic window
- For large tables (>1M rows), consider blue-green migration (create new table, copy data, swap)
- Monitor lock waits: `SELECT * FROM pg_locks WHERE NOT granted;`

**Warning signs:** Migration script hangs, application timeout errors, `pg_stat_activity` shows long-running ALTER TABLE.

### Pitfall 2: Forgetting Foreign Key CASCADE

**What goes wrong:** Dropping a primary key referenced by foreign keys fails with error: "cannot drop constraint ... because other objects depend on it".

**Why it happens:** Foreign keys enforce referential integrity. PostgreSQL prevents removing the referenced constraint without explicit CASCADE.

**How to avoid:**
```sql
-- Check for foreign key dependencies before dropping
SELECT
    conname AS constraint_name,
    conrelid::regclass AS table_name
FROM pg_constraint
WHERE confrelid = 'market_prices'::regclass
  AND contype = 'f';

-- Use CASCADE when dropping
ALTER TABLE market_prices
DROP CONSTRAINT market_prices_pkey CASCADE;

-- Recreate foreign keys after primary key change
ALTER TABLE dependent_table
ADD CONSTRAINT fk_name
FOREIGN KEY (ticker, date) REFERENCES market_prices(issuer_cik, price_date);
```

**Warning signs:** DROP CONSTRAINT fails with "other objects depend on it" error.

### Pitfall 3: NULL Values in New Primary Key Column

**What goes wrong:** After adding `issuer_cik` column and populating from mapping table, some rows have NULL CIK (unmapped tickers). Creating PRIMARY KEY fails with "column ... contains null values".

**Why it happens:** Not all tickers in market data may exist in `issuer_cik_ticker_map` (e.g., delisted companies, data quality issues).

**How to avoid:**
```sql
-- Step 1: Add column as nullable
ALTER TABLE market_prices ADD COLUMN issuer_cik TEXT;

-- Step 2: Populate from mapping
UPDATE market_prices mp
SET issuer_cik = m.issuer_cik
FROM issuer_cik_ticker_map m
WHERE mp.ticker = m.ticker;

-- Step 3: Check for NULLs BEFORE setting NOT NULL
SELECT ticker, COUNT(*)
FROM market_prices
WHERE issuer_cik IS NULL
GROUP BY ticker;

-- Step 4a: Fresh start approach (Phase 16 decision)
DELETE FROM market_prices WHERE issuer_cik IS NULL;

-- Step 4b: OR backfill approach (not used in Phase 16)
-- Resolve missing mappings or exclude from migration

-- Step 5: Set NOT NULL and create primary key
ALTER TABLE market_prices
ALTER COLUMN issuer_cik SET NOT NULL,
ADD PRIMARY KEY (issuer_cik, price_date);
```

**Warning signs:** "column contains null values" error when adding PRIMARY KEY, row count mismatch after migration.

### Pitfall 4: Composite Primary Key Column Order Impact

**What goes wrong:** Creating `PRIMARY KEY (price_date, issuer_cik)` instead of `(issuer_cik, price_date)` degrades query performance for CIK lookups.

**Why it happens:** PostgreSQL composite indexes (including primary keys) are most efficient when queries filter on the leftmost column(s). Enrichment queries filter by CIK first (`WHERE issuer_cik = ?`), so CIK must be the first column.

**How to avoid:**
```sql
-- CORRECT: CIK first (matches query pattern)
ALTER TABLE market_prices
ADD PRIMARY KEY (issuer_cik, price_date);

-- WRONG: Date first (inefficient for CIK lookups)
ALTER TABLE market_prices
ADD PRIMARY KEY (price_date, issuer_cik);

-- Verify query pattern matches index:
EXPLAIN SELECT * FROM market_prices
WHERE issuer_cik = '0000320193'
  AND price_date BETWEEN '2024-01-01' AND '2024-12-31';
-- Should show "Index Scan using market_prices_pkey"
```

**Warning signs:** EXPLAIN shows "Seq Scan" instead of "Index Scan" for CIK queries, slow enrichment performance after migration.

### Pitfall 5: Orphaned Indexes After Primary Key Change

**What goes wrong:** After dropping old primary key, related secondary indexes may become redundant or need adjustment.

**Why it happens:** Primary key constraint implicitly creates a unique index. Secondary indexes on the same columns may become duplicate or suboptimal.

**How to avoid:**
```sql
-- Step 1: List existing indexes before migration
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'market_prices';

-- Step 2: After primary key change, review indexes
-- Example: idx_market_prices_ticker_date may be redundant if queries now use CIK
DROP INDEX IF EXISTS idx_market_prices_ticker_date;

-- Step 3: Create new indexes matching query patterns
CREATE INDEX idx_market_prices_ticker ON market_prices(ticker);  -- For display/lookup
```

**Warning signs:** `\d+ market_prices` shows duplicate indexes, query planner chooses suboptimal index.

## Code Examples

Verified patterns for Phase 16 migration:

### Example 1: market_prices Re-keying (Fresh Start)

```sql
-- Source: PostgreSQL 18 official docs + Phase 16 requirements

-- Step 1: Drop existing primary key
ALTER TABLE market_prices
DROP CONSTRAINT market_prices_pkey;

-- Step 2: Add CIK column
ALTER TABLE market_prices
ADD COLUMN issuer_cik TEXT;

-- Step 3: Drop existing data (fresh start per user decision)
TRUNCATE TABLE market_prices;

-- Step 4: Recreate primary key with CIK first
ALTER TABLE market_prices
ADD CONSTRAINT market_prices_pkey
PRIMARY KEY (issuer_cik, price_date);

-- Step 5: Make ticker optional (metadata-only)
ALTER TABLE market_prices
ALTER COLUMN ticker DROP NOT NULL;

-- Step 6: Drop old index (now redundant)
DROP INDEX IF EXISTS idx_market_prices_ticker_date;

-- Step 7: Add new ticker index for reverse lookups
CREATE INDEX idx_market_prices_ticker ON market_prices(ticker);
```

### Example 2: cluster_events Re-keying with CIK Validation

```sql
-- Source: Phase 16 requirements + strict CIK exclusion decision

-- Note: cluster_events keeps cluster_id as primary key (auto-increment)
-- but adds issuer_cik as a required foreign key to mapping table

-- Step 1: Add issuer_cik column
ALTER TABLE cluster_events
ADD COLUMN issuer_cik TEXT;

-- Step 2: Populate from mapping table
UPDATE cluster_events ce
SET issuer_cik = m.issuer_cik
FROM issuer_cik_ticker_map m
WHERE ce.ticker = m.ticker;

-- Step 3: STRICT EXCLUSION - Delete unmapped clusters
DELETE FROM cluster_events
WHERE issuer_cik IS NULL;

-- Step 4: Make CIK required
ALTER TABLE cluster_events
ALTER COLUMN issuer_cik SET NOT NULL;

-- Step 5: Add foreign key to mapping table
ALTER TABLE cluster_events
ADD CONSTRAINT cluster_events_issuer_cik_fkey
FOREIGN KEY (issuer_cik)
REFERENCES issuer_cik_ticker_map(issuer_cik);

-- Step 6: Create index for CIK lookups
CREATE INDEX idx_cluster_events_issuer_cik ON cluster_events(issuer_cik);

-- Step 7: Keep ticker as metadata (optional)
ALTER TABLE cluster_events
ALTER COLUMN ticker DROP NOT NULL;
```

### Example 3: Enrichment Script Update for CIK-based Lookups

```python
# Source: Phase 15 CikTickerMapper + Phase 16 schema changes

from src.services.cik_ticker_mapping import get_mapper
from src.config import get_engine
from sqlalchemy import text

def enrich_cluster_with_price(cluster_dict):
    """Enrich cluster with price data using CIK-based lookup."""
    engine = get_engine()
    mapper = get_mapper(engine)

    # Get CIK from cluster (now required field)
    issuer_cik = cluster_dict.get("issuer_cik")
    if not issuer_cik:
        raise ValueError("Cluster missing issuer_cik (strict validation)")

    # Get ticker for API call (Financial Datasets API uses tickers)
    ticker = mapper.get_ticker(issuer_cik)
    if not ticker:
        raise ValueError(f"No ticker mapping for CIK {issuer_cik}")

    # Fetch price from API using ticker
    price_data = fetch_price_from_api(ticker)

    # Store price in database using CIK (permanent identifier)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO market_prices (issuer_cik, price_date, close_price, ticker)
            VALUES (:cik, :date, :price, :ticker)
            ON CONFLICT (issuer_cik, price_date) DO UPDATE
            SET close_price = EXCLUDED.close_price,
                ticker = EXCLUDED.ticker
        """), {
            "cik": issuer_cik,
            "date": price_data["date"],
            "price": price_data["close"],
            "ticker": ticker  # Stored as metadata
        })

    return {**cluster_dict, "price_at_entry": price_data["close"]}
```

### Example 4: Validation Query for Migration Completeness

```sql
-- Source: Best practice for migration validation

-- Check 1: No NULL CIKs in primary key columns
SELECT
    'market_prices' AS table_name,
    COUNT(*) AS null_cik_count
FROM market_prices
WHERE issuer_cik IS NULL
UNION ALL
SELECT
    'market_fundamentals',
    COUNT(*)
FROM market_fundamentals
WHERE issuer_cik IS NULL
UNION ALL
SELECT
    'cluster_events',
    COUNT(*)
FROM cluster_events
WHERE issuer_cik IS NULL;

-- Expected: All zero counts

-- Check 2: All CIKs exist in mapping table
SELECT
    'market_prices' AS table_name,
    COUNT(DISTINCT mp.issuer_cik) AS unmapped_ciks
FROM market_prices mp
LEFT JOIN issuer_cik_ticker_map m ON mp.issuer_cik = m.issuer_cik
WHERE m.issuer_cik IS NULL;

-- Expected: Zero unmapped CIKs

-- Check 3: Primary key constraints exist
SELECT
    conname AS constraint_name,
    conrelid::regclass AS table_name,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE contype = 'p'
  AND conrelid::regclass::text IN ('market_prices', 'market_fundamentals', 'cluster_events');

-- Expected: market_prices_pkey on (issuer_cik, price_date)
--           market_fundamentals_pkey on (issuer_cik, date)
--           cluster_events_pkey on (cluster_id) [unchanged]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ticker-based primary keys | CIK-based primary keys | Phase 16 (2026) | Eliminates data fragmentation on ticker changes, enables permanent historical tracking |
| Ticker as single source of truth | CIK as identifier, ticker as metadata | Phase 16 | Ticker changes (FB→META) no longer break data continuity |
| Backfill migrations with complex logic | Fresh start approach for re-fetchable data | Phase 16 | Simpler migration, no CIK backfill complexity |
| Manual CIK-ticker resolution | CikTickerMapper service (Phase 15) | Phase 15 | In-memory O(1) lookups, ~300KB for 8,982 mappings |

**Deprecated/outdated:**
- **Ticker-only market data storage:** Replaced by CIK-primary, ticker-metadata pattern
- **No mapping table:** Replaced by `issuer_cik_ticker_map` populated from SEC filings (Phase 15)

## Open Questions

1. **What about historical price data from before CIK mapping was established?**
   - What we know: Fresh start approach means dropping existing market data
   - What's unclear: Whether historical backtest data needs preservation
   - Recommendation: Confirm with user if any historical enriched exports need archiving before migration. Otherwise, proceed with fresh start (data is re-fetchable).

2. **Should cluster_events keep ticker column after migration?**
   - What we know: User decision says "ticker retained as metadata" for market tables
   - What's unclear: cluster_events currently uses ticker in exports, queries, display
   - Recommendation: Keep ticker as nullable metadata column in cluster_events for backward compatibility. Enrichment scripts can populate from CikTickerMapper.

3. **Do any external systems/scripts depend on ticker-based primary keys?**
   - What we know: Phase 16 changes schema for market_prices, market_fundamentals, cluster_events
   - What's unclear: Whether any external tools query these tables directly by ticker
   - Recommendation: Grep for hardcoded SQL queries with ticker-based WHERE clauses. Update to use issuer_cik or add CikTickerMapper lookups.

4. **Should migration be reversible (rollback plan)?**
   - What we know: Fresh start approach means data is dropped, no rollback to old data
   - What's unclear: Whether migration needs to be reversible for testing
   - Recommendation: For dev/staging, take database snapshot before migration. For production, fresh start is one-way (data re-fetchable, rollback is re-deployment).

## Sources

### Primary (HIGH confidence)
- [PostgreSQL 18 Documentation: ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) - Official docs for primary key changes
- [PostgreSQL 18 Documentation: Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html) - Foreign key CASCADE behavior
- Phase 15 implementation (`src/services/cik_ticker_mapping.py`) - CIK-ticker mapping service
- Project schema.sql - Current table definitions and constraints

### Secondary (MEDIUM confidence)
- [How to change PRIMARY KEY of an existing PostgreSQL table? (GitHub Gist)](https://gist.github.com/scaryguy/6269293) - Primary key migration pattern
- [Zero-downtime Postgres migrations - GoCardless](https://gocardless.com/blog/zero-downtime-postgres-migrations-the-hard-parts/) - Production migration strategies
- [PostgreSQL Composite Primary Keys | ObjectRocket](https://kb.objectrocket.com/postgresql/postgresql-composite-primary-keys-629) - Composite key best practices
- [Optimizing PostgreSQL with Composite and Partial Indexes | Stormatics](https://stormatics.tech/blogs/optimizing-postgresql-with-composite-and-partial-indexes) - Index performance implications

### Tertiary (LOW confidence)
- None - all findings verified with official PostgreSQL docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - PostgreSQL 18 features well-documented, project already uses SQLAlchemy
- Architecture: HIGH - Migration patterns verified with official docs and GitHub examples
- Pitfalls: HIGH - Identified from PostgreSQL docs (foreign key CASCADE, NULL values in PKs, composite key ordering)

**Research date:** 2026-02-12
**Valid until:** 90 days (schema migration patterns are stable, PostgreSQL 18 is current major version)

---

## Sources

- [PostgreSQL 18 Documentation: ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html)
- [PostgreSQL 18 Documentation: Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [How to change PRIMARY KEY of an existing PostgreSQL table? (GitHub Gist)](https://gist.github.com/scaryguy/6269293)
- [Zero-downtime Postgres migrations - GoCardless](https://gocardless.com/blog/zero-downtime-postgres-migrations-the-hard-parts/)
- [PostgreSQL Composite Primary Keys | ObjectRocket](https://kb.objectrocket.com/postgresql/postgresql-composite-primary-keys-629)
- [Optimizing PostgreSQL with Composite and Partial Indexes | Stormatics](https://stormatics.tech/blogs/optimizing-postgresql-with-composite-and-partial-indexes)
- [PostgreSQL Foreign Key Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)
