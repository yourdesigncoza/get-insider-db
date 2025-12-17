# Financial Datasets AI Price Enrichment and Max Drawdown Calculation

This document summarizes the functionality implemented in `scripts/enrich_clusters_with_price.py`, which enriches cluster analysis JSON output files with historical stock price data and performance metrics from the Financial Datasets AI API.

## Objective
To integrate the Financial Datasets AI API to fetch end-of-day stock price data and enrich our cluster analysis JSON files with historical price performance metrics, specifically focusing on returns and maximum drawdown over 1, 2, and 3-month periods.

## Implementation Details

### 1. API Setup and Dependencies
-   **API:** Financial Datasets AI (documentation: [https://docs.financialdatasets.ai/](https://docs.financialdatasets.ai/))
-   **Authentication:** The API key must be stored in a `.env` file as `FINANCIAL_DATASETS_API_KEY`.
-   **Dependencies:** The following Python libraries were added to `requirements.txt` and installed:
    -   `requests`: For making HTTP requests to the API.
    -   `python-dateutil`: For robust date calculations, especially `relativedelta` for month-wise additions.
    -   `tenacity`: To handle API rate limits and transient network issues with exponential backoff and retries.

### 2. Data Fetching Strategy
-   **Efficient History Retrieval:** The script fetches the required price history (from `window_end` up to 3 months forward) using the `prices/historical` endpoint.
-   **Fundamentals:** Market capitalization is fetched using the `company/facts` endpoint.
-   **Date Handling:** For any given target date, the script intelligently looks back up to 7 days to find the most recent trading day's closing price, effectively handling weekends and holidays.
-   **Caching:** An `lru_cache` is applied to the price history fetching function (`_get_price_history`) to prevent redundant API calls for the same ticker and date range within a single script run.

### 3. Data Enrichment Fields and Calculations
For each ticker in a cluster result, the following fields are added immediately after the `"avg_sale_to_purchase_ratio"` field:

-   **`price_at_window_end`**: The closing price of the stock on or before the `window_end` date.
-   **`price_1m_after`, `price_2m_after`, `price_3m_after`**: The closing price of the stock at approximately 1, 2, and 3 months after the `window_end` date, respectively (adjusted to the nearest trading day).
-   **`return_1m`, `return_2m`, `return_3m`**: The percentage return calculated from `price_at_window_end` to `price_Xm_after`. These are represented as percentages (e.g., `6.58` for a 6.58% return), rounded to two decimal places.
-   **`max_drawdown_1m`, `max_drawdown_2m`, `max_drawdown_3m`**: The maximum drawdown (MDD) calculated for the periods starting from `window_end` up to 1, 2, and 3 months forward, respectively. MDD represents the largest peak-to-trough decline in price over the period, expressed as a negative percentage (e.g., `-3.02` for a 3.02% drawdown), rounded to two decimal places.

### 4. Output
-   The script generates a new JSON file with the suffix `_enriched.json` (e.g., `clusters_..._original.json` becomes `clusters_..._original_enriched.json`) to preserve the original cluster analysis output.
-   The `metadata` section of the output JSON is updated with an `"enriched_at"` timestamp.

## Usage
To enrich a cluster analysis JSON file, run the script from the command line:

```bash
python3 scripts/enrich_clusters_with_price.py <path_to_json_file>
```

**Example:**

```bash
python3 scripts/enrich_clusters_with_price.py exports/cluster_runs/clusters_wd10_lb120_minins3_minrole15_minval0_mintrade0_limit5_minscore60.0_maxfund0.25_20251212T153927.json
```
