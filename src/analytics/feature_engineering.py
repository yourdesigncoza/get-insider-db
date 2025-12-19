from __future__ import annotations

import pandas as pd

def calculate_days_to_file(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates the number of days between transaction_date and filing_date.
    A positive value means the filing occurred after the transaction (normal).
    """
    df["days_to_file"] = (df["filing_date"] - df["transaction_date"]).dt.days
    return df

def calculate_sale_to_purchase_ratio(df: pd.DataFrame, lookback_days: int = 90) -> pd.DataFrame:
    """
    Calculates the sale-to-purchase ratio for each insider/ticker over a lookback period.
    Requires 'transaction_code' ('P' for purchase, 'S' for sale), 'shares', 'insider_name', 'ticker', 'transaction_date'.
    """
    # Ensure necessary columns are present and correctly typed
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0)
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])

    # Use normalized_name for consistent insider tracking if available, otherwise insider_name
    group_cols = ["ticker", "normalized_name"] if "normalized_name" in df.columns else ["ticker", "insider_name"]

    # Efficient rolling window per insider/ticker group (avoids O(n^2) filtering in groupby.apply).
    parts: list[pd.DataFrame] = []
    lookback_delta = pd.Timedelta(days=lookback_days).to_timedelta64()

    for keys, group in df.groupby(group_cols, sort=False):
        group = group.copy()
        if not isinstance(keys, tuple):
            keys = (keys,)
        for col, val in zip(group_cols, keys):
            group[col] = val

        group = group.sort_values(by="transaction_date")

        dates = group["transaction_date"].to_numpy(dtype="datetime64[ns]")
        shares = group["shares"].to_numpy(dtype=float)
        codes = group["transaction_code"].fillna("").astype(str).str.strip().str.upper().to_numpy()

        left = 0
        sales_sum = 0.0
        purchase_sum = 0.0
        ratios: list[float] = []

        for right in range(len(group)):
            code_r = codes[right]
            share_r = float(shares[right])
            if code_r == "S":
                sales_sum += share_r
            elif code_r == "P":
                purchase_sum += share_r

            lookback_start = dates[right] - lookback_delta
            while left <= right and dates[left] < lookback_start:
                code_l = codes[left]
                share_l = float(shares[left])
                if code_l == "S":
                    sales_sum -= share_l
                elif code_l == "P":
                    purchase_sum -= share_l
                left += 1

            ratios.append((sales_sum / purchase_sum) if purchase_sum > 0 else 0.0)

        group["sale_to_purchase_ratio"] = ratios
        parts.append(group)

    if not parts:
        df = df.copy()
        df["sale_to_purchase_ratio"] = 0.0
        return df

    return pd.concat(parts, ignore_index=True)
