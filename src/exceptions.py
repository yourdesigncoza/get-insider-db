"""Custom exceptions for the insider-db project."""


class InsiderDBError(Exception):
    """Base exception for the insider-db project."""

    def __init__(self, message: str, context: dict = None):
        super().__init__(message)
        self.context = context or {}


class DataAccessError(InsiderDBError):
    """Database operation failed (connection, query, integrity)."""
    pass


class ClassificationError(InsiderDBError):
    """Insider classification failed."""
    pass


class EnrichmentError(InsiderDBError):
    """Price/fundamental enrichment failed."""
    pass


class InvalidTickerError(EnrichmentError):
    """Ticker not found or unsupported by data provider."""
    pass


class RateLimitError(EnrichmentError):
    """API rate limit exceeded."""
    pass
