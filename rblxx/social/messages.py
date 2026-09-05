"""Private messages between players."""
from __future__ import annotations

import time

from ..data import database as db
from ..security.sanitize import ValidationError, clean_text, filter_chat
from . import blocks, friends, notifications


def send(from_id: int, to_id: int, subject: str, body: str) -> dict:
    if from_id == to_id:
        raise ValidationError("You cannot message yourself.")
    if blocks.is_blocked(from_id, to_id):
        raise ValidationError("That player cannot be messaged.")
    if not db.query_one("SELECT 1 FROM users WHERE id=?", (to_id,)):
        raise ValidationError("No such player.")
    text = filter_chat(clean_text(body, max_len=2000, allow_newlines=True))
    if not text:
        raise ValidationError("Message body cannot be empty.")
    subj = filter_chat(clean_text(subject, max_len=90)) or "(no subject)"
    mid = db.insert(
        "INSERT INTO messages(from_id,to_id,subject,body,created_at) "
        "VALUES(?,?,?,?,?)", (from_id, to_id, subj, text, time.time()))
    notifications.push(to_id, "message", {"from": from_id, "id": mid})
    return {"id": mid}


def inbox(user_id: int, limit: int = 40, offset: int = 0) -> list[dict]:
    return db.rows_to_dicts(db.query(
        "SELECT m.id, m.subject, m.body, m.created_at, m.read_at, "
        "m.from_id, u.username AS from_name FROM messages m "
        "JOIN users u ON u.id = m.from_id WHERE m.to_id=? "
        "ORDER BY m.created_at DESC LIMIT ? OFFSET ?",
        (user_id, limit, offset)))


def sent(user_id: int, limit: int = 40) -> list[dict]:
    return db.rows_to_dicts(db.query(
        "SELECT m.id, m.subject, m.body, m.created_at, m.to_id, "
        "u.username AS to_name FROM messages m "
        "JOIN users u ON u.id = m.to_id WHERE m.from_id=? "
        "ORDER BY m.created_at DESC LIMIT ?", (user_id, limit)))


def unread_count(user_id: int) -> int:
    return int(db.scalar(
        "SELECT COUNT(*) FROM messages WHERE to_id=? AND read_at IS NULL",
        (user_id,), 0))


def mark_read(user_id: int, message_id: int):
    db.execute("UPDATE messages SET read_at=? WHERE id=? AND to_id=? "
               "AND read_at IS NULL", (time.time(), message_id, user_id))


def mark_all_read(user_id: int):
    db.execute("UPDATE messages SET read_at=? WHERE to_id=? AND read_at IS NULL",
               (time.time(), user_id))


def delete(user_id: int, message_id: int):
    db.execute("DELETE FROM messages WHERE id=? AND (to_id=? OR from_id=?)",
               (message_id, user_id, user_id))
