// A single world: art, description, live roster, ratings and the Load button.

import { h, clear, fmt, commas, ago, date } from '../dom.js';
import { Worlds } from '../api.js';
import { getState } from '../store.js';
import { navigate } from '../router.js';
import { panel, toast, emptyState, spinnerBlock, statStrip } from '../components.js';
import { worldThumb } from '../thumbs.js';

export async function render(root, params) {
  const page = h('div', { class: 'page' });
  clear(root).appendChild(page);
  page.appendChild(spinnerBlock('Loading world…'));

  let data;
  try {
    data = (await Worlds.get(params.id)).world;
  } catch {
    clear(page).appendChild(emptyState('🚧', 'World not found',
      'That experience does not exist.',
      h('a', { class: 'btn', href: '#/games' }, 'Back to the browser')));
    return () => {};
  }
  document.title = `${data.name} — RBLXX`;
  const user = getState().user;
  clear(page);

  const canvas = h('canvas', { style: { width: '100%', display: 'block' } });
  requestAnimationFrame(() => worldThumb(canvas, data.id,
    { width: 760, height: 400 }));

  const voteInfo = h('div', { class: 'row small' });
  const likeBtn = h('button', { class: 'btn ghost sm' }, '👍 Like');
  const dislikeBtn = h('button', { class: 'btn ghost sm' }, '👎');
  const favBtn = h('button', { class: 'btn ghost sm' },
    data.favorited ? '★ Favourited' : '☆ Favourite');

  function paintVotes(v) {
    clear(voteInfo);
    const ratio = v.ratio;
    voteInfo.append(
      h('span', { class: 'ratio-bar', style: { width: '160px' } },
        h('i', { style: { width: (ratio == null ? 0 : ratio) + '%' } })),
      h('span', { class: 'bold' }, ratio == null ? 'Not rated' : `${ratio}%`),
      h('span', { class: 'muted' },
        `${commas(v.likes)} likes · ${commas(v.dislikes)} dislikes`));
    likeBtn.classList.toggle('green', v.myVote === 1);
    dislikeBtn.classList.toggle('red', v.myVote === -1);
  }
  paintVotes({ likes: data.likes, dislikes: data.dislikes, ratio: data.ratio,
               myVote: data.myVote || 0 });

  async function vote(value) {
    if (!user) return navigate('/login?next=' + encodeURIComponent(`/game/${data.id}`));
    paintVotes(await Worlds.vote(data.id, value));
  }
  likeBtn.onclick = () => vote(1);
  dislikeBtn.onclick = () => vote(-1);
  favBtn.onclick = async () => {
    if (!user) return navigate('/login');
    const res = await Worlds.favorite(data.id);
    favBtn.textContent = res.favorited ? '★ Favourited' : '☆ Favourite';
    toast(res.favorited ? 'Added to favourites' : 'Removed from favourites',
          data.name, res.favorited ? 'good' : '');
  };

  const playBtn = h('button', { class: 'btn play lg', onClick: () => {
    if (!user) return navigate('/login?next=' + encodeURIComponent(`/play/${data.id}`));
    if (!data.server.up) return toast('Server starting',
      'That world is still booting — try again in a second.', 'bad');
    location.href = `/play/${data.id}`;
  } }, 'Load');

  const left = h('div', { class: 'col' },
    h('div', { class: 'panel' },
      canvas,
      h('div', { class: 'panel-body' },
        h('div', { class: 'row', style: { alignItems: 'flex-start' } },
          h('div', { style: { flex: 1 } },
            h('h1', { style: { marginBottom: '2px' } }, data.name),
            h('div', { class: 'muted' }, `By ${data.creator} · ${data.genre}`),
            h('div', { class: 'row wrap', style: { marginTop: '8px' } },
              h('span', { class: 'chip blue' }, data.mode),
              h('span', { class: 'chip' }, data.difficulty),
              h('span', { class: 'chip' }, data.recommended),
              ...(data.tags || []).map((t) => h('span', { class: 'chip' }, t)))),
          h('div', { class: 'col', style: { alignItems: 'flex-end' } },
            playBtn,
            h('div', { class: 'row' }, likeBtn, dislikeBtn, favBtn)))),
      statStrip([
        ['Playing', commas(data.server.players)],
        ['Max players', data.max_players],
        ['Visits', fmt(data.visits)],
        ['Rating', data.ratio == null ? '—' : data.ratio + '%'],
        ['Parts', data.stats ? commas(data.stats.parts) : '—'],
      ]),
      h('div', { class: 'panel-body' }, voteInfo)),
    panel('About this experience',
      h('div', { style: { whiteSpace: 'pre-wrap', lineHeight: '1.75' } },
        data.description)));

  const roster = data.server.roster || [];
  const right = h('div', { class: 'col' },
    panel(`In this server (${roster.length})`,
      roster.length
        ? h('table', { class: 'tbl' },
            h('thead', {}, h('tr', {}, h('th', {}, 'Player'),
              h('th', {}, 'Team'), h('th', { style: { textAlign: 'right' } }, 'K/D'))),
            h('tbody', {}, roster.map((p) => h('tr', {},
              h('td', {}, h('a', { href: `#/profile/${p.userId}` }, p.name)),
              h('td', {}, h('span', { class: 'chip' }, p.team)),
              h('td', { class: 'num' }, `${p.kills}/${p.deaths}`)))))
        : emptyState('👥', 'Nobody in here yet', 'Be the first to load in.'),
      { bodyClass: 'flush' }),
    panel('Top players here',
      (data.topPlayers || []).length
        ? h('table', { class: 'tbl' },
            h('tbody', {}, data.topPlayers.map((p, i) => h('tr', {},
              h('td', { style: { width: '26px' } },
                h('b', { class: 'muted' }, `#${i + 1}`)),
              h('td', {}, h('a', { href: `#/profile/${p.id}` }, p.username)),
              h('td', { class: 'num' }, `${commas(p.kills || 0)} elims`)))))
        : emptyState('🏆', 'No records yet', 'Play a round to claim the top spot.'),
      { bodyClass: 'flush' }),
    panel('Server health', h('div', { class: 'col small' },
      row('Status', data.server.up
        ? h('span', { class: 'chip green' }, 'online')
        : h('span', { class: 'chip red' }, 'starting')),
      row('Tick time', data.server.tickMs != null
        ? `${data.server.tickMs.toFixed(2)} ms` : '—'),
      row('Uptime', data.server.uptime
        ? `${Math.round(data.server.uptime / 60)} min` : '—'),
      row('Simulation', '30 Hz authoritative · 20 Hz snapshots'))));

  page.appendChild(h('div', { class: 'grid sidebar-right' }, left, right));
  return () => {};
}

function row(label, value) {
  return h('div', { class: 'row' },
    h('span', { class: 'muted', style: { minWidth: '90px' } }, label),
    h('span', { class: 'bold' }, value));
}
