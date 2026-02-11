# Project Milestones: get-insider-db

## v1.1 Result Quality 01 (Shipped: 2026-02-11)

**Delivered:** Improved cluster scan output quality by filtering false positives, excluding non-tradeable entities, fixing broken features, and cleaning export formatting.

**Phases completed:** 08-14 (7 plans total)

**Key accomplishments:**

- Fund-heavy clusters filtered by strict exclusive boundary (max_fund_ratio) with config-driven CLI
- Invalid tickers (N/A, NULL, empty) excluded at SQL level across all query locations
- Window span validation enforced in merge logic; oversized spans kept as separate events
- Issuer CIK populated in scan output via SQL view extension (zero Python changes)
- Sale-to-purchase ratio fixed by creating insider_trade_signals view with P+S data
- Duplicate ticker handling with --deduplicate CLI flag and pure-function utilities
- All 5 floating-point fields rounded to 2 decimals in JSON exports

**Stats:**

- 39 files changed (+7,343 / -69)
- 11,243 lines of Python
- 7 phases, 7 plans, 14 tasks
- 1 day (2026-02-11)

**Git range:** `feat(08-01)` → `feat(14-01)`

**What's next:** TBD — next milestone planning

---

## v1.0 Codebase Remediation (Shipped: 2026-02-05)

**Delivered:** Transformed fragile SEC insider trading pipeline into production-ready system capable of handling 500-2000 clusters with full observability, crash recovery, and async processing.

**Phases completed:** 01-06 (20 plans total)

**Key accomplishments:**

- Eliminated SQL injection vulnerability via parameterized queries
- Added YFinance fallback for price data resilience (API + backup)
- Built async enrichment pipeline with streaming JSON (O(1) memory)
- Implemented AI-powered insider classification with Claude Haiku
- Added database-backed checkpointing for crash recovery
- Created append-only signal audit trail for compliance
- Standardized structured logging with structlog throughout

**Stats:**

- 9,933 lines of Python
- 6 phases, 20 plans, 83 must-haves verified
- 130+ tests passing
- 3 days from start to ship

**Git range:** `f049466` → `a2ff091`

**What's next:** Production deployment, real-world testing at scale

---
