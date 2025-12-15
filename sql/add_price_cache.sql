-- market_prices table for caching EOD data
CREATE TABLE IF NOT EXISTS public.market_prices (
    ticker TEXT NOT NULL,
    price_date DATE NOT NULL,
    close_price NUMERIC(18, 6),
    adj_close_price NUMERIC(18, 6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, price_date)
);

CREATE INDEX IF NOT EXISTS idx_market_prices_ticker_date ON public.market_prices (ticker, price_date);
