"""
Unit tests for float rounding behavior in cluster export.

Validates that all 5 floating-point fields are rounded to 2 decimals
in the export copy (out_df) while preserving integer magnitude fields
and handling edge cases like NaN values and missing columns.
"""

import pytest
import pandas as pd
import numpy as np
from scripts.scan_clusters import FLOAT_FIELDS_TO_ROUND


def test_all_float_fields_rounded():
    """
    Test that all 5 float fields are rounded to 2 decimal places.

    Create a DataFrame with float fields containing many decimals,
    apply rounding logic, verify precision is 2 decimals.
    """
    # Create test data with high-precision floats
    df = pd.DataFrame({
        "ticker": ["AAPL"],
        "cluster_score": [72.456789123],
        "avg_percent_change": [3.14159265359],
        "avg_days_to_file": [0.8333333333333334],
        "fund_ratio": [0.16666666666666666],
        "avg_sale_to_purchase_ratio": [0.14285714285714285],
        "total_shares": [1000],
        "total_value": [50000],
    })

    # Apply rounding (same logic as scan_clusters.py)
    for col in FLOAT_FIELDS_TO_ROUND:
        if col in df.columns:
            df[col] = df[col].round(2)

    # Verify all float fields are rounded to exactly 2 decimals
    assert df["cluster_score"].iloc[0] == 72.46, "cluster_score not rounded correctly"
    assert df["avg_percent_change"].iloc[0] == 3.14, "avg_percent_change not rounded correctly"
    assert df["avg_days_to_file"].iloc[0] == 0.83, "avg_days_to_file not rounded correctly"
    assert df["fund_ratio"].iloc[0] == 0.17, "fund_ratio not rounded correctly"
    assert df["avg_sale_to_purchase_ratio"].iloc[0] == 0.14, "avg_sale_to_purchase_ratio not rounded correctly"

    # Verify precision: check that values have at most 2 decimal places
    for col in FLOAT_FIELDS_TO_ROUND:
        if col in df.columns:
            value = df[col].iloc[0]
            # Convert to string and check decimal places
            str_value = f"{value:.10f}".rstrip('0').rstrip('.')
            if '.' in str_value:
                decimal_places = len(str_value.split('.')[1])
                assert decimal_places <= 2, f"{col} has more than 2 decimal places: {str_value}"


def test_magnitude_fields_not_rounded():
    """
    Test that integer magnitude fields (total_shares, total_value) are NOT rounded.

    These fields use .0f formatters and should not be in FLOAT_FIELDS_TO_ROUND.
    """
    # Verify magnitude fields are excluded from rounding list
    assert "total_shares" not in FLOAT_FIELDS_TO_ROUND, "total_shares should not be rounded"
    assert "total_value" not in FLOAT_FIELDS_TO_ROUND, "total_value should not be rounded"

    # Verify FLOAT_FIELDS_TO_ROUND contains exactly the expected 5 fields
    expected_fields = {
        "cluster_score",
        "avg_percent_change",
        "avg_days_to_file",
        "fund_ratio",
        "avg_sale_to_purchase_ratio",
    }
    assert set(FLOAT_FIELDS_TO_ROUND) == expected_fields, "Unexpected fields in FLOAT_FIELDS_TO_ROUND"


def test_rounding_preserves_nan():
    """
    Test that NaN values remain NaN after rounding (not converted to 0 or causing errors).
    """
    # Create DataFrame with NaN values in float fields
    df = pd.DataFrame({
        "ticker": ["AAPL", "GOOGL"],
        "cluster_score": [72.456789, np.nan],
        "avg_percent_change": [np.nan, 3.141592],
        "avg_days_to_file": [0.833333, np.nan],
        "fund_ratio": [np.nan, 0.166666],
        "avg_sale_to_purchase_ratio": [0.142857, np.nan],
    })

    # Apply rounding
    for col in FLOAT_FIELDS_TO_ROUND:
        if col in df.columns:
            df[col] = df[col].round(2)

    # Verify NaN values are preserved
    assert pd.isna(df["cluster_score"].iloc[1]), "NaN in cluster_score should be preserved"
    assert pd.isna(df["avg_percent_change"].iloc[0]), "NaN in avg_percent_change should be preserved"
    assert pd.isna(df["avg_days_to_file"].iloc[1]), "NaN in avg_days_to_file should be preserved"
    assert pd.isna(df["fund_ratio"].iloc[0]), "NaN in fund_ratio should be preserved"
    assert pd.isna(df["avg_sale_to_purchase_ratio"].iloc[1]), "NaN in avg_sale_to_purchase_ratio should be preserved"

    # Verify non-NaN values are still rounded correctly
    assert df["cluster_score"].iloc[0] == 72.46, "Non-NaN cluster_score should be rounded"
    assert df["avg_percent_change"].iloc[1] == 3.14, "Non-NaN avg_percent_change should be rounded"


def test_rounding_does_not_mutate_original():
    """
    Test that rounding a copy doesn't mutate the original DataFrame.

    This validates the out_df = df.copy() pattern in scan_clusters.py.
    """
    # Create original DataFrame
    original_df = pd.DataFrame({
        "ticker": ["AAPL"],
        "cluster_score": [72.456789123],
        "avg_percent_change": [3.14159265359],
    })

    # Store original values
    original_cluster_score = original_df["cluster_score"].iloc[0]
    original_avg_percent_change = original_df["avg_percent_change"].iloc[0]

    # Make a copy and apply rounding
    out_df = original_df.copy()
    for col in FLOAT_FIELDS_TO_ROUND:
        if col in out_df.columns:
            out_df[col] = out_df[col].round(2)

    # Verify original DataFrame is unchanged
    assert original_df["cluster_score"].iloc[0] == original_cluster_score, "Original cluster_score was mutated"
    assert original_df["avg_percent_change"].iloc[0] == original_avg_percent_change, "Original avg_percent_change was mutated"

    # Verify copy is rounded
    assert out_df["cluster_score"].iloc[0] == 72.46, "Copy cluster_score should be rounded"
    assert out_df["avg_percent_change"].iloc[0] == 3.14, "Copy avg_percent_change should be rounded"


def test_missing_columns_handled():
    """
    Test that missing columns are handled gracefully with 'if col in df.columns' guard.

    Some DataFrames may not have all float fields (e.g., early in pipeline).
    """
    # Create DataFrame with only some float fields
    df = pd.DataFrame({
        "ticker": ["AAPL"],
        "cluster_score": [72.456789123],
        # Missing: avg_percent_change, avg_days_to_file, fund_ratio, avg_sale_to_purchase_ratio
    })

    # Apply rounding loop (should not raise KeyError)
    try:
        for col in FLOAT_FIELDS_TO_ROUND:
            if col in df.columns:
                df[col] = df[col].round(2)
    except KeyError as e:
        pytest.fail(f"Rounding raised KeyError for missing column: {e}")

    # Verify existing column was rounded
    assert df["cluster_score"].iloc[0] == 72.46, "Existing column should be rounded"

    # Verify missing columns don't exist (and didn't cause errors)
    assert "avg_percent_change" not in df.columns, "Missing column should remain missing"
    assert "fund_ratio" not in df.columns, "Missing column should remain missing"
