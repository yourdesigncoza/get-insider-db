# Sector Column + SEC Links Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a sector column (SIC description from `sector_lookup` table) and a `--links` flag (SEC EDGAR filing URLs) to the insider cluster dashboard, with blocked sectors filtered by default.

**Architecture:** Add `load_sector_map()` to the shared services module to batch-fetch SIC data. Dashboard joins sector data, filters blocked SIC codes via existing `is_sic_blocked()`, adds a "Sector" column, and optionally prints SEC filing URLs below the table.

**Tech Stack:** Python, SQLAlchemy, Rich, existing `sector_lookup` table (8,982 rows), existing `sector_blocklist.py`

---

## Context

- `sector_lookup` table: keyed on `issuer_cik`, has `sic_code` (TEXT), `sic_description` (TEXT). 8,982 rows populated via `scripts/populate_sector_lookup.py`.
- `src/scoring_config/sector_blocklist.py`: `is_sic_blocked(sic_code: int) -> tuple[bool, str | None]` checks if a SIC code falls in the Edenfintech avoid-list. Takes an int.
- SEC EDGAR company filing URL format: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_padded}&type=4&dateb=&owner=include&count=10` where `cik_padded` is zero-padded to 10 digits.
- Permissive unknown policy: clusters without a `sector_lookup` row pass through (not blocked).

---

### Task 1: Add `load_sector_map()` to shared services

**Files:**
- Modify: `src/services/cluster_detection_fast.py`
- Test: `tests/test_cluster_detection_fast.py`

**Step 1: Write the test**

Create `tests/test_cluster_detection_fast.py`:

```python
import pytest
from unittest.mock import MagicMock
from src.services.cluster_detection_fast import load_sector_map


def test_load_sector_map_returns_dict():
    """load_sector_map returns {issuer_cik: {sic_code, sic_description}}."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = lambda s: mock_conn
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    # Simulate DB rows: (issuer_cik, sic_code, sic_description)
    mock_conn.execute.return_value.fetchall.return_value = [
        ("0001234567", "4911", "Electric Services"),
        ("0007654321", "7372", "Prepackaged Software"),
    ]

    result = load_sector_map(mock_engine)

    assert result["0001234567"]["sic_code"] == "4911"
    assert result["0001234567"]["sic_description"] == "Electric Services"
    assert result["0007654321"]["sic_description"] == "Prepackaged Software"
    assert "9999999999" not in result


def test_load_sector_map_empty():
    """load_sector_map returns empty dict when table is empty."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = lambda s: mock_conn
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.fetchall.return_value = []

    result = load_sector_map(mock_engine)
    assert result == {}
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cluster_detection_fast.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_sector_map'`

**Step 3: Implement `load_sector_map()`**

Add to `src/services/cluster_detection_fast.py` (after `resolve_ticker`):

```python
def load_sector_map(engine: Engine) -> dict[str, dict]:
    """Load issuer_cik -> {sic_code, sic_description} from sector_lookup."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT issuer_cik, sic_code, sic_description FROM sector_lookup"
        )).fetchall()
    return {
        r[0]: {"sic_code": r[1], "sic_description": r[2]}
        for r in rows
    }
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cluster_detection_fast.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/services/cluster_detection_fast.py tests/test_cluster_detection_fast.py
git commit -m "feat: add load_sector_map() to shared services"
```

---

### Task 2: Add sector column and blocklist filter to dashboard

**Files:**
- Modify: `scripts/dashboard.py`

**Step 1: Add imports**

At top of `scripts/dashboard.py`, add to the `cluster_detection_fast` import block:

```python
from src.services.cluster_detection_fast import (
    detect_clusters_fast,
    load_cik_ticker_map,
    load_sector_map,
    resolve_ticker,
)
```

And add:

```python
from src.scoring_config.sector_blocklist import is_sic_blocked
```

**Step 2: Add CLI flags**

In `main()`, add after the `--json` argument:

```python
parser.add_argument(
    "--no-sector-filter", action="store_true",
    help="Disable sector blocklist filtering (blocked sectors hidden by default)",
)
```

**Step 3: Load sector map in `main()`**

After `cik_map = load_cik_ticker_map(engine)`, add:

```python
sector_map = load_sector_map(engine)
```

**Step 4: Apply sector blocklist filter**

After the `max_value_per_insider` filter block (line ~182) and before the deduplication block, add:

```python
# 3b. Filter blocked sectors (unless --no-sector-filter)
if not args.no_sector_filter:
    filtered = []
    for c in clusters:
        sector_info = sector_map.get(c["issuer_cik"])
        if sector_info and sector_info["sic_code"]:
            try:
                blocked, _ = is_sic_blocked(int(sector_info["sic_code"]))
            except (ValueError, TypeError):
                blocked = False
            if blocked:
                continue
        filtered.append(c)
    clusters = filtered
```

**Step 5: Pass `sector_map` to `build_dashboard_rows` and `print_rich_table`**

Update the `build_dashboard_rows` call:

```python
rows = build_dashboard_rows(clusters, cik_map, rates, sector_map)
```

**Step 6: Update `build_dashboard_rows` signature and logic**

Change function signature to accept `sector_map`:

```python
def build_dashboard_rows(clusters, cik_map, rates, sector_map):
```

Inside the loop, after `resolved = resolve_ticker(c, cik_map)`, add:

```python
sector_info = sector_map.get(c["issuer_cik"], {})
sector_label = sector_info.get("sic_description", "")
```

Add `"sector": sector_label` to the row dict.

**Step 7: Add "Sector" column to Rich table**

In `print_rich_table`, add after the "Ticker" column:

```python
table.add_column("Sector", justify="left", no_wrap=True)
```

In the `for r in rows` loop, add `_truncate(r.get("sector", ""), 25)` as the second value in `table.add_row()` (after ticker, before CIK).

**Step 8: Test manually**

Run: `python3 scripts/dashboard.py --days-back 60`
Expected: Rich table with "Sector" column showing SIC descriptions, blocked sectors filtered out.

Run: `python3 scripts/dashboard.py --days-back 60 --no-sector-filter`
Expected: Same but with blocked sectors included.

**Step 9: Commit**

```bash
git add scripts/dashboard.py
git commit -m "feat: add sector column and blocklist filter to dashboard"
```

---

### Task 3: Add `--links` flag for SEC EDGAR URLs

**Files:**
- Modify: `scripts/dashboard.py`

**Step 1: Add CLI flag**

In `main()`, add after `--no-sector-filter`:

```python
parser.add_argument(
    "--links", action="store_true",
    help="Print SEC EDGAR filing links below the table",
)
```

**Step 2: Create link builder function**

Add after `_truncate`:

```python
def _sec_edgar_url(issuer_cik: str) -> str:
    """Build SEC EDGAR Form 4 filing search URL for a CIK."""
    padded = issuer_cik.zfill(10)
    return (
        f"https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcompany&CIK={padded}&type=4"
        f"&dateb=&owner=include&count=10"
    )
```

**Step 3: Create link printer function**

Add after `_sec_edgar_url`:

```python
def print_sec_links(rows):
    """Print SEC EDGAR filing links for each cluster."""
    console = Console()
    console.print()
    console.rule("[bold]SEC Filing Links[/bold]")
    console.print()
    for r in rows:
        ticker = r["display_ticker"]
        url = _sec_edgar_url(r["issuer_cik"])
        console.print(f"  {ticker:8s} {url}")
    console.print()
```

**Step 4: Wire into `main()`**

After `print_rich_table(rows, args.days_back, rates)` (the else branch), add:

```python
if args.links:
    print_sec_links(rows)
```

Also add links to JSON output — in the JSON rows, add `"sec_url"` field. In `build_dashboard_rows`, add to the row dict:

```python
"sec_url": _sec_edgar_url(c["issuer_cik"]),
```

But only compute when needed — actually just always include it, it's cheap.

**Step 5: Test manually**

Run: `python3 scripts/dashboard.py --days-back 60 --links`
Expected: Rich table followed by "SEC Filing Links" section with one URL per cluster.

Run: `python3 scripts/dashboard.py --days-back 60 --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['rows'][0].get('sec_url','MISSING'))"`
Expected: Prints a SEC URL.

**Step 6: Commit**

```bash
git add scripts/dashboard.py
git commit -m "feat: add --links flag for SEC EDGAR filing URLs"
```

---

### Task 4: Update README and run full tests

**Files:**
- Modify: `README.md`

**Step 1: Update README dashboard section**

In the Key flags list under the Dashboard section, add:
- `--no-sector-filter` — disable sector blocklist (blocked sectors hidden by default)
- `--links` — print SEC EDGAR filing links below the table

**Step 2: Run full test suite**

Run: `python3 -m pytest tests/ -v --tb=short`
Expected: 209+ pass (207 existing + 2 new), 23 pre-existing failures unchanged.

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add sector filter and links flags to README"
```

---

## Key Files Reference

| File | Role |
|------|------|
| `src/services/cluster_detection_fast.py` | MODIFY — add `load_sector_map()` |
| `scripts/dashboard.py` | MODIFY — sector column, blocklist filter, --links, --no-sector-filter |
| `src/scoring_config/sector_blocklist.py` | REUSE — `is_sic_blocked()` |
| `tests/test_cluster_detection_fast.py` | CREATE — tests for `load_sector_map()` |
| `README.md` | MODIFY — document new flags |
