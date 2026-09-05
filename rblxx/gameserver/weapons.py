"""Weapon definitions, firing rules and projectile simulation."""
from __future__ import annotations

import math
import random
import typing as t
from dataclasses import dataclass, field, asdict


@dataclass
class Weapon:
    id: str
    name: str
    slot: int                       # 1..5 quick-select
    damage: float
    rpm: float                      # rounds per minute
    mag: int
    reserve: int
    reload_time: float
    spread: float = 1.2             # degrees of cone at hip
    ads_spread: float = 0.25
    pellets: int = 1
    range: float = 900.0
    falloff_start: float = 180.0
    falloff_end: float = 520.0
    falloff_min: float = 0.45
    headshot_mult: float = 2.0
    auto: bool = True
    projectile_speed: float = 0.0   # 0 == hitscan
    splash_radius: float = 0.0
    splash_damage: float = 0.0
    self_damage_scale: float = 0.35
    knockback: float = 0.0
    self_knockback: float = 0.0
    recoil: float = 0.9
    zoom: float = 1.0
    move_scale: float = 1.0
    switch_time: float = 0.35
    bob: float = 1.0
    model: str = "rifle"
    tracer: str = "#ffe27a"
    sound: str = "shot"
    infinite_reserve: bool = False
    gravity: float = 0.0            # for lobbed projectiles
    bounces: int = 0

    @property
    def shot_interval(self) -> float:
        return 60.0 / max(1.0, self.rpm)

    def to_client(self) -> dict:
        d = asdict(self)
        d["shotInterval"] = self.shot_interval
        return d


WEAPONS: dict[str, Weapon] = {}


def _reg(w: Weapon) -> Weapon:
    WEAPONS[w.id] = w
    return w


_reg(Weapon(
    id="blaster", name="Blaster", slot=2, damage=24, rpm=340, mag=16,
    reserve=96, reload_time=1.35, spread=1.4, ads_spread=0.35, auto=False,
    recoil=0.85, zoom=1.18, model="pistol", tracer="#ffd35c",
    falloff_start=140, falloff_end=420,
))

_reg(Weapon(
    id="rifle", name="Ranger Rifle", slot=1, damage=17.5, rpm=630, mag=30,
    reserve=180, reload_time=1.9, spread=1.9, ads_spread=0.45, auto=True,
    recoil=1.05, zoom=1.35, model="rifle", tracer="#ffe27a",
    falloff_start=200, falloff_end=560, move_scale=0.98,
))

_reg(Weapon(
    id="scatter", name="Scattergun", slot=3, damage=10.5, rpm=76, mag=6,
    reserve=42, reload_time=2.6, spread=5.4, ads_spread=3.6, pellets=9,
    auto=False, recoil=2.4, zoom=1.1, model="shotgun", tracer="#ffbf6a",
    falloff_start=32, falloff_end=140, falloff_min=0.18, headshot_mult=1.45,
    knockback=9.0, move_scale=0.96,
))

_reg(Weapon(
    id="railer", name="Rail Sniper", slot=4, damage=92, rpm=44, mag=5,
    reserve=30, reload_time=2.9, spread=4.2, ads_spread=0.02, auto=False,
    recoil=3.4, zoom=4.2, model="sniper", tracer="#8fe3ff",
    falloff_start=900, falloff_end=1200, falloff_min=0.9, headshot_mult=2.4,
    move_scale=0.9, switch_time=0.55,
))

_reg(Weapon(
    id="rocket", name="Rocket Launcher", slot=5, damage=0, rpm=52, mag=1,
    reserve=14, reload_time=2.3, spread=0.4, ads_spread=0.2, auto=False,
    projectile_speed=140.0, splash_radius=22.0, splash_damage=96.0,
    self_damage_scale=0.42, knockback=42.0, self_knockback=54.0, recoil=3.0,
    zoom=1.1, model="launcher", tracer="#ff8a4c", move_scale=0.92,
    switch_time=0.6,
))

_reg(Weapon(
    id="superball", name="Superball", slot=6, damage=42, rpm=120, mag=1,
    reserve=0, reload_time=0.0, spread=0.0, projectile_speed=115.0,
    gravity=44.0, bounces=3, auto=False, recoil=0.4, model="ball",
    tracer="#ff4f4f", infinite_reserve=True, knockback=14.0,
    switch_time=0.3,
))

_reg(Weapon(
    id="zapper", name="Arc Zapper", slot=7, damage=13, rpm=780, mag=45,
    reserve=225, reload_time=2.1, spread=2.6, ads_spread=1.1, auto=True,
    recoil=0.7, model="zapper", tracer="#7ce8ff", falloff_start=80,
    falloff_end=240, falloff_min=0.3,
))

_reg(Weapon(
    id="mender", name="Field Mender", slot=8, damage=-16, rpm=180, mag=60,
    reserve=0, reload_time=2.4, spread=0.6, auto=True, recoil=0.0,
    model="mender", tracer="#6bffa5", range=110, infinite_reserve=True,
    headshot_mult=1.0,
))

DEFAULT_LOADOUT = ["rifle", "blaster", "scatter", "superball"]

LOADOUTS = {
    "assault": ["rifle", "blaster", "scatter", "superball"],
    "demolition": ["rocket", "blaster", "scatter", "superball"],
    "marksman": ["railer", "blaster", "rifle", "superball"],
    "support": ["zapper", "mender", "blaster", "superball"],
}


# --------------------------------------------------------------------------
# Runtime state carried per player
# --------------------------------------------------------------------------
class WeaponState:
    __slots__ = ("weapon", "ammo", "reserve", "next_fire", "reload_end",
                 "ready_at")

    def __init__(self, weapon: Weapon):
        self.weapon = weapon
        self.ammo = weapon.mag
        self.reserve = weapon.reserve
        self.next_fire = 0.0
        self.reload_end = 0.0
        self.ready_at = 0.0

    def reset(self):
        self.ammo = self.weapon.mag
        self.reserve = self.weapon.reserve
        self.reload_end = 0.0

    def to_client(self) -> dict:
        return {"id": self.weapon.id, "ammo": self.ammo,
                "reserve": -1 if self.weapon.infinite_reserve else self.reserve,
                "reloadEnd": self.reload_end}


def falloff_scale(weapon: Weapon, distance: float) -> float:
    if distance <= weapon.falloff_start:
        return 1.0
    if distance >= weapon.falloff_end:
        return weapon.falloff_min
    span = max(1e-3, weapon.falloff_end - weapon.falloff_start)
    t_ = (distance - weapon.falloff_start) / span
    return 1.0 + (weapon.falloff_min - 1.0) * t_


def spread_direction(direction, degrees: float, rng: random.Random):
    """Rotate a unit vector inside a cone of `degrees` half-angle."""
    if degrees <= 0.0001:
        return direction
    dx, dy, dz = direction
    # build an orthonormal basis around the direction
    up = (0.0, 1.0, 0.0) if abs(dy) < 0.95 else (1.0, 0.0, 0.0)
    rx = up[1] * dz - up[2] * dy
    ry = up[2] * dx - up[0] * dz
    rz = up[0] * dy - up[1] * dx
    rl = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
    rx, ry, rz = rx / rl, ry / rl, rz / rl
    ux = dy * rz - dz * ry
    uy = dz * rx - dx * rz
    uz = dx * ry - dy * rx
    ang = math.radians(degrees) * math.sqrt(rng.random())
    theta = rng.random() * math.tau
    sa, ca = math.sin(ang), math.cos(ang)
    ox = ca * dx + sa * (math.cos(theta) * rx + math.sin(theta) * ux)
    oy = ca * dy + sa * (math.cos(theta) * ry + math.sin(theta) * uy)
    oz = ca * dz + sa * (math.cos(theta) * rz + math.sin(theta) * uz)
    ln = math.sqrt(ox * ox + oy * oy + oz * oz) or 1.0
    return (ox / ln, oy / ln, oz / ln)


class Projectile:
    __slots__ = ("id", "owner_id", "team", "weapon", "x", "y", "z",
                 "vx", "vy", "vz", "life", "bounces_left", "spawn_time")

    _next_id = 1

    def __init__(self, owner_id, team, weapon: Weapon, pos, direction,
                 now: float):
        Projectile._next_id += 1
        self.id = Projectile._next_id
        self.owner_id = owner_id
        self.team = team
        self.weapon = weapon
        self.x, self.y, self.z = pos
        speed = weapon.projectile_speed
        self.vx = direction[0] * speed
        self.vy = direction[1] * speed
        self.vz = direction[2] * speed
        self.life = 6.0
        self.bounces_left = weapon.bounces
        self.spawn_time = now

    def to_client(self) -> dict:
        return {"id": self.id, "w": self.weapon.id,
                "p": [round(self.x, 2), round(self.y, 2), round(self.z, 2)],
                "v": [round(self.vx, 1), round(self.vy, 1), round(self.vz, 1)],
                "o": self.owner_id}
