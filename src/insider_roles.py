"""
Role-based weighting for insiders based on officer titles and flags.
"""

from __future__ import annotations

from typing import Optional

ROLE_WEIGHTS: dict[str, int] = {
    "CFO": 4,
    "CHIEF FINANCIAL OFFICER": 4,
    "GENERAL COUNSEL": 4,
    "CHIEF LEGAL OFFICER": 4,
    "COO": 3,
    "CHIEF OPERATING OFFICER": 3,
    "VP": 3,
    "VICE PRESIDENT": 3,
    "SVP": 3,
    "EVP": 3,
    "SENIOR VICE PRESIDENT": 3,
    "EXECUTIVE VICE PRESIDENT": 3,
    "CMO": 3,
    "CHIEF MARKETING OFFICER": 3,
    "CHIEF COMPLIANCE OFFICER": 3,
    "CHIEF PORTFOLIO MANAGER": 3,
    "CEO": 2,
    "CHIEF EXECUTIVE OFFICER": 2,
    "PRESIDENT": 2,
    "OFFICER": 1,
    "DIRECTOR": 1,
}


def compute_insider_role_weight(
    officer_title: Optional[str],
    is_director: bool,
    is_officer: bool,
) -> int:
    """
    Determine an insider's role weight based on their title/flags.
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
