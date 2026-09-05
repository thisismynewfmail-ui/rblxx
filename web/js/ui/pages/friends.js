// Friends: your list, incoming and outgoing requests, and suggestions.

import { h, clear, ago, debounce } from '../dom.js';
import { Social, Users } from '../api.js';
import { getState } from '../store.js';
import { navigate } from '../router.js';
import { panel, toast, emptyState, playerTile, spinnerBlock, tabs,
         confirmDialog } from '../components.js';

export async function render(root, params) {
  const me = getState().user;
  if (params.name) return renderOther(root, params.name);
  if (!me) { navigate('/login'); return () => {}; }

  document.title = 'Friends — RBLXX';
  const page = h('div', { class: 'page' });
  clear(root).appendChild(page);
  page.appendChild(spinnerBlock('Loading your circle…'));

  async function load() {
    const data = await Social.friends();
    clear(page);

    const search = h('input', { class: 'field', style: { maxWidth: '240px' },
      placeholder: 'Find players by username…' });
    const searchOut = h('div', { class: 'friend-grid' });
    search.addEventListener('input', debounce(async (e) => {
      const q = e.target.value.trim();
      clear(searchOut);
      if (q.length < 2) return;
      const res = await Users.search(q);
      if (!res.users.length) {
        searchOut.appendChild(h('div', { class: 'muted small' }, 'No matches.'));
        return;
      }
      res.users.forEach((u) => searchOut.appendChild(playerTile(u)));
    }, 260));

    page.append(
      h('div', { class: 'page-head' },
        h('h1', {}, 'Friends'),
        h('span', { class: 'sub' },
          `${data.friends.length} friends · ${data.incoming.length} pending`)),
      h('div', { class: 'grid sidebar-right' },
        h('div', { class: 'col' },
          panel(`Your friends (${data.friends.length})`,
            data.friends.length
              ? h('div', { class: 'friend-grid' },
                  data.friends.map((f) => friendTile(f, load)))
              : emptyState('🙂', 'No friends yet',
                  'Search for players below or meet people in game.')),
          panel('Find players', h('div', { class: 'col' }, search, searchOut))),
        h('div', { class: 'col' },
          panel(`Requests (${data.incoming.length})`,
            data.incoming.length
              ? h('div', { class: 'col' }, data.incoming.map((r) =>
                  h('div', { class: 'row' },
                    h('a', { class: 'bold', style: { flex: 1 },
                             href: `#/profile/${r.username}` }, r.username),
                    h('button', { class: 'btn sm green', onClick: async () => {
                      await Social.accept(r.username);
                      toast('You are now friends', r.username, 'good');
                      load();
                    } }, 'Accept'),
                    h('button', { class: 'btn sm ghost', onClick: async () => {
                      await Social.decline(r.username);
                      load();
                    } }, 'Decline'))))
              : h('div', { class: 'muted small' }, 'No pending requests.')),
          panel(`Sent (${data.outgoing.length})`,
            data.outgoing.length
              ? h('div', { class: 'col' }, data.outgoing.map((r) =>
                  h('div', { class: 'row' },
                    h('a', { style: { flex: 1 },
                             href: `#/profile/${r.username}` }, r.username),
                    h('button', { class: 'btn sm ghost', onClick: async () => {
                      await Social.cancel(r.username);
                      load();
                    } }, 'Cancel'))))
              : h('div', { class: 'muted small' }, 'Nothing sent.')),
          panel('People you may know',
            data.suggestions.length
              ? h('div', { class: 'col' }, data.suggestions.map((s) =>
                  h('div', { class: 'row' },
                    h('a', { style: { flex: 1 },
                             href: `#/profile/${s.username}` }, s.username),
                    s.mutual ? h('span', { class: 'chip' },
                      `${s.mutual} mutual`) : null,
                    h('button', { class: 'btn sm', onClick: async (e) => {
                      await Social.request(s.username);
                      e.target.textContent = 'Sent';
                      e.target.disabled = true;
                    } }, 'Add'))))
              : h('div', { class: 'muted small' },
                  'No suggestions right now.')))));
  }

  await load();
  return () => {};
}

function friendTile(f, reload) {
  const tile = playerTile(f);
  tile.appendChild(h('button', {
    class: 'btn ghost sm', style: { marginTop: '4px', width: '100%' },
    onClick: async (e) => {
      e.stopPropagation();
      if (!await confirmDialog('Remove friend',
        `Remove ${f.username} from your friends?`, 'Remove')) return;
      await Social.remove(f.username);
      toast('Friend removed', f.username);
      reload();
    },
  }, 'Remove'));
  return tile;
}

async function renderOther(root, name) {
  document.title = `${name}'s friends — RBLXX`;
  const page = h('div', { class: 'page' });
  clear(root).appendChild(page);
  page.appendChild(spinnerBlock('Loading…'));
  const [{ friends }, follow] = await Promise.all([
    Users.friends(name), Users.followers(name).catch(() => ({ followers: [], following: [] })),
  ]);
  clear(page);
  page.append(
    h('div', { class: 'page-head' },
      h('h1', {}, `${name}'s friends`),
      h('span', { style: { flex: 1 } }),
      h('a', { class: 'btn ghost', href: `#/profile/${name}` }, 'Back to profile')),
    panel(`Friends (${friends.length})`,
      friends.length
        ? h('div', { class: 'friend-grid' }, friends.map((f) => playerTile(f)))
        : emptyState('🙂', 'No friends yet', '')),
    panel(`Followers (${follow.followers.length})`,
      follow.followers.length
        ? h('div', { class: 'friend-grid' },
            follow.followers.map((f) => playerTile(f)))
        : emptyState('👀', 'No followers yet', '')),
    panel(`Following (${follow.following.length})`,
      follow.following.length
        ? h('div', { class: 'friend-grid' },
            follow.following.map((f) => playerTile(f)))
        : emptyState('👣', 'Not following anyone', '')));
  return () => {};
}
