// Application shell: chrome, routing and global state wiring.

import { h, clear, commas, debounce } from './dom.js';
import { api, Auth, Users, setCsrf, onApiError } from './api.js';
import { getState, setState, subscribe, setTheme, applyStoredTheme } from './store.js';
import * as router from './router.js';
import { toast } from './components.js';
import { disposeAllPreviews } from './preview3d.js';

const MAIN_NAV = [
  { path: '/home', label: 'Home' },
  { path: '/games', label: 'Games' },
  { path: '/catalog', label: 'Catalog' },
  { path: '/feed', label: 'Feed' },
  { path: '/leaderboard', label: 'Leaderboard' },
];

const SUB_NAV = [
  { path: '/home', label: 'Home' },
  { path: '/profile', label: 'Profile', auth: true },
  { path: '/messages', label: 'Messages', auth: true, badge: 'messages' },
  { path: '/friends', label: 'Friends', auth: true },
  { path: '/avatar', label: 'Avatar', auth: true },
  { path: '/inventory', label: 'Inventory', auth: true },
  { path: '/notifications', label: 'Alerts', auth: true, badge: 'notifications' },
  { path: '/settings', label: 'Settings', auth: true },
];

const PAGES = {
  home: () => import('./pages/home.js'),
  games: () => import('./pages/games.js'),
  gamedetail: () => import('./pages/gamedetail.js'),
  profile: () => import('./pages/profile.js'),
  avatar: () => import('./pages/avatar.js'),
  inventory: () => import('./pages/inventory.js'),
  catalog: () => import('./pages/catalog.js'),
  friends: () => import('./pages/friends.js'),
  feed: () => import('./pages/feed.js'),
  messages: () => import('./pages/messages.js'),
  leaderboard: () => import('./pages/leaderboard.js'),
  settings: () => import('./pages/settings.js'),
  notifications: () => import('./pages/notifications.js'),
  auth: () => import('./pages/auth.js'),
};

let cleanup = null;
let outlet = null;

async function mount(pageKey, params, query) {
  if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }
  disposeAllPreviews();
  renderShell();          // keeps the nav highlight in step with the route
  const mod = await PAGES[pageKey]();
  document.body.classList.toggle('bare', pageKey === 'auth');
  cleanup = await mod.render(outlet, params, query);
}

function chrome() {
  const state = getState();
  const brand = h('div', { class: 'brandbar' },
    h('div', { class: 'brandbar-inner' },
      h('a', { class: 'logo', href: '#/home' }, 'RBL', h('span', { class: 'x' }, 'XX')),
      searchBar(),
      h('div', { class: 'brand-actions' }, ...brandActions(state))));

  const main = h('nav', { class: 'mainnav' },
    h('div', { class: 'mainnav-inner' },
      MAIN_NAV.map((n) => h('a', {
        href: '#' + n.path,
        class: isActive(n.path) ? 'active' : '',
      }, n.label))));

  const sub = h('nav', { class: 'subnav' },
    h('div', { class: 'subnav-inner' },
      SUB_NAV.filter((n) => !n.auth || state.user).map((n) => {
        const href = n.path === '/profile' && state.user
          ? `#/profile/${state.user.username}` : '#' + n.path;
        const count = n.badge ? (state.unread[n.badge] || 0) : 0;
        return h('a', { href, class: isActive(n.path) ? 'active' : '' },
          n.label, count ? h('span', { class: 'pill' }, String(count)) : null);
      }),
      state.user ? null : h('a', { href: '#/login' }, 'Sign in')));

  return [brand, main, sub];
}

function isActive(path) {
  const cur = router.currentPath();
  return cur === path || cur.startsWith(path + '/');
}

function brandActions(state) {
  const out = [];
  if (state.user) {
    out.push(h('a', { class: 'currency', href: '#/settings',
                      title: 'Your balance' },
      h('i', { class: 'coin' }), commas(state.user.coins)));
    out.push(h('a', {
      class: 'icon-btn', href: '#/notifications', title: 'Notifications',
    }, '🔔', state.unread.notifications
      ? h('span', { class: 'badge-count' },
          String(state.unread.notifications)) : null));
    out.push(h('a', {
      class: 'icon-btn', href: '#/messages', title: 'Messages',
    }, '✉', state.unread.messages
      ? h('span', { class: 'badge-count' }, String(state.unread.messages)) : null));
    out.push(h('button', {
      class: 'icon-btn', title: 'Toggle theme',
      onClick: () => setTheme(getState().theme === 'dark' ? 'light' : 'dark'),
    }, getState().theme === 'dark' ? '☀' : '🌙'));
    out.push(h('a', { class: 'btn sm ghost',
                      href: `#/profile/${state.user.username}` },
      state.user.username));
  } else {
    out.push(h('button', {
      class: 'icon-btn', title: 'Toggle theme',
      onClick: () => setTheme(getState().theme === 'dark' ? 'light' : 'dark'),
    }, getState().theme === 'dark' ? '☀' : '🌙'));
    out.push(h('a', { class: 'btn', href: '#/login' }, 'Sign in'));
    out.push(h('a', { class: 'btn green', href: '#/login?mode=signup' },
      'Create account'));
  }
  return out;
}

function searchBar() {
  const input = h('input', { placeholder: 'Search players and worlds…',
                             'aria-label': 'Search' });
  const results = h('div', { class: 'search-results', style: { display: 'none' } });
  const wrap = h('div', { class: 'searchbar' }, input,
    h('button', { class: 'go', title: 'Search' }, '⌕'), results);

  const run = debounce(async () => {
    const q = input.value.trim();
    if (q.length < 2) { results.style.display = 'none'; return; }
    const worlds = (getState().worlds || []).filter((w) =>
      w.name.toLowerCase().includes(q.toLowerCase()));
    let users = [];
    try { users = (await Users.search(q)).users; } catch { /* ignore */ }
    clear(results);
    if (!worlds.length && !users.length) {
      results.appendChild(h('div', { class: 'sr muted' }, 'No matches'));
    }
    for (const w of worlds.slice(0, 4)) {
      results.appendChild(h('div', { class: 'sr', onClick: () => {
        router.navigate(`/game/${w.id}`); results.style.display = 'none';
        input.value = '';
      } }, h('span', { class: 'chip blue' }, 'World'),
        h('span', { class: 'bold' }, w.name)));
    }
    for (const u of users.slice(0, 6)) {
      results.appendChild(h('div', { class: 'sr', onClick: () => {
        router.navigate(`/profile/${u.username}`); results.style.display = 'none';
        input.value = '';
      } }, h('i', { class: u.online ? 'online-dot' : 'offline-dot' }),
        h('span', { class: 'bold' }, u.username)));
    }
    results.style.display = 'block';
  }, 240);

  input.addEventListener('input', run);
  input.addEventListener('focus', run);
  document.addEventListener('click', (e) => {
    if (!wrap.contains(e.target)) results.style.display = 'none';
  });
  return wrap;
}

function footer() {
  return h('footer', { class: 'footer' },
    h('div', { class: 'footer-inner' },
      h('div', {}, h('b', {}, 'RBLXX'), ' · a classic-flavoured game platform'),
      h('a', { href: '#/games' }, 'Worlds'),
      h('a', { href: '#/catalog' }, 'Catalog'),
      h('a', { href: '#/leaderboard' }, 'Leaderboard'),
      h('span', { style: { flex: 1 } }),
      h('span', {}, 'Runs entirely on your own machine.')));
}

function renderShell() {
  const app = document.getElementById('app');
  const scrollY = window.scrollY;
  clear(app);
  const [brand, main, sub] = chrome();
  outlet = outlet || h('main', { id: 'outlet', style: { flex: 1,
                                                        display: 'flex',
                                                        flexDirection: 'column' } });
  app.append(brand, main, sub, outlet, footer());
  window.scrollTo(0, scrollY);
}

async function refreshUnread() {
  const state = getState();
  if (!state.user) return;
  try {
    const me = await Auth.me();
    if (me.user) {
      setState({ user: { ...state.user, coins: me.user.coins },
                 render: me.render, unread: me.unread });
    }
  } catch { /* offline; try again later */ }
}

export async function boot() {
  applyStoredTheme();
  const app = document.getElementById('app');
  app.className = 'app';
  outlet = h('main', { id: 'outlet',
                       style: { flex: 1, display: 'flex',
                                flexDirection: 'column' } });

  onApiError((err) => {
    if (err.status === 401) return;
    toast('Something went wrong', err.message, 'bad');
  });

  let boot;
  try {
    boot = await Auth.bootstrap();
  } catch {
    app.innerHTML = '<div class="page"><div class="panel"><div class="panel-body">'
      + '<h2>Cannot reach the RBLXX server</h2>'
      + '<p class="muted">Make sure <code>python3 main.py</code> is running, '
      + 'then reload this page.</p></div></div></div>';
    return;
  }
  if (boot.csrf) setCsrf(boot.csrf);
  setState({
    user: boot.user, render: boot.render, worlds: boot.worlds || [],
    totalPlaying: boot.totalPlaying || 0, currency: boot.currency || 'Bux',
    unread: boot.unread || { messages: 0, notifications: 0 },
    ready: true,
  });

  subscribe(() => renderShell());
  renderShell();

  // ------------------------------------------------------------- routes
  router.route('/home', (p, q) => mount('home', p, q));
  router.route('/games', (p, q) => mount('games', p, q));
  router.route('/game/:id', (p, q) => mount('gamedetail', p, q));
  router.route('/profile', (p, q) => {
    const u = getState().user;
    if (!u) return router.navigate('/login');
    return router.navigate(`/profile/${u.username}`, { replace: true });
  });
  router.route('/profile/:name', (p, q) => mount('profile', p, q));
  router.route('/avatar', (p, q) => mount('avatar', p, q));
  router.route('/inventory', (p, q) => mount('inventory', p, q));
  router.route('/inventory/:name', (p, q) => mount('inventory', p, q));
  router.route('/catalog', (p, q) => mount('catalog', p, q));
  router.route('/friends', (p, q) => mount('friends', p, q));
  router.route('/friends/:name', (p, q) => mount('friends', p, q));
  router.route('/feed', (p, q) => mount('feed', p, q));
  router.route('/messages', (p, q) => mount('messages', p, q));
  router.route('/leaderboard', (p, q) => mount('leaderboard', p, q));
  router.route('/settings', (p, q) => mount('settings', p, q));
  router.route('/notifications', (p, q) => mount('notifications', p, q));
  router.route('/login', (p, q) => mount('auth', p, q));
  router.route('/signup', (p, q) => mount('auth', p,
    new URLSearchParams('mode=signup')));

  router.guard((path) => {
    const needsAuth = ['/avatar', '/settings', '/messages', '/notifications']
      .some((r) => path === r);
    if (needsAuth && !getState().user) {
      return `/login?next=${encodeURIComponent(path)}`;
    }
    return null;
  });

  router.fallback(() => {
    clear(outlet).appendChild(h('div', { class: 'page' },
      h('div', { class: 'panel' }, h('div', { class: 'panel-body center' },
        h('h1', {}, '404'),
        h('p', { class: 'muted' }, 'That page does not exist.'),
        h('a', { class: 'btn', href: '#/home' }, 'Back home')))));
  });

  router.start();
  setInterval(refreshUnread, 45000);
  window.addEventListener('focus', refreshUnread);
}

boot();
