"""Blocking — severs friendship, following and messaging both ways."""
from __future__ import annotations

import time

from ..data import database as db
from . import follows, friends


def block(user_id: int, target_id: int):
    if user_id == target_id:
        return
    with db.transaction():
        db.execute("INSERT OR IGNORE INTO blocks(user_id,blocked_id,"
                   "created_at) VALUES(?,?,?)",
                   (user_id, target_id, time.time()))
        lo, hi = (user_id, target_id) if user_id < target_id \
            else (target_id, user_id)
        db.execute("DELETE FROM friendships WHERE low_id=? AND high_id=?",
                   (lo, hi))
        db.execute("DELETE FROM friend_requests WHERE (from_id=? AND to_id=?)"
                   " OR (from_id=? AND to_id=?)",
                   (user_id, target_id, target_id, user_id))
        db.execute("DELETE FROM follows WHERE (follower_id=? AND followee_id=?)"
                   " OR (follower_id=? AND followee_id=?)",
                   (user_id, target_id, target_id, user_id))


def unblock(user_id: int, target_id: int):
    db.execute("DELETE FROM blocks WHERE user_id=? AND blocked_id=?",
               (user_id, target_id))


def is_blocked(user_id: int, target_id: int) -> bool:
    return db.query_one(
        "SELECT 1 FROM blocks WHERE (user_id=? AND blocked_id=?) "
        "OR (user_id=? AND blocked_id=?)",
        (user_id, target_id, target_id, user_id)) is not None


def blocked_ids(user_id: int) -> set[int]:
    return {r["blocked_id"] for r in db.query(
        "SELECT blocked_id FROM blocks WHERE user_id=?", (user_id,))}


def list_blocked(user_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query(
        "SELECT u.id, u.username, b.created_at FROM blocks b "
        "JOIN users u ON u.id = b.blocked_id WHERE b.user_id=? "
        "ORDER BY b.created_at DESC", (user_id,)))
