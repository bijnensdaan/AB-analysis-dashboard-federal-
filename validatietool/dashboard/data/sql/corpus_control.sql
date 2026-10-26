-- Losse controle: eerst per NUMAC groeperen, daarna sommen. Zelfde brontransactie.
WITH period AS (
 SELECT * FROM public.law_chunks
 WHERE (%(date_from)s::date IS NULL OR pub_date_iso >= %(date_from)s)
 AND (%(date_until)s::date IS NULL OR pub_date_iso < %(date_until)s)
), grouped AS (
 SELECT numac,bool_or(prediction=1 AND certainty>=0.75) selected FROM period GROUP BY numac
)
SELECT (SELECT count(*) FROM period) corpus_rows,
 (SELECT count(*) FROM grouped WHERE numac IS NOT NULL) corpus_acts,
 (SELECT count(*) FROM period WHERE numac IS NULL OR btrim(numac)='') corpus_missing_numac,
 (SELECT count(*) FROM grouped WHERE numac IS NOT NULL AND selected IS TRUE) classifier_selected,
 (SELECT min(pub_date_iso) FROM period) corpus_date_from,
 (SELECT max(pub_date_iso) FROM period) corpus_date_to;
