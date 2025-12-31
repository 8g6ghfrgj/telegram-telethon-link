import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, List, Optional

from config import DATABASE_PATH, EXPORT_DIR


# ======================
# Connection
# ======================

def get_connection():
    return sqlite3.connect(DATABASE_PATH, check_same_thread=False)


# ======================
# Init Database
# ======================

def init_db():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

    conn = get_connection()
    cur = conn.cursor()

    # جلسات تيليجرام
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT UNIQUE NOT NULL,
            is_active INTEGER DEFAULT 1,
            added_date TEXT
        )
    """)

    # الروابط
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            platform TEXT NOT NULL,
            link_type TEXT,
            source_session INTEGER,
            chat_id TEXT,
            message_date TEXT,
            collected_date TEXT,
            metadata TEXT
        )
    """)

    # جلسات الجمع
    cur.execute("""
        CREATE TABLE IF NOT EXISTS collection_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            stopped_at TEXT,
            status TEXT,
            telegram_count INTEGER DEFAULT 0,
            whatsapp_count INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


# ======================
# Session Management
# ======================

def add_session(session_string: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT OR IGNORE INTO sessions (session_string, is_active, added_date)
            VALUES (?, 1, ?)
        """, (session_string, datetime.now().isoformat()))
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


def delete_session(session_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


# ======================
# Collection Session
# ======================

def start_collection_session() -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO collection_sessions (started_at, status)
        VALUES (?, 'running')
    """, (datetime.now().isoformat(),))
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid


def update_collection_stats(
    collection_id: int,
    telegram_inc: int = 0,
    whatsapp_inc: int = 0,
    status: Optional[str] = None
):
    conn = get_connection()
    cur = conn.cursor()

    fields = []
    params = []

    if telegram_inc:
        fields.append("telegram_count = telegram_count + ?")
        params.append(telegram_inc)

    if whatsapp_inc:
        fields.append("whatsapp_count = whatsapp_count + ?")
        params.append(whatsapp_inc)

    if status:
        fields.append("status = ?")
        params.append(status)
        if status == "stopped":
            fields.append("stopped_at = ?")
            params.append(datetime.now().isoformat())

    if not fields:
        return

    params.append(collection_id)

    cur.execute(f"""
        UPDATE collection_sessions
        SET {", ".join(fields)}
        WHERE id = ?
    """, params)

    conn.commit()
    conn.close()


# ======================
# Links
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
    source_session: int,
    chat_id: str,
    message_date: Optional[datetime],
    metadata: Dict = None
) -> bool:
    if link_exists(url):
        return False

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO links
        (url, platform, link_type, source_session, chat_id, message_date, collected_date, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        url,
        platform,
        link_type,
        source_session,
        chat_id,
        message_date.isoformat() if message_date else None,
        datetime.now().isoformat(),
        json.dumps(metadata) if metadata else None
    ))

    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def get_links(platform: str) -> List[str]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT url FROM links WHERE platform = ?", (platform,))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


# ======================
# Export
# ======================

def export_links(platform: str) -> Optional[str]:
    links = get_links(platform)
    if not links:
        return None

    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, f"{platform}_links.txt")

    with open(path, "w", encoding="utf-8") as f:
        for url in links:
            f.write(url + "\n")

    return path


# ======================
# Init
# ======================

if __name__ == "__main__":
    init_db()
    print("✅ Database ready")
