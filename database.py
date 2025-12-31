import sqlite3
import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any

from config import DATABASE_PATH, EXPORT_DIR

# ======================
# Logging Configuration
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Database Connection
# ======================

def get_connection() -> sqlite3.Connection:
    """
    إنشاء اتصال بقاعدة البيانات
    
    Returns:
        sqlite3.Connection: كائن الاتصال بقاعدة البيانات
    """
    try:
        # إنشاء مجلد قاعدة البيانات إذا لم يكن موجوداً
        db_dir = os.path.dirname(DATABASE_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        
        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False,
            timeout=30
        )
        
        # تفعيل المفاتيح الأجنبية
        conn.execute("PRAGMA foreign_keys = ON")
        
        # تحسين الأداء
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = -2000")  # 2MB cache
        
        return conn
        
    except Exception as e:
        logger.error(f"Error creating database connection: {e}")
        raise

# ======================
# Database Initialization
# ======================

def init_db() -> None:
    """
    تهيئة قاعدة البيانات وإنشاء الجداول إذا لم تكن موجودة
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        logger.info("Initializing database...")
        
        # ======================
        # جدول الجلسات
        # ======================
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
                last_used TEXT,
                CONSTRAINT unique_session UNIQUE(session_string)
            )
        """)
        
        # ======================
        # جدول الروابط
        # ======================
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
                collected_date TEXT DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT unique_url UNIQUE(url)
            )
        """)
        
        # ======================
        # جدول إحصائيات الجمع
        # ======================
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
                verified_count INTEGER DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        """)
        
        # ======================
        # إنشاء الفهارس
        # ======================
        
        # فهارس الجلسات
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions (is_active)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_added_date ON sessions (added_date DESC)")
        
        # فهارس الروابط
        cur.execute("CREATE INDEX IF NOT EXISTS idx_links_platform ON links (platform)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_links_type ON links (link_type)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_links_verified ON links (is_verified)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_links_collected_date ON links (collected_date DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_links_platform_type ON links (platform, link_type)")
        
        # فهارس الإحصائيات
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stats_status ON collection_stats (status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stats_start_time ON collection_stats (start_time DESC)")
        
        conn.commit()
        logger.info("✅ Database initialized successfully!")
        
    except Exception as e:
        logger.error(f"❌ Error initializing database: {e}")
        raise
        
    finally:
        if conn:
            conn.close()

# ======================
# Session Management Functions
# ======================

def add_session(
    session_string: str,
    phone_number: str = None,
    user_id: int = 0,
    username: str = None,
    display_name: str = None
) -> bool:
    """
    إضافة جلسة جديدة إلى قاعدة البيانات
    
    Args:
        session_string: Session String
        phone_number: رقم الهاتف (اختياري)
        user_id: معرف المستخدم (اختياري)
        username: اسم المستخدم (اختياري)
        display_name: الاسم المعروض (اختياري)
        
    Returns:
        bool: True إذا تمت الإضافة بنجاح
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # إنشاء اسم عرضي إذا لم يتم توفيره
        if not display_name:
            if username:
                display_name = f"@{username}"
            elif phone_number:
                display_name = f"User_{phone_number[-4:]}" if len(phone_number) >= 4 else f"User_{phone_number}"
            else:
                display_name = f"Session_{datetime.now().strftime('%H%M%S')}"
        
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
                display_name,
                datetime.now().isoformat(),
                1  # مفعلة تلقائياً
            )
        )
        
        conn.commit()
        logger.info(f"✅ Session added: {display_name}")
        return True
        
    except sqlite3.IntegrityError as e:
        logger.warning(f"⚠️ Session already exists: {e}")
        return True  # نرجع True حتى إذا كانت موجودة مسبقاً
        
    except Exception as e:
        logger.error(f"❌ Error adding session: {e}")
        return False
        
    finally:
        if conn:
            conn.close()

def get_sessions(active_only: bool = True) -> List[Dict]:
    """
    الحصول على قائمة الجلسات
    
    Args:
        active_only: إذا كان True، يرجع الجلسات النشطة فقط
        
    Returns:
        list: قائمة بالجلسات
    """
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        if active_only:
            cur.execute("""
                SELECT id, session_string, phone_number, user_id, 
                       username, display_name, added_date, is_active, last_used
                FROM sessions 
                WHERE is_active = 1
                ORDER BY added_date DESC
            """)
        else:
            cur.execute("""
                SELECT id, session_string, phone_number, user_id, 
                       username, display_name, added_date, is_active, last_used
                FROM sessions 
                ORDER BY added_date DESC
            """)
        
        rows = cur.fetchall()
        sessions = [dict(row) for row in rows]
        
        logger.debug(f"Retrieved {len(sessions)} sessions")
        return sessions
        
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        return []
        
    finally:
        if conn:
            conn.close()

def get_session_by_id(session_id: int) -> Optional[Dict]:
    """
    الحصول على جلسة بواسطة المعرف
    
    Args:
        session_id: معرف الجلسة
        
    Returns:
        dict: معلومات الجلسة أو None إذا لم توجد
    """
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, session_string, phone_number, user_id, 
                   username, display_name, added_date, is_active, last_used
            FROM sessions 
            WHERE id = ?
        """, (session_id,))
        
        row = cur.fetchone()
        
        if row:
            return dict(row)
        else:
            logger.warning(f"Session with ID {session_id} not found")
            return None
            
    except Exception as e:
        logger.error(f"Error getting session by ID: {e}")
        return None
        
    finally:
        if conn:
            conn.close()

def get_session_by_string(session_string: str) -> Optional[Dict]:
    """
    الحصول على جلسة بواسطة Session String
    
    Args:
        session_string: Session String
        
    Returns:
        dict: معلومات الجلسة أو None إذا لم توجد
    """
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, session_string, phone_number, user_id, 
                   username, display_name, added_date, is_active, last_used
            FROM sessions 
            WHERE session_string = ?
        """, (session_string,))
        
        row = cur.fetchone()
        
        if row:
            return dict(row)
        else:
            return None
            
    except Exception as e:
        logger.error(f"Error getting session by string: {e}")
        return None
        
    finally:
        if conn:
            conn.close()

def update_session_status(session_id: int, is_active: bool) -> bool:
    """
    تحديث حالة الجلسة
    
    Args:
        session_id: معرف الجلسة
        is_active: الحالة الجديدة (True = نشط، False = غير نشط)
        
    Returns:
        bool: True إذا تم التحديث بنجاح
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute(
            """
            UPDATE sessions 
            SET is_active = ?, last_used = ?
            WHERE id = ?
            """,
            (1 if is_active else 0, datetime.now().isoformat(), session_id)
        )
        
        conn.commit()
        success = cur.rowcount > 0
        
        if success:
            status = "مفعل" if is_active else "معطل"
            logger.info(f"✅ Session {session_id} status updated to: {status}")
        else:
            logger.warning(f"⚠️ Session {session_id} not found for update")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Error updating session status: {e}")
        return False
        
    finally:
        if conn:
            conn.close()

def delete_session(session_id: int) -> bool:
    """
    حذف جلسة من قاعدة البيانات
    
    Args:
        session_id: معرف الجلسة
        
    Returns:
        bool: True إذا تم الحذف بنجاح
    """
    conn = None
    try:
        # الحصول على معلومات الجلسة قبل الحذف
        session_info = get_session_by_id(session_id)
        
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        
        conn.commit()
        success = cur.rowcount > 0
        
        if success and session_info:
            display_name = session_info.get('display_name', 'Unknown')
            logger.info(f"✅ Session deleted: {display_name} (ID: {session_id})")
        elif success:
            logger.info(f"✅ Session {session_id} deleted")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Error deleting session: {e}")
        return False
        
    finally:
        if conn:
            conn.close()

def get_session_count() -> Dict[str, int]:
    """
    الحصول على إحصائيات الجلسات
    
    Returns:
        dict: إحصائيات الجلسات
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # إجمالي الجلسات
        cur.execute("SELECT COUNT(*) FROM sessions")
        total = cur.fetchone()[0] or 0
        
        # الجلسات النشطة
        cur.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
        active = cur.fetchone()[0] or 0
        
        # الجلسات المعطلة
        cur.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 0")
        inactive = cur.fetchone()[0] or 0
        
        return {
            "total": total,
            "active": active,
            "inactive": inactive
        }
        
    except Exception as e:
        logger.error(f"Error getting session count: {e}")
        return {"total": 0, "active": 0, "inactive": 0}
        
    finally:
        if conn:
            conn.close()

# ======================
# Link Management Functions
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
    حفظ رابط جديد في قاعدة البيانات
    
    Args:
        url: الرابط
        platform: المنصة (telegram, whatsapp, etc.)
        link_type: نوع الرابط (channel, group, bot, etc.)
        source_account: الحساب المصدر
        chat_id: معرف المحادثة
        message_date: تاريخ الرسالة
        is_verified: إذا كان الرابط مفحوصاً
        verification_result: نتيجة الفحص
        metadata: بيانات إضافية
        
    Returns:
        bool: True إذا تم الحفظ بنجاح
    """
    conn = None
    try:
        if not url or not platform:
            logger.warning("URL and platform are required")
            return False
        
        conn = get_connection()
        cur = conn.cursor()
        
        # تحويل metadata إلى JSON
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        
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
                message_date.isoformat() if hasattr(message_date, 'isoformat') else message_date,
                1 if is_verified else 0,
                verification_result,
                metadata_json
            )
        )
        
        conn.commit()
        success = cur.rowcount > 0
        
        if success:
            logger.debug(f"✅ Link saved: {url}")
        else:
            logger.debug(f"⚠️ Link already exists: {url}")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Error saving link: {e}")
        return False
        
    finally:
        if conn:
            conn.close()

def update_link_verification(
    url: str,
    is_verified: bool,
    verification_result: str,
    metadata: Dict = None
) -> bool:
    """
    تحديث حالة فحص الرابط
    
    Args:
        url: الرابط
        is_verified: حالة الفحص
        verification_result: نتيجة الفحص
        metadata: بيانات إضافية
        
    Returns:
        bool: True إذا تم التحديث بنجاح
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        
        cur.execute(
            """
            UPDATE links 
            SET is_verified = ?, 
                verification_result = ?,
                verification_date = ?,
                metadata = COALESCE(?, metadata)
            WHERE url = ?
            """,
            (
                1 if is_verified else 0,
                verification_result,
                datetime.now().isoformat(),
                metadata_json,
                url
            )
        )
        
        conn.commit()
        success = cur.rowcount > 0
        
        if success:
            logger.debug(f"✅ Link verification updated: {url}")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Error updating link verification: {e}")
        return False
        
    finally:
        if conn:
            conn.close()

def get_links(
    platform: str = None,
    link_type: str = None,
    is_verified: bool = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict]:
    """
    الحصول على الروابط مع إمكانية التصفية
    
    Args:
        platform: المنصة للتصفية
        link_type: نوع الرابط للتصفية
        is_verified: حالة الفحص للتصفية
        limit: الحد الأقصى للنتائج
        offset: الإزاحة
        
    Returns:
        list: قائمة بالروابط
    """
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        query = "SELECT * FROM links"
        conditions = []
        params = []
        
        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        
        if link_type:
            conditions.append("link_type = ?")
            params.append(link_type)
        
        if is_verified is not None:
            conditions.append("is_verified = ?")
            params.append(1 if is_verified else 0)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY collected_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cur.execute(query, params)
        rows = cur.fetchall()
        
        links = []
        for row in rows:
            link = dict(row)
            
            # تحويل metadata من JSON إذا كانت موجودة
            if link.get('metadata'):
                try:
                    link['metadata'] = json.loads(link['metadata'])
                except:
                    pass
            
            links.append(link)
        
        logger.debug(f"Retrieved {len(links)} links")
        return links
        
    except Exception as e:
        logger.error(f"Error getting links: {e}")
        return []
        
    finally:
        if conn:
            conn.close()

def get_links_by_type(
    platform: str,
    link_type: str = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict]:
    """
    الحصول على الروابط حسب المنصة والنوع
    
    Args:
        platform: المنصة (telegram, whatsapp)
        link_type: نوع الرابط
        limit: الحد الأقصى للنتائج
        offset: الإزاحة
        
    Returns:
        list: قائمة بالروابط
    """
    return get_links(platform=platform, link_type=link_type, limit=limit, offset=offset)

def get_link_count(platform: str = None, link_type: str = None) -> int:
    """
    الحصول على عدد الروابط
    
    Args:
        platform: المنصة للتصفية
        link_type: نوع الرابط للتصفية
        
    Returns:
        int: عدد الروابط
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        query = "SELECT COUNT(*) FROM links"
        conditions = []
        params = []
        
        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        
        if link_type:
            conditions.append("link_type = ?")
            params.append(link_type)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        cur.execute(query, params)
        count = cur.fetchone()[0] or 0
        
        return count
        
    except Exception as e:
        logger.error(f"Error getting link count: {e}")
        return 0
        
    finally:
        if conn:
            conn.close()

# ======================
# Statistics Functions
# ======================

def get_link_stats() -> Dict:
    """
    الحصول على إحصائيات شاملة للروابط
    
    Returns:
        dict: إحصائيات الروابط
    """
    conn = None
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
        
        # إحصائيات حسب نوع التليجرام
        cur.execute("""
            SELECT link_type, COUNT(*) as count
            FROM links
            WHERE platform = 'telegram'
            GROUP BY link_type
        """)
        stats['telegram_by_type'] = {row[0]: row[1] for row in cur.fetchall()}
        
        # إحصائيات الفحص
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(is_verified) as verified,
                SUM(CASE WHEN verification_result = 'valid' THEN 1 ELSE 0 END) as valid
            FROM links
        """)
        row = cur.fetchone()
        stats['verification'] = {
            'total': row[0] or 0,
            'verified': row[1] or 0,
            'valid': row[2] or 0
        }
        
        # إحصائيات حسب التاريخ
        cur.execute("""
            SELECT DATE(collected_date) as date, COUNT(*) as count
            FROM links
            GROUP BY DATE(collected_date)
            ORDER BY date DESC
            LIMIT 7
        """)
        stats['daily'] = [{"date": row[0], "count": row[1]} for row in cur.fetchall()]
        
        # إجمالي الإحصائيات
        stats['total_links'] = sum(stats['by_platform'].values())
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting link stats: {e}")
        return {
            'by_platform': {},
            'telegram_by_type': {},
            'verification': {'total': 0, 'verified': 0, 'valid': 0},
            'daily': [],
            'total_links': 0
        }
        
    finally:
        if conn:
            conn.close()

def get_collection_stats() -> List[Dict]:
    """
    الحصول على إحصائيات عمليات الجمع
    
    Returns:
        list: قائمة بإحصائيات الجمع
    """
    conn = None
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        cur.execute("""
            SELECT cs.*, s.display_name
            FROM collection_stats cs
            LEFT JOIN sessions s ON cs.session_id = s.id
            ORDER BY cs.start_time DESC
            LIMIT 10
        """)
        
        rows = cur.fetchall()
        stats = [dict(row) for row in rows]
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting collection stats: {e}")
        return []
        
    finally:
        if conn:
            conn.close()

# ======================
# Collection Stats Functions
# ======================

def start_collection_session(session_id: int) -> int:
    """
    بدء جلسة جمع جديدة
    
    Args:
        session_id: معرف الجلسة
        
    Returns:
        int: معرف جلسة الجمع الجديدة
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute(
            """
            INSERT INTO collection_stats 
            (session_id, start_time, status)
            VALUES (?, ?, ?)
            """,
            (session_id, datetime.now().isoformat(), 'running')
        )
        
        conn.commit()
        collection_id = cur.lastrowid
        
        logger.info(f"✅ Collection session #{collection_id} started")
        return collection_id
        
    except Exception as e:
        logger.error(f"❌ Error starting collection session: {e}")
        return 0
        
    finally:
        if conn:
            conn.close()

def update_collection_stats(
    collection_id: int,
    status: str = None,
    telegram_count: int = 0,
    whatsapp_count: int = 0,
    verified_count: int = 0
) -> bool:
    """
    تحديث إحصائيات جلسة الجمع
    
    Args:
        collection_id: معرف جلسة الجمع
        status: الحالة الجديدة
        telegram_count: عدد روابط التليجرام المضافة
        whatsapp_count: عدد روابط الواتساب المضافة
        verified_count: عدد الروابط المفحوصة
        
    Returns:
        bool: True إذا تم التحديث بنجاح
    """
    conn = None
    try:
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
            # حساب الإجمالي
            total_increment = telegram_count + whatsapp_count
            
            # إضافة وقت النهاية إذا تم الانتهاء
            if status == 'completed':
                updates.append("end_time = ?")
                params.append(datetime.now().isoformat())
            
            # تحديث الإجمالي
            updates.append("total_collected = total_collected + ?")
            params.append(total_increment)
            
            # إضافة collection_id
            params.append(collection_id)
            
            query = f"UPDATE collection_stats SET {', '.join(updates)} WHERE id = ?"
            cur.execute(query, params)
            
            conn.commit()
            success = cur.rowcount > 0
            
            if success:
                logger.debug(f"✅ Collection stats updated for session #{collection_id}")
            else:
                logger.warning(f"⚠️ Collection session #{collection_id} not found")
            
            return success
        else:
            logger.warning("No updates provided")
            return False
        
    except Exception as e:
        logger.error(f"❌ Error updating collection stats: {e}")
        return False
        
    finally:
        if conn:
            conn.close()

# ======================
# Export Functions
# ======================

def export_links_by_type(platform: str, link_type: str = None) -> Optional[str]:
    """
    تصدير الروابط حسب النوع إلى ملف نصي
    
    Args:
        platform: المنصة (telegram, whatsapp)
        link_type: نوع الرابط
        
    Returns:
        str: مسار الملف المصدر أو None إذا فشل
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        if link_type:
            cur.execute("""
                SELECT url FROM links
                WHERE platform = ? AND link_type = ?
                ORDER BY collected_date ASC
            """, (platform, link_type))
            filename = f"links_{platform}_{link_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        else:
            cur.execute("""
                SELECT url FROM links
                WHERE platform = ?
                ORDER BY collected_date ASC
            """, (platform,))
            filename = f"links_{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        rows = cur.fetchall()
        
        if not rows:
            logger.warning(f"No links found for export: {platform}/{link_type}")
            return None
        
        # إنشاء مجلد التصدير إذا لم يكن موجوداً
        os.makedirs(EXPORT_DIR, exist_ok=True)
        filepath = os.path.join(EXPORT_DIR, filename)
        
        # كتابة الروابط إلى الملف
        with open(filepath, 'w', encoding='utf-8') as f:
            for (url,) in rows:
                f.write(url + "\n")
        
        logger.info(f"✅ Links exported to: {filepath} ({len(rows)} links)")
        return filepath
        
    except Exception as e:
        logger.error(f"❌ Error exporting links: {e}")
        return None
        
    finally:
        if conn:
            conn.close()

def export_all_links() -> Dict[str, str]:
    """
    تصدير جميع الروابط مصنفة حسب المنصة والنوع
    
    Returns:
        dict: مسارات الملفات المصدرة
    """
    try:
        export_paths = {}
        
        # تصدير جميع روابط التليجرام
        telegram_path = export_links_by_type("telegram")
        if telegram_path:
            export_paths["telegram_all"] = telegram_path
        
        # تصدير روابط التليجرام حسب النوع
        telegram_types = ["channel", "public_group", "private_group", "bot", "message"]
        for link_type in telegram_types:
            path = export_links_by_type("telegram", link_type)
            if path:
                export_paths[f"telegram_{link_type}"] = path
        
        # تصدير روابط الواتساب
        whatsapp_path = export_links_by_type("whatsapp")
        if whatsapp_path:
            export_paths["whatsapp_all"] = whatsapp_path
        
        # تصدير روابط الواتساب حسب النوع
        whatsapp_types = ["group", "phone"]
        for link_type in whatsapp_types:
            path = export_links_by_type("whatsapp", link_type)
            if path:
                export_paths[f"whatsapp_{link_type}"] = path
        
        return export_paths
        
    except Exception as e:
        logger.error(f"Error exporting all links: {e}")
        return {}

# ======================
# Database Maintenance
# ======================

def optimize_database() -> bool:
    """
    تحسين قاعدة البيانات
    
    Returns:
        bool: True إذا تم التحسين بنجاح
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # تشغيل VACUUM لتحسين المساحة
        cur.execute("VACUUM")
        
        # إعادة بناء الفهارس
        cur.execute("REINDEX")
        
        # تحليل قاعدة البيانات
        cur.execute("ANALYZE")
        
        conn.commit()
        logger.info("✅ Database optimized successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error optimizing database: {e}")
        return False
        
    finally:
        if conn:
            conn.close()

def backup_database(backup_path: str = None) -> Optional[str]:
    """
    إنشاء نسخة احتياطية من قاعدة البيانات
    
    Args:
        backup_path: مسار النسخة الاحتياطية
        
    Returns:
        str: مسار النسخة الاحتياطية أو None إذا فشل
    """
    try:
        import shutil
        import time
        
        if not backup_path:
            backup_dir = os.path.join(os.path.dirname(DATABASE_PATH), "backups")
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"database_backup_{timestamp}.db")
        
        # نسخ قاعدة البيانات
        shutil.copy2(DATABASE_PATH, backup_path)
        
        logger.info(f"✅ Database backed up to: {backup_path}")
        return backup_path
        
    except Exception as e:
        logger.error(f"❌ Error backing up database: {e}")
        return None

def cleanup_old_links(days: int = 30) -> int:
    """
    تنظيف الروابط القديمة
    
    Args:
        days: عدد الأيام (الروابط الأقدم من هذا العدد سيتم حذفها)
        
    Returns:
        int: عدد الروابط المحذوفة
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # حساب التاريخ القديم
        old_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        cur.execute("""
            DELETE FROM links 
            WHERE collected_date < ?
        """, (old_date,))
        
        deleted_count = cur.rowcount
        conn.commit()
        
        logger.info(f"✅ Cleaned up {deleted_count} old links (older than {days} days)")
        return deleted_count
        
    except Exception as e:
        logger.error(f"❌ Error cleaning up old links: {e}")
        return 0
        
    finally:
        if conn:
            conn.close()

# ======================
# Test Functions
# ======================

def test_database():
    """
    اختبار جميع وظائف قاعدة البيانات
    """
    print("\n" + "="*50)
    print("🧪 Testing Database Module")
    print("="*50)
    
    # 1. تهيئة قاعدة البيانات
    print("\n1. Initializing database...")
    init_db()
    print("   ✅ Database initialized")
    
    # 2. إضافة جلسة اختبار
    print("\n2. Adding test session...")
    session_added = add_session(
        session_string="test_session_string_123",
        phone_number="1234567890",
        user_id=123456,
        username="testuser",
        display_name="Test User"
    )
    print(f"   ✅ Session added: {session_added}")
    
    # 3. الحصول على الجلسات
    print("\n3. Getting sessions...")
    sessions = get_sessions()
    print(f"   📋 Found {len(sessions)} sessions")
    
    # 4. إحصائيات الجلسات
    print("\n4. Getting session statistics...")
    session_stats = get_session_count()
    print(f"   📊 Total: {session_stats['total']}, Active: {session_stats['active']}, Inactive: {session_stats['inactive']}")
    
    # 5. إضافة رابط اختبار
    print("\n5. Adding test link...")
    link_added = save_link(
        url="https://t.me/test_channel",
        platform="telegram",
        link_type="channel",
        source_account="test_session",
        is_verified=True,
        verification_result="valid"
    )
    print(f"   ✅ Link added: {link_added}")
    
    # 6. الحصول على الروابط
    print("\n6. Getting links...")
    links = get_links(platform="telegram")
    print(f"   🔗 Found {len(links)} telegram links")
    
    # 7. إحصائيات الروابط
    print("\n7. Getting link statistics...")
    link_stats = get_link_stats()
    print(f"   📊 Total links: {link_stats.get('total_links', 0)}")
    
    # 8. بدء جلسة جمع
    print("\n8. Starting collection session...")
    if sessions:
        collection_id = start_collection_session(sessions[0].get('id', 1))
        print(f"   ▶️ Collection session started with ID: {collection_id}")
    
    print("\n" + "="*50)
    print("✅ Database module test completed successfully!")
    print("="*50)

# ======================
# Main Execution
# ======================

if __name__ == "__main__":
    from datetime import timedelta
    
    # تشغيل الاختبار
    test_database()
