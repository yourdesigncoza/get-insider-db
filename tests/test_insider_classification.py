"""
Tests for insider classification logic.
"""

from src.insider_classification import (
    classify_insider_by_rules,
    normalize_insider_name,
    ENTITY_FUND,
    ENTITY_PERSON,
    RULE_CONFIDENCE_FUND,
    RULE_CONFIDENCE_PERSON,
)


def test_normalize_insider_name():
    assert normalize_insider_name("  John   Doe  ") == "JOHN DOE"
    assert normalize_insider_name("Acme Corp.") == "ACME CORP."
    assert normalize_insider_name("") == ""


def test_classify_insider_by_rules_fund():
    # Test cases that should be classified as funds
    fund_names = [
        "ACME CAPITAL LLC",
        "GLOBAL GROWTH FUND L.P.",
        "VENTURE PARTNERS II",
        "FAMILY TRUST",
    ]

    for name in fund_names:
        result = classify_insider_by_rules(name, None)
        assert result["entity_type"] == ENTITY_FUND, f"Failed for {name}"
        assert result["is_fund_like"] is True
        assert result["confidence"] == RULE_CONFIDENCE_FUND


def test_classify_insider_by_rules_person():
    # Test cases that should be classified as persons
    person_names = [
        "John Doe",
        "Smith Jane",
        "O'Connor Michael",
    ]

    for name in person_names:
        result = classify_insider_by_rules(name, None)
        assert result["entity_type"] == ENTITY_PERSON, f"Failed for {name}"
        assert result["is_fund_like"] is False
        assert result["confidence"] == RULE_CONFIDENCE_PERSON


def test_classify_insider_officer_flag():
    # Test that officer/director flags boost confidence for persons
    name = "Alice Director"
    flags = {"is_director": True}
    result = classify_insider_by_rules(name, None, flags=flags)
    
    assert result["entity_type"] == ENTITY_PERSON
    assert result["confidence"] >= 0.7  # Should be boosted from 0.6
    assert "Flagged as officer/director" in result["rationale"]


def test_classify_insider_title_boost():
    # Test that officer title boosts confidence or adds rationale
    name = "Bob Executive"
    title = "Chief Executive Officer"
    result = classify_insider_by_rules(name, title)
    
    assert result["entity_type"] == ENTITY_PERSON
    assert "Officer title present" in result["rationale"]
