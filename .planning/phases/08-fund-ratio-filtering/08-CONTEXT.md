# Phase 8: Fund Ratio Filtering - Context

**Gathered:** 2026-02-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Exclude fund-heavy clusters from scan_clusters.py output so results surface insider buying signals from actual individuals, not institutional fund activity. Filtering happens at the SQL query level. Only scan_clusters.py is affected — downstream scripts (enrich, backtest) process whatever input they receive.

</domain>

<decisions>
## Implementation Decisions

### Filter reporting
- No filter reporting. Excluded clusters are silently dropped.
- No log lines, no summary counts, no verbose mode for filtered entries.
- This is a pipeline producing clean results — if a cluster doesn't meet criteria, it simply doesn't appear.

### Fund ratio inspection
- fund_ratio always visible as a field in JSON export output.
- Purpose: scoring context — helps user understand why a cluster scored the way it did.
- fund_ratio is part of the conviction formula, so showing it aids interpretation.

### Threshold behavior
- Boundary: `fund_ratio >= max_fund_ratio` means excluded (strict — only below threshold passes).
- Null/unknown fund_ratio: excluded (conservative — if we can't verify, filter it out).
- CLI flag: `--max-fund-ratio` on scan_clusters.py, default from ClusterThresholds config.
- Default value: currently 0.25 — **researcher should analyze distribution of fund_ratio values in existing cluster data and recommend optimal threshold**.

### Output integration
- Filtering at SQL level — WHERE clause excludes fund-heavy clusters before they leave the database.
- Scan_clusters.py only — enrichment and backtest scripts do not apply fund_ratio filtering.

### Claude's Discretion
- Whether fund_ratio needs to be added to the query output (or is already there) — researcher investigates.

### Research Questions (for researcher)
- **Optimal max_fund_ratio default:** Analyze distribution of fund_ratio values across existing clusters. What threshold best separates meaningful insider signals from fund-dominated noise? Recommend a value with data backing.
- **Scoring penalty + hard filter:** The conviction formula already penalizes fund_ratio (`- w_fund * fund_ratio`). Should this penalty remain alongside the hard cutoff filter? Provide pros/cons of keeping both vs. filter-only.

</decisions>

<specifics>
## Specific Ideas

- User views results as data for further decision-making, not as an interactive experience — no need for explanatory output about what was filtered.
- fund_ratio visibility is about understanding scoring, not verifying filter correctness.

</specifics>

<deferred>
## Deferred Ideas

- Remove `--print` flag and console table functionality from scan_clusters.py — no longer useful.

</deferred>

---

*Phase: 08-fund-ratio-filtering*
*Context gathered: 2026-02-11*
