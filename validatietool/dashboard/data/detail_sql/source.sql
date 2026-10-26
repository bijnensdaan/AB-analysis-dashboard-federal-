-- Alleen metadata en citaten. Geen raw_text, llm_text of raw_response in de cache.
-- @query act
SELECT * FROM admin_burden.act;
-- @query verdict
SELECT * FROM admin_burden.act_verdict;
-- @query reading
SELECT reading_id,act_id,run_id,model_slug,act_relation,amended_acts,n_obligations_returned,
 n_obligations_kept,n_quotes_rejected,quote_reject_rate,n_fields_coerced,n_contradictions,
 text_chars,text_chars_sent,text_truncated,error,problems,read_fingerprint,prompt_id,created_at,updated_at
FROM admin_burden.reading;
-- @query duty
SELECT * FROM admin_burden.duty;
-- @query claim
SELECT o.*,r.run_id FROM admin_burden.obligation o JOIN admin_burden.reading r USING(reading_id);
-- @query review
SELECT * FROM admin_burden.review_decision;
-- @query text_metadata
-- Contentversie vaststellen zonder volledige teksten over te dragen.
SELECT act_id,n_articles,disposition,cleaner_version,updated_at,length(raw_text) raw_chars,
 length(llm_text) llm_chars,md5(raw_text) raw_hash,md5(llm_text) llm_hash
FROM admin_burden.act_text;
-- @query io_type
SELECT * FROM admin_burden.io_type;
-- @query admin_action
SELECT * FROM admin_burden.admin_action;
-- @query admin_action_io_link
SELECT * FROM admin_burden.admin_action_io_link;
-- @query cost_category
SELECT * FROM admin_burden.cost_category;
