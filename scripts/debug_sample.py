#!/usr/bin/env python
"""
Quick sanity check script for loaded insider transactions.
"""

from src.analytics.buy_signals import cluster_buys, fetch_buy_transactions


def main() -> None:
    df = fetch_buy_transactions()
    print(f"Fetched {len(df)} buy transactions")

    if df.empty:
        print("No buy transactions found; check your source data.")
        return

    clusters = cluster_buys(df)
    print(clusters.head())


if __name__ == "__main__":
    main()
