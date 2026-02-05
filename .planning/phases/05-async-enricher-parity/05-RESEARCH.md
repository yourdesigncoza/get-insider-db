# Phase 05: Async Enricher Parity - Research

**Researched:** 2026-02-05
**Domain:** Async Python / YFinance Integration / Checkpoint Resume
**Confidence:** HIGH

## Summary

This phase closes two integration gaps identified in the M1 audit:
1. YFinance fallback missing in async enricher (sync has it at lines 284-321)
2. Checkpointing missing in async enricher (sync uses CheckpointManager)

The research confirms that both features are straightforward to port. The sync script (`enrich_clusters_with_price.py`) provides working reference implementations. The main challenge is that yfinance is synchronous and must be wrapped for async use via `asyncio.to_thread()`. The CheckpointManager is already async-compatible since it uses standard SQLAlchemy which can be called from async code using thread isolation.

**Primary recommendation:** Wrap yfinance with `asyncio.to_thread()` for async-safe fallback. Integrate existing CheckpointManager into async CLI script with minimal changes.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| yfinance | 1.1.0 | Yahoo Finance data fallback | Free, no API key, already in sync script |
| asyncio (stdlib) | 3.10+ | Async primitives | Built-in `to_thread()` for sync wrapping |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sqlalchemy | 2.0+ | CheckpointManager | Already exists, reuse sync version |
| tenacity | 8.0+ | Retry logic | Already in async_client/retry.py |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| yfinance | yahooquery | More async-native but new dependency, API different |
| yfinance | yfinance-ez | Has async methods but less mature |
| asyncio.to_thread | run_in_executor | to_thread is simpler, handles context vars |

**Installation:**
```bash
# Already installed - no new dependencies required
pip show yfinance  # v1.1.0 confirmed
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── async_client/         # HTTP client, DB engine, retry (Phase 03)
├── services/
│   ├── enrichment_service.py  # AsyncEnricher class (modify for fallback)
│   └── streaming.py           # ijson streaming (no changes)
├── checkpointing/
│   └── checkpoint_manager.py  # Sync CheckpointManager (reuse as-is)
scripts/
└── enrich_clusters_async.py   # Async CLI (modify for checkpointing)
```

### Pattern 1: Sync-to-Async Wrapper for YFinance
**What:** Use `asyncio.to_thread()` to run blocking yfinance calls without blocking the event loop
**When to use:** When calling any synchronous library (yfinance, requests) from async code
**Example:**
```python
# Source: Python docs - asyncio.to_thread
import asyncio
import yfinance as yf

async def fetch_price_yfinance_async(ticker: str, target_date: date) -> float | None:
    """Async wrapper for synchronous yfinance call."""
    return await asyncio.to_thread(_fetch_price_yfinance_sync, ticker, target_date)

def _fetch_price_yfinance_sync(ticker: str, target_date: date) -> float | None:
    """Synchronous yfinance fetch (copied from sync script lines 284-321)."""
    try:
        stock = yf.Ticker(ticker)
        start = target_date - timedelta(days=7)
        end = target_date + timedelta(days=1)
        hist = stock.history(start=start.isoformat(), end=end.isoformat(), auto_adjust=True, repair=True)
        if hist.empty:
            return None
        hist.index = hist.index.date
        valid_dates = [d for d in hist.index if d <= target_date]
        if not valid_dates:
            return None
        closest_date = max(valid_dates)
        return float(hist.loc[closest_date, 'Close'])
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
```

### Pattern 2: Fallback Chain in Async Context
**What:** Primary API -> Fallback API pattern with error handling
**When to use:** When primary API fails (400, empty response)
**Example:**
```python
# Source: Existing sync script pattern (lines 748-764)
async def get_price_with_fallback(self, ticker: str, entry_date: datetime) -> tuple[list[dict], bool]:
    """Get prices with YFinance fallback on primary API failure."""
    used_fallback = False

    # Try primary API
    history = await self.get_price_history(ticker, entry_date, fetch_end)

    # Check if fallback needed
    base_record = _get_first_price_record_on_or_after(history, entry_date)
    if not history or base_record is None:
        # Try YFinance fallback
        fallback_price = await self._fetch_price_yfinance_async(ticker, entry_date.date())
        if fallback_price is not None:
            used_fallback = True
            # Return synthetic history with just the base price

    return history, base_record, used_fallback
```

### Pattern 3: Checkpoint Integration in Streaming Loop
**What:** Save checkpoint after N clusters, resume on restart
**When to use:** Long-running batch jobs that may crash
**Example:**
```python
# Source: Existing sync script pattern (lines 911-918)
CHECKPOINT_FREQUENCY = 25

for i, cluster in enumerate(clusters):
    enriched = await enricher.enrich_cluster(cluster)
    enriched_rows.append(enriched)
    processed_tickers.append(enriched.get("ticker", f"row_{i}"))

    if (i + 1) % CHECKPOINT_FREQUENCY == 0:
        checkpoint_mgr.save_checkpoint(
            run_id=run_id,
            last_index=i,
            processed_tickers=processed_tickers,
            errors=errors,
        )
```

### Anti-Patterns to Avoid
- **Blocking in async:** Calling yfinance directly without `to_thread()` blocks the event loop
- **Shared mutable state:** yfinance is not thread-safe, don't share Ticker objects between coroutines
- **Checkpoint in batch:** Don't checkpoint during batch processing, only between batches

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sync-to-async wrapping | Custom thread pool | `asyncio.to_thread()` | Handles context vars, built-in since 3.9 |
| Checkpoint storage | File-based JSON | CheckpointManager (exists) | JSONB, atomic upserts, already tested |
| YFinance data fetching | Custom Yahoo scraper | yfinance library | Handles splits, dividends, edge cases |

**Key insight:** Both features are ports of existing sync code. The sync script is the reference implementation.

## Common Pitfalls

### Pitfall 1: YFinance Not Thread-Safe
**What goes wrong:** Concurrent yfinance calls with same ticker can corrupt results
**Why it happens:** yfinance uses shared global dictionary for downloads
**How to avoid:** Create new Ticker object per call, don't cache Ticker instances
**Warning signs:** Intermittent wrong prices, test failures with concurrent tests

### Pitfall 2: Blocking the Event Loop
**What goes wrong:** Async enrichment becomes as slow as sync
**Why it happens:** Calling `yf.Ticker().history()` directly from async code
**How to avoid:** Always wrap with `asyncio.to_thread()`
**Warning signs:** Cluster-per-second rate drops to sync levels

### Pitfall 3: Checkpoint Frequency Too High
**What goes wrong:** DB I/O bottleneck, slower enrichment
**Why it happens:** Checkpointing after every cluster
**How to avoid:** Default frequency of 25 rows (matches sync script)
**Warning signs:** Enrichment time increases, DB connections spike

### Pitfall 4: Missing Checkpoint on Clean Exit
**What goes wrong:** Checkpoint not cleared, resume starts from wrong position
**Why it happens:** Forgetting to call `clear_checkpoint()` on success
**How to avoid:** Always clear checkpoint after successful completion
**Warning signs:** --no-resume flag needed for every run

### Pitfall 5: Streaming Mode Incompatible with Simple Checkpointing
**What goes wrong:** Can't resume streaming mode since output is written incrementally
**Why it happens:** Streaming writes partial JSON, can't "rewind"
**How to avoid:** For simplicity, checkpointing only in memory mode (<50 clusters) OR use checkpoint to track input position only
**Warning signs:** Corrupted output files, duplicate enrichment

## Code Examples

Verified patterns from existing codebase:

### YFinance Sync Fetch (Reference from sync script lines 284-321)
```python
# Source: scripts/enrich_clusters_with_price.py
def _fetch_price_yfinance(ticker: str, target_date: date) -> Optional[float]:
    """Fetch price from YFinance as fallback."""
    try:
        stock = yf.Ticker(ticker)
        start = target_date - timedelta(days=7)
        end = target_date + timedelta(days=1)

        hist = stock.history(
            start=start.isoformat(),
            end=end.isoformat(),
            auto_adjust=True,
            repair=True,
        )

        if hist.empty:
            return None

        hist.index = hist.index.date
        valid_dates = [d for d in hist.index if d <= target_date]
        if not valid_dates:
            return None

        closest_date = max(valid_dates)
        price = float(hist.loc[closest_date, 'Close'])
        return price
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        logger.error("yfinance_fallback_failed", ticker=ticker, error=str(e))
        return None
```

### CheckpointManager Integration (Reference from sync script lines 868-931)
```python
# Source: scripts/enrich_clusters_with_price.py
def process_file(file_path: Path, resume: bool = True):
    engine = get_engine()
    checkpoint_mgr = CheckpointManager(engine)
    run_id = f"enrich_{file_path.stem}"

    # Check for existing checkpoint
    start_index = 0
    processed_tickers: List[str] = []
    errors: Dict[str, str] = {}

    if resume:
        checkpoint = checkpoint_mgr.get_checkpoint(run_id)
        if checkpoint:
            start_index = checkpoint["last_index"] + 1
            processed_tickers = list(checkpoint["processed_tickers"])
            errors = dict(checkpoint["errors"])
            logger.info(f"Resuming from checkpoint: row {start_index}/{total}")

    # ... processing loop with periodic checkpoint saves ...

    # Clear checkpoint on success
    checkpoint_mgr.clear_checkpoint(run_id)
```

### Async Enrichment with Fallback (Target pattern)
```python
# Target: src/services/enrichment_service.py
async def _fetch_price_yfinance_async(self, ticker: str, target_date: date) -> float | None:
    """Async wrapper for yfinance fallback."""
    try:
        return await asyncio.to_thread(
            self._fetch_price_yfinance_sync, ticker, target_date
        )
    except Exception as e:
        logger.error("yfinance_async_failed", ticker=ticker, error=str(e))
        return None

def _fetch_price_yfinance_sync(self, ticker: str, target_date: date) -> float | None:
    """Synchronous yfinance fetch."""
    # Copy from sync script
    ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| run_in_executor | asyncio.to_thread | Python 3.9 | Simpler API, context var propagation |
| yfinance 0.1.x | yfinance 1.1.0 | 2025 | WebSocket support, better repair mode |

**Deprecated/outdated:**
- `loop.run_in_executor()`: Still works but `asyncio.to_thread()` is preferred for simple cases

## Open Questions

None. Both features have clear reference implementations in the sync script.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `scripts/enrich_clusters_with_price.py` - YFinance fallback (lines 284-321), Checkpointing (lines 868-931)
- Existing codebase: `src/checkpointing/checkpoint_manager.py` - CheckpointManager class
- Python docs: `asyncio.to_thread()` documentation

### Secondary (MEDIUM confidence)
- [PyPI yfinance](https://pypi.org/project/yfinance/) - yfinance 1.1.0 with WebSocket support
- [Python asyncio docs](https://docs.python.org/3/library/asyncio-task.html) - asyncio.to_thread best practices

### Tertiary (LOW confidence)
- [GitHub yfinance#2557](https://github.com/ranaroussi/yfinance/issues/2557) - Thread safety concerns (not fully verified)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Using existing dependencies
- Architecture: HIGH - Porting existing patterns from sync script
- Pitfalls: HIGH - Known issues from yfinance docs and codebase experience

**Research date:** 2026-02-05
**Valid until:** 2026-03-05 (30 days - stable patterns)
