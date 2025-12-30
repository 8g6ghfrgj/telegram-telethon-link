import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, List, Optional
import logging

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

def get_connection():
    return sqlite3.connect(DATABASE_PATH, check_same_thread=False)

def init_db():
    try:
        dir_name = os.path.dirname(DATABASE_PATH)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        
        conn = get_connection()
        cur = conn.cursor()
        
        # جدول الجلسات
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_string TEXT NOT NULL UNIQUE,
                phone_number TEXT,
                user_id INTEGER,
                username TEXT,
                display_name TEXT,
                added_date TEXT DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                last_used TEXT
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
                collected_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")
        
    except Exception as e:
        logger.error(f"❌ Error initializing database: {e}")

def add_session(session_string: str, phone: str = "", user_id: int = 0, 
                username: str = "", display_name: str = "") -> bool:
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        if not display_name:
            if username:
                display_name = f"@{username}"
            elif phone:
                display_name = f"User_{phone[-4:]}"
            else:
                display_name = f"Session_{datetime.now().strftime('%H%M%S')}"
        
        cur.execute("""
            INSERT OR REPLACE INTO sessions 
            (session_string, phone_number, user_id, username, display_name, added_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session_string, phone, user_id, username, display_name,
              datetime.now().isoformat(), 1))
        
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        
        if success:
            logger.info(f"✅ Session added: {display_name}")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Error adding session: {e}")
        return False

def get_sessions(active_only: bool = True) -> List[Dict]:
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        if active_only:
            cur.execute("SELECT * FROM sessions WHERE is_active = 1 ORDER BY added_date DESC")
        else:
            cur.execute("SELECT * FROM sessions ORDER BY added_date DESC")
        
        rows = cur.fetchall()
        sessions = []
        
        for row in rows:
            sessions.append({
                'id': row['id'],
                'session_string': row['session_string'],
                'phone_number': row['phone_number'],
                'user_id': row['user_id'],
                'username': row['username'],
                'display_name': row['display_name'],
                'added_date': row['added_date'],
                'is_active': bool(row['is_active']),
                'last_used': row['last_used']
            })
        
        conn.close()
        return sessions
        
    except Exception as e:
        logger.error(f"❌ Error getting sessions: {e}")
        return []

def get_session_by_id(session_id: int) -> Optional[Dict]:
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = cur.fetchone()
        
        if row:
            session = {
                'id': row['id'],
                'session_string': row['session_string'],
                'phone_number': row['phone_number'],
                'user_id': row['user_id'],
                'username': row['username'],
                'display_name': row['display_name'],
                'added_date': row['added_date'],
                'is_active': bool(row['is_active']),
                'last_used': row['last_used']
            }
        else:
            session = None
        
        conn.close()
        return session
        
    except Exception as e:
        logger.error(f"❌ Error getting session by ID: {e}")
        return None

def delete_session(session_id: int) -> bool:
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        
        if success:
            logger.info(f"✅ Session {session_id} deleted")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Error deleting session: {e}")
        return False

def save_link(url: str, platform: str, link_type: str = None, 
              source_account: str = None, chat_id: str = None,
              message_date=None) -> bool:
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT OR IGNORE INTO links 
            (url, platform, link_type, source_account, chat_id, message_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (url, platform, link_type, source_account, chat_id,
              message_date.isoformat() if message_date else None))
        
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        
        if success:
            logger.debug(f"✅ Link saved: {url}")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Error saving link: {e}")
        return False

def get_links_by_type(platform: str, link_type: str = None, 
                     limit: int = 100, offset: int = 0) -> List[Dict]:
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        if link_type:
            cur.execute("""
                SELECT * FROM links 
                WHERE platform = ? AND link_type = ?
                ORDER BY collected_date DESC 
                LIMIT ? OFFSET ?
            """, (platform, link_type, limit, offset))
        else:
            cur.execute("""
                SELECT * FROM links 
                WHERE platform = ?
                ORDER BY collected_date DESC 
                LIMIT ? OFFSET ?
            """, (platform, limit, offset))
        
        rows = cur.fetchall()
        links = []
        
        for row in rows:
            links.append({
                'id': row['id'],
                'url': row['url'],
                'platform': row['platform'],
                'link_type': row['link_type'],
                'source_account': row['source_account'],
                'collected_date': row['collected_date']
            })
        
        conn.close()
        return links
        
    except Exception as e:
        logger.error(f"❌ Error getting links: {e}")
        return []

def get_link_stats() -> Dict:
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        stats = {}
        
        cur.execute("SELECT platform, COUNT(*) FROM links GROUP BY platform")
        stats['by_platform'] = dict(cur.fetchall())
        
        cur.execute("SELECT link_type, COUNT(*) FROM links WHERE platform = 'telegram' GROUP BY link_type")
        stats['telegram_by_type'] = dict(cur.fetchall())
        
        conn.close()
        return stats
        
    except Exception as e:
        logger.error(f"❌ Error getting stats: {e}")
        return {}

def export_links_by_type(platform: str, link_type: str = None) -> Optional[str]:
    try:
        from config import EXPORT_DIR
        os.makedirs(EXPORT_DIR, exist_ok=True)
        
        links = get_links_by_type(platform, link_type, limit=10000, offset=0)
        
        if not links:
            return None
        
        if link_type:
            filename = f"links_{platform}_{link_type}.txt"
        else:
            filename = f"links_{platform}.txt"
        
        filepath = os.path.join(EXPORT_DIR, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for link in links:
                f.write(f"{link['url']}\n")
        
        logger.info(f"✅ Exported {len(links)} links to {filename}")
        return filepath
        
    except Exception as e:
        logger.error(f"❌ Error exporting links: {e}")
        return None

if __name__ == "__main__":
    init_db()
    print("✅ Database ready")
