// Tracers, sparks, explosions and floating combat text.

const GRAVITY = 52;

export const WEAPON_SKINS = {
  default: { body: '#3a3f47', accent: '#22262c', metal: '#9aa2ab', glow: 0 },
  gold: { body: '#e8b93d', accent: '#8a6a12', metal: '#ffe9a8', glow: 0.18 },
  neon: { body: '#1b2030', accent: '#0f1320', metal: '#2ad6ff', glow: 0.55 },
  wood: { body: '#8a6231', accent: '#5b4020', metal: '#b8bcc4', glow: 0 },
  paintball: { body: '#d8433c', accent: '#2f7fd6', metal: '#f2c53d', glow: 0.05 },
  carbon: { body: '#22252b', accent: '#14161a', metal: '#6f7885', glow: 0 },
  frost: { body: '#bfe6ff', accent: '#7fb3d8', metal: '#eaf7ff', glow: 0.25 },
};

export class Effects {
  constructor(renderer) {
    this.r = renderer;
    this.particles = [];
    this.tracers = [];
    this.blasts = [];
    this.decals = [];
    this.shake = 0;
    this.shakeVec = [0, 0];
  }

  addShake(amount) { this.shake = Math.min(1.4, this.shake + amount); }

  tracer(origin, dir, length, color, width = 0.10, life = 0.055) {
    this.tracers.push({ o: origin.slice(), d: dir.slice(), l: length,
                        c: color, w: width, life, max: life });
  }

  spark(x, y, z, normal, color = '#ffd98a', count = 7, speed = 22) {
    for (let i = 0; i < count; i++) {
      const nx = normal ? normal[0] : 0, ny = normal ? normal[1] : 1,
        nz = normal ? normal[2] : 0;
      this.particles.push({
        x, y, z,
        vx: nx * speed * (0.4 + Math.random()) + (Math.random() - 0.5) * speed,
        vy: ny * speed * (0.4 + Math.random()) + (Math.random() - 0.2) * speed,
        vz: nz * speed * (0.4 + Math.random()) + (Math.random() - 0.5) * speed,
        life: 0.28 + Math.random() * 0.3, max: 0.55,
        size: 0.10 + Math.random() * 0.22, c: color, g: 1, glow: 0.9,
      });
    }
  }

  debris(x, y, z, color, count = 10, speed = 16, size = 0.5) {
    for (let i = 0; i < count; i++) {
      this.particles.push({
        x, y, z,
        vx: (Math.random() - 0.5) * speed * 2,
        vy: Math.random() * speed * 1.6,
        vz: (Math.random() - 0.5) * speed * 2,
        life: 0.6 + Math.random() * 0.7, max: 1.3,
        size: size * (0.5 + Math.random()), c: color, g: 1, glow: 0,
        spin: (Math.random() - 0.5) * 12,
      });
    }
  }

  blood(x, y, z, color = '#c8372c') {
    for (let i = 0; i < 9; i++) {
      this.particles.push({
        x, y, z,
        vx: (Math.random() - 0.5) * 14,
        vy: Math.random() * 12,
        vz: (Math.random() - 0.5) * 14,
        life: 0.35 + Math.random() * 0.3, max: 0.65,
        size: 0.18 + Math.random() * 0.2, c: color, g: 1, glow: 0.1,
      });
    }
  }

  explosion(x, y, z, radius = 20, color = '#ff8a4c') {
    this.blasts.push({ x, y, z, r: radius, life: 0.55, max: 0.55, c: color });
    this.debris(x, y, z, '#5a4a3a', 16, radius * 0.9, radius * 0.05);
    this.spark(x, y, z, [0, 1, 0], '#ffd98a', 18, radius * 1.2);
    this.addShake(0.7);
  }

  muzzle(x, y, z, dir, color = '#ffe27a', scale = 1) {
    this.particles.push({
      x: x + dir[0] * 0.7, y: y + dir[1] * 0.7, z: z + dir[2] * 0.7,
      vx: dir[0] * 3, vy: dir[1] * 3, vz: dir[2] * 3,
      life: 0.05, max: 0.05, size: 0.85 * scale, c: color, g: 0, glow: 1,
      flash: true,
    });
  }

  update(dt) {
    this.shake = Math.max(0, this.shake - dt * 3.2);
    const s = this.shake * this.shake;
    this.shakeVec[0] = (Math.random() - 0.5) * s * 0.05;
    this.shakeVec[1] = (Math.random() - 0.5) * s * 0.05;

    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.life -= dt;
      if (p.life <= 0) { this.particles.splice(i, 1); continue; }
      if (p.g) p.vy -= GRAVITY * dt;
      p.x += p.vx * dt; p.y += p.vy * dt; p.z += p.vz * dt;
      p.vx *= 0.985; p.vz *= 0.985;
    }
    for (let i = this.tracers.length - 1; i >= 0; i--) {
      this.tracers[i].life -= dt;
      if (this.tracers[i].life <= 0) this.tracers.splice(i, 1);
    }
    for (let i = this.blasts.length - 1; i >= 0; i--) {
      this.blasts[i].life -= dt;
      if (this.blasts[i].life <= 0) this.blasts.splice(i, 1);
    }
    if (this.particles.length > 900) {
      this.particles.splice(0, this.particles.length - 900);
    }
  }

  draw() {
    const r = this.r;
    for (const t of this.tracers) {
      const a = t.life / t.max;
      const mx = t.o[0] + t.d[0] * t.l * 0.5;
      const my = t.o[1] + t.d[1] * t.l * 0.5;
      const mz = t.o[2] + t.d[2] * t.l * 0.5;
      const yaw = Math.atan2(-t.d[0], -t.d[2]);
      const pitch = Math.asin(Math.max(-1, Math.min(1, t.d[1])));
      r.add('dynamic', 'box', 'neon', mx, my, mz, t.w, t.w, t.l, t.c,
            { ry: yaw, rx: -pitch, glow: 1, alpha: 0.35 + a * 0.55 });
    }
    for (const p of this.particles) {
      const a = Math.max(0, p.life / p.max);
      const size = p.size * (p.flash ? (0.6 + a * 1.6) : (0.4 + a * 0.9));
      r.add('dynamic', p.flash ? 'sphere' : 'box', 'neon', p.x, p.y, p.z,
            size, size, size, p.c,
            { glow: p.glow, alpha: Math.min(1, a * 1.6),
              ry: p.spin ? p.spin * (1 - a) : 0 });
    }
    for (const b of this.blasts) {
      const a = b.life / b.max;
      const grow = (1 - a) ** 0.55;
      const rad = b.r * (0.35 + grow * 1.15);
      r.add('dynamic', 'sphere', 'neon', b.x, b.y, b.z, rad, rad, rad, b.c,
            { glow: 1, alpha: a * 0.55 });
      r.add('dynamic', 'sphere', 'neon', b.x, b.y, b.z, rad * 0.6, rad * 0.6,
            rad * 0.6, '#fff2c8', { glow: 1, alpha: a * 0.7 });
    }
  }
}
