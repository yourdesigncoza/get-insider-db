# Testing Patterns

**Analysis Date:** 2026-02-03

## Test Framework

**Runner:**
- pytest [version from requirements: `pytest`]
- Config: No `pytest.ini` or `pyproject.toml` test config detected; uses defaults
- Test cache: `.pytest_cache/` directory present

**Assertion Library:**
- Python built-in `assert` statements
- Example: `assert rows_inserted == 2`
- No specialized assertion library imported

**Run Commands:**
```bash
pytest                          # Run all tests (inferred from structure)
pytest tests/test_loader.py     # Run specific test file
pytest -v                       # Verbose output (likely)
pytest --tb=short               # Short traceback format (likely)
```

## Test File Organization

**Location:**
- Separate directory: `tests/` directory at project root
- Not co-located with source files

**Naming:**
- Pattern: `test_<module_name>.py` (e.g., `test_loader.py`, `test_cluster_scoring.py`, `test_look_ahead_bias.py`)
- All test files follow standard pytest naming convention for auto-discovery

**File Structure:**
```
tests/
├── conftest.py                          # Pytest configuration/fixtures
├── test_loader.py                       # Test for form345_loader module
├── test_insider_classification.py       # Tests for insider classification logic
├── test_cluster_scoring.py              # Tests for cluster scoring
├── test_look_ahead_bias.py              # Tests for temporal correctness
├── test_tradeable_window_selection.py   # Tests for window detection
```

## Test Structure

**Suite Organization:**
```python
# Basic function tests (test_insider_classification.py)
def test_normalize_insider_name():
    assert normalize_insider_name("  John   Doe  ") == "JOHN DOE"

def test_classify_insider_by_rules_fund():
    fund_names = ["ACME CAPITAL LLC", "GLOBAL GROWTH FUND L.P."]
    for name in fund_names:
        result = classify_insider_by_rules(name, None)
        assert result["entity_type"] == ENTITY_FUND
```

**Class-Based Tests (test_look_ahead_bias.py):**
```python
class TestMarketCapAdjustedScore:
    """Tests for compute_market_cap_adjusted_score function."""

    def test_no_mcap_returns_original(self):
        """When mcap_pct is None, return original score."""
        assert compute_market_cap_adjusted_score(70.0, None) == 70.0

    def test_zero_mcap_returns_original(self):
        """When mcap_pct is 0, return original score."""
        assert compute_market_cap_adjusted_score(70.0, 0.0) == 70.0
```

**Patterns:**
- **Setup:** Explicit test data setup within test functions (e.g., DataFrame creation)
- **Teardown:** No explicit teardown detected; uses Python garbage collection
- **Assertion:** Direct `assert` statements with message context where helpful
- **Docstrings:** Test functions include docstrings explaining what is being verified

**Example with detailed setup (test_look_ahead_bias.py):**
```python
def test_ratio_uses_only_available_data(self):
    """Verify that sale_to_purchase_ratio only uses temporally-available data."""
    base_date = date(2024, 1, 1)
    df = pd.DataFrame([
        {
            "ticker": "TEST",
            "normalized_name": "JOHN DOE",
            "transaction_date": pd.Timestamp(base_date + timedelta(days=5)),
            "filing_date": pd.Timestamp(base_date + timedelta(days=7)),
            "transaction_code": "P",
            "shares": 100.0,
        },
        # ... more rows ...
    ])

    df_all = calculate_sale_to_purchase_ratio(df.copy(), lookback_days=90)
    # Assertions follow
    assert len(df_at_jan17) == 2
```

## Mocking

**Framework:** `unittest.mock` (Python standard library)

**Patterns:**
```python
# Decorator-based mocking (test_loader.py)
@patch('src.loaders.form345_loader.pd.read_csv')
def test_load_file_uses_copy_expert(mock_read_csv):
    """Verify that load_file correctly calls psycopg2's copy_expert."""
    mock_cursor = MagicMock()
    mock_dbapi_conn = MagicMock()
    mock_dbapi_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_engine_connect

    # Setup return values
    df_to_return = pd.DataFrame({...}, dtype=str)
    mock_read_csv.return_value = df_to_return

    # Execute function under test
    rows_inserted = load_file(mock_file_path, mock_engine, table=table_name)

    # Verify interactions
    assert rows_inserted == 2
    mock_read_csv.assert_called_once_with(mock_file_path, sep="\t", dtype=str)
    mock_engine.connect.assert_called_once()
    mock_cursor.copy_expert.assert_called_once()
```

**What to Mock:**
- External dependencies: database connections, file I/O
- Example: `@patch('src.loaders.form345_loader.pd.read_csv')` mocks pandas file reading
- Database engine mocked to avoid real DB interactions during testing
- Cursor operations mocked to verify correct SQL commands are issued

**What NOT to Mock:**
- Pure business logic functions (e.g., `calculate_sale_to_purchase_ratio`, `classify_insider_by_rules`)
- Data structure operations
- These are tested with real data fixtures

**Mock Assertion Patterns:**
```python
# Verify function was called with correct arguments
mock_read_csv.assert_called_once_with(mock_file_path, sep="\t", dtype=str)

# Verify function was NOT called
mock_engine.connect.assert_not_called()

# Verify side effects (exception raising)
mock_read_csv.side_effect = Exception("File read error")
```

## Fixtures and Factories

**Test Data:**
```python
# Inline DataFrame creation (test_look_ahead_bias.py)
base_date = date(2024, 1, 1)
df = pd.DataFrame([
    {
        "ticker": "TEST",
        "normalized_name": "JOHN DOE",
        "transaction_date": pd.Timestamp(base_date + timedelta(days=5)),
        "filing_date": pd.Timestamp(base_date + timedelta(days=7)),
        "transaction_code": "P",
        "shares": 100.0,
    },
    # ... more test rows ...
])

# Helper function for common test data (test_tradeable_window_selection.py)
def _df(rows):
    df = pd.DataFrame(rows)
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    return df

# Usage
revealed = _df([
    {"transaction_date": "2024-01-01", "normalized_name": "a", "total_value": 100.0},
    {"transaction_date": "2024-01-02", "normalized_name": "b", "total_value": 200.0},
])
```

**Location:**
- Inline within test files (no separate `fixtures/` directory)
- `conftest.py` exists but contains only pytest configuration (path setup)
- Small fixtures defined as helper functions within test modules

**Example `conftest.py`:**
```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

## Coverage

**Requirements:** No explicit coverage requirement detected; no `.coverage` config or CI/CD pipeline

**View Coverage:**
```bash
# Likely command (not explicitly configured)
pytest --cov=src --cov-report=html
```

## Test Types

**Unit Tests:**
- Scope: Individual functions and classes in isolation
- Approach: Mock external dependencies (DB, file I/O)
- Examples:
  - `test_normalize_insider_name()` - tests string normalization
  - `test_classify_insider_by_rules_fund()` - tests classification logic
  - `test_cluster_score_normalization()` - tests scoring algorithm
- Typical pattern: Setup test data, call function, assert results

**Integration Tests:**
- Scope: Multi-function workflows with real data
- Approach: Use real DataFrames and business logic
- Examples:
  - `test_ratio_uses_only_available_data()` - tests temporal correctness across feature calculation
  - `test_role_weights_imported()` - verifies config integration
  - `TestConfigWeightsIntegration` class - tests centralized weights system
- Typical pattern: Create realistic data, execute multi-step logic, verify outputs

**E2E Tests:**
- Framework: Not detected
- Status: Not used in this codebase
- Database testing uses real database interaction simulation via mocking

## Common Patterns

**Async Testing:**
Not applicable (Python project uses synchronous code; no async/await detected)

**Error Testing:**
```python
# Exception handling verification (test_loader.py)
@patch('src.loaders.form345_loader.pd.read_csv')
def test_load_file_handles_read_error(mock_read_csv):
    """Verify that load_file correctly handles errors during pandas.read_csv."""
    mock_engine = MagicMock()
    mock_file_path = MagicMock()

    # Simulate an error
    mock_read_csv.side_effect = Exception("File read error")

    try:
        load_file(mock_file_path, mock_engine, table="any_table")
        assert False, "Expected an exception to be raised"
    except Exception as e:
        assert str(e) == "File read error"

    # Verify no database interaction occurred
    mock_engine.connect.assert_not_called()

@patch('src.loaders.form345_loader.pd.read_csv')
def test_load_file_handles_db_error(mock_read_csv):
    """Verify that load_file correctly handles database errors."""
    # ... setup mocks ...

    # Simulate DB error during copy_expert
    mock_cursor.copy_expert.side_effect = Exception("Database copy error")

    try:
        load_file(mock_file_path, mock_engine, table="any_table")
        assert False, "Expected an exception to be raised"
    except Exception as e:
        assert str(e) == "Database copy error"

    # Ensure commit was NOT called on failure (data integrity)
    mock_dbapi_conn.commit.assert_not_called()
```

**Parametrized Testing:**
```python
# Iteration-based parametrization (test_insider_classification.py)
def test_classify_insider_by_rules_fund():
    fund_names = [
        "ACME CAPITAL LLC",
        "GLOBAL GROWTH FUND L.P.",
        "VENTURE PARTNERS II",
        "FAMILY TRUST",
    ]

    for name in fund_names:
        result = classify_insider_by_rules(name, None)
        assert result["entity_type"] == ENTITY_FUND, f"Failed for {name}"
        assert result["is_fund_like"] is True
```

**Boundary/Edge Case Testing:**
```python
# From test_look_ahead_bias.py
def test_small_mcap_pct_adds_bonus(self):
    """0.1% of mcap should add ~5 points (with w_mcap_rel=50)."""
    adjusted = compute_market_cap_adjusted_score(70.0, 0.1)
    assert 74.5 <= adjusted <= 75.5  # Range-based assertion for floating point

def test_high_mcap_pct_capped_at_30(self):
    """Large mcap_pct should cap bonus at 30 points."""
    adjusted = compute_market_cap_adjusted_score(70.0, 1.0)
    assert adjusted == 100.0  # Final score capped at 100
```

**Print-Based Debugging in Tests:**
```python
# From test_cluster_scoring.py - used during test execution
def test_cluster_score_normalization():
    score_60 = compute_cluster_score(
        people=5,
        role_score=20,
        total_value_usd=1_000_000,
        # ... params ...
    )
    print(f"Raw ~60 case: {score_60}")
    assert 58 < score_60 < 62, f"Expected ~60, got {score_60}"
```

## Testing Best Practices Observed

1. **Test Independence:** Each test is self-contained; no shared state between tests
2. **Explicit Assertions:** Messages included in assertions for debugging (e.g., `assert result["entity_type"] == ENTITY_FUND, f"Failed for {name}"`)
3. **Isolation:** Database tests use mocking to avoid side effects
4. **Docstring Documentation:** Test docstrings explain the "why" (e.g., "Verify that sale_to_purchase_ratio only uses temporally-available data")
5. **Realistic Test Data:** When not mocking, test data mirrors real-world scenarios (e.g., temporal sequences in `test_look_ahead_bias.py`)

---

*Testing analysis: 2026-02-03*
