"""Game-mode rules for all five worlds.

    python3 -m tests.test_modes
"""
from __future__ import annotations

import math
import random
import sys
import time

from rblxx import config
from rblxx.data import database as db
from rblxx.gameserver.room import Room

db.init(seed=False)

def mkroom(world):
    r = Room(world)
    r.rng = random.Random(20260905)
    return r


def place(p, x, y, z):
    p.state.x, p.state.y, p.state.z = x, y, z
    p.state.vx = p.state.vy = p.state.vz = 0.0
    p.spawn_protect = 0.0

def run(room, seconds, dt=1/30):
    steps = int(seconds / dt)
    for _ in range(steps):
        room.tick(dt)
        room.drain_outbox()

print("=" * 64)
print("CTF — Fort Wars")
r = mkroom("fortwars")
red = r.add_player(1, "RedRunner", {}, None)
blue = r.add_player(2, "BlueGuard", {}, None)
red.team, blue.team = "red", "blue"
m = r.mode
print(f"   flags start: red={m.flags['red']['state']} blue={m.flags['blue']['state']}")
# red walks onto the blue flag
bf = m.flags["blue"]["home"]
place(red, bf[0], bf[1] - 6, bf[2])
place(blue, 0, 30, 0)
r.now = time.time(); m.tick(r.now, 1 / 30); r.drain_outbox()
print(f"   red touched the blue flag -> state={m.flags['blue']['state']} "
      f"carrier={red.carrying_flag}")
assert red.carrying_flag == "blue"
# and carries it home
place(blue, -200, 24, 0)
rf = m.flags["red"]["home"]
place(red, rf[0], rf[1] - 6, rf[2])
r.now = time.time(); m.tick(r.now, 1 / 30); r.drain_outbox()
print(f"   capture -> red score={m.team_score['red']} "
      f"captures={red.captures} blue flag={m.flags['blue']['state']}")
assert m.team_score["red"] == 1
# holding the middle extends the causeway (uncontested)
place(red, 0, 24, 0)
place(blue, -200, 24, 0)
before = m.bridge_extended
run(r, 10)
print(f"   red held the middle 10s -> causeway extended={m.bridge_extended} "
      f"(was {before}) owner={m.bridge_owner}")
assert m.bridge_extended
# dropping the flag on death
place(red, rf[0], rf[1] - 6, rf[2])
r.now = time.time(); m.tick(r.now, 1 / 30)
r.kill(red, blue, "rifle", False)
print(f"   carrier killed -> flag state={m.flags['blue']['state']}")

print("\nKOTH — Sky Haven")
r2 = mkroom("skyhaven")
sun = r2.add_player(3, "SunA", {}, None)
moon = r2.add_player(4, "MoonA", {}, None)
sun.team, moon.team = "sun", "moon"
m2 = r2.mode
bx, by, bz = m2.beacon_pos()
place(sun, bx, by, bz)
place(moon, 0, 400, 0)          # far away
run(r2, 5)
print(f"   sun stood on the beacon 5s -> capture={m2.capture:.2f} "
      f"owner={m2.owner} score={m2.team_score}")
assert m2.capture > 0.9 and m2.owner == "sun"
# contest it
place(moon, bx + 4, by, bz)
cap_before = m2.capture
run(r2, 3)
print(f"   moon contests -> capture held at {m2.capture:.2f} "
      f"(was {cap_before:.2f})")
# beacon relocation
old_island = m2.beacon_island
m2.beacon_moves_at = time.time() - 1
run(r2, 0.2)
print(f"   beacon relocated {old_island} -> {m2.beacon_island}, "
      f"capture reset to {m2.capture:.2f}")
assert m2.beacon_island != old_island

print("\nOUTBREAK — waves, downs and revives")
r3 = mkroom("outbreak")
p1 = r3.add_player(5, "Medic", {}, None)
p2 = r3.add_player(6, "Gunner", {}, None)
m3 = r3.mode
print(f"   start points: {p1.points}  phase={m3.state}")
m3.state_until = time.time() - 1
run(r3, 0.5)
print(f"   wave {m3.wave} began: {m3.enemies_to_spawn + m3.enemies_left} hostiles queued")
assert m3.wave == 1
run(r3, 4)
print(f"   after 4s: {len(r3.enemies)} zombies alive, "
      f"{m3.enemies_left} left in the wave")
assert len(r3.enemies) > 0
# shoot one
e = next(iter(r3.enemies.values()))
before_pts = p2.points
dealt = r3.damage_enemy(e, p2, e.health + 1)
print(f"   killed a walker -> gunner points {before_pts} -> {p2.points}, "
      f"kills={p2.kills}")
assert p2.points > before_pts
# down and revive
r3.kill(p1, None, "zombie", False)
print(f"   medic downed: downed={p1.id in m3.downed} alive={p1.alive} "
      f"hp={p1.health}")
assert p1.id in m3.downed
place(p2, p1.state.x + 2, p1.state.y, p1.state.z)
p2.input_use = True
run(r3, 4.5)
print(f"   gunner held E for 4.5s -> medic revived={p1.id not in m3.downed} "
      f"hp={p1.health:.0f}, reviver got {p2.revives} revive(s)")
assert p1.id not in m3.downed
# buying a door
p1.points = 5000
res = m3.interact(p1, "d_labs")
print(f"   bought the labs door: {res} -> open_rooms={sorted(m3.open_rooms)}")
assert "labs" in m3.open_rooms
res = m3.interact(p1, "wb_rifle")
print(f"   wall-buy: {res}")

print("\nLAVA RISE — rounds and the rising tide")
r4 = mkroom("lavarise")
a = r4.add_player(7, "Climber", {}, None)
b = r4.add_player(8, "Faller", {}, None)
m4 = r4.mode
m4.state_until = time.time() - 1
run(r4, 0.3)
print(f"   round {m4.round_no} started, lava at {m4.lava_y:.1f}, "
      f"alive={len(m4.contenders())}")
assert m4.state == "playing"
# the tide is wall-clock driven, so wind the round start back past the grace
m4.round_started = time.time() - 25.0
run(r4, 3)
print(f"   after the 20s grace, lava is at {m4.lava_y:.1f} "
      f"(rising {m4.rise_rate:.2f}/s)")
assert m4.lava_y > m4.LAVA_START
# drown one player
place(b, 0, m4.lava_y - 6, 0)
run(r4, 4)
print(f"   player under the tide -> hp={b.health:.0f} alive={b.alive} "
      f"spectating={b.spectating}")
# last one standing ends the round
print(f"   round state now: {m4.state}, winner recorded: {m4.last_winner}")

print("\nTDM — Crossroads score limit")
r5 = mkroom("crossroads")
x = r5.add_player(9, "R", {}, None); x.team = "red"
y = r5.add_player(10, "B", {}, None); y.team = "blue"
r5.mode.team_score["red"] = r5.mode.score_limit - 1
r5.mode.add_score("red", 1)
print(f"   reaching the limit ends the round: phase={r5.mode.phase} "
      f"winner={r5.mode.winner}")
assert r5.mode.phase == "intermission" and r5.mode.winner == "red"

print("\nALL MODE CHECKS PASSED")

sys.exit(0)
