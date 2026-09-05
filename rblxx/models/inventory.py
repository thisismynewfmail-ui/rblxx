"""Per-user inventory: ownership, purchases and grants."""
from __future__ import annotations

import time

from ..data import database as db
from . import catalog, economy


class PurchaseError(Exception):
    pass


def owns(user_id: int, item_id: str) -> bool:
    return db.query_one(
        "SELECT 1 FROM inventory WHERE user_id=? AND item_id=?",
        (user_id, item_id)) is not None


def owned_ids(user_id: int) -> set[str]:
    return {r["item_id"] for r in
            db.query("SELECT item_id FROM inventory WHERE user_id=?",
                     (user_id,))}


def item_count(user_id: int) -> int:
    return int(db.scalar("SELECT COUNT(*) FROM inventory WHERE user_id=?",
                         (user_id,), 0))


def list_inventory(user_id: int, category: str | None = None) -> list[dict]:
    rows = db.query(
        "SELECT item_id, acquired_at, serial, source FROM inventory "
        "WHERE user_id=? ORDER BY acquired_at DESC", (user_id,))
    out = []
    for r in rows:
        item = catalog.get_item(r["item_id"])
        if item is None:
            continue
        if category and category != "all" and item["category"] != category:
            continue
        entry = dict(item)
        entry["acquiredAt"] = r["acquired_at"]
        entry["serial"] = r["serial"]
        entry["source"] = r["source"]
        out.append(entry)
    return out


def grant(user_id: int, item_id: str, source: str = "grant") -> bool:
    item = catalog.get_item(item_id)
    if item is None or owns(user_id, item_id):
        return False
    serial = None
    if item.get("stock") is not None:
        serial = int(db.scalar("SELECT COUNT(*) FROM inventory WHERE item_id=?",
                               (item_id,), 0)) + 1
    db.execute(
        "INSERT OR IGNORE INTO inventory(user_id,item_id,acquired_at,serial,"
        "source) VALUES(?,?,?,?,?)",
        (user_id, item_id, time.time(), serial, source))
    return True


def grant_starter_items(user_id: int):
    from ..data.catalog_seed import STARTER_ITEMS
    for item_id in STARTER_ITEMS:
        grant(user_id, item_id, source="starter")


def purchase(user_id: int, item_id: str) -> dict:
    item = catalog.get_item(item_id)
    if item is None:
        raise PurchaseError("That item does not exist.")
    if item["offSale"]:
        raise PurchaseError("That item is off sale.")
    if owns(user_id, item_id):
        raise PurchaseError("You already own this item.")
    remaining = catalog.stock_remaining(item_id)
    if remaining is not None and remaining <= 0:
        raise PurchaseError("Sold out — this item is limited.")
    price = int(item["price"])
    with db.transaction():
        balance = economy.balance(user_id)
        if balance < price:
            raise PurchaseError(
                f"You need {price - balance:,} more Bux for that.")
        serial = None
        if item.get("stock") is not None:
            sold = int(db.scalar(
                "SELECT COUNT(*) FROM inventory WHERE item_id=?",
                (item_id,), 0))
            if sold >= int(item["stock"]):
                raise PurchaseError("Sold out — this item is limited.")
            serial = sold + 1
        db.execute(
            "INSERT INTO inventory(user_id,item_id,acquired_at,serial,source)"
            " VALUES(?,?,?,?,?)",
            (user_id, item_id, time.time(), serial, "purchase"))
        new_balance = economy.adjust(user_id, -price, "purchase",
                                     ref=item_id, in_transaction=True)
    from ..social import badges
    count = item_count(user_id)
    if count >= 10:
        badges.award(user_id, "collector")
    if item["rarity"] == "legendary":
        badges.award(user_id, "legendary_owner")
    return {"item": item, "balance": new_balance, "serial": serial}
