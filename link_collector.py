"""
محرك جمع الروابط من جميع الجلسات
"""

import asyncio
import logging
from typing import List, Dict
from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message

from config import API_ID, API_HASH
from database import save_link
from link_utils import extract_links_from_message, clean_link

logger = logging.getLogger(__name__)


async def collect_links_from_sessions(sessions: List[Dict]) -> Dict:
    """
    جمع الروابط من جميع الجلسات
    """
    results = {
        "total_sessions": len(sessions),
        "sessions_processed": 0,
        "links_collected": 0,
        "errors": 0,
        "start_time": datetime.now()
    }
    
    for session in sessions:
        try:
            links = await collect_from_session(session)
            results["links_collected"] += links
            results["sessions_processed"] += 1
            
            logger.info(f"Session {session['id']}: Collected {links} links")
            
        except Exception as e:
            logger.error(f"Error in session {session['id']}: {e}")
            results["errors"] += 1
        
        # تأخير بين الجلسات
        await asyncio.sleep(1)
    
    results["end_time"] = datetime.now()
    results["duration"] = (results["end_time"] - results["start_time"]).total_seconds()
    
    return results


async def collect_from_session(session_data: Dict, limit_messages: int = None) -> int:
    """
    جمع الروابط من جلسة واحدة
    """
    session_string = session_data.get('session_string')
    if not session_string:
        return 0
    
    links_collected = 0
    
    try:
        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH
        )
        
        await client.connect()
        
        if not await client.is_user_authorized():
            logger.warning(f"Session {session_data['id']} not authorized")
            return 0
        
        # جمع من جميع الدردشات
        async for dialog in client.iter_dialogs(limit=None):
            try:
                # حساب عدد الرسائل في الدردشة
                total_messages = await client.get_messages(dialog.entity, limit=1)
                if hasattr(total_messages, 'total'):
                    message_count = total_messages.total
                else:
                    message_count = 1000  # افتراضي
                
                logger.info(f"Processing {dialog.name}: {message_count} messages")
                
                # جمع الرسائل
                async for message in client.iter_messages(
                    dialog.entity,
                    limit=limit_messages or message_count,  # جميع الرسائل
                    reverse=True
                ):
                    # استخراج الروابط
                    links = extract_links_from_message(message)
                    
                    for link in links:
                        cleaned = clean_link(link)
                        if cleaned:
                            # تحديد المنصة والنوع
                            platform, link_type = classify_link(cleaned)
                            
                            # حفظ الرابط
                            save_link(
                                url=cleaned,
                                platform=platform,
                                link_type=link_type,
                                source_account=session_data.get('display_name', f"session_{session_data['id']}"),
                                chat_id=str(dialog.id),
                                message_date=message.date,
                                is_verified=False
                            )
                            
                            links_collected += 1
                    
                    # تأخير بسيط
                    await asyncio.sleep(0.005)
                    
            except Exception as e:
                logger.error(f"Error in dialog {dialog.name}: {e}")
                continue
        
        await client.disconnect()
        
    except Exception as e:
        logger.error(f"Error in session {session_data['id']}: {e}")
    
    return links_collected


def classify_link(url: str) -> tuple:
    """
    تصنيف الرابط إلى منصة ونوع
    """
    url_lower = url.lower()
    
    # تليجرام
    if "t.me" in url_lower:
        platform = "telegram"
        
        if "joinchat" in url_lower:
            link_type = "private_group"
        elif url_lower.startswith("https://t.me/+"):
            link_type = "public_group"
        elif "/c/" in url_lower:
            link_type = "channel"
        elif "/" in url_lower and url_lower.split("/")[-1].isdigit():
            link_type = "message"
        elif "bot" in url_lower:
            link_type = "bot"
        else:
            link_type = "channel"
    
    # واتساب
    elif "whatsapp.com" in url_lower or "wa.me" in url_lower:
        platform = "whatsapp"
        if "chat.whatsapp.com" in url_lower:
            link_type = "group"
        else:
            link_type = "phone"
    
    # أخرى
    else:
        platform = "other"
        link_type = "unknown"
    
    return platform, link_type


# ======================
# Quick Test
# ======================

async def test_collector():
    """اختبار المحرك"""
    print("🧪 Testing link collector...")
    
    # بيانات جلسة تجريبية
    test_session = {
        "id": 1,
        "session_string": "test",
        "display_name": "Test Session"
    }
    
    try:
        result = await collect_from_session(test_session, limit_messages=10)
        print(f"Test collected: {result} links")
    except Exception as e:
        print(f"Test error: {e}")
    
    print("✅ Collector test completed")


if __name__ == "__main__":
    asyncio.run(test_collector())
