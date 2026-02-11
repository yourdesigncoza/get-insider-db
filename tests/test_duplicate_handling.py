"""
Tests for duplicate ticker handling utilities.
"""

import pandas as pd
import pytest
from datetime import date

from src.analytics.duplicate_handling import deduplicate_by_highest_score, annotate_duplicates


def _make_df(rows):
    """Helper to create test DataFrames with required columns."""
    return pd.DataFrame(
        rows,
        columns=["ticker", "cluster_score", "total_value", "window_start", "window_end"],
    )


def test_deduplicate_keeps_highest_score():
    """Deduplicate keeps only the highest-scoring cluster per ticker."""
    df = _make_df([
        ("AAPL", 90.0, 1000000.0, date(2024, 1, 1), date(2024, 1, 10)),
        ("AAPL", 80.0, 900000.0, date(2024, 1, 5), date(2024, 1, 15)),
        ("AAPL", 70.0, 800000.0, date(2024, 1, 10), date(2024, 1, 20)),
        ("MSFT", 85.0, 950000.0, date(2024, 1, 1), date(2024, 1, 10)),
        ("GOOG", 95.0, 1100000.0, date(2024, 1, 1), date(2024, 1, 10)),
    ])

    result = deduplicate_by_highest_score(df)

    # Should have 3 rows (one per ticker)
    assert len(result) == 3

    # AAPL should have only the 90.0 score row
    aapl_rows = result[result["ticker"] == "AAPL"]
    assert len(aapl_rows) == 1
    assert aapl_rows.iloc[0]["cluster_score"] == 90.0

    # Other tickers should be unchanged
    assert len(result[result["ticker"] == "MSFT"]) == 1
    assert len(result[result["ticker"] == "GOOG"]) == 1


def test_deduplicate_tiebreaker_total_value():
    """When cluster_score is identical, tiebreaker uses total_value."""
    df = _make_df([
        ("AAPL", 85.0, 1000000.0, date(2024, 1, 1), date(2024, 1, 10)),
        ("AAPL", 85.0, 900000.0, date(2024, 1, 5), date(2024, 1, 15)),
    ])

    result = deduplicate_by_highest_score(df)

    assert len(result) == 1
    assert result.iloc[0]["total_value"] == 1000000.0


def test_deduplicate_tiebreaker_window_end():
    """When cluster_score and total_value are identical, tiebreaker uses window_end."""
    df = _make_df([
        ("AAPL", 85.0, 1000000.0, date(2024, 1, 1), date(2024, 1, 15)),
        ("AAPL", 85.0, 1000000.0, date(2024, 1, 5), date(2024, 1, 10)),
    ])

    result = deduplicate_by_highest_score(df)

    assert len(result) == 1
    assert result.iloc[0]["window_end"] == date(2024, 1, 15)


def test_deduplicate_preserves_output_sort_order():
    """After dedup, result is sorted by cluster_score desc (not by ticker)."""
    df = _make_df([
        ("AAPL", 90.0, 1000000.0, date(2024, 1, 1), date(2024, 1, 10)),
        ("MSFT", 85.0, 950000.0, date(2024, 1, 1), date(2024, 1, 10)),
        ("GOOG", 95.0, 1100000.0, date(2024, 1, 1), date(2024, 1, 10)),
        ("AAPL", 80.0, 900000.0, date(2024, 1, 5), date(2024, 1, 15)),
    ])

    result = deduplicate_by_highest_score(df)

    # Result should be sorted by cluster_score desc
    assert len(result) == 3
    assert result.iloc[0]["ticker"] == "GOOG"  # 95.0
    assert result.iloc[1]["ticker"] == "AAPL"  # 90.0
    assert result.iloc[2]["ticker"] == "MSFT"  # 85.0


def test_deduplicate_empty_dataframe():
    """Empty DataFrame returns empty DataFrame without error."""
    df = pd.DataFrame(columns=["ticker", "cluster_score", "total_value", "window_start", "window_end"])

    result = deduplicate_by_highest_score(df)

    assert result.empty
    assert list(result.columns) == ["ticker", "cluster_score", "total_value", "window_start", "window_end"]


def test_annotate_duplicates_adds_columns():
    """Annotate adds duplicate_count and duplicate_rank columns."""
    df = _make_df([
        ("AAPL", 90.0, 1000000.0, date(2024, 1, 1), date(2024, 1, 10)),
        ("AAPL", 80.0, 900000.0, date(2024, 1, 5), date(2024, 1, 15)),
        ("AAPL", 70.0, 800000.0, date(2024, 1, 10), date(2024, 1, 20)),
        ("MSFT", 85.0, 950000.0, date(2024, 1, 1), date(2024, 1, 10)),
    ])

    result = annotate_duplicates(df)

    # Should have new columns
    assert "duplicate_count" in result.columns
    assert "duplicate_rank" in result.columns

    # AAPL appears 3 times, all rows should have duplicate_count=3
    aapl_rows = result[result["ticker"] == "AAPL"]
    assert all(aapl_rows["duplicate_count"] == 3)

    # AAPL ranks should be 1, 2, 3 by descending cluster_score
    assert aapl_rows[aapl_rows["cluster_score"] == 90.0]["duplicate_rank"].iloc[0] == 1
    assert aapl_rows[aapl_rows["cluster_score"] == 80.0]["duplicate_rank"].iloc[0] == 2
    assert aapl_rows[aapl_rows["cluster_score"] == 70.0]["duplicate_rank"].iloc[0] == 3

    # MSFT appears once, should have duplicate_count=1, duplicate_rank=1
    msft_row = result[result["ticker"] == "MSFT"].iloc[0]
    assert msft_row["duplicate_count"] == 1
    assert msft_row["duplicate_rank"] == 1


def test_annotate_duplicates_unique_tickers():
    """Tickers appearing once have duplicate_count=1, duplicate_rank=1."""
    df = _make_df([
        ("AAPL", 90.0, 1000000.0, date(2024, 1, 1), date(2024, 1, 10)),
        ("MSFT", 85.0, 950000.0, date(2024, 1, 1), date(2024, 1, 10)),
        ("GOOG", 95.0, 1100000.0, date(2024, 1, 1), date(2024, 1, 10)),
    ])

    result = annotate_duplicates(df)

    # All tickers should have duplicate_count=1 and duplicate_rank=1
    assert all(result["duplicate_count"] == 1)
    assert all(result["duplicate_rank"] == 1)


def test_annotate_duplicates_empty_dataframe():
    """Empty DataFrame returns empty DataFrame without error."""
    df = pd.DataFrame(columns=["ticker", "cluster_score", "total_value", "window_start", "window_end"])

    result = annotate_duplicates(df)

    assert result.empty
    assert list(result.columns) == ["ticker", "cluster_score", "total_value", "window_start", "window_end"]


def test_annotate_does_not_mutate_input():
    """Original DataFrame is unchanged after annotate call."""
    df = _make_df([
        ("AAPL", 90.0, 1000000.0, date(2024, 1, 1), date(2024, 1, 10)),
        ("AAPL", 80.0, 900000.0, date(2024, 1, 5), date(2024, 1, 15)),
    ])

    original_columns = list(df.columns)
    original_len = len(df)

    result = annotate_duplicates(df)

    # Original DataFrame should be unchanged
    assert list(df.columns) == original_columns
    assert len(df) == original_len
    assert "duplicate_count" not in df.columns
    assert "duplicate_rank" not in df.columns

    # Result should have new columns
    assert "duplicate_count" in result.columns
    assert "duplicate_rank" in result.columns


def test_deduplicate_single_row_per_ticker():
    """When all tickers are unique, output should match input (minus sort order)."""
    df = _make_df([
        ("GOOG", 95.0, 1100000.0, date(2024, 1, 1), date(2024, 1, 10)),
        ("AAPL", 90.0, 1000000.0, date(2024, 1, 1), date(2024, 1, 10)),
        ("MSFT", 85.0, 950000.0, date(2024, 1, 1), date(2024, 1, 10)),
    ])

    result = deduplicate_by_highest_score(df)

    # All rows should be present
    assert len(result) == 3
    assert set(result["ticker"]) == {"AAPL", "MSFT", "GOOG"}

    # Should be sorted by cluster_score desc
    assert result.iloc[0]["ticker"] == "GOOG"
    assert result.iloc[1]["ticker"] == "AAPL"
    assert result.iloc[2]["ticker"] == "MSFT"
