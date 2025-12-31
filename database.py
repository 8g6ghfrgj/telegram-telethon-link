import sqlite3
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import os

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = "links.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        """الحصول على اتصال بقاعدة البيانات"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """تهيئة قاعدة البيانات وإنشاء الجداول"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        # جدول الجلسات
        cur.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_string TEXT NOT NULL,
                phone_number TEXT,
                username TEXT,
                user_id INTEGER,
                first_name TEXT,
                display_name TEXT,
                added_date TEXT NOT NULL,
                last_used TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')
        
        # جدول الروابط
        cur.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,  -- 'telegram' أو 'whatsapp'
                link_type TEXT,         -- النوع: channel, group, bot, message, phone
                url TEXT NOT NULL UNIQUE,
                title TEXT,
                description TEXT,
                members_count INTEGER,
                is_active INTEGER DEFAULT 1,
                collected_date TEXT NOT NULL,
                collected_by INTEGER,
                last_checked TEXT,
                metadata TEXT,
                FOREIGN KEY (collected_by) REFERENCES sessions(id)
            )
        ''')
        
        # جدول عمليات الجمع
        cur.execute('''
            CREATE TABLE IF NOT EXISTS collection_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT,  -- 'running', 'paused', 'stopped', 'completed'
                links_collected INTEGER DEFAULT 0,
                errors_count INTEGER DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        ''')
        
        # فهارس لتحسين الأداء
        cur.execute('CREATE INDEX IF NOT EXISTS idx_links_platform ON links(platform)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_links_type ON links(link_type)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_links_url ON links(url)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)')
        
        conn.commit()
        conn.close()
        
        logger.info("Database initialized successfully")
    
    # ==================== وظائف الجلسات ====================
    
    def add_session(self, session_data: Dict) -> int:
        """إضافة جلسة جديدة"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('''
                INSERT INTO sessions 
                (session_string, phone_number, username, user_id, 
                 first_name, display_name, added_date, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_data.get('session_string'),
                session_data.get('phone_number'),
                session_data.get('username'),
                session_data.get('user_id'),
                session_data.get('first_name'),
                session_data.get('display_name'),
                datetime.now().isoformat(),
                session_data.get('is_active', 1)
            ))
            
            session_id = cur.lastrowid
            conn.commit()
            
            return session_id
            
        except Exception as e:
            logger.error(f"Error adding session: {e}")
            conn.rollback()
            return -1
        finally:
            conn.close()
    
    def get_session_by_id(self, session_id: int) -> Optional[Dict]:
        """الحصول على جلسة بواسطة المعرف"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('''
                SELECT * FROM sessions WHERE id = ?
            ''', (session_id,))
            
            row = cur.fetchone()
            if row:
                return dict(row)
            return None
            
        finally:
            conn.close()
    
    def update_session_status(self, session_id: int, is_active: bool) -> bool:
        """تحديث حالة الجلسة"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('''
                UPDATE sessions 
                SET is_active = ?, last_used = ?
                WHERE id = ?
            ''', (
                1 if is_active else 0,
                datetime.now().isoformat(),
                session_id
            ))
            
            conn.commit()
            return cur.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error updating session status: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    # ==================== وظائف الروابط ====================
    
    def add_link(self, link_data: Dict) -> bool:
        """إضافة رابط جديد"""
        from link_utils import clean_link
        
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            # تنظيف الرابط
            url = clean_link(link_data.get('url', ''))
            if not url:
                return False
            
            cur.execute('''
                INSERT OR IGNORE INTO links 
                (platform, link_type, url, title, description, 
                 members_count, is_active, collected_date, 
                 collected_by, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                link_data.get('platform'),
                link_data.get('link_type'),
                url,
                link_data.get('title', ''),
                link_data.get('description', ''),
                link_data.get('members_count', 0),
                link_data.get('is_active', 1),
                datetime.now().isoformat(),
                link_data.get('collected_by'),
                link_data.get('metadata', '{}')
            ))
            
            conn.commit()
            return cur.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error adding link: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_links_by_type(self, platform: str, link_type: str = None, 
                         limit: int = 50, offset: int = 0) -> List[Dict]:
        """الحصول على الروابط حسب النوع"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            query = '''
                SELECT * FROM links 
                WHERE platform = ?
            '''
            params = [platform]
            
            if link_type and link_type != 'all':
                query += ' AND link_type = ?'
                params.append(link_type)
            
            query += ' ORDER BY id DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            
            cur.execute(query, params)
            
            rows = cur.fetchall()
            return [dict(row) for row in rows]
            
        finally:
            conn.close()
    
    def get_link_stats(self) -> Dict:
        """الحصول على إحصائيات الروابط"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            stats = {}
            
            # الإحصائيات حسب المنصة
            cur.execute('''
                SELECT platform, COUNT(*) as count 
                FROM links 
                GROUP BY platform
            ''')
            
            by_platform = {}
            for row in cur.fetchall():
                by_platform[row[0]] = row[1]
            stats['by_platform'] = by_platform
            
            # إحصائيات التليجرام حسب النوع
            cur.execute('''
                SELECT link_type, COUNT(*) as count 
                FROM links 
                WHERE platform = 'telegram'
                GROUP BY link_type
            ''')
            
            telegram_by_type = {}
            for row in cur.fetchall():
                if row[0]:
                    telegram_by_type[row[0]] = row[1]
            stats['telegram_by_type'] = telegram_by_type
            
            # إحصائيات الواتساب حسب النوع
            cur.execute('''
                SELECT link_type, COUNT(*) as count 
                FROM links 
                WHERE platform = 'whatsapp'
                GROUP BY link_type
            ''')
            
            whatsapp_by_type = {}
            for row in cur.fetchall():
                if row[0]:
                    whatsapp_by_type[row[0]] = row[1]
            stats['whatsapp_by_type'] = whatsapp_by_type
            
            # العدد الإجمالي
            cur.execute('SELECT COUNT(*) FROM links')
            stats['total'] = cur.fetchone()[0]
            
            # الروابط النشطة
            cur.execute('SELECT COUNT(*) FROM links WHERE is_active = 1')
            stats['active'] = cur.fetchone()[0]
            
            return stats
            
        finally:
            conn.close()
    
    def export_links_by_type(self, platform: str, link_type: str = None) -> Optional[str]:
        """تصدير الروابط إلى ملف نصي"""
        import os
        from config import EXPORT_DIR
        
        try:
            links = self.get_links_by_type(platform, link_type, limit=10000)
            
            if not links:
                return None
            
            # إنشاء اسم الملف
            filename_parts = [platform]
            if link_type and link_type != 'all':
                filename_parts.append(link_type)
            filename = f"{'_'.join(filename_parts)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join(EXPORT_DIR, filename)
            
            # كتابة الروابط في الملف
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link['url']}\n")
            
            return filepath
            
        except Exception as e:
            logger.error(f"Error exporting links: {e}")
            return None
    
    def update_link_status(self, url: str, is_active: bool) -> bool:
        """تحديث حالة الرابط"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('''
                UPDATE links 
                SET is_active = ?, last_checked = ?
                WHERE url = ?
            ''', (
                1 if is_active else 0,
                datetime.now().isoformat(),
                url
            ))
            
            conn.commit()
            return cur.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error updating link status: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def delete_links_by_platform(self, platform: str) -> int:
        """حذف جميع روابط منصة معينة"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('DELETE FROM links WHERE platform = ?', (platform,))
            deleted_count = cur.rowcount
            conn.commit()
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error deleting links: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()

# وظائف الاتصال للتوافق مع الكود القديم
def get_connection():
    """الحصول على اتصال بقاعدة البيانات (للتوافق)"""
    db = Database()
    return db.get_connection()

def init_db():
    """تهيئة قاعدة البيانات (للتوافق)"""
    db = Database()
    return True

# إنشاء كائن قاعدة البيانات
db_instance = Database()
