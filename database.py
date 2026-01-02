import sqlite3
import logging
import os
import json
import csv
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any, Union
from enum import Enum
import threading

from config import DATABASE_PATH, DATA_DIR, EXPORT_DIR, EXPORT_ENCODING, BACKUP_DIR

# ======================
# Configuration
# ======================

# إعدادات الحماية
FORCE_DELETE = False  # يجب تعيينها يدوياً للسماح بالحذف الكامل
PROTECTED_TABLES = ['links', 'sessions']  # الجداول المحمية
MAX_BACKUPS = 10  # الحد الأقصى لعدد النسخ الاحتياطية

# ======================
# Logging
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Constants & Enums
# ======================

class LinkType(Enum):
    """تحديد أنواع الروابط بشكل ثابت ومتسق"""
    # Telegram - الأنواع المستخدمة فقط
    TELEGRAM_PUBLIC_GROUP = "public_group"
    TELEGRAM_PRIVATE_GROUP = "private_group"
    TELEGRAM_JOIN_REQUEST = "join_request"
    
    # WhatsApp
    WHATSAPP_GROUP = "group"
    
    @classmethod
    def get_all_types(cls):
        """الحصول على جميع الأنواع النشطة"""
        return [
            cls.TELEGRAM_PUBLIC_GROUP.value,
            cls.TELEGRAM_PRIVATE_GROUP.value,
            cls.TELEGRAM_JOIN_REQUEST.value,
            cls.WHATSAPP_GROUP.value,
        ]
    
    @classmethod
    def get_telegram_types(cls):
        """الحصول على جميع أنواع تليجرام النشطة"""
        return [
            cls.TELEGRAM_PUBLIC_GROUP.value,
            cls.TELEGRAM_PRIVATE_GROUP.value,
            cls.TELEGRAM_JOIN_REQUEST.value,
        ]
    
    @classmethod
    def get_whatsapp_types(cls):
        """الحصول على جميع أنواع واتساب النشطة"""
        return [cls.WHATSAPP_GROUP.value]
    
    @classmethod
    def is_valid_type(cls, platform: str, link_type: str) -> bool:
        """التحقق من صحة نوع الرابط للمنصة"""
        if platform == "telegram":
            return link_type in cls.get_telegram_types()
        elif platform == "whatsapp":
            return link_type in cls.get_whatsapp_types()
        return False

# ======================
# Database Connection with Transactions
# ======================

class DatabaseConnection:
    """مدير اتصال قاعدة البيانات مع حماية متقدمة"""
    
    @staticmethod
    def get_connection():
        """الحصول على اتصال قاعدة البيانات"""
        try:
            # التأكد من وجود مجلد data
            os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
            
            # إنشاء الاتصال
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            
            # تحسين الأداء
            conn.execute('PRAGMA journal_mode = WAL')
            conn.execute('PRAGMA synchronous = NORMAL')
            conn.execute('PRAGMA cache_size = -2000')
            conn.execute('PRAGMA foreign_keys = ON')
            
            return conn
            
        except Exception as e:
            logger.error(f"❌ فشل في إنشاء اتصال قاعدة البيانات: {e}")
            
            # محاولة إصلاح بدلاً من الحذف
            if DatabaseConnection.repair_database():
                return DatabaseConnection.get_connection()
            else:
                logger.critical("❌ فشل إصلاح قاعدة البيانات، يرجى التحقق يدوياً")
                raise
    
    @staticmethod
    def backup_database():
        """إنشاء نسخة احتياطية من قاعدة البيانات"""
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            
            # تنظيف النسخ القديمة
            DatabaseConnection.cleanup_old_backups()
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}.db")
            
            if os.path.exists(DATABASE_PATH):
                shutil.copy2(DATABASE_PATH, backup_path)
                logger.info(f"✅ تم إنشاء نسخة احتياطية: {backup_path}")
                return backup_path
            
            logger.warning("⚠️ لا يوجد ملف قاعدة بيانات للنسخ الاحتياطي")
            return None
            
        except Exception as e:
            logger.error(f"❌ فشل في إنشاء نسخة احتياطية: {e}")
            return None
    
    @staticmethod
    def cleanup_old_backups():
        """تنظيف النسخ الاحتياطية القديمة"""
        try:
            if not os.path.exists(BACKUP_DIR):
                return
            
            backups = []
            for filename in os.listdir(BACKUP_DIR):
                if filename.startswith("backup_") and filename.endswith(".db"):
                    filepath = os.path.join(BACKUP_DIR, filename)
                    mtime = os.path.getmtime(filepath)
                    backups.append((mtime, filepath))
            
            # ترتيب حسب التاريخ (الأقدم أولاً)
            backups.sort()
            
            # حذف النسخ الزائدة عن الحد
            if len(backups) > MAX_BACKUPS:
                for i in range(len(backups) - MAX_BACKUPS):
                    os.remove(backups[i][1])
                    logger.info(f"🗑️ تم حذف النسخة الاحتياطية القديمة: {backups[i][1]}")
                    
        except Exception as e:
            logger.error(f"❌ فشل في تنظيف النسخ الاحتياطية: {e}")
    
    @staticmethod
    def repair_database():
        """إصلاح قاعدة البيانات التالفة"""
        try:
            if not os.path.exists(DATABASE_PATH):
                logger.info("ℹ️ لا يوجد ملف قاعدة بيانات للإصلاح")
                return True
            
            # 1. إنشاء نسخة احتياطية أولاً
            backup = DatabaseConnection.backup_database()
            if not backup:
                logger.error("❌ لا يمكن الإصلاح بدون نسخة احتياطية")
                return False
            
            # 2. محاولة فتح وإصلاح
            conn = None
            try:
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()
                
                # التحقق من الجداول
                cursor.execute("PRAGMA integrity_check")
                result = cursor.fetchone()[0]
                
                if result == "ok":
                    logger.info("✅ فحص سلامة قاعدة البيانات ناجح")
                    conn.close()
                    return True
                else:
                    logger.warning(f"⚠️ مشكلة في سلامة قاعدة البيانات: {result}")
                    
                    # محاولة إصلاح
                    cursor.execute("PRAGMA optimize")
                    cursor.execute("VACUUM")
                    conn.commit()
                    
                    cursor.execute("PRAGMA integrity_check")
                    result = cursor.fetchone()[0]
                    
                    if result == "ok":
                        logger.info("✅ تم إصلاح قاعدة البيانات بنجاح")
                        return True
                    else:
                        logger.error(f"❌ فشل إصلاح قاعدة البيانات: {result}")
                        return False
                        
            except Exception as e:
                logger.error(f"❌ خطأ أثناء الإصلاح: {e}")
                return False
            finally:
                if conn:
                    conn.close()
                    
        except Exception as e:
            logger.error(f"❌ خطأ عام في الإصلاح: {e}")
            return False

# ======================
# Transaction Decorator
# ======================

def transaction(func):
    """ديكوراتور لإدارة Transactions"""
    def wrapper(*args, **kwargs):
        conn = None
        cursor = None
        try:
            conn = DatabaseConnection.get_connection()
            cursor = conn.cursor()
            
            # بدء Transaction
            cursor.execute("BEGIN TRANSACTION")
            
            # تنفيذ الدالة
            result = func(*args, **kwargs, conn=conn, cursor=cursor)
            
            # تأكيد التغييرات
            conn.commit()
            return result
            
        except Exception as e:
            # التراجع عن التغييرات
            if conn:
                conn.rollback()
            logger.error(f"❌ فشلت المعاملة في {func.__name__}: {e}")
            raise
            
        finally:
            # إغلاق الاتصال
            if cursor:
                cursor.close()
            if conn:
                conn.close()
                
    return wrapper

# ======================
# Database Initialization
# ======================

def init_db():
    """تهيئة قاعدة البيانات وإنشاء الجداول"""
    try:
        # محاولة إصلاح قاعدة البيانات التالفة
        if os.path.exists(DATABASE_PATH):
            if not DatabaseConnection.repair_database():
                logger.error("❌ فشل إصلاح قاعدة البيانات الموجودة")
                return False
        
        conn = DatabaseConnection.get_connection()
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
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول الروابط - الأنواع النشطة فقط
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                platform TEXT NOT NULL,
                link_type TEXT NOT NULL,
                title TEXT,
                description TEXT,
                members_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                collected_by INTEGER,
                session_id INTEGER,
                metadata TEXT,
                last_checked TIMESTAMP,
                checked_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE SET NULL,
                CHECK (platform IN ('telegram', 'whatsapp')),
                CHECK (link_type IN ({','.join(['?'] * len(LinkType.get_all_types()))}))
            )
        ''', LinkType.get_all_types())
        
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
                channels_skipped INTEGER DEFAULT 0,
                platform TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول سجل التغييرات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS change_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                record_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                old_data TEXT,
                new_data TEXT,
                changed_by TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # فهارس للتحسين
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_links_platform_type 
            ON links(platform, link_type, is_active)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_links_collected_at 
            ON links(collected_at DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_links_is_active 
            ON links(is_active)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_links_url 
            ON links(url)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sessions_active 
            ON sessions(is_active)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_links_last_checked 
            ON links(last_checked)
        ''')
        
        conn.commit()
        conn.close()
        
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")
        return False

# ======================
# Protected Delete Functions
# ======================

@transaction
def delete_session(session_id: int, force_delete: bool = False, 
                  conn=None, cursor=None) -> bool:
    """حذف جلسة - مع حماية ضد الحذف العرضي"""
    try:
        if not force_delete and not FORCE_DELETE:
            logger.critical(f"🚫 محاولة حذف جلسة {session_id} بدون إذن - الحذف معطل")
            return False
        
        # الحصول على بيانات الجلسة قبل الحذف
        cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
        session = cursor.fetchone()
        
        if not session:
            logger.warning(f"⚠️ لم يتم العثور على جلسة بالرقم {session_id}")
            return False
        
        # تسجيل في سجل التغييرات قبل الحذف
        cursor.execute('''
            INSERT INTO change_log 
            (table_name, record_id, action, old_data, changed_at)
            VALUES ('sessions', ?, 'DELETE', ?, CURRENT_TIMESTAMP)
        ''', (session_id, json.dumps(dict(session))))
        
        # حذف الجلسة
        cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
        
        logger.warning(f"⚠️ تم حذف جلسة {session_id} (قوة الحذف: {force_delete})")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في حذف الجلسة: {e}")
        raise

@transaction
def delete_all_sessions(force_delete: bool = False, 
                       conn=None, cursor=None) -> bool:
    """حذف جميع الجلسات - مع حماية مشددة"""
    try:
        if not force_delete or not FORCE_DELETE:
            logger.critical("🚫 محاولة حذف جميع الجلسات بدون إذن - العملية مرفوضة")
            return False
        
        # الحصول على عدد الجلسات قبل الحذف
        cursor.execute('SELECT COUNT(*) as count FROM sessions')
        count_before = cursor.fetchone()['count']
        
        if count_before == 0:
            logger.info("ℹ️ لا توجد جلسات لحذفها")
            return True
        
        # تسجيل في سجل التغييرات قبل الحذف
        cursor.execute('SELECT * FROM sessions')
        all_sessions = cursor.fetchall()
        
        for session in all_sessions:
            session_dict = dict(session)
            cursor.execute('''
                INSERT INTO change_log 
                (table_name, record_id, action, old_data, changed_at)
                VALUES ('sessions', ?, 'DELETE_ALL', ?, CURRENT_TIMESTAMP)
            ''', (session_dict['id'], json.dumps(session_dict)))
        
        # حذف جميع الجلسات
        cursor.execute('DELETE FROM sessions')
        
        # إعادة ضبط السلسلة التلقائية
        cursor.execute('DELETE FROM sqlite_sequence WHERE name="sessions"')
        
        logger.warning(f"⚠️ تم حذف جميع الجلسات ({count_before} جلسة) - هذه عملية خطيرة")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في حذف جميع الجلسات: {e}")
        raise

@transaction
def delete_link(link_id: int, force_delete: bool = False, 
               conn=None, cursor=None) -> bool:
    """حذف رابط - مع حماية ضد الحذف العرضي"""
    try:
        if not force_delete and not FORCE_DELETE:
            logger.critical(f"🚫 محاولة حذف رابط {link_id} بدون إذن - الحذف معطل")
            return False
        
        # الحصول على بيانات الرابط قبل الحذف
        cursor.execute('SELECT * FROM links WHERE id = ?', (link_id,))
        link = cursor.fetchone()
        
        if not link:
            logger.warning(f"⚠️ لم يتم العثور على رابط بالرقم {link_id}")
            return False
        
        # تسجيل في سجل التغييرات قبل الحذف
        cursor.execute('''
            INSERT INTO change_log 
            (table_name, record_id, action, old_data, changed_at)
            VALUES ('links', ?, 'DELETE', ?, CURRENT_TIMESTAMP)
        ''', (link_id, json.dumps(dict(link))))
        
        # حذف الرابط
        cursor.execute('DELETE FROM links WHERE id = ?', (link_id,))
        
        logger.warning(f"⚠️ تم حذف رابط {link_id} (قوة الحذف: {force_delete})")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في حذف الرابط: {e}")
        raise

@transaction
def delete_all_links(force_delete: bool = False, 
                    conn=None, cursor=None) -> bool:
    """حذف جميع الروابط - مع حماية مشددة"""
    try:
        if not force_delete or not FORCE_DELETE:
            logger.critical("🚫 محاولة حذف جميع الروابط بدون إذن - العملية مرفوضة")
            return False
        
        # الحصول على عدد الروابط قبل الحذف
        cursor.execute('SELECT COUNT(*) as count FROM links')
        count_before = cursor.fetchone()['count']
        
        if count_before == 0:
            logger.info("ℹ️ لا توجد روابط لحذفها")
            return True
        
        # تسجيل في سجل التغييرات قبل الحذف
        cursor.execute('SELECT * FROM links')
        all_links = cursor.fetchall()
        
        for link in all_links:
            link_dict = dict(link)
            cursor.execute('''
                INSERT INTO change_log 
                (table_name, record_id, action, old_data, changed_at)
                VALUES ('links', ?, 'DELETE_ALL', ?, CURRENT_TIMESTAMP)
            ''', (link_dict['id'], json.dumps(link_dict)))
        
        # حذف جميع الروابط
        cursor.execute('DELETE FROM links')
        
        # إعادة ضبط السلسلة التلقائية
        cursor.execute('DELETE FROM sqlite_sequence WHERE name="links"')
        
        logger.warning(f"⚠️ تم حذف جميع الروابط ({count_before} رابط) - هذه عملية خطيرة")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في حذف جميع الروابط: {e}")
        raise

# ======================
# Session Management
# ======================

@transaction
def add_session(session_string: str, phone: str = "", user_id: int = 0, 
                username: str = "", display_name: str = "", 
                conn=None, cursor=None) -> bool:
    """إضافة جلسة جديدة"""
    try:
        # التحقق إذا كانت الجلسة موجودة مسبقاً
        cursor.execute(
            "SELECT id FROM sessions WHERE session_string = ?",
            (session_string,)
        )
        existing = cursor.fetchone()
        
        if existing:
            logger.info(f"ℹ️ الجلسة موجودة بالفعل بالرقم: {existing['id']}")
            return False
        
        # إضافة الجلسة الجديدة
        cursor.execute('''
            INSERT INTO sessions 
            (session_string, phone_number, user_id, username, display_name, 
             is_active, added_date, last_used)
            VALUES (?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ''', (session_string, phone, user_id, username, display_name))
        
        session_id = cursor.lastrowid
        
        # تسجيل في سجل التغييرات
        cursor.execute('''
            INSERT INTO change_log 
            (table_name, record_id, action, new_data, changed_at)
            VALUES ('sessions', ?, 'CREATE', ?, CURRENT_TIMESTAMP)
        ''', (session_id, json.dumps({
            'session_string': session_string,
            'display_name': display_name
        })))
        
        logger.info(f"✅ تمت إضافة جلسة جديدة: {display_name} (الرقم: {session_id})")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في إضافة جلسة: {e}")
        raise

@transaction
def get_sessions(active_only: bool = False, conn=None, cursor=None) -> List[Dict]:
    """الحصول على قائمة الجلسات"""
    try:
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
        
        return [dict(row) for row in cursor.fetchall()]
        
    except Exception as e:
        logger.error(f"❌ خطأ في الحصول على الجلسات: {e}")
        return []

@transaction  
def update_session_status(session_id: int, is_active: bool, conn=None, cursor=None) -> bool:
    """تحديث حالة الجلسة"""
    try:
        # الحصول على البيانات القديمة
        cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
        old_session = cursor.fetchone()
        
        if not old_session:
            logger.warning(f"⚠️ لم يتم العثور على جلسة بالرقم {session_id}")
            return False
        
        # تحديث الحالة
        cursor.execute('''
            UPDATE sessions 
            SET is_active = ?, last_used = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (1 if is_active else 0, session_id))
        
        # الحصول على البيانات الجديدة
        cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
        new_session = cursor.fetchone()
        
        # تسجيل في سجل التغييرات
        cursor.execute('''
            INSERT INTO change_log 
            (table_name, record_id, action, old_data, new_data, changed_at)
            VALUES ('sessions', ?, 'UPDATE', ?, ?, CURRENT_TIMESTAMP)
        ''', (session_id, json.dumps(dict(old_session)), json.dumps(dict(new_session))))
        
        status = "تم تفعيل" if is_active else "تم تعطيل"
        logger.info(f"✅ {status} الجلسة {session_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث حالة الجلسة: {e}")
        raise

# ======================
# Link Management
# ======================

@transaction
def add_link(url: str, platform: str, link_type: str, 
             title: str = "", members_count: int = 0, 
             session_id: int = None, description: str = "", 
             metadata: Dict = None, conn=None, cursor=None) -> Tuple[bool, str, Optional[int]]:
    """إضافة رابط جديد"""
    try:
        url = url.strip()
        
        if not LinkType.is_valid_type(platform, link_type):
            logger.error(f"❌ نوع رابط غير صالح: {platform}/{link_type}")
            return False, "invalid_type", None
        
        # التحقق من عدم تكرار الرابط
        cursor.execute('SELECT id FROM links WHERE url = ?', (url,))
        existing = cursor.fetchone()
        
        if existing:
            logger.info(f"ℹ️ الرابط موجود بالفعل: {url}")
            return False, "duplicate", existing['id']
        
        # تحويل metadata إلى JSON
        metadata_json = json.dumps(metadata) if metadata else None
        
        # إضافة الرابط الجديد
        cursor.execute('''
            INSERT INTO links 
            (url, platform, link_type, title, description, members_count, 
             collected_at, session_id, metadata, last_checked, checked_count)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, CURRENT_TIMESTAMP, 1)
        ''', (url, platform, link_type, title, description, members_count, 
              session_id, metadata_json))
        
        link_id = cursor.lastrowid
        
        # تسجيل في سجل التغييرات
        cursor.execute('''
            INSERT INTO change_log 
            (table_name, record_id, action, new_data, changed_at)
            VALUES ('links', ?, 'CREATE', ?, CURRENT_TIMESTAMP)
        ''', (link_id, json.dumps({
            'url': url,
            'platform': platform,
            'link_type': link_type,
            'title': title
        })))
        
        logger.info(f"✅ تمت إضافة رابط: {url} ({platform}/{link_type})")
        return True, "added", link_id
        
    except Exception as e:
        logger.error(f"❌ خطأ في إضافة رابط: {e}")
        raise

@transaction
def update_link_members(link_id: int, members_count: int, conn=None, cursor=None) -> bool:
    """تحديث عدد أعضاء الرابط"""
    try:
        cursor.execute('''
            UPDATE links 
            SET members_count = ?, 
                last_checked = CURRENT_TIMESTAMP,
                checked_count = checked_count + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (members_count, link_id))
        
        if cursor.rowcount > 0:
            logger.info(f"✅ تم تحديث رابط {link_id} إلى {members_count} عضو")
            return True
        return False
        
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث أعضاء الرابط: {e}")
        raise

@transaction
def deactivate_link(link_id: int, reason: str = "", conn=None, cursor=None) -> bool:
    """تعطيل رابط"""
    try:
        cursor.execute('''
            UPDATE links 
            SET is_active = 0,
                description = CASE 
                    WHEN description IS NOT NULL AND description != '' 
                    THEN description || ' | ' || ?
                    ELSE ?
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (f"تم التعطيل: {reason}", f"تم التعطيل: {reason}", link_id))
        
        if cursor.rowcount > 0:
            logger.info(f"✅ تم تعطيل رابط {link_id}: {reason}")
            return True
        return False
        
    except Exception as e:
        logger.error(f"❌ خطأ في تعطيل رابط: {e}")
        raise

@transaction
def get_links_by_type(platform: str, link_type: str = None,
                      active_only: bool = True, limit: int = 20, 
                      offset: int = 0, conn=None, cursor=None) -> List[Dict]:
    """الحصول على الروابط حسب المنصة والنوع"""
    try:
        query = '''
            SELECT * FROM links 
            WHERE platform = ?
        '''
        params = [platform]
        
        if link_type:
            query += ' AND link_type = ?'
            params.append(link_type)
        
        if active_only:
            query += ' AND is_active = 1'
        
        query += ' ORDER BY collected_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
        
    except Exception as e:
        logger.error(f"❌ خطأ في الحصول على الروابط حسب النوع: {e}")
        return []

@transaction
def cleanup_old_links(days_old: int = 30, force_delete: bool = False,
                     conn=None, cursor=None) -> int:
    """تنظيف الروابط القديمة المعطلة"""
    try:
        if not force_delete and not FORCE_DELETE:
            logger.critical("🚫 محاولة تنظيف الروابط بدون إذن - العملية معطلة")
            return 0
        
        cutoff_date = (datetime.now() - timedelta(days=days_old)).strftime('%Y-%m-%d')
        
        cursor.execute('''
            SELECT COUNT(*) as count FROM links 
            WHERE is_active = 0 
            AND DATE(updated_at) < ?
        ''', (cutoff_date,))
        
        count = cursor.fetchone()['count']
        
        if count > 0:
            # تسجيل في سجل التغييرات قبل الحذف
            cursor.execute('SELECT * FROM links WHERE is_active = 0 AND DATE(updated_at) < ?', 
                          (cutoff_date,))
            old_links = cursor.fetchall()
            
            for link in old_links:
                link_dict = dict(link)
                cursor.execute('''
                    INSERT INTO change_log 
                    (table_name, record_id, action, old_data, changed_at)
                    VALUES ('links', ?, 'CLEANUP', ?, CURRENT_TIMESTAMP)
                ''', (link_dict['id'], json.dumps(link_dict)))
            
            cursor.execute('''
                DELETE FROM links 
                WHERE is_active = 0 
                AND DATE(updated_at) < ?
            ''', (cutoff_date,))
            
            logger.warning(f"⚠️ تم تنظيف {count} رابط قديم (قوة الحذف: {force_delete})")
        
        return count
        
    except Exception as e:
        logger.error(f"❌ خطأ في تنظيف الروابط القديمة: {e}")
        raise

# ======================
# Statistics & Reporting
# ======================

@transaction
def get_link_stats(conn=None, cursor=None) -> Dict:
    """الحصول على إحصائيات مفصلة للروابط"""
    try:
        stats = {}
        
        # إحصائيات حسب المنصة
        cursor.execute('''
            SELECT platform, COUNT(*) as count 
            FROM links 
            WHERE is_active = 1 
            GROUP BY platform
        ''')
        stats['by_platform'] = {row['platform']: row['count'] for row in cursor.fetchall()}
        
        # إحصائيات تيليجرام مفصلة
        cursor.execute('''
            SELECT 
                link_type,
                COUNT(*) as count
            FROM links 
            WHERE platform = 'telegram' AND is_active = 1 
            GROUP BY link_type
            ORDER BY count DESC
        ''')
        
        telegram_stats = {}
        for row in cursor.fetchall():
            telegram_stats[row['link_type']] = row['count']
        
        stats['telegram_by_type'] = telegram_stats
        
        # إحصائيات واتساب
        cursor.execute('''
            SELECT 
                link_type,
                COUNT(*) as count
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
        
        # الروابط المعطلة
        cursor.execute('SELECT COUNT(*) as inactive FROM links WHERE is_active = 0')
        stats['inactive_links'] = cursor.fetchone()['inactive']
        
        # متوسط عدد الأعضاء
        cursor.execute('''
            SELECT platform, AVG(members_count) as avg_members
            FROM links 
            WHERE is_active = 1 AND members_count > 0
            GROUP BY platform
        ''')
        stats['avg_members_by_platform'] = {
            row['platform']: round(row['avg_members'], 0) 
            for row in cursor.fetchall()
        }
        
        # الروابط حسب النوع
        cursor.execute('''
            SELECT platform, link_type, COUNT(*) as count
            FROM links
            WHERE is_active = 1
            GROUP BY platform, link_type
            ORDER BY platform, count DESC
        ''')
        stats['by_platform_and_type'] = {}
        for row in cursor.fetchall():
            platform = row['platform']
            link_type = row['link_type']
            if platform not in stats['by_platform_and_type']:
                stats['by_platform_and_type'][platform] = {}
            stats['by_platform_and_type'][platform][link_type] = row['count']
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ خطأ في الحصول على الإحصائيات: {e}")
        return {}

# ======================
# Export Functions
# ======================

def export_all_links() -> List[str]:
    """تصدير جميع الروابط في أقسام منفصلة"""
    try:
        # التأكد من وجود مجلد التصدير
        os.makedirs(EXPORT_DIR, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = os.path.join(EXPORT_DIR, f"export_{timestamp}")
        os.makedirs(export_dir, exist_ok=True)
        
        exported_files = []
        
        # الحصول على إحصائيات
        stats = get_link_stats()
        
        # 1. تصدير روابط تليجرام - مجموعات عامة
        telegram_public_groups = get_links_by_type('telegram', LinkType.TELEGRAM_PUBLIC_GROUP.value)
        if telegram_public_groups:
            filename = f"telegram_public_groups_{timestamp}.txt"
            filepath = os.path.join(export_dir, filename)
            with open(filepath, 'w', encoding=EXPORT_ENCODING) as f:
                f.write(f"# Telegram Public Groups\n")
                f.write(f"# Exported: {datetime.now()}\n")
                f.write(f"# Total: {len(telegram_public_groups)}\n")
                f.write("=" * 50 + "\n\n")
                for link in telegram_public_groups:
                    f.write(f"{link['url']}\n")
            exported_files.append(filepath)
            logger.info(f"✅ تم تصدير {len(telegram_public_groups)} مجموعة عامة")
        
        # 2. تصدير روابط تليجرام - مجموعات خاصة
        telegram_private_groups = get_links_by_type('telegram', LinkType.TELEGRAM_PRIVATE_GROUP.value)
        if telegram_private_groups:
            filename = f"telegram_private_groups_{timestamp}.txt"
            filepath = os.path.join(export_dir, filename)
            with open(filepath, 'w', encoding=EXPORT_ENCODING) as f:
                f.write(f"# Telegram Private Groups\n")
                f.write(f"# Exported: {datetime.now()}\n")
                f.write(f"# Total: {len(telegram_private_groups)}\n")
                f.write("=" * 50 + "\n\n")
                for link in telegram_private_groups:
                    f.write(f"{link['url']}\n")
            exported_files.append(filepath)
            logger.info(f"✅ تم تصدير {len(telegram_private_groups)} مجموعة خاصة")
        
        # 3. تصدير روابط تليجرام - طلب انضمام
        telegram_join_request = get_links_by_type('telegram', LinkType.TELEGRAM_JOIN_REQUEST.value)
        if telegram_join_request:
            filename = f"telegram_join_requests_{timestamp}.txt"
            filepath = os.path.join(export_dir, filename)
            with open(filepath, 'w', encoding=EXPORT_ENCODING) as f:
                f.write(f"# Telegram Join Requests\n")
                f.write(f"# Exported: {datetime.now()}\n")
                f.write(f"# Total: {len(telegram_join_request)}\n")
                f.write("=" * 50 + "\n\n")
                for link in telegram_join_request:
                    f.write(f"{link['url']}\n")
            exported_files.append(filepath)
            logger.info(f"✅ تم تصدير {len(telegram_join_request)} طلب انضمام")
        
        # 4. تصدير روابط واتساب
        whatsapp_groups = get_links_by_type('whatsapp', LinkType.WHATSAPP_GROUP.value)
        if whatsapp_groups:
            filename = f"whatsapp_groups_{timestamp}.txt"
            filepath = os.path.join(export_dir, filename)
            with open(filepath, 'w', encoding=EXPORT_ENCODING) as f:
                f.write(f"# WhatsApp Groups\n")
                f.write(f"# Exported: {datetime.now()}\n")
                f.write(f"# Total: {len(whatsapp_groups)}\n")
                f.write("=" * 50 + "\n\n")
                for link in whatsapp_groups:
                    f.write(f"{link['url']}\n")
            exported_files.append(filepath)
            logger.info(f"✅ تم تصدير {len(whatsapp_groups)} مجموعة واتساب")
        
        # 5. إنشاء ملف إحصائي
        stats_file = os.path.join(export_dir, f"stats_{timestamp}.txt")
        with open(stats_file, 'w', encoding=EXPORT_ENCODING) as f:
            f.write(f"# Export Statistics\n")
            f.write(f"# Generated: {datetime.now()}\n")
            f.write("=" * 50 + "\n\n")
            
            f.write("📊 إحصائيات الروابط\n")
            f.write("=" * 30 + "\n")
            
            for platform, count in stats.get('by_platform', {}).items():
                f.write(f"\n{platform.upper()}: {count} رابط\n")
                
                if platform == 'telegram' and 'telegram_by_type' in stats:
                    for link_type, type_count in stats['telegram_by_type'].items():
                        f.write(f"  ├─ {link_type}: {type_count}\n")
                
                elif platform == 'whatsapp' and 'whatsapp_by_type' in stats:
                    for link_type, type_count in stats['whatsapp_by_type'].items():
                        f.write(f"  ├─ {link_type}: {type_count}\n")
            
            f.write(f"\n\n📈 ملخص\n")
            f.write("=" * 30 + "\n")
            f.write(f"إجمالي الروابط النشطة: {stats.get('total_links', 0)}\n")
            f.write(f"روابط اليوم: {stats.get('today_links', 0)}\n")
            f.write(f"روابط معطلة: {stats.get('inactive_links', 0)}\n")
        
        exported_files.append(stats_file)
        
        # 6. إنشاء ملف README
        readme_file = os.path.join(export_dir, "README.txt")
        with open(readme_file, 'w', encoding=EXPORT_ENCODING) as f:
            f.write(f"# Export Directory\n")
            f.write(f"# Generated: {datetime.now()}\n")
            f.write("=" * 50 + "\n\n")
            
            f.write("📁 قائمة الملفات:\n")
            f.write("=" * 30 + "\n")
            for file_path in exported_files:
                filename = os.path.basename(file_path)
                f.write(f"- {filename}\n")
            
            f.write(f"\n\n📊 إجمالي الملفات: {len(exported_files)}\n")
            f.write(f"📅 تاريخ التصدير: {datetime.now()}\n")
        
        logger.info(f"✅ تم تصدير جميع الروابط إلى {export_dir}")
        return exported_files
        
    except Exception as e:
        logger.error(f"❌ خطأ في تصدير الروابط: {e}")
        return []

# ======================
# Maintenance Functions
# ======================

def run_maintenance():
    """تشغيل عمليات الصيانة الدورية"""
    try:
        logger.info("🔧 تشغيل صيانة قاعدة البيانات...")
        
        # 1. إنشاء نسخة احتياطية
        backup_path = DatabaseConnection.backup_database()
        if backup_path:
            logger.info(f"💾 تم إنشاء نسخة احتياطية: {backup_path}")
        
        # 2. تحسين قاعدة البيانات
        conn = DatabaseConnection.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA optimize")
        cursor.execute("VACUUM")
        conn.commit()
        conn.close()
        
        logger.info("✅ اكتملت صيانة قاعدة البيانات")
        
    except Exception as e:
        logger.error(f"❌ خطأ في الصيانة: {e}")

# ======================
# Utility Functions
# ======================

def check_database_health():
    """فحص صحة قاعدة البيانات"""
    try:
        conn = DatabaseConnection.get_connection()
        cursor = conn.cursor()
        
        print("\n🔍 فحص صحة قاعدة البيانات:")
        print("=" * 50)
        
        # 1. فحص الجداول
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"✅ عدد الجداول: {len(tables)}")
        
        # 2. فحص الروابط
        cursor.execute('''
            SELECT platform, link_type, COUNT(*) as count
            FROM links
            GROUP BY platform, link_type
        ''')
        
        print("\n📊 أنواع الروابط في قاعدة البيانات:")
        total_links = 0
        for row in cursor.fetchall():
            print(f"  {row['platform']}/{row['link_type']}: {row['count']}")
            total_links += row['count']
        
        print(f"\n📈 إجمالي الروابط: {total_links}")
        
        # 3. فحص الجلسات
        cursor.execute("SELECT COUNT(*) as count FROM sessions")
        sessions_count = cursor.fetchone()['count']
        print(f"👥 عدد الجلسات: {sessions_count}")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ فحص صحة قاعدة البيانات فشل: {e}")
        return False

# ======================
# Initialization
# ======================

if __name__ == "__main__":
    print("🔧 تهيئة قاعدة البيانات...")
    if init_db():
        print("✅ تم تهيئة قاعدة البيانات بنجاح!")
        
        # فحص صحة قاعدة البيانات
        check_database_health()
        
        # تشغيل الصيانة الأولية
        run_maintenance()
    else:
        print("❌ فشل في تهيئة قاعدة البيانات!")
