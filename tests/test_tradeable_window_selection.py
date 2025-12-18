import pandas as pd

from src.analytics.window_detection import best_qualifying_window_indices


def _df(rows):
    df = pd.DataFrame(rows)
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    return df


def test_best_window_finds_qualifying_cluster():
    revealed = _df(
        [
            {"transaction_date": "2024-01-01", "normalized_name": "a", "total_value": 100.0, "shares": 1.0},
            {"transaction_date": "2024-01-02", "normalized_name": "b", "total_value": 200.0, "shares": 1.0},
            {"transaction_date": "2024-01-03", "normalized_name": "c", "total_value": 300.0, "shares": 1.0},
        ]
    )
    idx = best_qualifying_window_indices(
        revealed,
        window_interval_days=9,
        min_insiders=3,
        min_total_value=500.0,
    )
    assert idx == (0, 2)


def test_best_window_respects_transaction_date_window():
    revealed = _df(
        [
            {"transaction_date": "2024-01-01", "normalized_name": "a", "total_value": 300.0, "shares": 1.0},
            {"transaction_date": "2024-01-20", "normalized_name": "b", "total_value": 300.0, "shares": 1.0},
            {"transaction_date": "2024-01-21", "normalized_name": "c", "total_value": 300.0, "shares": 1.0},
        ]
    )
    # With a 10-day window (interval=9), Jan 1 cannot be in the same cluster as Jan 20/21.
    idx = best_qualifying_window_indices(
        revealed,
        window_interval_days=9,
        min_insiders=3,
        min_total_value=500.0,
    )
    assert idx is None


def test_best_window_prefers_higher_total_value():
    revealed = _df(
        [
            {"transaction_date": "2024-01-01", "normalized_name": "a", "total_value": 100.0, "shares": 1.0},
            {"transaction_date": "2024-01-02", "normalized_name": "b", "total_value": 100.0, "shares": 1.0},
            {"transaction_date": "2024-01-03", "normalized_name": "c", "total_value": 100.0, "shares": 1.0},
            {"transaction_date": "2024-01-04", "normalized_name": "d", "total_value": 1000.0, "shares": 1.0},
        ]
    )
    # Multiple qualifying windows exist; the best is the one with highest total_value.
    idx = best_qualifying_window_indices(
        revealed,
        window_interval_days=9,
        min_insiders=3,
        min_total_value=200.0,
    )
    assert idx == (0, 3)
