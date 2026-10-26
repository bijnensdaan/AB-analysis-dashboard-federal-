-- Eén corpusact per NUMAC; alleen metadata, nooit tekst of embeddings.
SELECT numac,pub_date_iso,language,doc_type,
       (prediction=1 AND certainty>=0.75) IS TRUE AS classifier_selected
FROM public.law_chunks
ORDER BY id;
