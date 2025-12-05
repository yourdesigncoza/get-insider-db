## 1️⃣ Table design: `insider_exclusions`

Simple and flexible:

```sql
CREATE TABLE insider_exclusions (
    id          serial PRIMARY KEY,
    pattern     text NOT NULL,   -- substring matched with ILIKE
    reason      text,            -- optional note, e.g. "Fund – RA Capital complex"
    active      boolean NOT NULL DEFAULT true
);
```

**How it works:**

* `pattern` is a substring you expect to appear in `insider_name`

  * e.g. `'RA CAPITAL'`, `'BAKER BROS'`, `'DEERFIELD MANAGEMENT'`,
    `'SILVER LAKE'`, `'BERKSHIRE HATHAWAY'`, `'ICONIQ STRATEGIC PARTNERS'`
* We will treat each row as:

  ```sql
  insider_name ILIKE '%' || pattern || '%'
  ```
* `active = true` lets you temporarily disable an exclusion without deleting it.

### Example seed data

You can insert a few to start:

```sql
INSERT INTO insider_exclusions (pattern, reason) VALUES
    ('RA CAPITAL', 'Healthcare fund complex'),
    ('BAKER BROS', 'Biotech hedge fund'),
    ('DEERFIELD MANAGEMENT', 'Healthcare fund'),
    ('SILVER LAKE', 'PE fund'),
    ('GAP COINVESTMENTS', 'General Atlantic co-invest vehicles'),
    ('ICONIQ STRATEGIC PARTNERS', 'Tech growth fund'),
    ('BERKSHIRE HATHAWAY', 'Buffett / Berkshire entity'),
    ('COLISEUM CAPITAL', 'Activist fund'),
    ('DEEP TRACK CAPITAL', 'Biotech fund'),
    ('IMPACTIVE CAPITAL', 'Activist fund');
```

You can refine this list over time as you see names you don’t want.

---

## 2️⃣ How clustering will use this table

We update the **base query** in `cluster_buys.py` (the one that pulls from `insider_buy_signals`) to exclude any insider where a matching pattern exists.

In SQL terms:

```sql
... FROM insider_buy_signals s
WHERE s.transaction_date BETWEEN :start_date AND :end_date
  AND s.ticker IS NOT NULL
  AND COALESCE(s.total_value, 0) >= :min_trade_value
  AND NOT EXISTS (
      SELECT 1
      FROM insider_exclusions e
      WHERE e.active
        AND s.insider_name ILIKE '%' || e.pattern || '%'
  )
```

Key points:

* We apply the `NOT EXISTS` filter **before** any aggregation / windowing.
* This means excluded insiders:

  * Don’t contribute to `num_trades`
  * Don’t contribute to `num_insiders`
  * Don’t contribute to `total_value`
* Your cluster engine then operates purely on the “cleaned” insider set.

No heuristics, no guessing — **only what you explicitly put in `insider_exclusions`**.

---

## 3️⃣ Codex prompt to implement this (Python + SQL)

Here’s a tight prompt you can paste into your Codex IDE to wire this in with minimal friction:

---

**Codex Prompt**

You are working in the `get-insider-db` project.

We want to introduce a dedicated Postgres table to exclude certain insiders (mostly funds) from our cluster buy engine.

### 1. Database table

Assume I have already executed the following SQL manually in Postgres:

```sql
CREATE TABLE insider_exclusions (
    id      serial PRIMARY KEY,
    pattern text NOT NULL,
    reason  text,
    active  boolean NOT NULL DEFAULT true
);
```

This table stores substring patterns that should be excluded based on `insider_name`.

### 2. Requirement: integrate exclusions into cluster_buys.py

File: `src/analytics/cluster_buys.py`

Current setup (important context):

* We query the view `insider_buy_signals` from Postgres.
* The view has columns (aliases): ticker, insider_name, transaction_date, total_value, etc.
* We already support parameters like `window_days`, `lookback_days`, `min_insiders`, `min_total_value`, `min_trade_value`, and optional `ticker`.
* We filter trades by:

  * `transaction_date` between `start_date` and `latest_date`
  * `ticker IS NOT NULL`
  * `COALESCE(total_value, 0) >= :min_trade_value`
* Then we build clusters from these filtered trades.

New requirement:

1. Add a boolean argument to the main function that fetches trades, e.g.:

```python
def find_cluster_buys(
    window_days: int = 10,
    lookback_days: int = 90,
    min_insiders: int = 2,
    min_total_value: float = 0.0,
    min_trade_value: float = 0.0,
    ticker: Optional[str] = None,
    use_exclusions: bool = True,
) -> pd.DataFrame:
    ...
```

2. When `use_exclusions` is `True`, modify the SQL query so that **each trade row** from `insider_buy_signals` is filtered against `insider_exclusions`:

   * Exclude any row where there exists an `insider_exclusions` record with `active = true` and
     `insider_name ILIKE '%' || pattern || '%'`.

   In SQL, this should look like:

   ```sql
   AND NOT EXISTS (
       SELECT 1
       FROM insider_exclusions e
       WHERE e.active
         AND s.insider_name ILIKE '%' || e.pattern || '%'
   )
   ```

   where `s` is the alias for `insider_buy_signals`.

3. Implement this logic directly inside the SQL used in `cluster_buys.py`. Use a `text(...)` query with named parameters (e.g. `:start_date`, `:end_date`, `:min_trade_value`, etc.).

4. If `use_exclusions` is `False`, the SQL should omit the `NOT EXISTS` clause entirely (i.e. we see all insiders, including funds).

5. Make sure the Python code still works for both:

   * global queries (no `ticker` filter),
   * and ticker-specific queries (`ticker` is not `None`).

### 3. CLI integration

File: `scripts/show_cluster_buys.py`

* Add a new CLI flag: `--no-exclusions`, default is **False**.
* Logic:

  * By default, we call `find_cluster_buys(..., use_exclusions=True)`.
  * If `--no-exclusions` is provided, pass `use_exclusions=False`.

Update the help text to explain:

> `--no-exclusions` disables the insider_exclusions filter, so fund / institutional insiders are included again.

### 4. Code style

* Keep type hints.
* Keep using SQLAlchemy `create_engine(DATABASE_URL)`.
* Use `text()` with named parameters.
* Don’t change the existing window-merging logic or the shape of the returned DataFrame — just ensure it operates on the filtered trade set.

Generate the updated implementations for:

* the main query / function in `src/analytics/cluster_buys.py`
* the CLI argument parsing and call in `scripts/show_cluster_buys.py`

---

If you want, after Codex updates the code, you can run:

```bash
python scripts/show_cluster_buys.py --window-days 10 --lookback-days 120 --min-insiders 2 --min-total-value 0 --min-trade-value 50000 --limit 20
```

and your table should now show **far fewer fund-heavy names** — or even mostly pure executive/operational insiders once you populate `insider_exclusions`.
