"""World 3 — OUTBREAK FACILITY: co-operative wave defence against the Nextbots."""
from __future__ import annotations

import math
import random
import time

from .base import GameMode, WorldDef, WorldMeta
from .builder import Level

FLOOR = "#6d747d"
FLOOR_DARK = "#4d525a"
WALL = "#98a2ad"
WALL_DARK = "#6f7680"
TRIM = "#2f3238"
GLASS = "#9fd8f0"
HAZARD = "#d9c22c"
GREEN = "#4be08a"
RUST = "#8a5a3a"

ROOMS = {
    #  name        cx     cz    w     d
    "reception": (0, 0, 74, 62),
    "labs":      (118, 0, 78, 70),
    "servers":   (0, -116, 84, 66),
    "cold":      (-118, 0, 74, 70),
    "reactor":   (118, 116, 86, 78),
    "vault":     (-118, 116, 70, 62),
}

DOORS = [
    # id,        from,        to,          cost, x,    z,    axis
    ("d_labs",    "reception", "labs",      750,  46,   0,   "z"),
    ("d_servers", "reception", "servers",  1000,   0,  -37,  "x"),
    ("d_cold",    "reception", "cold",      750, -46,   0,   "z"),
    ("d_reactor", "labs",      "reactor",  1250, 118,  46,   "x"),
    ("d_vault",   "cold",      "vault",    1500, -118,  46,  "x"),
]

WALL_BUYS = [
    ("wb_blaster", "blaster", 500,  -30,   6,  -28, "reception"),
    ("wb_rifle",   "rifle",  1200,   30,   6,  -28, "reception"),
    ("wb_scatter", "scatter", 1400, 100,   6,  -30, "labs"),
    ("wb_zapper",  "zapper",  1600, 136,   6,   20, "labs"),
    ("wb_railer",  "railer",  2200,  -36,  6, -140, "servers"),
    ("wb_mender",  "mender",  1500, -140,  6,   18, "cold"),
    ("wb_rocket",  "rocket",  3500, 150,   6,  138, "reactor"),
]

MYSTERY_BOX = ("mystery", -100, 6, 132, "vault", 950)


class OutbreakMode(GameMode):
    teams = ("survivor",)
    friendly_fire = False
    score_limit = 0
    time_limit = 0.0
    respawn_delay = 0.0
    allow_respawn = False
    hud_kind = "outbreak"

    BLEEDOUT = 26.0
    REVIVE_TIME = 4.0
    REVIVE_RANGE = 7.5

    def __init__(self, room):
        super().__init__(room)
        self.wave = 0
        self.enemies_left = 0
        self.enemies_to_spawn = 0
        self.spawn_cooldown = 0.0
        self.state = "prep"           # prep | wave | cleared | over
        self.state_until = time.time() + 12.0
        self.best_wave = 0
        self.doors = {d[0]: {"id": d[0], "cost": d[3], "open": False,
                             "p": [d[4], 8.0, d[5]], "axis": d[6],
                             "to": d[2]} for d in DOORS}
        self.open_rooms = {"reception"}
        self.wallbuys = {w[0]: {"id": w[0], "weapon": w[1], "cost": w[2],
                                "p": [w[3], w[4], w[5]], "room": w[6]}
                         for w in WALL_BUYS}
        self.box = {"id": MYSTERY_BOX[0], "p": list(MYSTERY_BOX[1:4]),
                    "room": MYSTERY_BOX[4], "cost": MYSTERY_BOX[5],
                    "rolling_until": 0.0, "result": None}
        self.downed: dict[int, float] = {}

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        self.announce("OUTBREAK FACILITY — survive as long as you can.",
                      "round")

    def on_join(self, player):
        player.team = "survivor"
        player.points = 500
        player.revives = 0
        player.downs = 0

    def on_spawn(self, player):
        player.downed_at = 0.0
        self.downed.pop(player.id, None)

    def wave_size(self) -> int:
        n = max(1, len(self.room.players))
        return int(round((5 + self.wave * 2.4) * (0.65 + 0.35 * n)))

    def enemy_stats(self):
        w = self.wave
        return {
            "health": 80 + w * 22 + max(0, w - 10) * 18,
            "speed": min(17.5, 7.0 + w * 0.42),
            "damage": 14 + w * 1.1,
            "boss": w % 5 == 0 and w > 0,
        }

    def tick(self, now, dt):
        alive_players = [p for p in self.room.players.values()
                         if p.alive and p.id not in self.downed]
        any_player = bool(self.room.players)

        # ---- downed / bleedout / revive ----
        for pid, down_at in list(self.downed.items()):
            p = self.room.players.get(pid)
            if p is None:
                self.downed.pop(pid, None)
                continue
            reviver = None
            for other in alive_players:
                dx = other.state.x - p.state.x
                dy = other.state.y - p.state.y
                dz = other.state.z - p.state.z
                if dx * dx + dy * dy + dz * dz < self.REVIVE_RANGE ** 2 \
                        and other.input_use:
                    reviver = other
                    break
            if reviver:
                p.revive_progress += dt / self.REVIVE_TIME
                p.reviver_name = reviver.username
                if p.revive_progress >= 1.0:
                    self.downed.pop(pid, None)
                    p.revive_progress = 0.0
                    p.health = 55
                    p.alive = True
                    p.downed_at = 0.0
                    reviver.points += 175
                    reviver.revives += 1
                    self.room.broadcast_event(
                        {"t": "revived", "who": p.username,
                         "by": reviver.username})
            else:
                p.revive_progress = max(0.0, p.revive_progress - dt * 0.5)
                p.reviver_name = None
                if now - down_at > self.BLEEDOUT:
                    self.downed.pop(pid, None)
                    p.alive = False
                    p.health = 0
                    self.room.broadcast_event(
                        {"t": "bledout", "who": p.username})

        # ---- game over ----
        if any_player and self.state in ("wave", "cleared") and \
                not alive_players and not self.downed:
            self.state = "over"
            self.state_until = now + 15.0
            self.best_wave = max(self.best_wave, self.wave)
            self.announce(f"The facility is lost. You reached wave {self.wave}.",
                          "defeat")
            self.room.on_round_end(None)
            return

        if self.state == "over":
            if now >= self.state_until:
                self.reset_run()
            return

        if self.state == "prep":
            if now >= self.state_until and any_player:
                self.begin_wave()
            return

        if self.state == "cleared":
            if now >= self.state_until:
                self.begin_wave()
            return

        # ---- spawn drip ----
        if self.enemies_to_spawn > 0:
            self.spawn_cooldown -= dt
            live = len(self.room.enemies)
            cap = 6 + min(18, self.wave * 2)
            if self.spawn_cooldown <= 0 and live < cap:
                self.spawn_cooldown = max(0.28, 1.5 - self.wave * 0.05)
                self.spawn_enemy()

        if self.enemies_left <= 0 and self.enemies_to_spawn <= 0:
            self.state = "cleared"
            self.state_until = now + 16.0
            bonus = 120 + self.wave * 35
            for p in self.room.players.values():
                p.points += bonus
            self.announce(f"Wave {self.wave} cleared! +{bonus} points.",
                          "victory")

        # ---- mystery box roll resolution ----
        if self.box["rolling_until"] and now >= self.box["rolling_until"]:
            self.box["rolling_until"] = 0.0
            self.box["result"] = None

    def reset_run(self):
        self.wave = 0
        self.state = "prep"
        self.state_until = time.time() + 12.0
        self.open_rooms = {"reception"}
        for d in self.doors.values():
            d["open"] = False
        self.room.enemies.clear()
        self.downed.clear()
        for p in self.room.players.values():
            p.points = 500
            p.revive_progress = 0.0
            self.room.respawn(p, force=True)
        self.announce("Systems rebooted. Prepare for a new outbreak.", "round")
        self.room.broadcast_event({"t": "doors",
                                   "open": [d for d, v in self.doors.items()
                                            if v["open"]]})

    def begin_wave(self):
        self.wave += 1
        self.state = "wave"
        n = self.wave_size()
        self.enemies_to_spawn = n
        self.enemies_left = n
        self.spawn_cooldown = 0.6
        stats = self.enemy_stats()
        label = "BOSS WAVE" if stats["boss"] else f"WAVE {self.wave}"
        self.announce(f"{label} — {n} hostiles inbound.", "wave")
        self.room.broadcast_event({"t": "wave", "wave": self.wave, "count": n,
                                   "boss": stats["boss"]})
        # revive anyone fully dead at the wave break
        for p in self.room.players.values():
            if not p.alive and p.id not in self.downed:
                self.room.respawn(p, force=True)

    def spawn_enemy(self):
        points = [s for s in self.level.spawns
                  if s.get("team") == "enemy" and
                  s.get("room", "reception") in self.open_rooms]
        if not points:
            points = [s for s in self.level.spawns if s.get("team") == "enemy"]
        if not points:
            return
        # bias toward spawns near a living player
        alive = [p for p in self.room.players.values() if p.alive]
        if alive:
            def near(s):
                px, _, pz = s["p"]
                return min((px - p.state.x) ** 2 + (pz - p.state.z) ** 2
                           for p in alive)
            points = sorted(points, key=near)[:max(2, len(points) // 2)]
        s = self.rng.choice(points)
        stats = self.enemy_stats()
        boss = stats["boss"] and self.enemies_to_spawn <= 2
        self.room.spawn_enemy(s["p"], stats, boss=boss)
        self.enemies_to_spawn -= 1

    def on_enemy_killed(self, enemy, killer):
        self.enemies_left = max(0, self.enemies_left - 1)
        if killer is not None:
            reward = 130 if enemy.boss else 55
            killer.points += reward
            killer.score += 5 if enemy.boss else 1
            killer.kills += 1
            killer.streak += 1

    def on_enemy_damaged(self, enemy, attacker, amount):
        if attacker is not None:
            attacker.points += max(1, int(amount * 0.55))

    def on_death(self, victim, killer, weapon_id, headshot):
        """Players go *down* rather than dying outright."""
        if victim.id in self.downed:
            return
        self.downed[victim.id] = time.time()
        victim.downed_at = time.time()
        victim.revive_progress = 0.0
        victim.downs += 1
        victim.alive = True         # still present, just incapacitated
        victim.health = 1
        self.room.broadcast_event({"t": "downed", "who": victim.username})

    # -- interaction -------------------------------------------------------
    def interact(self, player, target_id: str) -> dict | None:
        if target_id in self.doors:
            door = self.doors[target_id]
            if door["open"]:
                return None
            if player.points < door["cost"]:
                return {"t": "denied", "reason":
                        f"Need {door['cost']} points"}
            player.points -= door["cost"]
            door["open"] = True
            self.open_rooms.add(door["to"])
            self.announce(f"{player.username} opened the {door['to'].upper()}.",
                          "objective")
            self.room.open_door(target_id)
            return {"t": "door", "id": target_id}

        if target_id in self.wallbuys:
            wb = self.wallbuys[target_id]
            if wb["room"] not in self.open_rooms:
                return {"t": "denied", "reason": "Area sealed"}
            owned = any(w.weapon.id == wb["weapon"] for w in player.weapons)
            cost = wb["cost"] // 3 if owned else wb["cost"]
            if player.points < cost:
                return {"t": "denied", "reason": f"Need {cost} points"}
            player.points -= cost
            if owned:
                self.room.refill_ammo(player, wb["weapon"])
                return {"t": "ammo", "weapon": wb["weapon"]}
            self.room.give_weapon(player, wb["weapon"])
            return {"t": "weapon", "weapon": wb["weapon"]}

        if target_id == "mystery":
            if self.box["room"] not in self.open_rooms:
                return {"t": "denied", "reason": "Vault sealed"}
            if player.points < self.box["cost"]:
                return {"t": "denied", "reason":
                        f"Need {self.box['cost']} points"}
            player.points -= self.box["cost"]
            pool = ["rifle", "scatter", "railer", "rocket", "zapper",
                    "blaster", "mender"]
            pick = self.rng.choice(pool)
            self.box["rolling_until"] = time.time() + 2.6
            self.box["result"] = pick
            self.room.give_weapon(player, pick, delay=2.6)
            return {"t": "box", "weapon": pick}
        return None

    def hud(self):
        return {
            "kind": "outbreak",
            "phase": self.state,
            "wave": self.wave,
            "enemiesLeft": self.enemies_left + self.enemies_to_spawn,
            "nextIn": max(0.0, self.state_until - time.time())
                      if self.state in ("prep", "cleared", "over") else 0.0,
            "doors": [{"id": d["id"], "cost": d["cost"], "open": d["open"],
                       "p": d["p"]} for d in self.doors.values()],
            "wallbuys": [{"id": w["id"], "weapon": w["weapon"],
                          "cost": w["cost"], "p": w["p"],
                          "open": w["room"] in self.open_rooms}
                         for w in self.wallbuys.values()],
            "box": {"id": "mystery", "p": self.box["p"],
                    "cost": self.box["cost"],
                    "open": self.box["room"] in self.open_rooms},
            "bestWave": self.best_wave,
            "bleedout": self.BLEEDOUT,
        }


class Outbreak(WorldDef):
    meta = WorldMeta(
        id="outbreak",
        name="Outbreak Facility",
        tagline="Four survivors. One sealed lab. Endless waves.",
        description=(
            "Something got out of Containment Bay 4. Work together to hold "
            "the reception hall, then spend your points to blast open the "
            "labs, the server hall, cold storage and finally the reactor.\n\n"
            "Every hit earns points. Points buy wall weapons, doors and a "
            "very unreliable Mystery Box. Go down and a teammate has 26 "
            "seconds to pick you back up — if everyone drops, the run ends.\n\n"
            "Co-operative. No respawns mid-wave. How deep can you get?"
        ),
        genre="Horror",
        mode="Co-op Survival",
        max_players=8,
        thumb="outbreak",
        accent="#4be08a",
        sort_order=3,
        tags=["Co-op", "PvE", "Survival", "Waves"],
        difficulty="Very Hard",
        recommended="2-8 players",
    )
    mode_class = OutbreakMode

    def build(self) -> Level:
        lv = Level(sky="void", ambient=0.66, sun=(0.34, 0.72, 0.44),
                   fog="#161f2a", fog_near=120, fog_far=430, void_y=-40)
        lv.bounds = [-200, -200, 200, 200]

        for name, (cx, cz, w, d) in ROOMS.items():
            self._room(lv, name, cx, cz, w, d)

        self._corridor(lv, 37, 0, 79, 0, 18)        # reception -> labs
        self._corridor(lv, -37, 0, -81, 0, 18)      # reception -> cold
        self._corridor(lv, 0, -31, 0, -83, 18)      # reception -> servers
        self._corridor(lv, 118, 35, 118, 77, 18)    # labs -> reactor
        self._corridor(lv, -118, 35, -118, 85, 18)  # cold -> vault

        for did, frm, to, cost, x, z, axis in DOORS:
            self._blast_door(lv, did, x, z, axis)

        for wid, weapon, cost, x, y, z, room in WALL_BUYS:
            lv.box(x, y + 2, z, 7, 5, 0.8 if abs(z) > abs(x) else 0.8,
                   "#2c3138", "metal", tag=wid)
            lv.add((x, y + 2, z + (0.7 if z < 0 else -0.7)), (6, 4, 0.2),
                   "#f2c53d", "neon", glow=0.7, nocollide=True)
            lv.sign(x, y + 6, z, weapon.upper(), color="#f2c53d", size=3.5)

        # mystery box
        mid, mx, my, mz, mroom, mcost = MYSTERY_BOX
        lv.box(mx, my, mz, 7, 5, 5, "#6b4a2c", "wood", tag="mystery")
        lv.add((mx, my + 3.2, mz), (7.4, 1.0, 5.4), "#f2c53d", "neon",
               glow=0.9, nocollide=True)
        lv.sign(mx, my + 6, mz, "?", color="#f2c53d", size=8)

        # ---- player spawns ----
        for i in range(8):
            a = i * math.tau / 8
            lv.spawn(math.cos(a) * 16, 3, math.sin(a) * 14 - 6, "survivor",
                     180)

        # ---- enemy spawns, tagged by room ----
        enemy_spawns = [
            ("reception", (-32, -24)), ("reception", (32, -24)),
            ("reception", (0, 26)),
            ("labs", (146, -26)), ("labs", (146, 26)), ("labs", (96, 30)),
            ("servers", (-38, -144)), ("servers", (38, -144)),
            ("servers", (0, -88)),
            ("cold", (-148, -26)), ("cold", (-148, 26)), ("cold", (-96, 30)),
            ("reactor", (152, 92)), ("reactor", (152, 142)),
            ("reactor", (86, 140)),
            ("vault", (-146, 100)), ("vault", (-92, 142)),
        ]
        for room_name, (x, z) in enemy_spawns:
            lv.spawns.append({"p": [x, 3.0, z], "team": "enemy", "yaw": 0,
                              "room": room_name})

        # ---- navigation graph ----
        for name, (cx, cz, w, d) in ROOMS.items():
            lv.nav_grid(cx - w / 2 + 12, cz - d / 2 + 12,
                        cx + w / 2 - 12, cz + d / 2 - 12, 3.0, step=18)
        for a, b in (((37, 0), (79, 0)), ((-37, 0), (-81, 0)),
                     ((0, -31), (0, -83)), ((118, 35), (118, 77)),
                     ((-118, 35), (-118, 85))):
            steps = 4
            for i in range(steps + 1):
                t_ = i / steps
                lv.nav(a[0] + (b[0] - a[0]) * t_, 3.0,
                       a[1] + (b[1] - a[1]) * t_)

        lv.pickup("health", 0, 4, 22, respawn=40)
        lv.pickup("ammo", 118, 4, -26, respawn=35)
        lv.pickup("ammo", -118, 4, 26, respawn=35)
        return lv

    # ------------------------------------------------------------------
    def _room(self, lv: Level, name: str, cx, cz, w, d):
        h = 24.0
        lv.box(cx, -1.5, cz, w, 3, d, FLOOR, "tile")
        lv.box(cx, h + 1.5, cz, w, 3, d, FLOOR_DARK, "concrete")
        # perimeter with gaps handled by corridors punching through later
        lv.box(cx, h / 2, cz - d / 2, w, h, 3, WALL, "concrete")
        lv.box(cx, h / 2, cz + d / 2, w, h, 3, WALL, "concrete")
        lv.box(cx - w / 2, h / 2, cz, 3, h, d, WALL, "concrete")
        lv.box(cx + w / 2, h / 2, cz, 3, h, d, WALL, "concrete")
        # trim + lights
        for i in range(-2, 3):
            for j in range(-1, 2):
                lv.add((cx + i * (w / 5), h - 0.9, cz + j * (d / 3.2)),
                       (14, 0.9, 3.6), "#f4f7ff", "neon", glow=1.0,
                       nocollide=True)
            lv.add((cx + i * (w / 5), h - 2.6, cz), (13, 0.35, 2.6),
                   "#cfe4ff", "neon", glow=0.7, nocollide=True)
        lv.box(cx, 0.4, cz, w - 6, 0.5, d - 6, FLOOR_DARK, "tile",
               nocollide=True)

        if name == "reception":
            lv.box(0, 5, 22, 34, 10, 5, WALL_DARK, "metal")
            lv.box(0, 10.5, 22, 36, 1.2, 7, "#9aa2ab", "metal")
            for x in (-24, 24):
                lv.box(x, 4, -6, 8, 8, 8, WALL_DARK, "metal")
            lv.sign(0, 19, 24, "RECEPTION", color=GREEN)
        elif name == "labs":
            for i in range(-1, 2):
                lv.box(cx + i * 22, 4.5, -14, 14, 9, 6, "#c8ced6", "metal")
                lv.add((cx + i * 22, 10.5, -14), (13, 3.0, 5),
                       GLASS, "glass", opacity=0.42, nocollide=True)
            lv.box(cx, 3, 22, 46, 6, 10, WALL_DARK, "metal")
            lv.sign(cx, 15, -32, "LABORATORIES", color=GLASS)
        elif name == "servers":
            for i in range(-3, 4):
                for j in (-1, 1):
                    lv.box(cx + i * 11, 7, cz + j * 16, 7, 14, 20, TRIM,
                           "metal")
                    lv.add((cx + i * 11 + 3.6, 7, cz + j * 16), (0.4, 12, 18),
                           "#3ba7ff", "neon", glow=0.8, nocollide=True)
            lv.sign(cx, 18, cz - 28, "SERVER HALL", color="#3ba7ff")
        elif name == "cold":
            lv.box(cx, 0.6, cz, w - 8, 0.8, d - 8, "#cfe6f2", "snow",
                   nocollide=True)
            for i in range(-2, 3):
                lv.box(cx + i * 15, 6, cz - 18, 8, 12, 8, "#a8c8d8", "glass",
                       opacity=0.7)
                lv.box(cx + i * 15, 6, cz + 18, 8, 12, 8, "#a8c8d8", "glass",
                       opacity=0.7)
            lv.sign(cx, 16, cz - 30, "COLD STORAGE", color="#bfe6ff")
        elif name == "reactor":
            lv.add((cx, 12, cz), (26, 24, 26), "#2f3238", "metal",
                   shape="cylinder")
            lv.add((cx, 12, cz), (22, 22, 22), "#4be08a", "neon",
                   shape="cylinder", glow=1.0, nocollide=True)
            for i in range(8):
                a = i * math.tau / 8
                lv.box(cx + math.cos(a) * 30, 5, cz + math.sin(a) * 30,
                       6, 10, 6, TRIM, "metal")
            for i in range(-2, 3):
                lv.box(cx + i * 18, 0.7, cz - 32, 14, 1.0, 8, HAZARD,
                       "smooth", nocollide=True)
            lv.sign(cx, 20, cz - 36, "REACTOR — DANGER", color=HAZARD)
        elif name == "vault":
            lv.box(cx, 3, cz - 18, 40, 6, 6, RUST, "metal")
            for i in range(-2, 3):
                lv.box(cx + i * 13, 4, cz + 18, 8, 8, 8, RUST, "metal")
            lv.sign(cx, 16, cz - 26, "THE VAULT", color="#f2c53d")

    def _corridor(self, lv: Level, x1, z1, x2, z2, width):
        cx, cz = (x1 + x2) / 2, (z1 + z2) / 2
        dx, dz = abs(x2 - x1), abs(z2 - z1)
        h = 18.0
        if dx >= dz:
            lv.box(cx, -1.5, cz, dx, 3, width + 6, FLOOR, "tile")
            lv.box(cx, h + 1.5, cz, dx, 3, width + 6, FLOOR_DARK, "concrete")
            lv.box(cx, h / 2, cz - width / 2 - 1.5, dx, h, 3, WALL_DARK,
                   "concrete")
            lv.box(cx, h / 2, cz + width / 2 + 1.5, dx, h, 3, WALL_DARK,
                   "concrete")
            n = max(2, int(dx / 16))
            for i in range(n):
                lv.add((x1 + (x2 - x1) * (i + 0.5) / n, h - 0.8, cz),
                       (6, 0.6, 2.4), "#dfe8f5", "neon", glow=0.9,
                       nocollide=True)
        else:
            lv.box(cx, -1.5, cz, width + 6, 3, dz, FLOOR, "tile")
            lv.box(cx, h + 1.5, cz, width + 6, 3, dz, FLOOR_DARK, "concrete")
            lv.box(cx - width / 2 - 1.5, h / 2, cz, 3, h, dz, WALL_DARK,
                   "concrete")
            lv.box(cx + width / 2 + 1.5, h / 2, cz, 3, h, dz, WALL_DARK,
                   "concrete")
            n = max(2, int(dz / 16))
            for i in range(n):
                lv.add((cx, h - 0.8, z1 + (z2 - z1) * (i + 0.5) / n),
                       (2.4, 0.6, 6), "#dfe8f5", "neon", glow=0.9,
                       nocollide=True)

    def _blast_door(self, lv: Level, did: str, x, z, axis: str):
        if axis == "z":
            lv.box(x, 9, z, 3.5, 18, 20, "#b8452c", "metal", tag=did)
            lv.add((x + 2.2, 9, z), (0.4, 14, 16), HAZARD, "neon", glow=0.6,
                   nocollide=True)
        else:
            lv.box(x, 9, z, 20, 18, 3.5, "#b8452c", "metal", tag=did)
            lv.add((x, 9, z + 2.2), (16, 14, 0.4), HAZARD, "neon", glow=0.6,
                   nocollide=True)
