# Requirements: get-insider-db

**Defined:** 2026-02-11
**Core Value:** Accurate, actionable cluster buy signals from SEC insider trading data

## v1.1 Requirements

Requirements for Result Quality 01. Each maps to a roadmap phase.

### Filtering

- [ ] **FILT-01**: Clusters with fund ratio exceeding max_fund_ratio threshold are excluded from scan results
- [ ] **FILT-02**: Rows with N/A or missing tickers are excluded from scan results

### Data Integrity

- [ ] **DATA-01**: Window spans in results do not exceed the configured window_days parameter
- [ ] **DATA-02**: issuer_cik is populated for every row in scan output
- [ ] **DATA-03**: avg_sale_to_purchase_ratio computes correctly (non-zero when insiders have both sales and purchases in lookback)

### Output Quality

- [ ] **OUT-01**: Duplicate ticker entries across different windows are handled with explicit strategy (merge, flag, or deduplicate)
- [ ] **OUT-02**: All floating-point fields in JSON export are rounded to 2 decimal places

## Future Requirements

None yet — will capture during execution if new issues emerge.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Scoring formula redesign | Weights were tuned in v1.0 phase 07; this milestone focuses on data quality not scoring |
| UI/dashboard for results | CLI-focused pipeline, out of scope per PROJECT.md |
| Automated alerting on new clusters | Future milestone — requires notification infrastructure |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FILT-01 | Phase 08 | Pending |
| FILT-02 | Phase 09 | Pending |
| DATA-01 | Phase 10 | Pending |
| DATA-02 | Phase 11 | Pending |
| DATA-03 | Phase 12 | Pending |
| OUT-01 | Phase 13 | Pending |
| OUT-02 | Phase 14 | Pending |

**Coverage:**
- v1.1 requirements: 7 total
- Mapped to phases: 7
- Unmapped: 0

---
*Requirements defined: 2026-02-11*
*Last updated: 2026-02-11 after initial definition*
