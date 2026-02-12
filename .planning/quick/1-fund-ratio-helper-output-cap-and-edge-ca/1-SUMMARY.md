---
phase: quick
plan: 1
subsystem: cluster-detection
tags:
  - refactor
  - testing
  - data-integrity
dependency_graph:
  requires: []
  provides:
    - calc_fund_ratio helper function
  affects:
    - src/analytics/cluster_buys.py
    - tests/test_fund_ratio_filtering.py
tech_stack:
  added: []
  patterns:
    - DRY: Extracted inline computation into reusable helper
    - Data integrity: Cap ratio at 1.0 for bad source data
    - Defensive programming: Zero/negative denominator safety
key_files:
  created: []
  modified:
    - src/analytics/cluster_buys.py
    - tests/test_fund_ratio_filtering.py
decisions: []
metrics:
  duration_minutes: 3
  completed_date: 2026-02-12
---

# Quick Task 1: Fund Ratio Helper, Output Cap, and Edge Cases

**One-liner:** Extract fund_ratio computation into calc_fund_ratio() helper with 1.0 cap and zero-denom safety, add 9 edge case tests covering boundary conditions identified in Gemini review.

## Objective

Eliminate the zero-insider paradox between filter logic (excludes total=0) and output field (returns 0.0 for total=0), cap ratio at 1.0 for data integrity, and cover edge cases the existing test suite missed.

## Execution Summary

### Tasks Completed

**Task 1: Create calc_fund_ratio helper and wire into both functions** (commit: `614ce77`)
- Added module-level `calc_fund_ratio(num_fund_like, total_insiders)` helper
- Returns 0.0 for zero/negative denominators (no division error)
- Caps result at 1.0 for data integrity (handles bad source data where num_fund_like > total_insiders)
- Replaced inline computation in `find_cluster_buys()` (line 769)
- Replaced inline computation in `find_tradeable_cluster_signals()` (line 1162)
- Both functions now use consistent helper instead of `float(num_fund_like / max(total_unique_insiders, 1))`

**Task 2: Add edge case tests** (commit: `26c4583`)
- Added `TestCalcFundRatioHelper` class (5 tests):
  - Zero denominator returns 0.0
  - Negative denominator returns 0.0
  - Normal ratio computation
  - Cap at 1.0 when fund_like exceeds total (bad data)
  - Exact 1.0 ratio not capped
- Added `TestFundRatioEdgeCases` class (4 tests):
  - max_fund_ratio=0 excludes all clusters (0.0 < 0 is False)
  - Float precision at 1/3 boundary (exact match excluded)
  - Just below 1/3 boundary passes
  - Bad data (fund_like > total) caps at 1.0
- Updated `TestFundRatioInOutput` (2 tests) to use helper directly
- Total: 18 tests (9 original + 9 new)

### Verification Results

All verification checks passed:
- `calc_fund_ratio` importable from `src.analytics.cluster_buys`
- Zero inline ratio math remaining (grep count: 0)
- Helper used in 3 places (1 definition + 2 call sites)
- 18 tests in `test_fund_ratio_filtering.py`, all passing
- Full test suite: 176 passed, 2 skipped (32 pre-existing async failures unrelated to changes)

## Deviations from Plan

None - plan executed exactly as written.

## Technical Details

### Helper Function

```python
def calc_fund_ratio(num_fund_like: int, total_insiders: int) -> float:
    """Compute fund ratio with zero-denom safety and 1.0 cap.

    Returns 0.0 when total_insiders <= 0.
    Caps result at 1.0 for data integrity (handles bad source data
    where num_fund_like > total_insiders).
    """
    if total_insiders <= 0:
        return 0.0
    return min(num_fund_like / total_insiders, 1.0)
```

### Key Behaviors Tested

1. **Zero-denom safety:** `calc_fund_ratio(0, 0) == 0.0` (no ZeroDivisionError)
2. **Negative-denom safety:** `calc_fund_ratio(3, -1) == 0.0` (defensive)
3. **Data integrity cap:** `calc_fund_ratio(5, 3) == 1.0` (bad source data capped)
4. **Filter exclusion:** `max_fund_ratio=0` excludes everything (0.0 < 0 is False)
5. **Float precision:** 1/3 boundary behaves correctly (exact match excluded)

### Impact

- **DRY:** Single helper replaces 2 inline computations
- **Consistency:** Both output locations use identical logic
- **Safety:** No division errors on edge cases
- **Integrity:** Ratio never exceeds 1.0 in output, even with bad data
- **Coverage:** 9 new tests covering boundary conditions from Gemini review

## Self-Check

Verifying claims in this summary:

```bash
# Check helper function exists and is importable
python -c "from src.analytics.cluster_buys import calc_fund_ratio; print('OK')"
# Output: OK

# Check no inline ratio computation remains
grep -c "num_fund_like / max(total_unique_insiders, 1)" src/analytics/cluster_buys.py
# Output: 0

# Check helper usage (1 def + 2 calls)
grep -c "calc_fund_ratio" src/analytics/cluster_buys.py
# Output: 3

# Check test count
pytest tests/test_fund_ratio_filtering.py --collect-only | grep "tests collected"
# Output: 18 tests collected

# Check all tests pass
pytest tests/test_fund_ratio_filtering.py -v
# Output: 18 passed
```

**Self-Check Result:** PASSED

All files exist, helper is used correctly, tests pass.

## Next Phase Readiness

N/A - Quick task complete, no blockers for future work.
