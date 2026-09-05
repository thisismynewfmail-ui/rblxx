// Every surface in RBLXX is drawn procedurally onto a canvas at load time —
// no image assets, no network round-trips, and it all works offline.

function surface(size = 128) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const g = c.getContext('2d');
  g.imageSmoothingEnabled = true;
  return { c, g, size };
}

function rng(seed) {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13; s >>>= 0;
    s ^= s >> 17;
    s ^= s << 5; s >>>= 0;
    return s / 4294967296;
  };
}

function noise(g, size, seed, amount, scale = 1) {
  const r = rng(seed);
  const img = g.getImageData(0, 0, size, size);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const n = (r() - 0.5) * amount * 255;
    d[i] = Math.max(0, Math.min(255, d[i] + n));
    d[i + 1] = Math.max(0, Math.min(255, d[i + 1] + n));
    d[i + 2] = Math.max(0, Math.min(255, d[i + 2] + n));
  }
  g.putImageData(img, 0, 0);
}

function blobs(g, size, seed, count, radius, color, alpha) {
  const r = rng(seed);
  g.save();
  g.globalAlpha = alpha;
  g.fillStyle = color;
  for (let i = 0; i < count; i++) {
    const x = r() * size, y = r() * size, rad = radius * (0.4 + r());
    for (const [ox, oy] of [[0, 0], [size, 0], [-size, 0], [0, size], [0, -size]]) {
      g.beginPath();
      g.arc(x + ox, y + oy, rad, 0, Math.PI * 2);
      g.fill();
    }
  }
  g.restore();
}

// ---------------------------------------------------------------- surfaces
const MAKERS = {
  smooth(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
    noise(g, size, 7, 0.035);
    const grd = g.createLinearGradient(0, 0, 0, size);
    grd.addColorStop(0, 'rgba(255,255,255,0.06)');
    grd.addColorStop(1, 'rgba(0,0,0,0.05)');
    g.fillStyle = grd; g.fillRect(0, 0, size, size);
  },
  studs(s) {
    const { g, size } = s;
    MAKERS.smooth(s);
    const cx = size / 2, cy = size / 2, r = size * 0.24;
    const grd = g.createRadialGradient(cx - r * 0.35, cy - r * 0.35, r * 0.1,
      cx, cy, r);
    grd.addColorStop(0, 'rgba(255,255,255,0.85)');
    grd.addColorStop(0.55, 'rgba(255,255,255,0.12)');
    grd.addColorStop(0.86, 'rgba(0,0,0,0.10)');
    grd.addColorStop(1, 'rgba(0,0,0,0.30)');
    g.fillStyle = grd;
    g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.fill();
    g.strokeStyle = 'rgba(0,0,0,0.22)'; g.lineWidth = size * 0.014;
    g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.stroke();
    g.strokeStyle = 'rgba(255,255,255,0.45)'; g.lineWidth = size * 0.01;
    g.beginPath(); g.arc(cx - r * 0.12, cy - r * 0.14, r * 0.62, Math.PI * 0.9,
      Math.PI * 1.75); g.stroke();
  },
  inlet(s) {
    const { g, size } = s;
    MAKERS.smooth(s);
    const cx = size / 2, cy = size / 2, r = size * 0.26;
    g.strokeStyle = 'rgba(0,0,0,0.22)'; g.lineWidth = size * 0.03;
    g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.stroke();
  },
  grass(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
    blobs(g, size, 11, 90, size * 0.045, '#000000', 0.06);
    blobs(g, size, 23, 70, size * 0.035, '#ffffff', 0.10);
    const r = rng(31);
    g.strokeStyle = 'rgba(0,0,0,0.13)'; g.lineWidth = 1;
    for (let i = 0; i < 220; i++) {
      const x = r() * size, y = r() * size, h = 2 + r() * 4;
      g.beginPath(); g.moveTo(x, y); g.lineTo(x + (r() - 0.5) * 2, y - h); g.stroke();
    }
    noise(g, size, 99, 0.09);
  },
  brick(s) {
    const { g, size } = s;
    g.fillStyle = '#e8e8e8'; g.fillRect(0, 0, size, size);
    const rows = 4, h = size / rows;
    const r = rng(5);
    for (let row = 0; row < rows; row++) {
      const offset = (row % 2) * (size / 4);
      for (let col = -1; col < 3; col++) {
        const x = col * (size / 2) + offset + 2;
        const y = row * h + 2;
        const w = size / 2 - 4;
        g.fillStyle = `rgba(255,255,255,${0.55 + r() * 0.4})`;
        g.fillRect(x, y, w, h - 4);
        g.fillStyle = 'rgba(0,0,0,0.08)';
        g.fillRect(x, y + h - 7, w, 3);
      }
    }
    g.strokeStyle = 'rgba(0,0,0,0.30)'; g.lineWidth = 2;
    for (let row = 0; row <= rows; row++) {
      g.beginPath(); g.moveTo(0, row * h); g.lineTo(size, row * h); g.stroke();
    }
    for (let row = 0; row < rows; row++) {
      const offset = (row % 2) * (size / 4);
      for (let col = -1; col < 3; col++) {
        const x = col * (size / 2) + offset;
        g.beginPath(); g.moveTo(x, row * h); g.lineTo(x, (row + 1) * h); g.stroke();
      }
    }
    noise(g, size, 17, 0.06);
  },
  metal(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
    const r = rng(41);
    for (let i = 0; i < 260; i++) {
      g.strokeStyle = `rgba(0,0,0,${r() * 0.09})`;
      g.lineWidth = r() * 1.6;
      const y = r() * size;
      g.beginPath(); g.moveTo(0, y); g.lineTo(size, y + (r() - 0.5) * 3); g.stroke();
    }
    g.strokeStyle = 'rgba(0,0,0,0.20)'; g.lineWidth = 3;
    g.strokeRect(1.5, 1.5, size - 3, size - 3);
    for (const [x, y] of [[9, 9], [size - 9, 9], [9, size - 9], [size - 9, size - 9]]) {
      g.fillStyle = 'rgba(0,0,0,0.22)';
      g.beginPath(); g.arc(x, y, 3.2, 0, Math.PI * 2); g.fill();
      g.fillStyle = 'rgba(255,255,255,0.5)';
      g.beginPath(); g.arc(x - 0.8, y - 0.8, 1.6, 0, Math.PI * 2); g.fill();
    }
  },
  wood(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
    const r = rng(61);
    for (let i = 0; i < 26; i++) {
      g.strokeStyle = `rgba(0,0,0,${0.05 + r() * 0.12})`;
      g.lineWidth = 1 + r() * 3;
      const x = r() * size;
      g.beginPath();
      g.moveTo(x, 0);
      g.bezierCurveTo(x + (r() - 0.5) * 12, size / 3, x + (r() - 0.5) * 12,
        size * 2 / 3, x + (r() - 0.5) * 8, size);
      g.stroke();
    }
    for (let i = 0; i < 3; i++) {
      const x = r() * size, y = r() * size;
      g.strokeStyle = 'rgba(0,0,0,0.16)';
      for (let k = 1; k < 5; k++) {
        g.lineWidth = 1;
        g.beginPath(); g.ellipse(x, y, k * 2.6, k * 1.6, 0.4, 0, Math.PI * 2); g.stroke();
      }
    }
    noise(g, size, 71, 0.05);
  },
  plank(s) {
    const { g, size } = s;
    MAKERS.wood(s);
    g.strokeStyle = 'rgba(0,0,0,0.32)'; g.lineWidth = 2.5;
    for (let i = 0; i <= 3; i++) {
      const y = (i * size) / 3;
      g.beginPath(); g.moveTo(0, y); g.lineTo(size, y); g.stroke();
    }
    g.fillStyle = 'rgba(0,0,0,0.28)';
    const r = rng(83);
    for (let i = 0; i < 3; i++) {
      for (const x of [size * 0.18, size * 0.82]) {
        g.beginPath();
        g.arc(x + r() * 4, (i + 0.5) * size / 3, 2.2, 0, Math.PI * 2);
        g.fill();
      }
    }
  },
  glass(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
    const grd = g.createLinearGradient(0, 0, size, size);
    grd.addColorStop(0, 'rgba(255,255,255,0.9)');
    grd.addColorStop(0.45, 'rgba(255,255,255,0.35)');
    grd.addColorStop(0.55, 'rgba(255,255,255,0.85)');
    grd.addColorStop(1, 'rgba(255,255,255,0.4)');
    g.fillStyle = grd; g.fillRect(0, 0, size, size);
    g.strokeStyle = 'rgba(0,0,0,0.25)'; g.lineWidth = 4;
    g.strokeRect(2, 2, size - 4, size - 4);
  },
  lava(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
    blobs(g, size, 13, 26, size * 0.16, '#000000', 0.28);
    blobs(g, size, 29, 40, size * 0.06, '#ffffff', 0.55);
    const r = rng(37);
    g.strokeStyle = 'rgba(0,0,0,0.35)';
    for (let i = 0; i < 16; i++) {
      g.lineWidth = 1 + r() * 3;
      g.beginPath();
      let x = r() * size, y = r() * size;
      g.moveTo(x, y);
      for (let k = 0; k < 5; k++) {
        x += (r() - 0.5) * 40; y += (r() - 0.5) * 40;
        g.lineTo(x, y);
      }
      g.stroke();
    }
    noise(g, size, 43, 0.14);
  },
  water(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
    for (let i = 0; i < 9; i++) {
      g.strokeStyle = `rgba(255,255,255,${0.10 + i * 0.02})`;
      g.lineWidth = 2 + (i % 3);
      g.beginPath();
      for (let x = 0; x <= size; x += 4) {
        const y = size * (i / 9) + Math.sin((x / size) * Math.PI * 4 + i) * 4;
        x === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
      }
      g.stroke();
    }
    blobs(g, size, 19, 20, size * 0.1, '#000000', 0.05);
  },
  concrete(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
    blobs(g, size, 3, 160, size * 0.028, '#000000', 0.05);
    blobs(g, size, 53, 90, size * 0.02, '#ffffff', 0.12);
    noise(g, size, 67, 0.1);
  },
  sand(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
    noise(g, size, 89, 0.16);
    for (let i = 0; i < 6; i++) {
      g.strokeStyle = 'rgba(0,0,0,0.05)'; g.lineWidth = 5;
      g.beginPath();
      for (let x = 0; x <= size; x += 6) {
        const y = (i / 6) * size + Math.sin(x / 14 + i) * 5;
        x === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
      }
      g.stroke();
    }
  },
  snow(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
    blobs(g, size, 101, 60, size * 0.06, '#ffffff', 0.5);
    blobs(g, size, 103, 40, size * 0.03, '#cfe4f5', 0.4);
    noise(g, size, 107, 0.05);
  },
  neon(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
  },
  tile(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
    noise(g, size, 109, 0.03);
    g.strokeStyle = 'rgba(0,0,0,0.20)'; g.lineWidth = 2;
    for (let i = 0; i <= 2; i++) {
      const p = (i * size) / 2;
      g.beginPath(); g.moveTo(p, 0); g.lineTo(p, size); g.stroke();
      g.beginPath(); g.moveTo(0, p); g.lineTo(size, p); g.stroke();
    }
    g.fillStyle = 'rgba(255,255,255,0.35)';
    for (let a = 0; a < 2; a++) for (let b = 0; b < 2; b++) {
      if ((a + b) % 2 === 0) g.fillRect(a * size / 2 + 2, b * size / 2 + 2,
        size / 2 - 4, size / 2 - 4);
    }
  },
  rock(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
    const r = rng(127);
    for (let i = 0; i < 40; i++) {
      g.fillStyle = `rgba(${r() > 0.5 ? 0 : 255},${r() > 0.5 ? 0 : 255},${r() > 0.5 ? 0 : 255},${r() * 0.10})`;
      g.beginPath();
      const x = r() * size, y = r() * size, n = 5 + Math.floor(r() * 3);
      for (let k = 0; k <= n; k++) {
        const a = (k / n) * Math.PI * 2;
        const rad = size * (0.04 + r() * 0.06);
        const px = x + Math.cos(a) * rad, py = y + Math.sin(a) * rad;
        k === 0 ? g.moveTo(px, py) : g.lineTo(px, py);
      }
      g.closePath(); g.fill();
    }
    noise(g, size, 131, 0.14);
  },
  circuit(s) {
    const { g, size } = s;
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, size, size);
    const r = rng(149);
    g.strokeStyle = 'rgba(0,0,0,0.30)';
    for (let i = 0; i < 22; i++) {
      g.lineWidth = 1 + r() * 2;
      let x = Math.floor(r() * 8) * (size / 8);
      let y = Math.floor(r() * 8) * (size / 8);
      g.beginPath(); g.moveTo(x, y);
      for (let k = 0; k < 4; k++) {
        if (r() > 0.5) x += (r() > 0.5 ? 1 : -1) * (size / 8);
        else y += (r() > 0.5 ? 1 : -1) * (size / 8);
        g.lineTo(x, y);
      }
      g.stroke();
      g.fillStyle = 'rgba(0,0,0,0.35)';
      g.beginPath(); g.arc(x, y, 2.4, 0, Math.PI * 2); g.fill();
    }
  },
};

// Which side texture pairs with which top texture.
const PAIRS = {
  studs: ['studs', 'smooth'],
  plank: ['plank', 'wood'],
};

const DEFAULT_TILE = {
  studs: 2.0, smooth: 8, grass: 6, brick: 8, metal: 6, wood: 5, glass: 6,
  lava: 10, water: 12, concrete: 8, sand: 8, snow: 8, neon: 4, plank: 5,
  tile: 8, rock: 10, circuit: 8,
};

export const TEXTURE_NAMES = Object.keys(DEFAULT_TILE);

export function buildSurfaceTextures(ctx, glHelpers) {
  const out = {};
  for (const name of TEXTURE_NAMES) {
    const maker = MAKERS[name] || MAKERS.smooth;
    const [topName, sideName] = PAIRS[name] || [name, name];
    const topSurf = surface(128);
    (MAKERS[topName] || maker)(topSurf);
    const sideSurf = surface(128);
    (MAKERS[sideName] || maker)(sideSurf);
    out[name] = {
      name,
      top: glHelpers.texture2D(ctx, topSurf.c, { mipmap: true }),
      side: glHelpers.texture2D(ctx, sideSurf.c, { mipmap: true }),
      tile: DEFAULT_TILE[name],
      transparent: name === 'glass' || name === 'water',
    };
  }
  return out;
}

// ---------------------------------------------------------------- faces
export const FACE_IDS = ['smile', 'cheeky', 'shades', 'angry', 'surprised',
  'chill', 'robot', 'cat', 'winky', 'epic', 'dizzy', 'visor'];

export function drawFace(g, size, id) {
  g.clearRect(0, 0, size, size);
  const u = size / 100;
  g.lineCap = 'round';
  g.lineJoin = 'round';
  g.strokeStyle = '#1a1a1a';
  g.fillStyle = '#1a1a1a';
  const eye = (x, y, r) => { g.beginPath(); g.arc(x * u, y * u, r * u, 0, Math.PI * 2); g.fill(); };
  const smile = (w, d, y) => {
    g.lineWidth = 4.5 * u;
    g.beginPath();
    g.arc(50 * u, y * u, w * u, Math.PI * 0.18, Math.PI * 0.82);
    g.stroke();
  };
  switch (id) {
    case 'cheeky':
      eye(33, 40, 6); eye(67, 40, 6);
      g.lineWidth = 4.5 * u;
      g.beginPath(); g.arc(50 * u, 52 * u, 22 * u, Math.PI * 0.1, Math.PI * 0.7); g.stroke();
      break;
    case 'shades':
      g.fillStyle = '#15151a';
      g.beginPath(); g.roundRect(20 * u, 30 * u, 26 * u, 16 * u, 4 * u); g.fill();
      g.beginPath(); g.roundRect(54 * u, 30 * u, 26 * u, 16 * u, 4 * u); g.fill();
      g.lineWidth = 4 * u; g.strokeStyle = '#15151a';
      g.beginPath(); g.moveTo(46 * u, 36 * u); g.lineTo(54 * u, 36 * u); g.stroke();
      g.fillStyle = 'rgba(255,255,255,0.35)';
      g.beginPath(); g.moveTo(24 * u, 44 * u); g.lineTo(36 * u, 32 * u);
      g.lineTo(41 * u, 32 * u); g.lineTo(29 * u, 44 * u); g.closePath(); g.fill();
      g.fillStyle = '#1a1a1a'; smile(18, 0, 56);
      break;
    case 'angry':
      g.lineWidth = 6 * u;
      g.beginPath(); g.moveTo(24 * u, 30 * u); g.lineTo(42 * u, 38 * u); g.stroke();
      g.beginPath(); g.moveTo(76 * u, 30 * u); g.lineTo(58 * u, 38 * u); g.stroke();
      eye(33, 45, 5.5); eye(67, 45, 5.5);
      g.lineWidth = 4.5 * u;
      g.beginPath(); g.arc(50 * u, 74 * u, 16 * u, Math.PI * 1.2, Math.PI * 1.8); g.stroke();
      break;
    case 'surprised':
      eye(33, 40, 8); eye(67, 40, 8);
      g.beginPath(); g.ellipse(50 * u, 64 * u, 9 * u, 12 * u, 0, 0, Math.PI * 2); g.fill();
      break;
    case 'chill':
      g.lineWidth = 5 * u;
      g.beginPath(); g.arc(33 * u, 42 * u, 8 * u, Math.PI, Math.PI * 2); g.stroke();
      g.beginPath(); g.arc(67 * u, 42 * u, 8 * u, Math.PI, Math.PI * 2); g.stroke();
      smile(16, 0, 56);
      break;
    case 'robot':
      g.fillStyle = '#2ad6ff';
      g.fillRect(24 * u, 34 * u, 20 * u, 10 * u);
      g.fillRect(56 * u, 34 * u, 20 * u, 10 * u);
      g.fillStyle = '#1a1a1a';
      for (let i = 0; i < 6; i++) g.fillRect((30 + i * 7) * u, 62 * u, 4 * u, 8 * u);
      g.fillRect(26 * u, 58 * u, 48 * u, 3 * u);
      g.fillRect(26 * u, 72 * u, 48 * u, 3 * u);
      break;
    case 'cat':
      g.lineWidth = 5 * u;
      g.beginPath(); g.arc(33 * u, 44 * u, 7 * u, Math.PI * 1.1, Math.PI * 1.9); g.stroke();
      g.beginPath(); g.arc(67 * u, 44 * u, 7 * u, Math.PI * 1.1, Math.PI * 1.9); g.stroke();
      g.lineWidth = 4 * u;
      g.beginPath(); g.moveTo(44 * u, 60 * u); g.quadraticCurveTo(50 * u, 66 * u, 56 * u, 60 * u); g.stroke();
      g.beginPath(); g.moveTo(50 * u, 63 * u); g.lineTo(50 * u, 58 * u); g.stroke();
      g.lineWidth = 2.6 * u;
      for (const s of [-1, 1]) for (let i = 0; i < 3; i++) {
        g.beginPath();
        g.moveTo((50 + s * 10) * u, (58 + i * 4) * u);
        g.lineTo((50 + s * 34) * u, (52 + i * 7) * u);
        g.stroke();
      }
      break;
    case 'winky':
      eye(33, 40, 6);
      g.lineWidth = 5 * u;
      g.beginPath(); g.arc(67 * u, 44 * u, 8 * u, Math.PI * 1.15, Math.PI * 1.85); g.stroke();
      smile(18, 0, 54);
      break;
    case 'epic':
      g.lineWidth = 6 * u;
      g.beginPath(); g.moveTo(22 * u, 32 * u); g.lineTo(44 * u, 40 * u); g.stroke();
      g.beginPath(); g.moveTo(78 * u, 32 * u); g.lineTo(56 * u, 40 * u); g.stroke();
      eye(34, 47, 5); eye(66, 47, 5);
      g.fillStyle = '#1a1a1a';
      g.beginPath();
      g.moveTo(24 * u, 62 * u);
      g.quadraticCurveTo(50 * u, 92 * u, 76 * u, 62 * u);
      g.quadraticCurveTo(50 * u, 72 * u, 24 * u, 62 * u);
      g.closePath(); g.fill();
      g.fillStyle = '#ffffff';
      g.beginPath();
      g.moveTo(30 * u, 65 * u); g.lineTo(70 * u, 65 * u);
      g.lineTo(66 * u, 72 * u); g.lineTo(34 * u, 72 * u);
      g.closePath(); g.fill();
      break;
    case 'dizzy':
      g.lineWidth = 4 * u; g.strokeStyle = '#1a1a1a';
      for (const cx of [33, 67]) {
        g.beginPath();
        for (let a = 0; a < Math.PI * 4; a += 0.2) {
          const r = (a / (Math.PI * 4)) * 9 * u;
          const x = cx * u + Math.cos(a) * r, y = 42 * u + Math.sin(a) * r;
          a === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
        }
        g.stroke();
      }
      g.beginPath(); g.ellipse(50 * u, 68 * u, 10 * u, 7 * u, 0, 0, Math.PI * 2); g.stroke();
      break;
    case 'visor':
      g.fillStyle = '#12151b';
      g.beginPath(); g.roundRect(14 * u, 30 * u, 72 * u, 22 * u, 8 * u); g.fill();
      const grd = g.createLinearGradient(14 * u, 0, 86 * u, 0);
      grd.addColorStop(0, '#00e5ff'); grd.addColorStop(0.5, '#7cffd4');
      grd.addColorStop(1, '#00e5ff');
      g.fillStyle = grd;
      g.beginPath(); g.roundRect(20 * u, 36 * u, 60 * u, 8 * u, 4 * u); g.fill();
      break;
    default: // smile
      eye(33, 40, 6.5); eye(67, 40, 6.5);
      smile(20, 0, 54);
  }
}

export function faceTexture(ctx, glHelpers, id) {
  const s = surface(128);
  drawFace(s.g, s.size, id);
  return glHelpers.texture2D(ctx, s.c, { mipmap: true, repeat: false,
                                         flipY: false });
}

// ---------------------------------------------------------------- clothing
export const PATTERNS = {
  jersey(g, S) {
    g.fillStyle = 'rgba(255,255,255,0)'; g.fillRect(0, 0, S, S);
    g.fillStyle = 'rgba(255,255,255,0.85)';
    g.fillRect(S * 0.40, 0, S * 0.20, S * 0.30);
    g.fillStyle = 'rgba(0,0,0,0.16)';
    g.fillRect(0, S * 0.86, S, S * 0.14);
    g.fillStyle = 'rgba(255,255,255,0.7)';
    g.font = `bold ${S * 0.3}px Verdana, sans-serif`;
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('7', S / 2, S * 0.6);
  },
  hoodie(g, S) {
    g.fillStyle = 'rgba(0,0,0,0.18)';
    g.fillRect(S * 0.46, 0, S * 0.08, S);
    g.fillRect(S * 0.16, S * 0.60, S * 0.68, S * 0.22);
    g.strokeStyle = 'rgba(255,255,255,0.5)'; g.lineWidth = S * 0.03;
    g.beginPath();
    g.moveTo(S * 0.38, S * 0.06); g.quadraticCurveTo(S * 0.5, S * 0.24, S * 0.62, S * 0.06);
    g.stroke();
  },
  tuxedo(g, S) {
    g.fillStyle = 'rgba(255,255,255,0.95)';
    g.beginPath();
    g.moveTo(S * 0.36, 0); g.lineTo(S * 0.64, 0);
    g.lineTo(S * 0.58, S); g.lineTo(S * 0.42, S); g.closePath(); g.fill();
    g.fillStyle = 'rgba(20,20,25,0.9)';
    g.beginPath(); g.moveTo(S * 0.36, 0); g.lineTo(S * 0.5, S * 0.42);
    g.lineTo(S * 0.30, S * 0.30); g.closePath(); g.fill();
    g.beginPath(); g.moveTo(S * 0.64, 0); g.lineTo(S * 0.5, S * 0.42);
    g.lineTo(S * 0.70, S * 0.30); g.closePath(); g.fill();
    g.fillStyle = '#8f1d3f';
    g.beginPath(); g.moveTo(S * 0.44, S * 0.10); g.lineTo(S * 0.56, S * 0.10);
    g.lineTo(S * 0.5, S * 0.22); g.closePath(); g.fill();
  },
  hivis(g, S) {
    g.fillStyle = 'rgba(255,255,255,0.9)';
    g.fillRect(0, S * 0.42, S, S * 0.12);
    g.fillStyle = 'rgba(160,160,160,0.9)';
    g.fillRect(0, S * 0.56, S, S * 0.06);
    g.fillStyle = 'rgba(0,0,0,0.25)';
    g.fillRect(S * 0.46, 0, S * 0.08, S);
  },
  labcoat(g, S) {
    g.fillStyle = 'rgba(0,0,0,0.14)';
    g.fillRect(S * 0.47, 0, S * 0.06, S);
    g.fillRect(S * 0.12, S * 0.58, S * 0.20, S * 0.20);
    g.fillRect(S * 0.68, S * 0.58, S * 0.20, S * 0.20);
    g.fillStyle = '#2f7fd6'; g.fillRect(S * 0.70, S * 0.54, S * 0.04, S * 0.12);
  },
  stripes(g, S) {
    g.fillStyle = 'rgba(0,0,0,0.55)';
    for (let i = 0; i < 5; i++) g.fillRect(0, (i * 2 + 1) * S / 10, S, S / 10);
  },
  denim(g, S) {
    g.strokeStyle = 'rgba(0,0,0,0.10)'; g.lineWidth = 1;
    for (let i = 0; i < S; i += 3) {
      g.beginPath(); g.moveTo(i, 0); g.lineTo(i, S); g.stroke();
      g.beginPath(); g.moveTo(0, i); g.lineTo(S, i); g.stroke();
    }
    g.strokeStyle = '#e8c46a'; g.lineWidth = S * 0.012;
    g.setLineDash([S * 0.03, S * 0.03]);
    g.beginPath(); g.moveTo(S * 0.42, 0); g.lineTo(S * 0.42, S); g.stroke();
    g.beginPath(); g.moveTo(S * 0.58, 0); g.lineTo(S * 0.58, S); g.stroke();
    g.setLineDash([]);
  },
  astro(g, S) {
    g.strokeStyle = 'rgba(0,0,0,0.18)'; g.lineWidth = S * 0.02;
    for (let i = 1; i < 6; i++) {
      g.beginPath(); g.moveTo(0, i * S / 6); g.lineTo(S, i * S / 6); g.stroke();
    }
    g.fillStyle = '#c8372c'; g.fillRect(S * 0.10, S * 0.12, S * 0.16, S * 0.10);
    g.fillStyle = '#2f7fd6'; g.fillRect(S * 0.74, S * 0.12, S * 0.16, S * 0.10);
  },
  buxlogo(g, S) {
    g.fillStyle = '#f2c53d';
    g.save();
    g.translate(S / 2, S / 2); g.rotate(Math.PI / 4);
    g.fillRect(-S * 0.18, -S * 0.18, S * 0.36, S * 0.36);
    g.restore();
    g.fillStyle = '#111418';
    g.font = `bold ${S * 0.22}px Verdana, sans-serif`;
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('B', S / 2, S / 2);
  },
  plaid(g, S) {
    g.fillStyle = 'rgba(0,0,0,0.28)';
    for (let i = 0; i < 4; i++) {
      g.fillRect(i * S / 4, 0, S * 0.06, S);
      g.fillRect(0, i * S / 4, S, S * 0.06);
    }
    g.fillStyle = 'rgba(255,255,255,0.22)';
    for (let i = 0; i < 4; i++) {
      g.fillRect(i * S / 4 + S * 0.12, 0, S * 0.03, S);
      g.fillRect(0, i * S / 4 + S * 0.12, S, S * 0.03);
    }
  },
  hazmat(g, S) {
    g.fillStyle = 'rgba(0,0,0,0.35)';
    g.beginPath(); g.arc(S / 2, S * 0.55, S * 0.20, 0, Math.PI * 2); g.fill();
    g.fillStyle = 'rgba(255,255,255,0.85)';
    for (let i = 0; i < 3; i++) {
      g.save();
      g.translate(S / 2, S * 0.55); g.rotate((i * Math.PI * 2) / 3);
      g.beginPath(); g.moveTo(0, -S * 0.06);
      g.arc(0, 0, S * 0.18, -1.0, -0.15); g.closePath(); g.fill();
      g.restore();
    }
    g.strokeStyle = 'rgba(0,0,0,0.3)'; g.lineWidth = S * 0.03;
    g.beginPath(); g.moveTo(0, S * 0.16); g.lineTo(S, S * 0.16); g.stroke();
  },
  cargo(g, S) {
    g.fillStyle = 'rgba(0,0,0,0.16)';
    g.fillRect(S * 0.06, S * 0.34, S * 0.26, S * 0.26);
    g.fillRect(S * 0.68, S * 0.34, S * 0.26, S * 0.26);
    g.strokeStyle = 'rgba(0,0,0,0.24)'; g.lineWidth = S * 0.02;
    g.strokeRect(S * 0.06, S * 0.34, S * 0.26, S * 0.26);
    g.strokeRect(S * 0.68, S * 0.34, S * 0.26, S * 0.26);
  },
  track(g, S) {
    g.fillStyle = 'rgba(255,255,255,0.85)';
    g.fillRect(S * 0.06, 0, S * 0.05, S);
    g.fillRect(S * 0.89, 0, S * 0.05, S);
  },
  camo(g, S) {
    const r = rng(211);
    for (let i = 0; i < 26; i++) {
      g.fillStyle = ['rgba(0,0,0,0.30)', 'rgba(255,255,255,0.20)',
        'rgba(80,60,30,0.35)'][i % 3];
      g.beginPath();
      const x = r() * S, y = r() * S, n = 6;
      for (let k = 0; k <= n; k++) {
        const a = (k / n) * Math.PI * 2;
        const rad = S * (0.06 + r() * 0.10);
        const px = x + Math.cos(a) * rad, py = y + Math.sin(a) * rad;
        k === 0 ? g.moveTo(px, py) : g.lineTo(px, py);
      }
      g.closePath(); g.fill();
    }
  },
  ripped(g, S) {
    PATTERNS.denim(g, S);
    g.fillStyle = 'rgba(0,0,0,0.45)';
    g.fillRect(S * 0.18, S * 0.34, S * 0.24, S * 0.07);
    g.fillRect(S * 0.60, S * 0.56, S * 0.22, S * 0.06);
  },
  neon(g, S) {
    g.strokeStyle = 'rgba(255,255,255,0.75)'; g.lineWidth = S * 0.035;
    for (let i = 0; i < 5; i++) {
      g.beginPath();
      g.moveTo(0, i * S / 5); g.lineTo(S, i * S / 5 + S * 0.1); g.stroke();
    }
  },
};

export function patternTexture(ctx, glHelpers, id) {
  const s = surface(128);
  const fn = PATTERNS[id];
  if (!fn) return null;
  s.g.clearRect(0, 0, s.size, s.size);
  fn(s.g, s.size);
  return glHelpers.texture2D(ctx, s.c, { mipmap: true, repeat: false,
                                         flipY: false });
}

// ---------------------------------------------------------------- sky
export const SKY_PRESETS = {
  classic: { top: '#2c6cc4', horizon: '#a8d2ee', ground: '#6f9cbb',
             cloud: 0.55, sun: '#fff8dc', sunPos: [0.38, 0.84, 0.38] },
  dawn: { top: '#2f5fa8', horizon: '#ffd9a0', ground: '#8f9fb8',
          cloud: 0.42, sun: '#fff0c0', sunPos: [0.30, 0.78, -0.55] },
  overcast: { top: '#63788c', horizon: '#b6c4d1', ground: '#8b98a4',
              cloud: 0.45, sun: '#e8eef5', sunPos: [-0.35, 0.8, 0.42] },
  ember: { top: '#2a0d14', horizon: '#b8481a', ground: '#3d150c',
           cloud: 0.22, sun: '#ff9a3c', sunPos: [0.5, 0.42, -0.6] },
  void: { top: '#05070b', horizon: '#0d1119', ground: '#05070b',
          cloud: 0.0, sun: '#2d3b52', sunPos: [0.2, 0.9, 0.35] },
  studio: { top: '#dbe8f4', horizon: '#f4f8fc', ground: '#b9c9d8',
            cloud: 0.0, sun: '#ffffff', sunPos: [0.42, 0.86, 0.5] },
};

export function skyTexture(ctx, glHelpers, presetName) {
  const p = SKY_PRESETS[presetName] || SKY_PRESETS.classic;
  const W = 1024, H = 512;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  const grd = g.createLinearGradient(0, 0, 0, H);
  grd.addColorStop(0, p.top);
  grd.addColorStop(0.30, p.top);
  grd.addColorStop(0.47, p.horizon);
  grd.addColorStop(0.53, p.horizon);
  grd.addColorStop(1, p.ground);
  g.fillStyle = grd;
  g.fillRect(0, 0, W, H);

  if (p.cloud > 0) {
    const r = rng(1234);
    g.save();
    g.globalCompositeOperation = 'lighter';
    for (let layer = 0; layer < 3; layer++) {
      const alpha = p.cloud * (0.055 + layer * 0.028);
      const scale = 1 + layer * 0.7;
      for (let i = 0; i < 130; i++) {
        const x = r() * W;
        const y = r() * H * 0.46;
        const w = (30 + r() * 130) * scale;
        const h = (8 + r() * 26) * scale * (0.4 + y / (H * 0.46));
        const grad = g.createRadialGradient(x, y, 0, x, y, w);
        grad.addColorStop(0, `rgba(255,255,255,${alpha})`);
        grad.addColorStop(1, 'rgba(255,255,255,0)');
        g.fillStyle = grad;
        g.beginPath(); g.ellipse(x, y, w, h, 0, 0, Math.PI * 2); g.fill();
      }
    }
    g.restore();
    g.save();
    g.globalCompositeOperation = 'multiply';
    const r2 = rng(4321);
    for (let i = 0; i < 70; i++) {
      const x = r2() * W, y = r2() * H * 0.42;
      const w = 40 + r2() * 120, h = 10 + r2() * 24;
      const grad = g.createRadialGradient(x, y, 0, x, y, w);
      grad.addColorStop(0, `rgba(140,150,170,${0.10 * p.cloud})`);
      grad.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = grad;
      g.beginPath(); g.ellipse(x, y, w, h, 0, 0, Math.PI * 2); g.fill();
    }
    g.restore();
  }

  // sun disc, placed from the preset direction
  const dir = p.sunPos;
  const az = Math.atan2(dir[0], -dir[2]);
  const el = Math.asin(Math.max(-1, Math.min(1, dir[1])));
  const sx = ((az / (Math.PI * 2)) + 0.5) * W;
  const sy = (0.5 - el / Math.PI) * H;
  const sun = g.createRadialGradient(sx, sy, 0, sx, sy, 100);
  sun.addColorStop(0, p.sun);
  sun.addColorStop(0.11, p.sun);
  sun.addColorStop(0.34, 'rgba(255,246,214,0.40)');
  sun.addColorStop(1, 'rgba(255,246,214,0)');
  g.fillStyle = sun;
  g.beginPath(); g.arc(sx, sy, 100, 0, Math.PI * 2); g.fill();

  if (presetName === 'void') {
    const r3 = rng(777);
    for (let i = 0; i < 500; i++) {
      const x = r3() * W, y = r3() * H;
      g.fillStyle = `rgba(255,255,255,${0.2 + r3() * 0.7})`;
      g.fillRect(x, y, 1.2, 1.2);
    }
  }
  return glHelpers.texture2D(ctx, c, { mipmap: true, repeat: true,
                                       flipY: false });
}

// ---------------------------------------------------------------- signs
export function signTexture(ctx, glHelpers, text, color) {
  const W = 512, H = 128;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  g.fillStyle = 'rgba(12,14,18,0.86)';
  g.fillRect(0, 0, W, H);
  g.strokeStyle = color; g.lineWidth = 8;
  g.strokeRect(4, 4, W - 8, H - 8);
  g.fillStyle = color;
  g.font = `bold ${Math.min(72, 760 / Math.max(6, text.length))}px Verdana, sans-serif`;
  g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(text, W / 2, H / 2 + 3);
  return glHelpers.texture2D(ctx, c, { mipmap: true, repeat: false,
                                       flipY: false });
}
