# Phase 12: Sale-to-Purchase Ratio Debug - Research

**Researched:** 2026-02-11
**Domain:** Data pipeline debugging, SQL view design, pandas feature engineering
**Confidence:** HIGH

## Summary

The sale-to-purchase ratio feature is always 0.0 because the `insider_buy_signals` view filters to ONLY purchases (WHERE transaction_code='P'), excluding all sales transactions. The feature calculation in `calculate_sale_to_purchase_ratio()` attempts to compute a ratio using transaction_code='S' (sales) and 'P' (purchases), but when the input dataframe contains only purchases, the sales sum is always zero, yielding ratio=0.0.

This is a **data availability problem**, not a calculation logic error. The feature engineering code is correct, but it operates on a filtered dataset that excludes the very data it needs.

**Primary recommendation:** Create a separate view or modify the data loading query to include BOTH purchase and sale transactions for the lookback period calculation, while maintaining the purchase-only filter for cluster detection itself.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.x-3.0 | Dataframe operations for feature engineering | Industry standard for Python data manipulation |
| SQLAlchemy | 2.x | Database ORM and query interface | Standard Python SQL toolkit with broad ecosystem support |
| PostgreSQL | 18.x | Primary database | ACID-compliant RDBMS with excellent view support |
| pytest | 8.x | Testing framework | De facto standard for Python testing |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | Current | Structured logging | Already in use for diagnostic logging |
| psycopg2 | 2.x | PostgreSQL driver | SQLAlchemy backend for PostgreSQL |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Separate view | Modify existing view | Separate view preserves existing API contracts; modified view affects all consumers |
| SQL UNION | Pandas concat | SQL UNION is more efficient for database-resident data; pandas gives more control |
| CTE | Subquery | CTE is more readable for complex multi-stage queries; subquery may perform slightly better |

**Installation:**
```bash
# Already installed in project
pip install -r requirements.txt
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── analytics/
│   ├── feature_engineering.py  # Feature calculation functions
│   └── cluster_buys.py        # Main cluster detection logic
├── scoring_config/
│   └── scoring_weights.py     # Centralized configuration
└── models.py                  # SQLAlchemy models
schema.sql                     # Database DDL (views, tables, indexes)
tests/
└── test_feature_engineering.py # Feature calculation tests
```

### Pattern 1: Filtered View with Full-Data Subquery
**What:** Primary view filters to signal type (purchases), but dependent calculations query the base table directly for full context.

**When to use:** When you need a focused view for one purpose (cluster detection) but need broader data for supporting calculations (ratio features).

**Example:**
```sql
-- Current: insider_buy_signals view (purchases only)
CREATE VIEW insider_buy_signals AS
  SELECT ...
  FROM form345_nonderiv_trans t
  WHERE t.transaction_code = 'P';

-- Solution: Keep view as-is, create helper view for ratio calculation
CREATE VIEW insider_all_signals AS
  SELECT ...
  FROM form345_nonderiv_trans t
  WHERE t.transaction_code IN ('P', 'S');
```

**Alternative approach (in Python):**
```python
# Load broader dataset for feature calculation
base_sql = """
    SELECT ... FROM form345_nonderiv_trans
    WHERE transaction_code IN ('P', 'S')
      AND filing_date BETWEEN :start AND :end
"""
# Then filter to purchases for cluster detection
purchase_only = base_df[base_df['transaction_code'] == 'P']
```

### Pattern 2: Lookback Window Feature Engineering
**What:** Calculate features using data from a time window BEFORE the signal, ensuring temporal safety.

**When to use:** For any feature that depends on historical behavior (avg_days_to_file, sale_to_purchase_ratio, etc.).

**Example:**
```python
# From feature_engineering.py - correct implementation
def calculate_sale_to_purchase_ratio(df: pd.DataFrame, lookback_days: int = 90) -> pd.DataFrame:
    """
    Rolling window approach: For each row, calculate ratio using only
    transactions in [transaction_date - lookback_days, transaction_date].
    """
    # Sliding window algorithm maintains sales_sum and purchase_sum
    # by adding new transactions and removing expired ones
    for right in range(len(group)):
        # Add current transaction to window
        if code_r == "S":
            sales_sum += share_r
        elif code_r == "P":
            purchase_sum += share_r

        # Remove expired transactions from window
        lookback_start = dates[right] - lookback_delta
        while left <= right and dates[left] < lookback_start:
            # Subtract shares from expired transaction
            ...

        ratios.append((sales_sum / purchase_sum) if purchase_sum > 0 else 0.0)
```

### Pattern 3: Temporal Safety in Feature Calculation
**What:** Features calculated at signal time must use ONLY data available at that time (filing_date boundary).

**When to use:** Always, when calculating tradeable signals. Already correctly implemented in `cluster_buys.py:604-621`.

**Example:**
```python
# From cluster_buys.py (correct temporal safety)
signal_filing_date = subset["filing_date"].max().date()

# Filter to filings known at signal_filing_date to avoid look-ahead bias
temporally_safe_df = ticker_rows[
    ticker_rows["filing_date"].dt.date <= signal_filing_date
]
temporally_safe_df = calculate_sale_to_purchase_ratio(
    temporally_safe_df.copy(),
    lookback_days=lookback_days
)
```

### Anti-Patterns to Avoid
- **Assuming filtered views contain all needed data**: Always verify the WHERE clause of views before using for feature engineering
- **Silent zero fallbacks**: When a ratio is unexpectedly zero, it could indicate missing data, not actual zero behavior
- **Testing calculation logic without data availability checks**: Test that input data contains the expected transaction types BEFORE testing calculation

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SQL view introspection | Custom column detection | SQLAlchemy inspect() | Already used in `_get_optional_column()` - handles all edge cases |
| Rolling window calculations | Nested loops | Pandas rolling() OR sliding window pattern | Feature engineering already uses optimized sliding window (O(n) not O(n²)) |
| Division by zero handling | try/except blocks | Conditional expression `(a/b) if b > 0 else 0.0` | More explicit, no exception overhead |
| Test data setup | Manual SQL inserts | pytest fixtures with dataclasses | Maintainable, type-safe test data |

**Key insight:** The existing sliding window implementation in `calculate_sale_to_purchase_ratio()` is already optimized and correct. The problem is not the algorithm, it's the input data filtering.

## Common Pitfalls

### Pitfall 1: View WHERE Clause Hides Missing Data
**What goes wrong:** A calculation expects both sales and purchases, but the source view filters to purchases only (WHERE transaction_code='P'). The calculation runs without error but produces meaningless results (ratio always 0.0).

**Why it happens:** Views abstract the underlying filter logic. Developers see `insider_buy_signals` and assume it contains all signal-relevant data, missing that it excludes sales.

**How to avoid:**
1. Document view filters prominently in CLAUDE.md and schema comments
2. Add data validation checks: `assert 'S' in df['transaction_code'].values, "Missing sales data for ratio calculation"`
3. Use explicit naming: `insider_purchase_signals` instead of `insider_buy_signals` makes the filter obvious

**Warning signs:**
- Feature is always zero despite known historical sales activity
- Feature works in tests (which often use broader synthetic data) but fails in production
- No errors or warnings, just silent zero values

### Pitfall 2: Testing Calculation Logic Without Testing Data Availability
**What goes wrong:** Unit tests verify the ratio calculation formula works correctly with synthetic data containing both 'P' and 'S' codes, but production data source lacks 'S' codes entirely. Tests pass, production fails silently.

**Why it happens:** Tests focus on algorithmic correctness, not data pipeline integrity.

**How to avoid:**
1. Add integration tests that use actual views/queries, not synthetic dataframes
2. Test edge case: What happens when input has ZERO sales transactions?
3. Add assertions about expected transaction_code distribution

**Warning signs:**
- Unit tests pass, but exploratory queries show unexpected distributions
- Feature values don't match manual SQL calculations
- Test data is "too clean" compared to production queries

### Pitfall 3: Look-Ahead Bias in Temporal Filtering
**What goes wrong:** Feature calculation uses transactions filed AFTER the signal date, incorporating future information not available at signal time.

**Why it happens:** Forgetting to filter by `filing_date <= signal_filing_date` before calculating lookback features.

**How to avoid:**
- Already correctly implemented in this codebase (lines 604-621 of cluster_buys.py)
- Test with assertion: `assert all(df['filing_date'] <= signal_date)`
- Document temporal boundaries clearly in function docstrings

**Warning signs:**
- Backtest performance is suspiciously good (using future data)
- Features change when re-running historical analysis (temporal instability)
- `test_look_ahead_bias.py` fails

### Pitfall 4: Division by Zero in Ratio Calculations
**What goes wrong:** When purchase_sum is zero, division raises ZeroDivisionError or produces NaN/Inf.

**Why it happens:** Not all time windows contain purchase transactions.

**How to avoid:**
- Use conditional: `(sales / purchases) if purchases > 0 else 0.0`
- Already correctly implemented in `calculate_sale_to_purchase_ratio()` line 65
- Consider: Should zero purchases return 0.0, or np.nan to signal "undefined"?

**Warning signs:**
- Crashes in feature engineering
- Inf or NaN values in cluster exports

## Code Examples

Verified patterns from codebase:

### Correct Sliding Window Ratio Calculation
```python
# Source: src/analytics/feature_engineering.py lines 42-65
# O(n) sliding window - maintains running sums efficiently
left = 0
sales_sum = 0.0
purchase_sum = 0.0
ratios: list[float] = []

for right in range(len(group)):
    code_r = codes[right]
    share_r = float(shares[right])
    # Add current transaction to window
    if code_r == "S":
        sales_sum += share_r
    elif code_r == "P":
        purchase_sum += share_r

    # Remove expired transactions (before lookback window)
    lookback_start = dates[right] - lookback_delta
    while left <= right and dates[left] < lookback_start:
        code_l = codes[left]
        share_l = float(shares[left])
        if code_l == "S":
            sales_sum -= share_l
        elif code_l == "P":
            purchase_sum -= share_l
        left += 1

    # Calculate ratio with zero-division guard
    ratios.append((sales_sum / purchase_sum) if purchase_sum > 0 else 0.0)
```

### Correct Temporal Filtering for Look-Ahead Safety
```python
# Source: src/analytics/cluster_buys.py lines 604-621
# Calculate sale_to_purchase_ratio using only temporally-available data
# Filter to filings known at signal_filing_date to avoid look-ahead bias
signal_filing_date = subset["filing_date"].max().date()

temporally_safe_df = ticker_rows[
    ticker_rows["filing_date"].dt.date <= signal_filing_date
]
temporally_safe_df = calculate_sale_to_purchase_ratio(
    temporally_safe_df.copy(),
    lookback_days=lookback_days
)
```

### Data Validation Check (Recommended Addition)
```python
# Add to cluster_buys.py after loading base_df
# Validate data contains both transaction types for ratio calculation
if 'transaction_code' in base_df.columns:
    codes = base_df['transaction_code'].unique()
    if 'S' not in codes:
        logger.warning(
            "no_sales_transactions_for_ratio",
            available_codes=codes.tolist(),
            note="sale_to_purchase_ratio will be 0.0 for all rows"
        )
```

### SQL View Pattern for Full Transaction Access
```sql
-- Option 1: Create new view (recommended - preserves existing contracts)
CREATE VIEW insider_all_signals AS
 SELECT
    s.ACCESSION_NUMBER AS accession_number,
    s.FILING_DATE::date AS filing_date,
    s.ISSUERTRADINGSYMBOL AS ticker,
    r.RPTOWNERNAME AS insider_name,
    t.TRANS_DATE::date AS transaction_date,
    t.TRANS_CODE AS transaction_code,  -- 'P' or 'S'
    t.TRANS_SHARES::numeric AS shares,
    t.TRANS_PRICEPERSHARE::numeric AS price_per_share,
    (t.TRANS_SHARES::numeric * t.TRANS_PRICEPERSHARE::numeric) AS total_value
   FROM form345_nonderiv_trans t
   JOIN form345_submission s ON s.ACCESSION_NUMBER = t.ACCESSION_NUMBER
   LEFT JOIN form345_reportingowner r ON r.ACCESSION_NUMBER = s.ACCESSION_NUMBER
   WHERE t.TRANS_CODE IN ('P', 'S');  -- Include both purchases and sales

-- Then use this view for ratio calculation lookback data
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Inline ratio calculation in SQL | Pandas sliding window in Python | Initial implementation | Better testability, temporal safety, O(n) efficiency |
| Global config scattered across functions | Centralized `scoring_weights.py` | Phase 07 | Single source of truth for all parameters |
| Ad-hoc feature engineering | Dedicated `feature_engineering.py` module | Phase 07+ | Separation of concerns, reusable functions |

**Deprecated/outdated:**
- N/A - This is a new feature being debugged, not replacing old functionality

## Open Questions

1. **Should ratio be 0.0 or NaN when no sales exist?**
   - What we know: Current implementation returns 0.0 when sales_sum=0
   - What's unclear: Does 0.0 mean "no selling behavior" or "insufficient data to calculate"?
   - Recommendation: Keep 0.0 for now (simpler scoring), but document this semantic clearly in docstring

2. **Should we modify the existing view or create a new one?**
   - What we know: `insider_buy_signals` is used throughout codebase for cluster detection
   - What's unclear: Impact of modifying WHERE clause on existing consumers
   - Recommendation: Create NEW view `insider_all_signals` (safer, preserves contracts)

3. **What is the expected non-zero rate for this feature?**
   - What we know: Insiders can sell shares, but most Form 4 filings are purchases
   - What's unclear: Typical ratio distribution (10% non-zero? 50%?)
   - Recommendation: Query raw data to establish baseline expectations: `SELECT COUNT(*) FROM form345_nonderiv_trans WHERE TRANS_CODE='S'`

4. **Should the feature window match cluster detection window?**
   - What we know: Cluster window is 10 days, ratio lookback is 120 days
   - What's unclear: Is 120-day lookback appropriate for a 10-day cluster signal?
   - Recommendation: Keep 120 days (captures longer-term selling patterns), document rationale

## Sources

### Primary (HIGH confidence)
- Project codebase: `src/analytics/feature_engineering.py` (lines 13-76) - Implementation of `calculate_sale_to_purchase_ratio()`
- Project codebase: `src/analytics/cluster_buys.py` (lines 604-621) - Temporal filtering for ratio calculation
- Project codebase: `schema.sql` (line 288) - `insider_buy_signals` view WHERE clause filter
- Project exports: `exports/cluster_runs/*.json` - Confirmed all `avg_sale_to_purchase_ratio` values are 0.0

### Secondary (MEDIUM confidence)
- [Debugging missing data in SQL query results | Metabase Learn](https://www.metabase.com/learn/sql/debugging-sql/sql-logic-missing-data) - Systematic approach to diagnosing missing data in SQL views
- [pandas.DataFrame.rolling documentation](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.rolling.html) - Rolling window patterns and edge case handling
- [Advanced Feature Engineering with Pandas groupby | Medium](https://medium.com/@tzhaonj/advanced-feature-engineering-with-pandas-groupby-bdf4cd3a86a6) - Feature engineering patterns and debugging

### Tertiary (LOW confidence - needs verification)
- N/A

## Metadata

**Confidence breakdown:**
- Root cause identification: HIGH - Verified via schema.sql line 288 and export data analysis
- Fix approach (separate view): HIGH - Standard SQL pattern, preserves existing contracts
- Feature calculation correctness: HIGH - Code review confirms sliding window logic is correct
- Test strategy: MEDIUM - Pytest patterns identified, need to verify against project conventions

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (30 days - stable domain, SQL/pandas patterns don't change rapidly)
