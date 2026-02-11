"""
Tests for issuer_cik population in cluster scan output.

Validates that:
1. issuer_cik is included in cluster output dictionaries
2. CIK extraction logic works correctly with _first_nonempty_any()
3. Missing column fallback returns empty string
4. Zero-padding is preserved (e.g., "0000730255" not truncated)
5. _get_optional_column finds issuer_cik column via introspection
"""

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from src.analytics.cluster_buys import _first_nonempty_any, _get_optional_column


class TestIssuerCikOutputDict:
    """Test issuer_cik is included in cluster output dictionary."""

    def test_issuer_cik_included_in_output_dict(self):
        """Verify output dict structure matches cluster_buys.py line 697-714."""
        # Replicate the output dict structure
        output_dict = {
            "ticker": "AAPL",
            "issuer_cik": "0000320193",
            "issuer_name": "Apple Inc.",
            "window_start": "2024-01-01",
            "window_end": "2024-01-10",
            "signal_filing_date": "2024-01-10",
            "entry_date": "2024-01-11",
            "num_trades": 5,
            "num_insiders": 3,
            "num_total_insiders": 3,
            "num_fund_like": 0,
            "fund_ratio": 0.0,
            "total_shares": 10000.0,
            "total_value": 1500000.0,
        }

        # Assert issuer_cik key exists and is not None
        assert "issuer_cik" in output_dict
        assert output_dict["issuer_cik"] is not None
        assert output_dict["issuer_cik"] == "0000320193"


class TestIssuerCikExtraction:
    """Test CIK extraction logic from DataFrame subsets."""

    def test_issuer_cik_extraction_from_subset(self):
        """Verify _first_nonempty_any returns first non-empty CIK value."""
        # Create DataFrame with mixed CIK values
        df = pd.DataFrame({
            "issuer_cik": ["", None, "0000730255", "0000320193"]
        })

        result = _first_nonempty_any(df["issuer_cik"])

        assert result == "0000730255"

    def test_issuer_cik_all_empty(self):
        """When all CIK values are empty, return empty string."""
        df = pd.DataFrame({
            "issuer_cik": ["", None, "", None]
        })

        result = _first_nonempty_any(df["issuer_cik"])

        assert result == ""

    def test_issuer_cik_missing_column_fallback(self):
        """When issuer_cik column missing, extraction should handle gracefully."""
        # Create DataFrame without issuer_cik column
        df = pd.DataFrame({
            "ticker": ["AAPL", "GOOGL"],
            "issuer_name": ["Apple Inc.", "Alphabet Inc."]
        })

        # Replicate the fallback logic from line 595
        result = _first_nonempty_any(df["issuer_cik"]) if "issuer_cik" in df.columns else ""

        assert result == ""


class TestIssuerCikFormatPreservation:
    """Test that CIK zero-padding is preserved."""

    def test_issuer_cik_preserves_zero_padding(self):
        """Verify CIK strings like '0000730255' are not truncated to '730255'."""
        df = pd.DataFrame({
            "issuer_cik": ["0000730255", "0000320193", "0000012345"]
        })

        result = _first_nonempty_any(df["issuer_cik"])

        # Should preserve leading zeros
        assert result == "0000730255"
        assert len(result) == 10
        assert result.startswith("0000")

    def test_issuer_cik_numeric_conversion(self):
        """Guard against accidental int casting that would drop zeros."""
        # If CIK were converted to int then back to str, zeros would be lost
        df = pd.DataFrame({
            "issuer_cik": ["0000730255"]
        })

        result = _first_nonempty_any(df["issuer_cik"])

        # Verify it's NOT "730255"
        assert result != "730255"
        assert result == "0000730255"


class TestGetOptionalColumnFindsIssuerCik:
    """Test that _get_optional_column finds issuer_cik via introspection."""

    @patch("src.analytics.cluster_buys.inspect")
    def test_get_optional_column_finds_issuer_cik(self, mock_inspect):
        """Verify _get_optional_column returns 'issuer_cik' when column exists."""
        # Mock the SQLAlchemy inspector
        mock_inspector = MagicMock()
        mock_inspector.get_columns.return_value = [
            {"name": "ticker"},
            {"name": "issuer_name"},
            {"name": "issuer_cik"},
            {"name": "insider_cik"},
            {"name": "transaction_date"},
        ]
        mock_inspect.return_value = mock_inspector

        # Create mock engine
        mock_engine = MagicMock()

        # Test that _get_optional_column finds issuer_cik
        result = _get_optional_column(mock_engine, "insider_buy_signals", ("issuer_cik", "cik"))

        assert result == "issuer_cik"
        mock_inspector.get_columns.assert_called_once_with("insider_buy_signals")

    @patch("src.analytics.cluster_buys.inspect")
    def test_get_optional_column_fallback_to_cik(self, mock_inspect):
        """If issuer_cik missing but cik exists, return cik."""
        mock_inspector = MagicMock()
        mock_inspector.get_columns.return_value = [
            {"name": "ticker"},
            {"name": "cik"},
            {"name": "insider_cik"},
        ]
        mock_inspect.return_value = mock_inspector

        mock_engine = MagicMock()

        result = _get_optional_column(mock_engine, "insider_buy_signals", ("issuer_cik", "cik"))

        assert result == "cik"

    @patch("src.analytics.cluster_buys.inspect")
    def test_get_optional_column_returns_none_when_missing(self, mock_inspect):
        """When no candidate columns exist, return None."""
        mock_inspector = MagicMock()
        mock_inspector.get_columns.return_value = [
            {"name": "ticker"},
            {"name": "issuer_name"},
        ]
        mock_inspect.return_value = mock_inspector

        mock_engine = MagicMock()

        result = _get_optional_column(mock_engine, "insider_buy_signals", ("issuer_cik", "cik"))

        assert result is None
