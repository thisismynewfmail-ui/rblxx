"""Authoritative movement + collision.

Everything is an axis-aligned box, which keeps the simulation cheap, exactly
reproducible on the client (for prediction) and true to the blocky aesthetic.
A uniform grid broadphase keeps per-tick cost flat even on the larger maps.
"""
from __future__ import annotations

import math

from .. import config

STEP_HEIGHT = 2.6           # auto-climb: stairs & small ledges
GROUND_EPS = 0.06
MAX_SPEED = 260.0
AIR_CONTROL = 0.42
FRICTION_GROUND = 11.0
FRICTION_AIR = 0.35
ACCEL_GROUND = 90.0
ACCEL_AIR = 34.0
CELL = 32.0


class CollisionWorld:
    """Uniform-grid broadphase over static AABBs."""

    __slots__ = ("boxes", "grid", "void_y", "gravity_scale", "damage_boxes",
                 "tagged", "disabled")

    def __init__(self, colliders, *, void_y=-120.0, gravity_scale=1.0):
        self.boxes: list[tuple] = []
        self.damage_boxes: list[tuple] = []
        self.tagged: dict[str, list[int]] = {}
        self.void_y = void_y
        self.gravity_scale = gravity_scale
        self.disabled: set[str] = set()
        self.grid: dict[tuple[int, int], list[int]] = {}
        for c in colliders:
            minx, miny, minz, maxx, maxy, maxz, dmg, tag, passthrough = c
            if dmg:
                self.damage_boxes.append((minx, miny, minz, maxx, maxy, maxz,
                                          dmg, tag))
            if passthrough:
                continue
            idx = len(self.boxes)
            self.boxes.append((minx, miny, minz, maxx, maxy, maxz, tag))
            if tag:
                self.tagged.setdefault(tag, []).append(idx)
            for gx in range(int(math.floor(minx / CELL)),
                            int(math.floor(maxx / CELL)) + 1):
                for gz in range(int(math.floor(minz / CELL)),
                                int(math.floor(maxz / CELL)) + 1):
                    self.grid.setdefault((gx, gz), []).append(idx)

    # -- queries -----------------------------------------------------------
    def candidates(self, minx, minz, maxx, maxz):
        seen = set()
        for gx in range(int(math.floor(minx / CELL)),
                        int(math.floor(maxx / CELL)) + 1):
            for gz in range(int(math.floor(minz / CELL)),
                            int(math.floor(maxz / CELL)) + 1):
                bucket = self.grid.get((gx, gz))
                if bucket:
                    seen.update(bucket)
        return seen

    def overlaps(self, minx, miny, minz, maxx, maxy, maxz) -> bool:
        dis = self.disabled
        for i in self.candidates(minx, minz, maxx, maxz):
            b = self.boxes[i]
            if b[6] is not None and b[6] in dis:
                continue
            if (minx < b[3] and maxx > b[0] and miny < b[4] and maxy > b[1]
                    and minz < b[5] and maxz > b[2]):
                return True
        return False

    def boxes_with_tag(self, tag: str):
        return [self.boxes[i] for i in self.tagged.get(tag, ())]

    def set_tag_enabled(self, tag: str, enabled: bool):
        if enabled:
            self.disabled.discard(tag)
        else:
            self.disabled.add(tag)

    def damage_at(self, minx, miny, minz, maxx, maxy, maxz) -> float:
        worst = 0.0
        for b in self.damage_boxes:
            if b[7] is not None and b[7] in self.disabled:
                continue
            if (minx < b[3] and maxx > b[0] and miny < b[4] and maxy > b[1]
                    and minz < b[5] and maxz > b[2]):
                worst = max(worst, b[6])
        return worst

    def raycast(self, origin, direction, max_dist: float):
        """Slab test against every candidate box along the ray's footprint.

        Returns (distance, normal, tag) or None.
        """
        ox, oy, oz = origin
        dx, dy, dz = direction
        ex, ez = ox + dx * max_dist, oz + dz * max_dist
        best_t = max_dist
        best_n = None
        best_tag = None
        inv = (1.0 / dx if abs(dx) > 1e-9 else math.inf,
               1.0 / dy if abs(dy) > 1e-9 else math.inf,
               1.0 / dz if abs(dz) > 1e-9 else math.inf)
        dis = self.disabled
        for i in self.candidates(min(ox, ex) - 1, min(oz, ez) - 1,
                                 max(ox, ex) + 1, max(oz, ez) + 1):
            b = self.boxes[i]
            if b[6] is not None and b[6] in dis:
                continue
            tmin, tmax = 0.0, best_t
            hit_axis = -1
            for axis, (o, d, inv_d, lo, hi) in enumerate((
                    (ox, dx, inv[0], b[0], b[3]),
                    (oy, dy, inv[1], b[1], b[4]),
                    (oz, dz, inv[2], b[2], b[5]))):
                if inv_d == math.inf:
                    if o < lo or o > hi:
                        tmin = math.inf
                        break
                    continue
                t1 = (lo - o) * inv_d
                t2 = (hi - o) * inv_d
                if t1 > t2:
                    t1, t2 = t2, t1
                if t1 > tmin:
                    tmin = t1
                    hit_axis = axis
                tmax = min(tmax, t2)
                if tmin > tmax:
                    tmin = math.inf
                    break
            if tmin < best_t and tmin != math.inf and tmin >= 0:
                best_t = tmin
                best_tag = b[6]
                n = [0.0, 0.0, 0.0]
                if hit_axis >= 0:
                    comp = (dx, dy, dz)[hit_axis]
                    n[hit_axis] = -1.0 if comp > 0 else 1.0
                best_n = n
        if best_n is None:
            return None
        return best_t, best_n, best_tag

    def ground_height(self, x, z, from_y, radius=1.0, drop=200.0):
        """Highest solid top below from_y within the column."""
        best = -math.inf
        minx, maxx = x - radius, x + radius
        minz, maxz = z - radius, z + radius
        dis = self.disabled
        for i in self.candidates(minx, minz, maxx, maxz):
            b = self.boxes[i]
            if b[6] is not None and b[6] in dis:
                continue
            if minx < b[3] and maxx > b[0] and minz < b[5] and maxz > b[2]:
                if b[4] <= from_y + 0.5 and b[4] > best and b[4] > from_y - drop:
                    best = b[4]
        return None if best == -math.inf else best


class MoveState:
    """Mutable kinematic state for one character."""
    __slots__ = ("x", "y", "z", "vx", "vy", "vz", "on_ground", "radius",
                 "height", "last_ground_y", "step_phase", "in_water")

    def __init__(self, x=0.0, y=0.0, z=0.0,
                 radius=config.PLAYER_RADIUS, height=config.PLAYER_HEIGHT):
        self.x, self.y, self.z = x, y, z
        self.vx = self.vy = self.vz = 0.0
        self.on_ground = False
        self.radius = radius
        self.height = height
        self.last_ground_y = y
        self.step_phase = 0.0
        self.in_water = False

    def aabb(self, x=None, y=None, z=None):
        x = self.x if x is None else x
        y = self.y if y is None else y
        z = self.z if z is None else z
        r = self.radius
        return (x - r, y, z - r, x + r, y + self.height, z + r)


def move_character(state: MoveState, world: CollisionWorld, wish_dir,
                   dt: float, *, want_jump: bool, speed: float,
                   jump_power: float, gravity: float,
                   fly: bool = False, wish_up: float = 0.0) -> dict:
    """Advance one character by dt.  Returns an event dict."""
    events = {"landed": False, "jumped": False, "fall_distance": 0.0}

    wx, wz = wish_dir
    wlen = math.hypot(wx, wz)
    if wlen > 1.0:
        wx, wz = wx / wlen, wz / wlen
        wlen = 1.0

    if fly:
        state.vx = wx * speed
        state.vz = wz * speed
        state.vy = wish_up * speed
        _integrate(state, world, dt)
        return events

    # --- acceleration -----------------------------------------------------
    accel = ACCEL_GROUND if state.on_ground else ACCEL_AIR
    control = 1.0 if state.on_ground else AIR_CONTROL
    target_vx, target_vz = wx * speed, wz * speed
    state.vx += (target_vx - state.vx) * min(1.0, accel * control * dt / max(speed, 1.0) * 8.0)
    state.vz += (target_vz - state.vz) * min(1.0, accel * control * dt / max(speed, 1.0) * 8.0)

    # --- friction ---------------------------------------------------------
    if wlen < 0.01:
        f = FRICTION_GROUND if state.on_ground else FRICTION_AIR
        damp = max(0.0, 1.0 - f * dt)
        state.vx *= damp
        state.vz *= damp

    # --- jump -------------------------------------------------------------
    if want_jump and state.on_ground:
        state.vy = jump_power
        state.on_ground = False
        events["jumped"] = True

    # --- gravity ----------------------------------------------------------
    if not state.on_ground or state.vy > 0:
        state.vy -= gravity * dt
    state.vy = max(-MAX_SPEED, min(MAX_SPEED, state.vy))

    was_airborne = not state.on_ground
    top_before = state.y
    _integrate(state, world, dt)
    if state.on_ground and was_airborne:
        events["landed"] = True
        events["fall_distance"] = max(0.0, state.last_ground_y - state.y)
    if state.on_ground:
        state.last_ground_y = state.y
    else:
        state.last_ground_y = max(state.last_ground_y, top_before)

    horiz = math.hypot(state.vx, state.vz)
    state.step_phase = (state.step_phase + horiz * dt * 0.55) % (math.pi * 2)
    return events


def _integrate(state: MoveState, world: CollisionWorld, dt: float):
    """Swept axis-by-axis resolution with a step-up assist."""
    # ---- X ----
    dx = state.vx * dt
    if dx:
        nx = state.x + dx
        if world.overlaps(*state.aabb(x=nx)):
            if not _try_step(state, world, nx, state.z):
                state.x = _resolve_axis(state, world, "x", dx)
                state.vx = 0.0
            else:
                state.x = nx
        else:
            state.x = nx

    # ---- Z ----
    dz = state.vz * dt
    if dz:
        nz = state.z + dz
        if world.overlaps(*state.aabb(z=nz)):
            if not _try_step(state, world, state.x, nz):
                state.z = _resolve_axis(state, world, "z", dz)
                state.vz = 0.0
            else:
                state.z = nz
        else:
            state.z = nz

    # ---- Y ----
    dy = state.vy * dt
    state.on_ground = False
    if dy:
        ny = state.y + dy
        if world.overlaps(*state.aabb(y=ny)):
            state.y = _resolve_axis(state, world, "y", dy)
            if dy < 0:
                state.on_ground = True
            state.vy = 0.0
        else:
            state.y = ny

    # ---- ground probe (keeps players glued to floors on slopes/steps) ----
    if not state.on_ground and state.vy <= 0.01:
        probe = state.y - GROUND_EPS * 4
        if world.overlaps(*state.aabb(y=probe)):
            top = world.ground_height(state.x, state.z, state.y + 0.4,
                                      state.radius)
            if top is not None and state.y - top < 0.5:
                state.y = top
                state.on_ground = True
                if state.vy < 0:
                    state.vy = 0.0


def _resolve_axis(state: MoveState, world: CollisionWorld, axis: str,
                  delta: float) -> float:
    """Binary-search the furthest non-penetrating position on one axis."""
    lo, hi = 0.0, delta
    base = getattr(state, axis)
    for _ in range(7):
        mid = (lo + hi) / 2
        kw = {axis: base + mid}
        if world.overlaps(*state.aabb(**kw)):
            hi = mid
        else:
            lo = mid
    result = base + lo
    # nudge out of contact
    return result - (GROUND_EPS if delta > 0 else -GROUND_EPS) * 0.5 \
        if abs(lo) > 1e-6 else base


def _try_step(state: MoveState, world: CollisionWorld, nx: float,
              nz: float) -> bool:
    """Attempt to climb a ledge of up to STEP_HEIGHT at the new position."""
    if not state.on_ground and state.vy < -6.0:
        return False
    for lift in (0.7, 1.4, 2.0, STEP_HEIGHT):
        y = state.y + lift
        if not world.overlaps(*state.aabb(x=nx, y=y, z=nz)):
            top = world.ground_height(nx, nz, y + 0.2, state.radius)
            if top is not None and top - state.y <= STEP_HEIGHT + 0.05:
                state.y = max(state.y, top)
                return True
            state.y = y
            return True
    return False


def sphere_cast_players(origin, direction, max_dist, players, *,
                        ignore=None, radius=config.PLAYER_RADIUS,
                        height=config.PLAYER_HEIGHT):
    """Ray vs. player capsule-ish AABBs.  Returns (dist, player, headshot)."""
    ox, oy, oz = origin
    dx, dy, dz = direction
    best = None
    for p in players:
        if p is ignore or not p.alive:
            continue
        px, py, pz = p.state.x, p.state.y, p.state.z
        minx, maxx = px - radius, px + radius
        miny, maxy = py, py + height
        minz, maxz = pz - radius, pz + radius
        tmin, tmax = 0.0, max_dist
        ok = True
        for o, d, lo, hi in ((ox, dx, minx, maxx), (oy, dy, miny, maxy),
                             (oz, dz, minz, maxz)):
            if abs(d) < 1e-9:
                if o < lo or o > hi:
                    ok = False
                    break
                continue
            t1, t2 = (lo - o) / d, (hi - o) / d
            if t1 > t2:
                t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                ok = False
                break
        if ok and 0 <= tmin < (best[0] if best else max_dist):
            hit_y = oy + dy * tmin
            headshot = hit_y >= py + height - 1.35
            best = (tmin, p, headshot)
    return best
