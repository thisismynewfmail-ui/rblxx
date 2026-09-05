"""World 5 — FORT WARS: two hill forts, one canyon, classic capture the flag."""
from __future__ import annotations

import math
import time

from .base import GameMode, WorldDef, WorldMeta
from .builder import Level

GRASS = "#5a9c3a"
DIRT = "#7a5c3a"
STONE = "#9a9a9c"
STONE_DARK = "#74747a"
WOOD = "#8a6231"
WOOD_DARK = "#6b4a2c"
RED = "#c8372c"
BLUE = "#2f7fd6"
WATER = "#2f7fb8"
SAND = "#d8c893"

RED_BASE = (-190.0, 0.0)
BLUE_BASE = (190.0, 0.0)
FLAG_HEIGHT = 27.0


class FortWarsMode(GameMode):
    teams = ("red", "blue")
    score_limit = 3
    time_limit = 900.0
    respawn_delay = 6.0
    hud_kind = "ctf"

    RETURN_TIME = 30.0
    CAPTURE_RADIUS = 12.0
    PICKUP_RADIUS = 7.0
    BRIDGE_HOLD = 8.0

    def __init__(self, room):
        super().__init__(room)
        self.flags = {
            "red": {"team": "red", "home": [RED_BASE[0], FLAG_HEIGHT,
                                            RED_BASE[1]],
                    "pos": [RED_BASE[0], FLAG_HEIGHT, RED_BASE[1]],
                    "state": "home", "carrier": None, "dropped_at": 0.0},
            "blue": {"team": "blue", "home": [BLUE_BASE[0], FLAG_HEIGHT,
                                              BLUE_BASE[1]],
                     "pos": [BLUE_BASE[0], FLAG_HEIGHT, BLUE_BASE[1]],
                     "state": "home", "carrier": None, "dropped_at": 0.0},
        }
        self.bridge_owner: str | None = None
        self.bridge_progress = 0.0
        self.bridge_extended = False

    def start(self):
        self.announce("FORT WARS — three captures wins. Hold the bridge!",
                      "round")

    # -- flags -------------------------------------------------------------
    def enemy_of(self, team): return "blue" if team == "red" else "red"

    def tick(self, now, dt):
        super().tick(now, dt)
        if self.phase != "active":
            return

        # --- central bridge control ---
        counts = {"red": 0, "blue": 0}
        for p in self.room.players.values():
            if not p.alive:
                continue
            if abs(p.state.x) < 22 and abs(p.state.z) < 26 and \
                    -6 < p.state.y < 40:
                counts[p.team] += 1
        net = counts["red"] - counts["blue"]
        if net and not (counts["red"] and counts["blue"]):
            side = "red" if net > 0 else "blue"
            if self.bridge_owner not in (None, side):
                self.bridge_progress = max(0.0, self.bridge_progress -
                                           dt / self.BRIDGE_HOLD * 1.6)
                if self.bridge_progress <= 0.0:
                    self.bridge_owner = None
                    self.set_bridge(False)
            else:
                self.bridge_owner = side
                self.bridge_progress = min(1.0, self.bridge_progress +
                                           dt / self.BRIDGE_HOLD * abs(net) ** 0.6)
                if self.bridge_progress >= 1.0 and not self.bridge_extended:
                    self.set_bridge(True)
                    self.announce(f"{side.upper()} extended the causeway!",
                                  "objective")

        # --- flag logic ---
        for team, flag in self.flags.items():
            carrier = flag["carrier"]
            if carrier is not None:
                p = self.room.players.get(carrier)
                if p is None or not p.alive:
                    self.drop_flag(team)
                    continue
                flag["pos"] = [p.state.x, p.state.y + 5.6, p.state.z]
                # capture?
                own = self.flags[p.team]
                hx, hy, hz = own["home"]
                if own["state"] == "home" and \
                        (p.state.x - hx) ** 2 + (p.state.z - hz) ** 2 < \
                        self.CAPTURE_RADIUS ** 2:
                    self.capture(p, team)
                continue

            if flag["state"] == "dropped":
                if now - flag["dropped_at"] > self.RETURN_TIME:
                    self.return_flag(team, None)
                    continue

            for p in self.room.players.values():
                if not p.alive:
                    continue
                fx, fy, fz = flag["pos"]
                if (p.state.x - fx) ** 2 + (p.state.z - fz) ** 2 > \
                        self.PICKUP_RADIUS ** 2:
                    continue
                if abs(p.state.y + 2.5 - fy) > 14:
                    continue
                if p.team == team:
                    if flag["state"] == "dropped":
                        self.return_flag(team, p)
                        break
                else:
                    self.take_flag(team, p)
                    break

    def set_bridge(self, extended: bool):
        self.bridge_extended = extended
        self.room.set_part_active("causeway", extended)
        self.room.broadcast_event({"t": "bridge", "extended": extended,
                                   "owner": self.bridge_owner})

    def take_flag(self, team, player):
        flag = self.flags[team]
        flag["state"] = "carried"
        flag["carrier"] = player.id
        player.carrying_flag = team
        player.score += 5
        self.announce(f"{player.username} has the {team.upper()} flag!",
                      "objective")
        self.room.broadcast_event({"t": "flag", "team": team,
                                   "state": "carried",
                                   "by": player.username})

    def drop_flag(self, team):
        flag = self.flags[team]
        carrier = self.room.players.get(flag["carrier"] or -1)
        if carrier is not None:
            carrier.carrying_flag = None
            flag["pos"] = [carrier.state.x, max(carrier.state.y + 2.0, -20),
                           carrier.state.z]
        flag["carrier"] = None
        flag["state"] = "dropped"
        flag["dropped_at"] = time.time()
        self.room.broadcast_event({"t": "flag", "team": team,
                                   "state": "dropped"})

    def return_flag(self, team, by):
        flag = self.flags[team]
        flag["state"] = "home"
        flag["carrier"] = None
        flag["pos"] = list(flag["home"])
        if by is not None:
            by.score += 8
            self.announce(f"{by.username} returned the {team.upper()} flag.",
                          "objective")
        else:
            self.announce(f"The {team.upper()} flag returned to base.", "info")
        self.room.broadcast_event({"t": "flag", "team": team, "state": "home"})

    def capture(self, player, team):
        flag = self.flags[team]
        flag["state"] = "home"
        flag["carrier"] = None
        flag["pos"] = list(flag["home"])
        player.carrying_flag = None
        player.score += 40
        player.captures = getattr(player, "captures", 0) + 1
        self.add_score(player.team, 1)
        self.announce(f"{player.username} CAPTURED the {team.upper()} flag!",
                      "victory")
        self.room.broadcast_event({"t": "capture", "by": player.username,
                                   "team": player.team})

    def on_death(self, victim, killer, weapon_id, headshot):
        if victim.carrying_flag:
            self.drop_flag(victim.carrying_flag)
            if killer is not None and killer is not victim:
                killer.score += 10
        if killer is not None and killer is not victim and \
                killer.team != victim.team:
            killer.score += 2

    def hud(self):
        base = super().hud()
        base.update({
            "flags": {t_: {"state": f["state"],
                           "pos": [round(v, 1) for v in f["pos"]],
                           "carrier": (self.room.players[f["carrier"]].username
                                       if f["carrier"] in self.room.players
                                       else None)}
                      for t_, f in self.flags.items()},
            "bridge": {"owner": self.bridge_owner,
                       "progress": round(self.bridge_progress, 3),
                       "extended": self.bridge_extended},
        })
        return base


class FortWars(WorldDef):
    meta = WorldMeta(
        id="fortwars",
        name="Fort Wars",
        tagline="Two forts. One canyon. Three captures to win.",
        description=(
            "Red and Blue hold matching hill forts on either side of a deep "
            "canyon. Grab the enemy banner from their keep, get it home, do "
            "it three times.\n\n"
            "There are three ways across: the long low road through the "
            "riverbed, the zipline from either watchtower, and the central "
            "causeway — which only extends while your team holds the middle "
            "platform. Mounted repeaters cover both gatehouses.\n\n"
            "Classic capture the flag with a control point in the middle."
        ),
        genre="Fighting",
        mode="Capture the Flag",
        max_players=16,
        thumb="fortwars",
        accent="#c8372c",
        sort_order=5,
        tags=["CTF", "Team", "Objective", "Featured"],
        difficulty="Normal",
        recommended="8-16 players",
    )
    mode_class = FortWarsMode

    def build(self) -> Level:
        lv = Level(sky="overcast", ambient=0.55, sun=(-0.35, 0.8, 0.42),
                   fog="#c3cdd6", fog_near=300, fog_far=1100, void_y=-120)
        lv.bounds = [-270, -180, 270, 180]

        # ---- terrain: two plateaus with a real canyon carved between ----
        # Each plateau is solid rock from the canyon floor up to the grass so
        # the gap in the middle is genuinely open all the way down.
        for side, base_x in ((-1, -190), (1, 190)):
            lv.box(base_x, -32, 0, 220, 70, 380, "#4a3c30", "rock")
            lv.box(base_x, -3, 0, 220, 12, 340, GRASS, "grass")
            # stepped cliff shoulder facing the canyon
            for i in range(5):
                lv.box(base_x - side * (110 - i * 7), -10 - i * 8, 0,
                       12, 14, 360 - i * 22, "#6b5a48", "rock")
        # canyon floor + river
        lv.box(0, -80, 0, 200, 62, 420, "#3a3128", "rock")
        lv.box(0, -46, 0, 180, 8, 400, "#5f5244", "rock")
        lv.box(0, -41.5, 0, 60, 3, 400, WATER, "water", nocollide=True)
        for i in range(-2, 3):
            lv.box(i * 13, -41.0, 0, 5, 2.4, 400, "#3a8cc4", "water",
                   nocollide=True)
        # sandy banks + cover in the riverbed
        for i in range(-7, 8):
            lv.box(i * 24, -41.0, -70 + (i % 3) * 60, 16, 3, 20, SAND, "sand")
            lv.box(i * 26, -38, (i % 4) * 40 - 60, 8, 10, 8, "#6b5a48", "rock")

        # ---- the central control platform + retractable causeway ----
        lv.box(0, -6, 0, 44, 8, 52, STONE, "brick")
        lv.box(0, -1.0, 0, 40, 3, 48, "#b8b8ba", "tile")
        for sx in (-19, 19):
            for sz in (-23, 23):
                lv.box(sx, 8, sz, 4, 22, 4, STONE_DARK, "brick")
        lv.box(0, 20, 0, 44, 3, 52, STONE, "brick")
        lv.add((0, 3, 0), (16, 1.0, 16), "#f2c53d", "neon", glow=0.8,
               nocollide=True, tag="controlpad")
        # supports down to the riverbed so it can be climbed
        lv.box(0, -26, -22, 8, 40, 8, STONE_DARK, "concrete")
        lv.box(0, -26, 22, 8, 40, 8, STONE_DARK, "concrete")
        lv.stairs(0, -38, -50, steps=12, rise=2.7, run=3.2, width=12,
                  direction="+z", color=STONE_DARK, texture="concrete")
        # the causeway itself (toggled by the mode)
        for side in (-1, 1):
            for i in range(6):
                lv.box(side * (30 + i * 12), 0.0, 0, 12, 2.0, 16,
                       "#d8c07a", "plank", tag="causeway")

        # ---- forts ----
        self._fort(lv, RED_BASE[0], RED_BASE[1], RED, "red", face=1)
        self._fort(lv, BLUE_BASE[0], BLUE_BASE[1], BLUE, "blue", face=-1)

        # ---- ziplines between the watchtowers and the middle ----
        for side, colour in ((-1, RED), (1, BLUE)):
            lv.objective("zipline", side * 148, 44, -96,
                         to=[side * 26, 24, -20], team="red" if side < 0
                         else "blue")
            lv.objective("zipline", side * 148, 44, 96,
                         to=[side * 26, 24, 20], team="red" if side < 0
                         else "blue")

        # ---- low road bridges into the riverbed ----
        for side in (-1, 1):
            lv.ramp(side * 96, -3, -140, length=54, height=-38, width=16,
                    direction="+z" if side < 0 else "+z", color=DIRT,
                    texture="rock", segs=14)
            lv.ramp(side * 96, -3, 96, length=54, height=-38, width=16,
                    direction="+z", color=DIRT, texture="rock", segs=14)

        # ---- scenery ----
        for i in range(28):
            ang = i * 2.399963
            r = 120 + (i * 29) % 130
            x = math.cos(ang) * r * 1.5
            z = math.sin(ang) * r
            if abs(x) < 110 or abs(x) > 285 or abs(z) > 165:
                continue
            lv.tree(x, z, style="pine" if i % 2 else "round",
                    scale=0.9 + (i % 3) * 0.2)

        # perimeter cliffs
        for sz in (-1, 1):
            lv.box(0, 30, sz * 178, 620, 90, 24, "#6b5a48", "rock")
        for sx in (-1, 1):
            lv.box(sx * 296, 30, 0, 24, 90, 400, "#6b5a48", "rock")

        # ---- spawns ----
        # bailey spots, deliberately clear of the keep and the wall stairs
        spots = [(44, -60), (44, -20), (44, 20), (44, 60),
                 (14, -66), (38, -66), (14, 66), (38, 66)]
        for dx, dz in spots:
            lv.spawn(RED_BASE[0] - dx, 22.4, dz, "red", -90)
            lv.spawn(BLUE_BASE[0] + dx, 22.4, dz, "blue", 90)

        # ---- pickups ----
        lv.pickup("damage", 0, 26, 0, respawn=45)
        lv.pickup("armor", 0, 4, 0, respawn=32)
        lv.pickup("health", -120, 6, -70, respawn=20)
        lv.pickup("health", 120, 6, 70, respawn=20)
        lv.pickup("health", -120, 6, 70, respawn=20)
        lv.pickup("health", 120, 6, -70, respawn=20)
        lv.pickup("ammo", -172, 24, -60, respawn=14)
        lv.pickup("ammo", 172, 24, 60, respawn=14)
        lv.pickup("speed", -60, -38, 0, respawn=30)
        lv.pickup("speed", 60, -38, 0, respawn=30)
        lv.pickup("gravity", 0, -38, -120, respawn=30)
        return lv

    # ------------------------------------------------------------------
    def _fort(self, lv: Level, cx: float, cz: float, colour: str, team: str,
              face: int):
        # motte
        for i, (w, d, h) in enumerate(((150, 220, 7), (128, 190, 7),
                                       (108, 160, 7))):
            lv.box(cx, 3.5 + i * 7, cz, w, h, d, GRASS if i < 2 else DIRT,
                   "grass" if i < 2 else "rock")
        base_y = 21.0

        # curtain wall
        lv.room(cx, cz, 104, 156, 22, STONE, "brick", y=base_y,
                door="e" if face > 0 else "w")
        # walkway on top of the wall
        for sx, sz, w, d in ((cx, cz - 78, 104, 8), (cx, cz + 78, 104, 8),
                             (cx - 52, cz, 8, 156), (cx + 52, cz, 8, 156)):
            lv.box(sx, base_y + 23.5, sz, w, 3, d, STONE_DARK, "brick")
        # crenellations
        for i in range(-12, 13):
            lv.box(cx + i * 4.1, base_y + 27, cz - 80, 2.6, 4, 2.6, STONE,
                   "brick")
            lv.box(cx + i * 4.1, base_y + 27, cz + 80, 2.6, 4, 2.6, STONE,
                   "brick")
        for i in range(-18, 19):
            lv.box(cx - 54, base_y + 27, cz + i * 4.1, 2.6, 4, 2.6, STONE,
                   "brick")

        # keep (flag room)
        lv.room(cx - face * 14, cz, 48, 52, 26, colour, "brick", y=base_y,
                door="e" if face > 0 else "w")
        lv.box(cx - face * 14, base_y + 27.5, cz, 52, 3, 56, STONE_DARK,
               "brick")
        lv.box(cx - face * 14, base_y + 1.0, cz, 42, 2, 46, "#c8c8ca", "tile")
        # flag pedestal
        lv.add((cx, base_y + 2.0, cz), (14, 2, 14), "#d8d8da", "tile",
               shape="cylinder")
        lv.box(cx, base_y + 12, cz, 1.2, 18, 1.2, "#4a4a4c", "metal")

        # stairs from bailey to the wall walk
        lv.stairs(cx + face * 30, base_y, cz - 60, steps=12, rise=2.0,
                  run=3.0, width=10, direction="+z", color=STONE_DARK,
                  texture="brick")

        # gatehouse + mounted repeaters
        gx = cx + face * 52
        lv.box(gx, base_y + 14, cz - 14, 10, 28, 12, STONE_DARK, "brick")
        lv.box(gx, base_y + 14, cz + 14, 10, 28, 12, STONE_DARK, "brick")
        lv.box(gx, base_y + 26, cz, 10, 6, 40, STONE_DARK, "brick")
        for sz in (-14, 14):
            lv.objective("turret", gx, base_y + 30, cz + sz, team=team,
                         yaw=90 * face)
            lv.box(gx, base_y + 30, cz + sz, 4, 3, 4, "#3a3a3c", "metal")

        # watchtowers (zipline anchors)
        for sz in (-96, 96):
            tx = cx + face * 42
            lv.box(tx, base_y + 12, sz, 16, 46, 16, WOOD_DARK, "wood")
            lv.box(tx, base_y + 36, sz, 22, 3, 22, WOOD, "plank")
            for ox, oz in ((-10, -10), (10, -10), (-10, 10), (10, 10)):
                lv.box(tx + ox, base_y + 40, sz + oz, 1.4, 8, 1.4, WOOD,
                       "wood")
            lv.stairs(tx - face * 14, base_y, sz - 14, steps=12, rise=1.9,
                      run=2.6, width=8, direction="+z", color=WOOD,
                      texture="plank")

        # banner
        lv.box(cx - face * 14, base_y + 40, cz, 1.2, 22, 1.2, "#3a3a3c",
               "metal")
        lv.box(cx - face * 14 + face * 6, base_y + 46, cz, 12, 14, 0.5,
               colour, "smooth")
        lv.sign(cx + face * 62, base_y + 24, cz,
                "RED KEEP" if team == "red" else "BLUE KEEP", color=colour)
