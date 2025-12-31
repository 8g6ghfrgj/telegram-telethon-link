import sqlite3
import os
import json
from datetime import datetime
from config import DATABASE_PATH

def get_connection():
    """الحصول على اتصال بقاعدة البيانات"""
    return sqlite3.connect(DATABASE_PATH, check_same_thread=False)

def init_db():
    """إنشاء جميع الجداول"""
    conn = get_connection()
    cur = conn.cursor()
    
    # جدول الجلسات
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT UNIQUE NOT NULL,
            phone TEXT,
            username TEXT,
            user_id INTEGER,
            first_name TEXT,
            last_name TEXT,
            added_date TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    """)
    
    # جدول الروابط مع تصنيف مفصل
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            platform TEXT NOT NULL,
            link_type TEXT NOT NULL,
            source_session INTEGER,
            chat_title TEXT,
            collected_date TEXT DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT
        )
    """)
    
    # إنشاء الفهارس
    cur.execute("CREATE INDEX IF NOT EXISTS idx_links_platform ON links(platform)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_links_type ON links(link_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_links_date ON links(collected_date DESC)")
    
    conn.commit()
    conn.close()
    print("✅ قاعدة البيانات جاهزة")

def add_session(session_string, phone="", username="", user_id=0, first_name="", last_name=""):
    """إضافة جلسة جديدة"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT OR REPLACE INTO sessions 
            (session_string, phone, username, user_id, first_name, last_name, added_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_string, 
            phone, 
            username, 
            user_id,
            first_name,
            last_name,
            datetime.now().isoformat(),
            1
        ))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ خطأ في إضافة الجلسة: {e}")
        return False
    finally:
        conn.close()

def get_sessions():
    """جلب جميع الجلسات النشطة"""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM sessions WHERE is_active = 1 ORDER BY id DESC")
    sessions = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    return sessions

def save_link(url, platform="telegram", link_type="unknown", source_session=0, chat_title="", metadata=None):
    """حفظ رابط مع جميع المعلومات"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        metadata_json = json.dumps(metadata) if metadata else "{}"
        
        cur.execute("""
            INSERT OR IGNORE INTO links 
            (url, platform, link_type, source_session, chat_title, collected_date, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            url.strip(),
            platform,
            link_type,
            source_session,
            chat_title,
            datetime.now().isoformat(),
            metadata_json
        ))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"⚠️ رابط مكرر: {url}")
        return False
    finally:
        conn.close()

def get_links(platform=None, link_type=None, limit=50, offset=0):
    """جلب الروابط مع تصفية"""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    query = "SELECT * FROM links WHERE 1=1"
    params = []
    
    if platform:
        query += " AND platform = ?"
        params.append(platform)
    
    if link_type:
        query += " AND link_type = ?"
        params.append(link_type)
    
    query += " ORDER BY collected_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cur.execute(query, params)
    links = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    return links

def get_link_stats():
    """إحصائيات مفصلة"""
    conn = get_connection()
    cur = conn.cursor()
    
    stats = {}
    
    # إجمالي الروابط
    cur.execute("SELECT COUNT(*) FROM links")
    stats['total_links'] = cur.fetchone()[0]
    
    # حسب المنصة
    cur.execute("SELECT platform, COUNT(*) FROM links GROUP BY platform")
    stats['by_platform'] = dict(cur.fetchall())
    
    # حسب نوع التليجرام
    cur.execute("""
        SELECT link_type, COUNT(*) 
        FROM links 
        WHERE platform = 'telegram' 
        GROUP BY link_type
        ORDER BY COUNT(*) DESC
    """)
    stats['telegram_types'] = dict(cur.fetchall())
    
    # حسب نوع الواتساب
    cur.execute("""
        SELECT link_type, COUNT(*) 
        FROM links 
        WHERE platform = 'whatsapp' 
        GROUP BY link_type
    """)
    stats['whatsapp_types'] = dict(cur.fetchall())
    
    # آخر تحديث
    cur.execute("SELECT MAX(collected_date) FROM links")
    stats['last_update'] = cur.fetchone()[0]
    
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

def export_links(platform=None, link_type=None):
    """تصدير الروابط إلى ملف"""
    from config import EXPORT_DIR
    
    links = get_links(platform, link_type, limit=10000)
    if not links:
        return None
    
    # إنشاء اسم الملف
    if platform and link_type:
        filename = f"links_{platform}_{link_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    elif platform:
        filename = f"links_{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    else:
        filename = f"links_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    filepath = os.path.join(EXPORT_DIR, filename)
    
    # كتابة الروابط
    with open(filepath, 'w', encoding='utf-8') as f:
        for link in links:
            f.write(f"{link['url']}\n")
    
    return filepath

def get_links_count(platform=None, link_type=None):
    """عدد الروابط"""
    conn = get_connection()
    cur = conn.cursor()
    
    query = "SELECT COUNT(*) FROM links WHERE 1=1"
    params = []
    
    if platform:
        query += " AND platform = ?"
        params.append(platform)
    
    if link_type:
        query += " AND link_type = ?"
        params.append(link_type)
    
    cur.execute(query, params)
    count = cur.fetchone()[0]
    
    conn.close()
    return count
