import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from config import DATABASE_PATH


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
    """
    إنشاء الجداول الجديدة مع حقول التصنيف والفحص
    """
    
    dir_name = os.path.dirname(DATABASE_PATH)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    conn = get_connection()
    cur = conn.cursor()

    # جدول الجلسات - مضمون
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT NOT NULL,
            phone_number TEXT DEFAULT '',
            user_id INTEGER DEFAULT 0,
            username TEXT DEFAULT '',
            display_name TEXT DEFAULT 'New Session',
            added_date TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            last_used TEXT,
            UNIQUE(session_string)  -- منع التكرار
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

    # إنشاء الفهارس
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_active 
        ON sessions (is_active)
    """)
    
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_links_platform 
        ON links (platform)
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")


# ======================
# Session Management
# ======================

def add_session(session_string: str, phone_number: str = None) -> bool:
    """
    إضافة جلسة جديدة - مبسط
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # تنظيف Session String
        cleaned_session = session_string.strip()
        
        if not cleaned_session or len(cleaned_session) < 10:
            return False
        
        # محاولة الإدخال
        try:
            cur.execute(
                """
                INSERT INTO sessions 
                (session_string, phone_number, display_name, added_date, is_active)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    cleaned_session,
                    phone_number or "",
                    f"Session_{datetime.now().strftime('%H%M%S')}",
                    datetime.now().isoformat(),
                    1
                )
            )
            conn.commit()
            print(f"✅ Session added: {cleaned_session[:50]}...")
            return True
            
        except sqlite3.IntegrityError:
            # الجلسة موجودة مسبقاً
            print(f"ℹ️ Session already exists")
            conn.rollback()
            return False
            
        finally:
            conn.close()
            
    except Exception as e:
        print(f"❌ Error adding session: {e}")
        return False


def get_sessions(active_only: bool = True) -> List[Dict]:
    """
    الحصول على جميع الجلسات
    """
    try:
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
        
    except Exception as e:
        print(f"Error getting sessions: {e}")
        return []


# ======================
# Link Management
# ======================

def save_link(
    url: str,
    platform: str,
    link_type: str = None,
    source_account: str = None,
    chat_id: str = None,
    message_date = None,
    is_verified: bool = False,
    verification_result: str = None,
    metadata: Dict = None
) -> bool:
    """
    حفظ رابط جديد
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        metadata_json = json.dumps(metadata) if metadata else None
        
        cur.execute(
            """
            INSERT OR IGNORE INTO links
            (url, platform, link_type, source_account, chat_id, 
             message_date, is_verified, verification_result, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url,
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
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error saving link: {e}")
        return False


# ======================
# Statistics
# ======================

def get_link_stats() -> Dict:
    """
    إحصائيات شاملة للروابط
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        stats = {}
        
        # إحصائيات حسب المنصة
        cur.execute("""
            SELECT platform, COUNT(*) as count
            FROM links
            GROUP BY platform
        """)
        stats['by_platform'] = {row[0]: row[1] for row in cur.fetchall()}
        
        conn.close()
        return stats
        
    except Exception as e:
        print(f"Error getting stats: {e}")
        return {}


# ======================
# Export Functions
# ======================

def export_links_by_type(platform: str, link_type: str = None) -> Optional[str]:
    """
    تصدير الروابط حسب النوع
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        if link_type:
            cur.execute("""
                SELECT url FROM links
                WHERE platform = ? AND link_type = ?
                ORDER BY collected_date ASC
            """, (platform, link_type))
            filename = f"links_{platform}_{link_type}.txt"
        else:
            cur.execute("""
                SELECT url FROM links
                WHERE platform = ?
                ORDER BY collected_date ASC
            """, (platform,))
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
        
    except Exception as e:
        print(f"Export error: {e}")
        return None


# ======================
# Helper Functions
# ======================

def check_sessions_table():
    """
    التحقق من وجود جدول الجلسات
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # التحقق من وجود الجدول
        cur.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='sessions'
        """)
        
        table_exists = cur.fetchone() is not None
        
        if table_exists:
            # التحقق من عدد الجلسات
            cur.execute("SELECT COUNT(*) FROM sessions")
            count = cur.fetchone()[0]
            print(f"✅ Sessions table exists with {count} sessions")
        else:
            print("❌ Sessions table does not exist")
            
        conn.close()
        return table_exists
        
    except Exception as e:
        print(f"Error checking table: {e}")
        return False


# ======================
# Initialize Database
# ======================

if __name__ == "__main__":
    # تهيئة قاعدة البيانات
    init_db()
    
    # التحقق من الجدول
    check_sessions_table()
    
    # عرض الجلسات الموجودة
    sessions = get_sessions()
    print(f"\n📋 Total active sessions: {len(sessions)}")
    for session in sessions:
        print(f"  - ID: {session.get('id')}, Name: {session.get('display_name')}")
