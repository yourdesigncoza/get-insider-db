"""Tests for CheckpointManager CRUD operations."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.checkpointing import CheckpointManager


class TestCheckpointManager:
    """Tests for CheckpointManager database operations."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        engine = MagicMock()
        return engine

    @pytest.fixture
    def checkpoint_manager(self, mock_engine):
        """Create a CheckpointManager with mocked engine."""
        return CheckpointManager(mock_engine)

    def test_get_checkpoint_returns_none_when_not_found(self, checkpoint_manager, mock_engine):
        """get_checkpoint returns None when no checkpoint exists."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        result = checkpoint_manager.get_checkpoint("test_run_id")

        assert result is None
        mock_conn.execute.assert_called_once()

    def test_get_checkpoint_returns_data_when_found(self, checkpoint_manager, mock_engine):
        """get_checkpoint returns checkpoint data when it exists."""
        mock_conn = MagicMock()
        updated_at = datetime.now(timezone.utc)
        mock_conn.execute.return_value.fetchone.return_value = (
            10,  # last_processed_index
            ["AAPL", "MSFT"],  # processed_tickers
            {"GOOG": "API error"},  # errors
            updated_at,
        )
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        result = checkpoint_manager.get_checkpoint("test_run_id")

        assert result is not None
        assert result["last_index"] == 10
        assert result["processed_tickers"] == ["AAPL", "MSFT"]
        assert result["errors"] == {"GOOG": "API error"}
        assert result["updated_at"] == updated_at

    def test_get_checkpoint_handles_null_lists(self, checkpoint_manager, mock_engine):
        """get_checkpoint handles NULL values from database."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (
            0,  # last_processed_index
            None,  # processed_tickers is NULL
            None,  # errors is NULL
            datetime.now(timezone.utc),
        )
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        result = checkpoint_manager.get_checkpoint("test_run_id")

        assert result["processed_tickers"] == []
        assert result["errors"] == {}

    def test_save_checkpoint_creates_new_record(self, checkpoint_manager, mock_engine):
        """save_checkpoint inserts a new checkpoint record."""
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn

        checkpoint_manager.save_checkpoint(
            run_id="test_run_id",
            last_index=5,
            processed_tickers=["AAPL", "MSFT"],
            errors={"GOOG": "Invalid ticker"},
        )

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        params = call_args[0][1]

        assert params["run_id"] == "test_run_id"
        assert params["idx"] == 5
        assert json.loads(params["tickers"]) == ["AAPL", "MSFT"]
        assert json.loads(params["errors"]) == {"GOOG": "Invalid ticker"}
        assert isinstance(params["now"], datetime)

    def test_save_checkpoint_upsert_updates_existing(self, checkpoint_manager, mock_engine):
        """save_checkpoint uses upsert to update existing record."""
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn

        # First save
        checkpoint_manager.save_checkpoint(
            run_id="test_run_id",
            last_index=5,
            processed_tickers=["AAPL"],
            errors={},
        )

        # Second save (simulates update)
        checkpoint_manager.save_checkpoint(
            run_id="test_run_id",
            last_index=10,
            processed_tickers=["AAPL", "MSFT", "GOOG"],
            errors={"TSLA": "Rate limited"},
        )

        # Both calls should use the same upsert SQL
        assert mock_conn.execute.call_count == 2
        second_call_params = mock_conn.execute.call_args_list[1][0][1]
        assert second_call_params["idx"] == 10
        assert json.loads(second_call_params["tickers"]) == ["AAPL", "MSFT", "GOOG"]

    def test_clear_checkpoint_removes_record(self, checkpoint_manager, mock_engine):
        """clear_checkpoint deletes the checkpoint record."""
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn

        checkpoint_manager.clear_checkpoint("test_run_id")

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        sql_text = str(call_args[0][0])
        params = call_args[0][1]

        assert "DELETE" in sql_text
        assert "enrichment_checkpoints" in sql_text
        assert params["run_id"] == "test_run_id"

    def test_checkpoint_data_integrity_round_trip(self, checkpoint_manager, mock_engine):
        """Verify checkpoint data maintains integrity through save/get cycle."""
        # This tests the logic without actual DB - using mocks to simulate round trip
        saved_data = {}

        def mock_save(sql, params):
            saved_data["run_id"] = params["run_id"]
            saved_data["idx"] = params["idx"]
            saved_data["tickers"] = json.loads(params["tickers"])
            saved_data["errors"] = json.loads(params["errors"])
            saved_data["now"] = params["now"]

        mock_conn_save = MagicMock()
        mock_conn_save.execute.side_effect = mock_save
        mock_engine.begin.return_value.__enter__.return_value = mock_conn_save

        # Complex test data
        test_tickers = ["AAPL", "MSFT", "GOOG", "AMZN", "META"]
        test_errors = {
            "INVALID1": "Invalid ticker",
            "RATELIMIT": "429 Too Many Requests",
        }

        checkpoint_manager.save_checkpoint(
            run_id="complex_test",
            last_index=42,
            processed_tickers=test_tickers,
            errors=test_errors,
        )

        # Verify saved data
        assert saved_data["run_id"] == "complex_test"
        assert saved_data["idx"] == 42
        assert saved_data["tickers"] == test_tickers
        assert saved_data["errors"] == test_errors

    def test_empty_checkpoint_data(self, checkpoint_manager, mock_engine):
        """save_checkpoint handles empty lists and dicts."""
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn

        checkpoint_manager.save_checkpoint(
            run_id="empty_test",
            last_index=0,
            processed_tickers=[],
            errors={},
        )

        call_args = mock_conn.execute.call_args
        params = call_args[0][1]

        assert json.loads(params["tickers"]) == []
        assert json.loads(params["errors"]) == {}

    def test_large_checkpoint_data(self, checkpoint_manager, mock_engine):
        """save_checkpoint handles large lists of tickers."""
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn

        # Simulate 500 processed tickers
        large_ticker_list = [f"TICK{i}" for i in range(500)]
        large_errors = {f"ERR{i}": f"Error {i}" for i in range(50)}

        checkpoint_manager.save_checkpoint(
            run_id="large_test",
            last_index=499,
            processed_tickers=large_ticker_list,
            errors=large_errors,
        )

        call_args = mock_conn.execute.call_args
        params = call_args[0][1]

        parsed_tickers = json.loads(params["tickers"])
        parsed_errors = json.loads(params["errors"])

        assert len(parsed_tickers) == 500
        assert len(parsed_errors) == 50
        assert parsed_tickers[0] == "TICK0"
        assert parsed_tickers[499] == "TICK499"


class TestCheckpointManagerSQLQueries:
    """Tests to verify SQL query structure."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        return MagicMock()

    @pytest.fixture
    def checkpoint_manager(self, mock_engine):
        """Create a CheckpointManager with mocked engine."""
        return CheckpointManager(mock_engine)

    def test_get_checkpoint_uses_parameterized_query(self, checkpoint_manager, mock_engine):
        """get_checkpoint uses parameterized query to prevent SQL injection."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        # Attempt SQL injection in run_id
        malicious_id = "test'; DROP TABLE enrichment_checkpoints; --"
        checkpoint_manager.get_checkpoint(malicious_id)

        call_args = mock_conn.execute.call_args
        params = call_args[0][1]

        # Verify parameter is passed separately, not interpolated
        assert params["run_id"] == malicious_id
        sql_text = str(call_args[0][0])
        assert ":run_id" in sql_text

    def test_save_checkpoint_uses_parameterized_query(self, checkpoint_manager, mock_engine):
        """save_checkpoint uses parameterized query to prevent SQL injection."""
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn

        checkpoint_manager.save_checkpoint(
            run_id="test",
            last_index=1,
            processed_tickers=["AAPL"],
            errors={},
        )

        call_args = mock_conn.execute.call_args
        sql_text = str(call_args[0][0])

        # Verify parameterized placeholders
        assert ":run_id" in sql_text
        assert ":idx" in sql_text
        assert ":tickers" in sql_text
        assert ":errors" in sql_text

    def test_clear_checkpoint_uses_parameterized_query(self, checkpoint_manager, mock_engine):
        """clear_checkpoint uses parameterized query to prevent SQL injection."""
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn

        checkpoint_manager.clear_checkpoint("test")

        call_args = mock_conn.execute.call_args
        sql_text = str(call_args[0][0])

        assert ":run_id" in sql_text
