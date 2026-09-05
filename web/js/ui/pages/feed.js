// The social feed: posts, likes and comments.

import { h, clear, ago } from '../dom.js';
import { Social } from '../api.js';
import { getState } from '../store.js';
import { navigate } from '../router.js';
import { panel, toast, emptyState, spinnerBlock, confirmDialog } from '../components.js';
import { drawAvatar } from '../iso.js';
import { paletteFor } from '../components.js';

export async function render(root) {
  const me = getState().user;
  document.title = 'Feed — RBLXX';
  const page = h('div', { class: 'page' });
  clear(root).appendChild(page);

  let scope = 'friends';
  const list = h('div');
  const scopeTabs = h('div', { class: 'tabs' });

  const worlds = getState().worlds || [];
  const worldSel = h('select', { class: 'field', style: { maxWidth: '190px' } },
    h('option', { value: '' }, 'No world tag'),
    worlds.map((w) => h('option', { value: w.id }, w.name)));
  const textarea = h('textarea', { class: 'field', maxlength: 400,
    placeholder: 'What are you building?' });
  const counter = h('span', { class: 'tiny faint' }, '0 / 400');
  textarea.addEventListener('input', () => {
    counter.textContent = `${textarea.value.length} / 400`;
  });
  const postBtn = h('button', { class: 'btn' }, 'Post');
  postBtn.onclick = async () => {
    const body = textarea.value.trim();
    if (!body) return;
    postBtn.disabled = true;
    try {
      await Social.post(body, worldSel.value || null);
      textarea.value = '';
      counter.textContent = '0 / 400';
      toast('Posted!', '', 'good');
      load();
    } catch (e) { toast('Could not post', e.message, 'bad'); }
    postBtn.disabled = false;
  };

  const composer = me ? h('div', { class: 'composer' },
    textarea,
    h('div', { class: 'crow' }, worldSel, counter,
      h('span', { style: { flex: 1 } }), postBtn)) : null;

  page.append(
    h('div', { class: 'page-head' },
      h('h1', {}, 'Feed'),
      h('span', { class: 'sub' }, 'Posts from friends and people you follow')),
    h('div', { class: 'panel' },
      h('div', { class: 'cat-toolbar' }, scopeTabs),
      composer, list));

  function paintTabs() {
    clear(scopeTabs);
    for (const [id, label] of [['friends', 'Friends & following'],
                               ['everyone', 'Everyone']]) {
      scopeTabs.appendChild(h('div', {
        class: 'tab' + (id === scope ? ' active' : ''),
        onClick: () => { scope = id; load(); },
      }, label));
    }
  }

  async function load() {
    paintTabs();
    list.replaceChildren(spinnerBlock('Loading posts…'));
    const { posts } = await Social.feed(scope);
    clear(list);
    if (!posts.length) {
      list.appendChild(emptyState('💬', 'Quiet in here',
        scope === 'friends'
          ? 'Follow some players or switch to Everyone.'
          : 'Nobody has posted yet — be the first.'));
      return;
    }
    posts.forEach((p) => list.appendChild(postCard(p, me, load)));
  }

  if (!me) {
    list.appendChild(emptyState('🔒', 'Sign in to see the feed',
      'Posts from your friends land here.',
      h('a', { class: 'btn', href: '#/login' }, 'Sign in')));
    paintTabs();
    return () => {};
  }

  await load();
  return () => {};
}

export function postCard(post, me, reload) {
  const canvas = h('canvas', { style: { width: '100%', height: '100%' } });
  requestAnimationFrame(() => {
    if (canvas.isConnected) {
      drawAvatar(canvas, { colors: paletteFor({ id: post.user_id }) },
                 { scale: 0.88, shadow: false });
    }
  });

  const likeBtn = h('button', { class: post.liked ? 'liked' : '' },
    `♥ ${post.like_count}`);
  likeBtn.onclick = async () => {
    if (!me) return navigate('/login');
    const res = await Social.like(post.id);
    likeBtn.textContent = `♥ ${res.likeCount}`;
    likeBtn.classList.toggle('liked', res.liked);
  };

  const commentsBox = h('div', { style: { display: 'none', marginTop: '8px' } });
  let loaded = false;
  const commentBtn = h('button', {}, `💬 ${post.reply_count}`);
  commentBtn.onclick = async () => {
    const open = commentsBox.style.display === 'none';
    commentsBox.style.display = open ? 'block' : 'none';
    if (open && !loaded) {
      loaded = true;
      const { comments } = await Social.comments(post.id);
      clear(commentsBox);
      comments.forEach((c) => commentsBox.appendChild(
        h('div', { class: 'row small',
                   style: { padding: '4px 0',
                            borderTop: '1px solid var(--line-soft)' } },
          h('a', { class: 'bold', href: `#/profile/${c.username}` }, c.username),
          h('span', { style: { flex: 1 } }, c.body),
          h('span', { class: 'faint tiny' }, ago(c.created_at)))));
      if (me) {
        const input = h('input', { class: 'field',
                                   placeholder: 'Write a reply…' });
        input.addEventListener('keydown', async (e) => {
          if (e.key !== 'Enter' || !input.value.trim()) return;
          try {
            await Social.comment(post.id, input.value.trim());
            input.value = '';
            loaded = false;
            commentBtn.click(); commentBtn.click();
          } catch (ex) { toast('Could not reply', ex.message, 'bad'); }
        });
        commentsBox.appendChild(h('div', { style: { marginTop: '6px' } }, input));
      }
    }
  };

  const acts = h('div', { class: 'pacts' }, likeBtn, commentBtn);
  if (post.mine || (me && me.isAdmin)) {
    acts.appendChild(h('button', { onClick: async () => {
      if (!await confirmDialog('Delete post', 'Delete this post?', 'Delete')) return;
      await Social.deletePost(post.id);
      toast('Post deleted');
      reload && reload();
    } }, '🗑 Delete'));
  }

  return h('div', { class: 'post' },
    h('div', { class: 'pav' }, canvas),
    h('div', { class: 'pbody' },
      h('div', { class: 'pmeta' },
        h('a', { class: 'who', href: `#/profile/${post.username}` }, post.username),
        h('span', { class: 'faint tiny' }, ago(post.created_at)),
        post.world_name
          ? h('a', { class: 'chip blue', href: `#/game/${post.world_id}` },
              post.world_name) : null),
      h('div', { class: 'ptext' }, post.body),
      acts, commentsBox));
}
