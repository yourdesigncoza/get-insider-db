# 🔎 SYSTEM AUDIT PROMPT — VALUE FILTER ENFORCEMENT

You are performing a **strict architectural audit** of my insider cluster detection engine.

Your role is NOT to speculate.
Your role is to verify implementation details precisely and identify structural weaknesses.

---

## Objective

Determine whether a **capital deployment (value-based) filter** is implemented correctly and meaningfully.

Specifically investigate:

* `min_total_value`
* `min_trade_value`
* Any dynamic market-cap scaling logic
* Any weighting of dollar value in `cluster_score`
* Any logic preventing symbolic / compensation trades from inflating clusters

---

## Required Process

### 1️⃣ Locate Implementation

* Identify exact file(s) where cluster filtering occurs.
* Identify where `cluster_score` is computed.
* Identify where raw Form 4 trades are aggregated.
* Identify where filters are applied (pre-aggregation vs post-aggregation).

You must quote the relevant logic sections.

---

### 2️⃣ Answer Definitively

State clearly:

* ✅ Value filter exists and is enforced
  OR
* ❌ Value filter does not exist
  OR
* ⚠ Exists but is structurally weak / ineffective

No hedging.

---

### 3️⃣ If Missing or Weak

Provide:

* Exact insertion point in pipeline
* Updated filtering logic
* Suggested default thresholds
* Backtest impact expectation
* Edge case analysis (small cap vs large cap)
* Performance implications

Include pseudocode where necessary.

---

### 4️⃣ Risk Assessment

Explain:

* How lack of value filter distorts signal
* How it affects false positives
* How it impacts forward-return expectancy
* How it interacts with role_score and cluster_score

Be technical.

---

### 5️⃣ Enhancement Recommendation

Choose one of:

A) Static threshold
B) Market-cap scaled threshold
C) Hybrid threshold
D) Value-weighted scoring adjustment

Defend your choice quantitatively.

---

## Output Format

* Sectioned
* Technical
* Direct
* No motivational language
* No generic commentary
* Implementation-focused

---

This version will force your AI to think like:

> Senior quant engineer reviewing production code.

If you want an even harder version that forces it to produce refactored code blocks, I can give you that too.
