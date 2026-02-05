"""
Async HTTP client with connection pooling and rate limiting.

Uses aiohttp with TCPConnector for efficient connection reuse and
semaphore-based concurrency control for rate limiting.
"""

import asyncio
from typing import Any

import aiohttp
from aiohttp import ClientSession, ClientTimeout, TCPConnector


class AsyncHTTPClient:
    """
    Async HTTP client with connection pooling and rate limiting.

    Uses aiohttp.TCPConnector for connection pooling and asyncio.Semaphore
    for limiting concurrent requests.

    Example:
        async with AsyncHTTPClient("https://api.example.com") as client:
            data = await client.get("/endpoint", params={"key": "value"})
    """

    def __init__(
        self,
        base_url: str | None = None,
        max_connections: int = 50,
        per_host: int = 10,
        timeout: int = 30,
        max_concurrent: int = 10,
    ) -> None:
        """
        Initialize the async HTTP client.

        Args:
            base_url: Base URL for all requests (optional).
            max_connections: Total connection pool limit.
            per_host: Connection limit per host.
            timeout: Total request timeout in seconds.
            max_concurrent: Maximum concurrent requests (semaphore limit).
        """
        self.base_url = base_url.rstrip("/") if base_url else ""
        self._connector = TCPConnector(
            limit=max_connections,
            limit_per_host=per_host,
            enable_cleanup_closed=True,
        )
        self._timeout = ClientTimeout(total=timeout, connect=10)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._session: ClientSession | None = None

    async def _get_session(self) -> ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = ClientSession(
                connector=self._connector,
                timeout=self._timeout,
                headers={
                    "User-Agent": "InsiderDB-AsyncClient/1.0",
                    "Accept": "application/json",
                },
            )
        return self._session

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Make an async GET request.

        Args:
            url: URL path (appended to base_url if set).
            params: Query parameters.
            headers: Additional headers to merge with defaults.

        Returns:
            Parsed JSON response as dict.

        Raises:
            aiohttp.ClientError: On connection/protocol errors.
            aiohttp.ClientResponseError: On HTTP error status codes.
        """
        session = await self._get_session()
        full_url = f"{self.base_url}{url}" if self.base_url else url

        async with self._semaphore:
            async with session.get(
                full_url, params=params, headers=headers
            ) as response:
                response.raise_for_status()
                return await response.json()

    async def close(self) -> None:
        """
        Close the HTTP session and connector.

        Includes a short sleep for SSL cleanup to avoid warnings.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            # Allow time for SSL connections to close gracefully
            await asyncio.sleep(0.25)
        self._session = None

    async def __aenter__(self) -> "AsyncHTTPClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager, closing the session."""
        await self.close()
