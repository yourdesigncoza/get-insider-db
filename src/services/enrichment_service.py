"""
Async enrichment service for fetching price and fundamental data.

Provides AsyncEnricher class that fetches prices and fundamentals concurrently
with caching, rate limiting, and proper error handling per-cluster.
"""

import asyncio
import os
from datetime import datetime, timedelta, date
from typing import Any

import aiohttp
from dateutil.relativedelta import relativedelta
from sqlalchemy import text

from src.async_client import AsyncHTTPClient, async_session_factory, async_retry
from src.cluster_scoring import compute_market_cap_adjusted_score
from src.exceptions import InvalidTickerError


# Default configuration from environment
DEFAULT_API_BASE_URL = "https://api.financialdatasets.ai"
FINANCIAL_METRICS_PERIOD = os.getenv("FINANCIAL_METRICS_PERIOD", "quarterly")
FUNDAMENTALS_MAX_LOOKBACK_DAYS = int(os.getenv("FUNDAMENTALS_MAX_LOOKBACK_DAYS", "730"))
FUNDAMENTALS_MAX_FORWARD_DAYS = int(os.getenv("FUNDAMENTALS_MAX_FORWARD_DAYS", "120"))
FINANCIAL_METRICS_MAX_LIMIT = int(os.getenv("FINANCIAL_METRICS_MAX_LIMIT", "200"))
PRICE_LOOKAHEAD_BUFFER_DAYS = int(os.getenv("PRICE_LOOKAHEAD_BUFFER_DAYS", "10"))


def _parse_float(value: Any) -> float | None:
    """Parse value to float, handling None and string 'None'."""
    if value is None:
        return None
    if isinstance(value, str) and value.lower() == "none":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_date(value: Any) -> datetime | None:
    """Parse value to datetime, handling various formats."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        s = value[:10]
        try:
            return datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            return None
    return None


def _normalize_financial_metrics_record(
    record: dict[str, Any], fallback_date: datetime
) -> dict[str, Any]:
    """Normalize financial metrics record to standard format."""
    mc = _parse_float(
        record.get("market_cap") if "market_cap" in record else record.get("marketCap")
    )
    ev = _parse_float(
        record.get("enterprise_value")
        if "enterprise_value" in record
        else record.get("enterpriseVal")
    )
    pe = _parse_float(
        record.get("price_to_earnings_ratio")
        if "price_to_earnings_ratio" in record
        else record.get("pe_ratio", record.get("peRatio"))
    )
    pb = _parse_float(
        record.get("price_to_book_ratio")
        if "price_to_book_ratio" in record
        else record.get("pb_ratio", record.get("pbRatio"))
    )
    peg = _parse_float(
        record.get("peg_ratio")
        if "peg_ratio" in record
        else record.get("trailing_peg_ratio", record.get("trailingPegRatio"))
    )

    record_date = (
        _parse_date(record.get("date"))
        or _parse_date(record.get("report_period"))
        or _parse_date(record.get("reportPeriod"))
        or _parse_date(record.get("period_end_date"))
        or _parse_date(record.get("periodEndDate"))
        or fallback_date
    )

    return {
        "date": record_date,
        "marketCap": mc,
        "enterpriseVal": ev,
        "peRatio": pe,
        "pbRatio": pb,
        "trailingPegRatio": peg,
    }


def _completeness_score(record: dict[str, Any]) -> int:
    """Count how many fundamental fields are non-None."""
    return sum(
        1
        for k in ("marketCap", "enterpriseVal", "peRatio", "pbRatio", "trailingPegRatio")
        if record.get(k) is not None
    )


def _calculate_max_drawdown(
    prices: list[float], base_price: float | None
) -> float | None:
    """Calculate maximum drawdown from base price."""
    if not prices or base_price is None or base_price == 0:
        return None
    min_price = min(prices)
    if min_price >= base_price:
        return 0.0
    drawdown = (min_price - base_price) / base_price
    return round(drawdown * 100.0, 2)


def _get_closest_price_record(
    history: list[dict], target_date: datetime
) -> dict | None:
    """Get closest price record on or before target date."""
    candidate = None
    for record in history:
        if record["date"] <= target_date:
            candidate = record
        else:
            break
    return candidate


def _get_first_price_record_on_or_after(
    history: list[dict], target_date: datetime
) -> dict | None:
    """Get first price record on or after target date."""
    for record in history:
        if record["date"] >= target_date:
            return record
    return None


class AsyncEnricher:
    """
    Async enrichment service for cluster price and fundamental data.

    Fetches prices and fundamentals concurrently with caching and rate limiting.

    Example:
        async with AsyncEnricher(api_key="...") as enricher:
            enriched = await enricher.enrich_cluster(cluster_dict)
    """

    def __init__(
        self,
        api_key: str,
        max_concurrent: int = 10,
        base_url: str = DEFAULT_API_BASE_URL,
    ) -> None:
        """
        Initialize the async enricher.

        Args:
            api_key: Financial Datasets API key.
            max_concurrent: Maximum concurrent API requests.
            base_url: Base URL for the API (defaults to Financial Datasets AI).
        """
        self._api_key = api_key
        self._client = AsyncHTTPClient(
            base_url=base_url,
            max_concurrent=max_concurrent,
        )
        self._session_factory = async_session_factory()

    # -------------------------------------------------------------------------
    # PRICE CACHE METHODS
    # -------------------------------------------------------------------------

    async def _check_price_cache(
        self, ticker: str, start: datetime, end: datetime
    ) -> list[dict]:
        """
        Query market_prices table for cached prices in date range.

        Args:
            ticker: Stock ticker symbol.
            start: Start date for price range.
            end: End date for price range.

        Returns:
            List of price records [{"date": datetime, "close": float}, ...].
        """
        async with self._session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT price_date, close_price
                    FROM market_prices
                    WHERE ticker = :ticker
                      AND price_date BETWEEN :start AND :end
                    ORDER BY price_date
                """),
                {"ticker": ticker, "start": start.date(), "end": end.date()},
            )
            rows = result.fetchall()

        return [
            {
                "date": datetime.combine(row[0], datetime.min.time()),
                "close": float(row[1]),
            }
            for row in rows
        ]

    async def _save_prices_to_cache(
        self, ticker: str, prices: list[dict]
    ) -> None:
        """
        Batch insert prices into market_prices table.

        Args:
            ticker: Stock ticker symbol.
            prices: List of price records to save.
        """
        if not prices:
            return

        async with self._session_factory() as session:
            for p in prices:
                await session.execute(
                    text("""
                        INSERT INTO market_prices (ticker, price_date, close_price)
                        VALUES (:ticker, :date, :price)
                        ON CONFLICT (ticker, price_date) DO NOTHING
                    """),
                    {
                        "ticker": ticker,
                        "date": p["date"].date(),
                        "price": p["close"],
                    },
                )
            await session.commit()

    # -------------------------------------------------------------------------
    # FUNDAMENTALS CACHE METHODS
    # -------------------------------------------------------------------------

    async def _check_fundamentals_cache(
        self, ticker: str, target_date: datetime
    ) -> dict | None:
        """
        Query market_fundamentals table for cached fundamentals near target date.

        Args:
            ticker: Stock ticker symbol.
            target_date: Target date to find fundamentals for.

        Returns:
            Fundamental record dict or None if not found.
        """
        start_search = target_date - timedelta(days=FUNDAMENTALS_MAX_LOOKBACK_DAYS)
        end_search = target_date + timedelta(days=FUNDAMENTALS_MAX_FORWARD_DAYS)

        async with self._session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT date, market_cap, enterprise_value, pe_ratio, pb_ratio, trailing_peg_ratio
                    FROM market_fundamentals
                    WHERE ticker = :ticker
                      AND date BETWEEN :start AND :end
                    ORDER BY date DESC
                    LIMIT 40
                """),
                {
                    "ticker": ticker,
                    "start": start_search.date(),
                    "end": end_search.date(),
                },
            )
            rows = result.fetchall()

        if not rows:
            return None

        candidates: list[dict[str, Any]] = []
        for row in rows:
            candidates.append(
                {
                    "date": datetime.combine(row[0], datetime.min.time()),
                    "marketCap": float(row[1]) if row[1] else None,
                    "enterpriseVal": float(row[2]) if row[2] else None,
                    "peRatio": float(row[3]) if row[3] else None,
                    "pbRatio": float(row[4]) if row[4] else None,
                    "trailingPegRatio": float(row[5]) if row[5] else None,
                }
            )

        # Sort by: closest date, prefer <= target, then more complete
        candidates.sort(
            key=lambda r: (
                abs((r["date"].date() - target_date.date()).days),
                0 if r["date"].date() <= target_date.date() else 1,
                -_completeness_score(r),
                r["date"],
            )
        )
        return candidates[0]

    async def _save_fundamentals_to_cache(
        self, ticker: str, data: dict
    ) -> None:
        """
        Insert fundamental record into market_fundamentals table.

        Args:
            ticker: Stock ticker symbol.
            data: Fundamental record to save.
        """
        if not data:
            return

        async with self._session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO market_fundamentals (
                        ticker, date, market_cap, enterprise_value, pe_ratio, pb_ratio, trailing_peg_ratio
                    ) VALUES (
                        :ticker, :date, :mc, :ev, :pe, :pb, :peg
                    ) ON CONFLICT (ticker, date) DO NOTHING
                """),
                {
                    "ticker": ticker,
                    "date": data["date"].date(),
                    "mc": data.get("marketCap"),
                    "ev": data.get("enterpriseVal"),
                    "pe": data.get("peRatio"),
                    "pb": data.get("pbRatio"),
                    "peg": data.get("trailingPegRatio"),
                },
            )
            await session.commit()

    # -------------------------------------------------------------------------
    # API FETCH METHODS
    # -------------------------------------------------------------------------

    @async_retry()
    async def _fetch_prices_from_api(
        self, ticker: str, start: datetime, end: datetime
    ) -> list[dict]:
        """
        Fetch price history from Financial Datasets API.

        Args:
            ticker: Stock ticker symbol.
            start: Start date for price range.
            end: End date for price range.

        Returns:
            List of price records [{"date": datetime, "close": float}, ...].

        Raises:
            InvalidTickerError: If ticker is not valid/supported.
            aiohttp.ClientError: On connection/protocol errors.
        """
        params = {
            "ticker": ticker,
            "interval": "day",
            "interval_multiplier": 1,
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
        }

        try:
            data = await self._client.get(
                "/prices/",
                params=params,
                headers={"X-API-KEY": self._api_key},
            )
        except aiohttp.ClientResponseError as e:
            if e.status == 400:
                raise InvalidTickerError(f"Invalid ticker: {ticker}") from e
            raise

        time_series_data = data.get("prices", [])
        if not time_series_data:
            return []

        cleaned_data = []
        for item in time_series_data:
            date_str = item["time"][:10]
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            close_val = item.get("close")
            if close_val is not None:
                cleaned_data.append({"date": dt, "close": float(close_val)})

        # Filter to requested range
        cleaned_data = [d for d in cleaned_data if start <= d["date"] <= end]
        return sorted(cleaned_data, key=lambda x: x["date"])

    @async_retry()
    async def _fetch_fundamentals_from_api(
        self, ticker: str, target_date: datetime
    ) -> dict | None:
        """
        Fetch fundamental data from Financial Datasets API.

        Args:
            ticker: Stock ticker symbol.
            target_date: Target date to find fundamentals for.

        Returns:
            Fundamental record dict or None if not found.

        Raises:
            InvalidTickerError: If ticker is not valid/supported.
            aiohttp.ClientError: On connection/protocol errors.
        """
        min_allowed_date = target_date - timedelta(days=FUNDAMENTALS_MAX_LOOKBACK_DAYS)
        max_allowed_date = target_date + timedelta(days=FUNDAMENTALS_MAX_FORWARD_DAYS)

        # Try increasing limits to find data near target_date
        limits_to_try = [12, 40, 80, 120, FINANCIAL_METRICS_MAX_LIMIT]

        for limit in limits_to_try:
            params = {
                "ticker": ticker,
                "period": FINANCIAL_METRICS_PERIOD,
                "limit": limit,
            }

            try:
                payload = await self._client.get(
                    "/financial-metrics",
                    params=params,
                    headers={"X-API-KEY": self._api_key},
                )
            except aiohttp.ClientResponseError as e:
                if e.status == 400:
                    raise InvalidTickerError(f"Invalid ticker: {ticker}") from e
                raise

            # Parse response - support both list and dict formats
            records = []
            if isinstance(payload, list):
                records = payload
            elif isinstance(payload, dict):
                for key in ("financial_metrics", "metrics", "data"):
                    val = payload.get(key)
                    if isinstance(val, list):
                        records = val
                        break
                    if isinstance(val, dict):
                        records = [val]
                        break
                if not records and any(
                    k in payload
                    for k in ("market_cap", "enterprise_value", "price_to_earnings_ratio")
                ):
                    records = [payload]

            if not records:
                continue

            # Normalize and filter
            normalized = [
                _normalize_financial_metrics_record(r, fallback_date=target_date)
                for r in records
            ]

            candidates = []
            for r in normalized:
                if not (min_allowed_date <= r["date"] <= max_allowed_date):
                    continue
                if all(
                    r.get(k) is None
                    for k in (
                        "marketCap",
                        "enterpriseVal",
                        "peRatio",
                        "pbRatio",
                        "trailingPegRatio",
                    )
                ):
                    continue
                candidates.append(r)

            if candidates:
                # Sort by: closest date, prefer <= target, then more complete
                candidates.sort(
                    key=lambda r: (
                        abs((r["date"].date() - target_date.date()).days),
                        0 if r["date"].date() <= target_date.date() else 1,
                        -_completeness_score(r),
                        r["date"],
                    )
                )
                return candidates[0]

        return None

    # -------------------------------------------------------------------------
    # PUBLIC METHODS
    # -------------------------------------------------------------------------

    async def get_price_history(
        self, ticker: str, start: datetime, end: datetime
    ) -> list[dict]:
        """
        Get price history with cache-first pattern.

        Checks cache first, fetches from API if missing/incomplete,
        and saves new data to cache.

        Args:
            ticker: Stock ticker symbol.
            start: Start date for price range.
            end: End date for price range.

        Returns:
            List of price records [{"date": datetime, "close": float}, ...].
        """
        # Look back 7 days to capture start date if it's a weekend
        fetch_start = start - timedelta(days=7)

        # 1. Check cache
        db_prices = await self._check_price_cache(ticker, fetch_start, end)

        days_needed = (end - start).days
        needs_fetch = False

        if days_needed > 5:
            if len(db_prices) == 0:
                needs_fetch = True
            elif len(db_prices) < (days_needed * 0.5):
                needs_fetch = True
            else:
                # Check edges
                first_db = db_prices[0]["date"]
                last_db = db_prices[-1]["date"]
                if first_db > (start + timedelta(days=7)):
                    needs_fetch = True
                if last_db < (end - timedelta(days=7)):
                    needs_fetch = True
        elif not db_prices and days_needed > 0:
            needs_fetch = True

        if not needs_fetch:
            return db_prices

        # 2. Fetch from API
        api_prices = await self._fetch_prices_from_api(ticker, fetch_start, end)

        if not api_prices:
            return db_prices

        # 3. Save to cache
        await self._save_prices_to_cache(ticker, api_prices)

        return api_prices

    async def get_fundamentals(
        self, ticker: str, target_date: datetime
    ) -> dict | None:
        """
        Get fundamental data with cache-first pattern.

        Checks cache first, fetches from API if missing,
        and saves new data to cache.

        Args:
            ticker: Stock ticker symbol.
            target_date: Target date to find fundamentals for.

        Returns:
            Fundamental record dict or None if not found.
        """
        # 1. Check cache
        cached = await self._check_fundamentals_cache(ticker, target_date)
        if cached:
            return cached

        # 2. Fetch from API
        api_data = await self._fetch_fundamentals_from_api(ticker, target_date)

        if not api_data:
            return None

        # 3. Save to cache
        await self._save_fundamentals_to_cache(ticker, api_data)

        return api_data

    async def enrich_cluster(self, cluster: dict) -> dict:
        """
        Enrich a single cluster with price and fundamental data.

        Fetches prices and fundamentals concurrently for the cluster.

        Args:
            cluster: Cluster dict with ticker, window_end, entry_date, etc.

        Returns:
            Enriched cluster dict with price and fundamental fields.
        """
        ticker = cluster.get("ticker")
        window_end_str = cluster.get("window_end")
        total_value = cluster.get("total_value", 0)

        if not ticker or not window_end_str:
            return cluster

        try:
            window_end_date = datetime.strptime(window_end_str, "%Y-%m-%d")
        except ValueError:
            return cluster

        # Calculate entry date (lookahead-safe)
        entry_date_str = cluster.get("entry_date")
        filing_date_str = cluster.get("signal_filing_date")
        try:
            if entry_date_str:
                entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d")
            elif filing_date_str:
                entry_date = datetime.strptime(filing_date_str, "%Y-%m-%d") + timedelta(
                    days=1
                )
            else:
                entry_date = window_end_date + timedelta(days=1)
        except ValueError:
            entry_date = window_end_date + timedelta(days=1)

        # Calculate target dates
        date_1m = entry_date + relativedelta(months=1)
        date_2m = entry_date + relativedelta(months=2)
        date_3m = entry_date + relativedelta(months=3)
        price_fetch_end = date_3m + timedelta(days=PRICE_LOOKAHEAD_BUFFER_DAYS)

        # Fetch prices and fundamentals concurrently
        enrichment_status = "ok"
        enrichment_errors: list[str] = []
        history: list[dict] = []
        fund_data: dict | None = None

        results = await asyncio.gather(
            self.get_price_history(ticker, entry_date, price_fetch_end),
            self.get_fundamentals(ticker, entry_date),
            return_exceptions=True,
        )

        # Handle price result
        if isinstance(results[0], InvalidTickerError):
            enrichment_status = "unsupported_ticker"
            enrichment_errors.append(f"prices: {results[0]}")
        elif isinstance(results[0], Exception):
            enrichment_status = "error"
            enrichment_errors.append(f"prices: {results[0]}")
        else:
            history = results[0]

        # Handle fundamentals result
        if isinstance(results[1], InvalidTickerError):
            if enrichment_status == "ok":
                enrichment_status = "unsupported_ticker"
            enrichment_errors.append(f"fundamentals: {results[1]}")
        elif isinstance(results[1], Exception):
            if enrichment_status == "ok":
                enrichment_status = "partial"
            enrichment_errors.append(f"fundamentals: {results[1]}")
        else:
            fund_data = results[1]

        # Calculate price metrics
        base_record = _get_first_price_record_on_or_after(history, entry_date)
        base_price = base_record["close"] if base_record else None

        if enrichment_status == "ok" and not history:
            enrichment_status = "no_price_data"

        price_results = {}
        for suffix, end_date in [("1m", date_1m), ("2m", date_2m), ("3m", date_3m)]:
            end_record = _get_first_price_record_on_or_after(history, end_date)
            end_price = end_record["close"] if end_record else None

            ret_val = None
            if base_price and end_price:
                ret_val = round(((end_price - base_price) / base_price) * 100.0, 2)

            price_results[f"price_{suffix}_after"] = end_price
            price_results[f"return_{suffix}"] = ret_val

            if base_record and end_record:
                period_prices = [
                    r["close"]
                    for r in history
                    if base_record["date"] <= r["date"] <= end_record["date"]
                ]
                mdd = _calculate_max_drawdown(period_prices, base_price)
                price_results[f"max_drawdown_{suffix}"] = mdd
            else:
                price_results[f"max_drawdown_{suffix}"] = None

        # Extract fundamentals
        market_cap = fund_data.get("marketCap") if fund_data else None
        enterprise_value = fund_data.get("enterpriseVal") if fund_data else None
        pe_ratio = fund_data.get("peRatio") if fund_data else None
        pb_ratio = fund_data.get("pbRatio") if fund_data else None
        trailing_peg_ratio = fund_data.get("trailingPegRatio") if fund_data else None

        # Calculate cluster vs market cap percentage
        cluster_vs_mcap_pct = None
        if market_cap and total_value and market_cap > 0:
            cluster_vs_mcap_pct = round((total_value / market_cap) * 100.0, 4)

        # Compute market-cap adjusted score
        original_score = cluster.get("cluster_score", 0.0)
        adjusted_cluster_score = compute_market_cap_adjusted_score(
            original_score, cluster_vs_mcap_pct
        )

        # Build enriched result
        new_row = cluster.copy()
        new_row.update(
            {
                "enrichment_status": enrichment_status,
                "enrichment_errors": enrichment_errors,
                "price_at_entry": base_price,
                "market_cap_at_entry": market_cap,
                "enterprise_value_at_entry": enterprise_value,
                "pe_ratio_at_entry": pe_ratio,
                "pb_ratio_at_entry": pb_ratio,
                "trailing_peg_ratio_at_entry": trailing_peg_ratio,
                # Backward-compatible aliases
                "price_at_window_end": base_price,
                "market_cap_at_window_end": market_cap,
                "enterprise_value_at_window_end": enterprise_value,
                "pe_ratio_at_window_end": pe_ratio,
                "pb_ratio_at_window_end": pb_ratio,
                "trailing_peg_ratio_at_window_end": trailing_peg_ratio,
                "cluster_value_vs_mcap_pct": cluster_vs_mcap_pct,
                "adjusted_cluster_score": adjusted_cluster_score,
                **price_results,
            }
        )
        return new_row

    async def enrich_batch(self, clusters: list[dict]) -> list[dict]:
        """
        Enrich multiple clusters concurrently.

        Each cluster's price and fundamentals are fetched in parallel.
        Errors for one cluster don't crash the entire batch.

        Args:
            clusters: List of cluster dicts to enrich.

        Returns:
            List of enriched cluster dicts (same order as input).
        """
        tasks = [self.enrich_cluster(c) for c in clusters]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        enriched = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Return original cluster with error status
                cluster = clusters[i].copy()
                cluster["enrichment_status"] = "error"
                cluster["enrichment_errors"] = [str(result)]
                enriched.append(cluster)
            else:
                enriched.append(result)

        return enriched

    async def close(self) -> None:
        """Close HTTP client and dispose engine."""
        await self._client.close()

    async def __aenter__(self) -> "AsyncEnricher":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager, closing resources."""
        await self.close()
