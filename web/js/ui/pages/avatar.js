// Avatar Editor: live 3D preview on the left, colours and items on the right.

import { h, clear, commas } from '../dom.js';
import { Avatar, Catalog } from '../api.js';
import { getState, setState } from '../store.js';
import { navigate } from '../router.js';
import { panel, toast, emptyState, spinnerBlock, itemCard, tabs,
         modal, confirmDialog } from '../components.js';
import { AvatarPreview } from '../preview3d.js';

const PART_LABELS = {
  head: 'Head', torso: 'Torso', left_arm: 'Left arm', right_arm: 'Right arm',
  left_leg: 'Left leg', right_leg: 'Right leg',
};
const CATEGORIES = [
  { id: 'hat', label: 'Hats' }, { id: 'face', label: 'Faces' },
  { id: 'shirt', label: 'Shirts' }, { id: 'pants', label: 'Pants' },
  { id: 'back', label: 'Back' }, { id: 'gear', label: 'Gear Skins' },
];

export async function render(root) {
  document.title = 'Avatar Editor — RBLXX';
  const page = h('div', { class: 'page' });
  clear(root).appendChild(page);
  page.appendChild(spinnerBlock('Opening the wardrobe…'));

  const [avatarData, catalogData] = await Promise.all([
    Avatar.get(), Catalog.list({ limit: 200 }),
  ]);
  clear(page);

  let state = avatarData;
  let activePart = 'torso';
  let activeCat = 'hat';
  let preview = null;

  const canvas = h('canvas', { style: { width: '100%', height: '100%' } });
  const viewport = h('div', { class: 'viewport', style: { height: '400px' } },
    canvas, h('div', { class: 'vp-badge' }, '3D'),
    h('div', { class: 'vp-hint' }, 'drag to rotate · scroll to zoom'));

  requestAnimationFrame(() => {
    preview = new AvatarPreview(canvas, {
      bundle: state.render, dist: 12, spin: false, pose: 'idle',
    });
  });

  function refresh(next) {
    state = { ...state, ...next };
    if (preview) preview.setBundle(state.render);
    setState({ render: state.render });
    paintParts();
    paintItems();
    paintEquipped();
  }

  // ------------------------------------------------------------ colours
  const partPicker = h('div', { class: 'part-picker' });
  const swatches = h('div', { class: 'swatch-grid' });
  const customInput = h('input', { type: 'color', class: 'field',
    style: { padding: '2px', height: '32px', width: '58px' } });

  function paintParts() {
    clear(partPicker);
    for (const key of Object.keys(PART_LABELS)) {
      partPicker.appendChild(h('div', {
        class: 'pp' + (key === activePart ? ' active' : ''),
        onClick: () => { activePart = key; paintParts(); },
      }, h('i', { style: { background: state.avatar.colors[key] } }),
        PART_LABELS[key]));
    }
    customInput.value = state.avatar.colors[activePart] || '#ffffff';
    clear(swatches);
    for (const c of state.palette) {
      swatches.appendChild(h('div', {
        class: 'swatch' + (state.avatar.colors[activePart] === c ? ' active' : ''),
        style: { background: c },
        title: c,
        onClick: () => setColor(c),
      }));
    }
  }

  async function setColor(color, part = activePart) {
    const colors = { ...state.avatar.colors, [part]: color };
    const res = await Avatar.colors({ [part]: color });
    refresh({ avatar: res.avatar, render: res.render });
  }

  customInput.addEventListener('change', () => setColor(customInput.value));

  const applyAll = h('button', { class: 'btn ghost sm', onClick: async () => {
    const color = state.avatar.colors[activePart];
    const patch = {};
    for (const k of Object.keys(PART_LABELS)) patch[k] = color;
    const res = await Avatar.colors(patch);
    refresh({ avatar: res.avatar, render: res.render });
    toast('Applied to every body part', color, 'good');
  } }, 'Apply to all parts');

  const randomise = h('button', { class: 'btn ghost sm', onClick: async () => {
    const pick = () => state.palette[(Math.random() * state.palette.length) | 0];
    const skin = pick();
    const patch = { head: skin, left_arm: skin, right_arm: skin,
                    torso: pick(), left_leg: pick(), right_leg: pick() };
    patch.left_leg = patch.right_leg;
    const res = await Avatar.colors(patch);
    refresh({ avatar: res.avatar, render: res.render });
  } }, '🎲 Randomise');

  // ------------------------------------------------------------- items
  const itemGrid = h('div', { class: 'item-grid' });
  const catTabs = h('div', { class: 'tabs' });
  const ownedOnly = h('label', { class: 'row small', style: { gap: '5px' } },
    h('input', { type: 'checkbox', checked: true,
                 onChange: (e) => { onlyOwned = e.target.checked; paintItems(); } }),
    'Owned only');
  let onlyOwned = true;

  function paintItems() {
    clear(catTabs);
    for (const c of CATEGORIES) {
      catTabs.appendChild(h('div', {
        class: 'tab' + (c.id === activeCat ? ' active' : ''),
        onClick: () => { activeCat = c.id; paintItems(); },
      }, c.label));
    }
    const owned = new Set(state.owned);
    const equipped = new Set(Object.values(state.avatar.equipped || {}));
    let items = (catalogData.items || []).filter((i) => i.category === activeCat);
    if (onlyOwned) items = items.filter((i) => owned.has(i.id));
    clear(itemGrid);
    if (!items.length) {
      itemGrid.appendChild(emptyState('👕', 'Nothing here yet',
        onlyOwned ? 'Buy items in the Catalog to wear them.'
          : 'No items in this category.',
        h('a', { class: 'btn', href: '#/catalog' }, 'Open catalog')));
      return;
    }
    for (const item of items) {
      const isOwned = owned.has(item.id);
      const isOn = equipped.has(item.id);
      itemGrid.appendChild(itemCard(item, {
        owned: isOwned,
        equipped: isOn,
        priceLabel: isOn ? h('span', { class: 'bold',
          style: { color: 'var(--green)' } }, 'Wearing')
          : isOwned ? h('span', { class: 'muted' }, 'Owned')
            : h('span', {}, commas(item.price)),
        onClick: async () => {
          if (!isOwned) return navigate(`/catalog?item=${item.id}`);
          try {
            const res = isOn ? await Avatar.unequip(item.id)
              : await Avatar.equip(item.id);
            refresh({ avatar: res.avatar, render: res.render });
          } catch (e) { toast('Could not change that', e.message, 'bad'); }
        },
      }));
    }
  }

  // --------------------------------------------------------- equipped
  const equippedRow = h('div', { class: 'row wrap' });
  function paintEquipped() {
    clear(equippedRow);
    const eq = state.avatar.equipped || {};
    const entries = Object.entries(eq);
    if (!entries.length) {
      equippedRow.appendChild(h('span', { class: 'muted small' },
        'Nothing equipped.'));
      return;
    }
    for (const [slot, itemId] of entries) {
      const item = state.avatar.items[slot];
      equippedRow.appendChild(h('span', {
        class: 'chip blue', style: { cursor: 'pointer' },
        title: 'Click to remove',
        onClick: async () => {
          const res = await Avatar.unequip(slot);
          refresh({ avatar: res.avatar, render: res.render });
        },
      }, `${item ? item.name : itemId} ✕`));
    }
  }

  // --------------------------------------------------------- outfits
  const outfitsBox = h('div', { class: 'col' });
  function paintOutfits() {
    clear(outfitsBox);
    if (!state.outfits.length) {
      outfitsBox.appendChild(h('div', { class: 'muted small' },
        'Save your current look to switch back to it in one click.'));
    }
    for (const o of state.outfits) {
      outfitsBox.appendChild(h('div', { class: 'row' },
        h('span', { class: 'bold', style: { flex: 1 } }, o.name),
        h('button', { class: 'btn sm', onClick: async () => {
          const res = await Avatar.wearOutfit(o.id);
          refresh({ avatar: res.avatar, render: res.render });
          toast('Outfit applied', o.name, 'good');
        } }, 'Wear'),
        h('button', { class: 'btn ghost sm', onClick: async () => {
          if (!await confirmDialog('Delete outfit', `Delete "${o.name}"?`,
                                   'Delete')) return;
          const res = await Avatar.deleteOutfit(o.id);
          state.outfits = res.outfits;
          paintOutfits();
        } }, '✕')));
    }
    outfitsBox.appendChild(h('button', {
      class: 'btn ghost sm', onClick: async () => {
        const name = prompt('Name this outfit', 'My outfit');
        if (!name) return;
        const res = await Avatar.saveOutfit(name);
        state.outfits = res.outfits;
        paintOutfits();
        toast('Outfit saved', name, 'good');
      },
    }, '＋ Save current outfit'));
  }

  const scaleInput = h('input', {
    type: 'range', min: 0.75, max: 1.25, step: 0.01,
    value: state.avatar.bodyScale,
    onChange: async (e) => {
      const res = await Avatar.scale(parseFloat(e.target.value));
      state.avatar = res.avatar;
      state.render = { ...state.render, scale: res.avatar.bodyScale };
      if (preview) preview.setBundle(state.render);
    },
  });

  page.append(
    h('div', { class: 'page-head' },
      h('h1', {}, 'Avatar Editor'),
      h('span', { class: 'sub' },
        'Recolour every limb, stack two hats, and save outfits.'),
      h('span', { style: { flex: 1 } }),
      h('a', { class: 'btn ghost', href: '#/catalog' },
        'Explore the catalog to find more clothes')),
    h('div', { class: 'grid sidebar-left' },
      h('div', { class: 'col' },
        h('div', { class: 'panel' },
          h('div', { class: 'panel-head' }, 'Preview'),
          viewport,
          h('div', { class: 'panel-body tight' },
            h('div', { class: 'row' },
              h('button', { class: 'btn ghost sm',
                onClick: () => { preview.spin = !preview.spin; } }, 'Spin'),
              h('button', { class: 'btn ghost sm', onClick: () => {
                preview.setPose(preview.pose === 'hold' ? 'idle' : 'hold');
              } }, 'Hold pose'),
              h('button', { class: 'btn ghost sm', onClick: () => {
                preview.setPose(preview.pose === 'walk' ? 'idle' : 'walk');
              } }, 'Walk')),
            h('div', { class: 'row', style: { marginTop: '8px' } },
              h('span', { class: 'small muted' }, 'Height'), scaleInput))),
        panel('Body colours', h('div', { class: 'col' },
          partPicker, swatches,
          h('div', { class: 'row' }, customInput, applyAll, randomise))),
        panel('Currently wearing', equippedRow),
        panel('Outfits', outfitsBox)),
      h('div', { class: 'panel' },
        h('div', { class: 'cat-toolbar' }, catTabs,
          h('span', { style: { flex: 1 } }), ownedOnly),
        h('div', { class: 'panel-body' }, itemGrid))));

  paintParts();
  paintItems();
  paintEquipped();
  paintOutfits();
  return () => preview?.dispose();
}
