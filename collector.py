import asyncio
import logging
from typing import List, Dict
from datetime import datetime, timedelta

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message

from config import API_ID, API_HASH
from database import (
    save_link,
    get_sessions
)
from link_utils import (
    extract_links_from_message,
    clean_link,
    is_allowed_link,
    classify_platform,
    classify_telegram_link
)
from session_manager import get_active_sessions

# ======================
# Logging
# ======================

logger = logging.getLogger(__name__)

# ======================
# Global State
# ======================

_collection_status = {
    "running": False,
    "paused": False,
    "active_clients": [],
    "stats": {
        "telegram_collected": 0,
        "whatsapp_collected": 0,
        "total_collected": 0
    }
}

_stop_event = asyncio.Event()

# ======================
# Public API
# ======================

def get_collection_status() -> Dict:
    return _collection_status.copy()

def is_collecting() -> bool:
    return _collection_status["running"]

def is_paused() -> bool:
    return _collection_status["paused"]

async def start_collection():
    """بدء عملية الجمع"""
    global _collection_status
    
    if _collection_status["running"]:
        logger.warning("Collection is already running")
        return False
    
    _collection_status["running"] = True
    _collection_status["paused"] = False
    _stop_event.clear()
    
    # بدء الجمع في الخلفية
    asyncio.create_task(_run_collection())
    
    logger.info("🚀 Collection started")
    return True

async def pause_collection():
    """إيقاف الجمع مؤقتاً"""
    if not _collection_status["running"]:
        return False
    
    _collection_status["paused"] = True
    logger.info("⏸️ Collection paused")
    return True

async def resume_collection():
    """استئناف الجمع"""
    if not _collection_status["running"]:
        return False
    
    _collection_status["paused"] = False
    logger.info("▶️ Collection resumed")
    return True

async def stop_collection():
    """إيقاف الجمع نهائياً"""
    global _collection_status
    
    _collection_status["running"] = False
    _collection_status["paused"] = False
    _stop_event.set()
    
    logger.info("⏹️ Collection stopped")
    return True

# ======================
# Main Collection Loop
# ======================

async def _run_collection():
    """الحلقة الرئيسية للجمع"""
    try:
        logger.info("🚀 Starting link collection from all sessions...")
        
        # جمع من جميع الجلسات النشطة
        sessions = get_active_sessions()
        
        if not sessions:
            logger.error("❌ No active sessions found")
            _collection_status["running"] = False
            return
        
        tasks = []
        for session in sessions:
            task = asyncio.create_task(_collect_from_session(session))
            tasks.append(task)
        
        # انتظار جميع المهام
        await asyncio.gather(*tasks)
        
        logger.info("✅ Collection completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Error in collection loop: {e}")
    finally:
        _collection_status["running"] = False

# ======================
# Session Collection
# ======================

async def _collect_from_session(session_data: Dict):
    """الجمع من جلسة واحدة"""
    session_string = session_data.get("session_string")
    session_id = session_data.get("id")
    
    if not session_string:
        logger.error(f"❌ No session string for session {session_id}")
        return
    
    client = None
    try:
        # إنشاء العميل
        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH
        )
        
        await client.connect()
        
        if not await client.is_user_authorized():
            logger.error(f"❌ Session {session_id} is not authorized")
            return
        
        logger.info(f"✅ Connected to session {session_id}")
        
        # جمع من التليجرام (جميع التواريخ)
        await _collect_telegram_history(client, session_id)
        
        # الاستماع للجديد
        await _listen_for_new_messages(client, session_id)
        
        # انتظار حتى التوقف
        await _stop_event.wait()
        
    except Exception as e:
        logger.error(f"❌ Error in session {session_id}: {e}")
    finally:
        if client:
            await client.disconnect()
            logger.info(f"📤 Disconnected from session {session_id}")

# ======================
# Telegram History Collection
# ======================

async def _collect_telegram_history(client: TelegramClient, session_id: int):
    """جمع كل التاريخ من التليجرام"""
    if not _collection_status["running"]:
        return
    
    logger.info(f"📚 Collecting Telegram history from session {session_id}")
    
    try:
        # جلب جميع الدردشات
        dialogs = []
        async for dialog in client.iter_dialogs():
            if not _collection_status["running"]:
                break
            
            dialogs.append(dialog)
        
        logger.info(f"📁 Found {len(dialogs)} dialogs in session {session_id}")
        
        # معالجة كل دردشة
        for dialog in dialogs:
            if not _collection_status["running"]:
                break
            
            try:
                await _process_dialog_history(client, dialog, session_id)
            except Exception as e:
                logger.error(f"❌ Error processing dialog {dialog.name}: {e}")
                continue
            
            # تأخير صغير لمنع Flood
            await asyncio.sleep(0.3)
    
    except Exception as e:
        logger.error(f"❌ Error collecting history: {e}")

async def _process_dialog_history(client: TelegramClient, dialog, session_id: int):
    """معالجة تاريخ دردشة واحدة"""
    entity = dialog.entity
    
    try:
        # جمع جميع الرسائل (من 2000)
        total_messages = 0
        total_links = 0
        
        async for message in client.iter_messages(entity, limit=None):  # جميع الرسائل
            if not _collection_status["running"]:
                break
            
            # معالجة الرسالة
            links_found = await _process_message(client, message, session_id)
            total_links += links_found
            total_messages += 1
            
            # تسجيل التقدم كل 100 رسالة
            if total_messages % 100 == 0:
                logger.info(f"📊 Processed {total_messages} messages from {dialog.name}, found {total_links} links")
        
        if total_messages > 0:
            logger.info(f"✅ Finished {dialog.name}: {total_messages} messages, {total_links} links")
    
    except Exception as e:
        logger.error(f"❌ Error processing dialog {dialog.name}: {e}")

# ======================
# Live Listening
# ======================

async def _listen_for_new_messages(client: TelegramClient, session_id: int):
    """الاستماع للرسائل الجديدة"""
    @client.on(events.NewMessage)
    async def handler(event):
        if not _collection_status["running"] or _collection_status["paused"]:
            return
        
        await _process_message(client, event.message, session_id)
    
    logger.info(f"👂 Listening for new messages in session {session_id}")
    
    # الاستمرار حتى التوقف
    await _stop_event.wait()

# ======================
# Message Processing
# ======================

async def _process_message(client: TelegramClient, message: Message, session_id: int) -> int:
    """معالجة رسالة واحدة - ترجع عدد الروابط التي تم حفظها"""
    try:
        if not message:
            return 0
        
        # استخراج الروابط من النص
        raw_links = extract_links_from_message(message)
        
        if not raw_links:
            return 0
        
        # تنظيف وفلترة الروابط
        saved_count = 0
        for link in raw_links:
            cleaned = clean_link(link)
            if not cleaned or not is_allowed_link(cleaned):
                continue
            
            platform = classify_platform(cleaned)
            
            # تحديد نوع الرابط
            link_type = None
            if platform == "telegram":
                link_type = classify_telegram_link(cleaned)
            elif platform == "whatsapp":
                link_type = "group" if "chat.whatsapp.com" in cleaned else "phone"
            
            # حفظ الرابط
            success = save_link(
                url=cleaned,
                platform=platform,
                link_type=link_type,
                source_account=f"session_{session_id}",
                chat_id=str(message.chat_id) if message.chat_id else None,
                message_date=message.date,
                is_verified=False,
                verification_result="not_verified",
                metadata={"collected_from": "telegram"}
            )
            
            if success:
                saved_count += 1
                # تحديث الإحصائيات
                if platform == "telegram":
                    _collection_status["stats"]["telegram_collected"] += 1
                elif platform == "whatsapp":
                    _collection_status["stats"]["whatsapp_collected"] += 1
                
                _collection_status["stats"]["total_collected"] += 1
        
        if saved_count > 0:
            logger.debug(f"📎 Saved {saved_count} links from message in session {session_id}")
        
        return saved_count
        
    except Exception as e:
        logger.error(f"❌ Error processing message: {e}")
        return 0

# ======================
# WhatsApp Collection
# ======================

async def collect_whatsapp_links(session_id: int):
    """جمع روابط الواتساب من 6 أشهر مضت"""
    # ملاحظة: الواتساب لا يوفر API عام للرسائل
    # هذه وظيفة ستجمع الروابط من ملفات الدردشات المحفوظة
    
    logger.info(f"📞 Starting WhatsApp collection from 6 months ago for session {session_id}")
    
    # هذه وظيفة تحتاج إلى تنفيذ حسب مصادر البيانات المتاحة
    # يمكن جمع الروابط من:
    # 1. تصدير الدردشات من الواتساب
    # 2. ملفات نصية محفوظة
    # 3. مصادر خارجية أخرى
    
    return []

# ======================
# Helper Functions
# ======================

def get_chat_type(entity) -> str:
    """تحديد نوع المحادثة"""
    cls = entity.__class__.__name__.lower()
    
    if "channel" in cls:
        return "channel"
    if "chat" in cls:
        return "group"
    return "private"

# ======================
# Quick Test
# ======================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        print("🧪 Testing collector...")
        
        # بدء الجمع لفترة قصيرة
        await start_collection()
        await asyncio.sleep(5)
        await stop_collection()
        
        print(f"Status: {get_collection_status()}")
    
    asyncio.run(test())
