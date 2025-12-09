-- DDL for get-insider-db project with Foreign Key constraints

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';
SET default_table_access_method = heap;

-- form345_submission
CREATE TABLE public.form345_submission (
    "ACCESSION_NUMBER" TEXT PRIMARY KEY,
    "FILING_DATE" TEXT,
    "PERIOD_OF_REPORT" TEXT,
    "DATE_OF_ORIG_SUB" TEXT,
    "NO_SECURITIES_OWNED" TEXT,
    "NOT_SUBJECT_SEC16" TEXT,
    "FORM3_HOLDINGS_REPORTED" TEXT,
    "FORM4_TRANS_REPORTED" TEXT,
    "DOCUMENT_TYPE" TEXT,
    "ISSUERCIK" TEXT,
    "ISSUERNAME" TEXT,
    "ISSUERTRADINGSYMBOL" TEXT,
    "REMARKS" TEXT,
    "AFF10B5ONE" TEXT
);

-- form345_reportingowner
CREATE TABLE public.form345_reportingowner (
    "ACCESSION_NUMBER" TEXT REFERENCES public.form345_submission("ACCESSION_NUMBER"),
    "RPTOWNERCIK" TEXT,
    "RPTOWNERNAME" TEXT,
    "RPTOWNER_RELATIONSHIP" TEXT,
    "RPTOWNER_TITLE" TEXT,
    "RPTOWNER_TXT" TEXT,
    "RPTOWNER_STREET1" TEXT,
    "RPTOWNER_STREET2" TEXT,
    "RPTOWNER_CITY" TEXT,
    "RPTOWNER_STATE" TEXT,
    "RPTOWNER_ZIPCODE" TEXT,
    "RPTOWNER_STATE_DESC" TEXT,
    "FILE_NUMBER" TEXT
);

-- form345_nonderiv_trans
CREATE TABLE public.form345_nonderiv_trans (
    "ACCESSION_NUMBER" TEXT REFERENCES public.form345_submission("ACCESSION_NUMBER"),
    "NONDERIV_TRANS_SK" TEXT,
    "SECURITY_TITLE" TEXT,
    "SECURITY_TITLE_FN" TEXT,
    "TRANS_DATE" TEXT,
    "TRANS_DATE_FN" TEXT,
    "DEEMED_EXECUTION_DATE" TEXT,
    "DEEMED_EXECUTION_DATE_FN" TEXT,
    "TRANS_FORM_TYPE" TEXT,
    "TRANS_CODE" TEXT,
    "EQUITY_SWAP_INVOLVED" TEXT,
    "EQUITY_SWAP_TRANS_CD_FN" TEXT,
    "TRANS_TIMELINESS" TEXT,
    "TRANS_TIMELINESS_FN" TEXT,
    "TRANS_SHARES" TEXT,
    "TRANS_SHARES_FN" TEXT,
    "TRANS_PRICEPERSHARE" TEXT,
    "TRANS_PRICEPERSHARE_FN" TEXT,
    "TRANS_ACQUIRED_DISP_CD" TEXT,
    "TRANS_ACQUIRED_DISP_CD_FN" TEXT,
    "SHRS_OWND_FOLWNG_TRANS" TEXT,
    "SHRS_OWND_FOLWNG_TRANS_FN" TEXT,
    "VALU_OWND_FOLWNG_TRANS" TEXT,
    "VALU_OWND_FOLWNG_TRANS_FN" TEXT,
    "DIRECT_INDIRECT_OWNERSHIP" TEXT,
    "DIRECT_INDIRECT_OWNERSHIP_FN" TEXT,
    "NATURE_OF_OWNERSHIP" TEXT,
    "NATURE_OF_OWNERSHIP_FN" TEXT
);

-- form345_deriv_trans
CREATE TABLE public.form345_deriv_trans (
    "ACCESSION_NUMBER" TEXT REFERENCES public.form345_submission("ACCESSION_NUMBER"),
    "DERIV_TRANS_SK" TEXT,
    "SECURITY_TITLE" TEXT,
    "SECURITY_TITLE_FN" TEXT,
    "CONV_EXERCISE_PRICE" TEXT,
    "CONV_EXERCISE_PRICE_FN" TEXT,
    "TRANS_DATE" TEXT,
    "TRANS_DATE_FN" TEXT,
    "DEEMED_EXECUTION_DATE" TEXT,
    "DEEMED_EXECUTION_DATE_FN" TEXT,
    "TRANS_FORM_TYPE" TEXT,
    "TRANS_CODE" TEXT,
    "EQUITY_SWAP_INVOLVED" TEXT,
    "EQUITY_SWAP_TRANS_CD_FN" TEXT,
    "TRANS_TIMELINESS" TEXT,
    "TRANS_TIMELINESS_FN" TEXT,
    "TRANS_SHARES" TEXT,
    "TRANS_SHARES_FN" TEXT,
    "TRANS_TOTAL_VALUE" TEXT,
    "TRANS_TOTAL_VALUE_FN" TEXT,
    "TRANS_PRICEPERSHARE" TEXT,
    "TRANS_PRICEPERSHARE_FN" TEXT,
    "TRANS_ACQUIRED_DISP_CD" TEXT,
    "TRANS_ACQUIRED_DISP_CD_FN" TEXT,
    "EXCERCISE_DATE" TEXT,
    "EXCERCISE_DATE_FN" TEXT,
    "EXPIRATION_DATE" TEXT,
    "EXPIRATION_DATE_FN" TEXT,
    "UNDLYNG_SEC_TITLE" TEXT,
    "UNDLYNG_SEC_TITLE_FN" TEXT,
    "UNDLYNG_SEC_SHARES" TEXT,
    "UNDLYNG_SEC_SHARES_FN" TEXT,
    "UNDLYNG_SEC_VALUE" TEXT,
    "UNDLYNG_SEC_VALUE_FN" TEXT,
    "SHRS_OWND_FOLWNG_TRANS" TEXT,
    "SHRS_OWND_FOLWNG_TRANS_FN" TEXT,
    "VALU_OWND_FOLWNG_TRANS" TEXT,
    "VALU_OWND_FOLWNG_TRANS_FN" TEXT,
    "DIRECT_INDIRECT_OWNERSHIP" TEXT,
    "DIRECT_INDIRECT_OWNERSHIP_FN" TEXT,
    "NATURE_OF_OWNERSHIP" TEXT,
    "NATURE_OF_OWNERSHIP_FN" TEXT
);

-- insider_entities
CREATE SEQUENCE public.insider_entities_id_seq
    AS INTEGER
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE public.insider_entities (
    id INTEGER NOT NULL DEFAULT nextval('public.insider_entities_id_seq'),
    insider_id VARCHAR,
    normalized_name VARCHAR NOT NULL,
    entity_type VARCHAR NOT NULL,
    is_fund_like BOOLEAN NOT NULL,
    source VARCHAR NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT insider_entities_pkey PRIMARY KEY (id),
    CONSTRAINT uq_insider_entities_normalized_name UNIQUE (normalized_name)
);

-- insider_exclusions
CREATE SEQUENCE public.insider_exclusions_id_seq
    AS INTEGER
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE public.insider_exclusions (
    id INTEGER NOT NULL DEFAULT nextval('public.insider_exclusions_id_seq'),
    pattern TEXT NOT NULL,
    reason TEXT,
    active BOOLEAN DEFAULT TRUE NOT NULL,
    CONSTRAINT insider_exclusions_pkey PRIMARY KEY (id)
);

-- insider_trades (retained from schema_2.sql, consider adding PK/FK if this is a primary table)
CREATE TABLE public.insider_trades (
    id BIGINT,
    filing_id BIGINT,
    filed_at TIMESTAMP(6) WITHOUT TIME ZONE,
    trade_date DATE,
    issuer_ticker VARCHAR(32),
    issuer_cik VARCHAR(20),
    insider_name VARCHAR(255),
    insider_cik VARCHAR(20),
    insider_relationships VARCHAR[],
    is_officer BOOLEAN,
    is_director BOOLEAN,
    is_ten_percent BOOLEAN,
    is_ceo BOOLEAN,
    is_cfo BOOLEAN,
    transaction_code VARCHAR(4),
    security_title VARCHAR(255),
    shares NUMERIC(24,4),
    price NUMERIC(18,4),
    value_usd NUMERIC(24,2),
    ownership_direct BOOLEAN,
    created_at TIMESTAMP(6) WITHOUT TIME ZONE
);

-- VIEWS

-- insider_buy_signals
CREATE OR REPLACE VIEW public.insider_buy_signals AS
 SELECT s."ACCESSION_NUMBER" AS accession_number,
    (s."FILING_DATE")::DATE AS filing_date,
    (s."PERIOD_OF_REPORT")::DATE AS period_of_report,
    s."ISSUERTRADINGSYMBOL" AS ticker,
    s."ISSUERNAME" AS issuer_name,
    r."RPTOWNERCIK" AS insider_cik,
    r."RPTOWNERNAME" AS insider_name,
    r."RPTOWNER_TITLE" AS insider_title,
    r."RPTOWNER_RELATIONSHIP" AS insider_relationship,
    t."SECURITY_TITLE" AS security_title,
    (t."TRANS_DATE")::DATE AS transaction_date,
    t."TRANS_CODE" AS transaction_code,
    (NULLIF(t."TRANS_SHARES", ''::TEXT))::NUMERIC AS shares,
    (NULLIF(t."TRANS_PRICEPERSHARE", ''::TEXT))::NUMERIC AS price_per_share,
    ((NULLIF(t."TRANS_SHARES", ''::TEXT))::NUMERIC * (NULLIF(t."TRANS_PRICEPERSHARE", ''::TEXT))::NUMERIC) AS total_value,
    (NULLIF(t."SHRS_OWND_FOLWNG_TRANS", ''::TEXT))::NUMERIC AS shares_owned_after,
    t."DIRECT_INDIRECT_OWNERSHIP" AS direct_indirect,
    t."NATURE_OF_OWNERSHIP" AS nature_of_ownership
   FROM ((public.form345_nonderiv_trans t
     JOIN public.form345_submission s ON ((s."ACCESSION_NUMBER" = t."ACCESSION_NUMBER")))
     LEFT JOIN public.form345_reportingowner r ON ((r."ACCESSION_NUMBER" = s."ACCESSION_NUMBER")))
  WHERE (t."TRANS_CODE" = 'P'::TEXT);

-- insider_trades_with_title
CREATE OR REPLACE VIEW public.insider_trades_with_title AS
 SELECT id,
    filing_id,
    filed_at,
    trade_date,
    issuer_ticker,
    issuer_cik,
    insider_name,
    insider_cik,
    insider_relationships,
    is_officer,
    is_director,
    is_ten_percent,
    is_ceo,
    is_cfo,
    transaction_code,
    security_title,
    shares,
    price,
    value_usd,
    ownership_direct,
    created_at,
        CASE
            WHEN is_ceo THEN 'CEO'::TEXT
            WHEN is_cfo THEN 'CFO'::TEXT
            WHEN is_ten_percent THEN '10% Owner'::TEXT
            WHEN is_director THEN 'Director'::TEXT
            WHEN (is_officer AND (EXISTS ( SELECT 1
               FROM unnest(insider_trades.insider_relationships) rel(rel)
              WHERE (((rel.rel)::TEXT ~~* '%chief operating%'::TEXT) OR ((rel.rel)::TEXT ~~* '%coo%'::TEXT))))) THEN 'COO'::TEXT
            WHEN (is_officer AND (EXISTS ( SELECT 1
               FROM unnest(insider_trades.insider_relationships) rel(rel)
              WHERE ((rel.rel)::TEXT ~~* '%president%'::TEXT)))) THEN 'President'::TEXT
            WHEN (is_officer AND (EXISTS ( SELECT 1
               FROM unnest(insider_trades.insider_relationships) rel(rel)
              WHERE (((rel.rel)::TEXT ~~* '%general counsel%'::TEXT) OR ((rel.rel)::TEXT ~~* '%gc%'::TEXT))))) THEN 'GC'::TEXT
            WHEN is_officer THEN 'Officer'::TEXT
            ELSE 'Insider'::TEXT
        END AS insider_title
   FROM public.insider_trades;

-- Indexes (retained from schema_2.sql)
CREATE INDEX idx_nonderiv_accession ON public.form345_nonderiv_trans USING BTREE ("ACCESSION_NUMBER");
CREATE INDEX idx_nonderiv_trans_code ON public.form345_nonderiv_trans USING BTREE ("TRANS_CODE");
CREATE INDEX idx_nonderiv_trans_date ON public.form345_nonderiv_trans USING BTREE ("TRANS_DATE");
CREATE INDEX idx_reportingowner_accession ON public.form345_reportingowner USING BTREE ("ACCESSION_NUMBER");
CREATE INDEX idx_subm_accession ON public.form345_submission USING BTREE ("ACCESSION_NUMBER");
CREATE INDEX idx_subm_ticker_filingdate ON public.form345_submission USING BTREE ("ISSUERTRADINGSYMBOL", "FILING_DATE");
