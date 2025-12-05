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
) -> float:
    """
    Compute a composite score for a cluster window.

    Heuristics:
      - Higher role_score is good.
      - More people is good.
      - Larger total_value_usd is good (log scaled to reduce outlier dominance).
      - More funds relative to all_insiders is penalized.
    """
    all_insiders = max(int(all_insiders or 0), 1)
    people = int(people or 0)
    role_score = int(role_score or 0)
    funds = int(funds or 0)
    total_value_usd = float(total_value_usd or 0.0)

    value_score = math.log10(total_value_usd + 1.0) if total_value_usd > 0 else 0.0
    fund_ratio = funds / all_insiders

    w_role = 2.0
    w_people = 1.0
    w_value = 2.0
    w_fund = 2.0  # penalty

    score = (
        w_role * role_score
        + w_people * people
        + w_value * value_score
        - w_fund * fund_ratio
    )
    return score
