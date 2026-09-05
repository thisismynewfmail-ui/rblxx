// Hash router with route params and scroll restoration.

const routes = [];
let notFound = null;
let current = null;
let beforeEach = null;

export function route(pattern, handler) {
  const keys = [];
  const regex = new RegExp('^' + pattern
    .replace(/\/:([A-Za-z0-9_]+)\*/g, (_, k) => { keys.push(k); return '/(.+)'; })
    .replace(/\/:([A-Za-z0-9_]+)/g, (_, k) => { keys.push(k); return '/([^/]+)'; })
    + '$');
  routes.push({ regex, keys, handler, pattern });
}

export function fallback(handler) { notFound = handler; }
export function guard(fn) { beforeEach = fn; }

export function navigate(path, { replace = false } = {}) {
  const target = '#' + (path.startsWith('/') ? path : '/' + path);
  if (location.hash === target) { resolve(); return; }
  if (replace) history.replaceState(null, '', target);
  else location.hash = target;
}

export function currentPath() {
  const raw = location.hash.replace(/^#/, '') || '/home';
  return raw.split('?')[0] || '/home';
}

export function query() {
  const raw = location.hash.replace(/^#/, '');
  const qi = raw.indexOf('?');
  return qi < 0 ? new URLSearchParams()
    : new URLSearchParams(raw.slice(qi + 1));
}

export async function resolve() {
  const path = currentPath();
  for (const r of routes) {
    const m = r.regex.exec(path);
    if (!m) continue;
    const params = {};
    r.keys.forEach((k, i) => { params[k] = decodeURIComponent(m[i + 1]); });
    if (beforeEach) {
      const redirect = await beforeEach(path, r.pattern);
      if (redirect) return navigate(redirect, { replace: true });
    }
    current = { path, pattern: r.pattern, params };
    try {
      await r.handler(params, query());
    } catch (e) {
      console.error('route error', e);
    }
    return;
  }
  if (notFound) notFound(path);
}

export function start() {
  window.addEventListener('hashchange', () => {
    window.scrollTo(0, 0);
    resolve();
  });
  resolve();
}

export function activeRoute() { return current; }
