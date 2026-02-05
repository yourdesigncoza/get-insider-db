# Phase 06: Production Integration Cleanup - Context

**Gathered:** 2026-02-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Integrate orphaned modules into production pipeline and standardize logging/exceptions across async modules. No new features — purely wiring existing components together and aligning patterns with sync code.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion

This phase is mechanical cleanup. Standard patterns apply:

**SignalHistoryRecorder integration:**
- When to record (cluster detection, enrichment, or both)
- What metadata to capture in signal records
- Error handling if recording fails

**Structured logging:**
- Which async modules to update
- Log verbosity and context binding patterns
- Match existing structlog configuration

**Exception types:**
- Where to raise EnrichmentError, RateLimitError, InvalidTickerError
- Exception context/metadata to include
- Retry behavior on specific exception types

</decisions>

<specifics>
## Specific Ideas

No specific requirements — apply existing patterns from sync code.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-production-integration-cleanup*
*Context gathered: 2026-02-05*
