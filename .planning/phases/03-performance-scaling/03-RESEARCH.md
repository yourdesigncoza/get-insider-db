# Phase 03: Performance & Scaling - Research

**Researched:** 2026-02-05
**Domain:** Python async I/O, connection pooling, streaming JSON, resilient retry patterns
**Confidence:** HIGH

## Summary

This phase transforms the synchronous enrichment pipeline into a production-ready async system capable of processing 500-2000 clusters efficiently. The current codebase uses `concurrent.futures.ThreadPoolExecutor` with max_workers=2 for parallel fetching, which is limited by Python's GIL for I/O-bound operations and creates only 2 concurrent connections regardless of workload.

Research confirms that the Python async ecosystem is mature: aiohttp 3.x provides async HTTP with built-in connection pooling, SQLAlchemy 2.0 has native asyncio support via `create_async_engine`, and tenacity already supports async decorators. ijson enables streaming JSON parsing to avoid loading entire files into memory. The migration path from ThreadPoolExecutor to asyncio is well-documented and can be done incrementally.

**Primary recommendation:** Replace `concurrent.futures.ThreadPoolExecutor` with `asyncio` + `aiohttp` for HTTP calls, use `asyncio.Semaphore` for rate limiting, configure SQLAlchemy async engine with `AsyncAdaptedQueuePool`, and add streaming JSON processing with ijson for large exports.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| aiohttp | 3.13.x | Async HTTP client | Built-in connection pooling, session reuse, widely adopted |
| asyncpg | 0.30.x | Async PostgreSQL driver | Native async, connection pooling, fastest Python PG driver |
| ijson | 3.4.x | Streaming JSON parser | Memory-efficient, multiple backends, async support |
| tenacity | 8.x | Retry logic | Already in use, supports async decorators natively |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| aiolimiter | 1.x | Time-based rate limiting | When API has requests/second limits (not just concurrent) |
| memory_profiler | 0.61.x | Memory debugging | During development to validate streaming works |
| tracemalloc | stdlib | Memory tracing | Production leak detection |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| aiohttp | httpx | httpx has sync+async API; aiohttp more mature for pure async |
| asyncpg | psycopg3 async | psycopg3 newer; asyncpg battle-tested, faster |
| ijson | json-stream | json-stream is pure Python; ijson has C backends |

**Installation:**
```bash
pip install aiohttp asyncpg ijson aiolimiter memory_profiler
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── async_client/
│   ├── __init__.py           # Async engine singleton
│   ├── http_client.py        # aiohttp session management
│   ├── rate_limiter.py       # Semaphore + time-based limiting
│   └── retry.py              # Async retry decorators
├── services/
│   ├── enrichment_service.py # Async enrichment logic
│   └── streaming.py          # ijson streaming processors
└── db/
    └── async_engine.py       # create_async_engine setup
```

### Pattern 1: Async HTTP Client with Session Reuse
**What:** Create single aiohttp ClientSession per application lifecycle
**When to use:** All async HTTP requests
**Example:**
```python
# Source: https://docs.aiohttp.org/en/stable/client_quickstart.html
import aiohttp
import asyncio

class AsyncHTTPClient:
    def __init__(self, base_url: str, max_connections: int = 30, per_host: int = 10):
        connector = aiohttp.TCPConnector(
            limit=max_connections,      # Total concurrent connections
            limit_per_host=per_host,    # Per-host limit
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"User-Agent": "insider-db/1.0"}
        )

    async def get(self, url: str, params: dict = None) -> dict:
        async with self._session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def close(self):
        await self._session.close()
        await asyncio.sleep(0.25)  # Allow SSL connections to close
```

### Pattern 2: Semaphore-Based Rate Limiting
**What:** Use asyncio.Semaphore to cap concurrent API calls
**When to use:** When API has concurrent connection limits
**Example:**
```python
# Source: https://rednafi.com/python/limit_concurrency_with_semaphore/
import asyncio

class RateLimitedClient:
    def __init__(self, client: AsyncHTTPClient, max_concurrent: int = 5):
        self._client = client
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch(self, url: str, params: dict = None) -> dict:
        async with self._semaphore:
            return await self._client.get(url, params)
```

### Pattern 3: Async SQLAlchemy Engine
**What:** Use create_async_engine with asyncpg for non-blocking DB access
**When to use:** When DB operations interleave with HTTP calls
**Example:**
```python
# Source: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

def get_async_engine():
    return create_async_engine(
        "postgresql+asyncpg://user:pass@localhost/db",
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,  # Recycle connections after 1 hour
    )

async_session_factory = async_sessionmaker(
    get_async_engine(),
    expire_on_commit=False,
    class_=AsyncSession,
)

# Usage - each task gets its own session
async def fetch_cached_price(ticker: str, date: datetime) -> float | None:
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT close_price FROM market_prices WHERE ticker = :t AND price_date = :d"),
            {"t": ticker, "d": date}
        )
        row = result.fetchone()
        return float(row[0]) if row else None
```

### Pattern 4: Streaming JSON with ijson
**What:** Parse large JSON files without loading into memory
**When to use:** Files with 500+ clusters (>10MB)
**Example:**
```python
# Source: https://pypi.org/project/ijson/
import ijson

async def stream_clusters(file_path: str):
    """Yield clusters one at a time from large JSON file."""
    with open(file_path, 'rb') as f:
        # Assumes structure: {"rows": [...], "metadata": {...}}
        for cluster in ijson.items(f, 'rows.item'):
            yield cluster

async def process_clusters_streaming(file_path: str, enricher):
    """Process clusters in streaming fashion."""
    async for cluster in stream_clusters(file_path):
        enriched = await enricher.enrich(cluster)
        yield enriched
```

### Pattern 5: Async Retry with Exponential Backoff + Jitter
**What:** Use tenacity with async support and jitter for distributed systems
**When to use:** All external API calls
**Example:**
```python
# Source: https://tenacity.readthedocs.io/en/latest/
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
)
import structlog

logger = structlog.get_logger(__name__)

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=1, max=30, jitter=5),
    retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
async def fetch_price_with_retry(client: RateLimitedClient, ticker: str, date: str) -> dict:
    url = "https://api.financialdatasets.ai/prices/"
    params = {"ticker": ticker, "start_date": date, "end_date": date}
    return await client.fetch(url, params)
```

### Anti-Patterns to Avoid
- **Creating ClientSession per request:** Session creation is expensive; reuse across requests
- **Sharing AsyncSession across tasks:** SQLAlchemy AsyncSession is NOT thread/task-safe
- **Using sync requests in async code:** Blocks the event loop; always use aiohttp
- **Forgetting to close sessions:** Use context managers or explicit cleanup
- **Unbounded concurrency:** Always use semaphores or connector limits

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async HTTP client | Custom urllib wrapper | aiohttp.ClientSession | Connection pooling, keep-alive, timeouts built-in |
| Rate limiting | Sleep-based throttling | asyncio.Semaphore + aiolimiter | Proper backpressure, no busy-waiting |
| Retry logic | Custom retry loops | tenacity async decorators | Jitter, backoff, logging hooks |
| Connection pooling | Manual connection tracking | aiohttp TCPConnector / asyncpg pool | Automatic lifecycle, overflow handling |
| JSON streaming | Custom chunked reading | ijson.items() | Handles edge cases, multiple backends |

**Key insight:** The current `concurrent.futures.ThreadPoolExecutor` approach blocks 2 threads waiting on I/O. Async eliminates this waste - a single thread can manage thousands of concurrent connections.

## Common Pitfalls

### Pitfall 1: Event Loop Blocking
**What goes wrong:** Calling sync code (requests, time.sleep) blocks entire event loop
**Why it happens:** Mixing sync and async code without adaptation
**How to avoid:** Use `run_in_executor()` for unavoidable sync code; prefer async alternatives
**Warning signs:** Throughput doesn't scale with concurrent tasks; high CPU with low actual work

### Pitfall 2: Unbounded Task Creation
**What goes wrong:** Creating thousands of tasks crashes with memory exhaustion
**Why it happens:** `asyncio.gather(*[task for item in huge_list])` without limits
**How to avoid:** Use `asyncio.Semaphore` to cap concurrent tasks; process in batches
**Warning signs:** Memory grows linearly with input size; OOM on large inputs

### Pitfall 3: Session Lifecycle Mismanagement
**What goes wrong:** "Session is closed" errors; connection leaks
**Why it happens:** Session closed before all requests complete; missing cleanup on errors
**How to avoid:** Use `async with` context managers; cleanup in finally blocks
**Warning signs:** Intermittent connection errors; increasing connection count over time

### Pitfall 4: Database Connection Starvation
**What goes wrong:** Async HTTP fast, but DB becomes bottleneck; timeouts on pool checkout
**Why it happens:** pool_size too small for concurrent tasks; long-held connections
**How to avoid:** Set `pool_size` + `max_overflow` >= expected concurrent tasks; use short sessions
**Warning signs:** "QueuePool limit" errors; tasks blocked waiting for DB connections

### Pitfall 5: Rate Limit Thundering Herd
**What goes wrong:** All retries fire simultaneously after backoff expires
**Why it happens:** Fixed backoff without jitter; multiple instances synced
**How to avoid:** Always use `wait_exponential_jitter`; add randomness to initial delay
**Warning signs:** Sudden traffic spikes after rate limit recovery; repeated 429s

### Pitfall 6: Async/Sync Engine Confusion
**What goes wrong:** "Cannot use asyncio in synchronous context" errors
**Why it happens:** Mixing `create_engine()` with async code or vice versa
**How to avoid:** Use `create_async_engine()` for async code; keep sync and async engines separate
**Warning signs:** Runtime errors about event loops; "greenlet" errors

## Code Examples

### Complete Async Enrichment Flow
```python
# Source: Derived from aiohttp + SQLAlchemy async patterns
import asyncio
import aiohttp
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

class AsyncEnricher:
    def __init__(self, db_url: str, api_key: str, max_concurrent: int = 10):
        # HTTP client with connection limits
        connector = aiohttp.TCPConnector(limit=50, limit_per_host=max_concurrent)
        timeout = aiohttp.ClientTimeout(total=30)
        self._http = aiohttp.ClientSession(connector=connector, timeout=timeout)
        self._api_key = api_key
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # Async database engine
        self._engine = create_async_engine(
            db_url.replace("postgresql://", "postgresql+asyncpg://"),
            pool_size=max_concurrent,
            max_overflow=max_concurrent,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def close(self):
        await self._http.close()
        await self._engine.dispose()
        await asyncio.sleep(0.25)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=30, jitter=5),
    )
    async def _fetch_price(self, ticker: str, date: str) -> dict | None:
        async with self._semaphore:
            url = "https://api.financialdatasets.ai/prices/"
            headers = {"X-API-KEY": self._api_key}
            params = {"ticker": ticker, "start_date": date, "end_date": date}
            async with self._http.get(url, headers=headers, params=params) as resp:
                if resp.status == 429:
                    raise aiohttp.ClientResponseError(
                        resp.request_info, resp.history, status=429
                    )
                resp.raise_for_status()
                return await resp.json()

    async def _check_cache(self, ticker: str, date: str) -> float | None:
        async with self._session_factory() as session:
            result = await session.execute(
                text("SELECT close_price FROM market_prices WHERE ticker=:t AND price_date=:d"),
                {"t": ticker, "d": date}
            )
            row = result.fetchone()
            return float(row[0]) if row else None

    async def _save_to_cache(self, ticker: str, date: str, price: float):
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO market_prices (ticker, price_date, close_price)
                    VALUES (:t, :d, :p) ON CONFLICT DO NOTHING
                """),
                {"t": ticker, "d": date, "p": price}
            )
            await session.commit()

    async def enrich_cluster(self, cluster: dict) -> dict:
        ticker = cluster.get("ticker")
        date = cluster.get("window_end")
        if not ticker or not date:
            return cluster

        # Check cache first
        cached = await self._check_cache(ticker, date)
        if cached:
            cluster["price_at_window_end"] = cached
            return cluster

        # Fetch from API
        try:
            data = await self._fetch_price(ticker, date)
            prices = data.get("prices", [])
            if prices:
                price = prices[0].get("close")
                if price:
                    cluster["price_at_window_end"] = price
                    await self._save_to_cache(ticker, date, price)
        except Exception as e:
            cluster["enrichment_error"] = str(e)

        return cluster

    async def enrich_batch(self, clusters: list[dict]) -> list[dict]:
        """Process clusters concurrently with semaphore limit."""
        tasks = [self.enrich_cluster(c) for c in clusters]
        return await asyncio.gather(*tasks)
```

### Migration from ThreadPoolExecutor
```python
# BEFORE (current sync pattern in enrich_clusters_with_price.py:628)
def enrich_row(row: Dict[str, Any]) -> Dict[str, Any]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_prices = executor.submit(_get_price_history, ticker, entry_date, price_fetch_end)
        future_fundamentals = executor.submit(_get_fundamental_at_date, ticker, entry_date, None)
        history = future_prices.result()
        fund_data = future_fundamentals.result()
    # ... process results ...

# AFTER (async pattern)
async def enrich_row_async(row: Dict[str, Any], client: AsyncEnricher) -> Dict[str, Any]:
    ticker = row.get("ticker")
    entry_date = row.get("entry_date")

    # Concurrent async calls - no thread overhead
    history_task = client.get_price_history(ticker, entry_date)
    fund_task = client.get_fundamentals(ticker, entry_date)

    history, fund_data = await asyncio.gather(history_task, fund_task)
    # ... process results ...

# Entry point
async def main():
    async with AsyncEnricher(db_url, api_key) as client:
        enriched = await asyncio.gather(*[
            enrich_row_async(row, client) for row in data["rows"]
        ])
```

### Streaming JSON Processing
```python
# Source: https://pypi.org/project/ijson/
import ijson
import json
from pathlib import Path

async def process_large_export(input_path: Path, output_path: Path, enricher: AsyncEnricher):
    """Process large JSON export with streaming to avoid memory issues."""
    # Read metadata first (small)
    with open(input_path, 'rb') as f:
        # Skip to metadata at end or parse separately
        pass

    # Stream clusters
    results = []
    batch_size = 50  # Process in batches for efficiency
    batch = []

    with open(input_path, 'rb') as f:
        for cluster in ijson.items(f, 'rows.item'):
            batch.append(cluster)
            if len(batch) >= batch_size:
                enriched = await enricher.enrich_batch(batch)
                results.extend(enriched)
                batch = []

        # Final batch
        if batch:
            enriched = await enricher.enrich_batch(batch)
            results.extend(enriched)

    # Write output
    output = {"rows": results, "metadata": {"enriched_at": datetime.now().isoformat()}}
    output_path.write_text(json.dumps(output, indent=2, default=str))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| requests (sync) | aiohttp (async) | 2018+ | 10-100x throughput for I/O-bound |
| ThreadPoolExecutor | asyncio.gather | Python 3.7+ | No thread overhead, better scaling |
| time.sleep rate limit | asyncio.Semaphore | 2020+ | Non-blocking, proper backpressure |
| SQLAlchemy sync | SQLAlchemy async | 2.0 (2023) | Native asyncio support |
| json.load() full file | ijson streaming | 2019+ | O(1) memory for large files |

**Deprecated/outdated:**
- `aiohttp < 3.0`: Major API changes; use 3.x
- `asyncio.get_event_loop()`: Use `asyncio.run()` or `asyncio.get_running_loop()`
- `@asyncio.coroutine` + `yield from`: Use `async def` + `await`

## Connection Pooling Configuration

### aiohttp TCPConnector Settings
```python
# Source: https://docs.aiohttp.org/en/stable/client_advanced.html
connector = aiohttp.TCPConnector(
    limit=100,           # Total connections (default: 100)
    limit_per_host=10,   # Per-host limit (default: 0 = unlimited)
    enable_cleanup_closed=True,  # Clean up closed connections
    force_close=False,   # Keep connections alive for reuse
    keepalive_timeout=30,  # Keepalive timeout in seconds
)
```

### SQLAlchemy AsyncAdaptedQueuePool Settings
```python
# Source: https://docs.sqlalchemy.org/en/20/core/pooling.html
engine = create_async_engine(
    db_url,
    pool_size=10,        # Persistent connections (default: 5)
    max_overflow=20,     # Additional temporary connections (default: 10)
    pool_timeout=30,     # Seconds to wait for connection (default: 30)
    pool_recycle=3600,   # Recycle connections after N seconds
    pool_pre_ping=True,  # Validate connection before use
)
```

### asyncpg Direct Pool (if not using SQLAlchemy)
```python
# Source: https://magicstack.github.io/asyncpg/current/usage.html
pool = await asyncpg.create_pool(
    dsn=db_url,
    min_size=5,                     # Minimum ready connections
    max_size=20,                    # Maximum connections
    max_queries=50000,              # Recycle after N queries
    max_inactive_connection_lifetime=300,  # Close idle after 5 min
    command_timeout=60,             # Query timeout
)
```

## Memory Profiling Tools

### Using memory_profiler
```python
# Source: https://pypi.org/project/memory-profiler/
from memory_profiler import profile

@profile
def process_clusters(data):
    """Run with: python -m memory_profiler script.py"""
    for cluster in data["rows"]:
        enrich(cluster)
```

### Using tracemalloc (stdlib)
```python
# Source: https://docs.python.org/3/library/tracemalloc.html
import tracemalloc

tracemalloc.start()
# ... process ...
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
```

## Open Questions

1. **Gradual vs Full Migration**
   - What we know: Async requires refactoring; can't mix sync/async freely
   - What's unclear: Should we migrate incrementally or all at once?
   - Recommendation: Create async enricher alongside sync; migrate when stable

2. **Rate Limit Strategy**
   - What we know: Financial Datasets API likely has per-second limits
   - What's unclear: Exact rate limits; concurrent vs time-based
   - Recommendation: Start with Semaphore(5); add aiolimiter if needed

3. **Batch Size Optimization**
   - What we know: Too small = overhead; too large = memory pressure
   - What's unclear: Optimal batch size for this workload
   - Recommendation: Start with 50 clusters; profile and adjust

4. **Error Aggregation**
   - What we know: asyncio.gather can fail-fast or return_exceptions
   - What's unclear: Best strategy for partial failures
   - Recommendation: Use `return_exceptions=True`; aggregate errors in results

## Sources

### Primary (HIGH confidence)
- [aiohttp Client Documentation](https://docs.aiohttp.org/en/stable/client_quickstart.html) - Session management, connector settings
- [SQLAlchemy 2.0 Asyncio Extension](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) - Async engine, session patterns
- [SQLAlchemy Connection Pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html) - Pool configuration parameters
- [tenacity Documentation](https://tenacity.readthedocs.io/en/latest/) - Async retry, jitter
- [ijson PyPI](https://pypi.org/project/ijson/) - Streaming JSON, version 3.4.0

### Secondary (MEDIUM confidence)
- [Limit Concurrency with Semaphore](https://rednafi.com/python/limit_concurrency_with_semaphore/) - Rate limiting patterns
- [asyncpg Usage Guide](https://magicstack.github.io/asyncpg/current/usage.html) - Pool configuration

### Tertiary (LOW confidence)
- WebSearch results on async migration patterns - Need validation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - aiohttp, SQLAlchemy async are established
- Architecture patterns: HIGH - From official documentation
- Connection pooling: HIGH - Official SQLAlchemy/aiohttp docs
- Pitfalls: MEDIUM - Some based on experience patterns, not official docs
- Code examples: MEDIUM - Adapted from docs, not tested in this codebase

**Research date:** 2026-02-05
**Valid until:** 2026-03-05 (30 days for stable patterns)
