"""
Async client infrastructure for non-blocking I/O operations.

Provides HTTP client with connection pooling, async database engine,
and resilient retry decorators for rate-limited APIs.
"""

from src.async_client.http_client import AsyncHTTPClient
from src.async_client.db_engine import get_async_engine, async_session_factory
from src.async_client.retry import async_retry, default_api_retry

__all__ = [
    "AsyncHTTPClient",
    "get_async_engine",
    "async_session_factory",
    "async_retry",
    "default_api_retry",
]
