import asyncio
import logging
import os
import sys
import re
import time
from typing import List, Dict, Set
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    InviteHashInvalidError, InviteHashExpiredError
)

from config import BOT_TOKEN, LINKS_PER_PAGE, API_ID, API_HASH, init_config
from database import (
    init_db, get_link_stats, get_links_by_type, export_links_by_type,
    add_session, get_sessions, delete_session, update_session_status,
    start_collection_session, update_collection_stats, end_collection_session,
    delete_all_sessions, add_link, get_active_collection_session
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
    'start_time': None,
    'end_time': None
}
_collected_urls = set()  # لمنع التكرار في الجلسة الواحدة

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
            InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="menu_stop_collect")
        ],
        [
            InlineKeyboardButton("📊 عرض الروابط", callback_data="menu_view_links"),
            InlineKeyboardButton("📤 تصدير الروابط", callback_data="menu_export_links")
        ],
        [
            InlineKeyboardButton("📈 إحصائيات", callback_data="menu_stats"),
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
        'stats': _collection_stats.copy()
    }

def normalize_url(url: str) -> str:
    """تطبيع الرابط"""
    url = url.strip()
    
    # إزالة tracking parameters
    if '?' in url:
        url = url.split('?')[0]
    
    # إضافة https:// إذا لم يكن موجوداً
    if not url.startswith(('http://', 'https://')):
        if url.startswith('t.me/'):
            url = 'https://' + url
        elif url.startswith('chat.whatsapp.com/'):
            url = 'https://' + url
    
    # إزالة الـ trailing slash
    if url.endswith('/'):
        url = url[:-1]
    
    return url.lower()

def extract_telegram_username(url: str) -> str:
    """استخراج اسم المستخدم من رابط تيليجرام"""
    patterns = [
        r't\.me/([A-Za-z0-9_]+)',
        r'telegram\.me/([A-Za-z0-9_]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1).lower()
    
    return ""

def extract_telegram_invite_hash(url: str) -> str:
    """استخراج hash الدعوة من رابط تيليجرام الخاص"""
    patterns = [
        r't\.me/\+([A-Za-z0-9_-]+)',
        r'telegram\.me/\+([A-Za-z0-9_-]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return ""

def is_telegram_channel_link(url: str) -> bool:
    """التحقق مما إذا كان الرابط قناة تيليجرام"""
    patterns = [
        r't\.me/c/[0-9]+',
        r't\.me/s/[A-Za-z0-9_]+'
    ]
    
    for pattern in patterns:
        if re.match(pattern, url, re.IGNORECASE):
            return True
    
    # بعض الأسماء المعروفة للقنوات
    username = extract_telegram_username(url)
    if username:
        channel_keywords = ['channel', 'news', 'broadcast', 'اخبار', 'قناة']
        return any(keyword in username.lower() for keyword in channel_keywords)
    
    return False

# ======================
# Link Collection Functions
# ======================

async def verify_telegram_group(client: TelegramClient, url: str) -> Dict:
    """التحقق من مجموعة تيليجرام"""
    try:
        url_lower = url.lower()
        
        # التحقق إذا كان رابط قناة
        if is_telegram_channel_link(url_lower):
            return {'status': 'invalid', 'reason': 'قناة وليست مجموعة'}
        
        # استخراج المعرف
        if '+invite' in url_lower or 't.me/+' in url_lower:
            # رابط دعوة خاص
            invite_hash = extract_telegram_invite_hash(url_lower)
            if not invite_hash:
                return {'status': 'invalid', 'reason': 'رابط دعوة غير صالح'}
            
            try:
                entity = await client.get_entity(invite_hash)
                link_type = 'private_group'
            except (InviteHashInvalidError, InviteHashExpiredError):
                return {'status': 'invalid', 'reason': 'رابط دعوة غير صالح أو منتهي'}
        else:
            # رابط عام
            username = extract_telegram_username(url_lower)
            if not username:
                return {'status': 'invalid', 'reason': 'رابط غير صالح'}
            
            try:
                entity = await client.get_entity(username)
                link_type = 'public_group'
            except UsernameNotOccupiedError:
                return {'status': 'invalid', 'reason': 'المجموعة غير موجودة'}
        
        # التحقق من نوع الكيان
        if hasattr(entity, 'broadcast') and entity.broadcast:
            return {'status': 'invalid', 'reason': 'قناة وليست مجموعة'}
        
        if hasattr(entity, 'gigagroup') and entity.gigagroup:
            return {'status': 'valid', 'type': 'supergroup', 'title': entity.title, 
                   'members': getattr(entity, 'participants_count', 0), 'link_type': link_type}
        
        if hasattr(entity, 'megagroup') and entity.megagroup:
            return {'status': 'valid', 'type': 'megagroup', 'title': entity.title, 
                   'members': getattr(entity, 'participants_count', 0), 'link_type': link_type}
        
        # محاولة الحصول على عدد الأعضاء
        members_count = 0
        try:
            if hasattr(entity, 'participants_count'):
                members_count = entity.participants_count
            else:
                participants = await client.get_participants(entity, limit=10)
                members_count = len([p for p in participants if not p.bot])
        except (ChannelPrivateError, Exception):
            pass
        
        # التحقق من وجود أعضاء (وليس مشتركين)
        if members_count > 0:
            return {'status': 'valid', 'type': 'group', 'title': getattr(entity, 'title', ''), 
                   'members': members_count, 'link_type': link_type}
        else:
            return {'status': 'invalid', 'reason': 'مجموعة فارغة أو لا تحتوي على أعضاء'}
        
    except FloodWaitError as e:
        logger.warning(f"Flood wait: {e.seconds} seconds")
        await asyncio.sleep(e.seconds + 5)
        return {'status': 'retry', 'reason': f'Flood wait: {e.seconds}s'}
    
    except ChannelPrivateError:
        return {'status': 'invalid', 'reason': 'المجموعة خاصة ولا يمكن الوصول إليها'}
    
    except Exception as e:
        logger.error(f"Error verifying telegram group {url}: {e}")
        return {'status': 'error', 'reason': str(e)}

async def collect_links_from_session(session_data: Dict) -> Dict:
    """جمع الروابط من جلسة واحدة"""
    session_id = session_data.get('id')
    session_string = session_data.get('session_string')
    display_name = session_data.get('display_name', f"Session_{session_id}")
    
    results = {
        'session_id': session_id,
        'display_name': display_name,
        'total_collected': 0,
        'telegram_groups': 0,
        'whatsapp_groups': 0,
        'errors': 0,
        'links': []
    }
    
    client = None
    try:
        # إنشاء العميل
        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH,
            device_model="Link Collector",
            system_version="4.16.30-vxCUSTOM",
            app_version="4.16.30",
            lang_code="ar"
        )
        
        # الاتصال
        await client.connect()
        
        # التحقق من التخويل
        if not await client.is_user_authorized():
            logger.error(f"Session {display_name} not authorized")
            return results
        
        # مصادر الجمع
        sources = [
            collect_from_dialogs,
            collect_from_joined_channels,
            collect_from_messages,
            collect_from_group_search
        ]
        
        for source_func in sources:
            if not _collection_active:
                break
            
            try:
                collected = await source_func(client, session_id)
                results['links'].extend(collected)
                results['total_collected'] += len(collected)
                
                # تحديث الإحصائيات
                for link in collected:
                    if 't.me' in link['url']:
                        results['telegram_groups'] += 1
                    elif 'whatsapp.com' in link['url']:
                        results['whatsapp_groups'] += 1
                
                logger.info(f"Collected {len(collected)} links from {source_func.__name__}")
                await asyncio.sleep(2)  # تأخير بين المصادر
                
            except Exception as e:
                logger.error(f"Error in {source_func.__name__} for session {display_name}: {e}")
                results['errors'] += 1
                continue
        
        logger.info(f"✅ Finished collection from {display_name}: {results['total_collected']} links")
        
    except Exception as e:
        logger.error(f"❌ Error collecting from session {display_name}: {e}")
        results['errors'] += 1
    
    finally:
        if client:
            await client.disconnect()
    
    return results

async def collect_from_dialogs(client: TelegramClient, session_id: int) -> List[Dict]:
    """جمع الروابط من الدردشات"""
    collected = []
    
    try:
        async for dialog in client.iter_dialogs(limit=100):
            if not _collection_active:
                break
            
            try:
                if dialog.is_group or dialog.is_channel:
                    entity = dialog.entity
                    
                    # الحصول على رابط المجموعة
                    url = None
                    if hasattr(entity, 'username') and entity.username:
                        url = f"https://t.me/{entity.username}"
                    elif hasattr(entity, 'megagroup') and entity.megagroup:
                        # محاولة إنشاء رابط دعوة
                        try:
                            invite = await client(ExportChatInviteRequest(entity))
                            if hasattr(invite, 'link'):
                                url = invite.link
                        except:
                            continue
                    
                    if url:
                        # التحقق من الرابط
                        verification = await verify_telegram_group(client, url)
                        
                        if verification.get('status') == 'valid':
                            collected.append({
                                'url': normalize_url(url),
                                'platform': 'telegram',
                                'link_type': verification.get('link_type', 'unknown'),
                                'title': verification.get('title', ''),
                                'members': verification.get('members', 0),
                                'session_id': session_id
                            })
                            
                            # تحديث قاعدة البيانات
                            success, _ = add_link(
                                url=normalize_url(url),
                                platform='telegram',
                                link_type=verification.get('link_type', 'unknown'),
                                title=verification.get('title', ''),
                                members_count=verification.get('members', 0),
                                session_id=session_id
                            )
                            
                            if success:
                                _collection_stats['total_collected'] += 1
                                if verification.get('link_type') == 'public_group':
                                    _collection_stats['public_groups'] += 1
                                    _collection_stats['telegram_collected'] += 1
                                elif verification.get('link_type') == 'private_group':
                                    _collection_stats['private_groups'] += 1
                                    _collection_stats['telegram_collected'] += 1
                            
                            await asyncio.sleep(0.5)  # تأخير بين الطلبات
                
            except Exception as e:
                logger.debug(f"Error processing dialog: {e}")
                continue
    
    except Exception as e:
        logger.error(f"Error collecting from dialogs: {e}")
    
    return collected

async def collect_from_joined_channels(client: TelegramClient, session_id: int) -> List[Dict]:
    """جمع الروابط من القنوات المنضمة"""
    collected = []
    
    try:
        dialogs = await client.get_dialogs(limit=50)
        
        for dialog in dialogs:
            if not _collection_active:
                break
            
            try:
                if dialog.is_channel and hasattr(dialog.entity, 'username') and dialog.entity.username:
                    url = f"https://t.me/{dialog.entity.username}"
                    
                    # تجاهل القنوات (نريد المجموعات فقط)
                    verification = await verify_telegram_group(client, url)
                    
                    if verification.get('status') == 'valid' and 'group' in verification.get('type', ''):
                        collected.append({
                            'url': normalize_url(url),
                            'platform': 'telegram',
                            'link_type': verification.get('link_type', 'unknown'),
                            'title': verification.get('title', ''),
                            'members': verification.get('members', 0),
                            'session_id': session_id
                        })
                
            except Exception as e:
                logger.debug(f"Error processing channel: {e}")
                continue
    
    except Exception as e:
        logger.error(f"Error collecting from channels: {e}")
    
    return collected

async def collect_from_messages(client: TelegramClient, session_id: int) -> List[Dict]:
    """جمع الروابط من الرسائل"""
    collected = []
    WHATSAPP_START_DATE = datetime(2025, 12, 12)
  
    try:
        # مصطلحات البحث عن الروابط
        search_terms = [
            "t.me", "telegram.me", "مجموعة", "group", "رابط", "دعوة",
            "انضمام", "انضم", "join", "whatsapp", "واتساب", "chat.whatsapp.com"
        ]
        
        for term in search_terms:
            if not _collection_active:
                break
            
            try:
                async for message in client.iter_messages(None, search=term, limit=30):
                    if not _collection_active:
                        break
                    
                    if message.text:
                        # استخراج جميع الروابط من النص
                        urls = re.findall(
                            r'(https?://[^\s]+|t\.me/[^\s]+|telegram\.me/[^\s]+|chat\.whatsapp\.com/[^\s]+)',
                            message.text
                        )
                        
                        for raw_url in urls:
                            try:
                                url = normalize_url(raw_url)
                                
                                # تجاهل الروابط المكررة
                                if url in _collected_urls:
                                    _collection_stats['duplicate_links'] += 1
                                    continue
                                # تحليل الرابط
if 't.me' in url or 'telegram.me' in url:
    # رابط تيليجرام

    if is_telegram_channel_link(url):
        _collection_stats['channels_skipped'] += 1
        continue

    verification = await verify_telegram_group(client, url)

    if verification.get('status') == 'valid':
        _collected_urls.add(url)

        collected.append({
            'url': url,
            'platform': 'telegram',
            'link_type': verification.get('link_type', 'unknown'),
            'title': verification.get('title', ''),
            'members': verification.get('members', 0),
            'session_id': session_id
        })

        success, _ = add_link(
            url=url,
            platform='telegram',
            link_type=verification.get('link_type', 'unknown'),
            title=verification.get('title', ''),
            members_count=verification.get('members', 0),
            session_id=session_id
        )

        if success:
            _collection_stats['total_collected'] += 1
            if verification.get('link_type') == 'public_group':
                _collection_stats['public_groups'] += 1
                _collection_stats['telegram_collected'] += 1
            elif verification.get('link_type') == 'private_group':
                _collection_stats['private_groups'] += 1
                _collection_stats['telegram_collected'] += 1

elif 'whatsapp.com' in url or 'chat.whatsapp.com' in url:
    # رابط واتساب

    if message.date and message.date < WHATSAPP_START_DATE:
        continue

    _collected_urls.add(url)

    collected.append({
        'url': url,
        'platform': 'whatsapp',
        'link_type': 'group',
        'title': 'WhatsApp Group',
        'members': 0,
        'session_id': session_id
    })

    success, _ = add_link(
        url=url,
        platform='whatsapp',
        link_type='group',
        title='WhatsApp Group',
        members_count=0,
        session_id=session_id
    )

    if success:
        _collection_stats['total_collected'] += 1
        _collection_stats['whatsapp_collected'] += 1
        _collection_stats['whatsapp_groups'] += 1
                                
                                elif 'whatsapp.com' in url or 'chat.whatsapp.com' in url:
                                elif 'whatsapp.com' in url or 'chat.whatsapp.com' in url:

     # فلترة تاريخ واتساب (من 12/12/2025 فقط)
     if message.date and message.date < WHATSAPP_START_DATE:
        continue

    # رابط واتساب
    _collected_urls.add(url)

    collected.append({
        'url': url,
        'platform': 'whatsapp',
        'link_type': 'group',
        'title': 'WhatsApp Group',
        'members': 0,
        'session_id': session_id
    })

    # حفظ في قاعدة البيانات
    success, _ = add_link(
        url=url,
        platform='whatsapp',
        link_type='group',
        title='WhatsApp Group',
        members_count=0,
        session_id=session_id
    )

    if success:
        _collection_stats['total_collected'] += 1
        _collection_stats['whatsapp_collected'] += 1
        _collection_stats['whatsapp_groups'] += 1

                                
                                await asyncio.sleep(0.3)  # تأخير بين الطلبات
                                
                            except Exception as e:
                                logger.debug(f"Error processing URL {raw_url}: {e}")
                                continue
                    
            except Exception as e:
                logger.error(f"Error searching for term '{term}': {e}")
                continue
            
            await asyncio.sleep(1)  # تأخير بين مصطلحات البحث
    
    except Exception as e:
        logger.error(f"Error collecting from messages: {e}")
    
    return collected

async def collect_from_group_search(client: TelegramClient, session_id: int) -> List[Dict]:
    """جمع الروابط من البحث عن المجموعات"""
    collected = []
    
    try:
        # كلمات البحث الشائعة للمجموعات العربية
        search_keywords = [
            "مجموعة", "شات", "دردشة", "تحدث", "نقاش", "حوار",
            "اجتماع", "مجتمع", "جروب", "group", "chat", "community"
        ]
        
        for keyword in search_keywords:
            if not _collection_active:
                break
            
            try:
                # البحث في تيليجرام
                search_results = await client(SearchRequest(
                    q=keyword,
                    filter=InputMessagesFilterEmpty(),
                    min_date=None,
                    max_date=None,
                    offset_id=0,
                    add_offset=0,
                    limit=20,
                    max_id=0,
                    min_id=0,
                    hash=0
                ))
                
                for result in getattr(search_results, 'chats', []):
                    if not _collection_active:
                        break
                    
                    try:
                        if hasattr(result, 'username') and result.username:
                            url = f"https://t.me/{result.username}"
                            
                            # تجاهل القنوات
                            if is_telegram_channel_link(url):
                                continue
                            
                            verification = await verify_telegram_group(client, url)
                            
                            if verification.get('status') == 'valid' and verification.get('members', 0) > 0:
                                _collected_urls.add(url)
                                
                                collected.append({
                                    'url': url,
                                    'platform': 'telegram',
                                    'link_type': verification.get('link_type', 'unknown'),
                                    'title': verification.get('title', ''),
                                    'members': verification.get('members', 0),
                                    'session_id': session_id
                                })
                                
                                # حفظ في قاعدة البيانات
                                success, _ = add_link(
                                    url=url,
                                    platform='telegram',
                                    link_type=verification.get('link_type', 'unknown'),
                                    title=verification.get('title', ''),
                                    members_count=verification.get('members', 0),
                                    session_id=session_id
                                )
                                
                                if success:
                                    _collection_stats['total_collected'] += 1
                                    if verification.get('link_type') == 'public_group':
                                        _collection_stats['public_groups'] += 1
                                        _collection_stats['telegram_collected'] += 1
                                    elif verification.get('link_type') == 'private_group':
                                        _collection_stats['private_groups'] += 1
                                        _collection_stats['telegram_collected'] += 1
                                
                                await asyncio.sleep(0.5)
                    
                    except Exception as e:
                        logger.debug(f"Error processing search result: {e}")
                        continue
            
            except Exception as e:
                logger.error(f"Error searching for keyword '{keyword}': {e}")
                continue
            
            await asyncio.sleep(2)  # تأخير بين كلمات البحث
    
    except Exception as e:
        logger.error(f"Error collecting from group search: {e}")
    
    return collected

async def start_collection_process():
    """بدء عملية الجمع الرئيسية"""
    global _collection_active, _collection_paused, _collection_stats, _collected_urls
    
    try:
        # إعادة تعيين الإحصائيات
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
            'start_time': datetime.now().isoformat(),
            'end_time': None
        }
        _collected_urls.clear()
        
        # بدء جلسة جمع جديدة
        session_id = start_collection_session()
        
        # الحصول على الجلسات النشطة
        active_sessions = [s for s in get_sessions() if s.get('is_active')]
        
        if not active_sessions:
            logger.error("No active sessions available")
            return False
        
        logger.info(f"Starting collection with {len(active_sessions)} active sessions")
        
        # جمع الروابط من كل جلسة
        for session in active_sessions:
            if not _collection_active:
                break
            
            if _collection_paused:
                while _collection_paused and _collection_active:
                    await asyncio.sleep(1)
            
            try:
                results = await collect_links_from_session(session)
                logger.info(f"Session {results['display_name']}: {results['total_collected']} links")
                
                # تحديث إحصائيات الجلسة
                update_collection_stats(session_id, _collection_stats)
                
            except Exception as e:
                logger.error(f"Error collecting from session {session.get('id')}: {e}")
                continue
        
        # إنهاء جلسة الجمع
        _collection_stats['end_time'] = datetime.now().isoformat()
        update_collection_stats(session_id, _collection_stats)
        end_collection_session(session_id, 'completed')
        
        logger.info(f"✅ Collection completed: {_collection_stats['total_collected']} total links")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error in collection process: {e}")
        return False

# ======================
# Command Handlers
# ======================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /start"""
    user = update.effective_user
    
    welcome_text = f"""
    🤖 *مرحباً {user.first_name}!*
    
    *بوت جمع روابط المجموعات النشطة فقط*
    
    📋 *المميزات:*
    • جمع روابط مجموعات تيليجرام العامة والخاصة النشطة فقط
    • جمع روابط مجموعات واتساب النشطة فقط
    • فحص الروابط للتأكد من وجود أعضاء (وليس مشتركين)
    • جمع الروابط القديمة والجديدة (من 2020 حتى المستقبل)
    • تصدير الروابط مصنفة حسب النوع
    
    ⚠️ *ملاحظة:* البوت يجمع فقط المجموعات التي تحتوي على أعضاء
    ❌ لا يجمع القنوات (t.me/channel)
    ❌ لا يجمع المجموعات الفارغة
    
    اختر من القائمة:"""
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /help"""
    help_text = """
    🆘 *مساعدة*
    
    *الأوامر المتاحة:*
    /start - بدء البوت وعرض القائمة
    /help - عرض هذه الرساءة
    /status - عرض حالة الجمع
    /stats - عرض إحصائيات الروابط
    
    *إضافة جلسة:*
    1. اضغط "➕ إضافة جلسة"
    2. أرسل Session String
    3. يتحقق البوت من صحتها
    
    *جمع الروابط:*
    - بدء الجمع: ▶️ بدء الجمع
    - إيقاف الجمع: ⏹️ إيقاف الجمع
    
    *مصادر الجمع:*
    • الدردشات والمحادثات
    • المجموعات المنضمة
    • رسائل المجموعات
    • نتائج البحث
    • روابط واتساب
    
    *تصدير الروابط:*
    يمكن تصدير الروابط حسب التصنيف:
    • مجموعات عامة
    • مجموعات خاصة
    • مجموعات واتساب
    """
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /status"""
    status = get_collection_status()
    
    if status['active']:
        if status['paused']:
            status_text = "⏸️ *الجمع موقف مؤقتاً*"
        else:
            status_text = "🔄 *جاري الجمع حالياً*"
        
        stats = status['stats']
        status_text += f"""
        
        📊 *الإحصائيات الحالية:*
        • مجموعات عامة: {stats.get('public_groups', 0)}
        • مجموعات خاصة: {stats.get('private_groups', 0)}
        • مجموعات واتساب: {stats.get('whatsapp_groups', 0)}
        • الإجمالي: {stats.get('total_collected', 0)}
        
        • الروابط المكررة: {stats.get('duplicate_links', 0)}
        • القنوات المتجاهلة: {stats.get('channels_skipped', 0)}
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
    
    await update.message.reply_text(stats_text, parse_mode="Markdown")

# ======================
# Callback Handlers
# ======================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جميع الردود"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    try:
        # القائمة الرئيسية
        if data == "menu_main":
            await show_main_menu(query)
        
        # إضافة جلسة
        elif data == "menu_add_session":
            context.user_data['awaiting_session'] = True
            await query.message.edit_text(
                "📥 *إضافة جلسة جديدة*\n\n"
                "أرسل لي Session String الآن:\n\n"
                "⚠️ *ملاحظة:* تأكد من أن الجلسة نشطة ومسجلة في تليجرام",
                parse_mode="Markdown"
            )
        
        # عرض الجلسات
        elif data == "menu_list_sessions":
            await show_sessions_list(query)
        
        # حذف جميع الجلسات
        elif data == "menu_delete_all_sessions":
            await show_delete_all_confirmation(query)
        
        elif data == "confirm_delete_all_sessions":
            await delete_all_sessions_handler(query)
        
        # بدء الجمع
        elif data == "menu_start_collect":
            await start_collection_handler(query)
        
        # إيقاف الجمع
        elif data == "menu_stop_collect":
            await stop_collection_handler(query)
        
        # عرض الروابط
        elif data == "menu_view_links":
            await show_platforms_menu(query)
        
        # تصدير الروابط
        elif data == "menu_export_links":
            await show_export_menu(query)
        
        # الإحصائيات
        elif data == "menu_stats":
            await show_stats(query)
        
        # اختيار المنصة
        elif data == "view_telegram":
            await show_telegram_types(query)
        
        elif data == "view_whatsapp":
            await show_whatsapp_types(query)
        
        # أنواع التليجرام
        elif data.startswith("telegram_public_group_"):
            page = int(data.split('_')[3]) if len(data.split('_')) > 3 else 0
            await show_telegram_links(query, "public_group", page)
        
        elif data.startswith("telegram_private_group_"):
            page = int(data.split('_')[3]) if len(data.split('_')) > 3 else 0
            await show_telegram_links(query, "private_group", page)
        
        # إدارة الجلسات
        elif data.startswith("session_info_"):
            session_id = int(data.split('_')[2])
            await show_session_info(query, session_id)
        
        elif data.startswith("delete_session_"):
            session_id = int(data.split('_')[2])
            await delete_session_handler(query, session_id)
        
        elif data.startswith("toggle_session_"):
            session_id = int(data.split('_')[2])
            await toggle_session_handler(query, session_id)
        
        # التصدير
        elif data == "export_public_groups":
            await export_handler(query, "public_groups")
        
        elif data == "export_private_groups":
            await export_handler(query, "private_groups")
        
        elif data == "export_whatsapp_groups":
            await export_handler(query, "whatsapp_groups")
        
        elif data == "export_all":
            await export_handler(query, "all")
        
        # التصفح
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
# Menu Handlers
# ======================

async def show_main_menu(query):
    """عرض القائمة الرئيسية"""
    await query.message.edit_text(
        "📱 *القائمة الرئيسية*\n\n"
        "اختر من الخيارات:",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

async def show_platforms_menu(query):
    """عرض قائمة المنصات"""
    await query.message.edit_text(
        "📊 *اختر المنصة:*",
        reply_markup=platforms_keyboard(),
        parse_mode="Markdown"
    )

async def show_telegram_types(query):
    """عرض أنواع روابط التليجرام"""
    await query.message.edit_text(
        "📨 *روابط تيليجرام*\n\n"
        "اختر نوع المجموعات:",
        reply_markup=telegram_types_keyboard(),
        parse_mode="Markdown"
    )

async def show_whatsapp_types(query):
    """عرض أنواع روابط الواتساب"""
    await query.message.edit_text(
        "📞 *روابط واتساب*\n\n"
        "اختر نوع الروابط:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 مجموعات واتساب", callback_data="whatsapp_group")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="menu_view_links")]
        ]),
        parse_mode="Markdown"
    )

async def show_export_menu(query):
    """عرض قائمة التصدير"""
    await query.message.edit_text(
        "📤 *تصدير البيانات*\n\n"
        "اختر نوع التصدير:",
        reply_markup=export_options_keyboard(),
        parse_mode="Markdown"
    )

async def show_stats(query):
    """عرض الإحصائيات"""
    stats = get_link_stats()
    
    if not stats:
        await query.message.edit_text("📭 لا توجد إحصائيات حالياً")
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
    
    await query.message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")]
        ]),
        parse_mode="Markdown"
    )

async def show_delete_all_confirmation(query):
    """عرض تأكيد حذف جميع الجلسات"""
    sessions = get_sessions()
    
    if not sessions:
        await query.message.edit_text(
            "📭 لا توجد جلسات لحذفها",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_list_sessions")]
            ])
        )
        return
    
    active_sessions = len([s for s in sessions if s.get('is_active')])
    
    await query.message.edit_text(
        f"⚠️ *تحذير: حذف جميع الجلسات*\n\n"
        f"• عدد الجلسات: {len(sessions)}\n"
        f"• الجلسات النشطة: {active_sessions}\n\n"
        f"❌ *هذا الإجراء لا يمكن التراجع عنه*\n"
        f"سيتم حذف جميع الجلسات نهائياً.\n\n"
        f"هل أنت متأكد؟",
        reply_markup=delete_all_confirmation_keyboard(),
        parse_mode="Markdown"
    )

# ======================
# Session Handlers
# ======================

async def show_sessions_list(query):
    """عرض قائمة الجلسات"""
    sessions = get_sessions()
    
    if not sessions:
        await query.message.edit_text(
            "📭 *لا توجد جلسات مضافة*\n\n"
            "اضغط ➕ إضافة جلسة لإضافة جلسة جديدة",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")]
            ]),
            parse_mode="Markdown"
        )
        return
    
    active_count = len([s for s in sessions if s.get('is_active')])
    
    await query.message.edit_text(
        f"👥 *الجلسات المضافة*\n\n"
        f"• الإجمالي: {len(sessions)}\n"
        f"• النشطة: {active_count}\n"
        f"• المعطلة: {len(sessions) - active_count}\n\n"
        f"اختر جلسة للتفاصيل:",
        reply_markup=sessions_list_keyboard(sessions),
        parse_mode="Markdown"
    )

async def show_session_info(query, session_id: int):
    """عرض معلومات جلسة محددة"""
    sessions = get_sessions()
    session = next((s for s in sessions if s.get('id') == session_id), None)
    
    if not session:
        await query.message.edit_text("❌ الجلسة غير موجودة")
        return
    
    status = "🟢 نشط" if session.get('is_active') else "🔴 غير نشط"
    added_date = session.get('added_date', 'غير معروف')[:10]
    last_used = session.get('last_used', 'لم يستخدم')[:10] if session.get('last_used') else 'لم يستخدم'
    phone = session.get('phone_number', 'غير معروف')
    username = session.get('username', 'غير معروف')
    display_name = session.get('display_name', 'غير معروف')
    
    info_text = f"""
    🔍 *معلومات الجلسة*
    
    • **الاسم:** {display_name}
    • **الحالة:** {status}
    • **رقم الهاتف:** {phone}
    • **اسم المستخدم:** @{username}
    • **تاريخ الإضافة:** {added_date}
    • **آخر استخدام:** {last_used}
    • **معرف الجلسة:** {session_id}
    """
    
    await query.message.edit_text(
        info_text,
        reply_markup=session_actions_keyboard(session_id),
        parse_mode="Markdown"
    )

async def delete_session_handler(query, session_id: int):
    """حذف جلسة"""
    success = delete_session(session_id)
    
    if success:
        await query.message.edit_text(
            "✅ تم حذف الجلسة بنجاح",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع إلى الجلسات", callback_data="menu_list_sessions")]
            ])
        )
    else:
        await query.message.edit_text(
            "❌ فشل حذف الجلسة",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_list_sessions")]
            ])
        )

async def delete_all_sessions_handler(query):
    """حذف جميع الجلسات"""
    sessions = get_sessions()
    
    if not sessions:
        await query.message.edit_text(
            "📭 لا توجد جلسات لحذفها",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_list_sessions")]
            ])
        )
        return
    
    # حذف جميع الجلسات
    success = delete_all_sessions()
    
    if success:
        await query.message.edit_text(
            f"✅ تم حذف جميع الجلسات بنجاح\n"
            f"• عدد الجلسات المحذوفة: {len(sessions)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="menu_main")]
            ])
        )
    else:
        await query.message.edit_text(
            "❌ فشل حذف جميع الجلسات",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_list_sessions")]
            ])
        )

async def toggle_session_handler(query, session_id: int):
    """تفعيل/تعطيل جلسة"""
    sessions = get_sessions()
    session = next((s for s in sessions if s.get('id') == session_id), None)
    
    if not session:
        await query.message.edit_text("❌ الجلسة غير موجودة")
        return
    
    new_status = not session.get('is_active')
    success = update_session_status(session_id, new_status)
    
    if success:
        status_text = "تفعيل" if new_status else "تعطيل"
        await query.message.edit_text(
            f"✅ تم {status_text} الجلسة",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع إلى الجلسات", callback_data="menu_list_sessions")]
            ])
        )
    else:
        await query.message.edit_text(
            "❌ فشل تحديث حالة الجلسة",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_list_sessions")]
            ])
        )

# ======================
# Collection Handlers
# ======================

async def start_collection_handler(query):
    """بدء الجمع"""
    global _collection_active, _current_collection_task
    
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
    
    # بدء عملية الجمع في خلفية
    _current_collection_task = asyncio.create_task(start_collection_process())
    
    await query.message.edit_text(
        "🚀 *بدأ جمع الروابط*\n\n"
        "⚡ *يتم جمع فقط:*\n"
        "• مجموعات تيليجرام العامة النشطة\n"
        "• مجموعات تيليجرام الخاصة النشطة\n"
        "• مجموعات واتساب النشطة\n\n"
        "🔍 *فحص الروابط:*\n"
        "• التحقق من وجود أعضاء (وليس مشتركين)\n"
        "• تجاهل القنوات والمجموعات الفارغة\n"
        "• منع تكرار الروابط\n\n"
        "⏳ جاري جمع الروابط من جميع الجلسات...\n"
        "سيتم إعلامك بالتقدم.",
        parse_mode="Markdown"
    )

async def stop_collection_handler(query):
    """إيقاف الجمع"""
    global _collection_active, _current_collection_task
    
    if not _collection_active:
        await query.message.edit_text("⚠️ الجمع غير نشط حالياً")
        return
    
    _collection_active = False
    
    if _current_collection_task:
        _current_collection_task.cancel()
        try:
            await _current_collection_task
        except asyncio.CancelledError:
            pass
        _current_collection_task = None
    
    stats = get_collection_status()['stats']
    
    stop_text = """
    ⏹️ *تم إيقاف الجمع بنجاح*
    
    📊 *إحصائيات الجمع الأخير:*
    • مجموعات عامة: {public_groups}
    • مجموعات خاصة: {private_groups}
    • مجموعات واتساب: {whatsapp_groups}
    • الإجمالي: {total_collected}
    
    • الروابط المكررة: {duplicate_links}
    • القنوات المتجاهلة: {channels_skipped}
    """.format(
        public_groups=stats.get('public_groups', 0),
        private_groups=stats.get('private_groups', 0),
        whatsapp_groups=stats.get('whatsapp_groups', 0),
        total_collected=stats.get('total_collected', 0),
        duplicate_links=stats.get('duplicate_links', 0),
        channels_skipped=stats.get('channels_skipped', 0)
    )
    
    await query.message.edit_text(stop_text, parse_mode="Markdown")

# ======================
# Link Viewing Handlers
# ======================

async def show_telegram_links(query, link_type: str, page: int = 0):
    """عرض روابط التليجرام"""
    type_names = {
        "public_group": "المجموعات العامة",
        "private_group": "المجموعات الخاصة"
    }
    
    title = type_names.get(link_type, link_type)
    links = get_links_by_type("telegram", link_type, LINKS_PER_PAGE, page * LINKS_PER_PAGE)
    
    if not links and page == 0:
        await query.message.edit_text(
            f"📭 لا توجد روابط {title}",
            reply_markup=telegram_types_keyboard(page)
        )
        return
    
    message_text = f"📨 *{title}*\n\n"
    message_text += f"📄 الصفحة: {page + 1}\n\n"
    
    for i, link in enumerate(links, start=page * LINKS_PER_PAGE + 1):
        url = link.get('url', '')
        # تقصير الرابط الطويل لعرض أفضل
        if len(url) > 40:
            display_url = url[:37] + "..."
        else:
            display_url = url
        
        # إضافة رمز حسب نوع الرابط
        if "t.me/+" in url:
            symbol = "🔒"
        else:
            symbol = "👥"
        
        # إضافة عدد الأعضاء إذا كان متوفراً
        members = link.get('members_count', 0)
        if members > 0:
            display_url += f" ({members} عضو)"
        
        message_text += f"{i}. {symbol} `{display_url}`\n"
    
    has_next = len(links) == LINKS_PER_PAGE
    
    await query.message.edit_text(
        message_text,
        reply_markup=pagination_keyboard("telegram", link_type, page, has_next),
        parse_mode="Markdown"
    )

# ======================
# Export Handlers
# ======================

async def export_handler(query, export_type: str):
    """معالجة طلبات التصدير"""
    await query.message.edit_text("⏳ جاري تحضير الملف...")
    
    try:
        if export_type == "public_groups":
            path = export_links_by_type("telegram", "public_group")
            filename = "telegram_public_groups.txt"
            caption = "👥 مجموعات تيليجرام العامة النشطة"
        
        elif export_type == "private_groups":
            path = export_links_by_type("telegram", "private_group")
            filename = "telegram_private_groups.txt"
            caption = "🔒 مجموعات تيليجرام الخاصة النشطة"
        
        elif export_type == "whatsapp_groups":
            path = export_links_by_type("whatsapp", "group")
            filename = "whatsapp_groups.txt"
            caption = "📞 مجموعات واتساب النشطة"
        
        elif export_type == "all":
            # تصدير جميع الروابط في ملفات منفصلة
            await query.message.edit_text("⏳ جاري تحضير جميع الملفات...")
            
            telegram_public = export_links_by_type("telegram", "public_group")
            telegram_private = export_links_by_type("telegram", "private_group")
            whatsapp_groups = export_links_by_type("whatsapp", "group")
            
            files_sent = 0
            
            if telegram_public and os.path.exists(telegram_public):
                with open(telegram_public, 'rb') as f:
                    await query.message.reply_document(
                        f,
                        filename="telegram_public_groups.txt",
                        caption="👥 مجموعات تيليجرام العامة النشطة"
                    )
                    files_sent += 1
            
            if telegram_private and os.path.exists(telegram_private):
                with open(telegram_private, 'rb') as f:
                    await query.message.reply_document(
                        f,
                        filename="telegram_private_groups.txt",
                        caption="🔒 مجموعات تيليجرام الخاصة النشطة"
                    )
                    files_sent += 1
            
            if whatsapp_groups and os.path.exists(whatsapp_groups):
                with open(whatsapp_groups, 'rb') as f:
                    await query.message.reply_document(
                        f,
                        filename="whatsapp_groups.txt",
                        caption="📞 مجموعات واتساب النشطة"
                    )
                    files_sent += 1
            
            if files_sent > 0:
                await query.message.edit_text(f"✅ تم تصدير {files_sent} ملف")
            else:
                await query.message.edit_text("❌ لا توجد بيانات للتصدير")
            return
        
        else:
            await query.message.edit_text("❌ نوع تصدير غير معروف")
            return
        
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                await query.message.reply_document(
                    f,
                    filename=filename,
                    caption=caption
                )
            await query.message.edit_text("✅ تم التصدير بنجاح")
        else:
            await query.message.edit_text("❌ لا توجد بيانات للتصدير")
    
    except Exception as e:
        logger.error(f"Export error: {e}")
        await query.message.edit_text(f"❌ حدث خطأ أثناء التصدير\n\n{str(e)[:100]}")

# ======================
# Message Handlers
# ======================

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
        print("🔧 جاري تهيئة البوت...")
        init_config()
        
        # تهيئة قاعدة البيانات
        print("🗄️  جاري تهيئة قاعدة البيانات...")
        init_db()
        
        print("✅ تمت التهيئة بنجاح!")
        
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
        logger.info("🤖 Starting Telegram Link Collector Bot...")
        logger.info("⚡ Bot will collect active groups only (not channels)")
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}")
        print(f"❌ فشل تشغيل البوت: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
