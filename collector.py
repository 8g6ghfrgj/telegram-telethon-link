import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message, Channel, Chat, User
from telethon.errors import FloodWaitError

# بدلاً من هذا:
from config import API_ID, API_HASH

# استخدم هذا:
# قيم وهمية
DUMMY_API_ID = 1
DUMMY_API_HASH = "1"

# ثم في run_client:
client = TelegramClient(
    StringSession(session_string),
    DUMMY_API_ID,      # قيمة وهمية
    DUMMY_API_HASH     # قيمة وهمية
)
from database import (
    save_link, start_collection_session, update_collection_stats,
    get_sessions
)
from link_utils import (
    extract_links_from_message, clean_link, is_allowed_link,
    classify_platform, classify_telegram_link, verify_links_batch
)
from session_manager import get_active_sessions
from file_extractors import extract_links_from_file

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
    "current_session_id": None,
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
# Public API
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


async def start_collection():
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
        
        # بدء جلسة جمع في قاعدة البيانات
        sessions = get_sessions(active_only=True)
        if not sessions:
            logger.error("No active sessions found")
            _collection_status["running"] = False
            return False
        
        session_id = sessions[0]["id"]  # استخدام أول جلسة نشطة
        collection_id = start_collection_session(session_id)
        _collection_status["current_session_id"] = collection_id
        
        logger.info(f"Starting collection session #{collection_id}")
        
        # بدء الجمع في الخلفية
        asyncio.create_task(_run_collection())
        
        return True


async def pause_collection():
    """إيقاف الجمع مؤقتاً"""
    if not _collection_status["running"] or _collection_status["paused"]:
        return False
    
    _collection_status["paused"] = True
    _pause_event.clear()
    logger.info("Collection paused")
    return True


async def resume_collection():
    """استئناف الجمع"""
    if not _collection_status["running"] or not _collection_status["paused"]:
        return False
    
    _collection_status["paused"] = False
    _pause_event.set()
    logger.info("Collection resumed")
    return True


async def stop_collection():
    """إيقاف الجمع تماماً"""
    global _collection_status
    
    if not _collection_status["running"]:
        return False
    
    _collection_status["running"] = False
    _collection_status["paused"] = False
    _stop_event.set()
    _pause_event.set()
    
    # تحديث إحصائيات النهاية
    if _collection_status["current_session_id"]:
        update_collection_stats(
            _collection_status["current_session_id"],
            status="stopped",
            telegram_count=_collection_status["stats"]["telegram_collected"],
            whatsapp_count=_collection_status["stats"]["whatsapp_collected"],
            verified_count=_collection_status["stats"]["verified_count"]
        )
    
    logger.info("Collection stopped completely")
    return True


# ======================
# Main Collection Loop
# ======================

async def _run_collection():
    """الحلقة الرئيسية للجمع"""
    try:
        # انتظار بدء الجمع
        await asyncio.sleep(1)
        
        logger.info("🚀 Starting link collection...")
        
        # جمع من جميع الجلسات النشطة
        sessions = get_active_sessions()
        
        collection_tasks = []
        for session in sessions:
            task = asyncio.create_task(_collect_from_session(session))
            collection_tasks.append(task)
        
        # انتظار جميع المهام أو التوقف
        await asyncio.wait(collection_tasks, return_when=asyncio.FIRST_COMPLETED)
        
        # إلغاء المهام المتبقية
        for task in collection_tasks:
            task.cancel()
        
        # تحديث حالة النهاية
        if _collection_status["running"] and _collection_status["current_session_id"]:
            update_collection_stats(
                _collection_status["current_session_id"],
                status="completed",
                telegram_count=_collection_status["stats"]["telegram_collected"],
                whatsapp_count=_collection_status["stats"]["whatsapp_collected"],
                verified_count=_collection_status["stats"]["verified_count"]
            )
        
        logger.info("✅ Collection completed")
        
    except Exception as e:
        logger.error(f"Error in collection loop: {e}")
        if _collection_status["current_session_id"]:
            update_collection_stats(
                _collection_status["current_session_id"],
                status="error"
            )
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
        logger.error("No session string provided")
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
            logger.error(f"Session {session_id} is not authorized")
            return
        
        # إضافة العميل إلى القائمة النشطة
        _collection_status["active_clients"].append(client)
        
        logger.info(f"Connected to session {session_id}")
        
        # جمع التاريخ القديم
        await _collect_history(client, session_id)
        
        # الاستماع للرسائل الجديدة
        await _listen_for_new_messages(client, session_id)
        
        # انتظار حتى التوقف
        await _stop_event.wait()
        
    except FloodWaitError as e:
        logger.warning(f"Flood wait for {e.seconds} seconds")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logger.error(f"Error in session {session_id}: {e}")
    finally:
        # إزالة العميل من القائمة النشطة
        if client and client in _collection_status["active_clients"]:
            _collection_status["active_clients"].remove(client)
        
        # قطع الاتصال
        if client:
            await client.disconnect()
            logger.info(f"Disconnected from session {session_id}")


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
    async for message in client.iter_messages(entity, reverse=True, limit=1000):
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
            # محاولة استخراج من الملفات
            if message.file:
                file_links = await extract_links_from_file(client, message)
                raw_links.extend(file_links)
        
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
        
        # فحص الروابط إذا كان مفعلاً
        verified_links = []
        if clean_links:
            verification_results = await verify_links_batch(clean_links)
            
            for result in verification_results:
                if result.get('is_valid'):
                    verified_links.append(result)
        
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
        
        # تحديث الإحصائيات في قاعدة البيانات
        if _collection_status["current_session_id"] and verified_links:
            update_collection_stats(
                _collection_status["current_session_id"],
                telegram_count=len([l for l in verified_links if l.get('platform') == 'telegram']),
                whatsapp_count=len([l for l in verified_links if l.get('platform') == 'whatsapp']),
                verified_count=len(verified_links)
            )
        
        # تسجيل التقدم
        if len(verified_links) > 0:
            logger.debug(f"Collected {len(verified_links)} links from message in session {session_id}")
            
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
# Quick Test
# ======================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        print("Testing collector module...")
        
        # اختبار الوظائف الأساسية
        print(f"Is collecting: {is_collecting()}")
        print(f"Is paused: {is_paused()}")
        print(f"Status: {get_collection_status()}")
        
        # محاولة البدء بدون جلسات
        result = await start_collection()
        print(f"Start collection result: {result}")
    
    asyncio.run(test())
