"""
Composite cluster scoring for insider buy windows.
"""

from __future__ import annotations

import math


def compute_cluster_score(
    people: int,
    role_score: int,
    total_value_usd: float,
    funds: int,
    all_insiders: int,
    avg_percent_change: float,
    avg_days_to_file: float,
    avg_sale_to_purchase_ratio: float,
) -> float:
    """
    Compute a composite score for a cluster window.

    Heuristics:
      - Higher role_score is good.
      - More people is good.
      - Larger total_value_usd is good (log scaled to reduce outlier dominance).
      - More funds relative to all_insiders is penalized.
      - Higher avg_percent_change is good (insiders increasing their stake significantly).
      - Lower avg_days_to_file is good (faster filing suggests more conviction/urgency).
      - Lower avg_sale_to_purchase_ratio is good (more purchases relative to sales).
    """
    all_insiders = max(int(all_insiders or 0), 1)
    people = int(people or 0)
    role_score = int(role_score or 0)
    funds = int(funds or 0)
    total_value_usd = float(total_value_usd or 0.0)
    avg_percent_change = float(avg_percent_change or 0.0)
    avg_days_to_file = float(avg_days_to_file or 0.0)
    avg_sale_to_purchase_ratio = float(avg_sale_to_purchase_ratio or 0.0)

    value_score = math.log10(total_value_usd + 1.0) if total_value_usd > 0 else 0.0
    fund_ratio = funds / all_insiders

    w_role = 2.0
    w_people = 1.0
    w_value = 2.0
    w_fund = 2.0  # penalty
    w_percent_change = 5.0
    w_days_to_file = -0.5  # Penalty for more days to file
    w_sale_to_purchase_ratio = -3.0 # Penalty for higher sale-to-purchase ratio

    raw_score = (
        w_role * role_score
        + w_people * people
        + w_value * value_score
        - w_fund * fund_ratio
        + w_percent_change * avg_percent_change
        + w_days_to_file * avg_days_to_file
        + w_sale_to_purchase_ratio * avg_sale_to_purchase_ratio
    )

    # Normalize to 0-100 using an exponential saturation curve.
    # We want a raw score of ~60 (the common filter cutoff) to map to roughly 60
    # to preserve filter compatibility, while compressing high outliers (e.g. 100+)
    # into the 80-100 range.
    # Formula: f(x) = 100 * (1 - exp(-x / K))
    # Solving 60 = 100 * (1 - exp(-60 / K)) yields K approx 65.
    if raw_score <= 0:
        return 0.0

    k = 65.0
    final_score = 100.0 * (1.0 - math.exp(-raw_score / k))
    return final_score
