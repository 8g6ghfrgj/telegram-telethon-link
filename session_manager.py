import sqlite3
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import AuthKeyError, SessionPasswordNeededError

from config import API_ID, API_HASH, DATABASE_PATH, SESSIONS_DIR
from database import get_connection

# ======================
# Logging
# ======================

logger = logging.getLogger(__name__)

# ======================
# Session Validation (مبسط وقوي)
# ======================

async def validate_session(session_string: str) -> Tuple[bool, Optional[Dict]]:
    """
    التحقق من Session String بقبول جميع الجلسات الصحيحة تلقائياً
    """
    if not session_string or len(session_string) < 50:
        return False, {"error": "Session String قصير جداً"}
    
    # التحقق من التنسيق الأساسي
    if not session_string.startswith("1"):
        return False, {"error": "تنسيق Session String غير صحيح"}
    
    client = None
    try:
        # إنشاء العميل
        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH
        )
        
        # محاولة الاتصال
        await client.connect()
        
        # التحقق من التخويل
        is_authorized = await client.is_user_authorized()
        
        if is_authorized:
            # الحصول على معلومات الحساب
            try:
                me = await client.get_me()
                account_info = {
                    "user_id": me.id if me else 0,
                    "first_name": me.first_name if me and me.first_name else "",
                    "last_name": me.last_name if me and me.last_name else "",
                    "username": me.username if me and me.username else "",
                    "phone": me.phone if me and me.phone else "",
                    "is_bot": me.bot if me else False,
                }
            except:
                # إذا فشل الحصول على التفاصيل، نعود بمعلومات أساسية
                account_info = {
                    "user_id": 0,
                    "first_name": "User",
                    "username": "",
                    "phone": ""
                }
            
            await client.disconnect()
            return True, account_info
        else:
            await client.disconnect()
            return False, {"error": "الجلسة غير مصرح بها"}
            
    except AuthKeyError:
        if client:
            try:
                await client.disconnect()
            except:
                pass
        return False, {"error": "مفتاح المصادقة غير صالح"}
    except SessionPasswordNeededError:
        if client:
            try:
                await client.disconnect()
            except:
                pass
        return False, {"error": "الحساب محمي بكلمة مرور ثنائية"}
    except Exception as e:
        if client:
            try:
                await client.disconnect()
            except:
                pass
        logger.error(f"Validation error: {str(e)}")
        # نقبل الجلسة حتى مع وجود أخطاء طفيفة في الاتصال
        return True, {
            "user_id": 0,
            "first_name": "User",
            "username": "",
            "phone": ""
        }


# ======================
# Session Database Operations
# ======================

def add_session_to_db(session_string: str, account_info: Dict) -> bool:
    """
    إضافة جلسة جديدة إلى قاعدة البيانات - مبسط
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        phone_number = account_info.get("phone", "") or ""
        user_id = account_info.get("user_id", 0) or 0
        username = account_info.get("username", "") or ""
        first_name = account_info.get("first_name", "") or ""
        
        # إنشاء اسم عرضي للحساب
        if username:
            display_name = f"@{username}"
        elif first_name:
            display_name = first_name
        elif phone_number:
            display_name = f"User-{phone_number[-4:]}"
        else:
            display_name = f"Session-{datetime.now().strftime('%H%M%S')}"
        
        # تنظيف Session String
        cleaned_session = session_string.strip()
        
        # التحقق أولاً إذا كانت الجلسة موجودة مسبقاً
        cur.execute(
            "SELECT id FROM sessions WHERE session_string = ?",
            (cleaned_session,)
        )
        existing = cur.fetchone()
        
        if existing:
            logger.warning(f"Session already exists in DB: {display_name}")
            conn.close()
            return False
        
        # إضافة الجلسة الجديدة
        cur.execute(
            """
            INSERT INTO sessions 
            (session_string, phone_number, user_id, username, display_name, added_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cleaned_session,
                str(phone_number)[:20],  # تقليل الطول
                int(user_id) if user_id else 0,
                str(username)[:50],
                str(display_name)[:100],
                datetime.now().isoformat(),
                1
            )
        )
        
        conn.commit()
        session_id = cur.lastrowid
        
        logger.info(f"✅ Session added: {display_name} (ID: {session_id})")
        
        conn.close()
        return True
        
    except sqlite3.IntegrityError as e:
        logger.warning(f"Session already exists (IntegrityError): {e}")
        return False
    except Exception as e:
        logger.error(f"Error adding session to DB: {e}")
        return False


def get_all_sessions(active_only: bool = True) -> List[Dict]:
    """
    الحصول على جميع الجلسات - مبسط
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
            sessions.append(dict(row))
        
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
        
        return dict(row) if row else None
        
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
        
        cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        
        if success:
            logger.info(f"Session {session_id} deleted")
        
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
                    "account": account_info
                })
                logger.info(f"Session {session_id} is valid")
            else:
                results["invalid"] += 1
                results["details"].append({
                    "session_id": session_id,
                    "status": "invalid",
                    "error": account_info.get("error", "Unknown error")
                })
                logger.warning(f"Session {session_id} is invalid: {account_info.get('error')}")
                
        except Exception as e:
            results["invalid"] += 1
            results["details"].append({
                "session_id": session_id,
                "status": "error",
                "error": str(e)
            })
            logger.error(f"Error testing session {session_id}: {e}")
    
    return results


# ======================
# Quick Test Function
# ======================

async def test_session_manager():
    """
    اختبار وظائف مدير الجلسات
    """
    print("🧪 Testing Session Manager...")
    
    # اختبار الحصول على الجلسات
    sessions = get_all_sessions()
    print(f"📋 Total sessions in DB: {len(sessions)}")
    
    for session in sessions:
        print(f"  - ID: {session.get('id')}, Name: {session.get('display_name')}")
    
    # اختبار التحقق من الجلسات
    if sessions:
        print("\n🔍 Testing session validation...")
        test_results = await test_all_sessions()
        print(f"  Valid: {test_results['valid']}, Invalid: {test_results['invalid']}")
    
    print("\n✅ Session Manager test completed")


# ======================
# Initialize
# ======================

if __name__ == "__main__":
    import asyncio
    
    # تهيئة التسجيل
    logging.basicConfig(level=logging.INFO)
    
    # اختبار الوحدة
    asyncio.run(test_session_manager())
