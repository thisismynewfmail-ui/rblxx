"""The authoritative room simulation for one world instance."""
from __future__ import annotations

import json
import math
import random
import time
import typing as t

from .. import config
from ..security.sanitize import clean_text, filter_chat, looks_like_spam
from . import weapons as wp
from .ai import EnemyBrain, NavGraph
from .entity import (BTN_ADS, BTN_CROUCH, BTN_FIRE, BTN_JUMP, BTN_SPRINT,
                     BTN_USE, EFFECTS, Enemy, Player)
from .physics import CollisionWorld, MoveState, move_character, \
    sphere_cast_players
from .worlds import TEAM_COLORS, get_world

PICKUP_RADIUS = 5.2
PICKUP_EFFECTS = {
    "health": {"heal": 45, "color": "#ff5b6e", "label": "Health"},
    "armor":  {"armor": 60, "color": "#8fd8ff", "label": "Armour"},
    "ammo":   {"ammo": 1.0, "color": "#f2c53d", "label": "Ammo"},
    "speed":  {"effect": "speed", "color": "#38d0ff", "label": "Speed Coil"},
    "gravity": {"effect": "gravity", "color": "#b58cff",
                "label": "Gravity Coil"},
    "damage": {"effect": "damage", "color": "#ff7a2a", "label": "Damage Boost"},
}
LAUNCH_IMPULSE = 78.0
ZIP_SPEED = 62.0
TURRET_RANGE = 150.0
TURRET_DAMAGE = 7.5
TURRET_INTERVAL = 0.55
SPAWN_PROTECT = 2.4


class Room:
    """Everything that happens inside one world, on one node process."""

    def __init__(self, world_id: str, *, on_stat=None):
        self.world_id = world_id
        self.world = get_world(world_id)
        if self.world is None:
            raise ValueError(f"unknown world {world_id}")
        self.level = self.world.level()
        self.level_dict = self.level.to_dict()
        self.collision = CollisionWorld(
            self.level.colliders(), void_y=self.level.void_y,
            gravity_scale=self.level.gravity_scale)
        self.rng = random.Random(f"{world_id}:{time.time()}")

        self.players: dict[int, Player] = {}
        self.enemies: dict[int, Enemy] = {}
        self.projectiles: dict[int, wp.Projectile] = {}
        self.next_player_id = 1
        self.tick_no = 0
        self.started = time.time()
        self.now = self.started
        self.on_stat = on_stat

        self.mode = self.world.mode_class(self)
        self.mode.start()

        # dynamic parts
        self.inactive_tags: set[str] = set()
        self.pending_parts: list[tuple[float, str, bool]] = []
        self.lava_y: float | None = None

        # pickups
        self.pickup_state = {
            p["id"]: {"def": p, "ready_at": 0.0, "active": True}
            for p in self.level.pickups
        }
        self.launch_pads = [b for b in self.collision.boxes_with_tag("launch")]
        self.ziplines = [o for o in self.level.objectives
                         if o["kind"] == "zipline"]
        self.turrets = [dict(o, next_fire=0.0) for o in self.level.objectives
                        if o["kind"] == "turret"]

        # navigation (only built when the mode actually needs it)
        self.nav: NavGraph | None = None
        self.brain: EnemyBrain | None = None
        if self.level.navpoints:
            self.nav = NavGraph(self.level.navpoints, self.collision)
            self.brain = EnemyBrain(self.nav, self.collision, self.rng)

        self.outbox: list[tuple[Player | None, dict]] = []
        self.chat_log: list[dict] = []
        self.round_votes: dict[int, str] = {}
        self.kill_feed: list[dict] = []

        # apply any parts that start hidden
        if world_id == "fortwars":
            self.set_part_active("causeway", False)

    # ==================================================================
    # players
    # ==================================================================
    def add_player(self, user_id: int, username: str, avatar: dict,
                   socket) -> Player:
        pid = self.next_player_id
        self.next_player_id += 1
        p = Player(pid, user_id, username, avatar, socket)
        p.set_loadout(wp.LOADOUTS.get(p.loadout_name, wp.DEFAULT_LOADOUT))
        p.skin = (avatar or {}).get("skin", "default")
        self.players[pid] = p
        self.mode.on_join(p)
        self.respawn(p, force=True)
        self.broadcast({"t": "join", "player": p.profile()}, exclude=p)
        return p

    def remove_player(self, player: Player):
        if player.carrying_flag and hasattr(self.mode, "drop_flag"):
            self.mode.drop_flag(player.carrying_flag)
        self.players.pop(player.id, None)
        self.mode.on_leave(player)
        self.broadcast({"t": "leave", "id": player.id,
                        "name": player.username})

    def respawn(self, player: Player, force: bool = False):
        if not force and not self.mode.allow_respawn:
            return
        spot = self.mode.pick_spawn(player)
        px, py, pz = spot["p"]
        player.state = MoveState(px, py + 0.4, pz)
        player.yaw = math.radians(spot.get("yaw", 0.0))
        player.pitch = 0.0
        player.health = float(config.PLAYER_MAX_HEALTH)
        player.armor = 0.0
        player.alive = True
        player.spectating = False
        player.downed_at = 0.0
        player.revive_progress = 0.0
        player.effects.clear()
        player.carrying_flag = None
        player.zip_to = None
        player.zip_from = None
        player.damage_log.clear()
        player.spawn_protect = time.time() + SPAWN_PROTECT
        for w in player.weapons:
            w.reset()
        player.weapon_index = 0
        self.mode.on_spawn(player)
        self.send(player, {"t": "spawn", "p": [px, py + 0.4, pz],
                           "yaw": player.yaw,
                           "weapons": [w.to_client() for w in player.weapons]})

    # ==================================================================
    # input
    # ==================================================================
    def apply_input(self, player: Player, msg: dict):
        now = self.now
        seq = int(msg.get("seq", 0))
        if seq <= player.last_seq:
            return
        player.last_seq = seq
        player.last_input_at = now

        mv = msg.get("mv") or [0, 0]
        try:
            player.move_x = max(-1.0, min(1.0, float(mv[0])))
            player.move_z = max(-1.0, min(1.0, float(mv[1])))
            player.yaw = float(msg.get("y", player.yaw)) % math.tau
            player.pitch = max(-1.55, min(1.55, float(msg.get("p", 0.0))))
        except (TypeError, ValueError, IndexError):
            return
        btn = int(msg.get("b", 0))
        player.input_jump = bool(btn & BTN_JUMP)
        player.input_sprint = bool(btn & BTN_SPRINT)
        player.input_crouch = bool(btn & BTN_CROUCH)
        player.input_fire = bool(btn & BTN_FIRE)
        player.input_ads = bool(btn & BTN_ADS)
        player.input_use = bool(btn & BTN_USE)

    def switch_weapon(self, player: Player, slot: int):
        if 0 <= slot < len(player.weapons) and slot != player.weapon_index:
            player.weapon_index = slot
            w = player.weapon
            w.ready_at = self.now + w.weapon.switch_time
            w.reload_end = 0.0
            self.send(player, {"t": "swap", "slot": slot,
                               "ready": w.weapon.switch_time})

    def start_reload(self, player: Player):
        w = player.weapon
        if w is None or w.reload_end > self.now:
            return
        if w.ammo >= w.weapon.mag:
            return
        if not w.weapon.infinite_reserve and w.reserve <= 0:
            return
        w.reload_end = self.now + w.weapon.reload_time
        self.send(player, {"t": "reload", "end": w.weapon.reload_time})

    def finish_reload(self, player: Player, w: wp.WeaponState):
        need = w.weapon.mag - w.ammo
        if w.weapon.infinite_reserve:
            w.ammo = w.weapon.mag
        else:
            take = min(need, w.reserve)
            w.ammo += take
            w.reserve -= take
        w.reload_end = 0.0

    # ==================================================================
    # firing
    # ==================================================================
    def try_fire(self, player: Player, msg: dict):
        if not player.alive or player.downed_at:
            return
        w = player.weapon
        if w is None:
            return
        now = self.now
        weapon = w.weapon
        if now < w.next_fire or now < w.ready_at:
            return
        if w.reload_end:
            if now >= w.reload_end:
                self.finish_reload(player, w)
            else:
                return
        if w.ammo <= 0:
            self.start_reload(player)
            return

        w.next_fire = now + weapon.shot_interval
        w.ammo -= 1
        player.shots_fired += 1
        player.spawn_protect = 0.0

        origin = player.eye()
        direction = self._sanitised_dir(player, msg.get("d"))
        rewind = self._rewind_time(player, msg)

        if weapon.projectile_speed > 0:
            proj = wp.Projectile(player.id, player.team, weapon,
                                 (origin[0] + direction[0] * 2.2,
                                  origin[1] + direction[1] * 2.2,
                                  origin[2] + direction[2] * 2.2),
                                 direction, now)
            self.projectiles[proj.id] = proj
            self.broadcast({"t": "fx", "k": "launch", "w": weapon.id,
                            "p": [round(v, 2) for v in origin],
                            "d": [round(v, 3) for v in direction],
                            "o": player.id})
        else:
            self._hitscan(player, weapon, origin, direction, rewind)

        self.broadcast({"t": "shot", "i": player.id, "w": weapon.id},
                       exclude=player)
        if w.ammo == 0:
            self.start_reload(player)

    def _sanitised_dir(self, player: Player, raw):
        try:
            dx, dy, dz = (float(raw[0]), float(raw[1]), float(raw[2]))
            ln = math.sqrt(dx * dx + dy * dy + dz * dz)
            if ln < 1e-6:
                raise ValueError
            dx, dy, dz = dx / ln, dy / ln, dz / ln
        except (TypeError, ValueError, IndexError):
            return player.look_dir()
        # reject directions wildly off the reported view (anti-cheat)
        look = player.look_dir()
        if dx * look[0] + dy * look[1] + dz * look[2] < 0.62:
            return look
        return (dx, dy, dz)

    def _rewind_time(self, player: Player, msg: dict) -> float:
        latency = min(0.35, max(0.0, player.ping * 0.5))
        interp = 1.0 / config.SNAPSHOT_RATE * 2.0
        return self.now - latency - interp

    def _hitscan(self, shooter: Player, weapon: wp.Weapon, origin, direction,
                 rewind: float):
        targets = [p for p in self.players.values()
                   if p is not shooter and p.alive and not p.spectating]
        snapshots = {}
        for p in targets:
            snapshots[p.id] = (p.state.x, p.state.y, p.state.z)
            hx, hy, hz = p.position_at(rewind)
            p.state.x, p.state.y, p.state.z = hx, hy, hz

        rng = self.rng
        spread = weapon.ads_spread if shooter.input_ads else weapon.spread
        hits: dict[int, list] = {}
        enemy_hits: dict[int, float] = {}
        for _ in range(max(1, weapon.pellets)):
            d = wp.spread_direction(direction, spread, rng)
            world_hit = self.collision.raycast(origin, d, weapon.range)
            wall_dist = world_hit[0] if world_hit else weapon.range
            phit = sphere_cast_players(origin, d, wall_dist, targets)
            ehit = self._raycast_enemies(origin, d, wall_dist)
            if ehit and (not phit or ehit[0] < phit[0]):
                enemy_hits[ehit[1].id] = enemy_hits.get(ehit[1].id, 0.0) + \
                    self._damage_for(weapon, ehit[0], ehit[2], shooter)
                self._tracer(shooter, origin, d, ehit[0], weapon, "flesh")
            elif phit:
                dist, victim, head = phit
                dmg = self._damage_for(weapon, dist, head, shooter)
                entry = hits.setdefault(victim.id, [0.0, False, victim])
                entry[0] += dmg
                entry[1] = entry[1] or head
                self._tracer(shooter, origin, d, dist, weapon, "flesh")
            else:
                self._tracer(shooter, origin, d, wall_dist, weapon,
                             "wall" if world_hit else "air",
                             world_hit[1] if world_hit else None)

        for p in targets:
            p.state.x, p.state.y, p.state.z = snapshots[p.id]

        total_dealt = 0.0
        for victim_id, (dmg, head, victim) in hits.items():
            dealt = self.apply_damage(victim, shooter, dmg, weapon.id,
                                      headshot=head)
            total_dealt += dealt
            if head and dealt > 0:
                shooter.headshots += 1
        for eid, dmg in enemy_hits.items():
            enemy = self.enemies.get(eid)
            if enemy:
                total_dealt += self.damage_enemy(enemy, shooter, dmg)
        if total_dealt > 0:
            shooter.shots_hit += 1
            self.send(shooter, {"t": "hit", "d": round(total_dealt, 1),
                                "hs": any(v[1] for v in hits.values())})

    def _damage_for(self, weapon, dist, headshot, shooter) -> float:
        dmg = weapon.damage * wp.falloff_scale(weapon, dist)
        if headshot:
            dmg *= weapon.headshot_mult
        if shooter is not None and shooter.has_effect("damage", self.now):
            dmg *= 1.45
        return dmg

    def _tracer(self, shooter, origin, d, dist, weapon, kind, normal=None):
        msg = {"t": "fx", "k": "tracer", "w": weapon.id,
               "p": [round(v, 2) for v in origin],
               "d": [round(v, 3) for v in d],
               "l": round(dist, 2), "h": kind, "o": shooter.id}
        if normal:
            msg["n"] = [round(v, 2) for v in normal]
        self.broadcast(msg)

    def _raycast_enemies(self, origin, direction, max_dist):
        best = None
        ox, oy, oz = origin
        dx, dy, dz = direction
        for e in self.enemies.values():
            if not e.alive:
                continue
            r = e.state.radius
            minx, maxx = e.state.x - r, e.state.x + r
            miny, maxy = e.state.y, e.state.y + e.state.height
            minz, maxz = e.state.z - r, e.state.z + r
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
                head = (oy + dy * tmin) >= e.state.y + e.state.height - 1.6
                best = (tmin, e, head)
        return best

    # ==================================================================
    # damage
    # ==================================================================
    def apply_damage(self, victim: Player, attacker, amount: float,
                     source: str, *, headshot: bool = False) -> float:
        if not victim.alive or amount <= 0:
            return 0.0
        if victim.spawn_protect > self.now and attacker is not None:
            return 0.0
        if isinstance(attacker, Player):
            amount = self.mode.modify_damage(victim, attacker, amount, source)
            if amount <= 0:
                return 0.0
        if victim.armor > 0:
            absorbed = min(victim.armor, amount * 0.6)
            victim.armor -= absorbed
            amount -= absorbed
        victim.health -= amount
        if isinstance(attacker, Player):
            victim.damage_log[attacker.id] = \
                victim.damage_log.get(attacker.id, 0.0) + amount
            victim.last_damage_from = attacker.id
            victim.last_damage_at = self.now
            self.send(victim, {"t": "dmg", "a": round(amount, 1),
                               "from": [round(attacker.state.x, 1),
                                        round(attacker.state.y, 1),
                                        round(attacker.state.z, 1)],
                               "by": attacker.username})
        else:
            self.send(victim, {"t": "dmg", "a": round(amount, 1),
                               "src": source})
        if victim.health <= 0:
            self.kill(victim, attacker if isinstance(attacker, Player)
                      else None, source, headshot)
        return amount

    def heal(self, player: Player, amount: float):
        player.health = min(config.PLAYER_MAX_HEALTH, player.health + amount)

    def kill(self, victim: Player, killer, source: str, headshot: bool):
        victim.health = 0.0
        victim.deaths += 1
        victim.streak = 0
        victim.alive = False
        victim.respawn_at = self.now + self.mode.respawn_delay
        if killer is not None and killer is not victim:
            killer.kills += 1
            killer.streak += 1
            killer.best_streak = max(killer.best_streak, killer.streak)
        assists = [pid for pid, dmg in victim.damage_log.items()
                   if dmg >= 25 and (killer is None or pid != killer.id)]
        for pid in assists:
            helper = self.players.get(pid)
            if helper:
                helper.score += 1
        entry = {
            "t": "kill",
            "killer": killer.username if killer else None,
            "killerTeam": killer.team if killer else None,
            "killerId": killer.user_id if killer else None,
            "victim": victim.username,
            "victimTeam": victim.team,
            "victimId": victim.user_id,
            "weapon": source,
            "headshot": headshot,
            "assists": [self.players[p].username for p in assists
                        if p in self.players],
            "time": round(self.now - self.started, 2),
        }
        self.kill_feed.append(entry)
        if len(self.kill_feed) > 40:
            self.kill_feed.pop(0)
        self.broadcast(entry)
        self.mode.on_death(victim, killer, source, headshot)
        if self.on_stat:
            self.on_stat("kill", {"killer": killer.user_id if killer else None,
                                  "victim": victim.user_id,
                                  "headshot": headshot})

    # ==================================================================
    # enemies (PvE)
    # ==================================================================
    def spawn_enemy(self, pos, stats, boss=False):
        e = Enemy(pos, stats, boss)
        self.enemies[e.id] = e
        self.broadcast({"t": "enemy", "a": "spawn", "e": e.net_state(),
                        "boss": boss})
        return e

    def damage_enemy(self, enemy: Enemy, attacker, amount: float) -> float:
        if not enemy.alive:
            return 0.0
        enemy.health -= amount
        enemy.last_damage_from = attacker.id if attacker else None
        if amount > 30:
            enemy.stagger_until = self.now + 0.18
        if hasattr(self.mode, "on_enemy_damaged"):
            self.mode.on_enemy_damaged(enemy, attacker, amount)
        if enemy.health <= 0:
            enemy.alive = False
            self.enemies.pop(enemy.id, None)
            self.broadcast({"t": "enemy", "a": "die", "i": enemy.id,
                            "p": [round(enemy.state.x, 1),
                                  round(enemy.state.y, 1),
                                  round(enemy.state.z, 1)]})
            if hasattr(self.mode, "on_enemy_killed"):
                self.mode.on_enemy_killed(enemy, attacker)
        return amount

    def enemy_attack(self, enemy: Enemy, target: Player):
        self.apply_damage(target, None, enemy.damage, "zombie")
        self.broadcast({"t": "fx", "k": "melee", "i": enemy.id,
                        "target": target.id})

    # ==================================================================
    # dynamic parts / world control
    # ==================================================================
    def set_part_active(self, tag: str, active: bool, delay: float = 0.0):
        if delay > 0:
            self.pending_parts.append((self.now + delay, tag, active))
            return
        self.collision.set_tag_enabled(tag, active)
        if active:
            self.inactive_tags.discard(tag)
        else:
            self.inactive_tags.add(tag)
        self.broadcast({"t": "part", "tag": tag, "on": active})

    def reset_all_parts(self):
        for tag in list(self.inactive_tags):
            self.collision.set_tag_enabled(tag, True)
        self.inactive_tags.clear()
        self.pending_parts.clear()
        self.broadcast({"t": "parts", "off": []})

    def open_door(self, tag: str):
        self.set_part_active(tag, False)

    def set_lava(self, y: float):
        self.lava_y = y

    def give_weapon(self, player: Player, wid: str, delay: float = 0.0):
        if delay > 0:
            player.pending_weapon = wid
            player.pending_at = self.now + delay
            return
        weapon = wp.WEAPONS.get(wid)
        if not weapon:
            return
        for i, w in enumerate(player.weapons):
            if w.weapon.id == wid:
                w.reset()
                player.weapon_index = i
                self.send(player, {"t": "weapons",
                                   "list": [x.to_client() for x in player.weapons],
                                   "slot": i})
                return
        state = wp.WeaponState(weapon)
        if len(player.weapons) >= 4:
            player.weapons[player.weapon_index] = state
            slot = player.weapon_index
        else:
            player.weapons.append(state)
            slot = len(player.weapons) - 1
        player.weapon_index = slot
        state.ready_at = self.now + weapon.switch_time
        self.send(player, {"t": "weapons",
                           "list": [x.to_client() for x in player.weapons],
                           "slot": slot})

    def refill_ammo(self, player: Player, wid: str | None = None):
        for w in player.weapons:
            if wid is None or w.weapon.id == wid:
                w.reserve = w.weapon.reserve
                w.ammo = w.weapon.mag
        self.send(player, {"t": "weapons",
                           "list": [x.to_client() for x in player.weapons],
                           "slot": player.weapon_index})

    # ==================================================================
    # main tick
    # ==================================================================
    def tick(self, dt: float):
        self.now = time.time()
        now = self.now
        self.tick_no += 1

        for when, tag, active in list(self.pending_parts):
            if now >= when:
                self.pending_parts.remove((when, tag, active))
                self.set_part_active(tag, active)

        gravity = config.GRAVITY * self.level.gravity_scale

        # ---------------- players ----------------
        for p in list(self.players.values()):
            p.prune_effects(now)
            if p.pending_weapon and now >= p.pending_at:
                wid, p.pending_weapon = p.pending_weapon, None
                self.give_weapon(p, wid)

            if not p.alive:
                if self.mode.allow_respawn and now >= p.respawn_at:
                    self.respawn(p)
                continue

            w = p.weapon
            if w and w.reload_end and now >= w.reload_end:
                self.finish_reload(p, w)

            if p.downed_at:
                p.state.vx *= 0.82
                p.state.vz *= 0.82
                move_character(p.state, self.collision, (0, 0), dt,
                               want_jump=False, speed=0.0, jump_power=0.0,
                               gravity=gravity)
                p.record_history(now)
                continue

            if p.zip_to:
                self._tick_zipline(p, dt)
                p.record_history(now)
                continue

            speed = config.PLAYER_WALK_SPEED
            if p.input_sprint and p.move_z < -0.1:
                speed = config.PLAYER_SPRINT_SPEED
            if p.input_crouch:
                speed *= 0.48
            if p.has_effect("speed", now):
                speed *= 1.55
            if p.carrying_flag:
                speed *= 0.86
            if p.input_ads and p.weapon:
                speed *= 0.55 if p.weapon.weapon.zoom > 2 else 0.78
            if p.weapon:
                speed *= p.weapon.weapon.move_scale

            jump = config.PLAYER_JUMP_POWER
            if p.has_effect("gravity", now):
                jump *= 1.42

            # forward = (-sin yaw, -cos yaw); move_z is -1 when pressing
            # forward, so the forward term keeps move_z's sign.
            sy, cy = math.sin(p.yaw), math.cos(p.yaw)
            wish_x = p.move_z * sy + p.move_x * cy
            wish_z = p.move_z * cy - p.move_x * sy

            ev = move_character(p.state, self.collision, (wish_x, wish_z), dt,
                                want_jump=p.input_jump, speed=speed,
                                jump_power=jump, gravity=gravity)

            if ev["landed"] and ev["fall_distance"] > 34:
                fall_dmg = (ev["fall_distance"] - 34) * 2.4
                self.apply_damage(p, None, fall_dmg, "fall")

            self._check_launch(p, now)
            self._check_hazards(p, dt)
            self._check_pickups(p, now)
            p.record_history(now)
            p.playtime += dt

            if p.input_fire and p.weapon and p.weapon.weapon.auto:
                self.try_fire(p, {})

        # ---------------- enemies ----------------
        if self.brain:
            plist = list(self.players.values())
            for e in list(self.enemies.values()):
                self.brain.update(e, plist, dt, now, self)
                if e.state.y < self.level.void_y:
                    self.damage_enemy(e, None, e.health + 1)

        # ---------------- projectiles ----------------
        self._tick_projectiles(dt)

        # ---------------- turrets ----------------
        self._tick_turrets(now)

        # ---------------- pickups respawn ----------------
        for pid, st in self.pickup_state.items():
            if not st["active"] and now >= st["ready_at"]:
                st["active"] = True
                self.broadcast({"t": "pickup", "id": pid, "on": True})

        # ---------------- mode ----------------
        self.mode.tick(now, dt)

    def _tick_zipline(self, p: Player, dt: float):
        ax, ay, az = p.zip_from
        bx, by, bz = p.zip_to
        total = math.dist((ax, ay, az), (bx, by, bz)) or 1.0
        p.zip_t = min(1.0, p.zip_t + ZIP_SPEED * dt / total)
        p.state.x = ax + (bx - ax) * p.zip_t
        p.state.y = ay + (by - ay) * p.zip_t
        p.state.z = az + (bz - az) * p.zip_t
        p.state.vx = (bx - ax) / total * ZIP_SPEED
        p.state.vy = (by - ay) / total * ZIP_SPEED
        p.state.vz = (bz - az) / total * ZIP_SPEED
        p.state.on_ground = False
        if p.zip_t >= 1.0 or p.input_jump:
            p.zip_from = p.zip_to = None
            p.zip_t = 0.0

    def _check_launch(self, p: Player, now: float):
        if not p.state.on_ground or now - p.last_launch < 0.4:
            return
        minx, miny, minz, maxx, maxy, maxz = p.state.aabb()
        for b in self.launch_pads:
            if b[6] in self.collision.disabled:
                continue
            if (minx < b[3] and maxx > b[0] and minz < b[5] and maxz > b[2]
                    and abs(miny - b[4]) < 1.4):
                p.state.vy = LAUNCH_IMPULSE * (1.0 /
                                               max(0.4,
                                                   self.level.gravity_scale)) ** 0.5
                p.state.on_ground = False
                p.last_launch = now
                self.send(p, {"t": "fx", "k": "launch_pad"})
                self.broadcast({"t": "fx", "k": "pad", "i": p.id},
                               exclude=p)
                return

    def _check_hazards(self, p: Player, dt: float):
        box = p.state.aabb()
        dmg = self.collision.damage_at(*box)
        if dmg:
            self.apply_damage(p, None, dmg * dt, "lava")
        if self.lava_y is not None and p.state.y < self.lava_y - 0.4:
            pass    # handled by the mode so the tide owns its own damage
        if p.state.y < self.level.void_y:
            self.apply_damage(p, None, 9999, "void")

    def _check_pickups(self, p: Player, now: float):
        for pid, st in self.pickup_state.items():
            if not st["active"]:
                continue
            d = st["def"]
            px, py, pz = d["p"]
            if abs(p.state.x - px) > PICKUP_RADIUS or \
               abs(p.state.z - pz) > PICKUP_RADIUS or \
               abs(p.state.y + 2.5 - py) > 6.0:
                continue
            info = PICKUP_EFFECTS.get(d["kind"])
            if not info:
                continue
            if info.get("heal"):
                if p.health >= config.PLAYER_MAX_HEALTH:
                    continue
                self.heal(p, info["heal"])
            elif info.get("armor"):
                if p.armor >= info["armor"]:
                    continue
                p.armor = float(info["armor"])
            elif info.get("ammo"):
                self.refill_ammo(p)
            elif info.get("effect"):
                p.add_effect(info["effect"], now)
            st["active"] = False
            st["ready_at"] = now + d.get("respawn", 20.0)
            self.broadcast({"t": "pickup", "id": pid, "on": False,
                            "by": p.id})
            self.send(p, {"t": "got", "kind": d["kind"],
                          "label": info["label"], "color": info["color"]})

    def _tick_projectiles(self, dt: float):
        gravity = config.GRAVITY * self.level.gravity_scale
        for proj in list(self.projectiles.values()):
            weapon = proj.weapon
            if weapon.gravity:
                proj.vy -= weapon.gravity * dt
            steps = 2
            sdt = dt / steps
            for _ in range(steps):
                px, py, pz = proj.x, proj.y, proj.z
                dx, dy, dz = proj.vx * sdt, proj.vy * sdt, proj.vz * sdt
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                if dist < 1e-6:
                    continue
                d = (dx / dist, dy / dist, dz / dist)
                shooter = self.players.get(proj.owner_id)
                targets = [p for p in self.players.values()
                           if p.alive and p.id != proj.owner_id
                           and not p.spectating]
                world_hit = self.collision.raycast((px, py, pz), d, dist)
                phit = sphere_cast_players((px, py, pz), d,
                                           world_hit[0] if world_hit else dist,
                                           targets)
                ehit = self._raycast_enemies((px, py, pz), d,
                                             world_hit[0] if world_hit
                                             else dist)
                hit_thing = None
                hit_dist = dist
                if phit and (not ehit or phit[0] <= ehit[0]):
                    hit_thing, hit_dist = ("player", phit[1]), phit[0]
                elif ehit:
                    hit_thing, hit_dist = ("enemy", ehit[1]), ehit[0]
                elif world_hit:
                    hit_thing, hit_dist = ("world", world_hit[1]), world_hit[0]

                if hit_thing is None:
                    proj.x += dx
                    proj.y += dy
                    proj.z += dz
                    continue

                proj.x += d[0] * hit_dist
                proj.y += d[1] * hit_dist
                proj.z += d[2] * hit_dist

                if hit_thing[0] == "world" and proj.bounces_left > 0:
                    n = hit_thing[1]
                    dot = proj.vx * n[0] + proj.vy * n[1] + proj.vz * n[2]
                    proj.vx = (proj.vx - 2 * dot * n[0]) * 0.72
                    proj.vy = (proj.vy - 2 * dot * n[1]) * 0.72
                    proj.vz = (proj.vz - 2 * dot * n[2]) * 0.72
                    proj.x += n[0] * 0.4
                    proj.y += n[1] * 0.4
                    proj.z += n[2] * 0.4
                    proj.bounces_left -= 1
                    self.broadcast({"t": "fx", "k": "bounce",
                                    "p": [round(proj.x, 1), round(proj.y, 1),
                                          round(proj.z, 1)]})
                    continue

                self._detonate(proj, hit_thing, shooter)
                break
            else:
                proj.life -= dt
                if proj.life <= 0:
                    self._detonate(proj, ("expire", None),
                                   self.players.get(proj.owner_id))
                continue

    def _detonate(self, proj: wp.Projectile, hit, shooter):
        self.projectiles.pop(proj.id, None)
        weapon = proj.weapon
        pos = (proj.x, proj.y, proj.z)
        self.broadcast({"t": "fx", "k": "boom" if weapon.splash_radius
                        else "impact", "w": weapon.id,
                        "p": [round(v, 2) for v in pos],
                        "r": weapon.splash_radius})

        if hit[0] in ("player", "enemy") and not weapon.splash_radius:
            if hit[0] == "player":
                self.apply_damage(hit[1], shooter, weapon.damage, weapon.id)
                if weapon.knockback:
                    self._knock(hit[1], pos, weapon.knockback)
            else:
                self.damage_enemy(hit[1], shooter, weapon.damage)
            if shooter:
                self.send(shooter, {"t": "hit", "d": weapon.damage,
                                    "hs": False})
            return

        if not weapon.splash_radius:
            return

        r2 = weapon.splash_radius ** 2
        dealt = 0.0
        for p in list(self.players.values()):
            if not p.alive:
                continue
            d2 = ((p.state.x - pos[0]) ** 2 +
                  (p.state.y + 2.5 - pos[1]) ** 2 +
                  (p.state.z - pos[2]) ** 2)
            if d2 > r2:
                continue
            falloff = 1.0 - math.sqrt(d2) / weapon.splash_radius
            dmg = weapon.splash_damage * (falloff ** 0.7)
            if p.id == proj.owner_id:
                dmg *= weapon.self_damage_scale
                self._knock(p, pos, weapon.self_knockback * falloff)
                self.apply_damage(p, None, dmg, weapon.id)
            else:
                self._knock(p, pos, weapon.knockback * falloff)
                dealt += self.apply_damage(p, shooter, dmg, weapon.id)
        for e in list(self.enemies.values()):
            d2 = ((e.state.x - pos[0]) ** 2 + (e.state.y + 2 - pos[1]) ** 2 +
                  (e.state.z - pos[2]) ** 2)
            if d2 <= r2:
                falloff = 1.0 - math.sqrt(d2) / weapon.splash_radius
                dealt += self.damage_enemy(e, shooter,
                                           weapon.splash_damage * falloff)
        if shooter and dealt > 0:
            self.send(shooter, {"t": "hit", "d": round(dealt, 1), "hs": False})

    def _knock(self, player: Player, origin, force: float):
        dx = player.state.x - origin[0]
        dy = player.state.y + 2.0 - origin[1]
        dz = player.state.z - origin[2]
        d = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        player.state.vx += dx / d * force
        player.state.vy += max(0.35, dy / d) * force * 0.9
        player.state.vz += dz / d * force
        player.state.on_ground = False

    def _tick_turrets(self, now: float):
        if not self.turrets:
            return
        for turret in self.turrets:
            if now < turret["next_fire"]:
                continue
            tx, ty, tz = turret["p"]
            best = None
            for p in self.players.values():
                if not p.alive or p.team == turret.get("team"):
                    continue
                if p.spawn_protect > now:
                    continue
                d = math.dist((p.state.x, p.state.y + 2.5, p.state.z),
                              (tx, ty, tz))
                if d > TURRET_RANGE:
                    continue
                dirv = ((p.state.x - tx) / d, (p.state.y + 2.5 - ty) / d,
                        (p.state.z - tz) / d)
                if self.collision.raycast((tx, ty, tz), dirv, d - 1.0):
                    continue
                if best is None or d < best[0]:
                    best = (d, p, dirv)
            if best is None:
                continue
            turret["next_fire"] = now + TURRET_INTERVAL
            dist, victim, dirv = best
            self.apply_damage(victim, None, TURRET_DAMAGE, "turret")
            self.broadcast({"t": "fx", "k": "tracer", "w": "turret",
                            "p": [round(tx, 1), round(ty, 1), round(tz, 1)],
                            "d": [round(v, 3) for v in dirv],
                            "l": round(dist, 1), "h": "flesh", "o": -1})

    # ==================================================================
    # interaction & chat
    # ==================================================================
    def interact(self, player: Player, target: str | None):
        if not player.alive:
            return
        # ziplines first
        for zl in self.ziplines:
            ax, ay, az = zl["p"]
            if math.dist((player.state.x, player.state.y, player.state.z),
                         (ax, ay, az)) < 9.0:
                player.zip_from = (player.state.x, player.state.y,
                                   player.state.z)
                player.zip_to = tuple(zl["to"])
                player.zip_t = 0.0
                self.send(player, {"t": "fx", "k": "zip"})
                return
        if hasattr(self.mode, "interact") and target:
            result = self.mode.interact(player, target)
            if result:
                self.send(player, {"t": "interact", **result})

    def chat(self, player: Player, text: str, channel: str = "all"):
        now = self.now
        if now < player.muted_until:
            self.send(player, {"t": "sys",
                               "text": "You are muted for a few seconds."})
            return
        if now - player.last_chat_at < 0.55:
            return
        player.last_chat_at = now
        text = clean_text(text, max_len=180)
        if not text:
            return
        if looks_like_spam(text):
            player.chat_strikes += 1
            if player.chat_strikes >= 3:
                player.muted_until = now + 20
            self.send(player, {"t": "sys", "text": "Easy on the caps."})
            return
        text = filter_chat(text)
        if text.startswith("/"):
            self._chat_command(player, text)
            return
        entry = {"t": "chat", "id": player.id, "userId": player.user_id,
                 "from": player.username, "text": text,
                 "team": player.team,
                 "color": TEAM_COLORS.get(player.team, "#dfe6ee"),
                 "channel": channel if channel in ("all", "team") else "all",
                 "time": round(now, 2)}
        self.chat_log.append(entry)
        if len(self.chat_log) > 120:
            self.chat_log.pop(0)
        if entry["channel"] == "team":
            for p in self.players.values():
                if p.team == player.team:
                    self.send(p, entry)
        else:
            self.broadcast(entry)

    def _chat_command(self, player: Player, text: str):
        parts = text[1:].split()
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]
        if cmd in ("help", "?"):
            self.send(player, {"t": "sys", "text":
                               "/team <msg>  /vote <world>  /me <action>  "
                               "/stats  /players"})
        elif cmd == "team":
            self.chat(player, " ".join(args), "team")
        elif cmd == "me":
            self.broadcast({"t": "chat", "id": player.id,
                            "userId": player.user_id,
                            "from": "*", "text":
                            f"{player.username} {' '.join(args)}",
                            "color": "#c9a0ff", "channel": "all",
                            "time": round(self.now, 2)})
        elif cmd == "stats":
            acc = (player.shots_hit / player.shots_fired * 100
                   if player.shots_fired else 0)
            self.send(player, {"t": "sys", "text":
                               f"K/D {player.kills}/{player.deaths} · "
                               f"accuracy {acc:.0f}% · streak "
                               f"{player.best_streak}"})
        elif cmd == "players":
            names = ", ".join(p.username for p in self.players.values())
            self.send(player, {"t": "sys", "text": f"Online: {names}"})
        elif cmd == "vote":
            if args:
                self.cast_vote(player, args[0])
        else:
            self.send(player, {"t": "sys", "text": f"Unknown command /{cmd}"})

    def cast_vote(self, player: Player, choice: str):
        from .worlds import world_ids
        if choice not in world_ids():
            return
        player.vote = choice
        self.round_votes[player.id] = choice
        tally: dict[str, int] = {}
        for v in self.round_votes.values():
            tally[v] = tally.get(v, 0) + 1
        self.broadcast({"t": "votes", "tally": tally,
                        "total": len(self.players)})

    def on_round_end(self, winner):
        self.round_votes.clear()
        for p in self.players.values():
            p.vote = None
        self.broadcast({"t": "roundend", "winner": winner,
                        "scoreboard": self.scoreboard()})
        if self.on_stat:
            self.on_stat("round", {"winner": winner,
                                   "players": [p.user_id for p in
                                               self.players.values()]})

    # ==================================================================
    # networking helpers
    # ==================================================================
    def send(self, player: Player, msg: dict):
        self.outbox.append((player, msg))

    def broadcast(self, msg: dict, exclude: Player | None = None):
        for p in self.players.values():
            if p is not exclude:
                self.outbox.append((p, msg))

    def broadcast_event(self, msg: dict):
        self.broadcast({"t": "event", **msg})

    def drain_outbox(self):
        out, self.outbox = self.outbox, []
        return out

    def scoreboard(self) -> list[dict]:
        rows = [p.scoreboard_row() for p in self.players.values()]
        rows.sort(key=lambda r: (-r["score"], -r["kills"], r["deaths"]))
        return rows

    def snapshot(self) -> dict:
        snap = {
            "t": "snap",
            "k": self.tick_no,
            "s": round(self.now - self.started, 3),
            "pl": [p.net_state() for p in self.players.values()],
            "hud": self.mode.hud(),
        }
        if self.enemies:
            snap["en"] = [e.net_state() for e in self.enemies.values()]
        if self.projectiles:
            snap["pr"] = [p.to_client() for p in self.projectiles.values()]
        if self.lava_y is not None:
            snap["lava"] = round(self.lava_y, 2)
        return snap

    def personal_state(self, p: Player) -> dict:
        w = p.weapon
        return {
            "hp": round(p.health, 1),
            "ar": round(p.armor, 1),
            "seq": p.last_seq,
            "p": [round(p.state.x, 3), round(p.state.y, 3),
                  round(p.state.z, 3)],
            "v": [round(p.state.vx, 2), round(p.state.vy, 2),
                  round(p.state.vz, 2)],
            "g": p.state.on_ground,
            "a": p.alive,
            "rs": round(max(0.0, p.respawn_at - self.now), 2)
                  if not p.alive else 0,
            "am": w.ammo if w else 0,
            "rv": (-1 if w and w.weapon.infinite_reserve
                   else (w.reserve if w else 0)),
            "sl": p.weapon_index,
            "rl": round(max(0.0, (w.reload_end - self.now) if w else 0), 2),
            "ef": {k: round(v - self.now, 1) for k, v in p.effects.items()
                   if v > self.now},
            "sc": p.score, "ki": p.kills, "de": p.deaths, "st": p.streak,
            "pt": p.points,
            "fl": p.carrying_flag,
            "dn": round(p.revive_progress, 2) if p.downed_at else None,
            "rvn": p.reviver_name if p.downed_at else None,
            "sp": p.spectating,
        }

    def welcome_payload(self, p: Player) -> dict:
        return {
            "t": "welcome",
            "you": p.profile(),
            "yourId": p.id,
            "world": {
                "id": self.world.meta.id,
                "name": self.world.meta.name,
                "mode": self.world.meta.mode,
                "tagline": self.world.meta.tagline,
                "accent": self.world.meta.accent,
                "maxPlayers": self.world.meta.max_players,
            },
            "tickRate": config.TICK_RATE,
            "snapshotRate": config.SNAPSHOT_RATE,
            "gravity": config.GRAVITY * self.level.gravity_scale,
            "walkSpeed": config.PLAYER_WALK_SPEED,
            "sprintSpeed": config.PLAYER_SPRINT_SPEED,
            "jumpPower": config.PLAYER_JUMP_POWER,
            "playerHeight": config.PLAYER_HEIGHT,
            "playerRadius": config.PLAYER_RADIUS,
            "stepHeight": 2.6,
            "players": [q.profile() for q in self.players.values()],
            "weapons": {k: v.to_client() for k, v in wp.WEAPONS.items()},
            "loadout": [w.to_client() for w in p.weapons],
            "teams": {k: TEAM_COLORS.get(k, "#9aa2ab")
                      for k in self.mode.teams},
            "teamColors": TEAM_COLORS,
            "inactiveTags": sorted(self.inactive_tags),
            "pickups": [{"id": k, "on": v["active"]}
                        for k, v in self.pickup_state.items()],
            "chatLog": self.chat_log[-25:],
            "killFeed": self.kill_feed[-8:],
            "hud": self.mode.hud(),
            "serverTime": round(self.now - self.started, 3),
        }
