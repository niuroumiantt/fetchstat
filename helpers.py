"""Native HTML text and tables; scripts are data only, never executed."""
from html.parser import HTMLParser


class NativeHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.rows, self.row, self.cell = [], [], None, None
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        if self.skip:
            return
        if tag == 'tr':
            self.row = []
        if tag in ('th', 'td') and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in ('th', 'td') and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell = None
        if tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)
            if self.cell is not None:
                self.cell.append(data)

    @property
    def text(self):
        return ' '.join(' '.join(self.parts).split())


def html(data):
    p = NativeHTML()
    p.feed(data.decode('utf-8'))
    return p


def unknown():
    return {'value': None, 'precision': 'unknown', 'basis': None}


def date(value, precision, basis):
    return {'value': value, 'precision': precision, 'basis': basis}


def candidate(typ, name, identifiers, metric, value, unit, scope, kind, locator, quote, context,
              effective=None, published=None):
    number = isinstance(value, (int, float))
    return {'object': {'type': typ, 'name': name, 'identifiers': identifiers,
                       'match_status': 'unresolved', 'canonical_id': None},
            'metric': metric, 'value': {'type': 'number' if number else 'text',
                                      'number' if number else 'text': value, 'raw': quote},
            'unit': unit, 'scope': scope, 'kind': kind,
            'effective_time': effective or unknown(), 'published_time': published or unknown(),
            'evidence': {'locator': locator, 'quote': quote, 'context': context}}
