# PROJECT.md

## Overview

**Name:** get-insider-db
**Type:** Data pipeline for SEC insider trading analysis
**Status:** v1.0 shipped — production ready

## Purpose

Pipeline ingests SEC Form 3/4/5 data, classifies insiders, detects conviction-weighted "cluster buy" events, enriches with price performance, and exports for backtesting.

## Current State (v1.0)

**Shipped:** 2026-02-05
**Capabilities:**
- Secure parameterized SQL queries (no injection vulnerabilities)
- Async enrichment pipeline (500-2000 clusters, O(1) memory)
- AI-powered insider classification (Claude Haiku + rule fallback)
- Database-backed crash recovery (checkpointing)
- Append-only signal audit trail
- Structured logging (JSON production, colored dev)
- YFinance fallback for price data resilience

**Codebase:** 9,933 LOC Python, 130+ tests passing

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

### Active

(None — next milestone will define new requirements)

### Out of Scope

- Mobile/web interface — CLI-focused pipeline
- Real-time streaming — Batch processing sufficient
- Multi-tenant — Single-user analysis tool

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Secrets: env vars + pre-commit | Sufficient for current scale | ✓ Good |
| Scale target: 500-2000 clusters | Current performance baseline | ✓ Good |
| YFinance fallback in Phase 1 | Reduce API dependency costs | ✓ Good |
| LLM: Claude Haiku + Instructor | Cost-effective classification | ✓ Good |
| Checkpointing: database-backed | Reliable crash recovery | ✓ Good |
| Audit: append-only signal_history | Compliance and debugging | ✓ Good |
| Repository pattern deferred | Batch patterns sufficient | — Pending |

## Tech Stack

- Python 3.x, PostgreSQL, SQLAlchemy + asyncpg
- APIs: Financial Datasets API, YFinance (fallback)
- LLM: Claude Haiku via Anthropic SDK + Instructor
- Testing: pytest (130+ tests)

## References

- `CLAUDE.md` — Build commands, architecture overview
- `.planning/milestones/v1.0-ROADMAP.md` — v1.0 detailed archive
- `.planning/MILESTONES.md` — Milestone history
- `docs/REMEDIATION_PLAN.md` — Original remediation spec

---

*Last updated: 2026-02-05 after v1.0 milestone*
