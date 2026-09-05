"""Currency, transactions and the daily stipend."""
from __future__ import annotations

import time

from .. import config
from ..data import database as db


def balance(user_id: int) -> int:
    return int(db.scalar("SELECT coins FROM users WHERE id=?", (user_id,), 0))


def log_transaction(user_id: int, delta: int, new_balance: int, reason: str,
                    ref: str | None = None):
    db.execute(
        "INSERT INTO transactions(user_id,delta,balance,reason,ref,created_at)"
        " VALUES(?,?,?,?,?,?)",
        (user_id, delta, new_balance, reason, ref, time.time()))


def adjust(user_id: int, delta: int, reason: str, ref: str | None = None,
           *, in_transaction: bool = False) -> int:
    def _do():
        current = balance(user_id)
        new = max(0, current + int(delta))
        db.execute("UPDATE users SET coins=? WHERE id=?", (new, user_id))
        log_transaction(user_id, int(delta), new, reason, ref)
        return new

    if in_transaction:
        return _do()
    with db.transaction():
        return _do()


def history(user_id: int, limit: int = 40) -> list[dict]:
    return db.rows_to_dicts(db.query(
        "SELECT delta, balance, reason, ref, created_at FROM transactions "
        "WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, limit)))


def pay_daily_stipend(user_id: int) -> int:
    row = db.query_one("SELECT stipend_at, coins FROM users WHERE id=?",
                       (user_id,))
    if row is None:
        return 0
    now = time.time()
    if now - (row["stipend_at"] or 0) < 20 * 3600:
        return 0
    db.execute("UPDATE users SET stipend_at=? WHERE id=?", (now, user_id))
    adjust(user_id, config.DAILY_STIPEND, "daily_stipend")
    from ..social import notifications
    notifications.push(user_id, "stipend",
                       {"amount": config.DAILY_STIPEND})
    return config.DAILY_STIPEND
