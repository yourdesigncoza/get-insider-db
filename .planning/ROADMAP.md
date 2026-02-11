# Roadmap: get-insider-db

## Milestones

- ✅ **v1.0 Codebase Remediation** - Phases 1-7 (shipped 2026-02-05)
- 🚧 **v1.1 Result Quality 01** - Phases 8-14 (in progress)

## Phases

<details>
<summary>✅ v1.0 Codebase Remediation (Phases 1-7) - SHIPPED 2026-02-05</summary>

### Phase 1: Security Hardening & Data Integrity
**Goal**: Eliminate SQL injection vulnerabilities and ensure reliable price data access
**Plans**: 3 plans

Plans:
- [x] 01-01: SQL injection remediation with parameterized queries
- [x] 01-02: API resilience with YFinance fallback
- [x] 01-03: Pre-commit hooks for secrets detection

### Phase 2: Architectural Stabilization & Observability
**Goal**: Production-grade error handling and observability
**Plans**: 4 plans

Plans:
- [x] 02-01: Exception hierarchy with context metadata
- [x] 02-02: Structured logging with structlog
- [x] 02-03: N+1 query fix via batch loading
- [x] 02-04: Script exception cleanup

### Phase 3: Performance & Scaling
**Goal**: Async enrichment pipeline with streaming support
**Plans**: 4 plans

Plans:
- [x] 03-01: Async client infrastructure (aiohttp + asyncpg)
- [x] 03-02: Streaming JSON with ijson
- [x] 03-03: Async price enricher
- [x] 03-04: Async CLI script integration

### Phase 4: Feature Completeness & Debt Cleanup
**Goal**: AI classification, crash recovery, and audit trail
**Plans**: 4 plans

Plans:
- [x] 04-01: AI-powered insider classification with Claude Haiku
- [x] 04-02: Enrichment checkpointing for crash recovery
- [x] 04-03: Legacy code cleanup from cluster_service.py
- [x] 04-04: Signal audit trail with SignalHistoryRecorder

### Phase 5: Async Enricher Parity
**Goal**: Feature parity between sync and async enrichment
**Plans**: 2 plans

Plans:
- [x] 05-01: YFinance async fallback in AsyncEnricher
- [x] 05-02: Checkpoint integration for crash recovery

### Phase 6: Production Integration Cleanup
**Goal**: Complete async integration with audit and exception types
**Plans**: 3 plans

Plans:
- [x] 06-01: Signal history audit integration
- [x] 06-02: Structlog standardization in async_client
- [x] 06-03: Exception type wiring

### Phase 7: Value Filter Enforcement
**Goal**: Config-driven value filters across detection and CLI
**Plans**: 2 plans

Plans:
- [x] 07-01: Config wiring for value filters (functions)
- [x] 07-02: Config wiring for value filters (CLI scripts)

</details>

### 🚧 v1.1 Result Quality 01 (In Progress)

**Milestone Goal:** Improve cluster scan output quality by filtering false positives, excluding non-tradeable entities, debugging broken features, and cleaning export formatting.

#### Phase 8: Fund Ratio Filtering
**Goal**: Exclude fund-heavy clusters from scan results
**Depends on**: Phase 7 (value filter config infrastructure)
**Requirements**: FILT-01
**Success Criteria** (what must be TRUE):
  1. Clusters with fund_ratio exceeding max_fund_ratio threshold are automatically excluded from scan_clusters.py output
  2. User can inspect and verify fund_ratio values in output before filtering
  3. Fund ratio threshold is configurable via CLI flag (with default from ClusterThresholds)
  4. Excluded clusters are silently dropped (no filter reporting)
**Plans**: 1 plan

Plans:
- [x] 08-01-PLAN.md -- Fix boundary operators, add fund_ratio to output, wire CLI defaults, add boundary tests

#### Phase 9: N/A Ticker Exclusion
**Goal**: Prevent non-tradeable tickers from appearing in results
**Depends on**: Phase 8
**Requirements**: FILT-02
**Success Criteria** (what must be TRUE):
  1. Rows with ticker "N/A" are excluded from scan_clusters.py output
  2. Rows with NULL ticker values are excluded from scan_clusters.py output
  3. User sees log message indicating how many clusters were excluded due to invalid tickers
  4. Exclusion happens at SQL query level (not post-processing filter)
**Plans**: 1 plan

Plans:
- [x] 09-01-PLAN.md -- Add N/A/empty ticker exclusion to SQL queries, metadata documentation, and tests

#### Phase 10: Window Span Validation
**Goal**: Investigate and correct window merging behavior that creates spans exceeding window_days
**Depends on**: Phase 9
**Requirements**: DATA-01
**Success Criteria** (what must be TRUE):
  1. All cluster windows in scan output have window_end - window_start <= window_days
  2. Root cause of window merging issue is identified and documented
  3. Sliding window algorithm is corrected if flawed
  4. Test coverage added to prevent regression (window span validation)
**Plans**: 1 plan

Plans:
- [x] 10-01-PLAN.md -- Fix window merge span validation and add regression tests

#### Phase 11: Issuer CIK Population
**Goal**: Populate issuer_cik field in scan output
**Depends on**: Phase 10
**Requirements**: DATA-02
**Success Criteria** (what must be TRUE):
  1. Every row in scan_clusters.py output has non-null issuer_cik value
  2. CIK values match the SEC issuer identifier from form345_submission table
  3. Join logic between cluster detection and CIK lookup is correct
  4. Test coverage validates CIK population in cluster output
**Plans**: 1 plan

Plans:
- [x] 11-01-PLAN.md -- Add issuer_cik to insider_buy_signals view, apply migration, add regression tests

#### Phase 12: Sale-to-Purchase Ratio Debug
**Goal**: Fix avg_sale_to_purchase_ratio always being 0.0
**Depends on**: Phase 11
**Requirements**: DATA-03
**Success Criteria** (what must be TRUE):
  1. avg_sale_to_purchase_ratio reflects actual insider sale/purchase activity within lookback window
  2. Ratio is non-zero when insiders have both sales and purchases in lookback_days_for_features period
  3. Root cause of 0.0 value is identified and documented
  4. Test coverage validates ratio calculation logic
  5. User can verify ratio correctness against raw transaction data
**Plans**: 1 plan

Plans:
- [x] 12-01-PLAN.md -- Create insider_trade_signals view, wire P+S data into ratio calculation, add tests

#### Phase 13: Duplicate Ticker Handling
**Goal**: Implement explicit strategy for same ticker appearing multiple times
**Depends on**: Phase 12
**Requirements**: OUT-01
**Success Criteria** (what must be TRUE):
  1. User sees clear explanation when same ticker appears multiple times (different windows)
  2. Duplicate handling strategy is documented (merge, flag, or deduplicate)
  3. User can differentiate between independent cluster events vs overlapping activity
  4. CLI provides option to show all occurrences or deduplicate by highest score
**Plans**: 1 plan

Plans:
- [ ] 13-01-PLAN.md -- Add --deduplicate CLI flag, duplicate annotation in console, dedup utility with tests

#### Phase 14: Float Rounding
**Goal**: Round numeric export fields to 2 decimal places
**Depends on**: Phase 13
**Requirements**: OUT-02
**Success Criteria** (what must be TRUE):
  1. All floating-point fields in JSON export are rounded to 2 decimal places
  2. Rounding applies to avg_days_to_file, fund_ratio, avg_percent_change, cluster_score
  3. Rounding does not affect internal calculations (only final output)
  4. Export JSON is more readable and consistent
**Plans**: TBD

Plans:
- [ ] 14-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 8 → 9 → 10 → 11 → 12 → 13 → 14

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Security Hardening | v1.0 | 3/3 | Complete | 2026-02-05 |
| 2. Arch Stabilization | v1.0 | 4/4 | Complete | 2026-02-05 |
| 3. Performance & Scaling | v1.0 | 4/4 | Complete | 2026-02-05 |
| 4. Feature Completeness | v1.0 | 4/4 | Complete | 2026-02-05 |
| 5. Async Enricher Parity | v1.0 | 2/2 | Complete | 2026-02-05 |
| 6. Production Integration | v1.0 | 3/3 | Complete | 2026-02-05 |
| 7. Value Filter Enforcement | v1.0 | 2/2 | Complete | 2026-02-11 |
| 8. Fund Ratio Filtering | v1.1 | 1/1 | Complete | 2026-02-11 |
| 9. N/A Ticker Exclusion | v1.1 | 1/1 | Complete | 2026-02-11 |
| 10. Window Span Validation | v1.1 | 1/1 | Complete | 2026-02-11 |
| 11. Issuer CIK Population | v1.1 | 1/1 | Complete | 2026-02-11 |
| 12. Sale-to-Purchase Debug | v1.1 | 1/1 | Complete | 2026-02-11 |
| 13. Duplicate Ticker Handling | v1.1 | 0/1 | Not started | - |
| 14. Float Rounding | v1.1 | 0/1 | Not started | - |

---
*Roadmap created: 2026-02-11 for milestone v1.1*
