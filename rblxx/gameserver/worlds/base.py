"""World definition + game-mode framework."""
from __future__ import annotations

import random
import time
import typing as t
from dataclasses import dataclass, field

from .builder import Level

TEAM_COLORS = {
    "red":     "#c8372c",
    "blue":    "#2f7fd6",
    "sun":     "#f0a52a",
    "moon":    "#8a6bd8",
    "green":   "#3f9d47",
    "yellow":  "#e0c22c",
    "survivor": "#3fa9d8",
    "neutral": "#9aa2ab",
}


@dataclass
class WorldMeta:
    id: str
    name: str
    tagline: str
    description: str
    genre: str
    mode: str
    max_players: int = 16
    creator: str = "RBLXX Studios"
    thumb: str = ""                 # css gradient hint for the browser card
    accent: str = "#3aa0ff"
    sort_order: int = 0
    tags: list[str] = field(default_factory=list)
    difficulty: str = "Normal"
    recommended: str = "4-16 players"


class GameMode:
    """Base class for every world's rule-set."""

    #: teams players are assigned to.  ("neutral",) == free-for-all.
    teams: tuple[str, ...] = ("neutral",)
    friendly_fire: bool = False
    respawn_delay: float = 4.0
    score_limit: int = 50
    time_limit: float = 600.0
    allow_respawn: bool = True
    hud_kind: str = "generic"

    def __init__(self, room):
        self.room = room
        self.level: Level = room.level
        self.started_at = time.time()
        self.round_end_at = self.started_at + self.time_limit
        self.phase = "active"          # warmup | active | intermission
        self.team_score: dict[str, int] = {t_: 0 for t_ in self.teams}
        self.rng = random.Random(room.world_id)
        self.winner: str | None = None
        self.announcements: list[dict] = []

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        pass

    def tick(self, now: float, dt: float):
        if self.phase == "active" and self.time_limit and now >= self.round_end_at:
            self.end_round(self.leading_team())

    def on_join(self, player):
        player.team = self.pick_team(player)

    def on_leave(self, player):
        pass

    def on_spawn(self, player):
        pass

    def on_death(self, victim, killer, weapon_id, headshot):
        if killer is not None and killer is not victim:
            if not (self.teams != ("neutral",) and killer.team == victim.team):
                self.add_score(killer.team, 1)

    def modify_damage(self, victim, attacker, amount, weapon) -> float:
        if attacker is None or attacker is victim:
            return amount
        if len(self.teams) > 1 and attacker.team == victim.team \
                and not self.friendly_fire:
            return 0.0
        return amount

    # -- helpers -----------------------------------------------------------
    def pick_team(self, player) -> str:
        if self.teams == ("neutral",):
            return "neutral"
        counts = {t_: 0 for t_ in self.teams}
        for p in self.room.players.values():
            if p is not player and p.team in counts:
                counts[p.team] += 1
        smallest = min(counts.values())
        options = [t_ for t_, c in counts.items() if c == smallest]
        return self.rng.choice(options)

    def pick_spawn(self, player):
        pool = [s for s in self.level.spawns if s["team"] == player.team]
        if not pool:
            pool = [s for s in self.level.spawns if s["team"] == "neutral"]
        if not pool:
            pool = self.level.spawns or [{"p": [0, 6, 0], "yaw": 0}]
        # prefer spawns far from living enemies
        enemies = [p for p in self.room.players.values()
                   if p.alive and p is not player
                   and (self.teams == ("neutral",) or p.team != player.team)]
        if enemies:
            def safety(s):
                px, py, pz = s["p"]
                return min(((px - e.state.x) ** 2 + (pz - e.state.z) ** 2)
                           for e in enemies)
            pool = sorted(pool, key=safety, reverse=True)[:max(1, len(pool) // 2)]
        return self.rng.choice(pool)

    def add_score(self, team: str, amount: int):
        if team in self.team_score:
            self.team_score[team] += amount
            if self.score_limit and self.team_score[team] >= self.score_limit:
                self.end_round(team)

    def leading_team(self) -> str | None:
        if not self.team_score:
            return None
        best = max(self.team_score.values())
        leaders = [t_ for t_, v in self.team_score.items() if v == best]
        return leaders[0] if len(leaders) == 1 else None

    def end_round(self, winner: str | None):
        if self.phase == "intermission":
            return
        self.phase = "intermission"
        self.winner = winner
        self.round_end_at = time.time() + 12.0
        self.room.on_round_end(winner)

    def reset_round(self):
        self.phase = "active"
        self.winner = None
        self.started_at = time.time()
        self.round_end_at = self.started_at + self.time_limit
        for k in self.team_score:
            self.team_score[k] = 0

    def announce(self, text: str, kind: str = "info", ttl: float = 4.0):
        self.room.broadcast_event({"t": "announce", "text": text,
                                   "kind": kind, "ttl": ttl})

    # -- presentation ------------------------------------------------------
    def hud(self) -> dict:
        return {
            "kind": self.hud_kind,
            "phase": self.phase,
            "teams": [{"id": t_, "color": TEAM_COLORS.get(t_, "#9aa2ab"),
                       "score": self.team_score.get(t_, 0)}
                      for t_ in self.teams if t_ != "neutral"],
            "scoreLimit": self.score_limit,
            "timeLeft": max(0.0, self.round_end_at - time.time()),
            "winner": self.winner,
        }


class WorldDef:
    """Ties metadata, geometry and rules together."""

    meta: WorldMeta
    mode_class: type[GameMode] = GameMode

    def build(self) -> Level:                      # pragma: no cover
        raise NotImplementedError

    _cached: Level | None = None

    def level(self) -> Level:
        if self._cached is None:
            self._cached = self.build()
        return self._cached
