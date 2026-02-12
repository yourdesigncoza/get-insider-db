# Phase 15: CIK-Based Enrichment Lookup - Context

**Gathered:** 2026-02-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace ticker-based lookups in enrichment scripts (enrich_clusters_with_price.py, enrich_clusters_async.py) with issuer_cik as the primary identifier. Add a CIK-to-ticker mapping layer since external price APIs (Financial Datasets, YFinance) only accept ticker symbols. Re-key market tables and cluster_events to use CIK. Drop and rebuild market tables (fresh start).

</domain>

<decisions>
## Implementation Decisions

### Mapping Strategy
- Build CIK-to-ticker mapping from existing SEC data in form345_submission table (no external API dependency)
- Persist as a database table: issuer_cik_ticker_map (or similar)
- Latest ticker only per CIK (no historical ticker tracking)
- When one CIK maps to multiple tickers: use the most recent filing's ticker
- Mapping table populated/refreshed during data load (load_form345_quarter.py), not a standalone script

### Lookup Key Behavior
- Re-key market_prices and market_fundamentals from (ticker, date) to (issuer_cik, date)
- Re-key cluster_events table from ticker to issuer_cik — full CIK-centric model
- Enrichment flow: cluster CIK -> look up ticker from mapping -> call price API with ticker -> store price data keyed by CIK
- Ticker kept as metadata column in market tables (needed for API calls and display)
- Fresh start for market data: drop and rebuild market tables with CIK keys, re-fetch on next enrichment
- Display format in logs/progress: "0002076163 (BRR)" — both CIK and ticker shown

### Missing/Ambiguous CIK Handling
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

</decisions>

<specifics>
## Specific Ideas

- CIK is permanent, ticker can change (FB -> META) — this is the core motivation
- The mapping already exists implicitly in form345_submission (ISSUERCIK + ticker columns) — just needs extraction
- 92 occurrences of "ticker" across both enrich scripts — significant rewiring

</specifics>

<deferred>
## Deferred Ideas

- SEC EDGAR API integration for authoritative CIK-ticker mapping (could supplement DB-derived mapping)
- Historical ticker tracking (CIK had ticker X from date A to B, then ticker Y) — future phase if needed
- scan_clusters.py re-keying to CIK internally — separate from enrichment pipeline scope

</deferred>

---

*Phase: 15-cik-based-enrichment*
*Context gathered: 2026-02-12*
