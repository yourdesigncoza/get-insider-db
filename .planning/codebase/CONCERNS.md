# Codebase Concerns

**Analysis Date:** 2026-02-03

## Tech Debt

**Stubbed AI Classification:**
- Issue: `classify_insider_with_ai()` in `src/insider_classification.py` (lines 74-96) is a placeholder that merely reuses rule-based results with higher confidence
- Files: `src/insider_classification.py`
- Impact: Cannot leverage LLM-powered classification. Currently treats all non-high-confidence insiders identically, missing nuance in entity type detection
- Fix approach: Integrate with OpenAI API or equivalent, parse JSON response with entity_type and rationale, cache results in DB to avoid re-processing

**Deprecated Legacy Weights:**
- Issue: `_LEGACY_ROLE_WEIGHTS_FLOAT` dictionary kept in codebase as "reference only" (lines 19-35 in `src/analytics/cluster_service.py`)
- Files: `src/analytics/cluster_service.py`
- Impact: Dead code creates confusion; integer weights in `src/insider_roles.py` are canonical but float version persists as documentation
- Fix approach: Move legacy weights to docs, remove from active codebase; document migration path in ARCHITECTURE.md

**Duplicate SQL Query Building:**
- Issue: `fetch_recent_buys()` in `src/analytics/cluster_service.py` (lines 103-142) defines the same SQL query twice with different syntaxes (generic INTERVAL then Postgres-specific)
- Files: `src/analytics/cluster_service.py`
- Impact: Confusing to maintain; only Postgres version is used, generic version is dead code
- Fix approach: Remove lines 103-122, keep Postgres-specific query (125-142)

**Inconsistent Error Handling:**
- Issue: Broad `except Exception` blocks throughout codebase without logging context
- Files: `src/analytics/cluster_buys.py` (lines 42, 88-91), `scripts/enrich_clusters_with_price.py` (lines 76-92, 539-541)
- Impact: Silent failures in data classification/enrichment; errors caught but not logged, making debugging harder
- Fix approach: Add contextual logging before each exception, capture and log the exception details to identify systematic failures

**Raw String Queries Without Validation:**
- Issue: SQL text queries passed directly without parameterization checks; though SQLAlchemy `text()` is used, query building is error-prone
- Files: `src/analytics/cluster_buys.py` (line 309-322, 330-350, 380-398), `src/analytics/cluster_service.py` (lines 320-322)
- Impact: Injection risk if user input ever reaches these; maintainability concern if queries change
- Fix approach: Migrate to SQLAlchemy ORM patterns or create parameterized query builder helpers

## Known Bugs

**Look-ahead Bias in Enrichment (Recently Fixed but Fragile):**
- Symptoms: Window detection uses future information about when trades become public
- Files: `src/analytics/cluster_buys.py` (lines 814-856), tests in `tests/test_look_ahead_bias.py`
- Trigger: Using `signal_mode="full_reveal"` instead of `"first_qualify"`; reveals cluster only after all insiders' transactions are filed
- Workaround: Default to `"first_qualify"` mode; use `"full_reveal"` only for historical backtests where you know the future
- Note: Recent commit (5d8910b) addresses this but the dual-mode architecture remains fragile; tests are comprehensive

**Fundamental Data Gaps with Silent Fallthrough:**
- Symptoms: Clusters enriched with price data but missing fundamental metrics (market cap, PE, etc.) are still exported
- Files: `scripts/enrich_clusters_with_price.py` (lines 491-509, 625-653), enrich_row() function
- Trigger: Alpha Vantage returns no data near window_end; script falls back to no fundamentals rather than blocking
- Workaround: Check `enrichment_status` field in export (values: "ok", "partial", "no_price_data", "error", "unsupported_ticker")
- Impact: Backtest results can be skewed if missing ~30% of fundamental metrics; see docs/console.txt for examples

**Off-by-one in Date Calculations:**
- Symptoms: Entry date set to `signal_filing_date + 1 day` (line 858 in cluster_buys.py), which may land on weekends/non-trading days
- Files: `src/analytics/cluster_buys.py` (line 858)
- Trigger: Using any cluster from weekend filings; price enrichment then searches for "on_or_after" entry date, which may be Monday
- Workaround: `PRICE_LOOKAHEAD_BUFFER_DAYS` (default 10) mitigates by fetching extra days forward
- Impact: Forward returns slightly delayed; not a critical bug but edge case in timing

## Security Considerations

**Exposed Environment Configuration:**
- Risk: `.env` file contains `DATABASE_URL` and `FINANCIAL_DATASETS_API_KEY`
- Files: `.env` (listed in .gitignore but commonly leaked in CI/CD)
- Current mitigation: `.env` is in .gitignore; no hardcoded secrets in source
- Recommendations:
  - Use AWS Secrets Manager, HashiCorp Vault, or GitHub Secrets for API keys in production
  - Rotate `FINANCIAL_DATASETS_API_KEY` regularly
  - Add pre-commit hook to scan for env files before committing

**API Key Rate Limiting and Throttling:**
- Risk: `FINANCIAL_DATASETS_API_KEY` shared across all enrichment jobs; no per-key rate limiting
- Files: `scripts/enrich_clusters_with_price.py` (lines 45-48, 62-82)
- Current mitigation: Global `REQUEST_LOCK` and `RATE_LIMIT_SECONDS` variable (set to 0.0 by default)
- Recommendations:
  - Enable rate limiting via environment variable (e.g., `RATE_LIMIT_SECONDS=0.1`)
  - Implement exponential backoff more robustly (tenacity retry is present but only for connection errors)
  - Monitor API usage dashboard; add alerts for quota approaching

**SQL Injection Risk (Unlikely but Present):**
- Risk: Dynamic SQL building in cluster_buys.py could accept user input
- Files: `src/analytics/cluster_buys.py` (lines 309-350)
- Current mitigation: Code currently only used internally; no user input accepted
- Recommendations:
  - Migrate to SQLAlchemy ORM fully (use sessionmaker + mapped classes)
  - If dynamic queries needed, use Postgres parameterized statements exclusively

## Performance Bottlenecks

**N+1 Query Problem in Insider Classification:**
- Problem: `_classify_insiders()` iterates over unique insider names and calls `get_or_create_insider_entity()` for each (line 124 in cluster_buys.py)
- Files: `src/analytics/cluster_buys.py` (lines 113-143)
- Cause: One SQL query per insider; on large runs with 1000+ insiders, this becomes 1000+ DB round trips
- Improvement path:
  - Batch load all existing insiders from DB in a single query
  - Insert new ones in a single bulk INSERT
  - Current code shows intent (unique_rows) but doesn't optimize the session execution
  - Estimated improvement: 50-100x faster for large datasets

**Parallel Fetch Threading Pool Fixed at 2 Workers:**
- Problem: `ThreadPoolExecutor(max_workers=2)` in `enrich_row()` (line 628 in enrich_clusters_with_price.py) is hardcoded
- Files: `scripts/enrich_clusters_with_price.py` (line 628)
- Cause: Conservative default to avoid overwhelming API; but script processes one cluster at a time in main loop
- Improvement path:
  - Make `max_workers` configurable via environment or CLI flag
  - Consider processing clusters in batches (e.g., 10 at a time) with higher concurrency
  - Estimated improvement: 2-3x faster enrichment for 100+ clusters

**Synchronous API Calls in Main Loop:**
- Problem: `enrich_clusters_with_price.py` processes clusters sequentially; each cluster waits for API responses before moving to next
- Files: `scripts/enrich_clusters_with_price.py` (lines 750-800, main loop)
- Cause: Single-threaded main loop; only internal enrichment is parallel
- Improvement path:
  - Use `asyncio` to process multiple clusters concurrently
  - Queue API calls; use semaphore to limit concurrency (e.g., 5 concurrent)
  - Estimated improvement: 5-10x faster for 50+ clusters

**Unindexed Queries on Form345 Tables:**
- Problem: `form345_nonderiv_trans` and `form345_submission` tables have indexes but queries in `insider_buy_signals` view use INNER JOINs without filtering on indexed columns
- Files: `schema.sql` (lines 103-150), view definition in schema (lines 265-287)
- Cause: Raw form data not optimized for analytical queries; denormalization opportunity
- Improvement path:
  - Pre-aggregate buy signals into a materialized view or staging table
  - Index on (ticker, transaction_date) for faster clustering
  - Add CLUSTER ON this index for physical ordering
  - Estimated improvement: 10-50x faster cluster detection for 100k+ transactions

## Fragile Areas

**Window Detection Algorithm Relies on Manual Index Calculation:**
- Files: `src/analytics/window_detection.py`, `src/analytics/cluster_buys.py` (lines 826-840)
- Why fragile: `best_qualifying_window_indices()` returns tuple of array indices; if DataFrame is mutated between call and use, indices are stale
- Safe modification: Always re-sort and reset_index() before calling; never assume index stability across filters
- Test coverage: `tests/test_tradeable_window_selection.py` covers basic cases but not edge cases with duplicate dates

**Pandas dtype Coercion in Cluster Buys:**
- Files: `src/analytics/cluster_buys.py` (lines 860-867, 939-940)
- Why fragile: Code assumes numeric columns (shares, total_value) are numeric; if NULL values present, operations silently fail or produce nan
- Safe modification: Validate dtype on input; use fillna(0) explicitly; test with sparse/missing data
- Test coverage: No explicit tests for data quality/validation; only happy-path tests

**Fundamental Enrichment Fallback Chain Too Complex:**
- Files: `scripts/enrich_clusters_with_price.py` (lines 436-542)
- Why fragile: Multiple fallback levels (DB cache → API call → retry with larger limit → next-period data) make error handling non-obvious
- Safe modification: Add comprehensive logging at each fallback step; test offline to ensure DB cache works
- Test coverage: No unit tests for _get_fundamental_at_date; only integration tests via backtest script

## Scaling Limits

**Database Connection Pool Exhaustion:**
- Current capacity: SQLAlchemy default pool size is 5 connections; in-memory queue for overflow
- Limit: With concurrent enrichment script + data loader running together, can hit connection limit
- Scaling path:
  - Configure `pool_size` and `max_overflow` in `get_engine()` (src/config.py)
  - Monitor active connections: `SELECT count(*) FROM pg_stat_activity WHERE datname = 'insider_data'`
  - For 100+ concurrent tasks, set `pool_size=20, max_overflow=40`

**Memory Usage in Large Enrichment Runs:**
- Current capacity: Loading entire enriched cluster JSON into memory (line 760 in enrich_clusters_with_price.py)
- Limit: For 1000+ clusters, JSON can exceed 500MB; OOM on constrained hosts
- Scaling path:
  - Stream processing: process clusters in chunks of 50, write to output file incrementally
  - Use `ijson` for streaming JSON parsing if input is large
  - Estimated memory reduction: 10x

**Time-to-Enrich Grows Linearly with Cluster Count:**
- Current capacity: ~100 clusters → ~10-15 min (API calls + DB writes)
- Limit: 1000+ clusters → 100+ minutes; makes iterative development painful
- Scaling path:
  - Batch API requests (Financial Datasets API supports bulk ticker requests)
  - Use async/await for concurrent API calls (currently ThreadPoolExecutor is synchronous)
  - Cache more aggressively in market_prices/market_fundamentals
  - Estimated improvement: 5-10x

**Schema Not Optimized for Time-Series Queries:**
- Current capacity: cluster_events + market_prices tables work for historical analysis
- Limit: Querying price returns over time for backtesting is slow (no time-series optimizations)
- Scaling path:
  - Partition market_prices by ticker or date range
  - Add computed columns (e.g., rolling averages, volatility) to market_prices
  - Consider TimescaleDB extension for time-series optimization

## Dependencies at Risk

**Tenacity Retry Decorator Configuration Weak:**
- Risk: `stop_after_attempt(3)` with `wait_exponential(multiplier=1, min=1, max=5)` may not be appropriate for slow APIs
- Files: `scripts/enrich_clusters_with_price.py` (lines 57-60)
- Impact: API requests fail too quickly; enrichment jobs abort prematurely
- Migration plan:
  - Increase to `stop_after_attempt(5)` and `max=15` seconds
  - Add jitter: `randomize=True` in wait_exponential
  - Document SLA assumptions (e.g., "API responds within 30 sec, 95th percentile")

**Financial Datasets API Reliance:**
- Risk: External API used for price and fundamentals enrichment; no fallback if service down
- Files: `scripts/enrich_clusters_with_price.py` (throughout)
- Impact: Enrichment runs fail completely if API is down (no YFinance fallback present)
- Migration plan:
  - Add YFinance as fallback for price data (partially stubbed in comments)
  - Cache API responses aggressively in market_prices/market_fundamentals
  - Consider bulk-updating cache nightly to avoid API throttling during analysis

**SQLAlchemy ORM Not Used Consistently:**
- Risk: Mixed use of raw SQL (text()) and ORM; makes migration difficult
- Files: `src/analytics/cluster_buys.py` (heavy use of text()), vs `src/insider_classification.py` (uses ORM)
- Impact: Vendor lock-in to Postgres; switching to SQLite for testing is harder
- Migration plan:
  - Refactor cluster_buys.py to use declarative ORM (mapped classes)
  - Use sessionmaker(bind=engine) pattern
  - Test against SQLite in CI to ensure portability

## Missing Critical Features

**No Retry Mechanism for Failed Enrichments:**
- Problem: If enrichment fails partway through (e.g., API down after 50% of clusters), entire run is lost
- Blocks: Cannot resume partially-enriched runs; must restart from scratch
- Impact: Large enrichment jobs become high-risk; time-consuming
- Solution:
  - Save intermediate results to CSV/JSON after each cluster
  - Add `--resume-from-checkpoint` flag to enrich script
  - Estimated implementation: 2-3 hours

**No Audit Trail for Cluster Signal Changes:**
- Problem: If scoring weights or window logic changes, cannot trace which signals are affected
- Blocks: Cannot explain differences between two runs; makes backtesting validation hard
- Impact: Difficult to correlate performance changes with code changes
- Solution:
  - Add `detector_version` and `analysis_run_id` to cluster_events (partially present)
  - Log all parameter changes to separate audit table
  - Estimated implementation: 1-2 hours

**No Alert/Monitoring for Data Quality Issues:**
- Problem: If data loader fails silently (e.g., corrupted TSV), pipeline continues unaware
- Blocks: Cannot detect when "insiders" table is stale or incomplete
- Impact: Backtest results depend on silent failures; hard to debug
- Solution:
  - Add data quality checks after each load (count rows, validate date ranges)
  - Log warnings if counts drop unexpectedly
  - Estimated implementation: 1-2 hours

## Test Coverage Gaps

**Untested Area: Database Concurrency:**
- What's not tested: Multiple scripts writing to cluster_events simultaneously
- Files: `src/analytics/cluster_buys.py` (lines 330-350 INSERT with RETURNING)
- Risk: Race conditions in cluster_id generation; duplicate cluster detection
- Priority: High (risk of data corruption in production)
- Fix: Add integration test with multiple threads inserting clusters concurrently; verify PK/FK constraints

**Untested Area: API Error Handling Edge Cases:**
- What's not tested: Partial responses (e.g., API returns 200 but empty data), timeout behavior, rate limiting
- Files: `scripts/enrich_clusters_with_price.py` (error handling in _get_price_history, _get_fundamental_at_date)
- Risk: Silent failures; enrichment marked "partial" but data is unusable
- Priority: High (impacts backtest validity)
- Fix: Add mocked API responses for various failure modes; verify enrichment_status set correctly

**Untested Area: Large Data Volumes:**
- What's not tested: Performance with 100k+ transactions, memory limits
- Files: `src/analytics/cluster_buys.py` (DataFrame operations)
- Risk: Script runs out of memory on large quarters; unclear where limit is
- Priority: Medium (affects scalability)
- Fix: Parameterized load tests; measure memory usage; establish and document limits

**Untested Area: Data Quality and Nullability:**
- What's not tested: Null values in critical fields (ticker, trade_date, insider_name)
- Files: `src/analytics/cluster_buys.py` (groupby/agg operations assume no nulls)
- Risk: Silent aggregation errors; missing data in output
- Priority: Medium (data quality concern)
- Fix: Add validation tests; assert nullability assumptions at start of functions

**Untested Area: Fundamental Record Temporal Edge Cases:**
- What's not tested: What happens when no fundamentals exist within lookback window; forward-filling logic
- Files: `scripts/enrich_clusters_with_price.py` (lines 511-532, best candidate selection)
- Risk: Using next-period fundamentals from far future; market-cap-adjusted score becomes meaningless
- Priority: Medium (backtest validity)
- Fix: Add tests for _get_fundamental_at_date with sparse/missing data; document forward-fill behavior

---

*Concerns audit: 2026-02-03*
