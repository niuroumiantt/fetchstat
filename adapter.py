"""EIA table 5.6.B: Texas industrial YTD, not datacenter contract prices."""
from datetime import datetime
import re
from helpers import html, candidate, date


def extract(data, source, original, sampled_at):
    p = html(data)
    title = re.search(r'Year-to-Date through ([A-Za-z]+) (20\d\d) and (20\d\d)', p.text)
    release = re.search(r'Release Date: ([A-Za-z]+ \d{1,2}, 20\d\d)', p.text)
    if not title or not release or 'Industrial' not in p.text or 'Cents per Kilowatthour' not in p.text:
        raise ValueError('EIA period/sector/unit schema changed')
    month = datetime.strptime(title[1], '%B').month
    row = next((r for r in p.rows if len(r) == 11 and r[0] == 'Texas'), None)
    if row is None:
        raise ValueError('Texas row missing or column count changed')
    period = f'{title[2]}-{month:02d}'
    scope = f'Texas industrial sector; January through {title[1]} {title[2]}; sales-weighted average; all industrial customers, not data center tariff'
    result = candidate('statistic_series', 'EIA Texas industrial YTD electricity price',
        {'publisher': 'EIA', 'series': 'EPM 5.6.B industrial YTD', 'country': 'US', 'state': 'Texas'},
        'electricity.industrial_price', float(row[5]), 'US cents/kWh', scope, 'reported',
        'HTML Table 5.6.B; Texas row; Industrial first YTD column', row[5],
        title[0] + ' | Cents per Kilowatthour | Residential, Commercial, Industrial, Transportation, All Sectors | ' + ' | '.join(row),
        date(period, 'month', 'end of source YTD period, not a monthly-only price'),
        date(datetime.strptime(release[1], '%B %d, %Y').date().isoformat(), 'day', release[0]))
    result.update(period_start=f'{title[2]}-01-01', period_end=period, aggregation='year_to_date')
    return [result]
