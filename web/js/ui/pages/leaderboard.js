// Global leaderboards.

import { h, clear, commas, duration } from '../dom.js';
import { Users } from '../api.js';
import { panel, spinnerBlock, emptyState } from '../components.js';

const METRICS = [
  ['kills', 'Eliminations'], ['wins', 'Round wins'],
  ['score', 'Overall score'], ['playtime', 'Time played'],
];

export async function render(root, params, query) {
  document.title = 'Leaderboard — RBLXX';
  let metric = query.get('metric') || 'kills';
  const page = h('div', { class: 'page' });
  const body = h('div');
  clear(root).appendChild(page);

  const tabsEl = h('div', { class: 'tabs' });
  page.append(
    h('div', { class: 'page-head' },
      h('h1', {}, 'Leaderboard'),
      h('span', { class: 'sub' }, 'Across every world on the platform')),
    h('div', { class: 'panel' },
      h('div', { class: 'cat-toolbar' }, tabsEl),
      body));

  async function load() {
    clear(tabsEl);
    for (const [id, label] of METRICS) {
      tabsEl.appendChild(h('div', {
        class: 'tab' + (id === metric ? ' active' : ''),
        onClick: () => { metric = id; history.replaceState(null, '',
          `#/leaderboard?metric=${id}`); load(); },
      }, label));
    }
    body.replaceChildren(spinnerBlock('Counting…'));
    const { rows } = await Users.leaderboard(metric);
    clear(body);
    if (!rows.length) {
      body.appendChild(emptyState('🏆', 'No records yet',
        'Play a round to get on the board.'));
      return;
    }
    body.appendChild(h('table', { class: 'tbl' },
      h('thead', {}, h('tr', {},
        h('th', { style: { width: '48px' } }, '#'),
        h('th', {}, 'Player'),
        h('th', { style: { textAlign: 'right' } }, 'Elims'),
        h('th', { style: { textAlign: 'right' } }, 'Deaths'),
        h('th', { style: { textAlign: 'right' } }, 'K/D'),
        h('th', { style: { textAlign: 'right' } }, 'Wins'),
        h('th', { style: { textAlign: 'right' } }, 'Streak'),
        h('th', { style: { textAlign: 'right' } }, 'Played'))),
      h('tbody', {}, rows.map((r, i) => h('tr', {},
        h('td', {}, h('b', { style: { color: i < 3 ? 'var(--gold)' : '' } },
          `#${i + 1}`)),
        h('td', {}, h('a', { href: `#/profile/${r.username}` }, r.username)),
        h('td', { class: 'num' }, commas(r.kills)),
        h('td', { class: 'num' }, commas(r.deaths)),
        h('td', { class: 'num' },
          (r.kills / Math.max(1, r.deaths)).toFixed(2)),
        h('td', { class: 'num' }, commas(r.wins)),
        h('td', { class: 'num' }, r.best_streak),
        h('td', { class: 'num' }, duration(r.playtime)))))));
  }

  await load();
  return () => {};
}
