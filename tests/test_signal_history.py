"""
Unit tests for SignalHistoryRecorder.

Tests cover event recording, validation, history retrieval, filtering,
and JSONB serialization. Uses a mock engine to avoid database dependency.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch
import json

import pytest

from src.audit.signal_history import (
    SignalHistoryRecorder,
    EVENT_TYPES,
    ACTORS,
)


# -------------------------------------------------------------------------
# FIXTURES
# -------------------------------------------------------------------------


@pytest.fixture
def mock_engine():
    """Create a mock SQLAlchemy engine."""
    engine = MagicMock()
    return engine


@pytest.fixture
def recorder(mock_engine):
    """Create a SignalHistoryRecorder with mock engine."""
    return SignalHistoryRecorder(mock_engine)


@pytest.fixture
def mock_connection():
    """Create a mock connection with execute capability."""
    conn = MagicMock()
    return conn


# -------------------------------------------------------------------------
# VALIDATION TESTS
# -------------------------------------------------------------------------


class TestEventTypeValidation:
    """Tests for event_type validation."""

    def test_valid_event_types(self, recorder, mock_engine):
        """All valid event types should be accepted."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_conn.execute.return_value = mock_result
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        for event_type in EVENT_TYPES:
            record_id = recorder.record_event(
                cluster_id=1,
                event_type=event_type,
                changed_by="system",
            )
            assert record_id == 1

    def test_invalid_event_type_raises_error(self, recorder):
        """Invalid event_type should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            recorder.record_event(
                cluster_id=1,
                event_type="invalid_type",
                changed_by="system",
            )
        assert "Invalid event_type" in str(exc_info.value)
        assert "invalid_type" in str(exc_info.value)

    def test_invalid_event_type_filter_raises_error(self, recorder):
        """Invalid event_type filter should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            recorder.get_recent_events(event_type="bad_filter")
        assert "Invalid event_type filter" in str(exc_info.value)


class TestChangedByValidation:
    """Tests for changed_by validation."""

    def test_valid_actors(self, recorder, mock_engine):
        """All valid actors should be accepted."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_conn.execute.return_value = mock_result
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        for actor in ACTORS:
            record_id = recorder.record_event(
                cluster_id=1,
                event_type="created",
                changed_by=actor,
            )
            assert record_id == 1

    def test_invalid_actor_raises_error(self, recorder):
        """Invalid changed_by should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            recorder.record_event(
                cluster_id=1,
                event_type="created",
                changed_by="unknown_actor",
            )
        assert "Invalid changed_by" in str(exc_info.value)
        assert "unknown_actor" in str(exc_info.value)

    def test_invalid_actor_filter_raises_error(self, recorder):
        """Invalid changed_by filter should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            recorder.get_recent_events(changed_by="bad_actor")
        assert "Invalid changed_by filter" in str(exc_info.value)


# -------------------------------------------------------------------------
# RECORD EVENT TESTS
# -------------------------------------------------------------------------


class TestRecordEvent:
    """Tests for record_event method."""

    def test_record_event_returns_id(self, recorder, mock_engine):
        """record_event should return the created record ID."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (42,)
        mock_conn.execute.return_value = mock_result
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        record_id = recorder.record_event(
            cluster_id=123,
            event_type="created",
            changed_by="system",
        )
        assert record_id == 42

    def test_record_event_passes_correct_parameters(self, recorder, mock_engine):
        """record_event should pass correct parameters to SQL."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_conn.execute.return_value = mock_result
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        recorder.record_event(
            cluster_id=999,
            event_type="status_changed",
            changed_by="decay_job",
            old_values={"status": "active"},
            new_values={"status": "decayed"},
            reason="Expired after 30 days",
        )

        # Verify execute was called
        assert mock_conn.execute.called
        call_args = mock_conn.execute.call_args
        params = call_args[0][1]  # Second positional arg is params dict

        assert params["cid"] == 999
        assert params["event"] == "status_changed"
        assert params["by"] == "decay_job"
        assert params["old"] == '{"status": "active"}'
        assert params["new"] == '{"status": "decayed"}'
        assert params["reason"] == "Expired after 30 days"

    def test_record_event_with_null_values(self, recorder, mock_engine):
        """record_event should handle null old_values/new_values."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_conn.execute.return_value = mock_result
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        recorder.record_event(
            cluster_id=1,
            event_type="created",
            changed_by="system",
            old_values=None,
            new_values=None,
        )

        call_args = mock_conn.execute.call_args
        params = call_args[0][1]
        assert params["old"] is None
        assert params["new"] is None


# -------------------------------------------------------------------------
# GET HISTORY TESTS
# -------------------------------------------------------------------------


class TestGetHistory:
    """Tests for get_history method."""

    def test_get_history_returns_chronological_order(self, recorder, mock_engine):
        """get_history should return events in chronological order."""
        mock_conn = MagicMock()
        mock_rows = [
            (1, "created", "system", None, {"status": "active"}, None, datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)),
            (2, "enriched", "enrichment", None, {"price": 100}, None, datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)),
            (3, "status_changed", "decay_job", {"status": "active"}, {"status": "decayed"}, "Expired", datetime(2024, 2, 1, 10, 0, tzinfo=timezone.utc)),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        history = recorder.get_history(cluster_id=123)

        assert len(history) == 3
        assert history[0]["id"] == 1
        assert history[0]["event_type"] == "created"
        assert history[1]["id"] == 2
        assert history[1]["event_type"] == "enriched"
        assert history[2]["id"] == 3
        assert history[2]["event_type"] == "status_changed"
        assert history[2]["reason"] == "Expired"

    def test_get_history_empty_for_nonexistent_cluster(self, recorder, mock_engine):
        """get_history should return empty list for non-existent cluster."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        history = recorder.get_history(cluster_id=99999)
        assert history == []

    def test_get_history_preserves_jsonb_values(self, recorder, mock_engine):
        """get_history should preserve JSONB values correctly."""
        complex_values = {"score": 75.5, "insiders": ["CEO", "CFO"], "meta": {"source": "test"}}
        mock_conn = MagicMock()
        mock_rows = [
            (1, "score_updated", "system", {"score": 50}, complex_values, None, datetime(2024, 1, 1, tzinfo=timezone.utc)),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        history = recorder.get_history(cluster_id=1)

        assert history[0]["old_values"] == {"score": 50}
        assert history[0]["new_values"] == complex_values
        assert history[0]["new_values"]["insiders"] == ["CEO", "CFO"]


# -------------------------------------------------------------------------
# GET RECENT EVENTS TESTS
# -------------------------------------------------------------------------


class TestGetRecentEvents:
    """Tests for get_recent_events method."""

    def test_get_recent_events_default_limit(self, recorder, mock_engine):
        """get_recent_events should use default limit of 100."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        recorder.get_recent_events()

        call_args = mock_conn.execute.call_args
        params = call_args[0][1]
        assert params["limit"] == 100

    def test_get_recent_events_filter_by_event_type(self, recorder, mock_engine):
        """get_recent_events should filter by event_type."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        recorder.get_recent_events(event_type="created")

        call_args = mock_conn.execute.call_args
        sql = str(call_args[0][0])
        params = call_args[0][1]
        assert "event_type = :event_type" in sql
        assert params["event_type"] == "created"

    def test_get_recent_events_filter_by_changed_by(self, recorder, mock_engine):
        """get_recent_events should filter by changed_by."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        recorder.get_recent_events(changed_by="enrichment")

        call_args = mock_conn.execute.call_args
        sql = str(call_args[0][0])
        params = call_args[0][1]
        assert "changed_by = :changed_by" in sql
        assert params["changed_by"] == "enrichment"

    def test_get_recent_events_combined_filters(self, recorder, mock_engine):
        """get_recent_events should combine multiple filters."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        recorder.get_recent_events(event_type="enriched", changed_by="enrichment", limit=50)

        call_args = mock_conn.execute.call_args
        sql = str(call_args[0][0])
        params = call_args[0][1]
        assert "event_type = :event_type" in sql
        assert "changed_by = :changed_by" in sql
        assert params["event_type"] == "enriched"
        assert params["changed_by"] == "enrichment"
        assert params["limit"] == 50

    def test_get_recent_events_respects_limit(self, recorder, mock_engine):
        """get_recent_events should respect custom limit."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        recorder.get_recent_events(limit=25)

        call_args = mock_conn.execute.call_args
        params = call_args[0][1]
        assert params["limit"] == 25

    def test_get_recent_events_includes_cluster_id(self, recorder, mock_engine):
        """get_recent_events should include cluster_id in results."""
        mock_conn = MagicMock()
        mock_rows = [
            (1, 100, "created", "system", None, {"status": "active"}, None, datetime(2024, 1, 1, tzinfo=timezone.utc)),
            (2, 200, "created", "system", None, {"status": "active"}, None, datetime(2024, 1, 2, tzinfo=timezone.utc)),
        ]
        mock_conn.execute.return_value.fetchall.return_value = mock_rows
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        events = recorder.get_recent_events()

        assert len(events) == 2
        assert events[0]["cluster_id"] == 100
        assert events[1]["cluster_id"] == 200


# -------------------------------------------------------------------------
# APPEND-ONLY DESIGN TESTS
# -------------------------------------------------------------------------


class TestAppendOnlyDesign:
    """Tests to verify append-only design."""

    def test_no_update_method(self, recorder):
        """SignalHistoryRecorder should not have update method."""
        assert not hasattr(recorder, "update_event")
        assert not hasattr(recorder, "update")
        assert not hasattr(recorder, "modify")

    def test_no_delete_method(self, recorder):
        """SignalHistoryRecorder should not have delete method."""
        assert not hasattr(recorder, "delete_event")
        assert not hasattr(recorder, "delete")
        assert not hasattr(recorder, "remove")

    def test_only_read_and_append_methods(self, recorder):
        """SignalHistoryRecorder should only have read and append methods."""
        public_methods = [m for m in dir(recorder) if not m.startswith("_")]
        # Should only have: record_event, get_history, get_recent_events
        assert "record_event" in public_methods
        assert "get_history" in public_methods
        assert "get_recent_events" in public_methods
        # No mutation methods
        for method in public_methods:
            assert "update" not in method.lower()
            assert "delete" not in method.lower()
            assert "remove" not in method.lower()
            assert "modify" not in method.lower()
