# Phase 04: Feature Completeness & Debt Cleanup - Research

**Researched:** 2026-02-05
**Domain:** LLM integration for classification, checkpointing for crash recovery, legacy code removal, audit trail design
**Confidence:** MEDIUM

## Summary

This phase completes the insider-db feature set while cleaning up technical debt. Four distinct work areas exist: (1) AI-powered insider classification using Claude API to replace the current rule-based stub, (2) a checkpointing system to resume the enrichment pipeline after crashes, (3) removal of legacy code like `_LEGACY_ROLE_WEIGHTS_FLOAT`, and (4) an audit trail via a SignalHistory table for tracking signal lifecycle changes.

The AI classification stub at `src/insider_classification.py:74-96` currently just delegates to the rule-based classifier. The recommended approach uses the Anthropic Python SDK (v0.77.1) with Instructor for structured output validation. For checkpointing, the Python ecosystem offers generator-based state snapshots and database-backed progress tracking. The SignalHistory table should follow an event-sourcing pattern with immutable append-only records.

**Primary recommendation:** Integrate Claude Haiku (fastest/cheapest) via the Anthropic SDK with Instructor for structured classification output, implement database-backed checkpointing in `enrichment_checkpoint` table, remove 4 legacy code blocks identified below, and create `signal_history` table following event-sourcing patterns.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic | 0.77.1 | Claude API client | Official SDK, type-safe, async support |
| instructor | 1.x | Structured LLM output | Pydantic validation, automatic retries on schema errors |
| pydantic | 2.x | Data validation | Already used implicitly via SQLAlchemy, required for Instructor |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| litellm | 1.x | Multi-provider abstraction | If need to swap Claude for other providers later |
| tenacity | 8.x | Retry logic | Already in use; works with Instructor |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| anthropic SDK | litellm | litellm abstracts providers; direct SDK has full feature access |
| instructor | Raw JSON parsing | Instructor handles retries on validation errors automatically |
| Database checkpoints | File-based JSON | Database survives crashes better; enables distributed workers |

**Installation:**
```bash
pip install anthropic instructor
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── llm/
│   ├── __init__.py           # Export client singleton
│   ├── client.py             # Anthropic client setup with Instructor
│   ├── prompts.py            # Classification prompt templates
│   └── schemas.py            # Pydantic models for LLM responses
├── checkpointing/
│   ├── __init__.py
│   ├── checkpoint_manager.py # DB-backed checkpoint CRUD
│   └── models.py             # EnrichmentCheckpoint SQLAlchemy model
├── audit/
│   ├── __init__.py
│   └── signal_history.py     # SignalHistory event recording
└── insider_classification.py # Updated to use LLM client
```

### Pattern 1: Structured LLM Classification with Instructor
**What:** Use Pydantic models to enforce structured output from Claude
**When to use:** All LLM-based classification/extraction tasks
**Example:**
```python
# Source: https://python.useinstructor.com/ + https://pypi.org/project/anthropic/
import instructor
from anthropic import Anthropic
from pydantic import BaseModel, Field
from enum import Enum

class EntityType(str, Enum):
    PERSON = "person"
    FUND = "fund_or_investment_vehicle"
    OPERATING_CO = "operating_company"
    TRUST = "trust_or_foundation"
    OTHER = "other"

class InsiderClassification(BaseModel):
    """Structured classification result from LLM."""
    entity_type: EntityType = Field(description="Primary entity type")
    is_fund_like: bool = Field(description="True if entity behaves like an investment fund")
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence")
    rationale: str = Field(description="Brief explanation for classification")

# Create Instructor-wrapped client
client = instructor.from_anthropic(Anthropic())

def classify_insider_with_ai(
    name: str,
    officer_title: str | None,
    flags: dict | None = None,
) -> InsiderClassification:
    """Classify insider using Claude with structured output."""
    flags = flags or {}
    context_parts = [f"Name: {name}"]
    if officer_title:
        context_parts.append(f"Title: {officer_title}")
    if flags.get("is_officer"):
        context_parts.append("Flagged as officer")
    if flags.get("is_director"):
        context_parts.append("Flagged as director")

    return client.messages.create(
        model="claude-3-5-haiku-20241022",  # Fastest/cheapest
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": f"""Classify this SEC Form 4 insider into one of: person, fund_or_investment_vehicle, operating_company, trust_or_foundation, other.

Context:
{chr(10).join(context_parts)}

Consider:
- Investment funds often have LP, LLC, Partners, Capital, Fund in name
- Trusts often have Trust, Foundation in name
- Operating companies have Inc, Corp, but are NOT investment vehicles
- Persons are individual humans (most common for officers/directors)

Return your classification with confidence and rationale."""
        }],
        response_model=InsiderClassification,
    )
```

### Pattern 2: Database-Backed Checkpointing
**What:** Store enrichment progress in a dedicated checkpoint table
**When to use:** Long-running batch operations (enrichment, backfill)
**Example:**
```python
# Source: Derived from https://github.com/a-rahimi/python-checkpointing patterns
from sqlalchemy import text
from datetime import datetime

class CheckpointManager:
    """Track progress for resumable enrichment runs."""

    def __init__(self, engine):
        self._engine = engine

    def get_checkpoint(self, run_id: str) -> dict | None:
        """Get the latest checkpoint for a run."""
        with self._engine.connect() as conn:
            row = conn.execute(text("""
                SELECT last_processed_index, processed_tickers, errors, updated_at
                FROM enrichment_checkpoints
                WHERE run_id = :run_id
            """), {"run_id": run_id}).fetchone()

        if row:
            return {
                "last_index": row[0],
                "processed_tickers": row[1],  # JSONB array
                "errors": row[2],  # JSONB dict
                "updated_at": row[3],
            }
        return None

    def save_checkpoint(
        self,
        run_id: str,
        last_index: int,
        processed_tickers: list[str],
        errors: dict,
    ) -> None:
        """Save or update checkpoint."""
        with self._engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO enrichment_checkpoints
                    (run_id, last_processed_index, processed_tickers, errors, updated_at)
                VALUES
                    (:run_id, :idx, :tickers, :errors, :now)
                ON CONFLICT (run_id) DO UPDATE SET
                    last_processed_index = EXCLUDED.last_processed_index,
                    processed_tickers = EXCLUDED.processed_tickers,
                    errors = EXCLUDED.errors,
                    updated_at = EXCLUDED.updated_at
            """), {
                "run_id": run_id,
                "idx": last_index,
                "tickers": processed_tickers,
                "errors": errors,
                "now": datetime.utcnow(),
            })

    def clear_checkpoint(self, run_id: str) -> None:
        """Clear checkpoint after successful completion."""
        with self._engine.begin() as conn:
            conn.execute(text(
                "DELETE FROM enrichment_checkpoints WHERE run_id = :run_id"
            ), {"run_id": run_id})
```

### Pattern 3: Event-Sourced Audit Trail
**What:** Append-only events tracking signal lifecycle changes
**When to use:** When you need to trace who/what/when for signal state changes
**Example:**
```python
# Source: Derived from PostgreSQL event sourcing patterns
from sqlalchemy import text
from datetime import datetime
from typing import Any
import json

class SignalHistoryRecorder:
    """Record immutable events for signal audit trail."""

    def __init__(self, engine):
        self._engine = engine

    def record_event(
        self,
        cluster_id: int,
        event_type: str,
        changed_by: str,
        old_values: dict[str, Any] | None,
        new_values: dict[str, Any] | None,
        reason: str | None = None,
    ) -> int:
        """Record an event in the signal history."""
        with self._engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO signal_history
                    (cluster_id, event_type, changed_by, old_values, new_values, reason, created_at)
                VALUES
                    (:cid, :event, :by, :old, :new, :reason, :now)
                RETURNING id
            """), {
                "cid": cluster_id,
                "event": event_type,
                "by": changed_by,
                "old": json.dumps(old_values) if old_values else None,
                "new": json.dumps(new_values) if new_values else None,
                "reason": reason,
                "now": datetime.utcnow(),
            })
            return result.fetchone()[0]

    def get_history(self, cluster_id: int) -> list[dict]:
        """Get full history for a signal."""
        with self._engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id, event_type, changed_by, old_values, new_values, reason, created_at
                FROM signal_history
                WHERE cluster_id = :cid
                ORDER BY created_at ASC
            """), {"cid": cluster_id}).fetchall()

        return [
            {
                "id": r[0],
                "event_type": r[1],
                "changed_by": r[2],
                "old_values": r[3],
                "new_values": r[4],
                "reason": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]
```

### Anti-Patterns to Avoid
- **Calling LLM per-row in tight loops:** Batch classifications or use caching; API latency adds up
- **Mutable audit records:** Once written, signal_history rows should NEVER be updated/deleted
- **Checkpoint only at end:** Checkpoint periodically (every N rows) not just at completion
- **Storing credentials in prompts:** Never embed API keys or secrets in LLM prompts

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM response parsing | Regex/manual JSON | Instructor + Pydantic | Automatic retries on validation errors, type safety |
| Multi-provider LLM | Custom client per provider | litellm (if needed) | Unified API, handles auth/rate limits |
| Checkpoint serialization | Custom pickle/JSON | Database JSONB columns | ACID guarantees, query capability |
| Audit timestamps | Manual datetime strings | PostgreSQL `now()` | Consistent timezone, indexable |

**Key insight:** LLM APIs are inherently unreliable (rate limits, timeouts, malformed output). Instructor handles validation retries automatically, saving significant error handling code.

## Common Pitfalls

### Pitfall 1: LLM Rate Limits During Batch Classification
**What goes wrong:** Classification of 1000+ entities hits API rate limits
**Why it happens:** Anthropic has per-minute token limits; batch requests fire too fast
**How to avoid:** Use asyncio.Semaphore to limit concurrent requests; implement exponential backoff; cache results in insider_entities table
**Warning signs:** 429 errors; increasing response times

### Pitfall 2: Checkpoint Granularity
**What goes wrong:** Checkpoint every row = slow; checkpoint never = lose progress
**Why it happens:** Not balancing overhead vs recovery granularity
**How to avoid:** Checkpoint every 10-50 rows; adjust based on row processing time
**Warning signs:** Enrichment is 2x slower with checkpointing; crashes lose >10 min of work

### Pitfall 3: Audit Trail Performance Impact
**What goes wrong:** Signal updates slow down due to audit INSERT on every change
**Why it happens:** Synchronous writes to signal_history on hot path
**How to avoid:** Use async writes or queue audit events for batch insert
**Warning signs:** Signal update latency increases; pg_stat_activity shows many INSERTs to signal_history

### Pitfall 4: LLM Prompt Drift
**What goes wrong:** Classification quality degrades over time as data distribution shifts
**Why it happens:** Training examples in prompt become stale; new entity patterns emerge
**How to avoid:** Log classification results; periodically review edge cases; A/B test prompt changes
**Warning signs:** Increasing `source="rules"` fallbacks; user complaints about misclassification

### Pitfall 5: Incomplete Legacy Code Removal
**What goes wrong:** Remove code but leave references/imports; tests fail
**Why it happens:** Grep for symbol name misses dynamic references
**How to avoid:** Run full test suite after each removal; check for string references in comments/docs
**Warning signs:** ImportError at runtime; tests that passed now fail

## Code Examples

### Complete AI Classification Flow
```python
# src/llm/client.py
# Source: https://pypi.org/project/anthropic/ + https://python.useinstructor.com/
import os
import instructor
from anthropic import Anthropic
from functools import lru_cache

@lru_cache(maxsize=1)
def get_llm_client():
    """Get singleton Instructor-wrapped Anthropic client."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable required")
    return instructor.from_anthropic(Anthropic(api_key=api_key))
```

```python
# src/llm/schemas.py
from pydantic import BaseModel, Field
from enum import Enum

class EntityType(str, Enum):
    PERSON = "person"
    FUND = "fund_or_investment_vehicle"
    OPERATING_CO = "operating_company"
    TRUST = "trust_or_foundation"
    OTHER = "other"

class InsiderClassification(BaseModel):
    entity_type: EntityType
    is_fund_like: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
```

```python
# src/insider_classification.py (updated)
from src.llm.client import get_llm_client
from src.llm.schemas import InsiderClassification

def classify_insider_with_ai(
    name: str,
    officer_title: str | None,
    flags: dict | None = None,
) -> dict:
    """AI-powered classifier using Claude."""
    flags = flags or {}
    client = get_llm_client()

    context = f"Name: {name}"
    if officer_title:
        context += f"\nTitle: {officer_title}"
    if flags.get("is_officer"):
        context += "\nFlagged as officer"
    if flags.get("is_director"):
        context += "\nFlagged as director"

    try:
        result: InsiderClassification = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": f"""Classify this SEC Form 4 insider:

{context}

Categories:
- person: Individual human (most officers/directors)
- fund_or_investment_vehicle: Investment funds (LP, Partners, Capital, Fund)
- operating_company: Business entities (Inc, Corp) NOT investment vehicles
- trust_or_foundation: Trusts, foundations
- other: None of the above

Return classification with confidence (0-1) and brief rationale."""
            }],
            response_model=InsiderClassification,
        )

        return {
            "entity_type": result.entity_type.value,
            "is_fund_like": result.is_fund_like,
            "source": "ai",
            "confidence": result.confidence,
            "rationale": result.rationale,
        }
    except Exception as e:
        # Fallback to rules on AI failure
        from src.insider_classification import classify_insider_by_rules
        rules_result = classify_insider_by_rules(name, officer_title, flags)
        rules_result["rationale"] = f"AI fallback due to: {e}"
        return rules_result
```

### Checkpoint Table Schema
```sql
-- Add to schema.sql
CREATE TABLE IF NOT EXISTS enrichment_checkpoints (
    run_id text PRIMARY KEY,
    last_processed_index integer NOT NULL DEFAULT 0,
    processed_tickers jsonb NOT NULL DEFAULT '[]'::jsonb,
    errors jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE INDEX idx_checkpoint_updated ON enrichment_checkpoints (updated_at);
```

### SignalHistory Table Schema
```sql
-- Add to schema.sql
CREATE TABLE IF NOT EXISTS signal_history (
    id bigserial PRIMARY KEY,
    cluster_id bigint NOT NULL REFERENCES cluster_events(cluster_id) ON DELETE CASCADE,
    event_type text NOT NULL,  -- 'created', 'status_changed', 'score_updated', 'invalidated'
    changed_by text NOT NULL,  -- 'system', 'enrichment', 'manual', 'decay_job'
    old_values jsonb,
    new_values jsonb,
    reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE INDEX idx_signal_history_cluster ON signal_history (cluster_id, created_at);
CREATE INDEX idx_signal_history_event ON signal_history (event_type, created_at);
```

### Enrichment with Checkpointing
```python
# Source: Derived from python-checkpointing patterns
import json
from pathlib import Path
from src.checkpointing.checkpoint_manager import CheckpointManager

def process_file_with_checkpointing(
    file_path: Path,
    checkpoint_manager: CheckpointManager,
    checkpoint_frequency: int = 25,
):
    """Process enrichment file with crash recovery."""
    run_id = f"enrich_{file_path.stem}"

    # Load data
    data = json.loads(file_path.read_text())
    rows = data.get("rows", [])

    # Check for existing checkpoint
    checkpoint = checkpoint_manager.get_checkpoint(run_id)
    start_index = 0
    processed_tickers = []
    errors = {}

    if checkpoint:
        start_index = checkpoint["last_index"] + 1
        processed_tickers = checkpoint["processed_tickers"] or []
        errors = checkpoint["errors"] or {}
        print(f"Resuming from checkpoint: row {start_index}/{len(rows)}")

    # Process rows
    enriched_rows = data.get("rows", [])[:start_index]  # Already done

    for i in range(start_index, len(rows)):
        row = rows[i]
        ticker = row.get("ticker")

        try:
            enriched = enrich_row(row)
            enriched_rows.append(enriched)
            processed_tickers.append(ticker)
        except Exception as e:
            errors[ticker] = str(e)
            enriched_rows.append(row)  # Keep original on error

        # Checkpoint periodically
        if (i + 1) % checkpoint_frequency == 0:
            checkpoint_manager.save_checkpoint(
                run_id=run_id,
                last_index=i,
                processed_tickers=processed_tickers,
                errors=errors,
            )
            print(f"Checkpoint saved at row {i + 1}/{len(rows)}")

    # Final save
    data["rows"] = enriched_rows
    output_path = file_path.with_name(f"{file_path.stem}_enriched{file_path.suffix}")
    output_path.write_text(json.dumps(data, indent=2, default=str))

    # Clear checkpoint on success
    checkpoint_manager.clear_checkpoint(run_id)
    print(f"Completed. Errors: {len(errors)}")
```

## Legacy Code to Remove

Based on codebase analysis, the following legacy code blocks should be removed:

### 1. `_LEGACY_ROLE_WEIGHTS_FLOAT` in cluster_service.py
**Location:** `src/analytics/cluster_service.py:19-35`
**What:** Deprecated float-scale role weights dictionary
**Why remove:** Comment says "kept for reference only"; replaced by `ROLE_WEIGHTS` from `src.scoring_config.scoring_weights`
**Risk:** Low - already marked deprecated, no runtime references found
**Verification:** `grep -r "_LEGACY_ROLE_WEIGHTS_FLOAT" src/` returns only the definition

### 2. Duplicate `fetch_recent_buys` function
**Location:** `src/analytics/cluster_service.py:99-147`
**What:** Redundant buy signals fetch function
**Why remove:** `cluster_buys.py` has the canonical implementation; this file's function is never called externally
**Risk:** Medium - verify no imports before removal
**Verification:** Check imports in scripts/, tests/

### 3. Dead SQL query variable (first version at line 103-122)
**Location:** `src/analytics/cluster_service.py:103-122`
**What:** First query definition that gets immediately overwritten at line 125
**Why remove:** The first `query = text(...)` is overwritten before use; dead code
**Risk:** Low - obvious dead code pattern
**Verification:** Line 103 query is never executed (line 125 redefines before use at 144)

### 4. Unused `detect_clusters` function
**Location:** `src/analytics/cluster_service.py:149-304`
**What:** Cluster detection implementation
**Why remove:** `cluster_buys.py:get_cluster_buys()` is the canonical detection function used by scripts
**Risk:** Medium - verify no external callers
**Verification:** Check all scripts for imports from `cluster_service`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Rule-based classification | LLM classification with Instructor | 2024-2025 | Higher accuracy on edge cases |
| File-based JSON checkpoints | Database-backed checkpoints | 2024+ | Survives crashes, enables distributed workers |
| Manual audit logging | Event-sourced signal_history | 2020+ | Immutable audit trail, easy replay |
| Raw JSON from LLM | Pydantic-validated structured output | 2024 | Type safety, automatic retries |

**Deprecated/outdated:**
- OpenAI function_calling without validation: Use Instructor for type-safe extraction
- Pickle-based checkpointing: Use database or JSON for portability

## Open Questions

1. **LLM Model Selection**
   - What we know: Claude Haiku is fastest/cheapest; Sonnet more accurate
   - What's unclear: Required accuracy level for insider classification
   - Recommendation: Start with Haiku; measure accuracy; upgrade if needed

2. **Classification Caching Strategy**
   - What we know: Results already cached in `insider_entities` table
   - What's unclear: Should we re-classify existing entities with AI?
   - Recommendation: Only classify new entities; add flag to force re-classification

3. **Checkpoint Retention**
   - What we know: Checkpoints should be cleared on success
   - What's unclear: How long to keep failed run checkpoints?
   - Recommendation: Auto-expire checkpoints after 7 days; keep failed for debugging

4. **Audit Trail Granularity**
   - What we know: Track status changes (active/decayed/invalidated)
   - What's unclear: Should we track every score recalculation?
   - Recommendation: Track status changes, enrichment additions, manual edits only

## Sources

### Primary (HIGH confidence)
- [Anthropic Python SDK v0.77.1](https://pypi.org/project/anthropic/) - Installation, API patterns
- [Anthropic API Reference](https://platform.claude.com/docs/en/api/messages) - Model names, parameters
- [Instructor Documentation](https://python.useinstructor.com/) - Structured output patterns
- [PostgreSQL Event Sourcing](https://softwaremill.com/implementing-event-sourcing-using-a-relational-database/) - Audit trail patterns

### Secondary (MEDIUM confidence)
- [python-checkpointing](https://github.com/a-rahimi/python-checkpointing) - Checkpointing patterns
- [Django Auditlog](https://django-auditlog.readthedocs.io/) - Signal-based audit patterns

### Codebase Analysis (HIGH confidence)
- `src/insider_classification.py:74-96` - Current AI stub
- `src/analytics/cluster_service.py:19-35` - Legacy weights
- `src/analytics/cluster_service.py:103-122` - Dead SQL
- `schema.sql` - Current table structure

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Anthropic SDK is official, Instructor is established
- Architecture patterns: MEDIUM - Instructor patterns verified; checkpointing patterns adapted
- Legacy code removal: HIGH - Direct codebase analysis
- Audit trail design: MEDIUM - Based on PostgreSQL best practices, not project-specific validation

**Research date:** 2026-02-05
**Valid until:** 2026-03-05 (30 days for stable patterns; LLM ecosystem evolves fast)
