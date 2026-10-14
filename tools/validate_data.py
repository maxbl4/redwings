"""Проверка site/data.js: дырки в местах, пропущенные поля, сумма кругов != время, подозрительные города.

    py tools/validate_data.py [фильтр-id-гонки]
"""
import collections
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, 'site', 'data.js'), encoding='utf-8').read()
races = json.loads(src[src.index('=') + 1:].rstrip().rstrip(';'))
only = sys.argv[1] if len(sys.argv) > 1 else ''
bad = collections.Counter()


def report(kind, *a, limit=8):
    bad[kind] += 1
    if bad[kind] <= limit:
        print(kind, *a)


for r in races:
    if only not in r['id']:
        continue
    for g in r['groups']:
        places = [x.get('place') for x in g['rows'] if x.get('place') is not None]
        if places != list(range(1, len(places) + 1)):
            report('PLACES', r['id'], g['cls'], g['heat'], places[:30])
        for x in g['rows']:
            # в городе/клубе не должно быть цифр-номеров и времени — признак склеенных строк
            for k in ('city', 'club', 'name'):
                if re.search(r'\d+:\d\d|\b\d{2,4}\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+', x.get(k, '')):
                    report('GLUED', r['id'], g['cls'], k, repr(x.get(k)))
            if len(x.get('name', '').split()) < 2:
                report('NAME', r['id'], g['cls'], repr(x.get('name')))
            if g['heat'] == 'sum':
                continue
            for k in ('laps', 'time'):
                if k not in x:
                    report('MISSING_' + k, r['id'], g['cls'], g['heat'], x.get('name'))
            lt = x.get('lapTimes')
            if lt and x.get('time') and len(lt) == x.get('laps') and None not in lt and abs(sum(lt) - x['time']) > 1.5:
                report('LAPSUM', r['id'], g['cls'], g['heat'], x['name'], round(sum(lt), 1), x['time'])
print(dict(bad) or 'OK')
print(len(races), 'гонок,', sum(len(g['rows']) for r in races for g in r['groups']), 'строк')
