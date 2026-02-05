"""
LLM integration module for AI-powered classification.

Provides Instructor-wrapped Anthropic client for structured output.
"""

from src.llm.client import get_llm_client
from src.llm.schemas import EntityType, InsiderClassification

__all__ = ["get_llm_client", "EntityType", "InsiderClassification"]
