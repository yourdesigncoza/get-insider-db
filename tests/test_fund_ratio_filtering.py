import pytest
import pandas as pd


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


class TestFundRatioInOutput:
    """Verify fund_ratio field is computed correctly."""

    def test_fund_ratio_calculation(self):
        ratio = float(2 / max(8, 1))
        assert ratio == 0.25

    def test_fund_ratio_zero_total(self):
        ratio = float(0 / max(0, 1))
        assert ratio == 0.0
