# PROJECT.md

## Overview

**Name:** get-insider-db
**Type:** Data pipeline for SEC insider trading analysis
**Status:** v1.2 shipped — CIK-Based Enrichment

## Purpose

Pipeline ingests SEC Form 3/4/5 data, classifies insiders, detects conviction-weighted "cluster buy" events, enriches with price performance, and exports for backtesting.

## Current State (v1.2)

**Shipped:** 2026-02-12
**Capabilities:**
- Secure parameterized SQL queries (no injection vulnerabilities)
- Async enrichment pipeline (500-2000 clusters, O(1) memory)
- AI-powered insider classification (Claude Haiku + rule fallback)
- Database-backed crash recovery (checkpointing)
- Append-only signal audit trail
- Structured logging (JSON production, colored dev)
- YFinance fallback for price data resilience
- Fund ratio filtering with config-driven CLI defaults
- Invalid ticker exclusion at SQL level (N/A, NULL, empty)
- Window span validation in merge logic
- Issuer CIK population in scan output
- Sale-to-purchase ratio with P+S transaction data
- Duplicate ticker handling (--deduplicate flag)
- 2-decimal float rounding in JSON exports
- CIK-to-ticker mapping (8,982 mappings from SEC filings)
- CIK-based primary keys for market_prices, market_fundamentals, cluster_events
- CIK-first enrichment with strict exclusion of unmapped clusters
- CIK resolution statistics for data quality monitoring

**Codebase:** 11,829 LOC Python, 192+ tests passing

## Requirements

### Validated (v1.0)

- ✓ SQL injection remediation — v1.0
- ✓ Silent data fallthrough fix — v1.0
- ✓ Secrets management (pre-commit hooks) — v1.0
- ✓ Exception hierarchy (6 classes) — v1.0
- ✓ Structured logging (structlog) — v1.0
- ✓ N+1 query fix (batch loading) — v1.0
- ✓ Async pipeline (aiohttp, asyncpg) — v1.0
- ✓ Streaming JSON (ijson) — v1.0
- ✓ AI classification (Claude Haiku) — v1.0
- ✓ Checkpointing (crash recovery) — v1.0
- ✓ Audit trail (signal_history) — v1.0

### Validated (v1.1)

- ✓ Fund-heavy clusters filtered by max_fund_ratio — v1.1
- ✓ N/A tickers excluded from results — v1.1
- ✓ Window span behavior corrected — v1.1
- ✓ issuer_cik populated in output — v1.1
- ✓ avg_sale_to_purchase_ratio fixed — v1.1
- ✓ Duplicate ticker handling implemented — v1.1
- ✓ Numeric fields rounded to 2 decimal places — v1.1

### Validated (v1.2)

- ✓ CIK-to-ticker mapping table built from form345_submission (8,982 mappings) — v1.2
- ✓ market_prices and market_fundamentals re-keyed from (ticker, date) to (issuer_cik, date) — v1.2
- ✓ cluster_events re-keyed from ticker to issuer_cik — v1.2
- ✓ Enrichment scripts use CIK as primary lookup, ticker resolved via mapping — v1.2
- ✓ Missing CIK or unmapped CIK clusters excluded from enrichment output — v1.2
- ✓ CIK resolution statistics reported at end of enrichment — v1.2
- ✓ Mapping refreshed during data load (load_form345_quarter.py) — v1.2

### Active

(None — next milestone TBD)

### Out of Scope

- Mobile/web interface — CLI-focused pipeline
- Real-time streaming — Batch processing sufficient
- Multi-tenant — Single-user analysis tool
- Scoring formula redesign — Weights tuned in v1.0; v1.1 focused on data quality
- Automated alerting — Future milestone, requires notification infrastructure

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Secrets: env vars + pre-commit | Sufficient for current scale | ✓ Good |
| Scale target: 500-2000 clusters | Current performance baseline | ✓ Good |
| YFinance fallback in Phase 1 | Reduce API dependency costs | ✓ Good |
| LLM: Claude Haiku + Instructor | Cost-effective classification | ✓ Good |
| Checkpointing: database-backed | Reliable crash recovery | ✓ Good |
| Audit: append-only signal_history | Compliance and debugging | ✓ Good |
| Strict exclusive fund_ratio boundary | Clusters >= max excluded | ✓ Good |
| Separate insider_trade_signals view | P+S data without breaking buy signals | ✓ Good |
| Dedup as display concern | Both signals valid, user controls output | ✓ Good |
| Window overlap → keep separate events | Preserves all signals for Phase 13 dedup | ✓ Good |
| Repository pattern deferred | Batch patterns sufficient | — Pending |
| CIK as primary identifier | Tickers change, CIK is permanent | ✓ Good |
| Latest ticker per CIK (no history) | Simple, covers 99% of cases | ✓ Good |
| Fresh start for market data | Clean re-key, re-fetch on enrichment | ✓ Good |
| Strict CIK exclusion | No CIK = bad data, exclude entirely | ✓ Good |
| CIK stored as TEXT | Preserves zero-padding for SEC API compat | ✓ Good |
| In-memory mapping cache | 8,982 entries = ~300KB, O(1) lookups | ✓ Good |
| Pre-validation at CLI entry | Exclude bad data before expensive ops | ✓ Good |

## Tech Stack

- Python 3.x, PostgreSQL, SQLAlchemy + asyncpg
- APIs: Financial Datasets API, YFinance (fallback)
- LLM: Claude Haiku via Anthropic SDK + Instructor
- Testing: pytest (139+ tests)

## References

- `CLAUDE.md` — Build commands, architecture overview
- `.planning/milestones/v1.0-ROADMAP.md` — v1.0 detailed archive
- `.planning/milestones/v1.1-ROADMAP.md` — v1.1 detailed archive
- `.planning/MILESTONES.md` — Milestone history
- `docs/REMEDIATION_PLAN.md` — Original remediation spec

---

*Last updated: 2026-02-12 after v1.2 milestone*
