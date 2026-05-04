import os

import aiosqlite

import config

_CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    threshold REAL NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_RATE_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS rate_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank TEXT NOT NULL,
    rate REAL NOT NULL,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN city TEXT NOT NULL DEFAULT 'gomel'",
    "ALTER TABLE rate_history ADD COLUMN city TEXT NOT NULL DEFAULT 'gomel'",
]


async def get_connection() -> aiosqlite.Connection:
    db_dir = os.path.dirname(config.DATABASE_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    return await aiosqlite.connect(config.DATABASE_PATH)


async def init_db() -> None:
    db = await get_connection()
    try:
        await db.execute(_CREATE_USERS_TABLE)
        await db.execute(_CREATE_RATE_HISTORY_TABLE)
        await db.commit()

        for migration in _MIGRATIONS:
            try:
                await db.execute(migration)
            except aiosqlite.OperationalError:
                pass
        await db.commit()
    finally:
        await db.close()


async def add_user(user_id: int) -> None:
    db = await get_connection()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
            (user_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def set_threshold(user_id: int, threshold: float) -> None:
    db = await get_connection()
    try:
        await db.execute(
            "UPDATE users SET threshold = ? WHERE user_id = ?",
            (threshold, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def get_user(user_id: int) -> dict | None:
    db = await get_connection()
    try:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, threshold, is_active, created_at FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_active_users() -> list[dict]:
    db = await get_connection()
    try:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, threshold, is_active, created_at FROM users WHERE is_active = 1"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def toggle_user_active(user_id: int, active: bool) -> None:
    db = await get_connection()
    try:
        await db.execute(
            "UPDATE users SET is_active = ? WHERE user_id = ?",
            (1 if active else 0, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def save_rate(bank: str, rate: float) -> None:
    db = await get_connection()
    try:
        await db.execute(
            "INSERT INTO rate_history (bank, rate) VALUES (?, ?)",
            (bank, rate),
        )
        await db.commit()
    finally:
        await db.close()


async def get_last_rate() -> dict | None:
    db = await get_connection()
    try:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT bank, rate, checked_at FROM rate_history ORDER BY id DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_rate_history(limit: int = 10) -> list[dict]:
    db = await get_connection()
    try:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT bank, rate, checked_at FROM rate_history ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()