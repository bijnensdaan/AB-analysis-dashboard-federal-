-- Teleenheid: één opgeslagen acttekst per act met een verdict, ongeacht run.
-- Alleen een begrensd tekstbegin; geen volledige actteksten naar de client.
-- Beide MD5's moeten overeenkomen met de bestaande registersnapshot.
SELECT a.act_id,a.numac,left(t.raw_text,4096) AS prefix,
       md5(t.raw_text) AS raw_hash,md5(t.llm_text) AS llm_hash
FROM admin_burden.act a
LEFT JOIN admin_burden.act_text t USING(act_id)
WHERE EXISTS (SELECT 1 FROM admin_burden.act_verdict v WHERE v.act_id=a.act_id)
ORDER BY a.act_id;
