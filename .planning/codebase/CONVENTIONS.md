# Coding Conventions

**Analysis Date:** 2026-02-03

## Naming Patterns

**Files:**
- Module files: `snake_case.py` (e.g., `cluster_service.py`, `feature_engineering.py`)
- Test files: `test_<module_name>.py` (e.g., `test_cluster_scoring.py`, `test_look_ahead_bias.py`)
- Configuration files: Named with descriptive `snake_case` (e.g., `classification_config.py`, `scoring_weights.py`)

**Functions:**
- Functions use `snake_case` (e.g., `calculate_days_to_file`, `normalize_insider_name`, `compute_cluster_score`)
- Private/internal functions prefixed with underscore (e.g., `_df` helper in test files)
- Function names are descriptive and action-oriented: `fetch_recent_buys`, `detect_clusters`, `ensure_tables`

**Variables:**
- Local variables: `snake_case` (e.g., `lookback_days`, `total_value_usd`, `normalized_name`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_TABLE`, `FUND_TOKENS`, `ENTITY_FUND`, `ENTITY_PERSON`)
- Type hints use standard Python typing conventions (e.g., `Optional[str]`, `Dict[str, Any]`, `List[ClusterEvent]`)

**Classes:**
- `PascalCase` (e.g., `InsiderEntity`, `ClusterConfig`, `ClusterEvent`, `InsiderBuy`)
- Dataclasses and model classes follow same convention

**Modules and Packages:**
- Packages organize functionality by domain: `analytics/`, `loaders/`, `scoring_config/`
- Related config spread across domain-specific modules (e.g., classification config in `classification_config.py`, scoring weights in `scoring_config/scoring_weights.py`)

## Code Style

**Formatting:**
- No explicit linting/formatting tool detected (no `.flake8`, `.eslintrc`, `pyproject.toml` config)
- Standard Python style practices followed implicitly
- Line lengths vary; no strict enforcement detected

**Imports:**
- Future annotations enabled: `from __future__ import annotations` appears at top of most modules
- Type hints used throughout for clarity
- Standard library imports at top, then third-party, then local imports (not strictly enforced but observed)

## Import Organization

**Order:**
1. `from __future__ import annotations` (when used)
2. Standard library imports (e.g., `os`, `logging`, `pathlib`, `dataclasses`, `typing`)
3. Third-party imports (e.g., `pandas`, `sqlalchemy`, `sqlalchemy.orm`)
4. Local imports from `src` package (e.g., `from src.config import get_engine`)

**Path Aliases:**
- Absolute imports used with `src` package prefix (e.g., `from src.config import`, `from src.analytics.feature_engineering import`)
- No path aliases or import shortcuts detected

**Example from `src/analytics/cluster_service.py`:**
```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Set, Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.config import get_engine
from src.insider_classification import normalize_insider_name
from src.insider_roles import ROLE_WEIGHTS
```

## Error Handling

**Patterns:**
- Explicit exception raising and handling in critical paths (e.g., `FileNotFoundError` in `src/loaders/form345_loader.py`)
- Test files verify error handling via `try/except` blocks
- Database errors propagate naturally; not caught/suppressed
- Assertions used in test files for validation (e.g., `assert rows_inserted == 2`)

**Example from `src/loaders/form345_loader.py`:**
```python
if not base.exists():
    default_dir = pathlib.Path(DATA_DIR) / path
    if not default_dir.exists():
        raise FileNotFoundError(f"No TSVs found at {path} or {default_dir}")
```

**Example from `tests/test_loader.py`:**
```python
try:
    load_file(mock_file_path, mock_engine, table="any_table")
    assert False, "Expected an exception to be raised"
except Exception as e:
    assert str(e) == "File read error"
```

## Logging

**Framework:** Python `logging` module

**Patterns:**
- Logger created per module: `logger = logging.getLogger(__name__)`
- Example in `src/analytics/cluster_service.py`: `logger = logging.getLogger(__name__)`
- Print statements also used for console output during script execution (e.g., `print(f"Fetching buys for last {lookback_days} days...")`)
- No structured logging or third-party logging framework (Rich installed but not used for logging, only for terminal output)

## Comments

**When to Comment:**
- Docstrings on functions explain purpose and return values (e.g., `"""Load a single TSV file into the specified Postgres table using the efficient COPY command."""`)
- Inline comments explain non-obvious logic (e.g., `# Note: Interval syntax might vary by DB`)
- Comments explain rationale for choices (e.g., `# We want the max weight found? Or prioritized?` in deprecated code sections)
- TODO comments mark stubs or future work (e.g., `# TODO: replace the placeholder logic with an OpenAI (or similar) call`)

**JSDoc/TSDoc:**
- Not applicable (Python project; docstrings used instead)

**Function Docstrings:**
```python
def load_file(file_path: pathlib.Path, engine: Engine, table: str = DEFAULT_TABLE) -> int:
    """
    Load a single TSV file into the specified Postgres table using the efficient COPY command.

    Returns the number of rows written.
    """
```

## Function Design

**Size:** Functions are generally concise and focused; larger operations broken into helper functions

**Parameters:**
- Use keyword-only arguments for clarity: `engine: Engine, table: str = DEFAULT_TABLE`
- Default values provided where sensible (e.g., `lookback_days: int = 90`)
- Optional parameters typed as `Optional[str]` or `Optional[Dict[str, Any]]`

**Return Values:**
- Explicit return types specified in function signatures (e.g., `-> int`, `-> List[ClusterEvent]`)
- Functions return data structures (DataFrames, lists, dicts) rather than None
- Single responsibility principle: functions do one thing well

**Example from `src/insider_classification.py`:**
```python
def classify_insider_by_rules(
    name: str,
    officer_title: Optional[str],
    flags: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Rule-based classifier using name/title heuristics only."""
    flags = flags or {}
    # ... logic ...
    return {
        "entity_type": entity_type,
        "is_fund_like": is_fund_like,
        "source": "rules",
        "confidence": confidence,
        "rationale": "; ".join(rationale_parts),
    }
```

## Module Design

**Exports:**
- Modules export functions and classes that form their public API
- Constants exported for use in other modules (e.g., `ENTITY_FUND`, `ENTITY_PERSON` exported from `classification_config.py`)
- Example from `src/models.py`: exports `InsiderEntity`, `ensure_tables()`, `get_session()`

**Barrel Files:**
- Package `__init__.py` files present but minimal
- No extensive barrel file pattern observed
- Direct imports from specific modules preferred (e.g., `from src.analytics.feature_engineering import calculate_sale_to_purchase_ratio`)

**Example minimal `__init__.py`:**
```python
# src/analytics/__init__.py
# (Empty or minimal)
```

## Type Hints

**Usage:**
- Type hints used throughout for function parameters and return types
- Dataclass annotations use type hints (e.g., `window_days: int = 10`, `buys: List[InsiderBuy]`)
- Type aliases sometimes used for clarity: `Dict[str, Any]`, `Optional[str]`

**Example from `src/analytics/cluster_service.py`:**
```python
def detect_clusters(buys_df: pd.DataFrame, cfg: ClusterConfig) -> List[ClusterEvent]:
    """Detect insider clusters from recent buy signals."""
```

## Data Structures

**DataFrames:**
- Pandas DataFrames used extensively for data manipulation
- Column operations often include `.copy()` to avoid SettingWithCopyWarning
- Type conversions explicit: `df["shares"] = pd.to_numeric(df["shares"], errors="coerce")`

**Dictionaries:**
- Configuration stored in dictionaries (e.g., `FUND_TOKENS`, `ROLE_WEIGHTS`)
- Function return values often dictionaries for flexibility

**Dataclasses:**
- Used for structured data with clear schemas (e.g., `ClusterConfig`, `ClusterEvent`, `InsiderBuy`)
- Leverage Python 3.7+ dataclass decorator

## Configuration Management

**Location:**
- Central configuration in `src/config.py`: DATABASE_URL, DATA_DIR
- Environment variables loaded via `python-dotenv`
- Scoring/role weights in `src/scoring_config/scoring_weights.py`
- Classification rules in `src/classification_config.py`

**Pattern:**
```python
# src/config.py
import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://...")
DATA_DIR = Path(os.getenv("DATA_DIR", "data/extracted"))

@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create a singleton SQLAlchemy engine using the configured DATABASE_URL."""
    return create_engine(DATABASE_URL)
```

---

*Convention analysis: 2026-02-03*
