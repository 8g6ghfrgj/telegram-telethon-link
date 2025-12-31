import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Optional, Set

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message, Channel, Chat, User
from telethon.errors import FloodWaitError, AuthKeyError

from config import API_ID, API_HASH, COLLECT_TELEGRAM, COLLECT_WHATSAPP
from database import save_link, get_sessions
from session_manager import validate_session

# ======================
# Logging Configuration
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Global State
# ======================

_collection_status = {
    "running": False,
    "paused": False,
    "current_session": None,
    "active_clients": [],
    "stats": {
        "telegram_collected": 0,
        "whatsapp_collected": 0,
        "total_collected": 0,
        "verified_count": 0
    }
}

_collection_lock = asyncio.Lock()
_stop_event = asyncio.Event()
_pause_event = asyncio.Event()
_pause_event.set()  # غير موقف في البداية

# ======================
# Regex Patterns
# ======================

URL_REGEX = re.compile(r"(https?://[^\s<>\"]+)", re.IGNORECASE)

TELEGRAM_PATTERNS = {
    "channel": re.compile(r"https?://t\.me/([A-Za-z0-9_]+)$", re.I),
    "private_group": re.compile(r"https?://t\.me/joinchat/([A-Za-z0-9_-]+)", re.I),
    "public_group": re.compile(r"https?://t\.me/\+([A-Za-z0-9]+)", re.I),
    "bot": re.compile(r"https?://t\.me/([A-Za-z0-9_]+)bot(\?|$)", re.I),
    "message": re.compile(r"https?://t\.me/(c/)?([A-Za-z0-9_]+)/(\d+)", re.I),
}

WHATSAPP_PATTERNS = {
    "group": re.compile(r"https?://chat\.whatsapp\.com/([A-Za-z0-9]+)", re.I),
    "phone": re.compile(r"https?://wa\.me/(\d+)", re.I),
}

# ======================
# Public API Functions
# ======================

def get_collection_status() -> Dict:
    """الحصول على حالة الجمع الحالية"""
    return _collection_status.copy()

def is_collecting() -> bool:
    """هل الجمع يعمل حالياً؟"""
    return _collection_status["running"]

def is_paused() -> bool:
    """هل الجمع موقف مؤقتاً؟"""
    return _collection_status["paused"]

async def start_collection() -> bool:
    """بدء عملية الجمع"""
    global _collection_status
    
    if _collection_status["running"]:
        logger.warning("Collection is already running")
        return False
    
    async with _collection_lock:
        # إعادة التعيين
        _collection_status["running"] = True
        _collection_status["paused"] = False
        _collection_status["stats"] = {
            "telegram_collected": 0,
            "whatsapp_collected": 0,
            "total_collected": 0,
            "verified_count": 0
        }
        
        _stop_event.clear()
        _pause_event.set()
        
        # التحقق من وجود جلسات نشطة
        sessions = get_sessions(active_only=True)
        if not sessions:
            logger.error("No active sessions found")
            _collection_status["running"] = False
            return False
        
        logger.info(f"Starting collection with {len(sessions)} active sessions")
        
        # بدء الجمع في الخلفية
        asyncio.create_task(_run_collection())
        
        return True

async def pause_collection() -> bool:
    """إيقاف الجمع مؤقتاً"""
    if not _collection_status["running"] or _collection_status["paused"]:
        return False
    
    _collection_status["paused"] = True
    _pause_event.clear()
    logger.info("Collection paused")
    return True

async def resume_collection() -> bool:
    """استئناف الجمع"""
    if not _collection_status["running"] or not _collection_status["paused"]:
        return False
    
    _collection_status["paused"] = False
    _pause_event.set()
    logger.info("Collection resumed")
    return True

async def stop_collection() -> bool:
    """إيقاف الجمع تماماً"""
    global _collection_status
    
    if not _collection_status["running"]:
        return False
    
    _collection_status["running"] = False
    _collection_status["paused"] = False
    _stop_event.set()
    _pause_event.set()
    
    # إيقاف جميع العملاء النشطين
    for client in _collection_status["active_clients"]:
        try:
            await client.disconnect()
        except:
            pass
    
    _collection_status["active_clients"] = []
    
    logger.info("Collection stopped completely")
    return True

# ======================
# Link Processing Functions
# ======================

def clean_link(url: str) -> str:
    """تنظيف الرابط من الزوائد"""
    if not url:
        return ""
    
    # إزالة المسافات والنجوم
    cleaned = url.strip().replace('*', '').replace(' ', '')
    
    # إزالة الأحرف الغريبة في البداية والنهاية
    cleaned = re.sub(r'^[^a-zA-Z0-9]+', '', cleaned)
    cleaned = re.sub(r'[^a-zA-Z0-9]+$', '', cleaned)
    
    return cleaned

def extract_links_from_text(text: str) -> List[str]:
    """استخراج الروابط من النص"""
    if not text:
        return []
    
    links = set()
    for url in URL_REGEX.findall(text):
        cleaned = clean_link(url)
        if cleaned:
            links.add(cleaned)
    
    return list(links)

def extract_links_from_message(message: Message) -> List[str]:
    """استخراج الروابط من رسالة تليجرام"""
    links = set()
    
    # النص الأساسي
    text = message.text or message.message or ""
    if text:
        links.update(extract_links_from_text(text))
    
    # الكابتشن (إذا كانت صورة/فيديو)
    if hasattr(message, 'caption') and message.caption:
        links.update(extract_links_from_text(message.caption))
    
    # أزرار Inline
    if hasattr(message, 'reply_markup') and message.reply_markup:
        for row in message.reply_markup.rows:
            for button in row.buttons:
                if hasattr(button, "url") and button.url:
                    cleaned = clean_link(button.url)
                    if cleaned:
                        links.add(cleaned)
    
    return list(links)

def classify_platform(url: str) -> str:
    """تصنيف الرابط حسب المنصة"""
    url_lower = url.lower()
    
    if "t.me" in url_lower or "telegram.me" in url_lower:
        return "telegram"
    elif "whatsapp.com" in url_lower or "wa.me" in url_lower:
        return "whatsapp"
    else:
        return "other"

def classify_telegram_link(url: str) -> str:
    """تصنيف رابط تليجرام حسب النوع"""
    url_lower = url.lower()
    
    for link_type, pattern in TELEGRAM_PATTERNS.items():
        if pattern.search(url_lower):
            return link_type
    
    # إذا لم يتطابق مع الأنواع المعروفة
    if "joinchat/" in url_lower:
        return "private_group"
    elif url_lower.startswith("https://t.me/+") or url_lower.startswith("http://t.me/+"):
        return "public_group"
    elif re.search(r'/\d+$', url_lower):
        return "message"
    elif re.search(r'bot(\?|$)', url_lower):
        return "bot"
    elif re.match(r'^https?://t\.me/[A-Za-z0-9_]+$', url_lower):
        return "channel"
    
    return "unknown"

def classify_whatsapp_link(url: str) -> str:
    """تصنيف رابط واتساب حسب النوع"""
    url_lower = url.lower()
    
    for link_type, pattern in WHATSAPP_PATTERNS.items():
        if pattern.search(url_lower):
            return link_type
    
    return "unknown"

def is_allowed_link(url: str) -> bool:
    """التحقق مما إذا كان الرابط مسموحاً به"""
    if not url or len(url) < 10:
        return False
    
    platform = classify_platform(url)
    
    if not COLLECT_TELEGRAM and platform == "telegram":
        return False
    
    if not COLLECT_WHATSAPP and platform == "whatsapp":
        return False
    
    # السماح فقط بالتليجرام والواتساب
    return platform in ["telegram", "whatsapp"]

async def verify_link(url: str) -> Dict:
    """فحص الرابط (وظيفة مبسطة)"""
    platform = classify_platform(url)
    
    if platform == "telegram":
        link_type = classify_telegram_link(url)
    elif platform == "whatsapp":
        link_type = classify_whatsapp_link(url)
    else:
        link_type = "unknown"
    
    return {
        'url': url,
        'is_valid': True,
        'platform': platform,
        'link_type': link_type,
        'metadata': {}
    }

async def verify_links_batch(urls: List[str]) -> List[Dict]:
    """فحص مجموعة من الروابط"""
    if not urls:
        return []
    
    results = []
    for url in urls:
        if is_allowed_link(url):
            result = await verify_link(url)
            results.append(result)
    
    return results

# ======================
# Main Collection Loop
# ======================

async def _run_collection():
    """الحلقة الرئيسية للجمع"""
    try:
        await asyncio.sleep(1)  # انتظار بسيط
        
        logger.info("🚀 Starting link collection...")
        
        # جمع من جميع الجلسات النشطة
        sessions = get_sessions(active_only=True)
        
        collection_tasks = []
        for session in sessions:
            task = asyncio.create_task(_collect_from_session(session))
            collection_tasks.append(task)
        
        # انتظار جميع المهام أو التوقف
        await asyncio.wait(collection_tasks, return_when=asyncio.FIRST_COMPLETED)
        
        # إلغاء المهام المتبقية
        for task in collection_tasks:
            task.cancel()
        
        logger.info("✅ Collection completed")
        
    except Exception as e:
        logger.error(f"Error in collection loop: {e}")
    finally:
        _collection_status["running"] = False
        _collection_status["paused"] = False

# ======================
# Session Collection
# ======================

async def _collect_from_session(session_data: Dict):
    """الجمع من جلسة واحدة"""
    session_string = session_data.get("session_string")
    session_id = session_data.get("id")
    
    if not session_string:
        logger.error(f"No session string for session {session_id}")
        return
    
    client = None
    try:
        # إنشاء عميل تليجرام
        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH
        )
        
        await client.connect()
        
        # التحقق من أن الجلسة مصرح بها
        if not await client.is_user_authorized():
            logger.error(f"Session {session_id} is not authorized")
            return
        
        # إضافة العميل إلى القائمة النشطة
        _collection_status["active_clients"].append(client)
        
        logger.info(f"✅ Connected to session {session_id}")
        
        # جمع التاريخ القديم
        await _collect_history(client, session_id)
        
        # الاستماع للرسائل الجديدة
        await _listen_for_new_messages(client, session_id)
        
        # انتظار حتى التوقف
        await _stop_event.wait()
        
    except FloodWaitError as e:
        logger.warning(f"⏳ Flood wait for {e.seconds} seconds")
        await asyncio.sleep(e.seconds)
    except AuthKeyError:
        logger.error(f"❌ Session {session_id} has invalid auth key")
    except Exception as e:
        logger.error(f"Error in session {session_id}: {e}")
    finally:
        # إزالة العميل من القائمة النشطة
        if client and client in _collection_status["active_clients"]:
            _collection_status["active_clients"].remove(client)
        
        # قطع الاتصال
        if client:
            try:
                await client.disconnect()
                logger.info(f"Disconnected from session {session_id}")
            except:
                pass

# ======================
# History Collection
# ======================

async def _collect_history(client: TelegramClient, session_id: int):
    """جمع الروابط من التاريخ"""
    if not _collection_status["running"]:
        return
    
    logger.info(f"Collecting history from session {session_id}")
    
    try:
        # الحصول على جميع الدردشات
        async for dialog in client.iter_dialogs():
            # التحقق من التوقف أو الإيقاف المؤقت
            if not _collection_status["running"]:
                break
            
            await _pause_event.wait()  # انتظار إذا كان موقفاً
            
            try:
                await _process_dialog(client, dialog, session_id)
            except Exception as e:
                logger.error(f"Error processing dialog {dialog.name}: {e}")
                continue
            
            # تأخير صغير لمنع Flood
            await asyncio.sleep(0.5)
    
    except Exception as e:
        logger.error(f"Error collecting history: {e}")

async def _process_dialog(client: TelegramClient, dialog, session_id: int):
    """معالجة دردشة واحدة"""
    entity = dialog.entity
    
    # الحصول على الرسائل بترتيب عكسي (من الأقدم إلى الأحدث)
    async for message in client.iter_messages(entity, reverse=True, limit=500):
        # التحقق من التوقف أو الإيقاف المؤقت
        if not _collection_status["running"]:
            break
        
        await _pause_event.wait()
        
        # معالجة الرسالة
        await _process_message(client, message, session_id)
        
        # تأخير لمنع Flood
        await asyncio.sleep(0.1)

# ======================
# Live Listening
# ======================

async def _listen_for_new_messages(client: TelegramClient, session_id: int):
    """الاستماع للرسائل الجديدة"""
    @client.on(events.NewMessage)
    async def handler(event):
        # التحقق من التوقف أو الإيقاف المؤقت
        if not _collection_status["running"]:
            return
        
        await _pause_event.wait()
        
        # معالجة الرسالة الجديدة
        await _process_message(client, event.message, session_id)
    
    logger.info(f"Listening for new messages in session {session_id}")
    
    # الاستمرار في التشغيل حتى التوقف
    await _stop_event.wait()

# ======================
# Message Processing
# ======================

async def _process_message(client: TelegramClient, message: Message, session_id: int):
    """معالجة رسالة واحدة واستخراج الروابط"""
    try:
        if not message:
            return
        
        # استخراج الروابط من النص
        raw_links = extract_links_from_message(message)
        
        if not raw_links:
            return
        
        # تنظيف وفلترة الروابط
        clean_links = []
        for link in raw_links:
            cleaned = clean_link(link)
            if cleaned and is_allowed_link(cleaned):
                clean_links.append(cleaned)
        
        if not clean_links:
            return
        
        # فحص الروابط
        verified_links = await verify_links_batch(clean_links)
        
        # حفظ الروابط
        for link_data in verified_links:
            url = link_data.get('url')
            platform = link_data.get('platform')
            link_type = link_data.get('link_type')
            
            if not url or not platform:
                continue
            
            # تحديث الإحصائيات
            async with _collection_lock:
                if platform == "telegram":
                    _collection_status["stats"]["telegram_collected"] += 1
                elif platform == "whatsapp":
                    _collection_status["stats"]["whatsapp_collected"] += 1
                
                _collection_status["stats"]["total_collected"] += 1
                _collection_status["stats"]["verified_count"] += 1
            
            # حفظ في قاعدة البيانات
            save_link(
                url=url,
                platform=platform,
                link_type=link_type,
                source_account=f"session_{session_id}",
                chat_id=str(message.chat_id) if message.chat_id else None,
                message_date=message.date,
                is_verified=True,
                verification_result="valid",
                metadata=link_data.get('metadata', {})
            )
        
        # تسجيل التقدم
        if len(verified_links) > 0:
            logger.debug(f"Collected {len(verified_links)} links from session {session_id}")
            
    except Exception as e:
        logger.error(f"Error processing message: {e}")

# ======================
# Helper Functions
# ======================

def get_chat_type(entity) -> str:
    """تحديد نوع المحادثة"""
    if isinstance(entity, Channel):
        return "channel"
    elif isinstance(entity, Chat):
        return "group"
    elif isinstance(entity, User):
        return "private"
    else:
        return "unknown"

# ======================
# Test Functions
# ======================

async def test_collection():
    """اختبار وظائف الجمع"""
    print("🧪 Testing collection module...")
    
    print(f"1. Is collecting: {is_collecting()}")
    print(f"2. Is paused: {is_paused()}")
    print(f"3. Collection status: {get_collection_status()}")
    
    # اختبار تنظيف الروابط
    test_urls = [
        " * https://t.me/python * ",
        "  https://chat.whatsapp.com/abc123  ",
        "https://t.me/joinchat/abcdefg",
        "invalid url"
    ]
    
    print("\n4. Testing link cleaning:")
    for url in test_urls:
        cleaned = clean_link(url)
        print(f"   '{url}' -> '{cleaned}'")
    
    # اختبار تصنيف الروابط
    print("\n5. Testing link classification:")
    test_links = [
        "https://t.me/python",
        "https://t.me/joinchat/abc123",
        "https://t.me/+1234567890",
        "https://t.me/test_bot",
        "https://t.me/c/1234567890/123",
        "https://chat.whatsapp.com/abc123",
        "https://wa.me/1234567890"
    ]
    
    for link in test_links:
        platform = classify_platform(link)
        if platform == "telegram":
            link_type = classify_telegram_link(link)
        elif platform == "whatsapp":
            link_type = classify_whatsapp_link(link)
        else:
            link_type = "unknown"
        
        print(f"   {link} -> {platform}/{link_type}")
    
    print("\n✅ Collection module test completed")

# ======================
# Quick Test
# ======================

if __name__ == "__main__":
    async def main():
        await test_collection()
    
    asyncio.run(main())
