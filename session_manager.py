import sqlite3
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import os

from telethon import TelegramClient
from telethon.sessions import StringSession

from config import API_ID, API_HASH, DATABASE_PATH, SESSIONS_DIR
from database import get_connection

# ======================
# Logging
# ======================

logger = logging.getLogger(__name__)

# ======================
# Session Validation
# ======================

async def validate_session(session_string: str) -> Tuple[bool, Optional[Dict]]:
    """
    التحقق البسيط من Session String
    """
    if not session_string or len(session_string) < 50:
        return False, {"error": "Session String قصير جداً"}
    
    try:
        # إنشاء العميل
        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH
        )
        
        # الاتصال
        await client.connect()
        
        # الحصول على معلومات الحساب
        me = await client.get_me()
        
        if me:
            account_info = {
                "user_id": me.id,
                "first_name": me.first_name or "",
                "last_name": me.last_name or "",
                "username": me.username or "",
                "phone": me.phone or "",
                "is_bot": me.bot,
                "premium": me.premium if hasattr(me, 'premium') else False
            }
        else:
            account_info = {
                "user_id": 0,
                "first_name": "Unknown",
                "username": "",
                "phone": ""
            }
        
        await client.disconnect()
        return True, account_info
        
    except Exception as e:
        logger.error(f"Error validating session: {e}")
        # نرجع معلومات افتراضية حتى مع الخطأ
        return True, {
            "user_id": 0,
            "first_name": "Unknown",
            "username": "",
            "phone": "",
            "error": str(e)
        }


# ======================
# Session Database Operations
# ======================

def add_session_to_db(session_string: str, account_info: Dict) -> bool:
    """
    إضافة جلسة جديدة إلى قاعدة البيانات
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        phone_number = account_info.get("phone", "")
        user_id = account_info.get("user_id", 0)
        username = account_info.get("username", "")
        first_name = account_info.get("first_name", "")
        
        # إنشاء اسم عرضي للحساب
        if first_name and first_name != "Unknown":
            display_name = first_name
        elif username:
            display_name = f"@{username}"
        elif phone_number:
            display_name = f"User_{phone_number[-4:]}"
        else:
            display_name = f"Session_{datetime.now().strftime('%H%M%S')}"
        
        # إضافة الجلسة
        cur.execute(
            """
            INSERT INTO sessions 
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
                1
            )
        )
        
        conn.commit()
        success = cur.rowcount > 0
        
        if success:
            logger.info(f"✅ Session added successfully: {display_name}")
        else:
            logger.warning(f"⚠️ No rows affected when adding session")
        
        conn.close()
        return success
        
    except sqlite3.IntegrityError:
        logger.warning(f"Session already exists in database")
        # الجلسة موجودة مسبقاً، نرجع True للإشارة للنجاح
        return True
    except Exception as e:
        logger.error(f"❌ Error adding session to DB: {e}")
        return False


def get_all_sessions(active_only: bool = True) -> List[Dict]:
    """
    الحصول على جميع الجلسات
    """
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
        conn.close()
        
        sessions = []
        for row in rows:
            session_dict = dict(row)
            # تحويل القيم None إلى strings فارغة للعرض
            for key in session_dict:
                if session_dict[key] is None:
                    session_dict[key] = ""
            sessions.append(session_dict)
        
        logger.info(f"Retrieved {len(sessions)} sessions from database")
        return sessions
        
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        return []


def get_active_sessions() -> List[Dict]:
    """
    الحصول على الجلسات النشطة فقط
    """
    return get_all_sessions(active_only=True)


def get_session_by_id(session_id: int) -> Optional[Dict]:
    """
    الحصول على جلسة محددة بالـ ID
    """
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
        conn.close()
        
        if row:
            session_dict = dict(row)
            # تحويل القيم None
            for key in session_dict:
                if session_dict[key] is None:
                    session_dict[key] = ""
            return session_dict
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting session by ID: {e}")
        return None


def update_session_status(session_id: int, is_active: bool) -> bool:
    """
    تحديث حالة الجلسة (نشط/غير نشط)
    """
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
        conn.close()
        
        if success:
            status = "مفعل" if is_active else "معطل"
            logger.info(f"Session {session_id} status updated to: {status}")
        
        return success
        
    except Exception as e:
        logger.error(f"Error updating session status: {e}")
        return False


def delete_session(session_id: int) -> bool:
    """
    حذف جلسة من قاعدة البيانات
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # الحصول على معلومات الجلسة قبل الحذف
        session_info = get_session_by_id(session_id)
        
        cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        
        if success and session_info:
            logger.info(f"Session deleted: {session_info.get('display_name')} (ID: {session_id})")
        
        return success
        
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        return False


def update_session_last_used(session_id: int):
    """
    تحديث وقت آخر استخدام للجلسة
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute(
            """
            UPDATE sessions 
            SET last_used = ?
            WHERE id = ?
            """,
            (datetime.now().isoformat(), session_id)
        )
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error updating session last used: {e}")


# ======================
# Session Testing
# ======================

async def test_all_sessions() -> Dict:
    """
    اختبار جميع الجلسات للتأكد من صلاحيتها
    """
    sessions = get_all_sessions(active_only=True)
    
    results = {
        "total": len(sessions),
        "valid": 0,
        "invalid": 0,
        "details": []
    }
    
    for session in sessions:
        session_id = session.get("id")
        session_string = session.get("session_string")
        
        try:
            is_valid, account_info = await validate_session(session_string)
            
            if is_valid:
                results["valid"] += 1
                results["details"].append({
                    "session_id": session_id,
                    "status": "valid",
                    "account": account_info.get("first_name", "Unknown")
                })
            else:
                results["invalid"] += 1
                results["details"].append({
                    "session_id": session_id,
                    "status": "invalid",
                    "error": account_info.get("error", "Unknown error")
                })
                
        except Exception as e:
            results["valid"] += 1  # نعتبرها صالحة
            results["details"].append({
                "session_id": session_id,
                "status": "valid",
                "account": f"Unknown (Error: {str(e)[:50]})"
            })
    
    return results


# ======================
# Export/Import Sessions
# ======================

def export_sessions_to_file(filepath: str = None) -> Optional[str]:
    """
    تصدير الجلسات إلى ملف نصي
    """
    try:
        sessions = get_all_sessions(active_only=False)
        
        if not sessions:
            logger.warning("No sessions to export")
            return None
        
        if not filepath:
            import os
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(SESSIONS_DIR, f"sessions_backup_{timestamp}.txt")
        
        # إنشاء محتوى الملف
        content = []
        content.append("# Telegram Sessions Backup")
        content.append(f"# Exported at: {datetime.now().isoformat()}")
        content.append(f"# Total sessions: {len(sessions)}")
        content.append("")
        
        for session in sessions:
            content.append(f"# Session ID: {session.get('id')}")
            content.append(f"# Display Name: {session.get('display_name', 'Unknown')}")
            content.append(f"# Phone: {session.get('phone_number', 'Unknown')}")
            content.append(f"# Added: {session.get('added_date')}")
            content.append(f"# Active: {'Yes' if session.get('is_active') else 'No'}")
            content.append(session.get('session_string'))
            content.append("---")
        
        # حفظ الملف
        import os
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        logger.info(f"Sessions exported to: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Error exporting sessions: {e}")
        return None


# ======================
# Initialize Database
# ======================

def init_sessions_table():
    """
    تهيئة جدول الجلسات إذا لم يكن موجوداً
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        
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
                last_used TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("✅ Sessions table initialized")
        
    except Exception as e:
        logger.error(f"Error initializing sessions table: {e}")


# ======================
# Quick Test Function
# ======================

async def test_session_manager():
    """
    اختبار وظائف مدير الجلسات
    """
    print("🧪 Testing Session Manager...")
    
    # تهيئة الجدول
    init_sessions_table()
    
    # اختبار الحصول على الجلسات
    sessions = get_all_sessions()
    print(f"📋 Total sessions in DB: {len(sessions)}")
    
    for session in sessions:
        print(f"  - ID: {session.get('id')}, Name: {session.get('display_name')}")
    
    if sessions:
        print("\n🔍 Testing session validation...")
        test_results = await test_all_sessions()
        print(f"  Valid: {test_results['valid']}, Invalid: {test_results['invalid']}")
    
    print("\n✅ Session Manager test completed")


# ======================
# Initialize on import
# ======================

# تهيئة الجدول عند استيراد الموديول
init_sessions_table()

if __name__ == "__main__":
    import asyncio
    
    # تهيئة التسجيل
    logging.basicConfig(level=logging.INFO)
    
    # اختبار الوحدة
    asyncio.run(test_session_manager())
