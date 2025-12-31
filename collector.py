import asyncio
import logging
from typing import List, Dict
from datetime import datetime

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message, Channel, Chat, User
from telethon.errors import FloodWaitError

from config import API_ID, API_HASH
from database import save_link, start_collection_session, update_collection_stats
from session_manager import get_active_sessions
from link_utils import extract_links_from_message, clean_link, is_allowed_link, verify_links_batch

logger = logging.getLogger(__name__)

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
_pause_event.set()

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
            "total_collected": 0,
            "verified_count": 0
        }
        
        _stop_event.clear()
        _pause_event.set()
        
        sessions = get_active_sessions()
        if not sessions:
            logger.error("No active sessions found")
            _collection_status["running"] = False
            return False
        
        collection_id = start_collection_session(sessions[0]["id"])
        _collection_status["current_session_id"] = collection_id
        
        asyncio.create_task(_run_collection())
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
    
    if _collection_status["current_session_id"]:
        update_collection_stats(
            _collection_status["current_session_id"],
            status="stopped",
            telegram_count=_collection_status["stats"]["telegram_collected"],
            whatsapp_count=_collection_status["stats"]["whatsapp_collected"],
            verified_count=_collection_status["stats"]["verified_count"]
        )
    
    return True

async def _run_collection():
    try:
        await asyncio.sleep(1)
        logger.info("🚀 Starting link collection...")
        
        sessions = get_active_sessions()
        collection_tasks = []
        
        for session in sessions:
            task = asyncio.create_task(_collect_from_session(session))
            collection_tasks.append(task)
        
        await asyncio.wait(collection_tasks, return_when=asyncio.FIRST_COMPLETED)
        
        for task in collection_tasks:
            task.cancel()
        
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
    finally:
        _collection_status["running"] = False
        _collection_status["paused"] = False

async def _collect_from_session(session_data: Dict):
    session_string = session_data.get("session_string")
    session_id = session_data.get("id")
    
    if not session_string:
        return
    
    client = None
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            return
        
        _collection_status["active_clients"].append(client)
        logger.info(f"Connected to session {session_id}")
        
        await _collect_history(client, session_id)
        await _listen_for_new_messages(client, session_id)
        await _stop_event.wait()
        
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logger.error(f"Error in session {session_id}: {e}")
    finally:
        if client and client in _collection_status["active_clients"]:
            _collection_status["active_clients"].remove(client)
        
        if client:
            await client.disconnect()

async def _collect_history(client: TelegramClient, session_id: int):
    if not _collection_status["running"]:
        return
    
    try:
        async for dialog in client.iter_dialogs():
            if not _collection_status["running"]:
                break
            
            await _pause_event.wait()
            
            try:
                await _process_dialog(client, dialog, session_id)
            except:
                continue
            
            await asyncio.sleep(0.5)
    
    except Exception as e:
        logger.error(f"Error collecting history: {e}")

async def _process_dialog(client: TelegramClient, dialog, session_id: int):
    async for message in client.iter_messages(dialog.entity, reverse=True, limit=500):
        if not _collection_status["running"]:
            break
        
        await _pause_event.wait()
        await _process_message(client, message, session_id)
        await asyncio.sleep(0.1)

async def _listen_for_new_messages(client: TelegramClient, session_id: int):
    @client.on(events.NewMessage)
    async def handler(event):
        if not _collection_status["running"]:
            return
        
        await _pause_event.wait()
        await _process_message(client, event.message, session_id)
    
    await _stop_event.wait()

async def _process_message(client: TelegramClient, message: Message, session_id: int):
    try:
        raw_links = extract_links_from_message(message)
        
        clean_links = []
        for link in raw_links:
            cleaned = clean_link(link)
            if cleaned and is_allowed_link(cleaned):
                clean_links.append(cleaned)
        
        if not clean_links:
            return
        
        verified_links = await verify_links_batch(clean_links)
        
        for link_data in verified_links:
            url = link_data.get('url')
            platform = link_data.get('platform')
            link_type = link_data.get('link_type')
            
            if not url or not platform:
                continue
            
            async with _collection_lock:
                if platform == "telegram":
                    _collection_status["stats"]["telegram_collected"] += 1
                elif platform == "whatsapp":
                    _collection_status["stats"]["whatsapp_collected"] += 1
                
                _collection_status["stats"]["total_collected"] += 1
                _collection_status["stats"]["verified_count"] += 1
            
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
        
        if _collection_status["current_session_id"] and verified_links:
            update_collection_stats(
                _collection_status["current_session_id"],
                telegram_count=len([l for l in verified_links if l.get('platform') == 'telegram']),
                whatsapp_count=len([l for l in verified_links if l.get('platform') == 'whatsapp']),
                verified_count=len(verified_links)
            )
            
    except Exception as e:
        pass

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        print(f"Is collecting: {is_collecting()}")
        print(f"Is paused: {is_paused()}")
    
    asyncio.run(test())
