--
-- PostgreSQL database dump
--

\restrict shx8g9GBExn2GICQByKE5vR9t6wThL2OnNsWIC9UfWPQD9dU3NQhi5Y8mJx95pL

-- Dumped from database version 18.1 (Ubuntu 18.1-1.pgdg22.04+2)
-- Dumped by pg_dump version 18.1 (Ubuntu 18.1-1.pgdg22.04+2)

-- Started on 2026-01-26 21:30:46 SAST

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

--
-- TOC entry 232 (class 1259 OID 17727)
-- Name: cluster_event_members; Type: TABLE; Schema: public; Owner: myuser
--

CREATE TABLE public.cluster_event_members (
    cluster_id bigint NOT NULL,
    insider_id text NOT NULL,
    insider_name text,
    insider_title text,
    trade_date date NOT NULL,
    transaction_code text NOT NULL,
    shares numeric(18,4),
    price numeric(18,6),
    value_usd numeric(18,2) NOT NULL,
    ownership_delta_pct numeric(10,4)
);


ALTER TABLE public.cluster_event_members OWNER TO myuser;

--
-- TOC entry 231 (class 1259 OID 17702)
-- Name: cluster_events; Type: TABLE; Schema: public; Owner: myuser
--

CREATE TABLE public.cluster_events (
    cluster_id bigint NOT NULL,
    ticker text NOT NULL,
    window_start date NOT NULL,
    window_end date NOT NULL,
    signal_date date NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    expiry_date date NOT NULL,
    last_reinforcement_at date,
    decay_reason text,
    unique_insiders integer NOT NULL,
    total_value_usd numeric(18,2) NOT NULL,
    conviction_score numeric(18,6),
    detector_version text DEFAULT 'v1'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT cluster_events_status_check CHECK ((status = ANY (ARRAY['active'::text, 'decayed'::text, 'invalidated'::text])))
);


ALTER TABLE public.cluster_events OWNER TO myuser;

--
-- TOC entry 233 (class 1259 OID 17746)
-- Name: cluster_events_active_window; Type: VIEW; Schema: public; Owner: myuser
--

CREATE VIEW public.cluster_events_active_window AS
 SELECT cluster_id,
    ticker,
    signal_date,
    expiry_date,
    status,
    unique_insiders,
    total_value_usd,
    conviction_score
   FROM public.cluster_events
  WHERE (status = ANY (ARRAY['active'::text, 'decayed'::text, 'invalidated'::text]));


ALTER VIEW public.cluster_events_active_window OWNER TO myuser;

--
-- TOC entry 230 (class 1259 OID 17701)
-- Name: cluster_events_cluster_id_seq; Type: SEQUENCE; Schema: public; Owner: myuser
--

CREATE SEQUENCE public.cluster_events_cluster_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.cluster_events_cluster_id_seq OWNER TO myuser;

--
-- TOC entry 3491 (class 0 OID 0)
-- Dependencies: 230
-- Name: cluster_events_cluster_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: myuser
--

ALTER SEQUENCE public.cluster_events_cluster_id_seq OWNED BY public.cluster_events.cluster_id;


--
-- TOC entry 222 (class 1259 OID 17521)
-- Name: form345_deriv_trans; Type: TABLE; Schema: public; Owner: myuser
--

CREATE TABLE public.form345_deriv_trans (
    "ACCESSION_NUMBER" text,
    "DERIV_TRANS_SK" text,
    "SECURITY_TITLE" text,
    "SECURITY_TITLE_FN" text,
    "CONV_EXERCISE_PRICE" text,
    "CONV_EXERCISE_PRICE_FN" text,
    "TRANS_DATE" text,
    "TRANS_DATE_FN" text,
    "DEEMED_EXECUTION_DATE" text,
    "DEEMED_EXECUTION_DATE_FN" text,
    "TRANS_FORM_TYPE" text,
    "TRANS_CODE" text,
    "EQUITY_SWAP_INVOLVED" text,
    "EQUITY_SWAP_TRANS_CD_FN" text,
    "TRANS_TIMELINESS" text,
    "TRANS_TIMELINESS_FN" text,
    "TRANS_SHARES" text,
    "TRANS_SHARES_FN" text,
    "TRANS_TOTAL_VALUE" text,
    "TRANS_TOTAL_VALUE_FN" text,
    "TRANS_PRICEPERSHARE" text,
    "TRANS_PRICEPERSHARE_FN" text,
    "TRANS_ACQUIRED_DISP_CD" text,
    "TRANS_ACQUIRED_DISP_CD_FN" text,
    "EXCERCISE_DATE" text,
    "EXCERCISE_DATE_FN" text,
    "EXPIRATION_DATE" text,
    "EXPIRATION_DATE_FN" text,
    "UNDLYNG_SEC_TITLE" text,
    "UNDLYNG_SEC_TITLE_FN" text,
    "UNDLYNG_SEC_SHARES" text,
    "UNDLYNG_SEC_SHARES_FN" text,
    "UNDLYNG_SEC_VALUE" text,
    "UNDLYNG_SEC_VALUE_FN" text,
    "SHRS_OWND_FOLWNG_TRANS" text,
    "SHRS_OWND_FOLWNG_TRANS_FN" text,
    "VALU_OWND_FOLWNG_TRANS" text,
    "VALU_OWND_FOLWNG_TRANS_FN" text,
    "DIRECT_INDIRECT_OWNERSHIP" text,
    "DIRECT_INDIRECT_OWNERSHIP_FN" text,
    "NATURE_OF_OWNERSHIP" text,
    "NATURE_OF_OWNERSHIP_FN" text
);


ALTER TABLE public.form345_deriv_trans OWNER TO myuser;

--
-- TOC entry 221 (class 1259 OID 17516)
-- Name: form345_nonderiv_trans; Type: TABLE; Schema: public; Owner: myuser
--

CREATE TABLE public.form345_nonderiv_trans (
    "ACCESSION_NUMBER" text,
    "NONDERIV_TRANS_SK" text,
    "SECURITY_TITLE" text,
    "SECURITY_TITLE_FN" text,
    "TRANS_DATE" text,
    "TRANS_DATE_FN" text,
    "DEEMED_EXECUTION_DATE" text,
    "DEEMED_EXECUTION_DATE_FN" text,
    "TRANS_FORM_TYPE" text,
    "TRANS_CODE" text,
    "EQUITY_SWAP_INVOLVED" text,
    "EQUITY_SWAP_TRANS_CD_FN" text,
    "TRANS_TIMELINESS" text,
    "TRANS_TIMELINESS_FN" text,
    "TRANS_SHARES" text,
    "TRANS_SHARES_FN" text,
    "TRANS_PRICEPERSHARE" text,
    "TRANS_PRICEPERSHARE_FN" text,
    "TRANS_ACQUIRED_DISP_CD" text,
    "TRANS_ACQUIRED_DISP_CD_FN" text,
    "SHRS_OWND_FOLWNG_TRANS" text,
    "SHRS_OWND_FOLWNG_TRANS_FN" text,
    "VALU_OWND_FOLWNG_TRANS" text,
    "VALU_OWND_FOLWNG_TRANS_FN" text,
    "DIRECT_INDIRECT_OWNERSHIP" text,
    "DIRECT_INDIRECT_OWNERSHIP_FN" text,
    "NATURE_OF_OWNERSHIP" text,
    "NATURE_OF_OWNERSHIP_FN" text
);


ALTER TABLE public.form345_nonderiv_trans OWNER TO myuser;

--
-- TOC entry 220 (class 1259 OID 17507)
-- Name: form345_reportingowner; Type: TABLE; Schema: public; Owner: myuser
--

CREATE TABLE public.form345_reportingowner (
    "ACCESSION_NUMBER" text,
    "RPTOWNERCIK" text,
    "RPTOWNERNAME" text,
    "RPTOWNER_RELATIONSHIP" text,
    "RPTOWNER_TITLE" text,
    "RPTOWNER_TXT" text,
    "RPTOWNER_STREET1" text,
    "RPTOWNER_STREET2" text,
    "RPTOWNER_CITY" text,
    "RPTOWNER_STATE" text,
    "RPTOWNER_ZIPCODE" text,
    "RPTOWNER_STATE_DESC" text,
    "FILE_NUMBER" text
);


ALTER TABLE public.form345_reportingowner OWNER TO myuser;

--
-- TOC entry 219 (class 1259 OID 17502)
-- Name: form345_submission; Type: TABLE; Schema: public; Owner: myuser
--

CREATE TABLE public.form345_submission (
    "ACCESSION_NUMBER" text,
    "FILING_DATE" text,
    "PERIOD_OF_REPORT" text,
    "DATE_OF_ORIG_SUB" text,
    "NO_SECURITIES_OWNED" text,
    "NOT_SUBJECT_SEC16" text,
    "FORM3_HOLDINGS_REPORTED" text,
    "FORM4_TRANS_REPORTED" text,
    "DOCUMENT_TYPE" text,
    "ISSUERCIK" text,
    "ISSUERNAME" text,
    "ISSUERTRADINGSYMBOL" text,
    "REMARKS" text,
    "AFF10B5ONE" text
);


ALTER TABLE public.form345_submission OWNER TO myuser;

--
-- TOC entry 229 (class 1259 OID 17696)
-- Name: insider_buy_signals; Type: VIEW; Schema: public; Owner: myuser
--

CREATE VIEW public.insider_buy_signals AS
 SELECT s."ACCESSION_NUMBER" AS accession_number,
    (s."FILING_DATE")::date AS filing_date,
    (s."PERIOD_OF_REPORT")::date AS period_of_report,
    s."ISSUERTRADINGSYMBOL" AS ticker,
    s."ISSUERNAME" AS issuer_name,
    s."ISSUERCIK" AS issuer_cik,
    r."RPTOWNERCIK" AS insider_cik,
    r."RPTOWNERNAME" AS insider_name,
    r."RPTOWNER_TITLE" AS insider_title,
    r."RPTOWNER_RELATIONSHIP" AS insider_relationship,
    t."SECURITY_TITLE" AS security_title,
    (t."TRANS_DATE")::date AS transaction_date,
    t."TRANS_CODE" AS transaction_code,
    (NULLIF(t."TRANS_SHARES", ''::text))::numeric AS shares,
    (NULLIF(t."TRANS_PRICEPERSHARE", ''::text))::numeric AS price_per_share,
    ((NULLIF(t."TRANS_SHARES", ''::text))::numeric * (NULLIF(t."TRANS_PRICEPERSHARE", ''::text))::numeric) AS total_value,
    (NULLIF(t."SHRS_OWND_FOLWNG_TRANS", ''::text))::numeric AS shares_owned_after,
    t."DIRECT_INDIRECT_OWNERSHIP" AS direct_indirect,
    t."NATURE_OF_OWNERSHIP" AS nature_of_ownership
   FROM ((public.form345_nonderiv_trans t
     JOIN public.form345_submission s ON ((s."ACCESSION_NUMBER" = t."ACCESSION_NUMBER")))
     LEFT JOIN public.form345_reportingowner r ON ((r."ACCESSION_NUMBER" = s."ACCESSION_NUMBER")))
  WHERE (t."TRANS_CODE" = 'P'::text);


ALTER VIEW public.insider_buy_signals OWNER TO myuser;

--
-- TOC entry 267 (class 1259 OID 17800)
-- Name: insider_trade_signals; Type: VIEW; Schema: public; Owner: myuser
--

CREATE VIEW public.insider_trade_signals AS
 SELECT s."ACCESSION_NUMBER" AS accession_number,
    (s."FILING_DATE")::date AS filing_date,
    (s."PERIOD_OF_REPORT")::date AS period_of_report,
    s."ISSUERTRADINGSYMBOL" AS ticker,
    s."ISSUERNAME" AS issuer_name,
    s."ISSUERCIK" AS issuer_cik,
    r."RPTOWNERCIK" AS insider_cik,
    r."RPTOWNERNAME" AS insider_name,
    r."RPTOWNER_TITLE" AS insider_title,
    r."RPTOWNER_RELATIONSHIP" AS insider_relationship,
    t."SECURITY_TITLE" AS security_title,
    (t."TRANS_DATE")::date AS transaction_date,
    t."TRANS_CODE" AS transaction_code,
    (NULLIF(t."TRANS_SHARES", ''::text))::numeric AS shares,
    (NULLIF(t."TRANS_PRICEPERSHARE", ''::text))::numeric AS price_per_share,
    ((NULLIF(t."TRANS_SHARES", ''::text))::numeric * (NULLIF(t."TRANS_PRICEPERSHARE", ''::text))::numeric) AS total_value,
    (NULLIF(t."SHRS_OWND_FOLWNG_TRANS", ''::text))::numeric AS shares_owned_after,
    t."DIRECT_INDIRECT_OWNERSHIP" AS direct_indirect,
    t."NATURE_OF_OWNERSHIP" AS nature_of_ownership
   FROM ((public.form345_nonderiv_trans t
     JOIN public.form345_submission s ON ((s."ACCESSION_NUMBER" = t."ACCESSION_NUMBER")))
     LEFT JOIN public.form345_reportingowner r ON ((r."ACCESSION_NUMBER" = s."ACCESSION_NUMBER")))
  WHERE (t."TRANS_CODE" IN ('P', 'S'));


ALTER VIEW public.insider_trade_signals OWNER TO myuser;

--
-- TOC entry 228 (class 1259 OID 17674)
-- Name: insider_entities; Type: TABLE; Schema: public; Owner: myuser
--

CREATE TABLE public.insider_entities (
    id integer NOT NULL,
    insider_id character varying,
    normalized_name character varying NOT NULL,
    entity_type character varying NOT NULL,
    is_fund_like boolean NOT NULL,
    source character varying NOT NULL,
    confidence double precision NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.insider_entities OWNER TO myuser;

--
-- TOC entry 227 (class 1259 OID 17673)
-- Name: insider_entities_id_seq; Type: SEQUENCE; Schema: public; Owner: myuser
--

CREATE SEQUENCE public.insider_entities_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.insider_entities_id_seq OWNER TO myuser;

--
-- TOC entry 3492 (class 0 OID 0)
-- Dependencies: 227
-- Name: insider_entities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: myuser
--

ALTER SEQUENCE public.insider_entities_id_seq OWNED BY public.insider_entities.id;


--
-- TOC entry 224 (class 1259 OID 17649)
-- Name: insider_exclusions; Type: TABLE; Schema: public; Owner: myuser
--

CREATE TABLE public.insider_exclusions (
    id integer NOT NULL,
    pattern text NOT NULL,
    reason text,
    active boolean DEFAULT true NOT NULL
);


ALTER TABLE public.insider_exclusions OWNER TO myuser;

--
-- TOC entry 223 (class 1259 OID 17648)
-- Name: insider_exclusions_id_seq; Type: SEQUENCE; Schema: public; Owner: myuser
--

CREATE SEQUENCE public.insider_exclusions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.insider_exclusions_id_seq OWNER TO myuser;

--
-- TOC entry 3493 (class 0 OID 0)
-- Dependencies: 223
-- Name: insider_exclusions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: myuser
--

ALTER SEQUENCE public.insider_exclusions_id_seq OWNED BY public.insider_exclusions.id;


--
-- TOC entry 225 (class 1259 OID 17663)
-- Name: insider_trades; Type: TABLE; Schema: public; Owner: myuser
--

CREATE TABLE public.insider_trades (
    id bigint,
    filing_id bigint,
    filed_at timestamp(6) without time zone,
    trade_date date,
    issuer_ticker character varying(32),
    issuer_cik character varying(20),
    insider_name character varying(255),
    insider_cik character varying(20),
    insider_relationships character varying[],
    is_officer boolean,
    is_director boolean,
    is_ten_percent boolean,
    is_ceo boolean,
    is_cfo boolean,
    transaction_code character varying(4),
    security_title character varying(255),
    shares numeric(24,4),
    price numeric(18,4),
    value_usd numeric(24,2),
    ownership_direct boolean,
    created_at timestamp(6) without time zone
);


ALTER TABLE public.insider_trades OWNER TO myuser;

--
-- TOC entry 226 (class 1259 OID 17668)
-- Name: insider_trades_with_title; Type: VIEW; Schema: public; Owner: myuser
--

CREATE VIEW public.insider_trades_with_title AS
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
            WHEN is_ceo THEN 'CEO'::text
            WHEN is_cfo THEN 'CFO'::text
            WHEN is_ten_percent THEN '10% Owner'::text
            WHEN is_director THEN 'Director'::text
            WHEN (is_officer AND (EXISTS ( SELECT 1
               FROM unnest(insider_trades.insider_relationships) rel(rel)
              WHERE (((rel.rel)::text ~~* '%chief operating%'::text) OR ((rel.rel)::text ~~* '%coo%'::text))))) THEN 'COO'::text
            WHEN (is_officer AND (EXISTS ( SELECT 1
               FROM unnest(insider_trades.insider_relationships) rel(rel)
              WHERE ((rel.rel)::text ~~* '%president%'::text)))) THEN 'President'::text
            WHEN (is_officer AND (EXISTS ( SELECT 1
               FROM unnest(insider_trades.insider_relationships) rel(rel)
              WHERE (((rel.rel)::text ~~* '%general counsel%'::text) OR ((rel.rel)::text ~~* '%gc%'::text))))) THEN 'GC'::text
            WHEN is_officer THEN 'Officer'::text
            ELSE 'Insider'::text
        END AS insider_title
   FROM public.insider_trades;


ALTER VIEW public.insider_trades_with_title OWNER TO myuser;

--
-- TOC entry 235 (class 1259 OID 17765)
-- Name: market_fundamentals; Type: TABLE; Schema: public; Owner: myuser
--

CREATE TABLE public.market_fundamentals (
    ticker text NOT NULL,
    date date NOT NULL,
    market_cap numeric,
    enterprise_value numeric,
    pe_ratio numeric,
    pb_ratio numeric,
    trailing_peg_ratio numeric,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.market_fundamentals OWNER TO myuser;

--
-- TOC entry 234 (class 1259 OID 17753)
-- Name: market_prices; Type: TABLE; Schema: public; Owner: myuser
--

CREATE TABLE public.market_prices (
    ticker text NOT NULL,
    price_date date NOT NULL,
    close_price numeric(18,6),
    adj_close_price numeric(18,6),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.market_prices OWNER TO myuser;

--
-- TOC entry 3299 (class 2604 OID 17705)
-- Name: cluster_events cluster_id; Type: DEFAULT; Schema: public; Owner: myuser
--

ALTER TABLE ONLY public.cluster_events ALTER COLUMN cluster_id SET DEFAULT nextval('public.cluster_events_cluster_id_seq'::regclass);


--
-- TOC entry 3296 (class 2604 OID 17677)
-- Name: insider_entities id; Type: DEFAULT; Schema: public; Owner: myuser
--

ALTER TABLE ONLY public.insider_entities ALTER COLUMN id SET DEFAULT nextval('public.insider_entities_id_seq'::regclass);


--
-- TOC entry 3294 (class 2604 OID 17652)
-- Name: insider_exclusions id; Type: DEFAULT; Schema: public; Owner: myuser
--

ALTER TABLE ONLY public.insider_exclusions ALTER COLUMN id SET DEFAULT nextval('public.insider_exclusions_id_seq'::regclass);


--
-- TOC entry 3326 (class 2606 OID 17738)
-- Name: cluster_event_members cluster_event_members_pkey; Type: CONSTRAINT; Schema: public; Owner: myuser
--

ALTER TABLE ONLY public.cluster_event_members
    ADD CONSTRAINT cluster_event_members_pkey PRIMARY KEY (cluster_id, insider_id, trade_date);


--
-- TOC entry 3322 (class 2606 OID 17724)
-- Name: cluster_events cluster_events_pkey; Type: CONSTRAINT; Schema: public; Owner: myuser
--

ALTER TABLE ONLY public.cluster_events
    ADD CONSTRAINT cluster_events_pkey PRIMARY KEY (cluster_id);


--
-- TOC entry 3318 (class 2606 OID 17691)
-- Name: insider_entities insider_entities_pkey; Type: CONSTRAINT; Schema: public; Owner: myuser
--

ALTER TABLE ONLY public.insider_entities
    ADD CONSTRAINT insider_entities_pkey PRIMARY KEY (id);


--
-- TOC entry 3316 (class 2606 OID 17660)
-- Name: insider_exclusions insider_exclusions_pkey; Type: CONSTRAINT; Schema: public; Owner: myuser
--

ALTER TABLE ONLY public.insider_exclusions
    ADD CONSTRAINT insider_exclusions_pkey PRIMARY KEY (id);


--
-- TOC entry 3334 (class 2606 OID 17775)
-- Name: market_fundamentals market_fundamentals_pkey; Type: CONSTRAINT; Schema: public; Owner: myuser
--

ALTER TABLE ONLY public.market_fundamentals
    ADD CONSTRAINT market_fundamentals_pkey PRIMARY KEY (ticker, date);


--
-- TOC entry 3331 (class 2606 OID 17763)
-- Name: market_prices market_prices_pkey; Type: CONSTRAINT; Schema: public; Owner: myuser
--

ALTER TABLE ONLY public.market_prices
    ADD CONSTRAINT market_prices_pkey PRIMARY KEY (ticker, price_date);


--
-- TOC entry 3320 (class 2606 OID 17693)
-- Name: insider_entities uq_insider_entities_normalized_name; Type: CONSTRAINT; Schema: public; Owner: myuser
--

ALTER TABLE ONLY public.insider_entities
    ADD CONSTRAINT uq_insider_entities_normalized_name UNIQUE (normalized_name);


--
-- TOC entry 3323 (class 1259 OID 17726)
-- Name: idx_cluster_events_active; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_cluster_events_active ON public.cluster_events USING btree (status, expiry_date);


--
-- TOC entry 3324 (class 1259 OID 17725)
-- Name: idx_cluster_events_ticker_signal; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_cluster_events_ticker_signal ON public.cluster_events USING btree (ticker, signal_date);


--
-- TOC entry 3327 (class 1259 OID 17744)
-- Name: idx_cluster_members_cluster; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_cluster_members_cluster ON public.cluster_event_members USING btree (cluster_id);


--
-- TOC entry 3328 (class 1259 OID 17745)
-- Name: idx_cluster_members_ticker_date; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_cluster_members_ticker_date ON public.cluster_event_members USING btree (trade_date);


--
-- TOC entry 3332 (class 1259 OID 17776)
-- Name: idx_market_fundamentals_ticker_date; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_market_fundamentals_ticker_date ON public.market_fundamentals USING btree (ticker, date);


--
-- TOC entry 3329 (class 1259 OID 17764)
-- Name: idx_market_prices_ticker_date; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_market_prices_ticker_date ON public.market_prices USING btree (ticker, price_date);


--
-- TOC entry 3311 (class 1259 OID 17644)
-- Name: idx_nonderiv_accession; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_nonderiv_accession ON public.form345_nonderiv_trans USING btree ("ACCESSION_NUMBER");


--
-- TOC entry 3312 (class 1259 OID 17645)
-- Name: idx_nonderiv_trans_code; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_nonderiv_trans_code ON public.form345_nonderiv_trans USING btree ("TRANS_CODE");


--
-- TOC entry 3313 (class 1259 OID 25975)
-- Name: idx_nonderiv_trans_code_accession; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_nonderiv_trans_code_accession ON public.form345_nonderiv_trans USING btree ("TRANS_CODE", "ACCESSION_NUMBER");


--
-- TOC entry 3314 (class 1259 OID 17647)
-- Name: idx_nonderiv_trans_date; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_nonderiv_trans_date ON public.form345_nonderiv_trans USING btree ("TRANS_DATE");


--
-- TOC entry 3310 (class 1259 OID 17646)
-- Name: idx_reportingowner_accession; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_reportingowner_accession ON public.form345_reportingowner USING btree ("ACCESSION_NUMBER");


--
-- TOC entry 3306 (class 1259 OID 17642)
-- Name: idx_subm_accession; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_subm_accession ON public.form345_submission USING btree ("ACCESSION_NUMBER");


--
-- TOC entry 3307 (class 1259 OID 25976)
-- Name: idx_subm_filing_date; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_subm_filing_date ON public.form345_submission USING btree ("FILING_DATE");


--
-- TOC entry 3308 (class 1259 OID 25977)
-- Name: idx_subm_filing_ticker; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_subm_filing_ticker ON public.form345_submission USING btree ("FILING_DATE", "ISSUERTRADINGSYMBOL");


--
-- TOC entry 3309 (class 1259 OID 17643)
-- Name: idx_subm_ticker_filingdate; Type: INDEX; Schema: public; Owner: myuser
--

CREATE INDEX idx_subm_ticker_filingdate ON public.form345_submission USING btree ("ISSUERTRADINGSYMBOL", "FILING_DATE");


--
-- TOC entry 3335 (class 2606 OID 17739)
-- Name: cluster_event_members cluster_event_members_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: myuser
--

ALTER TABLE ONLY public.cluster_event_members
    ADD CONSTRAINT cluster_event_members_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.cluster_events(cluster_id) ON DELETE CASCADE;


--
-- Enrichment checkpointing for crash recovery
--

CREATE TABLE IF NOT EXISTS public.enrichment_checkpoints (
    run_id text PRIMARY KEY,
    last_processed_index integer NOT NULL DEFAULT 0,
    processed_tickers jsonb NOT NULL DEFAULT '[]'::jsonb,
    errors jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.enrichment_checkpoints OWNER TO myuser;

CREATE INDEX IF NOT EXISTS idx_checkpoint_updated ON public.enrichment_checkpoints (updated_at);


--
-- Signal audit trail (event-sourced, immutable)
--

CREATE TABLE IF NOT EXISTS public.signal_history (
    id bigserial PRIMARY KEY,
    cluster_id bigint NOT NULL REFERENCES public.cluster_events(cluster_id) ON DELETE CASCADE,
    event_type text NOT NULL,  -- 'created', 'status_changed', 'score_updated', 'enriched', 'invalidated'
    changed_by text NOT NULL,  -- 'system', 'enrichment', 'manual', 'decay_job', 'backtest'
    old_values jsonb,          -- Previous state (null for 'created')
    new_values jsonb,          -- New state
    reason text,               -- Optional explanation
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.signal_history OWNER TO myuser;

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_signal_history_cluster ON public.signal_history (cluster_id, created_at);
CREATE INDEX IF NOT EXISTS idx_signal_history_event ON public.signal_history (event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_signal_history_changed_by ON public.signal_history (changed_by, created_at);

COMMENT ON TABLE public.signal_history IS 'Append-only audit trail for cluster signal lifecycle events';
COMMENT ON COLUMN public.signal_history.event_type IS 'created|status_changed|score_updated|enriched|invalidated';
COMMENT ON COLUMN public.signal_history.changed_by IS 'Actor: system|enrichment|manual|decay_job|backtest';


-- Completed on 2026-01-26 21:30:56 SAST

--
-- PostgreSQL database dump complete
--

\unrestrict shx8g9GBExn2GICQByKE5vR9t6wThL2OnNsWIC9UfWPQD9dU3NQhi5Y8mJx95pL
