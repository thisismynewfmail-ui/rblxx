// Turns a level definition into renderer batches, a collision world and the
// gameplay props (pickups, signs, objectives).

import { CollisionWorld } from './physics.js';
import { signTexture } from '../engine/textures.js';
import * as glh from '../engine/gl.js';

const PICKUP_STYLE = {
  health:  { color: '#ff5b6e', shape: 'box', label: '+', spin: 1.6, size: 2.4 },
  armor:   { color: '#8fd8ff', shape: 'cone', label: 'A', spin: 1.2, size: 2.8 },
  ammo:    { color: '#f2c53d', shape: 'box', label: 'â—†', spin: 1.4, size: 2.2 },
  speed:   { color: '#38d0ff', shape: 'cylinder', label: 'S', spin: 2.4, size: 2.2 },
  gravity: { color: '#b58cff', shape: 'cylinder', label: 'G', spin: 2.4, size: 2.2 },
  damage:  { color: '#ff7a2a', shape: 'sphere', label: 'D', spin: 1.8, size: 2.6 },
};

export class GameWorld {
  constructor(renderer, level) {
    this.renderer = renderer;
    this.level = level;
    this.parts = level.parts || [];
    this.collision = new CollisionWorld(this.parts, {
      voidY: level.voidY, gravityScale: level.gravityScale || 1,
    });
    this.hiddenTags = new Set();
    this.pickups = new Map();
    for (const p of level.pickups || []) {
      this.pickups.set(p.id, { def: p, active: true, bob: Math.random() * 6.28 });
    }
    this.lavaY = null;
    this.beacon = null;
    this.flags = {};
    this.time = 0;
    this._buildStatic();
    this._buildSigns();
  }

  _buildStatic() {
    const r = this.renderer;
    r.clearStatic();
    for (const part of this.parts) {
      if (part.x && this.hiddenTags.has(part.x)) continue;
      this._addPart(part);
    }
    r.uploadStatic();
  }

  _addPart(part) {
    const [px, py, pz] = part.p;
    const [sx, sy, sz] = part.s;
    const rot = part.r || [0, 0, 0];
    this.renderer.add('static', part.k || 'box', part.t || 'smooth',
      px, py, pz, sx, sy, sz, part.c || '#a3a2a5', {
        rx: rot[0] * Math.PI / 180, ry: rot[1] * Math.PI / 180,
        rz: rot[2] * Math.PI / 180,
        alpha: part.o != null ? part.o : 1,
        glow: part.g || 0,
      });
  }

  _buildSigns() {
    this.signs = [];
    for (const d of this.level.decor || []) {
      if (d.kind !== 'sign') continue;
      const key = `sign:${d.text}:${d.color}`;
      if (!this.renderer.extraTextures.has(key)) {
        const tex = signTexture(this.renderer.ctx, glh, d.text, d.color);
        this.renderer.registerTexture(key, tex, { transparent: true });
      }
      this.signs.push({ ...d, key });
    }
  }

  setTagVisible(tag, visible) {
    if (visible) this.hiddenTags.delete(tag);
    else this.hiddenTags.add(tag);
    this.collision.setTagEnabled(tag, visible);
    this._buildStatic();
  }

  setPickupActive(id, active) {
    const p = this.pickups.get(id);
    if (p) p.active = active;
  }

  /** Draw everything that animates: pickups, signs, lava, objectives. */
  drawDynamic(dt, hud) {
    this.time += dt;
    const r = this.renderer;
    const t = this.time;

    for (const [, p] of this.pickups) {
      if (!p.active) continue;
      const style = PICKUP_STYLE[p.def.kind] || PICKUP_STYLE.health;
      const [x, y, z] = p.def.p;
      const bob = Math.sin(t * 2 + p.bob) * 0.4;
      r.add('dynamic', style.shape, 'neon', x, y + bob, z,
            style.size, style.size, style.size, style.color,
            { ry: t * style.spin, glow: 0.85, alpha: 0.95 });
      r.add('dynamic', 'cylinder', 'neon', x, y - 1.6, z,
            style.size * 1.9, 0.16, style.size * 1.9, style.color,
            { glow: 1, alpha: 0.30 });
    }

    for (const s of this.signs) {
      const [x, y, z] = s.p;
      const w = (s.size || 6) * 1.7;
      r.add('dynamic', 'quad', s.key, x, y, z, w, w * 0.25, 1, '#ffffff',
            { ry: Math.PI, uvMode: 1, alpha: 0.96, glow: 0.35 });
      r.add('dynamic', 'quad', s.key, x, y, z, w, w * 0.25, 1, '#ffffff',
            { uvMode: 1, alpha: 0.96, glow: 0.35 });
    }

    if (this.lavaY != null) {
      const size = 620;
      r.add('dynamic', 'box', 'lava', 0, this.lavaY - 40, 0, size, 80, size,
            '#e04d16', { glow: 0.4, alpha: 0.97 });
      r.add('dynamic', 'box', 'neon', 0, this.lavaY + 0.2, 0, size, 0.4, size,
            '#ffb03a', { glow: 1, alpha: 0.45 });
    }

    if (hud && hud.kind === 'koth' && hud.beaconPos) {
      const [x, y, z] = hud.beaconPos;
      const rad = hud.radius || 22;
      const owner = hud.owner;
      const color = owner === 'sun' ? '#f0a52a'
        : owner === 'moon' ? '#8a6bd8' : '#f4f7ff';
      r.add('dynamic', 'cylinder', 'neon', x, y + 1.0, z, rad * 2, 0.5,
            rad * 2, color, { glow: 1, alpha: 0.22 });
      const pulse = 1 + Math.sin(t * 3) * 0.06;
      r.add('dynamic', 'cylinder', 'neon', x, y + 9, z, 4 * pulse, 18,
            4 * pulse, color, { glow: 1, alpha: 0.55 });
      r.add('dynamic', 'sphere', 'neon', x, y + 20 + Math.sin(t * 2) * 1.2, z,
            5, 5, 5, color, { glow: 1, ry: t });
      const prog = Math.abs(hud.capture || 0);
      if (prog > 0.01) {
        r.add('dynamic', 'torus', 'neon', x, y + 2.2, z,
              rad * 2 * 0.85, 1.2, rad * 2 * 0.85,
              (hud.capture || 0) > 0 ? '#f0a52a' : '#8a6bd8',
              { glow: 1, alpha: 0.25 + prog * 0.6, ry: t * 0.7 });
      }
    }

    if (hud && hud.kind === 'ctf' && hud.flags) {
      for (const [team, flag] of Object.entries(hud.flags)) {
        const [x, y, z] = flag.pos;
        const color = team === 'red' ? '#c8372c' : '#2f7fd6';
        const bob = flag.state === 'home' ? 0 : Math.sin(t * 3) * 0.3;
        r.add('dynamic', 'box', 'metal', x, y - 2.2 + bob, z, 0.4, 5, 0.4,
              '#d8d8da', {});
        r.add('dynamic', 'box', 'smooth', x + 1.6, y + bob, z, 3.2, 2.2, 0.16,
              color, { glow: 0.25 });
        if (flag.state !== 'carried') {
          r.add('dynamic', 'cylinder', 'neon', x, y - 4.4 + bob, z, 7, 0.3, 7,
                color, { glow: 1, alpha: 0.3 });
        }
      }
    }

    if (hud && hud.kind === 'outbreak') {
      for (const d of hud.doors || []) {
        if (d.open) continue;
        const [x, y, z] = d.p;
        r.add('dynamic', 'sphere', 'neon', x, y + 6, z, 1.6, 1.6, 1.6,
              '#f2c53d', { glow: 1, alpha: 0.7 + Math.sin(t * 4) * 0.2 });
      }
      for (const w of hud.wallbuys || []) {
        if (!w.open) continue;
        const [x, y, z] = w.p;
        r.add('dynamic', 'sphere', 'neon', x, y + 4.4, z, 1.1, 1.1, 1.1,
              '#4be08a', { glow: 1, alpha: 0.75 });
      }
      if (hud.box && hud.box.open) {
        const [x, y, z] = hud.box.p;
        r.add('dynamic', 'sphere', 'neon', x, y + 5 + Math.sin(t * 2) * 0.4, z,
              1.5, 1.5, 1.5, '#f2c53d', { glow: 1 });
      }
    }
  }

  /** Nearest interactable within range, for the "press E" prompt. */
  findInteractable(x, y, z, hud, range = 11) {
    let best = null;
    const consider = (id, p, label, cost, enabled) => {
      const d = Math.hypot(p[0] - x, (p[1] - y) * 0.6, p[2] - z);
      if (d > range) return;
      if (!best || d < best.dist) {
        best = { id, dist: d, label, cost, enabled, p };
      }
    };
    for (const zl of this.level.objectives || []) {
      if (zl.kind === 'zipline') {
        consider('zipline', zl.p, 'Ride zipline', null, true);
      }
    }
    if (hud && hud.kind === 'outbreak') {
      for (const d of hud.doors || []) {
        if (!d.open) consider(d.id, d.p, 'Open blast door', d.cost, true);
      }
      for (const w of hud.wallbuys || []) {
        if (w.open) {
          consider(w.id, w.p, `Buy ${w.weapon}`, w.cost, true);
        }
      }
      if (hud.box && hud.box.open) {
        consider('mystery', hud.box.p, 'Mystery Box', hud.box.cost, true);
      }
    }
    return best;
  }
}
