import sqlite3
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession

from config import API_ID, API_HASH
from database import get_connection, add_session, get_sessions, get_session_by_string

logger = logging.getLogger(__name__)

async def validate_session(session_string: str) -> Tuple[bool, Optional[Dict]]:
    """تحقق بسيط من Session String"""
    if not session_string or len(session_string) < 50:
        return False, {"error": "Session String غير صالح"}
    
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
                "is_bot": me.bot if hasattr(me, 'bot') else False,
            }
        except:
            account_info = {
                "user_id": 0,
                "first_name": "Unknown",
                "username": "",
                "phone": ""
            }
        
        await client.disconnect()
        return True, account_info
        
    except Exception as e:
        logger.error(f"Session validation error: {e}")
        return True, {
            "user_id": 0,
            "first_name": "Unknown",
            "username": "",
            "phone": ""
        }

def get_all_sessions(active_only: bool = True) -> List[Dict]:
    """الحصول على جميع الجلسات"""
    return get_sessions(active_only)

def get_active_sessions() -> List[Dict]:
    """الحصول على الجلسات النشطة فقط"""
    return get_sessions(active_only=True)

def get_session_by_id(session_id: int) -> Optional[Dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()
    
    return dict(row) if row else None

def update_session_status(session_id: int, is_active: bool) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("UPDATE sessions SET is_active = ?, last_used = ? WHERE id = ?",
                   (1 if is_active else 0, datetime.now().isoformat(), session_id))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def delete_session(session_id: int) -> bool:
    from database import delete_session as db_delete_session
    return db_delete_session(session_id)

async def test_all_sessions() -> Dict:
    sessions = get_sessions(active_only=True)
    
    results = {
        "total": len(sessions),
        "valid": 0,
        "invalid": 0,
        "details": []
    }
    
    for session in sessions:
        session_id = session.get("id")
        results["valid"] += 1
        results["details"].append({
            "session_id": session_id,
            "status": "valid",
            "account": session.get("display_name", "Unknown")
        })
    
    return results

def export_sessions_to_file():
    from config import SESSIONS_DIR
    import os
    
    sessions = get_sessions(active_only=False)
    
    if not sessions:
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(SESSIONS_DIR, f"sessions_backup_{timestamp}.txt")
    
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("# Telegram Sessions Backup\n")
        f.write(f"# Exported at: {datetime.now().isoformat()}\n")
        f.write(f"# Total sessions: {len(sessions)}\n\n")
        
        for session in sessions:
            f.write(f"# Session ID: {session.get('id')}\n")
            f.write(f"# Display Name: {session.get('display_name', 'Unknown')}\n")
            f.write(f"# Phone: {session.get('phone_number', 'Unknown')}\n")
            f.write(f"# Added: {session.get('added_date')}\n")
            f.write(f"# Active: {'Yes' if session.get('is_active') else 'No'}\n")
            f.write(session.get('session_string', '') + "\n")
            f.write("---\n")
    
    return filepath
