"""SQLite access layer.

WAL mode + one connection per thread means the web edge and every game node
subprocess can talk to the same file safely.  Queries are small and indexed,
so they run inline on the event loop; anything expensive goes through
``run_in_thread``.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sqlite3
import threading
import time
import typing as t

from .. import config

_local = threading.local()
_init_lock = threading.Lock()
_initialised = False

SCHEMA_PATH = pathlib.Path(__file__).with_name("schema.sql")


def _configure(conn: sqlite3.Connection):
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    conn.execute("PRAGMA cache_size=-16000")
    conn.execute("PRAGMA temp_store=MEMORY")


def connection() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.DB_PATH), timeout=10.0,
                               isolation_level=None,
                               check_same_thread=False)
        _configure(conn)
        _local.conn = conn
    return conn


def init(seed: bool = True):
    """Create the schema (idempotent) and optionally seed reference data."""
    global _initialised
    with _init_lock:
        conn = connection()
        conn.executescript(SCHEMA_PATH.read_text())
        _initialised = True
    if seed:
        from . import seed as seed_module
        seed_module.ensure_seed_data()


# --------------------------------------------------------------------------
# Query helpers
# --------------------------------------------------------------------------
def query(sql: str, params: t.Sequence = ()) -> list[sqlite3.Row]:
    return connection().execute(sql, params).fetchall()


def query_one(sql: str, params: t.Sequence = ()) -> sqlite3.Row | None:
    return connection().execute(sql, params).fetchone()


def scalar(sql: str, params: t.Sequence = (), default=None):
    row = query_one(sql, params)
    if row is None:
        return default
    return row[0]


def execute(sql: str, params: t.Sequence = ()) -> sqlite3.Cursor:
    return connection().execute(sql, params)


def executemany(sql: str, seq) -> sqlite3.Cursor:
    return connection().executemany(sql, seq)


def insert(sql: str, params: t.Sequence = ()) -> int:
    cur = connection().execute(sql, params)
    return int(cur.lastrowid or 0)


class transaction:
    """`with transaction():` — IMMEDIATE so concurrent writers queue cleanly."""

    def __enter__(self):
        self.conn = connection()
        for attempt in range(6):
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                return self.conn
            except sqlite3.OperationalError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.execute("COMMIT")
        else:
            try:
                self.conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        return False


async def run_in_thread(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]


def json_field(raw, default=None):
    if not raw:
        return default if default is not None else {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default if default is not None else {}


def get_meta(key: str, default: str | None = None) -> str | None:
    return scalar("SELECT value FROM meta WHERE key=?", (key,), default)


def set_meta(key: str, value: str):
    execute("INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
