import asyncio
import re
import logging
from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message, Channel, Chat
from telethon.errors import FloodWaitError

from database import get_sessions, save_link

logger = logging.getLogger(__name__)

# ======================
# الأنماط والتصنيف
# ======================

TELEGRAM_REGEX = re.compile(
    r'(https?://(?:t\.me|telegram\.me)/[^\s<>"\'()]+)',
    re.IGNORECASE
)

WHATSAPP_REGEX = re.compile(
    r'(https?://(?:chat\.whatsapp\.com|wa\.me)/[^\s<>"\'()]+)',
    re.IGNORECASE
)

def extract_all_links(text):
    """استخراج جميع الروابط من النص"""
    if not text:
        return []
    
    links = []
    
    # تليجرام
    telegram_links = TELEGRAM_REGEX.findall(text)
    links.extend(telegram_links)
    
    # واتساب
    whatsapp_links = WHATSAPP_REGEX.findall(text)
    links.extend(whatsapp_links)
    
    return list(set(links))

def classify_telegram_link(url):
    """تصنيف رابط تليجرام"""
    url_lower = url.lower()
    
    if 'joinchat' in url_lower:
        return 'private_group'
    elif url_lower.startswith('https://t.me/+'):
        return 'public_group'
    elif '/c/' in url_lower:
        return 'message'
    elif re.search(r'/bot$|\?start=', url_lower):
        return 'bot'
    elif re.search(r't\.me/[a-z0-9_]+$', url_lower):
        return 'channel'
    else:
        return 'unknown'

def clean_link(url):
    """تنظيف الرابط"""
    if not url:
        return url
    
    # إزالة المسافات والنجوم
    url = url.strip().replace('*', '').replace(' ', '')
    
    # إزالة علامات الترقيم الملتصقة
    url = re.sub(r'[.,;!?]+$', '', url)
    
    return url

class SimpleCollector:
    def __init__(self):
        self.is_collecting = False
        self.stats = {
            'telegram': 0,
            'whatsapp': 0,
            'channels': 0,
            'groups': 0,
            'bots': 0,
            'messages': 0
        }
    
    async def start_collection(self):
        """بدء الجمع - نسخة مبسطة تعمل"""
        if self.is_collecting:
            return False
        
        logger.info("🚀 Starting SIMPLE collection...")
        self.is_collecting = True
        self.stats = {'telegram': 0, 'whatsapp': 0, 'channels': 0, 'groups': 0, 'bots': 0, 'messages': 0}
        
        sessions = get_sessions()
        if not sessions:
            logger.error("No active sessions!")
            self.is_collecting = False
            return False
        
        logger.info(f"Found {len(sessions)} sessions")
        
        # جمع من كل جلسة
        for session in sessions:
            await self.collect_from_session(session)
        
        logger.info(f"✅ Collection finished. Stats: {self.stats}")
        self.is_collecting = False
        return True
    
    async def collect_from_session(self, session_data):
        """الجمع من جلسة واحدة"""
        session_id = session_data['id']
        session_string = session_data['session_string']
        
        logger.info(f"📱 Processing session {session_id}")
        
        client = None
        try:
            # إنشاء العميل
            client = TelegramClient(
                StringSession(session_string),
                6,
                "eb06d4abfb49dc3eeb1aeb98ae0f581e"
            )
            
            await client.connect()
            
            # التحقق
            if not await client.is_user_authorized():
                logger.error(f"Session {session_id} not authorized")
                return
            
            # جمع من الدردشات
            await self.collect_dialogs(client, session_id)
            
            await client.disconnect()
            logger.info(f"✅ Finished session {session_id}")
            
        except FloodWaitError as e:
            logger.warning(f"Flood wait: {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Error in session {session_id}: {e}")
        finally:
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
    
    async def collect_dialogs(self, client, session_id):
        """جمع من الدردشات"""
        try:
            async for dialog in client.iter_dialogs(limit=50):  # 50 محادثة فقط
                if not self.is_collecting:
                    break
                
                try:
                    chat_title = dialog.name or "Unknown"
                    await self.collect_messages(client, dialog.entity, session_id, chat_title)
                    await asyncio.sleep(1)  # تأخير لمنع Flood
                    
                except Exception as e:
                    logger.debug(f"Error in {chat_title}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error collecting dialogs: {e}")
    
    async def collect_messages(self, client, chat, session_id, chat_title):
        """جمع الرسائل من محادثة"""
        try:
            # جمع 200 رسالة فقط من كل محادثة
            async for message in client.iter_messages(chat, limit=200):
                if not self.is_collecting:
                    return
                
                await self.process_message(message, session_id, chat_title)
                
        except Exception as e:
            logger.debug(f"Error collecting messages: {e}")
    
    async def process_message(self, message: Message, session_id, chat_title):
        """معالجة رسالة واحدة"""
        try:
            # جمع الروابط من النص
            text = message.text or message.message or ""
            
            # جمع من الكابشن
            if hasattr(message, 'caption') and message.caption:
                text += " " + message.caption
            
            links = extract_all_links(text)
            
            # حفظ الروابط
            for raw_link in links:
                link = clean_link(raw_link)
                if not link:
                    continue
                
                # تحديد المنصة
                if 't.me' in link or 'telegram.me' in link:
                    platform = 'telegram'
                    link_type = classify_telegram_link(link)
                    
                    # تحديث الإحصائيات
                    self.stats['telegram'] += 1
                    if link_type == 'channel':
                        self.stats['channels'] += 1
                    elif 'group' in link_type:
                        self.stats['groups'] += 1
                    elif link_type == 'bot':
                        self.stats['bots'] += 1
                    elif link_type == 'message':
                        self.stats['messages'] += 1
                        
                elif 'whatsapp.com' in link or 'wa.me' in link:
                    platform = 'whatsapp'
                    link_type = 'group' if 'chat.whatsapp.com' in link else 'phone'
                    self.stats['whatsapp'] += 1
                else:
                    continue
                
                # حفظ الرابط
                save_link(
                    url=link,
                    platform=platform,
                    link_type=link_type,
                    source=f"session_{session_id}",
                    chat_title=chat_title
                )
                
                logger.debug(f"Saved: {link} ({platform}/{link_type})")
            
        except Exception as e:
            logger.debug(f"Error processing message: {e}")
    
    def stop_collection(self):
        """إيقاف الجمع"""
        self.is_collecting = False
        return True
    
    def get_status(self):
        """الحصول على الحالة"""
        return {
            'is_collecting': self.is_collecting,
            'stats': self.stats.copy()
        }

# كائن عام
collector = SimpleCollector()
