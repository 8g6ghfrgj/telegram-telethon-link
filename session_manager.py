from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from database import add_session

async def validate_session(session_string):
    """التحقق من صحة الجلسة وإضافتها"""
    print(f"🔍 Validating session: {session_string[:50]}...")
    
    if not session_string or len(session_string) < 50:
        print("❌ Session string too short")
        return False, {"error": "Session String قصير جداً"}
    
    client = None
    try:
        # إنشاء العميل
        client = TelegramClient(
            StringSession(session_string),
            6,
            "eb06d4abfb49dc3eeb1aeb98ae0f581e"
        )
        
        await client.connect()
        print("✅ Connected to Telegram")
        
        # التحقق من التخويل
        if not await client.is_user_authorized():
            print("❌ Session not authorized")
            await client.disconnect()
            return False, {"error": "الجلسة غير مصرح بها"}
        
        # الحصول على معلومات الحساب
        try:
            me = await client.get_me()
            print(f"✅ Got user info: {me.id}")
            
            account_info = {
                "phone": me.phone or "",
                "username": me.username or "",
                "user_id": me.id,
                "first_name": me.first_name or "",
                "last_name": me.last_name or ""
            }
            
            print(f"📱 Phone: {account_info['phone']}")
            print(f"👤 Username: {account_info['username']}")
            print(f"🆔 User ID: {account_info['user_id']}")
            
            # إضافة الجلسة
            session_id = add_session(
                session_string=session_string,
                phone=account_info["phone"],
                username=account_info["username"],
                user_id=account_info["user_id"]
            )
            
            await client.disconnect()
            
            if session_id:
                print(f"✅ Session added to DB with ID: {session_id}")
                return True, account_info
            else:
                print("❌ Failed to add session to DB")
                return False, {"error": "فشل حفظ الجلسة"}
                
        except SessionPasswordNeededError:
            print("❌ 2FA required")
            await client.disconnect()
            return False, {"error": "الحساب محمي بكلمة مرور ثنائية"}
        except Exception as e:
            print(f"❌ Error getting user info: {e}")
            await client.disconnect()
            return False, {"error": f"خطأ في الحساب: {str(e)}"}
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False, {"error": f"خطأ اتصال: {str(e)}"}
