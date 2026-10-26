-- Aansluitende LITERALEN binnen dezelfde act/run, geen bewijs van doorgegeven data.
-- Gemeenteterm is slechts een zoekingang; actornamen worden niet geclassificeerd.
, incoming AS (
 SELECT DISTINCT m.act_id,m.run_id,m.duty_id,p.y
 FROM visible v JOIN analysisdb.membership m ON m.act_id=v.act_id AND m.run_id=v.run_id
 JOIN analysisdb.points p ON p.chart_id=m.chart_id AND p.point_id=m.point_id
 WHERE m.chart_id='actors'
 AND (p.y LIKE '%gemeente%' OR p.y LIKE '%commune%' OR p.y LIKE '%gemeinder%')
 AND EXISTS(SELECT 1 FROM eligible_duties d WHERE d.duty_id=m.duty_id)
 AND EXISTS(SELECT 1 FROM matched_claims c WHERE c.obligation_id=m.obligation_id)
)
SELECT DISTINCT a.act_id,a.numac,a.title,i.run_id
FROM incoming i JOIN acts a ON a.act_id=i.act_id
JOIN analysisdb.membership n ON n.act_id=i.act_id AND n.run_id=i.run_id AND n.chart_id='actors'
JOIN analysisdb.points q ON q.chart_id=n.chart_id AND q.point_id=n.point_id
WHERE q.x=i.y AND n.duty_id<>i.duty_id
AND EXISTS(SELECT 1 FROM eligible_duties d WHERE d.duty_id=n.duty_id)
AND EXISTS(SELECT 1 FROM matched_claims c WHERE c.obligation_id=n.obligation_id)
ORDER BY a.act_id LIMIT 5;
