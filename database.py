import sqlite3, os
from flask import g

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "avito.db")

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            avatar TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            city TEXT DEFAULT '',
            accent_color TEXT DEFAULT '#00aeef',
            is_admin INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            created_at INTEGER,
            is_verified  INTEGER DEFAULT 0,
            verify_token TEXT    DEFAULT '',
            tfa_enabled  INTEGER DEFAULT 0,
            tfa_method   TEXT    DEFAULT '',
            totp_secret  TEXT    DEFAULT '',
            current_game    TEXT    DEFAULT '',
            game_updated_at INTEGER DEFAULT 0,
            tracker_token   TEXT    DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            price REAL,
            category TEXT,
            city TEXT,
            image TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS rate_limit (
            ip TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            hits INTEGER DEFAULT 1,
            window_start INTEGER NOT NULL,
            PRIMARY KEY (ip, endpoint)
        );
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ad_id INTEGER NOT NULL,
            created_at INTEGER,
            UNIQUE(user_id, ad_id)
        );
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            created_at INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS email_change_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            new_email TEXT NOT NULL,
            token TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER NOT NULL,
            to_user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            text TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messenger_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            msn_username TEXT NOT NULL UNIQUE,
            msn_number TEXT NOT NULL UNIQUE,
            avatar TEXT DEFAULT '',
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS msn_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            group_id INTEGER,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS msn_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS msn_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            profile_id INTEGER NOT NULL,
            joined_at INTEGER NOT NULL,
            UNIQUE(group_id, profile_id)
        );
        CREATE TABLE IF NOT EXISTS msn_group_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS msn_statuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS msn_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id TEXT NOT NULL UNIQUE,
            caller_id INTEGER NOT NULL,
            callee_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'ringing',
            created_at INTEGER NOT NULL,
            started_at INTEGER,
            ended_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS msn_call_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id TEXT NOT NULL,
            from_id INTEGER NOT NULL,
            to_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            payload TEXT DEFAULT '',
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tfa_email_codes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            code       TEXT NOT NULL,
            purpose    TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            used       INTEGER DEFAULT 0
        );
    """)

    # Миграции — идемпотентно добавляем колонки если их ещё нет
    migrations = [
        ("users", "bio",                          "TEXT DEFAULT ''"),
        ("users", "city",                         "TEXT DEFAULT ''"),
        ("users", "accent_color",                 "TEXT DEFAULT '#00aeef'"),
        ("users", "is_admin",                     "INTEGER DEFAULT 0"),
        ("users", "is_banned",                    "INTEGER DEFAULT 0"),
        ("users", "avatar",                       "TEXT DEFAULT ''"),
        ("users", "balance",                      "REAL DEFAULT 0"),
        ("users", "is_support",                   "INTEGER DEFAULT 0"),
        ("users", "position",                     "TEXT DEFAULT ''"),
        ("users", "last_wheel_spin",               "INTEGER DEFAULT 0"),
        ("users", "is_verified",                  "INTEGER DEFAULT 0"),
        ("users", "verify_token",                 "TEXT DEFAULT ''"),
        ("users", "tfa_enabled",                  "INTEGER DEFAULT 0"),
        ("users", "tfa_method",                   "TEXT DEFAULT ''"),
        ("users", "totp_secret",                  "TEXT DEFAULT ''"),
        ("users", "current_game",                 "TEXT DEFAULT ''"),
        ("users", "game_updated_at",              "INTEGER DEFAULT 0"),
        ("users", "tracker_token",                "TEXT DEFAULT ''"),
        ("support_tickets", "assigned_support_id","INTEGER DEFAULT NULL"),
        ("support_tickets", "status",             "TEXT DEFAULT 'open'"),
        ("support_tickets", "is_support_agent",   "INTEGER DEFAULT 0"),
    ]
    for table, col, col_def in migrations:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
        except Exception:
            pass

    db.commit()
