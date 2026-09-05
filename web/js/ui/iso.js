// Crisp 2D isometric painter used for every small avatar/item thumbnail.
// Keeps WebGL contexts free for the big previews while still looking blocky
// and hand-built, like the real thing.

const COS30 = Math.cos(Math.PI / 6);
const SIN30 = Math.sin(Math.PI / 6);

function shade(hex, amount) {
  let h = (hex || '#999999').replace('#', '');
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  const n = parseInt(h, 16);
  const f = (v) => Math.max(0, Math.min(255, Math.round(
    amount > 0 ? v + (255 - v) * amount : v * (1 + amount))));
  return `rgb(${f((n >> 16) & 255)},${f((n >> 8) & 255)},${f(n & 255)})`;
}

export function project(x, y, z, scale, ox, oy) {
  return [ox + (x - z) * COS30 * scale, oy + ((x + z) * SIN30 - y) * scale];
}

class Painter {
  constructor(g, scale, ox, oy) {
    this.g = g; this.scale = scale; this.ox = ox; this.oy = oy;
    this.items = [];
  }
  box(x, y, z, sx, sy, sz, color, opts = {}) {
    this.items.push({ kind: 'box', x, y, z, sx, sy, sz, color, opts,
                      depth: x + z + y * 0.6 });
  }
  ellipse(x, y, z, sx, sy, color, opts = {}) {
    this.items.push({ kind: 'ellipse', x, y, z, sx, sy, color, opts,
                      depth: x + z + y * 0.6 });
  }
  draw() {
    this.items.sort((a, b) => a.depth - b.depth);
    for (const it of this.items) {
      if (it.kind === 'box') this._box(it);
      else this._ellipse(it);
    }
  }
  _box(it) {
    const { g, scale, ox, oy } = this;
    const { x, y, z, sx, sy, sz, color, opts } = it;
    const p = (dx, dy, dz) => project(x + dx, y + dy, z + dz, scale, ox, oy);
    const hx = sx / 2, hz = sz / 2;
    const alpha = opts.alpha != null ? opts.alpha : 1;
    g.globalAlpha = alpha;
    // With this projection +x runs down-right and +z down-left, so the three
    // faces the viewer can see are +y (top), +x (right) and +z (left).
    const faces = [
      { pts: [p(-hx, sy, -hz), p(hx, sy, -hz), p(hx, sy, hz), p(-hx, sy, hz)],
        c: shade(color, 0.24) },
      { pts: [p(-hx, 0, hz), p(hx, 0, hz), p(hx, sy, hz), p(-hx, sy, hz)],
        c: shade(color, -0.06) },
      { pts: [p(hx, 0, -hz), p(hx, 0, hz), p(hx, sy, hz), p(hx, sy, -hz)],
        c: shade(color, -0.26) },
    ];
    for (const f of faces) {
      g.beginPath();
      g.moveTo(f.pts[0][0], f.pts[0][1]);
      for (let i = 1; i < f.pts.length; i++) g.lineTo(f.pts[i][0], f.pts[i][1]);
      g.closePath();
      g.fillStyle = f.c;
      g.fill();
      if (opts.outline !== false) {
        g.strokeStyle = 'rgba(0,0,0,.20)';
        g.lineWidth = Math.max(0.5, scale * 0.028);
        g.stroke();
      }
    }
    if (opts.studs) {
      const [tx, ty] = project(x, y + sy, z, scale, ox, oy);
      const r = Math.min(sx, sz) * scale * 0.16;
      g.fillStyle = shade(color, 0.34);
      g.beginPath(); g.ellipse(tx, ty, r, r * SIN30, 0, 0, Math.PI * 2); g.fill();
      g.strokeStyle = 'rgba(0,0,0,.16)'; g.lineWidth = 0.7;
      g.stroke();
    }
    g.globalAlpha = 1;
  }
  _ellipse(it) {
    const { g, scale, ox, oy } = this;
    const [sx0, sy0] = project(it.x, it.y, it.z, scale, ox, oy);
    g.globalAlpha = it.opts.alpha != null ? it.opts.alpha : 1;
    g.fillStyle = it.color;
    g.beginPath();
    g.ellipse(sx0, sy0, it.sx * scale, it.sy * scale, 0, 0, Math.PI * 2);
    g.fill();
    g.globalAlpha = 1;
  }
}

// --------------------------------------------------------------- avatars
const BODY = {
  head: [1.30, 1.15, 1.30], torso: [2.00, 2.00, 1.00],
  arm: [1.00, 2.00, 1.00], leg: [1.00, 2.00, 1.00],
};

export function drawAvatar(canvas, bundle, opts = {}) {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const box = canvas.getBoundingClientRect();
  const w = Math.round(canvas.clientWidth || box.width || opts.width || 120);
  const hpx = Math.round(canvas.clientHeight || box.height || opts.height || 150);
  if (w < 2 || hpx < 2) {
    requestAnimationFrame(() => {
      if (canvas.isConnected) drawAvatar(canvas, bundle, opts);
    });
    return canvas;
  }
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(hpx * dpr);
  const g = canvas.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, hpx);

  const b = bundle || {};
  const colors = Object.assign({
    head: '#f3d64e', torso: '#1c7bc4', left_arm: '#f3d64e',
    right_arm: '#f3d64e', left_leg: '#8bc34a', right_leg: '#8bc34a',
  }, b.colors || {});
  const paint = b.paint || {};
  const snake = { head: 'head', torso: 'torso', leftArm: 'left_arm',
                  rightArm: 'right_arm', leftLeg: 'left_leg',
                  rightLeg: 'right_leg' };
  for (const [k, v] of Object.entries(paint)) {
    if (snake[k]) colors[snake[k]] = v;
  }

  const scale = (opts.scale || 1) * Math.min(w / 6.2, hpx / 7.4);
  const p = new Painter(g, scale, w / 2, hpx * 0.82);

  if (opts.shadow !== false) {
    g.save();
    g.globalAlpha = 0.16;
    g.fillStyle = '#0d1219';
    const [sx, sy] = project(0, 0, 0, scale, w / 2, hpx * 0.82);
    g.beginPath();
    g.ellipse(sx, sy + scale * 0.1, scale * 1.5, scale * 0.55, 0, 0, Math.PI * 2);
    g.fill();
    g.restore();
  }

  const legH = BODY.leg[1], torsoH = BODY.torso[1], headH = BODY.head[1];
  p.box(-0.5, 0, 0, ...BODY.leg, colors.left_leg, { studs: true });
  p.box(0.5, 0, 0, ...BODY.leg, colors.right_leg, { studs: true });
  p.box(0, legH, 0, ...BODY.torso, colors.torso, { studs: true });
  p.box(-1.5, legH, 0, ...BODY.arm, colors.left_arm, { studs: true });
  p.box(1.5, legH, 0, ...BODY.arm, colors.right_arm, { studs: true });
  p.box(0, legH + torsoH, 0, ...BODY.head, colors.head, { studs: true });

  const frames = {
    head: [0, legH + torsoH + headH / 2, 0],
    torso: [0, legH + torsoH / 2, 0],
    leftArm: [-1.5, legH + BODY.arm[1] / 2, 0],
    rightArm: [1.5, legH + BODY.arm[1] / 2, 0],
    leftLeg: [-0.5, BODY.leg[1] / 2, 0],
    rightLeg: [0.5, BODY.leg[1] / 2, 0],
  };
  for (const part of b.parts || []) {
    const f = frames[part.attach || 'head'];
    if (!f) continue;
    const [px, py, pz] = part.pos || [0, 0, 0];
    const [ix, iy, iz] = part.size || [1, 1, 1];
    p.box(f[0] + px, f[1] + py - iy / 2, f[2] + pz, ix, iy, iz,
          part.color || '#cccccc', { alpha: part.alpha, outline: true });
  }
  p.draw();

  // face, painted flat on the front-right facet of the head
  if (opts.face !== false) {
    drawIsoFace(g, scale, w / 2, hpx * 0.82, legH + torsoH, b.face || 'smile');
  }
  return canvas;
}

function drawIsoFace(g, scale, ox, oy, headY, faceId) {
  const [hx, hy] = project(0, headY + BODY.head[1] * 0.60, BODY.head[2] / 2,
                           scale, ox, oy);
  const s = scale * 0.16;
  g.save();
  g.translate(hx, hy);
  g.fillStyle = '#1a1a1d';
  g.strokeStyle = '#1a1a1d';
  g.lineWidth = Math.max(1, s * 0.42);
  g.lineCap = 'round';
  const eye = (dx, dy, r) => {
    g.beginPath(); g.ellipse(dx * s, dy * s, r * s, r * s * 1.15, 0, 0, Math.PI * 2);
    g.fill();
  };
  if (faceId === 'shades' || faceId === 'visor') {
    g.fillRect(-1.9 * s, -0.9 * s, 3.8 * s, 0.95 * s);
  } else if (faceId === 'robot') {
    g.fillStyle = '#2ad6ff';
    g.fillRect(-1.8 * s, -0.9 * s, 1.4 * s, 0.6 * s);
    g.fillRect(0.4 * s, -0.9 * s, 1.4 * s, 0.6 * s);
  } else {
    eye(-1.0, -0.7, 0.36); eye(1.0, -0.7, 0.36);
  }
  if (faceId !== 'robot') {
    g.beginPath();
    g.arc(0, 0.15 * s, 1.25 * s, 0.16 * Math.PI, 0.84 * Math.PI);
    g.stroke();
  }
  g.restore();
}

// ------------------------------------------------------------------ items
export function drawItem(canvas, item, opts = {}) {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const box = canvas.getBoundingClientRect();
  const w = Math.round(canvas.clientWidth || box.width || 120);
  const hpx = Math.round(canvas.clientHeight || box.height || 120);
  if (w < 2 || hpx < 2) {
    requestAnimationFrame(() => {
      if (canvas.isConnected) drawItem(canvas, item, opts);
    });
    return canvas;
  }
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(hpx * dpr);
  const g = canvas.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, hpx);

  const render = item.render || {};
  const parts = render.parts || [];
  const scale = Math.min(w, hpx) / 4.6;
  const p = new Painter(g, scale, w / 2, hpx * 0.70);

  if (item.category === 'face') {
    const faceCanvasSize = Math.min(w, hpx) * 0.82;
    g.save();
    g.translate(w / 2, hpx / 2);
    g.fillStyle = '#f3d64e';
    roundRect(g, -faceCanvasSize / 2, -faceCanvasSize / 2, faceCanvasSize,
              faceCanvasSize, faceCanvasSize * 0.14);
    g.fill();
    g.strokeStyle = 'rgba(0,0,0,.16)'; g.lineWidth = 1.5; g.stroke();
    g.restore();
    drawFlatFace(g, w / 2, hpx / 2, faceCanvasSize, render.face || 'smile');
    return canvas;
  }

  if (item.category === 'shirt' || item.category === 'pants') {
    const paint = render.paint || {};
    const isShirt = item.category === 'shirt';
    const main = paint.torso || paint.leftLeg || '#888888';
    const arm = paint.leftArm || main;
    if (isShirt) {
      p.box(0, 0, 0, 2, 2, 1, main, { studs: true });
      p.box(-1.5, 0, 0, 1, 2, 1, arm, { studs: true });
      p.box(1.5, 0, 0, 1, 2, 1, arm, { studs: true });
    } else {
      p.box(-0.5, 0, 0, 1, 2, 1, main, { studs: true });
      p.box(0.5, 0, 0, 1, 2, 1, main, { studs: true });
    }
    p.draw();
    return canvas;
  }

  if (item.category === 'gear') {
    const tint = { default: '#3a3f47', gold: '#e8b93d', neon: '#1b2030',
                   wood: '#8a6231', paintball: '#d8433c', carbon: '#22252b',
                   frost: '#bfe6ff' }[render.skin] || '#3a3f47';
    p.box(0, 0.4, 0, 0.5, 0.6, 3.0, tint);
    p.box(0, 0.9, -0.3, 0.35, 0.35, 1.8, '#9aa2ab');
    p.box(0, -0.4, 0.7, 0.4, 1.0, 0.6, tint);
    p.draw();
    return canvas;
  }

  // hats / back accessories: draw a ghost head or torso for context
  if (item.category === 'hat') {
    p.box(0, -1.15, 0, 1.3, 1.15, 1.3, '#c2cddb', { alpha: 0.55 });
  } else {
    p.box(0, -2.0, 0, 2.0, 2.0, 1.0, '#c2cddb', { alpha: 0.5 });
  }
  for (const part of parts) {
    const [px, py, pz] = part.pos || [0, 0, 0];
    const [ix, iy, iz] = part.size || [1, 1, 1];
    const baseY = item.category === 'hat' ? -1.15 + 1.15 / 2 : -1.0;
    p.box(px, baseY + py - iy / 2, pz, ix, iy, iz, part.color || '#cccccc',
          { alpha: part.alpha });
  }
  p.draw();
  return canvas;
}

function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

function drawFlatFace(g, cx, cy, size, id) {
  const s = size / 100;
  g.save();
  g.translate(cx - size / 2, cy - size / 2);
  g.scale(s, s);
  g.fillStyle = '#1a1a1d'; g.strokeStyle = '#1a1a1d';
  g.lineWidth = 5; g.lineCap = 'round';
  const eye = (x, y, r) => { g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill(); };
  switch (id) {
    case 'shades':
      g.fillRect(18, 32, 26, 15); g.fillRect(56, 32, 26, 15);
      g.fillRect(44, 37, 12, 4);
      g.beginPath(); g.arc(50, 56, 18, 0.18 * Math.PI, 0.82 * Math.PI); g.stroke();
      break;
    case 'robot':
      g.fillStyle = '#2ad6ff';
      g.fillRect(22, 34, 20, 10); g.fillRect(58, 34, 20, 10);
      g.fillStyle = '#1a1a1d';
      for (let i = 0; i < 6; i++) g.fillRect(30 + i * 7, 62, 4, 8);
      break;
    case 'visor':
      g.fillStyle = '#12151b';
      roundRect(g, 12, 30, 76, 22, 8); g.fill();
      g.fillStyle = '#2ad6ff'; roundRect(g, 18, 36, 64, 8, 4); g.fill();
      break;
    case 'angry':
      g.lineWidth = 6;
      g.beginPath(); g.moveTo(22, 30); g.lineTo(42, 39); g.stroke();
      g.beginPath(); g.moveTo(78, 30); g.lineTo(58, 39); g.stroke();
      eye(33, 46, 5); eye(67, 46, 5);
      g.beginPath(); g.arc(50, 74, 16, 1.2 * Math.PI, 1.8 * Math.PI); g.stroke();
      break;
    case 'surprised':
      eye(33, 40, 8); eye(67, 40, 8);
      g.beginPath(); g.ellipse(50, 64, 9, 12, 0, 0, Math.PI * 2); g.fill();
      break;
    case 'cat':
      g.beginPath(); g.arc(33, 44, 7, 1.1 * Math.PI, 1.9 * Math.PI); g.stroke();
      g.beginPath(); g.arc(67, 44, 7, 1.1 * Math.PI, 1.9 * Math.PI); g.stroke();
      g.beginPath(); g.moveTo(44, 60); g.quadraticCurveTo(50, 66, 56, 60); g.stroke();
      break;
    case 'winky':
      eye(33, 40, 6);
      g.beginPath(); g.arc(67, 44, 8, 1.15 * Math.PI, 1.85 * Math.PI); g.stroke();
      g.beginPath(); g.arc(50, 54, 18, 0.18 * Math.PI, 0.82 * Math.PI); g.stroke();
      break;
    case 'dizzy':
      for (const cxx of [33, 67]) {
        g.beginPath();
        for (let a = 0; a < Math.PI * 4; a += 0.2) {
          const r = (a / (Math.PI * 4)) * 9;
          const px = cxx + Math.cos(a) * r, py = 42 + Math.sin(a) * r;
          a === 0 ? g.moveTo(px, py) : g.lineTo(px, py);
        }
        g.stroke();
      }
      g.beginPath(); g.ellipse(50, 68, 10, 7, 0, 0, Math.PI * 2); g.stroke();
      break;
    case 'epic':
      g.lineWidth = 6;
      g.beginPath(); g.moveTo(22, 32); g.lineTo(44, 40); g.stroke();
      g.beginPath(); g.moveTo(78, 32); g.lineTo(56, 40); g.stroke();
      eye(34, 47, 5); eye(66, 47, 5);
      g.beginPath(); g.moveTo(24, 62);
      g.quadraticCurveTo(50, 92, 76, 62);
      g.quadraticCurveTo(50, 72, 24, 62); g.closePath(); g.fill();
      break;
    case 'chill':
      g.beginPath(); g.arc(33, 42, 8, Math.PI, Math.PI * 2); g.stroke();
      g.beginPath(); g.arc(67, 42, 8, Math.PI, Math.PI * 2); g.stroke();
      g.beginPath(); g.arc(50, 56, 16, 0.18 * Math.PI, 0.82 * Math.PI); g.stroke();
      break;
    case 'cheeky':
      eye(33, 40, 6); eye(67, 40, 6);
      g.beginPath(); g.arc(50, 52, 22, 0.1 * Math.PI, 0.7 * Math.PI); g.stroke();
      break;
    default:
      eye(33, 40, 6.5); eye(67, 40, 6.5);
      g.beginPath(); g.arc(50, 54, 20, 0.18 * Math.PI, 0.82 * Math.PI); g.stroke();
  }
  g.restore();
}
