"""
Compute historical win rates from enriched backtest JSON files.

Loads all exports/backtest/backtest_*_enriched.json files and buckets
signals by num_insiders and value_per_insider to provide context for
new cluster signals.
"""

import json
from pathlib import Path
from typing import Optional


HORIZONS = [30, 60, 90]


def _insider_bucket(num_insiders: int) -> str:
    if num_insiders <= 2:
        return "insiders_2"
    elif num_insiders <= 4:
        return "insiders_3_4"
    return "insiders_5_plus"


def _vpi_bucket(value_per_insider: float) -> str:
    if value_per_insider < 50_000:
        return "vpi_under_50k"
    elif value_per_insider <= 200_000:
        return "vpi_50k_200k"
    return "vpi_over_200k"


def _compute_bucket_stats(rows: list[dict]) -> dict:
    """Compute win rates and mean returns for a list of enriched rows."""
    if not rows:
        return {"n": 0, "win_rate_30d": 0, "win_rate_60d": 0, "win_rate_90d": 0,
                "mean_30d": 0, "mean_60d": 0, "mean_90d": 0}

    stats = {"n": len(rows)}
    for h in HORIZONS:
        key = f"return_{h}d"
        returns = [r[key] for r in rows if r.get(key) is not None]
        if returns:
            stats[f"win_rate_{h}d"] = sum(1 for r in returns if r > 0) / len(returns)
            stats[f"mean_{h}d"] = round(sum(returns) / len(returns), 2)
        else:
            stats[f"win_rate_{h}d"] = 0
            stats[f"mean_{h}d"] = 0
    return stats


def compute_historical_rates(rows: list[dict]) -> dict:
    """
    Compute historical win rates from enriched backtest rows.

    Accepts a list of row dicts (from enriched backtest JSON "rows" arrays).
    Returns a dict of bucket_name -> stats.
    """
    # Filter to only rows with price data
    ok_rows = [r for r in rows if r.get("enrichment_status") == "ok"]

    rates = {"overall": _compute_bucket_stats(ok_rows)}

    # Bucket by num_insiders
    insider_buckets: dict[str, list] = {}
    for r in ok_rows:
        bucket = _insider_bucket(r["num_insiders"])
        insider_buckets.setdefault(bucket, []).append(r)
    for bucket_name, bucket_rows in insider_buckets.items():
        rates[bucket_name] = _compute_bucket_stats(bucket_rows)

    # Bucket by value_per_insider
    vpi_buckets: dict[str, list] = {}
    for r in ok_rows:
        vpi = r.get("value_per_insider") or (r["total_value"] / max(r["num_insiders"], 1))
        bucket = _vpi_bucket(vpi)
        vpi_buckets.setdefault(bucket, []).append(r)
    for bucket_name, bucket_rows in vpi_buckets.items():
        rates[bucket_name] = _compute_bucket_stats(bucket_rows)

    return rates


def load_historical_rates(backtest_dir: Optional[str | Path] = None) -> dict:
    """
    Load all enriched backtest JSONs and compute aggregated historical rates.

    Looks for exports/backtest/backtest_*_enriched.json by default.
    """
    if backtest_dir is None:
        backtest_dir = Path(__file__).resolve().parents[2] / "exports" / "backtest"
    else:
        backtest_dir = Path(backtest_dir)

    all_rows = []
    for f in sorted(backtest_dir.glob("backtest_*_enriched.json")):
        data = json.loads(f.read_text())
        all_rows.extend(data.get("rows", []))

    return compute_historical_rates(all_rows)


def get_bucket_for_cluster(rates: dict, value_per_insider: float) -> Optional[dict]:
    """
    Return the best matching historical bucket for a cluster.

    Matches by value_per_insider range, falling back to overall.
    """
    bucket_name = _vpi_bucket(value_per_insider)
    bucket = rates.get(bucket_name)
    if bucket and bucket["n"] > 0:
        return bucket
    return rates.get("overall")
