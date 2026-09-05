"""Short status posts, likes and comments — the activity feed backbone."""
from __future__ import annotations

import time

from ..data import database as db
from ..security.sanitize import ValidationError, clean_text, filter_chat, \
    looks_like_spam
from . import blocks, notifications

MAX_POST = 400
MAX_COMMENT = 240


def create(user_id: int, body: str, world_id: str | None = None) -> dict:
    text = clean_text(body, max_len=MAX_POST, allow_newlines=True)
    if not text:
        raise ValidationError("Say something first!")
    if looks_like_spam(text):
        raise ValidationError("That looks like spam — try again.")
    text = filter_chat(text)
    if world_id:
        if not db.query_one("SELECT 1 FROM worlds WHERE id=?", (world_id,)):
            world_id = None
    pid = db.insert(
        "INSERT INTO posts(user_id, body, world_id, created_at) "
        "VALUES(?,?,?,?)", (user_id, text, world_id, time.time()))
    from . import badges
    badges.award(user_id, "first_post")
    return get(pid, user_id)


def edit(user_id: int, post_id: int, body: str) -> dict:
    row = db.query_one("SELECT user_id FROM posts WHERE id=?", (post_id,))
    if row is None or row["user_id"] != user_id:
        raise ValidationError("You can only edit your own posts.")
    text = filter_chat(clean_text(body, max_len=MAX_POST, allow_newlines=True))
    if not text:
        raise ValidationError("Post cannot be empty.")
    db.execute("UPDATE posts SET body=?, edited_at=? WHERE id=?",
               (text, time.time(), post_id))
    return get(post_id, user_id)


def delete(user_id: int, post_id: int, *, is_admin: bool = False):
    row = db.query_one("SELECT user_id FROM posts WHERE id=?", (post_id,))
    if row is None:
        return
    if row["user_id"] != user_id and not is_admin:
        raise ValidationError("You can only delete your own posts.")
    db.execute("DELETE FROM posts WHERE id=?", (post_id,))


def _hydrate(rows, viewer_id: int | None) -> list[dict]:
    out = []
    liked: set[int] = set()
    ids = [r["id"] for r in rows]
    if viewer_id and ids:
        marks = db.query(
            f"SELECT post_id FROM post_likes WHERE user_id=? AND post_id IN "
            f"({','.join('?' * len(ids))})", (viewer_id, *ids))
        liked = {m["post_id"] for m in marks}
    for r in rows:
        d = dict(r)
        d["liked"] = d["id"] in liked
        d["mine"] = viewer_id == d["user_id"]
        out.append(d)
    return out


BASE_SELECT = (
    "SELECT p.id, p.user_id, p.body, p.world_id, p.created_at, p.edited_at, "
    "p.like_count, p.reply_count, u.username, w.name AS world_name "
    "FROM posts p JOIN users u ON u.id = p.user_id "
    "LEFT JOIN worlds w ON w.id = p.world_id ")


def get(post_id: int, viewer_id: int | None = None) -> dict | None:
    row = db.query_one(BASE_SELECT + "WHERE p.id=?", (post_id,))
    if row is None:
        return None
    return _hydrate([row], viewer_id)[0]


def by_user(user_id: int, viewer_id: int | None = None, limit: int = 25,
            before: float | None = None) -> list[dict]:
    params = [user_id]
    sql = BASE_SELECT + "WHERE p.user_id=? "
    if before:
        sql += "AND p.created_at < ? "
        params.append(before)
    sql += "ORDER BY p.pinned DESC, p.created_at DESC LIMIT ?"
    params.append(limit)
    return _hydrate(db.query(sql, params), viewer_id)


def post_count(user_id: int) -> int:
    return int(db.scalar("SELECT COUNT(*) FROM posts WHERE user_id=?",
                         (user_id,), 0))


def feed(user_id: int | None, limit: int = 30, before: float | None = None,
         scope: str = "friends") -> list[dict]:
    from . import follows, friends
    if scope == "everyone" or user_id is None:
        ids = None
    else:
        ids = set(friends.friend_ids(user_id))
        ids.update(follows.following_ids(user_id))
        ids.add(user_id)
    hidden = blocks.blocked_ids(user_id) if user_id else set()
    params: list = []
    sql = BASE_SELECT
    where = []
    if ids is not None:
        ids = [i for i in ids if i not in hidden]
        if not ids:
            return []
        where.append(f"p.user_id IN ({','.join('?' * len(ids))})")
        params.extend(ids)
    elif hidden:
        where.append(f"p.user_id NOT IN ({','.join('?' * len(hidden))})")
        params.extend(hidden)
    if before:
        where.append("p.created_at < ?")
        params.append(before)
    if where:
        sql += "WHERE " + " AND ".join(where) + " "
    sql += "ORDER BY p.created_at DESC LIMIT ?"
    params.append(limit)
    return _hydrate(db.query(sql, params), user_id)


def toggle_like(user_id: int, post_id: int) -> dict:
    with db.transaction():
        existing = db.query_one(
            "SELECT 1 FROM post_likes WHERE post_id=? AND user_id=?",
            (post_id, user_id))
        if existing:
            db.execute("DELETE FROM post_likes WHERE post_id=? AND user_id=?",
                       (post_id, user_id))
            liked = False
        else:
            db.execute("INSERT INTO post_likes(post_id,user_id,created_at) "
                       "VALUES(?,?,?)", (post_id, user_id, time.time()))
            liked = True
        count = int(db.scalar(
            "SELECT COUNT(*) FROM post_likes WHERE post_id=?", (post_id,), 0))
        db.execute("UPDATE posts SET like_count=? WHERE id=?",
                   (count, post_id))
    if liked:
        owner = db.scalar("SELECT user_id FROM posts WHERE id=?", (post_id,))
        if owner and owner != user_id:
            notifications.push(owner, "post_like",
                               {"from": user_id, "post": post_id})
    return {"liked": liked, "likeCount": count}


# -- comments --------------------------------------------------------------
def add_comment(user_id: int, post_id: int, body: str) -> dict:
    text = clean_text(body, max_len=MAX_COMMENT)
    if not text:
        raise ValidationError("Comment cannot be empty.")
    text = filter_chat(text)
    if not db.query_one("SELECT 1 FROM posts WHERE id=?", (post_id,)):
        raise ValidationError("That post no longer exists.")
    with db.transaction():
        cid = db.insert(
            "INSERT INTO comments(post_id,user_id,body,created_at) "
            "VALUES(?,?,?,?)", (post_id, user_id, text, time.time()))
        count = int(db.scalar(
            "SELECT COUNT(*) FROM comments WHERE post_id=?", (post_id,), 0))
        db.execute("UPDATE posts SET reply_count=? WHERE id=?",
                   (count, post_id))
    owner = db.scalar("SELECT user_id FROM posts WHERE id=?", (post_id,))
    if owner and owner != user_id:
        notifications.push(owner, "post_comment",
                           {"from": user_id, "post": post_id})
    return {"id": cid, "body": text, "postId": post_id,
            "replyCount": count}


def comments(post_id: int, limit: int = 50) -> list[dict]:
    return db.rows_to_dicts(db.query(
        "SELECT c.id, c.user_id, c.body, c.created_at, u.username "
        "FROM comments c JOIN users u ON u.id = c.user_id "
        "WHERE c.post_id=? ORDER BY c.created_at ASC LIMIT ?",
        (post_id, limit)))


def delete_comment(user_id: int, comment_id: int, *, is_admin: bool = False):
    row = db.query_one("SELECT user_id, post_id FROM comments WHERE id=?",
                       (comment_id,))
    if row is None:
        return
    if row["user_id"] != user_id and not is_admin:
        raise ValidationError("You can only delete your own comments.")
    with db.transaction():
        db.execute("DELETE FROM comments WHERE id=?", (comment_id,))
        count = int(db.scalar("SELECT COUNT(*) FROM comments WHERE post_id=?",
                              (row["post_id"],), 0))
        db.execute("UPDATE posts SET reply_count=? WHERE id=?",
                   (count, row["post_id"]))
