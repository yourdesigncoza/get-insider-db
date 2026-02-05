"""
Async retry decorators with exponential backoff and jitter.

Provides resilient API call handling for rate-limited services.
Uses tenacity library for robust retry logic.
"""

import asyncio
import logging
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

import aiohttp
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def _is_retryable_http_error(exc: BaseException) -> bool:
    """
    Check if an HTTP error should be retried.

    Retries on:
    - Rate limits (429)
    - Server errors (500, 502, 503, 504)
    """
    if isinstance(exc, aiohttp.ClientResponseError):
        return exc.status in {429, 500, 502, 503, 504}
    return False


def async_retry(
    max_attempts: int = 5,
    initial_wait: float = 1.0,
    max_wait: float = 30.0,
    jitter: float = 5.0,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator factory for async retry with exponential backoff and jitter.

    Retries on:
    - aiohttp.ClientError (connection errors)
    - asyncio.TimeoutError
    - HTTP 429 (rate limit) and 5xx server errors

    Args:
        max_attempts: Maximum number of retry attempts.
        initial_wait: Initial wait time in seconds.
        max_wait: Maximum wait time between retries.
        jitter: Random jitter to add to wait time.

    Returns:
        Configured retry decorator.

    Example:
        @async_retry(max_attempts=3)
        async def fetch_price(client, ticker):
            return await client.get(f"/prices/{ticker}")
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(
            initial=initial_wait,
            max=max_wait,
            jitter=jitter,
        ),
        retry=(
            retry_if_exception_type(aiohttp.ClientError)
            | retry_if_exception_type(asyncio.TimeoutError)
            | retry_if_exception(_is_retryable_http_error)
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


# Pre-configured decorator for common API use case
default_api_retry = async_retry(
    max_attempts=5,
    initial_wait=1.0,
    max_wait=30.0,
    jitter=5.0,
)
