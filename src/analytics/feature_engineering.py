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

    # Group by insider and ticker to process each's history
    def apply_ratio_calculation(group):
        group = group.sort_values(by="transaction_date")
        sales_sum = 0.0
        purchase_sum = 0.0
        ratios = []

        for i, row in group.iterrows():
            current_date = row["transaction_date"]
            lookback_start = current_date - pd.Timedelta(days=lookback_days)

            # Filter group to only include trades within the lookback window relative to current trade
            window_trades = group[
                (group["transaction_date"] >= lookback_start)
                & (group["transaction_date"] <= current_date)
            ]

            sales = window_trades[window_trades["transaction_code"] == "S"]["shares"].sum()
            purchases = window_trades[window_trades["transaction_code"] == "P"]["shares"].sum()

            if purchases > 0:
                ratios.append(sales / purchases)
            else:
                ratios.append(0.0) # Or NaN, depending on desired behavior for no purchases
        
        group["sale_to_purchase_ratio"] = ratios
        return group

    # Use normalized_name for consistent insider tracking if available, otherwise insider_name
    group_cols = ["ticker", "normalized_name"] if "normalized_name" in df.columns else ["ticker", "insider_name"]
    
    # Apply the ratio calculation to each insider-ticker group
    df_with_ratio = df.groupby(group_cols).apply(apply_ratio_calculation).reset_index(drop=True)
    
    return df_with_ratio

