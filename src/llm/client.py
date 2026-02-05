"""
Anthropic client setup with Instructor for structured output.

Provides singleton client for LLM-powered classification.
"""

import os
from functools import lru_cache

import instructor
from anthropic import Anthropic


@lru_cache(maxsize=1)
def get_llm_client():
    """
    Get singleton Instructor-wrapped Anthropic client.

    Returns:
        Instructor-wrapped Anthropic client for structured output.

    Raises:
        ValueError: If ANTHROPIC_API_KEY environment variable is not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable required")
    return instructor.from_anthropic(Anthropic(api_key=api_key))
