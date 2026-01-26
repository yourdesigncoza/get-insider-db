"""
Role-based weighting for insiders based on officer titles and flags.

Weights are sourced from src.config.scoring_weights.ROLE_WEIGHTS.
"""

from __future__ import annotations

from typing import Optional

from src.scoring_config.scoring_weights import ROLE_WEIGHTS as _ROLE_WEIGHTS_CONFIG

# Export as dict for backward compatibility
ROLE_WEIGHTS: dict[str, int] = _ROLE_WEIGHTS_CONFIG.as_dict()


def compute_insider_role_weight(
    officer_title: Optional[str],
    is_director: bool,
    is_officer: bool,
) -> int:
    """
    Determine an insider's role weight based on their title/flags.

    Higher weights indicate roles with more conviction signal value:
    - CFO/GC: 4 (highest - financial/legal officers rarely buy for PR)
    - COO/VP: 3 (senior operators with deep business knowledge)
    - CEO: 2 (sometimes buy for PR/signaling)
    - Director/Officer: 1 (baseline insider)
    """
    title_u = (officer_title or "").upper()
    max_weight = 0
    for key, weight in ROLE_WEIGHTS.items():
        if key in title_u:
            max_weight = max(max_weight, weight)
    if max_weight == 0:
        if is_officer:
            return ROLE_WEIGHTS.get("OFFICER", 1)
        if is_director:
            return ROLE_WEIGHTS.get("DIRECTOR", 1)
        return 0
    return max_weight
