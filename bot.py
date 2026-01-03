import asyncio
import logging
import os
import sys
import re
from typing import List, Dict, Set, Optional
from datetime import datetime, timedelta
from collections import OrderedDict
from functools import lru_cache
import aiohttp
from urllib.parse import urlparse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, ChannelPrivateError, UsernameNotOccupiedError,
    InviteHashInvalidError, InviteHashExpiredError, ChatAdminRequiredError
)
from telethon.tl.types import Channel, Chat

from config import BOT_TOKEN, LINKS_PER_PAGE, API_ID, API_HASH, init_config
from database import (
    init_db, get_link_stats, get_links_by_type, export_links_by_type,
    add_session, get_sessions, delete_session, update_session_status,
    start_collection_session, update_collection_stats, end_collection_session,
    delete_all_sessions, add_links_batch, get_active_collection_session
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
# Global Variables
# ======================

# حالة الجمع
_collection_active = False
_collection_paused = False
_current_collection_task = None
_stop_requested = False

# تحسين إدارة الذاكرة
MAX_COLLECTED_URLS = 20000  # تقليل الحد الأقصى لـ 20,000 فقط
MAX_BATCH_SIZE = 100  # حجم الدفعة لحفظ الروابط
_collected_urls = OrderedDict()  # لمنع التكرار مع حد أقصى

# ذاكرة مؤقتة للتحقق من الروابط
_verified_cache = {}
_cache_max_size = 5000  # زيادة التخزين المؤقت

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
    'join_requests': 0,
    'admin_errors': 0,
    'start_time': None,
    'end_time': None
}

# ======================
# Keyboards
# ======================

def main_menu_keyboard():
    """لوحة المفاتيح الرئيسية"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ إضافة جلسة", callback_data="menu_add_session"),
            InlineKeyboardButton("👥 عرض الجلسات", callback_data="menu_list_sessions")
        ],
        [
            InlineKeyboardButton("▶️ بدء الجمع", callback_data="menu_start_collect"),
            InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="menu_pause_collect")
        ],
        [
            InlineKeyboardButton("⏹️ توقيف الجمع", callback_data="menu_stop_collect"),
            InlineKeyboardButton("📊 عرض الروابط", callback_data="menu_view_links")
        ],
        [
            InlineKeyboardButton("📤 تصدير الروابط", callback_data="menu_export_links"),
            InlineKeyboardButton("📈 إحصائيات", callback_data="menu_stats")
        ],
        [
            InlineKeyboardButton("🗑️ حذف جميع الجلسات", callback_data="menu_delete_all_sessions")
        ]
    ])

def platforms_keyboard():
    """اختيار المنصة"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📨 تيليجرام", callback_data="view_telegram"),
            InlineKeyboardButton("📞 واتساب", callback_data="view_whatsapp")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")
        ]
    ])

def telegram_types_keyboard(page: int = 0):
    """أنواع روابط التليجرام"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 المجموعات العامة", callback_data="telegram_public_group_0"),
            InlineKeyboardButton("🔒 المجموعات الخاصة", callback_data="telegram_private_group_0")
        ],
        [
            InlineKeyboardButton("📋 مجموعات طلب الانضمام", callback_data="telegram_join_request_0")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_view_links")
        ]
    ])

def sessions_list_keyboard(sessions: List[Dict]):
    """قائمة الجلسات مع أزرار"""
    keyboard = []
    
    for session in sessions:
        session_id = session.get('id')
        display_name = session.get('display_name', f"جلسة {session_id}")
        status = "🟢" if session.get('is_active') else "🔴"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {display_name}",
                callback_data=f"session_info_{session_id}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")
    ])
    
    return InlineKeyboardMarkup(keyboard)

def session_actions_keyboard(session_id: int):
    """أزرار إجراءات الجلسة"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ حذف الجلسة", callback_data=f"delete_session_{session_id}"),
            InlineKeyboardButton("🔄 تفعيل/تعطيل", callback_data=f"toggle_session_{session_id}")
        ],
        [
            InlineKeyboardButton("🔙 رجوع للجلسات", callback_data="menu_list_sessions")
        ]
    ])

def delete_all_confirmation_keyboard():
    """تأكيد حذف جميع الجلسات"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ نعم، احذف الكل", callback_data="confirm_delete_all_sessions"),
            InlineKeyboardButton("❌ لا، إلغاء", callback_data="menu_list_sessions")
        ]
    ])

def export_options_keyboard():
    """خيارات التصدير"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 مجموعات عامة", callback_data="export_public_groups"),
            InlineKeyboardButton("🔒 مجموعات خاصة", callback_data="export_private_groups")
        ],
        [
            InlineKeyboardButton("📞 مجموعات واتساب", callback_data="export_whatsapp_groups"),
            InlineKeyboardButton("📋 طلبات انضمام", callback_data="export_join_requests")
        ],
        [
            InlineKeyboardButton("📊 تصدير الكل", callback_data="export_all")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")
        ]
    ])

def pagination_keyboard(platform: str, link_type: str, page: int, has_next: bool):
    """أزرار التصفح"""
    buttons = []
    
    if page > 0:
        buttons.append(
            InlineKeyboardButton("⬅️ السابق", callback_data=f"page_{platform}_{link_type}_{page-1}")
        )
    
    buttons.append(
        InlineKeyboardButton(f"📄 {page+1}", callback_data="current_page")
    )
    
    if has_next:
        buttons.append(
            InlineKeyboardButton("➡️ التالي", callback_data=f"page_{platform}_{link_type}_{page+1}")
        )
    
    if platform == "telegram":
        back_button = "view_telegram"
    elif platform == "whatsapp":
        back_button = "view_whatsapp"
    else:
        back_button = "menu_view_links"
    
    return InlineKeyboardMarkup([
        buttons,
        [InlineKeyboardButton("🔙 رجوع", callback_data=back_button)]
    ])

def collection_control_keyboard():
    """أزرار التحكم في الجمع"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ استئناف", callback_data="menu_resume_collect"),
            InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="menu_pause_collect")
        ],
        [
            InlineKeyboardButton("⏹️ توقيف نهائي", callback_data="menu_stop_collect")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")
        ]
    ])

# ======================
# Helper Functions
# ======================

def is_collecting():
    """التحقق مما إذا كان الجمع نشطاً"""
    return _collection_active

def get_collection_status():
    """الحصول على حالة الجمع الحالية"""
    return {
        'active': _collection_active,
        'paused': _collection_paused,
        'stop_requested': _stop_requested,
        'stats': _collection_stats.copy()
    }

def normalize_url(url: str) -> Optional[str]:
    """تحسين تطبيع الروابط"""
    if not url or not isinstance(url, str):
        return None
    
    url = url.strip()
    
    # إزالة الأحرف غير المرغوبة من البداية والنهاية
    url = re.sub(r'^[,\s*#!]+|[,\s*#!]+$', '', url)
    
    # إزالة المساحات المتعددة
    url = re.sub(r'\s+', '', url)
    
    # التأكد من أن الرابط يبدأ بـ http:// أو https://
    if not url.startswith(('http://', 'https://')):
        if url.startswith(('t.me/', 'telegram.me/')):
            url = 'https://' + url
        elif url.startswith('chat.whatsapp.com/'):
            url = 'https://' + url
        elif url.startswith('wa.me/'):
            url = 'https://' + url
        else:
            # إذا لم يكن رابط معروف، نعيد None
            return None
    
    # تحليل الرابط وإعادة بنائه بشكل صحيح
    try:
        parsed = urlparse(url)
        # إعادة بناء الرابط بدون query و fragment
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        # إزالة الـ trailing slash
        clean_url = clean_url.rstrip('/')
        return clean_url.lower()
    except:
        return None

def extract_telegram_username(url: str) -> Optional[str]:
    """استخراج اسم المستخدم من رابط تيليجرام بشكل محسن"""
    url = normalize_url(url)
    if not url:
        return None
    
    patterns = [
        r't\.me/([a-z0-9_][a-z0-9_]{4,31})(?:/|$)',
        r'telegram\.me/([a-z0-9_][a-z0-9_]{4,31})(?:/|$)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            username = match.group(1).lower()
            # التحقق من صحة اسم المستخدم
            if re.match(r'^[a-z0-9_]{5,32}$', username):
                return username
    
    return None

def extract_telegram_invite_hash(url: str) -> Optional[str]:
    """استخراج hash الدعوة من رابط تيليجرام الخاص"""
    url = normalize_url(url)
    if not url:
        return None
    
    patterns = [
        r't\.me/\+([a-z0-9_-]{10,})',
        r'telegram\.me/\+([a-z0-9_-]{10,})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def is_telegram_channel_link(url: str) -> bool:
    """التحقق مما إذا كان الرابط قناة تيليجرام بشكل دقيق"""
    url = normalize_url(url)
    if not url:
        return False
    
    # أنماط محددة للقنوات
    patterns = [
        r't\.me/c/\d+',
        r't\.me/s/[a-z0-9_]+',
        r't\.me/joinchat/[a-z0-9_-]+',
        r't\.me/broadcast/[a-z0-9_]+'
    ]
    
    for pattern in patterns:
        if re.match(pattern, url):
            return True
    
    # التحقق من اسم المستخدم
    username = extract_telegram_username(url)
    if username:
        channel_keywords = {'channel', 'قناة', 'news', 'اخبار', 'broadcast', 'official'}
        username_lower = username.lower()
        return any(keyword in username_lower for keyword in channel_keywords)
    
    return False

def is_join_request_link(url: str) -> bool:
    """التحقق مما إذا كان الرابط يحتوي على طلب انضمام"""
    url = normalize_url(url)
    if not url:
        return False
    return 't.me/+' in url or 'telegram.me/+' in url

def is_valid_whatsapp_link(url: str) -> bool:
    """التحقق من صحة رابط واتساب بدون فحص فعلي"""
    url = normalize_url(url)
    if not url:
        return False
    
    # أنماط صالحة لروابط واتساب
    patterns = [
        r'^https://chat\.whatsapp\.com/[a-z0-9]{22}$',
        r'^https://chat\.whatsapp\.com/[a-z0-9]{22}\?[a-z0-9=&_-]+$',
        r'^https://chat\.whatsapp\.com/invite/[a-z0-9]{22}$'
    ]
    
    return any(re.match(pattern, url, re.IGNORECASE) for pattern in patterns)

# ======================
# Cache Management
# ======================

class URLCache:
    """فئة لإدارة ذاكرة التخزين المؤقت للروابط"""
    
    def __init__(self, max_size: int = 20000):
        self.max_size = max_size
        self.cache = OrderedDict()
        self.verified_cache = {}
    
    def add(self, url: str, data: Dict = None):
        """إضافة رابط إلى الذاكرة المؤقتة"""
        if url in self.cache:
            # نقل العنصر إلى النهاية (الأحدث)
            self.cache.move_to_end(url)
        else:
            self.cache[url] = data or {}
            # إذا تجاوزنا الحد الأقصى، إزالة العناصر القديمة
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)
    
    def get(self, url: str) -> Optional[Dict]:
        """الحصول على بيانات الرابط من الذاكرة المؤقتة"""
        if url in self.cache:
            # نقل العنصر إلى النهاية (الأحدث)
            self.cache.move_to_end(url)
            return self.cache[url]
        return None
    
    def exists(self, url: str) -> bool:
        """التحقق من وجود الرابط في الذاكرة المؤقتة"""
        return url in self.cache
    
    def clear(self):
        """مسح الذاكرة المؤقتة"""
        self.cache.clear()
        self.verified_cache.clear()
    
    def cleanup(self):
        """تنظيف دوري للذاكرة المؤقتة"""
        # إزالة 10% من العناصر الأقدم إذا تجاوزنا 90% من السعة
        if len(self.cache) > self.max_size * 0.9:
            items_to_remove = int(self.max_size * 0.1)
            for _ in range(items_to_remove):
                self.cache.popitem(last=False)

url_cache = URLCache(max_size=MAX_COLLECTED_URLS)

# ======================
# Telegram Entity Cache
# ======================

class TelegramEntityCache:
    """تخزين مؤقت لكيانات تيليجرام لتحسين الأداء"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.entity_cache = OrderedDict()
    
    async def get_entity(self, client: TelegramClient, identifier: str):
        """الحصول على الكيان مع التخزين المؤقت"""
        if identifier in self.entity_cache:
            entity_data = self.entity_cache[identifier]
            # التحقق من أن الكيان لا يزال صالحاً
            try:
                return entity_data['entity']
            except:
                # إزالة من التخزين المؤقت وإعادة الحصول
                del self.entity_cache[identifier]
        
        try:
            entity = await client.get_entity(identifier)
            self.entity_cache[identifier] = {
                'entity': entity,
                'timestamp': datetime.now()
            }
            
            # إدارة حجم التخزين المؤقت
            if len(self.entity_cache) > self.max_size:
                self.entity_cache.popitem(last=False)
            
            return entity
        except Exception as e:
            logger.warning(f"Failed to get entity {identifier}: {e}")
            raise
    
    def clear(self):
        """مسح التخزين المؤقت"""
        self.entity_cache.clear()

entity_cache = TelegramEntityCache()

# ======================
# Link Collection Functions
# ======================

async def verify_telegram_group(client: TelegramClient, url: str) -> Dict:
    """التحقق من مجموعة تيليجرام بشكل محسن"""
    
    # التحقق من التخزين المؤقت أولاً
    cache_key = f"telegram_verify_{url}"
    if cache_key in _verified_cache:
        return _verified_cache[cache_key]
    
    try:
        url_normalized = normalize_url(url)
        if not url_normalized:
            result = {'status': 'invalid', 'reason': 'رابط غير صالح'}
            _verified_cache[cache_key] = result
            return result
        
        # التحقق إذا كان رابط قناة
        if is_telegram_channel_link(url_normalized):
            result = {'status': 'invalid', 'reason': 'قناة وليست مجموعة'}
            _verified_cache[cache_key] = result
            return result
        
        # التحقق من رابط طلب الانضمام
        is_join_request = is_join_request_link(url_normalized)
        
        if is_join_request:
            invite_hash = extract_telegram_invite_hash(url_normalized)
            if not invite_hash:
                result = {'status': 'invalid', 'reason': 'رابط دعوة غير صالح'}
                _verified_cache[cache_key] = result
                return result
            
            try:
                entity = await entity_cache.get_entity(client, invite_hash)
                link_type = 'join_request'
            except (InviteHashInvalidError, InviteHashExpiredError):
                result = {'status': 'invalid', 'reason': 'رابط دعوة غير صالح أو منتهي'}
                _verified_cache[cache_key] = result
                return result
            except Exception as e:
                logger.warning(f"Could not verify join request link {url_normalized}: {e}")
                result = {
                    'status': 'valid', 
                    'type': 'group', 
                    'title': 'مجموعة طلب انضمام',
                    'members': 0, 
                    'link_type': 'join_request'
                }
                _verified_cache[cache_key] = result
                return result
        else:
            username = extract_telegram_username(url_normalized)
            if not username:
                result = {'status': 'invalid', 'reason': 'رابط غير صالح'}
                _verified_cache[cache_key] = result
                return result
            
            try:
                entity = await entity_cache.get_entity(client, username)
                
                # تحديد نوع المجموعة بشكل صحيح
                if hasattr(entity, 'username') and entity.username:
                    link_type = 'public_group'
                else:
                    link_type = 'private_group'
                    
            except UsernameNotOccupiedError:
                result = {'status': 'invalid', 'reason': 'المجموعة غير موجودة'}
                _verified_cache[cache_key] = result
                return result
        
        # التحقق من نوع الكيان
        if isinstance(entity, Channel) and entity.broadcast:
            result = {'status': 'invalid', 'reason': 'قناة وليست مجموعة'}
            _verified_cache[cache_key] = result
            return result
        
        # الحصول على عدد الأعضاء
        members_count = 0
        try:
            if hasattr(entity, 'participants_count'):
                members_count = entity.participants_count
            elif isinstance(entity, (Channel, Chat)):
                # الحصول على عدد محدود من المشاركين
                try:
                    participants = await client.get_participants(entity, limit=5)
                    members_count = len([p for p in participants if not getattr(p, 'bot', False)])
                except (ChannelPrivateError, Exception):
                    pass
        except Exception as e:
            logger.debug(f"Error getting members count: {e}")
        
        # التحقق من وجود أعضاء
        if members_count > 0:
            title = getattr(entity, 'title', '')
            result = {
                'status': 'valid', 
                'type': 'group', 
                'title': title, 
                'members': members_count, 
                'link_type': link_type
            }
        else:
            result = {'status': 'invalid', 'reason': 'مجموعة فارغة أو لا تحتوي على أعضاء'}
        
        # حفظ في التخزين المؤقت
        _verified_cache[cache_key] = result
        if len(_verified_cache) > _cache_max_size:
            # إزالة العنصر الأقدم
            oldest_key = next(iter(_verified_cache))
            del _verified_cache[oldest_key]
        
        return result
            
    except FloodWaitError as e:
        logger.warning(f"Flood wait: {e.seconds} seconds")
        await asyncio.sleep(min(e.seconds + 5, 60))  # حد أقصى 60 ثانية
        result = {'status': 'retry', 'reason': f'Flood wait: {e.seconds}s'}
        _verified_cache[cache_key] = result
        return result
    
    except ChannelPrivateError:
        result = {'status': 'invalid', 'reason': 'المجموعة خاصة ولا يمكن الوصول إليها'}
        _verified_cache[cache_key] = result
        return result
    
    except ChatAdminRequiredError:
        _collection_stats['admin_errors'] += 1
        result = {'status': 'invalid', 'reason': 'صلاحيات غير كافية'}
        _verified_cache[cache_key] = result
        return result
    
    except Exception as e:
        logger.error(f"Error verifying telegram group {url}: {e}")
        result = {'status': 'error', 'reason': str(e)[:100]}
        _verified_cache[cache_key] = result
        return result

async def verify_whatsapp_group(url: str) -> Dict:
    """التحقق من رابط واتساب بدون فحص فعلي"""
    try:
        url_normalized = normalize_url(url)
        if not url_normalized:
            return {'status': 'invalid', 'reason': 'رابط غير صالح'}
        
        # التحقق من صيغة الرابط فقط
        if not is_valid_whatsapp_link(url_normalized):
            return {'status': 'invalid', 'reason': 'رابط واتساب غير صالح'}
        
        # نعتبر جميع روابط واتساب صالحة بناءً على الصيغة فقط
        return {
            'status': 'valid',
            'type': 'whatsapp_group',
            'title': 'مجموعة واتساب',
            'members': 0,
            'link_type': 'whatsapp_group',
            'confidence': 'medium'  # ثقة متوسطة بناءً على الصيغة فقط
        }
        
    except Exception as e:
        logger.error(f"Error verifying whatsapp group {url}: {e}")
        return {'status': 'error', 'reason': str(e)[:100]}

async def collect_links_from_session(session_data: Dict) -> Dict:
    """جمع الروابط من جلسة واحدة بشكل محسن"""
    session_id = session_data.get('id')
    session_string = session_data.get('session_string')
    display_name = session_data.get('display_name', f"Session_{session_id}")
    
    results = {
        'session_id': session_id,
        'display_name': display_name,
        'total_collected': 0,
        'telegram_groups': 0,
        'whatsapp_groups': 0,
        'join_requests': 0,
        'errors': 0,
        'admin_errors': 0,
        'links': []
    }
    
    client = None
    try:
        # إنشاء العميل
        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH,
            connection_retries=3,
            request_retries=2,
            flood_sleep_threshold=60
        )
        
        # الاتصال مع مهلة
        await asyncio.wait_for(client.connect(), timeout=30)
        
        # التحقق من التخويل
        if not await client.is_user_authorized():
            logger.error(f"Session {display_name} not authorized")
            return results
        
        # مصادر الجمع
        sources = [
            collect_from_dialogs_optimized,
            collect_from_messages_optimized,
            collect_whatsapp_links_optimized
        ]
        
        for source_func in sources:
            if not _collection_active or _stop_requested:
                break
            
            try:
                collected = await source_func(client, session_id)
                if collected:
                    results['links'].extend(collected)
                    results['total_collected'] += len(collected)
                    
                    # تحديث الإحصائيات
                    for link in collected:
                        if link['platform'] == 'telegram':
                            if link.get('link_type') == 'join_request':
                                results['join_requests'] += 1
                            else:
                                results['telegram_groups'] += 1
                        elif link['platform'] == 'whatsapp':
                            results['whatsapp_groups'] += 1
                    
                    logger.info(f"Collected {len(collected)} links from {source_func.__name__}")
                    
                    # حفظ الدفعة في قاعدة البيانات
                    if len(results['links']) >= MAX_BATCH_SIZE:
                        await save_links_batch(results['links'], session_id)
                        results['links'].clear()
                
                await asyncio.sleep(1)  # تأخير قصير بين المصادر
                
            except Exception as e:
                logger.error(f"Error in {source_func.__name__} for session {display_name}: {e}")
                results['errors'] += 1
                continue
        
        # حفظ أي روابط متبقية
        if results['links']:
            await save_links_batch(results['links'], session_id)
        
        logger.info(f"✅ Finished collection from {display_name}: {results['total_collected']} links")
        
    except asyncio.TimeoutError:
        logger.error(f"Timeout connecting to session {display_name}")
        results['errors'] += 1
    except Exception as e:
        logger.error(f"❌ Error collecting from session {display_name}: {e}")
        results['errors'] += 1
    
    finally:
        if client:
            try:
                await client.disconnect()
            except:
                pass
    
    return results

async def save_links_batch(links: List[Dict], session_id: int):
    """حفظ دفعة من الروابط في قاعدة البيانات"""
    if not links:
        return
    
    try:
        # تحضير البيانات للحفظ
        links_data = []
        for link in links:
            links_data.append({
                'url': link['url'],
                'platform': link['platform'],
                'link_type': link.get('link_type', 'unknown'),
                'title': link.get('title', ''),
                'members_count': link.get('members', 0),
                'session_id': session_id,
                'confidence': link.get('confidence', 'high')
            })
        
        # حفظ الدفعة
        success_count = add_links_batch(links_data)
        
        if success_count > 0:
            # تحديث الإحصائيات
            _collection_stats['total_collected'] += success_count
            
            for link in links_data:
                if link['platform'] == 'telegram':
                    _collection_stats['telegram_collected'] += 1
                    if link['link_type'] == 'public_group':
                        _collection_stats['public_groups'] += 1
                    elif link['link_type'] == 'private_group':
                        _collection_stats['private_groups'] += 1
                    elif link['link_type'] == 'join_request':
                        _collection_stats['join_requests'] += 1
                elif link['platform'] == 'whatsapp':
                    _collection_stats['whatsapp_collected'] += 1
                    _collection_stats['whatsapp_groups'] += 1
        
        logger.info(f"Saved batch of {success_count} links to database")
        
    except Exception as e:
        logger.error(f"Error saving links batch: {e}")

async def collect_from_dialogs_optimized(client: TelegramClient, session_id: int) -> List[Dict]:
    """جمع الروابط من الدردشات بشكل محسن"""
    collected = []
    
    try:
        dialogs = []
        async for dialog in client.iter_dialogs(limit=100):
            if not _collection_active or _stop_requested:
                break
            dialogs.append(dialog)
        
        # معالجة الدردشات في مجموعات
        for i in range(0, len(dialogs), 10):  # 10 في كل مرة
            if not _collection_active or _stop_requested:
                break
            
            batch = dialogs[i:i+10]
            for dialog in batch:
                if not _collection_active or _stop_requested:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # جمع فقط من المجموعات والقنوات
                    if not (dialog.is_group or dialog.is_channel):
                        continue
                    
                    # الحصول على رابط المجموعة
                    url = None
                    if hasattr(entity, 'username') and entity.username:
                        url = normalize_url(f"https://t.me/{entity.username}")
                    
                    if url:
                        # التحقق من التكرار
                        if url_cache.exists(url):
                            _collection_stats['duplicate_links'] += 1
                            continue
                        
                        # التحقق من الرابط
                        verification = await verify_telegram_group(client, url)
                        
                        if verification.get('status') == 'valid':
                            url_cache.add(url, verification)
                            
                            collected.append({
                                'url': url,
                                'platform': 'telegram',
                                'link_type': verification.get('link_type', 'unknown'),
                                'title': verification.get('title', ''),
                                'members': verification.get('members', 0),
                                'session_id': session_id,
                                'confidence': 'high'
                            })
                            
                            # تأخير مناسب
                            if is_join_request_link(url):
                                await asyncio.sleep(2)
                            else:
                                await asyncio.sleep(0.5)
                
                except Exception as e:
                    logger.debug(f"Error processing dialog: {e}")
                    continue
            
            # تأخير بين المجموعات
            await asyncio.sleep(1)
    
    except Exception as e:
        logger.error(f"Error collecting from dialogs: {e}")
    
    return collected

async def collect_from_messages_optimized(client: TelegramClient, session_id: int) -> List[Dict]:
    """جمع الروابط من الرسائل بشكل محسن"""
    collected = []
    
    try:
        # مصطلحات البحث المحسنة
        search_terms = [
            "مجموعة", "group", "دعوة", "invite", "رابط", "link",
            "انضمام", "join", "تليجرام", "telegram"
        ]
        
        # الحصول على قائمة بالدردشات أولاً
        dialogs = []
        async for dialog in client.iter_dialogs(limit=50):
            if not _collection_active or _stop_requested:
                break
            if dialog.is_group or dialog.is_channel:
                dialogs.append(dialog)
        
        # البحث في كل دردشة
        for dialog in dialogs:
            if not _collection_active or _stop_requested:
                break
            
            for term in search_terms:
                if not _collection_active or _stop_requested:
                    break
                
                try:
                    # استخراج الروابط من الرسائل
                    async for message in client.iter_messages(
                        dialog.entity, 
                        search=term, 
                        limit=20
                    ):
                        if not _collection_active or _stop_requested:
                            break
                        
                        if message.text:
                            urls = extract_urls_from_text(message.text)
                            
                            for url in urls:
                                if not _collection_active or _stop_requested:
                                    break
                                
                                await process_url(client, url, session_id, collected, message.date)
                    
                    await asyncio.sleep(1)  # تأخير بين مصطلحات البحث
                    
                except Exception as e:
                    logger.debug(f"Error searching for term '{term}' in {dialog.name}: {e}")
                    continue
            
            await asyncio.sleep(2)  # تأخير بين الدردشات
    
    except Exception as e:
        logger.error(f"Error collecting from messages: {e}")
    
    return collected

def extract_urls_from_text(text: str) -> List[str]:
    """استخراج جميع الروابط من النص بشكل محسن"""
    if not text:
        return []
    
    # أنماط متنوعة للروابط
    patterns = [
        r'https?://(?:t\.me|telegram\.me)/[^\s<>"\']+',
        r'https?://chat\.whatsapp\.com/[^\s<>"\']+',
        r't\.me/[^\s<>"\']+',
        r'telegram\.me/[^\s<>"\']+',
        r'chat\.whatsapp\.com/[^\s<>"\']+'
    ]
    
    urls = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        urls.extend(matches)
    
    # إزالة التكرارات
    unique_urls = []
    seen = set()
    for url in urls:
        normalized = normalize_url(url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_urls.append(normalized)
    
    return unique_urls

async def process_url(client: TelegramClient, url: str, session_id: int, 
                     collected: List[Dict], message_date=None) -> bool:
    """معالجة رابط واحد بشكل منفصل"""
    try:
        # التحقق من التكرار
        if url_cache.exists(url):
            _collection_stats['duplicate_links'] += 1
            return False
        
        # معالجة حسب نوع الرابط
        if 't.me' in url or 'telegram.me' in url:
            # تجاهل القنوات
            if is_telegram_channel_link(url):
                _collection_stats['channels_skipped'] += 1
                return False
            
            verification = await verify_telegram_group(client, url)
            
            if verification.get('status') == 'valid':
                url_cache.add(url, verification)
                
                collected.append({
                    'url': url,
                    'platform': 'telegram',
                    'link_type': verification.get('link_type', 'unknown'),
                    'title': verification.get('title', ''),
                    'members': verification.get('members', 0),
                    'session_id': session_id,
                    'confidence': 'high'
                })
                
                # تأخير مناسب
                if is_join_request_link(url):
                    await asyncio.sleep(3)
                else:
                    await asyncio.sleep(0.5)
                
                return True
        
        elif 'whatsapp.com' in url:
            # استخدام التاريخ الديناميكي
            if message_date and message_date < (datetime.now() - timedelta(days=30)):
                return False
            
            verification = await verify_whatsapp_group(url)
            
            if verification.get('status') == 'valid':
                url_cache.add(url, verification)
                
                collected.append({
                    'url': url,
                    'platform': 'whatsapp',
                    'link_type': 'whatsapp_group',
                    'title': verification.get('title', 'WhatsApp Group'),
                    'members': 0,
                    'session_id': session_id,
                    'confidence': verification.get('confidence', 'medium')
                })
                
                await asyncio.sleep(0.3)
                return True
        
        return False
        
    except Exception as e:
        logger.debug(f"Error processing URL {url}: {e}")
        return False

async def collect_whatsapp_links_optimized(client: TelegramClient, session_id: int) -> List[Dict]:
    """جمع روابط واتساب بشكل محسن"""
    collected = []
    
    try:
        # مصطلحات البحث عن واتساب
        search_terms = [
            "whatsapp", "واتساب", "chat.whatsapp.com", "wa.me"
        ]
        
        # الحصول على الدردشات أولاً
        dialogs = []
        async for dialog in client.iter_dialogs(limit=30):
            if not _collection_active or _stop_requested:
                break
            dialogs.append(dialog)
        
        # البحث في كل دردشة
        for dialog in dialogs:
            if not _collection_active or _stop_requested:
                break
            
            for term in search_terms:
                if not _collection_active or _stop_requested:
                    break
                
                try:
                    async for message in client.iter_messages(
                        dialog.entity, 
                        search=term, 
                        limit=15
                    ):
                        if not _collection_active or _stop_requested:
                            break
                        
                        if message.text:
                            # استخراج روابط واتساب فقط
                            whatsapp_patterns = [
                                r'https?://chat\.whatsapp\.com/[^\s<>"\']+',
                                r'chat\.whatsapp\.com/[^\s<>"\']+',
                                r'https?://wa\.me/[^\s<>"\']+'
                            ]
                            
                            urls = []
                            for pattern in whatsapp_patterns:
                                matches = re.findall(pattern, message.text, re.IGNORECASE)
                                urls.extend(matches)
                            
                            for raw_url in urls:
                                url = normalize_url(raw_url)
                                if url:
                                    await process_url(client, url, session_id, collected, message.date)
                    
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.debug(f"Error searching for WhatsApp term '{term}' in {dialog.name}: {e}")
                    continue
            
            await asyncio.sleep(1)
    
    except Exception as e:
        logger.error(f"Error collecting WhatsApp links: {e}")
    
    return collected

async def start_collection_process():
    """بدء عملية الجمع الرئيسية بشكل محسن"""
    global _collection_active, _collection_paused, _collection_stats, _stop_requested
    
    try:
        # إعادة تعيين الإحصائيات والتخزين المؤقت
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
            'join_requests': 0,
            'admin_errors': 0,
            'start_time': datetime.now().isoformat(),
            'end_time': None
        }
        url_cache.clear()
        entity_cache.clear()
        _verified_cache.clear()
        _stop_requested = False
        
        # بدء جلسة جمع جديدة
        session_id = start_collection_session()
        
        # حلقة الجمع الرئيسية
        cycle_count = 0
        while _collection_active and not _stop_requested:
            cycle_count += 1
            
            try:
                # الحصول على الجلسات النشطة
                active_sessions = [s for s in get_sessions() if s.get('is_active')]
                
                if not active_sessions:
                    logger.warning("No active sessions available")
                    await asyncio.sleep(30)
                    continue
                
                logger.info(f"Starting collection cycle {cycle_count} with {len(active_sessions)} active sessions")
                
                # جمع الروابط من كل جلسة
                collection_tasks = []
                for session in active_sessions:
                    if not _collection_active or _stop_requested:
                        break
                    
                    if _collection_paused:
                        await wait_while_paused()
                    
                    task = asyncio.create_task(collect_links_from_session(session))
                    collection_tasks.append(task)
                    
                    # إضافة تأخير بين بدء مهام الجلسات
                    await asyncio.sleep(5)
                
                # انتظار انتهاء جميع المهام
                if collection_tasks:
                    await asyncio.gather(*collection_tasks, return_exceptions=True)
                
                # تحديث إحصائيات الجلسة
                update_collection_stats(session_id, _collection_stats)
                
                # تنظيف التخزين المؤقت
                url_cache.cleanup()
                
                # انتظار قبل الدورة التالية
                if _collection_active and not _stop_requested:
                    logger.info(f"Collection cycle {cycle_count} completed, waiting 30 seconds")
                    await asyncio.sleep(30)
            
            except Exception as e:
                logger.error(f"❌ Error in main collection loop: {e}")
                await asyncio.sleep(10)
                continue
        
        # إنهاء جلسة الجمع
        _collection_stats['end_time'] = datetime.now().isoformat()
        update_collection_stats(session_id, _collection_stats)
        end_collection_session(session_id, 'completed' if not _stop_requested else 'stopped')
        
        logger.info(f"✅ Collection {'stopped' if _stop_requested else 'completed'}: {_collection_stats['total_collected']} total links")
        
        # إعادة تعيين الحالة
        if _stop_requested:
            _collection_active = False
            _stop_requested = False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Fatal error in collection process: {e}")
        _collection_active = False
        _stop_requested = False
        return False

async def wait_while_paused():
    """الانتظار أثناء التوقف المؤقت"""
    while _collection_paused and _collection_active and not _stop_requested:
        await asyncio.sleep(1)

# ======================
# Command Handlers (نفس الكود السابق)
# ======================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /start"""
    user = update.effective_user
    
    welcome_text = f"""  
🤖 *مرحباً {user.first_name}!*  
    
*بوت جمع روابط المجموعات النشطة فقط - الإصدار المحسن*  
    
📋 *المميزات الجديدة:*  
• أداء محسن وسريع  
• ذاكرة مؤقتة محسنة  
• جمع واتساب بتحقق صيغة فقط  
• تخزين مؤقت لكيانات تيليجرام  
• نظام دفعات لحفظ البيانات  
• تنظيم ذاكرة أفضل  
    
⚡ *أنواع المجموعات:*  
• 👥 مجموعات تيليجرام العامة  
• 🔒 مجموعات تيليجرام الخاصة  
• 📋 طلبات انضمام تيليجرام  
• 📞 مجموعات واتساب (بصيغة صحيحة)  
    
اختر من القائمة:"""  
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /help"""
    help_text = """
🆘 مساعدة - الإصدار المحسن

*مميزات محسنة:*  
• أداء أسرع في جمع الروابط  
• ذاكرة مؤقتة محسنة (20,000 رابط كحد أقصى)  
• تخزين مؤقت لكيانات تيليجرام  
• جمع واتساب بدون فحص فعلي (بصيغة فقط)  
• نظام دفعات لحفظ البيانات  
    
*كيف يعمل البوت:*  
1. يجمع الروابط من الدردشات المفتوحة  
2. يتحقق من صحة روابط تيليجرام  
3. يقبل روابط واتساب بصيغة صحيحة فقط  
4. يحفظ الروابط في قاعدة البيانات  
5. يمكن التصدير حسب النوع  
    
*ملاحظات مهمة:*  
• واتساب: يتم التحقق من الصيغة فقط، بدون فحص فعلي  
• الذاكرة: الحد الأقصى 20,000 رابط في الذاكرة المؤقتة  
• الأداء: تحسين في سرعة الاستجابة  
"""
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

# ======================
# باقي Handlers (نفس الكود السابق مع تعديلات طفيفة)
# ======================

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /status"""
    status = get_collection_status()
    
    if status['active']:
        if status['paused']:
            status_text = "⏸️ *الجمع موقف مؤقتاً*"
        elif status['stop_requested']:
            status_text = "🛑 *جاري التوقيف...*"
        else:
            status_text = "🔄 *جاري الجمع حالياً*"
        
        stats = status['stats']
        status_text += f"""  
        
📊 *الإحصائيات الحالية:*  
• مجموعات عامة: {stats.get('public_groups', 0)}  
• مجموعات خاصة: {stats.get('private_groups', 0)}  
• طلبات انضمام: {stats.get('join_requests', 0)}  
• مجموعات واتساب: {stats.get('whatsapp_groups', 0)}  
• الإجمالي: {stats.get('total_collected', 0)}  
        
• الروابط المكررة: {stats.get('duplicate_links', 0)}  
• القنوات المتجاهلة: {stats.get('channels_skipped', 0)}  
• أخطاء الإدارة: {stats.get('admin_errors', 0)}  
        
💾 *حالة الذاكرة:*  
• الروابط المخزنة مؤقتاً: {len(_collected_urls)}  
"""
    else:
        status_text = "🛑 *الجمع متوقف*"
    
    sessions = get_sessions()
    active_sessions = len([s for s in sessions if s.get('is_active')])
    
    status_text += f"\n\n👥 *الجلسات:* {len(sessions)} (نشطة: {active_sessions})"
    
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /stats"""
    stats = get_link_stats()
    
    if not stats:
        await update.message.reply_text("📭 لا توجد إحصائيات حالياً")
        return
    
    stats_text = "📈 *إحصائيات الروابط*\n\n"
    
    by_platform = stats.get('by_platform', {})
    if by_platform:
        stats_text += "*حسب المنصة:*\n"
        for platform, count in by_platform.items():
            platform_name = "تيليجرام" if platform == "telegram" else "واتساب"
            stats_text += f"• {platform_name}: {count}\n"
    
    telegram_by_type = stats.get('telegram_by_type', {})
    if telegram_by_type:
        stats_text += "\n*روابط تيليجرام حسب النوع:*\n"
        for link_type, count in telegram_by_type.items():
            if link_type == 'public_group':
                stats_text += f"• مجموعات عامة: {count}\n"
            elif link_type == 'private_group':
                stats_text += f"• مجموعات خاصة: {count}\n"
            elif link_type == 'join_request':
                stats_text += f"• طلبات انضمام: {count}\n"
    
    await update.message.reply_text(stats_text, parse_mode="Markdown")

# ======================
# Callback Handlers (نفس الكود السابق)
# ======================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جميع الردود"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    try:
        if data == "menu_main":
            await show_main_menu(query)
        elif data == "menu_add_session":
            context.user_data['awaiting_session'] = True
            await query.message.edit_text(
                "📥 *إضافة جلسة جديدة*\n\n"
                "أرسل لي Session String الآن:\n\n"
                "⚠️ *ملاحظة:* تأكد من أن الجلسة نشطة ومسجلة في تليجرام",
                parse_mode="Markdown"
            )
        elif data == "menu_list_sessions":
            await show_sessions_list(query)
        elif data == "menu_delete_all_sessions":
            await show_delete_all_confirmation(query)
        elif data == "confirm_delete_all_sessions":
            await delete_all_sessions_handler(query)
        elif data == "menu_start_collect":
            await start_collection_handler(query)
        elif data == "menu_pause_collect":
            await pause_collection_handler(query)
        elif data == "menu_resume_collect":
            await resume_collection_handler(query)
        elif data == "menu_stop_collect":
            await stop_collection_handler(query)
        elif data == "menu_view_links":
            await show_platforms_menu(query)
        elif data == "menu_export_links":
            await show_export_menu(query)
        elif data == "menu_stats":
            await show_stats(query)
        elif data == "view_telegram":
            await show_telegram_types(query)
        elif data == "view_whatsapp":
            await show_whatsapp_types(query)
        elif data.startswith("telegram_public_group_"):
            page = int(data.split('_')[3]) if len(data.split('_')) > 3 else 0
            await show_telegram_links(query, "public_group", page)
        elif data.startswith("telegram_private_group_"):
            page = int(data.split('_')[3]) if len(data.split('_')) > 3 else 0
            await show_telegram_links(query, "private_group", page)
        elif data.startswith("telegram_join_request_"):
            page = int(data.split('_')[3]) if len(data.split('_')) > 3 else 0
            await show_telegram_links(query, "join_request", page)
        elif data.startswith("session_info_"):
            session_id = int(data.split('_')[2])
            await show_session_info(query, session_id)
        elif data.startswith("delete_session_"):
            session_id = int(data.split('_')[2])
            await delete_session_handler(query, session_id)
        elif data.startswith("toggle_session_"):
            session_id = int(data.split('_')[2])
            await toggle_session_handler(query, session_id)
        elif data == "export_public_groups":
            await export_handler(query, "public_groups")
        elif data == "export_private_groups":
            await export_handler(query, "private_groups")
        elif data == "export_whatsapp_groups":
            await export_handler(query, "whatsapp_groups")
        elif data == "export_join_requests":
            await export_handler(query, "join_requests")
        elif data == "export_all":
            await export_handler(query, "all")
        elif data.startswith("page_"):
            parts = data.split('_')
            platform = parts[1]
            link_type = parts[2]
            page = int(parts[3])
            
            if platform == "telegram":
                await show_telegram_links(query, link_type, page)
        
        else:
            await query.message.edit_text("❌ أمر غير معروف")
    
    except Exception as e:
        logger.error(f"Error in callback handler: {e}")
        await query.message.edit_text(f"❌ حدث خطأ في المعالجة\n\n{str(e)[:200]}")

# ======================
# باقي Handlers (نفس الكود السابق)
# ======================

# [يتبع باقي الكود كما هو مع تعديلات طفيفة في الرسائل]
# handlers لـ show_main_menu, show_platforms_menu, show_telegram_types, إلخ...
# [الكود متطابق مع السابق مع تعديلات طفيفة في الرسائل التوضيحية]

async def show_whatsapp_types(query):
    """عرض أنواع روابط الواتساب"""
    await query.message.edit_text(
        "📞 روابط واتساب\n\n"
        "*ملاحظة:* البوت يقبل روابط واتساب بصيغة صحيحة فقط\n"
        "بدون فحص فعلي للمجموعات\n\n"
        "📌 *صيغ مقبولة:*\n"
        "• https://chat.whatsapp.com/ABCDEFGHIJKLMNOPQRSTUV\n"
        "• https://chat.whatsapp.com/invite/ABCDEFGHIJKLMNOPQRSTUV\n\n"
        "اختر نوع الروابط:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 مجموعات واتساب", callback_data="whatsapp_group")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="menu_view_links")]
        ]),
        parse_mode="Markdown"
    )

async def start_collection_handler(query):
    """بدء الجمع"""
    global _collection_active, _current_collection_task, _stop_requested
    
    if _collection_active:
        await query.message.edit_text("⏳ الجمع يعمل بالفعل")
        return
    
    active_sessions = [s for s in get_sessions() if s.get('is_active')]
    if not active_sessions:
        await query.message.edit_text(
            "❌ لا توجد جلسات نشطة\n\n"
            "يجب إضافة وتفعيل جلسة على الأقل",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة جلسة", callback_data="menu_add_session")]
            ])
        )
        return
    
    _collection_active = True
    _collection_paused = False
    _stop_requested = False
    
    # بدء عملية الجمع في خلفية
    _current_collection_task = asyncio.create_task(start_collection_process())
    
    await query.message.edit_text(
        "🚀 *بدأ جمع الروابط - الإصدار المحسن*\n\n"
        "⚡ *مميزات محسنة:*\n"
        "• أداء أسرع وسرعة استجابة أفضل\n"
        "• ذاكرة مؤقتة محسنة (20,000 رابط)\n"
        "• تخزين مؤقت لكيانات تيليجرام\n"
        "• نظام دفعات لحفظ البيانات\n\n"
        "📊 *أنواع المجموعات:*\n"
        "• مجموعات تيليجرام العامة والخاصة\n"
        "• روابط طلبات الانضمام (+)\n"
        "• روابط واتساب بصيغة صحيحة\n\n"
        "⚠️ *ملاحظة واتساب:*\n"
        "يتم قبول روابط واتساب بصيغة صحيحة فقط\n"
        "بدون فحص فعلي للمجموعات\n\n"
        "⏳ جاري جمع الروابط...",
        reply_markup=collection_control_keyboard(),
        parse_mode="Markdown"
    )

# ======================
# باقي الوظائف متطابقة مع الإصدار السابق
# ======================

# [جميع handlers الأخرى متطابقة مع الإصدار السابق]
# handlers لـ handle_message, show_sessions_list, show_session_info, إلخ...

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    message = update.message
    text = message.text.strip()
    
    if context.user_data.get('awaiting_session'):
        context.user_data['awaiting_session'] = False
        
        await message.reply_text("🔍 جاري التحقق من صحة الجلسة...")
        
        try:
            from session_manager import validate_session
            
            is_valid, account_info = await validate_session(text)
            
            if not is_valid:
                await message.reply_text(
                    "❌ الجلسة غير صالحة\n\n"
                    "تأكد من:\n"
                    "1. أن الجلسة صحيحة\n"
                    "2. أن الحساب نشط\n"
                    "3. أنك قمت بتسجيل الدخول مسبقاً",
                    reply_markup=main_menu_keyboard()
                )
                return
            
            phone = account_info.get('phone', '')
            username = account_info.get('username', '')
            user_id = account_info.get('user_id', 0)
            first_name = account_info.get('first_name', '')
            
            display_name = first_name or username or f"User_{user_id}"
            
            success = add_session(text, phone, user_id, username, display_name)
            
            if success:
                await message.reply_text(
                    f"✅ *تمت إضافة الجلسة بنجاح*\n\n"
                    f"• الاسم: {display_name}\n"
                    f"• المعرف: {user_id}\n"
                    f"• المستخدم: @{username or 'لا يوجد'}\n"
                    f"• الهاتف: {phone or 'غير معروف'}\n\n"
                    f"⚡ *الجلسة نشطة وجاهزة للاستخدام*",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard()
                )
            else:
                await message.reply_text(
                    "⚠️ *تمت إضافة الجلسة (قد تكون مضافة مسبقاً)*\n\n"
                    "يمكنك تفعيلها من قائمة الجلسات",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard()
                )
                
        except Exception as e:
            logger.error(f"Error adding session: {e}")
            await message.reply_text(
                f"❌ *خطأ في إضافة الجلسة*\n\n"
                f"التفاصيل: {str(e)[:150]}\n\n"
                f"تأكد من صحة Session String",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
    
    else:
        await message.reply_text(
            "👋 استخدم الأزرار للتحكم في البوت",
            reply_markup=main_menu_keyboard()
        )

# ======================
# Main Application
# ======================

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    try:
        # تهيئة الإعدادات والمجلدات
        print("🔧 جاري تهيئة البوت - الإصدار المحسن...")
        init_config()
        
        # تهيئة قاعدة البيانات
        print("🗄️  جاري تهيئة قاعدة البيانات...")
        init_db()
        
        print("✅ تمت التهيئة بنجاح!")
        print("\n⚡ *مميزات الإصدار المحسن:*")
        print("• أداء محسن وسريع")
        print("• ذاكرة مؤقتة محسنة (20,000 رابط كحد أقصى)")
        print("• تخزين مؤقت لكيانات تيليجرام")
        print("• جمع واتساب بتحقق صيغة فقط")
        print("• نظام دفعات لحفظ البيانات")
        print("• تنظيم ذاكرة أفضل")
        print("\n📊 *حدود النظام:*")
        print("• الذاكرة المؤقتة: 20,000 رابط")
        print("• حجم الدفعة: 100 رابط")
        print("• التخزين المؤقت للكيان: 1,000 كيان")
        print("\n🤖 Starting Telegram Link Collector Bot - Optimized Version...")
        
        # إنشاء تطبيق البوت
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        
        # إضافة handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("status", status_command))
        app.add_handler(CommandHandler("stats", stats_command))
        
        app.add_handler(CallbackQueryHandler(handle_callback))
        
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # تشغيل البوت
        logger.info("🤖 Starting Telegram Link Collector Bot - Optimized Version...")
        logger.info("⚡ Enhanced performance with caching")
        logger.info("💾 Memory optimized: Max 20,000 cached URLs")
        logger.info("📱 WhatsApp: Format validation only")
        logger.info("⚙️ Batch processing for database operations")
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}")
        print(f"❌ فشل تشغيل البوت: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
