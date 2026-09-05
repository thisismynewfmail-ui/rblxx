// The blocky R6 character: geometry, clothing, accessories and animation.

import { faceTexture, patternTexture } from './textures.js';
import * as glh from './gl.js';

// Classic proportions in studs (before the uniform fit-to-collision scale).
export const BODY = {
  head:     { w: 1.30, h: 1.15, d: 1.30 },
  torso:    { w: 2.00, h: 2.00, d: 1.00 },
  arm:      { w: 1.00, h: 2.00, d: 1.00 },
  leg:      { w: 1.00, h: 2.00, d: 1.00 },
};
export const RAW_HEIGHT = BODY.leg.h + BODY.torso.h + BODY.head.h; // 5.15
export const FIT = 5.0 / RAW_HEIGHT;

const PART_KEYS = ['head', 'torso', 'leftArm', 'rightArm', 'leftLeg',
                   'rightLeg'];
const SNAKE = {
  head: 'head', torso: 'torso', leftArm: 'left_arm', rightArm: 'right_arm',
  leftLeg: 'left_leg', rightLeg: 'right_leg',
};

const faceCache = new Map();
const patternCache = new Map();

function faceKey(renderer, id) {
  const key = `face:${id || 'smile'}`;
  if (!faceCache.has(key)) {
    const tex = faceTexture(renderer.ctx, glh, id || 'smile');
    renderer.registerTexture(key, tex, { transparent: true });
    faceCache.set(key, key);
  }
  return key;
}

function patternKey(renderer, id) {
  if (!id) return null;
  const key = `pat:${id}`;
  if (!patternCache.has(key)) {
    const tex = patternTexture(renderer.ctx, glh, id);
    if (!tex) { patternCache.set(key, null); return null; }
    renderer.registerTexture(key, tex, { transparent: true });
    patternCache.set(key, key);
  }
  return patternCache.get(key);
}

export const DEFAULT_BUNDLE = {
  colors: {
    head: '#f3d64e', torso: '#1c7bc4', left_arm: '#f3d64e',
    right_arm: '#f3d64e', left_leg: '#8bc34a', right_leg: '#8bc34a',
  },
  parts: [], face: 'smile', paint: {}, pattern: {}, skin: 'default', scale: 1,
};

export class AvatarModel {
  constructor(bundle) {
    this.set(bundle);
    this.anim = {
      phase: 0, swing: 0, lean: 0, armPose: 0, bob: 0, jumpBlend: 0,
      lastYaw: 0,
    };
  }

  set(bundle) {
    const b = Object.assign({}, DEFAULT_BUNDLE, bundle || {});
    this.colors = Object.assign({}, DEFAULT_BUNDLE.colors, b.colors || {});
    const paint = b.paint || {};
    for (const key of PART_KEYS) {
      if (paint[key]) this.colors[SNAKE[key]] = paint[key];
    }
    this.parts = b.parts || [];
    this.face = b.face || 'smile';
    this.pattern = b.pattern || {};
    this.skin = b.skin || 'default';
    this.scale = b.scale || 1;
  }

  colorOf(key) { return this.colors[SNAKE[key]] || '#a3a2a5'; }

  /** Advance the animation given movement state. */
  update(dt, { speed = 0, onGround = true, holding = true, crouch = false,
               pitch = 0, dead = false } = {}) {
    const a = this.anim;
    const target = Math.min(1, speed / 16);
    a.swing += (target - a.swing) * Math.min(1, dt * 12);
    a.phase += dt * (4.2 + speed * 0.34);
    a.jumpBlend += ((onGround ? 0 : 1) - a.jumpBlend) * Math.min(1, dt * 9);
    a.armPose += ((holding ? 1 : 0) - a.armPose) * Math.min(1, dt * 10);
    a.bob = Math.sin(a.phase * 2) * 0.05 * a.swing;
    a.lean = crouch ? 0.24 : 0;
    a.pitch = pitch;
    a.dead = dead;
  }

  /**
   * Draw the character. `opts.hideHead` is used in first person so the
   * player's own head never clips the camera.
   */
  draw(renderer, opts) {
    const {
      x = 0, y = 0, z = 0, yaw = 0, pitch = 0, scale = 1, alpha = 1,
      layer = 'dynamic', hideHead = false, hideAll = false, tint = null,
      glow = 0,
    } = opts;
    if (hideAll) return;
    const s = FIT * this.scale * scale;
    const a = this.anim;

    const swingAmp = 0.62 * a.swing;
    const walk = Math.sin(a.phase);
    const legL = walk * swingAmp;
    const legR = -walk * swingAmp;
    let armL = -walk * swingAmp * 0.75;
    let armR = walk * swingAmp * 0.75;

    // Holding a weapon: classic straight-arm forward pose.
    // Positive X rotation swings a limb forward (see _limb).
    const aim = Math.PI / 2 + pitch * 0.9;
    armR = armR * (1 - a.armPose) + aim * a.armPose;
    armL = armL * (1 - a.armPose) + (aim * 0.78 - 0.12) * a.armPose;
    if (a.jumpBlend > 0.01) {
      const j = a.jumpBlend;
      armL = armL * (1 - j) + 2.55 * j;
      armR = armR * (1 - j) + 2.35 * j;
    }
    if (a.dead) {
      // ragdoll-ish flop
      armL = 1.9; armR = -1.9;
    }

    const crouchDrop = a.lean * 0.9;
    const baseY = y + a.bob * s - crouchDrop * s;

    const legH = BODY.leg.h * s;
    const torsoH = BODY.torso.h * s;
    const armH = BODY.arm.h * s;
    const headH = BODY.head.h * s;

    const hipY = baseY + legH;
    const shoulderY = hipY + torsoH;

    const put = (part, lx, ly, lz, w, h, d, colorKey, swingX, extra = {}) => {
      const cy = Math.cos(yaw), sy = Math.sin(yaw);
      const wx = x + lx * cy + lz * sy;
      const wz = z - lx * sy + lz * cy;
      renderer.add(layer, 'box', extra.tex || 'studs', wx, ly, wz, w, h, d,
                   tint || this.colorOf(colorKey), {
                     rx: swingX, ry: yaw, alpha,
                     glow, tile: extra.tile || 1, uvMode: extra.uvMode || 0,
                   });
      return { wx, wz, ly };
    };

    // --- legs (pivot at the hip) ---
    for (const [key, sign, ang] of [['leftLeg', -1, legL], ['rightLeg', 1, legR]]) {
      const px = sign * (BODY.leg.w / 2) * s;
      const cy = Math.cos(ang), sn = Math.sin(ang);
      const oy = hipY - (legH / 2) * cy;
      const oz = -(legH / 2) * sn;
      this._limb(renderer, layer, x, oy, z, yaw, px, oz, BODY.leg.w * s,
                 legH, BODY.leg.d * s, patternKey(renderer, this.pattern.pants),
                 ang, alpha, glow, this.colorOf(key), tint);
    }

    // --- torso ---
    {
      const cy = Math.cos(yaw), sy = Math.sin(yaw);
      const torsoTex = patternKey(renderer, this.pattern.shirt);
      renderer.add(layer, 'box', 'studs', x, hipY + torsoH / 2, z,
                   BODY.torso.w * s, torsoH, BODY.torso.d * s,
                   tint || this.colorOf('torso'),
                   { ry: yaw, alpha, glow });
      if (torsoTex) {
        renderer.add(layer, 'box', torsoTex, x, hipY + torsoH / 2, z,
                     BODY.torso.w * s * 1.012, torsoH * 1.012,
                     BODY.torso.d * s * 1.012, '#ffffff',
                     { ry: yaw, alpha: alpha * 0.98, uvMode: 1 });
      }
    }

    // --- arms (pivot at the shoulder) ---
    for (const [key, sign, ang] of [['leftArm', -1, armL], ['rightArm', 1, armR]]) {
      const px = sign * (BODY.torso.w / 2 + BODY.arm.w / 2) * s;
      const cy = Math.cos(ang), sn = Math.sin(ang);
      const oy = shoulderY - (armH / 2) * cy;
      const oz = -(armH / 2) * sn;
      this._limb(renderer, layer, x, oy, z, yaw, px, oz, BODY.arm.w * s,
                 armH, BODY.arm.d * s, patternKey(renderer, this.pattern.shirt),
                 ang, alpha, glow, this.colorOf(key), tint);
    }

    // --- head ---
    const headPitch = pitch * 0.35;
    const headY = shoulderY + headH / 2;
    if (!hideHead) {
      renderer.add(layer, 'box', 'studs', x, headY, z, BODY.head.w * s,
                   headH, BODY.head.d * s, tint || this.colorOf('head'),
                   { ry: yaw, rx: headPitch, alpha, glow });
      // face decal on the front of the head
      const fz = (BODY.head.d / 2) * s + 0.012;
      const cy = Math.cos(yaw), sy = Math.sin(yaw);
      renderer.add(layer, 'quad', faceKey(renderer, this.face),
                   x - fz * sy * Math.cos(headPitch),
                   headY + fz * Math.sin(headPitch),
                   z - fz * cy * Math.cos(headPitch),
                   BODY.head.w * s * 0.98, headH * 0.98, 1,
                   '#ffffff',
                   { ry: yaw + Math.PI, rx: -headPitch, alpha, uvMode: 1 });
    }

    // --- accessories ---
    if (this.parts.length) {
      const frames = {
        head: { x: 0, y: headY, z: 0, rx: headPitch },
        torso: { x: 0, y: hipY + torsoH / 2, z: 0, rx: 0 },
        leftArm: { x: -(BODY.torso.w / 2 + BODY.arm.w / 2) * s,
                   y: shoulderY - armH / 2, z: 0, rx: armL },
        rightArm: { x: (BODY.torso.w / 2 + BODY.arm.w / 2) * s,
                    y: shoulderY - armH / 2, z: 0, rx: armR },
        leftLeg: { x: -(BODY.leg.w / 2) * s, y: hipY - legH / 2, z: 0, rx: legL },
        rightLeg: { x: (BODY.leg.w / 2) * s, y: hipY - legH / 2, z: 0, rx: legR },
      };
      const cy = Math.cos(yaw), sy = Math.sin(yaw);
      for (const item of this.parts) {
        const frame = frames[item.attach || 'head'];
        if (!frame) continue;
        if (hideHead && (item.attach || 'head') === 'head') continue;
        const [ax, ay, az] = item.pos || [0, 0, 0];
        const [ix, iy, iz] = item.size || [1, 1, 1];
        const rot = item.rot || [0, 0, 0];
        const fr = frame.rx || 0;
        const cf = Math.cos(fr), sf = Math.sin(fr);
        // rotate the local offset into the part's frame, then into the world
        const ly = ay * cf - az * sf;
        const lz = ay * sf + az * cf;
        const lx = frame.x + ax * s;
        const wx = x + lx * cy + (lz * s) * sy;
        const wz = z - lx * sy + (lz * s) * cy;
        renderer.add(layer, item.shape || 'box',
                     item.glow ? 'neon' : (item.texture || 'smooth'),
                     wx, frame.y + ly * s, wz,
                     ix * s, iy * s, iz * s,
                     tint || item.color || '#cccccc', {
                       rx: fr + rot[0] * Math.PI / 180,
                       ry: yaw + rot[1] * Math.PI / 180,
                       rz: rot[2] * Math.PI / 180,
                       alpha: alpha * (item.alpha != null ? item.alpha : 1),
                       glow: item.glow ? 1 : glow,
                       spin: item.spin || 0,
                     });
      }
    }

    return { headY, shoulderY, hipY, scale: s };
  }

  _limb(renderer, layer, x, oy, z, yaw, px, oz, w, h, d, patTex, ang, alpha,
        glow, color, tint) {
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const wx = x + px * cy + oz * sy;
    const wz = z - px * sy + oz * cy;
    renderer.add(layer, 'box', 'studs', wx, oy, wz, w, h, d, tint || color,
                 { rx: ang, ry: yaw, alpha, glow });
    if (patTex) {
      renderer.add(layer, 'box', patTex, wx, oy, wz, w * 1.014, h * 1.014,
                   d * 1.014, '#ffffff',
                   { rx: ang, ry: yaw, alpha: alpha * 0.98, uvMode: 1 });
    }
  }

  /** Where the right hand sits, in character-local coordinates. */
  handOffset(pitch, scale = 1) {
    const s = FIT * this.scale * scale;
    const armH = BODY.arm.h * s;
    const shoulderY = BODY.leg.h * s + BODY.torso.h * s;
    const ang = Math.PI / 2 + pitch * 0.9;
    return {
      x: (BODY.torso.w / 2 + BODY.arm.w / 2) * s,
      y: shoulderY - armH * Math.cos(ang),
      z: -armH * Math.sin(ang),
      scale: s,
    };
  }

  /** World-space eye position for a character at (x, y, z). */
  eyeHeight(scale = 1) {
    return (BODY.leg.h + BODY.torso.h + BODY.head.h * 0.62) * FIT
      * this.scale * scale;
  }
}
