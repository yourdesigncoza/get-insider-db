---
phase: quick
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - src/analytics/cluster_buys.py
  - tests/test_fund_ratio_filtering.py
autonomous: true
must_haves:
  truths:
    - "fund_ratio output field never exceeds 1.0, even with bad source data"
    - "fund_ratio output returns 0.0 when total_insiders is 0 (not division error)"
    - "Both find_cluster_buys() and find_tradeable_cluster_signals() use the same calc_fund_ratio helper"
    - "max_fund_ratio=0 excludes all clusters (0.0 < 0 is False)"
    - "Float precision edge case at 1/3 boundary behaves correctly"
  artifacts:
    - path: "src/analytics/cluster_buys.py"
      provides: "calc_fund_ratio helper function"
      contains: "def calc_fund_ratio"
    - path: "tests/test_fund_ratio_filtering.py"
      provides: "Edge case tests for fund ratio"
      contains: "test_max_fund_ratio_zero"
  key_links:
    - from: "src/analytics/cluster_buys.py:find_cluster_buys"
      to: "calc_fund_ratio"
      via: "function call in output record dict"
      pattern: 'calc_fund_ratio\('
    - from: "src/analytics/cluster_buys.py:find_tradeable_cluster_signals"
      to: "calc_fund_ratio"
      via: "function call in output record dict"
      pattern: 'calc_fund_ratio\('
---

<objective>
Extract inline fund_ratio computation into a shared `calc_fund_ratio()` helper with 1.0 cap, and add edge case tests.

Purpose: Eliminate zero-insider paradox between filter logic (excludes total=0) and output field (returns 0.0 for total=0), cap ratio at 1.0 for data integrity, and cover edge cases the existing test suite misses.
Output: Updated cluster_buys.py with helper, updated test file with 3 new edge case tests.
</objective>

<execution_context>
@/home/laudes/.claude/get-shit-done/workflows/execute-plan.md
@/home/laudes/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/analytics/cluster_buys.py
@tests/test_fund_ratio_filtering.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create calc_fund_ratio helper and wire into both functions</name>
  <files>src/analytics/cluster_buys.py</files>
  <action>
1. Add a module-level helper function near the top of `cluster_buys.py` (after imports, before the class/function definitions):

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

2. In `find_cluster_buys()` (~line 769), replace:
   `"fund_ratio": float(num_fund_like / max(total_unique_insiders, 1)),`
   with:
   `"fund_ratio": calc_fund_ratio(int(num_fund_like), int(total_unique_insiders)),`

3. In `find_tradeable_cluster_signals()` (~line 1162), replace:
   `"fund_ratio": float(num_fund_like / max(total_unique_insiders, 1)),`
   with:
   `"fund_ratio": calc_fund_ratio(int(num_fund_like), total_unique_insiders),`

Do NOT change the filter logic in either function (the `< max_fund_ratio` checks). Only replace the output field computation.
  </action>
  <verify>
Run `python -c "from src.analytics.cluster_buys import calc_fund_ratio; assert calc_fund_ratio(0, 0) == 0.0; assert calc_fund_ratio(5, 3) == 1.0; assert calc_fund_ratio(1, 4) == 0.25; print('OK')"` from project root.
Then run `pytest tests/test_fund_ratio_filtering.py -v` -- all 9 existing tests must pass.
  </verify>
  <done>calc_fund_ratio exists, both output record locations use it, all existing tests pass.</done>
</task>

<task type="auto">
  <name>Task 2: Add edge case tests</name>
  <files>tests/test_fund_ratio_filtering.py</files>
  <action>
1. Add an import of calc_fund_ratio at the top:
   `from src.analytics.cluster_buys import calc_fund_ratio`

2. Add a new test class `TestCalcFundRatioHelper` with direct unit tests for the helper:

```python
class TestCalcFundRatioHelper:
    """Direct unit tests for calc_fund_ratio helper."""

    def test_zero_total_returns_zero(self):
        assert calc_fund_ratio(0, 0) == 0.0

    def test_negative_total_returns_zero(self):
        assert calc_fund_ratio(3, -1) == 0.0

    def test_normal_ratio(self):
        assert calc_fund_ratio(1, 4) == 0.25

    def test_cap_at_one_when_fund_exceeds_total(self):
        """Bad data: num_fund_like > num_total_insiders should cap at 1.0."""
        assert calc_fund_ratio(5, 3) == 1.0

    def test_exact_one_not_capped(self):
        assert calc_fund_ratio(4, 4) == 1.0
```

3. Add a new test class `TestFundRatioEdgeCases` with filter-level edge cases:

```python
class TestFundRatioEdgeCases:
    """Edge cases from Gemini code review."""

    def test_max_fund_ratio_zero_excludes_all(self):
        """max_fund_ratio=0 should exclude everything: 0.0 < 0 is False."""
        df = pd.DataFrame([
            make_cluster_row(0, 5),   # ratio=0.00, but 0.0 < 0 is False
            make_cluster_row(1, 5),   # ratio=0.20
        ])
        result = apply_fund_ratio_filter(df, 0.0)
        assert len(result) == 0

    def test_float_precision_one_third_boundary(self):
        """1/3 boundary: num=1, total=3, max=1/3. Exact match -> excluded."""
        df = pd.DataFrame([make_cluster_row(1, 3)])  # ratio=0.333...
        result = apply_fund_ratio_filter(df, 1 / 3)
        # 1/3 == 1/3 in float, so NOT strictly less than -> excluded
        assert len(result) == 0

    def test_float_precision_just_below_one_third(self):
        """Ratio just below 1/3 threshold should pass."""
        df = pd.DataFrame([make_cluster_row(1, 4)])  # ratio=0.25
        result = apply_fund_ratio_filter(df, 1 / 3)
        assert len(result) == 1

    def test_fund_like_exceeds_total_in_output(self):
        """Bad data: fund_like > total should produce capped ratio of 1.0 in output."""
        assert calc_fund_ratio(5, 3) == 1.0
        # Verify it does not exceed 1.0
        assert calc_fund_ratio(100, 1) == 1.0
```

4. Update the existing `TestFundRatioInOutput` tests to use `calc_fund_ratio` instead of inline math:

```python
class TestFundRatioInOutput:
    """Verify fund_ratio field is computed correctly via helper."""

    def test_fund_ratio_calculation(self):
        assert calc_fund_ratio(2, 8) == 0.25

    def test_fund_ratio_zero_total(self):
        assert calc_fund_ratio(0, 0) == 0.0
```
  </action>
  <verify>Run `pytest tests/test_fund_ratio_filtering.py -v` -- all tests (9 original + new edge cases) must pass.</verify>
  <done>Test file contains TestCalcFundRatioHelper (5 tests), TestFundRatioEdgeCases (4 tests), updated TestFundRatioInOutput (2 tests), and original TestFundRatioBoundary (7 tests). All pass.</done>
</task>

</tasks>

<verification>
1. `pytest tests/test_fund_ratio_filtering.py -v` -- all tests pass
2. `pytest tests/ -v` -- full test suite passes (no regressions)
3. `python -c "from src.analytics.cluster_buys import calc_fund_ratio"` -- importable
4. `grep -c "num_fund_like / max(total_unique_insiders, 1)" src/analytics/cluster_buys.py` returns 0 (no inline ratio left)
5. `grep -c "calc_fund_ratio" src/analytics/cluster_buys.py` returns 3 (1 def + 2 call sites)
</verification>

<success_criteria>
- calc_fund_ratio helper exists, handles zero/negative denom, caps at 1.0
- Both output record locations in cluster_buys.py use the helper (no inline ratio math)
- Filter logic unchanged (still uses < operator and inline division)
- 18 total tests in test_fund_ratio_filtering.py, all passing
- Full test suite passes with no regressions
</success_criteria>

<output>
After completion, create `.planning/quick/1-fund-ratio-helper-output-cap-and-edge-ca/1-SUMMARY.md`
</output>
