"""Central configuration for the RBLXX platform.

Everything tunable lives here so the supervisor, the web edge and the
game nodes all agree on ports, paths and protocol constants.
"""
from __future__ import annotations

import os
import pathlib

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB_ROOT = ROOT / "web"
DATA_DIR = pathlib.Path(os.environ.get("RBLXX_DATA_DIR", ROOT / "var"))
DB_PATH = DATA_DIR / "rblxx.sqlite3"
SECRET_PATH = DATA_DIR / "secret.key"
LOG_DIR = DATA_DIR / "logs"

# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------
#: The one public port exposed to the local network.  Everything (UI, API,
#: websockets for every world) is multiplexed through it.
WEB_HOST = os.environ.get("RBLXX_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("RBLXX_PORT", "8972"))

#: Game nodes are separate OS processes bound to loopback only.  The edge
#: server relays browser websockets to them, so they never need to be
#: reachable from the network directly.
NODE_HOST = "127.0.0.1"
NODE_PORT_BASE = int(os.environ.get("RBLXX_NODE_PORT_BASE", "8990"))

#: Seconds a game node may go without heart-beating before the supervisor
#: considers it dead and restarts it.
NODE_HEARTBEAT_INTERVAL = 2.0
NODE_HEARTBEAT_TIMEOUT = 12.0
NODE_RESTART_BACKOFF = (1.0, 2.0, 4.0, 8.0, 15.0)

# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------
TICK_RATE = 30                      # authoritative simulation steps / second
TICK_DT = 1.0 / TICK_RATE
SNAPSHOT_RATE = 20                  # state broadcasts / second
SNAPSHOT_EVERY = max(1, round(TICK_RATE / SNAPSHOT_RATE))
MAX_PLAYERS_PER_ROOM = 16
LAG_COMP_HISTORY = 1.0              # seconds of position history kept
MAX_CLIENT_INPUT_RATE = 90          # inputs/sec before we start dropping

# Studs are the classic unit.  1 stud == 1 world unit here.
GRAVITY = 68.0                      # studs / s^2  (snappy, arcade-y)
PLAYER_WALK_SPEED = 16.0
PLAYER_SPRINT_SPEED = 24.0
PLAYER_JUMP_POWER = 32.0
PLAYER_HEIGHT = 5.0
PLAYER_RADIUS = 1.4
PLAYER_MAX_HEALTH = 100
RESPAWN_DELAY = 4.0

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------
SESSION_TTL = 60 * 60 * 24 * 30     # 30 days
TICKET_TTL = 45                     # game-join ticket lifetime, seconds
PASSWORD_ITERATIONS = 200_000
MIN_PASSWORD_LEN = 6
MAX_PASSWORD_LEN = 200
USERNAME_RE = r"^[A-Za-z0-9_]{3,20}$"

# Simple in-memory rate limits: (max_events, window_seconds)
RATE_LIMITS = {
    "login": (12, 300),
    "signup": (6, 3600),
    "post": (12, 300),
    "comment": (30, 300),
    "message": (40, 300),
    "vote": (120, 300),
    "purchase": (60, 300),
    "default": (600, 60),
}

# --------------------------------------------------------------------------
# Economy
# --------------------------------------------------------------------------
STARTING_COINS = 1500
DAILY_STIPEND = 75
CURRENCY_NAME = "Bux"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
