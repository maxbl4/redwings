"""Сопоставление гонщиков из нашего рейтинга с протоколами mx4u.ru (кэш tools/mx4u_fetch.py).

    py tools/mx4u_match.py            -> cache/mx4u/results.json (все строки), cache/mx4u/match.md (отчёт)

Совпадение — по «фамилия имя» (ё = е). У mx4u нет года рождения, поэтому для проверки
личности выводятся города/клубы из mx4u рядом с городами из наших протоколов.
"""
import collections
import glob
import html
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'cache', 'mx4u')
LEVELS = ['мсмк', 'мс', 'кмс', 'i', 'ii', 'iii']  # выше — сильнее


def norm(n):
    return ' '.join(html.unescape(n).lower().replace('ё', 'е').split())


def text(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def comp_level(title):
    """Уровень соревнования по названию: 3 — ЧЕ/ЧМ/MXGP, 2 — ЧР/ПР/Кубок России, 1 — округ (ФО), 0 — прочее."""
    t = title.lower()
    if re.search(r'европ|(чемпионат|кубок|этап)\w*\s+мира|mxgp|mx of nations|наций', t):
        return 3
    if re.search(r'(чемпионат|первенство|кубок)\s+(и\s+(молодежное\s+|молодёжное\s+)?первенство\s+)?(россии|мфр|фмср)', t)             or 'кубок досааф россии' in t:
        return 2
    if re.search(r'федеральн|\b(цфо|сзфо|юфо|пфо|уфо|урфо|сфо|двфо|скфо)\b|округ', t):
        return 1
    return 0


def parse_race(path):
    rid = int(os.path.basename(path).split('.')[0])
    t = open(path, encoding='utf-8').read()
    # <title>Гонка {дата}: {название}</title> — есть на всех страницах, в отличие от h1/h2
    tt = re.search(r'<title>\s*Гонка\s*(.*?):\s*(.*?)</title>', t, re.S)
    date = text(tt.group(1)) if tt else ''
    title = text(tt.group(2)) if tt else ''
    year = re.search(r'(20\d\d|19\d\d)', date)
    rows = []
    # блоки «<h3>Класс …</h3> … <table class="raceResult"> … </table>»
    for m in re.finditer(r'<h3>(.*?)</h3>(.*?)(?=<h3>|<h2>|$)', t, re.S):
        cls = re.sub(r'^Класс\s+', '', text(m.group(1)))
        tab = re.search(r'<table class="raceResult">(.*?)</table>', m.group(2), re.S)
        if not tab:
            continue
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tab.group(1), re.S):
            if "class='name'" not in tr:
                continue
            cell = lambda c: (re.search(r"<td class='%s'[^>]*>(.*?)</td>" % c, tr, re.S) or [None, ''])[1]
            name_m = re.search(r'<a href="/pilots/[^"]*?\.(\d+)\.html">(.*?)</a>', tr)
            if not name_m:
                continue
            place = text(cell('i'))
            rows.append({
                'race': rid, 'date': date, 'year': int(year.group(1)) if year else None, 'title': title,
                'level': comp_level(title), 'cls': cls,
                'place': int(place) if place.isdigit() else None,
                'pilot': int(name_m.group(1)), 'name': text(name_m.group(2)),
                'city': text(cell('clubCity')), 'rank': text(cell('sportLevel')).lower(),
                'n': len(re.findall(r"<tr", tab.group(1))) - 2,
            })
    return rows


KID_CLASS_MAX_AGE = [(r'50', 11), (r'65', 13), (r'85', 16)]


def age_ok(r, birth_years):
    """Детский класс (50/65/85) у взрослого по нашему году рождения — однофамилец."""
    if not birth_years or not r['year']:
        return True
    for pat, max_age in KID_CLASS_MAX_AGE:
        if re.search(pat, r['cls']):
            return any(r['year'] - by <= max_age for by in birth_years)
    return True


def city_tokens(s):
    s = s.lower().replace('ё', 'е')
    return {w for w in re.findall(r'[а-яa-z-]{4,}', s)} - {'город', 'область', 'московская', 'обл', 'край', 'республика', 'досааф', 'россии', 'сборная'}


def main():
    files = sorted(glob.glob(os.path.join(CACHE, 'races', '*.html')), key=lambda p: int(os.path.basename(p).split('.')[0]))
    allrows = []
    for f in files:
        allrows += parse_race(f)
    json.dump(allrows, open(os.path.join(CACHE, 'results.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    by_name = collections.defaultdict(list)
    for r in allrows:
        by_name[norm(r['name'])].append(r)

    top = json.load(open(os.path.join(ROOT, 'cache', 'top100.json'), encoding='utf-8'))
    ours = json.load(open(os.path.join(ROOT, 'cache', 'riders_info.json'), encoding='utf-8'))
    out = ['# Сопоставление топ-100 рейтинга XC с mx4u.ru', '',
           'Гонок в кэше: %d, строк результатов: %d' % (len(files), len(allrows)), '']
    found = 0
    for rank, name in top:
        k = norm(name)
        rs = by_name.get(k, [])
        o = ours.get(k, {})
        head = '## %d. %s — наши данные: г.р. %s; %s; %s' % (
            rank, name, ','.join(map(str, o.get('year', []))) or '?', ', '.join(o.get('city', [])) or '?',
            '; '.join(o.get('club', [])[:2]) or '?')
        if not rs:
            out += [head, '- в mx4u не найден', '']
            continue
        found += 1
        pilots = collections.Counter(r['pilot'] for r in rs)
        cities = collections.Counter(r['city'] for r in rs if r['city'])
        ranks = [r['rank'] for r in rs if r['rank'] in LEVELS]
        best_rank = min(ranks, key=LEVELS.index) if ranks else '—'
        years = sorted({r['year'] for r in rs if r['year']})
        out.append(head)
        out.append('- mx4u: %d стартов, %s, профили: %s' % (
            len(rs), '%s–%s' % (years[0], years[-1]) if years else '?',
            ', '.join('[%d](https://mx4u.ru/pilots/x.%d.html) (%d)' % (p, p, c) for p, c in pilots.most_common())))
        out.append('- города/клубы в mx4u: ' + '; '.join('%s (%d)' % c for c in cities.most_common(4)))
        out.append('- высший разряд: **%s**' % best_rank)
        fed = sorted((r for r in rs if r['level'] >= 2), key=lambda r: (r['place'] or 999, -(r['year'] or 0)))
        if fed:
            out.append('- федеральный уровень (%d стартов), лучшие:' % len(fed))
            for r in fed[:5]:
                out.append('  - %s место из %s — %s, %s, класс %s ([протокол](https://mx4u.ru/races/x.%d.html?mod=results))' % (
                    r['place'] or '—', r['n'], r['title'], r['date'], r['cls'], r['race']))
        reg = sorted((r for r in rs if r['level'] < 2 and r['place'] and r['place'] <= 3), key=lambda r: -(r['year'] or 0))
        if reg:
            wins = sum(1 for r in reg if r['place'] == 1)
            out.append('- подиумы на прочих гонках: %d (побед %d), последние: %s' % (
                len(reg), wins, '; '.join('%d м. %s %s' % (r['place'], r['title'][:50], r['year'] or '') for r in reg[:3])))
        out.append('')
    out.insert(3, 'Найдено в mx4u: %d из %d' % (found, len(top)))
    # короткая сводка
    summ = ['| # | Гонщик | Наши г.р. / город | mx4u: стартов, годы | Города в mx4u | Разряд | Лучшее на ЧР/ПР/Кубке России | Город совпал | Возраст | Профилей |',
            '|---|---|---|---|---|---|---|---|---|---|']
    for rank, name in top:
        k = norm(name); o = ours.get(k, {})
        rs = by_name.get(k, [])
        if not rs:
            continue
        bys = [int(y) for y in o.get('year', [])]
        good = [r for r in rs if age_ok(r, bys)]
        bad = len(rs) - len(good)
        our_tok = set().union(*[city_tokens(c) for c in o.get('city', []) + o.get('club', [])]) if o else set()
        mx_tok = set().union(*[city_tokens(r['city']) for r in good]) if good else set()
        city_ok = 'да' if our_tok & mx_tok else ('?' if not our_tok else 'нет')
        ranks = [r['rank'] for r in good if r['rank'] in LEVELS]
        best_rank = min(ranks, key=LEVELS.index) if ranks else '—'
        fed = sorted((r for r in good if r['level'] >= 2 and r['place']), key=lambda r: (r['place'], -(r['year'] or 0)))
        bestfed = ('%d/%d %s %s (%s)' % (fed[0]['place'], fed[0]['n'], re.sub(r'\s+\d.*', '', fed[0]['title'])[:40], fed[0]['year'], fed[0]['cls'])) if fed else '—'
        years = sorted({r['year'] for r in good if r['year']})
        cities = collections.Counter(r['city'] for r in good if r['city'])
        summ.append('| %d | %s | %s / %s | %d, %s | %s | %s | %s | %s | %s | %d |' % (
            rank, name, ','.join(map(str, bys)) or '?', ', '.join(o.get('city', [])[:1]) or '?',
            len(good), '%s–%s' % (years[0], years[-1]) if years else '?',
            '; '.join(c for c, _ in cities.most_common(2))[:60], best_rank, bestfed, city_ok,
            ('не сходится (%d)' % bad) if bad else 'ок', len({r['pilot'] for r in good})))
    open(os.path.join(CACHE, 'summary.md'), 'w', encoding='utf-8').write('\n'.join(summ))
    open(os.path.join(CACHE, 'match.md'), 'w', encoding='utf-8').write('\n'.join(out))
    print('гонок %d, строк %d, найдено %d из %d -> cache/mx4u/match.md' % (len(files), len(allrows), found, len(top)))


if __name__ == '__main__':
    main()
