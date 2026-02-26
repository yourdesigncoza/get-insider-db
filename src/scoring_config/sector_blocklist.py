"""
Sector blocklist configuration — maps Edenfintech avoid-list categories to SIC code ranges.

Single source of truth for blocked industries. Each entry has:
- sic_ranges: list of (start, end) tuples (inclusive)
- reason: human-readable rationale for blocking

Unknown SIC policy: permissive — if a CIK has no sector_lookup row, the cluster passes through.
"""

from __future__ import annotations

SECTOR_BLOCKLIST: dict[str, dict] = {
    "airlines": {
        "sic_ranges": [(4512, 4512)],
        "reason": "Capital-destructive, razor-thin margins",
    },
    "banks": {
        "sic_ranges": [(6000, 6099)],
        "reason": "Complex balance sheets",
    },
    "biotech": {
        "sic_ranges": [(2830, 2836), (8731, 8731)],
        "reason": "Binary outcomes",
    },
    "car_manufacturers": {
        "sic_ranges": [(3711, 3711), (3713, 3713)],
        "reason": "Cyclical, capital-intensive",
    },
    "insurance": {
        "sic_ranges": [(6300, 6399), (6411, 6411)],
        "reason": "Complex float/reserves",
    },
    "marine_freight": {
        "sic_ranges": [(4400, 4499)],
        "reason": "Volatile, commodity-driven",
    },
    "precious_metal_miners": {
        "sic_ranges": [(1040, 1049)],
        "reason": "Commodity prices uncontrollable",
    },
    "restaurants": {
        "sic_ranges": [(5812, 5812)],
        "reason": "High failure, low margins",
    },
    "tobacco": {
        "sic_ranges": [(2100, 2199)],
        "reason": "Secular decline",
    },
    "textiles": {
        "sic_ranges": [(2200, 2299)],
        "reason": "Race-to-bottom pricing",
    },
    "trading_firms": {
        "sic_ranges": [(6200, 6211)],
        "reason": "Opaque, unpredictable",
    },
    "pure_ai": {
        "sic_ranges": [],
        "reason": "Too speculative",
    },
    "most_software": {
        "sic_ranges": [(7371, 7379)],
        "reason": "Often overvalued",
    },
}


def get_blocked_sic_codes() -> set[int]:
    """Flatten all SIC ranges into a set of blocked codes."""
    codes: set[int] = set()
    for entry in SECTOR_BLOCKLIST.values():
        for start, end in entry.get("sic_ranges", []):
            codes.update(range(start, end + 1))
    return codes


def is_sic_blocked(sic_code: int) -> tuple[bool, str | None]:
    """Check if a SIC code falls within any blocked sector.

    Returns (blocked, reason) — reason is None when not blocked.
    """
    for category, entry in SECTOR_BLOCKLIST.items():
        for start, end in entry.get("sic_ranges", []):
            if start <= sic_code <= end:
                return True, f"{category}: {entry['reason']}"
    return False, None
