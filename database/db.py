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

_DB: aiosqlite.Connection | None = None


async def get_connection() -> aiosqlite.Connection:
    global _DB
    if _DB is None:
        db_dir = os.path.dirname(config.DATABASE_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        _DB = await aiosqlite.connect(config.DATABASE_PATH)
        _DB.row_factory = aiosqlite.Row
    return _DB


async def close_db() -> None:
    global _DB
    if _DB:
        await _DB.close()
        _DB = None


async def init_db() -> None:
    db = await get_connection()
    await db.execute(_CREATE_USERS_TABLE)
    await db.execute(_CREATE_RATE_HISTORY_TABLE)
    try:
        await db.execute("ALTER TABLE users ADD COLUMN city TEXT NOT NULL DEFAULT 'gomel'")
    except aiosqlite.OperationalError:
        pass
    try:
        await db.execute("ALTER TABLE rate_history ADD COLUMN city TEXT NOT NULL DEFAULT 'gomel'")
    except aiosqlite.OperationalError:
        pass
    await db.commit()


async def add_user(user_id: int) -> None:
    db = await get_connection()
    await db.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (user_id,),
    )
    await db.commit()


async def set_threshold(user_id: int, threshold: float) -> None:
    db = await get_connection()
    await db.execute(
        "UPDATE users SET threshold = ? WHERE user_id = ?",
        (threshold, user_id),
    )
    await db.commit()


async def clear_threshold(user_id: int) -> None:
    db = await get_connection()
    await db.execute(
        "UPDATE users SET threshold = 0 WHERE user_id = ?",
        (user_id,),
    )
    await db.commit()


async def get_user(user_id: int) -> dict | None:
    db = await get_connection()
    cursor = await db.execute(
        "SELECT user_id, threshold, is_active, created_at FROM users WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_active_users() -> list[dict]:
    db = await get_connection()
    cursor = await db.execute(
        "SELECT user_id, threshold, is_active, created_at FROM users WHERE is_active = 1"
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def toggle_user_active(user_id: int, active: bool) -> None:
    db = await get_connection()
    await db.execute(
        "UPDATE users SET is_active = ? WHERE user_id = ?",
        (1 if active else 0, user_id),
    )
    await db.commit()


async def save_rate(bank: str, rate: float) -> None:
    db = await get_connection()
    await db.execute(
        "INSERT INTO rate_history (bank, rate) VALUES (?, ?)",
        (bank, rate),
    )
    await db.commit()


async def get_last_rate() -> dict | None:
    db = await get_connection()
    cursor = await db.execute(
        "SELECT bank, rate, checked_at FROM rate_history ORDER BY id DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_rate_history(limit: int = 10) -> list[dict]:
    db = await get_connection()
    cursor = await db.execute(
        "SELECT bank, rate, checked_at FROM rate_history ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def cleanup_rate_history(max_rows: int = 1000) -> None:
    db = await get_connection()
    await db.execute(
        "DELETE FROM rate_history WHERE id NOT IN "
        "(SELECT id FROM rate_history ORDER BY id DESC LIMIT ?)",
        (max_rows,),
    )
    await db.commit()