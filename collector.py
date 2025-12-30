import asyncio
import logging
from typing import List, Dict
from datetime import datetime, timedelta

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message, Channel, Chat, User
from telethon.errors import FloodWaitError

from config import API_ID, API_HASH, COLLECT_TELEGRAM, COLLECT_WHATSAPP, MAX_HISTORY_DAYS, MAX_WHATSAPP_DAYS
from database import save_link, get_sessions
from link_utils import extract_links_from_message, clean_link, is_allowed_link, classify_platform

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
    "current_session": None,
    "stats": {
        "telegram_collected": 0,
        "whatsapp_collected": 0,
        "total_collected": 0
    }
}

_stop_event = asyncio.Event()
_pause_event = asyncio.Event()
_pause_event.set()

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
    """بدء الجمع فعلياً"""
    global _collection_status
    
    if _collection_status["running"]:
        return False
    
    # الحصول على الجلسات النشطة
    sessions = get_sessions(active_only=True)
    if not sessions:
        logger.error("لا توجد جلسات نشطة")
        return False
    
    _collection_status["running"] = True
    _collection_status["paused"] = False
    _collection_status["stats"] = {
        "telegram_collected": 0,
        "whatsapp_collected": 0,
        "total_collected": 0
    }
    
    _stop_event.clear()
    _pause_event.set()
    
    # بدء الجمع في الخلفية
    asyncio.create_task(_collect_all_sessions(sessions))
    
    return True

async def pause_collection():
    if not _collection_status["running"] or _collection_status["paused"]:
        return False
    
    _collection_status["paused"] = True
    _pause_event.clear()
    return True

async def resume_collection():
    if not _collection_status["running"] or not _collection_status["paused"]:
        return False
    
    _collection_status["paused"] = False
    _pause_event.set()
    return True

async def stop_collection():
    global _collection_status
    
    if not _collection_status["running"]:
        return False
    
    _collection_status["running"] = False
    _collection_status["paused"] = False
    _stop_event.set()
    _pause_event.set()
    
    return True

# ======================
# Collection Functions
# ======================

async def _collect_all_sessions(sessions: List[Dict]):
    """الجمع من جميع الجلسات"""
    try:
        logger.info(f"🚀 بدأ جمع الروابط من {len(sessions)} جلسة")
        
        tasks = []
        for session in sessions:
            task = asyncio.create_task(_collect_from_session(session))
            tasks.append(task)
        
        # انتظار جميع المهام
        await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info("✅ اكتمل جمع الروابط")
        
    except Exception as e:
        logger.error(f"خطأ في الجمع: {e}")
    finally:
        _collection_status["running"] = False

async def _collect_from_session(session_data: Dict):
    """الجمع من جلسة واحدة"""
    session_string = session_data.get("session_string")
    session_id = session_data.get("id")
    
    if not session_string:
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
            logger.error(f"الجلسة {session_id} غير مصرح بها")
            return
        
        logger.info(f"✅ متصل بالجلسة {session_id}")
        
        # جمع التاريخ القديم
        await _collect_history(client, session_id)
        
        # الاستماع للجديد
        await _listen_for_messages(client, session_id)
        
        # انتظار حتى التوقف
        await _stop_event.wait()
        
    except FloodWaitError as e:
        logger.warning(f"انتظر {e.seconds} ثانية...")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logger.error(f"خطأ في الجلسة {session_id}: {e}")
    finally:
        if client:
            await client.disconnect()
            logger.info(f"✅ انقطع عن الجلسة {session_id}")

async def _collect_history(client: TelegramClient, session_id: int):
    """جمع التاريخ القديم"""
    if not _collection_status["running"]:
        return
    
    logger.info(f"جمع التاريخ من الجلسة {session_id}")
    
    try:
        # حساب التواريخ
        telegram_cutoff = datetime.now() - timedelta(days=MAX_HISTORY_DAYS)
        whatsapp_cutoff = datetime.now() - timedelta(days=MAX_WHATSAPP_DAYS)
        
        # جمع من جميع الدردشات
        async for dialog in client.iter_dialogs(limit=100):  # 100 دردشة كحد أقصى
            if not _collection_status["running"]:
                break
            
            await _pause_event.wait()
            
            try:
                await _collect_from_dialog(client, dialog, session_id, telegram_cutoff, whatsapp_cutoff)
            except Exception as e:
                logger.error(f"خطأ في {dialog.name}: {e}")
                continue
            
            await asyncio.sleep(1)  # منع Flood
        
    except Exception as e:
        logger.error(f"خطأ في جمع التاريخ: {e}")

async def _collect_from_dialog(client: TelegramClient, dialog, session_id: int, 
                              telegram_cutoff, whatsapp_cutoff):
    """جمع من دردشة واحدة"""
    entity = dialog.entity
    
    # تحديد تاريخ القطع حسب المنصة
    is_telegram = True  # نفترض تليجرام أولاً
    
    # الحصول على الرسائل
    try:
        async for message in client.iter_messages(entity, reverse=True, limit=10000):
            if not _collection_status["running"]:
                break
            
            await _pause_event.wait()
            
            # معالجة الرسالة
            await _process_message_for_collection(client, message, session_id, 
                                                 telegram_cutoff, whatsapp_cutoff)
            
            # تأخير لمنع Flood
            await asyncio.sleep(0.1)
            
    except Exception as e:
        logger.error(f"خطأ في قراءة الرسائل: {e}")

async def _listen_for_messages(client: TelegramClient, session_id: int):
    """الاستماع للرسائل الجديدة"""
    @client.on(events.NewMessage)
    async def handler(event):
        if not _collection_status["running"]:
            return
        
        await _pause_event.wait()
        
        await _process_message_for_collection(
            client, event.message, session_id,
            datetime.now() - timedelta(days=MAX_HISTORY_DAYS),
            datetime.now() - timedelta(days=MAX_WHATSAPP_DAYS)
        )
    
    logger.info(f"👂 يستمع للجديد في الجلسة {session_id}")
    
    # البقاء نشطاً حتى التوقف
    await _stop_event.wait()

async def _process_message_for_collection(client: TelegramClient, message: Message, 
                                         session_id: int, telegram_cutoff, whatsapp_cutoff):
    """معالجة رسالة للجمع"""
    try:
        if not message or not message.text:
            return
        
        # استخراج الروابط
        raw_links = extract_links_from_message(message)
        
        if not raw_links:
            return
        
        # معالجة كل رابط
        for link in raw_links:
            # تنظيف الرابط
            cleaned_link = clean_link(link)
            if not cleaned_link:
                continue
            
            # التحقق إذا كان مسموحاً به
            if not is_allowed_link(cleaned_link):
                continue
            
            # تصنيف المنصة
            platform = classify_platform(cleaned_link)
            
            # التحقق من تاريخ القطع
            message_date = message.date
            if platform == "telegram" and message_date < telegram_cutoff:
                continue
            elif platform == "whatsapp" and message_date < whatsapp_cutoff:
                continue
            
            # تحديد النوع
            link_type = "unknown"
            if platform == "telegram":
                if "t.me/joinchat/" in cleaned_link:
                    link_type = "private_group"
                elif "t.me/+" in cleaned_link:
                    link_type = "public_group"
                elif "t.me/" in cleaned_link and "/" in cleaned_link.split("t.me/")[1]:
                    # تحقق إذا كان رابط رسالة
                    if cleaned_link.count("/") >= 2:
                        link_type = "message"
                    else:
                        link_type = "channel"
                elif "bot" in cleaned_link.lower():
                    link_type = "bot"
            
            elif platform == "whatsapp":
                if "chat.whatsapp.com" in cleaned_link:
                    link_type = "group"
                elif "wa.me" in cleaned_link:
                    link_type = "phone"
            
            # حفظ الرابط
            save_link(
                url=cleaned_link,
                platform=platform,
                link_type=link_type,
                source_account=f"session_{session_id}",
                chat_id=str(message.chat_id) if message.chat_id else None,
                message_date=message.date,
                is_verified=False,
                verification_result=None,
                metadata={}
            )
            
            # تحديث الإحصائيات
            if platform == "telegram":
                _collection_status["stats"]["telegram_collected"] += 1
            elif platform == "whatsapp":
                _collection_status["stats"]["whatsapp_collected"] += 1
            
            _collection_status["stats"]["total_collected"] += 1
            
            logger.debug(f"جمع رابط: {cleaned_link}")
            
    except Exception as e:
        logger.error(f"خطأ في معالجة الرسالة: {e}")

# ======================
# Test Function
# ======================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        print("اختبار المجمع...")
        result = await start_collection()
        print(f"النتيجة: {result}")
        await asyncio.sleep(5)
        await stop_collection()
    
    asyncio.run(test())
