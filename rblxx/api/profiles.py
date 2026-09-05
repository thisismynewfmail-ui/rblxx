"""Profiles, avatar editing, inventory and the catalog."""
from __future__ import annotations

from ..data import database as db
from ..models import avatar as avatar_model
from ..models import catalog, economy, inventory, users
from ..security.sanitize import ValidationError
from .helpers import (body_int, body_str, fail, handle_errors, ok, rate_limit,
                      require_user)


def register(app):
    # ---------------- profiles ----------------
    @app.get("/api/users/<name>")
    def get_profile(request):
        viewer = request.state.get("user")
        target = users.get_user_by_name(request.params["name"])
        if target is None and request.params["name"].isdigit():
            target = users.get_user(int(request.params["name"]))
        if target is None:
            return fail("No such player.", 404)
        profile = users.public_profile(target["id"],
                                       viewer["id"] if viewer else None)
        profile["render"] = avatar_model.render_bundle(target["id"])
        return ok(profile)

    @app.get("/api/users/<name>/inventory")
    def get_inventory(request):
        target = users.get_user_by_name(request.params["name"])
        if target is None:
            return fail("No such player.", 404)
        category = request.q("category", "all")
        items = inventory.list_inventory(target["id"], category)
        return ok({"items": items, "total": len(items),
                   "categories": catalog.CATEGORIES,
                   "owner": {"id": target["id"],
                             "username": target["username"]}})

    @app.get("/api/search/users")
    def search(request):
        term = request.q("q", "")
        return ok({"users": [
            {"id": u["id"], "username": u["username"], "online": u["online"],
             "bio": u["bio"]} for u in users.search_users(term, 20)]})

    @app.get("/api/leaderboard")
    def leaderboard(request):
        metric = request.q("metric", "kills")
        return ok({"metric": metric,
                   "rows": users.leaderboard(metric, request.qint("limit", 25))})

    @app.get("/api/online")
    def online(request):
        return ok({"users": users.online_users()})

    # ---------------- avatar ----------------
    @app.get("/api/avatar")
    def get_avatar(request):
        user = require_user(request)
        return ok({
            "avatar": avatar_model.get_avatar(user["id"]),
            "render": avatar_model.render_bundle(user["id"]),
            "owned": sorted(inventory.owned_ids(user["id"])),
            "palette": avatar_model.PRESET_PALETTE,
            "outfits": avatar_model.list_outfits(user["id"]),
            "parts": avatar_model.BODY_PARTS,
        })

    @app.post("/api/avatar/colors")
    @handle_errors
    def set_colors(request):
        user = require_user(request)
        colors = request.data().get("colors") or {}
        if not isinstance(colors, dict):
            return fail("Bad colours payload.")
        avatar_model.set_colors(user["id"], colors)
        return ok({"avatar": avatar_model.get_avatar(user["id"]),
                   "render": avatar_model.render_bundle(user["id"])})

    @app.post("/api/avatar/equip")
    @handle_errors
    def equip(request):
        user = require_user(request)
        item_id = body_str(request, "itemId", max_len=80)
        try:
            av = avatar_model.equip(user["id"], item_id)
        except ValueError as e:
            return fail(str(e), 400)
        return ok({"avatar": av,
                   "render": avatar_model.render_bundle(user["id"])})

    @app.post("/api/avatar/unequip")
    @handle_errors
    def unequip(request):
        user = require_user(request)
        avatar_model.unequip(user["id"], body_str(request, "slot", max_len=40))
        return ok({"avatar": avatar_model.get_avatar(user["id"]),
                   "render": avatar_model.render_bundle(user["id"])})

    @app.post("/api/avatar/scale")
    @handle_errors
    def scale(request):
        user = require_user(request)
        try:
            avatar_model.set_scale(user["id"],
                                   float(request.data().get("scale", 1.0)))
        except (TypeError, ValueError):
            return fail("Bad scale value.")
        return ok({"avatar": avatar_model.get_avatar(user["id"])})

    @app.post("/api/avatar/outfits")
    @handle_errors
    def save_outfit(request):
        user = require_user(request)
        out = avatar_model.save_outfit(user["id"],
                                       body_str(request, "name", "Outfit", 40))
        return ok({"outfit": out,
                   "outfits": avatar_model.list_outfits(user["id"])})

    @app.post("/api/avatar/outfits/<oid>/wear")
    @handle_errors
    def wear_outfit(request):
        user = require_user(request)
        try:
            av = avatar_model.wear_outfit(user["id"],
                                          int(request.params["oid"]))
        except ValueError as e:
            return fail(str(e), 400)
        return ok({"avatar": av,
                   "render": avatar_model.render_bundle(user["id"])})

    @app.delete("/api/avatar/outfits/<oid>")
    def delete_outfit(request):
        user = require_user(request)
        avatar_model.delete_outfit(user["id"], int(request.params["oid"]))
        return ok({"outfits": avatar_model.list_outfits(user["id"])})

    # ---------------- catalog ----------------
    @app.get("/api/catalog")
    def list_catalog(request):
        user = request.state.get("user")
        result = catalog.list_items(
            category=request.q("category", "all"),
            search=request.q("q", ""),
            rarity=request.q("rarity", "all"),
            sort=request.q("sort", "featured"),
            offset=request.qint("offset", 0),
            limit=min(120, request.qint("limit", 60)))
        owned = inventory.owned_ids(user["id"]) if user else set()
        for item in result["items"]:
            item["owned"] = item["id"] in owned
            if item.get("stock") is not None:
                item["remaining"] = catalog.stock_remaining(item["id"])
        result["categories"] = catalog.CATEGORIES
        result["rarities"] = list(catalog.RARITY_COLORS.keys())
        result["balance"] = economy.balance(user["id"]) if user else 0
        return ok(result)

    @app.get("/api/catalog/<item_id>")
    def get_catalog_item(request):
        item = catalog.get_item(request.params["item_id"])
        if item is None:
            return fail("No such item.", 404)
        user = request.state.get("user")
        item = dict(item)
        item["owned"] = inventory.owns(user["id"], item["id"]) if user else False
        item["remaining"] = catalog.stock_remaining(item["id"])
        item["ownerCount"] = int(db.scalar(
            "SELECT COUNT(*) FROM inventory WHERE item_id=?",
            (item["id"],), 0))
        return ok({"item": item})

    @app.post("/api/catalog/<item_id>/buy")
    @handle_errors
    def buy(request):
        user = require_user(request)
        rate_limit(request, "purchase")
        try:
            result = inventory.purchase(user["id"], request.params["item_id"])
        except inventory.PurchaseError as e:
            return fail(str(e), 400)
        from ..social import notifications
        notifications.push(user["id"], "purchase",
                           {"item": result["item"]["name"]})
        return ok({"item": result["item"], "balance": result["balance"],
                   "serial": result["serial"]})

    @app.get("/api/economy")
    def economy_view(request):
        user = require_user(request)
        return ok({"balance": economy.balance(user["id"]),
                   "history": economy.history(user["id"])})
