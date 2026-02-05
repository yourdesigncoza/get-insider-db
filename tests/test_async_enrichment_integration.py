"""
Integration tests for async enrichment pipeline.

Tests cover streaming I/O, batch processing, and output schema validation.
Real API tests are marked with @pytest.mark.integration and skipped by default.
"""

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.services.streaming import (
    stream_clusters,
    read_metadata,
    write_clusters_streaming,
    batch_clusters,
)
from src.services.enrichment_service import AsyncEnricher


# Test API key placeholder (not a real secret)
TEST_API_KEY = "test-api-key-placeholder"  # pragma: allowlist secret


# -------------------------------------------------------------------------
# FIXTURES
# -------------------------------------------------------------------------


@pytest.fixture
def sample_export_file(tmp_path: Path) -> Path:
    """Create a small test export file."""
    data = {
        "rows": [
            {
                "ticker": "AAPL",
                "window_end": "2024-01-15",
                "entry_date": "2024-01-16",
                "total_value": 100000,
                "cluster_score": 70.0,
            },
            {
                "ticker": "MSFT",
                "window_end": "2024-01-15",
                "entry_date": "2024-01-16",
                "total_value": 200000,
                "cluster_score": 80.0,
            },
        ],
        "metadata": {"exported_at": "2024-01-20T10:00:00"},
    }
    file_path = tmp_path / "test_clusters.json"
    file_path.write_text(json.dumps(data))
    return file_path


@pytest.fixture
def large_export_file(tmp_path: Path) -> Path:
    """Create a larger test export file for streaming tests."""
    rows = []
    for i in range(100):
        rows.append(
            {
                "ticker": f"TICK{i:03d}",
                "window_end": "2024-01-15",
                "entry_date": "2024-01-16",
                "total_value": 100000 * (i + 1),
                "cluster_score": 50.0 + (i % 50),
            }
        )
    data = {
        "rows": rows,
        "metadata": {"exported_at": "2024-01-20T10:00:00", "count": 100},
    }
    file_path = tmp_path / "large_clusters.json"
    file_path.write_text(json.dumps(data))
    return file_path


# -------------------------------------------------------------------------
# STREAMING TESTS
# -------------------------------------------------------------------------


class TestStreamingIO:
    """Tests for streaming JSON I/O."""

    def test_stream_clusters_yields_items(self, sample_export_file: Path):
        """Verify stream_clusters yields individual cluster dicts."""
        clusters = list(stream_clusters(sample_export_file))
        assert len(clusters) == 2
        assert clusters[0]["ticker"] == "AAPL"
        assert clusters[1]["ticker"] == "MSFT"

    def test_stream_clusters_large_file(self, large_export_file: Path):
        """Verify streaming works for larger files."""
        clusters = list(stream_clusters(large_export_file))
        assert len(clusters) == 100
        assert clusters[0]["ticker"] == "TICK000"
        assert clusters[99]["ticker"] == "TICK099"

    def test_read_metadata_extracts_correctly(self, sample_export_file: Path):
        """Verify metadata is extracted without loading rows."""
        metadata = read_metadata(sample_export_file)
        assert metadata["exported_at"] == "2024-01-20T10:00:00"

    def test_streaming_read_write_roundtrip(self, sample_export_file: Path, tmp_path: Path):
        """Verify write -> stream read -> verify produces identical content."""
        output_path = tmp_path / "roundtrip.json"
        metadata = {"test": "roundtrip", "timestamp": "2024-01-20"}

        # Read and transform clusters
        def add_enriched_flag():
            for cluster in stream_clusters(sample_export_file):
                cluster["enriched"] = True
                yield cluster

        # Write with streaming
        count = write_clusters_streaming(add_enriched_flag(), output_path, metadata)

        assert count == 2
        assert output_path.exists()

        # Read back and verify
        result_clusters = list(stream_clusters(output_path))
        assert len(result_clusters) == 2
        assert all(c.get("enriched") is True for c in result_clusters)

        result_meta = read_metadata(output_path)
        assert result_meta["test"] == "roundtrip"


class TestBatchProcessing:
    """Tests for batch_clusters utility."""

    def test_batch_clusters_groups_correctly(self, large_export_file: Path):
        """Verify batch_clusters produces correct batch sizes."""
        clusters = stream_clusters(large_export_file)
        batches = list(batch_clusters(clusters, batch_size=25))

        assert len(batches) == 4  # 100 clusters / 25 per batch
        assert all(len(b) == 25 for b in batches)

    def test_batch_clusters_handles_partial_final_batch(self, large_export_file: Path):
        """Verify last batch has remaining items."""
        clusters = stream_clusters(large_export_file)
        batches = list(batch_clusters(clusters, batch_size=30))

        # 100 / 30 = 3 full batches + 1 partial
        assert len(batches) == 4
        assert len(batches[0]) == 30
        assert len(batches[3]) == 10  # Remaining 10

    def test_batch_clusters_single_item_batches(self, sample_export_file: Path):
        """Verify batch_size=1 yields single-item batches."""
        clusters = stream_clusters(sample_export_file)
        batches = list(batch_clusters(clusters, batch_size=1))

        assert len(batches) == 2
        assert len(batches[0]) == 1
        assert len(batches[1]) == 1


# -------------------------------------------------------------------------
# OUTPUT SCHEMA TESTS
# -------------------------------------------------------------------------


class TestEnrichmentOutputSchema:
    """Tests for enriched output field requirements."""

    @pytest.mark.asyncio
    async def test_enrichment_output_has_required_fields(self, sample_export_file: Path):
        """Verify enriched clusters have all required output fields."""
        # Required fields for backward compatibility with sync script
        required_fields = [
            "enrichment_status",
            "enrichment_errors",
            "price_at_entry",
            "market_cap_at_entry",
            "enterprise_value_at_entry",
            "pe_ratio_at_entry",
            "pb_ratio_at_entry",
            "trailing_peg_ratio_at_entry",
            # Backward-compatible aliases
            "price_at_window_end",
            "market_cap_at_window_end",
            "cluster_value_vs_mcap_pct",
            "adjusted_cluster_score",
            # Price returns
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

        # Mock prices and fundamentals
        mock_prices = [
            {"date": __import__("datetime").datetime(2024, 1, 16), "close": 150.0},
            {"date": __import__("datetime").datetime(2024, 2, 16), "close": 160.0},
            {"date": __import__("datetime").datetime(2024, 3, 16), "close": 170.0},
            {"date": __import__("datetime").datetime(2024, 4, 16), "close": 180.0},
        ]
        mock_fundamentals = {
            "date": __import__("datetime").datetime(2024, 1, 15),
            "marketCap": 2500000000000,
            "enterpriseVal": 2600000000000,
            "peRatio": 28.5,
            "pbRatio": 35.0,
            "trailingPegRatio": 2.1,
        }

        with patch.object(
            AsyncEnricher, "get_price_history", new_callable=AsyncMock
        ) as mock_get_prices, patch.object(
            AsyncEnricher, "get_fundamentals", new_callable=AsyncMock
        ) as mock_get_fund:
            # get_price_history returns (prices, used_yfinance_fallback)
            mock_get_prices.return_value = (mock_prices, False)
            mock_get_fund.return_value = mock_fundamentals

            clusters = list(stream_clusters(sample_export_file))

            async with AsyncEnricher(api_key=TEST_API_KEY) as enricher:
                enriched = await enricher.enrich_batch(clusters)

            # Verify all required fields present
            for cluster in enriched:
                for field in required_fields:
                    assert field in cluster, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_enrichment_preserves_original_fields(self, sample_export_file: Path):
        """Verify original cluster fields are preserved after enrichment."""
        original_fields = ["ticker", "window_end", "entry_date", "total_value", "cluster_score"]

        with patch.object(
            AsyncEnricher, "get_price_history", new_callable=AsyncMock
        ) as mock_get_prices, patch.object(
            AsyncEnricher, "get_fundamentals", new_callable=AsyncMock
        ) as mock_get_fund:
            # get_price_history returns (prices, used_yfinance_fallback)
            mock_get_prices.return_value = ([], False)
            mock_get_fund.return_value = None

            clusters = list(stream_clusters(sample_export_file))

            async with AsyncEnricher(api_key=TEST_API_KEY) as enricher:
                enriched = await enricher.enrich_batch(clusters)

            # Verify original fields preserved
            for i, cluster in enumerate(enriched):
                for field in original_fields:
                    assert field in cluster, f"Original field missing: {field}"
                    assert cluster[field] == clusters[i][field]


# -------------------------------------------------------------------------
# INTEGRATION TESTS (real API, skipped by default)
# -------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("FINANCIAL_DATASETS_API_KEY"),
    reason="FINANCIAL_DATASETS_API_KEY not set",
)
class TestRealAPIIntegration:
    """Real API integration tests. Run with: pytest -m integration"""

    @pytest.mark.asyncio
    async def test_real_enrichment_small_batch(self, tmp_path: Path):
        """Real API test with 2-3 clusters (rate limited)."""
        api_key = os.getenv("FINANCIAL_DATASETS_API_KEY")

        # Create a small test file with well-known tickers
        data = {
            "rows": [
                {
                    "ticker": "AAPL",
                    "window_end": "2024-01-15",
                    "entry_date": "2024-01-16",
                    "total_value": 500000,
                    "cluster_score": 75.0,
                },
                {
                    "ticker": "MSFT",
                    "window_end": "2024-01-15",
                    "entry_date": "2024-01-16",
                    "total_value": 300000,
                    "cluster_score": 70.0,
                },
            ],
            "metadata": {"test": True},
        }
        test_file = tmp_path / "real_test.json"
        test_file.write_text(json.dumps(data))

        clusters = list(stream_clusters(test_file))

        async with AsyncEnricher(api_key=api_key, max_concurrent=2) as enricher:
            enriched = await enricher.enrich_batch(clusters)

        # Verify we got real data
        for cluster in enriched:
            assert "enrichment_status" in cluster
            # With real API, at least one should succeed
            if cluster["enrichment_status"] == "ok":
                assert cluster.get("price_at_entry") is not None
