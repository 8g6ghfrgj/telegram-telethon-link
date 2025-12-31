import sqlite3
import os
from datetime import datetime
from config import DATABASE_PATH

def get_connection():
    return sqlite3.connect(DATABASE_PATH, check_same_thread=False)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    
    # الجلسات
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT UNIQUE NOT NULL,
            phone TEXT,
            username TEXT,
            user_id INTEGER,
            added_date TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)
    
    # الروابط
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            platform TEXT NOT NULL,
            link_type TEXT NOT NULL,
            source TEXT,
            collected_date TEXT,
            chat_title TEXT
        )
    """)
    
    # فهارس
    cur.execute("CREATE INDEX IF NOT EXISTS idx_platform ON links(platform)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_type ON links(link_type)")
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

def add_session(session_string, phone="", username="", user_id=0):
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT OR REPLACE INTO sessions 
            (session_string, phone, username, user_id, added_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_string, phone, username, user_id, datetime.now().isoformat(), 1))
        
        conn.commit()
        session_id = cur.lastrowid
        print(f"✅ Session added: ID={session_id}, User={username or phone}")
        return session_id
    except Exception as e:
        print(f"❌ Error adding session: {e}")
        return None
    finally:
        conn.close()

def get_sessions():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM sessions WHERE is_active = 1")
    sessions = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    print(f"📋 Found {len(sessions)} active sessions")
    return sessions

def save_link(url, platform="telegram", link_type="unknown", source="", chat_title=""):
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT OR IGNORE INTO links 
            (url, platform, link_type, source, collected_date, chat_title)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (url.strip(), platform, link_type, source, datetime.now().isoformat(), chat_title))
        
        conn.commit()
        saved = cur.rowcount > 0
        
        if saved:
            print(f"✅ Link saved: {url}")
        return saved
    except Exception as e:
        print(f"❌ Error saving link: {e}")
        return False
    finally:
        conn.close()

def get_links(platform=None, link_type=None, limit=50):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    query = "SELECT * FROM links"
    params = []
    
    if platform:
        query += " WHERE platform = ?"
        params.append(platform)
        if link_type:
            query += " AND link_type = ?"
            params.append(link_type)
    elif link_type:
        query += " WHERE link_type = ?"
        params.append(link_type)
    
    query += " ORDER BY collected_date DESC LIMIT ?"
    params.append(limit)
    
    cur.execute(query, params)
    links = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    print(f"📊 Retrieved {len(links)} links")
    return links

def get_stats():
    conn = get_connection()
    cur = conn.cursor()
    
    stats = {}
    
    cur.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
    stats['sessions'] = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM links")
    stats['total_links'] = cur.fetchone()[0]
    
    cur.execute("SELECT platform, COUNT(*) FROM links GROUP BY platform")
    stats['by_platform'] = dict(cur.fetchall())
    
    cur.execute("SELECT link_type, COUNT(*) FROM links WHERE platform = 'telegram' GROUP BY link_type")
    stats['telegram_types'] = dict(cur.fetchall())
    
    conn.close()
    
    print(f"📈 Stats: {stats}")
    return stats

def delete_session(session_id):
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    
    print(f"{'✅' if success else '❌'} Session {session_id} deleted")
    return success

def export_links(platform=None, link_type=None):
    from config import EXPORT_DIR
    
    links = get_links(platform, link_type, 10000)
    if not links:
        print("❌ No links to export")
        return None
    
    if platform and link_type:
        filename = f"links_{platform}_{link_type}.txt"
    elif platform:
        filename = f"links_{platform}.txt"
    else:
        filename = f"links_all.txt"
    
    filepath = os.path.join(EXPORT_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        for link in links:
            f.write(f"{link['url']}\n")
    
    print(f"✅ Exported {len(links)} links to {filename}")
    return filepath

if __name__ == "__main__":
    init_db()
