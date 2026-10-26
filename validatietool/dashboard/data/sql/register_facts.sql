-- Alleen lichte act/verdictmetadata voor exacte NUMAC-koppeling. Geen bronteksten.
WITH chosen AS (
 SELECT act_id,max(run_id) run_id FROM admin_burden.act_verdict
 WHERE (%(run_id)s::bigint IS NULL OR run_id=%(run_id)s) GROUP BY act_id
)
SELECT a.numac,a.pub_date,v.ab,v.ab_scope,v.run_id,
 EXISTS(SELECT 1 FROM admin_burden.reading r WHERE r.act_id=v.act_id AND r.run_id=v.run_id
 AND nullif(btrim(r.error),'') IS NULL) read_success,
 EXISTS(SELECT 1 FROM admin_burden.duty d WHERE d.act_id=v.act_id AND d.run_id=v.run_id AND d.status='accepted') accepted
FROM chosen c JOIN admin_burden.act a USING(act_id) JOIN admin_burden.act_verdict v USING(act_id,run_id)
WHERE (%(date_from)s::date IS NULL OR a.pub_date >= %(date_from)s)
AND (%(date_until)s::date IS NULL OR a.pub_date < %(date_until)s);
