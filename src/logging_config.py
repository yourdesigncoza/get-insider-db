"""Structured logging configuration for the insider-db project."""

from __future__ import annotations

import logging
import os

import structlog


def configure_logging() -> None:
    """
    Configure structlog for the application.

    Environment variables:
    - ENVIRONMENT: "production" for JSON output, else console
    - LOG_LEVEL: DEBUG, INFO, WARNING, ERROR (default: INFO)
    """
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Shared processors for all outputs
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.MODULE,
            }
        ),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if is_production:
        # JSON output for production (log aggregation, parsing)
        shared_processors.extend([
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ])
    else:
        # Pretty console output for development
        shared_processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a logger instance bound to the given module name.

    Usage:
        logger = get_logger(__name__)
        log = logger.bind(ticker="AAPL", operation="enrich")
        log.info("starting_enrichment", count=10)
    """
    return structlog.get_logger(name)
