import asyncio
import logging
import re
import random
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Set
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError, ChatAdminRequiredError, ChannelPrivateError,
    UsernameNotOccupiedError, UsernameInvalidError, ChatWriteForbiddenError,
    UserNotParticipantError, InviteHashInvalidError, InviteHashExpiredError
)

from config import (
    API_ID, API_HASH, SESSIONS_DIR, VERIFY_LINKS,
    VERIFY_TIMEOUT, MAX_CONCURRENT_VERIFICATIONS,
    MIN_MEMBERS_FOR_PUBLIC_GROUP, MIN_MEMBERS_FOR_PRIVATE_GROUP,
    COLLECTION_DELAY, IGNORED_PATTERNS, BLACKLISTED_DOMAINS,
    TELEGRAM_PUBLIC_GROUP_PATTERNS, TELEGRAM_PRIVATE_GROUP_PATTERNS,
    WHATSAPP_LINK_PATTERNS, FILTER_CHANNELS, FILTER_EMPTY_GROUPS,
    FILTER_BANNED_GROUPS, FILTER_DEAD_LINKS, MIN_GROUP_SIZE
)
from database import (
    get_sessions, add_link, add_links_batch, update_session_usage,
    start_collection_session, update_collection_stats, end_collection_session,
    get_active_collection_session, get_link_stats, update_daily_stats
)
from session_manager import validate_session

# ======================
# Logging
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Global Variables
# ======================

# حالة الجمع
_collection_active = False
_collection_paused = False
_collection_session_id = None
_collection_stats = {
    'total_collected': 0,
    'telegram_collected': 0,
    'whatsapp_collected': 0,
    'public_groups': 0,
    'private_groups': 0,
    'whatsapp_groups': 0,
    'duplicate_links': 0,
    'inactive_links': 0,
    'channels_skipped': 0,
    'banned_skipped': 0,
    'empty_skipped': 0,
    'start_time': None,
    'end_time': None,
    'duration': 0
}

# مجموعة للتحقق من التكرار أثناء الجلسة الواحدة
_collected_urls = set()

# ======================
# Helper Functions
# ======================

def is_collecting() -> bool:
    """التحقق مما إذا كان الجمع نشطاً"""
    return _collection_active

def is_paused() -> bool:
    """التحقق مما إذا كان الجمع موقفاً مؤقتاً"""
    return _collection_paused

def get_collection_status() -> Dict:
    """الحصول على حالة الجمع الحالية"""
    return {
        'active': _collection_active,
        'paused': _collection_paused,
        'session_id': _collection_session_id,
        'stats': _collection_stats.copy(),
        'collected_urls_count': len(_collected_urls)
    }

def reset_collection_state():
    """إعادة تعيين حالة الجمع"""
    global _collection_active, _collection_paused, _collection_session_id
    global _collection_stats, _collected_urls
    
    _collection_active = False
    _collection_paused = False
    _collection_session_id = None
    _collection_stats = {
        'total_collected': 0,
        'telegram_collected': 0,
        'whatsapp_collected': 0,
        'public_groups': 0,
        'private_groups': 0,
        'whatsapp_groups': 0,
        'duplicate_links': 0,
        'inactive_links': 0,
        'channels_skipped': 0,
        'banned_skipped': 0,
        'empty_skipped': 0,
        'start_time': None,
        'end_time': None,
        'duration': 0
    }
    _collected_urls.clear()

def normalize_url(url: str) -> str:
    """تطبيع الرابط (إزالة الـ query parameters غير الضرورية)"""
    # إزالة المسافات
    url = url.strip()
    
    # إزالة الـ tracking parameters الشائعة
    tracking_params = ['utm_', 'si=', 'ref=', 'share=', 'fbclid=', 'igshid=']
    for param in tracking_params:
        if '?' in url and param in url:
            # إزالة كل شيء بعد علامة الاستفهام
            url = url.split('?')[0]
            break
    
    # إزالة الـ trailing slash
    if url.endswith('/'):
        url = url[:-1]
    
    return url

def is_url_ignored(url: str) -> bool:
    """التحقق مما إذا كان الرابط يجب تجاهله"""
    # التحقق من الأنماط الممنوعة
    for pattern in IGNORED_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            logger.debug(f"Ignored (pattern): {url}")
            return True
    
    # التحقق من النطاقات الممنوعة
    for domain in BLACKLISTED_DOMAINS:
        if domain.lower() in url.lower():
            logger.debug(f"Ignored (domain): {url}")
            return True
    
    return False

def extract_telegram_username(url: str) -> Optional[str]:
    """استخراج اسم المستخدم من رابط تيليجرام"""
    patterns = [
        r't\.me/([A-Za-z0-9_]+)',
        r'telegram\.me/([A-Za-z0-9_]+)',
        r'tg://resolve\?domain=([A-Za-z0-9_]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            username = match.group(1)
            # إزالة أي query parameters
            if '?' in username:
                username = username.split('?')[0]
            return username.lower()
    
    return None

def extract_telegram_invite_hash(url: str) -> Optional[str]:
    """استخراج hash الدعوة من رابط تيليجرام الخاص"""
    patterns = [
        r't\.me/\+([A-Za-z0-9_-]+)',
        r'telegram\.me/\+([A-Za-z0-9_-]+)',
        r'tg://join\?invite=([A-Za-z0-9_-]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None

def is_telegram_channel_link(url: str) -> bool:
    """التحقق مما إذا كان الرابط قناة تيليجرام"""
    # الأنماط التي تشير إلى قنوات
    channel_patterns = [
        r't\.me/c/[0-9]+',
        r't\.me/s/[A-Za-z0-9_]+',
        r'telegram\.me/c/[0-9]+',
        r'tg://privatepost\?channel=[0-9]+'
    ]
    
    for pattern in channel_patterns:
        if re.match(pattern, url, re.IGNORECASE):
            return True
    
    # بعض الأسماء المعروفة للقنوات
    known_channel_keywords = ['channel', 'news', 'broadcast', 'announcement']
    username = extract_telegram_username(url)
    if username:
        for keyword in known_channel_keywords:
            if keyword in username.lower():
                return True
    
    return False

def is_telegram_group_link(url: str) -> bool:
    """التحقق مما إذا كان الرابط مجموعة تيليجرام"""
    # روابط المجموعات العامة
    for pattern in TELEGRAM_PUBLIC_GROUP_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return True
    
    # روابط المجموعات الخاصة
    for pattern in TELEGRAM_PRIVATE_GROUP_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return True
    
    return False

def is_whatsapp_group_link(url: str) -> bool:
    """التحقق مما إذا كان الرابط مجموعة واتساب"""
    for pattern in WHATSAPP_LINK_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            # تأكد أنه ليس رابط هاتف
            if 'wa.me/' in url and re.match(r'https?://wa\.me/[0-9]+', url):
                return False
            return True
    
    return False

def classify_telegram_link(url: str) -> str:
    """تصنيف رابط تيليجرام"""
    # التحقق مما إذا كان قناة
    if FILTER_CHANNELS and is_telegram_channel_link(url):
        return 'channel'
    
    # التحقق من المجموعات الخاصة
    if re.match(r'https?://t\.me/\+', url) or re.match(r'https?://telegram\.me/\+', url):
        return 'private_group'
    
    # المجموعات العامة
    if re.match(r'https?://t\.me/[A-Za-z0-9_]', url) or re.match(r'https?://telegram\.me/[A-Za-z0-9_]', url):
        return 'public_group'
    
    return 'unknown'

def classify_whatsapp_link(url: str) -> str:
    """تصنيف رابط واتساب"""
    if 'chat.whatsapp.com' in url:
        return 'group'
    elif 'wa.me/' in url:
        return 'phone'
    
    return 'unknown'

def is_valid_group_for_collection(platform: str, link_type: str) -> bool:
    """التحقق مما إذا كان نوع الرابط مطلوب جمعه"""
    from config import (
        COLLECT_TELEGRAM_PUBLIC_GROUPS,
        COLLECT_TELEGRAM_PRIVATE_GROUPS,
        COLLECT_WHATSAPP_GROUPS
    )
    
    if platform == 'telegram':
        if link_type == 'public_group':
            return COLLECT_TELEGRAM_PUBLIC_GROUPS
        elif link_type == 'private_group':
            return COLLECT_TELEGRAM_PRIVATE_GROUPS
    
    elif platform == 'whatsapp':
        if link_type == 'group':
            return COLLECT_WHATSAPP_GROUPS
    
    return False

# ======================
# Link Verification Functions
# ======================

async def verify_telegram_group(client: TelegramClient, url: str, link_type: str) -> Dict:
    """
    التحقق من مجموعة تيليجرام
    Returns: Dict with status and details
    """
    try:
        if link_type == 'public_group':
            username = extract_telegram_username(url)
            if not username:
                return {'status': 'invalid', 'reason': 'لا يمكن استخراج اسم المستخدم'}
            
            try:
                entity = await client.get_entity(username)
            except (UsernameNotOccupiedError, UsernameInvalidError):
                return {'status': 'invalid', 'reason': 'المستخدم غير موجود'}
            except ValueError:
                return {'status': 'invalid', 'reason': 'رابط غير صحيح'}
        
        elif link_type == 'private_group':
            invite_hash = extract_telegram_invite_hash(url)
            if not invite_hash:
                return {'status': 'invalid', 'reason': 'لا يمكن استخراج كود الدعوة'}
            
            try:
                entity = await client.get_entity(invite_hash)
            except (InviteHashInvalidError, InviteHashExpiredError):
                return {'status': 'invalid', 'reason': 'رابط الدعوة غير صالح أو منتهي'}
            except ValueError:
                return {'status': 'invalid', 'reason': 'رابط غير صحيح'}
        
        else:
            return {'status': 'invalid', 'reason': 'نوع رابط غير معروف'}
        
        # التحقق من نوع الكيان
        if hasattr(entity, 'broadcast') and entity.broadcast:
            return {'status': 'invalid', 'reason': 'هذه قناة وليست مجموعة'}
        
        if hasattr(entity, 'gigagroup') and entity.gigagroup:
            return {'status': 'valid', 'type': 'supergroup', 'title': entity.title, 'members': getattr(entity, 'participants_count', 0)}
        
        if hasattr(entity, 'megagroup') and entity.megagroup:
            return {'status': 'valid', 'type': 'megagroup', 'title': entity.title, 'members': getattr(entity, 'participants_count', 0)}
        
        # محاولة الحصول على عدد الأعضاء
        members_count = 0
        try:
            if hasattr(entity, 'participants_count'):
                members_count = entity.participants_count
            else:
                # محاولة الحصول على عدد الأعضاء
                participants = await client.get_participants(entity, limit=5)
                members_count = len([p for p in participants if not p.bot])
        except (ChatAdminRequiredError, ChannelPrivateError):
            # لا يمكن الوصول إلى قائمة الأعضاء
            pass
        
        return {
            'status': 'valid',
            'type': 'group',
            'title': getattr(entity, 'title', ''),
            'members': members_count
        }
        
    except FloodWaitError as e:
        logger.warning(f"Flood wait: {e.seconds} seconds")
        await asyncio.sleep(e.seconds + 5)
        return {'status': 'retry', 'reason': f'Flood wait: {e.seconds}s'}
    
    except ChatAdminRequiredError:
        return {'status': 'valid', 'type': 'group', 'title': 'مجموعة خاصة', 'members': 0}
    
    except ChannelPrivateError:
        return {'status': 'invalid', 'reason': 'المجموعة خاصة ولا يمكن الوصول إليها'}
    
    except ChatWriteForbiddenError:
        return {'status': 'valid', 'type': 'group', 'title': 'مجموعة مقروءة فقط', 'members': 0}
    
    except UserNotParticipantError:
        return {'status': 'valid', 'type': 'group', 'title': 'يجب الانضمام أولاً', 'members': 0}
    
    except Exception as e:
        logger.error(f"Error verifying telegram group {url}: {e}")
        return {'status': 'error', 'reason': str(e)}

async def verify_whatsapp_group(url: str) -> Dict:
    """
    التحقق من مجموعة واتساب
    Note: WhatsApp verification is limited due to API restrictions
    """
    try:
        # للواتساب، نقوم بتحليل بسيط للرابط
        if 'chat.whatsapp.com' not in url:
            return {'status': 'invalid', 'reason': 'ليس رابط مجموعة واتساب'}
        
        # يمكن إضافة تحقق أكثر تقدماً هنا
        # مثل استخدام Selenium أو طلبات HTTP
        
        return {'status': 'valid', 'type': 'whatsapp_group'}
        
    except Exception as e:
        logger.error(f"Error verifying whatsapp group {url}: {e}")
        return {'status': 'error', 'reason': str(e)}

async def verify_link(client: Optional[TelegramClient], url: str) -> Tuple[bool, str, Dict]:
    """
    التحقق من صحة الرابط ونشاطه
    Returns: (is_valid, link_type, details)
    """
    try:
        # تطبيع الرابط
        url = normalize_url(url)
        
        # التحقق من التكرار في الجلسة الحالية
        if url in _collected_urls:
            _collection_stats['duplicate_links'] += 1
            return False, 'duplicate', {}
        
        # التحقق مما إذا كان الرابط يجب تجاهله
        if is_url_ignored(url):
            return False, 'ignored', {}
        
        # تصنيف الرابط
        platform = None
        link_type = None
        
        if is_telegram_group_link(url):
            platform = 'telegram'
            link_type = classify_telegram_link(url)
            
            # تجاهل القنوات
            if link_type == 'channel':
                if FILTER_CHANNELS:
                    _collection_stats['channels_skipped'] += 1
                    return False, 'channel', {}
        
        elif is_whatsapp_group_link(url):
            platform = 'whatsapp'
            link_type = classify_whatsapp_link(url)
            
            # تجاهل روابط الهاتف
            if link_type == 'phone':
                return False, 'phone', {}
        
        else:
            return False, 'unknown_platform', {}
        
        # التحقق مما إذا كان هذا النوع مطلوب جمعه
        if not is_valid_group_for_collection(platform, link_type):
            return False, 'not_collected_type', {}
        
        # إذا كان الفحص معطلاً
        if not VERIFY_LINKS:
            return True, link_type, {'platform': platform}
        
        # التحقق من الروابط
        details = {}
        
        if platform == 'telegram' and client:
            verification = await verify_telegram_group(client, url, link_type)
            
            if verification['status'] == 'valid':
                details = verification
                
                # تطبيق قواعد الفلترة
                members = details.get('members', 0)
                
                if FILTER_EMPTY_GROUPS and members < MIN_GROUP_SIZE:
                    _collection_stats['empty_skipped'] += 1
                    return False, 'empty_group', details
                
                # التحقق من الحد الأدنى للأعضاء حسب نوع المجموعة
                if link_type == 'public_group' and members < MIN_MEMBERS_FOR_PUBLIC_GROUP:
                    _collection_stats['inactive_links'] += 1
                    return False, 'insufficient_members', details
                
                if link_type == 'private_group' and members < MIN_MEMBERS_FOR_PRIVATE_GROUP:
                    _collection_stats['inactive_links'] += 1
                    return False, 'insufficient_members', details
                
                return True, link_type, details
            
            elif verification['status'] == 'invalid':
                reason = verification.get('reason', '')
                if 'خاصة' in reason or 'مقفلة' in reason:
                    _collection_stats['banned_skipped'] += 1
                else:
                    _collection_stats['inactive_links'] += 1
                return False, verification['reason'], details
            
            else:
                return False, verification.get('reason', 'error'), details
        
        elif platform == 'whatsapp':
            verification = await verify_whatsapp_group(url)
            
            if verification['status'] == 'valid':
                return True, link_type, {'platform': platform}
            else:
                _collection_stats['inactive_links'] += 1
                return False, verification.get('reason', 'error'), {}
        
        return False, 'verification_failed', {}
        
    except Exception as e:
        logger.error(f"Error in verify_link for {url}: {e}")
        return False, f'error: {str(e)}', {}

# ======================
# Link Collection Functions
# ======================

async def collect_links_from_session(session_data: Dict, collection_queue: asyncio.Queue):
    """جمع الروابط من جلسة واحدة"""
    session_id = session_data.get('id')
    session_string = session_data.get('session_string')
    display_name = session_data.get('display_name', f"Session_{session_id}")
    
    logger.info(f"Starting collection from session: {display_name}")
    
    client = None
    try:
        # إنشاء العميل
        client = TelegramClient(
            session_string,
            API_ID,
            API_HASH,
            device_model="Link Collector Bot",
            system_version="4.16.30-vxCUSTOM",
            app_version="4.16.30",
            lang_code="ar",
            system_lang_code="ar"
        )
        
        # الاتصال
        await client.connect()
        
        # التحقق من الاتصال
        if not await client.is_user_authorized():
            logger.error(f"Session {display_name} not authorized")
            return
        
        # تحديث وقت الاستخدام
        update_session_usage(session_id)
        
        # جمع الروابط
        links_collected = 0
        max_links = 1000  # حد معقول لكل جلسة
        
        # مصادر لجمع الروابط
        sources = [
            collect_from_dialogs,
            collect_from_groups,
            collect_from_messages
        ]
        
        for source_func in sources:
            if not _collection_active or _collection_paused:
                break
            
            try:
                collected = await source_func(client, session_id, collection_queue, max_links - links_collected)
                links_collected += collected
                
                if links_collected >= max_links:
                    logger.info(f"Reached max links for session {display_name}")
                    break
                
                # تأخير بين المصادر
                await asyncio.sleep(COLLECTION_DELAY * 2)
                
            except Exception as e:
                logger.error(f"Error in {source_func.__name__} for session {display_name}: {e}")
                continue
        
        logger.info(f"Collected {links_collected} links from session {display_name}")
        
    except Exception as e:
        logger.error(f"Error collecting from session {display_name}: {e}")
    
    finally:
        if client:
            await client.disconnect()

async def collect_from_dialogs(client: TelegramClient, session_id: int, 
                               collection_queue: asyncio.Queue, limit: int = 200) -> int:
    """جمع الروابط من الدردشات"""
    collected = 0
    try:
        async for dialog in client.iter_dialogs(limit=100):
            if not _collection_active or _collection_paused:
                break
            
            try:
                if dialog.is_group or dialog.is_channel:
                    # الحصول على رابط المجموعة/القناة
                    entity = dialog.entity
                    
                    if hasattr(entity, 'username') and entity.username:
                        url = f"https://t.me/{entity.username}"
                        
                        # إضافة إلى قائمة المعالجة
                        await collection_queue.put({
                            'url': url,
                            'session_id': session_id,
                            'source': 'dialogs'
                        })
                        
                        collected += 1
                        
                        if collected >= limit:
                            break
                        
                        # تأخير صغير
                        await asyncio.sleep(COLLECTION_DELAY)
                    
            except Exception as e:
                logger.debug(f"Error processing dialog: {e}")
                continue
        
    except Exception as e:
        logger.error(f"Error collecting from dialogs: {e}")
    
    return collected

async def collect_from_groups(client: TelegramClient, session_id: int, 
                              collection_queue: asyncio.Queue, limit: int = 300) -> int:
    """جمع الروابط من المجموعات المنضمة"""
    collected = 0
    try:
        # الحصول على جميع الدردشات
        dialogs = await client.get_dialogs(limit=200)
        
        for dialog in dialogs:
            if not _collection_active or _collection_paused:
                break
            
            try:
                if dialog.is_group:
                    entity = dialog.entity
                    
                    # محاولة الحصول على رابط الدعوة
                    try:
                        if hasattr(entity, 'username') and entity.username:
                            url = f"https://t.me/{entity.username}"
                        else:
                            # محاولة إنشاء رابط دعوة
                            invite = await client(InviteToChannelRequest(
                                entity,
                                [await client.get_me()]
                            ))
                            if hasattr(invite, 'link'):
                                url = invite.link
                            else:
                                continue
                    except:
                        continue
                    
                    # إضافة إلى قائمة المعالجة
                    await collection_queue.put({
                        'url': url,
                        'session_id': session_id,
                        'source': 'groups'
                    })
                    
                    collected += 1
                    
                    if collected >= limit:
                        break
                    
                    # تأخير
                    await asyncio.sleep(COLLECTION_DELAY * 1.5)
                    
            except Exception as e:
                logger.debug(f"Error processing group: {e}")
                continue
    
    except Exception as e:
        logger.error(f"Error collecting from groups: {e}")
    
    return collected

async def collect_from_messages(client: TelegramClient, session_id: int, 
                                collection_queue: asyncio.Queue, limit: int = 500) -> int:
    """جمع الروابط من الرسائل"""
    collected = 0
    try:
        # البحث عن روابط في الرسائل الحديثة
        search_terms = [
            "t.me",
            "telegram.me",
            "chat.whatsapp.com",
            "انضمام",
            "مجموعة",
            "قناة",
            "رابط",
            "دعوة"
        ]
        
        for term in search_terms:
            if not _collection_active or _collection_paused:
                break
            
            try:
                async for message in client.iter_messages(None, search=term, limit=50):
                    if not _collection_active or _collection_paused:
                        break
                    
                    if message.text:
                        # استخراج الروابط من النص
                        urls = re.findall(
                            r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w .?=&%-]*',
                            message.text
                        )
                        
                        for url in urls:
                            if any(x in url for x in ['t.me', 'telegram.me', 'whatsapp.com']):
                                await collection_queue.put({
                                    'url': url,
                                    'session_id': session_id,
                                    'source': 'messages'
                                })
                                
                                collected += 1
                                
                                if collected >= limit:
                                    break
                        
                        if collected >= limit:
                            break
                    
                    # تأخير بين الرسائل
                    await asyncio.sleep(COLLECTION_DELAY * 0.5)
                
                if collected >= limit:
                    break
                
                # تأخير بين مصطلحات البحث
                await asyncio.sleep(COLLECTION_DELAY * 2)
                
            except Exception as e:
                logger.debug(f"Error searching for term '{term}': {e}")
                continue
    
    except Exception as e:
        logger.error(f"Error collecting from messages: {e}")
    
    return collected

async def process_collection_queue(collection_queue: asyncio.Queue):
    """معالجة قائمة انتظار الروابط المجمعة"""
    processed = 0
    
    while _collection_active:
        try:
            if _collection_paused:
                await asyncio.sleep(1)
                continue
            
            # محاولة الحصول على رابط من قائمة الانتظار
            try:
                item = await asyncio.wait_for(collection_queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                if collection_queue.empty():
                    # انتظار إذا كانت القائمة فارغة
                    await asyncio.sleep(3)
                continue
            
            url = item['url']
            session_id = item['session_id']
            
            # التحقق من الرابط
            is_valid, link_type, details = await verify_link(None, url)
            
            if is_valid:
                # إضافة الرابط إلى قاعدة البيانات
                platform = 'telegram' if 't.me' in url or 'telegram.me' in url else 'whatsapp'
                
                success, message = add_link(
                    url=url,
                    platform=platform,
                    link_type=link_type,
                    title=details.get('title', ''),
                    members_count=details.get('members', 0),
                    session_id=session_id
                )
                
                if success:
                    # تحديث الإحصائيات
                    _collection_stats['total_collected'] += 1
                    
                    if platform == 'telegram':
                        _collection_stats['telegram_collected'] += 1
                        if link_type == 'public_group':
                            _collection_stats['public_groups'] += 1
                        elif link_type == 'private_group':
                            _collection_stats['private_groups'] += 1
                    elif platform == 'whatsapp':
                        _collection_stats['whatsapp_collected'] += 1
                        _collection_stats['whatsapp_groups'] += 1
                    
                    # إضافة إلى مجموعة الروابط المجمعة
                    _collected_urls.add(url)
                    
                    processed += 1
                    
                    # تحديث الإحصائيات في قاعدة البيانات كل 10 روابط
                    if processed % 10 == 0:
                        update_collection_stats(_collection_session_id, _collection_stats)
                    
                    logger.debug(f"Collected: {url}")
                
                else:
                    if message == 'duplicate':
                        _collection_stats['duplicate_links'] += 1
                    logger.debug(f"Not collected ({message}): {url}")
            
            # إشعار بأن المعالجة اكتملت
            collection_queue.task_done()
            
            # تأخير بين المعالجات
            await asyncio.sleep(COLLECTION_DELAY)
            
        except Exception as e:
            logger.error(f"Error processing collection queue: {e}")
            await asyncio.sleep(5)

# ======================
# Main Collection Functions
# ======================

async def start_collection() -> bool:
    """بدء عملية جمع الروابط"""
    global _collection_active, _collection_paused, _collection_session_id
    global _collection_stats, _collected_urls
    
    try:
        # التحقق من عدم وجود عملية جمع نشطة
        if _collection_active:
            logger.warning("Collection is already active")
            return False
        
        # الحصول على الجلسات النشطة
        active_sessions = [s for s in get_sessions() if s.get('is_active')]
        if not active_sessions:
            logger.error("No active sessions available")
            return False
        
        # إعادة تعيين حالة الجمع
        reset_collection_state()
        
        # بدء جلسة جمع جديدة
        _collection_session_id = start_collection_session()
        if not _collection_session_id:
            logger.error("Failed to start collection session")
            return False
        
        # تحديث حالة الجمع
        _collection_active = True
        _collection_paused = False
        _collection_stats['start_time'] = datetime.now().isoformat()
        
        logger.info(f"Starting collection session {_collection_session_id} with {len(active_sessions)} active sessions")
        
        # إنشاء قائمة انتظار للروابط
        collection_queue = asyncio.Queue(maxsize=1000)
        
        # إنشاء مهام الجمع والمعالجة
        collection_tasks = []
        
        # مهمة معالجة قائمة الانتظار
        processor_task = asyncio.create_task(process_collection_queue(collection_queue))
        collection_tasks.append(processor_task)
        
        # مهام جمع الروابط من كل جلسة
        for session in active_sessions:
            if not _collection_active:
                break
            
            task = asyncio.create_task(
                collect_links_from_session(session, collection_queue)
            )
            collection_tasks.append(task)
            
            # تأخير بين بدء مهام الجلسات
            await asyncio.sleep(COLLECTION_DELAY * 3)
        
        # انتظار اكتمال جميع المهام
        try:
            await asyncio.gather(*collection_tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Error in collection tasks: {e}")
        
        # انتظار اكتمال معالجة جميع الروابط
        await collection_queue.join()
        
        # إيقاف المهام
        for task in collection_tasks:
            task.cancel()
        
        # إنهاء جلسة الجمع
        _collection_active = False
        _collection_stats['end_time'] = datetime.now().isoformat()
        
        # حساب المدة
        if _collection_stats['start_time'] and _collection_stats['end_time']:
            start = datetime.fromisoformat(_collection_stats['start_time'])
            end = datetime.fromisoformat(_collection_stats['end_time'])
            _collection_stats['duration'] = (end - start).total_seconds()
        
        # تحديث الإحصائيات النهائية
        update_collection_stats(_collection_session_id, _collection_stats)
        end_collection_session(_collection_session_id, 'completed')
        
        # تحديث إحصائيات اليوم
        update_daily_stats()
        
        logger.info(f"Collection completed. Total collected: {_collection_stats['total_collected']}")
        return True
        
    except Exception as e:
        logger.error(f"Error starting collection: {e}")
        
        # إنهاء جلسة الجمع في حالة الخطأ
        if _collection_session_id:
            update_collection_stats(_collection_session_id, _collection_stats)
            end_collection_session(_collection_session_id, 'error')
        
        reset_collection_state()
        return False

async def stop_collection() -> bool:
    """إيقاف عملية جمع الروابط"""
    global _collection_active, _collection_paused
    
    if not _collection_active:
        logger.warning("Collection is not active")
        return False
    
    logger.info("Stopping collection...")
    _collection_active = False
    _collection_paused = False
    
    # انتظار قليل للسماح بالمهام بالانتهاء
    await asyncio.sleep(2)
    
    # تحديث الإحصائيات النهائية
    if _collection_session_id:
        _collection_stats['end_time'] = datetime.now().isoformat()
        
        # حساب المدة
        if _collection_stats['start_time'] and _collection_stats['end_time']:
            start = datetime.fromisoformat(_collection_stats['start_time'])
            end = datetime.fromisoformat(_collection_stats['end_time'])
            _collection_stats['duration'] = (end - start).total_seconds()
        
        update_collection_stats(_collection_session_id, _collection_stats)
        end_collection_session(_collection_session_id, 'stopped')
        
        # تحديث إحصائيات اليوم
        update_daily_stats()
    
    logger.info(f"Collection stopped. Total collected: {_collection_stats['total_collected']}")
    return True

async def pause_collection() -> bool:
    """إيقاف جمع الروابط مؤقتاً"""
    global _collection_paused
    
    if not _collection_active:
        logger.warning("Collection is not active")
        return False
    
    if _collection_paused:
        logger.warning("Collection is already paused")
        return False
    
    logger.info("Pausing collection...")
    _collection_paused = True
    return True

async def resume_collection() -> bool:
    """استئناف جمع الروابط"""
    global _collection_paused
    
    if not _collection_active:
        logger.warning("Collection is not active")
        return False
    
    if not _collection_paused:
        logger.warning("Collection is not paused")
        return False
    
    logger.info("Resuming collection...")
    _collection_paused = False
    return True

# ======================
# Link Analysis Functions
# ======================

async def analyze_links_batch(links: List[str]) -> Dict:
    """تحليل مجموعة من الروابط"""
    results = {
        'total': len(links),
        'valid': 0,
        'invalid': 0,
        'telegram_groups': 0,
        'whatsapp_groups': 0,
        'channels': 0,
        'details': []
    }
    
    try:
        # الحصول على جلسة نشطة للتحقق
        active_sessions = [s for s in get_sessions() if s.get('is_active')]
        if not active_sessions:
            return results
        
        # استخدام أول جلسة نشطة
        session = active_sessions[0]
        session_string = session.get('session_string')
        
        client = TelegramClient(
            session_string,
            API_ID,
            API_HASH
        )
        
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.disconnect()
            return results
        
        # تحليل كل رابط
        for url in links:
            try:
                url = normalize_url(url)
                
                # التحقق من الرابط
                is_valid, link_type, details = await verify_link(client, url)
                
                result = {
                    'url': url,
                    'valid': is_valid,
                    'type': link_type,
                    'details': details
                }
                
                results['details'].append(result)
                
                if is_valid:
                    results['valid'] += 1
                    
                    if 'telegram' in details.get('platform', ''):
                        if link_type in ['public_group', 'private_group']:
                            results['telegram_groups'] += 1
                        elif link_type == 'channel':
                            results['channels'] += 1
                    elif 'whatsapp' in details.get('platform', ''):
                        if link_type == 'group':
                            results['whatsapp_groups'] += 1
                else:
                    results['invalid'] += 1
                
                # تأخير بين الطلبات
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error analyzing link {url}: {e}")
                results['invalid'] += 1
                continue
        
        await client.disconnect()
        
    except Exception as e:
        logger.error(f"Error in analyze_links_batch: {e}")
    
    return results

# ======================
# Test Functions
# ======================

async def test_collection_with_sample():
    """اختبار عملية الجمع بعينة صغيرة"""
    logger.info("Testing collection with sample...")
    
    # عينة من الروابط للاختبار
    sample_links = [
        "https://t.me/group_test",
        "https://t.me/+ABC123def",
        "https://chat.whatsapp.com/ABC123def",
        "https://t.me/channel_test"  # قناة للتجاهل
    ]
    
    results = await analyze_links_batch(sample_links)
    
    logger.info(f"Test results: {results}")
    return results

# ======================
# Main Entry Point for Testing
# ======================

if __name__ == "__main__":
    import sys
    
    async def main():
        """الدالة الرئيسية للاختبار"""
        print("🔧 Testing collector module...")
        
        # اختبار التحقق من الروابط
        test_links = [
            "https://t.me/test_group",
            "https://t.me/+test123",
            "https://chat.whatsapp.com/test123",
            "https://t.me/c/123456789"  # قناة
        ]
        
        print("\n🔍 Analyzing test links...")
        results = await analyze_links_batch(test_links)
        
        print(f"\n📊 Results:")
        print(f"• Total links: {results['total']}")
        print(f"• Valid links: {results['valid']}")
        print(f"• Invalid links: {results['invalid']}")
        print(f"• Telegram groups: {results['telegram_groups']}")
        print(f"• WhatsApp groups: {results['whatsapp_groups']}")
        print(f"• Channels: {results['channels']}")
        
        print("\n✅ Collector module test completed!")
    
    # تشغيل الاختبار
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
