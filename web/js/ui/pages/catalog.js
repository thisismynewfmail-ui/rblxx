// Catalog: the central item database, browsable and buyable.

import { h, clear, commas, debounce, date } from '../dom.js';
import { Catalog, Avatar } from '../api.js';
import { getState, setState } from '../store.js';
import { navigate } from '../router.js';
import { panel, toast, emptyState, itemCard, modal, skeletonGrid } from '../components.js';
import { drawItem } from '../iso.js';

const SORTS = [
  ['featured', 'Featured'], ['newest', 'Newest'], ['price_asc', 'Price ↑'],
  ['price_desc', 'Price ↓'], ['rarity', 'Rarity'], ['name', 'A → Z'],
];
const RARITIES = ['all', 'common', 'uncommon', 'rare', 'epic', 'legendary'];

export async function render(root, params, query) {
  document.title = 'Catalog — RBLXX';
  let category = query.get('category') || 'all';
  let sort = query.get('sort') || 'featured';
  let rarity = query.get('rarity') || 'all';
  let search = query.get('q') || '';
  const openItem = query.get('item');

  const page = h('div', { class: 'page' });
  const grid = h('div', { class: 'item-grid' });
  const countLabel = h('span', { class: 'muted small' });
  const balanceLabel = h('span', { class: 'currency' },
    h('i', { class: 'coin' }), '—');
  clear(root).appendChild(page);

  const searchInput = h('input', {
    class: 'field', style: { maxWidth: '220px' }, value: search,
    placeholder: 'Search the catalog…',
    onInput: debounce((e) => { search = e.target.value; load(); }, 250),
  });
  const catTabs = h('div', { class: 'tabs' });
  const sortSel = h('select', { class: 'field', style: { maxWidth: '150px' },
    onChange: (e) => { sort = e.target.value; load(); } },
    SORTS.map(([id, label]) => h('option', { value: id,
      selected: id === sort ? true : null }, label)));
  const raritySel = h('select', { class: 'field', style: { maxWidth: '140px' },
    onChange: (e) => { rarity = e.target.value; load(); } },
    RARITIES.map((r) => h('option', { value: r,
      selected: r === rarity ? true : null },
      r === 'all' ? 'Any rarity' : r[0].toUpperCase() + r.slice(1))));

  page.append(
    h('div', { class: 'page-head' },
      h('h1', {}, 'Catalog'),
      h('span', { class: 'sub' }, 'Every item on RBLXX, in one place.'),
      h('span', { style: { flex: 1 } }),
      balanceLabel),
    h('div', { class: 'panel' },
      h('div', { class: 'cat-toolbar' },
        searchInput, sortSel, raritySel,
        h('span', { style: { flex: 1 } }), countLabel),
      h('div', { class: 'panel-body' }, catTabs, grid)));

  async function load() {
    grid.replaceChildren(...skeletonGrid(12, '150px').children);
    const data = await Catalog.list({ category, sort, rarity, q: search,
                                      limit: 200 });
    balanceLabel.replaceChildren(h('i', { class: 'coin' }),
      commas(data.balance || 0));
    countLabel.textContent = `${data.total} items`;

    clear(catTabs);
    const cats = [{ id: 'all', label: 'All' }, ...(data.categories || [])];
    for (const c of cats) {
      catTabs.appendChild(h('div', {
        class: 'tab' + (c.id === category ? ' active' : ''),
        onClick: () => { category = c.id; load(); },
      }, c.label));
    }

    clear(grid);
    if (!data.items.length) {
      grid.appendChild(emptyState('🔍', 'Nothing matches',
        'Try a different search or clear the filters.'));
      return;
    }
    for (const item of data.items) {
      grid.appendChild(itemCard(item, { onClick: () => openDetail(item) }));
    }

    const qs = new URLSearchParams();
    if (category !== 'all') qs.set('category', category);
    if (sort !== 'featured') qs.set('sort', sort);
    if (rarity !== 'all') qs.set('rarity', rarity);
    if (search) qs.set('q', search);
    const s = qs.toString();
    history.replaceState(null, '', '#/catalog' + (s ? '?' + s : ''));
  }

  async function openDetail(itemStub) {
    const { item } = await Catalog.item(itemStub.id);
    const canvas = h('canvas', { style: { width: '100%', height: '190px' } });
    const buyBtn = h('button', { class: 'btn green lg' },
      item.owned ? 'Owned' : item.price > 0
        ? `Buy for ${commas(item.price)} Bux` : 'Get for free');
    if (item.owned) buyBtn.disabled = true;
    if (item.remaining === 0 && !item.owned) {
      buyBtn.disabled = true;
      buyBtn.textContent = 'Sold out';
    }

    const wearBtn = h('button', { class: 'btn ghost lg' }, 'Wear it now');
    wearBtn.style.display = item.owned ? '' : 'none';
    wearBtn.onclick = async () => {
      try {
        const res = await Avatar.equip(item.id);
        setState({ render: res.render });
        toast('Equipped', item.name, 'good');
        m.close();
      } catch (e) { toast('Could not equip', e.message, 'bad'); }
    };

    buyBtn.onclick = async () => {
      if (!getState().user) return navigate('/login');
      buyBtn.disabled = true;
      buyBtn.textContent = 'Purchasing…';
      try {
        const res = await Catalog.buy(item.id);
        toast('Purchased!', `${item.name}${res.serial ? ` · serial #${res.serial}` : ''}`,
              'gold');
        setState({ user: { ...getState().user, coins: res.balance } });
        buyBtn.textContent = 'Owned';
        wearBtn.style.display = '';
        load();
      } catch (e) {
        toast('Purchase failed', e.message, 'bad');
        buyBtn.disabled = false;
        buyBtn.textContent = `Buy for ${commas(item.price)} Bux`;
      }
    };

    const m = modal(item.name, h('div', { class: 'grid two' },
      h('div', {
        style: { background: 'var(--panel-2)', borderRadius: '4px',
                 border: '1px solid var(--line-soft)' },
      }, canvas),
      h('div', { class: 'col' },
        h('div', { class: 'row wrap' },
          h('span', { class: 'chip', style: { background: item.rarityColor,
                                              color: '#fff',
                                              borderColor: item.rarityColor } },
            item.rarity),
          h('span', { class: 'chip' }, item.category),
          item.limited ? h('span', { class: 'chip gold' }, 'Limited') : null),
        h('p', {}, item.description),
        h('div', { class: 'small muted' }, `Creator: ${item.creator}`),
        h('div', { class: 'small muted' },
          `Owned by ${commas(item.ownerCount || 0)} players`),
        item.stock != null
          ? h('div', { class: 'small', style: { color: 'var(--gold)' } },
              `${commas(item.remaining)} of ${commas(item.stock)} remaining`)
          : null,
        h('div', { class: 'row' }, buyBtn, wearBtn))), []);
    requestAnimationFrame(() => drawItem(canvas, item));
  }

  await load();
  if (openItem) {
    const stub = { id: openItem };
    openDetail(stub).catch(() => {});
  }
  return () => {};
}
