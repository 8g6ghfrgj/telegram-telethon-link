import sqlite3
import logging
import os
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import hashlib

from config import DATABASE_PATH, DATA_DIR

# ======================
# Logging
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Database Connection - إصلاح مهم!
# ======================

def get_db_connection():
    """إنشاء اتصال بقاعدة البيانات مع التعامل مع الأخطاء"""
    try:
        # التأكد من وجود مجلد data
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        
        # إنشاء الاتصال
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        
        # تحسين الأداء
        conn.execute('PRAGMA journal_mode = WAL')
        conn.execute('PRAGMA synchronous = NORMAL')
        conn.execute(f'PRAGMA cache_size = -{2000}')  # 2MB
        
        return conn
        
    except Exception as e:
        logger.error(f"❌ فشل في إنشاء اتصال بقاعدة البيانات: {e}")
        
        # محاولة إنشاء قاعدة بيانات جديدة
        try:
            # حذف الملف التالف إذا وجد
            if os.path.exists(DATABASE_PATH):
                os.remove(DATABASE_PATH)
                logger.info(f"🗑️ تم حذف قاعدة البيانات التالفة: {DATABASE_PATH}")
            
            # إنشاء مجلد جديد
            os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
            
            # إنشاء اتصال جديد
            conn = sqlite3.connect(DATABASE_PATH)
            conn.row_factory = sqlite3.Row
            
            # تهيئة الجداول
            init_db()
            
            logger.info(f"✅ تم إنشاء قاعدة بيانات جديدة: {DATABASE_PATH}")
            return conn
            
        except Exception as e2:
            logger.error(f"❌ فشل في إنشاء قاعدة بيانات جديدة: {e2}")
            raise

def init_db():
    """تهيئة قاعدة البيانات وإنشاء الجداول"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # جدول الجلسات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_string TEXT NOT NULL UNIQUE,
                phone_number TEXT,
                user_id INTEGER,
                username TEXT,
                display_name TEXT,
                is_active BOOLEAN DEFAULT 1,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                notes TEXT
            )
        ''')
        
        # جدول الروابط
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                platform TEXT NOT NULL,
                link_type TEXT NOT NULL,
                title TEXT,
                members_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                collected_by INTEGER,
                session_id INTEGER,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE SET NULL
            )
        ''')
        
        # جدول جلسات الجمع
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS collection_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT DEFAULT 'stopped',
                stats TEXT,
                total_links INTEGER DEFAULT 0,
                duplicate_links INTEGER DEFAULT 0,
                inactive_links INTEGER DEFAULT 0,
                channels_skipped INTEGER DEFAULT 0
            )
        ''')
        
        # فهارس للتحسين
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_links_platform_type ON links(platform, link_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_links_collected_at ON links(collected_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_links_url ON links(url)')
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Database initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error initializing database: {e}")
        return False

# ======================
# Session Management
# ======================

def add_session(session_string: str, phone: str = "", user_id: int = 0, 
                username: str = "", display_name: str = "") -> bool:
    """إضافة جلسة جديدة"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # التحقق إذا كانت الجلسة موجودة مسبقاً
        cursor.execute(
            "SELECT id FROM sessions WHERE session_string = ?",
            (session_string,)
        )
        existing = cursor.fetchone()
        
        if existing:
            logger.info(f"Session already exists with ID: {existing['id']}")
            conn.close()
            return False
        
        # إضافة الجلسة الجديدة
        cursor.execute('''
            INSERT INTO sessions 
            (session_string, phone_number, user_id, username, display_name, is_active, added_date)
            VALUES (?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
        ''', (session_string, phone, user_id, username, display_name))
        
        conn.commit()
        session_id = cursor.lastrowid
        conn.close()
        
        logger.info(f"✅ Added new session: {display_name} (ID: {session_id})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error adding session: {e}")
        return False

def get_sessions(active_only: bool = False) -> List[Dict]:
    """الحصول على قائمة الجلسات"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if active_only:
            cursor.execute('''
                SELECT * FROM sessions 
                WHERE is_active = 1 
                ORDER BY added_date DESC
            ''')
        else:
            cursor.execute('''
                SELECT * FROM sessions 
                ORDER BY is_active DESC, added_date DESC
            ''')
        
        sessions = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return sessions
        
    except Exception as e:
        logger.error(f"❌ Error getting sessions: {e}")
        return []

def delete_session(session_id: int) -> bool:
    """حذف جلسة"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
        
        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()
        
        if rows_affected > 0:
            logger.info(f"✅ Deleted session ID: {session_id}")
            return True
        else:
            logger.warning(f"❌ Session ID {session_id} not found")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error deleting session: {e}")
        return False

def delete_all_sessions() -> bool:
    """حذف جميع الجلسات"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # الحصول على عدد الجلسات قبل الحذف
        cursor.execute('SELECT COUNT(*) as count FROM sessions')
        count_before = cursor.fetchone()['count']
        
        # حذف جميع الجلسات
        cursor.execute('DELETE FROM sessions')
        
        # إعادة ضبط السلسلة التلقائية
        cursor.execute('DELETE FROM sqlite_sequence WHERE name="sessions"')
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Deleted all sessions ({count_before} sessions)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error deleting all sessions: {e}")
        return False

def update_session_status(session_id: int, is_active: bool) -> bool:
    """تحديث حالة الجلسة"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE sessions 
            SET is_active = ?, last_used = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (1 if is_active else 0, session_id))
        
        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()
        
        if rows_affected > 0:
            status = "activated" if is_active else "deactivated"
            logger.info(f"✅ Session {session_id} {status}")
            return True
        else:
            return False
            
    except Exception as e:
        logger.error(f"❌ Error updating session status: {e}")
        return False

def update_session_usage(session_id: int):
    """تحديث وقت آخر استخدام للجلسة"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE sessions 
            SET last_used = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (session_id,))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"❌ Error updating session usage: {e}")

# ======================
# Link Management
# ======================

def add_link(url: str, platform: str, link_type: str, 
             title: str = "", members_count: int = 0, 
             session_id: int = None) -> Tuple[bool, str]:
    """إضافة رابط جديد"""
    try:
        url = url.strip()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # التحقق من عدم تكرار الرابط
        cursor.execute('SELECT id FROM links WHERE url = ?', (url,))
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            return False, "duplicate"
        
        # إضافة الرابط الجديد
        cursor.execute('''
            INSERT INTO links 
            (url, platform, link_type, title, members_count, collected_at, session_id)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        ''', (url, platform, link_type, title, members_count, session_id))
        
        conn.commit()
        link_id = cursor.lastrowid
        conn.close()
        
        logger.info(f"✅ Added link: {url} ({platform}/{link_type})")
        return True, "added"
        
    except Exception as e:
        logger.error(f"❌ Error adding link: {e}")
        return False, f"error: {str(e)}"

def get_links_by_type(platform: str, link_type: str, 
                      limit: int = 20, offset: int = 0) -> List[Dict]:
    """الحصول على الروابط حسب النوع"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM links 
            WHERE platform = ? AND link_type = ? AND is_active = 1
            ORDER BY collected_at DESC
            LIMIT ? OFFSET ?
        ''', (platform, link_type, limit, offset))
        
        links = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return links
        
    except Exception as e:
        logger.error(f"❌ Error getting links by type: {e}")
        return []

def get_link_stats() -> Dict:
    """الحصول على إحصائيات الروابط"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # إحصائيات حسب المنصة
        cursor.execute('''
            SELECT platform, COUNT(*) as count 
            FROM links 
            WHERE is_active = 1 
            GROUP BY platform
        ''')
        stats['by_platform'] = {row['platform']: row['count'] for row in cursor.fetchall()}
        
        # إحصائيات تيليجرام حسب النوع
        cursor.execute('''
            SELECT link_type, COUNT(*) as count 
            FROM links 
            WHERE platform = 'telegram' AND is_active = 1 
            GROUP BY link_type
        ''')
        stats['telegram_by_type'] = {row['link_type']: row['count'] for row in cursor.fetchall()}
        
        # إجمالي الروابط
        cursor.execute('SELECT COUNT(*) as total FROM links WHERE is_active = 1')
        stats['total_links'] = cursor.fetchone()['total']
        
        # الروابط المضافة اليوم
        cursor.execute('''
            SELECT COUNT(*) as today_count 
            FROM links 
            WHERE DATE(collected_at) = DATE('now') AND is_active = 1
        ''')
        stats['today_links'] = cursor.fetchone()['today_count']
        
        conn.close()
        return stats
        
    except Exception as e:
        logger.error(f"❌ Error getting link stats: {e}")
        return {}

def export_links_by_type(platform: str, link_type: str = None, format: str = 'txt') -> str:
    """تصدير الروابط حسب المنصة والنوع"""
    try:
        from config import EXPORT_DIR, EXPORT_ENCODING
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if link_type:
            cursor.execute('''
                SELECT url FROM links 
                WHERE platform = ? AND link_type = ? AND is_active = 1
                ORDER BY collected_at DESC
            ''', (platform, link_type))
        else:
            cursor.execute('''
                SELECT url FROM links 
                WHERE platform = ? AND is_active = 1
                ORDER BY collected_at DESC
            ''', (platform,))
        
        links = cursor.fetchall()
        conn.close()
        
        if not links:
            return None
        
        # إنشاء اسم الملف
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if link_type:
            if link_type == "public_group":
                type_name = "public_groups"
            elif link_type == "private_group":
                type_name = "private_groups"
            elif link_type == "group":
                type_name = "groups"
            else:
                type_name = link_type
                
            filename = f"{platform}_{type_name}_{timestamp}.txt"
        else:
            filename = f"{platform}_all_{timestamp}.txt"
        
        filepath = os.path.join(EXPORT_DIR, filename)
        
        # كتابة الروابط إلى الملف
        with open(filepath, 'w', encoding=EXPORT_ENCODING) as f:
            f.write(f"# Exported at: {datetime.now()}\n")
            f.write(f"# Platform: {platform}\n")
            if link_type:
                f.write(f"# Type: {link_type}\n")
            f.write(f"# Total links: {len(links)}\n")
            f.write("=" * 50 + "\n\n")
            
            for link in links:
                f.write(f"{link['url']}\n")
        
        logger.info(f"✅ Exported {len(links)} links to {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"❌ Export error: {e}")
        return None

# ======================
# Collection Sessions
# ======================

def start_collection_session() -> int:
    """بدء جلسة جمع جديدة"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO collection_sessions 
            (start_time, status) 
            VALUES (CURRENT_TIMESTAMP, 'in_progress')
        ''')
        
        conn.commit()
        session_id = cursor.lastrowid
        conn.close()
        
        logger.info(f"✅ Started collection session ID: {session_id}")
        return session_id
        
    except Exception as e:
        logger.error(f"❌ Error starting collection session: {e}")
        return 0

def update_collection_stats(session_id: int, stats: Dict):
    """تحديث إحصائيات جلسة الجمع"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        stats_json = json.dumps(stats)
        
        cursor.execute('''
            UPDATE collection_sessions 
            SET stats = ?, 
                total_links = ?,
                duplicate_links = ?,
                inactive_links = ?,
                channels_skipped = ?
            WHERE id = ?
        ''', (
            stats_json,
            stats.get('total_collected', 0),
            stats.get('duplicate_links', 0),
            stats.get('inactive_links', 0),
            stats.get('channels_skipped', 0),
            session_id
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Updated collection session {session_id} stats")
        
    except Exception as e:
        logger.error(f"❌ Error updating collection stats: {e}")

def get_active_collection_session() -> Optional[int]:
    """الحصول على جلسة الجمع النشطة"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id FROM collection_sessions 
            WHERE status = 'in_progress' 
            ORDER BY start_time DESC 
            LIMIT 1
        ''')
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return result['id']
        return None
        
    except Exception as e:
        logger.error(f"❌ Error getting active collection session: {e}")
        return None

def end_collection_session(session_id: int, status: str = "completed"):
    """إنهاء جلسة الجمع"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE collection_sessions
            SET end_time = CURRENT_TIMESTAMP,
                status = ?
            WHERE id = ?
        ''', (status, session_id))

        conn.commit()
        conn.close()

        logger.info(f"✅ Ended collection session ID: {session_id}")

    except Exception as e:
        logger.error(f"❌ Error ending collection session: {e}")

# ======================
# Initialization
# ======================

if __name__ == "__main__":
    print("🔧 Initializing database...")
    if init_db():
        print("✅ Database initialized successfully!")
    else:
        print("❌ Failed to initialize database!")
