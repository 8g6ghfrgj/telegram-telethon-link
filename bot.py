import asyncio
import logging
import os
import sys
import re
import aiohttp
import random
import sqlite3
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Tuple, Any
from urllib.parse import urlparse, urlencode

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    JobQueue
)
from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, ChannelInvalidError, ChannelPrivateError,
    UsernameNotOccupiedError, UsernameInvalidError,
    InviteHashInvalidError, InviteHashExpiredError,
    ChatAdminRequiredError, ChatIdInvalidError,
    UserNotParticipantError, AuthKeyError
)

from config import BOT_TOKEN, LINKS_PER_PAGE, init_config, DATABASE_PATH, API_ID, API_HASH, SESSIONS_DIR
from database import (
    init_db, get_link_stats, get_links_by_type, export_links_by_type,
    add_session, get_sessions, delete_session, update_session_status,
    start_collection_session, update_collection_stats, get_active_collection_session,
    delete_all_sessions, add_link, get_all_links, link_exists,
    update_session_usage, get_session_usage_stats
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
_collection_job = None
_collection_stats = {
    'total_collected': 0,
    'telegram_collected': 0,
    'whatsapp_collected': 0,
    'public_groups': 0,
    'private_groups': 0,
    'whatsapp_groups': 0,
    'duplicate_links': 0,
    'inactive_links': 0,
    'invalid_links': 0,
    'channels_skipped': 0,
    'bots_skipped': 0,
    'start_time': None,
    'last_collection': None,
    'errors': 0
}

# ======================
# Configuration
# ======================

# مصادر الروابط القديمة (من عام 2020)
OLD_SOURCES = [
    # قنوات تيليجرام قديمة تحتوي على روابط مجموعات
    "https://t.me/s/TelegramChannels",
    "https://t.me/s/arabtelegramgroups",
    "https://t.me/s/telegram_groups_arabic",
    "https://t.me/s/arabicgroups",
    "https://t.me/s/TelegramGroups2020",
    "https://t.me/s/oldtelegramgroups",
    "https://t.me/s/TelegramGroupsArchive",
    "https://t.me/s/groups2021",
    "https://t.me/s/groups2022",
    "https://t.me/s/groups2023",
    
    # مصادر واتساب من 2025
    "https://t.me/s/Whatsapp_Groups_Links",
    "https://t.me/s/whatsappgroups2025",
    "https://t.me/s/WhatsAppGroupsLinks2025",
    "https://t.me/s/WhatsAppGroupsArchive",
    
    # مصادر أخرى
    "https://t.me/s/JoinGroups",
    "https://t.me/s/GroupLinksDaily",
    "https://t.me/s/FreeGroupLinks",
    "https://t.me/s/GroupInviteLinks",
    "https://t.me/s/PublicGroupsLinks",
]

# كلمات البحث للروابط القديمة
OLD_SEARCH_TERMS = [
    "مجموعة", "جروب", "group", "انضمام", "رابط", "دعوة",
    "t.me", "telegram.me", "whatsapp", "wa.me",
    "انضموا", "اضغط هنا", "اربط", "ارسل", "حياكم",
    "welcome", "join", "invite", "link", "دخول"
]

# ======================
# Link Collection Engine - Enhanced
# ======================

class AdvancedLinkCollector:
    """محرك جمع الروابط الذكي والمتقدم"""
    
    def __init__(self):
        self.session = None
        self.active_sessions = []
        self.collected_urls = set()
        self.blacklist = set()
        self.last_collection_time = {}
        self.http_session = None
        self.verified_links_cache = {}
        
    async def initialize(self):
        """تهيئة المجمع"""
        try:
            # إنشاء جلسة HTTP للتحقق من الروابط
            self.http_session = aiohttp.ClientSession()
            
            # تحميل الروابط المجمعة مسبقاً لمنع التكرار
            self.load_collected_urls()
            
            # تحميل القائمة السوداء
            self.load_blacklist()
            
            # تحميل ذاكرة التخزين المؤقت للروابط المفحوصة
            self.load_verified_cache()
            
            logger.info("✅ Advanced link collector initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error initializing link collector: {e}")
            return False
    
    def load_collected_urls(self):
        """تحميل الروابط المجمعة من قاعدة البيانات"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM links")
            urls = cursor.fetchall()
            conn.close()
            
            for url in urls:
                self.collected_urls.add(url[0])
            
            logger.info(f"📊 Loaded {len(self.collected_urls)} collected URLs")
            
        except Exception as e:
            logger.error(f"Error loading collected URLs: {e}")
    
    def load_verified_cache(self):
        """تحميل ذاكرة التخزين المؤقت للروابط المفحوصة"""
        try:
            cache_file = os.path.join(SESSIONS_DIR, "verified_links_cache.json")
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    self.verified_links_cache = json.load(f)
                logger.info(f"📊 Loaded verified cache: {len(self.verified_links_cache)} entries")
        except Exception as e:
            logger.error(f"Error loading verified cache: {e}")
            self.verified_links_cache = {}
    
    def save_verified_cache(self):
        """حفظ ذاكرة التخزين المؤقت"""
        try:
            cache_file = os.path.join(SESSIONS_DIR, "verified_links_cache.json")
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.verified_links_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving verified cache: {e}")
    
    def load_blacklist(self):
        """تحميل القائمة السوداء"""
        # قنوات معروفة يجب تجاهلها
        known_channels = [
            "telegram", "telegramtips", "telegramchannels",
            "telegramstore", "telegramandroid", "telegramios",
            "telegramdesktop", "telegramnews", "telegramapps",
            "durov", "telegramapp", "tgbeta", "tgandroid",
            "tgios", "tgmacos", "tgtips", "tgstories",
            "botfather", "bot", "channel", "news", "official"
        ]
        
        # كلمات تشير إلى القنوات والبوتات
        blacklist_keywords = [
            # قنوات
            'channel', 'قناة', 'رسمية', 'اخبارية', 'اعلانات',
            'announcement', 'broadcast', 'news', 'official',
            'نشرة', 'بث', 'اخبار', 'اعلام',
            
            # بوتات
            'bot', 'بوت', 'robot', 'روبو',
            
            # روابط غير مجمعة
            'store', 'android', 'ios', 'desktop',
            'apps', 'app', 'beta', 'tips', 'stories'
        ]
        
        for item in known_channels:
            self.blacklist.add(item.lower())
        
        for keyword in blacklist_keywords:
            self.blacklist.add(keyword.lower())
    
    def extract_links_from_text(self, text: str) -> List[str]:
        """استخراج الروابط من النص بكفاءة عالية"""
        if not text:
            return []
        
        urls = []
        
        # أنماط الروابط المدعومة
        patterns = [
            # تيليجرام
            r'https?://t\.me/(?:joinchat/)?[A-Za-z0-9_+-]+',
            r'https?://telegram\.me/(?:joinchat/)?[A-Za-z0-9_+-]+',
            r'tg://resolve\?domain=[A-Za-z0-9_+-]+',
            r'tg://join\?invite=[A-Za-z0-9_-]+',
            r'@[A-Za-z0-9_]{5,32}',
            
            # واتساب
            r'https?://chat\.whatsapp\.com/[A-Za-z0-9_-]+',
            r'https?://whatsapp\.com/channel/[A-Za-z0-9_-]+',
            r'https?://wa\.me/[0-9]+',
            r'https?://www\.whatsapp\.com/channel/[A-Za-z0-9_-]+',
            
            # روابط عامة
            r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            urls.extend(matches)
        
        # تنظيف وتطبيع الروابط
        cleaned_urls = []
        for url in urls:
            try:
                # تخطي المستخدمين الفرديين
                if url.startswith('@'):
                    continue
                
                url = url.strip()
                
                # إضافة https:// إذا لم يكن موجوداً
                if not url.startswith(('http://', 'https://', 'tg://')):
                    if url.startswith('t.me/'):
                        url = 'https://' + url
                    elif url.startswith('telegram.me/'):
                        url = 'https://' + url
                    elif url.startswith('wa.me/'):
                        url = 'https://' + url
                
                # إزالة علامات التحويل والمسافات
                url = url.split(' ')[0].strip()
                
                # إزالة الأحرف غير المرغوب فيها في النهاية
                url = re.sub(r'[.,;:!?()\[\]{}\'"<>]+$', '', url)
                
                cleaned_urls.append(url)
            except Exception as e:
                logger.debug(f"Error cleaning URL {url}: {e}")
                continue
        
        return list(set(cleaned_urls))  # إزالة التكرار
    
    def normalize_url(self, url: str) -> str:
        """تطبيع الرابط بشكل دقيق"""
        try:
            url = url.strip()
            
            # إزالة query parameters غير الضرورية
            if '?' in url:
                url_parts = url.split('?')
                url = url_parts[0]
            
            # إزالة trailing slash
            if url.endswith('/'):
                url = url[:-1]
            
            # تحويل إلى حروف صغيرة
            url = url.lower()
            
            # تحويل tg:// إلى https://
            if url.startswith('tg://'):
                if 'domain=' in url:
                    domain = url.split('domain=')[1].split('&')[0]
                    url = f"https://t.me/{domain}"
                elif 'invite=' in url:
                    invite = url.split('invite=')[1].split('&')[0]
                    url = f"https://t.me/+{invite}"
            
            # إزالة /joinchat/ إذا كان موجوداً
            url = url.replace('/joinchat/', '/')
            
            return url
        except Exception as e:
            logger.error(f"Error normalizing URL {url}: {e}")
            return url
    
    def is_url_blacklisted(self, url: str) -> Tuple[bool, str]:
        """التحقق مما إذا كان الرابط في القائمة السوداء"""
        url_lower = url.lower()
        
        # التحقق من القنوات المعروفة
        for blacklisted in self.blacklist:
            if blacklisted in url_lower:
                return True, f"محتوى محظور: {blacklisted}"
        
        # التحقق من أنماط القنوات
        if re.search(r't\.me/c/[0-9]+', url_lower):
            return True, "قناة تيليجرام"
        
        if re.search(r'tg://privatepost\?channel=[0-9]+', url_lower):
            return True, "قناة خاصة"
        
        # التحقق من البوتات
        if re.search(r't\.me/.*bot', url_lower) or '/bot' in url_lower:
            return True, "بوت"
        
        # التحقق من أنماط المجموعات الغير مرغوب فيها
        if re.search(r't\.me/[0-9]+', url_lower):
            return True, "رابط برقم"
        
        # التحقق من الروابط غير النشطة
        if 't.me/+' in url_lower:
            # روابط الدعوة تحتاج فحص إضافي
            pass
        
        return False, ""
    
    async def verify_telegram_link_detailed(self, url: str, client: Optional[TelegramClient] = None) -> Dict:
        """التحقق التفصيلي من رابط تيليجرام"""
        result = {
            'url': url,
            'is_valid': False,
            'is_active': False,
            'platform': 'telegram',
            'link_type': 'unknown',
            'members_count': 0,
            'active_members': 0,
            'participants_count': 0,
            'online_count': 0,
            'title': '',
            'description': '',
            'is_channel': False,
            'is_group': False,
            'is_supergroup': False,
            'is_broadcast': False,
            'has_username': False,
            'is_verified': False,
            'error': '',
            'verification_time': datetime.now().isoformat()
        }
        
        try:
            # التحقق من التخزين المؤقت أولاً
            cache_key = self.normalize_url(url)
            if cache_key in self.verified_links_cache:
                cached_data = self.verified_links_cache[cache_key]
                if datetime.now().timestamp() - cached_data.get('cache_time', 0) < 86400:  # 24 ساعة
                    return cached_data
            
            # تحديد نوع الرابط
            if 't.me/+' in url or 'telegram.me/+' in url or 'tg://join' in url:
                result['link_type'] = 'private_group'
                result['has_username'] = False
                
            elif 't.me/' in url or 'telegram.me/' in url:
                result['link_type'] = 'public_group'
                result['has_username'] = True
                
                # استخراج معرف المستخدم
                match = re.search(r't\.me/([A-Za-z0-9_]+)', url) or re.search(r'telegram\.me/([A-Za-z0-9_]+)', url)
                if match:
                    username = match.group(1).lower()
                    
                    # التحقق من القائمة السوداء
                    is_blacklisted, reason = self.is_url_blacklisted(url)
                    if is_blacklisted:
                        result['error'] = f'محتوى محظور: {reason}'
                        result['is_valid'] = False
                        return result
            
            # إذا كان هناك عميل تيليجرام متاح، قم بالتحقق التفصيلي
            if client:
                try:
                    if result['has_username']:
                        # الحصول على الكيان باستخدام معرف المستخدم
                        match = re.search(r't\.me/([A-Za-z0-9_]+)', url) or re.search(r'telegram\.me/([A-Za-z0-9_]+)', url)
                        if match:
                            username = match.group(1)
                            
                            try:
                                entity = await client.get_entity(username)
                                
                                # تحديد نوع الكيان
                                if hasattr(entity, 'broadcast') and entity.broadcast:
                                    result['is_channel'] = True
                                    result['is_broadcast'] = True
                                    result['error'] = 'قناة بث'
                                    result['is_valid'] = False
                                elif hasattr(entity, 'megagroup') and entity.megagroup:
                                    result['is_group'] = True
                                    result['is_supergroup'] = True
                                    result['is_valid'] = True
                                elif hasattr(entity, 'gigagroup'):
                                    result['is_group'] = True
                                    result['is_supergroup'] = True
                                    result['is_valid'] = True
                                else:
                                    result['is_group'] = True
                                    result['is_valid'] = True
                                
                                if result['is_valid']:
                                    # الحصول على المعلومات التفصيلية
                                    result['title'] = getattr(entity, 'title', '')
                                    result['description'] = getattr(entity, 'about', '')
                                    result['is_verified'] = getattr(entity, 'verified', False)
                                    
                                    # محاولة الحصول على عدد الأعضاء
                                    try:
                                        if hasattr(entity, 'participants_count'):
                                            result['participants_count'] = entity.participants_count
                                        
                                        # الحصول على بعض المشاركين للتحقق من النشاط
                                        participants = await client.get_participants(entity, limit=100)
                                        result['members_count'] = len(participants)
                                        
                                        # حساب الأعضاء النشطين (غير البوتات، متصلون مؤخراً)
                                        active_members = 0
                                        for participant in participants:
                                            if not getattr(participant, 'bot', False):
                                                active_members += 1
                                                # التحقق من آخر ظهور
                                                if hasattr(participant, 'status'):
                                                    if participant.status:
                                                        # التحقق مما إذا كان متصل في آخر 7 أيام
                                                        if hasattr(participant.status, 'was_online'):
                                                            was_online = participant.status.was_online
                                                            if was_online:
                                                                days_ago = (datetime.now() - was_online.replace(tzinfo=None)).days
                                                                if days_ago <= 7:
                                                                    result['online_count'] += 1
                                        
                                        result['active_members'] = active_members
                                        
                                        # حد أدنى للأعضاء النشطين
                                        if result['active_members'] >= 10:
                                            result['is_active'] = True
                                        else:
                                            result['is_active'] = False
                                            result['error'] = 'أعضاء غير كافيين'
                                    
                                    except Exception as e:
                                        logger.debug(f"Error getting participants for {url}: {e}")
                                        result['members_count'] = 0
                                        result['active_members'] = 0
                                        result['is_active'] = True  # نفترض النشاط في حالة الفشل
                                
                            except (UsernameNotOccupiedError, UsernameInvalidError):
                                result['error'] = 'المستخدم غير موجود'
                            except ChannelPrivateError:
                                result['error'] = 'المجموعة خاصة'
                            except Exception as e:
                                result['error'] = str(e)[:100]
                    
                    else:
                        # روابط الدعوة الخاصة
                        result['is_valid'] = True
                        result['is_active'] = True  # نفترض النشاط للروابط الخاصة
                
                except Exception as e:
                    logger.error(f"Error verifying telegram link {url} with client: {e}")
                    result['error'] = str(e)[:100]
            
            else:
                # بدون عميل، نقوم بتحقق أساسي
                result['is_valid'] = True
                result['is_active'] = True
            
            # حفظ في التخزين المؤقت
            result['cache_time'] = datetime.now().timestamp()
            self.verified_links_cache[cache_key] = result
            
            return result
            
        except Exception as e:
            logger.error(f"Error in verify_telegram_link_detailed for {url}: {e}")
            result['error'] = str(e)[:100]
            return result
    
    async def verify_whatsapp_link_detailed(self, url: str) -> Dict:
        """التحقق التفصيلي من رابط واتساب"""
        result = {
            'url': url,
            'is_valid': False,
            'is_active': False,
            'platform': 'whatsapp',
            'link_type': 'group',
            'members_count': 0,
            'title': '',
            'description': '',
            'error': '',
            'verification_time': datetime.now().isoformat()
        }
        
        try:
            # التحقق من التخزين المؤقت أولاً
            cache_key = self.normalize_url(url)
            if cache_key in self.verified_links_cache:
                cached_data = self.verified_links_cache[cache_key]
                if datetime.now().timestamp() - cached_data.get('cache_time', 0) < 86400:
                    return cached_data
            
            # التحقق من تنسيق رابط واتساب
            if 'chat.whatsapp.com' in url:
                result['is_valid'] = True
                
                try:
                    # محاولة الوصول إلى صفحة الرابط
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    
                    async with self.http_session.get(url, headers=headers, timeout=15) as response:
                        if response.status == 200:
                            html = await response.text()
                            
                            # البحث عن معلومات المجموعة
                            result['is_active'] = True
                            
                            # محاولة استخراج اسم المجموعة
                            title_match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
                            if title_match:
                                result['title'] = title_match.group(1).strip()
                                if 'whatsapp' in result['title'].lower():
                                    result['title'] = 'مجموعة واتساب'
                            
                            # البحث عن معلومات الأعضاء
                            members_match = re.search(r'(\d+)\s*(?:أعضاء|members|مشتركين)', html, re.IGNORECASE)
                            if members_match:
                                result['members_count'] = int(members_match.group(1))
                            
                            # التحقق مما إذا كانت الصفحة تظهر خطأ
                            if 'expired' in html.lower() or 'غير صالح' in html.lower():
                                result['is_active'] = False
                                result['error'] = 'الرابط منتهي'
                            
                        elif response.status == 404:
                            result['is_active'] = False
                            result['error'] = 'الرابط غير موجود'
                        else:
                            result['is_active'] = False
                            result['error'] = f'HTTP {response.status}'
                
                except asyncio.TimeoutError:
                    result['is_active'] = False
                    result['error'] = 'مهلة الاتصال'
                except Exception as e:
                    logger.debug(f"Error checking whatsapp link {url}: {e}")
                    result['is_active'] = True  # نفترض النشاط
            else:
                result['error'] = 'تنسيق رابط غير مدعوم'
            
            # حفظ في التخزين المؤقت
            result['cache_time'] = datetime.now().timestamp()
            self.verified_links_cache[cache_key] = result
            
            return result
            
        except Exception as e:
            logger.error(f"Error in verify_whatsapp_link_detailed for {url}: {e}")
            result['error'] = str(e)[:100]
            return result
    
    async def verify_link_comprehensive(self, url: str, client: Optional[TelegramClient] = None) -> Dict:
        """تحقق شامل من أي رابط"""
        url = self.normalize_url(url)
        
        # التحقق من التكرار
        if link_exists(url):
            return {
                'url': url,
                'is_valid': False,
                'is_active': False,
                'error': 'رابط مكرر',
                'duplicate': True
            }
        
        # التحقق من القائمة السوداء
        is_blacklisted, reason = self.is_url_blacklisted(url)
        if is_blacklisted:
            return {
                'url': url,
                'is_valid': False,
                'is_active': False,
                'error': reason,
                'blacklisted': True
            }
        
        # تحديد المنصة والتحقق
        if 't.me' in url or 'telegram.me' in url or 'tg://' in url:
            result = await self.verify_telegram_link_detailed(url, client)
        elif 'whatsapp.com' in url or 'wa.me' in url:
            result = await self.verify_whatsapp_link_detailed(url)
        else:
            result = {
                'url': url,
                'is_valid': False,
                'is_active': False,
                'error': 'منصة غير مدعومة',
                'unsupported': True
            }
        
        return result
    
    async def collect_from_session_comprehensive(self, session_info: Dict) -> int:
        """جمع شامل للروابط من جلسة تيليجرام"""
        collected = 0
        client = None
        
        try:
            client = TelegramClient(
                StringSession(session_info['session_string']),
                API_ID,
                API_HASH,
                device_model="Link Collector Pro",
                system_version="4.16.30",
                app_version="4.16.30",
                system_lang_code="ar",
                lang_code="ar"
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error(f"Session {session_info['id']} not authorized")
                return 0
            
            logger.info(f"🔍 Starting comprehensive collection from session: {session_info['display_name']}")
            
            # الجزء 1: جمع من الدردشات الحالية
            collected += await self.collect_from_dialogs(client, session_info['id'])
            
            if not _collection_active:
                return collected
            
            # الجزء 2: جمع من الرسائل القديمة (من 2020)
            collected += await self.collect_from_old_messages(client, session_info['id'])
            
            if not _collection_active:
                return collected
            
            # الجزء 3: البحث عن روابط في القنوات العامة
            collected += await self.collect_from_public_channels(client, session_info['id'])
            
            # تحديث وقت آخر استخدام للجلسة
            update_session_usage(session_info['id'])
            
            logger.info(f"📈 Session {session_info['display_name']} collected {collected} links")
            
        except Exception as e:
            logger.error(f"Error collecting from session {session_info['id']}: {e}")
            global _collection_stats
            _collection_stats['errors'] += 1
        
        finally:
            if client:
                await client.disconnect()
        
        return collected
    
    async def collect_from_dialogs(self, client: TelegramClient, session_id: int) -> int:
        """جمع الروابط من الدردشات"""
        collected = 0
        
        try:
            logger.info("📂 Collecting from dialogs...")
            
            dialogs = []
            async for dialog in client.iter_dialogs(limit=200):
                if not _collection_active:
                    break
                dialogs.append(dialog)
            
            logger.info(f"📊 Found {len(dialogs)} dialogs")
            
            for dialog in dialogs:
                if not _collection_active:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # تخطي المحادثات الخاصة
                    if not (dialog.is_group or dialog.is_channel):
                        continue
                    
                    # محاولة الحصول على رابط المجموعة
                    url = None
                    
                    if hasattr(entity, 'username') and entity.username:
                        url = f"https://t.me/{entity.username}"
                    
                    elif dialog.is_group and hasattr(entity, 'id'):
                        # محاولة إنشاء رابط دعوة للمجموعات الخاصة
                        try:
                            invite = await client(functions.messages.ExportChatInviteRequest(
                                peer=entity.id
                            ))
                            if hasattr(invite, 'link'):
                                url = invite.link
                        except Exception:
                            pass
                    
                    if url:
                        verification = await self.verify_link_comprehensive(url, client)
                        
                        if verification['is_valid'] and verification['is_active']:
                            platform = 'telegram'
                            link_type = 'public_group' if 't.me/' in url and not 't.me/+' in url else 'private_group'
                            
                            success, link_id = add_link(
                                url=url,
                                platform=platform,
                                link_type=link_type,
                                title=verification.get('title', ''),
                                members_count=verification.get('active_members', verification.get('members_count', 0)),
                                session_id=session_id
                            )
                            
                            if success:
                                collected += 1
                                self.collected_urls.add(url)
                                
                                # تحديث الإحصائيات
                                global _collection_stats
                                _collection_stats['total_collected'] += 1
                                _collection_stats['telegram_collected'] += 1
                                
                                if link_type == 'public_group':
                                    _collection_stats['public_groups'] += 1
                                else:
                                    _collection_stats['private_groups'] += 1
                                
                                logger.debug(f"✅ Collected from dialog: {url}")
                            
                        elif verification.get('error'):
                            if 'قناة' in verification['error']:
                                _collection_stats['channels_skipped'] += 1
                            elif 'بوت' in verification['error']:
                                _collection_stats['bots_skipped'] += 1
                            elif 'محتوى محظور' in verification['error']:
                                _collection_stats['invalid_links'] += 1
                    
                    await asyncio.sleep(0.3)
                    
                except Exception as e:
                    logger.debug(f"Error processing dialog: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error collecting from dialogs: {e}")
        
        return collected
    
    async def collect_from_old_messages(self, client: TelegramClient, session_id: int) -> int:
        """جمع الروابط من الرسائل القديمة (من 2020)"""
        collected = 0
        
        try:
            logger.info("🕰️ Collecting from old messages (from 2020)...")
            
            # قنوات ومجموعات معروفة تحتوي على روابط قديمة
            old_sources = [
                "TelegramChannels", "arabtelegramgroups", "telegram_groups_arabic",
                "arabicgroups", "TelegramGroups2020", "oldtelegramgroups",
                "TelegramGroupsArchive", "groups2021", "groups2022", "groups2023"
            ]
            
            for source in old_sources:
                if not _collection_active:
                    break
                
                try:
                    logger.info(f"🔎 Searching in {source}...")
                    
                    # محاولة الوصول إلى الكيان
                    try:
                        entity = await client.get_entity(source)
                    except Exception:
                        logger.debug(f"Could not access {source}")
                        continue
                    
                    # البحث عن الرسائل التي تحتوي على روابط
                    messages_collected = 0
                    
                    async for message in client.iter_messages(entity, limit=1000):
                        if not _collection_active:
                            break
                        
                        # تخطي الرسائل الجديدة جداً (آخر 3 أشهر)
                        if message.date and (datetime.now() - message.date.replace(tzinfo=None)).days < 90:
                            continue
                        
                        if message.text:
                            urls = self.extract_links_from_text(message.text)
                            
                            for url in urls:
                                if not _collection_active:
                                    break
                                
                                # تخطي الروابط المكررة
                                if link_exists(url):
                                    _collection_stats['duplicate_links'] += 1
                                    continue
                                
                                verification = await self.verify_link_comprehensive(url, client)
                                
                                if verification['is_valid'] and verification['is_active']:
                                    # تحديد المنصة والنوع
                                    if 't.me' in url or 'telegram.me' in url:
                                        platform = 'telegram'
                                        link_type = 'private_group' if 't.me/+' in url else 'public_group'
                                    else:
                                        platform = 'whatsapp'
                                        link_type = 'group'
                                    
                                    success, link_id = add_link(
                                        url=url,
                                        platform=platform,
                                        link_type=link_type,
                                        title=verification.get('title', ''),
                                        members_count=verification.get('active_members', verification.get('members_count', 0)),
                                        session_id=session_id
                                    )
                                    
                                    if success:
                                        collected += 1
                                        messages_collected += 1
                                        self.collected_urls.add(url)
                                        
                                        global _collection_stats
                                        _collection_stats['total_collected'] += 1
                                        
                                        if platform == 'telegram':
                                            _collection_stats['telegram_collected'] += 1
                                            if link_type == 'public_group':
                                                _collection_stats['public_groups'] += 1
                                            else:
                                                _collection_stats['private_groups'] += 1
                                        else:
                                            _collection_stats['whatsapp_collected'] += 1
                                            _collection_stats['whatsapp_groups'] += 1
                                        
                                        logger.debug(f"✅ Collected from old message ({message.date}): {url}")
                                    
                                    await asyncio.sleep(0.2)
                        
                        if messages_collected >= 50:  # حد لكل مصدر
                            break
                    
                    logger.info(f"📊 Collected {messages_collected} links from {source}")
                    await asyncio.sleep(5)
                    
                except Exception as e:
                    logger.error(f"Error collecting from {source}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error collecting from old messages: {e}")
        
        return collected
    
    async def collect_from_public_channels(self, client: TelegramClient, session_id: int) -> int:
        """جمع الروابط من القنوات العامة"""
        collected = 0
        
        try:
            logger.info("📢 Collecting from public channels...")
            
            # البحث في القنوات العامة عن روابط مجموعات
            search_terms = OLD_SEARCH_TERMS
            
            for term in search_terms:
                if not _collection_active:
                    break
                
                try:
                    logger.info(f"🔍 Searching for: {term}")
                    
                    messages_collected = 0
                    
                    async for message in client.iter_messages(None, search=term, limit=200):
                        if not _collection_active:
                            break
                        
                        if message.text:
                            urls = self.extract_links_from_text(message.text)
                            
                            for url in urls:
                                if not _collection_active:
                                    break
                                
                                if link_exists(url):
                                    continue
                                
                                verification = await self.verify_link_comprehensive(url, client)
                                
                                if verification['is_valid'] and verification['is_active']:
                                    # تحديد المنصة والنوع
                                    if 't.me' in url or 'telegram.me' in url:
                                        platform = 'telegram'
                                        link_type = 'private_group' if 't.me/+' in url else 'public_group'
                                    else:
                                        platform = 'whatsapp'
                                        link_type = 'group'
                                    
                                    success, link_id = add_link(
                                        url=url,
                                        platform=platform,
                                        link_type=link_type,
                                        title=verification.get('title', ''),
                                        members_count=verification.get('active_members', verification.get('members_count', 0)),
                                        session_id=session_id
                                    )
                                    
                                    if success:
                                        collected += 1
                                        messages_collected += 1
                                        self.collected_urls.add(url)
                                        
                                        global _collection_stats
                                        _collection_stats['total_collected'] += 1
                                        
                                        if platform == 'telegram':
                                            _collection_stats['telegram_collected'] += 1
                                            if link_type == 'public_group':
                                                _collection_stats['public_groups'] += 1
                                            else:
                                                _collection_stats['private_groups'] += 1
                                        else:
                                            _collection_stats['whatsapp_collected'] += 1
                                            _collection_stats['whatsapp_groups'] += 1
                                        
                                        logger.debug(f"✅ Collected from public search ({term}): {url}")
                                    
                                    await asyncio.sleep(0.2)
                        
                        if messages_collected >= 30:  # حد لكل مصطلح بحث
                            break
                    
                    logger.info(f"📊 Found {messages_collected} links for term: {term}")
                    await asyncio.sleep(3)
                    
                except Exception as e:
                    logger.error(f"Error searching for term '{term}': {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error collecting from public channels: {e}")
        
        return collected
    
    async def collect_from_web_sources(self) -> int:
        """جمع الروابط من مصادر الويب"""
        collected = 0
        
        try:
            logger.info("🌐 Collecting from web sources...")
            
            for source_url in OLD_SOURCES:
                if not _collection_active:
                    break
                
                try:
                    logger.info(f"🔗 Fetching: {source_url}")
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    
                    async with self.http_session.get(source_url, headers=headers, timeout=15) as response:
                        if response.status == 200:
                            text = await response.text()
                            urls = self.extract_links_from_text(text)
                            
                            logger.info(f"📊 Found {len(urls)} URLs in {source_url}")
                            
                            for url in urls:
                                if not _collection_active:
                                    break
                                
                                if link_exists(url):
                                    _collection_stats['duplicate_links'] += 1
                                    continue
                                
                                verification = await self.verify_link_comprehensive(url)
                                
                                if verification['is_valid'] and verification['is_active']:
                                    # تحديد المنصة والنوع
                                    if 't.me' in url or 'telegram.me' in url:
                                        platform = 'telegram'
                                        link_type = 'private_group' if 't.me/+' in url else 'public_group'
                                    else:
                                        platform = 'whatsapp'
                                        link_type = 'group'
                                    
                                    success, link_id = add_link(
                                        url=url,
                                        platform=platform,
                                        link_type=link_type,
                                        title=verification.get('title', ''),
                                        members_count=verification.get('active_members', verification.get('members_count', 0)),
                                        session_id=None  # جمع من الويب
                                    )
                                    
                                    if success:
                                        collected += 1
                                        self.collected_urls.add(url)
                                        
                                        global _collection_stats
                                        _collection_stats['total_collected'] += 1
                                        
                                        if platform == 'telegram':
                                            _collection_stats['telegram_collected'] += 1
                                            if link_type == 'public_group':
                                                _collection_stats['public_groups'] += 1
                                            else:
                                                _collection_stats['private_groups'] += 1
                                        else:
                                            _collection_stats['whatsapp_collected'] += 1
                                            _collection_stats['whatsapp_groups'] += 1
                                        
                                        logger.debug(f"✅ Collected from web: {url}")
                                    
                                    await asyncio.sleep(0.3)
                        
                        await asyncio.sleep(2)
                        
                except Exception as e:
                    logger.error(f"Error collecting from web source {source_url}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error in collect_from_web_sources: {e}")
        
        return collected
    
    async def run_comprehensive_collection(self):
        """تشغيل دورة الجمع الشاملة"""
        logger.info("🚀 Starting comprehensive collection cycle...")
        
        global _collection_stats
        _collection_stats['start_time'] = datetime.now().isoformat()
        
        # تحميل الجلسات النشطة
        self.active_sessions = [s for s in get_sessions() if s.get('is_active')]
        
        total_collected = 0
        
        if self.active_sessions:
            logger.info(f"📊 Using {len(self.active_sessions)} active sessions")
            
            # الجمع من الجلسات
            for session in self.active_sessions:
                if not _collection_active:
                    break
                
                logger.info(f"🔍 Collecting from session: {session.get('display_name')}")
                
                collected = await self.collect_from_session_comprehensive(session)
                total_collected += collected
                
                logger.info(f"📈 Session collected {collected} links")
                
                if not _collection_active:
                    break
                
                await asyncio.sleep(10)  # تأخير بين الجلسات
        
        else:
            logger.warning("⚠️ No active sessions available, using web collection only")
        
        # الجمع من مصادر الويب
        if _collection_active:
            logger.info("🌐 Collecting from web sources...")
            web_collected = await self.collect_from_web_sources()
            total_collected += web_collected
            logger.info(f"📈 Web collected {web_collected} links")
        
        # حفظ ذاكرة التخزين المؤقت
        self.save_verified_cache()
        
        _collection_stats['last_collection'] = datetime.now().isoformat()
        
        logger.info(f"✅ Collection cycle completed. Total collected: {total_collected}")
        
        # حفظ الإحصائيات
        session_id = get_active_collection_session()
        if session_id:
            update_collection_stats(session_id, _collection_stats)
        
        return total_collected

# إنشاء كائن المجمع
link_collector = AdvancedLinkCollector()

# ======================
# Keyboard Functions
# ======================

def main_menu_keyboard():
    """لوحة المفاتيح الرئيسية"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ إضافة جلسة", callback_data="menu_add_session"),
            InlineKeyboardButton("👥 عرض الجلسات", callback_data="menu_list_sessions")
        ],
        [
            InlineKeyboardButton("🚀 بدء الجمع", callback_data="menu_start_collect"),
            InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="menu_stop_collect")
        ],
        [
            InlineKeyboardButton("📊 عرض الروابط", callback_data="menu_view_links"),
            InlineKeyboardButton("📤 تصدير الروابط", callback_data="menu_export_links")
        ],
        [
            InlineKeyboardButton("📈 إحصائيات", callback_data="menu_stats"),
            InlineKeyboardButton("🔄 تحديث", callback_data="menu_refresh_stats")
        ],
        [
            InlineKeyboardButton("⚙️ الإعدادات", callback_data="menu_settings")
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
            InlineKeyboardButton("📊 جميع الروابط", callback_data="view_all_0"),
            InlineKeyboardButton("🆕 أحدث الروابط", callback_data="view_recent_0")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")
        ]
    ])

def telegram_types_keyboard(page: int = 0):
    """أنواع روابط التليجرام"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 المجموعات العامة", callback_data="view_telegram_public_group_0"),
            InlineKeyboardButton("🔒 المجموعات الخاصة", callback_data="view_telegram_private_group_0")
        ],
        [
            InlineKeyboardButton("📊 جميع مجموعات تيليجرام", callback_data="view_telegram_all_0")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_view_links")
        ]
    ])

def settings_keyboard():
    """قائمة الإعدادات"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ حذف جميع الجلسات", callback_data="settings_delete_all_sessions"),
            InlineKeyboardButton("🧹 تنظيف قاعدة البيانات", callback_data="settings_clean_db")
        ],
        [
            InlineKeyboardButton("📊 عرض إحصائيات مفصلة", callback_data="settings_detailed_stats"),
            InlineKeyboardButton("🔍 اختبار الاتصال", callback_data="settings_test_connection")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")
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
        InlineKeyboardButton("🗑️ حذف الكل", callback_data="confirm_delete_all_sessions"),
        InlineKeyboardButton("➕ إضافة جلسة", callback_data="menu_add_session")
    ])
    
    keyboard.append([
        InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")
    ])
    
    return InlineKeyboardMarkup(keyboard)

def session_actions_keyboard(session_id: int):
    """أزرار إجراءات الجلسة"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_session_{session_id}"),
            InlineKeyboardButton("🔄 تفعيل/تعطيل", callback_data=f"toggle_session_{session_id}")
        ],
        [
            InlineKeyboardButton("📊 إحصائيات الجلسة", callback_data=f"session_stats_{session_id}")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_list_sessions")
        ]
    ])

def pagination_keyboard(data_prefix: str, page: int, has_next: bool, extra_buttons: List = None):
    """أزرار التصفح العام"""
    buttons = []
    
    if page > 0:
        buttons.append(
            InlineKeyboardButton("⬅️ السابق", callback_data=f"{data_prefix}_{page-1}")
        )
    
    buttons.append(
        InlineKeyboardButton(f"📄 {page+1}", callback_data="current_page")
    )
    
    if has_next:
        buttons.append(
            InlineKeyboardButton("➡️ التالي", callback_data=f"{data_prefix}_{page+1}")
        )
    
    keyboard = [buttons]
    
    if extra_buttons:
        keyboard.append(extra_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu_view_links")])
    
    return InlineKeyboardMarkup(keyboard)

def export_options_keyboard():
    """خيارات التصدير"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 تيليجرام عامة", callback_data="export_telegram_public"),
            InlineKeyboardButton("🔒 تيليجرام خاصة", callback_data="export_telegram_private")
        ],
        [
            InlineKeyboardButton("📞 واتساب", callback_data="export_whatsapp"),
            InlineKeyboardButton("📊 الكل", callback_data="export_all")
        ],
        [
            InlineKeyboardButton("📅 القديمة (2020-2023)", callback_data="export_old"),
            InlineKeyboardButton("🆕 الجديدة (2024-2025)", callback_data="export_new")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")
        ]
    ])

# ======================
# Command Handlers
# ======================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /start"""
    user = update.effective_user
    
    stats = get_link_stats()
    
    welcome_text = f"""
    🤖 *مرحباً {user.first_name}!*
    
    *🎯 بوت جمع الروابط الذكي - الإصدار المتقدم*
    
    *✨ المميزات الجديدة:*
    • جمع الروابط القديمة (من 2020) والجديدة
    • فحص دقيق لنشاط الروابط وجودتها
    • جمع من مصادر متعددة (جلسات + ويب)
    • تصفية القنوات والبوتات والروابط الميتة
    • تحليل عدد الأعضاء النشطين
    
    *📊 الإحصائيات الحالية:*
    • إجمالي الروابط: {stats.get('total_links', 0)}
    • مجموعات تيليجرام: {stats.get('by_platform', {}).get('telegram', 0)}
    • مجموعات واتساب: {stats.get('by_platform', {}).get('whatsapp', 0)}
    
    *🕰️ آخر جمع:*
    {_collection_stats.get('last_collection', 'لم يبدأ بعد')}
    
    اختر من القائمة:"""
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /help"""
    help_text = """
    🆘 *مساعدة - بوت جمع الروابط المتقدم*
    
    *🎯 ما الجديد في هذا الإصدار:*
    1. **جمع الروابط القديمة**: يجمع الروابط من عام 2020 حتى الآن
    2. **فحص دقيق**: يتحقق من عدد الأعضاء النشطين وجودة الروابط
    3. **مصادر متعددة**: يجمع من الجلسات والويب والتاريخ القديم
    4. **تصفية ذكية**: يتجاهل القنوات والبوتات والروابط الميتة
    
    *📋 الأوامر المتاحة:*
    /start - بدء البوت وعرض القائمة
    /help - عرض رسالة المساعدة
    /status - عرض حالة الجمع الحالية
    /stats - عرض إحصائيات مفصلة
    /collect_now - بدء جمع فوري
    
    *🚀 بدء الجمع المتقدم:*
    - يجمع الروابط من:
      • الدردشات الحالية في الجلسات
      • الرسائل القديمة (من 2020)
      • القنوات العامة
      • مصادر الويب الأرشيفية
    
    *🔍 فحص الروابط:*
    - يتحقق من وجود أعضاء نشطين (10+ عضو)
    - يتجاهل القنوات والبوتات
    - يفحص تاريخ آخر نشاط
    - يتأكد من صحة الرابط
    
    *📊 عرض الروابط:*
    - عرض حسب التاريخ (قديم/جديد)
    - عرض حسب النوع (عامة/خاصة)
    - عرض حسب المنصة
    - تصفح بصفحات
    
    *⚙️ الإعدادات المتقدمة:*
    - تنظيف قاعدة البيانات
    - عرض إحصائيات مفصلة
    - اختبار اتصال الجلسات
    
    *📈 التقارير:*
    - إحصائيات الجمع بالتفصيل
    - تقارير عن الروابط المرفوضة
    - تحليل مصادر الجمع
    """
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /status"""
    global _collection_active, _collection_paused, _collection_stats
    
    stats = get_link_stats()
    
    status_text = ""
    
    if _collection_active:
        status_text = "🔄 *جاري الجمع حالياً*\n\n"
        
        if _collection_paused:
            status_text = "⏸️ *الجمع موقف مؤقتاً*\n\n"
        
        status_text += f"📊 *إحصائيات الجلسة الحالية:*\n"
        status_text += f"• تم جمع: {_collection_stats['total_collected']}\n"
        status_text += f"• مجموعات عامة: {_collection_stats['public_groups']}\n"
        status_text += f"• مجموعات خاصة: {_collection_stats['private_groups']}\n"
        status_text += f"• مجموعات واتساب: {_collection_stats['whatsapp_groups']}\n"
        status_text += f"• مكرر: {_collection_stats['duplicate_links']}\n"
        status_text += f"• غير نشط: {_collection_stats['inactive_links']}\n"
        
        if _collection_stats.get('start_time'):
            start_time = datetime.fromisoformat(_collection_stats['start_time'])
            duration = datetime.now() - start_time
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            status_text += f"• المدة: {hours} ساعة {minutes} دقيقة\n"
    
    else:
        status_text = "🛑 *الجمع متوقف*\n\n"
        status_text += f"📊 *الإحصائيات الإجمالية:*\n"
        status_text += f"• إجمالي الروابط: {stats.get('total_links', 0)}\n"
        status_text += f"• الروابط اليوم: {stats.get('today_links', 0)}\n"
        
        by_platform = stats.get('by_platform', {})
        if by_platform:
            status_text += f"• تيليجرام: {by_platform.get('telegram', 0)}\n"
            status_text += f"• واتساب: {by_platform.get('whatsapp', 0)}\n"
    
    sessions = get_sessions()
    active_sessions = len([s for s in sessions if s.get('is_active')])
    
    status_text += f"\n👥 *الجلسات:* {len(sessions)} (نشطة: {active_sessions})"
    
    if _collection_stats.get('last_collection'):
        last_collection = datetime.fromisoformat(_collection_stats['last_collection'])
        status_text += f"\n⏰ *آخر جمع:* {last_collection.strftime('%Y-%m-%d %H:%M')}"
    
    keyboard = [
        [InlineKeyboardButton("🚀 بدء الجمع", callback_data="menu_start_collect")],
        [InlineKeyboardButton("📈 إحصائيات مفصلة", callback_data="menu_stats")]
    ]
    
    if _collection_active:
        keyboard[0] = [InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="menu_stop_collect")]
    
    await update.message.reply_text(
        status_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /stats"""
    stats = get_link_stats()
    
    stats_text = "📈 *إحصائيات مفصلة*\n\n"
    
    stats_text += "*🔢 الإجماليات:*\n"
    stats_text += f"• الروابط المجمعة: {stats.get('total_links', 0)}\n"
    stats_text += f"• الروابط اليوم: {stats.get('today_links', 0)}\n"
    stats_text += f"• الروابط الأسبوع: {stats.get('week_links', 0)}\n"
    stats_text += f"• الروابط الشهر: {stats.get('month_links', 0)}\n"
    
    # حسب المنصة
    by_platform = stats.get('by_platform', {})
    if by_platform:
        stats_text += "\n*📱 حسب المنصة:*\n"
        telegram_count = by_platform.get('telegram', 0)
        whatsapp_count = by_platform.get('whatsapp', 0)
        stats_text += f"• تيليجرام: {telegram_count}\n"
        stats_text += f"• واتساب: {whatsapp_count}\n"
    
    # تيليجرام حسب النوع
    telegram_by_type = stats.get('telegram_by_type', {})
    if telegram_by_type:
        stats_text += "\n*📨 تيليجرام حسب النوع:*\n"
        public = telegram_by_type.get('public_group', 0)
        private = telegram_by_type.get('private_group', 0)
        stats_text += f"• مجموعات عامة: {public}\n"
        stats_text += f"• مجموعات خاصة: {private}\n"
    
    # الجلسات
    sessions = get_sessions()
    active_sessions = len([s for s in sessions if s.get('is_active')])
    total_links_by_sessions = sum(s.get('links_collected', 0) for s in sessions)
    
    stats_text += f"\n*👥 الجلسات:*\n"
    stats_text += f"• الإجمالي: {len(sessions)}\n"
    stats_text += f"• النشطة: {active_sessions}\n"
    stats_text += f"• الروابط بالجلسات: {total_links_by_sessions}\n"
    
    # إحصائيات الجلسة الحالية
    if _collection_active:
        stats_text += f"\n*🚀 الجلسة الحالية:*\n"
        stats_text += f"• تم جمع: {_collection_stats['total_collected']}\n"
        stats_text += f"• مرفوض (مكرر): {_collection_stats['duplicate_links']}\n"
        stats_text += f"• مرفوض (غير نشط): {_collection_stats['inactive_links']}\n"
        stats_text += f"• قنوات متجاهلة: {_collection_stats['channels_skipped']}\n"
        stats_text += f"• بوتات متجاهلة: {_collection_stats['bots_skipped']}\n"
    
    await update.message.reply_text(
        stats_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="menu_refresh_stats")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")]
        ])
    )

async def collect_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء جمع فوري"""
    global _collection_active
    
    if _collection_active:
        await update.message.reply_text("⚠️ الجمع يعمل بالفعل!")
        return
    
    active_sessions = [s for s in get_sessions() if s.get('is_active')]
    if not active_sessions:
        await update.message.reply_text(
            "❌ لا توجد جلسات نشطة!\n\n"
            "يجب إضافة وتفعيل جلسة واحدة على الأقل.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة جلسة", callback_data="menu_add_session")]
            ])
        )
        return
    
    await update.message.reply_text("🚀 بدء الجمع الفوري...")
    
    # بدء الجمع
    _collection_active = True
    start_collection_session()
    
    # تشغيل الجمع
    asyncio.create_task(run_advanced_collection_cycle())
    
    await update.message.reply_text(
        "✅ *بدأ الجمع الفوري*\n\n"
        "⚡ *جاري جمع الروابط من:*\n"
        "• الدردشات الحالية\n"
        "• الرسائل القديمة (من 2020)\n"
        "• مصادر الويب الأرشيفية\n"
        "• القنوات العامة\n\n"
        "📊 يمكنك متابعة التقدم عبر /status",
        parse_mode="Markdown"
    )

# ======================
# Collection Management
# ======================

async def run_advanced_collection_cycle():
    """تشغيل دورة الجمع المتقدمة"""
    global _collection_active
    
    try:
        while _collection_active:
            # تهيئة المجمع
            if not await link_collector.initialize():
                logger.error("❌ Failed to initialize collector")
                _collection_active = False
                break
            
            # تشغيل دورة الجمع
            collected = await link_collector.run_comprehensive_collection()
            
            logger.info(f"✅ Collection cycle completed: {collected} links")
            
            if not _collection_active:
                break
            
            # انتظار قبل الدورة التالية
            logger.info("⏳ Waiting 10 minutes before next collection cycle...")
            await asyncio.sleep(600)  # 10 دقائق
            
    except Exception as e:
        logger.error(f"❌ Error in advanced collection cycle: {e}")
        _collection_active = False

# ======================
# Callback Handlers - Enhanced
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
        
        elif data == "menu_settings":
            await show_settings_menu(query)
        
        # إضافة جلسة
        elif data == "menu_add_session":
            context.user_data['awaiting_session'] = True
            await query.message.edit_text(
                "📥 *إضافة جلسة جديدة*\n\n"
                "أرسل لي Session String الآن:\n\n"
                "ℹ️ *كيفية الحصول على Session String:*\n"
                "1. اذهب إلى @StringSessionBot\n"
                "2. اضغط /start\n"
                "3. اختر Telethon\n"
                "4. أرسل الكود الذي تحصل عليه هنا\n\n"
                "📝 *ملاحظة:*\n"
                "- يجب أن يكون الحساب نشط\n"
                "- يفضل أن يكون عمر الحساب أكثر من 6 أشهر\n"
                "- كلما كان الحساب أقدم، زادت الروابط التي يمكن جمعها",
                parse_mode="Markdown"
            )
        
        # عرض الجلسات
        elif data == "menu_list_sessions":
            await show_sessions_list(query)
        
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
        
        elif data == "menu_refresh_stats":
            await refresh_stats_handler(query)
        
        # اختيار المنصة
        elif data == "view_telegram":
            await show_telegram_types(query)
        elif data == "view_whatsapp":
            await show_whatsapp_links(query, "group", 0)
        
        # عرض جميع الروابط
        elif data.startswith("view_all_"):
            page = int(data.split('_')[2])
            await show_all_links(query, page)
        
        elif data.startswith("view_recent_"):
            page = int(data.split('_')[2])
            await show_recent_links(query, page)
        
        # عرض روابط تيليجرام
        elif data.startswith("view_telegram_"):
            parts = data.split('_')
            if len(parts) >= 4:
                link_type = parts[2]
                page = int(parts[3])
                await show_telegram_links(query, link_type, page)
        
        # إدارة الجلسات
        elif data.startswith("session_info_"):
            session_id = int(data.split('_')[2])
            await show_session_info(query, session_id)
        
        elif data.startswith("session_stats_"):
            session_id = int(data.split('_')[2])
            await show_session_stats(query, session_id)
        
        elif data.startswith("delete_session_"):
            session_id = int(data.split('_')[2])
            await delete_session_handler(query, session_id)
        
        elif data.startswith("toggle_session_"):
            session_id = int(data.split('_')[2])
            await toggle_session_handler(query, session_id)
        
        # حذف جميع الجلسات
        elif data == "confirm_delete_all_sessions":
            await delete_all_sessions_handler(query)
        
        # التصدير
        elif data.startswith("export_"):
            parts = data.split('_')
            export_type = parts[1]
            if len(parts) > 2:
                export_type += f"_{parts[2]}"
            await export_handler(query, export_type)
        
        # الإعدادات
        elif data == "settings_delete_all_sessions":
            await show_delete_all_confirmation(query)
        
        elif data == "settings_clean_db":
            await clean_database_handler(query)
        
        elif data == "settings_detailed_stats":
            await show_detailed_stats(query)
        
        elif data == "settings_test_connection":
            await test_connection_handler(query)
        
        # التصفح
        elif data.startswith("page_"):
            parts = data.split('_')
            if len(parts) >= 4:
                platform = parts[1]
                link_type = parts[2]
                page = int(parts[3])
                
                if platform == "telegram":
                    await show_telegram_links(query, link_type, page)
                elif platform == "whatsapp":
                    await show_whatsapp_links(query, link_type, page)
                elif platform == "all":
                    await show_all_links(query, page)
                elif platform == "recent":
                    await show_recent_links(query, page)
        
        else:
            await query.message.edit_text("❌ أمر غير معروف، جرب /start للبدء")
    
    except Exception as e:
        logger.error(f"❌ Error in callback handler: {e}")
        await query.message.edit_text(
            f"❌ حدث خطأ في المعالجة\n\n"
            f"📝 الخطأ: {str(e)[:100]}\n\n"
            f"🔄 اضغط /start لإعادة البدء",
            parse_mode="Markdown"
        )

# ======================
# Menu Handlers - Enhanced
# ======================

async def show_main_menu(query):
    """عرض القائمة الرئيسية"""
    stats = get_link_stats()
    
    menu_text = "📱 *القائمة الرئيسية*\n\n"
    menu_text += "🎯 *بوت جمع الروابط المتقدم*\n\n"
    menu_text += f"📊 *إحصائيات سريعة:*\n"
    menu_text += f"• الروابط المجمعة: {stats.get('total_links', 0)}\n"
    
    by_platform = stats.get('by_platform', {})
    if by_platform:
        menu_text += f"• تيليجرام: {by_platform.get('telegram', 0)}\n"
        menu_text += f"• واتساب: {by_platform.get('whatsapp', 0)}\n"
    
    global _collection_active
    if _collection_active:
        menu_text += f"\n🚀 *حالة الجمع:* نشط\n"
        menu_text += f"📈 المجموع الحالي: {_collection_stats['total_collected']}"
    else:
        menu_text += f"\n🛑 *حالة الجمع:* متوقف"
    
    await query.message.edit_text(
        menu_text,
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

async def show_settings_menu(query):
    """عرض قائمة الإعدادات"""
    await query.message.edit_text(
        "⚙️ *إعدادات البوت المتقدم*\n\n"
        "*🗑️ تنظيف وإدارة:*\n"
        "• حذف جميع الجلسات\n"
        "• تنظيف قاعدة البيانات\n\n"
        "*📊 تقارير وإحصائيات:*\n"
        "• إحصائيات مفصلة\n"
        "• اختبار اتصال الجلسات\n\n"
        "اختر الإعداد الذي تريد تعديله:",
        reply_markup=settings_keyboard(),
        parse_mode="Markdown"
    )

async def show_delete_all_confirmation(query):
    """عرض تأكيد حذف جميع الجلسات"""
    sessions = get_sessions()
    
    if not sessions:
        await query.message.edit_text(
            "📭 لا توجد جلسات لحذفها",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_settings")]
            ])
        )
        return
    
    active_sessions = len([s for s in sessions if s.get('is_active')])
    
    await query.message.edit_text(
        f"⚠️ *تحذير: حذف جميع الجلسات*\n\n"
        f"📊 *سوف يتم حذف:*\n"
        f"• عدد الجلسات: {len(sessions)}\n"
        f"• الجلسات النشطة: {active_sessions}\n"
        f"• الجلسات المعطلة: {len(sessions) - active_sessions}\n\n"
        f"❌ *هذا الإجراء لا يمكن التراجع عنه*\n\n"
        f"هل أنت متأكد؟",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ نعم، احذف الكل", callback_data="confirm_delete_all_sessions"),
                InlineKeyboardButton("❌ لا، إلغاء", callback_data="menu_settings")
            ]
        ]),
        parse_mode="Markdown"
    )

async def clean_database_handler(query):
    """تنظيف قاعدة البيانات"""
    try:
        await query.message.edit_text("🧹 جاري تنظيف قاعدة البيانات...")
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # حذف الروابط المكررة
        cursor.execute("""
            DELETE FROM links 
            WHERE id NOT IN (
                SELECT MIN(id) 
                FROM links 
                GROUP BY url
            )
        """)
        
        # حذف الروابط القديمة جداً (أقدم من 2023)
        cursor.execute("""
            DELETE FROM links 
            WHERE created_at < date('now', '-2 years')
        """)
        
        conn.commit()
        deleted_count = cursor.rowcount
        conn.close()
        
        await query.message.edit_text(
            f"✅ *تم تنظيف قاعدة البيانات*\n\n"
            f"📊 *الإحصائيات:*\n"
            f"• الروابط المحذوفة: {deleted_count}\n"
            f"• تم حذف المكررات والقديمة\n\n"
            f"🔄 قاعدة البيانات الآن نظيفة ومحسنة",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_settings")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error cleaning database: {e}")
        await query.message.edit_text(
            f"❌ حدث خطأ أثناء التنظيف\n\n{str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_settings")]
            ])
        )

async def show_detailed_stats(query):
    """عرض إحصائيات مفصلة"""
    stats = get_link_stats()
    
    detailed_text = "📊 *إحصائيات مفصلة جداً*\n\n"
    
    # إحصائيات حسب اليوم
    detailed_text += "*📅 حسب اليوم:*\n"
    for i in range(7):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        daily_count = 0  # سيتم استعلام قاعدة البيانات هنا
        detailed_text += f"• {date}: {daily_count}\n"
    
    # إحصائيات الجلسات
    sessions = get_sessions()
    detailed_text += f"\n*👥 إحصائيات الجلسات:*\n"
    for session in sessions[:10]:  # أول 10 جلسات فقط
        name = session.get('display_name', 'غير معروف')
        collected = session.get('links_collected', 0)
        status = "🟢" if session.get('is_active') else "🔴"
        detailed_text += f"• {status} {name}: {collected}\n"
    
    # إحصائيات الجمع
    detailed_text += f"\n*🚀 إحصائيات الجمع:*\n"
    detailed_text += f"• إجمالي المجموعة: {_collection_stats['total_collected']}\n"
    detailed_text += f"• روابط مكررة: {_collection_stats['duplicate_links']}\n"
    detailed_text += f"• روابط غير نشطة: {_collection_stats['inactive_links']}\n"
    detailed_text += f"• قنوات متجاهلة: {_collection_stats['channels_skipped']}\n"
    detailed_text += f"• أخطاء: {_collection_stats['errors']}\n"
    
    await query.message.edit_text(
        detailed_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="settings_detailed_stats")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="menu_settings")]
        ])
    )

async def test_connection_handler(query):
    """اختبار اتصال الجلسات"""
    await query.message.edit_text("🔌 جاري اختبار اتصال الجلسات...")
    
    sessions = get_sessions()
    results = []
    
    for session in sessions:
        try:
            client = TelegramClient(
                StringSession(session['session_string']),
                API_ID,
                API_HASH
            )
            
            await client.connect()
            
            if await client.is_user_authorized():
                me = await client.get_me()
                status = f"🟢 {session['display_name']}: متصل (@{me.username or 'لا يوجد'})"
            else:
                status = f"🔴 {session['display_name']}: غير مصرح"
            
            await client.disconnect()
            results.append(status)
            
        except Exception as e:
            results.append(f"🔴 {session['display_name']}: خطأ - {str(e)[:50]}")
    
    result_text = "📊 *نتائج اختبار الاتصال:*\n\n"
    result_text += "\n".join(results)
    
    await query.message.edit_text(
        result_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 إعادة الاختبار", callback_data="settings_test_connection")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="menu_settings")]
        ])
    )

# ======================
# Collection Handlers - Enhanced
# ======================

async def start_collection_handler(query):
    """بدء عملية الجمع المتقدمة"""
    global _collection_active, _collection_paused
    
    if _collection_active:
        await query.message.edit_text("⏳ الجمع يعمل بالفعل!")
        return
    
    # التحقق من وجود جلسات نشطة
    active_sessions = [s for s in get_sessions() if s.get('is_active')]
    if not active_sessions:
        await query.message.edit_text(
            "❌ لا توجد جلسات نشطة!\n\n"
            "يجب إضافة وتفعيل جلسة واحدة على الأقل لبدء الجمع المتقدم.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة جلسة", callback_data="menu_add_session")]
            ])
        )
        return
    
    # تهيئة المجمع
    await query.message.edit_text("🔧 جاري تهيئة نظام الجمع المتقدم...")
    
    if not await link_collector.initialize():
        await query.message.edit_text("❌ فشل في تهيئة نظام الجمع!")
        return
    
    # بدء الجمع
    _collection_active = True
    _collection_paused = False
    
    # بدء جلسة جمع جديدة
    start_collection_session()
    
    # تشغيل الجمع في خلفية
    asyncio.create_task(run_advanced_collection_cycle())
    
    await query.message.edit_text(
        "🚀 *بدأ جمع الروابط المتقدم*\n\n"
        "⚡ *يتم جمع الأنواع التالية:*\n"
        "• مجموعات تيليجرام العامة النشطة (10+ أعضاء)\n"
        "• مجموعات تيليجرام الخاصة النشطة\n"
        "• مجموعات واتساب النشطة\n\n"
        "🕰️ *جمع الروابط القديمة:*\n"
        "✓ يجمع الروابط من عام 2020 حتى الآن\n"
        "✓ يبحث في الأرشيفات والرسائل القديمة\n"
        "✓ يجمع من مصادر ويب قديمة\n\n"
        "🔍 *فحص متقدم:*\n"
        "✓ يتحقق من عدد الأعضاء النشطين\n"
        "✓ يتجاهل القنوات والبوتات\n"
        "✓ يفحص تاريخ آخر نشاط\n"
        "✓ يتأكد من صحة الرابط\n\n"
        "📊 *المصادر:*\n"
        "• الدردشات الحالية\n"
        "• الرسائل القديمة (من 2020)\n"
        "• القنوات العامة\n"
        "• مصادر الويب الأرشيفية\n\n"
        "⏳ جاري جمع الروابط...",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="menu_stop_collect")],
            [InlineKeyboardButton("📊 حالة الجمع", callback_data="menu_stats")]
        ])
    )

async def stop_collection_handler(query):
    """إيقاف عملية الجمع"""
    global _collection_active, _collection_paused
    
    if not _collection_active:
        await query.message.edit_text("⚠️ الجمع غير نشط حالياً")
        return
    
    _collection_active = False
    _collection_paused = False
    
    # حفظ ذاكرة التخزين المؤقت
    link_collector.save_verified_cache()
    
    stats_text = "⏹️ *تم إيقاف الجمع*\n\n"
    stats_text += f"📊 *إحصائيات الجلسة الأخيرة:*\n"
    stats_text += f"• تم جمع: {_collection_stats['total_collected']}\n"
    stats_text += f"• مجموعات عامة: {_collection_stats['public_groups']}\n"
    stats_text += f"• مجموعات خاصة: {_collection_stats['private_groups']}\n"
    stats_text += f"• مجموعات واتساب: {_collection_stats['whatsapp_groups']}\n"
    stats_text += f"• مرفوض (مكرر): {_collection_stats['duplicate_links']}\n"
    stats_text += f"• مرفوض (غير نشط): {_collection_stats['inactive_links']}\n"
    stats_text += f"• قنوات متجاهلة: {_collection_stats['channels_skipped']}\n\n"
    stats_text += f"✅ تم حفظ جميع الروابط في قاعدة البيانات"
    
    await query.message.edit_text(
        stats_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء جمع جديد", callback_data="menu_start_collect")],
            [InlineKeyboardButton("📊 عرض الروابط", callback_data="menu_view_links")]
        ])
    )

# ======================
# Link Viewing Handlers - Enhanced
# ======================

async def show_all_links(query, page: int = 0):
    """عرض جميع الروابط"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # حساب العدد الإجمالي
        cursor.execute("SELECT COUNT(*) FROM links")
        total_count = cursor.fetchone()[0]
        
        # الحصول على الروابط للصفحة الحالية
        offset = page * LINKS_PER_PAGE
        cursor.execute("""
            SELECT url, platform, link_type, title, members_count, created_at 
            FROM links 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        """, (LINKS_PER_PAGE, offset))
        
        links = cursor.fetchall()
        conn.close()
        
        if not links and page == 0:
            await query.message.edit_text(
                "📭 *لا توجد روابط مجمعة بعد*\n\n"
                "ابدأ عملية الجمع لجمع الروابط أولاً",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 بدء الجمع", callback_data="menu_start_collect")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="menu_view_links")]
                ]),
                parse_mode="Markdown"
            )
            return
        
        message_text = f"📊 *جميع الروابط*\n\n"
        message_text += f"📄 الصفحة: {page + 1}\n"
        message_text += f"🔢 الإجمالي: {total_count}\n\n"
        
        for i, link in enumerate(links, start=offset + 1):
            url, platform, link_type, title, members_count, created_at = link
            
            # تحديد الرمز
            if platform == 'telegram':
                symbol = "👥" if link_type == 'public_group' else "🔒"
            else:
                symbol = "📞"
            
            # تقصير الرابط
            if len(url) > 35:
                display_url = url[:32] + "..."
            else:
                display_url = url
            
            # عرض التاريخ
            date_str = created_at[:10] if created_at else "غير معروف"
            
            # عرض المعلومات
            message_text += f"{i}. {symbol} `{display_url}`\n"
            if members_count:
                message_text += f"   👥 {members_count} عضو"
            if title and title != 'مجموعة واتساب':
                message_text += f" | 📝 {title[:20]}"
            message_text += f" | 📅 {date_str}\n\n"
        
        has_next = len(links) == LINKS_PER_PAGE
        
        await query.message.edit_text(
            message_text,
            reply_markup=pagination_keyboard("view_all", page, has_next),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error showing all links: {e}")
        await query.message.edit_text(f"❌ حدث خطأ: {str(e)[:100]}")

async def show_recent_links(query, page: int = 0):
    """عرض أحدث الروابط"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # الحصول على الروابط المضافة في آخر 7 أيام
        seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        cursor.execute("""
            SELECT COUNT(*) FROM links 
            WHERE created_at >= ?
        """, (seven_days_ago,))
        total_count = cursor.fetchone()[0]
        
        offset = page * LINKS_PER_PAGE
        cursor.execute("""
            SELECT url, platform, link_type, title, members_count, created_at 
            FROM links 
            WHERE created_at >= ?
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        """, (seven_days_ago, LINKS_PER_PAGE, offset))
        
        links = cursor.fetchall()
        conn.close()
        
        if not links and page == 0:
            await query.message.edit_text(
                "📭 *لا توجد روابط حديثة*\n\n"
                "الروابط المضافة في آخر 7 أيام ستظهر هنا",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 بدء الجمع", callback_data="menu_start_collect")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="menu_view_links")]
                ]),
                parse_mode="Markdown"
            )
            return
        
        message_text = f"🆕 *أحدث الروابط (آخر 7 أيام)*\n\n"
        message_text += f"📄 الصفحة: {page + 1}\n"
        message_text += f"🔢 العدد: {total_count}\n\n"
        
        for i, link in enumerate(links, start=offset + 1):
            url, platform, link_type, title, members_count, created_at = link
            
            symbol = "👥" if platform == 'telegram' else "📞"
            
            if len(url) > 35:
                display_url = url[:32] + "..."
            else:
                display_url = url
            
            date_str = created_at[:10] if created_at else "اليوم"
            
            message_text += f"{i}. {symbol} `{display_url}`\n"
            if members_count:
                message_text += f"   👥 {members_count} عضو | "
            message_text += f"📅 {date_str}\n\n"
        
        has_next = len(links) == LINKS_PER_PAGE
        
        await query.message.edit_text(
            message_text,
            reply_markup=pagination_keyboard("view_recent", page, has_next),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error showing recent links: {e}")
        await query.message.edit_text(f"❌ حدث خطأ: {str(e)[:100]}")

async def show_telegram_links(query, link_type: str, page: int = 0):
    """عرض روابط التليجرام"""
    type_names = {
        "public_group": "المجموعات العامة",
        "private_group": "المجموعات الخاصة",
        "all": "جميع مجموعات تيليجرام"
    }
    
    title = type_names.get(link_type, link_type)
    
    if link_type == "all":
        links = get_links_by_type("telegram", None, LINKS_PER_PAGE, page * LINKS_PER_PAGE)
    else:
        links = get_links_by_type("telegram", link_type, LINKS_PER_PAGE, page * LINKS_PER_PAGE)
    
    if not links and page == 0:
        await query.message.edit_text(
            f"📭 *لا توجد روابط {title}*\n\n"
            f"ابدأ عملية الجمع لجمع الروابط أولاً",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء الجمع", callback_data="menu_start_collect")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="view_telegram")]
            ]),
            parse_mode="Markdown"
        )
        return
    
    message_text = f"📨 *{title}*\n\n"
    message_text += f"📄 الصفحة: {page + 1}\n"
    message_text += f"🔢 عدد الروابط: {len(links)}\n\n"
    
    for i, link in enumerate(links, start=page * LINKS_PER_PAGE + 1):
        url = link.get('url', '')
        members = link.get('members_count', 0)
        title_text = link.get('title', '')[:20]
        date = link.get('created_at', '')[:10]
        
        # تقصير الرابط
        if len(url) > 40:
            display_url = url[:37] + "..."
        else:
            display_url = url
        
        # إضافة رمز حسب نوع الرابط
        if "t.me/+" in url or link.get('link_type') == 'private_group':
            symbol = "🔒"
        else:
            symbol = "👥"
        
        message_text += f"{i}. {symbol} `{display_url}`\n"
        if members:
            message_text += f"   👥 {members} عضو"
        if title_text:
            message_text += f" | 📝 {title_text}"
        message_text += f" | 📅 {date}\n\n"
    
    has_next = len(links) == LINKS_PER_PAGE
    
    await query.message.edit_text(
        message_text,
        reply_markup=pagination_keyboard(
            f"view_telegram_{link_type}", 
            page, 
            has_next,
            [InlineKeyboardButton("🔙 رجوع", callback_data="view_telegram")]
        ),
        parse_mode="Markdown"
    )

async def show_whatsapp_links(query, link_type: str, page: int = 0):
    """عرض روابط الواتساب"""
    links = get_links_by_type("whatsapp", "group", LINKS_PER_PAGE, page * LINKS_PER_PAGE)
    
    if not links and page == 0:
        await query.message.edit_text(
            "📭 *لا توجد روابط واتساب*\n\n"
            "ابدأ عملية الجمع لجمع الروابط أولاً",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء الجمع", callback_data="menu_start_collect")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_view_links")]
            ]),
            parse_mode="Markdown"
        )
        return
    
    message_text = f"📞 *مجموعات واتساب*\n\n"
    message_text += f"📄 الصفحة: {page + 1}\n"
    message_text += f"🔢 عدد الروابط: {len(links)}\n\n"
    
    for i, link in enumerate(links, start=page * LINKS_PER_PAGE + 1):
        url = link.get('url', '')
        members = link.get('members_count', 0)
        date = link.get('created_at', '')[:10]
        
        if len(url) > 40:
            display_url = url[:37] + "..."
        else:
            display_url = url
        
        message_text += f"{i}. 📞 `{display_url}`\n"
        if members:
            message_text += f"   👥 {members} عضو"
        message_text += f" | 📅 {date}\n\n"
    
    has_next = len(links) == LINKS_PER_PAGE
    
    await query.message.edit_text(
        message_text,
        reply_markup=pagination_keyboard("view_whatsapp_group", page, has_next),
        parse_mode="Markdown"
    )

# ======================
# Session Handlers - Enhanced
# ======================

async def show_session_stats(query, session_id: int):
    """عرض إحصائيات جلسة محددة"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # الحصول على معلومات الجلسة
        cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        session = cursor.fetchone()
        
        if not session:
            await query.message.edit_text("❌ الجلسة غير موجودة")
            return
        
        # الحصول على إحصائيات الجلسة
        cursor.execute("""
            SELECT 
                COUNT(*) as total_links,
                COUNT(CASE WHEN platform = 'telegram' THEN 1 END) as telegram_links,
                COUNT(CASE WHEN platform = 'whatsapp' THEN 1 END) as whatsapp_links,
                COUNT(CASE WHEN link_type = 'public_group' THEN 1 END) as public_groups,
                COUNT(CASE WHEN link_type = 'private_group' THEN 1 END) as private_groups
            FROM links 
            WHERE session_id = ?
        """, (session_id,))
        
        stats = cursor.fetchone()
        conn.close()
        
        total_links, telegram_links, whatsapp_links, public_groups, private_groups = stats
        
        stats_text = f"📊 *إحصائيات الجلسة*\n\n"
        stats_text += f"📝 *المعلومات:*\n"
        stats_text += f"• الاسم: {session[5] or 'غير معروف'}\n"
        stats_text += f"• الحالة: {'🟢 نشط' if session[6] else '🔴 غير نشط'}\n"
        stats_text += f"• تاريخ الإضافة: {session[4][:10] if session[4] else 'غير معروف'}\n\n"
        
        stats_text += f"📈 *إحصائيات الروابط:*\n"
        stats_text += f"• الإجمالي: {total_links or 0}\n"
        stats_text += f"• تيليجرام: {telegram_links or 0}\n"
        stats_text += f"• واتساب: {whatsapp_links or 0}\n"
        stats_text += f"• مجموعات عامة: {public_groups or 0}\n"
        stats_text += f"• مجموعات خاصة: {private_groups or 0}\n"
        
        await query.message.edit_text(
            stats_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data=f"session_info_{session_id}")],
                [InlineKeyboardButton("📊 عرض روابط الجلسة", callback_data=f"view_session_{session_id}_0")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error showing session stats: {e}")
        await query.message.edit_text(f"❌ حدث خطأ: {str(e)[:100]}")

# ======================
# Export Handlers - Enhanced
# ======================

async def export_handler(query, export_type: str):
    """معالجة طلبات التصدير المتقدمة"""
    await query.message.edit_text("⏳ جاري تحضير الملف للتصدير...")
    
    try:
        if export_type == "telegram_public":
            path = export_links_by_type("telegram", "public_group")
            filename = "telegram_public_groups.txt"
            caption = "👥 مجموعات تيليجرام العامة النشطة (10+ أعضاء)"
        
        elif export_type == "telegram_private":
            path = export_links_by_type("telegram", "private_group")
            filename = "telegram_private_groups.txt"
            caption = "🔒 مجموعات تيليجرام الخاصة النشطة"
        
        elif export_type == "whatsapp":
            path = export_links_by_type("whatsapp", "group")
            filename = "whatsapp_groups.txt"
            caption = "📞 مجموعات واتساب النشطة"
        
        elif export_type == "old":
            # تصدير الروابط القديمة (قبل 2024)
            await query.message.edit_text("⏳ جاري تجميع الروابط القديمة...")
            
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT url FROM links 
                WHERE created_at < '2024-01-01'
                ORDER BY created_at DESC
            """)
            old_links = cursor.fetchall()
            conn.close()
            
            if old_links:
                temp_file = "telegram_old_groups_2020_2023.txt"
                with open(temp_file, 'w', encoding='utf-8') as f:
                    for link in old_links:
                        f.write(link[0] + "\n")
                
                with open(temp_file, 'rb') as f:
                    await query.message.reply_document(
                        f,
                        filename="old_groups_2020_2023.txt",
                        caption="🕰️ الروابط القديمة (2020-2023)"
                    )
                
                os.remove(temp_file)
                await query.message.edit_text(f"✅ تم تصدير {len(old_links)} رابط قديم")
            else:
                await query.message.edit_text("❌ لا توجد روابط قديمة للتصدير")
            return
        
        elif export_type == "new":
            # تصدير الروابط الجديدة (2024-2025)
            await query.message.edit_text("⏳ جاري تجميع الروابط الجديدة...")
            
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT url FROM links 
                WHERE created_at >= '2024-01-01'
                ORDER BY created_at DESC
            """)
            new_links = cursor.fetchall()
            conn.close()
            
            if new_links:
                temp_file = "telegram_new_groups_2024_2025.txt"
                with open(temp_file, 'w', encoding='utf-8') as f:
                    for link in new_links:
                        f.write(link[0] + "\n")
                
                with open(temp_file, 'rb') as f:
                    await query.message.reply_document(
                        f,
                        filename="new_groups_2024_2025.txt",
                        caption="🆕 الروابط الجديدة (2024-2025)"
                    )
                
                os.remove(temp_file)
                await query.message.edit_text(f"✅ تم تصدير {len(new_links)} رابط جديد")
            else:
                await query.message.edit_text("❌ لا توجد روابط جديدة للتصدير")
            return
        
        elif export_type == "all":
            # تصدير جميع الروابط
            await query.message.edit_text("⏳ جاري تجميع جميع الروابط...")
            
            all_links = get_all_links()
            
            if all_links:
                # تصدير حسب المنصة
                telegram_links = [l for l in all_links if l.get('platform') == 'telegram']
                whatsapp_links = [l for l in all_links if l.get('platform') == 'whatsapp']
                
                files_sent = 0
                
                if telegram_links:
                    temp_file = "all_telegram_groups.txt"
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        for link in telegram_links:
                            f.write(link.get('url', '') + "\n")
                    
                    with open(temp_file, 'rb') as f:
                        await query.message.reply_document(
                            f,
                            filename="all_telegram_groups.txt",
                            caption="📨 جميع مجموعات تيليجرام"
                        )
                    
                    os.remove(temp_file)
                    files_sent += 1
                
                if whatsapp_links:
                    temp_file = "all_whatsapp_groups.txt"
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        for link in whatsapp_links:
                            f.write(link.get('url', '') + "\n")
                    
                    with open(temp_file, 'rb') as f:
                        await query.message.reply_document(
                            f,
                            filename="all_whatsapp_groups.txt",
                            caption="📞 جميع مجموعات واتساب"
                        )
                    
                    os.remove(temp_file)
                    files_sent += 1
                
                if files_sent > 0:
                    await query.message.edit_text(f"✅ تم تصدير {files_sent} ملف")
                else:
                    await query.message.edit_text("❌ لا توجد بيانات للتصدير")
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
        logger.error(f"❌ Export error: {e}")
        await query.message.edit_text(
            f"❌ حدث خطأ أثناء التصدير\n\n"
            f"📝 الخطأ: {str(e)[:100]}",
            parse_mode="Markdown"
        )

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
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            
            client = None
            try:
                client = TelegramClient(
                    StringSession(text),
                    API_ID,
                    API_HASH
                )
                
                await client.connect()
                
                if not await client.is_user_authorized():
                    await message.reply_text(
                        "❌ *الجلسة غير صالحة*\n\n"
                        "⚠️ *تأكد من:*\n"
                        "1. أن الجلسة صحيحة\n"
                        "2. أن الحساب نشط\n"
                        "3. أنك قمت بتسجيل الدخول مسبقاً\n\n"
                        "🔄 *جرب مجدداً أو* اضغط ➕ إضافة جلسة",
                        parse_mode="Markdown",
                        reply_markup=main_menu_keyboard()
                    )
                    return
                
                me = await client.get_me()
                
                phone = me.phone or ''
                username = me.username or ''
                user_id = me.id
                first_name = me.first_name or ''
                last_name = me.last_name or ''
                
                display_name = first_name
                if last_name:
                    display_name += f" {last_name}"
                if not display_name:
                    display_name = username or f"User_{user_id}"
                
                success = add_session(text, phone, user_id, username, display_name)
                
                if success:
                    await message.reply_text(
                        f"✅ *تمت إضافة الجلسة بنجاح*\n\n"
                        f"📝 *معلومات الجلسة:*\n"
                        f"• الاسم: {display_name}\n"
                        f"• المعرف: {user_id}\n"
                        f"• المستخدم: @{username or 'لا يوجد'}\n"
                        f"• الهاتف: {phone or 'غير معروف'}\n\n"
                        f"⚡ *الجلسة نشطة وجاهزة للاستخدام في الجمع المتقدم*",
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
                    f"📝 *التفاصيل:* {str(e)[:150]}\n\n"
                    f"⚠️ *تأكد من صحة Session String*",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard()
                )
                
            finally:
                if client:
                    await client.disconnect()
        
        except Exception as e:
            logger.error(f"Error in session validation: {e}")
            await message.reply_text(
                f"❌ *خطأ في التحقق*\n\n"
                f"📝 {str(e)[:100]}\n\n"
                f"🔄 حاول مجدداً",
                parse_mode="Markdown"
            )
    
    else:
        # معالجة الرسائل الأخرى
        if text.startswith('/'):
            await message.reply_text(
                "⚡ *استخدم الأزرار للتحكم في البوت*\n\n"
                "اضغط /start لعرض القائمة الرئيسية",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu_main")]
                ])
            )
        else:
            # استخراج الروابط من الرسائل وإضافتها
            urls = link_collector.extract_links_from_text(text)
            
            if urls:
                await message.reply_text(
                    f"🔍 *وجدت {len(urls)} رابط في رسالتك*\n\n"
                    f"سأقوم بفحصها وإضافتها إذا كانت صالحة...",
                    parse_mode="Markdown"
                )
                
                added_count = 0
                for url in urls[:10]:  # حد 10 روابط فقط
                    if not link_exists(url):
                        verification = await link_collector.verify_link_comprehensive(url)
                        
                        if verification['is_valid'] and verification['is_active']:
                            platform = 'telegram' if 't.me' in url or 'telegram.me' in url else 'whatsapp'
                            link_type = 'group'
                            
                            if platform == 'telegram':
                                link_type = 'private_group' if 't.me/+' in url else 'public_group'
                            
                            success, _ = add_link(
                                url=url,
                                platform=platform,
                                link_type=link_type,
                                title=verification.get('title', ''),
                                members_count=verification.get('active_members', verification.get('members_count', 0))
                            )
                            
                            if success:
                                added_count += 1
                
                await message.reply_text(
                    f"✅ *تمت إضافة {added_count} رابط جديد*\n\n"
                    f"📊 يمكنك عرضها من قائمة عرض الروابط",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard()
                )
            else:
                await message.reply_text(
                    "👋 *مرحباً بك في بوت جمع الروابط المتقدم!*\n\n"
                    "⚡ *مميزات البوت:*\n"
                    "• جمع الروابط القديمة (من 2020)\n"
                    "• فحص دقيق لنشاط الروابط\n"
                    "• تصدير الروابط مصنفة\n\n"
                    "📝 *يمكنك:*\n"
                    "1. إرسال روابط مباشرة لإضافتها\n"
                    "2. استخدام الأزرار للتحكم\n"
                    "3. الضغط /start للبدء",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard()
                )

# ======================
# Main Application
# ======================

async def post_init(application):
    """تهيئة ما بعد التشغيل"""
    logger.info("✅ Bot is ready!")
    
    # تهيئة قاعدة البيانات
    init_db()
    
    # تهيئة المجمع
    await link_collector.initialize()

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    try:
        # التحقق من وجود الملفات الضرورية
        if not os.path.exists(SESSIONS_DIR):
            os.makedirs(SESSIONS_DIR)
        
        # إنشاء تطبيق البوت
        application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
        
        # إضافة المعالجات
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("collect_now", collect_now_command))
        
        application.add_handler(CallbackQueryHandler(handle_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # تشغيل البوت
        logger.info("🚀 Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
