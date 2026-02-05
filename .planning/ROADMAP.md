# ROADMAP.md

## Milestone 1: Codebase Remediation

**Goal:** Transform fragile pipeline -> production-ready system (500-2000 clusters)

---

### Phase 01: Security Hardening & Data Integrity ✓
**Goal:** Eliminate security vulnerabilities, ensure data accuracy
**Status:** Complete (verified 2026-02-05)

**Plans:** 3 plans

Plans:
- [x] 01-01-PLAN.md - SQL injection remediation (parameterized INTERVAL queries)
- [x] 01-02-PLAN.md - API resilience (explicit errors, rate limiting, YFinance fallback)
- [x] 01-03-PLAN.md - Pre-commit hooks (detect-secrets, .env blocking)

**Verification:** ✓ Tests pass (25/25), no SQL injection vectors, API failures logged explicitly

---

### Phase 02: Architectural Stabilization & Observability ✓
**Goal:** Remove fragile code, standardize data access, enable debugging
**Status:** Complete (verified 2026-02-05)

**Plans:** 4 plans

Plans:
- [x] 02-01-PLAN.md - Exception hierarchy and cluster_buys.py error handling
- [x] 02-02-PLAN.md - Structured logging with structlog
- [x] 02-03-PLAN.md - N+1 query fix (batch insider classification)
- [x] 02-04-PLAN.md - Script exception cleanup (enrich, backtest)

**Depends on:** Phase 01 SQL fixes
**Verification:** ✓ 17/17 must-haves verified, 0 bare exceptions, batch queries, structured logs

---

### Phase 03: Performance & Scaling ✓
**Goal:** Transform sync script -> production pipeline (target: 500-2000 clusters)
**Status:** Complete (verified 2026-02-05)

**Plans:** 4 plans

Plans:
- [x] 03-01-PLAN.md - Async client infrastructure (aiohttp, asyncpg, retry)
- [x] 03-02-PLAN.md - Streaming JSON processing (ijson)
- [x] 03-03-PLAN.md - Async enrichment service (cache-aware, concurrent)
- [x] 03-04-PLAN.md - Async CLI script integration + verification

**Depends on:** Phase 02 error handling
**Verification:** ✓ 17/17 must-haves verified, streaming O(1) memory, concurrent enrichment

---

### Phase 04: Feature Completeness & Debt Cleanup ✓
**Goal:** Clear dead code, enable advanced features
**Status:** Complete (verified 2026-02-05)

**Plans:** 4 plans

Plans:
- [x] 04-01-PLAN.md - AI classification (Claude + Instructor for structured LLM output)
- [x] 04-02-PLAN.md - Checkpointing system (database-backed crash recovery)
- [x] 04-03-PLAN.md - Legacy code removal (cluster_service.py cleanup)
- [x] 04-04-PLAN.md - Audit trail (SignalHistory table for event sourcing)

**Depends on:** Phase 03 async integration
**Verification:** ✓ 16/16 must-haves verified, legacy code removed, crash recovery works, audit trail populated

---

### Phase 05: Async Enricher Parity
**Goal:** Bring async enricher to feature parity with sync (fallback + resume)
**Status:** Planned (2 plans in 1 wave)
**Gap Closure:** Closes integration gaps from M1 audit

**Plans:** 2 plans

Plans:
- [ ] 05-01-PLAN.md - YFinance fallback in AsyncEnricher (asyncio.to_thread wrapper)
- [ ] 05-02-PLAN.md - Checkpointing in async CLI (memory mode crash recovery)

**Depends on:** Phase 03 async infrastructure, Phase 04 checkpointing
**Closes:**
- Integration: YFinance fallback -> async enricher
- Integration: Checkpointing -> async enricher
- Flow: Async enrichment gains fallback + resume

---

### Phase 06: Production Integration Cleanup
**Goal:** Integrate orphaned modules, fix logging/exception inconsistencies
**Status:** Pending
**Gap Closure:** Closes tech debt from M1 audit

Plans:
- [ ] 06-01-PLAN.md - SignalHistoryRecorder integration into enrichment pipeline
- [ ] 06-02-PLAN.md - Structured logging in async modules
- [ ] 06-03-PLAN.md - Exception type utilization (raise EnrichmentError, RateLimitError)

**Depends on:** Phase 05 async parity
**Closes:**
- Integration: SignalHistoryRecorder -> production pipeline
- Tech debt: stdlib logging -> get_logger() in async_client
- Tech debt: Exception types defined but never raised

---

## Timeline Estimate

| Sprint | Focus | Key Deliverables |
|--------|-------|------------------|
| 1-2 | Phase 01 | SQL injection fixed, secrets secured, YFinance fallback |
| 3-5 | Phase 02 | Unified ORM, N+1 fixed, logging, indexes |
| 6-8 | Phase 03 | Async pipeline, streaming, retry tuning |
| 9+ | Phase 04 | AI classification, checkpoints, cleanup |
