"""Read access to the central item catalog."""
from __future__ import annotations

import time

from ..data import database as db

RARITY_ORDER = {"common": 0, "uncommon": 1, "rare": 2, "epic": 3,
                "legendary": 4}
RARITY_COLORS = {
    "common": "#9aa2ab", "uncommon": "#4fbf6a", "rare": "#3aa0ff",
    "epic": "#b07cff", "legendary": "#f2b13d",
}
CATEGORIES = [
    {"id": "hat", "label": "Hats", "icon": "hat"},
    {"id": "face", "label": "Faces", "icon": "face"},
    {"id": "shirt", "label": "Shirts", "icon": "shirt"},
    {"id": "pants", "label": "Pants", "icon": "pants"},
    {"id": "back", "label": "Back", "icon": "back"},
    {"id": "gear", "label": "Gear Skins", "icon": "gear"},
]

_cache: dict[str, dict] = {}
_cache_stamp = 0.0


def _row_to_item(row) -> dict:
    d = dict(row)
    d["render"] = db.json_field(d.get("render"), {})
    d["rarityColor"] = RARITY_COLORS.get(d.get("rarity"), "#9aa2ab")
    d["tags"] = [t for t in (d.get("tags") or "").split(",") if t]
    d["limited"] = bool(d.get("limited"))
    d["offSale"] = bool(d.get("off_sale"))
    return d


def _refresh():
    global _cache, _cache_stamp
    if _cache and time.time() - _cache_stamp < 15:
        return
    rows = db.query("SELECT * FROM catalog_items ORDER BY category, "
                    "sort_order, name")
    _cache = {r["id"]: _row_to_item(r) for r in rows}
    _cache_stamp = time.time()


def invalidate():
    global _cache_stamp
    _cache_stamp = 0.0


def get_item(item_id: str) -> dict | None:
    _refresh()
    return _cache.get(item_id)


def all_items() -> list[dict]:
    _refresh()
    return list(_cache.values())


def list_items(*, category: str | None = None, search: str = "",
               rarity: str | None = None, sort: str = "featured",
               max_price: int | None = None,
               offset: int = 0, limit: int = 60) -> dict:
    items = all_items()
    if category and category != "all":
        items = [i for i in items if i["category"] == category]
    if rarity and rarity != "all":
        items = [i for i in items if i["rarity"] == rarity]
    if max_price is not None:
        items = [i for i in items if i["price"] <= max_price]
    term = (search or "").strip().lower()
    if term:
        items = [i for i in items
                 if term in i["name"].lower()
                 or term in i["description"].lower()
                 or any(term in t for t in i["tags"])]
    keys = {
        "featured": lambda i: (i["sort_order"], i["name"]),
        "price_asc": lambda i: (i["price"], i["name"]),
        "price_desc": lambda i: (-i["price"], i["name"]),
        "rarity": lambda i: (-RARITY_ORDER.get(i["rarity"], 0), i["price"]),
        "name": lambda i: i["name"].lower(),
        "newest": lambda i: -i["created_at"],
    }
    items = sorted(items, key=keys.get(sort, keys["featured"]))
    total = len(items)
    return {"items": items[offset:offset + limit], "total": total,
            "offset": offset, "limit": limit}


def stock_remaining(item_id: str) -> int | None:
    item = get_item(item_id)
    if not item or item.get("stock") is None:
        return None
    sold = db.scalar("SELECT COUNT(*) FROM inventory WHERE item_id=?",
                     (item_id,), 0)
    return max(0, int(item["stock"]) - int(sold))
