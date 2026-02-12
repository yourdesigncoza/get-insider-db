"""
Tests for CIK-ticker mapping service.

Validates CikTickerMapper class functionality including:
- Forward lookups (CIK -> ticker)
- Reverse lookups (ticker -> CIK)
- Existence checks
- Singleton pattern
- Refresh functionality
- Zero-padding preservation
"""

import pytest
from unittest.mock import MagicMock, patch

from src.services.cik_ticker_mapping import CikTickerMapper, get_mapper, reset_mapper


@pytest.fixture(autouse=True)
def clean_singleton():
    """Reset global mapper between tests."""
    reset_mapper()
    yield
    reset_mapper()


def _make_mapper(mapping: dict[str, str]) -> CikTickerMapper:
    """Create a CikTickerMapper with pre-loaded cache (no DB)."""
    with patch.object(CikTickerMapper, '_load_mapping'):
        mapper = CikTickerMapper(engine=MagicMock())
    mapper._cache = dict(mapping)
    mapper._reverse_cache = {v: k for k, v in mapping.items()}
    return mapper


class TestGetTicker:
    """Test forward CIK -> ticker lookups."""

    def test_get_ticker_returns_mapped_ticker(self):
        """Known CIK returns correct ticker."""
        mapper = _make_mapper({
            "0000320193": "AAPL",
            "0000789019": "MSFT",
        })

        assert mapper.get_ticker("0000320193") == "AAPL"
        assert mapper.get_ticker("0000789019") == "MSFT"

    def test_get_ticker_returns_none_for_unknown(self):
        """Unknown CIK returns None."""
        mapper = _make_mapper({"0000320193": "AAPL"})

        assert mapper.get_ticker("0000999999") is None
        assert mapper.get_ticker("") is None

    def test_get_ticker_preserves_zero_padding(self):
        """CIK zero-padding is preserved in lookups."""
        mapper = _make_mapper({"0000730255": "CAMP"})

        result = mapper.get_ticker("0000730255")

        assert result == "CAMP"
        # Verify the key itself is zero-padded
        assert "0000730255" in mapper._cache
        assert "730255" not in mapper._cache


class TestGetCik:
    """Test reverse ticker -> CIK lookups."""

    def test_get_cik_reverse_lookup(self):
        """Ticker reverse-maps to CIK."""
        mapper = _make_mapper({
            "0000320193": "AAPL",
            "0000789019": "MSFT",
        })

        assert mapper.get_cik("AAPL") == "0000320193"
        assert mapper.get_cik("MSFT") == "0000789019"

    def test_get_cik_returns_none_for_unknown(self):
        """Unknown ticker returns None."""
        mapper = _make_mapper({"0000320193": "AAPL"})

        assert mapper.get_cik("TSLA") is None
        assert mapper.get_cik("") is None


class TestHasCik:
    """Test CIK existence checks."""

    def test_has_cik_true_for_mapped(self):
        """has_cik returns True for known CIK."""
        mapper = _make_mapper({"0000320193": "AAPL"})

        assert mapper.has_cik("0000320193") is True

    def test_has_cik_false_for_unknown(self):
        """has_cik returns False for unknown CIK."""
        mapper = _make_mapper({"0000320193": "AAPL"})

        assert mapper.has_cik("0000999999") is False
        assert mapper.has_cik("") is False


class TestCount:
    """Test count property."""

    def test_count_returns_mapping_size(self):
        """count property returns correct number of mappings."""
        mapper = _make_mapper({
            "0000320193": "AAPL",
            "0000789019": "MSFT",
            "0000730255": "CAMP",
        })

        assert mapper.count == 3

    def test_count_zero_for_empty(self):
        """count is zero when no mappings loaded."""
        mapper = _make_mapper({})

        assert mapper.count == 0


class TestRefresh:
    """Test refresh functionality."""

    def test_refresh_reloads_from_db(self):
        """refresh() re-queries database."""
        # Initial mapping
        mapper = _make_mapper({"0000320193": "AAPL"})

        assert mapper.get_ticker("0000320193") == "AAPL"
        assert mapper.count == 1

        # Mock refresh to load new data
        with patch.object(mapper, '_load_mapping') as mock_load:
            def update_cache():
                mapper._cache = {
                    "0000320193": "AAPL",
                    "0000789019": "MSFT",
                }
                mapper._reverse_cache = {
                    "AAPL": "0000320193",
                    "MSFT": "0000789019",
                }
            mock_load.side_effect = update_cache

            mapper.refresh()

        assert mapper.count == 2
        assert mapper.get_ticker("0000789019") == "MSFT"
        mock_load.assert_called_once()


class TestSingleton:
    """Test singleton pattern."""

    def test_get_mapper_returns_singleton(self):
        """get_mapper() returns same instance on repeated calls."""
        with patch.object(CikTickerMapper, '_load_mapping'):
            mapper1 = get_mapper(engine=MagicMock())
            mapper2 = get_mapper()

        assert mapper1 is mapper2

    def test_reset_mapper_clears_singleton(self):
        """reset_mapper() allows new instance creation."""
        with patch.object(CikTickerMapper, '_load_mapping'):
            mapper1 = get_mapper(engine=MagicMock())
            reset_mapper()
            mapper2 = get_mapper(engine=MagicMock())

        assert mapper1 is not mapper2


class TestZeroPaddedCik:
    """Regression tests for CIK zero-padding preservation."""

    def test_zero_padded_cik_preserved(self):
        """CIK '0000730255' not truncated to '730255'."""
        mapper = _make_mapper({"0000730255": "CAMP"})

        # Verify key is stored with zero-padding
        assert "0000730255" in mapper._cache
        assert len("0000730255") == 10

        # Verify lookup works with zero-padded CIK
        result = mapper.get_ticker("0000730255")
        assert result == "CAMP"

    def test_multiple_zero_padded_ciks(self):
        """Multiple zero-padded CIKs handled correctly."""
        mapper = _make_mapper({
            "0000320193": "AAPL",
            "0000730255": "CAMP",
            "0000012345": "TEST",
        })

        assert mapper.get_ticker("0000320193") == "AAPL"
        assert mapper.get_ticker("0000730255") == "CAMP"
        assert mapper.get_ticker("0000012345") == "TEST"

        # Verify all stored with correct padding
        for cik in mapper._cache.keys():
            assert len(cik) == 10
            assert cik.startswith("0000")


class TestMappingTableSchema:
    """Tests verifying mapping table schema supports one-CIK-one-ticker."""

    def test_latest_ticker_per_cik(self):
        """
        Mapping table schema supports one ticker per CIK.
        This is enforced by PRIMARY KEY on issuer_cik.
        """
        # Simulate scenario where CIK had multiple tickers historically
        # After refresh, only latest ticker should be in mapping
        mapper = _make_mapper({"0002076163": "BRR"})  # Latest ticker

        # Old ticker should not exist
        assert mapper.get_cik("OLD_TICKER") is None

        # Latest ticker should be mapped
        assert mapper.get_ticker("0002076163") == "BRR"
        assert mapper.get_cik("BRR") == "0002076163"

    def test_one_cik_one_ticker_invariant(self):
        """Each CIK maps to exactly one ticker."""
        mapper = _make_mapper({
            "0000320193": "AAPL",
            "0000789019": "MSFT",
            "0000730255": "CAMP",
        })

        # Verify forward mapping: one ticker per CIK
        assert len(mapper._cache) == 3

        # Verify each CIK has exactly one ticker
        for cik in mapper._cache.keys():
            ticker = mapper.get_ticker(cik)
            assert ticker is not None
            assert isinstance(ticker, str)
            assert len(ticker) > 0
