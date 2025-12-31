from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH
from database import add_session, get_sessions, delete_session

async def validate_and_add_session(session_string):
    """التحقق من الجلسة وإضافتها"""
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        # التحقق من التخويل
        if not await client.is_user_authorized():
            await client.disconnect()
            return False, {"error": "الجلسة غير مصرح بها. تأكد من تسجيل الدخول أولاً"}
        
        # الحصول على معلومات الحساب
        me = await client.get_me()
        
        account_info = {
            "phone": me.phone or "",
            "username": me.username or "",
            "user_id": me.id,
            "first_name": me.first_name or "",
            "last_name": me.last_name or "",
        }
        
        await client.disconnect()
        
        # إضافة الجلسة إلى قاعدة البيانات
        success = add_session(
            session_string=session_string,
            phone=account_info["phone"],
            username=account_info["username"],
            user_id=account_info["user_id"],
            first_name=account_info["first_name"],
            last_name=account_info["last_name"]
        )
        
        if success:
            return True, account_info
        else:
            return False, {"error": "فشل حفظ الجلسة في قاعدة البيانات"}
        
    except Exception as e:
        print(f"❌ خطأ في التحقق من الجلسة: {e}")
        return False, {"error": f"خطأ تقني: {str(e)}"}

def get_all_sessions():
    """جلب جميع الجلسات"""
    return get_sessions()

def remove_session(session_id):
    """حذف جلسة"""
    return delete_session(session_id)
