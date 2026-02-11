# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pipeline for ingesting SEC Form 3/4/5 insider trading data, classifying insiders, detecting conviction-weighted "cluster buy" events (multiple insiders buying the same ticker synchronously), and exporting enriched results with price performance metrics.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
psql $DATABASE_URL -f schema.sql

# Load quarterly SEC data (from data/extracted/*_form345/)
python scripts/load_form345_quarter.py

# Run tests
pytest tests/

# Scan clusters (add --print for console table)
python scripts/scan_clusters.py --limit 50 --print

# Enrich with Alpha Vantage prices
python scripts/enrich_clusters_with_price.py exports/cluster_runs/<export>.json

# Backtest strategy
python scripts/backtest_cluster_strategy.py
```

## Environment Variables

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/insider_data  # pragma: allowlist secret
DATA_DIR=data/extracted                    # optional
FINANCIAL_DATASETS_API_KEY=<key>           # for price enrichment
RATE_LIMIT_SECONDS=<throttle>              # API throttling
```

## Architecture

**Data flow:** Ingest TSVs → Classify insiders → Detect clusters (sliding window) → Score conviction → Export JSON → Enrich with prices → Backtest

**Core modules:**
- `src/scoring_config/scoring_weights.py` - **Single source of truth** for all tunable weights/thresholds
- `src/cluster_scoring.py` - Composite conviction scoring (0-100 scale)
- `src/insider_roles.py` - Role-based weighting (CFO=4, COO/VP=3, CEO=2, Director=1)
- `src/insider_classification.py` - Entity type detection (person vs fund_like)
- `src/analytics/cluster_buys.py` - Main cluster detection engine
- `src/analytics/window_detection.py` - Sliding window algorithm

**Conviction scoring formula:**
```
raw_score = w_role * role_score
          + w_people * people_count
          + w_value * log10(total_value + 1)
          - w_fund * fund_ratio
          + w_percent_change * avg_percent_change
          + w_days_to_file * avg_days_to_file
          + w_sale_to_purchase_ratio * avg_sale_to_purchase_ratio

final_score = 100 * (1 - exp(-raw_score / saturation_k))
```

**Key thresholds** (from `ClusterThresholds`):
- `window_days`: 10 (rolling window for clustering)
- `min_unique_insiders`: 3 (cluster trigger)
- `min_cluster_score`: 60 (filter threshold)
- `max_fund_ratio`: 0.25 (cap fund-like entities)
- `lookback_days_for_features`: 120 (for days_to_file, sale_to_purchase_ratio)

## Database Schema

**Primary tables:** `form345_submission`, `form345_reportingowner`, `form345_nonderiv_trans`, `form345_deriv_trans`, `insider_entities`, `insider_trades`, `cluster_events`, `cluster_event_members`, `market_prices`, `market_fundamentals`

**Key views:** `insider_buy_signals` (clean open-market 'P' transactions), `insider_trades_with_title` (derived officer titles)

## Critical Tests

- `test_look_ahead_bias.py` - **Critical:** Validates signals don't use future price data (signal_date ≤ window_end)
- `test_cluster_scoring.py` - Scoring formula edge cases
- `test_tradeable_window_selection.py` - Window algorithm correctness

## Known Technical Debt

See `docs/REMEDIATION_PLAN.md` for prioritized issues:
- SQL injection in `cluster_buys.py:309-350` (P0)
- Silent data fallthroughs in API enrichment (P0)
- N+1 query pattern in insider batch loading (P1)
- Broad `except Exception` clauses throughout (P1)
