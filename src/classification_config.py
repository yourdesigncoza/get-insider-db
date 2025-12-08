"""
Configuration for insider classification, including hardcoded tokens and thresholds.
"""

# Tokens used to classify entities as 'fund-like'
FUND_TOKENS = [
    " L.P",
    " LP",
    " LLP",
    " L.L.P",
    " LLC",
    " L.L.C",
    " CORP",
    " CORPORATION",
    " INC",
    " INC.",
    " LIMITED",
    " LTD",
    " PLC",
    " FUND",
    " CAPITAL",
    " PARTNERS",
    " ADVISORS",
    " INVESTMENT",
    " INVESTORS",
    " ASSET MANAGEMENT",
    " MANAGEMENT LP",
    " HOLDINGS",
    " TRUST",
    " FOUNDATION",
]

# Confidence thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.8
RULE_CONFIDENCE_FUND = 0.8
RULE_CONFIDENCE_PERSON = 0.6

# Entity type constants
ENTITY_PERSON = "person"
ENTITY_FUND = "fund_or_investment_vehicle"
ENTITY_OPERATING_CO = "operating_company"
ENTITY_TRUST = "trust_or_foundation"
ENTITY_OTHER = "other"
ENTITY_UNKNOWN = "unknown"
