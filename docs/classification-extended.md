Nice, this is a perfect job for your Codex Coder 👨‍💻🤖

Here’s a ready-to-paste prompt you can give it:

---

### Prompt for Codex Coder: Insider Classification with Caching (Rules + AI Fallback)

You are working on a Python project called **`get-insider-db`** that ingests SEC Form 4 insider transactions into a PostgreSQL database and computes **cluster buys** (e.g. used by `scripts/show_cluster_buys.py`).

## Goal

Implement a **cached insider entity classification layer** so that:

1. Each **unique insider** (by normalized name) is classified **once** into a type (person vs fund vs other), with **rule-based logic first**.
2. Only **ambiguous cases** are sent to an **AI-based classifier** (stub in code; real OpenAI integration can be added later).
3. Future runs **reuse** the stored classification from the DB (no repeated AI calls).
4. Cluster logic (e.g. `show_cluster_buys.py`) can **filter/label insiders** using these classifications.

---

## 1. New DB Table: `insider_entities`

Create a new SQLAlchemy model and corresponding DB table to store classification metadata for each insider.

**Model name**: `InsiderEntity`
**Table name**: `insider_entities`

Fields (adjust types to match existing conventions):

* `id` – primary key (integer / big integer)
* `insider_id` – FK or reference to whatever identifies an insider in the existing schema

  * If you already have an `insiders` table/model, this should be `ForeignKey('insiders.id')`
* `normalized_name` – `String`, NOT NULL

  * Uppercased version of insider’s name, stripped of extra whitespace
* `entity_type` – `String`, NOT NULL

  * one of: `"person"`, `"fund_or_investment_vehicle"`, `"operating_company"`, `"trust_or_foundation"`, `"other"`, `"unknown"`
* `is_fund_like` – `Boolean`, NOT NULL
* `source` – `String`, NOT NULL

  * `"rules"`, `"ai"`, or `"manual"`
* `confidence` – numeric/float, default 1.0
* `created_at` – timestamp with default `now()`
* `updated_at` – timestamp with default `now()` and updated on change

**Requirements:**

* Add the SQLAlchemy model in the appropriate models module (follow existing project conventions).
* Add a DB migration (if the project uses Alembic or similar; follow the existing migration tooling).
* Enforce a **uniqueness constraint** on (`insider_id`) or (`normalized_name`) – choose whichever is the canonical key for insiders in the current schema.

---

## 2. Rule-Based Classifier (Python-only)

Create a new module, e.g. **`insider_classification.py`**, with a rule-based function to classify insiders using **only Python string logic**.

Function signature (can be adapted to project style):

```python
def classify_insider_by_rules(name: str, officer_title: str | None, flags: dict) -> dict:
    """
    flags may include:
      - is_director: bool
      - is_officer: bool
      - is_ten_percent_owner: bool
      - is_other: bool

    Returns a dict:
      {
        "entity_type": str,        # one of the allowed values
        "is_fund_like": bool,
        "source": "rules",
        "confidence": float,       # e.g. 0.6-0.8
        "rationale": str           # short reason, optional
      }
    """
```

Implement the following logic:

* Normalize:

  ```python
  name_u = (name or "").upper()
  title_u = (officer_title or "").upper()
  ```

* Define a list of **fund / vehicle tokens** to detect non-natural persons:

  Examples (include at least these):

  ```python
  FUND_TOKENS = [
      " L.P", " LP", " LLP", " L.L.P", " LLC", " L.L.C", " CORP", " CORPORATION",
      " INC", " INC.", " LIMITED", " LTD", " PLC",
      " FUND", " CAPITAL", " PARTNERS", " ADVISORS", " INVESTMENT", " INVESTORS",
      " ASSET MANAGEMENT", " MANAGEMENT LP",
      " HOLDINGS", " TRUST", " FOUNDATION"
  ]
  ```

* `is_fund_like = any(tok in name_u for tok in FUND_TOKENS)`

* Basic classification:

  * If `is_fund_like` is `True` → `entity_type = "fund_or_investment_vehicle"`
  * Else default to `entity_type = "person"`

* Confidence heuristic examples (you can tune):

  * If `is_fund_like` is True → `confidence ≈ 0.8`
  * Else → `confidence ≈ 0.6`

* Return dictionary with fields: `entity_type`, `is_fund_like`, `source="rules"`, `confidence`, `rationale` (short string).

---

## 3. AI Fallback (Stubbed Integration)

Add a second function to the same module for **AI-based classification**. For now, **just stub it**; it should be easy to wire later to OpenAI.

Example signature:

```python
def classify_insider_with_ai(name: str, officer_title: str | None, flags: dict) -> dict:
    """
    Calls an AI model to classify the insider.
    For now, stub it with a TODO or a dummy implementation.

    Should return the same dict shape as classify_insider_by_rules.
    """
```

Inside, do something like:

* Add a TODO comment where OpenAI call will go.
* For now, just return the rule-based result or a fixed dummy structure.
* But structure the code to make it trivial to plug in an actual LLM later.

Example prompt to be used later (commented in code):

> You classify insider names from SEC Form 4 filings into entity categories.
> Valid `entity_type` values: `"person"`, `"fund_or_investment_vehicle"`, `"operating_company"`, `"trust_or_foundation"`, `"other"`.
> Return JSON with: `entity_type`, `is_fund_like` (bool), `rationale` (short).

---

## 4. Orchestration: “Classify Once, Cache in DB”

Create a helper function that orchestrates:

1. Check DB for existing classification.
2. If found → return it.
3. If not:

   1. Run `classify_insider_by_rules`
   2. If `confidence` is high enough (e.g. ≥ 0.8) → **store** it as final.
   3. Else → call `classify_insider_with_ai`, then store that result.
   4. Return the stored object.

Example (adjust to project style):

```python
from models import InsiderEntity  # adjust import
from sqlalchemy.orm import Session  # or whatever session pattern you use

def get_or_create_insider_entity(
    db: Session,
    insider_id: int,
    name: str,
    officer_title: str | None,
    flags: dict
) -> InsiderEntity:
    normalized_name = (name or "").strip().upper()

    entity = (
        db.query(InsiderEntity)
        .filter(InsiderEntity.insider_id == insider_id)
        .one_or_none()
    )

    if entity is not None:
        return entity

    # First-time classification
    rules_result = classify_insider_by_rules(name, officer_title, flags)

    result = rules_result

    # If rules are low confidence, optionally call AI
    if rules_result.get("confidence", 0) < 0.8:
        ai_result = classify_insider_with_ai(name, officer_title, flags)
        if ai_result:
            result = ai_result

    entity = InsiderEntity(
        insider_id=insider_id,
        normalized_name=normalized_name,
        entity_type=result["entity_type"],
        is_fund_like=result["is_fund_like"],
        source=result["source"],
        confidence=result.get("confidence", 1.0),
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity
```

Adjust to fit the project’s DB/session pattern.

---

## 5. Integrate into Cluster Logic (`show_cluster_buys.py`)

Update the cluster-building pipeline (e.g. used by `scripts/show_cluster_buys.py`) so that:

1. For each insider involved in a cluster window:

   * Fetch or create its `InsiderEntity` via `get_or_create_insider_entity(...)`.
   * Use `entity_type` and `is_fund_like` to decide:

     * Whether to include them in “Key Insiders”
     * Whether to count them in insider-based conviction scores.

2. At minimum:

   * Exclude or separately list `is_fund_like = True` entities from the human “key insiders” list.
   * Keep them if you want for a separate “fund / holder” section.

3. Ensure that repeated runs:

   * Do **not** re-classify already-known insiders.
   * Only new insiders cause new classifications and DB inserts.

---

## 6. Acceptance Criteria

* [ ] New table `insider_entities` with model `InsiderEntity` exists and migrates correctly.
* [ ] Rule-based classification works and populates `entity_type` and `is_fund_like` for insiders.
* [ ] A single helper like `get_or_create_insider_entity(...)` implements the **“classify once, cache in DB”** pattern.
* [ ] `show_cluster_buys.py` (and any other relevant cluster logic) now:

  * Joins/queries `InsiderEntity` for each insider
  * Uses this classification to distinguish funds vs people
* [ ] AI classifier is stubbed in a way that’s easy to plug into OpenAI later (but project runs without requiring an API key).

Keep the code clean, well-factored, and consistent with existing repository patterns.

---
