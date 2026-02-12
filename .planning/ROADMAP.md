# Roadmap: get-insider-db

## Milestones

- ✅ **v1.0 Codebase Remediation** - Phases 1-6 (shipped 2026-02-05)
- ✅ **v1.1 Result Quality** - Phases 8-14 (shipped 2026-02-11)
- 🚧 **v1.2 CIK-Based Enrichment** - Phases 15-17 (in progress)

## Phases

<details>
<summary>✅ v1.0 Codebase Remediation (Phases 1-6) - SHIPPED 2026-02-05</summary>

### Phase 1: SQL Security & Resilience
**Goal**: Eliminate SQL injection, add fallback for price data
**Plans**: 2 plans
**Status**: Complete

Plans:
- [x] 01-01: SQL injection remediation
- [x] 01-02: YFinance fallback integration

### Phase 2: Async Pipeline
**Goal**: Handle 500-2000 clusters with O(1) memory
**Plans**: 3 plans
**Status**: Complete

Plans:
- [x] 02-01: Async enrichment with aiohttp/asyncpg
- [x] 02-02: Streaming JSON parsing
- [x] 02-03: Memory profiling

### Phase 3: AI Classification
**Goal**: Accurate insider entity type detection
**Plans**: 2 plans
**Status**: Complete

Plans:
- [x] 03-01: Claude Haiku integration
- [x] 03-02: Rule-based fallback

### Phase 4: Crash Recovery
**Goal**: Pipeline survives API failures, network issues
**Plans**: 1 plan
**Status**: Complete

Plans:
- [x] 04-01: Database-backed checkpointing

### Phase 5: Audit Trail
**Goal**: Compliance-ready signal history
**Plans**: 1 plan
**Status**: Complete

Plans:
- [x] 05-01: Append-only signal_history table

### Phase 6: Observability
**Goal**: Production-ready structured logging
**Plans**: 1 plan
**Status**: Complete

Plans:
- [x] 06-01: Structlog integration

</details>

<details>
<summary>✅ v1.1 Result Quality (Phases 8-14) - SHIPPED 2026-02-11</summary>

### Phase 8: Fund Ratio Filtering
**Goal**: Exclude fund-heavy clusters
**Plans**: 1 plan
**Status**: Complete

Plans:
- [x] 08-01: Strict exclusive boundary implementation

### Phase 9: Invalid Ticker Exclusion
**Goal**: Remove non-tradeable entities
**Plans**: 1 plan
**Status**: Complete

Plans:
- [x] 09-01: SQL-level ticker validation

### Phase 10: Window Span Validation
**Goal**: Accurate temporal clustering
**Plans**: 1 plan
**Status**: Complete

Plans:
- [x] 10-01: Merge logic validation

### Phase 11: Issuer CIK Population
**Goal**: CIK available in scan output
**Plans**: 1 plan
**Status**: Complete

Plans:
- [x] 11-01: SQL view extension

### Phase 12: Sale-to-Purchase Ratio Fix
**Goal**: Accurate ratio calculation
**Plans**: 1 plan
**Status**: Complete

Plans:
- [x] 12-01: insider_trade_signals view

### Phase 13: Duplicate Ticker Handling
**Goal**: User controls duplicate signal display
**Plans**: 1 plan
**Status**: Complete

Plans:
- [x] 13-01: --deduplicate CLI flag

### Phase 14: Float Rounding
**Goal**: Clean numeric export formatting
**Plans**: 1 plan
**Status**: Complete

Plans:
- [x] 14-01: 2-decimal rounding

</details>

### 🚧 v1.2 CIK-Based Enrichment (In Progress)

**Milestone Goal:** Replace volatile ticker-based lookups with permanent CIK identifiers throughout enrichment pipeline. Tickers change (FB→META), CIK is forever.

#### Phase 15: CIK-to-Ticker Mapping
**Goal**: Database stores authoritative CIK-to-ticker mapping from SEC data
**Depends on**: Nothing (milestone foundation)
**Requirements**: MAP-01
**Success Criteria** (what must be TRUE):
  1. New mapping table exists with schema: issuer_cik → ticker (latest filing wins when multiple tickers exist)
  2. Mapping populated from form345_submission table without external API dependency
  3. Script can query "what ticker does CIK 0002076163 currently use?" and get single authoritative answer
  4. When one CIK maps to multiple historical tickers, most recent filing's ticker is returned
**Plans**: 1 plan

Plans:
- [x] 15-01-PLAN.md --- Mapping table DDL, population in data load, CikTickerMapper service + tests

#### Phase 16: Schema Re-keying
**Goal**: Market data organized by permanent CIK identifier, not volatile tickers
**Depends on**: Phase 15 (needs mapping table)
**Requirements**: SCHEMA-01
**Success Criteria** (what must be TRUE):
  1. market_prices table primary key changed from (ticker, date) to (issuer_cik, date)
  2. Ticker retained as metadata column in market_prices for API calls and display
  3. Existing ticker-based price data dropped (fresh start approach)
  4. market_fundamentals table re-keyed to CIK using same pattern as market_prices
  5. cluster_events table re-keyed from ticker to issuer_cik
**Plans**: 1 plan

Plans:
- [ ] 16-01-PLAN.md --- Migration SQL scripts + schema.sql DDL update for CIK-based keys

#### Phase 17: Enrichment Pipeline Migration
**Goal**: Price enrichment works with CIK as primary key, tickers resolved for API calls
**Depends on**: Phase 16 (needs re-keyed schema)
**Requirements**: ENRICH-01, ENRICH-02, ENRICH-03
**Success Criteria** (what must be TRUE):
  1. enrich_clusters_with_price.py uses issuer_cik as lookup key, resolves ticker via mapping for Financial Datasets API
  2. enrich_clusters_async.py uses issuer_cik as lookup key, resolves ticker via mapping for both Financial Datasets and YFinance
  3. Clusters with missing issuer_cik (null/empty) excluded from enrichment output entirely
  4. Clusters with valid CIK but no ticker mapping excluded from enrichment output entirely
  5. Enrichment completion prints resolution statistics: "45/50 resolved, 3 missing CIK, 2 no ticker mapping"
  6. Progress logs display format "CIK (TICKER)" throughout enrichment runs
**Plans**: TBD

Plans:
- [ ] 17-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 15 → 16 → 17

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. SQL Security & Resilience | v1.0 | 2/2 | Complete | 2026-02-05 |
| 2. Async Pipeline | v1.0 | 3/3 | Complete | 2026-02-05 |
| 3. AI Classification | v1.0 | 2/2 | Complete | 2026-02-05 |
| 4. Crash Recovery | v1.0 | 1/1 | Complete | 2026-02-05 |
| 5. Audit Trail | v1.0 | 1/1 | Complete | 2026-02-05 |
| 6. Observability | v1.0 | 1/1 | Complete | 2026-02-05 |
| 8. Fund Ratio Filtering | v1.1 | 1/1 | Complete | 2026-02-11 |
| 9. Invalid Ticker Exclusion | v1.1 | 1/1 | Complete | 2026-02-11 |
| 10. Window Span Validation | v1.1 | 1/1 | Complete | 2026-02-11 |
| 11. Issuer CIK Population | v1.1 | 1/1 | Complete | 2026-02-11 |
| 12. Sale-to-Purchase Ratio Fix | v1.1 | 1/1 | Complete | 2026-02-11 |
| 13. Duplicate Ticker Handling | v1.1 | 1/1 | Complete | 2026-02-11 |
| 14. Float Rounding | v1.1 | 1/1 | Complete | 2026-02-11 |
| 15. CIK-to-Ticker Mapping | v1.2 | 1/1 | Complete | 2026-02-12 |
| 16. Schema Re-keying | v1.2 | 0/0 | Not started | - |
| 17. Enrichment Pipeline Migration | v1.2 | 0/0 | Not started | - |

---
*Last updated: 2026-02-12 after Phase 15 completion*
