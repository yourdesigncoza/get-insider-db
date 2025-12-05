How does the "FUND_TOKENS" differ from our "insider_exclusions" ?

Nice one, this is an important distinction to get clear.

Short version:

* **`FUND_TOKENS` = generic *rules* baked into code**
* **`insider_exclusions` = a curated *ban list* in your DB**

Let’s unpack.

---

## 1️⃣ `FUND_TOKENS` – generic pattern detector

This is a **code-level heuristic list** like:

```python
FUND_TOKENS = [
    " L.P", " LP", " LLP", " LLC", " CORP", " INC", " LTD", " PLC",
    " FUND", " CAPITAL", " PARTNERS", " ADVISORS", " INVESTMENT",
    " ASSET MANAGEMENT", " HOLDINGS", " TRUST", " FOUNDATION",
]
```

Purpose:

* Answer: **“Does this *look* like a fund / vehicle / non-human entity?”**
* Used to set things like:

  * `is_fund_like = True/False`
  * `entity_type = "fund_or_investment_vehicle"` vs `"person"`
* It’s **broad and fuzzy**: catches lots of stuff that *looks* like a fund, based on name structure.

Think of it as:

> “From the *shape* of this name, is this probably not a natural person?”

This feeds your **classifier**, not your hard business decision.

---

## 2️⃣ `insider_exclusions` – your curated “never count these” list

Your table like:

```sql
INSERT INTO insider_exclusions (pattern, reason) VALUES
    ('DEEP TRACK',        'Deep Track biotech fund'),
    ('ABRAMS CAPITAL',    'Abrams Capital hedge fund'),
    ('GOLDMAN SACHS',     'Goldman Sachs fund complex'),
    ...
```

Purpose:

* Answer: **“Even if this passes any other test, I *never* want to treat this as real insider conviction.”**
* Driven by your **playbook + experience**:

  * Specific fund complexes
  * Specific recurring entities that pollute the signal
* It’s **precise and opinionated**:

  * You decided “GOLDMAN SACHS” = always exclude as “smart money noise”.

Think of it as:

> “When this pattern appears in the name, treat it as excluded from my strategy, full stop.”

---

## 3️⃣ How they work *together* in the pipeline

I’d use them in this order:

### Step 1 – Hard exclusions (DB-driven)

* Check `insider_exclusions`:

  * If insider name matches `pattern` → mark as `excluded = True`
  * Optionally store `entity_type = 'fund_or_investment_vehicle'`, `is_fund_like = True`, `source = 'rules/exclusions'`

These are **top priority**. Your judgement > heuristics.

---

### Step 2 – Generic classification (code-driven)

If not excluded:

* Apply `FUND_TOKENS`:

  * If matches → `is_fund_like = True`
  * Else → probably a person by default
* Combine with Form 4 flags and title to produce:

  * `entity_type`
  * `confidence`
  * role weights etc.

This is your **automatic classifier** that handles the long tail.

---

### Step 3 – Optional AI fix-up

If rules are unsure (low confidence / weird names), use AI to refine `entity_type`.
But even then:

* If `insider_exclusions` says “exclude”, that still overrides everything.

---

## 4️⃣ Mental model

* `FUND_TOKENS` = **“shape of the name”** → helps guess fund vs person
* `insider_exclusions` = **“my trading doctrine”** → explicit do-not-use list

So:

* A name can be **fund-like** due to `FUND_TOKENS`, but **not necessarily excluded** (you might still want to *see* it).
* A name in **`insider_exclusions` is always excluded**, even if it doesn’t look like a fund (e.g. some weird structured executive trust you’ve decided is noise).

---

If you want, next step I can give you:

* a tiny helper like `is_excluded_insider(name)` and
* `is_fund_like_name(name)`

and show how to plug both into the classifier with precedence rules.
