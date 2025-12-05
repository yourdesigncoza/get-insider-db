Ohhhh man, this is *exactly* what we were aiming for 😎

Let’s translate what you’re looking at in human-speak.

---

## 1️⃣ What ClusterScore is actually doing (sanity check)

Using the formula we sketched:

```python
score = (
    2.0 * role_score +      # w_role
    1.0 * people +          # w_people
    2.0 * log10(total_value_usd + 1)  # w_value
    - 2.0 * fund_ratio      # w_fund penalty
)
```

Take **HPP** as a worked example:

* People = 14
* RoleScore = 30
* Total Value ≈ 2,564,984 → `log10(2.56M) ≈ 6.4`

So:

* `2 * 30 = 60`
* `+ 14 = 74`
* `+ 2 * 6.4 ≈ 12.8`
* No funds → no penalty

👉 `74 + 12.8 ≈ 86.8` ✅ matches your `ClusterScore 86.8`

So the top names are there **because**:

* Big **role density** (CFO + CEO + GC, multiple EVPs, etc.)
* Lots of **people** participating
* Non-trivial **$ size**
* **Zero or low funds** (HPP / WSBC / EMN / SFNC all show `Funds —`)

AVBH is slightly “noisier” (Patriot fund complex in Funds), but:

* 15 People
* RoleScore 25
* $12.6M of buys
* So it still scores very high at **78.8**, just under HPP.

That’s *exactly* what we wanted from the score:

> “Reward broad insider participation + senior roles + real money, gently penalize fund-heavy structures.”

---

## 2️⃣ How to *read* this table now (in trading terms)

You’ve basically turned the raw feed into:

* **HPP / AVBH / WSBC / EMN / SFNC**
  → All look like:

  * Bank / REIT / financial / industrial names
  * Multiple directors + C-suite + GC all stepping in
  * Reasonable to large dollar size
  * Very little or no fund noise (except AVBH, which you can handle via filters)

In “cluster-buy playbook” language:

* HPP: textbook **“everyone inside the house is buying”** pattern.
* AVBH: same story *plus* a private equity complex in the background (Patriot), but you’ve quarantined it nicely into `Funds`.
* WSBC / EMN / SFNC: high-quality “full suite” insiders with CFO+CEO showing up → great watchlist candidates.

---

## 3️⃣ What I’d do with this next (practically)

Now that the engine is behaving:

1. **Screening mode**
   Use CLI filters for “only show serious stuff”:

   ```bash
   python scripts/show_cluster_buys.py \
     --window-days 10 \
     --lookback-days 120 \
     --min-insiders 3 \
     --min-role-score 15 \
     --min-cluster-score 60 \
     --max-fund-ratio 0.25
   ```

   That should produce a *short* daily list that looks a lot like what you pasted.

2. **Tiering**
   In your head (or later in UI):

   * ClusterScore ≥ 80 → **Tier 1** (HPP / crazy conviction)
   * 65–80 → **Tier 2** (AVBH / WSBC / EMN)
   * 50–65 → **Tier 3** (still solid, maybe smaller size / fewer key officers)

3. **Flag for later**
   You can add a tiny flag in code like:

   * `has_cfo`, `has_ceo`, `has_gc`
     and later show something like: `Key Roles: CFO+CEO`, `CFO+GC`, etc.
     You already have `Key Roles = "CFO, GC, CEO"` collapsed at the window level, which is perfect.

---

If you want to keep pushing this, the next tiny upgrade I’d suggest is:

* a script like `export_top_clusters.py` that:

  * runs this logic
  * writes the table to CSV/Markdown
  * you drop it straight into Obsidian / Notion as a “cluster watchlist” per day.

But as-is: your engine is now **properly encoding your playbook** in the numbers. This is the fun part where you start trading *from* it instead of hacking *on* it.
