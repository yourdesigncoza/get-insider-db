"""
Tests for AI classification infrastructure and fallback behavior.
"""

import os
import pytest

from src.llm.schemas import EntityType, InsiderClassification
from src.insider_classification import (
    classify_insider_with_ai,
    classify_insider_by_rules,
)


class TestLLMSchemas:
    """Test that LLM schemas are valid and behave correctly."""

    def test_entity_type_enum_values(self):
        """EntityType enum has all expected values."""
        expected_values = {
            "person",
            "fund_or_investment_vehicle",
            "operating_company",
            "trust_or_foundation",
            "other",
        }
        actual_values = {e.value for e in EntityType}
        assert actual_values == expected_values

    def test_insider_classification_valid(self):
        """InsiderClassification validates correct data."""
        classification = InsiderClassification(
            entity_type=EntityType.PERSON,
            is_fund_like=False,
            confidence=0.85,
            rationale="Individual human name pattern",
        )
        assert classification.entity_type == EntityType.PERSON
        assert classification.is_fund_like is False
        assert classification.confidence == 0.85
        assert classification.rationale == "Individual human name pattern"

    def test_insider_classification_confidence_bounds(self):
        """InsiderClassification enforces confidence bounds (0-1)."""
        # Valid boundary values
        low = InsiderClassification(
            entity_type=EntityType.PERSON,
            is_fund_like=False,
            confidence=0.0,
            rationale="Low confidence",
        )
        assert low.confidence == 0.0

        high = InsiderClassification(
            entity_type=EntityType.FUND,
            is_fund_like=True,
            confidence=1.0,
            rationale="High confidence",
        )
        assert high.confidence == 1.0

        # Invalid values should raise validation error
        with pytest.raises(Exception):  # Pydantic ValidationError
            InsiderClassification(
                entity_type=EntityType.PERSON,
                is_fund_like=False,
                confidence=1.5,  # Out of bounds
                rationale="Invalid",
            )

        with pytest.raises(Exception):
            InsiderClassification(
                entity_type=EntityType.PERSON,
                is_fund_like=False,
                confidence=-0.1,  # Out of bounds
                rationale="Invalid",
            )


class TestAIClassifierFallback:
    """Test fallback behavior when API is unavailable."""

    def test_fallback_without_api_key(self, monkeypatch):
        """classify_insider_with_ai falls back to rules when API key missing."""
        # Ensure API key is not set
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # Clear the cached client to force re-initialization
        from src.llm.client import get_llm_client
        get_llm_client.cache_clear()

        result = classify_insider_with_ai("BLACKROCK INC", None)

        # Should fall back to rules
        assert result["source"] == "rules"
        assert "AI fallback" in result["rationale"]
        assert "entity_type" in result
        assert "is_fund_like" in result
        assert "confidence" in result

    def test_fallback_result_has_all_fields(self, monkeypatch):
        """Fallback result contains all required fields."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        from src.llm.client import get_llm_client
        get_llm_client.cache_clear()

        result = classify_insider_with_ai("John Smith", "CEO")

        required_fields = {"entity_type", "is_fund_like", "source", "confidence", "rationale"}
        assert required_fields.issubset(result.keys())


class TestRuleBasedClassifier:
    """Test that rule-based classification still works correctly."""

    def test_fund_tokens_trigger_fund_classification(self):
        """Fund tokens in name trigger is_fund_like=True."""
        fund_names = [
            "BLACKROCK CAPITAL PARTNERS LP",
            "VANGUARD FUND LLC",
            "SEQUOIA CAPITAL",
            "ABC INVESTMENT ADVISORS",
            "FAMILY TRUST",
        ]
        for name in fund_names:
            result = classify_insider_by_rules(name, None)
            assert result["is_fund_like"] is True, f"Expected fund-like for: {name}"
            assert result["entity_type"] == "fund_or_investment_vehicle"
            assert result["source"] == "rules"

    def test_person_classification(self):
        """Individual names classify as person."""
        result = classify_insider_by_rules("JOHN SMITH", "CEO")
        assert result["entity_type"] == "person"
        assert result["is_fund_like"] is False
        assert result["source"] == "rules"

    def test_officer_flag_boosts_confidence(self):
        """Officer/director flags increase person confidence."""
        without_flags = classify_insider_by_rules("JANE DOE", None)
        with_flags = classify_insider_by_rules("JANE DOE", None, {"is_officer": True})

        assert with_flags["confidence"] >= without_flags["confidence"]

    def test_rules_result_always_has_rationale(self):
        """Rule-based results always include rationale."""
        result = classify_insider_by_rules("RANDOM NAME", None)
        assert "rationale" in result
        assert len(result["rationale"]) > 0
