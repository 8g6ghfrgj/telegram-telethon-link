import sqlite3
import logging
import os
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import hashlib

from config import DATABASE_PATH

# ======================
# Logging
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Database Connection
# ======================

def get_db_connection():
    """إنشاء اتصال بقاعدة البيانات"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
        
        # جدول الإحصائيات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE DEFAULT CURRENT_DATE,
                total_links INTEGER DEFAULT 0,
                telegram_links INTEGER DEFAULT 0,
                whatsapp_links INTEGER DEFAULT 0,
                public_groups INTEGER DEFAULT 0,
                private_groups INTEGER DEFAULT 0,
                whatsapp_groups INTEGER DEFAULT 0,
                duplicate_links INTEGER DEFAULT 0,
                inactive_skipped INTEGER DEFAULT 0,
                channels_skipped INTEGER DEFAULT 0
            )
        ''')
        
        # فهارس للتحسين
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_links_platform_type ON links(platform, link_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_links_collected_at ON links(collected_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_links_active ON links(is_active)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_links_url ON links(url)')
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Database initialized successfully")
        
        # تحديث الإحصائيات الأولية
        update_daily_stats()
        
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

# ======================
# Session Management
# ======================

def add_session(session_string: str, phone: str = "", user_id: int = 0, 
                username: str = "", display_name: str = "") -> bool:
    """إضافة جلسة جديدة"""
    try:
        # إنشاء hash للجلسة للتحقق من التكرار
        session_hash = hashlib.md5(session_string.encode()).hexdigest()[:16]
        
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
        
        logger.info(f"Added new session: {display_name} (ID: {session_id})")
        return True
        
    except Exception as e:
        logger.error(f"Error adding session: {e}")
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
        logger.error(f"Error getting sessions: {e}")
        return []

def get_session_by_id(session_id: int) -> Optional[Dict]:
    """الحصول على جلسة بواسطة ID"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
        session = cursor.fetchone()
        
        conn.close()
        
        if session:
            return dict(session)
        return None
        
    except Exception as e:
        logger.error(f"Error getting session by ID: {e}")
        return None

def delete_session(session_id: int) -> bool:
    """حذف جلسة"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
        
        # تحديث الروابط التي جمعتها هذه الجلسة
        cursor.execute('''
            UPDATE links 
            SET session_id = NULL 
            WHERE session_id = ?
        ''', (session_id,))
        
        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()
        
        if rows_affected > 0:
            logger.info(f"Deleted session ID: {session_id}")
            return True
        else:
            logger.warning(f"Session ID {session_id} not found")
            return False
            
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
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
        
        # تحديث الروابط
        cursor.execute('UPDATE links SET session_id = NULL')
        
        conn.commit()
        conn.close()
        
        logger.info(f"Deleted all sessions ({count_before} sessions)")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting all sessions: {e}")
        return False

def update_session_status(session_id: int, is_active: bool) -> bool:
    """تحديث حالة الجلسة (تفعيل/تعطيل)"""
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
            logger.info(f"Session {session_id} {status}")
            return True
        else:
            return False
            
    except Exception as e:
        logger.error(f"Error updating session status: {e}")
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
        logger.error(f"Error updating session usage: {e}")

# ======================
# Link Management
# ======================

def add_link(url: str, platform: str, link_type: str, 
             title: str = "", members_count: int = 0, 
             session_id: int = None) -> Tuple[bool, str]:
    """
    إضافة رابط جديد
    Returns: (success, message)
    """
    try:
        # تنظيف الرابط
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
        
        logger.info(f"Added link: {url} ({platform}/{link_type})")
        return True, "added"
        
    except Exception as e:
        logger.error(f"Error adding link: {e}")
        return False, f"error: {str(e)}"

def add_links_batch(links_data: List[Dict]) -> Dict:
    """إضافة مجموعة من الروابط دفعة واحدة"""
    results = {
        'total': len(links_data),
        'added': 0,
        'duplicates': 0,
        'errors': 0,
        'error_messages': []
    }
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for link_data in links_data:
            try:
                url = link_data.get('url', '').strip()
                platform = link_data.get('platform', '')
                link_type = link_data.get('link_type', '')
                title = link_data.get('title', '')
                members_count = link_data.get('members_count', 0)
                session_id = link_data.get('session_id')
                
                if not url or not platform or not link_type:
                    results['errors'] += 1
                    results['error_messages'].append("Missing required fields")
                    continue
                
                # التحقق من عدم التكرار
                cursor.execute('SELECT id FROM links WHERE url = ?', (url,))
                if cursor.fetchone():
                    results['duplicates'] += 1
                    continue
                
                # إضافة الرابط
                cursor.execute('''
                    INSERT INTO links 
                    (url, platform, link_type, title, members_count, collected_at, session_id)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ''', (url, platform, link_type, title, members_count, session_id))
                
                results['added'] += 1
                
            except Exception as e:
                results['errors'] += 1
                results['error_messages'].append(str(e)[:100])
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error in batch add: {e}")
        results['errors'] += 1
        results['error_messages'].append(str(e)[:100])
    
    return results

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
        logger.error(f"Error getting links by type: {e}")
        return []

def get_all_links(limit: int = 100, offset: int = 0) -> List[Dict]:
    """الحصول على جميع الروابط"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM links 
            WHERE is_active = 1
            ORDER BY collected_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        
        links = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return links
        
    except Exception as e:
        logger.error(f"Error getting all links: {e}")
        return []

def search_links(query: str, limit: int = 50) -> List[Dict]:
    """بحث في الروابط"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        search_term = f"%{query}%"
        cursor.execute('''
            SELECT * FROM links 
            WHERE (url LIKE ? OR title LIKE ?) AND is_active = 1
            ORDER BY collected_at DESC
            LIMIT ?
        ''', (search_term, search_term, limit))
        
        links = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return links
        
    except Exception as e:
        logger.error(f"Error searching links: {e}")
        return []

def delete_link(link_id: int) -> bool:
    """حذف رابط"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM links WHERE id = ?', (link_id,))
        
        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()
        
        if rows_affected > 0:
            logger.info(f"Deleted link ID: {link_id}")
            return True
        else:
            return False
            
    except Exception as e:
        logger.error(f"Error deleting link: {e}")
        return False

def delete_all_links() -> bool:
    """حذف جميع الروابط"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # الحصول على عدد الروابط قبل الحذف
        cursor.execute('SELECT COUNT(*) as count FROM links')
        count_before = cursor.fetchone()['count']
        
        # حذف جميع الروابط
        cursor.execute('DELETE FROM links')
        
        # إعادة ضبط السلسلة التلقائية
        cursor.execute('DELETE FROM sqlite_sequence WHERE name="links"')
        
        conn.commit()
        conn.close()
        
        logger.info(f"Deleted all links ({count_before} links)")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting all links: {e}")
        return False

def update_link_status(link_id: int, is_active: bool) -> bool:
    """تحديث حالة الرابط"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE links 
            SET is_active = ? 
            WHERE id = ?
        ''', (1 if is_active else 0, link_id))
        
        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()
        
        if rows_affected > 0:
            status = "activated" if is_active else "deactivated"
            logger.info(f"Link {link_id} {status}")
            return True
        else:
            return False
            
    except Exception as e:
        logger.error(f"Error updating link status: {e}")
        return False

# ======================
# Statistics & Analytics
# ======================

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
        
        # إحصائيات واتساب حسب النوع
        cursor.execute('''
            SELECT link_type, COUNT(*) as count 
            FROM links 
            WHERE platform = 'whatsapp' AND is_active = 1 
            GROUP BY link_type
        ''')
        stats['whatsapp_by_type'] = {row['link_type']: row['count'] for row in cursor.fetchall()}
        
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
        
        # الروابط المضافة هذا الأسبوع
        cursor.execute('''
            SELECT COUNT(*) as week_count 
            FROM links 
            WHERE DATE(collected_at) >= DATE('now', '-7 days') AND is_active = 1
        ''')
        stats['week_links'] = cursor.fetchone()['week_count']
        
        # إحصائيات خاصة
        special_stats = {}
        
        # الروابط المكررة (محسوبة من جلسات الجمع)
        cursor.execute('SELECT SUM(duplicate_links) as total FROM collection_sessions')
        special_stats['duplicates_removed'] = cursor.fetchone()['total'] or 0
        
        # الروابط غير النشطة
        cursor.execute('SELECT SUM(inactive_links) as total FROM collection_sessions')
        special_stats['inactive_skipped'] = cursor.fetchone()['total'] or 0
        
        # القنوات المتجاهلة
        cursor.execute('SELECT SUM(channels_skipped) as total FROM collection_sessions')
        special_stats['channels_skipped'] = cursor.fetchone()['total'] or 0
        
        stats['special_stats'] = special_stats
        
        conn.close()
        return stats
        
    except Exception as e:
        logger.error(f"Error getting link stats: {e}")
        return {}

def get_detailed_stats() -> Dict:
    """الحصول على إحصائيات مفصلة"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # توزيع الروابط حسب الشهر
        cursor.execute('''
            SELECT 
                strftime('%Y-%m', collected_at) as month,
                COUNT(*) as count
            FROM links 
            WHERE is_active = 1
            GROUP BY strftime('%Y-%m', collected_at)
            ORDER BY month DESC
            LIMIT 12
        ''')
        stats['by_month'] = [dict(row) for row in cursor.fetchall()]
        
        # أفضل الجلسات أداءً
        cursor.execute('''
            SELECT 
                s.display_name,
                COUNT(l.id) as links_count
            FROM links l
            LEFT JOIN sessions s ON l.session_id = s.id
            WHERE l.is_active = 1
            GROUP BY l.session_id
            ORDER BY links_count DESC
            LIMIT 10
        ''')
        stats['top_sessions'] = [dict(row) for row in cursor.fetchall()]
        
        # توزيع الروابط حسب حجم المجموعة
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN members_count = 0 THEN 'غير معروف'
                    WHEN members_count < 100 THEN 'أقل من 100'
                    WHEN members_count < 1000 THEN '100-1000'
                    WHEN members_count < 10000 THEN '1000-10000'
                    ELSE 'أكثر من 10000'
                END as size_range,
                COUNT(*) as count
            FROM links 
            WHERE is_active = 1 AND members_count > 0
            GROUP BY size_range
            ORDER BY count DESC
        ''')
        stats['by_size'] = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return stats
        
    except Exception as e:
        logger.error(f"Error getting detailed stats: {e}")
        return {}

def update_daily_stats():
    """تحديث إحصائيات اليوم"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # التحقق إذا تم تحديث إحصائيات اليوم
        cursor.execute('SELECT id FROM statistics WHERE date = DATE("now")')
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            return
        
        # حساب إحصائيات اليوم
        cursor.execute('''
            SELECT 
                COUNT(*) as total_links,
                SUM(CASE WHEN platform = 'telegram' THEN 1 ELSE 0 END) as telegram_links,
                SUM(CASE WHEN platform = 'whatsapp' THEN 1 ELSE 0 END) as whatsapp_links,
                SUM(CASE WHEN link_type = 'public_group' THEN 1 ELSE 0 END) as public_groups,
                SUM(CASE WHEN link_type = 'private_group' THEN 1 ELSE 0 END) as private_groups,
                SUM(CASE WHEN link_type = 'group' THEN 1 ELSE 0 END) as whatsapp_groups
            FROM links 
            WHERE DATE(collected_at) = DATE('now') AND is_active = 1
        ''')
        
        today_stats = cursor.fetchone()
        
        # إضافة إحصائيات اليوم
        cursor.execute('''
            INSERT INTO statistics 
            (date, total_links, telegram_links, whatsapp_links, 
             public_groups, private_groups, whatsapp_groups)
            VALUES (DATE('now'), ?, ?, ?, ?, ?, ?)
        ''', (
            today_stats['total_links'] or 0,
            today_stats['telegram_links'] or 0,
            today_stats['whatsapp_links'] or 0,
            today_stats['public_groups'] or 0,
            today_stats['private_groups'] or 0,
            today_stats['whatsapp_groups'] or 0
        ))
        
        conn.commit()
        conn.close()
        
        logger.info("Updated daily statistics")
        
    except Exception as e:
        logger.error(f"Error updating daily stats: {e}")

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
        
        logger.info(f"Started collection session ID: {session_id}")
        return session_id
        
    except Exception as e:
        logger.error(f"Error starting collection session: {e}")
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
        
        logger.info(f"Updated collection session {session_id} stats")
        
    except Exception as e:
        logger.error(f"Error updating collection stats: {e}")

def end_collection_session(session_id: int, status: str = 'completed'):
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
        
        logger.info(f"Ended collection session {session_id} with status: {status}")
        
    except Exception as e:
        logger.error(f"Error ending collection session: {e}")

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
        logger.error(f"Error getting active collection session: {e}")
        return None

def get_collection_session_stats(session_id: int) -> Dict:
    """الحصول على إحصائيات جلسة الجمع"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM collection_sessions WHERE id = ?', (session_id,))
        session = cursor.fetchone()
        
        conn.close()
        
        if session:
            stats = dict(session)
            if stats.get('stats'):
                try:
                    stats['stats'] = json.loads(stats['stats'])
                except:
                    stats['stats'] = {}
            return stats
        return {}
        
    except Exception as e:
        logger.error(f"Error getting collection session stats: {e}")
        return {}

# ======================
# Export Functions
# ======================

def export_links_by_type(platform: str, link_type: str = None, format: str = 'txt') -> str:
    """تصدير الروابط حسب المنصة والنوع"""
    try:
        from config import EXPORT_DIR, EXPORT_ENCODING
        import os
        
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
        
        logger.info(f"Exported {len(links)} links to {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Export error: {e}")
        return None

def export_all_links(format: str = 'txt') -> str:
    """تصدير جميع الروابط"""
    try:
        from config import EXPORT_DIR, EXPORT_ENCODING
        import os
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT platform, link_type, url 
            FROM links 
            WHERE is_active = 1
            ORDER BY platform, link_type, collected_at DESC
        ''')
        
        links = cursor.fetchall()
        conn.close()
        
        if not links:
            return None
        
        # إنشاء اسم الملف
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"all_links_{timestamp}.txt"
        filepath = os.path.join(EXPORT_DIR, filename)
        
        # تنظيم الروابط حسب النوع
        organized_links = {}
        for link in links:
            platform = link['platform']
            link_type = link['link_type']
            key = f"{platform}_{link_type}"
            
            if key not in organized_links:
                organized_links[key] = []
            organized_links[key].append(link['url'])
        
        # كتابة الملف
        with open(filepath, 'w', encoding=EXPORT_ENCODING) as f:
            f.write(f"# Exported at: {datetime.now()}\n")
            f.write(f"# Total links: {len(links)}\n")
            f.write("=" * 50 + "\n\n")
            
            for key, urls in organized_links.items():
                f.write(f"\n# {key.upper()} ({len(urls)} links)\n")
                f.write("#" * 30 + "\n")
                for url in urls:
                    f.write(f"{url}\n")
                f.write("\n")
        
        logger.info(f"Exported all {len(links)} links to {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Export all error: {e}")
        return None

def export_sessions_backup() -> str:
    """تصدير نسخة احتياطية للجلسات"""
    try:
        from config import EXPORT_DIR, EXPORT_ENCODING
        import os
        
        sessions = get_sessions()
        
        if not sessions:
            return None
        
        # إنشاء اسم الملف
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sessions_backup_{timestamp}.json"
        filepath = os.path.join(EXPORT_DIR, filename)
        
        # تحضير البيانات
        backup_data = {
            'export_date': datetime.now().isoformat(),
            'total_sessions': len(sessions),
            'sessions': []
        }
        
        for session in sessions:
            session_data = {
                'session_string': session.get('session_string'),
                'phone_number': session.get('phone_number'),
                'user_id': session.get('user_id'),
                'username': session.get('username'),
                'display_name': session.get('display_name'),
                'is_active': bool(session.get('is_active')),
                'added_date': session.get('added_date'),
                'last_used': session.get('last_used')
            }
            backup_data['sessions'].append(session_data)
        
        # كتابة الملف
        with open(filepath, 'w', encoding=EXPORT_ENCODING) as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Exported {len(sessions)} sessions backup to {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Export sessions backup error: {e}")
        return None

# ======================
# Maintenance Functions
# ======================

def cleanup_database():
    """تنظيف قاعدة البيانات"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # حذف الروابط غير النشطة القديمة (أقدم من 30 يوم)
        cursor.execute('''
            DELETE FROM links 
            WHERE is_active = 0 AND 
                  DATE(collected_at) < DATE('now', '-30 days')
        ''')
        
        inactive_deleted = cursor.rowcount
        
        # حذف جلسات الجمع القديمة (أقدم من 90 يوم)
        cursor.execute('''
            DELETE FROM collection_sessions 
            WHERE DATE(start_time) < DATE('now', '-90 days')
        ''')
        
        sessions_deleted = cursor.rowcount
        
        # حذف الإحصائيات القديمة (أقدم من 180 يوم)
        cursor.execute('''
            DELETE FROM statistics 
            WHERE DATE(date) < DATE('now', '-180 days')
        ''')
        
        stats_deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f"Database cleanup: {inactive_deleted} inactive links, "
                   f"{sessions_deleted} old sessions, {stats_deleted} old stats deleted")
        
        return {
            'inactive_links': inactive_deleted,
            'old_sessions': sessions_deleted,
            'old_stats': stats_deleted
        }
        
    except Exception as e:
        logger.error(f"Database cleanup error: {e}")
        return {}

def get_database_size() -> Dict:
    """الحصول على حجم قاعدة البيانات"""
    try:
        import os
        
        if not os.path.exists(DATABASE_PATH):
            return {'size_bytes': 0, 'size_mb': 0.0}
        
        size_bytes = os.path.getsize(DATABASE_PATH)
        size_mb = size_bytes / (1024 * 1024)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # عدد السجلات في كل جدول
        tables = ['sessions', 'links', 'collection_sessions', 'statistics']
        table_counts = {}
        
        for table in tables:
            cursor.execute(f'SELECT COUNT(*) as count FROM {table}')
            table_counts[table] = cursor.fetchone()['count']
        
        conn.close()
        
        return {
            'size_bytes': size_bytes,
            'size_mb': round(size_mb, 2),
            'table_counts': table_counts
        }
        
    except Exception as e:
        logger.error(f"Error getting database size: {e}")
        return {}

# ======================
# Initialization
# ======================

if __name__ == "__main__":
    print("🔧 تهيئة قاعدة البيانات...")
    init_db()
    print("✅ تم تهيئة قاعدة البيانات بنجاح!")
    
    # عرض إحصائيات أولية
    size_info = get_database_size()
    print(f"📊 حجم قاعدة البيانات: {size_info.get('size_mb', 0)} MB")
    
    if size_info.get('table_counts'):
        print("📈 عدد السجلات:")
        for table, count in size_info['table_counts'].items():
            print(f"  • {table}: {count}")
