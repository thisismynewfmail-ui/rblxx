"""Sign up, sign in, session and account endpoints."""
from __future__ import annotations

import time

from .. import config
from ..models import avatar as avatar_model
from ..models import economy, inventory, users
from ..security import crypto
from ..security.sanitize import ValidationError
from ..social import messages, notifications
from .helpers import (CSRF_COOKIE, SESSION_COOKIE, body_str, fail,
                      handle_errors, ok, rate_limit, require_user)


def register(app):
    @app.post("/api/auth/signup")
    @handle_errors
    def signup(request):
        rate_limit(request, "signup")
        name = body_str(request, "username", max_len=32)
        password = body_str(request, "password", max_len=200)
        bio = body_str(request, "bio", max_len=280)
        user = users.create_user(name, password, bio=bio)
        return _login_response(request, user, created=True)

    @app.post("/api/auth/login")
    @handle_errors
    def login(request):
        rate_limit(request, "login", f"ip:{request.peer}")
        name = body_str(request, "username", max_len=32)
        password = body_str(request, "password", max_len=200)
        try:
            user = users.authenticate(name, password)
        except users.AuthError as e:
            return fail(str(e), 401)
        return _login_response(request, user)

    @app.post("/api/auth/logout")
    def logout(request):
        token = request.cookies.get(SESSION_COOKIE)
        users.end_session(token)
        resp = ok({"loggedOut": True})
        resp.clear_cookie(SESSION_COOKIE)
        resp.clear_cookie(CSRF_COOKIE)
        return resp

    @app.get("/api/auth/me")
    def me(request):
        user = request.state.get("user")
        if user is None:
            return ok({"user": None})
        users.touch(user["id"])
        return ok({
            "user": _public_self(user),
            "avatar": avatar_model.get_avatar(user["id"]),
            "render": avatar_model.render_bundle(user["id"]),
            "unread": {
                "messages": messages.unread_count(user["id"]),
                "notifications": notifications.unread_count(user["id"]),
            },
        })

    @app.post("/api/auth/password")
    @handle_errors
    def change_password(request):
        user = require_user(request)
        try:
            users.change_password(user["id"],
                                  body_str(request, "current", max_len=200),
                                  body_str(request, "new", max_len=200))
        except users.AuthError as e:
            return fail(str(e), 403)
        return ok({"changed": True})

    @app.post("/api/auth/profile")
    @handle_errors
    def update_profile(request):
        user = require_user(request)
        users.update_profile(user["id"],
                             bio=request.data().get("bio"),
                             status=request.data().get("status"))
        return ok({"user": _public_self(users.get_user(user["id"]))})


def _public_self(user: dict) -> dict:
    return {
        "id": user["id"], "username": user["username"], "bio": user["bio"],
        "status": user["status_text"], "coins": user["coins"],
        "membership": user["membership"], "createdAt": user["created_at"],
        "placeVisits": user["place_visits"], "isAdmin": bool(user["is_admin"]),
        "currency": config.CURRENCY_NAME,
    }


def _login_response(request, user, created: bool = False):
    token = users.start_session(user["id"], request.peer,
                                request.header("user-agent", ""))
    csrf = crypto.random_id(18)
    resp = ok({"user": _public_self(user),
               "avatar": avatar_model.get_avatar(user["id"]),
               "created": created})
    resp.set_cookie(SESSION_COOKIE, token, max_age=config.SESSION_TTL)
    resp.set_cookie(CSRF_COOKIE, csrf, max_age=config.SESSION_TTL,
                    http_only=False)
    return resp
