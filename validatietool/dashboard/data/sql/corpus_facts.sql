-- Geen law_chunks.text of embeddings laden. Alleen exacte koppelsleutel en classifierselectie.
SELECT numac,pub_date_iso,(prediction=1 AND certainty>=0.75) IS TRUE classifier_selected
FROM public.law_chunks
WHERE (%(date_from)s::date IS NULL OR pub_date_iso >= %(date_from)s)
AND (%(date_until)s::date IS NULL OR pub_date_iso < %(date_until)s);
