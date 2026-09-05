// Account settings: profile text, theme, password, currency history, blocks.

import { h, clear, commas, ago, date } from '../dom.js';
import { Auth, Economy, Social } from '../api.js';
import { getState, setState, setTheme } from '../store.js';
import { navigate } from '../router.js';
import { panel, toast, emptyState, spinnerBlock, confirmDialog } from '../components.js';

export async function render(root) {
  const me = getState().user;
  if (!me) { navigate('/login'); return () => {}; }
  document.title = 'Settings — RBLXX';

  const page = h('div', { class: 'page' });
  clear(root).appendChild(page);

  const bio = h('textarea', { class: 'field', maxlength: 280,
                              style: { minHeight: '90px' } });
  bio.value = me.bio || '';
  const status = h('input', { class: 'field', maxlength: 90,
                              placeholder: 'What are you up to?' });
  status.value = me.status || '';

  const saveProfile = h('button', { class: 'btn', onClick: async () => {
    const res = await Auth.updateProfile({ bio: bio.value, status: status.value });
    setState({ user: { ...getState().user, bio: res.user.bio,
                       status: res.user.status } });
    toast('Profile saved', '', 'good');
  } }, 'Save profile');

  const cur = h('input', { class: 'field', type: 'password',
                           placeholder: 'Current password' });
  const nw = h('input', { class: 'field', type: 'password',
                          placeholder: 'New password' });
  const pwErr = h('div', { class: 'small', style: { color: 'var(--brand)' } });
  const savePw = h('button', { class: 'btn', onClick: async () => {
    pwErr.textContent = '';
    try {
      await Auth.changePassword(cur.value, nw.value);
      cur.value = nw.value = '';
      toast('Password changed', 'You have been signed out everywhere else.',
            'good');
    } catch (e) { pwErr.textContent = e.message; }
  } }, 'Change password');

  const themeRow = h('div', { class: 'row' },
    ...['light', 'dark'].map((t) => h('button', {
      class: 'btn ' + (getState().theme === t ? '' : 'ghost'),
      onClick: (e) => {
        setTheme(t);
        [...themeRow.children].forEach((b, i) =>
          b.className = 'btn ' + (['light', 'dark'][i] === t ? '' : 'ghost'));
      },
    }, t === 'light' ? '☀ Classic light' : '🌙 Night mode')));

  const walletBox = h('div', {}, spinnerBlock('Loading transactions…'));
  const blockedBox = h('div', {}, spinnerBlock('Loading…'));

  page.append(
    h('div', { class: 'page-head' },
      h('h1', {}, 'Settings'),
      h('span', { class: 'sub' }, `Signed in as ${me.username}`)),
    h('div', { class: 'grid two' },
      h('div', { class: 'col' },
        panel('Profile', h('div', { class: 'col' },
          h('div', {}, h('label', { class: 'lbl' }, 'Status'), status),
          h('div', {}, h('label', { class: 'lbl' }, 'About me'), bio),
          h('div', { class: 'row' }, saveProfile,
            h('a', { class: 'btn ghost', href: `#/profile/${me.username}` },
              'View my profile')))),
        panel('Appearance', h('div', { class: 'col' },
          h('div', { class: 'small muted' },
            'The classic light theme matches the old site; night mode is easier '
            + 'on the eyes for long sessions.'),
          themeRow)),
        panel('Security', h('div', { class: 'col' },
          h('div', {}, h('label', { class: 'lbl' }, 'Current password'), cur),
          h('div', {}, h('label', { class: 'lbl' }, 'New password'), nw),
          pwErr, savePw,
          h('div', { class: 'divider' }),
          h('button', { class: 'btn red', onClick: async () => {
            if (!await confirmDialog('Sign out', 'Sign out of RBLXX?',
                                     'Sign out')) return;
            await Auth.logout();
            location.hash = '#/login';
            location.reload();
          } }, 'Sign out')))),
      h('div', { class: 'col' },
        panel(`Wallet — ${commas(me.coins)} Bux`, walletBox,
              { bodyClass: 'flush' }),
        panel('Blocked players', blockedBox),
        panel('About', h('div', { class: 'col small muted' },
          h('div', {}, h('b', {}, 'RBLXX'),
            ' — a self-hosted classic-flavoured game platform.'),
          h('div', {}, 'Five worlds, one port, zero third-party packages.'),
          h('div', {}, 'Simulation: 30 Hz authoritative, 20 Hz snapshots, '
            + 'client-side prediction with server reconciliation.'),
          h('div', {}, h('a', { href: '#/leaderboard' }, 'Leaderboard'), ' · ',
            h('a', { href: '#/games' }, 'World browser'), ' · ',
            h('a', { href: '#/catalog' }, 'Catalog')))))));

  (async () => {
    const data = await Economy.view();
    clear(walletBox);
    if (!data.history.length) {
      walletBox.appendChild(emptyState('🪙', 'No transactions yet', ''));
      return;
    }
    walletBox.appendChild(h('table', { class: 'tbl' },
      h('thead', {}, h('tr', {}, h('th', {}, 'When'), h('th', {}, 'Reason'),
        h('th', { style: { textAlign: 'right' } }, 'Change'),
        h('th', { style: { textAlign: 'right' } }, 'Balance'))),
      h('tbody', {}, data.history.map((t) => h('tr', {},
        h('td', {}, ago(t.created_at)),
        h('td', {}, t.reason.replace(/_/g, ' ')),
        h('td', { class: 'num', style: { color: t.delta >= 0
          ? 'var(--green)' : 'var(--brand)' } },
          `${t.delta >= 0 ? '+' : ''}${commas(t.delta)}`),
        h('td', { class: 'num' }, commas(t.balance)))))));
  })();

  (async () => {
    const { blocked } = await Social.blocked();
    clear(blockedBox);
    if (!blocked.length) {
      blockedBox.appendChild(h('div', { class: 'muted small' },
        'You have not blocked anyone.'));
      return;
    }
    blocked.forEach((b) => blockedBox.appendChild(h('div', { class: 'row' },
      h('span', { style: { flex: 1 } }, b.username),
      h('button', { class: 'btn ghost sm', onClick: async (e) => {
        await Social.block(b.username, true);
        e.target.closest('.row').remove();
        toast('Unblocked', b.username);
      } }, 'Unblock'))));
  })();

  return () => {};
}
