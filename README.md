# RBLXX

A self-hosted, classic-flavoured game platform: a full social website **and** a
first/third-person blocky shooter, in one Python project, on one port.

```
python3 main.py          #  →  http://<your-lan-ip>:8972/
```

No packages to install. No build step. No CDN. It runs offline.

---

## What it is

RBLXX is two halves that share one identity, one item database and one port.

**The UI** is the website: sign-up, profiles with a live 3D character, an
avatar editor, an inventory, a catalog, friends, following, posts, private
messages, notifications, leaderboards and a world browser.

**The Game View** is what loads when you press **Load** on a world: an
authoritative multiplayer shooter with client-side prediction, lag-compensated
hitscan, a rebindable control scheme, TF2-style kill feed, name plates and
in-game chat.

Five worlds ship with it, each with genuinely different rules:

| World | Mode | The idea |
|---|---|---|
| **Crossroads** | Team Deathmatch | The original four-corner baseplate. Red vs Blue, a contested central tower, a tunnel under the ruins, coils and a damage boost. First to 60. |
| **Sky Haven** | King of the Hill | Floating islands at 46 % gravity. A Beacon relocates every 75 s; stand in the ring to take it, hold it to bank points. There is no floor. |
| **Outbreak Facility** | Co-op Survival | Two to eight survivors against escalating waves of AI. Points buy wall weapons, blast doors and a Mystery Box. Go down and a teammate has 26 s to revive you. |
| **Lava Rise** | Battle Royale | A volcanic spire. Twenty seconds of grace, then the lava climbs and never stops. Orange platforms crumble under you. Friendly fire is on. |
| **Fort Wars** | Capture the Flag | Two hill forts across a real canyon. Three routes over: the riverbed, the watchtower ziplines, or the causeway that only extends while your team holds the middle. |

---

## Running it

```bash
python3 main.py                 # everything, on 0.0.0.0:8972
python3 main.py --port 9000     # a different port
python3 main.py --no-nodes      # website only, no game servers
python3 main.py --reset-db      # wipe and re-seed the database first
```

Requires **Python 3.10+** and a browser with WebGL. Nothing else — see
[`requirements.txt`](requirements.txt).

The console prints the LAN URLs to hand to other machines. Everyone on the
network uses the same single port; the edge server relays game traffic to the
right node internally.

Eight demo accounts are seeded on first run so the site is never empty —
`Builderman` / `brickmaster` is a good one to sign in as.

---

## How it is put together

```
main.py                      supervisor: web edge + one game node per world
rblxx/
  config.py                  ports, tick rates, physics constants, limits
  netcore/
    http_server.py           asyncio HTTP/1.1: keep-alive, range, gzip, routing
    websocket.py             RFC 6455 server + client + a raw relay pump
  security/
    crypto.py                PBKDF2 passwords, HMAC session & join tickets
    sanitize.py              validation, chat filtering, spam heuristics
    ratelimit.py             sliding-window limits per action
  data/
    schema.sql               SQLite schema (WAL, shared across processes)
    database.py              per-thread connections, transactions
    catalog_seed.py          the item database — 64 wearables
    seed.py                  idempotent seeding, demo community
  models/                    users, avatar, catalog, inventory, economy, worlds
  social/                    friends · follows · blocks · posts · messages
                             · notifications · badges  (one file each)
  api/                       auth · profiles · social · worlds JSON endpoints
  app.py                     the web edge: middleware, routes, websocket relay
  gameserver/
    supervisor.py            spawns, health-checks and restarts the nodes
    node.py                  one OS process per world: simulation + sockets
    room.py                  authoritative room: inputs, damage, snapshots
    physics.py               AABB movement, step-up, raycasts, grid broadphase
    weapons.py               eight weapons, falloff, spread, projectiles
    ai.py                    navmesh A* + steering for the Outbreak enemies
    entity.py                players and enemies, lag-compensation history
    worlds/                  builder DSL + the five worlds and their rules
web/
  index.html  play.html      the two entry documents
  css/                       design system, site chrome, HUD
  js/engine/                 WebGL renderer, meshes, procedural textures, avatar
  js/game/                   prediction physics, netcode, HUD, chat, menu, FX
  js/ui/                     router, store, API client, iso thumbnails, pages
tests/                       offline suites — physics, combat, modes, API
```

### Process model

The main process serves the site and supervises **one subprocess per world**,
so five simulations run truly in parallel across cores while the network only
ever sees port 8972.

```
browser ──HTTP/WS──> edge (:8972) ──relay──> node crossroads (:8990)
                          │                  node skyhaven   (:8991)
                          │                  node outbreak   (:8992)
                          │                  node lavarise   (:8993)
                          └── SQLite (WAL) ── node fortwars   (:8994)
```

Joining is ticketed: the edge authenticates the session cookie and mints a
45-second HMAC-signed ticket carrying the player's identity **and their avatar
bundle**, which the node verifies on the socket handshake. Nodes are bound to
loopback and never reachable from the network.

The relay is a pure byte pump. Browser→edge frames are already client-masked,
which is exactly what the node expects from its own client, and node→edge
frames are unmasked, which is what the browser expects — so the edge forwards
frames verbatim and never parses a game packet.

Nodes are health-polled every two seconds and restarted with backoff if they
die or wedge.

### Netcode

* **30 Hz** authoritative simulation, **20 Hz** snapshots.
* The client predicts its own movement with a physics module that is a literal
  port of the server's, then reconciles against the server's `me` block by
  snapping and replaying any unacknowledged inputs.
* Remote players are rendered 100 ms in the past and interpolated.
* Hitscan is **lag-compensated**: the server rewinds every target to where the
  shooter saw it (`ping/2 + interpolation`) before tracing. The test suite
  proves a 300 ms-ping shot connects where a 0 ms one misses.
* Aim direction is validated against the reported view before it is trusted;
  fire rate, ammo, reload and cooldowns are all server-side.

### Rendering

There is no third-party 3D library. `web/js/engine/` is a small instanced
WebGL2 renderer (with a WebGL1 + `ANGLE_instanced_arrays` fallback) that draws
the whole world in roughly twenty draw calls by batching per shape and texture.
Every surface — studs, brick, grass, lava, circuitry — plus every face, clothing
pattern, sign and sky is painted procedurally onto a canvas at load time, so
there are no image assets to ship or fetch.

Small thumbnails (friend tiles, catalog icons, post avatars) use a separate 2D
isometric painter, which keeps WebGL contexts free for the two big previews.

---

## The website

* **Profiles** — a real 3D character on the upper left that you can drag,
  zoom and pose, next to friends, badges, statistics, active places and posts.
* **Avatar Editor** — recolour head, torso, both arms and both legs
  independently from a preset palette or any custom colour, equip items (two
  hats stack, the classic way), adjust height and save named outfits.
* **Catalog & Inventory** — 64 items across hats, faces, shirts, pants, back
  accessories and weapon skins, with rarities, limited stock and serial
  numbers. Everything is one table, so adding more is a matter of appending to
  `rblxx/data/catalog_seed.py`.
* **Social** — friends with requests, one-way following, blocking, posts with
  likes and comments, private messages, notifications and badges. Each feature
  lives in its own module under `rblxx/social/`.
* **Economy** — Bux, a daily stipend and a full transaction ledger.

## The Game View

* Starts in first person; **P** switches to third person.
* **Y** opens chat, **U** team chat. Every binding is suppressed while the
  chat box has focus, so typing "was down" does not walk you off a ledge.
  Double-clicking a name in chat opens that profile in a new tab.
* Chat output sits at the lower-middle-left; the TF2-style kill feed sits at
  the top right with team-coloured names, weapon glyphs and headshot flags.
* Name plates scale with distance and show health, downed state and the flag
  carrier.
* **Esc** opens a pause menu with Resume, My Profile, Quit to Profile, a
  settings tab (sensitivity, FOV, HUD scale, crosshair, quality, toggles) and
  a Controls tab where all 21 bindings can be rebound.
* **Tab** holds the scoreboard. **V** opens the next-world vote.

### Default controls

| | | | |
|---|---|---|---|
| Move | `W A S D` | Chat | `Y` |
| Jump | `Space` | Team chat | `U` |
| Sprint | `L Shift` | Scoreboard | `Tab` (hold) |
| Crouch | `L Ctrl` | First / third person | `P` |
| Fire | Left mouse | Interact / revive | `E` |
| Aim | Right mouse | Weapons | `1`–`4`, wheel |
| Reload | `R` | Vote panel | `V` |

---

## Tests

```bash
python3 -m tests.run_all
```

* `tests/test_physics.py` — every spawn in every world settles on solid
  ground, jumps clear a ledge, no pickup floats out of reach.
* `tests/test_combat.py` — damage, kills and the feed, friendly fire, walls
  blocking shots, headshot multipliers, rocket splash and rocket jumping,
  pickups, lag compensation, fall and void damage.
* `tests/test_modes.py` — CTF pickup/capture/drop and the causeway, KOTH
  capture/contest/relocation, Outbreak waves, downs, revives, doors and
  wall-buys, the Lava Rise tide and round flow, the TDM score limit.
* `tests/test_api.py` — boots a real server on a spare port and exercises 33
  HTTP and WebSocket behaviours end to end, including CSRF enforcement,
  purchase integrity, forged join tickets and snapshot rate.

---

## Notes

* All data lives in `var/` (SQLite + logs + the server secret). Delete it, or
  pass `--reset-db`, to start over.
* Passwords are PBKDF2-HMAC-SHA256 with 200 000 iterations and a per-user
  salt. Sessions are random tokens stored hashed; state-changing API calls
  require a double-submit CSRF token; per-action rate limits cover login,
  signup, posting, messaging and purchases.
* This is designed for a trusted local network. It speaks plain HTTP — put it
  behind a reverse proxy with TLS if you expose it further.
