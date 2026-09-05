"""Achievement badges, in the spirit of the classic badge wall."""
from __future__ import annotations

import time

from ..data import database as db

CATALOG = [
    ("welcome", "Welcome", "Created an RBLXX account.", "star", "#3aa0ff",
     "platform"),
    ("friendship", "Friendship", "Made your first friend.", "heart",
     "#e0483c", "platform"),
    ("socialite", "Socialite", "Reached 10 friends.", "people", "#f2b13d",
     "platform"),
    ("first_post", "Broadcaster", "Published your first post.", "megaphone",
     "#7f5fbf", "platform"),
    ("collector", "Collector", "Owned 10 catalog items.", "box", "#4fbf6a",
     "platform"),
    ("legendary_owner", "Legendary", "Owned a legendary item.", "crown",
     "#f2c53d", "platform"),
    ("combat_initiation", "Combat Initiation", "Scored your first "
     "elimination.", "target", "#c0392b", "player"),
    ("warrior", "Warrior", "Scored 100 eliminations.", "sword", "#8e44ad",
     "player"),
    ("bricklayer", "Bricklayer", "Visited every world at least once.",
     "brick", "#e67e22", "player"),
    ("survivor", "Survivor", "Reached wave 10 in the Outbreak Facility.",
     "shield", "#4be08a", "player"),
    ("tide_rider", "Tide Rider", "Won a round of Lava Rise.", "flame",
     "#ff7a2a", "player"),
    ("flag_bearer", "Flag Bearer", "Captured a flag in Fort Wars.", "flag",
     "#2f7fd6", "player"),
    ("homestead", "Homestead", "Played for a total of one hour.", "home",
     "#8bc34a", "player"),
    ("veteran", "Veteran", "Played 50 rounds.", "medal", "#95a5a6", "player"),
]


def ensure_badges():
    for bid, name, desc, icon, color, kind in CATALOG:
        db.execute(
            "INSERT INTO badges(id,name,description,icon,color,kind) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "name=excluded.name, description=excluded.description, "
            "icon=excluded.icon, color=excluded.color, kind=excluded.kind",
            (bid, name, desc, icon, color, kind))


def award(user_id: int, badge_id: str) -> bool:
    if db.query_one("SELECT 1 FROM user_badges WHERE user_id=? AND badge_id=?",
                    (user_id, badge_id)):
        return False
    if not db.query_one("SELECT 1 FROM badges WHERE id=?", (badge_id,)):
        return False
    db.execute("INSERT OR IGNORE INTO user_badges(user_id,badge_id,awarded_at)"
               " VALUES(?,?,?)", (user_id, badge_id, time.time()))
    from . import notifications
    name = db.scalar("SELECT name FROM badges WHERE id=?", (badge_id,))
    notifications.push(user_id, "badge", {"badge": name, "id": badge_id})
    return True


def for_user(user_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query(
        "SELECT b.id, b.name, b.description, b.icon, b.color, b.kind, "
        "ub.awarded_at FROM user_badges ub JOIN badges b ON b.id = ub.badge_id "
        "WHERE ub.user_id=? ORDER BY ub.awarded_at", (user_id,)))


def all_badges() -> list[dict]:
    return db.rows_to_dicts(db.query("SELECT * FROM badges"))


def evaluate(user_id: int):
    """Re-check stat-driven badges (cheap; called after games)."""
    stats = db.query_one("SELECT * FROM player_stats WHERE user_id=?",
                         (user_id,))
    if not stats:
        return
    if stats["kills"] >= 1:
        award(user_id, "combat_initiation")
    if stats["kills"] >= 100:
        award(user_id, "warrior")
    if stats["playtime"] >= 3600:
        award(user_id, "homestead")
    if stats["rounds"] >= 50:
        award(user_id, "veteran")
    visited = int(db.scalar(
        "SELECT COUNT(DISTINCT world_id) FROM world_visits WHERE user_id=?",
        (user_id,), 0))
    total = int(db.scalar("SELECT COUNT(*) FROM worlds", (), 0))
    if total and visited >= total:
        award(user_id, "bricklayer")
