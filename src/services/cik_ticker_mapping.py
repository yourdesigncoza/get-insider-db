"""
CIK-to-ticker lookup service with in-memory caching.

Loads all CIK-ticker mappings from issuer_cik_ticker_map into a dict
on initialization. Provides get_ticker() for forward lookups and
get_cik() for reverse lookups.

Used by enrichment scripts to resolve CIK -> ticker for API calls.
"""

from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.config import get_engine
from src.logging_config import get_logger

logger = get_logger(__name__)


class CikTickerMapper:
    """Service for CIK-to-ticker lookups with in-memory caching."""

    def __init__(self, engine: Optional[Engine] = None):
        self.engine = engine or get_engine()
        self._cache: dict[str, str] = {}
        self._reverse_cache: dict[str, str] = {}
        self._load_mapping()

    def _load_mapping(self) -> None:
        """Load all CIK-ticker mappings into memory."""
        with self.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT issuer_cik, ticker FROM issuer_cik_ticker_map"
            )).fetchall()

        self._cache = {row[0]: row[1] for row in rows}
        self._reverse_cache = {row[1]: row[0] for row in rows}
        logger.info(f"Loaded {len(self._cache)} CIK-ticker mappings")

    def get_ticker(self, issuer_cik: str) -> Optional[str]:
        """Get ticker for a CIK. Returns None if not found."""
        ticker = self._cache.get(issuer_cik)
        if ticker and ',' in ticker:
            ticker = ticker.split(',')[0].strip()
        return ticker

    def get_cik(self, ticker: str) -> Optional[str]:
        """Get CIK for a ticker (reverse lookup). Returns None if not found."""
        return self._reverse_cache.get(ticker)

    def has_cik(self, issuer_cik: str) -> bool:
        """Check if CIK exists in mapping."""
        return issuer_cik in self._cache

    def refresh(self) -> None:
        """Reload mapping from database (call after data load)."""
        self._load_mapping()

    @property
    def count(self) -> int:
        """Number of CIK-ticker mappings loaded."""
        return len(self._cache)


_mapper: Optional[CikTickerMapper] = None


def get_mapper(engine: Optional[Engine] = None) -> CikTickerMapper:
    """Get or create global CikTickerMapper singleton."""
    global _mapper
    if _mapper is None:
        _mapper = CikTickerMapper(engine=engine)
    return _mapper


def reset_mapper() -> None:
    """Reset global mapper singleton (for testing)."""
    global _mapper
    _mapper = None
