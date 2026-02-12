# Requirements: get-insider-db

**Defined:** 2026-02-12
**Core Value:** Accurate, actionable cluster buy signals from SEC insider trading data

## v1.2 Requirements

Requirements for CIK-Based Enrichment milestone. Each maps to roadmap phases.

### Data Mapping

- [ ] **MAP-01**: CIK-to-ticker mapping table populated from form345_submission data, using most recent filing's ticker when one CIK has multiple tickers

### Schema Migration

- [ ] **SCHEMA-01**: market_prices table re-keyed from (ticker, date) to (issuer_cik, date) with ticker retained as metadata column

### Enrichment Pipeline

- [ ] **ENRICH-01**: Both enrich scripts (sync + async) use issuer_cik as primary lookup key, resolving ticker via mapping table for external API calls
- [ ] **ENRICH-02**: Clusters with missing issuer_cik or unmapped CIK excluded from enrichment output entirely
- [ ] **ENRICH-03**: CIK resolution statistics printed as summary at end of enrichment run (resolved count, missing CIK count, unmapped count)

## Future Requirements

### Schema

- **SCHEMA-02**: market_fundamentals re-keyed to CIK (same pattern as market_prices)
- **SCHEMA-03**: cluster_events re-keyed from ticker to issuer_cik
- **MAP-02**: Auto-refresh mapping during data load (load_form345_quarter.py)

### Observability

- **OBS-01**: Log format shows "CIK (TICKER)" throughout enrichment pipeline

## Out of Scope

| Feature | Reason |
|---------|--------|
| Historical ticker tracking (CIK had ticker X from date A-B) | Latest ticker sufficient for current needs |
| SEC EDGAR API for CIK-ticker mapping | DB-derived mapping sufficient |
| scan_clusters.py CIK re-keying | Separate from enrichment pipeline scope |
| Automated alerting | Requires notification infrastructure (future milestone) |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MAP-01 | — | Pending |
| SCHEMA-01 | — | Pending |
| ENRICH-01 | — | Pending |
| ENRICH-02 | — | Pending |
| ENRICH-03 | — | Pending |

**Coverage:**
- v1.2 requirements: 5 total
- Mapped to phases: 0
- Unmapped: 5

---
*Requirements defined: 2026-02-12*
*Last updated: 2026-02-12 after initial definition*
