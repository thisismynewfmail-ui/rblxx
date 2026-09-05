"""Lightweight notification inbox."""
from __future__ import annotations

import json
import time

from ..data import database as db

TEMPLATES = {
    "friend_request": "{who} sent you a friend request.",
    "friend_accepted": "{who} accepted your friend request.",
    "new_follower": "{who} started following you.",
    "post_like": "{who} liked your post.",
    "post_comment": "{who} commented on your post.",
    "message": "{who} sent you a message.",
    "badge": "You earned the {badge} badge!",
    "stipend": "Daily stipend paid: {amount} Bux.",
    "purchase": "You bought {item}.",
}


def push(user_id: int, kind: str, payload: dict | None = None):
    db.execute(
        "INSERT INTO notifications(user_id,kind,payload,created_at) "
        "VALUES(?,?,?,?)",
        (user_id, kind, json.dumps(payload or {}), time.time()))
    db.execute(
        "DELETE FROM notifications WHERE user_id=? AND id NOT IN "
        "(SELECT id FROM notifications WHERE user_id=? "
        " ORDER BY created_at DESC LIMIT 120)", (user_id, user_id))


def list_for(user_id: int, limit: int = 40) -> list[dict]:
    rows = db.query(
        "SELECT id, kind, payload, created_at, read_at FROM notifications "
        "WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, limit))
    out = []
    for r in rows:
        payload = db.json_field(r["payload"], {})
        who = None
        if payload.get("from"):
            who = db.scalar("SELECT username FROM users WHERE id=?",
                            (payload["from"],))
        text = TEMPLATES.get(r["kind"], r["kind"]).format(
            who=who or "Someone", badge=payload.get("badge", "new"),
            amount=payload.get("amount", 0), item=payload.get("item", "item"))
        out.append({"id": r["id"], "kind": r["kind"], "text": text,
                    "payload": payload, "createdAt": r["created_at"],
                    "read": r["read_at"] is not None,
                    "fromId": payload.get("from")})
    return out


def unread_count(user_id: int) -> int:
    return int(db.scalar(
        "SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL",
        (user_id,), 0))


def mark_all_read(user_id: int):
    db.execute("UPDATE notifications SET read_at=? WHERE user_id=? "
               "AND read_at IS NULL", (time.time(), user_id))
