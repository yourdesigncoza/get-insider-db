"""Tests for N/A and invalid ticker exclusion logic.

Validates that the SQL WHERE clause pattern used in cluster_buys.py
correctly filters out NULL, empty, 'NONE', 'N/A', 'NA', and their
case variants while preserving valid tickers.
"""
import pytest

# Invalid ticker values that the SQL filter must exclude
INVALID_TICKERS = ("NONE", "none", "N/A", "n/a", "NA", "na")


def is_valid_ticker(ticker: str | None) -> bool:
    """Replicate the SQL ticker filter logic from cluster_buys.py.

    SQL pattern:
        AND ticker IS NOT NULL
        AND ticker <> ''
        AND ticker NOT IN ('NONE', 'none', 'N/A', 'n/a', 'NA', 'na')
    """
    if ticker is None:
        return False
    if ticker == "":
        return False
    if ticker in INVALID_TICKERS:
        return False
    return True


class TestNullAndEmptyExclusion:
    """NULL and empty string tickers must be excluded."""

    def test_null_excluded(self):
        assert is_valid_ticker(None) is False

    def test_empty_string_excluded(self):
        assert is_valid_ticker("") is False


class TestInvalidTickerLiterals:
    """Known invalid ticker literals must be excluded."""

    @pytest.mark.parametrize("ticker", ["NONE", "none"])
    def test_none_variants_excluded(self, ticker):
        assert is_valid_ticker(ticker) is False

    @pytest.mark.parametrize("ticker", ["N/A", "n/a"])
    def test_n_a_variants_excluded(self, ticker):
        assert is_valid_ticker(ticker) is False

    @pytest.mark.parametrize("ticker", ["NA", "na"])
    def test_na_variants_excluded(self, ticker):
        assert is_valid_ticker(ticker) is False


class TestValidTickersPreserved:
    """Real stock tickers must pass the filter."""

    @pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "TSLA", "GOOG", "A"])
    def test_standard_tickers_pass(self, ticker):
        assert is_valid_ticker(ticker) is True

    def test_nasdaq_ticker_passes(self):
        assert is_valid_ticker("NVDA") is True

    def test_short_ticker_passes(self):
        """Single-char tickers (e.g., 'A' for Agilent) must not be caught."""
        assert is_valid_ticker("A") is True


class TestEdgeCases:
    """Edge cases that should NOT be filtered (not in scope)."""

    def test_ticker_with_dot_not_filtered(self):
        """BRK.A style tickers must pass."""
        assert is_valid_ticker("BRK.A") is True

    def test_ticker_with_dash_not_filtered(self):
        assert is_valid_ticker("BF-B") is True

    def test_n_a_dot_not_filtered(self):
        """'N.A.' is not in our exclusion list — out of scope."""
        assert is_valid_ticker("N.A.") is True
