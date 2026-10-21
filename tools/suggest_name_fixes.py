"""Поиск вероятных опечаток в именах: пары гонщиков из site/data.js, чьи «фамилия имя»
отличаются на 1–2 символа. Найденное вручную проверить и добавить в tools/name_fixes.txt.

    py tools/suggest_name_fixes.py
"""
import collections
import json
import re
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, 'site', 'data.js'), encoding='utf-8').read()
races = json.loads(re.search(r'window\.RACES = (.*?);\n', src, re.S).group(1))


def key(n):
    return ' '.join(n.lower().replace('ё', 'е').split())


def dist(a, b, limit=2):
    """Расстояние Левенштейна с ранним выходом, если больше limit."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


# пары, уже отмеченные в name_fixes.txt как разные люди («A != B»)
distinct = set()
for line in open(os.path.join(ROOT, 'tools', 'name_fixes.txt'), encoding='utf-8'):
    line = line.split('#', 1)[0]
    if '!=' in line:
        a, b = (key(x) for x in line.split('!=', 1))
        distinct.add(frozenset((a, b)))

people = collections.defaultdict(lambda: {'n': 0, 'dates': set(), 'name': ''})
for r in races:
    for g in r['groups']:
        if g['heat'] == 'abs':
            continue
        for x in g['rows']:
            p = people[key(x['name'])]
            p['n'] += 1
            p['dates'].add(r['date'])
            p['name'] = x['name']

keys = sorted(people)
pairs = []
for i, a in enumerate(keys):
    for b in keys[i + 1:]:
        if frozenset((a, b)) in distinct:
            continue
        d = dist(a, b)
        if d > 2:
            continue
        sa, sb = a.split(' ', 1)[0], b.split(' ', 1)[0]
        # одна буква в длинной фамилии — скорее опечатка; разные имена при одной фамилии — часто родственники
        if d == 2 and sa != sb:
            continue
        pairs.append((d, people[a], people[b]))

pairs.sort(key=lambda t: t[0])
for d, pa, pb in pairs:
    rare, common = sorted((pa, pb), key=lambda p: p['n'])
    print('%-26s %2d ст.  ->  %-26s %2d ст.  [разница %d]  даты редкого: %s'
          % (rare['name'], rare['n'], common['name'], common['n'], d, ', '.join(sorted(rare['dates']))))
print('\nПар:', len(pairs))
