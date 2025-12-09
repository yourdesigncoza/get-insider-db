import pandas as pd
from datasets import load_dataset
from sqlalchemy import create_engine, text
import sys
from pathlib import Path

# Allow running the script directly without installing the package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import DATABASE_URL
from src.analytics.feature_engineering import calculate_days_to_file, calculate_sale_to_purchase_ratio

def main():
    print("Loading SOV.AI insider flow prediction dataset...")
    try:
        # Load the dataset (using streaming=False to get the full train split as a single table)
        df_sovai = load_dataset("sovai/insider_flow_prediction", split="train").to_pandas()
        print(f"Successfully loaded SOV.AI dataset with {len(df_sovai)} rows and {len(df_sovai.columns)} columns.")
        # Convert 'date' column to datetime for easier merging/analysis
        df_sovai["date"] = pd.to_datetime(df_sovai["date"])
        df_sovai = df_sovai.sort_values(by=["ticker", "date"]).reset_index(drop=True)

    except Exception as e:
        print(f"Error loading SOV.AI dataset: {e}")
        print("Please ensure you have network access and the dataset is publicly available or you are authenticated.")
        return

    print("Connecting to internal database and loading insider_buy_signals...")
    try:
        engine = create_engine(DATABASE_URL)
        # Load our insider_buy_signals. We might need to filter by date to match SOV.AI's data range
        # Also need normalized_name for calculate_sale_to_purchase_ratio.
        # Re-using logic from cluster_buys to ensure consistency.
        from src.insider_classification import normalize_insider_name
        from src.insider_roles import compute_insider_role_weight # Not used directly here, but for context consistency.

        query = "SELECT * FROM insider_buy_signals WHERE transaction_date >= '2008-01-01' ORDER BY ticker, transaction_date"
        df_our_data = pd.read_sql(text(query), engine)
        print(f"Successfully loaded internal insider_buy_signals with {len(df_our_data)} rows and {len(df_our_data.columns)} columns.")
        df_our_data["transaction_date"] = pd.to_datetime(df_our_data["transaction_date"])
        df_our_data["filing_date"] = pd.to_datetime(df_our_data["filing_date"])

        # Add normalized_name for grouping in feature engineering
        df_our_data["normalized_name"] = df_our_data["insider_name"].fillna("").astype(str).map(normalize_insider_name)

    except Exception as e:
        print(f"Error loading internal data: {e}")
        return

    print("\n--- SOV.AI Dataset Overview ---")
    print(df_sovai.info())
    print("\n--- Our Data Overview (Before Feature Engineering) ---")
    print(df_our_data.info())

    print("\n--- Applying Feature Engineering to Our Data ---")
    df_our_data = calculate_days_to_file(df_our_data)
    df_our_data = calculate_sale_to_purchase_ratio(df_our_data, lookback_days=90)
    
    print("\n--- Our Data Overview (After Feature Engineering) ---")
    print(df_our_data.info())
    print("\n--- Head of Our Data with New Features ---")
    print(df_our_data[["ticker", "transaction_date", "filing_date", "days_to_file", "insider_name", "normalized_name", "transaction_code", "shares", "sale_to_purchase_ratio"]].head())

    print("\n--- Key SOV.AI Features and Mapping Strategy ---")
    print("1.  `flow_prediction` (Target Variable): This is what we ultimately want to predict.")
    print("    -> We need to build a regression model using features from our data to predict this.")
    print("\n2.  `market_impact`, `market_impact_percentage`: Related to stock price movement after filing.")
    print("    -> Requires external stock price data (e.g., from Yahoo Finance, Alpha Vantage) integrated with our pipeline.")
    print("\n3.  `transaction_value`: Total dollar value of transactions.")
    print("    -> We already have `total_value` in `insider_buy_signals`.")
    print("\n4.  `transaction_shares`: Total shares involved in transactions.")
    print("    -> We already have `shares` in `insider_buy_signals`.")
    print("\n5.  `holding_period`: Duration insider held shares (or similar). This is complex.")
    print("    -> Requires tracking an insider's buys and subsequent sells, or understanding typical holding durations if multiple transactions are present. Can be partially proxied by time between consecutive buys/sells by same insider on same ticker.")
    print("\n6.  `sale_to_purchase_ratio`: Insider's selling vs. buying activity.")
    print("    -> *DERIVED:* We now have this feature calculated over a 90-day lookback.")
    print("\n7.  `relative_transaction_size`: Transaction size relative to insider's holdings or company size.")
    print("    -> We have `avg_percent_change` (relative to insider's prior holdings). For company size, we'd need market cap data.")
    print("\n8.  `days_to_file`: Timeliness of filing.")
    print("    -> *DERIVED:* We now have this feature.")
    print("\n9.  'Perturbation' and 'Ratio' metrics: Indicate changes and relationships (e.g., `holding_period_pert`, `sale_purchase_ratio_impactperc_abs_ratio_pert`).")
    print("    -> These are advanced aggregations over time or across different insider groups. We can continue to build these as needed.")
    print("\nInitial feature mapping and derivation complete. Our data now has more features aligned with the SOV.AI dataset.")

if __name__ == "__main__":
    main()
