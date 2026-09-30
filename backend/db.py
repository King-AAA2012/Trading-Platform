"""SQLite storage for accounts, sessions, private per-user app state and payments (data/app.db)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time

from .data import DATA_DIR

PATH = DATA_DIR / "app.db"
_lock = threading.RLock()
_conn = sqlite3.connect(PATH, check_same_thread=False, isolation_level=None)
_conn.row_factory = sqlite3.Row
_conn.execute("PRAGMA journal_mode=WAL")
_conn.execute("PRAGMA foreign_keys=ON")
_conn.executescript("""
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, name TEXT, pw_hash TEXT NOT NULL,
  created INTEGER NOT NULL, trial_end INTEGER NOT NULL, paid_until INTEGER DEFAULT 0, plan TEXT,
  terms_version TEXT, terms_accepted INTEGER, disabled INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created INTEGER NOT NULL, expires INTEGER NOT NULL, ua TEXT);
CREATE TABLE IF NOT EXISTS user_state (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, json TEXT NOT NULL, updated INTEGER);
CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, order_id TEXT UNIQUE,
  payment_id TEXT, plan TEXT, amount INTEGER, currency TEXT, status TEXT, created INTEGER, paid_at INTEGER);
""")


def q(sql: str, args: tuple = (), one: bool = False):
    with _lock:
        cur = _conn.execute(sql, args)
        rows = cur.fetchall()
    return (dict(rows[0]) if rows else None) if one else [dict(r) for r in rows]


def execute(sql: str, args: tuple = ()) -> int:
    with _lock:
        cur = _conn.execute(sql, args)
        return cur.lastrowid


def get_state(user_id: int) -> dict | None:
    r = q("SELECT json FROM user_state WHERE user_id=?", (user_id,), one=True)
    return json.loads(r["json"]) if r else None


def put_state(user_id: int, st: dict) -> None:
    execute("INSERT INTO user_state(user_id, json, updated) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET json=excluded.json, updated=excluded.updated",
            (user_id, json.dumps(st), int(time.time())))
