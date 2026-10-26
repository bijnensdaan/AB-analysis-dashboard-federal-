-- Uitsluitend aangeroepen vanuit de expliciete detailmethode; geen bulkvoorladen.
SELECT act_id,raw_text,llm_text,n_articles,disposition,cleaner_version,updated_at
FROM admin_burden.act_text WHERE act_id=%(act_id)s;
