import sqlite3
import os
from datetime import datetime
from config import DATABASE_PATH

def get_connection():
    return sqlite3.connect(DATABASE_PATH, check_same_thread=False)

def init_db():
    """إنشاء الجداول"""
    conn = get_connection()
    cur = conn.cursor()
    
    # جدول الجلسات
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT UNIQUE NOT NULL,
            phone TEXT,
            username TEXT,
            added_date TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)
    
    # جدول الروابط
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            platform TEXT,
            link_type TEXT,
            source TEXT,
            collected_date TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def add_session(session_string, phone="", username=""):
    """إضافة جلسة"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT OR REPLACE INTO sessions 
            (session_string, phone, username, added_date, is_active)
            VALUES (?, ?, ?, ?, ?)
        """, (session_string, phone, username, datetime.now().isoformat(), 1))
        
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_sessions():
    """جلب جميع الجلسات"""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM sessions WHERE is_active = 1")
    sessions = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    return sessions

def save_link(url, platform="telegram", link_type="unknown", source=""):
    """حفظ رابط"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT OR IGNORE INTO links 
            (url, platform, link_type, source, collected_date)
            VALUES (?, ?, ?, ?, ?)
        """, (url, platform, link_type, source, datetime.now().isoformat()))
        
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_links(platform=None, limit=50):
    """جلب الروابط"""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    if platform:
        cur.execute("SELECT * FROM links WHERE platform = ? LIMIT ?", (platform, limit))
    else:
        cur.execute("SELECT * FROM links LIMIT ?", (limit,))
    
    links = [dict(row) for row in cur.fetchall()]
    conn.close()
    return links

def get_stats():
    """إحصائيات"""
    conn = get_connection()
    cur = conn.cursor()
    
    stats = {}
    
    cur.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
    stats['sessions'] = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM links")
    stats['links'] = cur.fetchone()[0]
    
    cur.execute("SELECT platform, COUNT(*) FROM links GROUP BY platform")
    stats['by_platform'] = dict(cur.fetchall())
    
    conn.close()
    return stats

def delete_session(session_id):
    """حذف جلسة"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    
    conn.close()
    return deleted

def export_links(platform=None):
    """تصدير الروابط"""
    from config import EXPORT_DIR
    
    links = get_links(platform, limit=10000)
    if not links:
        return None
    
    filename = f"links_{platform or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    filepath = os.path.join(EXPORT_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        for link in links:
            f.write(f"{link['url']}\n")
    
    return filepath
