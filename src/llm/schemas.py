"""
Pydantic models for LLM responses.

Defines structured output schemas for insider classification.
"""

from enum import Enum

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    """Entity type classification for SEC Form 4 insiders."""

    PERSON = "person"
    FUND = "fund_or_investment_vehicle"
    OPERATING_CO = "operating_company"
    TRUST = "trust_or_foundation"
    OTHER = "other"


class InsiderClassification(BaseModel):
    """Structured classification result from LLM."""

    entity_type: EntityType = Field(description="Primary entity type")
    is_fund_like: bool = Field(
        description="True if entity behaves like an investment fund"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Classification confidence (0-1)"
    )
    rationale: str = Field(description="Brief explanation for classification")
