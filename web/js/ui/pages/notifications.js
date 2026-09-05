// Notification inbox.

import { h, clear, ago } from '../dom.js';
import { Social } from '../api.js';
import { getState, setState } from '../store.js';
import { navigate } from '../router.js';
import { panel, emptyState, spinnerBlock } from '../components.js';

export async function render(root) {
  const me = getState().user;
  if (!me) { navigate('/login'); return () => {}; }
  document.title = 'Notifications — RBLXX';
  const page = h('div', { class: 'page' });
  clear(root).appendChild(page);
  page.appendChild(spinnerBlock('Loading…'));

  const { notifications } = await Social.notifications();
  await Social.readNotifications();
  setState({ unread: { ...getState().unread, notifications: 0 } });
  clear(page);

  const ICONS = {
    friend_request: '👥', friend_accepted: '🤝', new_follower: '👀',
    post_like: '♥', post_comment: '💬', message: '✉', badge: '🎖',
    stipend: '🪙', purchase: '🛍',
  };

  page.append(
    h('div', { class: 'page-head' }, h('h1', {}, 'Notifications')),
    panel('Recent activity',
      notifications.length
        ? h('div', {}, notifications.map((n) => h('div', {
            class: 'row',
            style: { padding: '9px 4px', borderBottom: '1px solid var(--line-soft)',
                     cursor: n.fromId ? 'pointer' : 'default',
                     background: n.read ? '' : 'rgba(20,120,208,.06)' },
            onClick: () => { if (n.fromId) navigate(`/profile/${n.fromId}`); },
          },
            h('span', { style: { fontSize: '17px', width: '26px' } },
              ICONS[n.kind] || '•'),
            h('span', { style: { flex: 1 } }, n.text),
            h('span', { class: 'tiny faint' }, ago(n.createdAt)))))
        : emptyState('🔔', 'Nothing new', 'Notifications will show up here.'),
      { bodyClass: 'flush' }));
  return () => {};
}
