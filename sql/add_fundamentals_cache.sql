-- market_fundamentals table for caching Tiingo Daily Fundamentals
CREATE TABLE IF NOT EXISTS public.market_fundamentals (
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    market_cap NUMERIC,
    enterprise_value NUMERIC,
    pe_ratio NUMERIC,
    pb_ratio NUMERIC,
    trailing_peg_ratio NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_market_fundamentals_ticker_date ON public.market_fundamentals (ticker, date);
