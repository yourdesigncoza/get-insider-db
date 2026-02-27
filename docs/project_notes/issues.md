# Completed Work Log

## 2026-02-26: Insider Cluster Dashboard
**Scope:** Built single-command dashboard replacing multi-script pipeline.

**Commits:**
1. `chore: add .worktrees/ to .gitignore`
2. `feat: add historical win rate lookup from backtest data`
3. `refactor: extract cluster detection and CIK mapping into shared module`
4. `feat: add insider cluster dashboard with historical context`
5. `docs: update README with dashboard usage and --max-value-per-insider flag`
6. `feat: sector blocklist filter, comma-ticker fix, checkpoint cast fix`

**New files:**
- `src/analytics/historical_rates.py` — win rate computation from backtest JSONs
- `src/services/cluster_detection_fast.py` — shared fast SQL cluster detection + CIK mapping
- `scripts/dashboard.py` — Rich table dashboard with historical context
- `tests/test_historical_rates.py` — 6 tests

**Modified files:**
- `scripts/fast_scan_for_backtest.py` — imports from shared module
- `scripts/fast_enrich_backtest.py` — imports from shared module
- `README.md` — dashboard docs added as step 5

**Gemini review:** Clean integration, no actionable bugs. Noted pre-existing quarter-grouping heuristic and ticker-vs-CIK join as future improvement areas.

## 2026-02-26: Sector Column + SEC Links
**Scope:** Added sector context and SEC EDGAR links to dashboard. Blocked sectors filtered by default.

**Commits:**
1. `feat: add load_sector_map() to shared services`
2. `feat: add sector column and blocklist filter to dashboard`
3. `feat: add --links flag for SEC EDGAR filing URLs`
4. `docs: add sector filter and links flags to README`
5. `fix: filter out issuers with no SIC code from dashboard by default`

**New files:**
- `tests/test_cluster_detection_fast.py` — 2 tests for `load_sector_map()`
- `docs/plans/2026-02-26-sector-and-links-design.md` — design doc
- `docs/plans/2026-02-26-sector-and-links-plan.md` — implementation plan

**Modified files:**
- `src/services/cluster_detection_fast.py` — added `load_sector_map()`
- `scripts/dashboard.py` — sector column, blocklist filter, `--links`, `--no-sector-filter`
- `README.md` — documented new flags
