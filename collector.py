import asyncio
import logging
import re
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message
from database import get_sessions, save_link

logger = logging.getLogger(__name__)

# ======================
# أنماط الروابط المحسنة
# ======================

TELEGRAM_PATTERNS = [
    # روابط القنوات والمجموعات
    r"https?://t\.me/([a-zA-Z0-9_]+)(?:/\d+)?",
    r"https?://telegram\.me/([a-zA-Z0-9_]+)(?:/\d+)?",
    
    # روابط الانضمام
    r"https?://t\.me/joinchat/([a-zA-Z0-9_-]+)",
    r"https?://t\.me/\+([a-zA-Z0-9]+)",
    
    # روابط الدردشات الخاصة
    r"https?://t\.me/c/(\d+)/(\d+)",
]

WHATSAPP_PATTERNS = [
    # مجموعات واتساب
    r"https?://chat\.whatsapp\.com/([a-zA-Z0-9]+)",
    
    # روابط أرقام
    r"https?://wa\.me/(\d+)(?:\?text=.+)?",
]

# ======================
# وظائف مساعدة
# ======================

def extract_links(text):
    """استخراج جميع الروابط من النص"""
    if not text:
        return []
    
    links = set()  # استخدام set لمنع التكرار
    
    # جمع روابط التليجرام
    for pattern in TELEGRAM_PATTERNS:
        for match in re.finditer(pattern, text):
            link = match.group(0)
            links.add(link)
    
    # جمع روابط الواتساب
    for pattern in WHATSAPP_PATTERNS:
        for match in re.finditer(pattern, text):
            link = match.group(0)
            links.add(link)
    
    return list(links)

def clean_url(url):
    """تنظيف الرابط من الزوائد"""
    if not url:
        return url
    
    # إزالة المسافات والنجوم
    url = url.strip().replace('*', '').replace(' ', '')
    
    # إزالة الأحرف الغريبة في النهاية
    url = re.sub(r'[.,;!?]+$', '', url)
    
    # إزالة الأقواس
    url = url.strip('()[]{}<>"\'')
    
    return url

def classify_link(url):
    """تصنيف الرابط"""
    url_lower = url.lower()
    
    # تليجرام
    if 't.me' in url_lower or 'telegram.me' in url_lower:
        if 'joinchat' in url_lower:
            return 'telegram', 'private_group'
        elif url_lower.startswith('https://t.me/+'):
            return 'telegram', 'public_group'
        elif '/c/' in url_lower:
            return 'telegram', 'message'
        elif re.search(r'bot$|/bot', url_lower):
            return 'telegram', 'bot'
        else:
            return 'telegram', 'channel'
    
    # واتساب
    elif 'whatsapp.com' in url_lower or 'wa.me' in url_lower:
        if 'chat.whatsapp.com' in url_lower:
            return 'whatsapp', 'group'
        else:
            return 'whatsapp', 'phone'
    
    return 'unknown', 'unknown'

# ======================
# الفئات الرئيسية
# ======================

class LinkCollector:
    def __init__(self):
        self.is_collecting = False
        self.active_clients = []
        self.collection_stats = {
            'telegram': 0,
            'whatsapp': 0,
            'total': 0
        }
    
    async def start_collection(self):
        """بدء عملية الجمع"""
        if self.is_collecting:
            logger.warning("Collection is already running")
            return False
        
        logger.info("🚀 Starting link collection...")
        self.is_collecting = True
        self.collection_stats = {'telegram': 0, 'whatsapp': 0, 'total': 0}
        
        sessions = get_sessions()
        if not sessions:
            logger.error("❌ No active sessions found")
            self.is_collecting = False
            return False
        
        logger.info(f"📊 Found {len(sessions)} active sessions")
        
        # تشغيل الجمع لكل جلسة
        tasks = []
        for session in sessions:
            task = asyncio.create_task(self.process_session(session))
            tasks.append(task)
        
        # الانتظار لبدء جميع المهام
        await asyncio.sleep(2)
        
        logger.info("✅ Collection started successfully")
        return True
    
    async def process_session(self, session_data):
        """معالجة جلسة واحدة"""
        session_id = session_data['id']
        session_string = session_data['session_string']
        
        logger.info(f"🔍 Processing session {session_id}")
        
        client = None
        try:
            # إنشاء العميل
            client = TelegramClient(
                StringSession(session_string),
                6,
                "eb06d4abfb49dc3eeb1aeb98ae0f581e"
            )
            
            await client.connect()
            
            # التحقق من الصلاحية
            if not await client.is_user_authorized():
                logger.error(f"❌ Session {session_id} is not authorized")
                return
            
            self.active_clients.append(client)
            logger.info(f"✅ Connected to session {session_id}")
            
            # جمع من المحادثات
            await self.collect_from_dialogs(client, session_id)
            
            # البقاء نشطاً للاستماع للجديد
            while self.is_collecting:
                await asyncio.sleep(10)
                
        except Exception as e:
            logger.error(f"❌ Error in session {session_id}: {e}")
        finally:
            if client:
                self.active_clients.remove(client)
                await client.disconnect()
                logger.info(f"🔌 Disconnected from session {session_id}")
    
    async def collect_from_dialogs(self, client, session_id):
        """جمع الروابط من جميع المحادثات"""
        try:
            async for dialog in client.iter_dialogs(limit=200):
                if not self.is_collecting:
                    break
                
                try:
                    await self.collect_from_chat(client, dialog.entity, session_id)
                    await asyncio.sleep(0.5)  # تأخير لمنع Flood
                    
                except Exception as e:
                    logger.debug(f"⚠️ Error in dialog {dialog.name}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Error collecting from dialogs: {e}")
    
    async def collect_from_chat(self, client, chat, session_id):
        """جمع الروابط من محادثة واحدة"""
        try:
            # جمع من الرسائل القديمة (الأحدث أولاً)
            async for message in client.iter_messages(
                chat,
                limit=500,  # 500 رسالة من كل محادثة
                reverse=True  # من الأقدم للأحدث
            ):
                if not self.is_collecting:
                    return
                
                await self.process_telegram_message(message, session_id)
                
        except Exception as e:
            logger.debug(f"⚠️ Error collecting from chat: {e}")
    
    async def process_telegram_message(self, message: Message, session_id):
        """معالجة رسالة تليجرام واحدة"""
        try:
            links_found = []
            
            # النص الأساسي
            if message.text:
                links_found.extend(extract_links(message.text))
            
            # الكابشن
            if hasattr(message, 'caption') and message.caption:
                links_found.extend(extract_links(message.caption))
            
            # أزرار Inline
            if hasattr(message, 'reply_markup') and message.reply_markup:
                for row in message.reply_markup.rows:
                    for button in row.buttons:
                        if hasattr(button, 'url') and button.url:
                            links_found.append(button.url)
            
            # حفظ الروابط
            for raw_link in set(links_found):
                link = clean_url(raw_link)
                if link:
                    platform, link_type = classify_link(link)
                    
                    # تحديث الإحصائيات
                    if platform in self.collection_stats:
                        self.collection_stats[platform] += 1
                        self.collection_stats['total'] += 1
                    
                    # حفظ في قاعدة البيانات
                    save_link(
                        url=link,
                        platform=platform,
                        link_type=link_type,
                        source=f"session_{session_id}"
                    )
            
            if links_found:
                logger.debug(f"📥 Found {len(links_found)} links in message")
                
        except Exception as e:
            logger.debug(f"⚠️ Error processing message: {e}")
    
    def stop_collection(self):
        """إيقاف عملية الجمع"""
        logger.info("🛑 Stopping collection...")
        self.is_collecting = False
        
        # إغلاق جميع العملاء
        for client in self.active_clients:
            try:
                asyncio.create_task(client.disconnect())
            except:
                pass
        
        self.active_clients.clear()
        logger.info(f"📊 Final stats: {self.collection_stats}")
        return True
    
    def get_status(self):
        """الحصول على حالة الجمع"""
        return {
            'is_collecting': self.is_collecting,
            'active_sessions': len(self.active_clients),
            'stats': self.collection_stats.copy()
        }

# ======================
# كائن عام
# ======================

collector = LinkCollector()

# ======================
# اختبار سريع
# ======================

if __name__ == "__main__":
    # اختبار وظائف الاستخراج
    test_text = """
    رابط قناة: https://t.me/python_ar
    رابط مجموعة: https://t.me/joinchat/ABCDEF
    رابط عام: https://t.me/+1234567890
    رابط واتساب: https://chat.whatsapp.com/ABCDEF123
    رابط رقم: https://wa.me/1234567890
    """
    
    links = extract_links(test_text)
    print("🔍 Test extraction results:")
    for link in links:
        platform, link_type = classify_link(link)
        print(f"  • {link} -> {platform}/{link_type}")
    
    print(f"\n✅ Found {len(links)} links")
