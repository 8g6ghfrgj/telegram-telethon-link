import asyncio
import logging
from pyrogram import Client
from pyrogram.errors import (
    AuthKeyUnregistered, 
    SessionRevoked, 
    AccessTokenExpired, 
    AuthKeyDuplicated
)
from typing import Dict, List, Tuple, Optional
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class SessionManager:
    def __init__(self):
        self.active_sessions = {}
        
    async def validate_session(self, session_string: str) -> Tuple[bool, Dict]:
        """
        التحقق من صحة جلسة التليجرام
        
        Args:
            session_string: نص جلسة التليجرام
            
        Returns:
            tuple: (is_valid, account_info)
        """
        try:
            # إنشاء عميل مؤقت للتحقق
            client = Client(
                name="session_validator",
                session_string=session_string,
                in_memory=True,
                no_updates=True
            )
            
            await client.connect()
            
            # الحصول على معلومات الحساب
            me = await client.get_me()
            
            account_info = {
                'user_id': me.id,
                'phone_number': me.phone_number,
                'username': me.username,
                'first_name': me.first_name,
                'last_name': me.last_name,
                'is_bot': me.is_bot,
                'language_code': me.language_code
            }
            
            await client.disconnect()
            
            return True, account_info
            
        except AuthKeyUnregistered:
            return False, {'error': 'الجلسة غير مسجلة أو منتهية'}
        except SessionRevoked:
            return False, {'error': 'تم إلغاء الجلسة'}
        except AccessTokenExpired:
            return False, {'error': 'انتهت صلاحية رمز الوصول'}
        except AuthKeyDuplicated:
            return False, {'error': 'تم استخدام الجلسة من مكان آخر'}
        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return False, {'error': f'خطأ غير متوقع: {str(e)}'}
    
    async def create_session_client(self, session_id: int, session_string: str, session_name: str = None) -> Optional[Client]:
        """
        إنشاء عميل جلسة
        
        Args:
            session_id: معرف الجلسة
            session_string: نص الجلسة
            session_name: اسم الجلسة (اختياري)
            
        Returns:
            Client or None
        """
        try:
            if not session_name:
                session_name = f"session_{session_id}"
            
            client = Client(
                name=session_name,
                session_string=session_string,
                in_memory=True
            )
            
            # اختبار الاتصال
            await client.connect()
            await client.get_me()
            
            self.active_sessions[session_id] = {
                'client': client,
                'last_used': datetime.now(),
                'is_active': True
            }
            
            return client
            
        except Exception as e:
            logger.error(f"Error creating session client: {e}")
            return None
    
    async def close_session(self, session_id: int):
        """إغلاق جلسة"""
        if session_id in self.active_sessions:
            try:
                client_data = self.active_sessions[session_id]
                await client_data['client'].disconnect()
                await client_data['client'].stop()
            except:
                pass
            
            del self.active_sessions[session_id]
    
    async def close_all_sessions(self):
        """إغلاق جميع الجلسات"""
        for session_id in list(self.active_sessions.keys()):
            await self.close_session(session_id)
    
    async def test_all_sessions(self, sessions_data: List[Dict]) -> Dict:
        """
        اختبار جميع الجلسات
        
        Args:
            sessions_data: قائمة بيانات الجلسات
            
        Returns:
            dict: نتائج الاختبار
        """
        results = {
            'total': len(sessions_data),
            'valid': 0,
            'invalid': 0,
            'details': []
        }
        
        for session in sessions_data:
            session_id = session.get('id')
            session_string = session.get('session_string')
            
            if not session_string:
                continue
            
            is_valid, info = await self.validate_session(session_string)
            
            result = {
                'session_id': session_id,
                'is_valid': is_valid,
                'info': info if is_valid else info.get('error', 'خطأ غير معروف')
            }
            
            results['details'].append(result)
            
            if is_valid:
                results['valid'] += 1
            else:
                results['invalid'] += 1
        
        return results

# وظائف مساعدة لقاعدة البيانات
def add_session_to_db(session_string: str, account_info: Dict) -> bool:
    """
    إضافة جلسة إلى قاعدة البيانات
    
    Args:
        session_string: نص الجلسة
        account_info: معلومات الحساب
        
    Returns:
        bool: True إذا نجحت الإضافة
    """
    from database import get_connection
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        display_name = account_info.get('first_name', '')
        if account_info.get('username'):
            display_name = f"@{account_info.get('username')}"
        elif not display_name:
            display_name = f"حساب {account_info.get('user_id')}"
        
        cur.execute('''
            INSERT INTO sessions 
            (session_string, phone_number, username, user_id, 
             first_name, display_name, added_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session_string,
            account_info.get('phone_number', ''),
            account_info.get('username', ''),
            account_info.get('user_id', ''),
            account_info.get('first_name', ''),
            display_name,
            datetime.now().isoformat(),
            1  # مفعلة افتراضياً
        ))
        
        conn.commit()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"Error adding session to DB: {e}")
        return False

def get_all_sessions() -> List[Dict]:
    """الحصول على جميع الجلسات"""
    from database import get_connection
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT id, session_string, phone_number, username, 
                   user_id, first_name, display_name, 
                   added_date, last_used, is_active
            FROM sessions
            ORDER BY id DESC
        ''')
        
        rows = cur.fetchall()
        conn.close()
        
        sessions = []
        for row in rows:
            sessions.append({
                'id': row[0],
                'session_string': row[1],
                'phone_number': row[2] or 'غير معروف',
                'username': row[3] or 'غير معروف',
                'user_id': row[4],
                'first_name': row[5] or '',
                'display_name': row[6] or f"جلسة {row[0]}",
                'added_date': row[7],
                'last_used': row[8] or 'لم يستخدم',
                'is_active': bool(row[9])
            })
        
        return sessions
        
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        return []

def delete_session(session_id: int) -> bool:
    """حذف جلسة"""
    from database import get_connection
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
        
        conn.commit()
        conn.close()
        
        return cur.rowcount > 0
        
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        return False

def export_sessions_to_file() -> Optional[str]:
    """
    تصدير جميع الجلسات إلى ملف
    
    Returns:
        str: مسار الملف أو None
    """
    import os
    from config import SESSIONS_DIR
    
    try:
        sessions = get_all_sessions()
        
        if not sessions:
            return None
        
        # إعداد البيانات للتخزين
        export_data = []
        for session in sessions:
            # إخفاء بعض المعلومات الحساسة
            safe_session = {
                'id': session['id'],
                'phone_number': session['phone_number'],
                'username': session['username'],
                'user_id': session['user_id'],
                'display_name': session['display_name'],
                'added_date': session['added_date'],
                'is_active': session['is_active']
            }
            export_data.append(safe_session)
        
        # حفظ في ملف
        filename = f"sessions_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(SESSIONS_DIR, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        return filepath
        
    except Exception as e:
        logger.error(f"Error exporting sessions: {e}")
        return None

# إنشاء كائن مدير الجلسات
session_manager = SessionManager()
