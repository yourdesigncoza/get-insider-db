---
phase: 16-schema-re-keying
plan: 01
subsystem: database-schema
tags: [schema-migration, cik-primary-key, data-integrity]
dependency_graph:
  requires:
    - 15-01: CIK-to-ticker mapping table and service
  provides:
    - CIK-based primary keys for market_prices
    - CIK-based primary keys for market_fundamentals
    - CIK column in cluster_events with FK constraint
    - Updated schema.sql DDL as source of truth
  affects:
    - Phase 17: Python code must be updated to use issuer_cik
    - Enrichment scripts must query by CIK, not ticker
    - Export formats must include issuer_cik
tech_stack:
  added: []
  patterns:
    - CIK-first composite keys for O(1) lookups
    - Strict exclusion pattern (unmapped = deleted)
    - Fresh start migration (TRUNCATE for re-fetchable data)
key_files:
  created:
    - sql/migrate_market_prices_to_cik.sql
    - sql/migrate_market_fundamentals_to_cik.sql
    - sql/migrate_cluster_events_to_cik.sql
  modified:
    - schema.sql
decisions:
  - id: D16-01-01
    what: CIK-first composite keys for market tables
    why: Optimizes for primary access pattern (enrichment queries by CIK)
    alternatives: Ticker-first would require index scan on every lookup
    impact: O(1) lookups, better query performance
  - id: D16-01-02
    what: TRUNCATE market_prices and market_fundamentals
    why: Data is re-fetchable, fresh start cleaner than in-place migration
    alternatives: Backfill CIK for existing rows (complex, error-prone)
    impact: All historical price data deleted (will be re-fetched)
  - id: D16-01-03
    what: Strict CIK exclusion for cluster_events
    why: Unmapped tickers = bad data, should not pollute output
    alternatives: Keep unmapped rows with NULL CIK (data quality issues)
    impact: 25 cluster_events deleted (6% of 447 total)
metrics:
  duration_seconds: 198
  completed_date: 2026-02-12
  tasks_completed: 2
  commits: 2
---

# Phase 16 Plan 01: Schema Re-Keying Summary

**One-liner:** Migrated market_prices, market_fundamentals, and cluster_events to CIK-based primary keys with strict exclusion of unmapped data.

## What Was Built

**Core Achievement:** Database schema now uses CIK (Central Index Key) as the primary identifier instead of ticker symbols, eliminating data fragmentation when tickers change (e.g., FB→META).

**Implementation:**
1. **market_prices table:**
   - Primary key: `(issuer_cik, price_date)` (was `(ticker, price_date)`)
   - issuer_cik: NOT NULL
   - ticker: nullable metadata
   - Index: `idx_market_prices_ticker` for reverse lookups
   - Migration: TRUNCATE for fresh start

2. **market_fundamentals table:**
   - Primary key: `(issuer_cik, date)` (was `(ticker, date)`)
   - issuer_cik: NOT NULL
   - ticker: nullable metadata
   - Index: `idx_market_fundamentals_ticker` for reverse lookups
   - Migration: TRUNCATE for fresh start

3. **cluster_events table:**
   - Added: `issuer_cik text NOT NULL`
   - ticker: now nullable metadata
   - Foreign key: `issuer_cik → issuer_cik_ticker_map(issuer_cik)`
   - Index: `idx_cluster_events_issuer_cik`
   - Migration: Populated from mapping table, deleted 25 unmapped rows (6% of 447 total)

4. **cluster_events_active_window view:**
   - Added: `issuer_cik` column to SELECT list

5. **schema.sql:**
   - Updated as canonical DDL source of truth
   - Reflects all CIK-based changes

## Migration Results

**Execution:**
- market_prices: TRUNCATE successful (fresh start)
- market_fundamentals: TRUNCATE successful (fresh start)
- cluster_events: 422 rows updated with CIK, 25 unmapped rows deleted

**Data Integrity:**
- 0 NULL issuer_cik values in cluster_events
- 0 rows in market_prices (clean slate)
- 0 rows in market_fundamentals (clean slate)
- Foreign key constraint enforced on cluster_events.issuer_cik

## Deviations from Plan

None - plan executed exactly as written.

## Technical Context

**Why CIK as primary key?**
- Tickers are mutable (FB→META, GOOGL→GOOG)
- CIK is permanent, assigned by SEC
- Avoids data fragmentation across ticker changes
- Simplifies enrichment logic (CIK lookup, ticker metadata)

**Why TRUNCATE market tables?**
- Data is re-fetchable from Alpha Vantage/yfinance
- In-place migration complex (requires CIK lookup for every row)
- Fresh start cleaner, no orphaned ticker-only rows
- Next enrichment run will repopulate with CIK-keyed data

**Why strict exclusion?**
- Unmapped cluster_events have no valid CIK = data quality issue
- Could be bad tickers, delisted companies, or mapping gaps
- Better to exclude than pollute exports with unmappable data
- 25 deleted rows (6%) is acceptable loss for data integrity

## Verification Results

All success criteria met:

✓ market_prices PK = (issuer_cik, price_date), ticker nullable
✓ market_fundamentals PK = (issuer_cik, date), ticker nullable
✓ cluster_events has issuer_cik NOT NULL with FK to mapping table
✓ All unmapped cluster_events rows deleted (strict exclusion)
✓ Market tables empty (fresh start)
✓ schema.sql updated as canonical DDL source of truth
✓ cluster_events_active_window view includes issuer_cik
✓ Critical cluster detection tests pass (17/17)

**Expected test failures:**
- 32 enrichment-related tests fail (expected)
- Failures due to Python code expecting old schema structure
- Will be fixed in Phase 17 when Python code is updated

## Phase Outputs

| Artifact | Purpose | Status |
|----------|---------|--------|
| sql/migrate_market_prices_to_cik.sql | Market prices re-keying | ✓ Created & applied |
| sql/migrate_market_fundamentals_to_cik.sql | Market fundamentals re-keying | ✓ Created & applied |
| sql/migrate_cluster_events_to_cik.sql | Cluster events CIK addition | ✓ Created & applied |
| schema.sql | Canonical DDL source of truth | ✓ Updated |

## Next Phase Readiness

**Blockers:** None

**Dependencies for Phase 17:**
- Python enrichment code must be updated to query by issuer_cik
- Export formats must include issuer_cik field
- CikTickerMapper service already available (Phase 15)

**Risks:**
- Low: Schema changes isolated, no breaking changes to raw form345 tables
- Medium: 32 enrichment tests currently fail (expected, addressed in Phase 17)

## Performance Impact

**Query Performance:**
- CIK-first composite keys enable O(1) lookups during enrichment
- No longer need ticker→CIK resolution on every price query
- Reduced index scan overhead (direct PK lookup)

**Storage:**
- CIK column adds ~10 bytes per row (TEXT with zero-padding)
- Negligible impact: market tables currently empty
- cluster_events: 422 rows × 10 bytes = ~4KB overhead

## Self-Check: PASSED

**Created files exist:**
```
FOUND: sql/migrate_market_prices_to_cik.sql
FOUND: sql/migrate_market_fundamentals_to_cik.sql
FOUND: sql/migrate_cluster_events_to_cik.sql
```

**Modified files exist:**
```
FOUND: schema.sql (28 insertions, 7 deletions)
```

**Commits exist:**
```
FOUND: ff8e3d3 - feat(16-01): migrate schema to CIK-based primary keys
FOUND: defc3e0 - feat(16-01): update schema.sql DDL to reflect CIK-based schema
```

**Database constraints verified:**
```
PRIMARY KEY (issuer_cik, price_date) on market_prices ✓
PRIMARY KEY (issuer_cik, date) on market_fundamentals ✓
FOREIGN KEY (issuer_cik) REFERENCES issuer_cik_ticker_map ✓
0 NULL issuer_cik in cluster_events ✓
```

All self-check validations passed.
