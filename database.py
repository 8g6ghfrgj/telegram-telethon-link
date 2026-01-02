import sqlite3
import logging
import os
import json
import csv
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
import hashlib

from config import DATABASE_PATH, DATA_DIR, EXPORT_DIR, EXPORT_ENCODING

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
                subtype TEXT,
                title TEXT,
                description TEXT,
                members_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                collected_by INTEGER,
                session_id INTEGER,
                metadata TEXT,
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
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_links_subtype ON links(subtype)')
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
             session_id: int = None, subtype: str = None,
             description: str = "", metadata: Dict = None) -> Tuple[bool, str]:
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
        
        # تحويل metadata إلى JSON إذا وجد
        metadata_json = json.dumps(metadata) if metadata else None
        
        # إضافة الرابط الجديد
        cursor.execute('''
            INSERT INTO links 
            (url, platform, link_type, subtype, title, description, members_count, collected_at, session_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
        ''', (url, platform, link_type, subtype, title, description, members_count, session_id, metadata_json))
        
        conn.commit()
        link_id = cursor.lastrowid
        conn.close()
        
        logger.info(f"✅ Added link: {url} ({platform}/{link_type})")
        return True, "added"
        
    except Exception as e:
        logger.error(f"❌ Error adding link: {e}")
        return False, f"error: {str(e)}"

def get_links_by_type(platform: str, link_type: str = None, subtype: str = None,
                      limit: int = 20, offset: int = 0) -> List[Dict]:
    """الحصول على الروابط حسب النوع والتصنيف الفرعي"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT * FROM links 
            WHERE platform = ? AND is_active = 1
        '''
        params = [platform]
        
        if link_type:
            query += ' AND link_type = ?'
            params.append(link_type)
        
        if subtype:
            query += ' AND subtype = ?'
            params.append(subtype)
        
        query += ' ORDER BY collected_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        links = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return links
        
    except Exception as e:
        logger.error(f"❌ Error getting links by type: {e}")
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
        logger.error(f"❌ Error getting all links: {e}")
        return []

def get_link_stats() -> Dict:
    """الحصول على إحصائيات مفصلة للروابط"""
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
        
        # إحصائيات تيليجرام مفصلة
        cursor.execute('''
            SELECT 
                link_type,
                subtype,
                COUNT(*) as count
            FROM links 
            WHERE platform = 'telegram' AND is_active = 1 
            GROUP BY link_type, subtype
            ORDER BY link_type, subtype
        ''')
        
        telegram_stats = {}
        for row in cursor.fetchall():
            link_type = row['link_type']
            subtype = row['subtype'] or 'general'
            if link_type not in telegram_stats:
                telegram_stats[link_type] = {}
            telegram_stats[link_type][subtype] = row['count']
        
        stats['telegram_details'] = telegram_stats
        
        # إحصائيات واتساب
        cursor.execute('''
            SELECT 
                link_type,
                COUNT(*) as count
            FROM links 
            WHERE platform = 'whatsapp' AND is_active = 1 
            GROUP BY link_type
        ''')
        stats['whatsapp_details'] = {row['link_type']: row['count'] for row in cursor.fetchall()}
        
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
        
        # الروابط حسب النوع
        cursor.execute('''
            SELECT platform, link_type, COUNT(*) as count
            FROM links
            WHERE is_active = 1
            GROUP BY platform, link_type
            ORDER BY platform, link_type
        ''')
        stats['by_platform_type'] = {}
        for row in cursor.fetchall():
            platform = row['platform']
            link_type = row['link_type']
            if platform not in stats['by_platform_type']:
                stats['by_platform_type'][platform] = {}
            stats['by_platform_type'][platform][link_type] = row['count']
        
        conn.close()
        return stats
        
    except Exception as e:
        logger.error(f"❌ Error getting link stats: {e}")
        return {}

def export_all_links(format: str = 'txt') -> List[str]:
    """تصدير جميع الروابط في أقسام منفصلة"""
    try:
        # التأكد من وجود مجلد التصدير
        os.makedirs(EXPORT_DIR, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = os.path.join(EXPORT_DIR, f"export_{timestamp}")
        os.makedirs(export_dir, exist_ok=True)
        
        exported_files = []
        
        # الحصول على إحصائيات للتعرف على الأقسام الموجودة
        stats = get_link_stats()
        
        # 1. تصدير روابط تليجرام - قنوات
        telegram_channels = get_links_by_type('telegram', 'channel')
        if telegram_channels:
            filename = f"telegram_channels_{timestamp}.txt"
            filepath = os.path.join(export_dir, filename)
            with open(filepath, 'w', encoding=EXPORT_ENCODING) as f:
                f.write(f"# Telegram Channels\n")
                f.write(f"# Exported: {datetime.now()}\n")
                f.write(f"# Total: {len(telegram_channels)}\n")
                f.write("=" * 50 + "\n\n")
                for link in telegram_channels:
                    f.write(f"{link['url']}\n")
            exported_files.append(filepath)
            logger.info(f"✅ Exported {len(telegram_channels)} Telegram channels")
        
        # 2. تصدير روابط تليجرام - مجموعات عامة
        telegram_public_groups = get_links_by_type('telegram', 'group', 'public')
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
            logger.info(f"✅ Exported {len(telegram_public_groups)} Telegram public groups")
        
        # 3. تصدير روابط تليجرام - مجموعات خاصة
        telegram_private_groups = get_links_by_type('telegram', 'group', 'private')
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
            logger.info(f"✅ Exported {len(telegram_private_groups)} Telegram private groups")
        
        # 4. تصدير روابط تليجرام - طلب انضمام
        telegram_join_request = get_links_by_type('telegram', 'join_request')
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
            logger.info(f"✅ Exported {len(telegram_join_request)} Telegram join requests")
        
        # 5. تصدير روابط تليجرام - بوتات
        telegram_bots = get_links_by_type('telegram', 'bot')
        if telegram_bots:
            filename = f"telegram_bots_{timestamp}.txt"
            filepath = os.path.join(export_dir, filename)
            with open(filepath, 'w', encoding=EXPORT_ENCODING) as f:
                f.write(f"# Telegram Bots\n")
                f.write(f"# Exported: {datetime.now()}\n")
                f.write(f"# Total: {len(telegram_bots)}\n")
                f.write("=" * 50 + "\n\n")
                for link in telegram_bots:
                    f.write(f"{link['url']}\n")
            exported_files.append(filepath)
            logger.info(f"✅ Exported {len(telegram_bots)} Telegram bots")
        
        # 6. تصدير جميع روابط تليجرام
        all_telegram = get_links_by_type('telegram', limit=10000)
        if all_telegram:
            filename = f"telegram_all_{timestamp}.txt"
            filepath = os.path.join(export_dir, filename)
            with open(filepath, 'w', encoding=EXPORT_ENCODING) as f:
                f.write(f"# All Telegram Links\n")
                f.write(f"# Exported: {datetime.now()}\n")
                f.write(f"# Total: {len(all_telegram)}\n")
                f.write("=" * 50 + "\n\n")
                for link in all_telegram:
                    link_type = link['link_type']
                    subtype = link['subtype'] or ''
                    if subtype:
                        f.write(f"# [{link_type}/{subtype}]\n")
                    else:
                        f.write(f"# [{link_type}]\n")
                    f.write(f"{link['url']}\n\n")
            exported_files.append(filepath)
            logger.info(f"✅ Exported {len(all_telegram)} total Telegram links")
        
        # 7. تصدير روابط واتساب
        whatsapp_groups = get_links_by_type('whatsapp', 'group')
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
            logger.info(f"✅ Exported {len(whatsapp_groups)} WhatsApp groups")
        
        # 8. تصدير جميع الروابط في ملف واحد
        all_links = get_all_links(limit=10000)
        if all_links:
            filename = f"all_platforms_{timestamp}.txt"
            filepath = os.path.join(export_dir, filename)
            with open(filepath, 'w', encoding=EXPORT_ENCODING) as f:
                f.write(f"# All Links - All Platforms\n")
                f.write(f"# Exported: {datetime.now()}\n")
                f.write(f"# Total: {len(all_links)}\n")
                f.write("=" * 50 + "\n\n")
                
                current_platform = None
                current_type = None
                
                for link in all_links:
                    platform = link['platform']
                    link_type = link['link_type']
                    subtype = link['subtype'] or ''
                    
                    if platform != current_platform:
                        f.write(f"\n{'='*50}\n")
                        f.write(f"# {platform.upper()} LINKS\n")
                        f.write(f"{'='*50}\n\n")
                        current_platform = platform
                        current_type = None
                    
                    type_label = f"{link_type}"
                    if subtype:
                        type_label += f" ({subtype})"
                    
                    if type_label != current_type:
                        f.write(f"\n## {type_label}\n")
                        current_type = type_label
                    
                    f.write(f"{link['url']}\n")
            
            exported_files.append(filepath)
            logger.info(f"✅ Exported {len(all_links)} total links from all platforms")
        
        # 9. إنشاء ملف إحصائي
        stats_file = os.path.join(export_dir, f"stats_{timestamp}.txt")
        with open(stats_file, 'w', encoding=EXPORT_ENCODING) as f:
            f.write(f"# Export Statistics\n")
            f.write(f"# Generated: {datetime.now()}\n")
            f.write("=" * 50 + "\n\n")
            
            f.write("📊 LINK STATISTICS\n")
            f.write("=" * 30 + "\n")
            
            for platform, count in stats.get('by_platform', {}).items():
                f.write(f"\n{platform.upper()}: {count} links\n")
                
                if platform == 'telegram' and 'telegram_details' in stats:
                    for link_type, subtypes in stats['telegram_details'].items():
                        f.write(f"  └─ {link_type}:\n")
                        for subtype, subcount in subtypes.items():
                            f.write(f"      ├─ {subtype}: {subcount}\n")
                
                elif platform == 'whatsapp' and 'whatsapp_details' in stats:
                    for link_type, count_type in stats['whatsapp_details'].items():
                        f.write(f"  └─ {link_type}: {count_type}\n")
            
            f.write(f"\n\n📈 SUMMARY\n")
            f.write("=" * 30 + "\n")
            f.write(f"Total Links: {stats.get('total_links', 0)}\n")
            f.write(f"Today's Links: {stats.get('today_links', 0)}\n")
        
        exported_files.append(stats_file)
        
        # 10. إنشاء ملف README
        readme_file = os.path.join(export_dir, "README.txt")
        with open(readme_file, 'w', encoding=EXPORT_ENCODING) as f:
            f.write(f"# Export Directory\n")
            f.write(f"# Generated: {datetime.now()}\n")
            f.write("=" * 50 + "\n\n")
            
            f.write("📁 FILE LIST:\n")
            f.write("=" * 30 + "\n")
            for file_path in exported_files:
                filename = os.path.basename(file_path)
                f.write(f"- {filename}\n")
            
            f.write(f"\n\n📊 TOTAL FILES: {len(exported_files)}\n")
            f.write(f"📅 EXPORT DATE: {datetime.now()}\n")
        
        logger.info(f"✅ Exported all links to {export_dir}")
        return exported_files
        
    except Exception as e:
        logger.error(f"❌ Error exporting all links: {e}")
        return []

def export_links_by_type(platform: str, link_type: str = None, subtype: str = None, 
                         format: str = 'txt') -> str:
    """تصدير الروابط حسب المنصة والنوع والتصنيف الفرعي"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT url, title, members_count, collected_at FROM links 
            WHERE platform = ? AND is_active = 1
        '''
        params = [platform]
        
        if link_type:
            query += ' AND link_type = ?'
            params.append(link_type)
        
        if subtype:
            query += ' AND subtype = ?'
            params.append(subtype)
        
        query += ' ORDER BY collected_at DESC'
        
        cursor.execute(query, params)
        links = cursor.fetchall()
        conn.close()
        
        if not links:
            return None
        
        # إنشاء اسم الملف
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if link_type and subtype:
            filename = f"{platform}_{link_type}_{subtype}_{timestamp}.txt"
        elif link_type:
            filename = f"{platform}_{link_type}_{timestamp}.txt"
        else:
            filename = f"{platform}_all_{timestamp}.txt"
        
        filepath = os.path.join(EXPORT_DIR, filename)
        
        # كتابة الروابط إلى الملف
        with open(filepath, 'w', encoding=EXPORT_ENCODING) as f:
            f.write(f"# Exported at: {datetime.now()}\n")
            f.write(f"# Platform: {platform}\n")
            if link_type:
                f.write(f"# Type: {link_type}\n")
            if subtype:
                f.write(f"# Subtype: {subtype}\n")
            f.write(f"# Total links: {len(links)}\n")
            f.write("=" * 50 + "\n\n")
            
            for link in links:
                f.write(f"{link['url']}\n")
                if link['title']:
                    f.write(f"# Title: {link['title']}\n")
                if link['members_count'] > 0:
                    f.write(f"# Members: {link['members_count']}\n")
                f.write(f"# Collected: {link['collected_at']}\n")
                f.write("\n")
        
        logger.info(f"✅ Exported {len(links)} links to {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"❌ Export error: {e}")
        return None

def export_to_csv(platform: str = None, link_type: str = None) -> str:
    """تصدير الروابط إلى ملف CSV"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if platform:
            if link_type:
                cursor.execute('''
                    SELECT url, platform, link_type, subtype, title, 
                           members_count, collected_at 
                    FROM links 
                    WHERE platform = ? AND link_type = ? AND is_active = 1
                    ORDER BY collected_at DESC
                ''', (platform, link_type))
            else:
                cursor.execute('''
                    SELECT url, platform, link_type, subtype, title, 
                           members_count, collected_at 
                    FROM links 
                    WHERE platform = ? AND is_active = 1
                    ORDER BY collected_at DESC
                ''', (platform,))
        else:
            cursor.execute('''
                SELECT url, platform, link_type, subtype, title, 
                       members_count, collected_at 
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
        
        if platform and link_type:
            filename = f"{platform}_{link_type}_{timestamp}.csv"
        elif platform:
            filename = f"{platform}_{timestamp}.csv"
        else:
            filename = f"all_links_{timestamp}.csv"
        
        filepath = os.path.join(EXPORT_DIR, filename)
        
        # كتابة إلى CSV
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
            fieldnames = ['url', 'platform', 'link_type', 'subtype', 'title', 
                         'members_count', 'collected_at']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for link in links:
                writer.writerow(dict(link))
        
        logger.info(f"✅ Exported {len(links)} links to CSV: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"❌ CSV export error: {e}")
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
# Utility Functions
# ======================

def search_links(keyword: str, platform: str = None) -> List[Dict]:
    """بحث في الروابط"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT * FROM links 
            WHERE (url LIKE ? OR title LIKE ? OR description LIKE ?) 
            AND is_active = 1
        '''
        params = [f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"]
        
        if platform:
            query += ' AND platform = ?'
            params.append(platform)
        
        query += ' ORDER BY collected_at DESC LIMIT 100'
        
        cursor.execute(query, params)
        links = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return links
        
    except Exception as e:
        logger.error(f"❌ Search error: {e}")
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
            logger.info(f"✅ Deleted link ID: {link_id}")
            return True
        else:
            logger.warning(f"❌ Link ID {link_id} not found")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error deleting link: {e}")
        return False

def get_recent_links(limit: int = 20) -> List[Dict]:
    """الحصول على أحدث الروابط"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM links 
            WHERE is_active = 1
            ORDER BY collected_at DESC
            LIMIT ?
        ''', (limit,))
        
        links = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return links
        
    except Exception as e:
        logger.error(f"❌ Error getting recent links: {e}")
        return []

# ======================
# Initialization
# ======================

if __name__ == "__main__":
    print("🔧 Initializing database...")
    if init_db():
        print("✅ Database initialized successfully!")
    else:
        print("❌ Failed to initialize database!")
