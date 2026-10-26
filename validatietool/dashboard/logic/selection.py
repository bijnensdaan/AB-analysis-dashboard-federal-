"""De run- en periodeselectie voor de datalaag; overige filters volgen in fase 5."""
from dataclasses import asdict, dataclass
from datetime import date


@dataclass(frozen=True)
class Selection:
    run_id: int | None = None
    year_from: int | None = None
    year_to: int | None = None

    def __post_init__(self):
        if self.run_id is not None and (type(self.run_id) is not int or self.run_id < 1):
            raise ValueError('Run moet een positief geheel getal zijn.')
        for value in (self.year_from, self.year_to):
            if value is not None and (type(value) is not int or not 1 <= value <= 9998):
                raise ValueError('Jaar moet tussen 1 en 9998 liggen.')
        if self.year_from is not None and self.year_to is not None and self.year_from > self.year_to:
            raise ValueError('Het beginjaar moet vóór of gelijk aan het eindjaar liggen.')

    def parameters(self):
        """Bovengrens is exclusief: 2020–2021 omvat beide volledige kalenderjaren."""
        return {'run_id': self.run_id,
                'date_from': date(self.year_from, 1, 1) if self.year_from else None,
                'date_until': date(self.year_to + 1, 1, 1) if self.year_to else None}

    def as_dict(self):
        return asdict(self)
