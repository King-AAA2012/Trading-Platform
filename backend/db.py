"""Storage for accounts, sessions, private per-user app state and payments.

SQLite (data/app.db) by default. Set DATABASE_URL to a Postgres URL (for example a free Neon or Supabase database) to keep
accounts on hosts whose disk is wiped on every restart, such as Render's free plan."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time

from . import config
from .data import DATA_DIR

PATH = DATA_DIR / "app.db"
PG = config.DATABASE_URL.startswith(("postgres://", "postgresql://"))
_lock = threading.RLock()
SCHEMA = """
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
"""

if PG:
    import psycopg
    from psycopg.rows import dict_row

    _pg: list = [None]

    def _conn():
        if _pg[0] is None or _pg[0].closed:
            _pg[0] = psycopg.connect(config.DATABASE_URL, autocommit=True, row_factory=dict_row)
        return _pg[0]

    def _run(sql: str, args: tuple, fetch: bool):
        sql = sql.replace("?", "%s")
        returning = bool(re.match(r"\s*INSERT INTO (users|payments)\b", sql, re.I))
        if returning:
            sql += " RETURNING id"
        for attempt in (0, 1):
            try:
                with _lock:
                    cur = _conn().execute(sql, args)
                    if returning:
                        return cur.fetchone()["id"]
                    return cur.fetchall() if fetch and cur.description else []
            except psycopg.OperationalError:          # free databases drop idle connections: reconnect once
                _pg[0] = None
                if attempt:
                    raise

    with _lock:
        _conn().execute(SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY").replace("INTEGER", "BIGINT"))
else:
    _sq = sqlite3.connect(PATH, check_same_thread=False, isolation_level=None)
    _sq.row_factory = sqlite3.Row
    _sq.execute("PRAGMA journal_mode=WAL")
    _sq.execute("PRAGMA foreign_keys=ON")
    _sq.executescript(SCHEMA)

    def _run(sql: str, args: tuple, fetch: bool):
        with _lock:
            cur = _sq.execute(sql, args)
            return [dict(r) for r in cur.fetchall()] if fetch else cur.lastrowid


def q(sql: str, args: tuple = (), one: bool = False):
    rows = [dict(r) for r in _run(sql, args, True)]
    return (rows[0] if rows else None) if one else rows


def execute(sql: str, args: tuple = ()) -> int:
    return _run(sql, args, False)


def get_state(user_id: int) -> dict | None:
    r = q("SELECT json FROM user_state WHERE user_id=?", (user_id,), one=True)
    return json.loads(r["json"]) if r else None


def put_state(user_id: int, st: dict) -> None:
    execute("INSERT INTO user_state(user_id, json, updated) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET json=excluded.json, updated=excluded.updated",
            (user_id, json.dumps(st), int(time.time())))
