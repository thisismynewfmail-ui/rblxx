// Private messages.

import { h, clear, ago } from '../dom.js';
import { Social, Users } from '../api.js';
import { getState, setState } from '../store.js';
import { navigate } from '../router.js';
import { panel, toast, emptyState, spinnerBlock, modal,
         confirmDialog } from '../components.js';

export async function render(root, params, query) {
  const me = getState().user;
  if (!me) { navigate('/login'); return () => {}; }
  document.title = 'Messages — RBLXX';

  const page = h('div', { class: 'page' });
  clear(root).appendChild(page);
  page.appendChild(spinnerBlock('Opening your mailbox…'));

  let box = 'inbox';
  let data = await Social.messages();
  clear(page);

  const listEl = h('div');
  const readerEl = h('div', { class: 'panel-body' },
    emptyState('✉', 'Nothing selected', 'Pick a message on the left.'));

  function paint() {
    clear(listEl);
    const rows = box === 'inbox' ? data.inbox : data.sent;
    if (!rows.length) {
      listEl.appendChild(emptyState('📭',
        box === 'inbox' ? 'Inbox empty' : 'Nothing sent',
        box === 'inbox' ? 'Messages from other players land here.' : ''));
      return;
    }
    for (const m of rows) {
      const unread = box === 'inbox' && !m.read_at;
      listEl.appendChild(h('div', {
        style: { padding: '9px 12px', cursor: 'pointer',
                 borderBottom: '1px solid var(--line-soft)',
                 background: unread ? 'rgba(20,120,208,.07)' : '' },
        onClick: () => openMessage(m),
      },
        h('div', { class: 'row' },
          h('span', { class: 'bold nowrap', style: { flex: 1 } },
            unread ? '● ' : '',
            box === 'inbox' ? m.from_name : `to ${m.to_name}`),
          h('span', { class: 'tiny faint' }, ago(m.created_at))),
        h('div', { class: 'small nowrap' }, m.subject),
        h('div', { class: 'tiny muted nowrap' }, m.body.slice(0, 70))));
    }
  }

  async function openMessage(m) {
    if (box === 'inbox' && !m.read_at) {
      const res = await Social.readMessage(m.id);
      m.read_at = Date.now() / 1000;
      setState({ unread: { ...getState().unread, messages: res.unread } });
      paint();
    }
    clear(readerEl).append(
      h('div', { class: 'row' },
        h('h3', { style: { flex: 1, margin: 0 } }, m.subject),
        h('span', { class: 'small faint' }, ago(m.created_at))),
      h('div', { class: 'small muted', style: { marginBottom: '10px' } },
        box === 'inbox'
          ? h('span', {}, 'From ',
              h('a', { href: `#/profile/${m.from_name}` }, m.from_name))
          : h('span', {}, 'To ',
              h('a', { href: `#/profile/${m.to_name}` }, m.to_name))),
      h('div', { style: { whiteSpace: 'pre-wrap', lineHeight: '1.7' } }, m.body),
      h('div', { class: 'row', style: { marginTop: '16px' } },
        box === 'inbox'
          ? h('button', { class: 'btn', onClick: () =>
              compose(m.from_name, 'Re: ' + m.subject) }, 'Reply') : null,
        h('button', { class: 'btn ghost', onClick: async () => {
          if (!await confirmDialog('Delete message', 'Delete this message?',
                                   'Delete')) return;
          await Social.deleteMessage(m.id);
          data = await Social.messages();
          paint();
          clear(readerEl).appendChild(emptyState('✉', 'Deleted', ''));
        } }, 'Delete')));
  }

  function compose(to = '', subject = '') {
    const toInput = h('input', { class: 'field', value: to,
                                 placeholder: 'Username' });
    const subjInput = h('input', { class: 'field', value: subject,
                                   maxlength: 90, placeholder: 'Subject' });
    const bodyInput = h('textarea', { class: 'field', maxlength: 2000,
      style: { minHeight: '140px' }, placeholder: 'Your message…' });
    const m = modal('New message', h('div', { class: 'col' },
      h('div', {}, h('label', { class: 'lbl' }, 'To'), toInput),
      h('div', {}, h('label', { class: 'lbl' }, 'Subject'), subjInput),
      h('div', {}, h('label', { class: 'lbl' }, 'Message'), bodyInput)),
      [h('button', { class: 'btn ghost', onClick: () => m.close() }, 'Cancel'),
       h('button', { class: 'btn', onClick: async () => {
         try {
           await Social.sendMessage(toInput.value.trim(), subjInput.value,
                                    bodyInput.value);
           toast('Message sent', `to ${toInput.value}`, 'good');
           m.close();
           data = await Social.messages();
           box = 'sent';
           paint();
         } catch (e) { toast('Could not send', e.message, 'bad'); }
       } }, 'Send')]);
    setTimeout(() => (to ? bodyInput : toInput).focus(), 60);
  }

  const tabsEl = h('div', { class: 'tabs' });
  function paintTabs() {
    clear(tabsEl);
    for (const [id, label, count] of [['inbox', 'Inbox', data.unread],
                                      ['sent', 'Sent', null]]) {
      tabsEl.appendChild(h('div', {
        class: 'tab' + (id === box ? ' active' : ''),
        onClick: () => { box = id; paint(); },
      }, label, count ? h('span', { class: 'chip red',
        style: { marginLeft: '5px' } }, String(count)) : null));
    }
  }

  page.append(
    h('div', { class: 'page-head' },
      h('h1', {}, 'Messages'),
      h('span', { style: { flex: 1 } }),
      h('button', { class: 'btn', onClick: () => compose() }, '✎ New message')),
    h('div', { class: 'grid sidebar-left' },
      h('div', { class: 'panel' },
        h('div', { class: 'cat-toolbar' }, tabsEl),
        listEl),
      h('div', { class: 'panel' },
        h('div', { class: 'panel-head' }, 'Reading'),
        readerEl)));

  paintTabs();
  paint();
  if (query && query.get('to')) compose(query.get('to'));
  return () => {};
}
