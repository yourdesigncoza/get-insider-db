from __future__ import annotations

from typing import Dict, Optional

import pandas as pd


def best_qualifying_window_indices(
    revealed_df: pd.DataFrame,
    *,
    window_interval_days: int,
    min_insiders: int,
    min_total_value: float,
) -> Optional[tuple[int, int]]:
    """
    Find the best (highest total_value) qualifying transaction-date window in revealed_df.

    revealed_df is expected to contain columns:
      - transaction_date (Timestamp)
      - normalized_name (str)
      - total_value (float)

    Returns (left_index, right_index) indices into revealed_df sorted by transaction_date.
    """
    if revealed_df.empty:
        return None

    ordered = revealed_df.sort_values("transaction_date").reset_index(drop=True)
    tdates = ordered["transaction_date"].tolist()
    insiders = ordered["normalized_name"].tolist()
    values = ordered["total_value"].astype(float).tolist()

    left = 0
    insider_counts: Dict[str, int] = {}
    unique_insiders = 0
    total_value = 0.0

    best: Optional[tuple[float, int, pd.Timestamp, int, int]] = None
    for right in range(len(ordered)):
        insider_r = insiders[right]
        prev = insider_counts.get(insider_r, 0)
        insider_counts[insider_r] = prev + 1
        if prev == 0:
            unique_insiders += 1
        total_value += values[right]

        while left <= right and (tdates[right] - tdates[left]).days > window_interval_days:
            insider_l = insiders[left]
            insider_counts[insider_l] -= 1
            if insider_counts[insider_l] <= 0:
                insider_counts.pop(insider_l, None)
                unique_insiders -= 1
            total_value -= values[left]
            left += 1

        if unique_insiders < min_insiders or total_value < min_total_value:
            continue

        candidate = (float(total_value), int(unique_insiders), pd.Timestamp(tdates[right]), left, right)
        if best is None or candidate[:3] > best[:3]:
            best = candidate

    if best is None:
        return None
    return best[3], best[4]
