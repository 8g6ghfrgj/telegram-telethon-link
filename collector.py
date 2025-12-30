import asyncio
import logging
from typing import List, Dict
from datetime import datetime

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message, Channel, Chat, User
from telethon.errors import FloodWaitError

from config import API_ID, API_HASH
from database import save_link, get_sessions
from session_manager import get_active_sessions
from link_utils import extract_links_from_message, clean_link, classify_platform, classify_telegram_link

logger = logging.getLogger(__name__)

_collection_status = {
    "running": False,
    "paused": False,
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

_clients = []

def get_collection_status() -> Dict:
    return _collection_status.copy()

def is_collecting() -> bool:
    return _collection_status["running"]

def is_paused() -> bool:
    return _collection_status["paused"]

async def start_collection():
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
        
        sessions = get_sessions(active_only=True)
        if not sessions:
            logger.error("No active sessions found")
            _collection_status["running"] = False
            return False
        
        logger.info(f"🚀 Starting collection with {len(sessions)} sessions")
        
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
    
    # إيقاف جميع العملاء
    for client in _clients:
        try:
            await client.disconnect()
        except:
            pass
    
    _clients.clear()
    logger.info("Collection stopped completely")
    return True

async def _run_collection():
    try:
        logger.info("🚀 Starting link collection...")
        
        sessions = get_active_sessions()
        collection_tasks = []
        
        for session in sessions:
            task = asyncio.create_task(_collect_from_session(session))
            collection_tasks.append(task)
        
        await asyncio.wait(collection_tasks, return_when=asyncio.FIRST_COMPLETED)
        
        for task in collection_tasks:
            task.cancel()
        
        logger.info("✅ Collection completed")
        
    except Exception as e:
        logger.error(f"Error in collection loop: {e}")
    finally:
        _collection_status["running"] = False
        _collection_status["paused"] = False

async def _collect_from_session(session_data: Dict):
    session_string = session_data.get("session_string")
    session_id = session_data.get("id")
    
    if not session_string:
        logger.error("No session string provided")
        return
    
    client = None
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            logger.error(f"Session {session_id} is not authorized")
            return
        
        _clients.append(client)
        logger.info(f"Connected to session {session_id}")
        
        # جمع التاريخ
        await _collect_history(client, session_id)
        
        # الانتظار حتى التوقف
        await _stop_event.wait()
        
    except FloodWaitError as e:
        logger.warning(f"Flood wait for {e.seconds} seconds")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logger.error(f"Error in session {session_id}: {e}")
    finally:
        if client and client in _clients:
            _clients.remove(client)
        
        if client:
            try:
                await client.disconnect()
            except:
                pass

async def _collect_history(client: TelegramClient, session_id: int):
    if not _collection_status["running"]:
        return
    
    logger.info(f"Collecting history from session {session_id}")
    
    try:
        async for dialog in client.iter_dialogs(limit=100):
            if not _collection_status["running"]:
                break
            
            await _pause_event.wait()
            
            try:
                await _process_dialog(client, dialog, session_id)
            except Exception as e:
                logger.error(f"Error processing dialog {dialog.name}: {e}")
                continue
            
            await asyncio.sleep(0.5)
    
    except Exception as e:
        logger.error(f"Error collecting history: {e}")

async def _process_dialog(client: TelegramClient, dialog, session_id: int):
    entity = dialog.entity
    
    try:
        # جمع جميع الرسائل من البداية
        async for message in client.iter_messages(entity, reverse=True, limit=10000):
            if not _collection_status["running"]:
                break
            
            await _pause_event.wait()
            
            await _process_message(client, message, session_id)
            
            await asyncio.sleep(0.05)
    
    except Exception as e:
        logger.error(f"Error processing messages in dialog {dialog.name}: {e}")

async def _process_message(client: TelegramClient, message: Message, session_id: int):
    try:
        if not message:
            return
        
        raw_links = extract_links_from_message(message)
        
        if not raw_links:
            return
        
        for link in raw_links:
            cleaned = clean_link(link)
            if not cleaned:
                continue
            
            platform = classify_platform(cleaned)
            
            if platform == "telegram":
                link_type = classify_telegram_link(cleaned)
                
                async with _collection_lock:
                    _collection_status["stats"]["telegram_collected"] += 1
                    _collection_status["stats"]["total_collected"] += 1
                
                save_link(
                    url=cleaned,
                    platform=platform,
                    link_type=link_type,
                    source_account=f"session_{session_id}",
                    chat_id=str(message.chat_id) if message.chat_id else None,
                    message_date=message.date
                )
                
                logger.debug(f"📨 Telegram link saved: {cleaned}")
            
            elif platform == "whatsapp":
                # تحقق من تاريخ رسالة الواتساب (آخر 6 أشهر)
                if message.date:
                    six_months_ago = datetime.now().timestamp() - (6 * 30 * 24 * 60 * 60)
                    message_timestamp = message.date.timestamp()
                    
                    if message_timestamp >= six_months_ago:
                        async with _collection_lock:
                            _collection_status["stats"]["whatsapp_collected"] += 1
                            _collection_status["stats"]["total_collected"] += 1
                        
                        save_link(
                            url=cleaned,
                            platform=platform,
                            link_type="group" if "chat.whatsapp.com" in cleaned else "phone",
                            source_account=f"session_{session_id}",
                            chat_id=str(message.chat_id) if message.chat_id else None,
                            message_date=message.date
                        )
                        
                        logger.debug(f"📞 WhatsApp link saved: {cleaned}")
            
            if _collection_status["stats"]["total_collected"] % 100 == 0:
                logger.info(f"📊 Progress: {_collection_status['stats']['total_collected']} links collected")
    
    except Exception as e:
        logger.error(f"Error processing message: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        print("Testing collector...")
        print(f"Is collecting: {is_collecting()}")
    
    asyncio.run(test())
