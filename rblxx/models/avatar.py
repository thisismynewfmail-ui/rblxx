"""Avatar body colours + equipped items."""
from __future__ import annotations

import json
import time

from ..data import database as db
from ..security.sanitize import validate_hex_color
from . import catalog, inventory

BODY_PARTS = ("head", "torso", "left_arm", "right_arm", "left_leg",
              "right_leg")
SLOTS = ("hat", "hat2", "face", "shirt", "pants", "back", "gear")
DEFAULTS = {
    "head": "#f3d64e", "torso": "#1c7bc4", "left_arm": "#f3d64e",
    "right_arm": "#f3d64e", "left_leg": "#8bc34a", "right_leg": "#8bc34a",
}
PRESET_PALETTE = [
    "#f3d64e", "#e8b93d", "#d9534f", "#c0392b", "#8e44ad", "#7f5fbf",
    "#2f7fd6", "#1c7bc4", "#17a2b8", "#2ecc71", "#8bc34a", "#4f9c33",
    "#f39c12", "#e67e22", "#ecf0f1", "#bdc3c7", "#95a5a6", "#5d6d7e",
    "#34495e", "#2c3e50", "#1a1a1d", "#7b4b2a", "#a3714a", "#f7c6a3",
    "#ff8fb1", "#ffd1dc", "#00e5c0", "#39ff6a", "#ff5f1f", "#b0002d",
]


def ensure_avatar(user_id: int):
    db.execute(
        "INSERT OR IGNORE INTO avatars(user_id, head, torso, left_arm,"
        " right_arm, left_leg, right_leg, equipped, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (user_id, DEFAULTS["head"], DEFAULTS["torso"], DEFAULTS["left_arm"],
         DEFAULTS["right_arm"], DEFAULTS["left_leg"], DEFAULTS["right_leg"],
         json.dumps({"face": "face_smile"}), time.time()))


def get_avatar(user_id: int) -> dict:
    ensure_avatar(user_id)
    row = db.query_one("SELECT * FROM avatars WHERE user_id=?", (user_id,))
    equipped = db.json_field(row["equipped"], {})
    items = {}
    for slot, item_id in list(equipped.items()):
        item = catalog.get_item(item_id)
        if item is None:
            equipped.pop(slot, None)
            continue
        items[slot] = item
    return {
        "colors": {p: row[p] for p in BODY_PARTS},
        "equipped": equipped,
        "items": items,
        "bodyScale": row["body_scale"],
        "skin": (items.get("gear") or {}).get("render", {}).get("skin",
                                                                "default"),
        "updatedAt": row["updated_at"],
    }


def render_bundle(user_id: int) -> dict:
    """Compact payload the 3D renderer consumes (also sent into games)."""
    av = get_avatar(user_id)
    return {
        "colors": av["colors"],
        "parts": [p for item in av["items"].values()
                  for p in (item.get("render", {}).get("parts") or [])],
        "face": (av["items"].get("face", {}).get("render", {})
                 .get("face", "smile")),
        "paint": {k: v for item in av["items"].values()
                  for k, v in (item.get("render", {}).get("paint") or {}).items()},
        "pattern": {
            "shirt": (av["items"].get("shirt", {}).get("render", {})
                      .get("pattern")),
            "pants": (av["items"].get("pants", {}).get("render", {})
                      .get("pattern")),
        },
        "skin": av["skin"],
        "scale": av["bodyScale"],
    }


def set_colors(user_id: int, colors: dict):
    ensure_avatar(user_id)
    sets, params = [], []
    for part in BODY_PARTS:
        if part in colors:
            sets.append(f"{part}=?")
            params.append(validate_hex_color(colors[part], DEFAULTS[part]))
    if not sets:
        return
    sets.append("updated_at=?")
    params.extend([time.time(), user_id])
    db.execute(f"UPDATE avatars SET {', '.join(sets)} WHERE user_id=?", params)


def equip(user_id: int, item_id: str) -> dict:
    item = catalog.get_item(item_id)
    if item is None:
        raise ValueError("Unknown item.")
    if not inventory.owns(user_id, item_id):
        raise ValueError("You do not own that item.")
    ensure_avatar(user_id)
    row = db.query_one("SELECT equipped FROM avatars WHERE user_id=?",
                       (user_id,))
    equipped = db.json_field(row["equipped"], {})
    slot = item["slot"]
    if slot == "hat" and equipped.get("hat") and equipped["hat"] != item_id:
        # a second hat is allowed — classic stacking
        if equipped.get("hat2") == item_id:
            equipped.pop("hat2")
        else:
            equipped["hat2"] = equipped["hat"]
    equipped[slot] = item_id
    db.execute("UPDATE avatars SET equipped=?, updated_at=? WHERE user_id=?",
               (json.dumps(equipped), time.time(), user_id))
    return get_avatar(user_id)


def unequip(user_id: int, slot_or_item: str) -> dict:
    ensure_avatar(user_id)
    row = db.query_one("SELECT equipped FROM avatars WHERE user_id=?",
                       (user_id,))
    equipped = db.json_field(row["equipped"], {})
    if slot_or_item in equipped:
        equipped.pop(slot_or_item)
    else:
        for slot, item_id in list(equipped.items()):
            if item_id == slot_or_item:
                equipped.pop(slot)
    db.execute("UPDATE avatars SET equipped=?, updated_at=? WHERE user_id=?",
               (json.dumps(equipped), time.time(), user_id))
    return get_avatar(user_id)


def set_scale(user_id: int, scale: float):
    scale = max(0.75, min(1.25, float(scale)))
    db.execute("UPDATE avatars SET body_scale=?, updated_at=? WHERE user_id=?",
               (scale, time.time(), user_id))


# -- outfits ---------------------------------------------------------------
def save_outfit(user_id: int, name: str) -> dict:
    from ..security.sanitize import clean_text
    av = get_avatar(user_id)
    config_json = json.dumps({"colors": av["colors"],
                              "equipped": av["equipped"],
                              "bodyScale": av["bodyScale"]})
    oid = db.insert(
        "INSERT INTO outfits(user_id,name,config,created_at) VALUES(?,?,?,?)",
        (user_id, clean_text(name, max_len=40) or "Outfit", config_json,
         time.time()))
    return {"id": oid, "name": name}


def list_outfits(user_id: int) -> list[dict]:
    rows = db.query("SELECT id,name,config,created_at FROM outfits "
                    "WHERE user_id=? ORDER BY created_at DESC", (user_id,))
    return [{"id": r["id"], "name": r["name"],
             "config": db.json_field(r["config"], {}),
             "createdAt": r["created_at"]} for r in rows]


def wear_outfit(user_id: int, outfit_id: int) -> dict:
    row = db.query_one("SELECT config FROM outfits WHERE id=? AND user_id=?",
                       (outfit_id, user_id))
    if row is None:
        raise ValueError("Outfit not found.")
    cfg = db.json_field(row["config"], {})
    set_colors(user_id, cfg.get("colors", {}))
    equipped = {s: i for s, i in (cfg.get("equipped") or {}).items()
                if inventory.owns(user_id, i)}
    db.execute("UPDATE avatars SET equipped=?, body_scale=?, updated_at=? "
               "WHERE user_id=?",
               (json.dumps(equipped), cfg.get("bodyScale", 1.0), time.time(),
                user_id))
    return get_avatar(user_id)


def delete_outfit(user_id: int, outfit_id: int):
    db.execute("DELETE FROM outfits WHERE id=? AND user_id=?",
               (outfit_id, user_id))
