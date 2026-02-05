---
phase: 02-architectural-stabilization
plan: 04
subsystem: error-handling
tags: [python, exceptions, scripts, logging, observability]

# Dependency graph
requires:
  - phase: 02-architectural-stabilization
    plan: 01
    provides: Custom exception hierarchy (EnrichmentError, InvalidTickerError, RateLimitError)
  - phase: 02-architectural-stabilization
    plan: 02
    provides: Structured logging with get_logger()
provides:
  - Specific exception handling in enrich_clusters_with_price.py (0 bare Exception)
  - Specific exception handling in backtest_cluster_strategy.py (0 bare Exception)
  - Structured logging throughout enrichment and backtest scripts
  - ImportError-based optional dependency handling pattern
affects: [enrichment-pipeline, backtesting, operational-observability]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Specific exception types over bare Exception in scripts
    - Structured logging context for all error paths (ticker, error_type)
    - ImportError for optional dependency graceful degradation

key-files:
  created: []
  modified:
    - scripts/enrich_clusters_with_price.py
    - scripts/backtest_cluster_strategy.py
    - scripts/show_cluster_buys.py

key-decisions:
  - "Replace bare Exception with specific types for diagnosable errors"
  - "Use structured logging (get_logger) for all error paths with context"
  - "ImportError (not Exception) for optional import graceful degradation"
  - "Remove duplicate exception classes from scripts, use src.exceptions hierarchy"

patterns-established:
  - "Script error handling: Import custom exceptions, use specific types, add structured context"
  - "API errors: requests.RequestException, json.JSONDecodeError, KeyError, ValueError"
  - "Data processing: ValueError, KeyError, TypeError for parsing/calculation errors"
  - "Optional imports: ImportError with descriptive comment for graceful degradation"

# Metrics
duration: 3min
completed: 2026-02-05
---

# Phase 02 Plan 04: Script Exception Handling Summary

**Replaced 9 bare `except Exception` blocks with specific exception types across enrichment and backtest scripts; added structured logging to all error paths**

## Objective

Replace bare `except Exception` blocks in enrichment and backtest scripts with specific exception handling using the custom exception hierarchy from Plan 02-01. Enable meaningful error diagnosis in scripts and prevent silent data loss during enrichment.

## What Was Built

### Exception Handling Updates

**scripts/enrich_clusters_with_price.py (7 blocks updated):**
- Line ~278: API fetch errors → `requests.RequestException, json.JSONDecodeError, KeyError, ValueError`
- Line ~317: YFinance fallback → `ValueError, KeyError, TypeError, AttributeError`
- Line ~553: Financial metrics API → `requests.RequestException, json.JSONDecodeError, KeyError`
- Line ~623: Fundamental processing → `ValueError, KeyError, TypeError`
- Line ~728: Price fetch fatal → `ValueError, KeyError, TypeError, AttributeError`
- Line ~738: Fundamentals fetch → `ValueError, KeyError, TypeError, AttributeError`
- Line ~852: JSON parsing → `OSError, json.JSONDecodeError`

**scripts/backtest_cluster_strategy.py (2 blocks updated):**
- Line ~53: Date parsing in enrichment index → `ValueError`
- Line ~275: Date parsing in backtest logic → `ValueError`

**scripts/show_cluster_buys.py (2 blocks updated):**
- Line ~19: Optional tabulate import → `ImportError`
- Line ~25: Optional rich import → `ImportError`

### Structured Logging Integration

- Imported `get_logger()` from `src.logging_config` in all modified scripts
- Added structured context to all error paths: `ticker`, `error`, `error_type`
- Removed duplicate exception classes (AlphaVantageError, InvalidTickerError) from enrich_clusters_with_price.py
- Now uses centralized exception hierarchy from `src.exceptions`

### Verification Results

```bash
# Bare Exception count
enrich_clusters_with_price.py: 0
backtest_cluster_strategy.py: 0
show_cluster_buys.py: 0

# All scripts load without errors
python scripts/enrich_clusters_with_price.py --help ✓
python scripts/backtest_cluster_strategy.py --help ✓

# Test suite
pytest tests/ -v: 28 passed, 1 skipped in 0.60s ✓
```

## Technical Implementation

### Exception Type Selection Pattern

**API/Network operations:**
```python
except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
    logger.warning("api_request_failed", ticker=ticker, error=str(e), error_type=type(e).__name__)
```

**Data parsing/processing:**
```python
except (ValueError, KeyError, TypeError) as e:
    logger.warning("data_processing_error", ticker=ticker, error=str(e), error_type=type(e).__name__)
```

**Optional imports (graceful degradation):**
```python
try:
    from tabulate import tabulate
except ImportError:  # Optional dependency - graceful degradation
    tabulate = None
```

### Logging Context Pattern

All error handlers include:
- **Event name**: `api_request_failed`, `yfinance_fallback_failed`, `fundamental_processing_error`
- **Entity context**: `ticker=ticker`, `file=str(file_path)`
- **Error details**: `error=str(e)`, `error_type=type(e).__name__`

This enables filtering in production logs: `grep "api_request_failed" | grep "ticker=AAPL"`

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Use specific exception types | Enable meaningful error diagnosis vs. catch-all | Errors now diagnosable by type |
| Add structured logging context | Production observability requirement | All errors traceable to entity |
| ImportError for optional imports | More specific than Exception for imports | Clearer intent for degradation |
| Remove duplicate exception classes | Single source of truth in src.exceptions | Consistent hierarchy usage |

## Deviations from Plan

None - plan executed exactly as written.

## Test Results

All 28 tests passed (1 skipped):
- Batch classification tests: 3/4 passed (1 skipped - expected)
- Cluster scoring tests: All passed
- Insider classification tests: All passed
- Loader tests: All passed
- Look-ahead bias tests: All passed
- Tradeable window selection tests: All passed

No regressions introduced by exception handling changes.

## Next Phase Readiness

**Phase 02 Plan 05 Dependencies Met:**
- ✓ Exception hierarchy available for database batch operations
- ✓ Structured logging available for N+1 query fixes
- ✓ Error handling patterns established for classification pipeline

**Known Issues:**
- None - all scripts load and tests pass

**Documentation Debt:**
- Exception handling patterns could be documented in a CONTRIBUTING.md guide
- Error code catalog could help with debugging (not blocking)

## Files Modified

| File | Changes | Lines | Bare Exception Before | After |
|------|---------|-------|----------------------|-------|
| scripts/enrich_clusters_with_price.py | Exception handling + logging | 7 blocks | 7 | 0 |
| scripts/backtest_cluster_strategy.py | Exception handling + logging | 2 blocks | 2 | 0 |
| scripts/show_cluster_buys.py | ImportError specificity | 2 blocks | 2 | 0 |

**Total:** 3 files, 11 exception blocks updated, 0 bare `except Exception` remaining

## Commits

| Commit | Message | Files |
|--------|---------|-------|
| 0fbadb3 | refactor(02-04): replace bare Exception with specific handlers in enrich_clusters_with_price.py | scripts/enrich_clusters_with_price.py |
| 36e3167 | refactor(02-04): replace bare Exception with specific handlers in backtest_cluster_strategy.py | scripts/backtest_cluster_strategy.py |
| 7661fd9 | refactor(02-04): use ImportError instead of Exception for optional imports in show_cluster_buys.py | scripts/show_cluster_buys.py |

## Key Learnings

1. **Specific exceptions enable diagnosis**: Moving from `except Exception` to `requests.RequestException` immediately tells you it's a network issue, not a parsing error
2. **Structured logging context is critical**: Adding `ticker=ticker` to every error means you can filter production logs by entity
3. **Optional imports deserve clarity**: `except ImportError` is more explicit than `except Exception` for graceful degradation
4. **Centralized exception hierarchy pays off**: Removing duplicate exception classes from scripts enforces single source of truth

## Success Metrics

- ✅ 0 bare `except Exception` in enrich_clusters_with_price.py
- ✅ 0 bare `except Exception` in backtest_cluster_strategy.py
- ✅ ImportError used for optional imports in show_cluster_buys.py
- ✅ All scripts import custom exceptions from src/exceptions.py
- ✅ All scripts use structured logging via get_logger()
- ✅ All scripts load without import errors
- ✅ All tests pass (28/28)
