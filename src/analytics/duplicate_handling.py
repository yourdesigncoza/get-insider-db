"""
Duplicate ticker handling utilities for cluster scan output.

Provides deduplication (keep highest score per ticker) and annotation
(add duplicate_count/duplicate_rank columns for console display awareness).
"""

import pandas as pd


def deduplicate_by_highest_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only the highest-scoring cluster per ticker.

    Tiebreakers (in order): cluster_score desc, total_value desc, window_end desc.

    Args:
        df: DataFrame with columns: ticker, cluster_score, total_value, window_end

    Returns:
        Deduplicated DataFrame sorted by cluster_score desc, total_value desc
    """
    if df.empty:
        return df

    # Sort by ticker asc (for grouping), then by scoring tiebreakers desc
    sorted_df = df.sort_values(
        by=["ticker", "cluster_score", "total_value", "window_end"],
        ascending=[True, False, False, False],
    )

    # Keep first occurrence of each ticker (highest score due to sort)
    deduped = sorted_df.drop_duplicates(subset="ticker", keep="first")

    # Re-sort by cluster_score desc, total_value desc for final output order
    result = deduped.sort_values(
        by=["cluster_score", "total_value"],
        ascending=[False, False],
    ).reset_index(drop=True)

    return result


def annotate_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add duplicate_count and duplicate_rank columns for console display awareness.

    duplicate_count: number of times each ticker appears in the dataset
    duplicate_rank: rank by cluster_score within ticker group (1 = highest)

    Args:
        df: DataFrame with columns: ticker, cluster_score

    Returns:
        Copy of input DataFrame with duplicate_count and duplicate_rank columns added
    """
    if df.empty:
        return df

    result = df.copy()

    # Add duplicate_count: number of times each ticker appears
    result["duplicate_count"] = result["ticker"].map(result["ticker"].value_counts())

    # Add duplicate_rank: rank by cluster_score within ticker group (1 = highest)
    result["duplicate_rank"] = (
        result.groupby("ticker")["cluster_score"]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    return result
