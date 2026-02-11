# Phase 10: Window Span Validation - Research

**Researched:** 2026-02-11
**Domain:** Sliding window algorithm and interval merging logic
**Confidence:** HIGH

## Summary

Phase 10 addresses DATA-01: window spans in cluster scan output exceed the configured `window_days=10` parameter. Empirical analysis of recent cluster output reveals 9 violations in 20 samples, with spans ranging from 10-37 days (expected: ≤9 days for a 10-day window).

Root cause identified: The window merging logic in `cluster_buys.py` lines 564-575 merges overlapping windows by extending `last_end` to `max(last_end, end)`, creating merged spans that can exceed `window_days`. This is correct for consolidating duplicate cluster events, but lacks post-merge validation.

**Primary recommendation:** Add post-merge span validation to cap merged windows at `window_days - 1` (inclusive range), split oversized windows if needed, and add regression tests for window span constraints.

## Evidence from Codebase

### Current Window Merging Behavior

**File:** `src/analytics/cluster_buys.py` lines 564-575

```python
for ticker_value, tdf in df.groupby("ticker"):
    intervals = sorted(zip(tdf["window_start"], tdf["window_end"]), key=lambda x: x[0])
    merged_intervals: list[tuple[date, date]] = []
    for start, end in intervals:
        if not merged_intervals:
            merged_intervals.append((start, end))
            continue
        last_start, last_end = merged_intervals[-1]
        if start <= last_end:  # overlap condition
            merged_intervals[-1] = (last_start, max(last_end, end))
        else:
            merged_intervals.append((start, end))
```

**Issue:** The merge extends `last_end` to `max(last_end, end)` without validating that `(last_start, extended_end)` still satisfies `extended_end - last_start <= window_days - 1`.

### Empirical Evidence

Sample from `exports/cluster_runs/my_run.json` (window_days=10, expected max span=9):

```
Violations (span > 9): 9 out of 20 samples
Max span seen: 37 days

Examples:
- AMCR: 2025-11-01 to 2025-11-12 = 11 days (+2 over limit)
- HYNE: 2025-11-24 to 2025-12-05 = 11 days (+2 over limit)
- N/A:  2025-11-22 to 2025-12-29 = 37 days (+28 over limit)
- VAC:  2025-11-05 to 2025-11-25 = 20 days (+11 over limit)
```

Note: The "N/A" ticker violation (37 days) is now prevented by Phase 9's ticker exclusion, but the merging logic bug remains.

### SQL Window Generation

**File:** `src/analytics/cluster_buys.py` lines 284-383

The SQL query computes transaction-date windows as:

```sql
window_start = transaction_date - INTERVAL '1 day' * :window_interval
window_end = transaction_date
```

Where `window_interval = window_days - 1` (e.g., for window_days=10, interval=9).

**This is correct** - each window is 9 days inclusive (day 0 to day 9 = 10 days total).

The SQL produces valid per-transaction windows. **The bug occurs during Python-side merging.**

### Window Detection Algorithm

**File:** `src/analytics/window_detection.py` lines 8-66

```python
def best_qualifying_window_indices(
    revealed_df: pd.DataFrame,
    *,
    window_interval_days: int,
    min_insiders: int,
    min_total_value: float,
) -> Optional[tuple[int, int]]:
    # Sliding window with constraint:
    while left <= right and (tdates[right] - tdates[left]).days > window_interval_days:
        # Shrink window from left
```

**This is correct** - the sliding window enforces `(end - start).days <= window_interval_days`.

The algorithm itself respects the window constraint. **The bug is in how `find_cluster_buys()` merges the SQL-generated windows.**

## Architecture Context

From `.planning/codebase/ARCHITECTURE.md` line 105-107:

```
7. Windows merged by ticker to handle overlapping periods
8. For each merged window:
   - Grouped by normalized insider name
```

**Purpose of merging:** Consolidate overlapping cluster events for the same ticker to avoid duplicate signals.

**Design tradeoff:** Merging prevents duplicate alerts but can create windows exceeding `window_days` if not constrained.

## Standard Stack

### Core Dependencies

Already in place - no new libraries required:

| Library | Version | Purpose |
|---------|---------|---------|
| pandas | Current | Date arithmetic and window manipulation |
| datetime | stdlib | Date comparisons |

### Test Infrastructure

| Library | Version | Purpose |
|---------|---------|---------|
| pytest | Current | Test framework |

## Architecture Patterns

### Pattern 1: Post-Merge Validation

**What:** After merging overlapping windows, validate merged span does not exceed `window_interval_days`.

**When to use:** Anytime interval merging occurs (cluster_buys.py lines 564-575).

**Example:**
```python
for start, end in intervals:
    if not merged_intervals:
        merged_intervals.append((start, end))
        continue
    last_start, last_end = merged_intervals[-1]
    if start <= last_end:  # overlap detected
        proposed_end = max(last_end, end)
        # Validate merged span doesn't exceed window_days
        if (proposed_end - last_start).days <= window_interval_days:
            merged_intervals[-1] = (last_start, proposed_end)
        else:
            # Overlapping but too wide - treat as separate window
            merged_intervals.append((start, end))
    else:
        merged_intervals.append((start, end))
```

### Pattern 2: Window Split Strategy

**What:** If merged window exceeds `window_days`, split into multiple valid windows.

**When to use:** When consolidation is required but span constraint must be honored.

**Example:**
```python
# Option A: Keep first valid window, discard overlap
if (proposed_end - last_start).days > window_interval_days:
    merged_intervals.append((start, end))  # New window

# Option B: Re-run sliding window on merged transaction set
# (More complex, but preserves "best" window behavior)
```

### Anti-Patterns to Avoid

- **Silent span violations:** Merging without validation creates invalid output
- **Post-processing filters:** Filtering out violations after scoring wastes computation
- **Window splitting without re-scoring:** Split windows must recalculate cluster metrics

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Date interval arithmetic | Custom date math | `datetime.timedelta` and `.days` | Handles edge cases (leap years, DST) |
| Interval merging validation | Custom overlap logic | Pattern 1 above with explicit `.days` check | Clear, testable, maintainable |

**Key insight:** Date arithmetic is deceptively complex. Use stdlib `datetime` and pandas `Timestamp` for all date operations.

## Common Pitfalls

### Pitfall 1: Inclusive vs Exclusive Range Confusion

**What goes wrong:** Off-by-one errors when converting between "N days" and date ranges.

**Why it happens:** window_days=10 means a 10-day range, but date subtraction gives 9 days (inclusive).

**How to avoid:**
- Use `window_interval = window_days - 1` consistently
- Validate with `(end - start).days <= window_interval`
- Test boundary cases (span = 9 days OK, span = 10 days FAIL for window_days=10)

**Warning signs:** Clusters with spans exactly equal to `window_days` (should be `window_days - 1`).

### Pitfall 2: Merging Without Re-Validation

**What goes wrong:** Merging two valid 9-day windows that overlap by 1 day can create a 17-day window.

**Why it happens:** `max(last_end, end)` extends without checking total span.

**How to avoid:**
- Validate `(proposed_end - last_start).days <= window_interval_days` before merging
- If validation fails, treat as separate window

**Warning signs:** Large span violations (20-37 days as seen in empirical data).

### Pitfall 3: Skipping Post-Merge Recalculation

**What goes wrong:** Merged window inherits `num_insiders`, `total_value` from SQL, but these may be stale after merge.

**Why it happens:** SQL computes metrics per transaction-date window; merging changes the window boundaries.

**How to avoid:** Lines 578-720 already recompute metrics from `base_df` subset - this is correct. **Do not skip this step.**

**Warning signs:** `num_insiders` or `total_value` don't match raw transaction sums.

## Code Examples

### Validated Merge with Span Constraint

```python
# Source: cluster_buys.py lines 564-575 (current) + proposed fix
window_interval = window_days - 1

for ticker_value, tdf in df.groupby("ticker"):
    intervals = sorted(zip(tdf["window_start"], tdf["window_end"]), key=lambda x: x[0])
    merged_intervals: list[tuple[date, date]] = []

    for start, end in intervals:
        if not merged_intervals:
            merged_intervals.append((start, end))
            continue

        last_start, last_end = merged_intervals[-1]

        if start <= last_end:  # overlap condition
            proposed_end = max(last_end, end)
            span_days = (proposed_end - last_start).days

            if span_days <= window_interval:
                # Valid merge - span constraint satisfied
                merged_intervals[-1] = (last_start, proposed_end)
            else:
                # Overlap detected but merged span exceeds window_days
                # Strategy: treat as separate window to honor span constraint
                merged_intervals.append((start, end))
        else:
            # No overlap
            merged_intervals.append((start, end))
```

### Test for Window Span Validation

```python
# test_cluster_buys.py
def test_merged_windows_respect_span_constraint():
    """Verify merged windows do not exceed window_days."""
    # Setup: create overlapping windows that would exceed limit if merged
    # Window 1: 2024-01-01 to 2024-01-10 (9 days, valid)
    # Window 2: 2024-01-05 to 2024-01-18 (13 days, valid standalone)
    # Merged: 2024-01-01 to 2024-01-18 (17 days, INVALID for window_days=10)

    df = find_cluster_buys(
        ticker="TEST",
        window_days=10,
        lookback_days=365,
        min_insiders=2,
        min_total_value=100_000.0,
    )

    for _, row in df.iterrows():
        span = (row["window_end"] - row["window_start"]).days
        assert span <= 9, f"Window span {span} exceeds window_days=10 (interval=9)"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Merge without validation | Merge with `max(last_end, end)` | Original implementation | Creates span violations |
| Post-process filtering | Pre-merge validation (proposed) | Phase 10 | Prevents violations at source |

**Current approach (unvalidated merge):** Functional for most cases, but fails when windows overlap significantly.

**Proposed approach (validated merge):** Honor span constraint at merge time, preventing invalid output.

## Open Questions

1. **Should oversized merged windows be split or rejected?**
   - What we know: Merging consolidates duplicate signals
   - What's unclear: If Window A (Jan 1-10) and Window B (Jan 5-20) overlap, which strategy?
     - Option A: Keep A, discard B (simple, may lose data)
     - Option B: Keep both as separate windows (honors span, but duplicates ticker)
     - Option C: Re-run sliding window on merged transaction set (complex, preserves "best" window)
   - Recommendation: Start with Option B (keep both), document as separate cluster events. Address in Phase 13 (Duplicate Ticker Handling).

2. **Are there legitimate cases where spans should exceed window_days?**
   - What we know: `window_days=10` is a strategy parameter, not a data quality rule
   - What's unclear: Should exceptional clusters (e.g., 30 insiders over 15 days) be allowed?
   - Recommendation: Enforce constraint strictly per DATA-01. Users can adjust `window_days` parameter if needed.

3. **Does the sliding window algorithm in window_detection.py need changes?**
   - What we know: `best_qualifying_window_indices()` correctly enforces `(end - start).days <= window_interval`
   - What's unclear: None - algorithm is correct
   - Recommendation: No changes needed to `window_detection.py`

## Sources

### Primary (HIGH confidence)
- `src/analytics/cluster_buys.py` lines 564-575 - Window merging logic
- `src/analytics/window_detection.py` lines 8-66 - Sliding window algorithm
- `exports/cluster_runs/my_run.json` - Empirical span violations (9 of 20 samples)
- `.planning/REQUIREMENTS.md` line 17 - DATA-01 requirement definition

### Secondary (MEDIUM confidence)
- `.planning/codebase/ARCHITECTURE.md` lines 105-107 - Window merging rationale
- `tests/test_tradeable_window_selection.py` - Existing window tests (no span validation)

## Metadata

**Confidence breakdown:**
- Root cause identification: HIGH - empirical evidence + code inspection confirms merging bug
- Proposed solution: HIGH - validated merge pattern is standard practice
- Interaction with Phase 13: MEDIUM - duplicate ticker handling may influence merge strategy

**Research date:** 2026-02-11
**Valid until:** 2026-03-13 (30 days - algorithm is stable)
