// A faithful JS port of rblxx/gameserver/physics.py.
// Keeping the two in lock-step is what makes client prediction feel right —
// the same inputs produce the same positions on both sides.

export const STEP_HEIGHT = 2.6;
export const GROUND_EPS = 0.06;
const MAX_SPEED = 260;
const AIR_CONTROL = 0.42;
const FRICTION_GROUND = 11.0;
const FRICTION_AIR = 0.35;
const ACCEL_GROUND = 90.0;
const ACCEL_AIR = 34.0;
const CELL = 32;

export class CollisionWorld {
  constructor(parts, { voidY = -120, gravityScale = 1 } = {}) {
    this.boxes = [];
    this.damageBoxes = [];
    this.tagIndex = new Map();
    this.disabled = new Set();
    this.grid = new Map();
    this.voidY = voidY;
    this.gravityScale = gravityScale;
    for (const part of parts) this.addPart(part);
    this.rebuildGrid();
  }

  addPart(part) {
    const [px, py, pz] = part.p;
    let [sx, sy, sz] = part.s;
    if (part.k === 'sphere' || part.k === 'cone') {
      sx *= 0.82; sy *= 0.82; sz *= 0.82;
    }
    const box = {
      minx: px - sx / 2, miny: py - sy / 2, minz: pz - sz / 2,
      maxx: px + sx / 2, maxy: py + sy / 2, maxz: pz + sz / 2,
      tag: part.x || null, solid: !part.n, damage: part.d || 0,
    };
    if (box.damage) this.damageBoxes.push(box);
    if (!box.solid) return;
    const i = this.boxes.length;
    this.boxes.push(box);
    if (box.tag) {
      if (!this.tagIndex.has(box.tag)) this.tagIndex.set(box.tag, []);
      this.tagIndex.get(box.tag).push(i);
    }
  }

  rebuildGrid() {
    this.grid.clear();
    for (let i = 0; i < this.boxes.length; i++) {
      const b = this.boxes[i];
      for (let gx = Math.floor(b.minx / CELL); gx <= Math.floor(b.maxx / CELL); gx++) {
        for (let gz = Math.floor(b.minz / CELL); gz <= Math.floor(b.maxz / CELL); gz++) {
          const key = gx * 100003 + gz;
          let bucket = this.grid.get(key);
          if (!bucket) { bucket = []; this.grid.set(key, bucket); }
          bucket.push(i);
        }
      }
    }
  }

  setTagEnabled(tag, enabled) {
    if (enabled) this.disabled.delete(tag); else this.disabled.add(tag);
  }

  *candidates(minx, minz, maxx, maxz) {
    const seen = new Set();
    for (let gx = Math.floor(minx / CELL); gx <= Math.floor(maxx / CELL); gx++) {
      for (let gz = Math.floor(minz / CELL); gz <= Math.floor(maxz / CELL); gz++) {
        const bucket = this.grid.get(gx * 100003 + gz);
        if (!bucket) continue;
        for (const i of bucket) {
          if (seen.has(i)) continue;
          seen.add(i);
          yield i;
        }
      }
    }
  }

  overlaps(minx, miny, minz, maxx, maxy, maxz) {
    for (const i of this.candidates(minx, minz, maxx, maxz)) {
      const b = this.boxes[i];
      if (b.tag && this.disabled.has(b.tag)) continue;
      if (minx < b.maxx && maxx > b.minx && miny < b.maxy && maxy > b.miny
          && minz < b.maxz && maxz > b.minz) return true;
    }
    return false;
  }

  damageAt(minx, miny, minz, maxx, maxy, maxz) {
    let worst = 0;
    for (const b of this.damageBoxes) {
      if (b.tag && this.disabled.has(b.tag)) continue;
      if (minx < b.maxx && maxx > b.minx && miny < b.maxy && maxy > b.miny
          && minz < b.maxz && maxz > b.minz) worst = Math.max(worst, b.damage);
    }
    return worst;
  }

  groundHeight(x, z, fromY, radius = 1, drop = 200) {
    let best = -Infinity;
    const minx = x - radius, maxx = x + radius;
    const minz = z - radius, maxz = z + radius;
    for (const i of this.candidates(minx, minz, maxx, maxz)) {
      const b = this.boxes[i];
      if (b.tag && this.disabled.has(b.tag)) continue;
      if (minx < b.maxx && maxx > b.minx && minz < b.maxz && maxz > b.minz) {
        if (b.maxy <= fromY + 0.5 && b.maxy > best && b.maxy > fromY - drop) {
          best = b.maxy;
        }
      }
    }
    return best === -Infinity ? null : best;
  }

  raycast(ox, oy, oz, dx, dy, dz, maxDist) {
    const ex = ox + dx * maxDist, ez = oz + dz * maxDist;
    let bestT = maxDist, bestN = null, bestTag = null, bestBox = null;
    const inv = [
      Math.abs(dx) > 1e-9 ? 1 / dx : Infinity,
      Math.abs(dy) > 1e-9 ? 1 / dy : Infinity,
      Math.abs(dz) > 1e-9 ? 1 / dz : Infinity,
    ];
    for (const i of this.candidates(Math.min(ox, ex) - 1, Math.min(oz, ez) - 1,
                                    Math.max(ox, ex) + 1, Math.max(oz, ez) + 1)) {
      const b = this.boxes[i];
      if (b.tag && this.disabled.has(b.tag)) continue;
      let tmin = 0, tmax = bestT, axis = -1, dead = false;
      const slabs = [
        [ox, inv[0], b.minx, b.maxx], [oy, inv[1], b.miny, b.maxy],
        [oz, inv[2], b.minz, b.maxz],
      ];
      for (let k = 0; k < 3; k++) {
        const [o, invD, lo, hi] = slabs[k];
        if (invD === Infinity) {
          if (o < lo || o > hi) { dead = true; break; }
          continue;
        }
        let t1 = (lo - o) * invD, t2 = (hi - o) * invD;
        if (t1 > t2) { const t = t1; t1 = t2; t2 = t; }
        if (t1 > tmin) { tmin = t1; axis = k; }
        if (t2 < tmax) tmax = t2;
        if (tmin > tmax) { dead = true; break; }
      }
      if (!dead && tmin < bestT && tmin >= 0) {
        bestT = tmin;
        bestTag = b.tag;
        bestBox = b;
        const n = [0, 0, 0];
        if (axis >= 0) n[axis] = [dx, dy, dz][axis] > 0 ? -1 : 1;
        bestN = n;
      }
    }
    return bestN ? { t: bestT, normal: bestN, tag: bestTag, box: bestBox } : null;
  }
}

export function makeState(x = 0, y = 0, z = 0, radius = 1.4, height = 5) {
  return { x, y, z, vx: 0, vy: 0, vz: 0, onGround: false, radius, height,
           lastGroundY: y, stepPhase: 0 };
}

function aabb(st, x, y, z) {
  x = x === undefined ? st.x : x;
  y = y === undefined ? st.y : y;
  z = z === undefined ? st.z : z;
  const r = st.radius;
  return [x - r, y, z - r, x + r, y + st.height, z + r];
}

export function moveCharacter(st, world, wishX, wishZ, dt,
                              { wantJump = false, speed = 16, jumpPower = 32,
                                gravity = 68 } = {}) {
  const events = { landed: false, jumped: false, fallDistance: 0 };
  let wlen = Math.hypot(wishX, wishZ);
  if (wlen > 1) { wishX /= wlen; wishZ /= wlen; wlen = 1; }

  const accel = st.onGround ? ACCEL_GROUND : ACCEL_AIR;
  const control = st.onGround ? 1 : AIR_CONTROL;
  const targetVx = wishX * speed, targetVz = wishZ * speed;
  const k = Math.min(1, accel * control * dt / Math.max(speed, 1) * 8);
  st.vx += (targetVx - st.vx) * k;
  st.vz += (targetVz - st.vz) * k;

  if (wlen < 0.01) {
    const f = st.onGround ? FRICTION_GROUND : FRICTION_AIR;
    const damp = Math.max(0, 1 - f * dt);
    st.vx *= damp; st.vz *= damp;
  }

  if (wantJump && st.onGround) {
    st.vy = jumpPower;
    st.onGround = false;
    events.jumped = true;
  }
  if (!st.onGround || st.vy > 0) st.vy -= gravity * dt;
  st.vy = Math.max(-MAX_SPEED, Math.min(MAX_SPEED, st.vy));

  const wasAirborne = !st.onGround;
  const topBefore = st.y;
  integrate(st, world, dt);
  if (st.onGround && wasAirborne) {
    events.landed = true;
    events.fallDistance = Math.max(0, st.lastGroundY - st.y);
  }
  if (st.onGround) st.lastGroundY = st.y;
  else st.lastGroundY = Math.max(st.lastGroundY, topBefore);

  st.stepPhase = (st.stepPhase + Math.hypot(st.vx, st.vz) * dt * 0.55) % (Math.PI * 2);
  return events;
}

function integrate(st, world, dt) {
  const dx = st.vx * dt;
  if (dx) {
    const nx = st.x + dx;
    if (world.overlaps(...aabb(st, nx, undefined, undefined))) {
      if (!tryStep(st, world, nx, st.z)) {
        st.x = resolveAxis(st, world, 'x', dx);
        st.vx = 0;
      } else st.x = nx;
    } else st.x = nx;
  }
  const dz = st.vz * dt;
  if (dz) {
    const nz = st.z + dz;
    if (world.overlaps(...aabb(st, undefined, undefined, nz))) {
      if (!tryStep(st, world, st.x, nz)) {
        st.z = resolveAxis(st, world, 'z', dz);
        st.vz = 0;
      } else st.z = nz;
    } else st.z = nz;
  }
  const dy = st.vy * dt;
  st.onGround = false;
  if (dy) {
    const ny = st.y + dy;
    if (world.overlaps(...aabb(st, undefined, ny, undefined))) {
      st.y = resolveAxis(st, world, 'y', dy);
      if (dy < 0) st.onGround = true;
      st.vy = 0;
    } else st.y = ny;
  }
  if (!st.onGround && st.vy <= 0.01) {
    const probe = st.y - GROUND_EPS * 4;
    if (world.overlaps(...aabb(st, undefined, probe, undefined))) {
      const top = world.groundHeight(st.x, st.z, st.y + 0.4, st.radius);
      if (top !== null && st.y - top < 0.5) {
        st.y = top;
        st.onGround = true;
        if (st.vy < 0) st.vy = 0;
      }
    }
  }
}

function resolveAxis(st, world, axis, delta) {
  let lo = 0, hi = delta;
  const base = st[axis];
  for (let i = 0; i < 7; i++) {
    const mid = (lo + hi) / 2;
    const probe = axis === 'x' ? aabb(st, base + mid, undefined, undefined)
      : axis === 'y' ? aabb(st, undefined, base + mid, undefined)
        : aabb(st, undefined, undefined, base + mid);
    if (world.overlaps(...probe)) hi = mid; else lo = mid;
  }
  if (Math.abs(lo) <= 1e-6) return base;
  return base + lo - (delta > 0 ? GROUND_EPS : -GROUND_EPS) * 0.5;
}

function tryStep(st, world, nx, nz) {
  if (!st.onGround && st.vy < -6) return false;
  for (const lift of [0.7, 1.4, 2.0, STEP_HEIGHT]) {
    const y = st.y + lift;
    if (!world.overlaps(...aabb(st, nx, y, nz))) {
      const top = world.groundHeight(nx, nz, y + 0.2, st.radius);
      if (top !== null && top - st.y <= STEP_HEIGHT + 0.05) {
        st.y = Math.max(st.y, top);
        return true;
      }
      st.y = y;
      return true;
    }
  }
  return false;
}
