# Phase 13: Duplicate Ticker Handling - Research

**Researched:** 2026-02-11
**Domain:** Python CLI output formatting and data deduplication
**Confidence:** HIGH

## Summary

Same ticker appearing multiple times in cluster scan output is a natural consequence of the sliding window algorithm — different transaction-date windows within the lookback period can qualify independently. Current codebase already handles overlapping window merging (Phase 10-01) but intentionally preserves separate cluster events when merged spans would violate window_days constraint.

Analysis of `exports/cluster_runs/clusters_wd10_lb120_minins2_minrole0_minval0.0_mintrade0.0_limit100_minscore0.0_maxfund0.25_20260211T181230.json` confirms duplicates are common: 100 rows contain 60 unique tickers, with 20 tickers appearing 2-7 times (MTDR appears 7 times, BFS 6 times). Example: AMCR appears twice with overlapping windows (2025-11-01 to 2025-11-10, score 94.6) and (2025-11-03 to 2025-11-12, score 91.67), representing independent cluster signals from different filing dates.

The duplicate ticker issue is an **output UX problem**, not a data correctness problem. Users need clarity on whether duplicates represent: (a) independent conviction events from distinct windows, or (b) overlapping activity that should be consolidated. The solution requires CLI-level deduplication options, not changes to cluster detection logic.

**Primary recommendation:** Add CLI flags to scan_clusters.py for deduplicate-by-highest-score mode (consolidate per ticker) and annotate output with duplicate markers when showing all occurrences.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.x | DataFrame deduplication | Built-in `drop_duplicates()`, `groupby().apply()`, and `sort_values()` patterns |
| argparse | stdlib | CLI flag parsing | Standard library, existing pattern in all scripts |
| Rich/tabulate | existing | Table output formatting | Already used in scan_clusters.py for console display |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| collections.Counter | stdlib | Duplicate detection/counting | For logging duplicate statistics |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pandas dedup | SQL DISTINCT ON | SQL enforces deduplication at query level, but loses flexibility for "show all" mode |
| CLI flags | Config file | CLI flags are explicit per-run, match existing pattern (--limit, --min-cluster-score) |

**Installation:**
No new dependencies required — all solutions use existing pandas and stdlib.

## Architecture Patterns

### Recommended Implementation Structure
```
scripts/scan_clusters.py
└── main()
    ├── get_top_cluster_buys()  # existing: returns DataFrame with duplicates
    ├── _deduplicate_tickers()  # NEW: optional post-processing
    ├── _annotate_duplicates()  # NEW: mark rows with duplicate_count, rank
    └── format_rows()           # existing: table output (may need columns)
```

### Pattern 1: Sort-and-Deduplicate (Keep Highest Score)
**What:** Sort DataFrame by cluster_score descending, then drop duplicates keeping first occurrence per ticker
**When to use:** When --deduplicate flag is set
**Example:**
```python
# Source: pandas official docs + Statology pattern
def deduplicate_by_highest_score(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only the highest-scoring cluster per ticker."""
    return (df.sort_values('cluster_score', ascending=False)
              .drop_duplicates('ticker', keep='first')
              .sort_values(['cluster_score', 'total_value'], ascending=[False, False])
              .reset_index(drop=True))
```

### Pattern 2: Annotate Duplicates (Show All with Context)
**What:** Add metadata columns (duplicate_count, duplicate_rank) to help users interpret multiple occurrences
**When to use:** When showing all results (default mode)
**Example:**
```python
def annotate_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Add duplicate metadata columns to DataFrame."""
    ticker_counts = df['ticker'].value_counts().to_dict()
    df['duplicate_count'] = df['ticker'].map(ticker_counts)

    # Rank by score within each ticker group (1 = highest)
    df['duplicate_rank'] = (df.groupby('ticker')['cluster_score']
                              .rank(ascending=False, method='min')
                              .astype(int))
    return df
```

### Pattern 3: CLI Flag Pattern (Existing Codebase Style)
**What:** Boolean flag for mode selection with consistent naming
**When to use:** For --deduplicate flag implementation
**Example:**
```python
# Source: scan_clusters.py existing patterns
parser.add_argument(
    "--deduplicate",
    action="store_true",
    help="Keep only highest-scoring cluster per ticker (default: show all)",
)
# Then in main():
if args.deduplicate:
    df = deduplicate_by_highest_score(df)
else:
    df = annotate_duplicates(df)
```

### Anti-Patterns to Avoid
- **Deduplicating in cluster_buys.py:** Window detection should remain pure — filtering is a display concern
- **Complex merge logic:** Don't try to intelligently merge overlapping windows beyond existing span validation (Phase 10 already handles this)
- **Silent deduplication:** Always log how many clusters were deduplicated when flag is used
- **Modifying sort order when annotating:** Preserve original cluster_score sort order when showing all occurrences

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Duplicate detection | Custom nested loops | `df['ticker'].value_counts()` | Pandas optimized, tested, one-liner |
| Deduplication logic | Manual index tracking | `df.sort_values().drop_duplicates()` | Standard pattern, readable, safe |
| Ranking within groups | Custom sorting | `df.groupby('ticker')['score'].rank()` | Built-in window functions |
| Logging duplicate stats | String concatenation | `collections.Counter(df['ticker'])` | Standard library, clean API |

**Key insight:** Pandas DataFrame deduplication is well-trodden territory with battle-tested patterns. Don't reinvent — use sort-and-drop or groupby-idxmax patterns from pandas ecosystem.

## Common Pitfalls

### Pitfall 1: Deduplicating Before Limit Application
**What goes wrong:** If you deduplicate the full result set AFTER applying --limit, you lose potential high-value duplicates that were excluded by limit
**Why it happens:** Natural order is scan → limit → deduplicate, but this creates biased samples
**How to avoid:** Apply deduplication BEFORE limit truncation, or document that --limit applies to deduplicated results
**Warning signs:** User reports missing high-scoring clusters when using --deduplicate with small --limit

### Pitfall 2: Ambiguous "Highest Score" When Ties Exist
**What goes wrong:** Two windows for same ticker have identical cluster_score — which one to keep?
**Why it happens:** drop_duplicates(keep='first') is arbitrary when scores tie
**How to avoid:** Use stable secondary sort (total_value desc, then window_end desc) before deduplication
**Warning signs:** Non-deterministic results across runs for same filters

### Pitfall 3: Duplicate Annotation Without Explanation
**What goes wrong:** Adding duplicate_count=3 column confuses users who don't know what it means
**Why it happens:** Column name alone doesn't convey "this ticker appears 3 times in full result set"
**How to avoid:** Add header/footer message when duplicates exist: "Note: N tickers appear multiple times (different windows)"
**Warning signs:** User confusion in issue reports: "What does duplicate_count mean?"

### Pitfall 4: Breaking JSON Export Schema
**What goes wrong:** Adding duplicate_count/duplicate_rank columns to JSON breaks downstream consumers
**Why it happens:** Consumers expect fixed schema; new columns are unexpected
**How to avoid:**
  - Option A: Only add annotation columns to console output (not JSON)
  - Option B: Add columns under --annotate-duplicates flag (opt-in)
  - Option C: Add metadata section to JSON payload (not in rows[])
**Warning signs:** Enrichment scripts fail with KeyError on duplicate_count

### Pitfall 5: Deduplication Breaking Window Analysis
**What goes wrong:** User wants to analyze temporal clustering patterns (e.g., "MTDR had 7 cluster events in 2 weeks") but deduplication hides this signal
**Why it happens:** Deduplication optimizes for "what to trade" but obscures "how strong is conviction over time"
**How to avoid:** Make --deduplicate opt-in (default: show all), document tradeoff in help text
**Warning signs:** User asks "how can I see all cluster events for a ticker?"

## Code Examples

Verified patterns from codebase and pandas ecosystem:

### Deduplication (Keep Highest Cluster Score)
```python
# Source: pandas docs + codebase pattern
def deduplicate_by_highest_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only the highest-scoring cluster per ticker.

    Tiebreaker: total_value desc, then window_end desc (most recent).
    """
    return (
        df.sort_values(
            by=['ticker', 'cluster_score', 'total_value', 'window_end'],
            ascending=[True, False, False, False]  # ticker groups, score/value/date desc
        )
        .drop_duplicates(subset='ticker', keep='first')
        .sort_values(
            by=['cluster_score', 'total_value'],
            ascending=[False, False]
        )
        .reset_index(drop=True)
    )
```

### Duplicate Annotation (Show All with Metadata)
```python
# Source: pandas groupby patterns
def annotate_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add duplicate_count and duplicate_rank columns for user clarity.

    duplicate_count: how many times this ticker appears in results
    duplicate_rank: rank by cluster_score within ticker (1 = highest)
    """
    if df.empty:
        return df

    df = df.copy()
    ticker_counts = df['ticker'].value_counts().to_dict()
    df['duplicate_count'] = df['ticker'].map(ticker_counts)

    df['duplicate_rank'] = (
        df.groupby('ticker')['cluster_score']
        .rank(ascending=False, method='min')
        .astype(int)
    )

    return df
```

### CLI Integration with Logging
```python
# Source: scan_clusters.py existing patterns
def main():
    parser = argparse.ArgumentParser(description="Scan for insider cluster buy events")
    # ... existing arguments ...
    parser.add_argument(
        "--deduplicate",
        action="store_true",
        help="Keep only highest-scoring cluster per ticker (default: show all occurrences)",
    )
    parser.add_argument(
        "--annotate-duplicates",
        action="store_true",
        help="Add duplicate_count and duplicate_rank columns to output",
    )
    args = parser.parse_args()

    df = get_top_cluster_buys(limit=args.limit, ...)  # existing

    if df.empty:
        print("No cluster buys found with the given filters.")
        return

    pre_dedup_count = len(df)
    unique_tickers = df['ticker'].nunique()

    if args.deduplicate:
        df = deduplicate_by_highest_score(df)
        post_dedup_count = len(df)
        removed = pre_dedup_count - post_dedup_count
        print(f"Deduplicated: {removed} duplicate clusters removed ({post_dedup_count} unique tickers)")
    elif args.annotate_duplicates:
        df = annotate_duplicates(df)
        dup_count = len(df[df['duplicate_count'] > 1])
        if dup_count > 0:
            dup_tickers = len(df[df['duplicate_count'] > 1]['ticker'].unique())
            print(f"Note: {dup_tickers} tickers appear multiple times ({dup_count} total duplicates)")

    # ... existing output logic ...
```

### Logging Duplicate Statistics
```python
# Source: existing logging patterns in cluster_buys.py
from collections import Counter

def log_duplicate_stats(df: pd.DataFrame, logger):
    """Log duplicate ticker statistics for observability."""
    ticker_counts = Counter(df['ticker'])
    duplicates = {t: c for t, c in ticker_counts.items() if c > 1}

    if duplicates:
        logger.info(
            "duplicate_tickers_found",
            unique_tickers=len(ticker_counts),
            duplicated_tickers=len(duplicates),
            total_duplicate_rows=sum(duplicates.values()),
            top_duplicates=dict(sorted(duplicates.items(), key=lambda x: -x[1])[:5]),
        )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SQL DISTINCT ON ticker | Post-query pandas dedup | N/A (new feature) | Flexibility: can show all or deduplicate at runtime |
| Silent merging | User-controlled flags | Phase 13 | Transparency: user decides tradeoff |
| Fixed schema | Optional annotation columns | Phase 13 | Backward compat: JSON schema unchanged by default |

**Deprecated/outdated:**
- None — this is a new feature, not a replacement

## Open Questions

1. **Should --deduplicate apply before or after --limit?**
   - What we know: Current --limit truncates final sorted results
   - What's unclear: Does user expect "top 20 unique tickers" or "top 20 clusters then deduplicate"?
   - Recommendation: Apply deduplication BEFORE limit (more intuitive: "show me top 20 tickers, keeping best cluster per ticker")

2. **Should duplicate annotations appear in JSON exports or console-only?**
   - What we know: JSON exports are consumed by enrich_clusters_async.py and backtest scripts
   - What's unclear: Will new columns break existing consumers?
   - Recommendation: Start with console-only annotations (format_rows()), add to JSON only if --annotate-duplicates flag is set

3. **What's the right default behavior?**
   - What we know: Phase 10-01 intentionally keeps separate windows when span exceeds limit
   - What's unclear: Do most users want "best signal per ticker" or "all signals"?
   - Recommendation: Default to show-all (preserves current behavior), require opt-in --deduplicate (safe evolution)

4. **Should we support --deduplicate-by options (ticker, issuer_cik)?**
   - What we know: Same company might have multiple tickers (GEF, GEF-B appear as single ticker "GEF, GEF-B")
   - What's unclear: Do users want to deduplicate by issuer CIK instead of ticker symbol?
   - Recommendation: Start with ticker-only deduplication (OUT-01 scope), defer issuer-level to future phase if requested

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `.planning/phases/10-window-span-validation/10-01-PLAN.md` - Window merge behavior
- Codebase analysis: `src/analytics/cluster_buys.py:614-632` - Overlapping window merge logic
- Codebase analysis: `scripts/scan_clusters.py` - Existing CLI patterns and output formatting
- Codebase analysis: `tests/test_window_span_validation.py` - Window merge test coverage
- Export analysis: `exports/cluster_runs/clusters_wd10_lb120_minins2_minrole0_minval0.0_mintrade0.0_limit100_minscore0.0_maxfund0.25_20260211T181230.json` - Real duplicate ticker data (100 rows, 60 unique, 20 duplicated)

### Secondary (MEDIUM confidence)
- [Pandas: Remove Duplicates but Keep Row with Max Value - Statology](https://www.statology.org/pandas-remove-duplicates-keep-max/) - Sort-and-deduplicate pattern
- [pandas.DataFrame.drop_duplicates — pandas 3.0.0 documentation](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.drop_duplicates.html) - Official API
- [RisingWave: Effective Deduplication of Events](https://risingwave.com/blog/effective-deduplication-of-events-in-batch-and-stream-processing/) - General deduplication strategies
- [How Overlapping Returns Inflate Measured Time Series Momentum - MDPI](https://www.mdpi.com/1911-8074/19/1/46) - Financial time series overlapping windows pitfalls

### Tertiary (LOW confidence)
- [GitHub - jpillora/dedup](https://github.com/jpillora/dedup) - CLI tool patterns for duplicate handling flags
- [uniq Linux Command - ioflood](https://ioflood.com/blog/uniq-linux-command/) - Unix deduplication UX patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - pandas deduplication is well-established, patterns verified in codebase
- Architecture: HIGH - CLI flag pattern matches existing scan_clusters.py conventions, implementation straightforward
- Pitfalls: HIGH - Derived from codebase analysis (window merge, JSON export schema) and pandas best practices

**Research date:** 2026-02-11
**Valid until:** 2026-03-15 (30 days, stable domain — CLI patterns and pandas APIs are mature)
