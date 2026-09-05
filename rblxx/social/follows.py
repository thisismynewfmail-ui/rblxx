"""Asymmetric following (one-way subscriptions to a player's activity)."""
from __future__ import annotations

import time

from ..data import database as db


def is_following(follower_id: int, followee_id: int) -> bool:
    return db.query_one(
        "SELECT 1 FROM follows WHERE follower_id=? AND followee_id=?",
        (follower_id, followee_id)) is not None


def follow(follower_id: int, followee_id: int) -> bool:
    if follower_id == followee_id:
        return False
    if db.query_one("SELECT 1 FROM blocks WHERE user_id=? AND blocked_id=?",
                    (followee_id, follower_id)):
        return False
    db.execute("INSERT OR IGNORE INTO follows(follower_id,followee_id,"
               "created_at) VALUES(?,?,?)",
               (follower_id, followee_id, time.time()))
    from . import notifications
    notifications.push(followee_id, "new_follower", {"from": follower_id})
    return True


def unfollow(follower_id: int, followee_id: int):
    db.execute("DELETE FROM follows WHERE follower_id=? AND followee_id=?",
               (follower_id, followee_id))


def toggle(follower_id: int, followee_id: int) -> bool:
    if is_following(follower_id, followee_id):
        unfollow(follower_id, followee_id)
        return False
    return follow(follower_id, followee_id)


def follower_count(user_id: int) -> int:
    return int(db.scalar("SELECT COUNT(*) FROM follows WHERE followee_id=?",
                         (user_id,), 0))


def following_count(user_id: int) -> int:
    return int(db.scalar("SELECT COUNT(*) FROM follows WHERE follower_id=?",
                         (user_id,), 0))


def following_ids(user_id: int) -> list[int]:
    return [r["followee_id"] for r in
            db.query("SELECT followee_id FROM follows WHERE follower_id=?",
                     (user_id,))]


def list_followers(user_id: int, limit: int = 100) -> list[dict]:
    rows = db.query(
        "SELECT u.id, u.username, u.last_seen, f.created_at FROM follows f "
        "JOIN users u ON u.id = f.follower_id WHERE f.followee_id=? "
        "ORDER BY f.created_at DESC LIMIT ?", (user_id, limit))
    return _mark(rows)


def list_following(user_id: int, limit: int = 100) -> list[dict]:
    rows = db.query(
        "SELECT u.id, u.username, u.last_seen, f.created_at FROM follows f "
        "JOIN users u ON u.id = f.followee_id WHERE f.follower_id=? "
        "ORDER BY f.created_at DESC LIMIT ?", (user_id, limit))
    return _mark(rows)


def _mark(rows) -> list[dict]:
    now = time.time()
    out = []
    for r in rows:
        d = dict(r)
        d["online"] = bool(d["last_seen"] and now - d["last_seen"] < 180)
        out.append(d)
    return out
