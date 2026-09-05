"""World 1 — CROSSROADS: the classic four-corner team deathmatch baseplate."""
from __future__ import annotations

import math
import time

from .base import GameMode, WorldDef, WorldMeta
from .builder import Level

GRASS = "#4f9c33"
GRASS_DARK = "#3f7f28"
ROAD = "#c8c8c8"
STONE = "#a3a3a5"
STONE_DARK = "#7c7c7e"
BRICK_RED = "#9c3a2e"
BRICK_BLUE = "#2f5f9c"
WOOD = "#8a6231"
WATER = "#2f7fb8"
SAND = "#d8c893"


class CrossroadsMode(GameMode):
    teams = ("red", "blue")
    score_limit = 60
    time_limit = 720.0
    hud_kind = "tdm"

    def __init__(self, room):
        super().__init__(room)
        self.next_overtime_note = 0.0

    def start(self):
        self.announce("CROSSROADS — Red vs Blue. First to 60 eliminations.",
                      "round")

    def tick(self, now, dt):
        super().tick(now, dt)
        if self.phase != "active":
            return
        left = self.round_end_at - now
        if left < 60 and now > self.next_overtime_note:
            self.next_overtime_note = now + 30
            self.announce(f"{int(left)} seconds remain!", "warn")

    def on_death(self, victim, killer, weapon_id, headshot):
        super().on_death(victim, killer, weapon_id, headshot)
        if killer is not None and killer is not victim and killer.streak == 5:
            self.announce(f"{killer.username} is on a rampage!", "streak")
        elif killer is not None and killer.streak == 10:
            self.announce(f"{killer.username} is UNSTOPPABLE!", "streak")


class Crossroads(WorldDef):
    meta = WorldMeta(
        id="crossroads",
        name="Crossroads",
        tagline="The map that started it all.",
        description=(
            "Four fortified corners, one contested bridge and a whole lot of "
            "history. Red and Blue clash across the original baseplate: hold "
            "the central tower, work the tunnels beneath the ruins, and grab "
            "a Speed Coil before the other team does.\n\n"
            "Classic team deathmatch. First squad to 60 eliminations takes it."
        ),
        genre="Fighting",
        mode="Team Deathmatch",
        max_players=16,
        thumb="crossroads",
        accent="#5aa02c",
        sort_order=1,
        tags=["Classic", "Team", "Shooter", "Featured"],
        difficulty="Normal",
        recommended="6-16 players",
    )
    mode_class = CrossroadsMode

    def build(self) -> Level:
        lv = Level(sky="classic", ambient=0.58, sun=(0.38, 0.84, 0.38),
                   fog="#cfe6f5", fog_near=340, fog_far=1000, void_y=-90)
        lv.bounds = [-190, -190, 190, 190]

        # ---------------- ground ----------------
        lv.baseplate(size=420, color=GRASS, texture="grass", thickness=12)
        # patchwork of darker grass for texture variety
        for i in range(26):
            ang = i * 2.399963
            r = 24 + (i * 13) % 150
            x, z = math.cos(ang) * r, math.sin(ang) * r
            s = 14 + (i * 7) % 26
            lv.box(x, -0.4, z, s, 1.2, s, GRASS_DARK, "grass", nocollide=False)

        # ---------------- the crossroads themselves ----------------
        lv.box(0, 0.3, 0, 24, 1.4, 340, ROAD, "concrete")
        lv.box(0, 0.3, 0, 340, 1.4, 24, ROAD, "concrete")
        for i in range(-8, 9):
            lv.box(0, 1.05, i * 20, 2.2, 0.2, 9, "#f2e05a", "smooth",
                   nocollide=True)
            lv.box(i * 20, 1.05, 0, 9, 0.2, 2.2, "#f2e05a", "smooth",
                   nocollide=True)

        # ---------------- central lake + bridge ----------------
        lv.box(0, -3.0, 78, 96, 6, 60, "#274a2a", "rock")
        lv.box(0, -0.6, 78, 92, 3.0, 56, WATER, "water", nocollide=True,
               tag="water")
        lv.box(0, 1.6, 78, 22, 1.6, 62, WOOD, "plank", tag="bridge")
        for side in (-11.5, 11.5):
            for i in range(-3, 4):
                lv.box(side, 4.0, 78 + i * 8.5, 1.0, 4.0, 1.0, WOOD, "wood")
            lv.box(side, 6.4, 78, 1.2, 1.2, 62, WOOD, "wood")
        for x in (-24, 24):
            lv.tree(x, 108, style="round", scale=1.1)

        # ---------------- central tower (contested high ground) ----------
        self._central_tower(lv)

        # ---------------- red fort (west) ----------------
        self._fort(lv, -122, 0, BRICK_RED, "red", flip=False)
        # ---------------- blue fort (east) ----------------
        self._fort(lv, 122, 0, BRICK_BLUE, "blue", flip=True)

        # ---------------- north: hillside cabin & sniper deck ----------
        self._cabin(lv, 0, -128)
        # ---------------- south: stone ruins + tunnel ----------------
        self._ruins(lv, 0, 150)

        # ---------------- scenery ----------------
        scatter = [(-165, -150), (-150, -95), (-90, -160), (60, -165),
                   (150, -140), (170, -70), (165, 70), (150, 140),
                   (80, 165), (-70, 168), (-150, 150), (-172, 40),
                   (-58, -60), (58, -60), (-58, 60), (58, 60)]
        for i, (x, z) in enumerate(scatter):
            lv.tree(x, z, scale=0.9 + (i % 4) * 0.16,
                    style="pine" if i % 3 == 0 else "round",
                    leaves="#2f7d32" if i % 2 else "#39913c")
        for x, z in ((-34, -34), (34, -34), (-34, 34), (34, 34)):
            lv.light_post(x, z)

        # low perimeter wall so players cannot wander off the plate
        for sign in (-1, 1):
            lv.box(sign * 186, 8, 0, 8, 16, 380, STONE_DARK, "brick")
            lv.box(0, 8, sign * 186, 380, 16, 8, STONE_DARK, "brick")

        # ---------------- spawns ----------------
        for i in range(8):
            lv.spawn(-136 + (i % 4) * 7, 4, -14 + (i // 4) * 28, "red", 90)
            lv.spawn(136 - (i % 4) * 7, 4, -14 + (i // 4) * 28, "blue", -90)

        # ---------------- pickups ----------------
        lv.pickup("speed", 0, 6, -46, respawn=28)
        lv.pickup("gravity", 0, 6, 46, respawn=28)
        lv.pickup("health", -62, 5, -62, respawn=18)
        lv.pickup("health", 62, 5, 62, respawn=18)
        lv.pickup("health", -62, 5, 62, respawn=18)
        lv.pickup("health", 62, 5, -62, respawn=18)
        lv.pickup("damage", 0, 34, 0, respawn=45)
        lv.pickup("ammo", -100, 5, -100, respawn=15)
        lv.pickup("ammo", 100, 5, 100, respawn=15)
        lv.pickup("armor", 0, 5, 150, respawn=35)

        lv.sign(0, 14, -60, "CROSSROADS", color="#f2e05a")
        return lv

    # ------------------------------------------------------------------
    def _central_tower(self, lv: Level):
        lv.box(0, 1.5, 0, 60, 3, 60, STONE, "brick")
        lv.box(0, 5.0, 0, 46, 4, 46, STONE, "brick")
        # corner pillars
        for sx in (-19, 19):
            for sz in (-19, 19):
                lv.box(sx, 16, sz, 5, 26, 5, STONE_DARK, "brick")
        # upper deck
        lv.box(0, 29.5, 0, 46, 3, 46, STONE, "brick")
        for sx, sz, w, d in ((0, -22.5, 46, 2), (0, 22.5, 46, 2),
                             (-22.5, 0, 2, 46), (22.5, 0, 2, 46)):
            lv.box(sx, 33.0, sz, w, 6, d, STONE_DARK, "brick")
        # crenellations
        for i in range(-5, 6):
            for (x, z) in ((i * 4.2, -22.5), (i * 4.2, 22.5),
                           (-22.5, i * 4.2), (22.5, i * 4.2)):
                lv.box(x, 37.5, z, 2.4, 3.0, 2.4, STONE, "brick")
        # ramps up from the road, on all four faces
        lv.ramp(-30, 3, -8, length=22, height=26.5, width=14, direction="+x",
                color=STONE_DARK, texture="brick", segs=11)
        lv.ramp(30, 3, 8, length=22, height=26.5, width=14, direction="-x",
                color=STONE_DARK, texture="brick", segs=11)
        # top beacon
        lv.add((0, 44, 0), (4, 10, 4), "#f2c53d", "neon", shape="cylinder",
               glow=1.0, nocollide=True)
        lv.add((0, 50, 0), (6, 6, 6), "#ffe07a", "neon", shape="sphere",
               glow=1.0, nocollide=True)

    def _fort(self, lv: Level, cx: float, cz: float, brick: str, team: str,
              flip: bool):
        d = -1 if flip else 1
        # platform
        lv.box(cx, 2.0, cz, 74, 4, 96, STONE, "concrete")
        # keep
        lv.room(cx - d * 8, cz, 46, 66, 20, brick, "brick", y=4,
                door="e" if not flip else "w")
        lv.box(cx - d * 8, 24.5, cz, 46, 3, 66, STONE, "concrete")
        # battlements on the roof
        for i in range(-7, 8):
            lv.box(cx - d * 8 + i * 3.0, 27.5, cz - 32, 2.2, 3.0, 2.2, brick,
                   "brick")
            lv.box(cx - d * 8 + i * 3.0, 27.5, cz + 32, 2.2, 3.0, 2.2, brick,
                   "brick")
        for i in range(-10, 11):
            lv.box(cx - d * 31, 27.5, cz + i * 3.0, 2.2, 3.0, 2.2, brick,
                   "brick")
        # interior spawn room floor markings
        lv.box(cx - d * 8, 4.3, cz, 40, 0.6, 60,
               "#8a2a20" if team == "red" else "#254f86", "tile",
               nocollide=True)
        # stairs up to the roof
        lv.stairs(cx + d * 12, 4, cz - 26, steps=10, rise=2.05, run=3.2,
                  width=10, direction="+z", color=STONE_DARK,
                  texture="concrete")
        # forward barricades
        for z in (-30, 0, 30):
            lv.box(cx + d * 44, 6.5, cz + z, 4, 9, 18, STONE_DARK, "concrete")
        # team banner
        lv.box(cx - d * 8, 34, cz, 1.0, 16, 1.0, "#3a3a3a", "metal")
        lv.box(cx - d * 8 + d * 5, 38, cz, 10, 12, 0.4,
               "#c8372c" if team == "red" else "#2f7fd6", "smooth")
        lv.sign(cx + d * 40, 16, cz, "RED BASE" if team == "red" else "BLUE BASE",
                color="#c8372c" if team == "red" else "#2f7fd6")
        lv.pickup("ammo", cx, 6, cz - 40, respawn=12)
        lv.pickup("ammo", cx, 6, cz + 40, respawn=12)

    def _cabin(self, lv: Level, cx: float, cz: float):
        # hill
        for i, (w, h) in enumerate(((92, 4), (74, 4), (56, 4), (40, 4))):
            lv.box(cx, 2 + i * 4, cz, w, h, w * 0.75, GRASS_DARK, "grass")
        top = 18
        lv.room(cx, cz, 34, 26, 16, WOOD, "plank", y=top, door="s")
        lv.box(cx, top + 17.5, cz, 38, 3, 30, "#6b4a2c", "wood")
        lv.box(cx, top + 20.0, cz, 30, 2.5, 22, "#7d5834", "wood")
        # sniper deck
        lv.box(cx, top + 22.0, cz + 20, 30, 2, 14, WOOD, "plank")
        for i in range(-4, 5):
            lv.box(cx + i * 3.4, top + 24.0, cz + 26.5, 1.6, 3, 1.6, WOOD,
                   "wood")
        lv.stairs(cx + 22, 18, cz + 6, steps=8, rise=1.6, run=3.0, width=8,
                  direction="+z", color=WOOD, texture="plank")
        lv.pickup("health", cx, top + 3, cz, respawn=20)
        lv.sign(cx, top + 26, cz + 26, "LOOKOUT", color="#f2e05a")

    def _ruins(self, lv: Level, cx: float, cz: float):
        lv.box(cx, 1.0, cz, 110, 2, 70, SAND, "sand")
        # broken columns
        for i in range(-4, 5):
            h = 10 + (abs(i) % 3) * 7
            lv.box(cx + i * 12, 2 + h / 2, cz - 24, 5, h, 5, STONE, "rock")
            h2 = 8 + ((i + 1) % 3) * 8
            lv.box(cx + i * 12, 2 + h2 / 2, cz + 24, 5, h2, 5, STONE, "rock")
        # sunken tunnel (a covered flank route)
        lv.box(cx, -4.5, cz, 24, 9, 62, "#3c3c3e", "rock")
        lv.box(cx, 1.2, cz, 20, 1.6, 58, STONE_DARK, "concrete")
        lv.box(cx, 8.5, cz, 26, 3, 46, STONE, "rock")
        for i in range(6):
            lv.box(cx - 10 + i * 4, 0.2, cz - 31 + i * 1.5, 20, 1.2, 4,
                   STONE_DARK, "rock")
        lv.add((cx, 6.0, cz), (2.4, 2.4, 2.4), "#ffd98a", "neon",
               shape="sphere", glow=1.0, nocollide=True)
        lv.pickup("armor", cx, 4, cz, respawn=30)
        lv.sign(cx, 14, cz - 34, "RUINS", color="#e8d9a8")
