# Sector Column + SEC Links — Design

## Goal
Add sector context and SEC filing links to the insider cluster dashboard.

## Sector Column
- Join `sector_lookup` table on `issuer_cik` to get `sic_description`
- Add "Sector" column to Rich table (after Ticker)
- Filter blocked sectors by default using `is_sic_blocked()` from `src/scoring_config/sector_blocklist.py`
- New `--no-sector-filter` flag disables filtering
- Clusters without a `sector_lookup` row pass through (permissive unknown policy)

## SEC Filing Links
- New `--links` flag (boolean)
- When set, prints "SEC Filing Links" section below the table
- Format: `TICKER — https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<cik_padded>&type=4&dateb=&owner=include&count=10`
- CIK zero-padded to 10 digits

## Files
- **Modify:** `src/services/cluster_detection_fast.py` — add `load_sector_map()` to batch-fetch SIC codes
- **Modify:** `scripts/dashboard.py` — sector column, blocklist filter, --links output, --no-sector-filter flag
- **Reuse:** `src/scoring_config/sector_blocklist.py` — `is_sic_blocked()`
- **Reuse:** `sector_lookup` table (8,982 rows populated)
