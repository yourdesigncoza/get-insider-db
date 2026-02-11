---
phase: 10-window-span-validation
verified: 2026-02-11T19:30:00Z
status: human_needed
score: 3/4 must-haves verified
re_verification: false
human_verification:
  - test: "Run scan_clusters.py with latest code and verify window spans"
    expected: "All output rows have (window_end - window_start).days <= 9 for window_days=10"
    why_human: "No scan output exists after fix was deployed (19:09); all existing scans use old code"
  - test: "Verify merged windows with overlapping activity"
    expected: "Overlapping windows exceeding span are kept as separate cluster events in output"
    why_human: "Need real data to verify behavior with actual overlapping cluster windows"
---

# Phase 10: Window Span Validation Verification Report

**Phase Goal:** Investigate and correct window merging behavior that creates spans exceeding window_days
**Verified:** 2026-02-11T19:30:00Z
**Status:** human_needed
**Re-verification:** No - initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                     | Status     | Evidence                                                                   |
| --- | ------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------- |
| 1   | Merged windows never exceed window_days span (window_end - start <= 9)   | ✓ VERIFIED | Code review: line 574 validates span before merge; 11 tests pass           |
| 2   | Overlapping windows exceeding span kept as separate cluster events       | ✓ VERIFIED | Code review: line 579 appends to merged_intervals; test case validates     |
| 3   | Post-merge metric recomputation works correctly for non-merged windows   | ✓ VERIFIED | Code unchanged (lines 584-720); existing tests pass                        |
| 4   | All cluster windows in scan output have span <= window_days              | ? UNCERTAIN | No scan output exists after fix deployment; requires human verification    |

**Score:** 3/4 truths verified (4th requires human verification with fresh scan)

### Required Artifacts

| Artifact                                  | Expected                                  | Status     | Details                                                          |
| ----------------------------------------- | ----------------------------------------- | ---------- | ---------------------------------------------------------------- |
| `src/analytics/cluster_buys.py`          | Span-validated window merging logic       | ✓ VERIFIED | Lines 572-581: proposed_end validation, span check in place      |
| `tests/test_window_span_validation.py`   | Regression tests for window span          | ✓ VERIFIED | 144 lines, 11 tests, all pass, covers boundary cases             |

### Key Link Verification

| From                          | To                       | Via                      | Status     | Details                                                    |
| ----------------------------- | ------------------------ | ------------------------ | ---------- | ---------------------------------------------------------- |
| cluster_buys.py merge loop    | window_interval variable | span validation (line 574)| ✓ WIRED    | window_interval defined at line 272, used in condition     |
| merge logic                   | test suite               | replicated algorithm     | ✓ WIRED    | Test helper mirrors exact production logic                 |
| cluster_buys.py               | window span constraint   | inequality check         | ✓ WIRED    | `(proposed_end - last_start).days <= window_interval`      |

### Requirements Coverage

| Requirement | Status        | Details                                                              |
| ----------- | ------------- | -------------------------------------------------------------------- |
| DATA-01     | ✓ IMPLEMENTED | Window span validation added; needs human verification with scan     |

### Anti-Patterns Found

**None** - Code review clean:
- No TODO/FIXME/placeholder comments in merge logic
- No empty handlers or stub patterns
- Variable scope correct (window_interval accessible at line 574)
- Date arithmetic uses stdlib `datetime` (not hand-rolled)

### Human Verification Required

#### 1. Fresh Scan with Updated Code

**Test:** Run `python scripts/scan_clusters.py --limit 50 --print` after fix deployment and verify output
**Expected:**
- All rows have `(window_end - window_start).days <= 9` for default `window_days=10`
- No violations like the 23/50 seen in pre-fix scan (clusters_wd10_lb120_minins2_minrole0_minval0_mintrade0_limit50_20260211T073716.json)
- Overlapping windows with span violations appear as separate rows with same ticker

**Why human:** No scan output exists after fix was committed at 2026-02-11 19:09:46. All existing scans (last at 16:21) use old code. Need fresh scan to validate fix works in production.

**How to verify:**
```bash
# Run fresh scan
python scripts/scan_clusters.py --limit 50 --print > /tmp/scan_output.txt

# Validate spans programmatically
python3 -c "
import json
from datetime import datetime

with open('exports/cluster_runs/<latest>.json') as f:
    data = json.load(f)

violations = []
for row in data['rows']:
    start = datetime.fromisoformat(row['window_start']).date()
    end = datetime.fromisoformat(row['window_end']).date()
    span = (end - start).days
    if span > 9:
        violations.append((row['ticker'], span))

if violations:
    print(f'FAILED: {len(violations)} span violations found')
    for ticker, span in violations[:5]:
        print(f'  {ticker}: {span} days')
else:
    print('PASSED: All windows respect span constraint')
"
```

#### 2. Overlapping Window Behavior

**Test:** Identify tickers with multiple cluster windows in same scan and verify they're handled correctly
**Expected:**
- If windows overlap but merged span would exceed 9 days, both appear as separate rows
- Each row has valid span <= 9 days
- Ticker deduplication (choosing which signal to trade) deferred to Phase 13

**Why human:** Need real cluster data with overlapping activity to verify separation logic works correctly. Test suite validates algorithm but not production data flow.

### Gaps Summary

**No gaps** - All automated verification passed. Implementation is correct per code review and test suite.

**Awaiting human verification:**
1. Fresh scan output with updated code to validate production behavior
2. Overlapping window separation in real data

---

## Technical Verification Details

### Code Review

**Span validation added at lines 572-581:**
```python
if start <= last_end:  # overlap detected
    proposed_end = max(last_end, end)
    if (proposed_end - last_start).days <= window_interval:
        merged_intervals[-1] = (last_start, proposed_end)
    else:
        # Overlap exists but merged span would exceed window_days;
        # keep as separate cluster event to honor span constraint.
        merged_intervals.append((start, end))
```

**Key design decisions validated:**
- Uses `window_interval` (defined as `window_days - 1` at line 272)
- Checks span BEFORE merging (prevents violation at source)
- Keeps overlapping windows separate when constraint violated (preserves signals for Phase 13)
- No changes to post-merge metric recomputation (lines 584-720 already handle separate intervals)

### Test Coverage

**11 regression tests in test_window_span_validation.py:**

1. `test_non_overlapping_windows_kept_separate` - Basic non-overlap case
2. `test_overlapping_windows_merged_when_within_span` - Valid merge (7 days <= 9)
3. `test_overlapping_windows_kept_separate_when_exceeding_span` - **Critical:** Validates fix (17 days > 9 → separate)
4. `test_boundary_merge_at_exact_window_interval` - Boundary: 9 days == 9 → merge
5. `test_boundary_reject_at_one_over_window_interval` - Boundary: 10 days > 9 → separate
6. `test_three_windows_partial_merge` - Chain: AB merge (7 days), C separate (19 days)
7. `test_all_spans_valid_after_merge` - **Invariant check:** All output spans <= window_interval
8. `test_single_window_passes_through` - Edge: single window unchanged
9. `test_empty_input` - Edge: empty list returns empty
10. `test_identical_windows_merge` - Edge: duplicate windows merge to one
11. `test_adjacent_windows_no_overlap` - Edge: adjacent (day 10 → day 11) stay separate

**Test helper mirrors production:**
- `merge_intervals_with_span_check()` replicates exact algorithm from cluster_buys.py
- Same variable names (`proposed_end`, `window_interval`)
- Same logic flow (if-else structure identical)
- Validates contract: "merged span <= window_interval"

**All tests pass:**
```bash
$ pytest tests/test_window_span_validation.py -v
11 passed in 0.02s
```

**Existing tests unaffected:**
```bash
$ pytest tests/test_tradeable_window_selection.py tests/test_cluster_scoring.py -v
4 passed in 0.33s
```

### Root Cause Validation

**Research findings confirmed:**
- Bug location: cluster_buys.py lines 564-575 (merge loop)
- Root cause: `max(last_end, end)` extended without span validation
- Empirical impact: 23/50 violations in pre-fix scan (spans 10-53 days vs limit of 9)
- Fix approach: Add span check before merge (Option B from research: keep both when violated)

**Design tradeoff documented:**
- Merged windows prevent duplicate signals (good)
- Unvalidated merging created invalid spans (bad)
- Span validation preserves both benefits (fix)
- Ticker deduplication deferred to Phase 13 (explicit decision in PLAN.md line 82)

### Anti-Pattern Scan

**Files checked:** src/analytics/cluster_buys.py (lines 220-720)

**Patterns searched:**
- TODO/FIXME/XXX/HACK/placeholder - **None found** in merge logic
- Empty implementations (return null/empty) - **None**
- Console.log-only handlers - **Not applicable** (Python)
- Broad except clauses - **None** in modified code

**Variable scope validation:**
- `window_interval` defined at function level (line 272)
- Used in merge loop (line 574) - **In scope ✓**
- No nested function boundaries between definition and use

### Empirical Evidence

**Pre-fix scan analysis:**
File: `exports/cluster_runs/clusters_wd10_lb120_minins2_minrole0_minval0_mintrade0_limit50_20260211T073716.json`
Timestamp: 2026-02-11 09:37 (before fix at 19:09)

```
Window days config: 10
Max expected span: 9 days
Total rows: 50
Valid spans: 27
Violations: 23

Sample violations:
  FFAI: 2025-08-16 to 2025-09-02 = 17 days
  AVBC: 2025-07-27 to 2025-09-18 = 53 days
  AMRZ: 2025-07-30 to 2025-08-27 = 28 days
```

**Post-fix validation pending:** No scan output exists after fix deployment. Human verification required.

---

_Verified: 2026-02-11T19:30:00Z_
_Verifier: Claude (gsd-verifier)_
