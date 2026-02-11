---
phase: 08-fund-ratio-filtering
verified: 2026-02-11T18:30:00Z
status: passed
score: 7/7 must-haves verified
re_verification: false
---

# Phase 8: Fund Ratio Filtering Verification Report

**Phase Goal:** Exclude fund-heavy clusters from scan results
**Verified:** 2026-02-11T18:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                           | Status     | Evidence                                                                 |
| --- | ------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------ |
| 1   | Clusters with fund_ratio >= 0.25 are excluded from scan_clusters.py output     | ✓ VERIFIED | Line 713: `< max_fund_ratio` (strict boundary)                           |
| 2   | Clusters with fund_ratio = 0.25 exactly are excluded (strict boundary)         | ✓ VERIFIED | Test passes: `test_exact_threshold_excluded`                             |
| 3   | Clusters with num_total_insiders = 0 are excluded (data integrity guard)       | ✓ VERIFIED | Line 712: `(denom > 0)` explicit check; test passes                      |
| 4   | fund_ratio field appears in JSON export output for every cluster               | ✓ VERIFIED | Lines 679, 1038: field in both output dicts                              |
| 5   | Fund ratio threshold defaults to 0.25 from ClusterThresholds in CLI scripts    | ✓ VERIFIED | scan_clusters.py:224, backtest:208 use CLUSTER_THRESHOLDS.max_fund_ratio |
| 6   | User can override fund ratio threshold via --max-fund-ratio CLI flag           | ✓ VERIFIED | Both scripts have --max-fund-ratio arg with config default              |
| 7   | Excluded clusters are silently dropped (no log lines)                          | ✓ VERIFIED | No logger calls found for fund_ratio filtering                           |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact                                  | Expected                                                   | Status     | Details                                                             |
| ----------------------------------------- | ---------------------------------------------------------- | ---------- | ------------------------------------------------------------------- |
| `src/analytics/cluster_buys.py`          | Strict boundary fund_ratio filtering and export field      | ✓ VERIFIED | Lines 709-714: `< max_fund_ratio`, Lines 679, 1038: fund_ratio field |
| `scripts/scan_clusters.py`               | Config-driven --max-fund-ratio default                     | ✓ VERIFIED | Line 224: `default=CLUSTER_THRESHOLDS.max_fund_ratio`               |
| `scripts/backtest_cluster_strategy.py`   | Config-driven --max-fund-ratio default                     | ✓ VERIFIED | Line 208: `default=CLUSTER_THRESHOLDS.max_fund_ratio`               |
| `tests/test_fund_ratio_filtering.py`     | Boundary enforcement tests                                 | ✓ VERIFIED | 9 tests, all passing (boundary, zero-denom, output)                |

### Key Link Verification

| From                      | To                                     | Via                               | Status     | Details                                           |
| ------------------------- | -------------------------------------- | --------------------------------- | ---------- | ------------------------------------------------- |
| scripts/scan_clusters.py  | src/scoring_config/scoring_weights.py  | CLUSTER_THRESHOLDS.max_fund_ratio | ✓ WIRED    | Import line 34, usage line 224                    |
| scripts/backtest_*.py     | src/scoring_config/scoring_weights.py  | CLUSTER_THRESHOLDS.max_fund_ratio | ✓ WIRED    | Import line 29, usage line 208                    |
| src/analytics/cluster_buys| JSON export output                     | fund_ratio field in record dict   | ✓ WIRED    | Lines 679, 1038: field included in output dicts   |

### Requirements Coverage

| Requirement | Status      | Supporting Evidence                                             |
| ----------- | ----------- | --------------------------------------------------------------- |
| FILT-01     | ✓ SATISFIED | All 7 truths verified; filtering logic correct and tested       |

### Anti-Patterns Found

**None detected.** No blocking anti-patterns found.

### Boundary Logic Correctness

**Critical verification:** The boundary operator logic is **correct and consistent** across both filtering paths:

1. **find_cluster_buys() (line 713):** Uses `< max_fund_ratio` (keep if ratio strictly less than max)
   - Interpretation: fund_ratio >= 0.25 → EXCLUDED
   - Zero-denom guard: `(denom > 0)` explicitly excludes invalid clusters

2. **find_tradeable_cluster_signals() (line 1022):** Uses `>= max_fund_ratio` (skip if ratio at or above max)
   - Interpretation: fund_ratio >= 0.25 → EXCLUDED (via continue)
   - Zero-denom guard: explicit check at line 1020

**Both paths are logically equivalent:** They enforce the same strict exclusive boundary (fund_ratio >= max means excluded).

### Test Coverage Analysis

**test_fund_ratio_filtering.py:** 9 tests, all passing

**Boundary enforcement tests:**
- ✓ Below threshold (0.20) passes
- ✓ Exact threshold (0.25) excluded — **CRITICAL TEST PASSES**
- ✓ Above threshold (0.50) excluded
- ✓ Zero fund_ratio (0.00) passes
- ✓ Zero total_insiders excluded
- ✓ None max disables filter
- ✓ Mixed clusters filtered correctly

**Output field tests:**
- ✓ fund_ratio calculation correct
- ✓ fund_ratio handles zero denominator

### Config Wiring Verification

**CLUSTER_THRESHOLDS.max_fund_ratio = 0.25** (from scoring_weights.py:120)

**CLI wiring:**
- scan_clusters.py line 224: `default=CLUSTER_THRESHOLDS.max_fund_ratio` ✓
- backtest_cluster_strategy.py line 208: `default=CLUSTER_THRESHOLDS.max_fund_ratio` ✓

**Both scripts correctly import and use config default.**

### Silent Filtering Verification

**No log statements found for fund_ratio filtering:**
- No `logger.info` calls
- No `logger.warning` calls
- No `logger.debug` calls
- No `log.info` calls about filtered clusters

**Only general cluster count logged (line 720):** `log.info("clusters_found", count=len(merged_df))` — this logs the count AFTER filtering, which is correct.

---

## Summary

**All success criteria met:**

1. ✓ Clusters with fund_ratio >= 0.25 are automatically excluded from scan_clusters.py output
   - Verified: Boundary operator logic correct in both functions
   - Verified: Test confirms fund_ratio=0.25 exactly is excluded

2. ✓ User can inspect and verify fund_ratio values in output before filtering
   - Verified: fund_ratio field present in both output dicts (lines 679, 1038)

3. ✓ Fund ratio threshold is configurable via CLI flag (with default from ClusterThresholds)
   - Verified: Both CLI scripts use CLUSTER_THRESHOLDS.max_fund_ratio as default
   - Verified: CLI flags accept user override

4. ✓ Excluded clusters are silently dropped (no filter reporting)
   - Verified: No logger calls for fund_ratio filtering
   - Verified: Only general cluster count logged

**Additional quality indicators:**
- Zero-denom clusters (num_total_insiders=0) are explicitly excluded as data integrity guard
- Comprehensive test coverage with 9 passing tests
- Boundary logic is consistent across both detection paths
- No anti-patterns or code smells detected

**Phase goal achieved.** Ready to proceed to Phase 09.

---

_Verified: 2026-02-11T18:30:00Z_
_Verifier: John @ YourDesign.co.za_
