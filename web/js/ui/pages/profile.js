// Player profile: the 3D character sits top-left, everything else to the right.

import { h, clear, fmt, commas, ago, date, duration } from '../dom.js';
import { Users, Social, Worlds } from '../api.js';
import { getState } from '../store.js';
import { navigate } from '../router.js';
import { panel, toast, emptyState, spinnerBlock, statStrip, playerTile,
         badgeDisc, itemCard, modal, confirmDialog, gameCard } from '../components.js';
import { AvatarPreview } from '../preview3d.js';
import { drawAvatar } from '../iso.js';

export async function render(root, params) {
  const page = h('div', { class: 'page' });
  clear(root).appendChild(page);
  page.appendChild(spinnerBlock('Loading profile…'));

  let data;
  try {
    data = await Users.profile(params.name);
  } catch {
    clear(page).appendChild(emptyState('👤', 'Player not found',
      'That profile does not exist.',
      h('a', { class: 'btn', href: '#/home' }, 'Go home')));
    return () => {};
  }

  const me = getState().user;
  const u = data.user;
  const isSelf = me && me.id === u.id;
  document.title = `${u.username} — RBLXX`;
  clear(page);

  let preview = null;
  const canvas = h('canvas', { style: { width: '100%', height: '100%' } });
  const viewport = h('div', { class: 'viewport', style: { height: '330px' } },
    canvas,
    h('div', { class: 'vp-badge' }, '3D'),
    h('div', { class: 'vp-hint' }, 'drag to rotate · scroll to zoom'));

  requestAnimationFrame(() => {
    preview = new AvatarPreview(canvas, {
      bundle: data.render, dist: 12.5, spin: true, pose: 'idle',
    });
  });

  const poseBtn = h('button', { class: 'btn ghost sm', onClick: () => {
    const next = preview.pose === 'idle' ? 'walk'
      : preview.pose === 'walk' ? 'hold' : 'idle';
    preview.setPose(next);
    poseBtn.textContent = `Pose: ${next}`;
  } }, 'Pose: idle');

  // ---------------------------------------------------------- left column
  const leftCol = h('div', { class: 'col' },
    h('div', { class: 'panel avatar-card' },
      h('div', { class: 'panel-head' }, 'Character',
        h('span', { style: { flex: 1 } }),
        h('span', { class: 'small' }, u.online ? 'Online' : 'Offline')),
      viewport,
      h('div', { class: 'panel-body tight row' },
        poseBtn,
        h('button', { class: 'btn ghost sm', onClick: () => {
          preview.spin = !preview.spin;
        } }, 'Toggle spin'),
        h('span', { style: { flex: 1 } }),
        h('a', { class: 'btn sm',
          href: `#/inventory/${u.username}` }, 'View Inventory')),
      statStrip([
        ['Friends', data.counts.friends],
        ['Followers', data.counts.followers],
        ['Items', data.counts.items],
        ['Posts', data.counts.posts],
      ])),
    panel('Statistics', h('div', { class: 'col small' },
      statRow('Eliminations', commas(data.stats.kills || 0)),
      statRow('Deaths', commas(data.stats.deaths || 0)),
      statRow('K/D ratio', ((data.stats.kills || 0)
        / Math.max(1, data.stats.deaths || 0)).toFixed(2)),
      statRow('Best streak', data.stats.best_streak || 0),
      statRow('Rounds played', commas(data.stats.rounds || 0)),
      statRow('Headshots', commas(data.stats.headshots || 0)),
      statRow('Time in game', duration(data.stats.playtime || 0)),
      statRow('Place visits', commas(u.placeVisits || 0)),
      statRow('Joined', date(u.createdAt)),
      statRow('Last seen', u.online ? 'Currently online' : ago(u.lastSeen)))));

  // --------------------------------------------------------- right column
  const rel = data.relationship || {};
  const actions = h('div', { class: 'row wrap' });

  if (isSelf) {
    actions.append(
      h('a', { class: 'btn', href: '#/avatar' }, '✎ Edit avatar'),
      h('a', { class: 'btn ghost', href: '#/inventory' }, 'Inventory'),
      h('a', { class: 'btn ghost', href: '#/settings' }, 'Settings'));
  } else if (me) {
    const friendBtn = h('button', { class: 'btn' },
      rel.friend ? '✓ Friends' : rel.requestSent ? 'Request sent'
        : rel.requestReceived ? 'Accept request' : '+ Add friend');
    friendBtn.onclick = async () => {
      friendBtn.disabled = true;
      try {
        if (rel.friend) {
          if (await confirmDialog('Remove friend',
            `Remove ${u.username} from your friends?`, 'Remove')) {
            await Social.remove(u.username);
            toast('Friend removed', u.username);
            navigate(`/profile/${u.username}`); location.reload();
          }
        } else if (rel.requestReceived) {
          await Social.accept(u.username);
          toast('You are now friends!', u.username, 'good');
          friendBtn.textContent = '✓ Friends';
        } else if (rel.requestSent) {
          await Social.cancel(u.username);
          friendBtn.textContent = '+ Add friend';
          rel.requestSent = false;
        } else {
          await Social.request(u.username);
          toast('Friend request sent', u.username, 'good');
          friendBtn.textContent = 'Request sent';
          rel.requestSent = true;
        }
      } catch (e) { toast('Could not do that', e.message, 'bad'); }
      friendBtn.disabled = false;
    };

    const followBtn = h('button', { class: 'btn ghost' },
      rel.following ? '✓ Following' : '+ Follow');
    followBtn.onclick = async () => {
      const res = await Social.follow(u.username);
      followBtn.textContent = res.following ? '✓ Following' : '+ Follow';
      toast(res.following ? `Following ${u.username}`
        : `Unfollowed ${u.username}`, '', res.following ? 'good' : '');
    };

    actions.append(friendBtn, followBtn,
      h('button', { class: 'btn ghost', onClick: () => messageDialog(u) },
        '✉ Message'),
      h('a', { class: 'btn ghost', href: `#/inventory/${u.username}` },
        'Inventory'),
      h('button', {
        class: 'btn ghost', title: 'Block this player',
        onClick: async () => {
          if (await confirmDialog('Block player',
            `Block ${u.username}? This removes the friendship and hides their posts.`,
            'Block')) {
            await Social.block(u.username);
            toast('Player blocked', u.username);
          }
        },
      }, '⃠'));
  } else {
    actions.append(h('a', { class: 'btn', href: '#/login' },
      'Sign in to interact'));
  }

  const header = h('div', { class: 'panel' },
    h('div', { class: 'panel-body' },
      h('div', { class: 'row', style: { alignItems: 'flex-start' } },
        h('div', { style: { flex: 1 } },
          h('h1', { class: 'profile-name' }, `${u.username}'s Profile`),
          h('div', { class: 'profile-handle' },
            `@${u.username}`,
            u.isAdmin ? h('span', { class: 'chip red',
                                    style: { marginLeft: '6px' } }, 'Staff') : null,
            h('span', { class: 'chip', style: { marginLeft: '6px' } },
              u.online ? 'Online' : `Last seen ${ago(u.lastSeen)}`)),
          u.status ? h('div', { class: 'chip blue',
                                style: { marginTop: '8px' } }, u.status) : null),
        h('div', {}, actions)),
      u.bio
        ? h('p', { style: { whiteSpace: 'pre-wrap', marginTop: '10px',
                            marginBottom: '0' } }, u.bio)
        : h('p', { class: 'muted', style: { marginBottom: 0 } },
            isSelf ? 'You have not written a bio yet — add one in Settings.'
              : 'This player has not written a bio.')));

  const rightCol = h('div', { class: 'col' }, header);

  // recent worlds
  if ((data.recentWorlds || []).length) {
    rightCol.appendChild(panel('Active Places',
      h('div', { class: 'col' }, data.recentWorlds.map((w) =>
        h('div', {
          class: 'row',
          style: { padding: '6px 0', borderBottom: '1px solid var(--line-soft)',
                   cursor: 'pointer' },
          onClick: () => navigate(`/game/${w.world_id}`),
        },
          h('span', { style: { color: 'var(--green)' } }, '▶'),
          h('span', { class: 'bold' }, w.name),
          h('span', { style: { flex: 1 } }),
          h('span', { class: 'small muted' },
            `${w.sessions} sessions · ${commas(w.kills || 0)} elims · ${ago(w.last_played)}`))))));
  }

  // friends
  const friendsPanel = panel(`Friends (${data.counts.friends})`,
    spinnerBlock('Loading friends…'), {
      action: h('a', { href: `#/friends/${u.username}` }, 'See All'),
    });
  rightCol.appendChild(friendsPanel);
  (async () => {
    try {
      const { friends } = await Users.friends(u.username);
      const body = friends.length
        ? h('div', { class: 'friend-grid' },
            friends.slice(0, 10).map((f) => playerTile(f)))
        : emptyState('🙂', 'No friends yet',
            isSelf ? 'Find people in the World Browser or the leaderboard.' : '');
      friendsPanel.querySelector('.panel-body').replaceChildren(body);
    } catch { /* ignore */ }
  })();

  // badges
  rightCol.appendChild(panel(`Badges (${(data.badges || []).length})`,
    (data.badges || []).length
      ? h('div', { class: 'badge-wall' }, data.badges.map((b) => badgeDisc(b)))
      : emptyState('🎖', 'No badges yet', 'Badges unlock as you play.')));

  // posts
  const postsPanel = panel('Posts', spinnerBlock('Loading posts…'),
    { bodyClass: 'flush' });
  rightCol.appendChild(postsPanel);
  (async () => {
    try {
      const { posts } = await Users.posts(u.username);
      const body = posts.length
        ? h('div', {}, posts.map((p) => postRow(p, me, data.render)))
        : emptyState('💬', 'No posts yet',
            isSelf ? 'Share what you have been building.' : '');
      postsPanel.querySelector('.panel-body').replaceChildren(body);
    } catch { /* ignore */ }
  })();

  page.appendChild(h('div', { class: 'profile-top' }, leftCol, rightCol));
  return () => preview?.dispose();
}

function statRow(label, value) {
  return h('div', {
    class: 'row',
    style: { justifyContent: 'space-between',
             borderBottom: '1px solid var(--line-soft)', padding: '3px 0' },
  }, h('span', { class: 'muted' }, label), h('span', { class: 'bold' }, String(value)));
}

function postRow(post, me, render) {
  const canvas = h('canvas', { style: { width: '100%', height: '100%' } });
  requestAnimationFrame(() => {
    if (canvas.isConnected) drawAvatar(canvas, render, { scale: 0.9, shadow: false });
  });
  const likeBtn = h('button', { class: post.liked ? 'liked' : '' },
    `♥ ${post.like_count}`);
  likeBtn.onclick = async () => {
    if (!me) return navigate('/login');
    const res = await (await import('../api.js')).Social.like(post.id);
    likeBtn.textContent = `♥ ${res.likeCount}`;
    likeBtn.classList.toggle('liked', res.liked);
  };
  return h('div', { class: 'post' },
    h('div', { class: 'pav' }, canvas),
    h('div', { class: 'pbody' },
      h('div', { class: 'pmeta' },
        h('a', { class: 'who', href: `#/profile/${post.username}` }, post.username),
        h('span', { class: 'faint tiny' }, ago(post.created_at)),
        post.world_name ? h('span', { class: 'chip blue' }, post.world_name) : null),
      h('div', { class: 'ptext' }, post.body),
      h('div', { class: 'pacts' }, likeBtn,
        h('button', {}, `💬 ${post.reply_count}`))));
}

function messageDialog(user) {
  const subject = h('input', { class: 'field', maxlength: 90,
                               placeholder: 'Subject' });
  const body = h('textarea', { class: 'field', maxlength: 2000,
                               style: { minHeight: '130px' },
                               placeholder: `Write to ${user.username}…` });
  const m = modal(`Message ${user.username}`,
    h('div', { class: 'col' },
      h('div', {}, h('label', { class: 'lbl' }, 'Subject'), subject),
      h('div', {}, h('label', { class: 'lbl' }, 'Message'), body)),
    [h('button', { class: 'btn ghost', onClick: () => m.close() }, 'Cancel'),
     h('button', { class: 'btn', onClick: async () => {
       try {
         await Social.sendMessage(user.username, subject.value, body.value);
         toast('Message sent', `to ${user.username}`, 'good');
         m.close();
       } catch (e) { toast('Could not send', e.message, 'bad'); }
     } }, 'Send')]);
  setTimeout(() => subject.focus(), 60);
}
