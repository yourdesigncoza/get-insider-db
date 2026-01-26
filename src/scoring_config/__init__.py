"""
Configuration package for get-insider-db.

Centralizes scoring weights, thresholds, and other tunable parameters.
"""

from src.scoring_config.scoring_weights import (
    ROLE_WEIGHTS,
    SCORING_WEIGHTS,
    CLUSTER_THRESHOLDS,
    RoleWeights,
    ClusterScoringWeights,
    ClusterThresholds,
)

__all__ = [
    "ROLE_WEIGHTS",
    "SCORING_WEIGHTS",
    "CLUSTER_THRESHOLDS",
    "RoleWeights",
    "ClusterScoringWeights",
    "ClusterThresholds",
]
