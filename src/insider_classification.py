"""
Insider entity classification helpers with a rule-based pass and AI fallback.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models import InsiderEntity, ensure_tables
from src.classification_config import (
    FUND_TOKENS,
    HIGH_CONFIDENCE_THRESHOLD,
    RULE_CONFIDENCE_FUND,
    RULE_CONFIDENCE_PERSON,
    ENTITY_PERSON,
    ENTITY_FUND,
    ENTITY_OPERATING_CO,
    ENTITY_TRUST,
    ENTITY_OTHER,
    ENTITY_UNKNOWN,
)
from src.llm.client import get_llm_client
from src.llm.schemas import InsiderClassification as LLMClassification


def normalize_insider_name(name: str) -> str:
    """
    Normalize an insider name for consistent lookups and storage.
    """
    return " ".join((name or "").upper().split())


def classify_insider_by_rules(
    name: str,
    officer_title: Optional[str],
    flags: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Rule-based classifier using name/title heuristics only.
    """
    flags = flags or {}
    name_u = (name or "").upper()
    title_u = (officer_title or "").upper()

    is_fund_like = any(token in name_u for token in FUND_TOKENS)
    entity_type = ENTITY_FUND if is_fund_like else ENTITY_PERSON
    confidence = RULE_CONFIDENCE_FUND if is_fund_like else RULE_CONFIDENCE_PERSON

    rationale_parts: list[str] = []
    if is_fund_like:
        hits = sorted({token.strip() for token in FUND_TOKENS if token in name_u})
        if hits:
            rationale_parts.append(f"Matched fund token(s): {', '.join(hits)}")
        else:
            rationale_parts.append("Name resembles fund or legal entity")
    elif flags.get("is_officer") or flags.get("is_director"):
        rationale_parts.append("Flagged as officer/director")
        confidence = max(confidence, 0.7)
    elif title_u:
        rationale_parts.append("Officer title present")
    else:
        rationale_parts.append("Defaulted to person; no fund markers detected")

    return {
        "entity_type": entity_type,
        "is_fund_like": is_fund_like,
        "source": "rules",
        "confidence": confidence,
        "rationale": "; ".join(rationale_parts),
    }


def classify_insider_with_ai(
    name: str,
    officer_title: Optional[str],
    flags: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    AI-powered classifier using Claude.

    Uses Claude Haiku for cost-effective classification with structured output
    via Instructor. Falls back to rule-based classification on API failure.

    Args:
        name: Insider entity name from SEC filing.
        officer_title: Officer title if available.
        flags: Optional dict with is_officer, is_director flags.

    Returns:
        Dict with entity_type, is_fund_like, source, confidence, rationale.
    """
    flags = flags or {}

    # Build context for LLM
    context_parts = [f"Name: {name}"]
    if officer_title:
        context_parts.append(f"Title: {officer_title}")
    if flags.get("is_officer"):
        context_parts.append("Flagged as officer")
    if flags.get("is_director"):
        context_parts.append("Flagged as director")

    try:
        client = get_llm_client()
        result: LLMClassification = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": f"""Classify this SEC Form 4 insider:

{chr(10).join(context_parts)}

Categories:
- person: Individual human (most officers/directors)
- fund_or_investment_vehicle: Investment funds (LP, Partners, Capital, Fund)
- operating_company: Business entities (Inc, Corp) NOT investment vehicles
- trust_or_foundation: Trusts, foundations
- other: None of the above

Return classification with confidence (0-1) and brief rationale.""",
                }
            ],
            response_model=LLMClassification,
        )

        return {
            "entity_type": result.entity_type.value,
            "is_fund_like": result.is_fund_like,
            "source": "ai",
            "confidence": result.confidence,
            "rationale": result.rationale,
        }
    except Exception as e:
        # Fallback to rules on any AI failure
        rules_result = classify_insider_by_rules(name, officer_title, flags)
        rules_result["rationale"] = f"AI fallback: {e}"
        return rules_result


def get_or_create_insider_entity(
    session: Session,
    insider_name: str,
    officer_title: Optional[str],
    flags: Optional[Dict[str, Any]] = None,
    insider_id: Optional[str] = None,
) -> InsiderEntity:
    """
    Fetch a cached classification or create one using rules with AI fallback.
    """
    ensure_tables(session.get_bind())

    normalized_name = normalize_insider_name(insider_name)
    if not normalized_name:
        raise ValueError("insider_name is required for classification")

    existing = (
        session.query(InsiderEntity)
        .filter(InsiderEntity.normalized_name == normalized_name)
        .one_or_none()
    )
    if existing:
        return existing

    flags = flags or {}
    rules_result = classify_insider_by_rules(insider_name, officer_title, flags)
    result = rules_result
    if rules_result.get("confidence", 0.0) < HIGH_CONFIDENCE_THRESHOLD:
        ai_result = classify_insider_with_ai(insider_name, officer_title, flags)
        if ai_result:
            result = ai_result

    entity = InsiderEntity(
        insider_id=insider_id,
        normalized_name=normalized_name,
        entity_type=result.get("entity_type", ENTITY_UNKNOWN),
        is_fund_like=bool(result.get("is_fund_like")),
        source=result.get("source", "rules"),
        confidence=float(result.get("confidence", 1.0)),
    )
    session.add(entity)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = (
            session.query(InsiderEntity)
            .filter(InsiderEntity.normalized_name == normalized_name)
            .one_or_none()
        )
        if existing:
            return existing
        raise

    session.refresh(entity)
    return entity
