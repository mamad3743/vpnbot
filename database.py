import os
import time
from typing import Optional

import aiosqlite

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    wallet_balance INTEGER NOT NULL DEFAULT 0,
    joined_at TEXT,
    is_banned INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    days INTEGER NOT NULL,
    gb INTEGER NOT NULL,
    price INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS discount_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    percent INTEGER NOT NULL,
    max_uses INTEGER NOT NULL DEFAULT 0,
    used_count INTEGER NOT NULL DEFAULT 0,
    expires_at INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_id INTEGER,
    plan_title TEXT,
    price_paid INTEGER NOT NULL,
    discount_code TEXT,
    panel_username TEXT,
    sub_link TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS trial_usage (
    user_id INTEGER PRIMARY KEY,
    used_at TEXT
);

CREATE TABLE IF NOT EXISTS wallet_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

_conn: Optional[aiosqlite.Connection] = None


async def init_db() -> None:
    global _conn
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    _conn = await aiosqlite.connect(DB_PATH)
    _conn.row_factory = aiosqlite.Row
    await _conn.executescript(SCHEMA)
    await _conn.commit()


def db() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("Database not initialized, call init_db() first")
    return _conn


# ---------------- users ----------------

async def ensure_user(user_id: int, username: Optional[str]) -> None:
    await db().execute(
        "INSERT INTO users (user_id, username, joined_at) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username",
        (user_id, username, str(int(time.time()))),
    )
    await db().commit()


async def get_user(user_id: int) -> Optional[aiosqlite.Row]:
    cur = await db().execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return await cur.fetchone()


async def get_wallet_balance(user_id: int) -> int:
    row = await get_user(user_id)
    return row["wallet_balance"] if row else 0


async def add_to_wallet(user_id: int, amount: int) -> None:
    await db().execute(
        "UPDATE users SET wallet_balance = wallet_balance + ? WHERE user_id = ?",
        (amount, user_id),
    )
    await db().commit()


async def deduct_wallet(user_id: int, amount: int) -> bool:
    balance = await get_wallet_balance(user_id)
    if balance < amount:
        return False
    await db().execute(
        "UPDATE users SET wallet_balance = wallet_balance - ? WHERE user_id = ?",
        (amount, user_id),
    )
    await db().commit()
    return True


async def all_user_ids() -> list[int]:
    cur = await db().execute("SELECT user_id FROM users WHERE is_banned = 0")
    rows = await cur.fetchall()
    return [r["user_id"] for r in rows]


async def count_users() -> int:
    cur = await db().execute("SELECT COUNT(*) AS c FROM users")
    row = await cur.fetchone()
    return row["c"]


# ---------------- plans ----------------

async def add_plan(title: str, days: int, gb: int, price: int) -> None:
    await db().execute(
        "INSERT INTO plans (title, days, gb, price) VALUES (?, ?, ?, ?)",
        (title, days, gb, price),
    )
    await db().commit()


async def list_plans(active_only: bool = True) -> list[aiosqlite.Row]:
    q = "SELECT * FROM plans"
    if active_only:
        q += " WHERE is_active = 1"
    q += " ORDER BY price ASC"
    cur = await db().execute(q)
    return await cur.fetchall()


async def get_plan(plan_id: int) -> Optional[aiosqlite.Row]:
    cur = await db().execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
    return await cur.fetchone()


async def delete_plan(plan_id: int) -> None:
    await db().execute("UPDATE plans SET is_active = 0 WHERE id = ?", (plan_id,))
    await db().commit()


# ---------------- discount codes ----------------

async def add_discount_code(
    code: str, percent: int, max_uses: int, expires_at: Optional[int]
) -> None:
    await db().execute(
        "INSERT INTO discount_codes (code, percent, max_uses, expires_at) "
        "VALUES (?, ?, ?, ?)",
        (code.upper(), percent, max_uses, expires_at),
    )
    await db().commit()


async def get_discount_code(code: str) -> Optional[aiosqlite.Row]:
    cur = await db().execute(
        "SELECT * FROM discount_codes WHERE code = ? AND is_active = 1",
        (code.strip().upper(),),
    )
    row = await cur.fetchone()
    if row and row["expires_at"] and row["expires_at"] < int(time.time()):
        return None
    return row


async def use_discount_code(code: str) -> None:
    await db().execute(
        "UPDATE discount_codes SET used_count = used_count + 1 WHERE code = ?",
        (code.upper(),),
    )
    await db().commit()


async def list_discount_codes() -> list[aiosqlite.Row]:
    cur = await db().execute("SELECT * FROM discount_codes ORDER BY id DESC")
    return await cur.fetchall()


# ---------------- orders ----------------

async def create_order(
    user_id: int,
    plan_id: Optional[int],
    plan_title: str,
    price_paid: int,
    discount_code: Optional[str],
    panel_username: str,
    sub_link: str,
) -> None:
    await db().execute(
        "INSERT INTO orders (user_id, plan_id, plan_title, price_paid, discount_code, "
        "panel_username, sub_link, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            plan_id,
            plan_title,
            price_paid,
            discount_code,
            panel_username,
            sub_link,
            str(int(time.time())),
        ),
    )
    await db().commit()


async def count_orders() -> int:
    cur = await db().execute("SELECT COUNT(*) AS c FROM orders")
    row = await cur.fetchone()
    return row["c"]


async def total_revenue() -> int:
    cur = await db().execute("SELECT COALESCE(SUM(price_paid), 0) AS s FROM orders")
    row = await cur.fetchone()
    return row["s"]


async def user_orders(user_id: int) -> list[aiosqlite.Row]:
    cur = await db().execute(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (user_id,)
    )
    return await cur.fetchall()


# ---------------- trial ----------------

async def has_used_trial(user_id: int) -> bool:
    cur = await db().execute("SELECT 1 FROM trial_usage WHERE user_id = ?", (user_id,))
    return await cur.fetchone() is not None


async def mark_trial_used(user_id: int) -> None:
    await db().execute(
        "INSERT OR IGNORE INTO trial_usage (user_id, used_at) VALUES (?, ?)",
        (user_id, str(int(time.time()))),
    )
    await db().commit()


# ---------------- wallet charge requests ----------------

async def create_wallet_request(user_id: int, amount: int, note: str) -> int:
    cur = await db().execute(
        "INSERT INTO wallet_requests (user_id, amount, note, created_at) VALUES (?, ?, ?, ?)",
        (user_id, amount, note, str(int(time.time()))),
    )
    await db().commit()
    return cur.lastrowid


async def get_wallet_request(request_id: int) -> Optional[aiosqlite.Row]:
    cur = await db().execute("SELECT * FROM wallet_requests WHERE id = ?", (request_id,))
    return await cur.fetchone()


async def set_wallet_request_status(request_id: int, status: str) -> None:
    await db().execute(
        "UPDATE wallet_requests SET status = ? WHERE id = ?", (status, request_id)
    )
    await db().commit()


# ---------------- key/value settings (everything configurable from the bot) ----------------

async def get_setting_raw(key: str) -> Optional[str]:
    cur = await db().execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = await cur.fetchone()
    return row["value"] if row else None


async def set_setting_raw(key: str, value: str) -> None:
    await db().execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    await db().commit()


async def get_all_settings_raw() -> dict[str, str]:
    cur = await db().execute("SELECT key, value FROM settings")
    rows = await cur.fetchall()
    return {r["key"]: r["value"] for r in rows}
