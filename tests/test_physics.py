"""Movement, collision and level-sanity checks for every world.

    python3 -m tests.test_physics
"""
from __future__ import annotations

import math
import sys

from rblxx import config
from rblxx.gameserver.physics import CollisionWorld, MoveState, move_character
from rblxx.gameserver.worlds import all_worlds


def settle(state, world, gravity, ticks=120):
    for _ in range(ticks):
        move_character(state, world, (0, 0), config.TICK_DT, want_jump=False,
                       speed=0.0, jump_power=0.0, gravity=gravity)
    return state


def run() -> int:
    failures = 0
    for wd in all_worlds():
        lv = wd.level()
        cw = CollisionWorld(lv.colliders(), void_y=lv.void_y,
                            gravity_scale=lv.gravity_scale)
        gravity = config.GRAVITY * lv.gravity_scale
        spawns = [s for s in lv.spawns if s.get("team") != "enemy"]

        bad = []
        for spot in spawns:
            st = MoveState(spot["p"][0], spot["p"][1] + 0.4, spot["p"][2])
            settle(st, cw, gravity)
            if not st.on_ground or st.y < lv.void_y + 5:
                bad.append((spot["p"], round(st.y, 2), st.on_ground))

        # enemy spawns matter too — the AI must not start inside geometry
        for spot in [s for s in lv.spawns if s.get("team") == "enemy"]:
            st = MoveState(spot["p"][0], spot["p"][1] + 0.4, spot["p"][2],
                           radius=1.3, height=4.8)
            settle(st, cw, gravity)
            if not st.on_ground:
                bad.append((spot["p"], round(st.y, 2), "enemy"))

        # a jump from a settled spawn must clear a normal ledge
        st = MoveState(spawns[0]["p"][0], spawns[0]["p"][1] + 0.4,
                       spawns[0]["p"][2])
        settle(st, cw, gravity, 40)
        base = st.y
        peak = base
        for i in range(80):
            move_character(st, cw, (0, 0), config.TICK_DT, want_jump=(i == 0),
                           speed=0.0, jump_power=config.PLAYER_JUMP_POWER,
                           gravity=gravity)
            peak = max(peak, st.y)
        jump = peak - base

        # every pickup should be reachable (something solid underneath)
        floating = 0
        for pk in lv.pickups:
            hit = cw.raycast((pk["p"][0], pk["p"][1], pk["p"][2]), (0, -1, 0), 90)
            if hit is None:
                floating += 1

        ok = not bad and jump > 3 and floating == 0
        failures += 0 if ok else 1
        print(f"  {wd.meta.id:11s} parts={len(lv.parts):4d} "
              f"spawns={len(spawns) - len(bad)}/{len(spawns)} "
              f"jump={jump:5.2f} unreachable_pickups={floating} "
              f"{'ok' if ok else 'FAIL'}")
        for entry in bad[:4]:
            print(f"      bad spawn {entry}")
    return failures


if __name__ == "__main__":
    print("physics & level sanity")
    sys.exit(1 if run() else 0)
