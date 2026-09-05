"""Idempotent seeding of catalog items, worlds, badges and demo accounts."""
from __future__ import annotations

import json
import random
import time

from . import database as db
from .catalog_seed import ALL_ITEMS

SEED_VERSION = "4"

DEMO_USERS = [
    ("Builderman", "brickmaster", "Keeping the baseplate tidy since day one.",
     {"head": "#f3d64e", "torso": "#3a5a86", "left_arm": "#f3d64e",
      "right_arm": "#f3d64e", "left_leg": "#4a4a4c", "right_leg": "#4a4a4c"},
     ["hat_classic_cap", "face_smile", "shirt_hivis", "pants_jeans"]),
    ("Telamon", "oldschool", "Ask me about the Crossroads bridge.",
     {"head": "#f3d64e", "torso": "#1b1c20", "left_arm": "#f3d64e",
      "right_arm": "#f3d64e", "left_leg": "#1b1c20", "right_leg": "#1b1c20"},
     ["hat_top_hat", "face_shades", "shirt_tuxedo", "pants_tux"]),
    ("StudSlinger", "gravitycoil", "Rocket jumping is a lifestyle.",
     {"head": "#f7c6a3", "torso": "#c0392b", "left_arm": "#f7c6a3",
      "right_arm": "#f7c6a3", "left_leg": "#2c3e50", "right_leg": "#2c3e50"},
     ["hat_bandana", "face_cheeky", "shirt_red_team", "pants_camo",
      "gear_skin_paint"]),
    ("NoobKing2007", "hunter2x", "yes i am wearing the cone. no i will not "
     "explain.", {"head": "#f3d64e", "torso": "#2f7fd6",
                  "left_arm": "#f3d64e", "right_arm": "#f3d64e",
                  "left_leg": "#8bc34a", "right_leg": "#8bc34a"},
     ["hat_party_cone", "face_smile", "shirt_blue_team", "pants_jeans"]),
    ("VoidWalker", "skyhaven", "See you on the high island.",
     {"head": "#bfe6cf", "torso": "#8a6bd8", "left_arm": "#bfe6cf",
      "right_arm": "#bfe6cf", "left_leg": "#4a3f6b", "right_leg": "#4a3f6b"},
     ["hat_halo", "face_visor", "shirt_astro", "pants_space", "back_wings",
      "gear_skin_neon"]),
    ("CrateGoblin", "mysterybox", "The box gave me a mender. Again.",
     {"head": "#d9e34a", "torso": "#d9e34a", "left_arm": "#d9e34a",
      "right_arm": "#d9e34a", "left_leg": "#5b6069", "right_leg": "#5b6069"},
     ["hat_space_helmet", "face_robot", "shirt_hazmat", "pants_hazmat",
      "back_pack"]),
    ("PineRidge", "antlers22", "Building a cabin, one brick at a time.",
     {"head": "#f7c6a3", "torso": "#8d2f2f", "left_arm": "#f7c6a3",
      "right_arm": "#f7c6a3", "left_leg": "#4b5b39", "right_leg": "#4b5b39"},
     ["hat_antlers", "face_chill", "shirt_flannel", "pants_cargo"]),
    ("BuxBaron", "goldplate", "Every hat has a price. I paid all of them.",
     {"head": "#f3d64e", "torso": "#111418", "left_arm": "#f3d64e",
      "right_arm": "#f3d64e", "left_leg": "#f2c53d", "right_leg": "#f2c53d"},
     ["hat_crown", "face_epic", "shirt_bux", "pants_neon", "back_cape",
      "gear_skin_gold"]),
]

DEMO_POSTS = [
    ("Builderman", "Server maintenance is done — all five worlds are back "
     "online. Go break something."),
    ("Telamon", "Reminder that the Crossroads tunnel connects to the ruins. "
     "Nobody uses it. Everybody should."),
    ("StudSlinger", "Rocket jumped from the red fort straight onto the "
     "central tower. Clip of the year."),
    ("VoidWalker", "Sky Haven tip: hold the launch pad on the HIGH island. "
     "The beacon always comes back to it."),
    ("CrateGoblin", "Wave 14 in the Outbreak Facility. Three menders. We do "
     "not talk about wave 15."),
    ("NoobKing2007", "who keeps stealing the speed coil"),
    ("PineRidge", "Fort Wars causeway is the single best objective in this "
     "whole platform. Fight me."),
    ("BuxBaron", "Crown of Bux serial #1. Yes I will be insufferable about "
     "it."),
]


def ensure_seed_data():
    seed_items()
    seed_worlds()
    seed_badges()
    if db.get_meta("demo_seed") != SEED_VERSION:
        seed_demo_users()
        db.set_meta("demo_seed", SEED_VERSION)


def seed_items():
    now = time.time()
    rows = []
    for item in ALL_ITEMS:
        rows.append((
            item["id"], item["name"], item["category"], item["slot"],
            item.get("rarity", "common"), int(item.get("price", 0)),
            item.get("creator", "RBLXX"), item.get("description", ""),
            json.dumps(item.get("render", {})), item.get("tags", ""),
            int(item.get("limited", 0)), item.get("stock"),
            int(item.get("off_sale", 0)), int(item.get("sort_order", 0)), now))
    db.executemany(
        "INSERT INTO catalog_items(id,name,category,slot,rarity,price,creator,"
        "description,render,tags,limited,stock,off_sale,sort_order,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
        "category=excluded.category, slot=excluded.slot, "
        "rarity=excluded.rarity, price=excluded.price, "
        "description=excluded.description, render=excluded.render, "
        "tags=excluded.tags, limited=excluded.limited, stock=excluded.stock, "
        "sort_order=excluded.sort_order", rows)
    from ..models import catalog
    catalog.invalidate()


def seed_worlds():
    from ..models import worlds
    worlds.sync_worlds()


def seed_badges():
    from ..social import badges
    badges.ensure_badges()


def seed_demo_users():
    """Create a small, believable community so the UI is never empty."""
    from ..models import avatar as avatar_model
    from ..models import inventory, users
    from ..security.sanitize import ValidationError
    from ..social import follows, friends, posts

    rng = random.Random(20061201)
    created: dict[str, int] = {}
    for name, password, bio, colors, items in DEMO_USERS:
        existing = users.get_user_by_name(name)
        if existing:
            created[name] = existing["id"]
            continue
        try:
            u = users.create_user(name, password, bio=bio)
        except ValidationError:
            continue
        uid = u["id"]
        created[name] = uid
        avatar_model.set_colors(uid, colors)
        for item_id in items:
            inventory.grant(uid, item_id, source="seed")
            try:
                avatar_model.equip(uid, item_id)
            except ValueError:
                pass
        db.execute("UPDATE users SET coins=?, created_at=?, last_seen=? "
                   "WHERE id=?",
                   (rng.randint(800, 24000),
                    time.time() - rng.randint(30, 900) * 86400,
                    time.time() - rng.randint(0, 5) * 3600, uid))
        db.execute(
            "INSERT INTO player_stats(user_id,kills,deaths,wins,rounds,"
            "playtime,best_streak,headshots,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
            "kills=excluded.kills, deaths=excluded.deaths, "
            "wins=excluded.wins, rounds=excluded.rounds, "
            "playtime=excluded.playtime, best_streak=excluded.best_streak",
            (uid, rng.randint(40, 900), rng.randint(30, 700),
             rng.randint(2, 60), rng.randint(10, 220),
             rng.randint(3600, 260000), rng.randint(3, 22),
             rng.randint(5, 180), time.time()))

    ids = list(created.values())
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if rng.random() < 0.55:
                lo, hi = (a, b) if a < b else (b, a)
                db.execute("INSERT OR IGNORE INTO friendships(low_id,high_id,"
                           "created_at) VALUES(?,?,?)",
                           (lo, hi, time.time() - rng.randint(1, 200) * 86400))
            if rng.random() < 0.45:
                follows.follow(a, b)
            if rng.random() < 0.35:
                follows.follow(b, a)

    world_ids = [r["id"] for r in db.query("SELECT id FROM worlds")]
    for name, body in DEMO_POSTS:
        uid = created.get(name)
        if not uid:
            continue
        try:
            p = posts.create(uid, body,
                             rng.choice(world_ids) if rng.random() < 0.5
                             else None)
        except Exception:
            continue
        db.execute("UPDATE posts SET created_at=? WHERE id=?",
                   (time.time() - rng.randint(600, 400000), p["id"]))
        for liker in rng.sample(ids, k=min(len(ids), rng.randint(1, 5))):
            if liker != uid:
                posts.toggle_like(liker, p["id"])
        if rng.random() < 0.6:
            commenter = rng.choice(ids)
            if commenter != uid:
                posts.add_comment(commenter, p["id"],
                                  rng.choice([
                                      "this is the way",
                                      "no way you pulled that off",
                                      "adding this to my favourites",
                                      "see you in there tonight",
                                      "certified classic moment"]))

    # a plausible spread of world votes so the browser shows ratings
    for wid in world_ids:
        for uid in ids:
            if rng.random() < 0.8:
                db.execute(
                    "INSERT OR IGNORE INTO world_votes(world_id,user_id,value,"
                    "created_at) VALUES(?,?,?,?)",
                    (wid, uid, 1 if rng.random() < 0.86 else -1, time.time()))
        likes = int(db.scalar("SELECT COUNT(*) FROM world_votes WHERE "
                              "world_id=? AND value=1", (wid,), 0))
        dislikes = int(db.scalar("SELECT COUNT(*) FROM world_votes WHERE "
                                 "world_id=? AND value=-1", (wid,), 0))
        db.execute("UPDATE worlds SET likes=?, dislikes=?, visits=? WHERE id=?",
                   (likes + rng.randint(120, 900),
                    dislikes + rng.randint(8, 90),
                    rng.randint(12000, 480000), wid))
