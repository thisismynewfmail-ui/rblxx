// World Browser — search, sort, filter and jump into any experience.

import { h, clear, debounce, fmt, commas } from '../dom.js';
import { Worlds } from '../api.js';
import { getState } from '../store.js';
import { navigate } from '../router.js';
import { gameCard, panel, emptyState, skeletonGrid, tabs } from '../components.js';

const SORTS = [
  { id: 'featured', label: 'Featured' },
  { id: 'popular', label: 'Most Playing' },
  { id: 'visits', label: 'Most Visited' },
  { id: 'rating', label: 'Top Rated' },
  { id: 'name', label: 'A → Z' },
];

export async function render(root, params, query) {
  document.title = 'World Browser — RBLXX';
  let sort = query.get('sort') || 'featured';
  let genre = query.get('genre') || 'all';
  let search = query.get('q') || '';

  const page = h('div', { class: 'page' });
  const results = h('div', { class: 'card-grid' });
  const meta = h('div', { class: 'muted small' });
  clear(root).appendChild(page);

  const searchInput = h('input', {
    class: 'field', style: { maxWidth: '260px' }, value: search,
    placeholder: 'Search worlds…',
    onInput: debounce((e) => { search = e.target.value; load(); }, 250),
  });

  const sortSelect = h('select', {
    class: 'field', style: { maxWidth: '170px' },
    onChange: (e) => { sort = e.target.value; load(); },
  }, SORTS.map((s) => h('option', { value: s.id,
    selected: s.id === sort ? true : null }, s.label)));

  const genreRow = h('div', { class: 'tabs' });

  page.append(
    h('div', { class: 'page-head' },
      h('h1', {}, 'World Browser'),
      h('span', { class: 'sub' }, 'Five hand-built experiences. Pick one and press Load.'),
      h('span', { style: { flex: 1 } }),
      meta),
    h('div', { class: 'panel' },
      h('div', { class: 'cat-toolbar' },
        searchInput, sortSelect,
        h('span', { style: { flex: 1 } }),
        h('button', { class: 'btn ghost sm', onClick: () => {
          search = ''; sort = 'featured'; genre = 'all';
          searchInput.value = ''; sortSelect.value = 'featured'; load();
        } }, 'Reset')),
      h('div', { class: 'panel-body' }, genreRow, results)));

  async function load() {
    results.replaceChildren(...skeletonGrid(5, '180px').children);
    const data = await Worlds.list({ sort, genre, q: search });
    const worlds = data.worlds || [];
    meta.textContent = `${commas(data.totalPlaying || 0)} players in game right now`;

    const genres = ['all', ...(data.genres || [])];
    clear(genreRow);
    genres.forEach((g) => genreRow.appendChild(h('div', {
      class: 'tab' + (g === genre ? ' active' : ''),
      onClick: () => { genre = g; load(); },
    }, g === 'all' ? 'All genres' : g)));

    clear(results);
    if (!worlds.length) {
      results.appendChild(emptyState('🔍', 'No worlds match that',
        'Try a different search or reset the filters.'));
      return;
    }
    worlds.forEach((w) => results.appendChild(gameCard(w)));

    const url = new URLSearchParams();
    if (sort !== 'featured') url.set('sort', sort);
    if (genre !== 'all') url.set('genre', genre);
    if (search) url.set('q', search);
    const qs = url.toString();
    history.replaceState(null, '', '#/games' + (qs ? '?' + qs : ''));
  }

  await load();
  return () => {};
}
