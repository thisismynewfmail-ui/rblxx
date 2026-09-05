"""The web edge: UI, JSON API and the websocket relay into the game nodes.

Everything the local network talks to lives on a single port.  Game traffic
is relayed byte-for-byte into the per-world node processes, so the edge never
has to parse a game frame.
"""
from __future__ import annotations

import asyncio
import time
import traceback

from . import config
from .api import auth as auth_api
from .api import profiles as profiles_api
from .api import social as social_api
from .api import worlds as worlds_api
from .api.helpers import CSRF_COOKIE, SESSION_COOKIE, check_csrf
from .data import database as db
from .gameserver.supervisor import Supervisor
from .models import users
from .netcore import websocket as ws
from .netcore.http_server import (HttpError, HttpServer, Response,
                                  json_response, redirect)
from .security import crypto

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
CSRF_EXEMPT = ("/api/auth/login", "/api/auth/signup")


def build_app(supervisor: Supervisor) -> HttpServer:
    app = HttpServer(name="rblxx", access_log=False)

    # ---------------- middleware ----------------
    @app.middleware
    async def attach_user(request, nxt):
        token = request.cookies.get(SESSION_COOKIE)
        request.state["user"] = users.session_user(token) if token else None
        request.state["supervisor"] = supervisor
        response = await nxt(request)
        return response

    @app.middleware
    async def csrf_guard(request, nxt):
        if request.method not in SAFE_METHODS and \
                request.path.startswith("/api/") and \
                request.path not in CSRF_EXEMPT:
            if request.state.get("user") is not None:
                check_csrf(request)
        return await nxt(request)

    @app.middleware
    async def security_headers(request, nxt):
        response = await nxt(request)
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control",
                                        "no-store, must-revalidate")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        return response

    # ---------------- API ----------------
    auth_api.register(app)
    profiles_api.register(app)
    social_api.register(app)
    worlds_api.register(app, supervisor)

    @app.get("/api/bootstrap")
    def bootstrap(request):
        """One round-trip everything the SPA needs to paint its first frame."""
        from .models import avatar as avatar_model
        from .models import worlds as worlds_model
        from .social import messages, notifications
        user = request.state.get("user")
        live = {n["world"]: n["players"] for n in supervisor.summary()}
        payload = {
            "ok": True,
            "currency": config.CURRENCY_NAME,
            "worlds": worlds_model.list_worlds(live,
                                               user["id"] if user else None),
            "totalPlaying": sum(live.values()),
            "user": None,
        }
        if user:
            users.touch(user["id"])
            payload["user"] = {
                "id": user["id"], "username": user["username"],
                "coins": user["coins"], "bio": user["bio"],
                "status": user["status_text"],
                "isAdmin": bool(user["is_admin"]),
                "createdAt": user["created_at"],
            }
            payload["render"] = avatar_model.render_bundle(user["id"])
            payload["unread"] = {
                "messages": messages.unread_count(user["id"]),
                "notifications": notifications.unread_count(user["id"]),
            }
            payload["csrf"] = request.cookies.get(CSRF_COOKIE)
        return json_response(payload)

    @app.get("/api/health")
    def health(request):
        return json_response({
            "ok": True,
            "uptime": round(time.time() - START_TIME, 1),
            "nodes": supervisor.summary(),
        })

    # ---------------- websocket relay ----------------
    @app.websocket("/ws/game/<wid>")
    async def relay(request):
        await relay_to_node(request, supervisor)

    # ---------------- static & SPA ----------------
    app.static("/assets", str(config.WEB_ROOT / "assets"),
               cache_control="public, max-age=86400")
    app.static("/css", str(config.WEB_ROOT / "css"), cache_control="no-cache")
    app.static("/js", str(config.WEB_ROOT / "js"), cache_control="no-cache")

    @app.get("/favicon.ico")
    def favicon(request):
        path = config.WEB_ROOT / "assets" / "favicon.svg"
        if path.exists():
            return Response(path.read_bytes(), 200, "image/svg+xml",
                            {"Cache-Control": "public, max-age=86400"})
        return Response(b"", 204)

    @app.get("/play/<wid>")
    def play(request):
        return _page("play.html")

    @app.fallback
    def spa(request):
        if request.path.startswith(("/api/", "/ws/")):
            raise HttpError(404, "Unknown endpoint.")
        return _page("index.html")

    return app


def _page(name: str) -> Response:
    path = config.WEB_ROOT / name
    if not path.exists():
        raise HttpError(404, f"{name} is missing from the web root.")
    return Response(path.read_bytes(), 200, "text/html; charset=utf-8",
                    {"Cache-Control": "no-cache"})


async def relay_to_node(request, supervisor: Supervisor):
    """Authenticate, then pump raw websocket frames to the world's node.

    Frames already carry the correct masking for each direction, so no
    re-framing is needed — the edge is a pure byte pump and stays cheap
    even with a full server on every world.
    """
    wid = request.params.get("wid", "")
    node = supervisor.nodes.get(wid)
    ticket = request.q("ticket", "")
    claims = crypto.verify_token(ticket, purpose="gamejoin")
    if node is None or not node.alive or not claims or claims.get("world") != wid:
        request.writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n"
                             b"Connection: close\r\n\r\n")
        try:
            await request.writer.drain()
        except Exception:
            pass
        return

    head = ws.handshake_headers(request)
    if head is None:
        request.writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n"
                             b"Connection: close\r\n\r\n")
        await request.writer.drain()
        return

    try:
        up_reader, up_writer = await ws.client_handshake(
            config.NODE_HOST, node.port, f"/ws?ticket={ticket}",
            {"X-Forwarded-For": request.peer}, timeout=6.0)
    except (OSError, ConnectionError, asyncio.TimeoutError):
        request.writer.write(b"HTTP/1.1 503 Service Unavailable\r\n"
                             b"Content-Length: 0\r\nConnection: close\r\n\r\n")
        try:
            await request.writer.drain()
        except Exception:
            pass
        return

    request.writer.write(head)
    await request.writer.drain()

    await asyncio.gather(
        ws.pump(request.reader, up_writer),
        ws.pump(up_reader, request.writer),
        return_exceptions=True,
    )


START_TIME = time.time()
