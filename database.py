import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from config import DATABASE_PATH

def get_connection():
    return sqlite3.connect(DATABASE_PATH, check_same_thread=False)

def init_db():
    dir_name = os.path.dirname(DATABASE_PATH)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    conn = get_connection()
    cur = conn.cursor()

    # جدول الجلسات
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT NOT NULL,
            phone_number TEXT,
            user_id INTEGER,
            username TEXT,
            display_name TEXT,
            added_date TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            last_used TEXT,
            UNIQUE(session_string)
        )
    """)

    # جدول الروابط
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            platform TEXT NOT NULL,
            link_type TEXT,
            source_account TEXT,
            chat_id TEXT,
            message_date TEXT,
            is_verified INTEGER DEFAULT 0,
            verification_date TEXT,
            verification_result TEXT,
            metadata TEXT,
            collected_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # جدول إحصائيات الجمع
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

def add_session(session_string: str, phone_number: str = None, user_id: int = 0, 
                username: str = None, display_name: str = None) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            """
            INSERT OR REPLACE INTO sessions 
            (session_string, phone_number, user_id, username, display_name, added_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_string,
                phone_number,
                user_id,
                username,
                display_name or f"Session_{datetime.now().strftime('%H%M%S')}",
                datetime.now().isoformat(),
                1
            )
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding session: {e}")
        return False
    finally:
        conn.close()

def get_sessions(active_only: bool = True) -> List[Dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    if active_only:
        cur.execute("""
            SELECT * FROM sessions 
            WHERE is_active = 1
            ORDER BY added_date DESC
        """)
    else:
        cur.execute("""
            SELECT * FROM sessions 
            ORDER BY added_date DESC
        """)
    
    rows = cur.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_session_by_string(session_string: str) -> Optional[Dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM sessions WHERE session_string = ?", (session_string,))
    row = cur.fetchone()
    conn.close()
    
    return dict(row) if row else None

def delete_session(session_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        print(f"Error deleting session: {e}")
        return False
    finally:
        conn.close()

def save_link(url: str, platform: str, link_type: str = None, source_account: str = None,
              chat_id: str = None, message_date = None, is_verified: bool = False,
              verification_result: str = None, metadata: Dict = None) -> bool:
    if not url or not platform:
        return False

    conn = get_connection()
    cur = conn.cursor()

    try:
        metadata_json = json.dumps(metadata) if metadata else None
        
        cur.execute(
            """
            INSERT OR IGNORE INTO links
            (url, platform, link_type, source_account, chat_id, 
             message_date, is_verified, verification_result, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url.strip(),
                platform,
                link_type,
                source_account,
                chat_id,
                message_date.isoformat() if message_date else None,
                1 if is_verified else 0,
                verification_result,
                metadata_json
            )
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving link: {e}")
        return False
    finally:
        conn.close()

def get_link_stats() -> Dict:
    conn = get_connection()
    cur = conn.cursor()

    stats = {}
    
    cur.execute("SELECT platform, COUNT(*) FROM links GROUP BY platform")
    stats['by_platform'] = {row[0]: row[1] for row in cur.fetchall()}
    
    cur.execute("SELECT link_type, COUNT(*) FROM links WHERE platform = 'telegram' GROUP BY link_type")
    stats['telegram_by_type'] = {row[0]: row[1] for row in cur.fetchall()}
    
    conn.close()
    return stats

def get_links_by_type(platform: str, link_type: str = None, limit: int = 100, offset: int = 0) -> List[Dict]:
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
    
    return [dict(row) for row in rows]

def export_links_by_type(platform: str, link_type: str = None) -> Optional[str]:
    conn = get_connection()
    cur = conn.cursor()
    
    if link_type:
        cur.execute("SELECT url FROM links WHERE platform = ? AND link_type = ? ORDER BY collected_date ASC", 
                   (platform, link_type))
        filename = f"links_{platform}_{link_type}.txt"
    else:
        cur.execute("SELECT url FROM links WHERE platform = ? ORDER BY collected_date ASC", (platform,))
        filename = f"links_{platform}.txt"
    
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        return None
    
    from config import EXPORT_DIR
    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, filename)
    
    with open(path, "w", encoding="utf-8") as f:
        for (url,) in rows:
            f.write(url + "\n")
    
    return path

def start_collection_session(session_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("INSERT INTO collection_stats (session_id, start_time, status) VALUES (?, ?, ?)",
               (session_id, datetime.now().isoformat(), 'running'))
    
    conn.commit()
    collection_id = cur.lastrowid
    conn.close()
    
    return collection_id

def update_collection_stats(collection_id: int, status: str = None, 
                           telegram_count: int = 0, whatsapp_count: int = 0, 
                           verified_count: int = 0):
    conn = get_connection()
    cur = conn.cursor()
    
    updates = []
    params = []
    
    if status:
        updates.append("status = ?")
        params.append(status)
    
    if telegram_count > 0:
        updates.append("telegram_collected = telegram_collected + ?")
        params.append(telegram_count)
    
    if whatsapp_count > 0:
        updates.append("whatsapp_collected = whatsapp_collected + ?")
        params.append(whatsapp_count)
    
    if verified_count > 0:
        updates.append("verified_count = verified_count + ?")
        params.append(verified_count)
    
    if updates:
        params.append(collection_id)
        query = f"UPDATE collection_stats SET {', '.join(updates)}, end_time = ? WHERE id = ?"
        
        total_increment = telegram_count + whatsapp_count
        params.insert(-1, datetime.now().isoformat() if status == 'completed' else None)
        
        cur.execute(query, params)
        conn.commit()
    
    conn.close()

if __name__ == "__main__":
    init_db()
    print("✅ Database initialized successfully!")
