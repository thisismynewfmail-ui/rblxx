// The front page: hero, discover rails, live servers, friends and the feed.

import { h, clear, fmt, commas, ago } from '../dom.js';
import { Worlds, Social, Users } from '../api.js';
import { getState } from '../store.js';
import { navigate } from '../router.js';
import { gameCard, panel, rail, sectionHead, playerTile, emptyState,
         skeletonGrid, spinnerBlock, paletteFor } from '../components.js';
import { drawAvatar } from '../iso.js';
import { worldThumb } from '../thumbs.js';

export async function render(root) {
  document.title = 'RBLXX — Home';
  const state = getState();
  const page = h('div', { class: 'page' });
  clear(root).appendChild(page);

  const worlds = state.worlds && state.worlds.length ? state.worlds
    : (await Worlds.list({ sort: 'featured' })).worlds;

  // ---- hero ----
  const featured = worlds[0];
  page.appendChild(heroBanner(featured, worlds));

  // ---- discover ----
  const popular = [...worlds].sort((a, b) =>
    (b.playing - a.playing) || (b.visits - a.visits));
  page.appendChild(sectionHead('Most Engaging',
    h('a', { href: '#/games' }, 'See All')));
  page.appendChild(rail(popular.map((w) => gameCard(w))));

  page.appendChild(sectionHead('Recommended For You',
    h('a', { href: '#/games?sort=rating' }, 'See All')));
  page.appendChild(rail([...worlds].sort((a, b) =>
    (b.ratio || 0) - (a.ratio || 0)).map((w) => gameCard(w))));

  // ---- two column: feed + sidebar ----
  const grid = h('div', { class: 'grid sidebar-right',
                          style: { marginTop: '22px' } });
  const feedCol = h('div');
  const sideCol = h('div', { class: 'col' });
  grid.append(feedCol, sideCol);
  page.appendChild(grid);

  feedCol.appendChild(panel('Latest from the community',
    spinnerBlock('Loading the feed…'), { bodyClass: 'flush' }));
  sideCol.appendChild(panel('Servers', spinnerBlock('Checking…'),
    { bodyClass: 'flush' }));

  // feed
  (async () => {
    try {
      const { posts } = await Social.feed('everyone');
      const body = posts.length
        ? h('div', {}, posts.slice(0, 8).map(postRow))
        : emptyState('💬', 'Nothing posted yet',
            'Be the first to say something.',
            h('a', { class: 'btn', href: '#/feed' }, 'Write a post'));
      feedCol.replaceChildren(panel('Latest from the community', body, {
        bodyClass: 'flush',
        action: h('a', { href: '#/feed' }, 'Open feed'),
      }));
    } catch { /* handled by the global error toast */ }
  })();

  // servers + online players
  (async () => {
    try {
      const [{ nodes }, online] = await Promise.all([
        Worlds.servers(), Users.online().catch(() => ({ users: [] })),
      ]);
      const rows = h('table', { class: 'tbl' },
        h('thead', {}, h('tr', {},
          h('th', {}, 'World'), h('th', {}, 'Status'),
          h('th', { style: { textAlign: 'right' } }, 'Players'))),
        h('tbody', {}, nodes.map((n) => {
          const world = worlds.find((w) => w.id === n.world);
          return h('tr', { style: { cursor: 'pointer' },
                           onClick: () => navigate(`/game/${n.world}`) },
            h('td', {}, world ? world.name : n.world),
            h('td', {}, n.up
              ? h('span', { class: 'chip green' }, 'online')
              : h('span', { class: 'chip red' }, 'starting')),
            h('td', { class: 'num' }, `${n.players}/${n.max || 16}`));
        })));
      sideCol.firstChild.replaceWith(panel('Live Servers', rows,
        { bodyClass: 'flush' }));

      if (online.users && online.users.length) {
        sideCol.appendChild(panel(`Online Now (${online.users.length})`,
          h('div', { class: 'friend-grid' },
            online.users.slice(0, 12).map((u) =>
              playerTile({ ...u, online: true })))));
      }
    } catch { /* ignore */ }
  })();

  sideCol.appendChild(panel('Getting started', h('div', { class: 'col' },
    tip('1', 'Pick a world', 'Open the World Browser and press Load on any '
      + 'experience to drop straight into it.'),
    tip('2', 'Build your look', 'The Avatar Editor lets you recolour every '
      + 'body part and stack hats.'),
    tip('3', 'Bring friends', 'Add friends, follow builders and post about '
      + 'your best rounds.'))));

  return () => {};
}

function tip(n, title, body) {
  return h('div', { style: { display: 'flex', gap: '10px' } },
    h('div', {
      style: { width: '22px', height: '22px', flex: 'none', borderRadius: '50%',
               background: 'var(--blue)', color: '#fff', display: 'grid',
               placeItems: 'center', fontWeight: '700', fontSize: '11px' },
    }, n),
    h('div', {}, h('div', { class: 'bold' }, title),
      h('div', { class: 'small muted' }, body)));
}

function heroBanner(world, worlds) {
  if (!world) return h('div');
  const canvas = h('canvas', {
    style: { position: 'absolute', inset: '0', width: '100%', height: '100%',
             objectFit: 'cover' },
  });
  requestAnimationFrame(() => worldThumb(canvas, world.id,
    { width: 1180, height: 380 }));
  return h('div', {
    class: 'panel',
    style: { position: 'relative', overflow: 'hidden', minHeight: '250px',
             display: 'flex', alignItems: 'flex-end', padding: '0' },
  },
    canvas,
    h('div', {
      style: { position: 'relative', zIndex: '2', padding: '22px 24px',
               width: '100%',
               background: 'linear-gradient(0deg, rgba(8,12,18,.88), rgba(8,12,18,.25) 60%, transparent)' },
    },
      h('div', { class: 'chip gold', style: { marginBottom: '8px' } },
        'Featured experience'),
      h('h1', { style: { color: '#fff', margin: '0 0 4px',
                         textShadow: '0 3px 12px rgba(0,0,0,.7)' } }, world.name),
      h('div', { style: { color: '#dbe6f2', marginBottom: '12px',
                          maxWidth: '620px' } }, world.tagline),
      h('div', { class: 'row' },
        h('button', { class: 'btn play',
                      onClick: () => navigate(`/game/${world.id}`) }, 'Load'),
        h('button', { class: 'btn ghost', onClick: () => navigate('/games') },
          'Browse all worlds'),
        h('div', { style: { color: '#cfe0ee', marginLeft: '6px' } },
          `${commas(world.playing)} playing now · ${fmt(world.visits)} visits`))));
}

function postRow(post) {
  const canvas = h('canvas', { style: { width: '100%', height: '100%' } });
  requestAnimationFrame(() => {
    if (canvas.isConnected) {
      drawAvatar(canvas, { colors: paletteFor({ id: post.user_id }) },
                 { scale: 0.88, shadow: false });
    }
  });
  return h('div', { class: 'post' },
    h('div', { class: 'pav' }, canvas),
    h('div', { class: 'pbody' },
      h('div', { class: 'pmeta' },
        h('a', { class: 'who', href: `#/profile/${post.username}` }, post.username),
        h('span', { class: 'faint tiny' }, ago(post.created_at)),
        post.world_name
          ? h('span', { class: 'chip blue' }, post.world_name) : null),
      h('div', { class: 'ptext' }, post.body),
      h('div', { class: 'pacts' },
        h('span', {}, `♥ ${post.like_count}`),
        h('span', {}, `💬 ${post.reply_count}`))));
}
