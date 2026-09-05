"""Mutual friendships and friend requests."""
from __future__ import annotations

import time

from ..data import database as db
from ..security.sanitize import clean_text

MAX_FRIENDS = 200


class SocialError(Exception):
    pass


def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def are_friends(a: int, b: int) -> bool:
    lo, hi = _pair(a, b)
    return db.query_one(
        "SELECT 1 FROM friendships WHERE low_id=? AND high_id=?",
        (lo, hi)) is not None


def friend_count(user_id: int) -> int:
    return int(db.scalar(
        "SELECT COUNT(*) FROM friendships WHERE low_id=? OR high_id=?",
        (user_id, user_id), 0))


def friend_ids(user_id: int) -> list[int]:
    rows = db.query(
        "SELECT CASE WHEN low_id=? THEN high_id ELSE low_id END AS other "
        "FROM friendships WHERE low_id=? OR high_id=?",
        (user_id, user_id, user_id))
    return [r["other"] for r in rows]


def list_friends(user_id: int, limit: int = 200) -> list[dict]:
    rows = db.query(
        "SELECT u.id, u.username, u.last_seen, u.status_text, f.created_at "
        "FROM friendships f "
        "JOIN users u ON u.id = CASE WHEN f.low_id=? THEN f.high_id "
        "                            ELSE f.low_id END "
        "WHERE f.low_id=? OR f.high_id=? "
        "ORDER BY u.last_seen DESC LIMIT ?",
        (user_id, user_id, user_id, limit))
    now = time.time()
    return [{"id": r["id"], "username": r["username"],
             "lastSeen": r["last_seen"],
             "status": r["status_text"],
             "online": bool(r["last_seen"] and now - r["last_seen"] < 180),
             "friendsSince": r["created_at"]} for r in rows]


def request_exists(from_id: int, to_id: int) -> bool:
    return db.query_one(
        "SELECT 1 FROM friend_requests WHERE from_id=? AND to_id=?",
        (from_id, to_id)) is not None


def send_request(from_id: int, to_id: int, note: str = "") -> dict:
    if from_id == to_id:
        raise SocialError("You cannot friend yourself.")
    if are_friends(from_id, to_id):
        raise SocialError("You are already friends.")
    if db.query_one("SELECT 1 FROM blocks WHERE user_id=? AND blocked_id=?",
                    (to_id, from_id)):
        raise SocialError("That request could not be sent.")
    if friend_count(from_id) >= MAX_FRIENDS:
        raise SocialError("Your friends list is full.")
    if request_exists(to_id, from_id):
        return accept_request(from_id, to_id)
    db.execute(
        "INSERT OR IGNORE INTO friend_requests(from_id,to_id,created_at,note)"
        " VALUES(?,?,?,?)",
        (from_id, to_id, time.time(), clean_text(note, max_len=140)))
    from . import notifications
    notifications.push(to_id, "friend_request", {"from": from_id})
    return {"status": "requested"}


def cancel_request(from_id: int, to_id: int):
    db.execute("DELETE FROM friend_requests WHERE from_id=? AND to_id=?",
               (from_id, to_id))


def accept_request(user_id: int, requester_id: int) -> dict:
    if not request_exists(requester_id, user_id):
        raise SocialError("No pending request from that player.")
    lo, hi = _pair(user_id, requester_id)
    with db.transaction():
        db.execute("DELETE FROM friend_requests WHERE (from_id=? AND to_id=?) "
                   "OR (from_id=? AND to_id=?)",
                   (requester_id, user_id, user_id, requester_id))
        db.execute("INSERT OR IGNORE INTO friendships(low_id,high_id,"
                   "created_at) VALUES(?,?,?)", (lo, hi, time.time()))
    from . import badges, notifications
    notifications.push(requester_id, "friend_accepted", {"from": user_id})
    for uid in (user_id, requester_id):
        if friend_count(uid) >= 1:
            badges.award(uid, "friendship")
        if friend_count(uid) >= 10:
            badges.award(uid, "socialite")
    return {"status": "friends"}


def decline_request(user_id: int, requester_id: int):
    db.execute("DELETE FROM friend_requests WHERE from_id=? AND to_id=?",
               (requester_id, user_id))


def unfriend(a: int, b: int):
    lo, hi = _pair(a, b)
    db.execute("DELETE FROM friendships WHERE low_id=? AND high_id=?",
               (lo, hi))


def pending_incoming(user_id: int) -> list[dict]:
    rows = db.query(
        "SELECT u.id, u.username, r.created_at, r.note FROM friend_requests r "
        "JOIN users u ON u.id = r.from_id WHERE r.to_id=? "
        "ORDER BY r.created_at DESC", (user_id,))
    return db.rows_to_dicts(rows)


def pending_outgoing(user_id: int) -> list[dict]:
    rows = db.query(
        "SELECT u.id, u.username, r.created_at FROM friend_requests r "
        "JOIN users u ON u.id = r.to_id WHERE r.from_id=? "
        "ORDER BY r.created_at DESC", (user_id,))
    return db.rows_to_dicts(rows)


def suggestions(user_id: int, limit: int = 8) -> list[dict]:
    """Friends-of-friends who aren't already connected."""
    rows = db.query(
        "SELECT u.id, u.username, COUNT(*) AS mutual FROM users u "
        "WHERE u.id != ? AND u.id IN ("
        "  SELECT CASE WHEN f2.low_id = fof.fid THEN f2.high_id "
        "              ELSE f2.low_id END "
        "  FROM (SELECT CASE WHEN low_id=? THEN high_id ELSE low_id END AS fid"
        "        FROM friendships WHERE low_id=? OR high_id=?) fof "
        "  JOIN friendships f2 ON f2.low_id = fof.fid OR f2.high_id = fof.fid"
        ") AND u.id NOT IN ("
        "  SELECT CASE WHEN low_id=? THEN high_id ELSE low_id END "
        "  FROM friendships WHERE low_id=? OR high_id=?"
        ") GROUP BY u.id ORDER BY mutual DESC, u.last_seen DESC LIMIT ?",
        (user_id, user_id, user_id, user_id, user_id, user_id, user_id, limit))
    out = db.rows_to_dicts(rows)
    if len(out) < limit:
        extra = db.query(
            "SELECT id, username, 0 AS mutual FROM users WHERE id != ? "
            "AND id NOT IN (SELECT CASE WHEN low_id=? THEN high_id "
            "ELSE low_id END FROM friendships WHERE low_id=? OR high_id=?) "
            "ORDER BY last_seen DESC LIMIT ?",
            (user_id, user_id, user_id, user_id, limit - len(out)))
        have = {r["id"] for r in out}
        out.extend(r for r in db.rows_to_dicts(extra) if r["id"] not in have)
    return out[:limit]
