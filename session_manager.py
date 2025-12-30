import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import AuthKeyError, SessionPasswordNeededError

from config import API_ID, API_HASH
from database import (
    add_session,
    get_sessions,
    update_session_status
)

logger = logging.getLogger(__name__)

# ======================
# Validation
# ======================

async def validate_session(session_string: str) -> Tuple[bool, Optional[Dict]]:
    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)

    try:
        await client.connect()
        if not await client.is_user_authorized():
            return False, {"error": "Session غير مصرح"}

        me = await client.get_me()
        return True, {
            "user_id": me.id,
            "username": me.username,
            "phone": me.phone,
            "first_name": me.first_name,
        }

    except (AuthKeyError, SessionPasswordNeededError):
        return False, {"error": "Session غير صالح أو محمي"}
    except Exception as e:
        return False, {"error": str(e)}
    finally:
        await client.disconnect()


# ======================
# Public helpers
# ======================

def get_active_sessions() -> List[Dict]:
    return get_sessions(active_only=True)


def disable_session(session_id: int):
    update_session_status(session_id, False)


async def test_all_sessions() -> Dict:
    sessions = get_sessions(active_only=True)
    results = {"total": len(sessions), "valid": 0, "invalid": 0}

    for s in sessions:
        valid, _ = await validate_session(s["session_string"])
        if valid:
            results["valid"] += 1
        else:
            results["invalid"] += 1
            disable_session(s["id"])

    return results
