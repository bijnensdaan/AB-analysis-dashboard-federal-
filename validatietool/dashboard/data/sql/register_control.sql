-- Onafhankelijke controle: NOT EXISTS i.p.v. MAX-CTE; afzonderlijke scalartellingen.
-- Niets uit de productiequery wordt hergebruikt. Nooit tellen via obligation.
WITH picked AS (
 SELECT v.* FROM admin_burden.act_verdict v JOIN admin_burden.act a USING(act_id)
 WHERE ((%(run_id)s::bigint IS NOT NULL AND v.run_id=%(run_id)s) OR
 (%(run_id)s::bigint IS NULL AND NOT EXISTS(
 SELECT 1 FROM admin_burden.act_verdict newer WHERE newer.act_id=v.act_id AND newer.run_id>v.run_id)))
 AND (%(date_from)s::date IS NULL OR a.pub_date >= %(date_from)s)
 AND (%(date_until)s::date IS NULL OR a.pub_date < %(date_until)s)
)
SELECT
 (SELECT count(*) FROM picked) acts,
 (SELECT count(*) FROM picked WHERE ab IS TRUE) acts_ab,
 (SELECT count(*) FROM picked WHERE ab IS FALSE) acts_no_ab,
 (SELECT count(*) FROM picked WHERE ab IS NULL) acts_unknown,
 (SELECT count(*) FROM picked WHERE needs_review IS TRUE) acts_needs_review,
 (SELECT count(*) FROM admin_burden.duty d WHERE EXISTS(SELECT 1 FROM picked p WHERE p.act_id=d.act_id AND p.run_id=d.run_id)) duties,
 (SELECT count(*) FROM admin_burden.duty d WHERE n_ab_claims>0 AND EXISTS(SELECT 1 FROM picked p WHERE p.act_id=d.act_id AND p.run_id=d.run_id)) duties_ab,
 (SELECT count(*) FROM admin_burden.duty d WHERE status='accepted' AND EXISTS(SELECT 1 FROM picked p WHERE p.act_id=d.act_id AND p.run_id=d.run_id)) duties_accepted,
 (SELECT count(*) FROM admin_burden.duty d WHERE status='needs_review' AND EXISTS(SELECT 1 FROM picked p WHERE p.act_id=d.act_id AND p.run_id=d.run_id)) duties_needs_review,
 (SELECT count(*) FROM admin_burden.duty d WHERE n_ab_claims>0 AND status='accepted' AND EXISTS(SELECT 1 FROM picked p WHERE p.act_id=d.act_id AND p.run_id=d.run_id)) duties_ab_accepted,
 (SELECT count(*) FROM admin_burden.duty d WHERE n_ab_claims>0 AND status='needs_review' AND EXISTS(SELECT 1 FROM picked p WHERE p.act_id=d.act_id AND p.run_id=d.run_id)) duties_ab_needs_review,
 (SELECT count(DISTINCT d.act_id) FROM admin_burden.duty d WHERE status='accepted' AND EXISTS(SELECT 1 FROM picked p WHERE p.act_id=d.act_id AND p.run_id=d.run_id)) acts_with_accepted_duty,
 (SELECT count(DISTINCT r.act_id) FROM admin_burden.reading r WHERE EXISTS(SELECT 1 FROM picked p WHERE p.act_id=r.act_id AND p.run_id=r.run_id)) acts_with_reading,
 (SELECT count(DISTINCT r.act_id) FROM admin_burden.reading r WHERE nullif(btrim(r.error),'') IS NULL AND EXISTS(SELECT 1 FROM picked p WHERE p.act_id=r.act_id AND p.run_id=r.run_id)) acts_read,
 (SELECT count(*) FROM admin_burden.reading r WHERE EXISTS(SELECT 1 FROM picked p WHERE p.act_id=r.act_id AND p.run_id=r.run_id)) readings,
 (SELECT count(*) FROM admin_burden.reading r WHERE nullif(btrim(r.error),'') IS NOT NULL AND EXISTS(SELECT 1 FROM picked p WHERE p.act_id=r.act_id AND p.run_id=r.run_id)) reading_errors;
