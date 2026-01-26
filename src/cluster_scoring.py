"""
Composite cluster scoring for insider buy windows.
"""

from __future__ import annotations

import math
from typing import Optional

from src.scoring_config.scoring_weights import SCORING_WEIGHTS as W


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

    Weights are sourced from src.config.scoring_weights.SCORING_WEIGHTS.
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

    raw_score = (
        W.w_role * role_score
        + W.w_people * people
        + W.w_value * value_score
        - W.w_fund * fund_ratio
        + W.w_percent_change * avg_percent_change
        + W.w_days_to_file * avg_days_to_file
        + W.w_sale_to_purchase_ratio * avg_sale_to_purchase_ratio
    )

    # Normalize to 0-100 using an exponential saturation curve.
    # We want a raw score of ~60 (the common filter cutoff) to map to roughly 60
    # to preserve filter compatibility, while compressing high outliers (e.g. 100+)
    # into the 80-100 range.
    # Formula: f(x) = 100 * (1 - exp(-x / K))
    # Solving 60 = 100 * (1 - exp(-60 / K)) yields K approx 65.
    if raw_score <= 0:
        return 0.0

    final_score = 100.0 * (1.0 - math.exp(-raw_score / W.saturation_k))
    return final_score


def compute_market_cap_adjusted_score(
    cluster_score: float,
    cluster_value_vs_mcap_pct: Optional[float],
) -> float:
    """
    Adjust cluster_score by market-cap relative conviction.

    This function applies a bonus to the cluster score based on how significant
    the cluster's total value is relative to the company's market cap.

    A $1M purchase is more significant for a $100M company (1%) than for a
    $10B company (0.01%). This adjustment rewards higher relative conviction.

    Args:
        cluster_score: The original cluster score (0-100)
        cluster_value_vs_mcap_pct: Cluster value as percentage of market cap
                                   (e.g., 0.5 means 0.5% of market cap)

    Returns:
        Adjusted score, capped at 100.0

    Example:
        - cluster_score=70, mcap_pct=0.1 (0.1%) → bonus=5, adjusted=75
        - cluster_score=70, mcap_pct=0.5 (0.5%) → bonus=25, adjusted=95
        - cluster_score=70, mcap_pct=1.0 (1.0%) → bonus=30 (capped), adjusted=100
    """
    if cluster_value_vs_mcap_pct is None or cluster_value_vs_mcap_pct <= 0:
        return cluster_score

    # Bonus based on relative conviction
    # w_mcap_rel=50 means 0.1% of mcap → +5 points, 0.5% → +25 points
    mcap_bonus = min(cluster_value_vs_mcap_pct * W.w_mcap_rel, 30.0)
    return min(cluster_score + mcap_bonus, 100.0)
