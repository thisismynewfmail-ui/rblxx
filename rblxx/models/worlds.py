"""World catalogue rows, votes and favourites."""
from __future__ import annotations

import time

from ..data import database as db
from ..gameserver.worlds import all_worlds, get_world


def sync_worlds():
    """Ensure every code-defined world has a database row."""
    now = time.time()
    for world in all_worlds():
        m = world.meta
        db.execute(
            "INSERT INTO worlds(id,name,tagline,description,genre,mode,"
            "max_players,creator,sort_order,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
            "tagline=excluded.tagline, description=excluded.description, "
            "genre=excluded.genre, mode=excluded.mode, "
            "max_players=excluded.max_players, "
            "sort_order=excluded.sort_order",
            (m.id, m.name, m.tagline, m.description, m.genre, m.mode,
             m.max_players, m.creator, m.sort_order, now))


def _decorate(row, live: dict | None = None, user_id: int | None = None):
    d = dict(row)
    world = get_world(d["id"])
    meta = world.meta if world else None
    total = d["likes"] + d["dislikes"]
    d["ratio"] = round(d["likes"] / total * 100) if total else None
    d["thumb"] = meta.thumb if meta else d["id"]
    d["accent"] = meta.accent if meta else "#3aa0ff"
    d["tags"] = meta.tags if meta else []
    d["difficulty"] = meta.difficulty if meta else "Normal"
    d["recommended"] = meta.recommended if meta else ""
    d["playing"] = (live or {}).get(d["id"], 0)
    if user_id:
        vote = db.query_one(
            "SELECT value FROM world_votes WHERE world_id=? AND user_id=?",
            (d["id"], user_id))
        d["myVote"] = vote["value"] if vote else 0
        d["favorited"] = bool(db.query_one(
            "SELECT 1 FROM favorites WHERE user_id=? AND world_id=?",
            (user_id, d["id"])))
    return d


def list_worlds(live: dict | None = None, user_id: int | None = None,
                *, sort: str = "featured", genre: str | None = None,
                search: str = "") -> list[dict]:
    rows = db.query("SELECT * FROM worlds ORDER BY sort_order")
    out = [_decorate(r, live, user_id) for r in rows]
    if genre and genre != "all":
        out = [w for w in out if w["genre"] == genre]
    term = (search or "").strip().lower()
    if term:
        out = [w for w in out if term in w["name"].lower()
               or term in w["tagline"].lower()
               or any(term in t.lower() for t in w["tags"])]
    keys = {
        "featured": lambda w: w["sort_order"],
        "popular": lambda w: (-w["playing"], -w["visits"]),
        "visits": lambda w: -w["visits"],
        "rating": lambda w: -(w["ratio"] or 0),
        "name": lambda w: w["name"].lower(),
    }
    return sorted(out, key=keys.get(sort, keys["featured"]))


def get_world_row(world_id: str, live: dict | None = None,
                  user_id: int | None = None) -> dict | None:
    row = db.query_one("SELECT * FROM worlds WHERE id=?", (world_id,))
    return _decorate(row, live, user_id) if row else None


def vote(user_id: int, world_id: str, value: int) -> dict:
    value = 1 if value > 0 else (-1 if value < 0 else 0)
    with db.transaction():
        prev = db.query_one(
            "SELECT value FROM world_votes WHERE world_id=? AND user_id=?",
            (world_id, user_id))
        prev_val = prev["value"] if prev else 0
        if value == 0 or value == prev_val:
            db.execute("DELETE FROM world_votes WHERE world_id=? AND user_id=?",
                       (world_id, user_id))
            value = 0
        else:
            db.execute(
                "INSERT INTO world_votes(world_id,user_id,value,created_at) "
                "VALUES(?,?,?,?) ON CONFLICT(world_id,user_id) DO UPDATE SET "
                "value=excluded.value, created_at=excluded.created_at",
                (world_id, user_id, value, time.time()))
        likes = int(db.scalar(
            "SELECT COUNT(*) FROM world_votes WHERE world_id=? AND value=1",
            (world_id,), 0))
        dislikes = int(db.scalar(
            "SELECT COUNT(*) FROM world_votes WHERE world_id=? AND value=-1",
            (world_id,), 0))
        db.execute("UPDATE worlds SET likes=?, dislikes=? WHERE id=?",
                   (likes, dislikes, world_id))
    total = likes + dislikes
    return {"likes": likes, "dislikes": dislikes, "myVote": value,
            "ratio": round(likes / total * 100) if total else None}


def toggle_favorite(user_id: int, world_id: str) -> bool:
    existing = db.query_one(
        "SELECT 1 FROM favorites WHERE user_id=? AND world_id=?",
        (user_id, world_id))
    if existing:
        db.execute("DELETE FROM favorites WHERE user_id=? AND world_id=?",
                   (user_id, world_id))
        return False
    db.execute("INSERT INTO favorites(user_id,world_id,created_at) "
               "VALUES(?,?,?)", (user_id, world_id, time.time()))
    return True


def favorites(user_id: int, live: dict | None = None) -> list[dict]:
    rows = db.query(
        "SELECT w.* FROM favorites f JOIN worlds w ON w.id = f.world_id "
        "WHERE f.user_id=? ORDER BY f.created_at DESC", (user_id,))
    return [_decorate(r, live, user_id) for r in rows]


def genres() -> list[str]:
    return sorted({r["genre"] for r in db.query("SELECT DISTINCT genre "
                                                "FROM worlds")})
