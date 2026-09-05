"""Enemy AI: navigation-graph pathing + steering for the Outbreak world."""
from __future__ import annotations

import heapq
import math
import random
import time

from .physics import move_character


class NavGraph:
    """Sparse waypoint graph with line-of-sight edges."""

    def __init__(self, points, world, max_edge=42.0):
        self.points = [tuple(p) for p in points]
        self.edges: list[list[tuple[int, float]]] = [[] for _ in self.points]
        for i, a in enumerate(self.points):
            for j in range(i + 1, len(self.points)):
                b = self.points[j]
                dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                if dist > max_edge or dist < 0.01:
                    continue
                if self._clear(a, b, world, dist):
                    self.edges[i].append((j, dist))
                    self.edges[j].append((i, dist))

    @staticmethod
    def _clear(a, b, world, dist) -> bool:
        ax, ay, az = a[0], a[1] + 2.6, a[2]
        dx = (b[0] - a[0]) / dist
        dy = (b[1] - a[1]) / dist
        dz = (b[2] - a[2]) / dist
        for lateral in (-1.4, 0.0, 1.4):
            # offset perpendicular in the XZ plane so we require some width
            px, pz = -dz * lateral, dx * lateral
            hit = world.raycast((ax + px, ay, az + pz), (dx, dy, dz),
                                dist - 0.5)
            if hit is not None:
                return False
        return True

    def nearest(self, pos, limit=90.0) -> int | None:
        best, best_d = None, limit * limit
        for i, p in enumerate(self.points):
            dx, dy, dz = p[0] - pos[0], p[1] - pos[1], p[2] - pos[2]
            d = dx * dx + dy * dy * 0.4 + dz * dz
            if d < best_d:
                best, best_d = i, d
        return best

    def path(self, start_pos, goal_pos) -> list[tuple]:
        s = self.nearest(start_pos)
        g = self.nearest(goal_pos)
        if s is None or g is None:
            return []
        if s == g:
            return [self.points[g]]
        pts = self.points
        gx, gy, gz = pts[g]

        def h(i):
            p = pts[i]
            return math.dist((p[0], p[1], p[2]), (gx, gy, gz))

        open_heap = [(h(s), 0.0, s)]
        came: dict[int, int] = {}
        best_g = {s: 0.0}
        seen = set()
        while open_heap:
            _, gcost, node = heapq.heappop(open_heap)
            if node in seen:
                continue
            seen.add(node)
            if node == g:
                break
            for nxt, w in self.edges[node]:
                ng = gcost + w
                if ng < best_g.get(nxt, math.inf):
                    best_g[nxt] = ng
                    came[nxt] = node
                    heapq.heappush(open_heap, (ng + h(nxt), ng, nxt))
        if g not in came and g != s:
            return []
        out = [g]
        while out[-1] != s:
            out.append(came[out[-1]])
        out.reverse()
        return [pts[i] for i in out[1:]]


class EnemyBrain:
    """Steering + attack behaviour applied to an Enemy each tick."""

    ATTACK_RANGE = 6.2
    ATTACK_COOLDOWN = 1.15
    REPATH_INTERVAL = 0.8
    LOSE_TARGET = 220.0

    def __init__(self, nav: NavGraph, world, rng: random.Random):
        self.nav = nav
        self.world = world
        self.rng = rng

    def update(self, enemy, players, dt: float, now: float, room):
        if not enemy.alive:
            return
        st = enemy.state

        target = self._choose_target(enemy, players)
        if target is None:
            enemy.target_id = None
            move_character(st, self.world, (0.0, 0.0), dt, want_jump=False,
                           speed=0.0, jump_power=0.0,
                           gravity=self.world.gravity_scale * 68.0)
            return
        enemy.target_id = target.id

        tx, ty, tz = target.state.x, target.state.y, target.state.z
        dx, dz = tx - st.x, tz - st.z
        flat = math.hypot(dx, dz)

        if now >= enemy.stagger_until:
            # --- direct line of sight? then just charge ---
            direct = self._can_see(enemy, target, flat)
            if direct:
                enemy.path = []
                wish = (dx / (flat or 1), dz / (flat or 1))
            else:
                if now >= enemy.repath_at or not enemy.path:
                    enemy.repath_at = now + self.REPATH_INTERVAL + \
                        self.rng.random() * 0.4
                    enemy.path = self.nav.path((st.x, st.y, st.z),
                                               (tx, ty, tz))
                    enemy.path_index = 0
                wish = self._follow_path(enemy)

            # --- separation from other enemies so they don't stack ---
            sx = sz = 0.0
            for other in room.enemies.values():
                if other is enemy or not other.alive:
                    continue
                ox, oz = st.x - other.state.x, st.z - other.state.z
                d2 = ox * ox + oz * oz
                if 0.01 < d2 < 36.0:
                    inv = 1.0 / math.sqrt(d2)
                    sx += ox * inv
                    sz += oz * inv
            if sx or sz:
                wish = (wish[0] + sx * 0.55, wish[1] + sz * 0.55)

            want_jump = False
            if flat < 60 and st.on_ground:
                ahead = self.world.overlaps(
                    st.x + wish[0] * 2.2 - st.radius, st.y + 0.4,
                    st.z + wish[1] * 2.2 - st.radius,
                    st.x + wish[0] * 2.2 + st.radius, st.y + 3.0,
                    st.z + wish[1] * 2.2 + st.radius)
                if ahead or (ty - st.y > 3.0 and flat < 22):
                    want_jump = True

            speed = enemy.speed * (0.55 if enemy.boss and flat < 12 else 1.0)
            move_character(st, self.world, wish, dt, want_jump=want_jump,
                           speed=speed, jump_power=34.0,
                           gravity=self.world.gravity_scale * 68.0)
            enemy.yaw = math.atan2(-wish[0], -wish[1]) if (wish[0] or wish[1]) \
                else enemy.yaw
            enemy.anim = (enemy.anim + dt * speed * 0.35) % 6.283
        else:
            move_character(st, self.world, (0, 0), dt, want_jump=False,
                           speed=0.0, jump_power=0.0,
                           gravity=self.world.gravity_scale * 68.0)

        # --- attack ---
        dist3 = math.dist((st.x, st.y, st.z), (tx, ty, tz))
        if dist3 <= self.ATTACK_RANGE + (1.6 if enemy.boss else 0.0) and \
                now >= enemy.attack_at:
            enemy.attack_at = now + self.ATTACK_COOLDOWN
            room.enemy_attack(enemy, target)

    def _choose_target(self, enemy, players):
        st = enemy.state
        best, best_d = None, self.LOSE_TARGET ** 2
        for p in players:
            if not p.alive or p.spectating:
                continue
            if getattr(p, "downed_at", 0):
                weight = 2.6          # deprioritise but still finish them
            else:
                weight = 1.0
            d = ((p.state.x - st.x) ** 2 + (p.state.y - st.y) ** 2 * 0.6 +
                 (p.state.z - st.z) ** 2) * weight
            if d < best_d:
                best, best_d = p, d
        return best

    def _can_see(self, enemy, target, flat) -> bool:
        if flat > 130:
            return False
        st = enemy.state
        ox, oy, oz = st.x, st.y + st.height * 0.7, st.z
        tx, ty, tz = target.state.x, target.state.y + 2.6, target.state.z
        dx, dy, dz = tx - ox, ty - oy, tz - oz
        dist = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        hit = self.world.raycast((ox, oy, oz),
                                 (dx / dist, dy / dist, dz / dist), dist - 1.0)
        return hit is None

    def _follow_path(self, enemy):
        st = enemy.state
        while enemy.path_index < len(enemy.path):
            wx, wy, wz = enemy.path[enemy.path_index]
            dx, dz = wx - st.x, wz - st.z
            if dx * dx + dz * dz < 64.0 and abs(wy - st.y) < 14:
                enemy.path_index += 1
                continue
            d = math.hypot(dx, dz) or 1.0
            return (dx / d, dz / d)
        enemy.path = []
        return (0.0, 0.0)
