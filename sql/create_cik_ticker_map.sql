CREATE TABLE IF NOT EXISTS public.issuer_cik_ticker_map (
    issuer_cik TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    issuer_name TEXT,
    last_seen_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cik_ticker_map_ticker ON issuer_cik_ticker_map (ticker);
CREATE INDEX IF NOT EXISTS idx_cik_ticker_map_date ON issuer_cik_ticker_map (last_seen_date DESC);
