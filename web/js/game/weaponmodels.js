// Blocky weapon models, shared by the first-person view model and the
// third-person characters.  Parts are in the weapon's local frame:
// +x right, +y up, -z forward (muzzle direction).

const M = (shape, pos, size, tint, opts = {}) =>
  ({ shape, pos, size, tint, ...opts });

export const WEAPON_MODELS = {
  pistol: {
    grip: [0, -0.26, 0.04],
    muzzle: [0, 0.06, -0.95],
    parts: [
      M('box', [0, 0, -0.30], [0.20, 0.26, 1.05], 'body'),
      M('box', [0, 0.16, -0.62], [0.14, 0.10, 0.55], 'accent'),
      M('box', [0, -0.30, 0.06], [0.18, 0.50, 0.28], 'accent', { rx: 12 }),
      M('box', [0, -0.10, -0.86], [0.10, 0.10, 0.24], 'metal'),
    ],
  },
  rifle: {
    grip: [0, -0.26, -0.62],
    muzzle: [0, 0.05, -1.75],
    parts: [
      M('box', [0, 0, -0.45], [0.22, 0.28, 1.90], 'body'),
      M('box', [0, 0.20, -0.55], [0.10, 0.10, 1.50], 'accent'),
      M('box', [0, -0.02, -1.55], [0.13, 0.13, 0.45], 'metal'),
      M('box', [0, -0.34, -0.10], [0.16, 0.46, 0.26], 'accent', { rx: 10 }),
      M('box', [0, -0.24, -0.75], [0.14, 0.34, 0.42], 'accent'),
      M('box', [0, 0.02, 0.52], [0.20, 0.30, 0.62], 'accent'),
      M('box', [0, 0.30, -0.30], [0.06, 0.10, 0.08], 'metal'),
    ],
  },
  shotgun: {
    grip: [0, -0.24, -0.62],
    muzzle: [0, 0.02, -1.60],
    parts: [
      M('box', [0, 0.06, -0.60], [0.30, 0.20, 1.90], 'body'),
      M('box', [0, -0.14, -0.70], [0.26, 0.18, 1.30], 'accent'),
      M('box', [0, -0.30, 0.05], [0.18, 0.44, 0.28], 'accent', { rx: 14 }),
      M('box', [0, 0.04, 0.55], [0.26, 0.34, 0.70], 'accent'),
      M('cylinder', [0.07, 0.08, -1.45], [0.12, 0.30, 0.12], 'metal', { rx: 90 }),
      M('cylinder', [-0.07, 0.08, -1.45], [0.12, 0.30, 0.12], 'metal', { rx: 90 }),
    ],
  },
  sniper: {
    grip: [0, -0.26, -0.02],
    muzzle: [0, 0.04, -2.30],
    parts: [
      M('box', [0, 0, -0.70], [0.20, 0.24, 2.70], 'body'),
      M('box', [0, 0.26, -0.40], [0.14, 0.20, 0.80], 'accent'),
      M('cylinder', [0, 0.42, -0.40], [0.18, 0.90, 0.18], 'metal', { rx: 90 }),
      M('box', [0, -0.02, -2.05], [0.12, 0.12, 0.60], 'metal'),
      M('box', [0, -0.34, -0.05], [0.16, 0.46, 0.26], 'accent', { rx: 8 }),
      M('box', [0, 0.02, 0.70], [0.20, 0.34, 0.90], 'accent'),
      M('box', [0, -0.22, -1.55], [0.34, 0.10, 0.44], 'accent'),
    ],
  },
  launcher: {
    grip: [0, -0.24, -0.08],
    muzzle: [0, 0.08, -1.85],
    parts: [
      M('cylinder', [0, 0.08, -0.55], [0.40, 2.40, 0.40], 'body', { rx: 90 }),
      M('cylinder', [0, 0.08, -1.72], [0.48, 0.30, 0.48], 'accent', { rx: 90 }),
      M('cylinder', [0, 0.08, 0.58], [0.46, 0.24, 0.46], 'accent', { rx: 90 }),
      M('box', [0, -0.30, -0.10], [0.16, 0.44, 0.26], 'accent', { rx: 10 }),
      M('box', [0, 0.36, -0.70], [0.10, 0.22, 0.60], 'metal'),
      M('box', [0.22, 0.10, -0.05], [0.10, 0.16, 1.10], 'metal'),
    ],
  },
  ball: {
    grip: [0, -0.10, -0.10],
    muzzle: [0, 0, -0.55],
    parts: [
      M('sphere', [0, -0.05, -0.35], [0.62, 0.62, 0.62], 'body', { glow: 0.2 }),
      M('sphere', [0, -0.05, -0.35], [0.68, 0.20, 0.68], 'metal',
        { glow: 0.4, alpha: 0.6 }),
    ],
  },
  zapper: {
    grip: [0, -0.26, 0.00],
    muzzle: [0, 0.10, -1.35],
    parts: [
      M('box', [0, 0, -0.40], [0.26, 0.30, 1.50], 'body'),
      M('cylinder', [0, 0.10, -1.20], [0.26, 0.40, 0.26], 'metal', { rx: 90, glow: 0.4 }),
      M('box', [0, 0.26, -0.20], [0.12, 0.16, 0.90], 'metal', { glow: 0.5 }),
      M('box', [0, -0.32, 0.02], [0.16, 0.44, 0.26], 'accent', { rx: 10 }),
      M('box', [0, 0.04, 0.50], [0.22, 0.30, 0.55], 'accent'),
    ],
  },
  mender: {
    grip: [0, -0.24, 0.00],
    muzzle: [0, 0.08, -1.10],
    parts: [
      M('box', [0, 0, -0.35], [0.24, 0.26, 1.20], 'body'),
      M('cylinder', [0, 0.16, -0.30], [0.30, 0.70, 0.30], 'metal',
        { rx: 90, glow: 0.35 }),
      M('box', [0, -0.30, 0.02], [0.16, 0.42, 0.26], 'accent', { rx: 10 }),
      M('sphere', [0, 0.10, -1.00], [0.26, 0.26, 0.26], 'metal', { glow: 0.8 }),
    ],
  },
};

export function modelFor(weaponId, weaponDefs) {
  const def = weaponDefs && weaponDefs[weaponId];
  const name = def ? def.model : 'rifle';
  return WEAPON_MODELS[name] || WEAPON_MODELS.rifle;
}
