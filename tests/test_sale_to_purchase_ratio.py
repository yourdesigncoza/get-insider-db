"""
Tests for sale-to-purchase ratio data availability fix.

Validates that:
1. Ratio is non-zero when insiders have both P and S transactions
2. Ratio is zero when only purchases exist
3. Ratio respects lookback window
4. Ratio calculation is temporally safe (no look-ahead bias)
5. Graceful fallback when insider_trade_signals view doesn't exist
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.analytics.cluster_buys import _load_trades_for_ratio
from src.analytics.feature_engineering import calculate_sale_to_purchase_ratio


def test_ratio_nonzero_with_mixed_transactions():
    """
    Test that sale-to-purchase ratio is non-zero when an insider has both
    sales and purchases in the lookback period.
    """
    data = {
        "ticker": ["AAPL"] * 4,
        "normalized_name": ["john_doe"] * 4,
        "transaction_date": pd.to_datetime([
            "2025-01-01",
            "2025-01-05",  # Purchase
            "2025-01-10",  # Sale
            "2025-01-15",  # Purchase
        ]),
        "transaction_code": ["P", "P", "S", "P"],
        "shares": [100.0, 200.0, 150.0, 100.0],
        "filing_date": pd.to_datetime([
            "2025-01-02",
            "2025-01-06",
            "2025-01-11",
            "2025-01-16",
        ]),
    }
    df = pd.DataFrame(data)

    result = calculate_sale_to_purchase_ratio(df, lookback_days=90)

    # After the sale on 2025-01-10, ratio should be non-zero
    # At that point: purchases = 300, sales = 150, ratio = 150/300 = 0.5
    last_ratio = result.loc[result["transaction_date"] == "2025-01-10", "sale_to_purchase_ratio"].values[0]
    assert last_ratio > 0, "Ratio should be non-zero when both P and S transactions exist"
    assert last_ratio == 0.5, f"Expected ratio 0.5, got {last_ratio}"


def test_ratio_zero_with_purchases_only():
    """
    Test that sale-to-purchase ratio is zero when insider only has purchases
    (no sales in lookback period).
    """
    data = {
        "ticker": ["AAPL"] * 3,
        "normalized_name": ["john_doe"] * 3,
        "transaction_date": pd.to_datetime([
            "2025-01-01",
            "2025-01-05",
            "2025-01-10",
        ]),
        "transaction_code": ["P", "P", "P"],
        "shares": [100.0, 200.0, 150.0],
        "filing_date": pd.to_datetime([
            "2025-01-02",
            "2025-01-06",
            "2025-01-11",
        ]),
    }
    df = pd.DataFrame(data)

    result = calculate_sale_to_purchase_ratio(df, lookback_days=90)

    # All ratios should be zero (no sales)
    assert (result["sale_to_purchase_ratio"] == 0.0).all(), "Ratio should be zero with purchases only"


def test_ratio_zero_with_no_sales_in_lookback():
    """
    Test that ratio is zero when sales exist but are outside the lookback window.
    """
    data = {
        "ticker": ["AAPL"] * 4,
        "normalized_name": ["john_doe"] * 4,
        "transaction_date": pd.to_datetime([
            "2024-01-01",  # Sale (old, outside lookback)
            "2025-01-01",  # Purchase
            "2025-01-05",  # Purchase
            "2025-01-10",  # Purchase
        ]),
        "transaction_code": ["S", "P", "P", "P"],
        "shares": [500.0, 100.0, 200.0, 150.0],
        "filing_date": pd.to_datetime([
            "2024-01-02",
            "2025-01-02",
            "2025-01-06",
            "2025-01-11",
        ]),
    }
    df = pd.DataFrame(data)

    result = calculate_sale_to_purchase_ratio(df, lookback_days=30)

    # For transactions in Jan 2025, the old sale from 2024-01-01 should not be in lookback
    recent_ratios = result.loc[result["transaction_date"] >= "2025-01-01", "sale_to_purchase_ratio"]
    assert (recent_ratios == 0.0).all(), "Ratio should be zero when sales are outside lookback window"


def test_ratio_correctness_simple_case():
    """
    Test ratio calculation correctness with a simple known case.
    """
    data = {
        "ticker": ["AAPL"] * 3,
        "normalized_name": ["john_doe"] * 3,
        "transaction_date": pd.to_datetime([
            "2025-01-01",  # Purchase 100 shares
            "2025-01-05",  # Purchase 100 shares (total: 200 P)
            "2025-01-10",  # Sale 100 shares (total: 200 P, 100 S, ratio=100/200=0.5)
        ]),
        "transaction_code": ["P", "P", "S"],
        "shares": [100.0, 100.0, 100.0],
        "filing_date": pd.to_datetime([
            "2025-01-02",
            "2025-01-06",
            "2025-01-11",
        ]),
    }
    df = pd.DataFrame(data)

    result = calculate_sale_to_purchase_ratio(df, lookback_days=90)

    # Check ratios at each point
    ratios = result.set_index("transaction_date")["sale_to_purchase_ratio"].to_dict()

    assert ratios[pd.Timestamp("2025-01-01")] == 0.0, "First purchase: no sales yet, ratio=0"
    assert ratios[pd.Timestamp("2025-01-05")] == 0.0, "Second purchase: no sales yet, ratio=0"
    assert ratios[pd.Timestamp("2025-01-10")] == 0.5, "After sale: 100 sold / 200 purchased = 0.5"


def test_ratio_temporal_safety():
    """
    Test that ratio calculation doesn't use future data (temporal safety).
    Each transaction's ratio should only reflect data up to that transaction date.
    """
    data = {
        "ticker": ["AAPL"] * 4,
        "normalized_name": ["john_doe"] * 4,
        "transaction_date": pd.to_datetime([
            "2025-01-01",  # Purchase
            "2025-01-05",  # Purchase
            "2025-01-10",  # Sale (shouldn't affect earlier ratios)
            "2025-01-15",  # Purchase
        ]),
        "transaction_code": ["P", "P", "S", "P"],
        "shares": [100.0, 100.0, 50.0, 100.0],
        "filing_date": pd.to_datetime([
            "2025-01-02",
            "2025-01-06",
            "2025-01-11",
            "2025-01-16",
        ]),
    }
    df = pd.DataFrame(data)

    result = calculate_sale_to_purchase_ratio(df, lookback_days=90)
    ratios = result.set_index("transaction_date")["sale_to_purchase_ratio"].to_dict()

    # Transactions before the sale should have ratio=0 (no sales known yet)
    assert ratios[pd.Timestamp("2025-01-01")] == 0.0, "No look-ahead: first purchase ratio=0"
    assert ratios[pd.Timestamp("2025-01-05")] == 0.0, "No look-ahead: second purchase ratio=0"

    # After sale, ratio should reflect the sale
    assert ratios[pd.Timestamp("2025-01-10")] == 0.25, "After sale: 50 sold / 200 purchased = 0.25"

    # Final purchase should still have the sale in lookback
    assert ratios[pd.Timestamp("2025-01-15")] > 0, "Final purchase should include previous sale in ratio"


def test_load_trades_for_ratio_graceful_fallback():
    """
    Test that _load_trades_for_ratio returns empty DataFrame when
    insider_trade_signals view doesn't exist (graceful fallback).
    """
    mock_engine = MagicMock()

    # Simulate view not existing (inspect raises SQLAlchemyError)
    with patch("src.analytics.cluster_buys.inspect") as mock_inspect:
        mock_inspect.return_value.get_columns.side_effect = SQLAlchemyError("View does not exist")

        result = _load_trades_for_ratio(
            mock_engine,
            ["AAPL"],
            date(2025, 1, 1),
            date(2025, 12, 31),
        )

        assert result.empty, "Should return empty DataFrame when view doesn't exist"


def test_load_trades_for_ratio_returns_both_codes():
    """
    Test that _load_trades_for_ratio returns both P and S transaction codes
    when the view exists and has data.
    """
    mock_engine = MagicMock()

    # Mock data with both P and S codes
    mock_data = pd.DataFrame({
        "ticker": ["AAPL", "AAPL", "AAPL"],
        "transaction_date": pd.to_datetime(["2025-01-01", "2025-01-05", "2025-01-10"]),
        "filing_date": pd.to_datetime(["2025-01-02", "2025-01-06", "2025-01-11"]),
        "insider_name": ["John Doe", "John Doe", "John Doe"],
        "transaction_code": ["P", "S", "P"],
        "shares": [100.0, 50.0, 75.0],
    })

    with patch("src.analytics.cluster_buys.inspect") as mock_inspect, \
         patch("src.analytics.cluster_buys.pd.read_sql_query", return_value=mock_data):

        # Mock view exists
        mock_inspect.return_value.get_columns.return_value = [
            {"name": "ticker"},
            {"name": "transaction_date"},
            {"name": "filing_date"},
            {"name": "insider_name"},
            {"name": "transaction_code"},
            {"name": "shares"},
        ]

        result = _load_trades_for_ratio(
            mock_engine,
            ["AAPL"],
            date(2025, 1, 1),
            date(2025, 12, 31),
        )

        assert not result.empty, "Should return data when view exists"
        assert "P" in result["transaction_code"].values, "Should include P (purchase) codes"
        assert "S" in result["transaction_code"].values, "Should include S (sale) codes"
        assert "normalized_name" in result.columns, "Should have normalized_name column"


@pytest.mark.skipif(
    True,  # Skip by default (requires database)
    reason="Integration test - requires live database with insider_trade_signals view"
)
def test_insider_trade_signals_view_includes_sales():
    """
    Integration test: Verify insider_trade_signals view includes sales transactions.
    This test requires a live database connection and is skipped by default.

    To run: pytest tests/test_sale_to_purchase_ratio.py::test_insider_trade_signals_view_includes_sales -v
    """
    from src.config import get_engine
    from sqlalchemy import text

    engine = get_engine()

    # Check that view exists and has both P and S transactions
    query = text("""
        SELECT transaction_code, COUNT(*) as count
        FROM insider_trade_signals
        GROUP BY transaction_code
        ORDER BY transaction_code
    """)

    result = pd.read_sql_query(query, engine)

    assert not result.empty, "insider_trade_signals view should contain data"
    codes = result["transaction_code"].tolist()
    assert "P" in codes, "View should include P (purchase) transactions"
    assert "S" in codes, "View should include S (sale) transactions"

    # Verify S count is non-zero
    s_count = result.loc[result["transaction_code"] == "S", "count"].values[0]
    assert s_count > 0, "View should have at least some sale transactions"
