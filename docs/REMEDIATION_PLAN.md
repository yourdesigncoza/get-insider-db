# Codebase Concerns Remediation Plan

Based on Gemini's analysis of `.planning/codebase/CONCERNS.md`

---

## Phase 1: Security Hardening & Data Integrity
**Goal:** Eliminate security vulnerabilities, ensure data accuracy

| Task | Pri | Effort | Files |
|------|-----|--------|-------|
| Secure secrets management (rotate keys, use env injection) | P0 | S | `.env`, deployment config |
| Remediate SQL injection (parameterized queries) | P0 | M | `src/analytics/cluster_buys.py:309-350` |
| Fix silent data fallthroughs (explicit checks for empty API responses) | P0 | S | `scripts/enrich_clusters_with_price.py:491-509` |
| Harden window detection (replace manual index calc) | P1 | M | `src/analytics/cluster_buys.py:814-856`, `window_detection.py` |
| Enforce rate limiting (`RATE_LIMIT_SECONDS` > 0) | P1 | S | `scripts/enrich_clusters_with_price.py:45-48` |
| Add pre-commit hook for .env detection | P1 | S | `.pre-commit-config.yaml` |
| Implement YFinance fallback for price data | P1 | M | `scripts/enrich_clusters_with_price.py` |

---

## Phase 2: Architectural Stabilization & Observability
**Goal:** Remove fragile code, standardize data access, enable debugging

| Task | Pri | Effort | Files | Depends On |
|------|-----|--------|-------|------------|
| Standardize data access layer (unified SQLAlchemy ORM) | P1 | L | `cluster_buys.py`, `cluster_service.py` | Phase 1 SQL fixes |
| Fix N+1 query pattern (batch load insiders) | P1 | M | `cluster_buys.py:113-143` | Data access layer |
| Global error handling (structured logging, specific exceptions) | P1 | M | All files with `except Exception` |
| Database indexing (ticker, filing_date on Form345) | P1 | S | `schema.sql` |
| Data quality monitoring (post-enrichment validation) | P2 | M | `enrich_clusters_with_price.py` | Silent fallthrough fix |

---

## Phase 3: Performance & Scaling
**Goal:** Transform sync script → production pipeline (target: 500-2000 clusters)

| Task | Pri | Effort | Files | Depends On |
|------|-----|--------|-------|------------|
| Async API integration (asyncio/aiohttp) | P1 | L | `enrich_clusters_with_price.py` | Error handling |
| Streaming data processing (ijson/generators) | P2 | M | `enrich_clusters_with_price.py:760` | Data access layer |
| Resilient retry logic (exponential backoff w/ jitter) | P2 | S | `enrich_clusters_with_price.py:57-60` | Async integration |
| Connection pooling tuning (pool_size, max_overflow) | P2 | S | `src/config.py` | Async integration |

---

## Phase 4: Feature Completeness & Debt Cleanup
**Goal:** Clear dead code, enable advanced features

| Task | Pri | Effort | Files | Depends On |
|------|-----|--------|-------|------------|
| Implement AI classification (LLM integration) | P2 | L | `src/insider_classification.py:74-96` | Async integration |
| Checkpointing system (resume from crash) | P2 | M | `enrich_clusters_with_price.py` | Data access layer |
| Remove legacy code (`_LEGACY_ROLE_WEIGHTS_FLOAT`, dead SQL) | P3 | S | `cluster_service.py:19-35, 103-122` |
| Audit trail (SignalHistory table) | P3 | M | `schema.sql`, new module | Data access layer |

---

## Execution Timeline

| Sprint | Focus | Key Deliverables |
|--------|-------|------------------|
| 1-2 | Phase 1 | SQL injection fixed, secrets secured, data integrity, YFinance fallback |
| 3-5 | Phase 2 | Unified ORM, N+1 fixed, logging, indexes |
| 6-8 | Phase 3 | Async pipeline, streaming, retry tuning |
| 9+ | Phase 4 | AI classification, checkpoints, cleanup |

---

## Decisions Made

- **Secrets:** Simple env vars + pre-commit hooks to prevent leaks
- **Scale target:** 500-2000 clusters (async + batching required)
- **YFinance fallback:** Add in Phase 1 (prevent total outage)
- **Scope:** All 4 phases

---

## Verification

After each phase:
1. Run existing tests: `pytest tests/`
2. Check for regressions in backtest output
3. Verify enrichment completes without silent failures
4. Monitor DB connection count during concurrent runs

---

*Plan generated: 2026-02-03*
