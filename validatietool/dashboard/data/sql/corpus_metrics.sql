-- Unieke NUMAC's: geen secties/chunks als acts tellen. Periode is gelijk aan registerselectie.
SELECT count(*) corpus_rows,count(DISTINCT numac) corpus_acts,
 count(*) FILTER(WHERE numac IS NULL OR btrim(numac)='') corpus_missing_numac,
 count(DISTINCT numac) FILTER(WHERE prediction=1 AND certainty>=0.75) classifier_selected,
 min(pub_date_iso) corpus_date_from,max(pub_date_iso) corpus_date_to
FROM public.law_chunks
WHERE (%(date_from)s::date IS NULL OR pub_date_iso >= %(date_from)s)
AND (%(date_until)s::date IS NULL OR pub_date_iso < %(date_until)s);
