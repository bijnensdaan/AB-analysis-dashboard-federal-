-- Alleen beschikbaarheidsmetadata; content wordt pas bij een detailopvraag geladen.
SELECT celex,count(*) sections FROM public.eu_legal_text GROUP BY celex ORDER BY celex;
