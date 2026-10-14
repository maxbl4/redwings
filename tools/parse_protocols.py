"""Парсер PDF-протоколов -> site/data.js

Формат borisovo.club/timing — «Финишный протокол» (по кругам / очки / абсолют / сумма очков).

Запуск:  py tools/parse_protocols.py
Зависимости: pip install pymupdf
"""
import glob
import hashlib
import json
import os
import re
import shutil
import sys
from collections import OrderedDict

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTO_DIR = os.path.join(ROOT, 'protocols')
OUT = os.path.join(ROOT, 'site', 'data.js')
PDF_OUT = os.path.join(ROOT, 'site', 'protocols')  # оригиналы для скачивания с сайта

TIME_RE = re.compile(r'^(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)$')
GAP_RE = re.compile(r'^(-|\+[\d:.]+|-\d+\s*кр\.?)$')
INT_RE = re.compile(r'^\d+$')
HEAT_RE = re.compile(r'(\d)\s*-?\s*й\s+заезд', re.I)
DATE_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})')
LETTER_RE = re.compile(r'[A-Za-zА-Яа-яЁё]')
STATUSES = {'DSQ', 'DNF', 'DNS', 'Н/Ф', 'Н/С', 'СХОД'}

DISC_BY_PREFIX = [
    ('КАНТРИКРОСС', 'XC'),
    ('МОТОКРОСС', 'MX'),
    ('СУПЕРСПРИНТ', 'SS'),
    ('СУПЕР-СПРИНТ', 'SS'),
    ('ЭНДУРО', 'EN'),
    ('СУПЕР-ЭНДУРО', 'EN'),
    ('СУПЕРЭНДУРО', 'EN'),
]


def parse_time(s):
    s = s.strip()
    m = TIME_RE.match(s)
    if not m or ':' not in s and '.' not in s:
        return None
    parts = [float(p) for p in s.split(':')]
    v = 0.0
    for p in parts:
        v = v * 60 + p
    return round(v, 1)


def disc_from_text(t):
    t = t.lower()
    if 'эндуро' in t:
        return 'EN'
    if 'спринт' in t and 'кантри' not in t:
        return 'SS'
    if 'мотокросс' in t:
        return 'MX'
    if 'кантри' in t:
        return 'XC'
    if 'спринт' in t:
        return 'SS'
    return None


def disc_from_class(name):
    u = name.upper()
    for pref, d in DISC_BY_PREFIX:
        if u.startswith(pref):
            return d
    return None


def header_key(label):
    l = label.strip().rstrip('.').lower()
    if l in ('кр',):
        return 'laps'
    if l in ('финиш', 'время'):
        return 'time'
    if l == 'г.р':
        return 'year'
    if l == 'город':
        return 'city'
    if l == 'клуб':
        return 'club'
    if l == 'мин':
        return 'best'
    if l in ('сред', 'срed'):
        return 'avg'
    if l == 'макс':
        return 'worst'
    if l.startswith('очк'):
        return 'points'
    if l.startswith('сум') or l == 'су':
        return 'sum'
    if l.startswith('1й'):
        return 'h1'
    if l.startswith('2й'):
        return 'h2'
    if l in ('мес', 'место', 'ме'):
        return 'place'
    if INT_RE.match(l):
        return 'lap%s' % l
    return None


NUMLIKE_RE = re.compile(r'^[+-]?[\d:.]+$')


def split_span(s):
    """Генератор PDF иногда склеивает соседние ячейки в один спан: '10 442', '6:34.3 6:51.1'.
    Отделяем ведущие числовые токены. Координаты символов оцениваем пропорционально
    (rawdict с точными координатами в pymupdf очень медленный; цифры в Arial одной ширины)."""
    words, cur = [], []
    for ch in s['chars']:
        if ch['c'].isspace():
            if cur:
                words.append(cur)
                cur = []
        else:
            cur.append(ch)
    if cur:
        words.append(cur)
    out = []
    i = 0
    while i < len(words) - 1 and NUMLIKE_RE.match(''.join(c['c'] for c in words[i])):
        w = words[i]
        out.append((''.join(c['c'] for c in w), w[0]['bbox'][0], w[-1]['bbox'][2]))
        i += 1
    if not out:
        return [(s['t'], s['bbox'][0], s['bbox'][2])]
    rest = words[i:]
    text = ' '.join(''.join(c['c'] for c in w) for w in rest)
    if NUMLIKE_RE.match(text) or ' ' not in text or not LETTER_RE.search(text):
        # хвост — тоже одно число/время или одно слово
        if len(rest) == 1 or all(NUMLIKE_RE.match(''.join(c['c'] for c in w)) for w in rest):
            out += [(''.join(c['c'] for c in w), w[0]['bbox'][0], w[-1]['bbox'][2]) for w in rest]
            return out
    # хвост с буквами (имя, «кр.») оставляем одним спаном; «-1 кр.» не трогаем
    if out and LETTER_RE.search(text) and len(out) == 1 and out[0][0].startswith('-'):
        return [(s['t'], s['bbox'][0], s['bbox'][2])]
    out.append((text, rest[0][0]['bbox'][0], rest[-1][-1]['bbox'][2]))
    return out


def page_rows(page):
    spans = []
    # без картинок (логотипы): с ними извлечение медленнее в ~60 раз
    for b in page.get_text('dict', flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                s['t'] = s['text'].strip()
                if not s['t']:
                    continue
                parts = [(s['t'], s['bbox'][0], s['bbox'][2])]
                if ' ' in s['t']:
                    x0, x1, text = s['bbox'][0], s['bbox'][2], s['text']
                    cw = (x1 - x0) / max(1, len(text))
                    s['chars'] = [{'c': c, 'bbox': (x0 + i * cw, 0, x0 + (i + 1) * cw, 0)} for i, c in enumerate(text)]
                    parts = split_span(s)
                for t, x0, x1 in parts:
                    spans.append({
                        't': t,
                        'x0': x0, 'x1': x1,
                        'y0': s['bbox'][1], 'y1': s['bbox'][3],
                        'bold': bool(s['flags'] & 16),
                        'italic': bool(s['flags'] & 2),
                        'size': s['size'],
                    })
    spans.sort(key=lambda s: ((s['y0'] + s['y1']) / 2, s['x0']))
    rows = []
    for s in spans:
        yc = (s['y0'] + s['y1']) / 2
        if rows and abs(rows[-1]['yc'] - yc) < 3:
            rows[-1]['spans'].append(s)
        else:
            rows.append({'yc': yc, 'spans': [s]})
    for r in rows:
        r['spans'].sort(key=lambda s: s['x0'])
        r['text'] = ' '.join(s['t'] for s in r['spans'])
    red = []
    for dr in page.get_drawings():
        f = dr.get('fill')
        if f and len(f) == 3 and f[0] > 0.6 and f[1] < 0.25 and f[2] < 0.25:
            red.append(dr['rect'])
    return rows, red


def split_header_spans(spans):
    """Разбить склеенные заголовки типа '№Участник', '1й заезд'."""
    out = []
    for s in spans:
        t = s['t']
        if t.startswith('№') and len(t) > 1:
            w = (s['x1'] - s['x0']) / len(t)
            out.append(dict(s, t='№', x1=s['x0'] + w))
            out.append(dict(s, t=t[1:].strip(), x0=s['x0'] + w))
        else:
            out.append(s)
    return out


class Section:
    def __init__(self, kind, heat, disc=None):
        self.kind = kind  # laps | points | abs | sum
        self.heat = heat  # None | 1 | 2
        self.disc = disc  # дисциплина, если указана на странице (в одном файле бывают и МХ, и XC)
        self.classes = OrderedDict()  # name -> list of records


def parse_record(spans, cols, name_x, no_x):
    """spans: отсортированные по x спаны строки с местом."""
    rec = {}
    i = 0
    if spans and spans[0]['t'].upper() in STATUSES:
        rec['status'] = spans[0]['t'].upper()
        i = 1
    ints = []
    while i < len(spans) and INT_RE.match(spans[i]['t']) and spans[i]['x0'] < name_x - 2:
        ints.append(spans[i])
        i += 1
    if len(ints) >= 2:
        rec['place'], rec['bib'] = int(ints[0]['t']), int(ints[1]['t'])
    elif len(ints) == 1 and 'status' in rec:
        rec['bib'] = int(ints[0]['t'])
    elif len(ints) == 1:
        # одно число: место (левее колонки «№») или номер (строка без места, напр. DSQ)
        if ints[0]['x1'] < no_x - 1:
            rec['place'] = int(ints[0]['t'])
        else:
            rec['bib'] = int(ints[0]['t'])
    # имя — текстовый спан сразу за номером
    rec['name'] = ''
    if i < len(spans) and LETTER_RE.search(spans[i]['t']) and not GAP_RE.match(spans[i]['t']):
        rec['name'] = spans[i]['t']
        i += 1
    assign_rest(rec, spans[i:], cols)
    return rec


def nearest_col(span, cols, allowed=None):
    xc = (span['x0'] + span['x1']) / 2
    best, bd = None, 1e9
    for c in cols:
        if allowed and not (c['key'] in allowed or any(c['key'].startswith(a) for a in allowed if a.endswith('*'))):
            continue
        d = abs(c['xc'] - xc)
        if d < bd:
            best, bd = c, d
    return best


def assign_rest(rec, spans, cols):
    col_keys = {c['key'] for c in cols}
    for s in spans:
        t = s['t']
        if re.match(r'^\(\d+\)$', t):
            c = nearest_col(s, cols, [k for k in col_keys if k.startswith('lap')])
            if c:
                rec.setdefault('lapRanks', {})[int(c['key'][3:])] = int(t[1:-1])
            continue
        if GAP_RE.match(t) or re.match(r'^-\d+$', t):
            if re.match(r'^-\d+$', t):
                t = t + ' кр.'
            rec['gap'] = t
            continue
        if t in ('кр.', 'кр'):
            if rec.get('gap', '').startswith('-') and 'кр' not in rec['gap']:
                rec['gap'] += ' кр.'
            continue
        if t.upper() in STATUSES:
            rec['status'] = t.upper()
            continue
        tv = parse_time(t) if (':' in t or '.' in t) else None
        if tv is not None:
            c = nearest_col(s, cols, ['time', 'best', 'avg', 'worst'] + [k for k in col_keys if k.startswith('lap')])
            if c:
                if c['key'].startswith('lap'):
                    rec.setdefault('lapMap', {})[int(c['key'][3:])] = tv
                else:
                    rec[c['key']] = tv
            continue
        if INT_RE.match(t):
            v = int(t)
            c = nearest_col(s, cols, ['laps', 'year', 'points', 'h1', 'h2', 'sum', 'place'])
            if c:
                if c['key'] == 'year' or (1900 <= v < 2030 and 'year' in col_keys and len(t) == 4):
                    # 1900, 2025 и т.п. — заглушки в заявках
                    if 1930 < v < 2022:
                        rec['year'] = v
                else:
                    rec[c['key']] = v
            continue
        # текст: город / клуб
        c = nearest_col(s, cols, ['city', 'club'])
        if c:
            rec[c['key']] = (rec.get(c['key'], '') + ' ' + t).strip()
        elif s['italic']:
            rec['club'] = (rec.get('club', '') + ' ' + t).strip()
        elif LETTER_RE.search(t):
            # колонка без заголовка справа (класс в общем заезде)
            rec['subcls'] = (rec.get('subcls', '') + ' ' + t).strip()


def parse_file(path):
    doc = pymupdf.open(path)
    fname = os.path.basename(path)
    info = {'file': fname, 'title': None, 'date': None, 'location': None, 'sections': []}
    cur_section = None
    cur_class = None
    for page in doc:
        rows, red = page_rows(page)
        if not rows:
            continue
        title = rows[0]['text']
        # вторая строка шапки иногда — просто название дисциплины («МОТОКРОСС», «КАНТРИКРОСС»)
        page_disc = disc_from_class(rows[1]['text'].strip()) if len(rows) > 1 and rows[1]['yc'] < 75 else None
        subtitle = ''
        header = None
        for r in rows[:10]:
            if 'ротокол' in r['text'] and not subtitle:
                subtitle = r['text']
            m = DATE_RE.search(r['text'])
            if m and not info['date'] and r['yc'] < 125:
                info['date'] = m.group(0)
            if 'Участник' in r['text'] and header is None:
                header = r
        if info['title'] is None:
            info['title'] = title
        # место проведения — строка сразу под датой
        for i, r in enumerate(rows[:8]):
            if DATE_RE.fullmatch(r['text'].strip()) and i + 1 < len(rows) and not info['location']:
                loc = rows[i + 1]['text']
                if 'Количество' not in loc and 'Участник' not in loc:
                    info['location'] = loc
        if header is None:
            continue
        sl = subtitle.lower()
        if 'абсолют' in sl:
            kind = 'abs'
        elif 'сумма' in sl:
            kind = 'sum'
        elif 'очки' in sl:
            kind = 'points'
        else:
            kind = 'laps'
        hm = HEAT_RE.search(subtitle) or HEAT_RE.search(title)
        heat = int(hm.group(1)) if hm and kind in ('laps', 'points') else None
        if re.search(r'класс\s+\S+', subtitle):
            # выборка по клубу (напр. «класс S17») — дублирует основные протоколы
            cur_section = None
            continue
        if cur_section is None or cur_section.kind != kind or cur_section.heat != heat                 or (page_disc and cur_section.disc != page_disc):
            cur_section = Section(kind, heat, page_disc)
            info['sections'].append(cur_section)
            cur_class = 'Абсолют' if kind == 'abs' else None
        # колонки
        hs = split_header_spans(header['spans'])
        cols = []
        name_x = None
        no_x = 30
        for s in hs:
            if s['t'] == 'Участник':
                name_x = s['x0']
            if s['t'] == '№':
                no_x = s['x0']
            k = header_key(s['t'])
            if k:
                cols.append({'key': k, 'xc': (s['x0'] + s['x1']) / 2, 'x0': s['x0']})
        if name_x is None:
            name_x = 60
        # в заголовках "№" стоит над номером, а имя может начинаться левее "Участник"
        name_x = min(name_x, min((s['x0'] for r in rows if r['yc'] > header['yc'] for s in r['spans']
                                  if LETTER_RE.search(s['t']) and s['x0'] > 30), default=name_x))
        last = None
        for r in rows:
            if r['yc'] <= header['yc'] + 2:
                continue
            if 'borisovo.club' in r['text']:
                continue
            is_red = any(rr.y0 - 1 <= r['yc'] <= rr.y1 + 1 for rr in red)
            first = r['spans'][0]
            if is_red or (not INT_RE.match(first['t']) and first['x0'] < 20 and not first['italic']
                          and disc_from_class(r['text'])):
                cur_class = re.sub(r'\s+', ' ', r['text']).strip()
                last = None
                continue
            if (INT_RE.match(first['t']) or first['t'].upper() in STATUSES) and first['x0'] < name_x - 2:
                if cur_class is None:
                    cur_class = 'Абсолют' if kind == 'abs' else 'Общий заезд'
                rec = parse_record(r['spans'], cols, name_x, no_x)
                if not rec.get('name'):
                    continue
                cur_section.classes.setdefault(cur_class, []).append(rec)
                last = rec
            elif last is not None:
                # строка-продолжение (клуб курсивом, отставание, места на кругах, перенос кругов)
                sp = r['spans']
                if sp and LETTER_RE.search(sp[0]['t']) and sp[0]['x0'] < name_x + 60 and not GAP_RE.match(sp[0]['t']):
                    last['club'] = (last.get('club', '') + ' ' + sp[0]['t']).strip()
                    sp = sp[1:]
                assign_rest(last, sp, cols)
    return info


PATRONYMIC_RE = re.compile(r'(вич|вна|ична|чна|ьич|оглы|кызы)$', re.I)


def load_name_fixes():
    """tools/name_fixes.txt: «как в протоколе -> как правильно» (опечатки в фамилиях/именах)."""
    fixes = {}
    path = os.path.join(ROOT, 'tools', 'name_fixes.txt')
    if os.path.exists(path):
        for line in open(path, encoding='utf-8'):
            line = line.split('#', 1)[0].strip()
            if '->' in line:
                wrong, right = (x.strip() for x in line.split('->', 1))
                fixes[norm_name(wrong)] = right
    return fixes


NAME_FIXES = {}
lap_fixes = []
fixes_used = set()


def fix_name(n):
    key = norm_name(n)
    if key in NAME_FIXES:
        fixes_used.add(key)
        return NAME_FIXES[key]
    return n


def strip_patronymic(n):
    """«Данилкин Егор Алексеевич» -> «Данилкин Егор» (сопоставление по фамилии и имени)."""
    w = n.split()
    if len(w) == 3 and PATRONYMIC_RE.search(w[2]):
        w = w[:2]
    return ' '.join(w)


def norm_name(n):
    n = re.sub(r'\s+', ' ', n.replace('ё', 'е').replace('Ё', 'Е')).strip().lower()
    return n


def pretty_name(n):
    def cap(w):
        return '-'.join(p[:1].upper() + p[1:].lower() for p in w.split('-'))
    return ' '.join(cap(w) for w in n.split())


def date_from_filename(fname):
    for m in re.finditer(r'(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)', fname):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return '20%02d-%02d-%02d' % (y, mo, d)
    return None


def finalize_rec(r):
    out = OrderedDict()
    for k in ('place', 'bib', 'name', 'year', 'city', 'club', 'laps', 'time', 'gap', 'best', 'avg', 'worst',
              'points', 'h1', 'h2', 'sum', 'status', 'subcls'):
        if k in r and r[k] not in (None, ''):
            out[k] = r[k]
    if out.get('name'):
        out['name'] = fix_name(strip_patronymic(out['name']))
    if r.get('lapMap'):
        n = max(r['lapMap'])
        out['lapTimes'] = [r['lapMap'].get(i) for i in range(1, n + 1)]
    # ошибка протокола: «Кр.» не совпадает с числом кругов, хотя их сумма = финишному времени
    # (31.01.26: 32 круга вместо 7) — верим кругам
    lt = out.get('lapTimes')
    if lt and None not in lt and out.get('time') and out.get('laps') and len(lt) != out['laps']             and abs(sum(lt) - out['time']) < 1.5:
        lap_fixes.append('%s: %s круг(ов) -> %d по времени кругов' % (out.get('name'), out['laps'], len(lt)))
        out['laps'] = len(lt)
    if r.get('lapRanks'):
        n = max(r['lapRanks'])
        out['lapRanks'] = [r['lapRanks'].get(i) for i in range(1, n + 1)]
    return out


def merge_into(dst, src):
    for k, v in src.items():
        if k not in dst or dst[k] in (None, '', []):
            dst[k] = v
        elif k == 'lapTimes' and len(v) > len(dst[k]):
            dst[k] = v
        elif k == 'name' and len(v) > len(dst[k]):
            dst[k] = v


def venue_of(location):
    """Место проведения по адресу из протокола. «о.Русский» — это Дракино
    (в 2025 г. в адрес дописали деревню; темп кругов на трассах совпадает)."""
    loc = (location or '').lower()
    if 'дракино' in loc or 'русский' in loc:
        return 'Дракино'
    if 'васильевское' in loc:
        return 'Васильевское'
    m = re.search(r'(?:д|с|пос|г)\.\s*([А-ЯЁ][а-яё-]+)', location or '')
    return m.group(1) if m else None


def fmt_gap(sec):
    m, s_ = divmod(round(sec, 1), 60)
    return '+%d:%04.1f' % (m, s_) if m else '+%.1f' % s_


def synth_absolute(race):
    """Кантри-кросс без листа «абсолют» в PDF: все классы едут одним заездом,
    поэтому абсолют = все участники по кругам (больше — выше), затем по времени."""
    seen = {}
    for g in race['groups'].values():
        if g['heat'] != 'main':
            continue
        for r in g['rows'].values():
            # один гонщик в двух классах — одинаковые круги и время; тёзки — разные
            k = (norm_name(r.get('name', '')), r.get('laps'), r.get('time'))
            if k[0] and k not in seen and r.get('laps') and r.get('time'):
                seen[k] = r
    rows = []
    taken = set()
    for r in sorted(seen.values(), key=lambda r: (-r['laps'], r['time'])):
        # тот же номер и имя с разными результатами в двух классах (ошибка протокола) — берём лучший
        k = (r.get('bib'), norm_name(r['name']))
        if k not in taken:
            taken.add(k)
            rows.append(r)
    out = OrderedDict()
    for i, r in enumerate(rows):
        a = OrderedDict((k, r[k]) for k in ('bib', 'name', 'club', 'laps', 'time', 'lapTimes') if k in r)
        a['place'] = i + 1
        lead = rows[0]
        a['gap'] = '-' if i == 0 else (fmt_gap(r['time'] - lead['time']) if r['laps'] == lead['laps']
                                       else '-%d кр.' % (lead['laps'] - r['laps']))
        out[(r.get('bib'), norm_name(r['name']))] = a
    return {'cls': 'Абсолют', 'heat': 'abs', 'rows': out, 'synthetic': True}


def main():
    files = sorted(glob.glob(os.path.join(PROTO_DIR, '*.pdf')))
    races = OrderedDict()
    warnings = []
    seen_md5 = {}
    NAME_FIXES.update(load_name_fixes())
    for f in files:
        md5 = hashlib.md5(open(f, 'rb').read()).hexdigest()
        if md5 in seen_md5:
            warnings.append('%s — дубль %s, пропущен' % (os.path.basename(f), seen_md5[md5]))
            continue
        seen_md5[md5] = os.path.basename(f)
        info = parse_file(f)
        fname = info['file']
        date = info['date'] or date_from_filename(fname)
        fdate = date_from_filename(fname)
        if info['date'] and fdate and fdate != info['date']:
            warnings.append('%s: дата в файле %s, в имени %s' % (fname, info['date'], fdate))
        # дисциплина файла: по названиям классов, иначе по заголовку
        cnt = {}
        for s in info['sections']:
            for c, recs in s.classes.items():
                d = disc_from_class(c)
                if d:
                    cnt[d] = cnt.get(d, 0) + len(recs)
        file_disc = max(cnt, key=cnt.get) if cnt else disc_from_text(info['title'] or '') or '?'
        for s in info['sections']:
            sc = {}
            for c, recs in s.classes.items():
                d = disc_from_class(c)
                if d:
                    sc[d] = sc.get(d, 0) + len(recs)
            disc = s.disc or (max(sc, key=sc.get) if sc else file_disc)
            rid = '%s-%s' % (date, disc.lower())
            race = races.get(rid)
            if race is None:
                race = races[rid] = {
                    'id': rid, 'date': date, 'disc': disc,
                    'title': re.sub(r'\s+\d-?й\s+заезд\s*$', '', info['title'] or '').strip(),
                    'location': info['location'], 'files': [], 'groups': OrderedDict(),
                }
            if fname not in race['files']:
                race['files'].append(fname)
            if not race['location'] and info['location']:
                race['location'] = info['location']
            for cname, recs in s.classes.items():
                if s.kind == 'abs':
                    heat = 'abs'
                    cls = cname
                elif s.kind == 'sum':
                    heat = 'sum'
                    cls = cname
                else:
                    heat = str(s.heat) if s.heat else 'main'
                    cls = cname
                key = (cls, heat)
                g = race['groups'].get(key)
                if g is None:
                    g = race['groups'][key] = {'cls': cls, 'heat': heat, 'rows': OrderedDict()}
                for r in recs:
                    fr = finalize_rec(r)
                    # один и тот же гонщик из разных протоколов: номер + имя
                    # (номера иногда дублируются, имя бывает сокращено до фамилии)
                    nn = norm_name(fr.get('name', ''))
                    k = next((k for k, v in g['rows'].items()
                              if k[0] == fr.get('bib') and (k[1] == nn or k[1].startswith(nn) or nn.startswith(k[1]))),
                             None)
                    if k is not None:
                        merge_into(g['rows'][k], fr)
                    else:
                        g['rows'][(fr.get('bib'), nn)] = fr
    for race in races.values():
        if race['disc'] == 'XC' and not any(g['heat'] == 'abs' for g in race['groups'].values()):
            race['groups'][('Абсолют', 'abs')] = synth_absolute(race)
            warnings.append('%s: абсолюта в PDF нет — собран из протоколов классов' % race['id'])
    # адрес у протоколов без шапки (суперспринт) — от гонок того же дня
    for race in races.values():
        if not race['location']:
            race['location'] = next((r['location'] for r in races.values()
                                     if r['date'] == race['date'] and r['location']), None)
        race['venue'] = venue_of(race['location'])
        if not race['venue']:
            warnings.append('%s: не удалось определить место по адресу «%s»' % (race['id'], race['location']))
    out_races = []
    for race in races.values():
        groups = []
        for g in race['groups'].values():
            rows = list(g['rows'].values())
            rows.sort(key=lambda r: (r.get('place') is None, r.get('place') or 0))
            for r in rows:
                r['name'] = pretty_name(r.get('name', ''))
            groups.append({'cls': g['cls'], 'heat': g['heat'], 'rows': rows} | ({'synthetic': True} if g.get('synthetic') else {}))
        out_races.append({k: race[k] for k in ('id', 'date', 'disc', 'title', 'location', 'venue', 'files')} | {'groups': groups})
    out_races.sort(key=lambda r: r['date'], reverse=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as fh:
        fh.write('// Сгенерировано tools/parse_protocols.py — не редактировать вручную\n')
        fh.write('window.RACES = ')
        json.dump(out_races, fh, ensure_ascii=False, separators=(',', ':'))
        fh.write(';\n')
    # оригиналы PDF (без дублей) рядом с сайтом
    shutil.rmtree(PDF_OUT, ignore_errors=True)
    os.makedirs(PDF_OUT)
    for fname in seen_md5.values():
        shutil.copy2(os.path.join(PROTO_DIR, fname), os.path.join(PDF_OUT, fname))
    for f in sorted(set(lap_fixes)):
        warnings.append('исправлено число кругов: ' + f)
    for k in NAME_FIXES:
        if k not in fixes_used:
            warnings.append('name_fixes.txt: «%s» не встретилось ни в одном протоколе' % k)
    sys.stdout.reconfigure(encoding='utf-8')
    for w in warnings:
        print('WARN', w)
    for r in out_races:
        n = sum(len(g['rows']) for g in r['groups'])
        print(r['date'], r['disc'], len(r['groups']), 'групп', n, 'строк', r['files'])


if __name__ == '__main__':
    main()
