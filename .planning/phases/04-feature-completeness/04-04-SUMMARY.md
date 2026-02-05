---
phase: 04-feature-completeness
plan: 04
subsystem: audit
tags: [audit, signal-history, event-sourcing, postgresql, jsonb]

dependency-graph:
  requires: [04-01]
  provides: [signal-history-table, signal-history-recorder]
  affects: []

tech-stack:
  added: []
  patterns: [event-sourcing, append-only, audit-trail]

key-files:
  created:
    - src/audit/__init__.py
    - src/audit/signal_history.py
    - tests/test_signal_history.py
  modified:
    - schema.sql

decisions:
  - id: signal-history-append-only
    choice: Append-only table design (no UPDATE/DELETE operations)
    rationale: Immutable audit trail for compliance and debugging
  - id: event-type-validation
    choice: Application-level validation of event_type and changed_by
    rationale: Enforce valid values without DB CHECK constraints for flexibility
  - id: jsonb-state-storage
    choice: JSONB columns for old_values and new_values
    rationale: Flexible schema evolution for different event types

metrics:
  duration: ~2 minutes
  tasks: 3/3
  tests: 21 passing
  completed: 2026-02-05
---

# Phase 04 Plan 04: Signal Audit Trail Summary

Event-sourced signal_history table with SignalHistoryRecorder for immutable lifecycle tracking.

## What Changed

### Schema (schema.sql)
- Added `signal_history` table with FK to `cluster_events`
- Added indexes for efficient querying by cluster_id, event_type, changed_by
- Added table/column comments documenting append-only design

### Audit Module (src/audit/)
- Created `SignalHistoryRecorder` class with three methods:
  - `record_event()` - Append new audit event
  - `get_history()` - Get chronological history for a cluster
  - `get_recent_events()` - Get filtered recent events across all clusters
- Application-level validation of `event_type` and `changed_by` fields
- JSONB serialization for `old_values` and `new_values`

### Tests (tests/test_signal_history.py)
- 21 unit tests covering:
  - Event type and changed_by validation
  - Record creation with correct parameters
  - History retrieval in chronological order
  - Filtering by event_type and changed_by
  - JSONB value serialization
  - Append-only design verification (no update/delete methods)

## Technical Decisions

1. **Append-only by design**: The SignalHistoryRecorder has no update or delete methods. The table uses CASCADE delete from cluster_events as the only removal mechanism.

2. **Validated enums at application layer**: EVENT_TYPES and ACTORS are frozensets, validated before SQL execution. This allows flexibility to add new types without schema migration.

3. **JSONB for state tracking**: old_values and new_values are JSONB columns, enabling different event types to store different state structures.

## Commit Log

| Commit | Type | Description |
|--------|------|-------------|
| dae0b30 | feat | Add signal_history table for audit trail |
| 1840802 | feat | Add SignalHistoryRecorder for audit trail |
| a54a2b5 | test | Add SignalHistoryRecorder unit tests |

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

| Check | Status |
|-------|--------|
| signal_history table in schema.sql | Pass |
| SignalHistoryRecorder imports | Pass |
| 21 tests passing | Pass |
| Append-only design (no update/delete) | Pass |

## Next Steps

This audit trail infrastructure enables:
- Tracking signal creation events
- Recording status changes from decay jobs
- Logging enrichment updates
- Debugging signal evolution over time
