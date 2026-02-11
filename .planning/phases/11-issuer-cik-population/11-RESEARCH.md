# Phase 11: Issuer CIK Population - Research

**Researched:** 2026-02-11
**Domain:** SQL view modification, data integrity
**Confidence:** HIGH

## Summary

Phase 11 requires populating the `issuer_cik` field in scan output. The field already exists in the output schema but is currently `null` because the `insider_buy_signals` view doesn't expose the `ISSUERCIK` column from `form345_submission` table. This is a simple SQL view modification requiring no Python code changes.

**Current state:** The code in `cluster_buys.py` lines 413-433 already attempts to fetch `issuer_cik` using `_get_optional_column()`, and includes it in output at line 700. However, the column doesn't exist in the `insider_buy_signals` view, so it returns empty/null values.

**Primary recommendation:** Add `s."ISSUERCIK" AS issuer_cik` to the `insider_buy_signals` view SELECT clause (schema.sql line 270), then run a single migration to recreate the view. No Python code changes needed.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PostgreSQL | 18.1+ | Database with view support | Already in use; native SQL views |
| SQLAlchemy | Current | ORM/query builder | Already integrated; handles view introspection |
| pandas | Current | DataFrame operations | Already used for cluster analysis |

### Supporting
None - this is a pure SQL change.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQL view modification | Application-level join in Python | More complex; duplicates database logic; slower |
| SQL view modification | Denormalize into new table | Over-engineering; adds maintenance burden |

**Installation:**
No new dependencies required. Uses existing PostgreSQL setup.

## Architecture Patterns

### Recommended Project Structure
```
schema.sql              # View definition to modify
scripts/
├── scan_clusters.py    # Already handles issuer_cik output
src/analytics/
└── cluster_buys.py     # Already attempts to fetch issuer_cik
tests/
└── test_issuer_cik_population.py  # New test file
```

### Pattern 1: SQL View Column Addition
**What:** Alter a SQL view by adding a column from an already-joined table
**When to use:** When the join already exists and you need to expose an additional column
**Example:**
```sql
-- Current view (simplified)
CREATE VIEW insider_buy_signals AS
SELECT
    s."ACCESSION_NUMBER" AS accession_number,
    s."ISSUERNAME" AS issuer_name,
    s."ISSUERTRADINGSYMBOL" AS ticker
    -- Missing: s."ISSUERCIK"
FROM form345_nonderiv_trans t
JOIN form345_submission s ON s."ACCESSION_NUMBER" = t."ACCESSION_NUMBER"
WHERE t."TRANS_CODE" = 'P';

-- Updated view
CREATE OR REPLACE VIEW insider_buy_signals AS
SELECT
    s."ACCESSION_NUMBER" AS accession_number,
    s."ISSUERNAME" AS issuer_name,
    s."ISSUERTRADINGSYMBOL" AS ticker,
    s."ISSUERCIK" AS issuer_cik  -- ADD THIS LINE
FROM form345_nonderiv_trans t
JOIN form345_submission s ON s."ACCESSION_NUMBER" = t."ACCESSION_NUMBER"
WHERE t."TRANS_CODE" = 'P';
```

### Pattern 2: Safe View Migration Strategy
**What:** Recreate view with new column while preserving backward compatibility
**When to use:** When adding a nullable column to an existing view
**Example:**
```sql
-- Step 1: Drop existing view
DROP VIEW IF EXISTS public.insider_buy_signals;

-- Step 2: Recreate with new column
CREATE VIEW public.insider_buy_signals AS
SELECT
    -- existing columns...
    s."ISSUERCIK" AS issuer_cik,  -- new column
    -- more existing columns...
FROM ...;

-- Step 3: Restore ownership
ALTER VIEW public.insider_buy_signals OWNER TO myuser;
```

**Migration approach:**
Since views don't hold data (they're query definitions), dropping and recreating is safe. No data loss, no backup needed. The migration script can be a simple `.sql` file applied via `psql`.

### Pattern 3: Application-Level Handling
**What:** Python code already uses `_get_optional_column()` to safely check for column existence
**When to use:** When dealing with schema evolution where columns may or may not exist
**Example:**
```python
# From cluster_buys.py line 413
issuer_cik_col = _get_optional_column(engine, "insider_buy_signals", ("issuer_cik", "cik"))

# Later at line 595
issuer_cik = _first_nonempty_any(subset["issuer_cik"]) if "issuer_cik" in subset.columns else ""
```

**Why this pattern exists:** The code was written defensively to handle missing columns. Once we add `issuer_cik` to the view, this code will automatically start working with no changes needed.

### Anti-Patterns to Avoid
- **Adding columns without snake_case aliases:** The view uses uppercase source columns (e.g., `ISSUERCIK`) but exports lowercase aliases (e.g., `issuer_cik`). Maintain consistency.
- **Forgetting to handle nulls:** CIK values should always exist in `form345_submission`, but use defensive programming. The existing `_first_nonempty_any()` helper already handles this.
- **Changing existing column order:** Add new column after existing issuer fields (after `issuer_name`, before `insider_cik`) to maintain logical grouping.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema migrations | Custom Python migration runner | Direct SQL files via psql | PostgreSQL views are DDL; no data migration logic needed |
| Column existence checking | Try/except on DataFrame access | `_get_optional_column()` helper | Already implemented at line 57 in cluster_buys.py |
| CIK validation | Custom regex/format checker | Database constraints if needed | SEC CIK format is stable (10-digit zero-padded string) |

**Key insight:** This is a straightforward SQL view modification. The defensive Python code already exists and will work immediately once the column is available.

## Common Pitfalls

### Pitfall 1: CIK Format Assumptions
**What goes wrong:** CIKs in SEC data are numeric but stored as text with leading zeros (e.g., "0000730255"). Converting to integer loses these zeros.
**Why it happens:** Developers treat CIK as a number because it looks numeric.
**How to avoid:** Keep CIK as TEXT/VARCHAR in SQL, string in Python. Never cast to integer.
**Warning signs:** Export JSON shows CIK as `730255` instead of `"0000730255"`.

### Pitfall 2: View Dependency Breakage
**What goes wrong:** Other views or materialized views might depend on `insider_buy_signals`. Dropping it causes cascade failures.
**Why it happens:** PostgreSQL doesn't always warn about dependencies when using IF EXISTS.
**How to avoid:** Check for dependencies before migration:
```sql
SELECT dependent_view.relname
FROM pg_depend
JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid
JOIN pg_class as dependent_view ON pg_rewrite.ev_class = dependent_view.oid
WHERE pg_depend.refobjid = 'insider_buy_signals'::regclass;
```
**Warning signs:** Migration succeeds but queries fail with "relation does not exist" errors.

**Mitigation:** Check schema.sql for views that reference `insider_buy_signals`. In this codebase, no other views depend on it (verified by grep).

### Pitfall 3: Null CIKs in Output
**What goes wrong:** After adding column, some rows still have null `issuer_cik`.
**Why it happens:** Source data in `form345_submission.ISSUERCIK` might have null/empty values.
**How to avoid:** Add data quality check in test suite to verify non-null CIKs in output.
**Warning signs:** Test passes but exported JSON shows `"issuer_cik": null` for some rows.

**Mitigation:** Add validation test that scans exported JSON and asserts all rows have non-null, non-empty `issuer_cik` values.

### Pitfall 4: Case Sensitivity in Column Names
**What goes wrong:** PostgreSQL column names in raw tables are uppercase (e.g., `ISSUERCIK`) but the view aliases them to lowercase (e.g., `issuer_name`). Forgetting quotes around uppercase names causes "column does not exist" errors.
**Why it happens:** PostgreSQL folds unquoted identifiers to lowercase.
**How to avoid:** Always quote uppercase column names: `s."ISSUERCIK"` not `s.ISSUERCIK`.
**Warning signs:** SQL error: `column "issuercik" does not exist` (note the lowercase).

## Code Examples

Verified patterns from existing codebase:

### View Column Addition (Exact Change Needed)
```sql
-- Current schema.sql line 265-287
CREATE VIEW public.insider_buy_signals AS
 SELECT s."ACCESSION_NUMBER" AS accession_number,
    (s."FILING_DATE")::date AS filing_date,
    (s."PERIOD_OF_REPORT")::date AS period_of_report,
    s."ISSUERTRADINGSYMBOL" AS ticker,
    s."ISSUERNAME" AS issuer_name,
    -- ADD NEXT LINE HERE:
    s."ISSUERCIK" AS issuer_cik,
    -- THEN CONTINUE WITH:
    r."RPTOWNERCIK" AS insider_cik,
    r."RPTOWNERNAME" AS insider_name,
    r."RPTOWNER_TITLE" AS insider_title,
    r."RPTOWNER_RELATIONSHIP" AS insider_relationship,
    t."SECURITY_TITLE" AS security_title,
    (t."TRANS_DATE")::date AS transaction_date,
    t."TRANS_CODE" AS transaction_code,
    (NULLIF(t."TRANS_SHARES", ''::text))::numeric AS shares,
    (NULLIF(t."TRANS_PRICEPERSHARE", ''::text))::numeric AS price_per_share,
    ((NULLIF(t."TRANS_SHARES", ''::text))::numeric * (NULLIF(t."TRANS_PRICEPERSHARE", ''::text))::numeric) AS total_value,
    (NULLIF(t."SHRS_OWND_FOLWNG_TRANS", ''::text))::numeric AS shares_owned_after,
    t."DIRECT_INDIRECT_OWNERSHIP" AS direct_indirect,
    t."NATURE_OF_OWNERSHIP" AS nature_of_ownership
   FROM ((public.form345_nonderiv_trans t
     JOIN public.form345_submission s ON ((s."ACCESSION_NUMBER" = t."ACCESSION_NUMBER")))
     LEFT JOIN public.form345_reportingowner r ON ((r."ACCESSION_NUMBER" = s."ACCESSION_NUMBER")))
  WHERE (t."TRANS_CODE" = 'P'::text);
```

### Test: Verify CIK Population
```python
# New file: tests/test_issuer_cik_population.py
import json
import pytest
from pathlib import Path
from src.analytics.cluster_buys import get_top_cluster_buys

def test_issuer_cik_populated_in_cluster_output():
    """Verify every cluster row has non-null issuer_cik."""
    df = get_top_cluster_buys(limit=10, window_days=10, lookback_days=30)

    if df.empty:
        pytest.skip("No clusters found in test data")

    # Check DataFrame column exists
    assert "issuer_cik" in df.columns, "issuer_cik column missing from output"

    # Check all values are non-null
    null_count = df["issuer_cik"].isna().sum()
    assert null_count == 0, f"Found {null_count} null issuer_cik values"

    # Check all values are non-empty strings
    empty_count = (df["issuer_cik"] == "").sum()
    assert empty_count == 0, f"Found {empty_count} empty issuer_cik values"

def test_issuer_cik_format():
    """Verify issuer_cik values match SEC CIK format (10-digit zero-padded)."""
    df = get_top_cluster_buys(limit=5)

    if df.empty:
        pytest.skip("No clusters found in test data")

    for idx, row in df.iterrows():
        cik = row["issuer_cik"]
        # CIK should be 10 digits, possibly zero-padded
        assert cik.isdigit(), f"CIK {cik} contains non-digit characters"
        assert len(cik) == 10, f"CIK {cik} is not 10 digits (got {len(cik)})"

def test_exported_json_has_issuer_cik(tmp_path):
    """Verify exported JSON files contain issuer_cik field."""
    # This test would require refactoring scan_clusters.py to accept output_dir
    # For now, manually verify against existing exports
    export_file = Path("exports/cluster_runs/my_run.json")

    if not export_file.exists():
        pytest.skip("No export file found")

    with open(export_file) as f:
        data = json.load(f)

    rows = data.get("rows", [])
    assert len(rows) > 0, "No rows in export"

    for i, row in enumerate(rows):
        assert "issuer_cik" in row, f"Row {i} missing issuer_cik field"
        # Allow null for now (will fail after fix)
        if row["issuer_cik"] is not None:
            assert isinstance(row["issuer_cik"], str), f"Row {i} issuer_cik is not string"
```

### Migration Script
```bash
#!/bin/bash
# scripts/migrations/011_add_issuer_cik_to_view.sh

set -e

echo "Adding issuer_cik to insider_buy_signals view..."

psql $DATABASE_URL <<SQL
-- Drop and recreate view with new column
DROP VIEW IF EXISTS public.insider_buy_signals;

CREATE VIEW public.insider_buy_signals AS
 SELECT s."ACCESSION_NUMBER" AS accession_number,
    (s."FILING_DATE")::date AS filing_date,
    (s."PERIOD_OF_REPORT")::date AS period_of_report,
    s."ISSUERTRADINGSYMBOL" AS ticker,
    s."ISSUERNAME" AS issuer_name,
    s."ISSUERCIK" AS issuer_cik,
    r."RPTOWNERCIK" AS insider_cik,
    r."RPTOWNERNAME" AS insider_name,
    r."RPTOWNER_TITLE" AS insider_title,
    r."RPTOWNER_RELATIONSHIP" AS insider_relationship,
    t."SECURITY_TITLE" AS security_title,
    (t."TRANS_DATE")::date AS transaction_date,
    t."TRANS_CODE" AS transaction_code,
    (NULLIF(t."TRANS_SHARES", ''::text))::numeric AS shares,
    (NULLIF(t."TRANS_PRICEPERSHARE", ''::text))::numeric AS price_per_share,
    ((NULLIF(t."TRANS_SHARES", ''::text))::numeric * (NULLIF(t."TRANS_PRICEPERSHARE", ''::text))::numeric) AS total_value,
    (NULLIF(t."SHRS_OWND_FOLWNG_TRANS", ''::text))::numeric AS shares_owned_after,
    t."DIRECT_INDIRECT_OWNERSHIP" AS direct_indirect,
    t."NATURE_OF_OWNERSHIP" AS nature_of_ownership
   FROM ((public.form345_nonderiv_trans t
     JOIN public.form345_submission s ON ((s."ACCESSION_NUMBER" = t."ACCESSION_NUMBER")))
     LEFT JOIN public.form345_reportingowner r ON ((r."ACCESSION_NUMBER" = s."ACCESSION_NUMBER")))
  WHERE (t."TRANS_CODE" = 'P'::text);

ALTER VIEW public.insider_buy_signals OWNER TO myuser;

SELECT COUNT(*) AS row_count FROM insider_buy_signals LIMIT 1;
SQL

echo "View recreated successfully"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual column handling in Python | Defensive `_get_optional_column()` | Already implemented | Code works with or without column |
| Hard-coded column lists | Introspection-based column detection | Already implemented | No Python changes needed |

**Deprecated/outdated:**
- None - this is adding a missing column, not replacing anything.

**Current best practice:**
PostgreSQL 12+ supports `CREATE OR REPLACE VIEW` for adding columns at the end. However, adding columns in the middle (our case) still requires DROP/CREATE. This is safe for views (no data loss).

## Open Questions

1. **What percentage of form345_submission rows have null/empty ISSUERCIK?**
   - What we know: Sample data shows populated CIKs ("0000730255")
   - What's unclear: Whether all historical data has CIKs
   - Recommendation: Run data quality query before migration:
     ```sql
     SELECT
       COUNT(*) AS total_rows,
       COUNT(NULLIF("ISSUERCIK", '')) AS populated_ciks,
       COUNT(*) - COUNT(NULLIF("ISSUERCIK", '')) AS missing_ciks
     FROM form345_submission;
     ```

2. **Are there any dependent views or materialized views?**
   - What we know: Grep shows no other views reference `insider_buy_signals`
   - What's unclear: Runtime-created views or external dependencies
   - Recommendation: Run dependency check query before migration (see Pitfall 2)

3. **Should CIK be indexed for join performance?**
   - What we know: Current view doesn't use CIK in JOIN or WHERE clauses
   - What's unclear: Whether future phases will join on CIK
   - Recommendation: Add index only if Phase 12+ requires CIK joins

## Sources

### Primary (HIGH confidence)
- Codebase files:
  - `/home/laudes/zoot/projects/get-insider-db/schema.sql` lines 240-290 - Table and view definitions
  - `/home/laudes/zoot/projects/get-insider-db/src/analytics/cluster_buys.py` lines 413-433, 595-600 - CIK handling code
  - `/home/laudes/zoot/projects/get-insider-db/data/extracted/2020q3_form345/SUBMISSION.tsv` - Sample data showing CIK format
  - `/home/laudes/zoot/projects/get-insider-db/exports/cluster_runs/my_run.json` - Current output showing null CIKs
- PostgreSQL 18.1 documentation - View modification syntax

### Secondary (MEDIUM confidence)
- `.planning/REQUIREMENTS.md` - DATA-02 requirement specification
- `.planning/ROADMAP.md` - Phase 11 success criteria

### Tertiary (LOW confidence)
None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Pure SQL change, no new dependencies
- Architecture: HIGH - Single view modification, existing code handles it
- Pitfalls: HIGH - CIK format and null handling are well-documented in codebase

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (30 days - stable domain)
