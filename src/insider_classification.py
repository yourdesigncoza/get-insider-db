"""
Insider entity classification helpers with a rule-based pass and AI stub.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models import InsiderEntity, ensure_tables

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

HIGH_CONFIDENCE_THRESHOLD = 0.8
RULE_CONFIDENCE_FUND = 0.8
RULE_CONFIDENCE_PERSON = 0.6

ENTITY_PERSON = "person"
ENTITY_FUND = "fund_or_investment_vehicle"
ENTITY_OPERATING_CO = "operating_company"
ENTITY_TRUST = "trust_or_foundation"
ENTITY_OTHER = "other"
ENTITY_UNKNOWN = "unknown"


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
    Stub for an AI-powered classifier.

    TODO: replace the placeholder logic with an OpenAI (or similar) call that
    returns a JSON payload containing entity_type, is_fund_like, and rationale.
    """
    flags = flags or {}
    rules_result = classify_insider_by_rules(name, officer_title, flags)
    # Example prompt to use when wiring an actual model:
    # "Classify SEC Form 4 insider names into: person, fund_or_investment_vehicle,
    #  operating_company, trust_or_foundation, other. Return JSON with entity_type,
    #  is_fund_like (bool), and a short rationale."
    ai_result = dict(rules_result)
    ai_result["source"] = "ai"
    ai_result["confidence"] = max(rules_result.get("confidence", 0.0), 0.75)
    if not ai_result.get("rationale"):
        ai_result["rationale"] = "Stubbed AI classification reused rule-based result"
    return ai_result


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
