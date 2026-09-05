"""World browser, voting, favourites and game-join tickets."""
from __future__ import annotations

import time

from .. import config
from ..gameserver.worlds import get_world
from ..models import avatar as avatar_model
from ..models import users
from ..models import worlds as worlds_model
from ..security import crypto
from .helpers import (body_str, fail, handle_errors, ok, rate_limit,
                      require_user)


def register(app, supervisor):
    def live_counts() -> dict:
        return {n["world"]: n["players"] for n in supervisor.summary()}

    @app.get("/api/worlds")
    def list_worlds(request):
        user = request.state.get("user")
        rows = worlds_model.list_worlds(
            live_counts(), user["id"] if user else None,
            sort=request.q("sort", "featured"),
            genre=request.q("genre", "all"),
            search=request.q("q", ""))
        return ok({"worlds": rows, "genres": worlds_model.genres(),
                   "totalPlaying": sum(w["playing"] for w in rows)})

    @app.get("/api/worlds/<wid>")
    def get_world_detail(request):
        user = request.state.get("user")
        row = worlds_model.get_world_row(request.params["wid"], live_counts(),
                                         user["id"] if user else None)
        if row is None:
            return fail("No such world.", 404)
        node = next((n for n in supervisor.summary()
                     if n["world"] == row["id"]), None)
        world = get_world(row["id"])
        row["server"] = {
            "up": bool(node and node["up"]),
            "players": node["players"] if node else 0,
            "roster": node.get("roster", []) if node else [],
            "tickMs": node.get("tickMs") if node else None,
            "uptime": node.get("uptime") if node else 0,
        }
        if world:
            lv = world.level()
            row["stats"] = {"parts": len(lv.parts), "spawns": len(lv.spawns),
                            "pickups": len(lv.pickups)}
            row["mode"] = world.meta.mode
        from ..data import database as db
        row["topPlayers"] = db.rows_to_dicts(db.query(
            "SELECT u.username, u.id, SUM(v.kills) AS kills, "
            "COUNT(*) AS sessions FROM world_visits v "
            "JOIN users u ON u.id=v.user_id WHERE v.world_id=? "
            "GROUP BY v.user_id ORDER BY kills DESC LIMIT 8", (row["id"],)))
        return ok({"world": row})

    @app.get("/api/worlds/<wid>/level")
    def get_level(request):
        world = get_world(request.params["wid"])
        if world is None:
            return fail("No such world.", 404)
        from ..netcore.http_server import json_response
        resp = json_response(world.level().to_dict())
        resp.header("Cache-Control", "public, max-age=600")
        return resp

    @app.post("/api/worlds/<wid>/vote")
    @handle_errors
    def vote(request):
        user = require_user(request)
        rate_limit(request, "vote")
        try:
            value = int(request.data().get("value", 0))
        except (TypeError, ValueError):
            value = 0
        if not worlds_model.get_world_row(request.params["wid"]):
            return fail("No such world.", 404)
        return ok(worlds_model.vote(user["id"], request.params["wid"], value))

    @app.post("/api/worlds/<wid>/favorite")
    def favorite(request):
        user = require_user(request)
        if not worlds_model.get_world_row(request.params["wid"]):
            return fail("No such world.", 404)
        state = worlds_model.toggle_favorite(user["id"], request.params["wid"])
        return ok({"favorited": state})

    @app.get("/api/favorites")
    def favorites(request):
        user = require_user(request)
        return ok({"worlds": worlds_model.favorites(user["id"], live_counts())})

    # ------------------------------------------------------------------
    @app.post("/api/worlds/<wid>/join")
    def join(request):
        """Mint a short-lived, signed ticket the game node will accept."""
        user = require_user(request)
        wid = request.params["wid"]
        world = get_world(wid)
        if world is None:
            return fail("No such world.", 404)
        node = supervisor.nodes.get(wid)
        if node is None or not node.alive:
            return fail("That world's server is starting up — try again in a "
                        "moment.", 503)
        players = (node.last_status or {}).get("players", 0)
        if players >= world.meta.max_players:
            return fail("That server is full right now.", 409)
        ticket = crypto.sign_token({
            "uid": user["id"],
            "name": user["username"],
            "world": wid,
            "av": avatar_model.render_bundle(user["id"]),
        }, config.TICKET_TTL, purpose="gamejoin")
        users.touch(user["id"])
        return ok({"ticket": ticket, "world": wid,
                   "socket": f"/ws/game/{wid}",
                   "expiresIn": config.TICKET_TTL})

    @app.get("/api/servers")
    def servers(request):
        return ok({"nodes": supervisor.summary(),
                   "tickRate": config.TICK_RATE,
                   "snapshotRate": config.SNAPSHOT_RATE})
