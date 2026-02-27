# Key Facts & Configuration

## Dashboard CLI (`scripts/dashboard.py`)
| Flag | Default | Description |
|------|---------|-------------|
| `--days-back` | 30 | Lookback window |
| `--min-insiders` | 2 | Minimum distinct insiders |
| `--min-total-value` | 100000 | Minimum cluster dollar value |
| `--min-value-per-insider` | 0 | Floor for $/insider |
| `--max-value-per-insider` | 0 (no cap) | Ceiling for $/insider |
| `--window-days` | 10 | Rolling window size |
| `--limit` | 20 | Max rows to display |
| `--json` | false | JSON output mode |
| `--no-sector-filter` | false | Disable sector blocklist + no-SIC filter |
| `--links` | false | Print SEC EDGAR filing links below table |

## Historical Win Rate Buckets (from 4,143 backtest signals)
| Bucket | n | Win Rate 90d |
|--------|---|-------------|
| Overall | 4,143 | 50% |
| vpi_under_50k | 380 | 56% |
| vpi_50k_200k | 1,469 | 54% |
| vpi_over_200k | 2,294 | 46% |
| insiders_2 | 1,463 | 51% |
| insiders_3_4 | 1,404 | 49% |
| insiders_5_plus | 1,276 | 49% |

## Sector Blocklist (from `src/scoring_config/sector_blocklist.py`)
Airlines, Banks, Biotech, Car Manufacturers, Insurance, Marine Freight, Precious Metal Miners, Restaurants, Tobacco, Textiles, Trading Firms, Most Software, Pure AI. Issuers with no SIC code (funds, SPACs) also filtered by default.

## Sector Lookup Table
- `sector_lookup`: 8,982 rows, keyed on `issuer_cik`, has `sic_code` (TEXT), `sic_description` (TEXT)
- Populated via `scripts/populate_sector_lookup.py` (fetches from SEC EDGAR)
- Some issuers have empty SIC codes (closed-end funds, blank checks)

## Key File Paths
- Dashboard: `scripts/dashboard.py`
- Shared cluster detection: `src/services/cluster_detection_fast.py`
- Sector blocklist: `src/scoring_config/sector_blocklist.py`
- Sector filter: `src/analytics/sector_filter.py`
- Historical rates: `src/analytics/historical_rates.py`
- Backtest data: `exports/backtest/backtest_*_enriched.json`
- Tests: `tests/test_historical_rates.py` (6 tests), `tests/test_cluster_detection_fast.py` (2 tests)
