import asyncio
import logging
import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from telethon import TelegramClient
from telethon.errors import (
    AuthKeyError, SessionPasswordNeededError,
    PhoneCodeInvalidError, FloodWaitError,
    ApiIdInvalidError, AccessTokenExpiredError,
    AccessTokenInvalidError
)
from telethon.sessions import StringSession

from config import (
    API_ID, API_HASH, SESSIONS_DIR,
    AUTO_VALIDATE_SESSIONS, VALIDATE_SESSIONS_ON_ADD,
    MAX_CONNECTION_RETRIES, RETRY_DELAY,
    SESSION_EXPIRY_DAYS, ALLOW_DUPLICATE_SESSIONS
)
from database import (
    get_db_connection, get_sessions, update_session_status,
    update_session_usage, delete_session
)

# ======================
# Logging
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Session Management
# ======================

def get_session_filepath(session_id: int) -> str:
    """الحصول على مسار ملف الجلسة"""
    return os.path.join(SESSIONS_DIR, f"session_{session_id}.session")

def save_session_to_file(session_string: str, session_id: int) -> bool:
    """حفظ الجلسة إلى ملف"""
    try:
        filepath = get_session_filepath(session_id)
        
        # استخدام StringSession لحفظ الجلسة
        session = StringSession(session_string)
        
        # حفظ الجلسة
        session.save(filepath)
        
        logger.info(f"Session saved to file: {filepath}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving session to file: {e}")
        return False

def load_session_from_file(session_id: int) -> Optional[str]:
    """تحميل الجلسة من ملف"""
    try:
        filepath = get_session_filepath(session_id)
        
        if not os.path.exists(filepath):
            logger.warning(f"Session file not found: {filepath}")
            return None
        
        # تحميل الجلسة من الملف
        with open(filepath, 'r') as f:
            session_string = f.read().strip()
        
        return session_string
        
    except Exception as e:
        logger.error(f"Error loading session from file: {e}")
        return None

def delete_session_file(session_id: int) -> bool:
    """حذف ملف الجلسة"""
    try:
        filepath = get_session_filepath(session_id)
        
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Deleted session file: {filepath}")
            return True
        else:
            logger.warning(f"Session file not found: {filepath}")
            return False
            
    except Exception as e:
        logger.error(f"Error deleting session file: {e}")
        return False

# ======================
# Session Validation
# ======================

async def validate_session(session_string: str) -> Tuple[bool, Dict]:
    """
    التحقق من صحة جلسة تيليجرام
    Returns: (is_valid, account_info)
    """
    client = None
    account_info = {
        'user_id': 0,
        'phone': '',
        'username': '',
        'first_name': '',
        'last_name': '',
        'is_bot': False,
        'is_premium': False,
        'is_active': False
    }
    
    try:
        # إنشاء العميل باستخدام الجلسة
        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH,
            device_model="Link Collector",
            system_version="4.16.30-vxCUSTOM",
            app_version="4.16.30",
            lang_code="ar",
            system_lang_code="ar"
        )
        
        # الاتصال
        await client.connect()
        
        # التحقق من صحة الجلسة
        is_authorized = await client.is_user_authorized()
        
        if not is_authorized:
            logger.warning("Session is not authorized")
            return False, account_info
        
        # الحصول على معلومات الحساب
        me = await client.get_me()
        
        if me:
            account_info.update({
                'user_id': me.id,
                'phone': me.phone or '',
                'username': me.username or '',
                'first_name': me.first_name or '',
                'last_name': me.last_name or '',
                'is_bot': me.bot,
                'is_premium': getattr(me, 'premium', False),
                'is_active': True
            })
            
            logger.info(f"Session validated for user: @{account_info['username']} ({account_info['phone']})")
            return True, account_info
        else:
            logger.warning("Could not get user information")
            return False, account_info
        
    except AuthKeyError:
        logger.error("Session auth key error")
        return False, account_info
    
    except SessionPasswordNeededError:
        logger.error("Session needs password (2FA enabled)")
        return False, account_info
    
    except ApiIdInvalidError:
        logger.error("Invalid API ID/API Hash")
        return False, account_info
    
    except FloodWaitError as e:
        logger.error(f"Flood wait: {e.seconds} seconds")
        return False, account_info
    
    except Exception as e:
        logger.error(f"Error validating session: {e}")
        return False, account_info
    
    finally:
        if client:
            await client.disconnect()

async def validate_session_by_id(session_id: int) -> Tuple[bool, Dict]:
    """التحقق من صحة جلسة بواسطة ID"""
    try:
        # تحميل الجلسة من قاعدة البيانات
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT session_string FROM sessions WHERE id = ?",
            (session_id,)
        )
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            logger.error(f"Session ID {session_id} not found")
            return False, {}
        
        session_string = result['session_string']
        return await validate_session(session_string)
        
    except Exception as e:
        logger.error(f"Error validating session by ID {session_id}: {e}")
        return False, {}

async def validate_all_sessions() -> Dict:
    """التحقق من صحة جميع الجلسات"""
    sessions = get_sessions()
    results = {
        'total': len(sessions),
        'valid': 0,
        'invalid': 0,
        'active': 0,
        'inactive': 0,
        'details': []
    }
    
    for session in sessions:
        session_id = session.get('id')
        display_name = session.get('display_name', f"Session_{session_id}")
        is_active = session.get('is_active', False)
        
        logger.info(f"Validating session: {display_name}")
        
        is_valid, account_info = await validate_session_by_id(session_id)
        
        if is_valid:
            results['valid'] += 1
            
            # تحديث حالة الجلسة إذا لزم الأمر
            if not is_active:
                update_session_status(session_id, True)
                results['details'].append({
                    'session_id': session_id,
                    'display_name': display_name,
                    'status': 'reactivated',
                    'account_info': account_info
                })
            else:
                results['details'].append({
                    'session_id': session_id,
                    'display_name': display_name,
                    'status': 'valid',
                    'account_info': account_info
                })
        else:
            results['invalid'] += 1
            
            # تحديث حالة الجلسة إذا لزم الأمر
            if is_active:
                update_session_status(session_id, False)
                results['details'].append({
                    'session_id': session_id,
                    'display_name': display_name,
                    'status': 'deactivated',
                    'account_info': account_info
                })
            else:
                results['details'].append({
                    'session_id': session_id,
                    'display_name': display_name,
                    'status': 'invalid',
                    'account_info': account_info
                })
        
        # التحقق من حالة الجلسة
        if is_active:
            results['active'] += 1
        else:
            results['inactive'] += 1
        
        # تأخير بين التحقق من الجلسات
        await asyncio.sleep(1)
    
    return results

# ======================
# Session Testing
# ======================

async def test_session_connection(session_string: str) -> Dict:
    """اختبار اتصال الجلسة"""
    results = {
        'connection': False,
        'authorization': False,
        'account_info': {},
        'errors': [],
        'ping_time': 0
    }
    
    client = None
    start_time = datetime.now()
    
    try:
        # إنشاء العميل
        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH
        )
        
        # اختبار الاتصال
        await client.connect()
        results['connection'] = True
        
        # اختبار التخويل
        results['authorization'] = await client.is_user_authorized()
        
        if results['authorization']:
            # الحصول على معلومات الحساب
            me = await client.get_me()
            if me:
                results['account_info'] = {
                    'user_id': me.id,
                    'phone': me.phone or '',
                    'username': me.username or '',
                    'first_name': me.first_name or '',
                    'last_name': me.last_name or '',
                    'is_bot': me.bot,
                    'is_premium': getattr(me, 'premium', False)
                }
        
        # حساب وقت الاستجابة
        end_time = datetime.now()
        results['ping_time'] = (end_time - start_time).total_seconds()
        
        logger.info(f"Session test successful (ping: {results['ping_time']:.2f}s)")
        
    except AuthKeyError as e:
        results['errors'].append(f"Auth key error: {e}")
        logger.error(f"Session auth key error: {e}")
    
    except SessionPasswordNeededError as e:
        results['errors'].append("2FA password needed")
        logger.error("Session needs 2FA password")
    
    except ApiIdInvalidError as e:
        results['errors'].append("Invalid API ID/API Hash")
        logger.error("Invalid API credentials")
    
    except FloodWaitError as e:
        results['errors'].append(f"Flood wait: {e.seconds}s")
        logger.error(f"Flood wait error: {e}")
    
    except Exception as e:
        results['errors'].append(str(e))
        logger.error(f"Session test error: {e}")
    
    finally:
        if client:
            await client.disconnect()
    
    return results

async def test_all_sessions() -> Dict:
    """اختبار جميع الجلسات"""
    sessions = get_sessions()
    results = {
        'total': len(sessions),
        'passed': 0,
        'failed': 0,
        'active': 0,
        'inactive': 0,
        'average_ping': 0,
        'details': []
    }
    
    total_ping = 0
    ping_count = 0
    
    for session in sessions:
        session_id = session.get('id')
        display_name = session.get('display_name', f"Session_{session_id}")
        is_active = session.get('is_active', False)
        
        logger.info(f"Testing session: {display_name}")
        
        session_string = session.get('session_string', '')
        test_result = await test_session_connection(session_string)
        
        detail = {
            'session_id': session_id,
            'display_name': display_name,
            'is_active_db': is_active,
            'connection': test_result['connection'],
            'authorization': test_result['authorization'],
            'ping_time': test_result['ping_time'],
            'errors': test_result['errors']
        }
        
        if test_result['connection'] and test_result['authorization']:
            results['passed'] += 1
            detail['status'] = 'passed'
            
            # تحديث وقت الاستخدام
            update_session_usage(session_id)
            
            # تحديث حالة الجلسة إذا كانت معطلة
            if not is_active:
                update_session_status(session_id, True)
                detail['status'] = 'reactivated'
        else:
            results['failed'] += 1
            detail['status'] = 'failed'
            
            # تحديث حالة الجلسة إذا كانت مفعلة
            if is_active:
                update_session_status(session_id, False)
                detail['status'] = 'deactivated'
        
        # تحديث إحصائيات ping
        if test_result['ping_time'] > 0:
            total_ping += test_result['ping_time']
            ping_count += 1
        
        # تحديث حالة الجلسة
        if is_active:
            results['active'] += 1
        else:
            results['inactive'] += 1
        
        results['details'].append(detail)
        
        # تأخير بين الاختبارات
        await asyncio.sleep(0.5)
    
    # حساب متوسط ping
    if ping_count > 0:
        results['average_ping'] = total_ping / ping_count
    
    logger.info(f"Session tests completed: {results['passed']}/{results['total']} passed")
    return results

# ======================
# Session Maintenance
# ======================

def check_session_expiry() -> Dict:
    """التحقق من انتهاء صلاحية الجلسات"""
    results = {
        'total': 0,
        'expired': 0,
        'expiring_soon': 0,
        'valid': 0,
        'expired_sessions': []
    }
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if SESSION_EXPIRY_DAYS > 0:
            # الحصول على الجلسات المنتهية الصلاحية
            expiry_date = (datetime.now() - timedelta(days=SESSION_EXPIRY_DAYS)).strftime('%Y-%m-%d')
            
            cursor.execute('''
                SELECT id, display_name, added_date, last_used 
                FROM sessions 
                WHERE is_active = 1
            ''')
            
            sessions = cursor.fetchall()
            results['total'] = len(sessions)
            
            for session in sessions:
                session_id = session['id']
                display_name = session['display_name']
                added_date = session['added_date']
                last_used = session['last_used']
                
                # استخدام آخر تاريخ استخدام أو تاريخ الإضافة
                check_date = last_used or added_date
                
                if check_date:
                    try:
                        check_datetime = datetime.strptime(check_date, '%Y-%m-%d %H:%M:%S')
                        
                        # التحقق من انتهاء الصلاحية
                        if check_datetime < datetime.now() - timedelta(days=SESSION_EXPIRY_DAYS):
                            results['expired'] += 1
                            results['expired_sessions'].append({
                                'session_id': session_id,
                                'display_name': display_name,
                                'last_used': last_used,
                                'added_date': added_date
                            })
                            
                            # تعطيل الجلسة المنتهية
                            update_session_status(session_id, False)
                            logger.info(f"Session {display_name} expired and deactivated")
                        
                        # التحقق من الجلسات التي تنتهي قريباً (أقل من 3 أيام)
                        elif check_datetime < datetime.now() - timedelta(days=SESSION_EXPIRY_DAYS - 3):
                            results['expiring_soon'] += 1
                        
                        else:
                            results['valid'] += 1
                    
                    except ValueError:
                        # إذا كان هناك خطأ في تحويل التاريخ، تجاهل
                        continue
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error checking session expiry: {e}")
    
    return results

def cleanup_invalid_sessions() -> Dict:
    """تنظيف الجلسات غير الصالحة"""
    results = {
        'total': 0,
        'cleaned': 0,
        'kept': 0,
        'cleaned_sessions': []
    }
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # الحصول على جميع الجلسات
        cursor.execute('SELECT id, display_name, is_active FROM sessions')
        sessions = cursor.fetchall()
        results['total'] = len(sessions)
        
        for session in sessions:
            session_id = session['id']
            display_name = session['display_name']
            is_active = session['is_active']
            
            # حذف الجلسات المعطلة لأكثر من 30 يوم
            if not is_active:
                cursor.execute('''
                    SELECT last_used FROM sessions 
                    WHERE id = ? 
                ''', (session_id,))
                
                last_used_result = cursor.fetchone()
                
                if last_used_result and last_used_result['last_used']:
                    try:
                        last_used = datetime.strptime(last_used_result['last_used'], '%Y-%m-%d %H:%M:%S')
                        
                        # إذا مر أكثر من 30 يوم على تعطيل الجلسة، احذفها
                        if last_used < datetime.now() - timedelta(days=30):
                            # حذف الجلسة
                            delete_session(session_id)
                            
                            # حذف ملف الجلسة
                            delete_session_file(session_id)
                            
                            results['cleaned'] += 1
                            results['cleaned_sessions'].append({
                                'session_id': session_id,
                                'display_name': display_name,
                                'reason': 'inactive_for_30_days'
                            })
                            
                            logger.info(f"Cleaned inactive session: {display_name}")
                            continue
                    
                    except ValueError:
                        pass
            
            results['kept'] += 1
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error cleaning invalid sessions: {e}")
    
    return results

async def auto_validate_sessions():
    """التحقق التلقائي من صحة الجلسات"""
    if not AUTO_VALIDATE_SESSIONS:
        return
    
    logger.info("Starting automatic session validation...")
    
    try:
        # التحقق من جميع الجلسات
        validation_results = await validate_all_sessions()
        
        # التحقق من انتهاء الصلاحية
        expiry_results = check_session_expiry()
        
        # تنظيف الجلسات غير الصالحة
        cleanup_results = cleanup_invalid_sessions()
        
        # تسجيل النتائج
        logger.info(f"Auto-validation results:")
        logger.info(f"  • Sessions validated: {validation_results['valid']}/{validation_results['total']}")
        logger.info(f"  • Expired sessions: {expiry_results['expired']}")
        logger.info(f"  • Expiring soon: {expiry_results['expiring_soon']}")
        logger.info(f"  • Sessions cleaned: {cleanup_results['cleaned']}")
        
        return {
            'validation': validation_results,
            'expiry': expiry_results,
            'cleanup': cleanup_results
        }
        
    except Exception as e:
        logger.error(f"Error in auto-validation: {e}")
        return None

# ======================
# Session Operations
# ======================

def create_new_session(phone_number: str) -> Optional[Dict]:
    """إنشاء جلسة جديدة (للإضافة يدوياً)"""
    # هذه الدالة للاستخدام المستقبلي
    # يمكن استخدامها لإنشاء جلسات جديدة عبر API
    return None

async def rotate_sessions() -> Dict:
    """تدوير الجلسات (تفعيل/تعطيل بالتناوب)"""
    sessions = get_sessions()
    results = {
        'total': len(sessions),
        'activated': 0,
        'deactivated': 0,
        'unchanged': 0,
        'details': []
    }
    
    try:
        # الحصول على الجلسات النشطة
        active_sessions = [s for s in sessions if s.get('is_active')]
        inactive_sessions = [s for s in sessions if not s.get('is_active')]
        
        # إذا كان هناك أكثر من 5 جلسات نشطة، عطل بعضها
        if len(active_sessions) > 5:
            to_deactivate = active_sessions[5:]  # ابقي على 5 جلسات فقط
            
            for session in to_deactivate:
                session_id = session.get('id')
                display_name = session.get('display_name')
                
                update_session_status(session_id, False)
                results['deactivated'] += 1
                results['details'].append({
                    'session_id': session_id,
                    'display_name': display_name,
                    'action': 'deactivated'
                })
        
        # تفعيل الجلسات المعطلة إذا كان هناك أقل من 3 جلسات نشطة
        if len(active_sessions) < 3 and inactive_sessions:
            needed = 3 - len(active_sessions)
            to_activate = inactive_sessions[:needed]
            
            for session in to_activate:
                session_id = session.get('id')
                display_name = session.get('display_name')
                
                # التحقق من صحة الجلسة قبل التفعيل
                is_valid, _ = await validate_session_by_id(session_id)
                
                if is_valid:
                    update_session_status(session_id, True)
                    results['activated'] += 1
                    results['details'].append({
                        'session_id': session_id,
                        'display_name': display_name,
                        'action': 'activated'
                    })
        
        results['unchanged'] = results['total'] - results['activated'] - results['deactivated']
        
        logger.info(f"Session rotation: {results['activated']} activated, {results['deactivated']} deactivated")
        
    except Exception as e:
        logger.error(f"Error rotating sessions: {e}")
    
    return results

# ======================
# Session Export/Import
# ======================

def export_sessions_to_file(filepath: str = None) -> Optional[str]:
    """تصدير الجلسات إلى ملف"""
    try:
        sessions = get_sessions()
        
        if not sessions:
            logger.warning("No sessions to export")
            return None
        
        # إنشاء اسم الملف
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(SESSIONS_DIR, f"sessions_backup_{timestamp}.json")
        
        # تحضير البيانات للتصدير
        export_data = {
            'export_date': datetime.now().isoformat(),
            'total_sessions': len(sessions),
            'sessions': []
        }
        
        for session in sessions:
            session_data = {
                'id': session.get('id'),
                'session_string': session.get('session_string'),
                'phone_number': session.get('phone_number'),
                'user_id': session.get('user_id'),
                'username': session.get('username'),
                'display_name': session.get('display_name'),
                'is_active': bool(session.get('is_active')),
                'added_date': session.get('added_date'),
                'last_used': session.get('last_used')
            }
            export_data['sessions'].append(session_data)
        
        # كتابة الملف
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Exported {len(sessions)} sessions to {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Error exporting sessions: {e}")
        return None

def import_sessions_from_file(filepath: str) -> Dict:
    """استيراد الجلسات من ملف"""
    results = {
        'total': 0,
        'imported': 0,
        'skipped': 0,
        'failed': 0,
        'details': []
    }
    
    try:
        if not os.path.exists(filepath):
            logger.error(f"Import file not found: {filepath}")
            return results
        
        # قراءة الملف
        with open(filepath, 'r', encoding='utf-8') as f:
            import_data = json.load(f)
        
        if 'sessions' not in import_data:
            logger.error("Invalid import file format")
            return results
        
        sessions_to_import = import_data['sessions']
        results['total'] = len(sessions_to_import)
        
        for session_data in sessions_to_import:
            try:
                session_string = session_data.get('session_string')
                phone = session_data.get('phone_number', '')
                user_id = session_data.get('user_id', 0)
                username = session_data.get('username', '')
                display_name = session_data.get('display_name', '')
                
                if not session_string:
                    results['skipped'] += 1
                    results['details'].append({
                        'display_name': display_name,
                        'status': 'skipped',
                        'reason': 'No session string'
                    })
                    continue
                
                # التحقق من التكرار إذا كان غير مسموح
                if not ALLOW_DUPLICATE_SESSIONS:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    cursor.execute(
                        "SELECT id FROM sessions WHERE session_string = ?",
                        (session_string,)
                    )
                    
                    if cursor.fetchone():
                        results['skipped'] += 1
                        results['details'].append({
                            'display_name': display_name,
                            'status': 'skipped',
                            'reason': 'Duplicate session'
                        })
                        conn.close()
                        continue
                    
                    conn.close()
                
                # التحقق من صحة الجلسة إذا كان مطلوباً
                if VALIDATE_SESSIONS_ON_ADD:
                    is_valid, account_info = await validate_session(session_string)
                    
                    if not is_valid:
                        results['failed'] += 1
                        results['details'].append({
                            'display_name': display_name,
                            'status': 'failed',
                            'reason': 'Invalid session'
                        })
                        continue
                
                # إضافة الجلسة إلى قاعدة البيانات
                from database import add_session
                success = add_session(session_string, phone, user_id, username, display_name)
                
                if success:
                    results['imported'] += 1
                    results['details'].append({
                        'display_name': display_name,
                        'status': 'imported'
                    })
                else:
                    results['skipped'] += 1
                    results['details'].append({
                        'display_name': display_name,
                        'status': 'skipped',
                        'reason': 'Database error'
                    })
                
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'display_name': session_data.get('display_name', 'Unknown'),
                    'status': 'failed',
                    'reason': str(e)[:100]
                })
                logger.error(f"Error importing session: {e}")
        
        logger.info(f"Import completed: {results['imported']}/{results['total']} imported")
        
    except Exception as e:
        logger.error(f"Error importing sessions: {e}")
    
    return results

# ======================
# Session Statistics
# ======================

def get_session_statistics() -> Dict:
    """الحصول على إحصائيات الجلسات"""
    stats = {
        'total': 0,
        'active': 0,
        'inactive': 0,
        'by_status': {},
        'recently_used': 0,
        'never_used': 0,
        'average_age_days': 0
    }
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # إحصائيات أساسية
        cursor.execute('SELECT COUNT(*) as total FROM sessions')
        stats['total'] = cursor.fetchone()['total']
        
        cursor.execute('SELECT COUNT(*) as active FROM sessions WHERE is_active = 1')
        stats['active'] = cursor.fetchone()['active']
        
        stats['inactive'] = stats['total'] - stats['active']
        
        # الجلسات المستخدمة مؤخراً (آخر 7 أيام)
        cursor.execute('''
            SELECT COUNT(*) as recent 
            FROM sessions 
            WHERE last_used >= DATE('now', '-7 days')
        ''')
        stats['recently_used'] = cursor.fetchone()['recent']
        
        # الجلسات التي لم تستخدم أبداً
        cursor.execute('''
            SELECT COUNT(*) as never_used 
            FROM sessions 
            WHERE last_used IS NULL
        ''')
        stats['never_used'] = cursor.fetchone()['never_used']
        
        # متوسط عمر الجلسات (بالأيام)
        cursor.execute('''
            SELECT 
                AVG(julianday('now') - julianday(added_date)) as avg_age
            FROM sessions
        ''')
        avg_age = cursor.fetchone()['avg_age']
        stats['average_age_days'] = round(avg_age or 0, 1)
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error getting session statistics: {e}")
    
    return stats

def get_session_health_report() -> Dict:
    """تقرير صحة الجلسات"""
    report = {
        'timestamp': datetime.now().isoformat(),
        'summary': {},
        'issues': [],
        'recommendations': []
    }
    
    try:
        # إحصائيات الجلسات
        stats = get_session_statistics()
        report['summary'] = stats
        
        # التحقق من المشاكل
        if stats['active'] == 0:
            report['issues'].append({
                'type': 'critical',
                'message': 'لا توجد جلسات نشطة',
                'suggestion': 'أضف جلسة واحدة على الأقل وقم بتفعيلها'
            })
        
        if stats['inactive'] > stats['active'] * 2:
            report['issues'].append({
                'type': 'warning',
                'message': 'معظم الجلسات معطلة',
                'suggestion': 'تحقق من صحة الجلسات المعطلة أو احذفها'
            })
        
        if stats['never_used'] > stats['total'] * 0.5:
            report['issues'].append({
                'type': 'warning',
                'message': 'أكثر من نصف الجلسات لم تستخدم أبداً',
                'suggestion': 'فكر في حذف الجلسات القديمة غير المستخدمة'
            })
        
        if stats['average_age_days'] > 60:
            report['issues'].append({
                'type': 'info',
                'message': 'الجلسات قديمة جداً',
                'suggestion': 'فكر في تجديد الجلسات القديمة'
            })
        
        # توصيات
        if stats['active'] < 3:
            report['recommendations'].append('أضف المزيد من الجلسات النشطة لتحسين الأداء')
        
        if stats['inactive'] > 5:
            report['recommendations'].append('نظف الجلسات المعطلة لتحسين الأداء')
        
        if stats['recently_used'] == 0:
            report['recommendations'].append('ابدأ عملية جمع لاختبار الجلسات')
        
    except Exception as e:
        logger.error(f"Error generating session health report: {e}")
        report['error'] = str(e)
    
    return report

# ======================
# Test Functions
# ======================

async def test_session_manager():
    """اختبار مدير الجلسات"""
    print("🔧 اختبار مدير الجلسات...")
    print("=" * 60)
    
    # اختبار إحصائيات الجلسات
    print("\n📊 إحصائيات الجلسات:")
    stats = get_session_statistics()
    
    for key, value in stats.items():
        if isinstance(value, dict):
            print(f"  📈 {key}:")
            for k, v in value.items():
                print(f"     • {k}: {v}")
        else:
            print(f"  📈 {key}: {value}")
    
    # اختبار تقرير الصحة
    print("\n🏥 تقرير صحة الجلسات:")
    health_report = get_session_health_report()
    
    print(f"  ⏰ الوقت: {health_report['timestamp']}")
    
    if health_report.get('issues'):
        print(f"  ⚠️  المشاكل:")
        for issue in health_report['issues']:
            print(f"     • [{issue['type']}] {issue['message']}")
            print(f"       💡 {issue['suggestion']}")
    
    if health_report.get('recommendations'):
        print(f"  💡 التوصيات:")
        for rec in health_report['recommendations']:
            print(f"     • {rec}")
    
    # اختبار التحقق من الصلاحية
    print("\n🔍 التحقق من صلاحية الجلسات...")
    
    # الحصول على جلسة للاختبار
    sessions = get_sessions()
    if sessions:
        session = sessions[0]
        session_id = session.get('id')
        display_name = session.get('display_name')
        
        print(f"  اختبار الجلسة: {display_name}")
        
        is_valid, account_info = await validate_session_by_id(session_id)
        
        print(f"  ✅ صالحة: {is_valid}")
        if is_valid:
            print(f"  👤 الحساب: @{account_info.get('username')}")
            print(f"  📞 الهاتف: {account_info.get('phone')}")
    
    print("\n" + "=" * 60)
    print("✅ اختبار مدير الجلسات اكتمل بنجاح!")

# ======================
# Main Entry Point
# ======================

if __name__ == "__main__":
    import sys
    
    async def main():
        """الدالة الرئيسية للاختبار"""
        print("🚀 تشغيل مدير الجلسات...")
        
        # التحقق من وجود مجلد الجلسات
        if not os.path.exists(SESSIONS_DIR):
            os.makedirs(SESSIONS_DIR, exist_ok=True)
            print(f"📁 تم إنشاء مجلد الجلسات: {SESSIONS_DIR}")
        
        # اختبار الدوال الأساسية
        print("\n🔧 اختبار الدوال الأساسية...")
        
        # اختبار إحصائيات
        stats = get_session_statistics()
        print(f"📊 عدد الجلسات: {stats['total']}")
        print(f"   • النشطة: {stats['active']}")
        print(f"   • المعطلة: {stats['inactive']}")
        
        # اختبار التحقق من الصلاحية
        print("\n🔍 اختبار التحقق من الصلاحية...")
        
        if stats['total'] > 0:
            # اختبار جلسة واحدة
            sessions = get_sessions()
            if sessions:
                session = sessions[0]
                session_id = session['id']
                
                is_valid, account_info = await validate_session_by_id(session_id)
                print(f"   • الجلسة {session_id}: {'✅ صالحة' if is_valid else '❌ غير صالحة'}")
                
                if is_valid:
                    print(f"     👤 الحساب: @{account_info.get('username', 'N/A')}")
        
        # اختبار التنظيف
        print("\n🧹 اختبار تنظيف الجلسات...")
        cleanup_results = cleanup_invalid_sessions()
        print(f"   • تم تنظيف: {cleanup_results['cleaned']} جلسة")
        
        # اختبار كامل
        print("\n" + "=" * 60)
        await test_session_manager()
        
        print("\n✅ مدير الجلسات جاهز للعمل!")
    
    # تشغيل الاختبار
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ تم إيقاف الاختبار")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ خطأ في الاختبار: {e}")
        sys.exit(1)
