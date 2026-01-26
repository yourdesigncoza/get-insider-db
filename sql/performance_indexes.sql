-- Performance indexes for get-insider-db
--
-- These indexes improve query performance for the insider_buy_signals VIEW
-- and other frequently-used queries.
--
-- Run with: psql -d insider_data -f sql/performance_indexes.sql
-- Or execute each statement individually in your database client.

-- Composite index for insider_buy_signals VIEW performance
-- The VIEW filters by TRANS_CODE='P' and joins on ACCESSION_NUMBER
-- This composite index allows the database to use a single index scan
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nonderiv_trans_code_accession
ON form345_nonderiv_trans ("TRANS_CODE", "ACCESSION_NUMBER");

-- Index for filing date range queries
-- Commonly used in cluster detection (WHERE filing_date BETWEEN ... AND ...)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_subm_filing_date
ON form345_submission ("FILING_DATE");

-- Composite index for transaction date + ticker lookups
-- Used when filtering by ticker and date range in cluster detection
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_subm_filing_ticker
ON form345_submission ("FILING_DATE", "ISSUERTRADINGSYMBOL");

-- Verify indexes were created
SELECT
    indexname,
    tablename,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('form345_nonderiv_trans', 'form345_submission')
ORDER BY tablename, indexname;
