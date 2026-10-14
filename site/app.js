'use strict';

const RACES = window.RACES || [];
const DISC = { XC: 'Кантри-кросс', MX: 'Мотокросс', SS: 'Суперспринт', EN: 'Супер-эндуро' };
const HEAT_LABEL = { sum: 'Итог', main: 'Результаты', 1: '1 заезд', 2: '2 заезд', abs: 'Абсолют' };
const HEAT_ORDER = ['sum', 'main', '1', '2', 'abs'];
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

const $app = document.getElementById('app');
let useFirstLap = lsGet('firstLap', false);
const LAP_LEGEND = () => `<div class="muted" style="padding:8px">${useFirstLap ? '' : '1-й круг (серый) не учитывается в лучшем круге · '}Цвета кругов: <span style="color:var(--fastest);font-weight:700">быстрейший в классе на этом круге</span> · <span style="color:var(--best);font-weight:700">личный лучший</span> · <span style="color:var(--slow)">медленнее медианы гонщика на 15%+</span></div>`;

// ---------- утилиты ----------
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function nkey(name) {
  return String(name || '').toLowerCase().replace(/ё/g, 'е').replace(/[.]/g, '').replace(/\s+/g, ' ').trim();
}
function fmtTime(sec) {
  if (sec == null) return '';
  const neg = sec < 0; sec = Math.abs(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const ss = s.toFixed(1).padStart(4, '0');
  const out = h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
  return (neg ? '-' : '') + out;
}
function fmtDate(d, withYear = true) {
  const [y, m, dd] = d.split('-').map(Number);
  return `${dd} ${MONTHS[m - 1]}${withYear ? ' ' + y : ''}`;
}
function fmtDateShort(d) {
  const [y, m, dd] = d.split('-');
  return `${dd}.${m}.${y.slice(2)}`;
}
function weekday(d) { return WEEKDAYS[new Date(d + 'T12:00:00').getDay()]; }
function shortCls(c) {
  return String(c).replace(/^(КАНТРИ-?КРОСС|МОТОКРОСС|СУПЕР-?ЭНДУРО|СУПЕР-?СПРИНТ|ЭНДУРО)\s*[-–]?\s*/i, '') || c;
}
function placeHtml(p, status) {
  if (p == null) return `<span class="muted">${esc(status || '—')}</span>`;
  return `<span class="place ${p <= 3 ? 'p' + p : ''}">${p}</span>`;
}
function riderLink(name) {
  return `<a href="#/rider/${encodeURIComponent(nkey(name))}">${esc(name)}</a>`;
}
function parseHash() {
  const h = decodeURIComponent(location.hash.replace(/^#\/?/, ''));
  const [path, qs] = h.split('?');
  const parts = path.split('/').filter(Boolean);
  const q = new URLSearchParams(qs || '');
  return { parts, q };
}
function setQuery(params) {
  const { parts, q } = parseHash();
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === '') q.delete(k); else q.set(k, v);
  }
  const s = q.toString();
  history.replaceState(null, '', '#/' + parts.map(encodeURIComponent).join('/') + (s ? '?' + s : ''));
}
function matchesQuery(row, words) {
  if (!words.length) return true;
  const hay = nkey(row.name) + ' ' + (row.bib != null ? '#' + row.bib + ' ' + row.bib : '');
  return words.every(w => {
    if (/^\d+$/.test(w)) return row.bib === Number(w);
    return hay.includes(w);
  });
}
function lsGet(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }
function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* ignore */ } }

// ---------- подготовка данных ----------
const raceById = new Map();
for (const r of RACES) {
  raceById.set(r.id, r);
  const classes = new Map();
  for (const g of r.groups) {
    if (!classes.has(g.cls)) classes.set(g.cls, { name: g.cls, heats: {} });
    classes.get(g.cls).heats[g.heat] = g;
    for (const row of g.rows) row.key = nkey(row.name);
  }
  r.classes = [...classes.values()].sort((a, b) => (a.heats.abs ? 1 : 0) - (b.heats.abs ? 1 : 0));
  for (const c of r.classes) {
    c.heatList = HEAT_ORDER.filter(h => c.heats[h]);
    c.count = Math.max(...c.heatList.map(h => c.heats[h].rows.length));
  }
  r.participants = new Set(r.groups.filter(g => g.heat !== 'abs').flatMap(g => g.rows.map(x => x.key))).size;
  // класс каждого гонщика (для абсолюта)
  r.clsOf = new Map();
  for (const g of r.groups) if (g.heat !== 'abs') for (const row of g.rows) r.clsOf.set(row.key, g.cls);
}

// индекс гонщиков: key -> { name, entries: [{race, cls, heats:{heat:row}, abs}] }
const people = new Map();
for (const r of RACES) {
  const absRows = new Map();
  for (const c of r.classes) if (c.heats.abs) for (const row of c.heats.abs.rows) absRows.set(row.key, row);
  for (const c of r.classes) {
    if (c.heats.abs) continue;
    const byKey = new Map();
    for (const h of c.heatList) for (const row of c.heats[h].rows) {
      if (!row.key) continue;
      if (!byKey.has(row.key)) byKey.set(row.key, {});
      byKey.get(row.key)[h] = row;
    }
    for (const [key, heats] of byKey) {
      if (!people.has(key)) people.set(key, { key, name: null, entries: [] });
      const p = people.get(key);
      p.entries.push({ race: r, cls: c.name, heats, abs: absRows.get(key) });
    }
  }
}
for (const p of people.values()) {
  p.entries.sort((a, b) => b.race.date.localeCompare(a.race.date));
  const e = p.entries[0];
  p.name = Object.values(e.heats)[0].name;
  const counts = {};
  for (const x of p.entries) counts[x.race.disc] = (counts[x.race.disc] || 0) + 1;
  p.discCounts = counts;
}

// ---------- навигация ----------
function render() {
  const { parts } = parseHash();
  const page = parts[0] || '';
  document.querySelectorAll('[data-nav]').forEach(a => {
    const n = a.dataset.nav;
    a.classList.toggle('active', (n === 'races' && (page === '' || page === 'race')) || n === page);
  });
  window.scrollTo(0, 0);
  if (page === 'race') return renderRace(parts[1]);
  if (page === 'rider') return renderRider(parts[1]);
  if (page === 'rating') return renderRating();
  return renderRaces();
}
window.addEventListener('hashchange', render);
const $firstLap = document.getElementById('firstLap');
$firstLap.checked = useFirstLap;
$firstLap.onchange = () => {
  useFirstLap = $firstLap.checked;
  lsSet('firstLap', useFirstLap);
  const y = window.scrollY;
  render();
  window.scrollTo(0, y);
};

// ---------- список гонок ----------
function renderRaces() {
  document.title = 'Гонки — протоколы';
  const discOn = lsGet('discFilter', []);
  const byDate = new Map();
  for (const r of RACES) {
    if (discOn.length && !discOn.includes(r.disc)) continue;
    if (!byDate.has(r.date)) byDate.set(r.date, []);
    byDate.get(r.date).push(r);
  }
  const discs = Object.keys(DISC).filter(d => RACES.some(r => r.disc === d));
  const years = [...new Set(RACES.map(r => r.date.slice(0, 4)))];
  let html = `<h1>Гонки</h1><div class="sub">${RACES.length} протоколов, ${people.size} гонщиков · новые сверху</div>
    <div class="filters">${discs.map(d => `<button class="chip ${discOn.includes(d) ? 'on' : ''}" data-disc="${d}">${DISC[d]}</button>`).join('')}</div>`;
  for (const y of years) {
    const dates = [...byDate.keys()].filter(d => d.startsWith(y));
    if (!dates.length) continue;
    html += `<h2>${y}</h2><div class="panel">`;
    for (const d of dates) {
      html += `<div class="day"><div class="date">${fmtDate(d, false)}<small>${weekday(d)}, ${fmtDateShort(d)}</small></div><div class="items">`;
      for (const r of byDate.get(d)) {
        html += `<a class="race-link" href="#/race/${r.id}"><span class="badge ${r.disc}">${r.disc}</span>
          <span class="t">${esc(r.title)}</span><span class="muted">${r.participants} уч.</span></a>`;
      }
      html += `</div></div>`;
    }
    html += `</div>`;
  }
  $app.innerHTML = html;
  $app.querySelectorAll('[data-disc]').forEach(b => b.onclick = () => {
    const d = b.dataset.disc;
    const cur = lsGet('discFilter', []);
    lsSet('discFilter', cur.includes(d) ? cur.filter(x => x !== d) : [...cur, d]);
    renderRaces();
  });
}

// ---------- страница гонки ----------
function renderRace(id) {
  const r = raceById.get(id);
  if (!r) { $app.innerHTML = '<div class="empty">Гонка не найдена</div>'; return; }
  document.title = `${DISC[r.disc] || r.disc} ${fmtDateShort(r.date)}`;
  const { q } = parseHash();
  let cls = q.get('cls');
  if (!r.classes.find(c => c.name === cls)) cls = r.classes[0] && r.classes[0].name;
  const state = { cls, heat: q.get('heat'), search: q.get('q') || '', laps: lsGet('showLaps', false) };

  const sameDay = RACES.filter(x => x.date === r.date && x.id !== r.id);
  $app.innerHTML = `
    <h1><span class="badge ${r.disc}">${r.disc}</span> ${esc(r.title)}</h1>
    <div class="sub">${fmtDate(r.date)} (${weekday(r.date)}) · ${esc(r.location || '')} · ${r.participants} участников
      ${sameDay.length ? ' · в этот день также: ' + sameDay.map(x => `<a href="#/race/${x.id}">${DISC[x.disc] || x.disc}</a>`).join(', ') : ''}</div>
    <div class="files">Оригинал протокола: ${r.files.map(f => `<a href="protocols/${encodeURIComponent(f)}" target="_blank" rel="noopener">⬇ ${esc(f)}</a>`).join(' ')}</div>
    <div class="race-layout">
      <div class="panel classes" id="classes"></div>
      <div>
        <div class="toolbar">
          <select class="class-select" id="classSelect"></select>
          <input class="search" id="search" type="search" placeholder="Поиск по номеру или фамилии во всей гонке" value="${esc(state.search)}">
          <span id="heatTabs"></span>
          <label class="toggle"><input type="checkbox" id="lapsToggle" ${state.laps ? 'checked' : ''}> Круги</label>
        </div>
        <div class="panel tbl-wrap" id="results"></div>
      </div>
    </div>`;

  const $classes = document.getElementById('classes');
  const $select = document.getElementById('classSelect');
  const $search = document.getElementById('search');

  function drawClasses() {
    let html = '';
    r.classes.forEach((c, i) => {
      if (c.heats.abs && i > 0 && !r.classes[i - 1].heats.abs) html += '<div class="sep"></div>';
      html += `<button data-cls="${esc(c.name)}" class="${c.name === state.cls && !state.search ? 'on' : ''}">
        <span>${esc(shortCls(c.name))}</span><span class="n">${c.count}</span></button>`;
    });
    $classes.innerHTML = html;
    $select.innerHTML = r.classes.map(c => `<option ${c.name === state.cls ? 'selected' : ''}>${esc(c.name)}</option>`).join('');
    $classes.querySelectorAll('button').forEach(b => b.onclick = () => selectClass(b.dataset.cls));
  }
  function selectClass(name) {
    state.cls = name; state.heat = null; state.search = ''; $search.value = '';
    setQuery({ cls: name, heat: null, q: null });
    drawClasses(); drawResults();
  }
  $select.onchange = () => selectClass($select.value);
  $search.oninput = () => {
    state.search = $search.value;
    setQuery({ q: state.search || null });
    drawClasses(); drawResults();
  };
  document.getElementById('lapsToggle').onchange = e => {
    state.laps = e.target.checked; lsSet('showLaps', state.laps); drawResults();
  };

  function drawResults() {
    const $res = document.getElementById('results');
    const $tabs = document.getElementById('heatTabs');
    const words = nkey(state.search).split(' ').filter(Boolean);
    if (words.length) {
      $tabs.innerHTML = '';
      // поиск по всей гонке: все классы и заезды
      let html = '';
      let found = 0;
      for (const c of r.classes) {
        for (const h of c.heatList) {
          const g = c.heats[h];
          const rows = g.rows.filter(x => matchesQuery(x, words));
          if (!rows.length) continue;
          found += rows.length;
          const title = h === 'abs' || (h === 'main' && c.heatList.length === 1) ? shortCls(c.name) : shortCls(c.name) + ' · ' + HEAT_LABEL[h];
          html += `<div class="group-title">${esc(title)}</div>` + resultsTable(r, g, rows, state.laps, true);
        }
      }
      $res.innerHTML = found ? html + (state.laps ? LAP_LEGEND() : '') : '<div class="empty">Ничего не найдено</div>';
      bindRowClicks($res);
      return;
    }
    const c = r.classes.find(x => x.name === state.cls);
    if (!c) { $res.innerHTML = '<div class="empty">Нет данных</div>'; return; }
    if (!state.heat || !c.heats[state.heat]) state.heat = c.heatList[0];
    $tabs.innerHTML = c.heatList.length > 1
      ? `<span class="tabs">${c.heatList.map(h => `<button data-heat="${h}" class="${h === state.heat ? 'on' : ''}">${HEAT_LABEL[h]}</button>`).join('')}</span>` : '';
    $tabs.querySelectorAll('button').forEach(b => b.onclick = () => {
      state.heat = b.dataset.heat; setQuery({ heat: state.heat }); drawResults();
    });
    const g = c.heats[state.heat];
    $res.innerHTML = (g.synthetic ? '<div class="muted" style="padding:8px 8px 0">В оригинальном протоколе абсолюта нет — он собран из протоколов классов (все классы ехали одним заездом): больше кругов — выше, при равных кругах — меньше время.</div>' : '')
      + resultsTable(r, g, g.rows, state.laps, false) + (state.laps && g.heat !== 'sum' ? LAP_LEGEND() : '');
    bindRowClicks($res);
  }
  drawClasses(); drawResults();
}

function resultsTable(race, g, rows, showLaps, compact) {
  const has = k => g.rows.some(x => x[k] != null && x[k] !== '');
  const isSum = g.heat === 'sum';
  const isAbs = g.heat === 'abs';
  const cols = [];
  cols.push({ h: 'Место', cls: 'c', f: x => placeHtml(x.place, x.status) });
  cols.push({ h: '№', cls: 'num', f: x => esc(x.bib) });
  cols.push({ h: 'Гонщик', cls: 'name', f: x => riderLink(x.name) });
  if (isAbs) cols.push({ h: 'Класс', f: x => esc(shortCls(race.clsOf.get(x.key) || '')) });
  if (g.rows.some(x => x.subcls)) cols.push({ h: 'Класс', f: x => esc(x.subcls || '') });
  if (!compact && has('year')) cols.push({ h: 'Г.р.', cls: 'num', f: x => esc(x.year || '') });
  if (!compact && has('city')) cols.push({ h: 'Город', cls: 'wrap', f: x => esc(x.city || '') });
  if (!compact && has('club')) cols.push({ h: 'Клуб', cls: 'wrap', f: x => esc(x.club || '') });
  if (isSum) {
    cols.push({ h: '1 заезд', cls: 'num', f: x => esc(x.h1 ?? '') });
    cols.push({ h: '2 заезд', cls: 'num', f: x => esc(x.h2 ?? '') });
    cols.push({ h: 'Сумма', cls: 'num', f: x => `<b>${esc(x.sum ?? '')}</b>` });
  } else {
    cols.push({ h: 'Кр.', cls: 'num', f: x => esc(x.laps ?? '') });
    cols.push({ h: 'Время', cls: 'num', f: x => `<b>${fmtTime(x.time)}</b>` });
    cols.push({ h: 'Отст.', cls: 'num', f: x => esc(x.gap && x.gap !== '-' ? x.gap : '') });
    if (has('best') || g.rows.some(x => x.lapTimes)) cols.push({ h: 'Лучший', cls: 'num', f: x => fmtTime(bestLap(x)) });
    if (!showLaps && has('avg')) cols.push({ h: 'Средний', cls: 'num', f: x => fmtTime(x.avg) });
    if (has('points')) cols.push({ h: 'Очки', cls: 'num', f: x => `<b>${esc(x.points ?? '')}</b>` });
  }
  let lapCols = 0;
  let fastest = [];
  if (showLaps && !isSum) {
    lapCols = Math.max(0, ...g.rows.map(x => (x.lapTimes || []).length));
    for (let i = 0; i < lapCols; i++) {
      const v = g.rows.map(x => (x.lapTimes || [])[i]).filter(v => v != null);
      fastest[i] = v.length && countedLap(i, 2) ? Math.min(...v) : null;
    }
  }
  let html = '<table><thead><tr>' + cols.map(c => `<th class="${c.cls || ''}">${c.h}</th>`).join('');
  for (let i = 0; i < lapCols; i++) html += `<th class="num">${i + 1}</th>`;
  html += '</tr></thead><tbody>';
  for (const x of rows) {
    html += `<tr data-key="${esc(x.key)}">` + cols.map(c => `<td class="${c.cls || ''}">${c.f(x)}</td>`).join('');
    if (lapCols) {
      const lt = x.lapTimes || [];
      const bi = bestLapIdx(x);
      const med = median(lt.filter((v, i) => v != null && countedLap(i, lt.length)));
      for (let i = 0; i < lapCols; i++) {
        const v = lt[i];
        let k = 'lap';
        if (v != null && !countedLap(i, lt.length)) k += ' excluded';
        else if (v != null && v === fastest[i] && lt.length > 1) k += ' fastest';
        else if (i === bi) k += ' best';
        else if (v != null && med && v > med * 1.15) k += ' slow';
        html += `<td class="${k}">${v != null ? fmtTime(v) : ''}</td>`;
      }
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}
// Первый круг обычно короче (старт дают не от линии круга), поэтому по умолчанию
// он не участвует в лучшем круге; галочка в шапке включает его обратно.
function countedLap(i, n) { return useFirstLap || i > 0 || n === 1; }
function bestLapIdx(x) {
  const lt = x.lapTimes || [];
  let bi = -1;
  lt.forEach((v, i) => { if (v != null && countedLap(i, lt.length) && (bi < 0 || v < lt[bi])) bi = i; });
  return bi;
}
function bestLap(x) {
  const bi = bestLapIdx(x);
  if (bi >= 0) return x.lapTimes[bi];
  // кругов нет в протоколе — берём «Мин» из листа очков (он включает первый круг)
  return x.best != null ? x.best : null;
}
function median(a) {
  if (!a.length) return null;
  const s = [...a].sort((x, y) => x - y);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
function bindRowClicks() { /* ссылки на гонщика работают через href */ }

// ---------- страница гонщика ----------
function renderRider(key) {
  document.title = 'Гонщики';
  const { q } = parseHash();
  const initial = key ? '' : (q.get('q') || '');
  $app.innerHTML = `
    <h1>Гонщики</h1>
    <div class="toolbar"><input class="search" id="psearch" type="search" placeholder="Фамилия и/или имя" value="${esc(initial)}" autofocus></div>
    <div id="plist"></div>
    <div id="pcard"></div>`;
  const $s = document.getElementById('psearch');
  const $list = document.getElementById('plist');
  function drawList() {
    const words = nkey($s.value).split(' ').filter(Boolean);
    if (!words.length) { $list.innerHTML = key ? '' : '<div class="muted">Начните вводить фамилию — например, «Шамшин» или «Шамшин петр».</div>'; return; }
    const found = [...people.values()].filter(p => words.every(w => p.key.includes(w)))
      .sort((a, b) => b.entries.length - a.entries.length);
    if (found.length === 1 && !key) { location.hash = '#/rider/' + encodeURIComponent(found[0].key); return; }
    $list.innerHTML = found.length
      ? `<div class="people">${found.slice(0, 60).map(p => `<a class="chip ${p.key === key ? 'on' : ''}" href="#/rider/${encodeURIComponent(p.key)}">${esc(p.name)} <span class="muted">· ${p.entries.length}</span></a>`).join('')}</div>`
        + (found.length > 60 ? `<div class="muted">и ещё ${found.length - 60}…</div>` : '')
      : '<div class="muted">Никого не найдено</div>';
  }
  $s.oninput = () => { if (!key) setQuery({ q: $s.value || null }); drawList(); };
  $s.onkeydown = e => {
    if (e.key === 'Enter') {
      const a = $list.querySelector('a'); if (a) location.hash = a.getAttribute('href');
    }
  };
  drawList();
  if (key) drawPerson(key);
}

function drawPerson(key) {
  const p = people.get(key);
  const $c = document.getElementById('pcard');
  if (!p) { $c.innerHTML = '<div class="empty">Гонщик не найден</div>'; return; }
  document.title = p.name;
  const wins = p.entries.filter(e => mainRow(e) && mainRow(e).place === 1).length;
  const podiums = p.entries.filter(e => mainRow(e) && mainRow(e).place <= 3).length;
  const rating = getRating(defaultRatingOpts());
  const rr = rating.list.find(x => x.key === key);
  const clubMap = new Map();
  for (const e of p.entries) for (const x of Object.values(e.heats)) if (x.club && !clubMap.has(nkey(x.club))) clubMap.set(nkey(x.club), x.club);
  const clubs = [...clubMap.values()].slice(0, 4);
  const years = [...new Set(p.entries.flatMap(e => Object.values(e.heats).map(x => x.year)).filter(Boolean))];
  let html = `<h2 style="font-size:20px">${esc(p.name)}</h2>
    <div class="sub">${years.length ? 'г.р. ' + years.join('/') + ' · ' : ''}${esc(clubs.join(', '))}</div>
    <div class="stats">
      <div class="panel stat"><b>${p.entries.length}</b><span>стартов (класс/гонка)</span></div>
      <div class="panel stat"><b>${wins}</b><span>побед</span></div>
      <div class="panel stat"><b>${podiums}</b><span>подиумов</span></div>
      ${rr ? `<div class="panel stat"><b><a href="#/rating?f=${encodeURIComponent(p.name)}">#${rr.rank}</a></b><span>рейтинг XC ${defaultRatingOpts().years.slice().reverse().join('–')} из ${rating.list.length}</span></div>` : ''}
    </div>
    <div class="panel tbl-wrap"><table><thead><tr>
      <th>Дата</th><th>Дисц.</th><th>Гонка / класс</th><th class="c">Место</th><th class="num">№</th>
      <th class="num">Кр.</th><th class="num">Время</th><th class="num">Отст.</th><th class="num">Лучший</th><th class="num">Очки</th>
      <th>Заезды / абсолют</th><th></th>
    </tr></thead><tbody>`;
  p.entries.forEach((e, i) => {
    const m = mainRow(e);
    const lapRow = e.heats.main;
    const extra = [];
    if (e.heats['1']) extra.push(`1 заезд: ${placeTxt(e.heats['1'])}`);
    if (e.heats['2']) extra.push(`2 заезд: ${placeTxt(e.heats['2'])}`);
    if (e.abs) extra.push(`абсолют: <b>${e.abs.place ?? '—'}</b> из ${absCount(e.race)}`);
    const clsRows = e.race.classes.find(c => c.name === e.cls);
    const total = clsRows ? clsRows.count : '';
    const hasLaps = Object.values(e.heats).some(x => x.lapTimes && x.lapTimes.length);
    html += `<tr>
      <td>${fmtDateShort(e.race.date)}</td>
      <td><span class="badge ${e.race.disc}">${e.race.disc}</span></td>
      <td class="wrap"><a href="#/race/${e.race.id}?cls=${encodeURIComponent(e.cls)}&q=${encodeURIComponent(p.name)}">${esc(shortCls(e.cls))}</a>
        <div class="muted" style="font-size:12px">${esc(shortTitle(e.race.title))}</div></td>
      <td class="c">${placeHtml(m.place, m.status)} <span class="muted">/ ${total}</span></td>
      <td class="num">${esc(m.bib ?? '')}</td>
      <td class="num">${lapRow ? esc(lapRow.laps ?? '') : ''}</td>
      <td class="num">${lapRow ? fmtTime(lapRow.time) : ''}</td>
      <td class="num">${lapRow && lapRow.gap !== '-' ? esc(lapRow.gap || '') : ''}</td>
      <td class="num">${fmtTime(bestOfEntry(e))}</td>
      <td class="num"><b>${esc(m.sum ?? m.points ?? '')}</b></td>
      <td class="wrap">${extra.join(' · ')}</td>
      <td>${hasLaps ? `<button class="link" data-exp="${i}" title="Круги">круги ▾</button>` : ''}</td>
    </tr><tr class="expand" id="exp${i}" hidden><td colspan="12">${lapsInline(e)}</td></tr>`;
  });
  html += '</tbody></table></div>';
  $c.innerHTML = html;
  $c.querySelectorAll('[data-exp]').forEach(b => b.onclick = () => {
    const tr = document.getElementById('exp' + b.dataset.exp);
    tr.hidden = !tr.hidden;
  });
}
function bestOfEntry(e) {
  const v = ['main', '1', '2'].map(h => e.heats[h] && bestLap(e.heats[h])).filter(x => x != null);
  return v.length ? Math.min(...v) : null;
}
function shortTitle(t) {
  return String(t).replace(/^Соревнования по \S+( и \S+)?[,\s]*(на\s+)?/i, '') || t;
}
function mainRow(e) { return e.heats.sum || e.heats.main || e.heats['1'] || e.heats['2']; }
function placeTxt(x) { return `<b>${x.place ?? '—'}</b>${x.time ? ' (' + fmtTime(x.time) + ')' : ''}`; }
function absCount(r) { const c = r.classes.find(c => c.heats.abs); return c ? c.heats.abs.rows.length : ''; }
function lapsInline(e) {
  let out = '';
  for (const h of ['main', '1', '2']) {
    const x = e.heats[h];
    if (!x || !x.lapTimes) continue;
    const bi = bestLapIdx(x);
    out += `<div style="margin:4px 0"><span class="muted">${HEAT_LABEL[h]}:</span> <span class="laps-inline">${x.lapTimes.map((v, i) =>
      `<span class="${i === bi ? 'best' : !countedLap(i, x.lapTimes.length) ? 'excluded' : ''}" title="Круг ${i + 1}">${i + 1}: ${fmtTime(v)}</span>`).join('')}</span></div>`;
  }
  return out;
}

// ---------- рейтинг XC ----------
// Модель: для каждого гонщика i в гонке r логарифм его темпа (сек/круг)
//   log(pace_ir) = mu_r - s_i + шум
// mu_r — «сложность» трассы/условий конкретной гонки, s_i — сила гонщика.
// Сравниваются только гонщики, ехавшие вместе (общий старт кантри-кросса),
// очки и количество посещённых этапов не влияют. s_i оценивается
// взвешенными наименьшими квадратами с робастными весами (Хьюбер)
// и слабым априорным «притяжением» к среднему для гонщиков с малым числом гонок.

function hasFullLaps(x) {
  const lt = x.lapTimes;
  return !!(lt && lt.length === x.laps && lt.length >= 3 && lt.every(v => v != null && v > 0));
}
function paceOf(x) {
  const lt = x.lapTimes;
  if (hasFullLaps(x)) {
    let rest = lt.slice(1); // первый круг искажён стартом
    if (rest.length >= 4) { // отбрасываем один худший круг (падение, поломка)
      const worst = Math.max(...rest);
      rest.splice(rest.indexOf(worst), 1);
    }
    return rest.reduce((a, b) => a + b, 0) / rest.length;
  }
  if (x.laps > 0 && x.time > 0) return x.time / x.laps;
  return null;
}

// годы, в которых есть гонки кантри-кросса (новые первыми) и число гонок в каждом
function xcYears() {
  const cnt = {};
  for (const r of RACES) if (r.disc === 'XC') cnt[r.date.slice(0, 4)] = (cnt[r.date.slice(0, 4)] || 0) + 1;
  return Object.keys(cnt).sort().reverse().map(y => ({ y, n: cnt[y] }));
}
// по умолчанию — текущий год; если в нём меньше двух гонок — текущий и прошлый
function defaultYears() {
  const cur = new Date().getFullYear();
  const n = (xcYears().find(x => x.y === String(cur)) || { n: 0 }).n;
  return n >= 2 ? [String(cur)] : [String(cur), String(cur - 1)];
}
// выбранные годы из адреса (?y=2026,2025) или по умолчанию; только те, где есть гонки
function selectedYears() {
  const have = new Set(xcYears().map(x => x.y));
  const fromUrl = (parseHash().q.get('y') || '').split(',').filter(y => have.has(y));
  return fromUrl.length ? fromUrl.sort().reverse() : selectedYearsDefault();
}
function selectedYearsDefault() {
  const have = new Set(xcYears().map(x => x.y));
  const ys = defaultYears().filter(y => have.has(y));
  return (ys.length ? ys : have.size ? [xcYears()[0].y] : []).sort().reverse();
}
function defaultRatingOpts() {
  return { years: selectedYearsDefault(), halfLife: lsGet('rHalf2', 0), minRaces: lsGet('rMin', 1) };
}

const ratingCache = new Map();
function getRating(opts) {
  const ck = JSON.stringify(opts);
  if (ratingCache.has(ck)) return ratingCache.get(ck);
  // opts.years — выбранные годы (нет — все); opts.before — для проверки прогноза на прошлых данных
  const xcRaces = RACES.filter(r => r.disc === 'XC' && (!opts.before || r.date < opts.before)
    && (!opts.years || opts.years.includes(r.date.slice(0, 4)))
    && (!opts.venue || r.venue === opts.venue));
  const lastDate = xcRaces.length ? xcRaces[0].date : '2000-01-01';
  const t0 = new Date(lastDate + 'T12:00:00').getTime();

  const obs = []; // {r, i, y, w}
  const riders = new Map(); // key -> info
  const races = [];
  for (const r of xcRaces) {
    const ageDays = (t0 - new Date(r.date + 'T12:00:00').getTime()) / 864e5;
    const wTime = opts.halfLife ? Math.pow(0.5, ageDays / opts.halfLife) : 1;
    const rows = [];
    // только протокол абсолюта: все классы ехали одним заездом
    const absCls = r.classes.find(c => c.heats.abs);
    if (!absCls) continue;
    // если у гонщика в PDF видны не все круги, темп = время/круги, приведённое к той же шкале
    // через медианное отношение «темп по кругам / (время/круги)» у остальных в этой гонке
    const ratios = absCls.heats.abs.rows.filter(x => hasFullLaps(x) && x.time > 0).map(x => paceOf(x) / (x.time / x.laps));
    const k = ratios.length >= 5 ? median(ratios) : 1;
    for (const x of absCls.heats.abs.rows) {
      if (!x.key || x.status) continue;
      let pace = paceOf(x);
      if (!pace) continue;
      if (!hasFullLaps(x)) pace *= k;
      rows.push({ x, cls: r.clsOf.get(x.key) || '', pace });
    }
    if (rows.length < 3) continue;
    const maxLaps = Math.max(...rows.map(o => o.x.laps || 0));
    const ri = races.length;
    races.push({ race: r, n: rows.length });
    const seen = new Set();
    for (const o of rows) {
      if (seen.has(o.x.key)) continue; // один гонщик в двух классах — берём первый
      seen.add(o.x.key);
      if (!riders.has(o.x.key)) riders.set(o.x.key, { key: o.x.key, name: o.x.name, races: [], idx: riders.size });
      const rd = riders.get(o.x.key);
      rd.races.push({ race: r, cls: o.cls, row: o.x, pace: o.pace });
      const wLaps = Math.min(1, (o.x.laps || 0) / (0.5 * maxLaps));
      obs.push({ r: ri, i: rd.idx, y: Math.log(o.pace), w: wTime * wLaps, wTime });
    }
  }
  const R = races.length, N = riders.size;
  const s = new Float64Array(N), mu = new Float64Array(R);
  const lambda = opts.lambda != null ? opts.lambda : 0.2; // сила априорного притяжения к среднему (в «гонках»)
  let robust = obs.map(() => 1);
  let sigma = 0.05;
  for (let iter = 0; iter < 60; iter++) {
    // mu_r
    const num = new Float64Array(R), den = new Float64Array(R);
    obs.forEach((o, k) => { const w = o.w * robust[k]; num[o.r] += w * (o.y + s[o.i]); den[o.r] += w; });
    for (let r = 0; r < R; r++) mu[r] = den[r] ? num[r] / den[r] : 0;
    // s_i
    const sn = new Float64Array(N), sd = new Float64Array(N);
    obs.forEach((o, k) => { const w = o.w * robust[k]; sn[o.i] += w * (mu[o.r] - o.y); sd[o.i] += w; });
    for (let i = 0; i < N; i++) s[i] = sn[i] / (sd[i] + lambda);
    // робастные веса
    if (iter % 5 === 4) {
      const res = obs.map(o => o.y - (mu[o.r] - s[o.i]));
      sigma = 1.4826 * median(res.map(Math.abs)) || sigma;
      const c = 1.5 * sigma;
      robust = res.map(e => Math.abs(e) <= c ? 1 : c / Math.abs(e));
    }
  }
  // неопределённость
  const sd = new Float64Array(N);
  obs.forEach((o, k) => { sd[o.i] += o.w * robust[k]; });
  const list = [...riders.values()].map(rd => ({
    key: rd.key, name: people.get(rd.key) ? people.get(rd.key).name : rd.name,
    s: s[rd.idx], se: sigma / Math.sqrt(sd[rd.idx] + lambda),
    n: rd.races.length, races: rd.races.sort((a, b) => b.race.date.localeCompare(a.race.date)),
  })).filter(x => x.n >= opts.minRaces).sort((a, b) => b.s - a.s);
  list.forEach((x, i) => { x.rank = i + 1; });
  const top = list.length ? list[0].s : 0;
  list.forEach(x => { x.gapPct = (Math.exp(top - x.s) - 1) * 100; });
  const out = { list, races, sigma };
  ratingCache.set(ck, out);
  return out;
}

function renderRating() {
  document.title = 'Рейтинг кантри-кросс';
  const { q } = parseHash();
  const opts = defaultRatingOpts();
  const years = xcYears();
  let selYears = selectedYears();
  // места проведения кантри-кросса (Дракино, Васильевское…); '' — все
  const venues = [...new Set(RACES.filter(r => r.disc === 'XC' && r.venue).map(r => r.venue))].sort();
  let selVenue = venues.includes(parseHash().q.get('v')) ? parseHash().q.get('v') : '';
  const filterText = q.get('f') != null ? q.get('f') : lsGet('rFilter', '');
  $app.innerHTML = `
    <h1>Рейтинг кантри-кросс</h1>
    <div class="sub">Прогноз финиша абсолюта, если бы все ехали в одном заезде. Строится только по протоколам абсолюта кантри-кросса: классы не учитываются, все участники заезда сравниваются между собой.</div>
    <div class="rating-layout">
      <div class="panel rating-side">
        <label for="rf">Фильтр — каждая строка работает как «ИЛИ»</label>
        <textarea id="rf" placeholder="Перевалов&#10;Петров&#10;Сидоров иван">${esc(filterText)}</textarea>
        <label>Годы <span class="muted">(можно несколько)</span></label>
        <div class="filters years" id="ry">${years.map(x => `<button class="chip" data-year="${x.y}" title="${x.n} гонок кантри-кросса">${x.y} <span class="n">${x.n}</span></button>`).join('')}</div>
        <label>Место</label>
        <div class="filters years" id="rv">${['', ...venues].map(v => `<button class="chip" data-venue="${esc(v)}">${v ? esc(v) : 'Все места'} <span class="n"></span></button>`).join('')}</div>
        <label for="rh">Вес старых гонок</label>
        <select id="rh">
          <option value="0">Все гонки равноценны</option>
          <option value="365">Вдвое меньше за каждый год</option>
          <option value="180">Вдвое меньше за каждые полгода</option>
        </select>
        <label for="rm">Минимум гонок</label>
        <select id="rm"><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="5">5</option></select>
        <details class="method"><summary>Как считается</summary>
          <p>Источник — только протоколы абсолюта. Для каждого гонщика в каждой гонке берётся темп — среднее время круга (без стартового круга и одного худшего круга, чтобы падение не ломало оценку).</p>
          <p>Модель: темп = «сложность конкретной гонки» ÷ «сила гонщика». Сложность гонки (трасса, погода, длина круга) оценивается по всем, кто в ней ехал, поэтому гонщики сравниваются только с теми, с кем стартовали вместе. Через общих соперников сравнение переносится на тех, кто никогда не встречался.</p>
          <p>Количество посещённых этапов и очки не дают преимущества: одна быстрая гонка значит столько же, сколько десять — лишь с большей неопределённостью. Гонщики с одной гонкой слегка «притянуты» к среднему. Незавершённые гонки (сход) учитываются с меньшим весом.</p>
          <p><b>Проверка:</b> если строить рейтинг только по прошлым гонкам, он верно предсказывает, кто из двух гонщиков финиширует выше в следующей гонке, примерно в 83–84% пар.</p>
          <p><b>Место:</b> можно оставить только гонки в Дракино или только в Васильевском — тогда рейтинг показывает, кто быстрее на конкретной трассе. «о.Русский» в протоколах — это Дракино.</p>
          <p><b>Годы:</b> по умолчанию рейтинг строится по гонкам текущего года; если в нём меньше двух гонок — по текущему и прошлому. Можно выбрать любые годы.</p>
          <p><b>Отставание</b> — насколько медленнее лидера рейтинга в среднем темпе; «на 1 ч» — сколько это времени за час гонки.</p>
        </details>
      </div>
      <div>
        <div id="rinfo" class="toolbar muted"></div>
        <div class="panel tbl-wrap" id="rtable"></div>
        <div id="h2h"></div>
      </div>
    </div>`;
  const $f = document.getElementById('rf'), $h = document.getElementById('rh'), $m = document.getElementById('rm');
  $h.value = String(opts.halfLife); $m.value = String(opts.minRaces);
  const $years = document.getElementById('ry');
  const drawYears = () => $years.querySelectorAll('[data-year]').forEach(b => b.classList.toggle('on', selYears.includes(b.dataset.year)));
  $years.querySelectorAll('[data-year]').forEach(b => b.onclick = () => {
    const y = b.dataset.year;
    if (selYears.includes(y)) {
      if (selYears.length === 1) return; // хотя бы один год должен быть выбран
      selYears = selYears.filter(x => x !== y);
    } else {
      selYears = [...selYears, y].sort().reverse();
    }
    // год по умолчанию в адрес не пишем — ссылка остаётся «текущий год»
    const isDefault = selYears.join() === selectedYearsDefault().join();
    setQuery({ y: isDefault ? null : selYears.join(',') });
    drawYears(); drawVenues(); drawRating();
  });
  const $venues = document.getElementById('rv');
  // на кнопках мест — число гонок с учётом выбранных лет
  const drawVenues = () => $venues.querySelectorAll('[data-venue]').forEach(b => {
    b.classList.toggle('on', b.dataset.venue === selVenue);
    b.querySelector('.n').textContent = RACES.filter(r => r.disc === 'XC' && selYears.includes(r.date.slice(0, 4))
      && (!b.dataset.venue || r.venue === b.dataset.venue)).length;
  });
  $venues.querySelectorAll('[data-venue]').forEach(b => b.onclick = () => {
    selVenue = b.dataset.venue;
    setQuery({ v: selVenue || null });
    drawVenues(); drawRating();
  });
  drawYears(); drawVenues();
  const update = () => {
    lsSet('rFilter', $f.value); lsSet('rHalf2', Number($h.value)); lsSet('rMin', Number($m.value));
    setQuery({ f: null });
    drawRating();
  };
  $f.oninput = update; $h.onchange = update; $m.onchange = update;
  drawRating();

  function drawRating() {
    const o = { years: selYears, venue: selVenue, halfLife: Number($h.value), minRaces: Number($m.value) };
    const rating = getRating(o);
    const lines = $f.value.split('\n').map(l => nkey(l).split(' ').filter(Boolean)).filter(w => w.length);
    const sel = lines.length ? rating.list.filter(x => lines.some(ws => ws.every(w => x.key.includes(w)))) : rating.list;
    document.getElementById('rinfo').innerHTML =
      `${selYears.length > 1 ? selYears.slice().reverse().join(', ') + ' гг.' : selYears[0] + ' г.'}${selVenue ? ', ' + esc(selVenue) : ''}: ${rating.races.length} гонок, ${rating.list.length} гонщиков${lines.length ? ` · выбрано ${sel.length}` : ''}`;
    const maxGap = Math.max(1, ...rating.list.slice(0, Math.max(10, Math.floor(rating.list.length * 0.9))).map(x => x.gapPct));
    const first = sel.length ? sel[0] : null;
    let html = `<table><thead><tr><th class="num">#</th>${lines.length ? '<th class="num">Среди выбр.</th>' : ''}<th>Гонщик</th>
      <th class="num">Отставание</th><th class="num">на 1 ч</th>${lines.length ? '<th class="num">от 1-го выбр.</th>' : ''}<th></th>
      <th class="num">Гонок</th><th>Последняя</th><th>Класс (последний)</th></tr></thead><tbody>`;
    sel.forEach((x, i) => {
      const last = x.races[0];
      const w = Math.max(2, 100 - Math.min(100, x.gapPct / maxGap * 100));
      const relGap = first ? (Math.exp(first.s - x.s) - 1) * 100 : 0;
      html += `<tr>
        <td class="num"><b>${x.rank}</b></td>${lines.length ? `<td class="num">${i + 1}</td>` : ''}
        <td class="name">${riderLink(x.name)}</td>
        <td class="num" title="± ${(x.se * 100).toFixed(1)}%">${x.rank === 1 ? '—' : '+' + x.gapPct.toFixed(1) + '%'}</td>
        <td class="num">${x.rank === 1 ? '' : '+' + fmtTime(x.gapPct / 100 * 3600).replace(/\.\d$/, '')}</td>
        ${lines.length ? `<td class="num">${i === 0 ? '—' : '+' + relGap.toFixed(1) + '%'}</td>` : ''}
        <td><div class="bar"><i style="width:${w}%"></i></div></td>
        <td class="num">${x.n}</td>
        <td><a href="#/race/${last.race.id}?cls=${encodeURIComponent(last.cls)}&q=${encodeURIComponent(x.name)}">${fmtDateShort(last.race.date)}</a> <span class="muted">${placeTxtShort(last.row)}</span></td>
        <td>${esc(shortCls(last.cls))}</td>
      </tr>`;
    });
    html += '</tbody></table>';
    if (!sel.length) html = '<div class="empty">Никого не найдено</div>';
    document.getElementById('rtable').innerHTML = html;
    drawH2H(lines.length && sel.length >= 2 && sel.length <= 25 ? sel : null, o);
  }
}
function placeTxtShort(row) { return row.place ? `${row.place} в абс.` : ''; }

// личные встречи выбранных гонщиков в общих заездах кантри-кросса
function drawH2H(sel, o) {
  const $el = document.getElementById('h2h');
  if (!sel) { $el.innerHTML = ''; return; }
  const idx = new Map(sel.map((x, i) => [x.key, i]));
  const n = sel.length;
  const M = Array.from({ length: n }, () => Array.from({ length: n }, () => [0, 0]));
  const byRace = new Map();
  for (const x of sel) for (const rr of x.races) {
    if (!byRace.has(rr.race.id)) byRace.set(rr.race.id, []);
    byRace.get(rr.race.id).push({ i: idx.get(x.key), row: rr.row });
  }
  const ahead = (a, b) => (a.laps || 0) !== (b.laps || 0) ? (a.laps || 0) > (b.laps || 0) : a.time < b.time;
  for (const list of byRace.values()) for (const a of list) for (const b of list) {
    if (a.i === b.i) continue;
    if (ahead(a.row, b.row)) M[a.i][b.i][0]++; else M[a.i][b.i][1]++;
  }
  let html = `<h2>Личные встречи</h2><div class="sub">Кто финишировал выше в абсолюте (больше кругов / быстрее) в тех гонках, где оба ехали. Строка — против столбца.</div>
    <div class="panel tbl-wrap"><table class="h2h"><thead><tr><th></th>${sel.map(x => `<th class="rot">${esc(x.name)}</th>`).join('')}</tr></thead><tbody>`;
  sel.forEach((x, i) => {
    html += `<tr><td style="text-align:left" class="name">${riderLink(x.name)}</td>`;
    for (let j = 0; j < n; j++) {
      if (i === j) { html += '<td class="muted">·</td>'; continue; }
      const [w, l] = M[i][j];
      html += `<td class="${w + l ? (w > l ? 'win' : w < l ? 'loss' : '') : 'muted'}">${w + l ? w + '–' + l : ''}</td>`;
    }
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  $el.innerHTML = html;
}

render();
