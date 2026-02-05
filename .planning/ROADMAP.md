# ROADMAP.md

## Milestone 1: Codebase Remediation

**Goal:** Transform fragile pipeline -> production-ready system (500-2000 clusters)

---

### Phase 01: Security Hardening & Data Integrity
**Goal:** Eliminate security vulnerabilities, ensure data accuracy

**Plans:** 3 plans

Plans:
- [ ] 01-01-PLAN.md - SQL injection remediation (parameterized INTERVAL queries)
- [ ] 01-02-PLAN.md - API resilience (explicit errors, rate limiting, YFinance fallback)
- [ ] 01-03-PLAN.md - Pre-commit hooks (detect-secrets, .env blocking)

**Verification:** Tests pass, no SQL injection vectors, API failures logged explicitly

---

### Phase 02: Architectural Stabilization & Observability
**Goal:** Remove fragile code, standardize data access, enable debugging

**Plans:** 4 plans

Plans:
- [ ] 02-01-PLAN.md - Exception hierarchy and cluster_buys.py error handling
- [ ] 02-02-PLAN.md - Structured logging with structlog
- [ ] 02-03-PLAN.md - N+1 query fix (batch insider classification)
- [ ] 02-04-PLAN.md - Script exception cleanup (enrich, backtest)

**Depends on:** Phase 01 SQL fixes
**Verification:** No bare `except Exception`, structured logs, batch queries, specific exception types

---

### Phase 03: Performance & Scaling
**Goal:** Transform sync script -> production pipeline (target: 500-2000 clusters)

**Plans:** 4 plans

Plans:
- [ ] 03-01-PLAN.md - Async client infrastructure (aiohttp, asyncpg, retry)
- [ ] 03-02-PLAN.md - Streaming JSON processing (ijson)
- [ ] 03-03-PLAN.md - Async enrichment service (cache-aware, concurrent)
- [ ] 03-04-PLAN.md - Async CLI script integration + verification

**Depends on:** Phase 02 error handling
**Verification:** 500+ clusters enriched without memory issues, <5min for 100 clusters

---

### Phase 04: Feature Completeness & Debt Cleanup
**Goal:** Clear dead code, enable advanced features

**Tasks:**
- P2: Implement AI classification (LLM integration)
- P2: Checkpointing system (resume from crash)
- P3: Remove legacy code (`_LEGACY_ROLE_WEIGHTS_FLOAT`, dead SQL)
- P3: Audit trail (SignalHistory table)

**Depends on:** Phase 03 async integration
**Verification:** No legacy code, crash recovery works, audit trail populated

---

## Timeline Estimate

| Sprint | Focus | Key Deliverables |
|--------|-------|------------------|
| 1-2 | Phase 01 | SQL injection fixed, secrets secured, YFinance fallback |
| 3-5 | Phase 02 | Unified ORM, N+1 fixed, logging, indexes |
| 6-8 | Phase 03 | Async pipeline, streaming, retry tuning |
| 9+ | Phase 04 | AI classification, checkpoints, cleanup |
