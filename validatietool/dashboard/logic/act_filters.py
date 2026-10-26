"""Gedeelde actlijstfilters: dezelfde claim voor alle lezerskenmerken."""
from dataclasses import asdict, dataclass
import re

from .selection import Selection

CLAIM_FIELDS = ('io_id','duty_bearer_kind','recipient_kind','scope','frequency',
                'cost_category','source_kind','is_new_here')
SORT_FIELDS = ('numac','title','pub_date','act_form','level','orgaan','ab','ab_duties',
               'scope','needs_review','truncated','run_id','lang')


def norm(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip().casefold()


def search_terms(filters):
    query=norm(filters.q)
    # Accept a pasted identifier label, while keeping title/quote searches literal.
    if filters.q_in in ('all','numac'):
        identifier=re.fullmatch(r"['\"‘’“”]?\s*numac\s*[:·#-]?\s*(\d{10})\s*['\"‘’“”]?",query)
        if identifier:query=identifier.group(1)
    return query.split()


@dataclass(frozen=True)
class ActFilters:
    run_id: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    level: str = ''
    entity: str = ''
    act_form: str = ''
    lang: str = ''
    orgaan: str = ''
    beleidsdomein: str = ''
    io_id: str = ''
    duty_bearer_kind: str = ''
    recipient_kind: str = ''
    scope: str = ''
    frequency: str = ''
    cost_category: str = ''
    source_kind: str = ''
    is_new_here: str = ''
    duty_status: str = ''
    verdict: str = ''
    truncated: str = ''
    disposition: str = ''
    q: str = ''
    q_in: str = 'all'
    sort: str = 'pub_date'
    direction: str = 'desc'
    page: int = 1
    size: int = 25
    chart_id: str = ''
    point_id: str = ''

    def __post_init__(self):
        Selection(self.run_id,self.year_from,self.year_to)
        if self.chart_id or self.point_id:
            from .analysis import CHARTS
            charts=self.chart_id.split(',');points=self.point_id.split(',')
            if len(charts)!=len(points) or len(charts)>6 or any(c not in CHARTS for c in charts) or any(not re.fullmatch('[0-9a-f]{32}',p) for p in points):
                raise ValueError('Ongeldige grafiekselectie.')
        if self.q_in not in ('all','numac','title','quote') or self.sort not in SORT_FIELDS:
            raise ValueError('Onbekend zoekveld of sorteerveld.')
        if self.direction not in ('asc','desc'):
            raise ValueError('Onbekende sorteerrichting.')
        for value in (self.verdict,self.truncated):
            if value not in ('','yes','no','unknown'):
                raise ValueError('Onbekende ja/nee/onbekend-selectie.')
        if self.is_new_here not in ('','yes','no','unknown'):
            raise ValueError('Onbekende nieuwheidsselectie.')
        if self.duty_status not in ('','accepted','needs_review'):
            raise ValueError('Onbekende bepalingsstatus.')
        if type(self.page) is not int or self.page<1 or type(self.size) is not int or not 1<=self.size<=100:
            raise ValueError('Pagina moet positief zijn; paginagrootte 1–100.')
        if len(self.q)>500:
            raise ValueError('Gebruik maximaal 500 tekens; zoek met een fragment van een langere titel of citaat.')
        for key,value in asdict(self).items():
            if isinstance(value,str) and key!='q' and len(value)>300:
                raise ValueError('Filterwaarde is te lang.')

    @classmethod
    def from_params(cls, values):
        unknown = set(values)-set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError('Onbekende filterparameter.')
        converted=dict(values)
        for key in ('run_id','year_from','year_to','page','size'):
            if key in converted:
                if str(converted[key]).strip()=='':
                    converted.pop(key)
                else:
                    try:converted[key]=int(converted[key])
                    except (TypeError,ValueError):raise ValueError('Ongeldig getal in selectie.') from None
        return cls(**converted)

    def as_dict(self):
        return asdict(self)
