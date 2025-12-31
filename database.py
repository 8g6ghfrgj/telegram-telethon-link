import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, List, Optional

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/database.db")

# ======================================================
# Connection
# ======================================================

def get_connection():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    return sqlite3.connect(DATABASE_PATH, check_same_thread=False)


# ======================================================
# Init DB
# ======================================================

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # sessions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT UNIQUE NOT NULL,
            phone_number TEXT,
            display_name TEXT,
            is_active INTEGER DEFAULT 1,
            added_date TEXT,
            last_used TEXT
        )
    """)

    # links
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            platform TEXT,
            link_type TEXT,
            source_account TEXT,
            chat_id TEXT,
            message_date TEXT,
            collected_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # collection stats
    cur.execute("""
        CREATE TABLE IF NOT EXISTS collection_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            start_time TEXT,
            end_time TEXT,
            status TEXT,
            telegram_collected INTEGER DEFAULT 0,
            whatsapp_collected INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


# ======================================================
# Sessions
# ======================================================

def add_session_to_db(session_string: str, account_info: Dict) -> bool:
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT OR IGNORE INTO sessions
            (session_string, phone_number, display_name, added_date, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (
            session_string,
            account_info.get("phone"),
            account_info.get("username") or account_info.get("first_name"),
            datetime.now().isoformat()
        ))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_sessions(active_only: bool = True) -> List[Dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if active_only:
        cur.execute("SELECT * FROM sessions WHERE is_active = 1")
    else:
        cur.execute("SELECT * FROM sessions")

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_active_sessions() -> List[Dict]:
    return get_sessions(active_only=True)


def update_session_status(session_id: int, is_active: bool):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE sessions
        SET is_active = ?, last_used = ?
        WHERE id = ?
    """, (1 if is_active else 0, datetime.now().isoformat(), session_id))
    conn.commit()
    conn.close()


def delete_session(session_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


# ======================================================
# Links
# ======================================================

def save_link(
    url: str,
    platform: str,
    link_type: str,
    source_account: str,
    chat_id: str,
    message_date
) -> bool:
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT OR IGNORE INTO links
            (url, platform, link_type, source_account, chat_id, message_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            url,
            platform,
            link_type,
            source_account,
            chat_id,
            message_date.isoformat() if message_date else None
        ))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_links_by_type(platform: str, link_type: Optional[str] = None) -> List[Dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if link_type:
        cur.execute(
            "SELECT * FROM links WHERE platform=? AND link_type=?",
            (platform, link_type)
        )
    else:
        cur.execute(
            "SELECT * FROM links WHERE platform=?",
            (platform,)
        )

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ======================================================
# Collection stats  (🔥 هذه هي الدوال التي كانت ناقصة)
# ======================================================

def start_collection_session(session_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO collection_stats
        (session_id, start_time, status)
        VALUES (?, ?, 'running')
    """, (session_id, datetime.now().isoformat()))

    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid


def update_collection_stats(
    collection_id: int,
    status: Optional[str] = None,
    telegram_count: int = 0,
    whatsapp_count: int = 0
):
    conn = get_connection()
    cur = conn.cursor()

    if status:
        cur.execute("""
            UPDATE collection_stats
            SET status=?, end_time=?
            WHERE id=?
        """, (status, datetime.now().isoformat(), collection_id))

    if telegram_count or whatsapp_count:
        cur.execute("""
            UPDATE collection_stats
            SET telegram_collected = telegram_collected + ?,
                whatsapp_collected = whatsapp_collected + ?
            WHERE id=?
        """, (telegram_count, whatsapp_count, collection_id))

    conn.commit()
    conn.close()
