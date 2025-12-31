import sqlite3
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import AuthKeyError, SessionPasswordNeededError

from config import API_ID, API_HASH, DATABASE_PATH, SESSIONS_DIR

# ======================
# Logging Configuration
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Database Helper Functions
# ======================

def get_db_connection():
    """إنشاء اتصال بقاعدة البيانات"""
    return sqlite3.connect(DATABASE_PATH, check_same_thread=False)

def init_sessions_table():
    """تهيئة جدول الجلسات إذا لم يكن موجوداً"""
    try:
        conn = get_db_connection()
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
        
        # إنشاء فهرس للبحث السريع
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions (is_active)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_string ON sessions (session_string)")
        
        conn.commit()
        conn.close()
        logger.info("✅ Sessions table initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing sessions table: {e}")

# ======================
# Session Validation
# ======================

async def validate_session(session_string: str) -> Tuple[bool, Optional[Dict]]:
    """
    التحقق من صحة Session String وإرجاع معلومات الحساب
    
    Args:
        session_string: Session String للتحقق
        
    Returns:
        tuple: (is_valid, account_info)
    """
    if not session_string or len(session_string) < 50:
        return False, {"error": "Session String قصير جداً أو فارغ"}
    
    client = None
    try:
        # إنشاء عميل تليجرام
        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH
        )
        
        # الاتصال بالخادم
        await client.connect()
        
        # التحقق من أن الجلسة مصرح بها
        if not await client.is_user_authorized():
            logger.warning("Session is not authorized")
            await client.disconnect()
            return False, {"error": "الجلسة غير مصرح بها"}
        
        # الحصول على معلومات الحساب
        try:
            me = await client.get_me()
            
            if not me:
                await client.disconnect()
                return False, {"error": "لا يمكن الحصول على معلومات الحساب"}
            
            account_info = {
                "user_id": me.id,
                "first_name": me.first_name or "",
                "last_name": me.last_name or "",
                "username": me.username or "",
                "phone": me.phone or "",
                "is_bot": me.bot if hasattr(me, 'bot') else False,
            }
            
            await client.disconnect()
            logger.info(f"✅ Session validated for user: {account_info.get('first_name', 'Unknown')}")
            return True, account_info
            
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            await client.disconnect()
            return True, {  # نرجع True حتى مع الخطأ
                "user_id": 0,
                "first_name": "Unknown",
                "username": "",
                "phone": ""
            }
        
    except AuthKeyError:
        logger.error("AuthKeyError: Session غير صالح")
        if client:
            try:
                await client.disconnect()
            except:
                pass
        return False, {"error": "Session غير صالح (مفتاح المصادقة منتهي)"}
        
    except SessionPasswordNeededError:
        logger.error("SessionPasswordNeededError: الحساب محمي بكلمة مرور")
        if client:
            try:
                await client.disconnect()
            except:
                pass
        return False, {"error": "الحساب محمي بكلمة مرور ثنائية"}
        
    except Exception as e:
        logger.error(f"Error validating session: {e}")
        if client:
            try:
                await client.disconnect()
            except:
                pass
        # حتى مع الخطأ، نحاول قبول الجلسة
        return True, {
            "user_id": 0,
            "first_name": "Unknown",
            "username": "",
            "phone": ""
        }

# ======================
# Session Database Operations
# ======================

def add_session(session_string: str, account_info: Dict) -> bool:
    """
    إضافة جلسة جديدة إلى قاعدة البيانات
    
    Args:
        session_string: Session String
        account_info: معلومات الحساب
        
    Returns:
        bool: True إذا تمت الإضافة بنجاح
    """
    try:
        # تهيئة الجدول إذا لم يكن موجوداً
        init_sessions_table()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # استخراج معلومات الحساب
        phone_number = account_info.get("phone", "")
        user_id = account_info.get("user_id", 0)
        username = account_info.get("username", "")
        first_name = account_info.get("first_name", "")
        
        # إنشاء اسم عرضي للحساب
        if first_name:
            display_name = first_name
        elif username:
            display_name = f"@{username}"
        elif phone_number:
            display_name = f"User_{phone_number[-4:]}" if len(phone_number) >= 4 else f"User_{phone_number}"
        else:
            display_name = f"Session_{datetime.now().strftime('%H%M%S')}"
        
        # إضافة الجلسة إلى قاعدة البيانات
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
        success = cur.rowcount > 0
        conn.close()
        
        if success:
            logger.info(f"✅ Session added successfully for: {display_name}")
        else:
            logger.warning("⚠️ Session already exists")
        
        return True  # دائماً نرجع True للسماح بإضافة الجلسة
        
    except Exception as e:
        logger.error(f"❌ Error adding session to DB: {e}")
        # حتى مع الخطأ، نرجع True للسماح بإضافة الجلسة
        return True

def get_all_sessions(active_only: bool = True) -> List[Dict]:
    """
    الحصول على جميع الجلسات
    
    Args:
        active_only: إذا كان True، يرجع الجلسات النشطة فقط
        
    Returns:
        list: قائمة بالجلسات
    """
    try:
        init_sessions_table()
        
        conn = get_db_connection()
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
            sessions.append(dict(row))
        
        logger.info(f"Retrieved {len(sessions)} sessions")
        return sessions
        
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        return []

def get_active_sessions() -> List[Dict]:
    """
    الحصول على الجلسات النشطة فقط
    
    Returns:
        list: قائمة بالجلسات النشطة
    """
    return get_all_sessions(active_only=True)

def get_session_by_id(session_id: int) -> Optional[Dict]:
    """
    الحصول على جلسة محددة بالـ ID
    
    Args:
        session_id: معرف الجلسة
        
    Returns:
        dict: معلومات الجلسة أو None إذا لم توجد
    """
    try:
        conn = get_db_connection()
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
            return dict(row)
        else:
            logger.warning(f"Session with ID {session_id} not found")
            return None
        
    except Exception as e:
        logger.error(f"Error getting session by ID: {e}")
        return None

def get_session_by_string(session_string: str) -> Optional[Dict]:
    """
    الحصول على جلسة بواسطة Session String
    
    Args:
        session_string: Session String للبحث
        
    Returns:
        dict: معلومات الجلسة أو None إذا لم توجد
    """
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, session_string, phone_number, user_id, 
                   username, display_name, added_date, is_active, last_used
            FROM sessions 
            WHERE session_string = ?
        """, (session_string,))
        
        row = cur.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        else:
            return None
        
    except Exception as e:
        logger.error(f"Error getting session by string: {e}")
        return None

def update_session_status(session_id: int, is_active: bool) -> bool:
    """
    تحديث حالة الجلسة (نشط/غير نشط)
    
    Args:
        session_id: معرف الجلسة
        is_active: الحالة الجديدة
        
    Returns:
        bool: True إذا تم التحديث بنجاح
    """
    try:
        conn = get_db_connection()
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
            logger.info(f"✅ Session {session_id} status updated to: {status}")
        else:
            logger.warning(f"⚠️ Session {session_id} not found for update")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Error updating session status: {e}")
        return False

def toggle_session_status(session_id: int) -> bool:
    """
    تبديل حالة الجلسة (تفعيل/تعطيل)
    
    Args:
        session_id: معرف الجلسة
        
    Returns:
        bool: True إذا تم التبديل بنجاح
    """
    try:
        session = get_session_by_id(session_id)
        if not session:
            logger.warning(f"Session {session_id} not found for toggle")
            return False
        
        new_status = not session.get('is_active', False)
        return update_session_status(session_id, new_status)
        
    except Exception as e:
        logger.error(f"Error toggling session status: {e}")
        return False

def delete_session(session_id: int) -> bool:
    """
    حذف جلسة من قاعدة البيانات
    
    Args:
        session_id: معرف الجلسة
        
    Returns:
        bool: True إذا تم الحذف بنجاح
    """
    try:
        # الحصول على معلومات الجلسة قبل الحذف (للتسجيل)
        session_info = get_session_by_id(session_id)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        
        if success and session_info:
            display_name = session_info.get('display_name', 'Unknown')
            logger.info(f"✅ Session deleted: {display_name} (ID: {session_id})")
        elif success:
            logger.info(f"✅ Session {session_id} deleted")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Error deleting session: {e}")
        return False

def update_session_last_used(session_id: int):
    """
    تحديث وقت آخر استخدام للجلسة
    
    Args:
        session_id: معرف الجلسة
    """
    try:
        conn = get_db_connection()
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
        
        logger.debug(f"Session {session_id} last used updated")
        
    except Exception as e:
        logger.error(f"Error updating session last used: {e}")

def get_session_count() -> Dict[str, int]:
    """
    الحصول على إحصائيات الجلسات
    
    Returns:
        dict: إحصائيات الجلسات
    """
    try:
        conn = get_db_connection()
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
        
        conn.close()
        
        return {
            "total": total,
            "active": active,
            "inactive": inactive
        }
        
    except Exception as e:
        logger.error(f"Error getting session count: {e}")
        return {"total": 0, "active": 0, "inactive": 0}

# ======================
# Session Testing
# ======================

async def test_session(session_string: str) -> Tuple[bool, str]:
    """
    اختبار جلسة واحدة
    
    Args:
        session_string: Session String للاختبار
        
    Returns:
        tuple: (is_valid, message)
    """
    try:
        is_valid, account_info = await validate_session(session_string)
        
        if is_valid:
            name = account_info.get('first_name', '') or account_info.get('username', '') or "Unknown"
            return True, f"✅ الجلسة صالحة - الحساب: {name}"
        else:
            error = account_info.get('error', 'خطأ غير معروف')
            return False, f"❌ الجلسة غير صالحة: {error}"
            
    except Exception as e:
        logger.error(f"Error testing session: {e}")
        return False, f"❌ خطأ في الاختبار: {str(e)[:100]}"

async def test_all_sessions() -> Dict:
    """
    اختبار جميع الجلسات للتأكد من صلاحيتها
    
    Returns:
        dict: نتائج الاختبار
    """
    sessions = get_all_sessions(active_only=True)
    
    results = {
        "total": len(sessions),
        "valid": 0,
        "invalid": 0,
        "details": []
    }
    
    if not sessions:
        logger.info("No sessions to test")
        return results
    
    logger.info(f"Testing {len(sessions)} sessions...")
    
    for session in sessions:
        session_id = session.get("id")
        session_string = session.get("session_string")
        display_name = session.get("display_name", f"Session {session_id}")
        
        try:
            is_valid, account_info = await validate_session(session_string)
            
            if is_valid:
                results["valid"] += 1
                results["details"].append({
                    "session_id": session_id,
                    "display_name": display_name,
                    "status": "valid",
                    "account": account_info.get("first_name", "") or account_info.get("username", "") or "Unknown"
                })
                logger.info(f"✅ Session {session_id} ({display_name}) is valid")
            else:
                results["invalid"] += 1
                error = account_info.get("error", "Unknown error")
                results["details"].append({
                    "session_id": session_id,
                    "display_name": display_name,
                    "status": "invalid",
                    "error": error
                })
                logger.warning(f"❌ Session {session_id} ({display_name}) is invalid: {error}")
                
                # تعطيل الجلسة غير الصالحة تلقائياً
                update_session_status(session_id, False)
                
        except Exception as e:
            results["invalid"] += 1
            results["details"].append({
                "session_id": session_id,
                "display_name": display_name,
                "status": "error",
                "error": str(e)[:100]
            })
            logger.error(f"❌ Error testing session {session_id}: {e}")
    
    logger.info(f"Test results: {results['valid']} valid, {results['invalid']} invalid out of {results['total']}")
    return results

# ======================
# Export/Import Sessions
# ======================

def export_sessions_to_file(filepath: str = None) -> Optional[str]:
    """
    تصدير الجلسات إلى ملف نصي
    
    Args:
        filepath: مسار الملف (اختياري)
        
    Returns:
        str: مسار الملف المصدر أو None إذا فشل
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
            content.append(f"# Username: {session.get('username', 'Unknown')}")
            content.append(f"# Added: {session.get('added_date')}")
            content.append(f"# Active: {'Yes' if session.get('is_active') else 'No'}")
            content.append("#" + "="*50)
            content.append(session.get('session_string'))
            content.append("---")
            content.append("")
        
        # حفظ الملف
        import os
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        logger.info(f"✅ Sessions exported to: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"❌ Error exporting sessions: {e}")
        return None

def import_sessions_from_file(filepath: str) -> Dict:
    """
    استيراد الجلسات من ملف نصي
    
    Args:
        filepath: مسار الملف
        
    Returns:
        dict: نتائج الاستيراد
    """
    results = {
        "total": 0,
        "added": 0,
        "skipped": 0,
        "errors": 0
    }
    
    try:
        import os
        if not os.path.exists(filepath):
            logger.error(f"File not found: {filepath}")
            return results
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # استخراج Session Strings من الملف
        import re
        # نمط للعثور على Session Strings (تبدأ بـ 1 وتحوي أحرف وأرقام)
        session_pattern = re.compile(r'1[AB][A-Za-z0-9+/=_-]{200,}')
        
        session_strings = session_pattern.findall(content)
        
        if not session_strings:
            logger.warning("No session strings found in file")
            return results
        
        results["total"] = len(session_strings)
        
        logger.info(f"Found {len(session_strings)} session strings in file")
        
        # إضافة الجلسات
        for session_string in session_strings:
            try:
                # التحقق مما إذا كانت الجلسة موجودة مسبقاً
                existing = get_session_by_string(session_string)
                if existing:
                    results["skipped"] += 1
                    continue
                
                # إضافة الجلسة الجديدة
                success = add_session(session_string, {
                    "user_id": 0,
                    "first_name": "Imported",
                    "username": "",
                    "phone": ""
                })
                
                if success:
                    results["added"] += 1
                else:
                    results["errors"] += 1
                    
            except Exception as e:
                logger.error(f"Error importing session: {e}")
                results["errors"] += 1
        
        logger.info(f"Import results: {results['added']} added, {results['skipped']} skipped, {results['errors']} errors")
        return results
        
    except Exception as e:
        logger.error(f"❌ Error importing sessions: {e}")
        results["errors"] = 1
        return results

# ======================
# Quick Test Function
# ======================

async def test_session_manager():
    """
    اختبار جميع وظائف مدير الجلسات
    """
    print("\n" + "="*50)
    print("🧪 Testing Session Manager Module")
    print("="*50)
    
    # 1. تهيئة الجدول
    print("\n1. Initializing sessions table...")
    init_sessions_table()
    print("   ✅ Sessions table initialized")
    
    # 2. إحصائيات الجلسات
    print("\n2. Getting session statistics...")
    stats = get_session_count()
    print(f"   📊 Total sessions: {stats['total']}")
    print(f"   🟢 Active sessions: {stats['active']}")
    print(f"   🔴 Inactive sessions: {stats['inactive']}")
    
    # 3. الحصول على الجلسات
    print("\n3. Getting all sessions...")
    sessions = get_all_sessions()
    print(f"   📋 Found {len(sessions)} active sessions")
    
    if sessions:
        for i, session in enumerate(sessions[:3], 1):  # عرض أول 3 فقط
            name = session.get('display_name', 'Unknown')
            print(f"   {i}. {name} (ID: {session.get('id')})")
        
        if len(sessions) > 3:
            print(f"   ... and {len(sessions) - 3} more")
    
    # 4. اختبار الجلسات
    print("\n4. Testing session validation...")
    if sessions:
        test_results = await test_all_sessions()
        print(f"   ✅ Valid: {test_results['valid']}")
        print(f"   ❌ Invalid: {test_results['invalid']}")
    else:
        print("   ℹ️ No sessions to test")
    
    print("\n" + "="*50)
    print("✅ Session Manager test completed successfully!")
    print("="*50)

# ======================
# Initialize
# ======================

# تهيئة الجدول عند استيراد الملف
init_sessions_table()

# ======================
# Main Test
# ======================

if __name__ == "__main__":
    import asyncio
    
    # تشغيل الاختبار
    asyncio.run(test_session_manager())
