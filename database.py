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
    return sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )


# ======================
# Init Database
# ======================

def init_db():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

    conn = get_connection()
    cur = conn.cursor()

    # ======================
    # Sessions
    # ======================
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT UNIQUE NOT NULL,
            phone_number TEXT,
            added_date TEXT,
            is_active INTEGER DEFAULT 1,
            last_used TEXT
        )
    """)

    # ======================
    # Links (No duplicates enforced)
    # ======================
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            normalized_key TEXT UNIQUE NOT NULL,
            platform TEXT NOT NULL,                 -- telegram / whatsapp
            link_type TEXT NOT NULL,                -- channel / public_group / private_group
            source_chat_id TEXT,
            source_session_id INTEGER,
            message_date TEXT,
            collected_date TEXT,
            metadata TEXT
        )
    """)

    # ======================
    # Indexes
    # ======================
    cur.execute("CREATE INDEX IF NOT EXISTS idx_links_platform ON links(platform)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_links_type ON links(link_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_links_date ON links(collected_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)")

    conn.commit()
    conn.close()


# ======================
# Sessions
# ======================

def add_session(session_string: str, phone_number: str = None) -> bool:
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT OR IGNORE INTO sessions
            (session_string, phone_number, added_date, is_active)
            VALUES (?, ?, ?, 1)
        """, (session_string, phone_number, datetime.utcnow().isoformat()))

        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_active_sessions() -> List[Dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM sessions
        WHERE is_active = 1
        ORDER BY added_date ASC
    """)

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ======================
# Duplicate Protection
# ======================

def link_exists(normalized_key: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT 1 FROM links WHERE normalized_key = ? LIMIT 1",
        (normalized_key,)
    )

    exists = cur.fetchone() is not None
    conn.close()
    return exists


# ======================
# Save Link
# ======================

def save_link(
    *,
    url: str,
    normalized_key: str,
    platform: str,
    link_type: str,
    source_chat_id: str,
    source_session_id: int,
    message_date: Optional[datetime],
    metadata: Optional[Dict] = None
) -> bool:
    if not url or not normalized_key:
        return False

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT OR IGNORE INTO links
            (
                url,
                normalized_key,
                platform,
                link_type,
                source_chat_id,
                source_session_id,
                message_date,
                collected_date,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            url,
            normalized_key,
            platform,
            link_type,
            source_chat_id,
            source_session_id,
            message_date.isoformat() if message_date else None,
            datetime.utcnow().isoformat(),
            json.dumps(metadata) if metadata else None
        ))

        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ======================
# Queries
# ======================

def get_links(
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


def get_stats() -> Dict:
    conn = get_connection()
    cur = conn.cursor()

    stats = {}

    cur.execute("""
        SELECT platform, COUNT(*)
        FROM links
        GROUP BY platform
    """)
    stats["by_platform"] = dict(cur.fetchall())

    cur.execute("""
        SELECT link_type, COUNT(*)
        FROM links
        WHERE platform = 'telegram'
        GROUP BY link_type
    """)
    stats["telegram_by_type"] = dict(cur.fetchall())

    conn.close()
    return stats


# ======================
# Export
# ======================

def export_links(platform: str, link_type: Optional[str] = None) -> Optional[str]:
    conn = get_connection()
    cur = conn.cursor()

    if link_type:
        cur.execute("""
            SELECT url FROM links
            WHERE platform = ? AND link_type = ?
            ORDER BY collected_date ASC
        """, (platform, link_type))
        filename = f"{platform}_{link_type}.txt"
    else:
        cur.execute("""
            SELECT url FROM links
            WHERE platform = ?
            ORDER BY collected_date ASC
        """, (platform,))
        filename = f"{platform}_all.txt"

    rows = cur.fetchall()
    conn.close()

    if not rows:
        return None

    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, filename)

    with open(path, "w", encoding="utf-8") as f:
        for (url,) in rows:
            f.write(url + "\n")

    return path


# ======================
# Init
# ======================

if __name__ == "__main__":
    init_db()
    print("✅ Database initialized successfully")
