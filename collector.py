import asyncio
import logging
from typing import List, Dict
from datetime import datetime

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message, Channel, Chat, User
from telethon.errors import FloodWaitError, ChannelPrivateError

from config import API_ID, API_HASH
from database import save_link, get_sessions
from link_utils import (
    extract_links_from_message, clean_link, is_allowed_link,
    classify_platform, classify_telegram_link
)

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

_collection_lock = asyncio.Lock()
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
    """بدء الجمع الفعلي"""
    global _collection_status
    
    if _collection_status["running"]:
        logger.warning("Collection is already running")
        return False
    
    async with _collection_lock:
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
        asyncio.create_task(_run_collection())
        
        return True


async def pause_collection():
    if not _collection_status["running"] or _collection_status["paused"]:
        return False
    
    _collection_status["paused"] = True
    _pause_event.clear()
    logger.info("Collection paused")
    return True


async def resume_collection():
    if not _collection_status["running"] or not _collection_status["paused"]:
        return False
    
    _collection_status["paused"] = False
    _pause_event.set()
    logger.info("Collection resumed")
    return True


async def stop_collection():
    global _collection_status
    
    if not _collection_status["running"]:
        return False
    
    _collection_status["running"] = False
    _collection_status["paused"] = False
    _stop_event.set()
    _pause_event.set()
    
    # قطع اتصال جميع العملاء
    for client in _collection_status["active_clients"]:
        try:
            await client.disconnect()
        except:
            pass
    
    _collection_status["active_clients"] = []
    
    logger.info("Collection stopped completely")
    return True


# ======================
# Main Collection Loop
# ======================

async def _run_collection():
    """الحلقة الرئيسية للجمع الفعلي"""
    try:
        logger.info("🚀 Starting REAL link collection...")
        
        # جمع من جميع الجلسات
        sessions = get_sessions(active_only=True)
        
        if not sessions:
            logger.error("No active sessions found")
            return
        
        collection_tasks = []
        for session in sessions:
            task = asyncio.create_task(_collect_from_session(session))
            collection_tasks.append(task)
        
        # انتظار جميع المهام
        done, pending = await asyncio.wait(collection_tasks, return_when=asyncio.ALL_COMPLETED)
        
        logger.info(f"✅ Collection completed. Tasks: {len(done)} done, {len(pending)} pending")
        
    except Exception as e:
        logger.error(f"Error in collection loop: {e}")
    finally:
        _collection_status["running"] = False
        _collection_status["paused"] = False


# ======================
# Session Collection
# ======================

async def _collect_from_session(session_data: Dict):
    """الجمع من جلسة واحدة فعلياً"""
    session_string = session_data.get("session_string")
    session_id = session_data.get("id")
    display_name = session_data.get("display_name", f"Session_{session_id}")
    
    if not session_string:
        logger.error(f"No session string for session {session_id}")
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
        
        logger.info(f"✅ Connected to session: {display_name}")
        
        # جمع من جميع الدردشات
        await _collect_all_dialogs(client, session_id, display_name)
        
        # الاستماع للجديد
        await _listen_for_new_messages(client, session_id)
        
        # انتظار حتى التوقف
        await _stop_event.wait()
        
    except FloodWaitError as e:
        logger.warning(f"Flood wait for {e.seconds} seconds")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logger.error(f"Error in session {session_id}: {e}")
    finally:
        # إزالة العميل
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
# Collect All Dialogs
# ======================

async def _collect_all_dialogs(client: TelegramClient, session_id: int, display_name: str):
    """جمع من جميع الدردشات (القنوات، المجموعات، المحادثات)"""
    if not _collection_status["running"]:
        return
    
    logger.info(f"📂 Collecting from all dialogs for {display_name}...")
    
    total_collected = 0
    dialog_count = 0
    
    try:
        async for dialog in client.iter_dialogs():
            # التحقق من التوقف
            if not _collection_status["running"]:
                break
            
            await _pause_event.wait()  # انتظار إذا كان موقفاً
            
            dialog_count += 1
            try:
                collected = await _collect_from_dialog(client, dialog, session_id)
                total_collected += collected
                
                logger.info(f"  [{dialog_count}] {dialog.name}: {collected} links")
                
                # تأخير لمنع Flood
                await asyncio.sleep(1)
                
            except ChannelPrivateError:
                logger.warning(f"  ⚠️ {dialog.name}: Channel is private, skipping")
                continue
            except Exception as e:
                logger.error(f"  ❌ {dialog.name}: Error - {e}")
                continue
        
        logger.info(f"✅ {display_name}: Collected {total_collected} links from {dialog_count} dialogs")
        
    except Exception as e:
        logger.error(f"Error collecting dialogs for {display_name}: {e}")


async def _collect_from_dialog(client: TelegramClient, dialog, session_id: int) -> int:
    """جمع من دردشة واحدة"""
    collected = 0
    entity = dialog.entity
    
    try:
        # الحصول على جميع الرسائل من البداية
        async for message in client.iter_messages(entity, limit=None, reverse=True):
            # التحقق من التوقف
            if not _collection_status["running"]:
                break
            
            await _pause_event.wait()
            
            # معالجة الرسالة
            links_collected = await _process_message_for_collection(client, message, session_id)
            collected += links_collected
            
            # تأخير بسيط
            if collected % 100 == 0:
                await asyncio.sleep(0.1)
        
        return collected
        
    except Exception as e:
        logger.error(f"Error collecting from dialog {dialog.name}: {e}")
        return collected


# ======================
# Message Processing
# ======================

async def _process_message_for_collection(client: TelegramClient, message: Message, session_id: int) -> int:
    """معالجة رسالة لجمع الروابط"""
    collected = 0
    
    try:
        if not message:
            return 0
        
        # استخراج الروابط من النص
        raw_links = extract_links_from_message(message)
        
        # تنظيف وفلترة الروابط
        for raw_link in raw_links:
            cleaned = clean_link(raw_link)
            if cleaned and is_allowed_link(cleaned):
                # تصنيف الرابط
                platform = classify_platform(cleaned)
                
                if platform == "telegram":
                    link_type = classify_telegram_link(cleaned)
                    _collection_status["stats"]["telegram_collected"] += 1
                elif platform == "whatsapp":
                    link_type = "group" if "chat.whatsapp.com" in cleaned else "phone"
                    _collection_status["stats"]["whatsapp_collected"] += 1
                else:
                    link_type = "other"
                
                # حفظ الرابط
                save_link(
                    url=cleaned,
                    platform=platform,
                    link_type=link_type,
                    source_account=f"session_{session_id}",
                    chat_id=str(message.chat_id) if message.chat_id else None,
                    message_date=message.date,
                    is_verified=False,
                    verification_result="not_verified"
                )
                
                collected += 1
                _collection_status["stats"]["total_collected"] += 1
        
        return collected
        
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        return 0


# ======================
# Live Listening
# ======================

async def _listen_for_new_messages(client: TelegramClient, session_id: int):
    """الاستماع للرسائل الجديدة"""
    if not _collection_status["running"]:
        return
    
    @client.on(events.NewMessage)
    async def handler(event):
        if not _collection_status["running"]:
            return
        
        await _pause_event.wait()
        
        # معالجة الرسالة الجديدة
        await _process_message_for_collection(client, event.message, session_id)
    
    logger.info(f"👂 Listening for new messages in session {session_id}")
    
    # الاستمرار حتى التوقف
    await _stop_event.wait()


# ======================
# Bot Integration
# ======================

# دالة مساعدة للبوت
def get_collection_stats() -> Dict:
    """الحصول على إحصائيات الجمع"""
    return {
        "running": _collection_status["running"],
        "paused": _collection_status["paused"],
        "stats": _collection_status["stats"].copy(),
        "active_sessions": len(_collection_status["active_clients"])
    }


# ======================
# Test Function
# ======================

async def test_collector():
    """اختبار المجمع"""
    print("🧪 Testing collector...")
    
    # اختبار الوظائف الأساسية
    print(f"Is collecting: {is_collecting()}")
    print(f"Is paused: {is_paused()}")
    print(f"Status: {get_collection_status()}")
    
    # بدء جمع تجريبي (بدون جلسات حقيقية)
    print("\n🚀 Starting test collection...")
    
    # محاكاة إحصائيات
    _collection_status["stats"]["telegram_collected"] = 150
    _collection_status["stats"]["whatsapp_collected"] = 50
    _collection_status["stats"]["total_collected"] = 200
    
    print(f"Test stats: {_collection_status['stats']}")
    print("✅ Collector test completed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_collector())
