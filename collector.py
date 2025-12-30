import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

from config import API_ID, API_HASH
from database import (
    save_link,
    link_exists,
    start_collection_session,
    update_collection_stats,
)
from session_manager import get_active_sessions
from link_utils import (
    extract_links_from_message,
    extract_links_from_file,
    normalize_telegram_link,
    is_valid_telegram_group_link,
    is_valid_whatsapp_group_link,
)

logger = logging.getLogger(__name__)

# ======================
# Global State
# ======================

_running = False
_pause_event = asyncio.Event()
_stop_event = asyncio.Event()
_pause_event.set()

_stats = {
    "telegram": 0,
    "whatsapp": 0,
}


# ======================
# Public Controls
# ======================

async def start_collection():
    global _running

    if _running:
        return False

    _running = True
    _stop_event.clear()
    _pause_event.set()
    _stats["telegram"] = 0
    _stats["whatsapp"] = 0

    sessions = get_active_sessions()
    if not sessions:
        _running = False
        return False

    collection_id = start_collection_session(sessions[0]["id"])

    tasks = []
    for session in sessions:
        tasks.append(asyncio.create_task(_run_session(session, collection_id)))

    asyncio.create_task(_wait_for_stop(tasks, collection_id))
    return True


async def pause_collection():
    _pause_event.clear()


async def resume_collection():
    _pause_event.set()


async def stop_collection():
    global _running
    _running = False
    _stop_event.set()
    _pause_event.set()


# ======================
# Internal
# ======================

async def _wait_for_stop(tasks, collection_id):
    await _stop_event.wait()

    for task in tasks:
        task.cancel()

    update_collection_stats(
        collection_id,
        status="completed",
        telegram_count=_stats["telegram"],
        whatsapp_count=_stats["whatsapp"],
    )


async def _run_session(session: Dict, collection_id: int):
    client = TelegramClient(
        StringSession(session["session_string"]),
        API_ID,
        API_HASH,
    )

    try:
        await client.connect()
        if not await client.is_user_authorized():
            return

        logger.info(f"Session connected: {session['id']}")

        await _collect_history(client, session["id"], collection_id)
        await _listen_live(client, session["id"], collection_id)

    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
    finally:
        await client.disconnect()


# ======================
# History
# ======================

async def _collect_history(client: TelegramClient, session_id: int, collection_id: int):
    six_months_ago = datetime.utcnow() - timedelta(days=180)

    async for dialog in client.iter_dialogs():
        if not dialog.is_group:
            continue

        async for message in client.iter_messages(dialog.entity, reverse=True):
            if not _running:
                return

            await _pause_event.wait()
            await _process_message(
                client, message, session_id, collection_id, six_months_ago
            )


# ======================
# Live
# ======================

async def _listen_live(client, session_id, collection_id):
    @client.on(events.NewMessage)
    async def handler(event):
        if not _running:
            return

        await _pause_event.wait()
        await _process_message(
            client,
            event.message,
            session_id,
            collection_id,
            datetime.utcnow() - timedelta(days=180),
        )

    await _stop_event.wait()


# ======================
# Core Logic
# ======================

async def _process_message(
    client,
    message,
    session_id: int,
    collection_id: int,
    whatsapp_limit_date: datetime,
):
    links = extract_links_from_message(message)

    if message.file:
        file_links = await extract_links_from_file(client, message)
        links.extend(file_links)

    for url in links:
        # -------- Telegram --------
        if is_valid_telegram_group_link(url):
            normalized = normalize_telegram_link(url)
            if link_exists(normalized):
                continue

            save_link(
                url=normalized,
                platform="telegram",
                link_type="group",
                source_account=f"session_{session_id}",
                chat_id=str(message.chat_id),
                message_date=message.date,
                is_verified=True,
                verification_result="valid",
            )

            _stats["telegram"] += 1
            update_collection_stats(collection_id, telegram_count=1)

        # -------- WhatsApp --------
        elif is_valid_whatsapp_group_link(url):
            if message.date and message.date < whatsapp_limit_date:
                continue

            if link_exists(url):
                continue

            save_link(
                url=url,
                platform="whatsapp",
                link_type="group",
                source_account=f"session_{session_id}",
                chat_id=str(message.chat_id),
                message_date=message.date,
                is_verified=True,
                verification_result="valid",
            )

            _stats["whatsapp"] += 1
            update_collection_stats(collection_id, whatsapp_count=1)
