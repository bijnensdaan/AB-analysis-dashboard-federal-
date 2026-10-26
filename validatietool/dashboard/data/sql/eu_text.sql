-- Exacte CELEX-opvraag; geen gegiste koppeling op titel of vrije tekst.
SELECT celex,section_type,section_number,section_title,content
FROM public.eu_legal_text WHERE celex=%(celex)s ORDER BY id;
