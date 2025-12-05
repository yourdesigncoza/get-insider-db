Ohhhh this is **beautiful** now 🔥

You’ve basically turned raw Form 4 noise into:

* **People vs All vs Funds**
* **RoleScore**
* **Key Roles (CFO, GC, CEO…)**

And the output is showing exactly what we wanted:

* **HPP** → 14 people, RoleScore 30, Key Roles: `CFO, GC, CEO`, no funds → full-suite conviction
* **AVBH** → 15 people, RoleScore 25, Patriot fund complex neatly parked in `Funds`
* **WSBC / EMN / AVBC** → classic “bank/industrial insider wall” with CFO+CEO+GC all in

So 1️⃣ (exclusions) + 2️⃣ (RoleScore) is clearly working.

The *next natural step* is 3️⃣: **turn this into a single “ClusterScore” and proper ranking/filtering logic** so you can sort by “most interesting cluster” instead of just eyeballing.

Here’s a prompt you can hand straight to Codex Coder 👇

---

## Prompt for Codex Coder: Add ClusterScore + Strategy Filters to `show_cluster_buys.py`

You are working on the **`get-insider-db`** project.

We already have in `scripts/show_cluster_buys.py`:

* For each cluster window:

  * `ticker`
  * `window_start`, `window_end`
  * `people_count` (People)
  * `all_insiders_count` (All)
  * `funds_count` (Funds)
  * `role_score` (RoleScore)
  * `trades_count`
  * `total_value_usd`
  * `total_shares`
  * `key_roles` (e.g. `"CFO, GC, CEO"`)
  * `insiders_display` and `funds_display` columns
* `insider_exclusions` are already wired in.
* People vs Funds splitting is already working.

### Goal

1. Implement a **single numeric `cluster_score`** per window that summarizes:

   * more People
   * higher RoleScore
   * larger Total Value
   * fewer Funds (fund-heavy = penalty)
2. Use `cluster_score` as part of the **default sort order**.
3. Add a few optional **CLI filters** to quickly show only high-conviction clusters.

---

## 1. Add cluster_score computation

Create a helper function (same module or a small utility module, your choice):

```python
def compute_cluster_score(
    people: int,
    role_score: int,
    total_value_usd: float,
    funds: int,
    all_insiders: int,
) -> float:
    """
    Compute a composite score for a cluster window.

    Heuristics:
      - Higher role_score is good (CFO/GC/CEO/COO/...).
      - More people is good (broad insider participation).
      - Larger total_value_usd is good, but use log-scaling to avoid domination by outliers.
      - More funds (relative to all_insiders) is bad -> penalty.

    Return a float; higher is better.
    """
```

Suggested implementation (tune weights but keep logic explicit and centralized):

```python
import math

def compute_cluster_score(people, role_score, total_value_usd, funds, all_insiders):
    # Avoid division by zero
    all_insiders = max(all_insiders, 1)

    # Log-scale dollar value to avoid 1 huge trade dominating everything
    # Add 1 to avoid log(0)
    value_score = math.log10(total_value_usd + 1.0) if total_value_usd > 0 else 0.0

    # Funds ratio in [0, 1+]
    fund_ratio = funds / all_insiders

    # Weights (tweakable constants)
    w_role   = 2.0
    w_people = 1.0
    w_value  = 2.0
    w_fund   = 2.0  # penalty

    score = (
        w_role   * role_score +
        w_people * people +
        w_value  * value_score -
        w_fund   * fund_ratio
    )

    return score
```

Key points:

* RoleScore is **central**.
* People count matters.
* TotalValue helps differentiate small vs big clusters.
* Heavy fund participation leads to a **small penalty** via `fund_ratio`.

Attach this `cluster_score` to the per-window structure, e.g.:

```python
window.cluster_score = compute_cluster_score(
    people=people_count,
    role_score=role_score,
    total_value_usd=total_value_usd,
    funds=funds_count,
    all_insiders=all_insiders_count,
)
```

---

## 2. Default sort order

Currently the script probably sorts by something like `total_value_usd` or is unsorted.

Update the sorting so that the **default order** is:

1. Descending `cluster_score`
2. Then descending `role_score`
3. Then descending `people_count`
4. Then descending `total_value_usd`

Example:

```python
windows.sort(
    key=lambda w: (
        w.cluster_score,
        w.role_score,
        w.people_count,
        w.total_value_usd,
    ),
    reverse=True,
)
```

This ensures the top of the table is always:

* High role conviction (lots of CFO/GC/CEO/etc.)
* Many people involved
* Decent dollar value
* Not dominated by funds

---

## 3. Show ClusterScore in the CLI table

Add a column to the printed table:

```text
| Ticker | Start      | End        | People | All | RoleScore | ClusterScore | Trades | Total Value | Shares | Key Roles | Funds |
|--------|------------|------------|--------|-----|-----------|--------------|--------|-------------|--------|-----------|-------|
| HPP    | ...        | ...        |   14   |  14 |    30     |    37.2      |   14   | $2,564,984  | ...    | CFO,GC,CEO| —     |
```

* Format `cluster_score` to 1 decimal place or similar.
* If the table width is too big, you can keep both `RoleScore` and `ClusterScore`, or drop one when needed. For now, keep **both**.

---

## 4. Add CLI filters for “high conviction”

Add the following **optional arguments** to `scripts/show_cluster_buys.py` via `argparse`:

* `--min-cluster-score` (float, default `None`)
* `--min-role-score` (int, default `None`)
* `--min-people` (int, default `None`)
* `--max-fund-ratio` (float, default `None`)

Filtering logic (after computing all metrics but before sorting/printing):

```python
def passes_filters(window, args):
    # Example attributes on window object or dict:
    people = window.people_count
    role_score = window.role_score
    cluster_score = window.cluster_score
    funds = window.funds_count
    all_insiders = max(window.all_insiders_count, 1)

    fund_ratio = funds / all_insiders

    if args.min_cluster_score is not None and cluster_score < args.min_cluster_score:
        return False

    if args.min_role_score is not None and role_score < args.min_role_score:
        return False

    if args.min_people is not None and people < args.min_people:
        return False

    if args.max_fund_ratio is not None and fund_ratio > args.max_fund_ratio:
        return False

    return True
```

Then:

```python
windows = [w for w in windows if passes_filters(w, args)]
```

Example usage from CLI:

* Show only very high conviction clusters:
  `python scripts/show_cluster_buys.py --min-insiders 3 --min-role-score 10 --min-cluster-score 20`
* Show clusters where funds don’t dominate:
  `python scripts/show_cluster_buys.py --max-fund-ratio 0.3`

---

## 5. Acceptance Criteria

* [ ] A central `compute_cluster_score(...)` function exists with a clear, tweakable formula.
* [ ] Each cluster window now has a `cluster_score` attribute.
* [ ] Default sort order uses `cluster_score`, then `role_score`, then `people`, then `total_value_usd` (all descending).
* [ ] CLI output includes a `ClusterScore` column.
* [ ] New CLI flags (`--min-cluster-score`, `--min-role-score`, `--min-people`, `--max-fund-ratio`) work as filters.
* [ ] Existing columns (`People`, `All`, `RoleScore`, `Funds`, `Key Roles`) continue to behave as before.

Keep the implementation consistent with the current code style and structures already in `show_cluster_buys.py`.

---
