"""Player and enemy entities living inside a room."""
from __future__ import annotations

import math
import time
from collections import deque

from .. import config
from .physics import MoveState
from .weapons import WEAPONS, WeaponState, Weapon, DEFAULT_LOADOUT

BTN_JUMP = 1
BTN_SPRINT = 2
BTN_CROUCH = 4
BTN_FIRE = 8
BTN_ADS = 16
BTN_USE = 32

EFFECTS = {
    "speed":   {"duration": 18.0, "color": "#38d0ff", "label": "Speed Coil"},
    "gravity": {"duration": 22.0, "color": "#b58cff", "label": "Gravity Coil"},
    "damage":  {"duration": 20.0, "color": "#ff7a2a", "label": "Damage Boost"},
    "armor":   {"duration": 0.0,  "color": "#8fd8ff", "label": "Armour"},
}


class Player:
    __slots__ = (
        "id", "user_id", "username", "avatar", "team", "state", "health",
        "armor", "alive", "respawn_at", "weapons", "weapon_index", "score",
        "kills", "deaths", "streak", "best_streak", "ping", "last_seq",
        "yaw", "pitch", "effects", "points", "carrying_flag", "spectating",
        "input_jump", "input_sprint", "input_crouch", "input_fire",
        "input_ads", "input_use", "move_x", "move_z", "history", "socket",
        "joined_at", "last_input_at", "last_chat_at", "input_budget",
        "downed_at", "revive_progress", "reviver_name", "revives", "downs",
        "captures", "wins", "on_point", "pending_weapon", "pending_at",
        "damage_log", "last_damage_from", "last_damage_at", "headshots",
        "shots_fired", "shots_hit", "vote", "idle_since", "emote",
        "emote_until", "playtime", "loadout_name", "skin", "muted_until",
        "chat_strikes", "visit_id", "zip_from", "zip_to", "zip_t",
        "last_launch", "spawn_protect",
    )

    def __init__(self, pid: int, user_id: int, username: str, avatar: dict,
                 socket=None):
        self.id = pid
        self.user_id = user_id
        self.username = username
        self.avatar = avatar
        self.socket = socket
        self.team = "neutral"
        self.state = MoveState()
        self.health = float(config.PLAYER_MAX_HEALTH)
        self.armor = 0.0
        self.alive = False
        self.respawn_at = 0.0
        self.weapons: list[WeaponState] = []
        self.weapon_index = 0
        self.score = 0
        self.kills = 0
        self.deaths = 0
        self.streak = 0
        self.best_streak = 0
        self.headshots = 0
        self.shots_fired = 0
        self.shots_hit = 0
        self.ping = 0.0
        self.last_seq = 0
        self.yaw = 0.0
        self.pitch = 0.0
        self.effects: dict[str, float] = {}
        self.points = 0
        self.carrying_flag = None
        self.spectating = False
        self.input_jump = False
        self.input_sprint = False
        self.input_crouch = False
        self.input_fire = False
        self.input_ads = False
        self.input_use = False
        self.move_x = 0.0
        self.move_z = 0.0
        self.history = deque(maxlen=int(config.TICK_RATE * config.LAG_COMP_HISTORY) + 4)
        self.joined_at = time.time()
        self.last_input_at = self.joined_at
        self.last_chat_at = 0.0
        self.input_budget = 0.0
        self.downed_at = 0.0
        self.revive_progress = 0.0
        self.reviver_name = None
        self.revives = 0
        self.downs = 0
        self.captures = 0
        self.wins = 0
        self.on_point = False
        self.pending_weapon = None
        self.pending_at = 0.0
        self.damage_log: dict[int, float] = {}
        self.last_damage_from = None
        self.last_damage_at = 0.0
        self.vote = None
        self.idle_since = 0.0
        self.emote = None
        self.emote_until = 0.0
        self.playtime = 0.0
        self.loadout_name = "assault"
        self.skin = (avatar or {}).get("skin", "default")
        self.muted_until = 0.0
        self.chat_strikes = 0
        self.visit_id = None
        self.zip_from = None
        self.zip_to = None
        self.zip_t = 0.0
        self.last_launch = 0.0
        self.spawn_protect = 0.0

    # -- weapons -----------------------------------------------------------
    def set_loadout(self, ids: list[str]):
        self.weapons = [WeaponState(WEAPONS[i]) for i in ids if i in WEAPONS]
        if not self.weapons:
            self.weapons = [WeaponState(WEAPONS[i]) for i in DEFAULT_LOADOUT]
        self.weapon_index = 0

    @property
    def weapon(self) -> WeaponState | None:
        if not self.weapons:
            return None
        return self.weapons[min(self.weapon_index, len(self.weapons) - 1)]

    def has_weapon(self, wid: str) -> bool:
        return any(w.weapon.id == wid for w in self.weapons)

    # -- effects -----------------------------------------------------------
    def add_effect(self, kind: str, now: float, duration: float | None = None):
        info = EFFECTS.get(kind)
        if not info:
            return
        dur = duration if duration is not None else info["duration"]
        self.effects[kind] = max(self.effects.get(kind, 0.0), now + dur)

    def has_effect(self, kind: str, now: float) -> bool:
        return self.effects.get(kind, 0.0) > now

    def prune_effects(self, now: float):
        for k in [k for k, v in self.effects.items() if v <= now]:
            self.effects.pop(k, None)

    # -- lag compensation --------------------------------------------------
    def record_history(self, now: float):
        self.history.append((now, self.state.x, self.state.y, self.state.z))

    def position_at(self, when: float):
        if not self.history:
            return (self.state.x, self.state.y, self.state.z)
        if when >= self.history[-1][0]:
            return (self.state.x, self.state.y, self.state.z)
        prev = self.history[0]
        for entry in self.history:
            if entry[0] >= when:
                span = entry[0] - prev[0]
                t_ = 0.0 if span <= 0 else (when - prev[0]) / span
                return (prev[1] + (entry[1] - prev[1]) * t_,
                        prev[2] + (entry[2] - prev[2]) * t_,
                        prev[3] + (entry[3] - prev[3]) * t_)
            prev = entry
        return (prev[1], prev[2], prev[3])

    # -- eye / aim ---------------------------------------------------------
    def eye(self):
        return (self.state.x, self.state.y + config.PLAYER_HEIGHT - 0.85,
                self.state.z)

    def look_dir(self):
        cp = math.cos(self.pitch)
        return (-math.sin(self.yaw) * cp, math.sin(self.pitch),
                -math.cos(self.yaw) * cp)

    # -- serialisation -----------------------------------------------------
    def net_state(self) -> dict:
        s = self.state
        d = {
            "i": self.id,
            "p": [round(s.x, 2), round(s.y, 2), round(s.z, 2)],
            "v": [round(s.vx, 1), round(s.vy, 1), round(s.vz, 1)],
            "y": round(self.yaw, 3),
            "t": round(self.pitch, 3),
            "h": round(self.health, 1),
            "a": self.alive,
            "w": self.weapon.weapon.id if self.weapon else None,
            "f": (self.input_fire and self.alive),
            "g": s.on_ground,
            "c": self.input_crouch,
            "sp": self.input_sprint,
        }
        if self.carrying_flag:
            d["fl"] = self.carrying_flag
        if self.emote and self.emote_until > time.time():
            d["em"] = self.emote
        if self.downed_at:
            d["dn"] = round(self.revive_progress, 2)
        if self.zip_to:
            d["zp"] = 1
        if self.spawn_protect > time.time():
            d["sh"] = 1
        return d

    def profile(self) -> dict:
        return {
            "id": self.id,
            "userId": self.user_id,
            "name": self.username,
            "team": self.team,
            "avatar": self.avatar,
            "skin": self.skin,
        }

    def scoreboard_row(self) -> dict:
        return {
            "id": self.id, "userId": self.user_id, "name": self.username,
            "team": self.team, "score": self.score, "kills": self.kills,
            "deaths": self.deaths, "ping": int(self.ping * 1000),
            "streak": self.streak, "points": self.points,
            "captures": self.captures, "revives": self.revives,
            "wins": self.wins, "alive": self.alive,
            "flag": bool(self.carrying_flag),
        }


class Enemy:
    """Server-simulated hostile used by the Outbreak world."""

    __slots__ = ("id", "state", "health", "max_health", "speed", "damage",
                 "boss", "target_id", "attack_at", "path", "path_index",
                 "repath_at", "alive", "spawned_at", "stagger_until",
                 "last_damage_from", "kind", "yaw", "anim")

    _next_id = 10000

    def __init__(self, pos, stats: dict, boss: bool = False):
        Enemy._next_id += 1
        self.id = Enemy._next_id
        self.state = MoveState(pos[0], pos[1], pos[2],
                               radius=1.7 if boss else 1.3,
                               height=6.6 if boss else 4.8)
        self.max_health = stats["health"] * (7.0 if boss else 1.0)
        self.health = self.max_health
        self.speed = stats["speed"] * (0.82 if boss else 1.0)
        self.damage = stats["damage"] * (2.4 if boss else 1.0)
        self.boss = boss
        self.kind = "brute" if boss else "walker"
        self.target_id = None
        self.attack_at = 0.0
        self.path: list = []
        self.path_index = 0
        self.repath_at = 0.0
        self.alive = True
        self.spawned_at = time.time()
        self.stagger_until = 0.0
        self.last_damage_from = None
        self.yaw = 0.0
        self.anim = 0.0

    def net_state(self) -> dict:
        s = self.state
        return {
            "i": self.id,
            "p": [round(s.x, 2), round(s.y, 2), round(s.z, 2)],
            "y": round(self.yaw, 3),
            "h": round(self.health / self.max_health, 3),
            "k": self.kind,
            "a": round(self.anim, 2),
        }
