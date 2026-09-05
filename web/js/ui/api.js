// Thin JSON API client: CSRF, error surfacing and a tiny GET cache.

let csrfToken = null;
const listeners = new Set();

export function setCsrf(token) { csrfToken = token; }

export function onApiError(fn) { listeners.add(fn); return () => listeners.delete(fn); }

function readCookie(name) {
  const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return m ? decodeURIComponent(m[1]) : null;
}

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.status = status;
    this.payload = payload || {};
  }
}

async function request(method, path, body, opts = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const token = csrfToken || readCookie('rx_csrf');
  if (token && method !== 'GET') headers['X-CSRF-Token'] = token;

  let res;
  try {
    res = await fetch(path, {
      method,
      headers,
      credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    const err = new ApiError('Cannot reach the RBLXX server.', 0);
    if (!opts.quiet) listeners.forEach((fn) => fn(err));
    throw err;
  }

  let data = {};
  const text = await res.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = { raw: text }; }
  }
  if (!res.ok || data.ok === false) {
    const err = new ApiError(data.error || `Request failed (${res.status})`,
                             res.status, data);
    if (!opts.quiet) listeners.forEach((fn) => fn(err));
    throw err;
  }
  return data;
}

export const api = {
  get: (p, opts) => request('GET', p, undefined, opts),
  post: (p, b, opts) => request('POST', p, b || {}, opts),
  patch: (p, b, opts) => request('PATCH', p, b || {}, opts),
  del: (p, opts) => request('DELETE', p, undefined, opts),
};

// ---------------------------------------------------------------- helpers
export const Auth = {
  bootstrap: () => api.get('/api/bootstrap'),
  me: () => api.get('/api/auth/me'),
  login: (username, password) =>
    api.post('/api/auth/login', { username, password }, { quiet: true }),
  signup: (username, password, bio) =>
    api.post('/api/auth/signup', { username, password, bio }, { quiet: true }),
  logout: () => api.post('/api/auth/logout'),
  updateProfile: (data) => api.post('/api/auth/profile', data),
  changePassword: (current, next) =>
    api.post('/api/auth/password', { current, new: next }, { quiet: true }),
};

export const Worlds = {
  list: (params = {}) => api.get('/api/worlds?' + new URLSearchParams(params)),
  get: (id) => api.get(`/api/worlds/${encodeURIComponent(id)}`),
  vote: (id, value) => api.post(`/api/worlds/${encodeURIComponent(id)}/vote`, { value }),
  favorite: (id) => api.post(`/api/worlds/${encodeURIComponent(id)}/favorite`),
  favorites: () => api.get('/api/favorites'),
  servers: () => api.get('/api/servers'),
};

export const Catalog = {
  list: (params = {}) => api.get('/api/catalog?' + new URLSearchParams(params)),
  item: (id) => api.get(`/api/catalog/${encodeURIComponent(id)}`),
  buy: (id) => api.post(`/api/catalog/${encodeURIComponent(id)}/buy`, {}, { quiet: true }),
};

export const Avatar = {
  get: () => api.get('/api/avatar'),
  colors: (colors) => api.post('/api/avatar/colors', { colors }),
  equip: (itemId) => api.post('/api/avatar/equip', { itemId }),
  unequip: (slot) => api.post('/api/avatar/unequip', { slot }),
  scale: (scale) => api.post('/api/avatar/scale', { scale }),
  saveOutfit: (name) => api.post('/api/avatar/outfits', { name }),
  wearOutfit: (id) => api.post(`/api/avatar/outfits/${id}/wear`),
  deleteOutfit: (id) => api.del(`/api/avatar/outfits/${id}`),
};

export const Users = {
  profile: (name) => api.get(`/api/users/${encodeURIComponent(name)}`),
  inventory: (name, category) =>
    api.get(`/api/users/${encodeURIComponent(name)}/inventory?category=${category || 'all'}`),
  posts: (name, before) =>
    api.get(`/api/users/${encodeURIComponent(name)}/posts`
      + (before ? `?before=${before}` : '')),
  friends: (name) => api.get(`/api/users/${encodeURIComponent(name)}/friends`),
  followers: (name) => api.get(`/api/users/${encodeURIComponent(name)}/followers`),
  search: (q) => api.get('/api/search/users?q=' + encodeURIComponent(q)),
  leaderboard: (metric) => api.get('/api/leaderboard?metric=' + (metric || 'kills')),
  online: () => api.get('/api/online'),
};

export const Social = {
  friends: () => api.get('/api/friends'),
  request: (user, note) => api.post('/api/friends/request', { user, note }, { quiet: true }),
  accept: (user) => api.post('/api/friends/accept', { user }),
  decline: (user) => api.post('/api/friends/decline', { user }),
  cancel: (user) => api.post('/api/friends/cancel', { user }),
  remove: (user) => api.post('/api/friends/remove', { user }),
  follow: (user) => api.post('/api/follow', { user }),
  block: (user, unblock) => api.post('/api/block', { user, unblock }),
  blocked: () => api.get('/api/blocked'),
  feed: (scope, before) => api.get('/api/feed?scope=' + (scope || 'friends')
    + (before ? `&before=${before}` : '')),
  post: (body, worldId) => api.post('/api/posts', { body, worldId }, { quiet: true }),
  like: (id) => api.post(`/api/posts/${id}/like`),
  deletePost: (id) => api.del(`/api/posts/${id}`),
  comments: (id) => api.get(`/api/posts/${id}/comments`),
  comment: (id, body) => api.post(`/api/posts/${id}/comments`, { body }, { quiet: true }),
  messages: () => api.get('/api/messages'),
  sendMessage: (to, subject, body) =>
    api.post('/api/messages', { to, subject, body }, { quiet: true }),
  readMessage: (id) => api.post(`/api/messages/${id}/read`),
  deleteMessage: (id) => api.del(`/api/messages/${id}`),
  notifications: () => api.get('/api/notifications'),
  readNotifications: () => api.post('/api/notifications/read'),
  badges: () => api.get('/api/badges'),
};

export const Economy = { view: () => api.get('/api/economy') };
