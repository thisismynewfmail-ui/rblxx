-- ==========================================================================
-- RBLXX core schema.  SQLite in WAL mode so the web edge and every game
-- node process can read/write concurrently.
-- ==========================================================================

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL,
    username_lower  TEXT    NOT NULL UNIQUE,
    password_hash   TEXT    NOT NULL,
    created_at      REAL    NOT NULL,
    last_login      REAL,
    last_seen       REAL,
    bio             TEXT    NOT NULL DEFAULT '',
    status_text     TEXT    NOT NULL DEFAULT '',
    coins           INTEGER NOT NULL DEFAULT 0,
    membership      TEXT    NOT NULL DEFAULT 'standard',
    place_visits    INTEGER NOT NULL DEFAULT 0,
    is_admin        INTEGER NOT NULL DEFAULT 0,
    stipend_at      REAL    NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_seen ON users(last_seen DESC);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    ip          TEXT,
    user_agent  TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

-- --------------------------------------------------------------------------
-- Avatar / character
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS avatars (
    user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    head        TEXT NOT NULL DEFAULT '#f3d64e',
    torso       TEXT NOT NULL DEFAULT '#1c7bc4',
    left_arm    TEXT NOT NULL DEFAULT '#f3d64e',
    right_arm   TEXT NOT NULL DEFAULT '#f3d64e',
    left_leg    TEXT NOT NULL DEFAULT '#8bc34a',
    right_leg   TEXT NOT NULL DEFAULT '#8bc34a',
    equipped    TEXT NOT NULL DEFAULT '{}',     -- json: slot -> item_id
    body_scale  REAL NOT NULL DEFAULT 1.0,
    updated_at  REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS outfits (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    config      TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outfits_user ON outfits(user_id);

-- --------------------------------------------------------------------------
-- Central item catalog + per-user inventory
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS catalog_items (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL,      -- hat | face | shirt | pants | gear | package
    slot         TEXT NOT NULL,      -- hat | face | shirt | pants | gear | back
    rarity       TEXT NOT NULL DEFAULT 'common',
    price        INTEGER NOT NULL DEFAULT 0,
    creator      TEXT NOT NULL DEFAULT 'RBLXX',
    description  TEXT NOT NULL DEFAULT '',
    render       TEXT NOT NULL DEFAULT '{}',   -- json geometry/appearance spec
    tags         TEXT NOT NULL DEFAULT '',
    limited      INTEGER NOT NULL DEFAULT 0,
    stock        INTEGER,                       -- NULL = unlimited
    off_sale     INTEGER NOT NULL DEFAULT 0,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_catalog_cat ON catalog_items(category, sort_order);

CREATE TABLE IF NOT EXISTS inventory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id     TEXT NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
    acquired_at REAL NOT NULL,
    serial      INTEGER,
    source      TEXT NOT NULL DEFAULT 'purchase',
    UNIQUE(user_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory(user_id);

CREATE TABLE IF NOT EXISTS transactions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    delta      INTEGER NOT NULL,
    balance    INTEGER NOT NULL,
    reason     TEXT NOT NULL,
    ref        TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id, created_at DESC);

-- --------------------------------------------------------------------------
-- Worlds
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS worlds (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    tagline       TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    genre         TEXT NOT NULL DEFAULT 'Fighting',
    mode          TEXT NOT NULL DEFAULT 'tdm',
    max_players   INTEGER NOT NULL DEFAULT 16,
    creator       TEXT NOT NULL DEFAULT 'RBLXX Studios',
    visits        INTEGER NOT NULL DEFAULT 0,
    likes         INTEGER NOT NULL DEFAULT 0,
    dislikes      INTEGER NOT NULL DEFAULT 0,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS world_votes (
    world_id   TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    value      INTEGER NOT NULL,        -- 1 like, -1 dislike
    created_at REAL NOT NULL,
    PRIMARY KEY (world_id, user_id)
);

CREATE TABLE IF NOT EXISTS favorites (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    world_id   TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    PRIMARY KEY (user_id, world_id)
);

CREATE TABLE IF NOT EXISTS world_visits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    world_id   TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at   REAL,
    kills      INTEGER NOT NULL DEFAULT 0,
    deaths     INTEGER NOT NULL DEFAULT 0,
    score      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_visits_user ON world_visits(user_id, started_at DESC);

-- --------------------------------------------------------------------------
-- Social
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS friendships (
    low_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    high_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    PRIMARY KEY (low_id, high_id)
);
CREATE INDEX IF NOT EXISTS idx_friend_high ON friendships(high_id);

CREATE TABLE IF NOT EXISTS friend_requests (
    from_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    to_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    note       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (from_id, to_id)
);
CREATE INDEX IF NOT EXISTS idx_freq_to ON friend_requests(to_id);

CREATE TABLE IF NOT EXISTS follows (
    follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    followee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  REAL NOT NULL,
    PRIMARY KEY (follower_id, followee_id)
);
CREATE INDEX IF NOT EXISTS idx_follow_ee ON follows(followee_id);

CREATE TABLE IF NOT EXISTS blocks (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    PRIMARY KEY (user_id, blocked_id)
);

CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    world_id   TEXT,
    created_at REAL NOT NULL,
    edited_at  REAL,
    like_count INTEGER NOT NULL DEFAULT 0,
    reply_count INTEGER NOT NULL DEFAULT 0,
    pinned     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_time ON posts(created_at DESC);

CREATE TABLE IF NOT EXISTS post_likes (
    post_id    INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    PRIMARY KEY (post_id, user_id)
);

CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id, created_at);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    to_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject    TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL,
    created_at REAL NOT NULL,
    read_at    REAL
);
CREATE INDEX IF NOT EXISTS idx_msg_to ON messages(to_id, created_at DESC);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    payload    TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    read_at    REAL
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, created_at DESC);

-- --------------------------------------------------------------------------
-- Badges & stats
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS badges (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL,
    icon        TEXT NOT NULL DEFAULT 'star',
    color       TEXT NOT NULL DEFAULT '#ffb400',
    kind        TEXT NOT NULL DEFAULT 'player'   -- platform | player
);

CREATE TABLE IF NOT EXISTS user_badges (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    badge_id   TEXT NOT NULL REFERENCES badges(id) ON DELETE CASCADE,
    awarded_at REAL NOT NULL,
    PRIMARY KEY (user_id, badge_id)
);

CREATE TABLE IF NOT EXISTS player_stats (
    user_id      INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    kills        INTEGER NOT NULL DEFAULT 0,
    deaths       INTEGER NOT NULL DEFAULT 0,
    wins         INTEGER NOT NULL DEFAULT 0,
    rounds       INTEGER NOT NULL DEFAULT 0,
    playtime     REAL NOT NULL DEFAULT 0,
    best_streak  INTEGER NOT NULL DEFAULT 0,
    headshots    INTEGER NOT NULL DEFAULT 0,
    updated_at   REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
