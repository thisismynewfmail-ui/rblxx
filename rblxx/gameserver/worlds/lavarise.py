"""World 4 — LAVA RISE: free-for-all tower survival against a rising lava tide."""
from __future__ import annotations

import math
import time

from .base import GameMode, WorldDef, WorldMeta
from .builder import Level

ROCK = "#6e5a4a"
ROCK_DARK = "#54453a"
OBSIDIAN = "#2a2430"
BASALT = "#8c7563"
EMBER = "#ff7a2a"
GOLD = "#f2c53d"
WOOD = "#8a6231"

TIERS = [
    #  y     radius   style
    (6,    92, "ring"),
    (34,   78, "ring"),
    (62,   64, "spokes"),
    (90,   52, "ring"),
    (118,  40, "spokes"),
    (146,  30, "ring"),
    (174,  20, "crown"),
]


class LavaRiseMode(GameMode):
    teams = ("neutral",)
    friendly_fire = True
    score_limit = 0
    time_limit = 0.0
    respawn_delay = 0.0
    allow_respawn = False
    hud_kind = "lavarise"

    LAVA_START = -14.0
    LAVA_TOP = 182.0
    GRACE = 20.0
    ROUND_MAX = 330.0
    INTERMISSION = 14.0

    def __init__(self, room):
        super().__init__(room)
        self.round_no = 0
        self.state = "intermission"
        self.state_until = time.time() + 8.0
        self.lava_y = self.LAVA_START
        self.rise_rate = 0.0
        self.round_started = 0.0
        self.alive_order: list[str] = []
        self.last_winner: str | None = None
        self.crumbled: dict[str, float] = {}

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        self.announce("LAVA RISE — last blockhead standing wins the round.",
                      "round")

    def on_join(self, player):
        player.team = "neutral"
        player.wins = getattr(player, "wins", 0)
        if self.state == "playing":
            player.spectating = True

    def contenders(self):
        return [p for p in self.room.players.values()
                if p.alive and not p.spectating]

    def tick(self, now, dt):
        if self.state == "intermission":
            if now >= self.state_until and len(self.room.players) >= 1:
                self.begin_round()
            return

        elapsed = now - self.round_started

        # ---- lava ----
        if elapsed > self.GRACE:
            t_ = elapsed - self.GRACE
            self.rise_rate = 1.15 + min(3.4, t_ / 42.0)
            self.lava_y = min(self.LAVA_TOP, self.lava_y + self.rise_rate * dt)
        self.room.set_lava(self.lava_y)

        # ---- crumbling platforms ----
        for tag, expire in list(self.crumbled.items()):
            if now >= expire:
                self.crumbled.pop(tag, None)
                self.room.set_part_active(tag, True)

        # ---- burn anything under the tide ----
        for p in self.contenders():
            if p.state.y < self.lava_y - 0.4:
                self.room.apply_damage(p, None, 42.0 * dt, "lava")

        alive = self.contenders()
        if self.state == "playing":
            if len(alive) == 1 and len(self.room.players) > 1:
                self.finish_round(alive[0])
            elif not alive:
                self.finish_round(None)
            elif self.lava_y >= self.LAVA_TOP and elapsed > self.ROUND_MAX:
                self.finish_round(max(alive, key=lambda p: p.state.y)
                                  if alive else None)

    def begin_round(self):
        self.round_no += 1
        self.state = "playing"
        self.round_started = time.time()
        self.lava_y = self.LAVA_START
        self.rise_rate = 0.0
        self.crumbled.clear()
        self.room.reset_all_parts()
        for p in self.room.players.values():
            p.spectating = False
            self.room.respawn(p, force=True)
        self.announce(f"ROUND {self.round_no} — the tide rises in "
                      f"{int(self.GRACE)} seconds.", "round")
        self.room.broadcast_event({"t": "lavaround", "round": self.round_no})

    def finish_round(self, winner):
        self.state = "intermission"
        self.state_until = time.time() + self.INTERMISSION
        if winner is not None:
            winner.wins = getattr(winner, "wins", 0) + 1
            winner.score += 100
            self.last_winner = winner.username
            self.announce(f"{winner.username} survives the tide!", "victory")
        else:
            self.last_winner = None
            self.announce("The tide takes everyone. Nobody survives.",
                          "defeat")
        self.room.on_round_end(winner.username if winner else None)

    def on_death(self, victim, killer, weapon_id, headshot):
        victim.spectating = True
        if killer is not None and killer is not victim:
            killer.score += 25
            self.announce(f"{killer.username} eliminated {victim.username}",
                          "kill", ttl=2.5)

    def on_stand(self, player, tag: str):
        """Called when a player stands on a tagged crumbling platform."""
        if tag and tag.startswith("crumb") and tag not in self.crumbled:
            self.crumbled[tag] = time.time() + 9.0
            self.room.set_part_active(tag, False, delay=1.4)

    def hud(self):
        return {
            "kind": "lavarise",
            "phase": self.state,
            "round": self.round_no,
            "lava": round(self.lava_y, 2),
            "riseRate": round(self.rise_rate, 2),
            "alive": len(self.contenders()),
            "total": len(self.room.players),
            "nextIn": max(0.0, self.state_until - time.time())
                      if self.state == "intermission" else 0.0,
            "grace": max(0.0, self.GRACE - (time.time() - self.round_started))
                     if self.state == "playing" else 0.0,
            "lastWinner": self.last_winner,
        }


class LavaRise(WorldDef):
    meta = WorldMeta(
        id="lavarise",
        name="Lava Rise",
        tagline="Climb, fight, survive. The floor is very much lava.",
        description=(
            "A volcanic spire in the middle of a caldera. When the round "
            "starts you get twenty seconds of grace — then the lava begins "
            "to climb, and it never stops.\n\n"
            "Fight your way up seven tiers of crumbling basalt. Orange "
            "platforms give way about a second after you land on them. Jump "
            "pads, bridges and a very exposed crown at the top are the only "
            "way to stay dry.\n\n"
            "Free-for-all. Friendly fire is very much on. Last survivor wins "
            "the round."
        ),
        genre="Adventure",
        mode="Battle Royale",
        max_players=16,
        thumb="lavarise",
        accent="#ff7a2a",
        sort_order=4,
        tags=["FFA", "Parkour", "Survival", "Rounds"],
        difficulty="Hard",
        recommended="4-16 players",
    )
    mode_class = LavaRiseMode

    def build(self) -> Level:
        lv = Level(sky="ember", ambient=0.62, sun=(0.5, 0.62, -0.6),
                   fog="#4a2418", fog_near=220, fog_far=900, void_y=-60)
        lv.bounds = [-190, -190, 190, 190]

        # caldera floor + lava pit (the moving tide is a dynamic part)
        lv.add((0, -22, 0), (360, 8, 360), OBSIDIAN, "rock")
        lv.add((0, -16.5, 0), (352, 4, 352), "#e04d16", "lava", glow=0.42,
               nocollide=True, damage=42, tag="lavafloor")
        # caldera walls
        seg = 36
        for i in range(seg):
            a = i * math.tau / seg
            x, z = math.cos(a) * 172, math.sin(a) * 172
            lv.box(x, 60, z, 34, 200, 34, "#6b5344", "rock",
                   rot=[0, -math.degrees(a), 0])

        # ---- the spire ----
        core_prev_r = None
        for idx, (y, r, style) in enumerate(TIERS):
            self._tier(lv, idx, y, r, style)
            if core_prev_r is not None:
                self._connect(lv, idx, TIERS[idx - 1][0], TIERS[idx - 1][1],
                              y, r)
            core_prev_r = r

        # central column
        lv.add((0, 92, 0), (18, 190, 18), OBSIDIAN, "rock", shape="cylinder")

        # crown
        lv.add((0, 188, 0), (24, 4, 24), GOLD, "metal", shape="cylinder")
        lv.add((0, 194, 0), (5, 12, 5), "#ffb03a", "neon", shape="cylinder",
               glow=1.0, nocollide=True)
        lv.sign(0, 200, 0, "THE CROWN", color=GOLD)

        # ---- spawns: spread around the lowest ring ----
        for i in range(16):
            a = i * math.tau / 16
            lv.spawn(math.cos(a) * 78, 10, math.sin(a) * 78, "neutral",
                     math.degrees(a) + 180)

        # ---- pickups spread up the tower (better loot higher up) ----
        lv.pickup("health", 0, 12, 70, respawn=22)
        lv.pickup("health", 0, 12, -70, respawn=22)
        lv.pickup("ammo", 62, 12, 0, respawn=16)
        lv.pickup("ammo", -62, 12, 0, respawn=16)
        lv.pickup("speed", 0, 40, 58, respawn=30)
        lv.pickup("gravity", 0, 68, -46, respawn=30)
        lv.pickup("armor", 0, 96, 36, respawn=34)
        lv.pickup("damage", 0, 124, 0, respawn=42)
        lv.pickup("health", 0, 152, 20, respawn=25)
        return lv

    # ------------------------------------------------------------------
    def _tier(self, lv: Level, idx: int, y: float, r: float, style: str):
        thickness = 5.0
        colour = ROCK if idx % 2 == 0 else BASALT
        if style == "ring":
            seg = max(12, int(r / 3))
            for i in range(seg):
                a = i * math.tau / seg
                px, pz = math.cos(a) * r * 0.78, math.sin(a) * r * 0.78
                w = max(9.0, r * 0.42)
                crumbly = (i % 4 == 3)
                lv.box(px, y, pz, w, thickness, w,
                       EMBER if crumbly else colour,
                       "rock" if not crumbly else "smooth",
                       tag=f"crumb_{idx}_{i}" if crumbly else None,
                       rot=[0, -math.degrees(a), 0])
            lv.add((0, y, 0), (r * 0.95, thickness, r * 0.95), colour, "rock",
                   shape="cylinder")
        elif style == "spokes":
            for i in range(6):
                a = i * math.tau / 6
                length = r * 1.5
                px, pz = math.cos(a) * r * 0.55, math.sin(a) * r * 0.55
                lv.box(px, y, pz, length if abs(math.cos(a)) > 0.5 else 14,
                       thickness,
                       14 if abs(math.cos(a)) > 0.5 else length,
                       colour, "rock", rot=[0, -math.degrees(a), 0])
                if i % 2 == 0:
                    lv.box(math.cos(a) * r, y + 4.5, math.sin(a) * r, 10, 4,
                           10, EMBER, "smooth", tag=f"crumb_{idx}_s{i}")
            lv.add((0, y, 0), (r * 0.7, thickness, r * 0.7), colour, "rock",
                   shape="cylinder")
        else:  # crown
            lv.add((0, y, 0), (r * 2, thickness, r * 2), colour, "rock",
                   shape="cylinder")
            for i in range(8):
                a = i * math.tau / 8
                lv.box(math.cos(a) * (r - 3), y + 4.5, math.sin(a) * (r - 3),
                       5, 6, 5, OBSIDIAN, "rock")

        # cover blocks + a jump pad per tier
        for i in range(4):
            a = i * math.tau / 4 + 0.7
            lv.box(math.cos(a) * r * 0.55, y + 5.0, math.sin(a) * r * 0.55,
                   7, 7, 7, ROCK_DARK, "rock")
        lv.box(0, y + 3.2, r * 0.62, 9, 1.4, 9, "#38d0ff", "neon", glow=0.8,
               tag="launch")
        lv.add((0, y + 4.2, r * 0.62), (8, 0.3, 8), "#8ff0ff", "neon",
               glow=1.0, nocollide=True)

    def _connect(self, lv: Level, idx: int, y0, r0, y1, r1):
        """A ramp and a rope-bridge linking one tier to the next."""
        a0 = idx * 0.9
        x0, z0 = math.cos(a0) * r0 * 0.8, math.sin(a0) * r0 * 0.8
        x1, z1 = math.cos(a0 + 0.7) * r1 * 0.8, math.sin(a0 + 0.7) * r1 * 0.8
        steps = 9
        for i in range(1, steps):
            t_ = i / steps
            px = x0 + (x1 - x0) * t_
            pz = z0 + (z1 - z0) * t_
            py = y0 + (y1 - y0) * t_
            lv.box(px, py, pz, 9, 1.6, 9, WOOD, "plank")
            if i % 3 == 0:
                lv.box(px, py + 3, pz, 0.6, 6, 0.6, "#5b4630", "wood")
