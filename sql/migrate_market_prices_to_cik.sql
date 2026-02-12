-- Migration: Re-key market_prices from ticker-based to CIK-based primary key
-- Purpose: Eliminates data fragmentation when tickers change (FB->META)
-- CIK is permanent, ticker becomes nullable metadata

BEGIN;

-- Drop old primary key constraint
ALTER TABLE market_prices DROP CONSTRAINT IF EXISTS market_prices_pkey;

-- Drop redundant index (will be replaced with ticker-only index)
DROP INDEX IF EXISTS idx_market_prices_ticker_date;

-- Add issuer_cik column (nullable initially for schema change)
ALTER TABLE market_prices ADD COLUMN IF NOT EXISTS issuer_cik TEXT;

-- TRUNCATE: Fresh start per user decision - data is re-fetchable
TRUNCATE TABLE market_prices;

-- Make issuer_cik NOT NULL (safe after truncate)
ALTER TABLE market_prices ALTER COLUMN issuer_cik SET NOT NULL;

-- Make ticker nullable (now metadata, not primary identifier)
ALTER TABLE market_prices ALTER COLUMN ticker DROP NOT NULL;

-- Create new CIK-based primary key (CIK first for query efficiency)
ALTER TABLE market_prices ADD CONSTRAINT market_prices_pkey PRIMARY KEY (issuer_cik, price_date);

-- Create index on ticker for reverse lookups
CREATE INDEX IF NOT EXISTS idx_market_prices_ticker ON market_prices(ticker);

COMMIT;
