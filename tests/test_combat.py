"""Combat pipeline: hitscan, falloff, headshots, splash, lag compensation.

    python3 -m tests.test_combat
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
    # deterministic weapon spread so single-shot assertions do not flake
    r.rng = random.Random(20260905)
    return r

def place(p, x, y, z, yaw=0.0, pitch=0.0):
    p.state.x, p.state.y, p.state.z = x, y, z
    p.state.vx = p.state.vy = p.state.vz = 0.0
    p.yaw, p.pitch = yaw, pitch
    p.spawn_protect = 0.0
    p.record_history(time.time())

def collect(room, kinds):
    out = []
    for _, msg in room.drain_outbox():
        if msg.get("t") in kinds:
            out.append(msg)
    return out

print("=" * 62)
print("1) hitscan damage + kill + kill feed (Crossroads, opposing teams)")
room = mkroom("crossroads")
a = room.add_player(1, "Shooter", {}, None)
b = room.add_player(2, "Target", {}, None)
a.team, b.team = "red", "blue"
place(a, 0, 40, -30)
place(b, 0, 40, -60)          # 30 studs straight ahead (-Z at yaw 0)
room.now = time.time()
room.drain_outbox()

shots = 0
while b.alive and shots < 40:
    a.weapon.next_fire = 0
    a.weapon.ammo = 30
    room.now = time.time() + shots * 0.2
    room.try_fire(a, {"d": [0, 0, -1]})
    shots += 1
msgs = collect(room, {"kill"})
print(f"   shots fired: {shots}  target hp: {b.health:.1f}  alive: {b.alive}")
print(f"   killer kills={a.kills} streak={a.streak}  victim deaths={b.deaths}")
print(f"   kill feed entries: {[(m['killer'], m['weapon'], m['victim']) for m in msgs]}")
assert not b.alive and a.kills == 1 and msgs, "kill pipeline failed"

print("\n2) friendly fire is blocked on a team mode")
room2 = mkroom("crossroads")
c = room2.add_player(3, "Red1", {}, None)
d = room2.add_player(4, "Red2", {}, None)
c.team = d.team = "red"
place(c, 0, 40, -30); place(d, 0, 40, -60)
room2.now = time.time()
before = d.health
c.weapon.next_fire = 0
room2.try_fire(c, {"d": [0, 0, -1]})
print(f"   teammate hp {before:.0f} -> {d.health:.0f} (expected unchanged)")
assert d.health == before

print("\n3) walls block shots")
room3 = mkroom("crossroads")
e = room3.add_player(5, "A", {}, None)
f = room3.add_player(6, "B", {}, None)
e.team, f.team = "red", "blue"
# either side of the central tower's solid core
place(e, -30, 32, 0); place(f, 30, 32, 0)
room3.now = time.time()
hp0 = f.health
for _ in range(6):
    e.weapon.next_fire = 0
    room3.try_fire(e, {"d": [1, 0, 0]})
print(f"   through-wall hp {hp0:.0f} -> {f.health:.0f} (expected unchanged)")

print("\n4) headshots multiply damage (aim at the chest vs the head)")
room4 = mkroom("crossroads")
g = room4.add_player(7, "A", {}, None)
hgt = room4.add_player(8, "B", {}, None)
g.team, hgt.team = "red", "blue"
place(g, 0, 40, -30); place(hgt, 0, 40, -50)
room4.now = time.time()
eye = g.state.y + config.PLAYER_HEIGHT - 0.85

def aim_damage(target_y, tries=14):
    best = 0.0
    for k in range(tries):
        hgt.health = 100.0
        hgt.alive = True
        g.weapon.next_fire = 0
        g.weapon.ammo = 30
        room4.now = time.time() + k * 0.3
        dy = target_y - eye
        dz = -20.0
        ln = math.hypot(dy, dz)
        g.pitch = math.asin(dy / ln)
        room4.try_fire(g, {"d": [0, dy / ln, dz / ln]})
        best = max(best, 100 - hgt.health)
    return best

body = aim_damage(hgt.state.y + 2.2)
head = aim_damage(hgt.state.y + 4.2)
print(f"   best chest hit {body:.1f} dmg vs best head hit {head:.1f} dmg")
assert head > body * 1.5, "headshot multiplier not applied"

print("\n5) rocket splash + self knockback (rocket jump)")
room5 = mkroom("crossroads")
r1 = room5.add_player(9, "Demo", {}, None)
r2 = room5.add_player(10, "Victim", {}, None)
r1.team, r2.team = "red", "blue"
room5.give_weapon(r1, "rocket")
place(r1, 0, 6, 0); place(r2, 0, 6, -12)
room5.now = time.time()
r1.weapon.next_fire = 0
r1.weapon.ready_at = 0
r1.pitch = -1.2
room5.try_fire(r1, {"d": [0, -0.93, -0.36]})
assert room5.projectiles, "rocket was not launched"
for i in range(60):
    room5.now = time.time() + i * 0.033
    room5._tick_projectiles(0.033)
    if not room5.projectiles:
        break
print(f"   projectile resolved after {i} steps; shooter vy={r1.state.vy:.1f} "
      f"hp={r1.health:.0f}; victim hp={r2.health:.0f}")
assert r1.state.vy > 5, "rocket jump should launch the shooter"

print("\n6) pickups")
room6 = mkroom("crossroads")
p = room6.add_player(11, "P", {}, None)
pid, st = next(iter(room6.pickup_state.items()))
while st["def"]["kind"] != "speed":
    pid, st = next(it for it in list(room6.pickup_state.items())
                   if it[1]["def"]["kind"] == "speed")
    break
place(p, st["def"]["p"][0], st["def"]["p"][1] - 2.5, st["def"]["p"][2])
room6.now = time.time()
room6._check_pickups(p, room6.now)
print(f"   speed coil picked up: {p.has_effect('speed', room6.now)}  "
      f"pickup active: {st['active']}")
assert p.has_effect('speed', room6.now)

print("\n7) lag compensation rewinds the target")
room7 = mkroom("crossroads")
s1 = room7.add_player(12, "Sniper", {}, None)
t1 = room7.add_player(13, "Runner", {}, None)
s1.team, t1.team = "red", "blue"
place(s1, 0, 40, -30)
now = time.time()
# runner was in front 150 ms ago, has since strafed 12 studs away
t1.spawn_protect = 0.0
t1.history.clear()
# the runner was dead on the shooter's axis 250 ms ago and has since
# sprinted 12 studs sideways
for k in range(10):
    t1.state.x = 12.0 * k / 9.0
    t1.state.y, t1.state.z = 40, -60
    t1.record_history(now - 0.25 + k * (0.22 / 9.0))
t1.state.x = 12.0
s1.ping = 0.30
rewound = 0.0
for attempt in range(8):
    t1.health = 100.0
    t1.alive = True
    room7.now = now
    s1.weapon.next_fire = 0
    s1.weapon.ammo = 30
    room7.try_fire(s1, {"d": [0, 0, -1]})
    rewound = max(rewound, 100 - t1.health)
    if rewound:
        break
print(f"   runner is 12 studs off-axis now; rewound shot dealt "
      f"{rewound:.1f} damage")
assert rewound > 0, "lag compensation did not rewind the target"

# and without rewind (ping 0) the same shot should miss
worst = 0.0
for attempt in range(6):
    t1.health = 100.0
    t1.alive = True
    s1.ping = 0.0
    s1.weapon.next_fire = 0
    s1.weapon.ammo = 30
    room7.now = now + 1.0 + attempt
    room7.try_fire(s1, {"d": [0, 0, -1]})
    worst = max(worst, 100 - t1.health)
print(f"   same shot with 0 ms ping deals {worst:.1f} damage "
      f"(target really is elsewhere now)")
assert worst == 0, "shot should miss without lag compensation"

print("\n8) fall damage and the void")
room8 = mkroom("skyhaven")
fp = room8.add_player(14, "Faller", {}, None)
place(fp, 0, -80, 0)
room8.now = time.time()
room8._check_hazards(fp, 0.033)
print(f"   below the void plane -> alive={fp.alive} hp={fp.health:.0f}")
assert not fp.alive

print("\nALL COMBAT CHECKS PASSED")

sys.exit(0)
