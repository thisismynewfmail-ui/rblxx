"""Friends, following, posts, messages, notifications."""
from __future__ import annotations

from ..models import users
from ..security.sanitize import ValidationError
from ..social import (badges, blocks, follows, friends, messages,
                      notifications, posts)
from .helpers import (body_int, body_str, fail, handle_errors, ok, rate_limit,
                      require_user)


def _resolve(target: str) -> dict | None:
    if str(target).isdigit():
        return users.get_user(int(target))
    return users.get_user_by_name(target)


def register(app):
    # ---------------- friends ----------------
    @app.get("/api/friends")
    def list_friends(request):
        user = require_user(request)
        return ok({
            "friends": friends.list_friends(user["id"]),
            "incoming": friends.pending_incoming(user["id"]),
            "outgoing": friends.pending_outgoing(user["id"]),
            "suggestions": friends.suggestions(user["id"]),
        })

    @app.get("/api/users/<name>/friends")
    def friends_of(request):
        target = _resolve(request.params["name"])
        if target is None:
            return fail("No such player.", 404)
        return ok({"friends": friends.list_friends(target["id"])})

    @app.post("/api/friends/request")
    @handle_errors
    def send_request(request):
        user = require_user(request)
        rate_limit(request, "default")
        target = _resolve(body_str(request, "user", max_len=32))
        if target is None:
            return fail("No such player.", 404)
        try:
            result = friends.send_request(user["id"], target["id"],
                                          body_str(request, "note", max_len=140))
        except friends.SocialError as e:
            return fail(str(e), 400)
        return ok(result)

    @app.post("/api/friends/accept")
    @handle_errors
    def accept(request):
        user = require_user(request)
        target = _resolve(body_str(request, "user", max_len=32))
        if target is None:
            return fail("No such player.", 404)
        try:
            return ok(friends.accept_request(user["id"], target["id"]))
        except friends.SocialError as e:
            return fail(str(e), 400)

    @app.post("/api/friends/decline")
    def decline(request):
        user = require_user(request)
        target = _resolve(body_str(request, "user", max_len=32))
        if target:
            friends.decline_request(user["id"], target["id"])
        return ok({"status": "declined"})

    @app.post("/api/friends/cancel")
    def cancel(request):
        user = require_user(request)
        target = _resolve(body_str(request, "user", max_len=32))
        if target:
            friends.cancel_request(user["id"], target["id"])
        return ok({"status": "cancelled"})

    @app.post("/api/friends/remove")
    def remove(request):
        user = require_user(request)
        target = _resolve(body_str(request, "user", max_len=32))
        if target:
            friends.unfriend(user["id"], target["id"])
        return ok({"status": "removed"})

    # ---------------- following ----------------
    @app.post("/api/follow")
    def toggle_follow(request):
        user = require_user(request)
        target = _resolve(body_str(request, "user", max_len=32))
        if target is None:
            return fail("No such player.", 404)
        following = follows.toggle(user["id"], target["id"])
        return ok({"following": following,
                   "followers": follows.follower_count(target["id"])})

    @app.get("/api/users/<name>/followers")
    def followers(request):
        target = _resolve(request.params["name"])
        if target is None:
            return fail("No such player.", 404)
        return ok({"followers": follows.list_followers(target["id"]),
                   "following": follows.list_following(target["id"])})

    # ---------------- blocking ----------------
    @app.post("/api/block")
    def block(request):
        user = require_user(request)
        target = _resolve(body_str(request, "user", max_len=32))
        if target is None:
            return fail("No such player.", 404)
        if request.data().get("unblock"):
            blocks.unblock(user["id"], target["id"])
            return ok({"blocked": False})
        blocks.block(user["id"], target["id"])
        return ok({"blocked": True})

    @app.get("/api/blocked")
    def blocked(request):
        user = require_user(request)
        return ok({"blocked": blocks.list_blocked(user["id"])})

    # ---------------- posts ----------------
    @app.get("/api/feed")
    def feed(request):
        user = request.state.get("user")
        scope = request.q("scope", "friends")
        if user is None and scope != "everyone":
            return fail("Sign in to see your friends' posts.", 401)
        before = request.q("before")
        return ok({"posts": posts.feed(
            user["id"] if user else None,
            limit=min(50, request.qint("limit", 25)),
            before=float(before) if before else None, scope=scope)})

    @app.post("/api/posts")
    @handle_errors
    def create_post(request):
        user = require_user(request)
        rate_limit(request, "post")
        post = posts.create(user["id"], body_str(request, "body", max_len=400),
                            request.data().get("worldId"))
        return ok({"post": post})

    @app.get("/api/users/<name>/posts")
    def user_posts(request):
        viewer = request.state.get("user")
        target = _resolve(request.params["name"])
        if target is None:
            return fail("No such player.", 404)
        before = request.q("before")
        return ok({"posts": posts.by_user(
            target["id"], viewer["id"] if viewer else None,
            limit=min(50, request.qint("limit", 25)),
            before=float(before) if before else None)})

    @app.post("/api/posts/<pid>/like")
    def like(request):
        user = require_user(request)
        rate_limit(request, "vote")
        return ok(posts.toggle_like(user["id"], int(request.params["pid"])))

    @app.delete("/api/posts/<pid>")
    @handle_errors
    def delete_post(request):
        user = require_user(request)
        posts.delete(user["id"], int(request.params["pid"]),
                     is_admin=bool(user.get("is_admin")))
        return ok({"deleted": True})

    @app.patch("/api/posts/<pid>")
    @handle_errors
    def edit_post(request):
        user = require_user(request)
        return ok({"post": posts.edit(user["id"], int(request.params["pid"]),
                                      body_str(request, "body", max_len=400))})

    @app.get("/api/posts/<pid>/comments")
    def list_comments(request):
        return ok({"comments": posts.comments(int(request.params["pid"]))})

    @app.post("/api/posts/<pid>/comments")
    @handle_errors
    def add_comment(request):
        user = require_user(request)
        rate_limit(request, "comment")
        return ok(posts.add_comment(user["id"], int(request.params["pid"]),
                                    body_str(request, "body", max_len=240)))

    @app.delete("/api/comments/<cid>")
    @handle_errors
    def delete_comment(request):
        user = require_user(request)
        posts.delete_comment(user["id"], int(request.params["cid"]),
                             is_admin=bool(user.get("is_admin")))
        return ok({"deleted": True})

    # ---------------- messages ----------------
    @app.get("/api/messages")
    def inbox(request):
        user = require_user(request)
        return ok({"inbox": messages.inbox(user["id"]),
                   "sent": messages.sent(user["id"]),
                   "unread": messages.unread_count(user["id"])})

    @app.post("/api/messages")
    @handle_errors
    def send_message(request):
        user = require_user(request)
        rate_limit(request, "message")
        target = _resolve(body_str(request, "to", max_len=32))
        if target is None:
            return fail("No such player.", 404)
        return ok(messages.send(user["id"], target["id"],
                                body_str(request, "subject", max_len=90),
                                body_str(request, "body", max_len=2000)))

    @app.post("/api/messages/<mid>/read")
    def read_message(request):
        user = require_user(request)
        messages.mark_read(user["id"], int(request.params["mid"]))
        return ok({"unread": messages.unread_count(user["id"])})

    @app.delete("/api/messages/<mid>")
    def delete_message(request):
        user = require_user(request)
        messages.delete(user["id"], int(request.params["mid"]))
        return ok({"deleted": True})

    # ---------------- notifications ----------------
    @app.get("/api/notifications")
    def list_notifications(request):
        user = require_user(request)
        return ok({"notifications": notifications.list_for(user["id"]),
                   "unread": notifications.unread_count(user["id"])})

    @app.post("/api/notifications/read")
    def read_notifications(request):
        user = require_user(request)
        notifications.mark_all_read(user["id"])
        return ok({"unread": 0})

    # ---------------- badges ----------------
    @app.get("/api/badges")
    def all_badges(request):
        return ok({"badges": badges.all_badges()})
