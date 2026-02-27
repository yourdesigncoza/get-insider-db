# Architecture Decision Records

## ADR-001: Rank by $/insider instead of conviction score
- **Date:** 2026-02-26
- **Context:** Backtest across 4,143 signals (2021-2025) showed conviction score was anti-predictive (50% win rate, 0% median return at 90d).
- **Decision:** Dashboard ranks clusters by `value_per_insider` DESC. Dollar commitment per insider is the most intuitive and honest ranking metric.
- **Consequence:** Scoring formula (`cluster_score`) is preserved for legacy scan_clusters.py but not used in dashboard.

## ADR-002: Extract shared functions from scripts into src/services/
- **Date:** 2026-02-26
- **Context:** `detect_clusters_fast()` and `load_cik_ticker_map()` were inline in scripts. Dashboard needed to reuse them.
- **Decision:** Created `src/services/cluster_detection_fast.py` as the shared home. Scripts import from there.
- **Consequence:** Avoids dashboard importing from scripts (bad practice). DRY.

## ADR-003: Historical rates bucketed by value_per_insider
- **Date:** 2026-02-26
- **Context:** Need to give context to live signals — "what does history say about clusters like this one?"
- **Decision:** Bucket by VPI (<$50K, $50K-$200K, $200K+) and by num_insiders (2, 3-4, 5+). Show closest bucket's win rate in dashboard.
- **Consequence:** Under-$50K bucket (56% win rate) is the sweet spot. Dashboard exposes this via `--max-value-per-insider`.

## ADR-004: Filter blocked sectors and missing-SIC issuers by default
- **Date:** 2026-02-26
- **Context:** Dashboard showed issuers from blocked industries (biotech, banks, etc.) and issuers with no SIC code (closed-end funds, SPACs, blank checks). These add noise.
- **Decision:** Sector blocklist filter is ON by default. Issuers with no SIC code are also filtered out. `--no-sector-filter` disables both.
- **Consequence:** Cleaner dashboard output. Permissive unknown policy flipped to restrictive for the dashboard. Blocklist config lives in `src/scoring_config/sector_blocklist.py`.

## ADR-005: SEC EDGAR links as separate section, not inline
- **Date:** 2026-02-26
- **Context:** Wanted clickable SEC filing links in dashboard. Terminal Rich tables can't reliably render inline hyperlinks across all terminals.
- **Decision:** `--links` flag prints a separate "SEC Filing Links" section below the table. JSON output always includes `sec_url` field.
- **Consequence:** Works in all terminals. No dependency on OSC 8 support.
