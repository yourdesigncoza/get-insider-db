---
phase: 10-window-span-validation
plan: 01
subsystem: cluster-detection

tags: [data-quality, window-merging, span-validation]

requires:
  - phase: 09-n-a-ticker-exclusion
    provides: Clean ticker filtering for valid cluster detection
provides:
  - Span-validated window merging that enforces window_days constraint
  - Regression test suite for merge logic boundary cases
affects: [11-ticker-deduplication-in-overlaps, 13-duplicate-ticker-handling]

tech-stack:
  added: []
  patterns: [span-constraint-validation, separate-overlapping-windows]

key-files:
  created:
    - tests/test_window_span_validation.py
  modified:
    - src/analytics/cluster_buys.py

key-decisions:
  - "When overlapping windows would create span > window_interval, keep both as separate cluster events (Phase 13 will handle ticker deduplication)"

duration: 2min
completed: 2026-02-11
---

# Phase 10 Plan 01: Window Span Validation Summary

**Enforced window_days constraint in merge logic; overlapping windows exceeding span kept separate**

## Performance
- **Duration:** 2 minutes
- **Started:** 2026-02-11T17:08:42Z
- **Completed:** 2026-02-11T17:10:40Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments

Fixed DATA-01 critical data quality issue where 9 of 20 clusters had window spans up to 37 days (configured limit: 10 days). Root cause: merge loop extended `last_end` via `max(last_end, end)` without validating resulting span.

### Task 1: Span validation in merge logic
- Added span check before merging overlapping windows
- Formula: `(proposed_end - last_start).days <= window_interval`
- When constraint violated, overlapping window kept as separate cluster event
- No changes to post-merge metric recomputation (already handles separate intervals correctly)

### Task 2: Regression test suite
- 11 tests covering all merge scenarios
- Boundary cases: exact window_interval (passes), window_interval+1 (rejects)
- Edge cases: empty input, single window, identical windows, adjacent windows
- Adversarial: chain of 4 overlapping windows (validates output invariant)
- All tests pass

## Task Commits

1. **Task 1: Add span validation to window merging logic** - `9408698` (fix)
   - Modified merge loop at lines 567-575 in `cluster_buys.py`
   - Added `proposed_end` calculation and span validation
   - Overlapping windows exceeding span kept separate

2. **Task 2: Add regression tests for window span validation** - `f0caa56` (test)
   - Created `tests/test_window_span_validation.py` (144 lines)
   - Helper function `merge_intervals_with_span_check()` replicates prod logic
   - 11 tests with 100% pass rate

## Files Created/Modified

- `src/analytics/cluster_buys.py` - Added span validation to window merge loop (lines 573-577)
- `tests/test_window_span_validation.py` - New test suite with 11 regression tests

## Decisions Made

**Overlap handling strategy:** When overlapping windows would create span > window_interval, keep both as separate cluster events rather than:
- Option A: Truncate merged window (loses data)
- Option B: Keep both ✓ (selected - preserves all signals, Phase 13 will deduplicate tickers)

This decision defers ticker deduplication to Phase 13 (Duplicate Ticker Handling), maintaining single-responsibility for this phase.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The variable `window_interval` was already in scope for the merge loop (defined at line 272), so no scope adjustments were needed.

## Next Phase Readiness

**Status:** Ready for Phase 11 (Ticker Deduplication in Overlaps)

**Blockers:** None

**Dependencies satisfied:**
- Window spans now respect window_days constraint
- Separate overlapping windows preserved for Phase 11 deduplication logic
- Test coverage for all boundary cases

**Output contract:**
- Every merged window span satisfies: `(window_end - window_start).days <= window_days - 1`
- Overlapping windows with span violations kept as separate cluster events
- Post-merge metric recomputation works correctly for both merged and separate intervals

## Self-Check: PASSED

**Files created:**
```bash
$ ls -1 /home/laudes/zoot/projects/get-insider-db/tests/test_window_span_validation.py
/home/laudes/zoot/projects/get-insider-db/tests/test_window_span_validation.py
```

**Commits exist:**
```bash
$ git log --oneline -2
f0caa56 test(10-01): add regression tests for window span validation
9408698 fix(10-01): add span validation to window merging logic
```

**Tests pass:**
```bash
$ pytest tests/test_window_span_validation.py -q
11 passed in 0.02s
```

**Modified code verified:**
```bash
$ grep -c "proposed_end" src/analytics/cluster_buys.py
3
$ grep -c "window_interval" src/analytics/cluster_buys.py
5
```

All verifications passed.
