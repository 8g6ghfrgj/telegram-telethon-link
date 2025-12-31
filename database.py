import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, List, Optional

from config import DATABASE_PATH

# =====================================================
# Connection
# =====================================================

def get_connection():
    return sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )

# =====================================================
# Init Database
# =====================================================

def init_db():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

    conn = get_connection()
    cur = conn.cursor()

    # ----------------- Sessions -----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT UNIQUE NOT NULL,
            phone_number TEXT,
            added_date TEXT,
            last_used TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)

    # ----------------- Links -----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            platform TEXT NOT NULL,
            link_type TEXT,
            source_account TEXT,
            chat_id TEXT,
            message_date TEXT,
            is_verified INTEGER DEFAULT 0,
            verification_result TEXT,
            metadata TEXT,
            collected_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ----------------- Collection Stats -----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS collection_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            start_time TEXT,
            end_time TEXT,
            status TEXT,
            total_collected INTEGER DEFAULT 0,
            telegram_collected INTEGER DEFAULT 0,
            whatsapp_collected INTEGER DEFAULT 0,
            verified_count INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

# =====================================================
# Sessions
# =====================================================

def add_session(session_string: str, phone_number: str = None) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT OR IGNORE INTO sessions
            (session_string, phone_number, added_date, is_active)
            VALUES (?, ?, ?, 1)
        """, (session_string, phone_number, datetime.now().isoformat()))
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

# =====================================================
# Links
# =====================================================

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
    source_account: str = None,
    chat_id: str = None,
    message_date=None,
    is_verified: bool = True,
    verification_result: str = "valid",
    metadata: Dict = None
) -> bool:
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT OR IGNORE INTO links
            (url, platform, link_type, source_account, chat_id,
             message_date, is_verified, verification_result, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            url,
            platform,
            link_type,
            source_account,
            chat_id,
            message_date.isoformat() if message_date else None,
            1 if is_verified else 0,
            verification_result,
            json.dumps(metadata) if metadata else None
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

    query = "SELECT * FROM links WHERE platform = ?"
    params = [platform]

    if link_type:
        query += " AND link_type = ?"
        params.append(link_type)

    query += " ORDER BY collected_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# =====================================================
# Collection Stats (المهمات الناقصة التي سببت الخطأ)
# =====================================================

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
    status: str = None,
    telegram_count: int = 0,
    whatsapp_count: int = 0,
    verified_count: int = 0
):
    conn = get_connection()
    cur = conn.cursor()

    updates = []
    params = []

    if status:
        updates.append("status = ?")
        params.append(status)
        updates.append("end_time = ?")
        params.append(datetime.now().isoformat())

    if telegram_count:
        updates.append("telegram_collected = telegram_collected + ?")
        params.append(telegram_count)

    if whatsapp_count:
        updates.append("whatsapp_collected = whatsapp_collected + ?")
        params.append(whatsapp_count)

    if verified_count:
        updates.append("verified_count = verified_count + ?")
        params.append(verified_count)

    if updates:
        updates.append("total_collected = total_collected + ?")
        params.append(telegram_count + whatsapp_count)
        params.append(collection_id)

        query = f"""
            UPDATE collection_stats
            SET {', '.join(updates)}
            WHERE id = ?
        """
        cur.execute(query, params)
        conn.commit()

    conn.close()

# =====================================================
# Stats
# =====================================================

def get_link_stats() -> Dict:
    conn = get_connection()
    cur = conn.cursor()

    stats = {}

    cur.execute("SELECT platform, COUNT(*) FROM links GROUP BY platform")
    stats["by_platform"] = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("""
        SELECT link_type, COUNT(*)
        FROM links
        WHERE platform = 'telegram'
        GROUP BY link_type
    """)
    stats["telegram_by_type"] = {r[0]: r[1] for r in cur.fetchall()}

    conn.close()
    return stats
