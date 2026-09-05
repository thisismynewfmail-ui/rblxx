// Sign in / create account — the front door.

import { h, clear } from '../dom.js';
import { Auth } from '../api.js';
import { setState } from '../store.js';
import { navigate } from '../router.js';
import { toast } from '../components.js';
import { AvatarPreview } from '../preview3d.js';

const RANDOM_COLORS = [
  ['#f3d64e', '#1c7bc4', '#8bc34a'], ['#f7c6a3', '#c0392b', '#2c3e50'],
  ['#bfe6cf', '#8a6bd8', '#4a3f6b'], ['#e8b93d', '#111418', '#f2c53d'],
  ['#a3714a', '#3f9d47', '#5d4037'], ['#ffd1dc', '#ff8fb1', '#7f5fbf'],
];

export function render(root, params, query) {
  document.title = 'Sign in — RBLXX';
  const next = query.get('next') || '/home';
  let mode = query.get('mode') === 'signup' ? 'signup' : 'login';
  let preview = null;

  const canvas = h('canvas', { style: { width: '100%', height: '100%' } });
  const shell = h('div', { class: 'auth-wrap' },
    h('div', { class: 'auth-hero' }),
    h('div', { class: 'auth-stage' }, canvas,
      h('div', { class: 'auth-stage-cap' },
        'Every account starts with a blank blockhead. Make it yours.')),
    h('div', { class: 'auth-card panel' }));
  clear(root).appendChild(shell);

  const card = shell.querySelector('.auth-card');
  const seed = RANDOM_COLORS[(Math.random() * RANDOM_COLORS.length) | 0];

  requestAnimationFrame(() => {
    preview = new AvatarPreview(canvas, {
      bundle: {
        colors: { head: seed[0], torso: seed[1], left_arm: seed[0],
                  right_arm: seed[0], left_leg: seed[2], right_leg: seed[2] },
        face: 'smile',
      },
      sky: 'dawn', stage: true, dist: 15, fov: 34, focus: 2.7,
      spin: true, pitch: 0.12,
    });
  });

  function draw() {
    clear(card);
    card.appendChild(h('div', {
      class: 'panel-head',
      style: { justifyContent: 'center', fontSize: '17px' },
    }, mode === 'login' ? 'Sign in to RBLXX' : 'Create your account'));

    card.appendChild(h('div', { class: 'auth-tabs' },
      h('button', { class: mode === 'login' ? 'active' : '',
                    onClick: () => { mode = 'login'; draw(); } }, 'Sign in'),
      h('button', { class: mode === 'signup' ? 'active' : '',
                    onClick: () => { mode = 'signup'; draw(); } }, 'Create account')));

    const username = h('input', { class: 'field', autocomplete: 'username',
                                  maxlength: 20, placeholder: 'BlockBuilder99' });
    const password = h('input', { class: 'field', type: 'password',
      autocomplete: mode === 'login' ? 'current-password' : 'new-password',
      placeholder: '••••••••' });
    const bio = h('textarea', { class: 'field', maxlength: 280,
                                placeholder: 'Say hello to the neighbourhood…' });
    const err = h('div', { class: 'small', style: { color: 'var(--brand)',
                                                    minHeight: '16px' } });
    const submit = h('button', { class: 'btn lg block', type: 'submit' },
      mode === 'login' ? 'Sign in' : 'Create account and play');

    const form = h('form', { class: 'panel-body' },
      h('div', { class: 'form-row' },
        h('label', { class: 'lbl' }, 'Username'), username),
      h('div', { class: 'form-row' },
        h('label', { class: 'lbl' }, 'Password'), password),
      mode === 'signup'
        ? h('div', { class: 'form-row' },
            h('label', { class: 'lbl' }, 'About you (optional)'), bio)
        : null,
      err,
      submit,
      h('div', { class: 'small muted', style: { marginTop: '12px',
                                                textAlign: 'center' } },
        mode === 'login'
          ? 'New here? Create an account — it takes five seconds.'
          : `You start with 1,500 Bux and a full starter outfit.`));

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      err.textContent = '';
      submit.disabled = true;
      submit.textContent = mode === 'login' ? 'Signing in…' : 'Creating…';
      try {
        const res = mode === 'login'
          ? await Auth.login(username.value.trim(), password.value)
          : await Auth.signup(username.value.trim(), password.value,
                              bio.value.trim());
        setState({ user: res.user });
        toast(mode === 'login' ? `Welcome back, ${res.user.username}!`
          : `Welcome to RBLXX, ${res.user.username}!`,
          mode === 'login' ? '' : 'Your starter items are in your inventory.',
          'good');
        const boot = await (await fetch('/api/bootstrap',
          { credentials: 'same-origin' })).json();
        setState({ user: boot.user, render: boot.render,
                   unread: boot.unread || { messages: 0, notifications: 0 },
                   worlds: boot.worlds || [] });
        if (next.startsWith('/play/')) location.href = next;
        else navigate(next);
      } catch (ex) {
        err.textContent = ex.message;
        submit.disabled = false;
        submit.textContent = mode === 'login' ? 'Sign in' : 'Create account and play';
      }
    });

    card.appendChild(form);
    setTimeout(() => username.focus(), 60);
  }

  draw();
  return () => preview?.dispose();
}
