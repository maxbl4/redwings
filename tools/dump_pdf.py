"""Отладка разметки PDF: строки страницы со спанами (x:текст, * — жирный, / — курсив).

    py tools/dump_pdf.py protocols/file.pdf 0,3,5
"""
import sys

import pymupdf

sys.stdout.reconfigure(encoding='utf-8')
f, pages = sys.argv[1], [int(x) for x in sys.argv[2].split(',')]
d = pymupdf.open(f)
for pn in pages:
    p = d[pn]
    print('######## page', pn, 'of', len(d), p.rect)
    fills = {}
    for dr in p.get_drawings():
        if dr.get('fill') and dr['fill'] != (1, 1, 1):
            fills.setdefault(tuple(round(c, 2) for c in dr['fill']), []).append(dr['rect'])
    for k, v in fills.items():
        print('fill', k, len(v), v[:2])
    spans = [s for b in p.get_text('dict', flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)['blocks'] for l in b.get('lines', []) for s in l['spans'] if s['text'].strip()]
    spans.sort(key=lambda s: ((s['bbox'][1] + s['bbox'][3]) / 2, s['bbox'][0]))
    rows = []
    for s in spans:
        yc = (s['bbox'][1] + s['bbox'][3]) / 2
        if rows and abs(rows[-1][0] - yc) < 3:
            rows[-1][1].append(s)
        else:
            rows.append([yc, [s]])
    for yc, ss in rows:
        ss.sort(key=lambda s: s['bbox'][0])
        print('%6.1f ' % yc + ' | '.join('%d:%s%s%s' % (s['bbox'][0], s['text'], '*' if s['flags'] & 16 else '',
                                                         '/' if s['flags'] & 2 else '') for s in ss))
