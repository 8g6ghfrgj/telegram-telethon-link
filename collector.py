import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message
import re
from database import get_sessions, save_link

logger = logging.getLogger(__name__)

# أنماط الروابط
TELEGRAM_PATTERNS = [
    r"https?://t\.me/[a-zA-Z0-9_]+",
    r"https?://telegram\.me/[a-zA-Z0-9_]+",
    r"https?://t\.me/joinchat/[a-zA-Z0-9_-]+",
    r"https?://t\.me/\+[a-zA-Z0-9]+"
]

WHATSAPP_PATTERNS = [
    r"https?://chat\.whatsapp\.com/[a-zA-Z0-9]+",
    r"https?://wa\.me/\d+"
]

def extract_links(text):
    """استخراج الروابط من النص"""
    links = []
    
    # جمع روابط التليجرام
    for pattern in TELEGRAM_PATTERNS:
        links.extend(re.findall(pattern, text or ""))
    
    # جمع روابط الواتساب
    for pattern in WHATSAPP_PATTERNS:
        links.extend(re.findall(pattern, text or ""))
    
    return list(set(links))

class LinkCollector:
    def __init__(self):
        self.is_collecting = False
        self.clients = []
    
    async def start_collection(self):
        """بدء جمع الروابط"""
        if self.is_collecting:
            return False
        
        self.is_collecting = True
        sessions = get_sessions()
        
        if not sessions:
            logger.error("No active sessions found")
            return False
        
        # جمع من كل جلسة
        tasks = []
        for session in sessions:
            task = asyncio.create_task(self.collect_from_session(session))
            tasks.append(task)
        
        # تشغيل جميع المهام
        await asyncio.gather(*tasks, return_exceptions=True)
        return True
    
    async def collect_from_session(self, session_data):
        """الجمع من جلسة واحدة"""
        session_string = session_data.get('session_string')
        if not session_string:
            return
        
        client = None
        try:
            # إنشاء العميل
            client = TelegramClient(
                StringSession(session_string),
                6,  # API_ID العام
                "eb06d4abfb49dc3eeb1aeb98ae0f581e"  # API_HASH العام
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error("Session not authorized")
                return
            
            # جمع من المحادثات
            await self.collect_from_chats(client, session_data['id'])
            
            # الاستماع للجديد
            await self.listen_for_new_messages(client, session_data['id'])
            
        except Exception as e:
            logger.error(f"Error in session {session_data.get('id')}: {e}")
        finally:
            if client:
                await client.disconnect()
    
    async def collect_from_chats(self, client, session_id):
        """جمع الروابط من جميع المحادثات"""
        try:
            async for dialog in client.iter_dialogs(limit=100):
                try:
                    # جمع من الرسائل القديمة (آخر 1000 رسالة)
                    async for message in client.iter_messages(
                        dialog.entity, 
                        limit=1000,
                        reverse=True
                    ):
                        if not self.is_collecting:
                            return
                        
                        await self.process_message(message, session_id)
                        
                except Exception as e:
                    logger.debug(f"Error in dialog {dialog.name}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error collecting from chats: {e}")
    
    async def listen_for_new_messages(self, client, session_id):
        """الاستماع للرسائل الجديدة"""
        @client.on(events.NewMessage)
        async def handler(event):
            if self.is_collecting:
                await self.process_message(event.message, session_id)
        
        # البقاء في الحلقة حتى التوقف
        while self.is_collecting:
            await asyncio.sleep(1)
    
    async def process_message(self, message: Message, session_id):
        """معالجة رسالة واستخراج الروابط"""
        try:
            # استخراج الروابط من النص
            text = message.text or message.message or ""
            links = extract_links(text)
            
            # استخراج من الكابتشن
            if hasattr(message, 'caption') and message.caption:
                links.extend(extract_links(message.caption))
            
            # حفظ الروابط
            for link in set(links):
                # تحديد المنصة
                platform = "telegram" if "t.me" in link or "telegram.me" in link else "whatsapp"
                
                # تحديد النوع
                link_type = "channel" if "/joinchat/" not in link and "/+" not in link else "group"
                
                # حفظ الرابط
                save_link(
                    url=link,
                    platform=platform,
                    link_type=link_type,
                    source=f"session_{session_id}"
                )
            
        except Exception as e:
            logger.debug(f"Error processing message: {e}")
    
    def stop_collection(self):
        """إيقاف الجمع"""
        self.is_collecting = False

# كائن عام
collector = LinkCollector()
