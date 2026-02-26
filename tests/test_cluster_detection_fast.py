import pytest
from unittest.mock import MagicMock
from src.services.cluster_detection_fast import load_sector_map


def test_load_sector_map_returns_dict():
    """load_sector_map returns {issuer_cik: {sic_code, sic_description}}."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = lambda s: mock_conn
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    # Simulate DB rows: (issuer_cik, sic_code, sic_description)
    mock_conn.execute.return_value.fetchall.return_value = [
        ("0001234567", "4911", "Electric Services"),
        ("0007654321", "7372", "Prepackaged Software"),
    ]

    result = load_sector_map(mock_engine)

    assert result["0001234567"]["sic_code"] == "4911"
    assert result["0001234567"]["sic_description"] == "Electric Services"
    assert result["0007654321"]["sic_description"] == "Prepackaged Software"
    assert "9999999999" not in result


def test_load_sector_map_empty():
    """load_sector_map returns empty dict when table is empty."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = lambda s: mock_conn
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.fetchall.return_value = []

    result = load_sector_map(mock_engine)
    assert result == {}
