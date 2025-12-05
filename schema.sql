-- No foreign key relationships found in the database.

CREATE TABLE public.form345_deriv_trans (
    submission_id TEXT,
    transaction_date DATE,
    issuer_cik TEXT,
    issuer_name TEXT,
    rpt_owner_cik TEXT,
    rpt_owner_name TEXT,
    transaction_code TEXT,
    transaction_shares BIGINT,
    shares_owned_following_transaction BIGINT,
    underlying_security_title TEXT,
    underlying_shares BIGINT,
    conversion_or_exercise_price DOUBLE PRECISION
);

CREATE TABLE public.form345_nonderiv_trans (
    submission_id TEXT,
    transaction_date DATE,
    issuer_cik TEXT,
    issuer_name TEXT,
    rpt_owner_cik TEXT,
    rpt_owner_name TEXT,
    transaction_code TEXT,
    transaction_shares BIGINT,
    transaction_price_per_share DOUBLE PRECISION,
    shares_owned_following_transaction BIGINT
);

CREATE TABLE public.form345_reportingowner (
    submission_id TEXT,
    issuer_cik TEXT,
    issuer_name TEXT,
    rpt_owner_cik TEXT,
    rpt_owner_name TEXT,
    is_director BOOLEAN,
    is_officer BOOLEAN,
    is_ten_percent_owner BOOLEAN,
    is_other BOOLEAN,
    officer_title TEXT
);

CREATE TABLE public.form345_submission (
    submission_id TEXT,
    filing_date DATE,
    issue_cik TEXT,
    issuer_name TEXT,
    rpt_owner_cik TEXT,
    rpt_owner_name TEXT
);

CREATE TABLE public.insider_exclusions (
    cik TEXT,
    name TEXT
);

CREATE TABLE public.insider_trades (
    issuer_cik TEXT,
    issuer_name TEXT,
    rpt_owner_cik TEXT,
    rpt_owner_name TEXT,
    transaction_date DATE,
    transaction_code TEXT,
    transaction_shares BIGINT,
    transaction_price_per_share DOUBLE PRECISION,
    shares_owned_following_transaction BIGINT
);

CREATE TABLE public.insider_buy_signals (
    issuer_cik TEXT,
    issuer_name TEXT,
    transaction_date DATE,
    total_transaction_shares BIGINT,
    average_price_per_share DOUBLE PRECISION,
    insider_count BIGINT
);

CREATE TABLE public.insider_trades_with_title (
    issuer_cik TEXT,
    issuer_name TEXT,
    rpt_owner_cik TEXT,
    rpt_owner_name TEXT,
    is_director BOOLEAN,
    is_officer BOOLEAN,
    is_ten_percent_owner BOOLEAN,
    officer_title TEXT,
    transaction_date DATE,
    transaction_code TEXT,
    transaction_shares BIGINT,
    transaction_price_per_share DOUBLE PRECISION,
    shares_owned_following_transaction BIGINT
);