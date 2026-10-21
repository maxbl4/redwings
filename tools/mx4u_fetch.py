"""Скачивание протоколов гонок mx4u.ru в кэш (cache/mx4u/races/{id}.html).

    py tools/mx4u_fetch.py [от] [до]      (по умолчанию 480..1950)

Вежливо: 1 запрос в секунду, уже скачанное не перекачивается, несуществующие id
помечаются файлом {id}.404. Остановить можно в любой момент — продолжит с места остановки.
"""
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'cache', 'mx4u', 'races')
UA = 'rw-protocols-research/1.0 (+https://rw.braaap.ru; maxbl4@gmail.com)'
DELAY = 1.0


def fetch(race_id):
    url = 'https://mx4u.ru/races/x.%d.html?mod=results' % race_id
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, ''
            if e.code in (429, 500, 502, 503):
                time.sleep(10 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(10 * (attempt + 1))
    return None, ''


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 480
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 1950
    os.makedirs(CACHE, exist_ok=True)
    got = miss = 0
    for rid in range(lo, hi + 1):
        html_path = os.path.join(CACHE, '%d.html' % rid)
        nf_path = os.path.join(CACHE, '%d.404' % rid)
        if os.path.exists(html_path) or os.path.exists(nf_path):
            continue
        status, body = fetch(rid)
        # сайт отдаёт «Страница не найдена» и с кодом 200
        if status == 404 or 'Страница не найдена' in body:
            open(nf_path, 'w').close()
            miss += 1
        elif status == 200:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(body)
            got += 1
        else:
            print('id %d: ошибка, пропущен (повторите запуск позже)' % rid, flush=True)
        if (got + miss) % 50 == 0:
            print('id %d: скачано %d, нет страницы %d' % (rid, got, miss), flush=True)
        time.sleep(DELAY)
    print('готово: скачано %d, нет страницы %d' % (got, miss))


if __name__ == '__main__':
    main()
