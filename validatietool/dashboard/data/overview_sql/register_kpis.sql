-- Toegevoegd aan de GEDEELDE selectie-CTE's uit actlist.selection_sql.
-- Acts: één gekozen act_verdict met leesregistratie; NULL is onbekend.
-- Duties: unieke eligible_duties van zichtbare acts, nooit claimrijen.
SELECT count(*) acts,
 coalesce(sum(ab IS TRUE),0) acts_ab,
 coalesce(sum(ab IS FALSE),0) acts_no_ab,
 coalesce(sum(ab IS NULL),0) acts_unknown,
 coalesce(sum(successes>0),0) read_success,
 coalesce(sum(successes=0),0) read_failed,
 coalesce(sum(matched_duties),0) duties,
 coalesce(sum(ab_duties),0) ab_duties,
 (SELECT count(*) FROM eligible_duties d JOIN visible v USING(act_id,run_id) WHERE d.status='accepted') duties_accepted,
 (SELECT count(*) FROM eligible_duties d JOIN visible v USING(act_id,run_id) WHERE d.status='needs_review') duties_needs_review,
 (SELECT count(*) FROM eligible_duties d JOIN visible v USING(act_id,run_id) WHERE d.status='accepted' AND d.n_ab_claims>0) ab_duties_accepted,
 (SELECT count(*) FROM eligible_duties d JOIN visible v USING(act_id,run_id) WHERE d.status='needs_review' AND d.n_ab_claims>0) ab_duties_needs_review
FROM visible;
