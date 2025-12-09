DROP VIEW IF EXISTS public.insider_buy_signals;

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
