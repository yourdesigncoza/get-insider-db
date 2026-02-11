import pytest
from src.cluster_scoring import compute_cluster_score

def test_cluster_score_normalization():
    # Case 1: The "Cutoff" case (Raw ~60 originally, ~65 with w_value=3.0)
    # 5 people, role 10, value 1M (log 6), change 0.5 (50%), fund 0, days 0, ratio 0
    # With w_value=3.0:
    # Score = 1*5 + 2*20 + 3*6 + 5*0.5 = 5 + 40 + 18 + 2.5 = 65.5
    # Via saturation curve: 100 * (1 - exp(-65.5/65)) ≈ 63.6
    score_60 = compute_cluster_score(
        people=5,
        role_score=20,
        total_value_usd=1_000_000,
        funds=0,
        all_insiders=5,
        avg_percent_change=0.5,
        avg_days_to_file=0,
        avg_sale_to_purchase_ratio=0
    )
    # With w_value=3.0, raw score shifts from ~59.5 to ~65.5, final ~63.6
    print(f"Raw ~65 case: {score_60}")
    assert 62 < score_60 < 66, f"Expected ~63.6, got {score_60}"

    # Case 2: The "Over 100" case (Raw ~113 like AVBC)
    score_high = compute_cluster_score(
        people=8,
        role_score=20,
        total_value_usd=1_790_000,
        funds=0,
        all_insiders=8,
        avg_percent_change=10.77,
        avg_days_to_file=1.8,
        avg_sale_to_purchase_ratio=0
    )
    print(f"High case: {score_high}")
    assert 80 < score_high < 90, f"Expected 80-90, got {score_high}"

    # Case 3: Extreme outlier
    score_extreme = compute_cluster_score(
        people=20,
        role_score=50,
        total_value_usd=100_000_000,
        funds=0,
        all_insiders=20,
        avg_percent_change=100.0, # 10000%
        avg_days_to_file=0,
        avg_sale_to_purchase_ratio=0
    )
    print(f"Extreme case: {score_extreme}")
    assert 99 <= score_extreme <= 100, f"Expected ~100, got {score_extreme}"
