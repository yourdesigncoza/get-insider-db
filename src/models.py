"""
SQLAlchemy models shared across the project.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Session, declarative_base

from src.config import get_engine

Base = declarative_base()


class InsiderEntity(Base):
    __tablename__ = "insider_entities"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_insider_entities_normalized_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    insider_id = Column(String, nullable=True)
    normalized_name = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    is_fund_like = Column(Boolean, nullable=False)
    source = Column(String, nullable=False)
    confidence = Column(Float, nullable=False, default=1.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def ensure_tables(engine=None) -> None:
    """
    Create tables for defined models if they do not already exist.
    """
    engine = engine or get_engine()
    Base.metadata.create_all(engine, tables=[InsiderEntity.__table__])


def get_session(engine=None) -> Session:
    """
    Convenience helper to create a Session bound to the configured engine.
    """
    engine = engine or get_engine()
    return Session(bind=engine)
