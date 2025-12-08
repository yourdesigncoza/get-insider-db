# Codebase Overview

This document provides a high-level summary of the `get-insider-db` project, outlining its architecture, core components, and data flow.

## 1. Project Goal

The primary goal of this project is to identify and score meaningful **clustered insider stock purchases**. It ingests raw SEC Form 3, 4, and 5 data, processes it, and runs an analysis to find windows of time where multiple company insiders are buying stock, filtering out noise from investment funds and private equity firms.

## 2. Core Workflow

The workflow can be broken down into two main stages:

1.  **ETL (Extract, Transform, Load):** Raw TSV data from SEC quarterly filings is loaded into a PostgreSQL database.
2.  **Analysis & Scoring:** The loaded data is queried to find "buy clusters," which are then enriched, classified, and scored to rank them by significance.

## 3. Key Components

### 3.1. Data Loading

-   **Script:** `scripts/load_form345_quarter.py`
-   **Function:** This script is the main ETL handler. It scans the `data/extracted` directory for quarterly data folders (e.g., `2025q3_form345`).
-   **Process:** It reads the core TSV files (`SUBMISSION.tsv`, `REPORTINGOWNER.tsv`, etc.) into pandas DataFrames and appends them to the corresponding `form345_*` tables in the database. It keeps a log (`loaded_to_db.txt`) to avoid reprocessing quarters.

### 3.2. Database & Models

-   **Schema Definition:** While a `schema.sql` exists, the application's ORM layer is defined in `src/models.py` using SQLAlchemy.
-   **Core Model:** The primary model defined is `InsiderEntity`, which corresponds to the `insider_entities` table. This table acts as a cache for insider classification, storing whether an entity is a person or a fund-like vehicle.
-   **Raw Data Tables:** The `form345_*` tables (`form345_submission`, `form345_reportingowner`, `form345_nonderiv_trans`, etc.) store the raw, unprocessed data from the TSV files.
-   **Key View:** The `insider_buy_signals` view (defined in `schema.sql` but used by the analytics script) is crucial. It pre-joins and cleans the raw data to create a unified view of open-market purchases (`TRANS_CODE = 'P'`).

### 3.3. Cluster Analysis

-   **Script:** `src/analytics/cluster_buys.py`
-   **Function:** This is the heart of the project. The `find_cluster_buys` function executes the main analysis.
-   **Process:**
    1.  It queries the `insider_buy_signals` view to get a base set of purchase transactions within a specified lookback period.
    2.  A complex SQL query with a rolling window (`INTERVAL`) identifies initial clusters where multiple insiders buy within a few days of each other.
    3.  The results are loaded into a pandas DataFrame. The code then merges overlapping time windows to consolidate clusters.
    4.  For each consolidated cluster, it calculates detailed metrics: `num_insiders`, `total_value`, `role_score`, `cluster_score`, etc.

### 3.4. Insider Classification & Scoring

The analysis is supported by several helper modules that classify and weight insiders to determine the quality of a cluster.

-   **Insider Classification (`src/insider_classification.py`):**
    -   Normalizes insider names (e.g., `normalize_insider_name`).
    -   Uses a rule-based system (`classify_insider_by_rules`) with a list of `FUND_TOKENS` (like "LP", "CAPITAL", "PARTNERS") to determine if an insider is a person or a "fund-like" entity.
    -   Caches these classifications in the `insider_entities` database table via `get_or_create_insider_entity` to avoid re-computation.

-   **Insider Role Weighting (`src/insider_roles.py`):**
    -   The `compute_insider_role_weight` function assigns a numerical weight to an insider based on their title (e.g., CFO, CEO, Director).
    -   This helps differentiate clusters involving key executives from those involving lower-level insiders.

-   **Cluster Scoring (`src/cluster_scoring.py`):**
    -   The `compute_cluster_score` function calculates a final composite score for each buy cluster.
    -   The score is a weighted combination of the number of people involved, the total role score, the total dollar value of the purchases, and a penalty for the ratio of funds involved.

### 3.5. Configuration

-   **Script:** `src/config.py`
-   **Function:** Manages project-level configuration.
-   **Process:** It uses `python-dotenv` to load environment variables from a `.env` file. Key variables include `DATABASE_URL` for the PostgreSQL connection and `DATA_DIR` for the location of the raw TSV files. It also provides a cached SQLAlchemy engine via `get_engine()`.
