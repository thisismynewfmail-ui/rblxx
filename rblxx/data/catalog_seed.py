"""The central item catalog.

Every wearable in RBLXX is declared here once and inserted into the
``catalog_items`` table.  Adding an item later is a matter of appending a
dict — inventories reference items by id, so the catalog can grow freely.

`render` is a tiny declarative spec the WebGL avatar renderer understands:

    {"parts": [ {shape, attach, pos, size, color, rot, texture, shade} ... ],
     "face":  "<face-id>",                # face items only
     "paint": {"torso": "#hex", ...},     # clothing recolours
     "pattern": "<pattern-id>",           # procedural cloth texture
     "skin":  "<weapon-skin-id>"}         # gear items only

Attach points: head | torso | leftArm | rightArm | leftLeg | rightLeg | back
Shapes:        box | sphere | cylinder | cone | wedge | torus
Positions are in studs, relative to the centre of the attach part.
"""
from __future__ import annotations

# Reference part sizes (studs) — kept in sync with web/js/engine/avatar.js
PART_SIZES = {
    "head":     (1.30, 1.15, 1.30),
    "torso":    (2.00, 2.00, 1.00),
    "leftArm":  (1.00, 2.00, 1.00),
    "rightArm": (1.00, 2.00, 1.00),
    "leftLeg":  (1.00, 2.00, 1.00),
    "rightLeg": (1.00, 2.00, 1.00),
}

HEAD_TOP = PART_SIZES["head"][1] / 2      # 0.575


def _hat(id_, name, price, rarity, parts, desc, tags="", order=0, limited=0,
         stock=None):
    return dict(id=id_, name=name, category="hat", slot="hat", price=price,
                rarity=rarity, description=desc, tags=tags,
                render={"parts": parts}, sort_order=order, limited=limited,
                stock=stock)


def _face(id_, name, price, rarity, face_id, desc, order=0):
    return dict(id=id_, name=name, category="face", slot="face", price=price,
                rarity=rarity, description=desc, tags="face",
                render={"face": face_id}, sort_order=order)


def _shirt(id_, name, price, rarity, paint, pattern, desc, order=0, parts=None):
    return dict(id=id_, name=name, category="shirt", slot="shirt", price=price,
                rarity=rarity, description=desc, tags="clothing",
                render={"paint": paint, "pattern": pattern,
                        "parts": parts or []},
                sort_order=order)


def _pants(id_, name, price, rarity, paint, pattern, desc, order=0):
    return dict(id=id_, name=name, category="pants", slot="pants", price=price,
                rarity=rarity, description=desc, tags="clothing",
                render={"paint": paint, "pattern": pattern}, sort_order=order)


def _back(id_, name, price, rarity, parts, desc, order=0):
    return dict(id=id_, name=name, category="back", slot="back", price=price,
                rarity=rarity, description=desc, tags="accessory",
                render={"parts": parts}, sort_order=order)


def _gear(id_, name, price, rarity, skin, desc, order=0):
    return dict(id=id_, name=name, category="gear", slot="gear", price=price,
                rarity=rarity, description=desc, tags="gear",
                render={"skin": skin}, sort_order=order)


# ==========================================================================
# HATS
# ==========================================================================
HATS = [
    _hat("hat_classic_cap", "Classic Red Ball Cap", 250, "common", [
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP + 0.17, 0],
         "size": [1.42, 0.34, 1.42], "color": "#8f1d1d"},
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP + 0.06, -0.92],
         "size": [1.30, 0.12, 0.72], "color": "#3a3a3a"},
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP + 0.20, 0.72],
         "size": [0.34, 0.24, 0.03], "color": "#f5f5f5", "decal": "letter_r"},
    ], "The cap every builder starts with. Brim worn backwards, obviously.",
        "classic,retro", 1),

    _hat("hat_top_hat", "Midnight Top Hat", 900, "rare", [
        {"shape": "cylinder", "attach": "head", "pos": [0, HEAD_TOP + 0.06, 0],
         "size": [1.75, 0.12, 1.75], "color": "#141418"},
        {"shape": "cylinder", "attach": "head", "pos": [0, HEAD_TOP + 0.62, 0],
         "size": [1.15, 1.12, 1.15], "color": "#141418"},
        {"shape": "cylinder", "attach": "head", "pos": [0, HEAD_TOP + 0.20, 0],
         "size": [1.20, 0.18, 1.20], "color": "#6b1f2a"},
    ], "For the distinguished blockhead about town.", "formal", 2),

    _hat("hat_witch", "Witching Hour Hat", 750, "rare", [
        {"shape": "cylinder", "attach": "head", "pos": [0, HEAD_TOP + 0.05, 0],
         "size": [2.15, 0.10, 2.15], "color": "#4a3524"},
        {"shape": "cone", "attach": "head", "pos": [0, HEAD_TOP + 0.85, 0],
         "size": [1.30, 1.60, 1.30], "color": "#5d4630",
         "rot": [8, 0, 6]},
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP + 0.18, 0],
         "size": [1.24, 0.14, 1.24], "color": "#2b2018"},
    ], "Slightly singed. Smells faintly of cauldron.", "spooky", 3),

    _hat("hat_sombrero", "Fiesta Sombrero", 480, "uncommon", [
        {"shape": "cone", "attach": "head", "pos": [0, HEAD_TOP + 0.12, 0],
         "size": [2.60, 0.34, 2.60], "color": "#d8b166"},
        {"shape": "cone", "attach": "head", "pos": [0, HEAD_TOP + 0.52, 0],
         "size": [1.10, 0.72, 1.10], "color": "#c79a4e"},
        {"shape": "cylinder", "attach": "head", "pos": [0, HEAD_TOP + 0.26, 0],
         "size": [1.26, 0.12, 1.26], "color": "#a8452f"},
    ], "Wide enough to shade two blockheads.", "party", 4),

    _hat("hat_beanie", "Slouch Beanie", 180, "common", [
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP + 0.02, 0],
         "size": [1.40, 0.46, 1.40], "color": "#2f6f8f"},
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP + 0.30, 0],
         "size": [1.22, 0.30, 1.22], "color": "#3b86ab"},
        {"shape": "sphere", "attach": "head", "pos": [0, HEAD_TOP + 0.56, 0],
         "size": [0.42, 0.42, 0.42], "color": "#f0f0f0"},
    ], "Warm, woolly, and a little bit lopsided.", "winter", 5),

    _hat("hat_propeller", "Propeller Beanie", 340, "uncommon", [
        {"shape": "sphere", "attach": "head", "pos": [0, HEAD_TOP + 0.14, 0],
         "size": [1.36, 0.72, 1.36], "color": "#e0483c"},
        {"shape": "cylinder", "attach": "head", "pos": [0, HEAD_TOP + 0.44, 0],
         "size": [0.16, 0.34, 0.16], "color": "#c9c9c9"},
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP + 0.62, 0],
         "size": [1.60, 0.06, 0.20], "color": "#38a1e0", "spin": 8.0},
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP + 0.62, 0],
         "size": [0.20, 0.06, 1.60], "color": "#f2d43b", "spin": 8.0},
    ], "Does not actually enable flight. We checked.", "classic,animated", 6),

    _hat("hat_viking", "Ironhold Viking Helm", 1200, "epic", [
        {"shape": "sphere", "attach": "head", "pos": [0, HEAD_TOP + 0.05, 0],
         "size": [1.46, 0.96, 1.46], "color": "#8d949c"},
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP - 0.10, 0],
         "size": [1.52, 0.20, 1.52], "color": "#5f666e"},
        {"shape": "cone", "attach": "head", "pos": [-0.86, HEAD_TOP + 0.30, 0],
         "size": [0.34, 0.90, 0.34], "color": "#efe4cd", "rot": [0, 0, 62]},
        {"shape": "cone", "attach": "head", "pos": [0.86, HEAD_TOP + 0.30, 0],
         "size": [0.34, 0.90, 0.34], "color": "#efe4cd", "rot": [0, 0, -62]},
    ], "Forged in the Ironhold foundries beneath Fort Wars.", "combat", 7),

    _hat("hat_knight", "Knight of the Baseplate", 1500, "epic", [
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP - 0.28, 0],
         "size": [1.44, 1.10, 1.44], "color": "#9aa2ab"},
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP + 0.20, 0],
         "size": [1.50, 0.42, 1.50], "color": "#b6bec7"},
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP - 0.34, 0.74],
         "size": [0.30, 0.10, 0.06], "color": "#22262b"},
        {"shape": "cone", "attach": "head", "pos": [0, HEAD_TOP + 0.66, 0],
         "size": [0.36, 0.55, 0.36], "color": "#c8433c"},
    ], "Visor down. Honour up.", "combat,medieval", 8),

    _hat("hat_bucket", "Angler's Bucket Hat", 220, "common", [
        {"shape": "cylinder", "attach": "head", "pos": [0, HEAD_TOP + 0.10, 0],
         "size": [1.98, 0.14, 1.98], "color": "#7e8a5c"},
        {"shape": "cylinder", "attach": "head", "pos": [0, HEAD_TOP + 0.32, 0],
         "size": [1.42, 0.46, 1.42], "color": "#8c9866"},
    ], "Catches fish, compliments and rain.", "casual", 9),

    _hat("hat_party_cone", "Birthday Cone", 120, "common", [
        {"shape": "cone", "attach": "head", "pos": [0, HEAD_TOP + 0.62, 0],
         "size": [0.96, 1.28, 0.96], "color": "#f24b8b", "rot": [0, 0, 9]},
        {"shape": "sphere", "attach": "head", "pos": [0.20, HEAD_TOP + 1.28, 0],
         "size": [0.34, 0.34, 0.34], "color": "#ffe14f"},
    ], "Happy build-day to you.", "party", 10),

    _hat("hat_ice_cream", "Mint Chip Cone Head", 2400, "legendary", [
        {"shape": "sphere", "attach": "head", "pos": [0, HEAD_TOP + 0.28, 0],
         "size": [1.32, 1.00, 1.32], "color": "#bfe6cf"},
        {"shape": "cone", "attach": "head", "pos": [0, HEAD_TOP + 1.20, 0],
         "size": [1.05, 1.35, 1.05], "color": "#e0b866", "rot": [180, 0, 0]},
        {"shape": "cylinder", "attach": "head", "pos": [0, HEAD_TOP + 0.62, 0],
         "size": [1.18, 0.22, 1.18], "color": "#eac878"},
    ], "A dessert-based identity crisis. Melts nothing.", "meme,limited", 11,
        limited=1, stock=250),

    _hat("hat_halo", "Baseplate Halo", 3500, "legendary", [
        {"shape": "torus", "attach": "head", "pos": [0, HEAD_TOP + 0.72, 0],
         "size": [1.55, 0.14, 1.55], "color": "#ffe07a", "glow": 1},
    ], "Awarded to those who never once teamkilled. Allegedly.",
        "limited,prestige", 12, limited=1, stock=100),

    _hat("hat_antlers", "Pine Ridge Antlers", 640, "rare", [
        {"shape": "box", "attach": "head", "pos": [-0.42, HEAD_TOP + 0.42, 0],
         "size": [0.14, 0.85, 0.14], "color": "#6b4a2c", "rot": [0, 0, 18]},
        {"shape": "box", "attach": "head", "pos": [0.42, HEAD_TOP + 0.42, 0],
         "size": [0.14, 0.85, 0.14], "color": "#6b4a2c", "rot": [0, 0, -18]},
        {"shape": "box", "attach": "head", "pos": [-0.70, HEAD_TOP + 0.72, 0],
         "size": [0.44, 0.10, 0.10], "color": "#6b4a2c", "rot": [0, 0, 35]},
        {"shape": "box", "attach": "head", "pos": [0.70, HEAD_TOP + 0.72, 0],
         "size": [0.44, 0.10, 0.10], "color": "#6b4a2c", "rot": [0, 0, -35]},
    ], "Straight from the frozen pines of Sky Haven.", "winter,nature", 13),

    _hat("hat_headphones", "Studio Cans", 520, "uncommon", [
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP + 0.10, 0],
         "size": [1.46, 0.18, 0.34], "color": "#2c2f36"},
        {"shape": "box", "attach": "head", "pos": [-0.76, HEAD_TOP - 0.34, 0],
         "size": [0.22, 0.62, 0.62], "color": "#2c2f36"},
        {"shape": "box", "attach": "head", "pos": [0.76, HEAD_TOP - 0.34, 0],
         "size": [0.22, 0.62, 0.62], "color": "#2c2f36"},
        {"shape": "box", "attach": "head", "pos": [-0.88, HEAD_TOP - 0.34, 0],
         "size": [0.06, 0.28, 0.28], "color": "#3ba7ff", "glow": 1},
    ], "Noise-cancelling. Blocks out the kill feed.", "tech", 14),

    _hat("hat_crown", "Crown of Bux", 5000, "legendary", [
        {"shape": "cylinder", "attach": "head", "pos": [0, HEAD_TOP + 0.22, 0],
         "size": [1.36, 0.44, 1.36], "color": "#f2c53d"},
        {"shape": "cone", "attach": "head", "pos": [0, HEAD_TOP + 0.60, 0.56],
         "size": [0.26, 0.42, 0.26], "color": "#f2c53d"},
        {"shape": "cone", "attach": "head", "pos": [0.56, HEAD_TOP + 0.60, 0],
         "size": [0.26, 0.42, 0.26], "color": "#f2c53d"},
        {"shape": "cone", "attach": "head", "pos": [-0.56, HEAD_TOP + 0.60, 0],
         "size": [0.26, 0.42, 0.26], "color": "#f2c53d"},
        {"shape": "cone", "attach": "head", "pos": [0, HEAD_TOP + 0.60, -0.56],
         "size": [0.26, 0.42, 0.26], "color": "#f2c53d"},
        {"shape": "sphere", "attach": "head", "pos": [0, HEAD_TOP + 0.30, 0.66],
         "size": [0.24, 0.24, 0.24], "color": "#e0483c", "glow": 1},
    ], "Heavy is the head. Heavier is the wallet.", "prestige,limited", 15,
        limited=1, stock=50),

    _hat("hat_space_helmet", "Vacuum-Rated Dome", 1800, "epic", [
        {"shape": "sphere", "attach": "head", "pos": [0, 0.10, 0],
         "size": [1.85, 1.85, 1.85], "color": "#bfe4ff", "alpha": 0.42},
        {"shape": "cylinder", "attach": "head", "pos": [0, -0.62, 0],
         "size": [1.55, 0.26, 1.55], "color": "#d8dde3"},
        {"shape": "box", "attach": "head", "pos": [0, 0.30, 0.86],
         "size": [0.90, 0.10, 0.08], "color": "#f2c53d", "glow": 1},
    ], "Standard issue for the Outbreak Facility clean rooms.", "sci-fi", 16),

    _hat("hat_bandana", "Ranger Bandana", 260, "common", [
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP - 0.06, 0],
         "size": [1.40, 0.30, 1.40], "color": "#b23a2e"},
        {"shape": "box", "attach": "head", "pos": [0, HEAD_TOP - 0.16, -0.78],
         "size": [0.30, 0.22, 0.44], "color": "#93291f", "rot": [24, 0, 0]},
    ], "Keeps the sweat out during a lava climb.", "casual,combat", 17),

    _hat("hat_explorer", "Explorer's Fedora", 700, "rare", [
        {"shape": "cylinder", "attach": "head", "pos": [0, HEAD_TOP + 0.06, 0],
         "size": [2.05, 0.12, 2.05], "color": "#8a7f63"},
        {"shape": "cylinder", "attach": "head", "pos": [0, HEAD_TOP + 0.40, 0],
         "size": [1.30, 0.62, 1.30], "color": "#9a8e6f"},
        {"shape": "cylinder", "attach": "head", "pos": [0, HEAD_TOP + 0.18, 0],
         "size": [1.36, 0.16, 1.36], "color": "#4d4436"},
    ], "Has seen four ruins and one very angry zombie.", "adventure", 18),
]

# ==========================================================================
# FACES
# ==========================================================================
FACES = [
    _face("face_smile", "Classic Smile", 0, "common", "smile",
          "The face that launched a million baseplates.", 1),
    _face("face_cheeky", "Cheeky", 150, "common", "cheeky",
          "You are absolutely up to something.", 2),
    _face("face_shades", "Cool Shades", 400, "uncommon", "shades",
          "Deal-with-it energy, permanently equipped.", 3),
    _face("face_angry", "Furrowed", 300, "common", "angry",
          "For when the round is not going your way.", 4),
    _face("face_surprised", "Whoa!", 300, "common", "surprised",
          "Someone just rocket-jumped over your head.", 5),
    _face("face_chill", "Perfectly Calm", 350, "uncommon", "chill",
          "Lava? What lava?", 6),
    _face("face_robot", "Unit-77 Optics", 1100, "epic", "robot",
          "Scanning... target acquired... friendship acquired.", 7),
    _face("face_cat", "Whiskers", 800, "rare", "cat",
          "Meow-based combat superiority.", 8),
    _face("face_winky", "Winking", 250, "common", "winky",
          "Half a smile is twice as smug.", 9),
    _face("face_epic", "Epic Grin", 2000, "legendary", "epic",
          "Unlocked by legend. Worn by menaces.", 10),
    _face("face_dizzy", "Seeing Studs", 450, "uncommon", "dizzy",
          "That fall did not go well.", 11),
    _face("face_visor", "Neon Visor", 1400, "epic", "visor",
          "One glowing bar of pure attitude.", 12),
]

# ==========================================================================
# SHIRTS
# ==========================================================================
SHIRTS = [
    _shirt("shirt_red_team", "Red Team Jersey", 200, "common",
           {"torso": "#c0392b", "leftArm": "#c0392b", "rightArm": "#c0392b"},
           "jersey", "Bleed red at Crossroads.", 1),
    _shirt("shirt_blue_team", "Blue Team Jersey", 200, "common",
           {"torso": "#2471c9", "leftArm": "#2471c9", "rightArm": "#2471c9"},
           "jersey", "Bleed blue at Crossroads.", 2),
    _shirt("shirt_hoodie", "Everyday Hoodie", 350, "common",
           {"torso": "#4a5058", "leftArm": "#4a5058", "rightArm": "#4a5058"},
           "hoodie", "Comfortable enough to survive a 40-wave run.", 3,
           parts=[{"shape": "box", "attach": "torso",
                   "pos": [0, 0.96, -0.34], "size": [1.30, 0.44, 0.56],
                   "color": "#3f444b"}]),
    _shirt("shirt_tuxedo", "Formal Tuxedo", 900, "rare",
           {"torso": "#1b1c20", "leftArm": "#1b1c20", "rightArm": "#1b1c20"},
           "tuxedo", "Black tie, blocky shoulders.", 4),
    _shirt("shirt_hivis", "Hi-Vis Site Vest", 300, "common",
           {"torso": "#e8a317", "leftArm": "#d6d6d6", "rightArm": "#d6d6d6"},
           "hivis", "Safety first, respawns second.", 5),
    _shirt("shirt_labcoat", "Facility Lab Coat", 650, "uncommon",
           {"torso": "#eceff2", "leftArm": "#eceff2", "rightArm": "#eceff2"},
           "labcoat", "Clearance level: probably fine.", 6),
    _shirt("shirt_stripes", "Rugby Stripes", 280, "common",
           {"torso": "#f0f0f0", "leftArm": "#f0f0f0", "rightArm": "#f0f0f0"},
           "stripes", "Two-tone classic.", 7),
    _shirt("shirt_denim", "Denim Jacket", 520, "uncommon",
           {"torso": "#3f5b82", "leftArm": "#3f5b82", "rightArm": "#3f5b82"},
           "denim", "Distressed in all the right places.", 8),
    _shirt("shirt_astro", "Astro Pressure Suit", 1600, "epic",
           {"torso": "#e6e9ee", "leftArm": "#e6e9ee", "rightArm": "#e6e9ee"},
           "astro", "Rated for vacuum, lava and awkward silences.", 9,
           parts=[{"shape": "box", "attach": "torso", "pos": [0, 0.40, 0.54],
                   "size": [0.72, 0.42, 0.10], "color": "#2b3038"},
                  {"shape": "box", "attach": "torso", "pos": [-0.20, 0.40, 0.60],
                   "size": [0.16, 0.16, 0.04], "color": "#4be08a", "glow": 1}]),
    _shirt("shirt_bux", "Bux Logo Tee", 400, "uncommon",
           {"torso": "#111418", "leftArm": "#111418", "rightArm": "#111418"},
           "buxlogo", "Show everyone exactly how you spend your evenings.", 10),
    _shirt("shirt_flannel", "Lumber Flannel", 380, "common",
           {"torso": "#8d2f2f", "leftArm": "#8d2f2f", "rightArm": "#8d2f2f"},
           "plaid", "Chopped exactly zero trees.", 11),
    _shirt("shirt_hazmat", "Outbreak Hazmat", 1900, "epic",
           {"torso": "#d9e34a", "leftArm": "#d9e34a", "rightArm": "#d9e34a"},
           "hazmat", "Sealed, filtered, and slightly sweaty.", 12),
]

# ==========================================================================
# PANTS
# ==========================================================================
PANTS = [
    _pants("pants_jeans", "Blue Jeans", 180, "common",
           {"leftLeg": "#3a5a86", "rightLeg": "#3a5a86"}, "denim",
           "Goes with absolutely everything.", 1),
    _pants("pants_cargo", "Cargo Shorts", 220, "common",
           {"leftLeg": "#7c7a5f", "rightLeg": "#7c7a5f"}, "cargo",
           "Eleven pockets. Zero organisation.", 2),
    _pants("pants_track", "Track Pants", 260, "common",
           {"leftLeg": "#22262d", "rightLeg": "#22262d"}, "track",
           "White stripe adds 3 studs per second. (It does not.)", 3),
    _pants("pants_camo", "Woodland Camo", 480, "uncommon",
           {"leftLeg": "#4b5b39", "rightLeg": "#4b5b39"}, "camo",
           "Invisible, if the enemy is a bush.", 4),
    _pants("pants_tux", "Tuxedo Slacks", 700, "rare",
           {"leftLeg": "#1b1c20", "rightLeg": "#1b1c20"}, "tuxedo",
           "Crease sharp enough to deal damage.", 5),
    _pants("pants_ripped", "Ripped Jeans", 340, "common",
           {"leftLeg": "#5b7399", "rightLeg": "#5b7399"}, "ripped",
           "The lava did that. Honest.", 6),
    _pants("pants_space", "Astro Trousers", 1200, "epic",
           {"leftLeg": "#e6e9ee", "rightLeg": "#e6e9ee"}, "astro",
           "Matching set sold separately, as tradition demands.", 7),
    _pants("pants_neon", "Neon Runner Leggings", 900, "rare",
           {"leftLeg": "#12e0c8", "rightLeg": "#12e0c8"}, "neon",
           "Visible from three islands away.", 8),
    _pants("pants_hazmat", "Hazmat Legs", 1500, "epic",
           {"leftLeg": "#d9e34a", "rightLeg": "#d9e34a"}, "hazmat",
           "Boots included. Confidence not.", 9),
]

# ==========================================================================
# BACK ACCESSORIES
# ==========================================================================
BACKS = [
    _back("back_jetpack", "Surplus Jetpack", 1400, "epic", [
        {"shape": "box", "attach": "torso", "pos": [-0.34, 0.10, -0.72],
         "size": [0.46, 1.20, 0.46], "color": "#b8bcc4"},
        {"shape": "box", "attach": "torso", "pos": [0.34, 0.10, -0.72],
         "size": [0.46, 1.20, 0.46], "color": "#b8bcc4"},
        {"shape": "cone", "attach": "torso", "pos": [-0.34, -0.66, -0.72],
         "size": [0.36, 0.34, 0.36], "color": "#5a5f66", "rot": [180, 0, 0]},
        {"shape": "cone", "attach": "torso", "pos": [0.34, -0.66, -0.72],
         "size": [0.36, 0.34, 0.36], "color": "#5a5f66", "rot": [180, 0, 0]},
    ], "Fuel gauge permanently reads 'ask again later'.", 1),

    _back("back_wings", "Featherlight Wings", 2600, "legendary", [
        {"shape": "box", "attach": "torso", "pos": [-0.95, 0.34, -0.62],
         "size": [1.40, 1.00, 0.10], "color": "#f4f6fa", "rot": [0, 24, 26]},
        {"shape": "box", "attach": "torso", "pos": [0.95, 0.34, -0.62],
         "size": [1.40, 1.00, 0.10], "color": "#f4f6fa", "rot": [0, -24, -26]},
    ], "Non-functional but extremely flattering.", 2),

    _back("back_pack", "Field Backpack", 420, "common", [
        {"shape": "box", "attach": "torso", "pos": [0, 0.10, -0.76],
         "size": [1.30, 1.34, 0.52], "color": "#5c6b4a"},
        {"shape": "box", "attach": "torso", "pos": [0, -0.30, -1.04],
         "size": [1.00, 0.34, 0.10], "color": "#3f4a34"},
    ], "Holds snacks, ammo and unfounded optimism.", 3),

    _back("back_cape", "Champion's Cape", 1800, "epic", [
        {"shape": "box", "attach": "torso", "pos": [0, -0.20, -0.62],
         "size": [1.90, 2.40, 0.08], "color": "#8f1d3f", "rot": [7, 0, 0]},
        {"shape": "box", "attach": "torso", "pos": [0, 0.92, -0.58],
         "size": [2.05, 0.24, 0.14], "color": "#f2c53d"},
    ], "Flutters even when there is no wind. Especially then.", 4),

    _back("back_sword", "Sheathed Broadsword", 1100, "rare", [
        {"shape": "box", "attach": "torso", "pos": [0.10, 0.24, -0.70],
         "size": [0.30, 2.30, 0.14], "color": "#5b4630", "rot": [0, 0, 22]},
        {"shape": "box", "attach": "torso", "pos": [-0.36, 1.16, -0.70],
         "size": [0.20, 0.60, 0.12], "color": "#c9ced6", "rot": [0, 0, 22]},
        {"shape": "box", "attach": "torso", "pos": [-0.28, 0.92, -0.70],
         "size": [0.72, 0.14, 0.14], "color": "#f2c53d", "rot": [0, 0, 22]},
    ], "Purely decorative. Mostly.", 5),

    _back("back_shell", "Turtle Shell", 950, "rare", [
        {"shape": "sphere", "attach": "torso", "pos": [0, 0.05, -0.78],
         "size": [1.90, 1.70, 0.90], "color": "#4e7a3a"},
        {"shape": "sphere", "attach": "torso", "pos": [0, 0.05, -0.90],
         "size": [1.10, 1.00, 0.60], "color": "#79a659"},
    ], "Provides zero armour and infinite charm.", 6),
]

# ==========================================================================
# GEAR (weapon skins carried into the Game View)
# ==========================================================================
GEAR = [
    _gear("gear_skin_default", "Standard Issue", 0, "common", "default",
          "Factory finish. Reliable, unremarkable.", 1),
    _gear("gear_skin_gold", "Gilded Plating", 3200, "legendary", "gold",
          "Adds no accuracy. Adds all the swagger.", 2),
    _gear("gear_skin_neon", "Neon Circuit", 1600, "epic", "neon",
          "Glows in the dark of the Outbreak Facility.", 3),
    _gear("gear_skin_wood", "Woodgrain Classic", 700, "uncommon", "wood",
          "Hand-finished. Slightly splintery.", 4),
    _gear("gear_skin_paint", "Retro Paintball", 500, "uncommon", "paintball",
          "Bright, loud, and covered in old splatter.", 5),
    _gear("gear_skin_carbon", "Carbon Weave", 1200, "rare", "carbon",
          "Twelve percent lighter. Zero percent measurable.", 6),
    _gear("gear_skin_frost", "Glacier Frost", 1400, "epic", "frost",
          "Recovered from the Sky Haven cold vaults.", 7),
]

ALL_ITEMS = HATS + FACES + SHIRTS + PANTS + BACKS + GEAR

STARTER_ITEMS = ["face_smile", "hat_classic_cap", "shirt_blue_team",
                 "pants_jeans", "gear_skin_default"]
