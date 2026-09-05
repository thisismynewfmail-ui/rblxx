// Shared UI building blocks: toasts, modals, cards, tiles.

import { h, clear, esc, fmt, commas, ago, date } from './dom.js';
import { drawAvatar, drawItem } from './iso.js';
import { worldThumb } from './thumbs.js';
import { navigate } from './router.js';

// ------------------------------------------------------------------ toast
let toastHost = null;
export function toast(title, body, kind = '', ttl = 4200) {
  if (!toastHost) {
    toastHost = document.getElementById('toasts')
      || document.body.appendChild(h('div', { id: 'toasts' }));
  }
  const el = h('div', { class: `toast ${kind}` },
    h('div', { class: 'tt' }, title),
    body ? h('div', { class: 'tb' }, body) : null);
  toastHost.appendChild(el);
  const kill = () => {
    el.style.transition = 'opacity .25s, transform .25s';
    el.style.opacity = '0';
    el.style.transform = 'translateX(14px)';
    setTimeout(() => el.remove(), 260);
  };
  el.addEventListener('click', kill);
  setTimeout(kill, ttl);
  return el;
}

// ------------------------------------------------------------------ modal
export function modal(title, content, actions = []) {
  const back = h('div', { class: 'modal-back' });
  const box = h('div', { class: 'modal' },
    h('div', { class: 'panel-head' }, title,
      h('span', { class: 'spacer', style: { flex: 1 } }),
      h('button', {
        class: 'icon-btn', style: { background: 'transparent', border: 0,
                                    color: '#fff' },
        onClick: () => close(),
      }, '✕')),
    h('div', { class: 'panel-body' }, content),
    actions.length
      ? h('div', {
          class: 'panel-body',
          style: { borderTop: '1px solid var(--line-soft)', display: 'flex',
                   gap: '8px', justifyContent: 'flex-end',
                   background: 'var(--panel-2)' },
        }, actions)
      : null);
  back.appendChild(box);
  back.addEventListener('mousedown', (e) => { if (e.target === back) close(); });
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  window.addEventListener('keydown', onKey);
  function close() {
    window.removeEventListener('keydown', onKey);
    back.remove();
  }
  document.body.appendChild(back);
  return { el: back, close };
}

export function confirmDialog(title, message, confirmLabel = 'Confirm') {
  return new Promise((resolve) => {
    const m = modal(title, h('p', {}, message), [
      h('button', { class: 'btn ghost', onClick: () => { m.close(); resolve(false); } },
        'Cancel'),
      h('button', { class: 'btn red', onClick: () => { m.close(); resolve(true); } },
        confirmLabel),
    ]);
  });
}

// ------------------------------------------------------------------ panel
export function panel(title, body, opts = {}) {
  return h('div', { class: 'panel ' + (opts.class || '') },
    title ? h('div', { class: 'panel-head' },
      title,
      opts.action ? [h('span', { class: 'spacer', style: { flex: 1 } }),
                     opts.action] : null) : null,
    h('div', { class: 'panel-body ' + (opts.bodyClass || '') }, body));
}

export function emptyState(icon, title, note, action) {
  return h('div', {
    style: { textAlign: 'center', padding: '34px 18px', color: 'var(--ink-soft)' },
  },
    h('div', { style: { fontSize: '38px', opacity: '.5', marginBottom: '6px' } }, icon),
    h('div', { style: { fontWeight: '700', marginBottom: '4px',
                        color: 'var(--ink)' } }, title),
    note ? h('div', { class: 'small' }, note) : null,
    action ? h('div', { style: { marginTop: '12px' } }, action) : null);
}

export function skeletonGrid(n = 8, height = '170px') {
  return h('div', { class: 'card-grid' },
    Array.from({ length: n }, () =>
      h('div', { class: 'skeleton', style: { height } })));
}

export function spinnerBlock(label = 'Loading…') {
  return h('div', {
    style: { display: 'flex', gap: '10px', alignItems: 'center',
             justifyContent: 'center', padding: '30px', color: 'var(--ink-soft)' },
  }, h('div', { class: 'spinner', style: { borderTopColor: 'var(--blue)',
                                           borderColor: 'var(--line)' } }), label);
}

// -------------------------------------------------------------- game card
export function gameCard(world, opts = {}) {
  const canvas = h('canvas', { class: 'thumb-art', width: 320, height: 240 });
  requestAnimationFrame(() => worldThumb(canvas, world.id,
    { width: 320, height: 240 }));
  const card = h('div', {
    class: 'gcard',
    onClick: () => navigate(`/game/${world.id}`),
    title: world.tagline,
  },
    h('div', { class: 'thumb' },
      canvas,
      world.playing > 0
        ? h('div', { class: 'badge-live' }, h('i', { class: 'dot' }),
            `${fmt(world.playing)} playing`)
        : null,
      h('div', { class: 'mode-tag' }, world.mode)),
    h('div', { class: 'meta' },
      h('div', { class: 'title' }, world.name),
      h('div', { class: 'players' },
        world.playing > 0 ? `${commas(world.playing)} players online`
          : `${fmt(world.visits)} visits`),
      world.ratio != null
        ? h('div', { class: 'votes' },
            h('span', {}, `Voted: ${world.ratio}%`),
            h('span', { class: 'ratio-bar' },
              h('i', { style: { width: world.ratio + '%' } })))
        : h('div', { class: 'votes' }, 'No ratings yet')));
  if (opts.wide) card.style.width = '100%';
  return card;
}

// ------------------------------------------------------------ player tile
export function playerTile(user, opts = {}) {
  const canvas = h('canvas');
  const box = h('div', { class: 'fbox' }, canvas);
  const tile = h('div', {
    class: 'friend-tile',
    onClick: () => navigate(`/profile/${user.username || user.id}`),
    title: user.username,
  }, box,
    h('div', { class: 'fname' },
      h('i', { class: user.online ? 'online-dot' : 'offline-dot' }),
      h('span', { class: 'nowrap' }, user.username)));
  requestAnimationFrame(() => {
    if (!canvas.isConnected) return;
    drawAvatar(canvas, user.render || { colors: paletteFor(user) },
               { scale: 0.92 });
  });
  return tile;
}

// A deterministic pleasant palette so players without a loaded bundle still
// look distinct in lists.
export function paletteFor(user) {
  const seed = (user.id || 0) * 2654435761 % 360;
  const skin = ['#f3d64e', '#f7c6a3', '#a3714a', '#bfe6cf', '#e8b93d'][
    (user.id || 0) % 5];
  const torso = `hsl(${seed}, 55%, 45%)`;
  const legs = `hsl(${(seed + 40) % 360}, 40%, 35%)`;
  return { head: skin, torso, left_arm: skin, right_arm: skin,
           left_leg: legs, right_leg: legs };
}

// -------------------------------------------------------------- item card
export function itemCard(item, opts = {}) {
  const canvas = h('canvas');
  const card = h('div', {
    class: 'icard' + (opts.equipped ? ' equipped' : ''),
    style: { '--rc': item.rarityColor || '#9aa2ab' },
    onClick: () => opts.onClick && opts.onClick(item),
    title: `${item.name} — ${item.description}`,
  },
    h('div', { class: 'ithumb' }, canvas,
      h('i', { class: 'rarity-flag' }),
      item.limited ? h('div', { class: 'limited-tag' }, 'LIMITED') : null,
      item.owned || opts.owned ? h('div', { class: 'owned-tick' }, '✓') : null),
    h('div', { class: 'iname' }, item.name),
    h('div', { class: 'iprice' },
      opts.priceLabel !== undefined ? opts.priceLabel
        : (item.price > 0 ? [h('i', { class: 'coin',
            style: { width: '11px', height: '11px', borderRadius: '50%',
                     background: 'radial-gradient(circle at 34% 32%, #ffe9a8, #e8a317 62%, #9a6b06)',
                     display: 'inline-block' } }), commas(item.price)]
          : 'Free')));
  requestAnimationFrame(() => {
    if (canvas.isConnected) drawItem(canvas, item);
  });
  return card;
}

// ------------------------------------------------------------------ tabs
export function tabs(items, active, onSelect) {
  return h('div', { class: 'tabs' },
    items.map((it) => h('div', {
      class: 'tab' + (it.id === active ? ' active' : ''),
      onClick: () => onSelect(it.id),
    }, it.label, it.count != null
      ? h('span', { class: 'chip', style: { marginLeft: '5px' } }, String(it.count))
      : null)));
}

export function sectionHead(title, action) {
  return h('div', { class: 'section-head' },
    h('h2', {}, title),
    action ? h('div', { class: 'see-all' }, action) : null);
}

export function statStrip(stats) {
  return h('div', { class: 'stat-strip' },
    stats.map(([label, value]) => h('div', { class: 'st' },
      h('b', {}, String(value)), h('span', {}, label))));
}

export function rail(children) {
  const track = h('div', { class: 'rail' }, children);
  const wrap = h('div', { class: 'card-rail' },
    h('button', { class: 'rail-btn left', onClick: () =>
      track.scrollBy({ left: -track.clientWidth * 0.8, behavior: 'smooth' }) }, '‹'),
    track,
    h('button', { class: 'rail-btn right', onClick: () =>
      track.scrollBy({ left: track.clientWidth * 0.8, behavior: 'smooth' }) }, '›'));
  return wrap;
}

export function badgeDisc(badge, size = 52) {
  const ICONS = {
    star: '★', heart: '♥', people: '☻', megaphone: '📣', box: '▣',
    crown: '♔', target: '◎', sword: '⚔', brick: '▤', shield: '⛨',
    flame: '🔥', flag: '⚑', home: '⌂', medal: '✪',
  };
  return h('div', { class: 'badge-item', title: badge.description },
    h('div', {
      class: 'disc',
      style: { width: size + 'px', height: size + 'px',
               background: `radial-gradient(circle at 34% 30%, ${badge.color}, ${shadeHex(badge.color, -0.4)})` },
    }, ICONS[badge.icon] || '★'),
    h('div', { class: 'bname' }, badge.name));
}

function shadeHex(hex, amount) {
  const n = parseInt((hex || '#888').replace('#', ''), 16);
  const f = (v) => Math.max(0, Math.min(255, Math.round(v * (1 + amount))));
  return `rgb(${f((n >> 16) & 255)},${f((n >> 8) & 255)},${f(n & 255)})`;
}

export { fmt, commas, ago, date, esc, h, clear };
