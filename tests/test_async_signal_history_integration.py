"""
Tests for SignalHistoryRecorder integration with async enrichment.

Verifies that enrichment events are recorded to signal_history table
and that recording failures do not crash the enrichment process.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.enrich_clusters_async import enrich_small_file


# Test API key placeholder (not a real secret)
TEST_API_KEY = "test-api-key-placeholder"  # pragma: allowlist secret


# -------------------------------------------------------------------------
# FIXTURES
# -------------------------------------------------------------------------


@pytest.fixture
def sample_clusters_with_ids(tmp_path: Path) -> Path:
    """Create a test export file with cluster_id fields."""
    data = {
        "rows": [
            {
                "cluster_id": 101,
                "ticker": "AAPL",
                "window_end": "2024-01-15",
                "entry_date": "2024-01-16",
                "total_value": 500000,
                "cluster_score": 75.0,
            },
            {
                "cluster_id": 102,
                "ticker": "MSFT",
                "window_end": "2024-01-15",
                "entry_date": "2024-01-16",
                "total_value": 300000,
                "cluster_score": 68.0,
            },
            {
                # No cluster_id - should not trigger recording
                "ticker": "GOOG",
                "window_end": "2024-01-15",
                "entry_date": "2024-01-16",
                "total_value": 200000,
                "cluster_score": 62.0,
            },
        ],
        "metadata": {"exported_at": "2024-01-20T10:00:00"},
    }
    file_path = tmp_path / "clusters_with_ids.json"
    file_path.write_text(json.dumps(data))
    return file_path


@pytest.fixture
def mock_enricher():
    """Create a mock AsyncEnricher that adds enrichment fields."""
    async def mock_enrich_cluster(cluster):
        enriched = dict(cluster)
        enriched["enrichment_status"] = "ok"
        enriched["price_at_entry"] = 150.0
        enriched["adjusted_cluster_score"] = cluster.get("cluster_score", 60.0) * 1.1
        return enriched

    enricher = MagicMock()
    enricher.enrich_cluster = AsyncMock(side_effect=mock_enrich_cluster)
    enricher.__aenter__ = AsyncMock(return_value=enricher)
    enricher.__aexit__ = AsyncMock(return_value=None)
    return enricher


@pytest.fixture
def mock_recorder():
    """Create a mock SignalHistoryRecorder."""
    recorder = MagicMock()
    recorder.record_event.return_value = 1  # Return record ID
    return recorder


@pytest.fixture
def mock_checkpoint_manager():
    """Create a mock CheckpointManager."""
    mock = MagicMock()
    mock.get_checkpoint.return_value = None
    mock.save_checkpoint.return_value = None
    mock.clear_checkpoint.return_value = None
    return mock


# -------------------------------------------------------------------------
# SIGNAL HISTORY RECORDING TESTS
# -------------------------------------------------------------------------


class TestSignalHistoryRecording:
    """Tests verifying SignalHistoryRecorder is called during enrichment."""

    @pytest.mark.asyncio
    async def test_record_event_called_for_clusters_with_id(
        self, sample_clusters_with_ids: Path, mock_enricher, mock_recorder, mock_checkpoint_manager
    ):
        """Verify record_event is called for clusters that have cluster_id."""
        with patch(
            "scripts.enrich_clusters_async.AsyncEnricher",
            return_value=mock_enricher,
        ):
            output_path, stats, elapsed = await enrich_small_file(
                file_path=sample_clusters_with_ids,
                api_key=TEST_API_KEY,
                max_concurrent=5,
                shutdown=None,
                resume=False,
                checkpoint_mgr=mock_checkpoint_manager,
                recorder=mock_recorder,
            )

        # Should have recorded 2 events (for clusters with cluster_id)
        # Third cluster has no cluster_id so should not be recorded
        assert mock_recorder.record_event.call_count == 2

        # Verify call arguments
        calls = mock_recorder.record_event.call_args_list

        # First call for cluster_id=101
        call1_kwargs = calls[0][1]
        assert call1_kwargs["cluster_id"] == 101
        assert call1_kwargs["event_type"] == "enriched"
        assert call1_kwargs["changed_by"] == "async_enrichment"
        assert call1_kwargs["new_values"]["enrichment_status"] == "ok"
        assert call1_kwargs["new_values"]["price_at_entry"] == 150.0
        assert "Async enriched:" in call1_kwargs["reason"]

        # Second call for cluster_id=102
        call2_kwargs = calls[1][1]
        assert call2_kwargs["cluster_id"] == 102
        assert call2_kwargs["event_type"] == "enriched"
        assert call2_kwargs["changed_by"] == "async_enrichment"

    @pytest.mark.asyncio
    async def test_no_recording_without_cluster_id(
        self, tmp_path: Path, mock_enricher, mock_recorder, mock_checkpoint_manager
    ):
        """Verify no recording for clusters without cluster_id."""
        # Create file with no cluster_ids
        data = {
            "rows": [
                {"ticker": "TEST1", "window_end": "2024-01-15"},
                {"ticker": "TEST2", "window_end": "2024-01-15"},
            ],
            "metadata": {},
        }
        file_path = tmp_path / "no_ids.json"
        file_path.write_text(json.dumps(data))

        with patch(
            "scripts.enrich_clusters_async.AsyncEnricher",
            return_value=mock_enricher,
        ):
            output_path, stats, elapsed = await enrich_small_file(
                file_path=file_path,
                api_key=TEST_API_KEY,
                max_concurrent=5,
                shutdown=None,
                resume=False,
                checkpoint_mgr=mock_checkpoint_manager,
                recorder=mock_recorder,
            )

        # No record_event calls since no cluster_ids
        assert mock_recorder.record_event.call_count == 0

    @pytest.mark.asyncio
    async def test_enrichment_metadata_in_new_values(
        self, sample_clusters_with_ids: Path, mock_enricher, mock_recorder, mock_checkpoint_manager
    ):
        """Verify enrichment metadata is captured in new_values."""
        with patch(
            "scripts.enrich_clusters_async.AsyncEnricher",
            return_value=mock_enricher,
        ):
            await enrich_small_file(
                file_path=sample_clusters_with_ids,
                api_key=TEST_API_KEY,
                max_concurrent=5,
                shutdown=None,
                resume=False,
                checkpoint_mgr=mock_checkpoint_manager,
                recorder=mock_recorder,
            )

        # Check new_values contains expected fields
        call_kwargs = mock_recorder.record_event.call_args_list[0][1]
        new_values = call_kwargs["new_values"]

        assert "enrichment_status" in new_values
        assert "price_at_entry" in new_values
        assert "adjusted_cluster_score" in new_values


# -------------------------------------------------------------------------
# ERROR HANDLING TESTS
# -------------------------------------------------------------------------


class TestRecordingErrorHandling:
    """Tests verifying recording failures do not crash enrichment."""

    @pytest.mark.asyncio
    async def test_recording_failure_does_not_crash_enrichment(
        self, sample_clusters_with_ids: Path, mock_enricher, mock_checkpoint_manager
    ):
        """Verify enrichment continues when record_event raises exception."""
        # Create recorder that raises on first call
        failing_recorder = MagicMock()
        failing_recorder.record_event.side_effect = Exception("Database connection failed")

        with patch(
            "scripts.enrich_clusters_async.AsyncEnricher",
            return_value=mock_enricher,
        ):
            # Should not raise exception
            output_path, stats, elapsed = await enrich_small_file(
                file_path=sample_clusters_with_ids,
                api_key=TEST_API_KEY,
                max_concurrent=5,
                shutdown=None,
                resume=False,
                checkpoint_mgr=mock_checkpoint_manager,
                recorder=failing_recorder,
            )

        # Enrichment should have completed successfully
        assert output_path.exists()
        assert stats.total_clusters == 3
        assert stats.success == 3

        # Recorder was called (and failed) but enrichment continued
        assert failing_recorder.record_event.call_count == 2

    @pytest.mark.asyncio
    async def test_recording_failure_logged_as_warning(
        self, sample_clusters_with_ids: Path, mock_enricher, mock_checkpoint_manager
    ):
        """Verify recording failures are logged with warning level."""
        failing_recorder = MagicMock()
        failing_recorder.record_event.side_effect = Exception("DB error")

        logged_warnings = []

        def capture_warning(*args, **kwargs):
            if args and args[0] == "signal_history_record_failed":
                logged_warnings.append(kwargs)

        with patch(
            "scripts.enrich_clusters_async.AsyncEnricher",
            return_value=mock_enricher,
        ), patch(
            "scripts.enrich_clusters_async.logger.warning",
            side_effect=capture_warning,
        ):
            await enrich_small_file(
                file_path=sample_clusters_with_ids,
                api_key=TEST_API_KEY,
                max_concurrent=5,
                shutdown=None,
                resume=False,
                checkpoint_mgr=mock_checkpoint_manager,
                recorder=failing_recorder,
            )

        # Should have logged warnings for failed recordings
        assert len(logged_warnings) == 2
        assert logged_warnings[0]["cluster_id"] == 101
        assert "DB error" in logged_warnings[0]["error"]


# -------------------------------------------------------------------------
# NO RECORDER TESTS
# -------------------------------------------------------------------------


class TestNoRecorder:
    """Tests verifying enrichment works without recorder."""

    @pytest.mark.asyncio
    async def test_enrichment_works_without_recorder(
        self, sample_clusters_with_ids: Path, mock_enricher, mock_checkpoint_manager
    ):
        """Verify enrichment completes when recorder is None."""
        with patch(
            "scripts.enrich_clusters_async.AsyncEnricher",
            return_value=mock_enricher,
        ):
            output_path, stats, elapsed = await enrich_small_file(
                file_path=sample_clusters_with_ids,
                api_key=TEST_API_KEY,
                max_concurrent=5,
                shutdown=None,
                resume=False,
                checkpoint_mgr=mock_checkpoint_manager,
                recorder=None,  # No recorder
            )

        # Enrichment should complete successfully
        assert output_path.exists()
        assert stats.total_clusters == 3
        assert stats.success == 3

        # Verify output has enriched data
        with open(output_path) as f:
            output_data = json.load(f)

        assert len(output_data["rows"]) == 3
        for row in output_data["rows"]:
            assert row.get("enrichment_status") == "ok"
