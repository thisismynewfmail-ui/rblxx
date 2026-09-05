// A tiny observable app store.

const state = {
  user: null,
  render: null,          // the signed-in player's avatar render bundle
  worlds: [],
  unread: { messages: 0, notifications: 0 },
  totalPlaying: 0,
  currency: 'Bux',
  theme: localStorage.getItem('rblxx.theme') || 'light',
  ready: false,
};

const subs = new Set();

export function getState() { return state; }

export function subscribe(fn) {
  subs.add(fn);
  return () => subs.delete(fn);
}

export function setState(patch) {
  Object.assign(state, patch);
  for (const fn of [...subs]) fn(state);
}

export function setTheme(theme) {
  state.theme = theme;
  localStorage.setItem('rblxx.theme', theme);
  document.documentElement.dataset.theme = theme;
  for (const fn of [...subs]) fn(state);
}

export function applyStoredTheme() {
  document.documentElement.dataset.theme = state.theme;
}
