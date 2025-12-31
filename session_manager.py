from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH
from database import add_session

async def validate_and_add_session(session_string):
    """التحقق من الجلسة وإضافتها"""
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        try:
            me = await client.get_me()
            phone = me.phone or ""
            username = me.username or ""
            
            # إضافة الجلسة
            success = add_session(session_string, phone, username)
            
            await client.disconnect()
            return success, {"phone": phone, "username": username}
            
        except Exception as e:
            await client.disconnect()
            # نضيفها حتى لو فشل الحصول على المعلومات
            add_session(session_string, "", "")
            return True, {"phone": "", "username": ""}
            
    except Exception as e:
        return False, {"error": str(e)}
