import sqlite3
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from database import get_connection

# ======================
# Logging
# ======================

logger = logging.getLogger(__name__)

# ======================
# Session Validation (مبسطة جداً)
# ======================

async def validate_session(session_string: str) -> Tuple[bool, Optional[Dict]]:
    """
    التحقق البسيط من Session String
    فقط التحقق من التنسيق
    """
    if not session_string or len(session_string) < 50:
        return False, {"error": "Session String قصير جداً"}
    
    # التحقق من أن Session String يبدأ بـ 1 (تنسيق Telethon)
    if not session_string.startswith("1"):
        return False, {"error": "تنسيق Session String غير صحيح"}
    
    # قبول الجلسة
    return True, {
        "user_id": 0,
        "first_name": "User",
        "username": "",
        "phone": "",
        "is_bot": False,
        "premium": False
    }


# ======================
# Session Database Operations
# ======================

def add_session_to_db(session_string: str, account_info: Dict = None) -> bool:
    """
    إضافة جلسة جديدة إلى قاعدة البيانات
    """
    try:
        from database import add_session
        
        # تنظيف Session String
        cleaned_session = session_string.strip()
        
        # استخدام دالة add_session من database.py
        phone_number = account_info.get("phone", "") if account_info else ""
        success = add_session(cleaned_session, phone_number)
        
        if success:
            logger.info(f"✅ Session added successfully: {cleaned_session[:30]}...")
        else:
            logger.info(f"ℹ️ Session already exists or error: {cleaned_session[:30]}...")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Error in add_session_to_db: {e}")
        return False


def get_all_sessions(active_only: bool = True) -> List[Dict]:
    """
    الحصول على جميع الجلسات
    """
    try:
        from database import get_sessions
        return get_sessions(active_only)
        
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        return []


def get_active_sessions() -> List[Dict]:
    """
    الحصول على الجلسات النشطة فقط
    """
    return get_all_sessions(active_only=True)


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
    اختبار جميع الجلسات
    """
    sessions = get_all_sessions(active_only=True)
    
    results = {
        "total": len(sessions),
        "valid": len(sessions),
        "invalid": 0,
        "details": []
    }
    
    for session in sessions:
        session_id = session.get("id")
        display_name = session.get("display_name", f"Session_{session_id}")
        
        results["details"].append({
            "session_id": session_id,
            "status": "valid",
            "display_name": display_name
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
