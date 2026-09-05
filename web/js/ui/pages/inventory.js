// Inventory — everything a player owns, grouped by category.

import { h, clear, commas, date, ago } from '../dom.js';
import { Users, Avatar } from '../api.js';
import { getState, setState } from '../store.js';
import { navigate } from '../router.js';
import { panel, toast, emptyState, itemCard, spinnerBlock } from '../components.js';

export async function render(root, params) {
  const me = getState().user;
  const owner = params.name || (me && me.username);
  if (!owner) { navigate('/login'); return () => {}; }

  document.title = `${owner}'s Inventory — RBLXX`;
  const page = h('div', { class: 'page' });
  clear(root).appendChild(page);
  page.appendChild(spinnerBlock('Opening the toy box…'));

  const data = await Users.inventory(owner, 'all');
  clear(page);
  const isSelf = me && me.username.toLowerCase() === owner.toLowerCase();

  let category = 'all';
  const grid = h('div', { class: 'item-grid' });
  const catTabs = h('div', { class: 'tabs' });
  const counts = {};
  for (const item of data.items) {
    counts[item.category] = (counts[item.category] || 0) + 1;
  }

  function paint() {
    clear(catTabs);
    const cats = [{ id: 'all', label: 'Everything', count: data.items.length },
                  ...data.categories.map((c) => ({ ...c,
                    count: counts[c.id] || 0 }))];
    for (const c of cats) {
      catTabs.appendChild(h('div', {
        class: 'tab' + (c.id === category ? ' active' : ''),
        onClick: () => { category = c.id; paint(); },
      }, c.label, h('span', { class: 'chip', style: { marginLeft: '5px' } },
        String(c.count))));
    }
    const items = category === 'all' ? data.items
      : data.items.filter((i) => i.category === category);
    clear(grid);
    if (!items.length) {
      grid.appendChild(emptyState('📦', 'Nothing in this drawer',
        isSelf ? 'Head to the catalog and pick something up.' : '',
        isSelf ? h('a', { class: 'btn', href: '#/catalog' }, 'Open catalog') : null));
      return;
    }
    for (const item of items) {
      grid.appendChild(itemCard(item, {
        owned: true,
        priceLabel: h('span', { class: 'muted tiny' },
          item.serial ? `Serial #${item.serial}` : ago(item.acquiredAt)),
        onClick: async () => {
          if (!isSelf) return navigate(`/catalog?item=${item.id}`);
          try {
            const res = await Avatar.equip(item.id);
            setState({ render: res.render });
            toast('Equipped', item.name, 'good');
          } catch (e) { toast('Could not equip', e.message, 'bad'); }
        },
      }));
    }
  }

  const value = data.items.reduce((sum, i) => sum + (i.price || 0), 0);

  page.append(
    h('div', { class: 'page-head' },
      h('h1', {}, isSelf ? 'My Inventory' : `${data.owner.username}'s Inventory`),
      h('span', { class: 'sub' },
        `${data.items.length} items · collection value ${commas(value)} Bux`),
      h('span', { style: { flex: 1 } }),
      h('a', { class: 'btn ghost', href: `#/profile/${data.owner.username}` },
        'Back to profile'),
      isSelf ? h('a', { class: 'btn', href: '#/avatar' }, 'Edit avatar') : null),
    h('div', { class: 'panel' },
      h('div', { class: 'cat-toolbar' }, catTabs),
      h('div', { class: 'panel-body' }, grid)));

  paint();
  return () => {};
}
