Context:

* We already:

  * Ingest Form 4 data into Postgres.
  * Compute **cluster buy windows** (e.g. in `scripts/show_cluster_buys.py`).
  * Distinguish **People vs Funds vs All** insiders.
  * Apply **`insider_exclusions`** to push known funds/vehicles out of the “People” list.
* The current CLI output looks roughly like this:

```text
| Ticker |   Start    |    End     | People | All | Trades |  Total Value |    Shares | Insiders          | Funds              |
|--------|------------|------------|--------|-----|--------|--------------|-----------|-------------------|--------------------|
| PTN    | 2025-06-04 | 2025-06-13 |      3 |   3 |      3 | $454,000,000 |     3,200 | ...               | —                  |
| KYMR   | 2025-06-21 | 2025-06-30 |      3 |  14 |     38 | $254,921,480 | 5,793,670 | (people)          | (BVF, LP funds...) |
| ...    |            |            |        |     |        |              |           |                   |                    |
```

### Goal

Implement:

2. A **role-based score** per cluster (`RoleScore`) derived from insider titles & roles.
3. A **strategy ranking** that uses `RoleScore`, `People`, `Funds`, and `Total Value` to order/filter cluster windows.

The goal is to prioritize clusters with **high-conviction insiders** (CFO/GC/CEO/COO/VP, etc.) over purely fund-driven clusters.

---

## 1. Add Role Weights and RoleScore

We already have, for each insider in a cluster:

* Name
* `officer_title` (raw SEC text, e.g. `"President and CEO"`, `"Executive VP and CFO/COO"`, `"Chief Compliance Officer"`)
* Boolean flags: `is_director`, `is_officer`, `is_ten_percent_owner`, `is_other`
* Classification into **People vs Funds** (People excludes funds + exclusions).

### 1.1. Define role weights

Create a **mapping** in Python to assign weights to roles:

```python
ROLE_WEIGHTS = {
    "CFO": 4,
    "CHIEF FINANCIAL OFFICER": 4,

    "GENERAL COUNSEL": 4,
    "CHIEF LEGAL OFFICER": 4,

    "COO": 3,
    "CHIEF OPERATING OFFICER": 3,

    "VP": 3,
    "VICE PRESIDENT": 3,
    "SVP": 3,
    "EVP": 3,
    "SENIOR VICE PRESIDENT": 3,
    "EXECUTIVE VICE PRESIDENT": 3,

    "CMO": 3,
    "CHIEF MARKETING OFFICER": 3,

    "CEO": 2,
    "CHIEF EXECUTIVE OFFICER": 2,
    "PRESIDENT": 2,

    "CHIEF COMPLIANCE OFFICER": 3,
    "CHIEF PORTFOLIO MANAGER": 3,

    # Fallbacks:
    "OFFICER": 1,
    "DIRECTOR": 1,
}
```

You can tweak or extend where needed, but this structure should exist in a shared place (e.g. `insider_roles.py` or within `show_cluster_buys.py` if that’s simpler for now).

### 1.2. Implement a helper: compute weight for a single insider

Create a helper function (module-level or shared):

```python
def compute_insider_role_weight(officer_title: str | None,
                                is_director: bool,
                                is_officer: bool) -> int:
    """
    Given officer_title and flags, return an integer role weight using ROLE_WEIGHTS.
    Rules:
      - Normalize officer_title to upper-case.
      - For each key in ROLE_WEIGHTS, if it appears in officer_title,
        take the MAX weight across all matches.
      - If no title-based match:
          * If is_officer: use ROLE_WEIGHTS["OFFICER"] if present, else 1
          * Elif is_director: use ROLE_WEIGHTS["DIRECTOR"] if present, else 1
          * Else: 0
      - Funds (i.e. not People) will be handled at a higher level and should not get a weight here.
    """
```

Logic:

* `title_u = (officer_title or "").upper()`
* Iterate through `ROLE_WEIGHTS` keys, check `if key in title_u`.
* Track `max_weight` among matches.
* If `max_weight == 0`:

  * If `is_officer` → fallback weight = `ROLE_WEIGHTS.get("OFFICER", 1)`
  * Else if `is_director` → fallback weight = `ROLE_WEIGHTS.get("DIRECTOR", 1)`
  * Else → 0
* Return the final integer.

### 1.3. Aggregate RoleScore per cluster window

In the cluster-building code (where you group trades into windows for `show_cluster_buys.py`):

* For each cluster window, you already have a list of **People** (not Funds) insiders.

* For each such insider, compute:

  ```python
  weight = compute_insider_role_weight(
      officer_title=insider.officer_title,
      is_director=insider.is_director,
      is_officer=insider.is_officer,
  )
  ```

* Then:

  ```python
  role_score = sum(weight for all People insiders in the cluster)
  num_key_officers = count of insiders in People with weight >= 3  # CFO/GC/COO/VP/CMO/etc.
  has_cfo = any("CFO" in (officer_title or "").upper() for People)
  has_gc  = any("GENERAL COUNSEL" in (officer_title or "").upper() or "CHIEF LEGAL OFFICER" in title for People)
  has_ceo = any("CEO" in (officer_title or "").upper() or "CHIEF EXECUTIVE OFFICER" in title for People)
  ```

Add these **per-window** fields to the in-memory representation of each cluster.

### 1.4. Expose RoleScore and key flags in CLI table

Update the `show_cluster_buys.py` output to include at least:

* A new column: `RoleScore`
* Optionally: `KeyRoles` as a compact string (e.g. `"CFO, CEO, GC"`)

For example:

```text
| Ticker | Start      | End        | People | All | Trades | Total Value   | Shares   | RoleScore | Insiders (People) | Funds |
|--------|------------|------------|--------|-----|--------|--------------:|---------:|----------:|-------------------|-------|
| PTN    | 2025-06-04 | 2025-06-13 |      3 |   3 |      3 | $454,000,000  |    3,200 |       10  | ...               | —     |
| KYMR   | 2025-06-21 | 2025-06-30 |      3 |  14 |     38 | $254,921,480  | 5,793,670|        3  | ...               | BVF.. |
```

Any compact representation is fine as long as `RoleScore` is clearly visible.

---

## 2. Strategy Ranking Logic (Sorting + Optional Filters)

We want to **rank** cluster windows by how attractive they are, based on:

* Number of People insiders
* RoleScore
* Total Value
* Fund vs People mix

### 2.1. Define a default ranking

Implement a **default sort order** for `show_cluster_buys.py`:

1. Descending `RoleScore`
2. Then descending `People`
3. Then descending `Total Value`
4. Optionally: ascending `Funds` (i.e. fewer funds is better) or by people/funds ratio.

Pseudo-sort key:

```python
sort_key = (
    role_score,         # higher first
    num_people,         # higher first
    total_value_usd,    # higher first
    -num_funds,         # fewer funds preferred
)
```

When constructing the final list of cluster windows before printing, apply this ordering by default.

### 2.2. Add CLI arguments for filters (optional but useful)

Add **optional** arguments to `scripts/show_cluster_buys.py`:

* `--min-role-score` (int, default 0)
* `--min-people` (int, default existing `--min-insiders` or leave both)
* `--max-fund-ratio` (float, optional)

  * e.g. if set to `1.0`, keep windows where `Funds / All <= 1.0`
  * If not provided, don’t filter on fund ratio.

Implement filtering approximately like:

```python
if args.min_role_score is not None and role_score < args.min_role_score:
    skip cluster

if args.min_people is not None and num_people < args.min_people:
    skip cluster

if args.max_fund_ratio is not None:
    fund_ratio = num_funds / max(all_insiders, 1)
    if fund_ratio > args.max_fund_ratio:
        skip cluster
```

You can wire these via `argparse` in the same style as existing flags (`--window-days`, `--min-insiders`, etc.).

### 2.3. Ensure People vs Funds is respected

When computing:

* `num_people` → count of **People** insiders (not including Funds or exclusions).
* `num_funds` → count of fund/investment-vehicle insiders.
* `all_insiders` → as currently defined (before classification), or the existing “All” column.

`RoleScore` should be computed **only** from People insiders, not Funds.

---

## 3. Acceptance Criteria

* [ ] Role weighting is implemented via a reusable `ROLE_WEIGHTS` mapping and `compute_insider_role_weight()` helper.
* [ ] Each cluster window now includes:

  * `role_score` (int)
  * `num_key_officers` (count of People with weight ≥ 3)
  * At least some flags: `has_cfo`, `has_gc`, `has_ceo` (can be used later in UI/filters).
* [ ] `show_cluster_buys.py` output includes a **RoleScore** column.
* [ ] Windows are **sorted by default** using a role-based strategy ranking (RoleScore, People, TotalValue, etc.).
* [ ] Optional CLI flags (`--min-role-score`, `--min-people`, `--max-fund-ratio`) allow filtering based on these new metrics.
* [ ] Funds and People classification already in place is preserved and used correctly (RoleScore only counts People).

Keep code style and structure consistent with the existing project.
