import { projectedWins, margin, outcome, summary, agreement, clinched, EPSILON } from './model.mjs';

const $ = selector => document.querySelector(selector);
const COLORS = { Met: '#276c94', Sasso: '#ae7436', Zach: '#7d6a99', Bill: '#4e7f6a', House: '#af6260' };
const DASHES = ['', '7 3', '2 4', '9 3 2 3', '4 3'];
const number = new Intl.NumberFormat('it-IT', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat('it-IT');
const escape = text => String(text).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const signed = value => value === null ? '—' : Math.abs(value) < EPSILON ? '0,0' : `${value > 0 ? '+' : '−'}${Math.abs(value) < .05 ? '<0,1' : number.format(Math.abs(value))}`;
const percent = value => value === null ? '—' : `${number.format(value)}%`;
const state = { conference: 'all', search: '', locks: false, sort: 'line', direction: -1, history: 'all', visiblePeople: new Set() };
let config, current, history;

function heat(value) {
  if (value === null) return { bg: '#f0f1eb', fg: '#69777a', border: '#bfc7bd' };
  const weight = Math.min(Math.abs(value) / 20, 1);
  const target = value >= 0 ? [40, 107, 153] : [183, 79, 80];
  const base = [248, 247, 241];
  const rgb = factor => base.map((v, i) => Math.round(v + (target[i] - v) * factor));
  const mix = factor => `rgb(${rgb(factor).join(',')})`;
  const luminance = rgb(weight * .88).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
    .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
  // Choose text by contrast, including the middle of the diverging scale.
  const whiteContrast = 1.039 / (luminance + .05);
  return { bg: mix(weight * .88), fg: whiteContrast >= 4.5 ? '#fffefa' : '#000000', border: mix(.35 + weight * .65) };
}

function renderStatus() {
  const played = Object.values(current.records).reduce((sum, r) => sum + r.wins, 0);
  const total = config.teams.length * config.games / 2;
  $('#games-played').textContent = integer.format(played);
  $('.games-counter>span').textContent = `/ ${integer.format(total)} partite`;
  $('#season-progress').setAttribute('aria-valuemax', total);
  $('#season-progress').setAttribute('aria-valuenow', played);
  $('#season-progress>span').style.width = `${100 * played / total}%`;
  const date = new Date(current.updatedAt);
  const formatted = new Intl.DateTimeFormat('it-IT', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: config.timezone }).format(date);
  const stale = Date.now() - date.getTime() > 36 * 3600 * 1000;
  $('#update-status').textContent = `Dati prelevati il ${formatted}`;
  $('#update-status').classList.toggle('stale', stale);
  if (stale) {
    $('#notice').hidden = false;
    $('#notice').textContent = `L’ultimo prelievo risale a oltre 36 ore fa (${formatted}). Mostriamo gli ultimi record validi. L’aggiornamento potrebbe non essere attivo o essere fallito.`;
  }
  $('#season').textContent = config.season.replace('-', '–');
  $('#footer-season').textContent = config.season.replace('-', '–');
  $('#lines-note').textContent = config.linesNote;
  $('#source-link').href = current.source.url;
  document.title = `O/U Club — NBA ${config.season.replace('-', '–')}`;
}

function renderLeaderboard() {
  const summaries = config.players.map(player => ({ ...summary(config, current.records, player), locks: summary(config, current.records, player, true) }));
  summaries.sort((a, b) => (b.percentage ?? -1) - (a.percentage ?? -1) || (b.averageMargin ?? -100) - (a.averageMargin ?? -100));
  $('#leaderboard').innerHTML = summaries.map(s => {
    const rank = 1 + summaries.filter(other => (other.percentage ?? -1) > (s.percentage ?? -1) + EPSILON).length;
    const extra = s.push || s.pending ? ` · ${s.push} pari · ${s.pending} N.D.` : '';
    return `<article class="person-card" style="--person-color:${COLORS[s.player]}" aria-label="${s.player}: ${s.correct} giusti, ${s.wrong} sbagliati${extra}">
      <div class="card-top"><span class="person-label"><i class="person-dot" aria-hidden="true"></i>${s.player}</span><span class="card-position">#${rank}</span></div>
      <p class="card-score" title="${s.correct} giusti, ${s.wrong} sbagliati${extra}">${s.correct}–${s.wrong}<span>${percent(s.percentage)}</span></p>
      <div class="card-bottom"><span>◆ Locks <b>${s.locks.correct}–${s.locks.wrong}</b></span><span title="Margine medio di tutti i pronostici">Media <b>${signed(s.averageMargin)}</b></span></div>
    </article>`;
  }).join('');
}

function renderTableHead() {
  const columns = [['team', 'Squadra'], ['record', 'V–S'], ['projection', 'Proiez. V'], ['line', 'Linea O/U'], ...config.players.map(p => [p, p])];
  $('#table-head').innerHTML = `<tr>${columns.map(([key, name]) => `<th scope="col"${key === state.sort ? ` aria-sort="${state.direction === 1 ? 'ascending' : 'descending'}"` : ''}>
    <button type="button" data-sort="${key}" aria-label="Ordina per ${name}" class="${config.players.includes(key) ? 'player-header' : ''}">${COLORS[key] ? `<i class="person-dot" aria-hidden="true" style="--person-color:${COLORS[key]}"></i>` : ''}${name}<span class="sort-mark" aria-hidden="true">${key === state.sort ? state.direction === 1 ? '↑' : '↓' : '↕'}</span></button>
  </th>`).join('')}</tr>`;
}

function sortValue(team) {
  if (state.sort === 'team') return team.name;
  if (state.sort === 'line') return team.line;
  if (state.sort === 'record') return projectedWins(current.records[team.id], config.games);
  if (state.sort === 'projection') return projectedWins(current.records[team.id], config.games);
  return margin(team, state.sort, current.records[team.id], config.games);
}

function renderTable() {
  const query = state.search.toLocaleLowerCase('it-IT').trim();
  const teams = config.teams.filter(team => (state.conference === 'all' || team.conference === state.conference)
    && (!query || `${team.name} ${team.id}`.toLocaleLowerCase('it-IT').includes(query))
    && (!state.locks || config.players.some(p => team.picks[p].lock)));
  teams.sort((a, b) => {
    const av = sortValue(a), bv = sortValue(b);
    if (av === null || bv === null) return av === bv ? a.name.localeCompare(b.name) : av === null ? 1 : -1;
    return (typeof av === 'string' ? av.localeCompare(bv) : av - bv) * state.direction || a.name.localeCompare(b.name);
  });
  $('#table-body').innerHTML = teams.map(team => {
    const record = current.records[team.id];
    const projection = projectedWins(record, config.games);
    const recordText = record ? `${record.wins}–${record.losses}` : '—';
    return `<tr><th scope="row"><div class="team"><span class="team-code">${team.id}</span><span><span class="team-name">${escape(team.name)}</span><span class="team-conference">${team.conference.toUpperCase()}</span></span></div></th>
      <td class="record">${recordText}</td><td class="projection" title="${projection === null ? 'Nessuna partita giocata' : `${number.format(projection)} vittorie, ${number.format(config.games - projection)} sconfitte proiettate`}">${projection === null ? '—' : number.format(projection)}</td><td class="line">${number.format(team.line)}</td>
      ${config.players.map(player => {
        const pick = team.picks[player], value = margin(team, player, record, config.games), color = heat(value);
        const certain = clinched(team, player, record, config.games);
        const status = { correct: 'attualmente giusto', wrong: 'attualmente sbagliato', push: 'pari sulla linea', pending: 'nessuna proiezione disponibile' }[outcome(value)];
        const title = `${player}: ${pick.side === 'O' ? 'Over' : 'Under'} ${number.format(team.line)}${pick.lock ? ', lock' : ''}; ${status}; margine ${signed(value)}${certain ? `; esito matematicamente ${certain === 'correct' ? 'giusto' : 'sbagliato'}` : ''}`;
        return `<td class="pick-col"><div class="pick-cell${pick.lock ? ' is-lock' : state.locks ? ' not-lock' : ''}" style="--cell-bg:${color.bg};--cell-fg:${color.fg};--cell-border:${color.border}" title="${escape(title)}" aria-label="${escape(title)}"><span class="pick-side">${pick.side}${pick.lock ? '<span class="lock-symbol" aria-hidden="true">◆</span>' : ''}${certain ? '<span class="clinched" aria-hidden="true">✓</span>' : ''}</span><span class="pick-value">${signed(value)}</span></div></td>`;
      }).join('')}</tr>`;
  }).join('');
  $('#no-results').hidden = teams.length !== 0;
  $('#team-count').textContent = `${teams.length} / 30 squadre${state.locks ? ' con almeno un lock' : ' · 150 pronostici totali'}`;
  $('#reset-filters').hidden = state.conference === 'all' && !state.search && !state.locks;
}

function renderBars(target, locksOnly) {
  $(target).innerHTML = config.players.map(player => {
    const s = summary(config, current.records, player, locksOnly);
    const tooltip = `${player}: ${s.correct} giusti, ${s.wrong} sbagliati, ${s.push} pari, ${s.pending} N.D., su ${s.total}`;
    return `<div class="bar-row"><span class="bar-name">${player}</span><div class="bar-track" role="img" aria-label="${tooltip}" title="${tooltip}">
      <span class="bar-segment bar-positive" style="width:${100 * s.correct / s.total}%"></span><span class="bar-segment bar-negative" style="width:${100 * s.wrong / s.total}%"></span><span class="bar-segment bar-neutral" style="width:${100 * (s.push + s.pending) / s.total}%"></span></div>
      <div class="bar-stats"><strong>${s.correct}–${s.wrong}</strong><span>${percent(s.percentage)}${locksOnly ? ` · ${s.total} locks` : ''}</span></div></div>`;
  }).join('');
}

function renderAgreement() {
  $('#agreement-chart').innerHTML = `<table class="agreement-table"><caption class="sr-only">Numero di scelte concordi su 30, per ogni coppia di partecipanti</caption><thead><tr><th scope="col"><span class="sr-only">Partecipante</span></th>${config.players.map(p => `<th scope="col">${p}</th>`).join('')}</tr></thead><tbody>${config.players.map(a => `<tr><th scope="row">${a}</th>${config.players.map(b => {
    if (a === b) return '<td><span class="diagonal" aria-label="Stesso partecipante">—</span></td>';
    const same = agreement(config, a, b).same;
    return `<td><span style="background:rgba(54,100,111,${.06 + .6 * same / 30});color:${same > 24 ? '#fffefa' : '#233b43'}" title="${a} e ${b}: ${same} scelte uguali su 30" aria-label="${a} e ${b}: ${same} su 30">${same}</span></td>`;
  }).join('')}</tr>`).join('')}</tbody></table>`;
}

function renderContrarians() {
  const singles = config.teams.flatMap(team => {
    const overs = config.players.filter(p => team.picks[p].side === 'O');
    if (overs.length !== 1 && overs.length !== 4) return [];
    const player = overs.length === 1 ? overs[0] : config.players.find(p => team.picks[p].side === 'U');
    return [{ team, player, value: margin(team, player, current.records[team.id], config.games) }];
  }).sort((a, b) => Math.abs(b.value ?? 0) - Math.abs(a.value ?? 0));
  $('#contrarian-chart').innerHTML = singles.slice(0, 5).map(({ team, player, value }) => `<div class="contrarian-row"><div><div class="contrarian-team">${escape(team.name)}</div><div class="contrarian-detail"><strong>${player}</strong> ${team.picks[player].side === 'O' ? 'Over' : 'Under'} ${number.format(team.line)}${team.picks[player].lock ? ' ◆' : ''} · gli altri quattro all’opposto</div></div><span class="contrarian-margin ${outcome(value) === 'correct' ? 'positive-text' : outcome(value) === 'wrong' ? 'negative-text' : ''}">${signed(value)}</span></div>`).join('') || '<p class="empty-state">Nessuna scelta solitaria.</p>';
  $('#contrarian-chart').nextElementSibling.textContent = `I ${Math.min(5, singles.length)} margini assoluti più grandi su ${singles.length} scelte solitarie. Positivo = per ora ha ragione chi è solo.`;
}

function historyTooltip(index, points) {
  const point = points[index];
  const date = new Intl.DateTimeFormat('it-IT', { day: 'numeric', month: 'short', timeZone: config.timezone }).format(new Date(point.updatedAt));
  $('#history-values').innerHTML = `<strong>${date}</strong>${config.players.filter(p => state.visiblePeople.has(p)).map(p => `<span><i class="person-dot" style="--person-color:${COLORS[p]}"></i> ${p} <strong>${percent(point.values[p])}</strong></span>`).join('')}`;
}

function renderHistory() {
  const locks = state.history === 'locks';
  const points = history.snapshots.map(s => ({ ...s, values: Object.fromEntries(config.players.map(p => [p, summary(config, s.records, p, locks).percentage])) }));
  if (!points.length) return;
  const width = 1120, height = 260, pad = { top: 17, right: 24, bottom: 38, left: 44 };
  const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
  const times = points.map(p => new Date(p.updatedAt).getTime());
  const min = times[0], max = times.at(-1);
  const x = index => min === max ? pad.left + plotW / 2 : pad.left + plotW * (times[index] - min) / (max - min);
  const y = value => pad.top + plotH * (1 - value / 100);
  const axes = [0, 25, 50, 75, 100].map(v => `<line x1="${pad.left}" y1="${y(v)}" x2="${width - pad.right}" y2="${y(v)}" stroke="${v === 50 ? '#bdc7bd' : '#e9ece5'}"${v === 50 ? ' stroke-dasharray="3 5"' : ''}/><text class="chart-svg-label" x="${pad.left - 12}" y="${y(v) + 3}" text-anchor="end">${v}%</text>`).join('');
  const labelIndices = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])];
  const labels = labelIndices.map(index => `<text class="chart-svg-label" x="${x(index)}" y="${height - 12}" text-anchor="middle">${new Intl.DateTimeFormat('it-IT', { day: '2-digit', month: 'short', timeZone: config.timezone }).format(new Date(points[index].updatedAt))}</text>`).join('');
  const people = config.players.filter(p => state.visiblePeople.has(p));
  const lines = people.map(person => {
    const segments = [];
    let segment = [];
    points.forEach((point, index) => {
      if (point.values[person] === null) { if (segment.length) segments.push(segment); segment = []; }
      else segment.push([x(index), y(point.values[person])]);
    });
    if (segment.length) segments.push(segment);
    const dash = DASHES[config.players.indexOf(person)];
    return segments.map(s => `<polyline class="chart-line" points="${s.map(pair => pair.join(',')).join(' ')}" stroke="${COLORS[person]}" stroke-dasharray="${dash}"/>`).join('')
      + points.map((point, index) => point.values[person] === null ? '' : `<circle cx="${x(index)}" cy="${y(point.values[person])}" r="${points.length === 1 ? 5 : 3}" fill="${COLORS[person]}"><title>${person}, ${point.date}: ${percent(point.values[person])}</title></circle>`).join('');
  }).join('');
  const message = !people.length ? '<text x="560" y="115" text-anchor="middle" class="chart-svg-label">Seleziona almeno un partecipante nella legenda.</text>' : '';
  $('#history-chart').innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Storico percentuale dei pronostici corretti: ${points.length} snapshot giornalieri, ${locks ? 'solo locks' : 'tutti i pronostici'}"><desc>Scala da zero a cento per cento. Legenda cliccabile per mostrare o nascondere ciascun partecipante. I valori dell’ultimo giorno sono riportati sotto il grafico.</desc>${axes}${labels}${lines}${message}<line id="history-cursor" x1="${x(points.length - 1)}" y1="${pad.top}" x2="${x(points.length - 1)}" y2="${height - pad.bottom}" stroke="#9ca9a0" stroke-dasharray="2 4"/><rect class="data-hit" x="${pad.left}" y="${pad.top}" width="${plotW}" height="${plotH}" fill="transparent"/></svg><div class="history-values" id="history-values" aria-live="polite"></div>`;
  historyTooltip(points.length - 1, points);
  const svg = $('#history-chart svg');
  svg.addEventListener('pointermove', event => {
    const screen = svg.getScreenCTM();
    if (!screen) return;
    const coordinate = new DOMPoint(event.clientX, event.clientY).matrixTransform(screen.inverse());
    const index = points.reduce((best, _, i) => Math.abs(x(i) - coordinate.x) < Math.abs(x(best) - coordinate.x) ? i : best, 0);
    $('#history-cursor').setAttribute('x1', x(index));
    $('#history-cursor').setAttribute('x2', x(index));
    historyTooltip(index, points);
  });
  svg.addEventListener('pointerleave', () => {
    $('#history-cursor').setAttribute('x1', x(points.length - 1));
    $('#history-cursor').setAttribute('x2', x(points.length - 1));
    historyTooltip(points.length - 1, points);
  });
  $('#history-note').textContent = points.length === 1 ? `Primo snapshot: ${points[0].date.split('-').reverse().join('/')}. Dal prossimo aggiornamento il grafico inizierà a tracciare l’andamento. Nessun dato storico inventato.` : `${points.length} snapshot giornalieri dal ${points[0].date.split('-').reverse().join('/')}. Tocca o passa sul grafico per leggere i valori; clicca sui nomi per confrontarli.`;
}

function bindEvents() {
  $('[aria-label="Filtra per conference"]').addEventListener('click', event => {
    const button = event.target.closest('[data-conference]');
    if (!button) return;
    state.conference = button.dataset.conference;
    document.querySelectorAll('[data-conference]').forEach(b => { b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', b === button); });
    renderTable();
  });
  $('#search').addEventListener('input', event => { state.search = event.target.value; renderTable(); });
  $('#locks-only').addEventListener('change', event => { state.locks = event.target.checked; renderTable(); });
  $('#reset-filters').addEventListener('click', () => {
    state.search = ''; state.locks = false;
    $('#search').value = ''; $('#locks-only').checked = false;
    $('[data-conference="all"]').click();
  });
  $('#table-head').addEventListener('click', event => {
    const button = event.target.closest('[data-sort]');
    if (!button) return;
    const oldFocus = button.dataset.sort;
    state.direction = state.sort === oldFocus ? -state.direction : oldFocus === 'team' ? 1 : -1;
    state.sort = oldFocus;
    renderTableHead(); renderTable();
    $(`[data-sort="${oldFocus}"]`).focus({ preventScroll: true });
  });
  document.querySelectorAll('[data-history]').forEach(button => button.addEventListener('click', () => {
    state.history = button.dataset.history;
    document.querySelectorAll('[data-history]').forEach(b => { b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', b === button); });
    renderHistory();
  }));
  $('#history-legend').innerHTML = config.players.map(player => `<button type="button" class="person-toggle" data-person="${player}" aria-pressed="true" aria-label="Mostra o nascondi ${player}"><i class="person-dot" style="--person-color:${COLORS[player]}"></i>${player}</button>`).join('');
  $('#history-legend').addEventListener('click', event => {
    const button = event.target.closest('[data-person]');
    if (!button) return;
    const person = button.dataset.person;
    state.visiblePeople.has(person) ? state.visiblePeople.delete(person) : state.visiblePeople.add(person);
    button.setAttribute('aria-pressed', state.visiblePeople.has(person));
    renderHistory();
  });
}

async function loadJson(path) {
  const response = await fetch(new URL(path, document.baseURI), { cache: 'no-cache' });
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${path}`);
  return response.json();
}

try {
  [config, history] = await Promise.all([loadJson('./data/picks.json'), loadJson('./data/history.json')]);
  if (history.season !== config.season || !Array.isArray(history.snapshots) || !history.snapshots.length) throw new Error('Nessuno snapshot per questa stagione');
  current = history.snapshots.at(-1);
  if (!Number.isFinite(new Date(current.updatedAt).getTime()) || !current.source?.url?.startsWith('https://en.wikipedia.org/')) throw new Error('Metadati della fonte non validi');
  if (config.teams.length !== 30 || config.teams.some(t => !current.records[t.id])) throw new Error('Mancano i record di alcune squadre');
  state.visiblePeople = new Set(config.players);
  renderStatus(); renderLeaderboard(); renderTableHead(); renderTable();
  renderBars('#all-chart', false); renderBars('#locks-chart', true); renderAgreement(); renderContrarians();
  bindEvents(); renderHistory();
} catch (error) {
  console.error(error);
  $('#update-status').textContent = 'Dati non disponibili';
  $('#update-status').classList.add('stale');
  $('#error').hidden = false;
  $('#error').textContent = location.protocol === 'file:' ? 'Per visualizzare la pagina serve un server locale oppure GitHub Pages. Segui le istruzioni nel README.' : 'Non riesco a caricare i dati della stagione. Riprova tra poco o controlla l’ultimo aggiornamento su GitHub Actions.';
}
