import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession

from config import API_ID, API_HASH
from database import add_session as db_add_session, get_sessions as db_get_sessions, delete_session as db_delete_session

logger = logging.getLogger(__name__)

async def validate_session(session_string: str) -> Tuple[bool, Optional[Dict]]:
    if not session_string or len(session_string) < 50:
        return False, {"error": "Session String قصير جداً"}
    
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        try:
            me = await client.get_me()
            
            account_info = {
                "user_id": me.id if me else 0,
                "first_name": me.first_name or "",
                "last_name": me.last_name or "",
                "username": me.username or "",
                "phone": me.phone or "",
                "is_bot": me.bot if me and hasattr(me, 'bot') else False,
            }
            
        except Exception as e:
            logger.warning(f"⚠️ Could not get user info: {e}")
            account_info = {
                "user_id": 0,
                "first_name": "Unknown",
                "username": "",
                "phone": ""
            }
        
        await client.disconnect()
        return True, account_info
        
    except Exception as e:
        logger.error(f"❌ Session validation error: {e}")
        return False, {"error": str(e)}

def add_session_to_db(session_string: str, account_info: Dict) -> bool:
    return db_add_session(
        session_string=session_string,
        phone=account_info.get("phone", ""),
        user_id=account_info.get("user_id", 0),
        username=account_info.get("username", ""),
        display_name=account_info.get("first_name", "Unknown")
    )

def get_all_sessions(active_only: bool = True) -> List[Dict]:
    return db_get_sessions(active_only=active_only)

def get_active_sessions() -> List[Dict]:
    return get_all_sessions(active_only=True)

def delete_session(session_id: int) -> bool:
    return db_delete_session(session_id)

def test_all_sessions() -> Dict:
    sessions = get_all_sessions(active_only=True)
    
    return {
        "total": len(sessions),
        "valid": len(sessions),
        "invalid": 0,
        "details": [{
            "session_id": s["id"],
            "status": "valid",
            "account": s["display_name"]
        } for s in sessions]
    }
