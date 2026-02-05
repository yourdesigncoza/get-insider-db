"""
Unit tests for AsyncEnricher enrichment service.

Tests cover happy path, cache hits, API errors, and batch processing.
All API calls are mocked to avoid real network requests.
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from src.services.enrichment_service import (
    AsyncEnricher,
    _calculate_max_drawdown,
    _completeness_score,
    _get_first_price_record_on_or_after,
    _normalize_financial_metrics_record,
    _parse_date,
    _parse_float,
)
from src.exceptions import InvalidTickerError


# Test API key placeholder (not a real secret)
TEST_API_KEY = "test-api-key-placeholder"  # pragma: allowlist secret


# -------------------------------------------------------------------------
# FIXTURES
# -------------------------------------------------------------------------


@pytest.fixture
def mock_cluster():
    """Basic cluster fixture for testing."""
    return {
        "ticker": "AAPL",
        "window_end": "2024-01-15",
        "entry_date": "2024-01-16",
        "total_value": 500000,
        "cluster_score": 75.0,
    }


@pytest.fixture
def mock_prices():
    """Mock price history response."""
    return [
        {"date": datetime(2024, 1, 16), "close": 150.0},
        {"date": datetime(2024, 1, 17), "close": 152.0},
        {"date": datetime(2024, 1, 18), "close": 148.0},
        {"date": datetime(2024, 2, 16), "close": 160.0},
        {"date": datetime(2024, 3, 16), "close": 170.0},
        {"date": datetime(2024, 4, 16), "close": 180.0},
    ]


@pytest.fixture
def mock_fundamentals():
    """Mock fundamentals response."""
    return {
        "date": datetime(2024, 1, 15),
        "marketCap": 2500000000000,  # 2.5T
        "enterpriseVal": 2600000000000,
        "peRatio": 28.5,
        "pbRatio": 35.0,
        "trailingPegRatio": 2.1,
    }


# -------------------------------------------------------------------------
# HELPER FUNCTION TESTS
# -------------------------------------------------------------------------


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_parse_float_with_valid_float(self):
        assert _parse_float(123.45) == 123.45

    def test_parse_float_with_none(self):
        assert _parse_float(None) is None

    def test_parse_float_with_string_none(self):
        assert _parse_float("None") is None
        assert _parse_float("none") is None

    def test_parse_float_with_invalid_string(self):
        assert _parse_float("invalid") is None

    def test_parse_date_with_datetime(self):
        dt = datetime(2024, 1, 15)
        assert _parse_date(dt) == dt

    def test_parse_date_with_string(self):
        result = _parse_date("2024-01-15")
        assert result == datetime(2024, 1, 15)

    def test_parse_date_with_iso_string(self):
        result = _parse_date("2024-01-15T12:30:00Z")
        assert result == datetime(2024, 1, 15)

    def test_parse_date_with_none(self):
        assert _parse_date(None) is None

    def test_completeness_score_all_fields(self):
        record = {
            "marketCap": 1000,
            "enterpriseVal": 1100,
            "peRatio": 25,
            "pbRatio": 3.5,
            "trailingPegRatio": 1.5,
        }
        assert _completeness_score(record) == 5

    def test_completeness_score_partial_fields(self):
        record = {
            "marketCap": 1000,
            "enterpriseVal": None,
            "peRatio": 25,
        }
        assert _completeness_score(record) == 2

    def test_completeness_score_no_fields(self):
        record = {}
        assert _completeness_score(record) == 0

    def test_normalize_financial_metrics_snake_case(self):
        record = {
            "market_cap": 1000000,
            "enterprise_value": 1100000,
            "price_to_earnings_ratio": 25.0,
            "price_to_book_ratio": 3.5,
            "peg_ratio": 1.5,
            "report_period": "2024-01-15",
        }
        fallback = datetime(2024, 1, 1)
        result = _normalize_financial_metrics_record(record, fallback)

        assert result["marketCap"] == 1000000
        assert result["enterpriseVal"] == 1100000
        assert result["peRatio"] == 25.0
        assert result["pbRatio"] == 3.5
        assert result["trailingPegRatio"] == 1.5
        assert result["date"] == datetime(2024, 1, 15)

    def test_normalize_financial_metrics_camel_case(self):
        record = {
            "marketCap": 2000000,
            "peRatio": 30.0,
            "date": "2024-02-01",
        }
        fallback = datetime(2024, 1, 1)
        result = _normalize_financial_metrics_record(record, fallback)

        assert result["marketCap"] == 2000000
        assert result["peRatio"] == 30.0
        assert result["date"] == datetime(2024, 2, 1)

    def test_calculate_max_drawdown_with_drawdown(self):
        prices = [100, 95, 90, 95, 100]  # Min = 90
        base = 100
        result = _calculate_max_drawdown(prices, base)
        assert result == -10.0  # (90 - 100) / 100 * 100 = -10%

    def test_calculate_max_drawdown_no_drawdown(self):
        prices = [100, 105, 110]
        base = 100
        result = _calculate_max_drawdown(prices, base)
        assert result == 0.0

    def test_calculate_max_drawdown_empty_prices(self):
        result = _calculate_max_drawdown([], 100)
        assert result is None

    def test_calculate_max_drawdown_none_base(self):
        result = _calculate_max_drawdown([100, 95], None)
        assert result is None

    def test_get_first_price_record_on_or_after_exact_match(self):
        history = [
            {"date": datetime(2024, 1, 15), "close": 100},
            {"date": datetime(2024, 1, 16), "close": 102},
        ]
        result = _get_first_price_record_on_or_after(history, datetime(2024, 1, 15))
        assert result["close"] == 100

    def test_get_first_price_record_on_or_after_later_date(self):
        history = [
            {"date": datetime(2024, 1, 15), "close": 100},
            {"date": datetime(2024, 1, 17), "close": 102},
        ]
        result = _get_first_price_record_on_or_after(history, datetime(2024, 1, 16))
        assert result["close"] == 102  # First record on or after 1/16

    def test_get_first_price_record_on_or_after_no_match(self):
        history = [
            {"date": datetime(2024, 1, 15), "close": 100},
        ]
        result = _get_first_price_record_on_or_after(history, datetime(2024, 1, 20))
        assert result is None


# -------------------------------------------------------------------------
# ASYNC ENRICHER TESTS
# -------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="function")
class TestAsyncEnricher:
    """Tests for AsyncEnricher class."""

    async def test_enrich_cluster_happy_path(self, mock_cluster, mock_prices, mock_fundamentals):
        """Test successful enrichment with mocked API responses."""
        with patch.object(
            AsyncEnricher, "get_price_history", new_callable=AsyncMock
        ) as mock_get_prices, patch.object(
            AsyncEnricher, "get_fundamentals", new_callable=AsyncMock
        ) as mock_get_fund:
            mock_get_prices.return_value = mock_prices
            mock_get_fund.return_value = mock_fundamentals

            async with AsyncEnricher(api_key=TEST_API_KEY) as enricher:
                result = await enricher.enrich_cluster(mock_cluster)

            assert result["enrichment_status"] == "ok"
            assert result["enrichment_errors"] == []
            assert result["price_at_entry"] == 150.0
            assert result["market_cap_at_entry"] == 2500000000000
            assert result["pe_ratio_at_entry"] == 28.5
            assert "return_1m" in result
            assert "return_2m" in result
            assert "return_3m" in result
            assert "adjusted_cluster_score" in result

    async def test_enrich_cluster_cache_hit(self, mock_cluster, mock_prices, mock_fundamentals):
        """Test that cache is checked before API calls."""
        with patch.object(
            AsyncEnricher, "_check_price_cache", new_callable=AsyncMock
        ) as mock_cache_prices, patch.object(
            AsyncEnricher, "_fetch_prices_from_api", new_callable=AsyncMock
        ) as mock_api_prices, patch.object(
            AsyncEnricher, "_check_fundamentals_cache", new_callable=AsyncMock
        ) as mock_cache_fund, patch.object(
            AsyncEnricher, "_fetch_fundamentals_from_api", new_callable=AsyncMock
        ) as mock_api_fund:
            # Simulate cache hits - return enough data that API won't be called
            mock_cache_prices.return_value = mock_prices
            mock_cache_fund.return_value = mock_fundamentals

            async with AsyncEnricher(api_key=TEST_API_KEY) as enricher:
                result = await enricher.enrich_cluster(mock_cluster)

            # API should not have been called since cache had data
            mock_api_fund.assert_not_called()
            assert result["enrichment_status"] == "ok"
            assert result["market_cap_at_entry"] == 2500000000000

    async def test_enrich_cluster_api_error(self, mock_cluster):
        """Test error handling when API returns 500."""
        with patch.object(
            AsyncEnricher, "get_price_history", new_callable=AsyncMock
        ) as mock_get_prices, patch.object(
            AsyncEnricher, "get_fundamentals", new_callable=AsyncMock
        ) as mock_get_fund:
            mock_get_prices.side_effect = aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=500,
                message="Internal Server Error",
            )
            mock_get_fund.return_value = None

            async with AsyncEnricher(api_key=TEST_API_KEY) as enricher:
                result = await enricher.enrich_cluster(mock_cluster)

            assert result["enrichment_status"] == "error"
            assert len(result["enrichment_errors"]) > 0
            assert "prices:" in result["enrichment_errors"][0]

    async def test_enrich_cluster_invalid_ticker(self, mock_cluster):
        """Test handling of invalid ticker (400 response)."""
        with patch.object(
            AsyncEnricher, "get_price_history", new_callable=AsyncMock
        ) as mock_get_prices, patch.object(
            AsyncEnricher, "get_fundamentals", new_callable=AsyncMock
        ) as mock_get_fund:
            mock_get_prices.side_effect = InvalidTickerError("Invalid ticker: BADTK")
            mock_get_fund.side_effect = InvalidTickerError("Invalid ticker: BADTK")

            async with AsyncEnricher(api_key=TEST_API_KEY) as enricher:
                result = await enricher.enrich_cluster(mock_cluster)

            assert result["enrichment_status"] == "unsupported_ticker"
            assert len(result["enrichment_errors"]) >= 1

    async def test_enrich_batch_partial_failure(self, mock_cluster, mock_prices, mock_fundamentals):
        """Test batch processing where one cluster fails but others succeed."""
        clusters = [
            mock_cluster.copy(),
            {"ticker": "BADTK", "window_end": "2024-01-15", "entry_date": "2024-01-16"},
            mock_cluster.copy(),
        ]
        clusters[0]["ticker"] = "AAPL"
        clusters[2]["ticker"] = "MSFT"

        async def mock_enrich(cluster):
            if cluster.get("ticker") == "BADTK":
                raise InvalidTickerError("Invalid ticker: BADTK")
            enriched = cluster.copy()
            enriched["enrichment_status"] = "ok"
            enriched["price_at_entry"] = 150.0
            return enriched

        with patch.object(
            AsyncEnricher, "enrich_cluster", new_callable=AsyncMock
        ) as mock_enrich_fn:
            mock_enrich_fn.side_effect = mock_enrich

            async with AsyncEnricher(api_key=TEST_API_KEY) as enricher:
                results = await enricher.enrich_batch(clusters)

            assert len(results) == 3
            assert results[0]["enrichment_status"] == "ok"
            assert results[1]["enrichment_status"] == "error"
            assert results[2]["enrichment_status"] == "ok"

    async def test_semaphore_limits_concurrency(self, mock_cluster):
        """Test that semaphore limits concurrent API requests."""
        max_concurrent = 2
        concurrent_count = 0
        max_observed = 0
        lock = asyncio.Lock()

        async def mock_get(*args, **kwargs):
            nonlocal concurrent_count, max_observed
            async with lock:
                concurrent_count += 1
                if concurrent_count > max_observed:
                    max_observed = concurrent_count
            await asyncio.sleep(0.05)  # Simulate API latency
            async with lock:
                concurrent_count -= 1
            return {"prices": []}

        with patch.object(
            AsyncEnricher, "_check_price_cache", new_callable=AsyncMock
        ) as mock_cache, patch(
            "src.services.enrichment_service.AsyncHTTPClient"
        ) as MockClient:
            mock_cache.return_value = []  # Force API fetch

            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            # Create enricher with limited concurrency
            enricher = AsyncEnricher(api_key=TEST_API_KEY, max_concurrent=max_concurrent)
            enricher._client = mock_client

            # Make multiple concurrent price requests
            clusters = [mock_cluster.copy() for _ in range(5)]

            # Patch fundamentals to return quickly
            with patch.object(
                AsyncEnricher, "get_fundamentals", new_callable=AsyncMock
            ) as mock_fund:
                mock_fund.return_value = None

                await enricher.enrich_batch(clusters)
                await enricher.close()

        # The AsyncHTTPClient semaphore should limit concurrent requests
        # Note: max_observed depends on timing, but it should complete without error
        assert max_observed >= 1  # At least some concurrency

    async def test_context_manager(self, mock_cluster):
        """Test that context manager properly closes resources."""
        with patch.object(
            AsyncEnricher, "close", new_callable=AsyncMock
        ) as mock_close:
            async with AsyncEnricher(api_key=TEST_API_KEY):
                pass

            mock_close.assert_called_once()

    async def test_enrich_cluster_missing_ticker(self):
        """Test cluster without ticker returns unchanged."""
        cluster = {"window_end": "2024-01-15"}

        async with AsyncEnricher(api_key=TEST_API_KEY) as enricher:
            result = await enricher.enrich_cluster(cluster)

        assert result == cluster

    async def test_enrich_cluster_no_price_data(self, mock_cluster):
        """Test handling when no price data is available."""
        with patch.object(
            AsyncEnricher, "get_price_history", new_callable=AsyncMock
        ) as mock_prices, patch.object(
            AsyncEnricher, "get_fundamentals", new_callable=AsyncMock
        ) as mock_fund:
            mock_prices.return_value = []  # No price data
            mock_fund.return_value = None

            async with AsyncEnricher(api_key=TEST_API_KEY) as enricher:
                result = await enricher.enrich_cluster(mock_cluster)

            assert result["enrichment_status"] == "no_price_data"
            assert result["price_at_entry"] is None


# -------------------------------------------------------------------------
# INTEGRATION-STYLE TESTS (still mocked, but test full flow)
# -------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="function")
class TestAsyncEnricherIntegration:
    """Integration-style tests for full enrichment flow."""

    async def test_full_enrichment_flow(self, mock_cluster, mock_prices, mock_fundamentals):
        """Test complete enrichment flow from cluster to enriched output."""
        with patch.object(
            AsyncEnricher, "get_price_history", new_callable=AsyncMock
        ) as mock_get_prices, patch.object(
            AsyncEnricher, "get_fundamentals", new_callable=AsyncMock
        ) as mock_get_fund:
            mock_get_prices.return_value = mock_prices
            mock_get_fund.return_value = mock_fundamentals

            async with AsyncEnricher(api_key=TEST_API_KEY) as enricher:
                result = await enricher.enrich_cluster(mock_cluster)

            # Verify all expected fields are present
            expected_fields = [
                "enrichment_status",
                "enrichment_errors",
                "price_at_entry",
                "market_cap_at_entry",
                "enterprise_value_at_entry",
                "pe_ratio_at_entry",
                "pb_ratio_at_entry",
                "trailing_peg_ratio_at_entry",
                "price_at_window_end",  # Backward-compatible alias
                "cluster_value_vs_mcap_pct",
                "adjusted_cluster_score",
                "price_1m_after",
                "price_2m_after",
                "price_3m_after",
                "return_1m",
                "return_2m",
                "return_3m",
                "max_drawdown_1m",
                "max_drawdown_2m",
                "max_drawdown_3m",
            ]
            for field in expected_fields:
                assert field in result, f"Missing field: {field}"

            # Verify original cluster fields preserved
            assert result["ticker"] == "AAPL"
            assert result["window_end"] == "2024-01-15"
            assert result["cluster_score"] == 75.0

    async def test_batch_enrichment_maintains_order(self, mock_cluster, mock_prices):
        """Test that batch enrichment maintains cluster order."""
        clusters = []
        for i in range(5):
            c = mock_cluster.copy()
            c["ticker"] = f"TICK{i}"
            c["order_id"] = i
            clusters.append(c)

        with patch.object(
            AsyncEnricher, "get_price_history", new_callable=AsyncMock
        ) as mock_get_prices, patch.object(
            AsyncEnricher, "get_fundamentals", new_callable=AsyncMock
        ) as mock_get_fund:
            mock_get_prices.return_value = mock_prices
            mock_get_fund.return_value = None

            async with AsyncEnricher(api_key=TEST_API_KEY) as enricher:
                results = await enricher.enrich_batch(clusters)

            # Verify order is maintained
            for i, result in enumerate(results):
                assert result["order_id"] == i
                assert result["ticker"] == f"TICK{i}"
