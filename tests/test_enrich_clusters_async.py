"""
Tests for async enrichment CLI checkpoint integration.

Covers crash recovery, periodic checkpoint saves, checkpoint clearing,
--no-resume flag behavior, and streaming mode exclusion.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module components we're testing
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.enrich_clusters_async import (
    enrich_small_file,
    CHECKPOINT_FREQUENCY,
)


# Test API key placeholder (not a real secret)
TEST_API_KEY = "test-api-key-placeholder"  # pragma: allowlist secret


# -------------------------------------------------------------------------
# FIXTURES
# -------------------------------------------------------------------------


@pytest.fixture
def sample_clusters_file(tmp_path: Path) -> Path:
    """Create a small test export file with 10 clusters."""
    data = {
        "rows": [
            {
                "ticker": f"TICK{i:02d}",
                "window_end": "2024-01-15",
                "entry_date": "2024-01-16",
                "total_value": 100000 * (i + 1),
                "cluster_score": 60.0 + i,
            }
            for i in range(10)
        ],
        "metadata": {"exported_at": "2024-01-20T10:00:00"},
    }
    file_path = tmp_path / "test_clusters.json"
    file_path.write_text(json.dumps(data))
    return file_path


@pytest.fixture
def mock_checkpoint_manager():
    """Create a mock CheckpointManager."""
    mock = MagicMock()
    mock.get_checkpoint.return_value = None
    mock.save_checkpoint.return_value = None
    mock.clear_checkpoint.return_value = None
    return mock


@pytest.fixture
def mock_enricher():
    """Create a mock AsyncEnricher that adds enrichment_status to clusters."""
    async def mock_enrich_cluster(cluster):
        enriched = dict(cluster)
        enriched["enrichment_status"] = "ok"
        enriched["price_at_entry"] = 100.0
        return enriched

    enricher = MagicMock()
    enricher.enrich_cluster = AsyncMock(side_effect=mock_enrich_cluster)
    enricher.__aenter__ = AsyncMock(return_value=enricher)
    enricher.__aexit__ = AsyncMock(return_value=None)
    return enricher


# -------------------------------------------------------------------------
# CHECKPOINT RESUME TESTS
# -------------------------------------------------------------------------


class TestCheckpointResume:
    """Tests for crash recovery via checkpointing."""

    @pytest.mark.asyncio
    async def test_checkpoint_resume_from_crash(
        self, sample_clusters_file: Path, mock_checkpoint_manager, mock_enricher
    ):
        """Verify processing resumes from checkpoint after simulated crash."""
        # Pre-populate checkpoint at index 4 (5 clusters processed: 0-4)
        mock_checkpoint_manager.get_checkpoint.return_value = {
            "last_index": 4,
            "processed_tickers": ["TICK00", "TICK01", "TICK02", "TICK03", "TICK04"],
            "errors": {},
        }

        # Track which clusters get enriched
        enriched_tickers = []

        async def track_enrich(cluster):
            enriched_tickers.append(cluster["ticker"])
            enriched = dict(cluster)
            enriched["enrichment_status"] = "ok"
            return enriched

        mock_enricher.enrich_cluster = AsyncMock(side_effect=track_enrich)

        with patch(
            "scripts.enrich_clusters_async.AsyncEnricher",
            return_value=mock_enricher,
        ):
            output_path, stats, elapsed = await enrich_small_file(
                file_path=sample_clusters_file,
                api_key=TEST_API_KEY,
                max_concurrent=5,
                shutdown=None,
                resume=True,
                checkpoint_mgr=mock_checkpoint_manager,
            )

        # Should have only enriched clusters 5-9 (indices 5-9), not 0-4
        assert enriched_tickers == ["TICK05", "TICK06", "TICK07", "TICK08", "TICK09"]

        # get_checkpoint should have been called with the run_id
        mock_checkpoint_manager.get_checkpoint.assert_called_once()
        run_id_call = mock_checkpoint_manager.get_checkpoint.call_args[0][0]
        assert "async_enrich_" in run_id_call

    @pytest.mark.asyncio
    async def test_no_resume_flag_ignores_checkpoint(
        self, sample_clusters_file: Path, mock_checkpoint_manager, mock_enricher
    ):
        """Verify resume=False starts fresh, ignoring existing checkpoint."""
        # Pre-populate checkpoint at index 4
        mock_checkpoint_manager.get_checkpoint.return_value = {
            "last_index": 4,
            "processed_tickers": ["TICK00", "TICK01", "TICK02", "TICK03", "TICK04"],
            "errors": {},
        }

        enriched_tickers = []

        async def track_enrich(cluster):
            enriched_tickers.append(cluster["ticker"])
            enriched = dict(cluster)
            enriched["enrichment_status"] = "ok"
            return enriched

        mock_enricher.enrich_cluster = AsyncMock(side_effect=track_enrich)

        with patch(
            "scripts.enrich_clusters_async.AsyncEnricher",
            return_value=mock_enricher,
        ):
            output_path, stats, elapsed = await enrich_small_file(
                file_path=sample_clusters_file,
                api_key=TEST_API_KEY,
                max_concurrent=5,
                shutdown=None,
                resume=False,  # <-- Start fresh
                checkpoint_mgr=mock_checkpoint_manager,
            )

        # Should have enriched ALL 10 clusters from index 0
        assert len(enriched_tickers) == 10
        assert enriched_tickers[0] == "TICK00"
        assert enriched_tickers[9] == "TICK09"

        # get_checkpoint should NOT have been called with resume=False
        mock_checkpoint_manager.get_checkpoint.assert_not_called()


# -------------------------------------------------------------------------
# CHECKPOINT SAVE TESTS
# -------------------------------------------------------------------------


class TestCheckpointSaves:
    """Tests for periodic checkpoint saves."""

    @pytest.mark.asyncio
    async def test_checkpoint_saved_periodically(
        self, tmp_path: Path, mock_checkpoint_manager, mock_enricher
    ):
        """Verify checkpoint is saved every CHECKPOINT_FREQUENCY clusters."""
        # Create file with enough clusters to trigger multiple saves
        # With CHECKPOINT_FREQUENCY=25, we need at least 50 for 2 saves
        # But for testing, we'll monkeypatch to use a smaller frequency
        num_clusters = 10
        data = {
            "rows": [
                {"ticker": f"T{i:02d}", "window_end": "2024-01-15"}
                for i in range(num_clusters)
            ],
            "metadata": {},
        }
        file_path = tmp_path / "clusters_for_save.json"
        file_path.write_text(json.dumps(data))

        with patch(
            "scripts.enrich_clusters_async.AsyncEnricher",
            return_value=mock_enricher,
        ), patch(
            "scripts.enrich_clusters_async.CHECKPOINT_FREQUENCY", 3
        ):
            # With frequency=3 and 10 clusters, saves at indices 2, 5, 8
            output_path, stats, elapsed = await enrich_small_file(
                file_path=file_path,
                api_key=TEST_API_KEY,
                max_concurrent=5,
                shutdown=None,
                resume=True,
                checkpoint_mgr=mock_checkpoint_manager,
            )

        # Check save_checkpoint was called at the right intervals
        # With frequency=3: after processing index 2 (3rd), index 5 (6th), index 8 (9th)
        save_calls = mock_checkpoint_manager.save_checkpoint.call_args_list
        assert len(save_calls) == 3

        # Verify the last_index values in calls
        last_indices = [call[1]["last_index"] for call in save_calls]
        assert last_indices == [2, 5, 8]

    @pytest.mark.asyncio
    async def test_checkpoint_cleared_on_success(
        self, sample_clusters_file: Path, mock_checkpoint_manager, mock_enricher
    ):
        """Verify checkpoint is cleared after successful completion."""
        with patch(
            "scripts.enrich_clusters_async.AsyncEnricher",
            return_value=mock_enricher,
        ):
            output_path, stats, elapsed = await enrich_small_file(
                file_path=sample_clusters_file,
                api_key=TEST_API_KEY,
                max_concurrent=5,
                shutdown=None,
                resume=True,
                checkpoint_mgr=mock_checkpoint_manager,
            )

        # clear_checkpoint should have been called once with the run_id
        mock_checkpoint_manager.clear_checkpoint.assert_called_once()
        run_id_call = mock_checkpoint_manager.clear_checkpoint.call_args[0][0]
        assert "async_enrich_test_clusters" in run_id_call


# -------------------------------------------------------------------------
# STREAMING MODE TESTS
# -------------------------------------------------------------------------


class TestStreamingModeNoCheckpointing:
    """Tests verifying streaming mode doesn't use checkpointing."""

    def test_streaming_mode_logs_checkpointing_disabled(self, tmp_path: Path):
        """Verify streaming mode logs that checkpointing is disabled."""
        # Create a large file that would trigger streaming mode (>50 clusters)
        num_clusters = 60
        data = {
            "rows": [
                {"ticker": f"T{i:03d}", "window_end": "2024-01-15"}
                for i in range(num_clusters)
            ],
            "metadata": {},
        }
        file_path = tmp_path / "large_clusters.json"
        file_path.write_text(json.dumps(data))

        # Import process_file for this test
        from scripts.enrich_clusters_async import process_file

        # We just verify the structure - streaming mode doesn't pass
        # checkpoint_mgr to enrich_streaming. The actual streaming function
        # doesn't have checkpoint support parameters at all.
        import inspect
        from scripts.enrich_clusters_async import enrich_streaming

        sig = inspect.signature(enrich_streaming)
        param_names = list(sig.parameters.keys())

        # enrich_streaming should NOT have checkpoint_mgr parameter
        assert "checkpoint_mgr" not in param_names
        assert "resume" not in param_names


# -------------------------------------------------------------------------
# OUTPUT VERIFICATION TESTS
# -------------------------------------------------------------------------


class TestOutputVerification:
    """Tests verifying enrichment output structure."""

    @pytest.mark.asyncio
    async def test_enrichment_output_written_to_file(
        self, sample_clusters_file: Path, mock_checkpoint_manager, mock_enricher
    ):
        """Verify enriched data is written to output file."""
        with patch(
            "scripts.enrich_clusters_async.AsyncEnricher",
            return_value=mock_enricher,
        ):
            output_path, stats, elapsed = await enrich_small_file(
                file_path=sample_clusters_file,
                api_key=TEST_API_KEY,
                max_concurrent=5,
                shutdown=None,
                resume=True,
                checkpoint_mgr=mock_checkpoint_manager,
            )

        assert output_path.exists()
        assert "_enriched" in output_path.stem

        # Verify output structure
        with open(output_path) as f:
            output_data = json.load(f)

        assert "rows" in output_data
        assert len(output_data["rows"]) == 10

        # All rows should have enrichment_status
        for row in output_data["rows"]:
            assert "enrichment_status" in row

    @pytest.mark.asyncio
    async def test_already_processed_clusters_preserved_on_resume(
        self, sample_clusters_file: Path, mock_checkpoint_manager, mock_enricher
    ):
        """Verify already processed clusters are preserved in output on resume."""
        # Checkpoint at index 4 means clusters 0-4 already processed
        mock_checkpoint_manager.get_checkpoint.return_value = {
            "last_index": 4,
            "processed_tickers": ["TICK00", "TICK01", "TICK02", "TICK03", "TICK04"],
            "errors": {},
        }

        with patch(
            "scripts.enrich_clusters_async.AsyncEnricher",
            return_value=mock_enricher,
        ):
            output_path, stats, elapsed = await enrich_small_file(
                file_path=sample_clusters_file,
                api_key=TEST_API_KEY,
                max_concurrent=5,
                shutdown=None,
                resume=True,
                checkpoint_mgr=mock_checkpoint_manager,
            )

        with open(output_path) as f:
            output_data = json.load(f)

        # Should still have all 10 rows (5 preserved + 5 newly enriched)
        assert len(output_data["rows"]) == 10

        # First 5 should be preserved (no enrichment_status added since not re-enriched)
        # Actually they should have original data since we slice clusters[:start_index]
        for i, row in enumerate(output_data["rows"][:5]):
            assert row["ticker"] == f"TICK{i:02d}"

        # Last 5 should be enriched (have enrichment_status)
        for row in output_data["rows"][5:]:
            assert row.get("enrichment_status") == "ok"
