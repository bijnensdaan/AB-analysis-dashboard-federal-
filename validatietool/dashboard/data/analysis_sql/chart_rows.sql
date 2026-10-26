-- Toegevoegd aan de gedeelde actlijst-CTE's. Eén membership is bewijs van
-- categorielidmaatschap, GEEN teleenheid. COUNT(DISTINCT duty_id/act_id) telt.
-- Zowel globale filters als een actieve grafiekselectie zijn al toegepast.
, chart_rows AS (
 SELECT DISTINCT m.point_id,m.act_id,m.run_id,m.duty_id,m.obligation_id,p.x,p.y,p.label
 FROM visible v JOIN analysisdb.membership m ON m.act_id=v.act_id AND m.run_id=v.run_id
 JOIN analysisdb.points p ON p.chart_id=m.chart_id AND p.point_id=m.point_id
 WHERE m.chart_id=?
 AND (m.duty_id IS NULL OR EXISTS(SELECT 1 FROM eligible_duties d WHERE d.duty_id=m.duty_id))
 AND (m.obligation_id IS NULL OR EXISTS(SELECT 1 FROM matched_claims c WHERE c.obligation_id=m.obligation_id))
)
SELECT point_id,x,y,label,count(DISTINCT act_id) register_acts,
 count(DISTINCT duty_id) duties
FROM chart_rows GROUP BY point_id,x,y,label;
