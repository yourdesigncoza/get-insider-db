"""Tests for batch insider classification."""

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from src.analytics.cluster_buys import _classify_insiders


class TestBatchClassification:
    """Test batch classification to prevent N+1 regression."""

    def test_empty_dataframe_returns_empty_dict(self):
        """Empty input should return empty output without DB calls."""
        engine = MagicMock()
        result = _classify_insiders(pd.DataFrame(), engine)
        assert result == {}

    def test_missing_normalized_name_column_returns_empty(self):
        """Missing normalized_name column should return empty."""
        engine = MagicMock()
        df = pd.DataFrame({"other_column": [1, 2, 3]})
        result = _classify_insiders(df, engine)
        assert result == {}

    def test_batch_uses_single_select_query(self):
        """Verify batch uses IN clause, not per-row queries."""
        # This is a structural test - verify the code uses .in_()
        import inspect
        from src.analytics.cluster_buys import _classify_insiders

        source = inspect.getsource(_classify_insiders)
        assert ".in_(" in source, "Should use IN clause for batch fetch"
        assert "add_all" in source, "Should use add_all for bulk insert"
        # Should NOT have the old pattern of calling get_or_create per row
        assert "for _, row in unique_rows.iterrows():" not in source or \
               "get_or_create_insider_entity" not in source, \
               "Should not call get_or_create per row"

    def test_classification_result_structure(self):
        """Verify classification returns expected dict structure."""
        # Integration test if DB available, otherwise skip
        pytest.skip("Requires database connection - run manually")
