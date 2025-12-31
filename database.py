import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Optional

DATABASE_PATH = "data/database.db"


# ======================
# Connection
# ======================

def get_connection():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    return sqlite3.connect(DATABASE_PATH, check_same_thread=False)


# ======================
# Init DB
# ======================

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # Sessions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT UNIQUE NOT NULL,
            phone TEXT,
            is_active INTEGER DEFAULT 1,
            added_at TEXT,
            last_used TEXT
        )
    """)

    # Links
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            platform TEXT NOT NULL,
            link_type TEXT,
            source TEXT,
            chat_id TEXT,
            message_date TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


# ======================
# Session Management
# ======================

def add_session(session_string: str, phone: str = None) -> bool:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO sessions
            (session_string, phone, is_active, added_at)
            VALUES (?, ?, 1, ?)
        """, (session_string, phone, datetime.utcnow().isoformat()))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_sessions(active_only: bool = False) -> List[Dict]:
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


def update_session_status(session_id: int, is_active: bool) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE sessions
        SET is_active = ?, last_used = ?
        WHERE id = ?
    """, (1 if is_active else 0, datetime.utcnow().isoformat(), session_id))
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    return success


def delete_session(session_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    return success


# ======================
# Link Management
# ======================

def link_exists(url: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM links WHERE url = ?", (url,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def save_link(
    url: str,
    platform: str,
    link_type: str,
    source: str = None,
    chat_id: str = None,
    message_date=None
) -> bool:
    if not url or not platform:
        return False

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO links
            (url, platform, link_type, source, chat_id, message_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            url,
            platform,
            link_type,
            source,
            chat_id,
            message_date.isoformat() if message_date else None,
            datetime.utcnow().isoformat()
        ))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_links_by_type(
    platform: str,
    link_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if link_type:
        cur.execute("""
            SELECT * FROM links
            WHERE platform = ? AND link_type = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (platform, link_type, limit, offset))
    else:
        cur.execute("""
            SELECT * FROM links
            WHERE platform = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (platform, limit, offset))

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def export_links_by_type(platform: str, link_type: Optional[str] = None) -> Optional[str]:
    links = get_links_by_type(platform, link_type, limit=100000, offset=0)
    if not links:
        return None

    os.makedirs("exports", exist_ok=True)
    name = f"{platform}_{link_type or 'all'}.txt"
    path = os.path.join("exports", name)

    with open(path, "w", encoding="utf-8") as f:
        for link in links:
            f.write(link["url"] + "\n")

    return path
