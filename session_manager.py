from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from database import add_session

async def validate_session(session_string):
    """التحقق من صحة الجلسة وإضافتها"""
    try:
        # إنشاء العميل
        client = TelegramClient(
            StringSession(session_string),
            6,
            "eb06d4abfb49dc3eeb1aeb98ae0f581e"
        )
        
        await client.connect()
        
        # التحقق من التخويل
        if not await client.is_user_authorized():
            await client.disconnect()
            return False, {"error": "الجلسة غير مصرح بها"}
        
        # الحصول على معلومات الحساب
        try:
            me = await client.get_me()
            
            account_info = {
                "phone": me.phone or "",
                "username": me.username or "",
                "user_id": me.id,
                "first_name": me.first_name or "",
                "last_name": me.last_name or ""
            }
            
            # إضافة الجلسة
            session_id = add_session(
                session_string=session_string,
                phone=account_info["phone"],
                username=account_info["username"],
                user_id=account_info["user_id"]
            )
            
            await client.disconnect()
            
            if session_id:
                return True, account_info
            else:
                return False, {"error": "فشل حفظ الجلسة"}
                
        except SessionPasswordNeededError:
            await client.disconnect()
            return False, {"error": "الحساب محمي بكلمة مرور ثنائية"}
        except Exception as e:
            await client.disconnect()
            return False, {"error": f"خطأ في الحساب: {str(e)}"}
            
    except Exception as e:
        return False, {"error": f"خطأ اتصال: {str(e)}"}
