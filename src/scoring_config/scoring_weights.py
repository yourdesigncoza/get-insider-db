"""
Centralized scoring weights and thresholds for cluster detection and scoring.

This module provides a single source of truth for all tunable parameters
used in insider trading cluster detection and scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class RoleWeights:
    """
    Weights for insider roles based on officer titles.

    Higher weights indicate roles with more conviction signal value.
    Scale: 0-4 (integer)

    Rationale:
    - CFO/GC (4): Financial/legal officers rarely buy for PR; highest conviction
    - VP/COO (3): Senior operators with deep business knowledge
    - CEO (2): Sometimes buy for PR/signaling; moderate conviction
    - Director/Officer (1): Baseline insider with board visibility
    """
    # Finance / Legal (highest conviction)
    CFO: int = 4
    CHIEF_FINANCIAL_OFFICER: int = 4
    GENERAL_COUNSEL: int = 4
    CHIEF_LEGAL_OFFICER: int = 4
    CHIEF_COMPLIANCE_OFFICER: int = 3

    # Operations (high conviction)
    COO: int = 3
    CHIEF_OPERATING_OFFICER: int = 3
    CHIEF_PORTFOLIO_MANAGER: int = 3

    # VP level (high conviction)
    VP: int = 3
    VICE_PRESIDENT: int = 3
    SVP: int = 3
    EVP: int = 3
    SENIOR_VICE_PRESIDENT: int = 3
    EXECUTIVE_VICE_PRESIDENT: int = 3
    CMO: int = 3
    CHIEF_MARKETING_OFFICER: int = 3

    # Executive (moderate conviction - sometimes buy for PR)
    CEO: int = 2
    CHIEF_EXECUTIVE_OFFICER: int = 2
    PRESIDENT: int = 2

    # Board/Generic (baseline conviction)
    OFFICER: int = 1
    DIRECTOR: int = 1

    def as_dict(self) -> Dict[str, int]:
        """Return weights as dictionary for lookup."""
        return {
            k.replace("_", " "): v
            for k, v in self.__dict__.items()
            if not k.startswith("_")
        }


@dataclass
class ClusterScoringWeights:
    """
    Weights for the compute_cluster_score() formula.

    The composite score combines multiple factors:
    - Positive factors: role_score, people count, dollar value, % stake increase
    - Negative factors: fund ratio, filing delay, sale activity

    Formula:
        raw_score = w_role * role_score
                  + w_people * people
                  + w_value * log10(total_value + 1)
                  - w_fund * fund_ratio
                  + w_percent_change * avg_percent_change
                  + w_days_to_file * avg_days_to_file
                  + w_sale_to_purchase_ratio * avg_sale_to_purchase_ratio

        final_score = 100 * (1 - exp(-raw_score / saturation_k))
    """
    # Positive weights
    w_role: float = 2.0          # Role-weighted insider quality
    w_people: float = 1.0        # Number of unique insiders
    w_value: float = 3.0         # Log-scaled dollar value
    w_percent_change: float = 5.0  # Average stake increase (high conviction signal)

    # Penalty weights (applied as negatives)
    w_fund: float = 2.0          # Penalty for fund-like entities
    w_days_to_file: float = -0.5  # Penalty per day of filing delay
    w_sale_to_purchase_ratio: float = -3.0  # Penalty for selling behavior

    # Normalization
    saturation_k: float = 65.0   # Exponential saturation constant

    # Market-cap adjustment (post-enrichment)
    w_mcap_rel: float = 50.0     # Bonus per 1% of market cap purchased


@dataclass
class ClusterThresholds:
    """
    Default thresholds for cluster detection and filtering.
    """
    # Cluster detection
    window_days: int = 10
    min_unique_insiders: int = 3
    min_total_value_usd: float = 500_000.0
    min_trade_value_usd: float = 50_000.0

    # Scoring filters
    min_cluster_score: float = 60.0
    min_role_score: int = 0
    max_fund_ratio: float = 0.25

    # Feature calculation
    lookback_days_for_features: int = 120

    # Ranking filters (post-enrichment)
    min_mcap_millions: float = 50.0
    min_conviction_bps: float = 5.0


# Singleton instances - import these for use
ROLE_WEIGHTS = RoleWeights()
SCORING_WEIGHTS = ClusterScoringWeights()
CLUSTER_THRESHOLDS = ClusterThresholds()
