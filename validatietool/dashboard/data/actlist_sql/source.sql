-- @query acts
SELECT act_id,numac,title,pub_date,act_form,level,entity,lang,url FROM admin_burden.act;
-- @query verdicts
SELECT act_id,run_id,ab,ab_scope,needs_review FROM admin_burden.act_verdict;
-- @query readings
SELECT reading_id,act_id,run_id,model_slug,text_truncated,
 (nullif(btrim(error),'') IS NOT NULL) failed FROM admin_burden.reading;
-- @query duties
SELECT duty_id,act_id,run_id,status,n_ab_claims FROM admin_burden.duty;
-- @query claims
-- Citaten van ALLE lezers, ook negatieve/losse claims. Geen volledige acttekst.
SELECT o.obligation_id,o.act_id,r.run_id,o.quote,o.io_id,o.duty_bearer_kind,o.recipient_kind,
 o.ab_scope,o.frequency,o.cost_category,o.source_kind,o.is_new_here,o.counts_as_ab
FROM admin_burden.obligation o JOIN admin_burden.reading r USING(reading_id);
-- @query duty_claims
SELECT duty_id,obligation_id FROM admin_burden.duty_claim;
-- @query text_metadata
-- Alleen lengte en kwaliteitsmetadata; raw_text/llm_text worden NIET geëxporteerd.
SELECT act_id,length(raw_text) raw_chars,disposition FROM admin_burden.act_text;
-- @query io_types
SELECT io_id,name_short FROM admin_burden.io_type;
-- @query cost_categories
SELECT code,name FROM admin_burden.cost_category;
