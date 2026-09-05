// Procedural world thumbnails — a painted-on-canvas poster per world.

function rng(seed) {
  let s = seed >>> 0 || 7;
  return () => { s ^= s << 13; s >>>= 0; s ^= s >> 17; s ^= s << 5; s >>>= 0;
                 return s / 4294967296; };
}

function sky(g, w, h, top, bottom, sunX, sunY, sunColor) {
  const grd = g.createLinearGradient(0, 0, 0, h);
  grd.addColorStop(0, top);
  grd.addColorStop(1, bottom);
  g.fillStyle = grd;
  g.fillRect(0, 0, w, h);
  if (sunColor) {
    const s = g.createRadialGradient(sunX, sunY, 0, sunX, sunY, h * 0.55);
    s.addColorStop(0, sunColor);
    s.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = s;
    g.fillRect(0, 0, w, h);
  }
}

function clouds(g, w, h, seed, alpha = 0.5, count = 8) {
  const r = rng(seed);
  g.save();
  g.globalAlpha = alpha;
  g.fillStyle = '#ffffff';
  for (let i = 0; i < count; i++) {
    const x = r() * w, y = r() * h * 0.4, s = w * (0.06 + r() * 0.10);
    for (let k = 0; k < 3; k++) {
      g.beginPath();
      g.ellipse(x + k * s * 0.5 - s * 0.5, y + (k === 1 ? -s * 0.22 : 0),
                s * (0.7 - k * 0.08), s * 0.36, 0, 0, Math.PI * 2);
      g.fill();
    }
  }
  g.restore();
}

// A tiny isometric-ish box helper for the poster art.
function block(g, x, y, w, h, d, color, light = 1) {
  const sh = (c, k) => {
    const n = parseInt(c.slice(1), 16);
    const f = (v) => Math.max(0, Math.min(255, Math.round(v * k)));
    return `rgb(${f((n >> 16) & 255)},${f((n >> 8) & 255)},${f(n & 255)})`;
  };
  g.fillStyle = sh(color, 1.0 * light);
  g.fillRect(x, y, w, h);
  g.fillStyle = sh(color, 1.22 * light);
  g.beginPath();
  g.moveTo(x, y); g.lineTo(x + d, y - d); g.lineTo(x + w + d, y - d);
  g.lineTo(x + w, y); g.closePath(); g.fill();
  g.fillStyle = sh(color, 0.74 * light);
  g.beginPath();
  g.moveTo(x + w, y); g.lineTo(x + w + d, y - d);
  g.lineTo(x + w + d, y + h - d); g.lineTo(x + w, y + h); g.closePath(); g.fill();
}

const PAINTERS = {
  crossroads(g, w, h) {
    sky(g, w, h, '#4d92d8', '#c9e6f7', w * 0.72, h * 0.16, 'rgba(255,250,220,.75)');
    clouds(g, w, h, 11, 0.55, 7);
    g.fillStyle = '#4f9c33';
    g.fillRect(0, h * 0.56, w, h * 0.44);
    g.fillStyle = '#3f7f28';
    g.fillRect(0, h * 0.56, w, h * 0.03);
    // roads
    g.fillStyle = '#c8c8c8';
    g.beginPath();
    g.moveTo(w * 0.40, h * 0.56); g.lineTo(w * 0.60, h * 0.56);
    g.lineTo(w * 0.86, h); g.lineTo(w * 0.14, h); g.closePath(); g.fill();
    g.fillStyle = '#f2e05a';
    for (let i = 0; i < 4; i++) {
      const t0 = i / 4, t1 = t0 + 0.12;
      const y0 = h * (0.56 + 0.44 * t0), y1 = h * (0.56 + 0.44 * t1);
      const wid0 = 3 + t0 * 10, wid1 = 3 + t1 * 10;
      g.beginPath();
      g.moveTo(w / 2 - wid0 / 2, y0); g.lineTo(w / 2 + wid0 / 2, y0);
      g.lineTo(w / 2 + wid1 / 2, y1); g.lineTo(w / 2 - wid1 / 2, y1);
      g.closePath(); g.fill();
    }
    // central tower
    block(g, w * 0.42, h * 0.28, w * 0.16, h * 0.30, w * 0.05, '#a3a3a5');
    for (let i = 0; i < 5; i++) {
      block(g, w * (0.42 + i * 0.033), h * 0.245, w * 0.024, h * 0.04,
            w * 0.018, '#8f8f92');
    }
    g.fillStyle = '#f2c53d';
    g.beginPath(); g.arc(w * 0.50, h * 0.22, w * 0.022, 0, Math.PI * 2); g.fill();
    // forts
    block(g, w * 0.06, h * 0.46, w * 0.20, h * 0.16, w * 0.045, '#9c3a2e');
    block(g, w * 0.74, h * 0.46, w * 0.20, h * 0.16, w * 0.045, '#2f5f9c');
    // trees
    const r = rng(5);
    for (let i = 0; i < 7; i++) {
      const x = r() * w, y = h * (0.62 + r() * 0.3);
      const s = w * (0.02 + r() * 0.016);
      g.fillStyle = '#6b4a2c';
      g.fillRect(x - s * 0.18, y, s * 0.36, s * 1.1);
      g.fillStyle = '#2f7d32';
      g.beginPath(); g.arc(x, y - s * 0.2, s, 0, Math.PI * 2); g.fill();
    }
  },

  skyhaven(g, w, h) {
    sky(g, w, h, '#2f5fa8', '#ffd9a0', w * 0.24, h * 0.30, 'rgba(255,236,190,.85)');
    clouds(g, w, h, 23, 0.4, 10);
    const island = (cx, cy, r0, tint) => {
      g.fillStyle = tint;
      g.beginPath(); g.ellipse(cx, cy, r0, r0 * 0.32, 0, 0, Math.PI * 2); g.fill();
      g.fillStyle = '#8e9aa6';
      g.beginPath();
      g.moveTo(cx - r0, cy); g.lineTo(cx + r0, cy);
      g.lineTo(cx + r0 * 0.28, cy + r0 * 1.25);
      g.lineTo(cx - r0 * 0.28, cy + r0 * 1.25);
      g.closePath(); g.fill();
      g.fillStyle = '#6f7a86';
      g.beginPath();
      g.moveTo(cx - r0 * 0.28, cy + r0 * 1.25);
      g.lineTo(cx + r0 * 0.28, cy + r0 * 1.25);
      g.lineTo(cx, cy + r0 * 1.9); g.closePath(); g.fill();
    };
    island(w * 0.24, h * 0.66, w * 0.16, '#4f9c5a');
    island(w * 0.76, h * 0.72, w * 0.13, '#4f9c5a');
    island(w * 0.52, h * 0.44, w * 0.22, '#5aa864');
    // beacon
    g.fillStyle = 'rgba(255,229,138,.85)';
    g.fillRect(w * 0.505, h * 0.24, w * 0.03, h * 0.20);
    g.fillStyle = '#ffe07a';
    g.beginPath(); g.arc(w * 0.52, h * 0.22, w * 0.035, 0, Math.PI * 2); g.fill();
    // bridge
    g.strokeStyle = '#a08054'; g.lineWidth = Math.max(2, w * 0.012);
    g.beginPath();
    g.moveTo(w * 0.30, h * 0.66);
    g.quadraticCurveTo(w * 0.40, h * 0.62, w * 0.42, h * 0.46);
    g.stroke();
  },

  outbreak(g, w, h) {
    const grd = g.createLinearGradient(0, 0, 0, h);
    grd.addColorStop(0, '#0b1016');
    grd.addColorStop(1, '#16202a');
    g.fillStyle = grd; g.fillRect(0, 0, w, h);
    // corridor perspective
    g.fillStyle = '#202934';
    g.beginPath();
    g.moveTo(0, 0); g.lineTo(w * 0.28, h * 0.34);
    g.lineTo(w * 0.28, h * 0.72); g.lineTo(0, h); g.closePath(); g.fill();
    g.beginPath();
    g.moveTo(w, 0); g.lineTo(w * 0.72, h * 0.34);
    g.lineTo(w * 0.72, h * 0.72); g.lineTo(w, h); g.closePath(); g.fill();
    g.fillStyle = '#2b3644';
    g.fillRect(w * 0.28, h * 0.34, w * 0.44, h * 0.38);
    g.fillStyle = '#101820';
    g.beginPath();
    g.moveTo(0, h); g.lineTo(w * 0.28, h * 0.72);
    g.lineTo(w * 0.72, h * 0.72); g.lineTo(w, h); g.closePath(); g.fill();
    // ceiling strips
    for (let i = 0; i < 4; i++) {
      const t = i / 4;
      const y = h * (0.10 + t * 0.22);
      const x0 = w * (0.5 - (0.48 - t * 0.22));
      const x1 = w * (0.5 + (0.48 - t * 0.22));
      g.fillStyle = `rgba(220,240,255,${0.55 - t * 0.1})`;
      g.fillRect(x0, y, x1 - x0, Math.max(1.5, h * 0.012));
    }
    // reactor glow
    const glow = g.createRadialGradient(w * 0.5, h * 0.55, 0, w * 0.5, h * 0.55,
                                        w * 0.30);
    glow.addColorStop(0, 'rgba(75,224,138,.55)');
    glow.addColorStop(1, 'rgba(75,224,138,0)');
    g.fillStyle = glow; g.fillRect(0, 0, w, h);
    // silhouettes
    const r = rng(9);
    for (let i = 0; i < 4; i++) {
      const x = w * (0.34 + r() * 0.34), s = h * (0.16 + r() * 0.14);
      const y = h * 0.72;
      g.fillStyle = 'rgba(8,12,16,.92)';
      g.fillRect(x - s * 0.20, y - s, s * 0.40, s * 0.60);
      g.fillRect(x - s * 0.13, y - s * 0.42, s * 0.11, s * 0.42);
      g.fillRect(x + 0.02 * s, y - s * 0.42, s * 0.11, s * 0.42);
      g.fillRect(x - s * 0.14, y - s * 1.24, s * 0.28, s * 0.26);
      g.fillStyle = '#ffe14f';
      g.fillRect(x - s * 0.10, y - s * 1.16, s * 0.06, s * 0.05);
      g.fillRect(x + s * 0.04, y - s * 1.16, s * 0.06, s * 0.05);
    }
  },

  lavarise(g, w, h) {
    sky(g, w, h, '#2a1018', '#c2521c', w * 0.5, h * 0.86, 'rgba(255,140,40,.6)');
    // caldera walls
    g.fillStyle = '#3a2018';
    g.beginPath();
    g.moveTo(0, h * 0.30); g.lineTo(w * 0.22, h * 0.52);
    g.lineTo(0, h); g.closePath(); g.fill();
    g.beginPath();
    g.moveTo(w, h * 0.28); g.lineTo(w * 0.78, h * 0.52);
    g.lineTo(w, h); g.closePath(); g.fill();
    // lava lake
    const lava = g.createLinearGradient(0, h * 0.70, 0, h);
    lava.addColorStop(0, '#ff7a2a');
    lava.addColorStop(0.5, '#ff4a10');
    lava.addColorStop(1, '#b02a08');
    g.fillStyle = lava;
    g.fillRect(0, h * 0.70, w, h * 0.30);
    g.fillStyle = 'rgba(255,220,120,.5)';
    for (let i = 0; i < 8; i++) {
      const y = h * (0.72 + (i / 8) * 0.26);
      g.fillRect(w * (0.05 + (i % 3) * 0.25), y, w * (0.12 + (i % 4) * 0.06), 2);
    }
    // spire
    const tiers = 5;
    for (let i = 0; i < tiers; i++) {
      const t = i / (tiers - 1);
      const cw = w * (0.44 - t * 0.30);
      const cy = h * (0.72 - t * 0.44);
      block(g, w / 2 - cw / 2, cy, cw, h * 0.05, w * 0.03,
            i % 2 ? '#6e5a4a' : '#8c7563');
      if (i % 2 === 1) {
        g.fillStyle = '#ff7a2a';
        g.fillRect(w / 2 - cw / 2, cy - 2, cw * 0.22, 4);
      }
    }
    g.fillStyle = '#f2c53d';
    g.beginPath();
    g.moveTo(w / 2, h * 0.20); g.lineTo(w / 2 + w * 0.03, h * 0.26);
    g.lineTo(w / 2 - w * 0.03, h * 0.26); g.closePath(); g.fill();
    // embers
    const r = rng(17);
    g.fillStyle = 'rgba(255,180,90,.8)';
    for (let i = 0; i < 26; i++) {
      g.fillRect(r() * w, h * (0.2 + r() * 0.7), 2, 2 + r() * 3);
    }
  },

  fortwars(g, w, h) {
    sky(g, w, h, '#7d8b99', '#dbe4ec', w * 0.5, h * 0.1, 'rgba(255,255,255,.5)');
    clouds(g, w, h, 41, 0.7, 9);
    // far cliffs
    g.fillStyle = '#6b5a48';
    g.fillRect(0, h * 0.48, w, h * 0.10);
    // canyon
    g.fillStyle = '#4a3c30';
    g.beginPath();
    g.moveTo(w * 0.32, h * 0.58); g.lineTo(w * 0.68, h * 0.58);
    g.lineTo(w * 0.80, h); g.lineTo(w * 0.20, h); g.closePath(); g.fill();
    g.fillStyle = '#2f7fb8';
    g.beginPath();
    g.moveTo(w * 0.42, h * 0.80); g.lineTo(w * 0.58, h * 0.80);
    g.lineTo(w * 0.64, h); g.lineTo(w * 0.36, h); g.closePath(); g.fill();
    // plateaus
    g.fillStyle = '#5a9c3a';
    g.fillRect(0, h * 0.52, w * 0.34, h * 0.10);
    g.fillRect(w * 0.66, h * 0.52, w * 0.34, h * 0.10);
    g.fillStyle = '#6b5a48';
    g.fillRect(0, h * 0.62, w * 0.34, h * 0.38);
    g.fillRect(w * 0.66, h * 0.62, w * 0.34, h * 0.38);
    // forts
    block(g, w * 0.03, h * 0.34, w * 0.26, h * 0.20, w * 0.04, '#9a9a9c');
    block(g, w * 0.71, h * 0.34, w * 0.26, h * 0.20, w * 0.04, '#9a9a9c');
    // banners
    g.fillStyle = '#3a3a3c';
    g.fillRect(w * 0.14, h * 0.20, 3, h * 0.16);
    g.fillRect(w * 0.84, h * 0.20, 3, h * 0.16);
    g.fillStyle = '#c8372c';
    g.fillRect(w * 0.145, h * 0.20, w * 0.07, h * 0.07);
    g.fillStyle = '#2f7fd6';
    g.fillRect(w * 0.845, h * 0.20, w * 0.07, h * 0.07);
    // causeway
    g.fillStyle = '#d8c07a';
    g.fillRect(w * 0.32, h * 0.565, w * 0.36, h * 0.022);
    g.fillStyle = '#9a9a9c';
    g.fillRect(w * 0.46, h * 0.50, w * 0.08, h * 0.09);
  },
};

const cache = new Map();

export function worldThumb(canvas, worldId, { width = 320, height = 240 } = {}) {
  const key = `${worldId}:${width}x${height}`;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  let bitmap = cache.get(key);
  if (!bitmap) {
    const off = document.createElement('canvas');
    off.width = Math.round(width * dpr);
    off.height = Math.round(height * dpr);
    const g = off.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const painter = PAINTERS[worldId] || PAINTERS.crossroads;
    painter(g, width, height);
    // a subtle vignette so text overlays stay readable
    const v = g.createRadialGradient(width / 2, height / 2, height * 0.2,
                                     width / 2, height / 2, height * 0.9);
    v.addColorStop(0, 'rgba(0,0,0,0)');
    v.addColorStop(1, 'rgba(0,0,0,.28)');
    g.fillStyle = v;
    g.fillRect(0, 0, width, height);
    bitmap = off;
    cache.set(key, off);
  }
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const g2 = canvas.getContext('2d');
  g2.drawImage(bitmap, 0, 0);
  return canvas;
}

export const WORLD_IDS = Object.keys(PAINTERS);
