import asyncio
import re
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message, Channel, Chat
from config import API_ID, API_HASH
from database import get_sessions, save_link, get_links_count

logger = logging.getLogger(__name__)

# ======================
# تصنيف الروابط
# ======================

def classify_telegram_link(url):
    """تصنيف رابط تليجرام"""
    url_lower = url.lower()
    
    if "t.me/joinchat/" in url_lower:
        return "private_group"
    elif url_lower.startswith("https://t.me/+") or "t.me/+" in url_lower:
        return "public_group"
    elif "/c/" in url_lower:
        return "message"
    elif re.search(r'/bot$|bot\?|bot/', url_lower):
        return "bot"
    elif re.match(r'https?://t\.me/[a-zA-Z0-9_]+$', url_lower):
        return "channel"
    else:
        return "unknown"

def classify_whatsapp_link(url):
    """تصنيف رابط واتساب"""
    if "chat.whatsapp.com" in url.lower():
        return "group"
    elif "wa.me" in url.lower():
        return "phone"
    else:
        return "unknown"

# ======================
# استخراج الروابط
# ======================

def extract_all_links(text):
    """استخراج جميع الروابط من النص"""
    if not text:
        return []
    
    # نمط شامل لجميع الروابط
    url_pattern = r'https?://[^\s<>"]+'
    
    links = []
    for match in re.finditer(url_pattern, text, re.IGNORECASE):
        url = match.group(0).strip()
        
        # تنظيف الرابط
        url = url.rstrip('.,;!?)').rstrip('(')
        
        # إزالة المسافات والنجوم
        url = url.replace('*', '').replace(' ', '')
        
        if url:
            links.append(url)
    
    return list(set(links))  # إزالة التكرار

# ======================
# المجمع الرئيسي
# ======================

class TelegramLinkCollector:
    def __init__(self):
        self.is_active = False
        self.collection_stats = {
            'telegram': {'channels': 0, 'groups': 0, 'bots': 0, 'messages': 0, 'total': 0},
            'whatsapp': {'groups': 0, 'phones': 0, 'total': 0},
            'sessions_processed': 0,
            'total_collected': 0
        }
        self.clients = []
    
    async def start_collection(self):
        """بدء عملية الجمع"""
        if self.is_active:
            return {"success": False, "message": "الجمع يعمل بالفعل"}
        
        logger.info("🚀 بدء جمع الروابط...")
        self.is_active = True
        self.collection_stats = {
            'telegram': {'channels': 0, 'groups': 0, 'bots': 0, 'messages': 0, 'total': 0},
            'whatsapp': {'groups': 0, 'phones': 0, 'total': 0},
            'sessions_processed': 0,
            'total_collected': 0
        }
        
        sessions = get_sessions()
        if not sessions:
            self.is_active = False
            return {"success": False, "message": "لا توجد جلسات نشطة"}
        
        logger.info(f"📊 وجد {len(sessions)} جلسة نشطة")
        
        # تشغيل الجمع لكل جلسة
        collection_tasks = []
        for session in sessions:
            task = asyncio.create_task(self.process_session(session))
            collection_tasks.append(task)
        
        # جمع النتائج
        results = await asyncio.gather(*collection_tasks, return_exceptions=True)
        
        # تلخيص النتائج
        successful = sum(1 for r in results if isinstance(r, dict) and r.get('success'))
        failed = len(results) - successful
        
        self.is_active = False
        
        return {
            "success": True,
            "message": f"اكتمل الجمع: {successful} ناجح، {failed} فاشل",
            "stats": self.collection_stats
        }
    
    async def process_session(self, session_data):
        """معالجة جلسة واحدة"""
        session_id = session_data['id']
        session_string = session_data['session_string']
        
        logger.info(f"🔍 معالجة الجلسة {session_id}")
        
        client = None
        try:
            # إنشاء العميل
            client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
            await client.connect()
            
            # التحقق من التخويل
            if not await client.is_user_authorized():
                logger.error(f"❌ الجلسة {session_id} غير مصرح بها")
                return {"success": False, "session_id": session_id, "error": "غير مصرح"}
            
            logger.info(f"✅ تم الاتصال بالجلسة {session_id}")
            self.collection_stats['sessions_processed'] += 1
            
            # جمع من المحادثات
            await self.collect_from_dialogs(client, session_id)
            
            await client.disconnect()
            return {"success": True, "session_id": session_id}
            
        except Exception as e:
            logger.error(f"❌ خطأ في الجلسة {session_id}: {e}")
            if client:
                await client.disconnect()
            return {"success": False, "session_id": session_id, "error": str(e)}
    
    async def collect_from_dialogs(self, client, session_id):
        """جمع الروابط من جميع المحادثات"""
        try:
            async for dialog in client.iter_dialogs(limit=100):
                if not self.is_active:
                    break
                
                try:
                    chat_title = dialog.name or "Unknown"
                    
                    # جمع من الرسائل
                    await self.collect_from_messages(client, dialog.entity, session_id, chat_title)
                    
                    # تأخير لمنع Flood
                    await asyncio.sleep(0.3)
                    
                except Exception as e:
                    logger.debug(f"⚠️ تخطي المحادثة {dialog.name}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"❌ خطأ في جمع المحادثات: {e}")
    
    async def collect_from_messages(self, client, chat, session_id, chat_title):
        """جمع الروابط من الرسائل"""
        try:
            async for message in client.iter_messages(
                chat,
                limit=300,  # 300 رسالة من كل محادثة
                reverse=True
            ):
                if not self.is_active:
                    return
                
                # استخراج الروابط
                links_found = []
                
                # النص
                if message.text:
                    links_found.extend(extract_all_links(message.text))
                
                # الكابشن
                if hasattr(message, 'caption') and message.caption:
                    links_found.extend(extract_all_links(message.caption))
                
                # حفظ الروابط
                for url in set(links_found):
                    if self.process_and_save_link(url, session_id, chat_title):
                        self.collection_stats['total_collected'] += 1
                
                # تأخير بسيط
                await asyncio.sleep(0.05)
                
        except Exception as e:
            logger.debug(f"⚠️ خطأ في جمع الرسائل: {e}")
    
    def process_and_save_link(self, url, session_id, chat_title):
        """معالجة وحفظ الرابط"""
        try:
            url_lower = url.lower()
            
            # تليجرام
            if 't.me' in url_lower or 'telegram.me' in url_lower:
                link_type = classify_telegram_link(url)
                platform = 'telegram'
                
                # تحديث الإحصائيات
                if link_type == 'channel':
                    self.collection_stats['telegram']['channels'] += 1
                elif link_type in ['private_group', 'public_group']:
                    self.collection_stats['telegram']['groups'] += 1
                elif link_type == 'bot':
                    self.collection_stats['telegram']['bots'] += 1
                elif link_type == 'message':
                    self.collection_stats['telegram']['messages'] += 1
                
                self.collection_stats['telegram']['total'] += 1
            
            # واتساب
            elif 'whatsapp.com' in url_lower or 'wa.me' in url_lower:
                link_type = classify_whatsapp_link(url)
                platform = 'whatsapp'
                
                # تحديث الإحصائيات
                if link_type == 'group':
                    self.collection_stats['whatsapp']['groups'] += 1
                elif link_type == 'phone':
                    self.collection_stats['whatsapp']['phones'] += 1
                
                self.collection_stats['whatsapp']['total'] += 1
            
            else:
                return False  # تجاهل الروابط الأخرى
            
            # حفظ الرابط
            success = save_link(
                url=url,
                platform=platform,
                link_type=link_type,
                source_session=session_id,
                chat_title=chat_title
            )
            
            if success:
                logger.debug(f"📥 تم حفظ الرابط: {url}")
            
            return success
            
        except Exception as e:
            logger.debug(f"⚠️ خطأ في معالجة الرابط: {e}")
            return False
    
    def stop_collection(self):
        """إيقاف الجمع"""
        if self.is_active:
            self.is_active = False
            logger.info("🛑 تم إيقاف الجمع")
            return True
        return False
    
    def get_status(self):
        """الحصول على حالة الجمع"""
        return {
            'is_active': self.is_active,
            'stats': self.collection_stats
        }

# كائن المجمع العام
collector = TelegramLinkCollector()
