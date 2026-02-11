# STATE.md

## Current Position

**Milestone:** v1.1 Result Quality 01
**Phase:** Phase 8 (Fund Ratio Filtering)
**Plan:** 1 of 1
**Status:** Phase complete
**Last activity:** 2026-02-11 — Completed 08-01-PLAN.md

**Progress:** v1.1: █░░░░░░░░░ 14% (1/7 phases complete)

## Phase Status

| Phase | Name | Plans | Status |
|-------|------|-------|--------|
| 01 | Security Hardening & Data Integrity | 3 | Complete (verified) |
| 02 | Architectural Stabilization & Observability | 4 | Complete (verified) |
| 03 | Performance & Scaling | 4 | Complete (verified) |
| 04 | Feature Completeness & Debt Cleanup | 4 | Complete (verified) |
| 05 | Async Enricher Parity | 2 | Complete (verified) |
| 06 | Production Integration Cleanup | 3 | Complete (verified) |
| 07 | Value Filter Enforcement | 2 | Complete (verified) |
| 08 | Fund Ratio Filtering | 1 | Complete (verified) |
| 09 | N/A Ticker Exclusion | 0 | Not started |
| 10 | Window Span Validation | 0 | Not started |
| 11 | Issuer CIK Population | 0 | Not started |
| 12 | Sale-to-Purchase Ratio Debug | 0 | Not started |
| 13 | Duplicate Ticker Handling | 0 | Not started |
| 14 | Float Rounding | 0 | Not started |

**Total:** 23 plans across 14 phases (22 complete in v1.0, 1 complete in v1.1)

## Decisions Made

| Plan | Decision | Rationale |
|------|----------|-----------|
| Planning | Secrets: env vars + pre-commit (no vault) | Sufficient for current scale |
| Planning | Scale target: 500-2000 clusters | Current performance baseline |
| Planning | YFinance fallback: Phase 01 | Reduce API dependency costs |
| Planning | All 4 phases in scope | Complete remediation plan |
| Planning | Repository pattern deferred | Batch patterns first |
| Planning | Index verification via EXPLAIN ANALYZE | During execution |
| Planning | Async enricher alongside sync | Non-destructive addition |
| Planning | LLM: Claude Haiku via Anthropic SDK + Instructor | Cost-effective classification |
| 01-01 | Use PostgreSQL INTERVAL arithmetic for parameterization | Native support for safe interval binding |
| 01-01 | No f-string interpolation in SQL queries | Prevent SQL injection attacks |
| 01-02 | YFinance as fallback API | Free, reliable, no API key required for price data |
| 01-02 | Rate limit minimum 0.1s | Prevent API hammering even with misconfiguration |
| 01-02 | Statistics dataclass pattern | Track success/failure rates across both APIs |
| 01-03 | detect-secrets over git-secrets | Better plugin ecosystem, baseline tracking |
| 01-03 | Commit .secrets.baseline | Share known false positives across team |
| 01-03 | Local .env hook with explicit regex | Catches .env variants even if .gitignore misconfigured |
| 02-01 | Context dict in base InsiderDBError | Structured error metadata for logging integration |
| 02-01 | EnrichmentError hierarchy | Separate base for API failures (InvalidTickerError, RateLimitError) |
| 02-01 | Preserve _classify_insiders exception | Defer to Plan 02-03 N+1 query fix |
| 02-01 | Safe URL truncation in DataAccessError | Prevent credential exposure in error context |
| 02-02 | Use structlog not stdlib logging | Structured context binding for production observability |
| 02-02 | Environment-based renderer | JSON in production (ENVIRONMENT=production), colored console in dev |
| 02-02 | Bind context per operation | logger.bind() pattern for operation-specific context (ticker, count) |
| 02-02 | Minimal logging in execution path | Only function boundaries and errors, avoid tight loops |
| 02-03 | Batch loading with IN clause | SELECT ... WHERE normalized_name IN (...) for O(1) entity fetch |
| 02-03 | Bulk insert with add_all() | Minimize round-trips for missing entity creation |
| 02-03 | IntegrityError retry pattern | Handle race conditions by re-fetching conflicting entities |
| 02-03 | Structural testing for patterns | Use inspect.getsource() to verify code structure and prevent regression |
| 02-04 | Replace bare Exception with specific types | Enable diagnosable errors in enrichment/backtest scripts |
| 02-04 | Structured logging for all error paths | Add ticker, error_type context for production observability |
| 02-04 | ImportError for optional dependencies | More specific than Exception for graceful degradation |
| 03-01 | TCPConnector pooling with configurable limits | Balance throughput vs resource usage (50 total, 10 per host) |
| 03-01 | Semaphore-based rate limiting | Prevent API hammering (default 10 concurrent) |
| 03-01 | Singleton async engine via lru_cache | Consistent with sync config.py pattern |
| 03-01 | Retry on 429 + 5xx with jitter | Standard transient error handling |
| 03-02 | Use ijson.items('rows.item') for streaming | Native streaming without custom parsing |
| 03-02 | Default batch_size=50 | Balance memory consumption vs processing overhead |
| 03-02 | Support file paths and file-like objects | Flexibility for testing and production use |
| 03-03 | Price and fundamentals fetched concurrently via asyncio.gather | Maximum parallelism for enrichment |
| 03-03 | Cache-first pattern: check DB before API call | Reduce API calls and costs |
| 03-03 | Error isolation: batch failures don't crash other clusters | Resilient batch processing |
| 03-03 | Backward-compatible output fields | Existing consumers continue to work |
| 03-04 | Auto-detect streaming mode (threshold: 50 clusters) | Balance memory vs overhead |
| 03-04 | Graceful shutdown via signal handlers | Clean resource cleanup on Ctrl+C |
| 03-04 | Progress reporting per cluster | Visibility during long enrichment runs |
| 04-01 | Claude 3.5 Haiku for AI classification | Cost-effective, fastest response time |
| 04-01 | Rule-based fallback on API failure | Pipeline reliability over AI accuracy |
| 04-01 | Singleton client via lru_cache | Consistent with sync config.py pattern |
| 04-02 | JSONB for checkpoint tickers/errors | Flexible schema for structured data |
| 04-02 | PostgreSQL upsert for checkpoint saves | Atomic updates without read-modify-write |
| 04-02 | Default checkpoint frequency 25 rows | Balance I/O overhead vs data loss risk |
| 04-03 | Remove deprecated _LEGACY_ROLE_WEIGHTS_FLOAT | Canonical weights in insider_roles.py |
| 04-03 | Remove fetch_recent_buys | Duplicate SQL, cluster_buys.py is canonical |
| 04-03 | Remove detect_clusters | Unused, cluster_buys.py is canonical |
| 04-03 | Keep ClusterConfig, InsiderBuy, ClusterEvent dataclasses | Still referenced elsewhere |
| 05-01 | Use asyncio.to_thread for YFinance | Wrap blocking library calls to avoid blocking event loop |
| 05-01 | Tuple return from get_price_history | Returns (prices, used_fallback) for tracking without breaking interface |
| 05-01 | New yf.Ticker per call | Thread safety for concurrent async usage |
| 05-02 | CHECKPOINT_FREQUENCY = 25 for async | Match sync script default for consistency |
| 05-02 | Streaming mode excluded from checkpointing | Cannot resume mid-stream without full re-parse |
| 05-02 | Run ID format: async_enrich_{file_stem} | Unique per input file, distinguishes from sync |
| 06-01 | async_enrichment actor distinct from sync enrichment | Traceability in audit trail |
| 06-01 | Recording failures do not crash enrichment | Resilience over strict audit trail |
| 06-01 | Only record events for clusters with cluster_id | DB join in export provides cluster_id |
| 06-02 | Custom _before_sleep_structlog for tenacity | stdlib before_sleep_log incompatible with structlog |
| 06-02 | Debug-level logging for HTTP/DB ops | High-frequency operations, avoid noise |
| 06-03 | RateLimitError raised before raise_for_status() on 429 | Specific exception type for rate limit handling |
| 06-03 | RateLimitError added to retry conditions | Redundant coverage in _is_retryable and retry_if_exception_type |
| 06-03 | EnrichmentError wraps batch failures with context | Structured error metadata (ticker, error, error_type) |
| 07-01 | Increased w_value from 2.0 to 3.0 | Amplifies dollar value impact in scoring formula |
| 07-01 | Set min_trade_value_usd to 50_000.0 | Filters out small trades that don't signal meaningful conviction |
| 07-01 | Wired config into function defaults | Eliminates disconnect where ClusterThresholds defined values but functions defaulted to 0.0 |
| 07-02 | Import CLUSTER_THRESHOLDS into CLI scripts | Centralized default management for value filters across all 3 CLI scripts |
| 07-02 | Config-driven CLI defaults | show/export/backtest scripts default to 500K total value and 50K trade value from config |
| 07-02 | Preserve user override capability | Users can still pass explicit CLI flags to override config defaults |
| 08-01 | Strict exclusive boundary (< max_fund_ratio) | Clusters with fund_ratio >= max are excluded (not <=) |
| 08-01 | Zero total_insiders guard | Clusters with 0 total insiders excluded as data integrity check |
| 08-01 | Silent filtering | No log lines for excluded clusters to avoid log noise |
| 08-01 | Config-driven fund_ratio default | CLI --max-fund-ratio defaults to 0.25 from CLUSTER_THRESHOLDS |

## Blockers

None

## Session Continuity

**Last session:** 2026-02-11 16:18 UTC
**Stopped at:** Completed plan 08-01
**Resume file:** .planning/phases/08-fund-ratio-filtering/08-01-SUMMARY.md

## Notes

v1.0 milestone shipped: 2026-02-05 (22 plans across 7 phases)
v1.1 milestone started: 2026-02-11 (roadmap phase)
Roadmap created: 2026-02-11 for phases 08-14
Phase 08 (Fund Ratio Filtering) complete: 2026-02-11 (1 plan)
