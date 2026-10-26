-- Acts via act_verdict; duties via duty. Lezers bepalen alleen de leesstatus.
-- Eén run per act: laatste met verdict, of expliciet gekozen run zonder fallback.
WITH chosen AS (
 SELECT act_id,max(run_id) run_id FROM admin_burden.act_verdict
 WHERE (%(run_id)s::bigint IS NULL OR run_id=%(run_id)s) GROUP BY act_id
), selected AS (
 SELECT a.act_id,v.run_id,v.ab,v.ab_scope,v.needs_review
 FROM chosen c JOIN admin_burden.act a USING(act_id)
 JOIN admin_burden.act_verdict v USING(act_id,run_id)
 WHERE (%(date_from)s::date IS NULL OR a.pub_date >= %(date_from)s)
 AND (%(date_until)s::date IS NULL OR a.pub_date < %(date_until)s)
), duties AS (
 SELECT d.* FROM admin_burden.duty d JOIN selected s USING(act_id,run_id)
), readings AS (
 SELECT r.* FROM admin_burden.reading r JOIN selected s USING(act_id,run_id)
), a_counts AS (
 SELECT count(*) acts,count(*) FILTER(WHERE ab IS TRUE) acts_ab,
 count(*) FILTER(WHERE ab IS FALSE) acts_no_ab,count(*) FILTER(WHERE ab IS NULL) acts_unknown,
 count(*) FILTER(WHERE needs_review IS TRUE) acts_needs_review FROM selected
), d_counts AS (
 SELECT count(*) duties,count(*) FILTER(WHERE n_ab_claims>0) duties_ab,
 count(*) FILTER(WHERE status='accepted') duties_accepted,
 count(*) FILTER(WHERE status='needs_review') duties_needs_review,
 count(*) FILTER(WHERE n_ab_claims>0 AND status='accepted') duties_ab_accepted,
 count(*) FILTER(WHERE n_ab_claims>0 AND status='needs_review') duties_ab_needs_review,
 count(DISTINCT act_id) FILTER(WHERE status='accepted') acts_with_accepted_duty FROM duties
), r_counts AS (
 SELECT count(DISTINCT act_id) acts_with_reading,
 count(DISTINCT act_id) FILTER(WHERE nullif(btrim(error),'') IS NULL) acts_read,
 count(*) readings,count(*) FILTER(WHERE nullif(btrim(error),'') IS NOT NULL) reading_errors FROM readings
)
SELECT * FROM a_counts CROSS JOIN d_counts CROSS JOIN r_counts;
