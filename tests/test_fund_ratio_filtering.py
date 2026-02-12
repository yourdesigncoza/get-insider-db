import pytest
import pandas as pd
from src.analytics.cluster_buys import calc_fund_ratio


def apply_fund_ratio_filter(df: pd.DataFrame, max_fund_ratio: float | None) -> pd.DataFrame:
    """Replicate the fund_ratio filter logic from find_cluster_buys()."""
    if max_fund_ratio is not None:
        denom = df["num_total_insiders"]
        df = df[
            (denom > 0) &
            ((df["num_fund_like"] / denom) < max_fund_ratio)
        ]
    return df


def make_cluster_row(num_fund_like: int, num_total_insiders: int) -> dict:
    """Helper to create minimal cluster row for filtering tests."""
    return {
        "num_fund_like": num_fund_like,
        "num_total_insiders": num_total_insiders,
    }


class TestFundRatioBoundary:
    """Test strict boundary: fund_ratio >= max_fund_ratio means excluded."""

    def test_below_threshold_passes(self):
        df = pd.DataFrame([make_cluster_row(1, 5)])  # ratio=0.20
        result = apply_fund_ratio_filter(df, 0.25)
        assert len(result) == 1

    def test_exact_threshold_excluded(self):
        """Critical: fund_ratio=0.25 with max=0.25 must be EXCLUDED."""
        df = pd.DataFrame([make_cluster_row(1, 4)])  # ratio=0.25
        result = apply_fund_ratio_filter(df, 0.25)
        assert len(result) == 0

    def test_above_threshold_excluded(self):
        df = pd.DataFrame([make_cluster_row(2, 4)])  # ratio=0.50
        result = apply_fund_ratio_filter(df, 0.25)
        assert len(result) == 0

    def test_zero_fund_ratio_passes(self):
        df = pd.DataFrame([make_cluster_row(0, 5)])  # ratio=0.00
        result = apply_fund_ratio_filter(df, 0.25)
        assert len(result) == 1

    def test_zero_total_insiders_excluded(self):
        """Data integrity: clusters with 0 total insiders are excluded."""
        df = pd.DataFrame([make_cluster_row(0, 0)])
        result = apply_fund_ratio_filter(df, 0.25)
        assert len(result) == 0

    def test_none_max_disables_filter(self):
        """When max_fund_ratio is None, no filtering occurs."""
        df = pd.DataFrame([make_cluster_row(5, 5)])  # ratio=1.0
        result = apply_fund_ratio_filter(df, None)
        assert len(result) == 1

    def test_mixed_clusters_filtered_correctly(self):
        df = pd.DataFrame([
            make_cluster_row(0, 5),   # 0.00 → pass
            make_cluster_row(1, 5),   # 0.20 → pass
            make_cluster_row(1, 4),   # 0.25 → excluded
            make_cluster_row(3, 4),   # 0.75 → excluded
            make_cluster_row(0, 0),   # zero denom → excluded
        ])
        result = apply_fund_ratio_filter(df, 0.25)
        assert len(result) == 2


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


class TestFundRatioInOutput:
    """Verify fund_ratio field is computed correctly via helper."""

    def test_fund_ratio_calculation(self):
        assert calc_fund_ratio(2, 8) == 0.25

    def test_fund_ratio_zero_total(self):
        assert calc_fund_ratio(0, 0) == 0.0
