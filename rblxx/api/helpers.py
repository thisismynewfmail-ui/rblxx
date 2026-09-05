"""Shared plumbing for the JSON API."""
from __future__ import annotations

import functools
import time

from ..netcore.http_server import HttpError, Request, json_response
from ..security import crypto
from ..security.ratelimit import limiter
from ..security.sanitize import ValidationError

SESSION_COOKIE = "rx_session"
CSRF_COOKIE = "rx_csrf"


def ok(payload=None, **extra) -> "Response":
    body = {"ok": True}
    if isinstance(payload, dict):
        body.update(payload)
    elif payload is not None:
        body["data"] = payload
    body.update(extra)
    return json_response(body)


def fail(message: str, status: int = 400, **extra):
    return json_response({"ok": False, "error": message, **extra}, status)


def current_user(request: Request):
    return request.state.get("user")


def require_user(request: Request) -> dict:
    user = request.state.get("user")
    if user is None:
        raise HttpError(401, "Sign in to do that.")
    return user


def require_admin(request: Request) -> dict:
    user = require_user(request)
    if not user.get("is_admin"):
        raise HttpError(403, "Administrators only.")
    return user


def rate_limit(request: Request, action: str, identity: str | None = None):
    user = request.state.get("user")
    ident = identity or (f"u{user['id']}" if user else f"ip:{request.peer}")
    allowed, retry = limiter.check(action, ident)
    if not allowed:
        raise HttpError(429, f"Slow down — try again in {retry:.0f}s.",
                        headers={"Retry-After": str(int(retry) + 1)})


def check_csrf(request: Request):
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    sent = request.header("x-csrf-token") or request.data().get("_csrf")
    cookie = request.cookies.get(CSRF_COOKIE)
    if not cookie or not sent or not crypto.constant_time_eq(sent, cookie):
        raise HttpError(403, "Security token missing or stale — reload the "
                             "page and try again.")


def handle_errors(fn):
    @functools.wraps(fn)
    def wrapper(request, *args, **kwargs):
        try:
            return fn(request, *args, **kwargs)
        except ValidationError as e:
            return fail(str(e), 422)
    return wrapper


def body_str(request: Request, key: str, default: str = "",
             max_len: int = 4000) -> str:
    value = request.data().get(key, default)
    if value is None:
        return default
    return str(value)[:max_len]


def body_int(request: Request, key: str, default: int = 0) -> int:
    try:
        return int(request.data().get(key, default))
    except (TypeError, ValueError):
        return default
