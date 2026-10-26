"""Beleidsrubriek uit één expliciete voordragende minister in de eigen aanhef.

Dit is een rubricering van de genoemde portefeuille, geen inhoudelijke
classificatie en geen identificatie van een ministerie of bevoegde overheid.
Onvolledige, samengestelde en niet opgesomde portefeuilles blijven onbekend.
"""
import re

from .authorities import folded


REMIT_GROUPS = {
    'Werk en sociaal overleg': ['werk', 'werkgelegenheid', 'tewerkstelling en arbeid', 'werkgelegenheid, arbeid en sociaal overleg'],
    'Financiën': ['financien'],
    'Financiën en begroting': ['financien en begroting'],
    'Volksgezondheid, voedselveiligheid en leefmilieu': ['volksgezondheid', 'consumentenzaken, volksgezondheid en leefmilieu'],
    'Sociale zekerheid': ['sociale zaken', 'sociale zekerheid', 'pensioenen', 'sociale aangelegenheden'],
    'Sociale zaken, volksgezondheid en leefmilieu': ['sociale zaken en volksgezondheid'],
    'Justitie': ['justitie'],
    'Binnenlandse zaken': ['binnenlandse zaken', 'binnenlandse zaken en veiligheid', 'veiligheid en binnenlandse zaken'],
    'Buitenlandse zaken en ontwikkelingssamenwerking': ['buitenlandse zaken', 'ontwikkelingssamenwerking'],
    'Mobiliteit en vervoer': ['mobiliteit', 'vervoer', 'mobiliteit en vervoer'],
    'Mobiliteit en openbare werken': ['mobiliteit en openbare werken'],
    'Economie en energie': ['economie', 'energie', 'klimaat en energie'],
    'Landbouw en middenstand': ['landbouw', 'landbouw en middenstand', 'middenstand', 'landbouw en de kleine en middelgrote ondernemingen'],
    'Leefmilieu': ['leefmilieu', 'milieu', 'duurzame ontwikkeling'],
    'Dierenwelzijn': ['dierenwelzijn'],
    'Huisvesting': ['huisvesting', 'wonen'],
    'Ruimtelijke ordening': ['ruimtelijke ordening'],
    'Onderwijs en vorming': ['onderwijs', 'onderwijs en vorming', 'vorming'],
    'Welzijn en volksgezondheid': ['welzijn', 'welzijn, volksgezondheid en gezin'],
    'Cultuur, jeugd en media': ['cultuur', 'cultuur, jeugd en media', 'media'],
    'Defensie': ['landsverdediging', 'defensie'],
    'Wetenschapsbeleid': ['wetenschapsbeleid'],
    'Digitalisering': ['digitalisering'],
    'Noordzee': ['noordzee'],
}
REMITS = {alias: group for group, aliases in REMIT_GROUPS.items() for alias in aliases}

# Vereis een eigen, herkenbare aanhef; een vermelding in een verslag, advies,
# artikel, bijlage of geciteerde voorgeschiedenis is onvoldoende.
OPENING = re.compile(
    r"^(?:(?:filip|philippe|albert ii|albert|boudewijn|baudouin|leopold iii),"
    r"|(?:de )?(?:vlaamse regering|waalse regering|brusselse hoofdstedelijke regering"
    r"|regering van (?:het brussels hoofdstedelijk gewest|de franse gemeenschap|de duitstalige gemeenschap))\s*,"
    r"|de (?:vlaamse )?minister(?:-president)?\b)"
)
PROPOSAL = re.compile(r'op de voordracht van\s+')
END = re.compile(r'(?:hebben wij besloten|na beraadslaging|besluit\s*:|besluiten\s*:|(?:en )?op het advies van)')
OPERATIVE = re.compile(r'(?:artikel\s*1\s*[.:]|art\.\s*1\s*[.:]|hebben wij besloten|besluit\s*:)')
ROLE = re.compile(r'(?:(?:de|onze)\s+)?(?:vice-eerste minister en (?:de |onze )?)?minister(?: bevoegd)? (?:van|voor) (.+)')


def identify_remit(prefix):
    """Een volledige, eenduidige portefeuille; behoud exacte bronposities."""
    if not prefix:
        return None
    normalized, positions = folded(prefix[:4096])
    if not OPENING.match(normalized.lstrip()):
        return None
    operative = OPERATIVE.search(normalized)
    preamble_end = operative.start() if operative else len(normalized)
    proposals = list(PROPOSAL.finditer(normalized[:preamble_end]))
    if len(proposals) != 1:
        return None
    proposal = proposals[0]
    end = END.search(normalized, proposal.end())
    # Een afgekapt tekstbegin of volgende bepaling is geen volledige clausule.
    if end is None or end.start() > preamble_end:
        return None
    clause = normalized[proposal.end():end.start()].strip(' ,;\n')
    role = ROLE.fullmatch(clause)
    domain = REMITS.get(role.group(1)) if role else None
    if domain is None:
        return None
    start = positions[proposal.start()]
    stop = positions[end.start() - 1] + 1
    return {'beleidsdomein': domain, 'domain_method': 'expliciete_voordragende_portefeuille',
            'domain_evidence': [{'start': start, 'end': stop, 'text': prefix[start:stop],
                                 'method': 'expliciete_voordragende_portefeuille'}]}
