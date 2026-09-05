"""World registry."""
from __future__ import annotations

from .base import GameMode, WorldDef, WorldMeta, TEAM_COLORS
from .builder import Level
from .crossroads import Crossroads
from .skyhaven import SkyHaven
from .outbreak import Outbreak
from .lavarise import LavaRise
from .fortwars import FortWars

WORLD_CLASSES = [Crossroads, SkyHaven, Outbreak, LavaRise, FortWars]

_INSTANCES: dict[str, WorldDef] = {}


def all_worlds() -> list[WorldDef]:
    if not _INSTANCES:
        for cls in WORLD_CLASSES:
            _INSTANCES[cls.meta.id] = cls()
    return sorted(_INSTANCES.values(), key=lambda w: w.meta.sort_order)


def get_world(world_id: str) -> WorldDef | None:
    all_worlds()
    return _INSTANCES.get(world_id)


def world_ids() -> list[str]:
    return [w.meta.id for w in all_worlds()]


__all__ = ["GameMode", "WorldDef", "WorldMeta", "Level", "TEAM_COLORS",
           "all_worlds", "get_world", "world_ids", "WORLD_CLASSES"]
