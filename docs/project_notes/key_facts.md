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

## Key File Paths
- Dashboard: `scripts/dashboard.py`
- Shared cluster detection: `src/services/cluster_detection_fast.py`
- Historical rates: `src/analytics/historical_rates.py`
- Backtest data: `exports/backtest/backtest_*_enriched.json`
- Tests: `tests/test_historical_rates.py` (6 tests)
