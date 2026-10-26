-- Lokale cache-indexen en vooraggregaties; geen wijzigingen aan de brondatabase.
CREATE UNIQUE INDEX acts_numac ON acts(numac);
CREATE INDEX readings_act_run ON readings(act_id,run_id);
CREATE INDEX duties_act_run ON duties(act_id,run_id);
CREATE INDEX claims_act_run ON claims(act_id,run_id);
CREATE INDEX links_claim ON duty_claims(obligation_id,duty_id);
CREATE TABLE latest AS SELECT act_id,max(run_id) run_id FROM verdicts GROUP BY act_id;
CREATE UNIQUE INDEX latest_act ON latest(act_id);
CREATE TABLE reading_summary AS SELECT act_id,run_id,count(*) readings,
 sum(failed=0) successes,sum(failed=1) errors,max(text_truncated) text_truncated
 FROM readings GROUP BY act_id,run_id;
CREATE UNIQUE INDEX summary_reading ON reading_summary(act_id,run_id);
CREATE TABLE duty_totals AS SELECT act_id,run_id,count(*) duties,
 sum(n_ab_claims>0) ab_duties FROM duties GROUP BY act_id,run_id;
CREATE UNIQUE INDEX summary_duty ON duty_totals(act_id,run_id);
