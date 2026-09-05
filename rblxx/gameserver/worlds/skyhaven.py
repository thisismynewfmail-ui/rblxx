"""World 2 — SKY HAVEN: low-gravity floating islands, roaming King of the Hill."""
from __future__ import annotations

import math
import time

from .base import GameMode, WorldDef, WorldMeta
from .builder import Level

CLOUD = "#e8f2fb"
STONE = "#8e9aa6"
STONE_LIGHT = "#b3bdc7"
GOLD = "#f2c53d"
MOSS = "#4f9c5a"
SUN_T = "#f0a52a"
MOON_T = "#8a6bd8"

ISLANDS = [
    # (id,        x,     y,    z,    radius, height)
    ("home_sun",  -168,  34,   0,    44, 12),
    ("home_moon",  168,  34,   0,    44, 12),
    ("centre",       0,  52,   0,    40, 14),
    ("north",        0,  40, -118,   32, 10),
    ("south",        0,  40,  118,   32, 10),
    ("nw",         -96,  66,  -92,   26,  9),
    ("ne",          96,  66,  -92,   26,  9),
    ("sw",         -96,  66,   92,   26,  9),
    ("se",          96,  66,   92,   26,  9),
    ("high",         0,  96,    0,   20,  8),
]
ISLAND_BY_ID = {i[0]: i for i in ISLANDS}
BEACON_ISLANDS = ["centre", "north", "south", "nw", "ne", "sw", "se", "high"]


class SkyHavenMode(GameMode):
    teams = ("sun", "moon")
    score_limit = 300
    time_limit = 900.0
    respawn_delay = 3.0
    hud_kind = "koth"

    BEACON_PERIOD = 75.0
    CAPTURE_RATE = 0.34          # progress/sec per player
    RADIUS = 22.0

    def __init__(self, room):
        super().__init__(room)
        self.beacon_index = 0
        self.beacon_island = BEACON_ISLANDS[0]
        self.beacon_moves_at = time.time() + self.BEACON_PERIOD
        self.capture = 0.0            # -1 (moon) .. +1 (sun)
        self.owner: str | None = None
        self.point_accum = 0.0
        self._last_contested = False

    def beacon_pos(self):
        _, x, y, z, r, h = ISLAND_BY_ID[self.beacon_island]
        return (x, y + h / 2 + 1.0, z)

    def start(self):
        self.announce("SKY HAVEN — hold the Beacon. It relocates every 75s.",
                      "round")
        self.room.broadcast_event({"t": "beacon", "island": self.beacon_island,
                                   "p": list(self.beacon_pos())})

    def tick(self, now, dt):
        super().tick(now, dt)
        if self.phase != "active":
            return

        if now >= self.beacon_moves_at:
            self.beacon_index = (self.beacon_index + 1) % len(BEACON_ISLANDS)
            self.beacon_island = BEACON_ISLANDS[self.beacon_index]
            self.beacon_moves_at = now + self.BEACON_PERIOD
            self.capture = 0.0
            self.owner = None
            self.announce(f"The Beacon has moved to {self.beacon_island.upper()}!",
                          "objective")
            self.room.broadcast_event({"t": "beacon",
                                       "island": self.beacon_island,
                                       "p": list(self.beacon_pos())})

        bx, by, bz = self.beacon_pos()
        counts = {"sun": 0, "moon": 0}
        for p in self.room.players.values():
            if not p.alive:
                continue
            dx = p.state.x - bx
            dz = p.state.z - bz
            dy = p.state.y - by
            if dx * dx + dz * dz <= self.RADIUS ** 2 and abs(dy) < 26:
                counts[p.team] = counts.get(p.team, 0) + 1
                p.on_point = True
            else:
                p.on_point = False

        net = counts["sun"] - counts["moon"]
        contested = counts["sun"] > 0 and counts["moon"] > 0
        if contested:
            net = 0
        if net:
            step = self.CAPTURE_RATE * dt * (1.0 + 0.35 * (abs(net) - 1))
            self.capture = max(-1.0, min(1.0, self.capture +
                                         step * (1 if net > 0 else -1)))
        elif not contested and counts["sun"] == 0 and counts["moon"] == 0:
            # slowly decays back to neutral when abandoned
            self.capture *= max(0.0, 1.0 - 0.12 * dt)

        new_owner = "sun" if self.capture >= 1.0 else \
                    "moon" if self.capture <= -1.0 else None
        if new_owner != self.owner:
            self.owner = new_owner
            if new_owner:
                self.announce(f"{new_owner.upper()} controls the Beacon!",
                              "objective")

        if self.owner:
            holders = counts[self.owner]
            self.point_accum += dt * (2.0 + 0.6 * holders)
            while self.point_accum >= 1.0:
                self.point_accum -= 1.0
                self.add_score(self.owner, 1)
                for p in self.room.players.values():
                    if p.team == self.owner and p.alive and p.on_point:
                        p.score += 1

        self._last_contested = contested

    def on_death(self, victim, killer, weapon_id, headshot):
        if killer is not None and killer is not victim and \
                killer.team != victim.team:
            killer.score += 3
            self.add_score(killer.team, 2)

    def hud(self):
        base = super().hud()
        base.update({
            "beacon": self.beacon_island,
            "beaconPos": [round(v, 1) for v in self.beacon_pos()],
            "capture": round(self.capture, 3),
            "owner": self.owner,
            "moveIn": max(0.0, self.beacon_moves_at - time.time()),
            "contested": self._last_contested,
            "radius": self.RADIUS,
        })
        return base


class SkyHaven(WorldDef):
    meta = WorldMeta(
        id="skyhaven",
        name="Sky Haven",
        tagline="Low gravity. High stakes. Don't look down.",
        description=(
            "A shattered archipelago suspended above an endless sky. Gravity "
            "here is barely half of normal, so every jump is a leap and every "
            "launch pad is a decision.\n\n"
            "Sun and Moon fight for a single roaming Beacon that relocates to "
            "a new island every 75 seconds. Stand inside the ring to capture "
            "it, hold it to bank points — and remember there is no floor to "
            "catch you."
        ),
        genre="Fighting",
        mode="King of the Hill",
        max_players=14,
        thumb="skyhaven",
        accent="#7fb3ff",
        sort_order=2,
        tags=["Low Gravity", "Objective", "Team", "Vertical"],
        difficulty="Hard",
        recommended="6-14 players",
    )
    mode_class = SkyHavenMode

    def build(self) -> Level:
        lv = Level(sky="dawn", ambient=0.62, sun=(0.30, 0.78, -0.55),
                   fog="#bcd8f2", fog_near=420, fog_far=1400,
                   gravity_scale=0.46, void_y=-60)
        lv.bounds = [-230, -230, 230, 230]

        for iid, x, y, z, r, h in ISLANDS:
            self._island(lv, iid, x, y, z, r, h)

        # ---- connective tissue: bridges & launch pads ----
        self._bridge(lv, (-168, 40, 0), (0, 58, 0))
        self._bridge(lv, (168, 40, 0), (0, 58, 0))
        self._bridge(lv, (0, 46, -118), (0, 58, 0))
        self._bridge(lv, (0, 46, 118), (0, 58, 0))

        for iid in ("nw", "ne", "sw", "se"):
            _, x, y, z, r, h = ISLAND_BY_ID[iid]
            lv.pickup("gravity", x, y + h / 2 + 4, z, respawn=25)

        # launch pads on each home island aimed at the middle
        for team, sx in (("sun", -168), ("moon", 168)):
            lv.box(sx + (26 if team == "sun" else -26), 41.0, 0, 10, 1.6, 10,
                   "#38d0ff", "neon", glow=0.8, tag="launch")
            lv.add((sx + (26 if team == "sun" else -26), 42.4, 0),
                   (9, 0.4, 9), "#8ff0ff", "neon", glow=1.0, nocollide=True)

        for iid in BEACON_ISLANDS:
            _, x, y, z, r, h = ISLAND_BY_ID[iid]
            lv.box(x, y + h / 2 + 0.8, z, 10, 1.6, 10, "#38d0ff", "neon",
                   glow=0.8, tag="launch")

        # ---- decorative cloud banks ----
        for i in range(30):
            ang = i * 2.399963
            r = 190 + (i * 41) % 240
            x, z = math.cos(ang) * r, math.sin(ang) * r
            y = -30 + (i * 23) % 150
            s = 34 + (i * 13) % 52
            lv.add((x, y, z), (s, s * 0.34, s * 0.85), CLOUD, "smooth",
                   shape="sphere", opacity=0.30, glow=0.5, nocollide=True)

        # ---- spawns ----
        for i in range(7):
            a = i * (math.tau / 7)
            lv.spawn(-168 + math.cos(a) * 20, 42, math.sin(a) * 20, "sun", -90)
            lv.spawn(168 + math.cos(a) * 20, 42, math.sin(a) * 20, "moon", 90)

        # ---- pickups ----
        _, cx, cy, cz, cr, ch = ISLAND_BY_ID["centre"]
        lv.pickup("damage", cx, cy + ch / 2 + 14, cz, respawn=50)
        lv.pickup("health", -168, 42, -26, respawn=16)
        lv.pickup("health", 168, 42, -26, respawn=16)
        lv.pickup("armor", 0, 102, 0, respawn=40)
        lv.pickup("ammo", 0, 46, -118, respawn=14)
        lv.pickup("ammo", 0, 46, 118, respawn=14)
        lv.pickup("speed", -96, 72, -92, respawn=30)
        lv.pickup("speed", 96, 72, 92, respawn=30)
        return lv

    # ------------------------------------------------------------------
    def _island(self, lv: Level, iid: str, x, y, z, r, h):
        team_tint = None
        if iid == "home_sun":
            team_tint = SUN_T
        elif iid == "home_moon":
            team_tint = MOON_T

        # tiered rock underside — reads as a floating chunk of land
        tiers = 5
        for i in range(tiers):
            f = 1.0 - i / tiers
            rr = r * (f ** 0.75)
            lv.add((x, y - h / 2 - i * 3.2, z), (rr * 2, 3.4, rr * 2),
                   STONE if i % 2 else "#7d8892", "rock",
                   shape="cylinder" if i < 2 else "cone")
        lv.add((x, y - h / 2 - tiers * 3.2 - 4, z), (r * 0.5, 12, r * 0.5),
               "#6b757f", "rock", shape="cone", rot=[180, 0, 0])

        # top surface
        lv.add((x, y, z), (r * 2, h, r * 2), STONE_LIGHT, "rock",
               shape="cylinder")
        lv.add((x, y + h / 2 + 0.4, z), (r * 2 - 1.5, 1.2, r * 2 - 1.5),
               MOSS if team_tint is None else team_tint, "grass",
               shape="cylinder")

        # ring wall so you don't trivially slide off
        seg = 26
        for i in range(seg):
            a = i * math.tau / seg
            px, pz = x + math.cos(a) * (r - 1.0), z + math.sin(a) * (r - 1.0)
            lv.box(px, y + h / 2 + 1.6, pz, 3.4, 2.4, 3.4, STONE, "rock")

        if iid == "high":
            for i in range(6):
                a = i * math.tau / 6
                lv.box(x + math.cos(a) * 13, y + h / 2 + 6, z + math.sin(a) * 13,
                       3, 12, 3, GOLD, "metal")
            lv.add((x, y + h / 2 + 14, z), (26, 2.2, 26), "#d8c88a", "rock",
                   shape="cylinder")
        elif iid == "centre":
            # ruined arena with cover
            for i in range(8):
                a = i * math.tau / 8
                lv.box(x + math.cos(a) * 24, y + h / 2 + 5, z + math.sin(a) * 24,
                       5, 10, 5, STONE, "rock")
            lv.box(x, y + h / 2 + 2.5, z, 18, 4, 18, "#c7cfd8", "tile")
            lv.add((x, y + h / 2 + 8, z), (5, 9, 5), "#f2c53d", "neon",
                   shape="cylinder", glow=0.9, nocollide=True)
        elif team_tint:
            colour = team_tint
            lv.room(x, z, 30, 22, 14, colour, "concrete", y=y + h / 2,
                    door="e" if iid == "home_sun" else "w")
            lv.box(x, y + h / 2 + 15, z, 34, 2, 26, "#d8dde3", "metal")
            lv.sign(x, y + h / 2 + 20, z,
                    "SUN SPIRE" if iid == "home_sun" else "MOON SPIRE",
                    color=colour)
        else:
            for i in range(4):
                a = i * math.tau / 4 + 0.5
                lv.box(x + math.cos(a) * 14, y + h / 2 + 4, z + math.sin(a) * 14,
                       6, 8, 6, STONE, "rock")

    def _bridge(self, lv: Level, a, b, *, width=9.0):
        ax, ay, az = a
        bx, by, bz = b
        dx, dy, dz = bx - ax, by - ay, bz - az
        dist = math.hypot(dx, dz)
        steps = max(6, int(dist / 12))
        for i in range(1, steps):
            t_ = i / steps
            # gentle catenary sag
            sag = math.sin(t_ * math.pi) * 5.0
            px = ax + dx * t_
            pz = az + dz * t_
            py = ay + dy * t_ - sag
            lv.box(px, py, pz, width if abs(dx) < abs(dz) else dist / steps + 1.5,
                   1.2,
                   dist / steps + 1.5 if abs(dx) < abs(dz) else width,
                   "#a08054", "plank")
            if i % 2 == 0:
                for s in (-1, 1):
                    ox = s * width / 2 if abs(dx) < abs(dz) else 0
                    oz = 0 if abs(dx) < abs(dz) else s * width / 2
                    lv.box(px + ox, py + 2.6, pz + oz, 0.6, 4.0, 0.6,
                           "#6f5738", "wood")
