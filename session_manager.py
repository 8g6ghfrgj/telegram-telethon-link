import sqlite3
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import AuthKeyError, SessionPasswordNeededError

from config import BOT_TOKEN, DATABASE_URL, SESSIONS_DIR
from database import get_connection

# Logging
logger = logging.getLogger(__name__)

# Session Validation
async def validate_session(session_string: str) -> Tuple[bool, Optional[Dict]]:
    """
    التحقق من صحة Session String
    وإرجاع معلومات الحساب
    """
    client = None
    try:
        # استخدام API ID و HASH من config (إذا موجود) أو None للبوت
        from config import API_ID, API_HASH
        api_id = API_ID if hasattr(API_ID, '__len__') else None
        api_hash = API_HASH if hasattr(API_HASH, '__len__') else None
        
        client = TelegramClient(
            StringSession(session_string),
            api_id,
            api_hash
        )

        await client.connect()  
          
        if not await client.is_user_authorized():  
            return False, {"error": "Session غير مصرح به"}  
          
        # الحصول على معلومات الحساب  
        me = await client.get_me()  
          
        account_info = {  
            "user_id": me.id,  
            "first_name": me.first_name,  
            "last_name": me.last_name,  
            "username": me.username,  
            "phone": me.phone,  
            "is_bot": me.bot,  
            "premium": me.premium if hasattr(me, 'premium') else False  
        }  
          
        await client.disconnect()  
        return True, account_info  
          
    except AuthKeyError:  
        logger.error("AuthKeyError: Session غير صالح")  
        return False, {"error": "Session غير صالح (AuthKeyError)"}  
    except SessionPasswordNeededError:  
        logger.error("SessionPasswordNeededError: الحساب محمي بكلمة مرور")  
        return False, {"error": "الحساب محمي بكلمة مرور ثنائية"}  
    except Exception as e:  
        logger.error(f"Error validating session: {e}")  
        if client:  
            try:  
                await client.disconnect()  
            except:  
                pass  
        return False, {"error": str(e)}

# Session Database Operations
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
        display_name = first_name or username or f"User_{user_id}"  
          
        cur.execute(  
            """  
            INSERT OR IGNORE INTO sessions   
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
            logger.info(f"Session added for user: {display_name} (ID: {user_id})")  
        else:  
            logger.warning(f"Session already exists for user: {display_name}")  
          
        conn.close()  
        return success  
          
    except Exception as e:  
        logger.error(f"Error adding session to DB: {e}")  
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

        # الحصول على معلومات الجلسة قبل الحذف (للتسجيل)  
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

# Session Testing
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
                  
                # تعطيل الجلسة غير الصالحة تلقائياً  
                update_session_status(session_id, False)  
                  
        except Exception as e:  
            results["invalid"] += 1  
            results["details"].append({  
                "session_id": session_id,  
                "status": "error",  
                "error": str(e)  
            })  
            logger.error(f"Error testing session {session_id}: {e}")  
    
    return results

# Export/Import Sessions
def export_sessions_to_file(filepath: str = None) -> Optional[str]:
    """
    تصدير الجلسات إلى ملف نصي (مشفر)
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

# Quick Test Function
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

# Initialize
if __name__ == "__main__":
    import asyncio

    # تهيئة التسجيل  
    logging.basicConfig(level=logging.INFO)  
    
    # اختبار الوحدة  
    asyncio.run(test_session_manager())
