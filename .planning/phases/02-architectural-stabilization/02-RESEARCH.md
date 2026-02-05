# Phase 02: Architectural Stabilization & Observability - Research

**Researched:** 2026-02-05
**Domain:** Python data access patterns, PostgreSQL indexing, structured logging
**Confidence:** HIGH

## Summary

This phase addresses the architectural debt identified in the codebase: inconsistent data access patterns (raw SQL + partial ORM), N+1 query issues, broad exception handling, and missing database indexes. The codebase currently uses a hybrid approach with raw SQL via `pd.read_sql_query()` / `text()` alongside SQLAlchemy ORM for the `InsiderEntity` table only.

The research confirms that SQLAlchemy 2.0 provides mature patterns for solving the N+1 problem through eager loading strategies (`selectinload`, `joinedload`), and that structlog is the standard choice for Python structured logging. PostgreSQL indexing is already partially addressed with indexes on `FILING_DATE` and `ISSUERTRADINGSYMBOL`, but the Phase 01 work on parameterized queries sets the foundation for a unified data access layer.

**Primary recommendation:** Standardize on SQLAlchemy ORM for all data access, use `selectinload` for batch insider classification, implement structlog with JSON output for production, and verify existing indexes cover the critical query paths.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.x | ORM + Core SQL | Already in use; 2.0 has explicit transactions, modern patterns |
| structlog | 25.x | Structured logging | Industry standard for Python structured logging; JSON output |
| psycopg2-binary | 2.9.x | PostgreSQL driver | Already in use; required for SQLAlchemy+Postgres |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| alembic | 1.13.x | DB migrations | When schema evolves; tracks index changes |
| python-json-logger | 3.x | stdlib logging JSON | If keeping stdlib logging alongside structlog |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQLAlchemy ORM | Raw SQL everywhere | Raw SQL is faster for complex analytics; ORM better for domain modeling |
| structlog | stdlib logging | structlog has better context binding; stdlib is simpler |
| alembic | Manual SQL scripts | Manual is faster for one-off; alembic tracks history |

**Installation:**
```bash
pip install structlog alembic
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── db/
│   ├── __init__.py           # Engine singleton, session factory
│   ├── models.py             # All ORM models (InsiderEntity, etc.)
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── insider_repo.py   # InsiderEntity CRUD + batch ops
│   │   └── signal_repo.py    # cluster_events, market_prices access
│   └── queries/
│       └── cluster_queries.py # Complex SQL kept separate
├── services/
│   ├── cluster_service.py    # Business logic (calls repositories)
│   └── enrichment_service.py # Price/fundamentals enrichment
└── logging_config.py         # structlog setup
```

### Pattern 1: Repository Pattern for Data Access
**What:** Centralize all database operations in repository classes
**When to use:** When you have multiple modules accessing the same tables
**Example:**
```python
# Source: SQLAlchemy 2.0 patterns
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

class InsiderRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_normalized_names(self, names: list[str]) -> dict[str, InsiderEntity]:
        """Batch load insiders by name - solves N+1."""
        stmt = select(InsiderEntity).where(
            InsiderEntity.normalized_name.in_(names)
        )
        results = self._session.scalars(stmt).all()
        return {e.normalized_name: e for e in results}

    def bulk_create(self, entities: list[InsiderEntity]) -> None:
        """Batch insert with conflict handling."""
        self._session.add_all(entities)
        self._session.flush()
```

### Pattern 2: Solving N+1 with Batch Loading
**What:** Replace loop-based single queries with batch IN queries
**When to use:** When iterating over rows and querying for each
**Example:**
```python
# Source: SQLAlchemy 2.0 docs - selectinload pattern
# BEFORE (N+1 pattern at cluster_buys.py:113-143):
for _, row in unique_rows.iterrows():
    entity = get_or_create_insider_entity(session, ...)  # 1 query per row

# AFTER (batch pattern):
# 1. Collect all normalized names
names = unique_rows["normalized_name"].dropna().unique().tolist()

# 2. Batch fetch existing
existing = insider_repo.get_by_normalized_names(names)

# 3. Create only missing
to_create = []
for _, row in unique_rows.iterrows():
    name = row.get("normalized_name")
    if name and name not in existing:
        entity = InsiderEntity(...)
        to_create.append(entity)
        existing[name] = entity  # cache for later access

# 4. Bulk insert
if to_create:
    insider_repo.bulk_create(to_create)
```

### Pattern 3: Structured Logging with Context
**What:** Use structlog for JSON output with request/operation context
**When to use:** All logging in the codebase
**Example:**
```python
# Source: structlog best practices
import structlog

# In logging_config.py
def configure_logging(json_output: bool = True):
    processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

# In cluster_buys.py
logger = structlog.get_logger(__name__)

def _classify_insiders(base_df, engine):
    log = logger.bind(operation="classify_insiders", count=len(base_df))
    log.info("starting_classification")
    # ... work ...
    log.info("classification_complete", classified=len(classifications))
```

### Pattern 4: Custom Exception Hierarchy
**What:** Replace bare `except Exception` with specific exceptions
**When to use:** All error handling
**Example:**
```python
# Source: Python best practices
# In src/exceptions.py
class InsiderDBError(Exception):
    """Base exception for insider-db project."""
    pass

class DataAccessError(InsiderDBError):
    """Database operation failed."""
    pass

class ClassificationError(InsiderDBError):
    """Insider classification failed."""
    pass

class EnrichmentError(InsiderDBError):
    """Price/fundamental enrichment failed."""
    pass

class InvalidTickerError(EnrichmentError):
    """Ticker not found in data provider."""
    pass

# Usage:
try:
    entity = get_or_create_insider_entity(...)
except IntegrityError as e:
    raise DataAccessError(f"Failed to create entity: {e}") from e
```

### Anti-Patterns to Avoid
- **Bare `except Exception:`** - Hides bugs, masks real errors; use specific exceptions
- **Session-per-query** - Creates connection churn; use session scopes (request/operation)
- **Mixed raw SQL + ORM without strategy** - Pick one per domain; analytics = raw SQL, entities = ORM
- **Logging without context** - Always bind operation/ticker/count for traceability

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Batch loading | Loop + single queries | `IN` clause with batch fetch | N+1 creates O(n) queries |
| Connection pooling | Manual connection management | SQLAlchemy engine pool | Built-in connection reuse, overflow handling |
| Retry logic | Simple sleep loops | tenacity library (already used) | Exponential backoff, jitter, proper exception handling |
| JSON logging | Manual dict formatting | structlog JSONRenderer | Consistent format, exception serialization |
| DB migrations | Manual ALTER scripts | alembic | Version tracking, rollback support |

**Key insight:** The codebase already uses tenacity for API retries. The same philosophy (don't hand-roll) should apply to data access patterns.

## Common Pitfalls

### Pitfall 1: Lazy Loading in Loops (N+1)
**What goes wrong:** Each iteration triggers a separate query
**Why it happens:** ORM relationships default to lazy loading
**How to avoid:** Use `selectinload()` or `joinedload()` in query options; or use batch pattern shown above
**Warning signs:** `DEBUG` SQL logs show repeating SELECT patterns

### Pitfall 2: Session Scope Too Wide
**What goes wrong:** Long-lived sessions hold transactions, cause locks
**Why it happens:** Reusing session across unrelated operations
**How to avoid:** Use context managers: `with Session(engine) as session:`
**Warning signs:** "idle in transaction" in pg_stat_activity

### Pitfall 3: Swallowing Exceptions
**What goes wrong:** Errors silently pass, data integrity issues go unnoticed
**Why it happens:** Defensive `except Exception: pass` or `continue`
**How to avoid:** Catch specific exceptions; log and re-raise or propagate
**Warning signs:** Functions return `None` or empty results without explanation

### Pitfall 4: Missing Indexes on Filter Columns
**What goes wrong:** Full table scans on large tables
**Why it happens:** Assuming indexes exist; not running EXPLAIN
**How to avoid:** Create indexes on WHERE clause columns; use `EXPLAIN ANALYZE`
**Warning signs:** Slow queries on filtered columns; seq scans in EXPLAIN

### Pitfall 5: Mixing Transaction Boundaries
**What goes wrong:** Partial commits, inconsistent state
**Why it happens:** Committing inside loops; nested session.commit() calls
**How to avoid:** Commit once at end of logical operation; use explicit transaction scopes
**Warning signs:** Partial data after errors

## Code Examples

### Batch Insider Classification (Fixing N+1)
```python
# Source: Derived from SQLAlchemy 2.0 selectinload pattern
# Replace cluster_buys.py:113-143

def _classify_insiders_batch(base_df: pd.DataFrame, engine: Engine) -> Dict[str, Dict[str, Any]]:
    """
    Batch classify insiders - O(1) queries instead of O(n).
    """
    if base_df.empty or "normalized_name" not in base_df:
        return {}

    unique_names = base_df["normalized_name"].dropna().unique().tolist()
    if not unique_names:
        return {}

    classifications: Dict[str, Dict[str, Any]] = {}

    with Session(bind=engine, expire_on_commit=False) as session:
        # 1. Batch fetch existing entities (single query)
        stmt = select(InsiderEntity).where(
            InsiderEntity.normalized_name.in_(unique_names)
        )
        existing = {e.normalized_name: e for e in session.scalars(stmt).all()}

        # 2. Identify missing names
        missing_names = set(unique_names) - set(existing.keys())

        # 3. Prepare new entities for missing
        to_create = []
        name_to_row = base_df.drop_duplicates(subset=["normalized_name"]).set_index("normalized_name")

        for name in missing_names:
            if name not in name_to_row.index:
                continue
            row = name_to_row.loc[name]
            flags = _derive_flags(row)
            rules_result = classify_insider_by_rules(
                row.get("insider_name", name),
                row.get("insider_title"),
                flags
            )
            entity = InsiderEntity(
                insider_id=str(row.get("insider_cik")) if pd.notna(row.get("insider_cik")) else None,
                normalized_name=name,
                entity_type=rules_result.get("entity_type", "unknown"),
                is_fund_like=bool(rules_result.get("is_fund_like")),
                source=rules_result.get("source", "rules"),
                confidence=float(rules_result.get("confidence", 1.0)),
            )
            to_create.append(entity)
            existing[name] = entity

        # 4. Bulk insert (single statement)
        if to_create:
            session.add_all(to_create)
            try:
                session.commit()
            except IntegrityError:
                # Race condition: another process inserted
                session.rollback()
                # Re-fetch to get the committed versions
                stmt = select(InsiderEntity).where(
                    InsiderEntity.normalized_name.in_([e.normalized_name for e in to_create])
                )
                for e in session.scalars(stmt).all():
                    existing[e.normalized_name] = e

        # 5. Build return dict
        for name, entity in existing.items():
            classifications[name] = {
                "is_fund_like": bool(entity.is_fund_like),
                "entity_type": entity.entity_type,
            }

    return classifications
```

### Structured Logging Configuration
```python
# Source: structlog best practices
# src/logging_config.py

import logging
import os
import structlog

def configure_logging():
    """Configure structlog for the application."""
    is_production = os.getenv("ENVIRONMENT", "development") == "production"
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Shared processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if is_production:
        # JSON output for production
        shared_processors.extend([
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ])
    else:
        # Pretty console output for development
        shared_processors.extend([
            structlog.dev.ConsoleRenderer(colors=True),
        ])

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

# Usage in modules:
logger = structlog.get_logger(__name__)

def process_cluster(ticker: str, window_start: date, window_end: date):
    log = logger.bind(ticker=ticker, window_start=str(window_start), window_end=str(window_end))
    log.info("processing_cluster")
    try:
        # ... work ...
        log.info("cluster_processed", num_trades=42)
    except DataAccessError as e:
        log.error("cluster_processing_failed", error=str(e))
        raise
```

### Custom Exception Hierarchy
```python
# Source: Python best practices
# src/exceptions.py

class InsiderDBError(Exception):
    """Base exception for the insider-db project."""

    def __init__(self, message: str, context: dict = None):
        super().__init__(message)
        self.context = context or {}


class DataAccessError(InsiderDBError):
    """Database operation failed."""
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


# Usage pattern - replacing bare except Exception:
# BEFORE:
try:
    entity = get_or_create(...)
except Exception:  # BAD: swallows all errors
    pass

# AFTER:
try:
    entity = get_or_create(...)
except IntegrityError as e:
    logger.warning("entity_exists", normalized_name=name)
    entity = fetch_existing(name)  # recover gracefully
except SQLAlchemyError as e:
    raise DataAccessError(f"Database error: {e}", {"name": name}) from e
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SQLAlchemy 1.x implicit autocommit | SQLAlchemy 2.0 explicit transactions | Jan 2023 | Must use `session.commit()` explicitly |
| Query object `.query(Model)` | `select(Model)` statements | SQLAlchemy 2.0 | More explicit, composable |
| `session.execute(text(...))` raw | Still valid, but typed `text()` | SQLAlchemy 2.0 | Parameters must use `:name` style |
| stdlib logging + formatters | structlog for structured logs | 2020+ | JSON-native, context binding |

**Deprecated/outdated:**
- `session.query()` API: Works but deprecated in SQLAlchemy 2.0; use `select()`
- `_LEGACY_ROLE_WEIGHTS_FLOAT` in cluster_service.py: Already marked deprecated

## Open Questions

1. **ORM Model Coverage**
   - What we know: Only `InsiderEntity` has ORM model; other tables accessed via raw SQL
   - What's unclear: Should `cluster_events`, `market_prices` get ORM models?
   - Recommendation: Start with repository pattern for raw SQL; add ORM models incrementally if needed

2. **Migration Strategy**
   - What we know: Schema changes happen via `schema.sql`
   - What's unclear: Should we adopt alembic for future migrations?
   - Recommendation: Out of scope for this phase; consider for Phase 4

3. **Index Verification**
   - What we know: Indexes exist on `FILING_DATE`, `ISSUERTRADINGSYMBOL`, etc. (from schema.sql)
   - What's unclear: Are current indexes optimal for actual query patterns?
   - Recommendation: Run `EXPLAIN ANALYZE` on cluster_buys queries to verify

## Current Codebase Analysis

### Exception Handling Locations (found via grep)
| File | Line | Pattern | Issue |
|------|------|---------|-------|
| `cluster_buys.py` | 42, 56, 91, 163 | `except Exception:` | Silent pass/None return |
| `cluster_service.py` | (none) | N/A | Clean |
| `enrich_clusters_with_price.py` | 231, 467, 539, 639, 650, 735 | `except Exception as e:` | Logs but continues |
| `backtest_cluster_strategy.py` | 53, 275 | `except Exception:` | Silent fallback |
| `show_cluster_buys.py` | 19, 25 | `except Exception:` | Optional import |

### N+1 Pattern Location
**File:** `src/analytics/cluster_buys.py`
**Lines:** 113-143
**Issue:** Loop iterates over `unique_rows.iterrows()` and calls `get_or_create_insider_entity()` per row, which issues a SELECT per insider name.
**Solution:** Batch pattern shown in Code Examples above.

### Current Indexes (from schema.sql)
| Table | Index | Columns |
|-------|-------|---------|
| cluster_events | idx_cluster_events_ticker_signal | ticker, signal_date |
| cluster_events | idx_cluster_events_active | status, expiry_date |
| cluster_event_members | idx_cluster_members_cluster | cluster_id |
| cluster_event_members | idx_cluster_members_ticker_date | trade_date |
| form345_nonderiv_trans | idx_nonderiv_accession | ACCESSION_NUMBER |
| form345_nonderiv_trans | idx_nonderiv_trans_code | TRANS_CODE |
| form345_nonderiv_trans | idx_nonderiv_trans_code_accession | TRANS_CODE, ACCESSION_NUMBER |
| form345_nonderiv_trans | idx_nonderiv_trans_date | TRANS_DATE |
| form345_submission | idx_subm_accession | ACCESSION_NUMBER |
| form345_submission | idx_subm_filing_date | FILING_DATE |
| form345_submission | idx_subm_filing_ticker | FILING_DATE, ISSUERTRADINGSYMBOL |
| form345_submission | idx_subm_ticker_filingdate | ISSUERTRADINGSYMBOL, FILING_DATE |
| form345_reportingowner | idx_reportingowner_accession | ACCESSION_NUMBER |
| market_prices | idx_market_prices_ticker_date | ticker, price_date |
| market_fundamentals | idx_market_fundamentals_ticker_date | ticker, date |

**Assessment:** Indexes appear comprehensive for current query patterns. The `insider_buy_signals` VIEW joins on `ACCESSION_NUMBER` which is indexed. Recommend running `EXPLAIN ANALYZE` to verify no missing indexes.

## Sources

### Primary (HIGH confidence)
- [SQLAlchemy 2.0 ORM Querying Guide](https://docs.sqlalchemy.org/en/20/orm/queryguide/index.html) - selectinload, joinedload patterns
- [structlog Logging Best Practices](https://www.structlog.org/en/stable/logging-best-practices.html) - JSON output, context binding

### Secondary (MEDIUM confidence)
- [PostgreSQL Indexing Best Practices - pgMustard](https://www.pgmustard.com/blog/indexing-best-practices-postgresql) - Index creation guidance
- [10 SQLAlchemy Relationship Patterns - Medium](https://medium.com/@Modexa/10-sqlalchemy-relationship-patterns-that-dont-become-n-1-hell-9643dbc68712) - N+1 patterns

### Codebase Analysis (HIGH confidence)
- `src/analytics/cluster_buys.py` - N+1 pattern at lines 113-143
- `src/models.py` - Existing InsiderEntity ORM model
- `schema.sql` - Current indexes
- `src/config.py` - Engine singleton pattern

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - SQLAlchemy and structlog are established
- Architecture: HIGH - Patterns derived from official documentation
- Pitfalls: HIGH - Based on codebase analysis and official docs
- Code examples: MEDIUM - Adapted from docs, not tested in this codebase

**Research date:** 2026-02-05
**Valid until:** 2026-03-05 (30 days for stable patterns)
