# Phase 14: Float Rounding - Research

**Researched:** 2026-02-11
**Domain:** Python JSON serialization and pandas DataFrame numeric formatting
**Confidence:** HIGH

## Summary

Phase 14 implements floating-point rounding for JSON exports to improve readability and consistency. The current implementation already rounds `cluster_score` and `avg_percent_change` to 2 decimals (line 334 in `scan_clusters.py`), but several float fields still serialize with full precision (e.g., `avg_days_to_file: 0.8333333333333334`).

**Primary recommendation:** Extend existing pandas `.round(2)` approach to cover all float columns before JSON export. This is a simple, low-risk change that maintains internal calculation precision while cleaning output.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | (current) | DataFrame manipulation | Already used throughout codebase for data operations |
| json (stdlib) | Python 3.x | JSON serialization | Standard library, no dependencies |

### No Additional Dependencies Required
This phase extends existing pandas usage. No new libraries needed.

## Architecture Patterns

### Current Implementation Pattern

**Location:** `scripts/scan_clusters.py:332-334`

```python
# Remove console-only annotation columns from JSON export
for col in ("duplicate_count", "duplicate_rank"):
    if col in out_df.columns:
        out_df = out_df.drop(columns=[col])

# EXISTING: Partial rounding (cluster_score, avg_percent_change)
for col in ("cluster_score", "avg_percent_change"):
    if col in out_df.columns:
        out_df[col] = out_df[col].round(2)
```

**Gap:** Missing fields: `avg_days_to_file`, `fund_ratio`, `avg_sale_to_purchase_ratio`

### Recommended Pattern: Column List Approach

```python
# Round all float fields for export readability (OUT-02)
FLOAT_FIELDS_TO_ROUND = [
    "cluster_score",
    "avg_percent_change",
    "avg_days_to_file",
    "fund_ratio",
    "avg_sale_to_purchase_ratio",
]

for col in FLOAT_FIELDS_TO_ROUND:
    if col in out_df.columns:
        out_df[col] = out_df[col].round(2)
```

**Rationale:**
- Explicit list documents which fields get rounded
- Easy to verify against requirement (OUT-02)
- Consistent with existing code style
- Safe: only operates on columns that exist

### Fields NOT Rounded

**Preserve full precision:**
- `total_shares`: Integer-valued, display uses `.0f` formatter
- `total_value`: Currency, display uses `.0f` formatter
- **Rationale:** These are large absolute values where 2 decimals don't improve readability (e.g., `$1,234,567.89` adds noise vs `$1,234,568`)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON float formatting | Custom JSONEncoder | pandas `.round()` | DataFrame already in memory, simpler, less code |
| Numeric precision control | String formatting in loop | Pandas vectorized round | Faster, cleaner, fewer edge cases |

**Key insight:** Pandas `.round()` is vectorized and handles edge cases (NaN, inf) correctly. Custom encoders add complexity without benefit.

## Common Pitfalls

### Pitfall 1: Rounding Before Calculations
**What goes wrong:** Applying `.round()` to DataFrames used for downstream calculations causes precision loss
**Why it happens:** Confusing "export DataFrame" with "calculation DataFrame"
**How to avoid:** Always copy DataFrame before rounding (`out_df = df.copy()` already exists at line 325)
**Warning signs:** Test failures showing incorrect calculations, precision-sensitive operations

### Pitfall 2: Forgetting New Float Columns
**What goes wrong:** Future code adds new float fields, they don't get rounded
**Why it happens:** No documentation of which fields are float-typed
**How to avoid:**
- Add comment listing expected float fields above rounding code
- Verify with test: "all float fields in export are rounded"
**Warning signs:** New exports with 15-decimal values

### Pitfall 3: Over-Rounding Display vs Storage
**What goes wrong:** Rounding fields like `total_value` to 2 decimals (e.g., `$1234.56`) makes large values less readable
**Why it happens:** Blanket "round all floats" approach
**How to avoid:** Distinguish between "precision fields" (ratios, scores) and "magnitude fields" (currency, shares)
**Warning signs:** Export shows `$1234567.89` instead of cleaner `$1,234,568`

## Code Examples

Verified patterns from codebase:

### Current Partial Implementation
```python
# Source: scripts/scan_clusters.py:325-334
out_df = df.copy()

# Remove console-only annotation columns from JSON export
for col in ("duplicate_count", "duplicate_rank"):
    if col in out_df.columns:
        out_df = out_df.drop(columns=[col])

for col in ("cluster_score", "avg_percent_change"):
    if col in out_df.columns:
        out_df[col] = out_df[col].round(2)
```

### Recommended Complete Implementation
```python
# Source: Research recommendation
out_df = df.copy()

# Remove console-only annotation columns from JSON export
for col in ("duplicate_count", "duplicate_rank"):
    if col in out_df.columns:
        out_df = out_df.drop(columns=[col])

# Round all floating-point fields to 2 decimals (OUT-02)
# Fields: cluster_score, avg_percent_change, avg_days_to_file,
#         fund_ratio, avg_sale_to_purchase_ratio
FLOAT_FIELDS_TO_ROUND = [
    "cluster_score",
    "avg_percent_change",
    "avg_days_to_file",
    "fund_ratio",
    "avg_sale_to_purchase_ratio",
]
for col in FLOAT_FIELDS_TO_ROUND:
    if col in out_df.columns:
        out_df[col] = out_df[col].round(2)
```

### Verification Pattern (Test)
```python
# Test: All expected float fields are rounded to 2 decimals
def test_float_rounding_in_export():
    # Run scan_clusters with known data
    result = subprocess.run([...], capture_output=True)

    # Load JSON export
    data = json.loads(Path(export_file).read_text())

    # Verify rounding for all float fields
    EXPECTED_FLOAT_FIELDS = [
        "cluster_score",
        "avg_percent_change",
        "avg_days_to_file",
        "fund_ratio",
        "avg_sale_to_purchase_ratio",
    ]

    for row in data["rows"]:
        for field in EXPECTED_FLOAT_FIELDS:
            if field in row and isinstance(row[field], float):
                # Check max 2 decimal places
                str_val = f"{row[field]:.10f}"  # High precision string
                decimal_part = str_val.split(".")[1].rstrip("0")
                assert len(decimal_part) <= 2, \
                    f"{field}={row[field]} has >{2} decimals"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No rounding | Partial rounding (2 of 5 fields) | Phase 13 (2026-02-11) | Some fields still show full precision |
| N/A | Need full rounding (all 5 fields) | Phase 14 (this phase) | Complete export readability |

**Deprecated/outdated:** None - this is a new requirement (OUT-02)

## Field Inventory

From actual export inspection (`exports/cluster_runs/*.json`):

**Float fields requiring 2-decimal rounding (OUT-02):**
1. `cluster_score` - Already rounded ✓
2. `avg_percent_change` - Already rounded ✓
3. `avg_days_to_file` - **Needs rounding** (currently: `0.8333333333333334`)
4. `fund_ratio` - **Needs rounding** (currently: `0.0`, but could be `0.2499999`)
5. `avg_sale_to_purchase_ratio` - **Needs rounding** (currently: `0.0`, but variable)

**Float fields NOT requiring rounding:**
- `total_shares`: Display uses `.0f` formatter (integer magnitude)
- `total_value`: Display uses `.0f` formatter (currency magnitude)

**Integer fields (no action needed):**
- `num_trades`, `num_insiders`, `num_total_insiders`, `num_fund_like`
- `role_score`, `num_key_officers`

**String/Date fields (no action needed):**
- `ticker`, `issuer_cik`, `issuer_name`
- `window_start`, `window_end`, `signal_filing_date`, `entry_date`
- `top_insiders`, `fund_like_insiders`, `key_roles`

**Boolean fields (no action needed):**
- `has_cfo`, `has_gc`, `has_ceo`

## Testing Strategy

### Boundary Cases
1. **NaN handling**: Verify `.round(2)` preserves NaN (doesn't crash or convert to 0)
2. **Zero values**: `0.0` → `0.0` (verify no precision artifacts like `0.00000001`)
3. **Precision edge**: `0.999` → `1.0` (standard rounding rules apply)
4. **Negative values**: If any (verify sign preserved)

### Integration Test
**Scenario:** Run `scan_clusters.py`, verify JSON export has all float fields rounded

```bash
python scripts/scan_clusters.py --limit 5 --basename test_rounding
# Inspect: exports/cluster_runs/test_rounding.json
# Verify: avg_days_to_file shows 2 decimals max
```

## Open Questions

None - implementation path is clear:
1. Extend existing rounding code to cover 3 additional fields
2. Add test to verify all 5 fields are rounded
3. No breaking changes (internal calculations unaffected)

## Sources

### Primary (HIGH confidence)
- **Codebase inspection**: `scripts/scan_clusters.py:332-334` (existing partial implementation)
- **Live export data**: `exports/cluster_runs/*.json` (field types and current precision)
- **Requirements**: `.planning/REQUIREMENTS.md` OUT-02 specification
- **Pandas documentation**: `DataFrame.round()` behavior (standard library)

### Testing
- **Python stdlib**: `json.dumps()` serialization behavior verified via REPL testing
- **Pandas round behavior**: Verified via REPL with sample data matching production patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies, extending existing pandas usage
- Architecture: HIGH - Simple extension of existing pattern at line 334
- Pitfalls: HIGH - Field inventory complete, test strategy clear

**Research date:** 2026-02-11
**Valid until:** 90 days (stable requirement, unlikely to change)
