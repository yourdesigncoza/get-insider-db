-- Migration: Add issuer_cik to cluster_events with strict CIK exclusion
-- Purpose: Eliminates data fragmentation when tickers change (FB->META)
-- Note: cluster_events keeps cluster_id as PK (auto-increment), we ADD issuer_cik
-- Strict exclusion: unmapped rows (no CIK) are DELETED

BEGIN;

-- Add issuer_cik column (nullable initially for population)
ALTER TABLE cluster_events ADD COLUMN IF NOT EXISTS issuer_cik TEXT;

-- Populate from mapping table
UPDATE cluster_events ce
SET issuer_cik = m.issuer_cik
FROM issuer_cik_ticker_map m
WHERE ce.ticker = m.ticker;

-- STRICT EXCLUSION: Delete unmapped rows (cascade will clean cluster_event_members + signal_history)
DELETE FROM cluster_events WHERE issuer_cik IS NULL;

-- Make issuer_cik NOT NULL (safe after deletion)
ALTER TABLE cluster_events ALTER COLUMN issuer_cik SET NOT NULL;

-- Add foreign key constraint to mapping table
ALTER TABLE cluster_events
ADD CONSTRAINT fk_cluster_events_issuer_cik
FOREIGN KEY (issuer_cik) REFERENCES issuer_cik_ticker_map(issuer_cik);

-- Create index for efficient CIK lookups
CREATE INDEX IF NOT EXISTS idx_cluster_events_issuer_cik ON cluster_events(issuer_cik);

-- Make ticker nullable (now metadata, not primary identifier)
ALTER TABLE cluster_events ALTER COLUMN ticker DROP NOT NULL;

COMMIT;
