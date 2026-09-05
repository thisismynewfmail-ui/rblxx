"""User accounts, sessions and public profiles."""
from __future__ import annotations

import hashlib
import time

from .. import config
from ..data import database as db
from ..security import crypto
from ..security.sanitize import (ValidationError, clean_text,
                                 validate_password, validate_username)
from . import avatar as avatar_model
from . import economy, inventory


class AuthError(Exception):
    pass


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --------------------------------------------------------------------------
# creation / auth
# --------------------------------------------------------------------------
def create_user(username: str, password: str, *, bio: str = "",
                admin: bool = False) -> dict:
    name = validate_username(username)
    pw = validate_password(password)
    existing = db.query_one("SELECT id FROM users WHERE username_lower=?",
                            (name.lower(),))
    if existing:
        raise ValidationError("That username is already taken.")
    now = time.time()
    with db.transaction():
        uid = db.insert(
            "INSERT INTO users(username, username_lower, password_hash,"
            " created_at, last_seen, bio, coins, is_admin, stipend_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (name, name.lower(), crypto.hash_password(pw), now, now,
             clean_text(bio, max_len=280, allow_newlines=True),
             config.STARTING_COINS, int(admin), now))
        avatar_model.ensure_avatar(uid)
        inventory.grant_starter_items(uid)
        db.execute("INSERT OR IGNORE INTO player_stats(user_id, updated_at) "
                   "VALUES(?,?)", (uid, now))
        economy.log_transaction(uid, config.STARTING_COINS,
                                config.STARTING_COINS, "signup_bonus")
        from ..social import badges
        badges.award(uid, "welcome")
    return get_user(uid)


def authenticate(username: str, password: str) -> dict:
    row = db.query_one(
        "SELECT * FROM users WHERE username_lower=?",
        (clean_text(username, max_len=20).lower(),))
    if row is None:
        # constant-ish work factor so timing doesn't leak existence
        crypto.verify_password(password, crypto.hash_password("decoy"))
        raise AuthError("Incorrect username or password.")
    if not crypto.verify_password(password, row["password_hash"]):
        raise AuthError("Incorrect username or password.")
    if crypto.needs_rehash(row["password_hash"]):
        db.execute("UPDATE users SET password_hash=? WHERE id=?",
                   (crypto.hash_password(password), row["id"]))
    now = time.time()
    db.execute("UPDATE users SET last_login=?, last_seen=? WHERE id=?",
               (now, now, row["id"]))
    economy.pay_daily_stipend(row["id"])
    return get_user(row["id"])


def change_password(user_id: int, old: str, new: str):
    row = db.query_one("SELECT password_hash FROM users WHERE id=?", (user_id,))
    if not row or not crypto.verify_password(old, row["password_hash"]):
        raise AuthError("Current password is incorrect.")
    pw = validate_password(new)
    db.execute("UPDATE users SET password_hash=? WHERE id=?",
               (crypto.hash_password(pw), user_id))
    db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


# --------------------------------------------------------------------------
# sessions
# --------------------------------------------------------------------------
def start_session(user_id: int, ip: str = "", user_agent: str = "") -> str:
    token = crypto.random_id(32)
    now = time.time()
    db.execute(
        "INSERT INTO sessions(token_hash,user_id,created_at,expires_at,ip,"
        "user_agent) VALUES(?,?,?,?,?,?)",
        (_token_hash(token), user_id, now, now + config.SESSION_TTL, ip,
         clean_text(user_agent, max_len=200)))
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    return token


def session_user(token: str) -> dict | None:
    if not token:
        return None
    row = db.query_one(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash=? AND s.expires_at > ?",
        (_token_hash(token), time.time()))
    if row is None:
        return None
    return _user_dict(row)


def end_session(token: str):
    if token:
        db.execute("DELETE FROM sessions WHERE token_hash=?",
                   (_token_hash(token),))


def touch(user_id: int):
    db.execute("UPDATE users SET last_seen=? WHERE id=?",
               (time.time(), user_id))


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------
def _user_dict(row) -> dict:
    d = dict(row)
    d.pop("password_hash", None)
    d["online"] = bool(d.get("last_seen") and
                       time.time() - d["last_seen"] < 180)
    return d


def get_user(user_id: int) -> dict | None:
    row = db.query_one("SELECT * FROM users WHERE id=?", (user_id,))
    return _user_dict(row) if row else None


def get_user_by_name(username: str) -> dict | None:
    row = db.query_one("SELECT * FROM users WHERE username_lower=?",
                       (clean_text(username, max_len=20).lower(),))
    return _user_dict(row) if row else None


def search_users(term: str, limit: int = 20) -> list[dict]:
    term = clean_text(term, max_len=20).lower()
    if not term:
        return []
    rows = db.query(
        "SELECT * FROM users WHERE username_lower LIKE ? "
        "ORDER BY (username_lower = ?) DESC, last_seen DESC LIMIT ?",
        (f"%{term}%", term, limit))
    return [_user_dict(r) for r in rows]


def update_profile(user_id: int, *, bio=None, status=None):
    sets, params = [], []
    if bio is not None:
        sets.append("bio=?")
        params.append(clean_text(bio, max_len=280, allow_newlines=True))
    if status is not None:
        sets.append("status_text=?")
        params.append(clean_text(status, max_len=90))
    if not sets:
        return
    params.append(user_id)
    db.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", params)


def public_profile(user_id: int, viewer_id: int | None = None) -> dict | None:
    user = get_user(user_id)
    if user is None:
        return None
    from ..social import badges, follows, friends, posts
    stats = db.query_one("SELECT * FROM player_stats WHERE user_id=?",
                         (user_id,)) or {}
    return {
        "user": {
            "id": user["id"], "username": user["username"],
            "bio": user["bio"], "status": user["status_text"],
            "createdAt": user["created_at"], "lastSeen": user["last_seen"],
            "online": user["online"], "membership": user["membership"],
            "placeVisits": user["place_visits"],
            "isAdmin": bool(user["is_admin"]),
        },
        "avatar": avatar_model.get_avatar(user_id),
        "stats": dict(stats),
        "counts": {
            "friends": friends.friend_count(user_id),
            "followers": follows.follower_count(user_id),
            "following": follows.following_count(user_id),
            "posts": posts.post_count(user_id),
            "items": inventory.item_count(user_id),
        },
        "badges": badges.for_user(user_id),
        "relationship": relationship(viewer_id, user_id) if viewer_id else None,
        "recentWorlds": recent_worlds(user_id),
    }


def relationship(viewer_id: int, target_id: int) -> dict:
    from ..social import follows, friends
    if viewer_id == target_id:
        return {"self": True, "friend": False, "following": False,
                "requestSent": False, "requestReceived": False}
    return {
        "self": False,
        "friend": friends.are_friends(viewer_id, target_id),
        "following": follows.is_following(viewer_id, target_id),
        "requestSent": friends.request_exists(viewer_id, target_id),
        "requestReceived": friends.request_exists(target_id, viewer_id),
        "blocked": bool(db.query_one(
            "SELECT 1 FROM blocks WHERE user_id=? AND blocked_id=?",
            (viewer_id, target_id))),
    }


def recent_worlds(user_id: int, limit: int = 5) -> list[dict]:
    rows = db.query(
        "SELECT v.world_id, w.name, MAX(v.started_at) AS last_played, "
        "COUNT(*) AS sessions, SUM(v.kills) AS kills "
        "FROM world_visits v JOIN worlds w ON w.id = v.world_id "
        "WHERE v.user_id=? GROUP BY v.world_id "
        "ORDER BY last_played DESC LIMIT ?", (user_id, limit))
    return db.rows_to_dicts(rows)


def leaderboard(metric: str = "kills", limit: int = 25) -> list[dict]:
    column = {"kills": "s.kills", "wins": "s.wins", "score": "s.kills*3+s.wins*10",
              "playtime": "s.playtime"}.get(metric, "s.kills")
    rows = db.query(
        f"SELECT u.id, u.username, s.kills, s.deaths, s.wins, s.rounds, "
        f"s.playtime, s.best_streak, {column} AS metric "
        f"FROM player_stats s JOIN users u ON u.id = s.user_id "
        f"ORDER BY metric DESC, s.kills DESC LIMIT ?", (limit,))
    return db.rows_to_dicts(rows)


def online_users(limit: int = 40) -> list[dict]:
    cutoff = time.time() - 180
    rows = db.query(
        "SELECT id, username, last_seen FROM users WHERE last_seen > ? "
        "ORDER BY last_seen DESC LIMIT ?", (cutoff, limit))
    return db.rows_to_dicts(rows)
