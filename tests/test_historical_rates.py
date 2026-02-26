"""Tests for historical win rate computation from backtest data."""

import pytest
from src.analytics.historical_rates import compute_historical_rates


def test_compute_rates_from_rows():
    rows = [
        {"num_insiders": 3, "total_value": 600000, "return_30d": 5.0, "return_60d": 8.0, "return_90d": 10.0, "enrichment_status": "ok"},
        {"num_insiders": 3, "total_value": 700000, "return_30d": -3.0, "return_60d": -5.0, "return_90d": 2.0, "enrichment_status": "ok"},
        {"num_insiders": 2, "total_value": 200000, "return_30d": 1.0, "return_60d": 4.0, "return_90d": -1.0, "enrichment_status": "ok"},
        {"num_insiders": 2, "total_value": 200000, "return_30d": None, "return_60d": None, "return_90d": None, "enrichment_status": "no_price"},
    ]
    rates = compute_historical_rates(rows)

    # Overall rates based on the 3 "ok" rows
    assert "overall" in rates
    assert rates["overall"]["n"] == 3
    assert 0 <= rates["overall"]["win_rate_90d"] <= 1
    # 2 of 3 have positive 90d return
    assert rates["overall"]["win_rate_90d"] == pytest.approx(2 / 3, abs=0.01)
    # All 3 have positive 30d return (5, -3, 1 -> 2 of 3 positive)
    assert rates["overall"]["win_rate_30d"] == pytest.approx(2 / 3, abs=0.01)


def test_bucket_by_num_insiders():
    rows = [
        {"num_insiders": 2, "total_value": 100000, "return_30d": 5.0, "return_60d": 5.0, "return_90d": 5.0, "enrichment_status": "ok"},
        {"num_insiders": 2, "total_value": 100000, "return_30d": -5.0, "return_60d": -5.0, "return_90d": -5.0, "enrichment_status": "ok"},
        {"num_insiders": 4, "total_value": 100000, "return_30d": 10.0, "return_60d": 10.0, "return_90d": 10.0, "enrichment_status": "ok"},
        {"num_insiders": 6, "total_value": 100000, "return_30d": 2.0, "return_60d": 2.0, "return_90d": 2.0, "enrichment_status": "ok"},
    ]
    rates = compute_historical_rates(rows)

    assert "insiders_2" in rates
    assert rates["insiders_2"]["n"] == 2
    assert rates["insiders_2"]["win_rate_90d"] == pytest.approx(0.5)

    assert "insiders_3_4" in rates
    assert rates["insiders_3_4"]["n"] == 1
    assert rates["insiders_3_4"]["win_rate_90d"] == pytest.approx(1.0)

    assert "insiders_5_plus" in rates
    assert rates["insiders_5_plus"]["n"] == 1


def test_bucket_by_value_per_insider():
    rows = [
        # vpi = 10000/2 = 5000 -> under_50k
        {"num_insiders": 2, "total_value": 10000, "return_30d": 5.0, "return_60d": 5.0, "return_90d": 5.0, "enrichment_status": "ok"},
        # vpi = 200000/2 = 100000 -> 50k_200k
        {"num_insiders": 2, "total_value": 200000, "return_30d": -5.0, "return_60d": -5.0, "return_90d": -5.0, "enrichment_status": "ok"},
        # vpi = 900000/3 = 300000 -> over_200k
        {"num_insiders": 3, "total_value": 900000, "return_30d": 10.0, "return_60d": 10.0, "return_90d": 10.0, "enrichment_status": "ok"},
    ]
    rates = compute_historical_rates(rows)

    assert "vpi_under_50k" in rates
    assert rates["vpi_under_50k"]["n"] == 1

    assert "vpi_50k_200k" in rates
    assert rates["vpi_50k_200k"]["n"] == 1

    assert "vpi_over_200k" in rates
    assert rates["vpi_over_200k"]["n"] == 1
    assert rates["vpi_over_200k"]["win_rate_90d"] == pytest.approx(1.0)


def test_skips_no_price_rows():
    rows = [
        {"num_insiders": 3, "total_value": 300000, "return_30d": None, "return_60d": None, "return_90d": None, "enrichment_status": "no_price"},
        {"num_insiders": 3, "total_value": 300000, "return_30d": None, "return_60d": None, "return_90d": None, "enrichment_status": "no_price"},
    ]
    rates = compute_historical_rates(rows)
    assert rates["overall"]["n"] == 0


def test_mean_return_computed():
    rows = [
        {"num_insiders": 3, "total_value": 300000, "return_30d": 10.0, "return_60d": 20.0, "return_90d": 30.0, "enrichment_status": "ok"},
        {"num_insiders": 3, "total_value": 300000, "return_30d": -10.0, "return_60d": -20.0, "return_90d": -30.0, "enrichment_status": "ok"},
    ]
    rates = compute_historical_rates(rows)
    assert rates["overall"]["mean_90d"] == pytest.approx(0.0, abs=0.01)
    assert rates["overall"]["mean_30d"] == pytest.approx(0.0, abs=0.01)


def test_get_bucket_for_cluster():
    """Test the helper that matches a cluster to its best historical bucket."""
    from src.analytics.historical_rates import get_bucket_for_cluster

    rows = [
        {"num_insiders": 3, "total_value": 300000, "return_30d": 5.0, "return_60d": 5.0, "return_90d": 5.0, "enrichment_status": "ok"},
    ]
    rates = compute_historical_rates(rows)

    # A cluster with vpi=150k should match vpi_50k_200k
    bucket = get_bucket_for_cluster(rates, value_per_insider=150000)
    assert bucket is not None
    assert bucket["n"] >= 1
