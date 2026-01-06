import os
import sys
import subprocess
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
import signal
import secrets
import base64
import traceback
import threading
import time
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
    ApplicationBuilder
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
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    
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
    DB_POOL_SIZE = 5  # تقليل عدد الاتصالات المتزامنة
    
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

# Setup logging
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
# Global Instances - المثيلات العالمية
# ======================

class GlobalInstances:
    """إدارة المثيلات العالمية لمنع التكرار"""
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalInstances, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    async def initialize(self):
        """تهيئة جميع المثيلات"""
        async with self._lock:
            if not self._initialized:
                self.db_manager = await EnhancedDatabaseManager.get_instance()
                self.cache_manager = CacheManager.get_instance()
                self.memory_manager = MemoryManager.get_instance()
                self.encryption_manager = EncryptionManager.get_instance()
                self._initialized = True
    
    @classmethod
    async def get_instance(cls):
        """الحصول على المثيل العالمي"""
        if cls._instance is None:
            cls._instance = GlobalInstances()
        await cls._instance.initialize()
        return cls._instance

# ======================
# Enhanced Link Processor - معالج الروابط المحسن
# ======================

class EnhancedLinkProcessor:
    """Advanced link processing with improved Telegram detection"""
    
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
        """Normalize URL with enhanced Telegram handling"""
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
        """Extract comprehensive information from URL with enhanced Telegram detection"""
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
        """Extract Telegram specific information with improved detection"""
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
        """Extract WhatsApp specific information"""
        return {
            'is_valid': True,
            'invite_code': parsed.path.strip('/'),
            'is_group': True
        }
    
    @staticmethod
    def _extract_discord_info(url: str, parsed) -> Dict:
        """Extract Discord specific information"""
        return {
            'is_valid': True,
            'invite_code': parsed.path.strip('/'),
            'is_invite': True
        }
    
    @staticmethod
    def _extract_signal_info(url: str, parsed) -> Dict:
        """Extract Signal specific information"""
        return {
            'is_valid': True,
            'group_code': parsed.path.strip('/'),
            'is_group': True
        }
    
    @staticmethod
    async def validate_telegram_link_advanced(client: TelegramClient, url: str, check_join_request: bool = False) -> Dict:
        """Advanced validation for Telegram links"""
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
            
            # التحقق من روابط الانضمام
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
            
            # التحقق من المجموعات العامة
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
    """Advanced database management with improved link handling"""
    
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    
    @classmethod
    async def get_instance(cls):
        """Get database instance with proper async initialization"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = EnhancedDatabaseManager()
                    await cls._instance._initialize()
        return cls._instance
    
    async def _initialize(self):
        """Initialize database asynchronously"""
        if self._initialized:
            return
        
        self.db_path = Config.DB_PATH
        
        # التحقق من وجود الملف
        db_exists = os.path.exists(self.db_path)
        
        # إنشاء مجلد إذا لم يكن موجوداً
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        
        # إنشاء اتصال قاعدة البيانات
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        
        # تهيئة الجداول
        await self._create_tables()
        
        # إنشاء نسخة احتياطية إذا كانت قاعدة البيانات موجودة مسبقاً
        if db_exists and Config.BACKUP_ENABLED:
            await BackupManager.create_backup()
            await BackupManager.rotate_backups()
        
        self._initialized = True
        
        logger.info(f"تم تهيئة قاعدة البيانات بنجاح - db_path: {self.db_path}, db_exists: {db_exists}")
    
    async def _create_tables(self):
        """Create database tables with enhanced structure"""
        # جدول الجلسات المحسن
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
        
        # جدول الروابط المحسن مع تفاصيل أكثر
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
        
        # جدول جلسات الجمع المحسن
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
        
        # جدول المستخدمين المحسن
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
        
        # جدول إحصائيات النظام
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS system_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                metric_value TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,
                UNIQUE(metric_name, recorded_at)
            )
        ''')
        
        # جدول الأخطاء والتحذيرات
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS error_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_type TEXT,
                error_message TEXT,
                stack_trace TEXT,
                user_id INTEGER,
                command TEXT,
                occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved BOOLEAN DEFAULT 0,
                metadata TEXT
            )
        ''')
        
        # جدول روابط الانضمام المؤقتة
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS pending_join_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL,
                platform TEXT NOT NULL,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                check_attempts INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                metadata TEXT,
                CONSTRAINT unique_pending_hash UNIQUE(url_hash)
            )
        ''')
        
        await self.conn.commit()
        
        # إنشاء فهارس
        await self._create_indexes()
    
    async def _create_indexes(self):
        """Create database indexes for performance"""
        indexes = [
            ('idx_links_url_hash', 'links(url_hash)'),
            ('idx_links_platform_type', 'links(platform, link_type)'),
            ('idx_links_collected_date', 'links(collected_date)'),
            ('idx_links_added_by_user', 'links(added_by_user)'),
            ('idx_links_validation_score', 'links(validation_score)'),
            ('idx_links_requires_join', 'links(requires_join, is_active)'),
            ('idx_links_telegram_type', 'links(platform, telegram_type, is_active)'),
            ('idx_sessions_active', 'sessions(is_active, health_score)'),
            ('idx_sessions_added_by', 'sessions(added_by_user, last_used)'),
            ('idx_users_last_active', 'bot_users(last_active)'),
            ('idx_collection_sessions_uid', 'collection_sessions(session_uid)'),
            ('idx_error_log_occurred', 'error_log(occurred_at, error_type)'),
            ('idx_system_stats_metric', 'system_stats(metric_name, recorded_at)'),
            ('idx_pending_join_status', 'pending_join_links(status, last_checked)')
        ]
        
        for index_name, index_sql in indexes:
            try:
                await self.conn.execute(f'CREATE INDEX IF NOT EXISTS {index_name} ON {index_sql}')
            except Exception as e:
                logger.error(f"خطأ في إنشاء الفهرس {index_name}: {e}", exc_info=True)
        
        await self.conn.commit()
    
    async def add_link_enhanced(self, link_info: Dict) -> Tuple[bool, str, Dict]:
        """Add link with enhanced Telegram information"""
        try:
            # استخراج معلومات الرابط
            url = link_info.get('url', '')
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return False, "رابط غير صالح", {}
            
            details = url_info['details']
            
            # التحقق من التكرار
            cursor = await self.conn.execute(
                'SELECT id FROM links WHERE url_hash = ?',
                (url_info['url_hash'],)
            )
            existing = await cursor.fetchone()
            
            if existing:
                return False, "الرابط موجود مسبقاً", {'link_id': existing['id']}
            
            # إعداد بيانات الرابط
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
            
            # إدخال الرابط
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
            
            # تحديث إحصائيات المستخدم
            if link_data['added_by_user']:
                await self.update_user_stats(link_data['added_by_user'], 'link_added')
            
            return True, "تمت إضافة الرابط بنجاح", {
                'link_id': link_id,
                'url_hash': url_info['url_hash']
            }
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الرابط المحسن: {e}", exc_info=True)
            await self.conn.rollback()
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def add_pending_join_link(self, url: str, platform: str = 'telegram', metadata: Dict = None) -> Tuple[bool, str, Dict]:
        """Add pending join link for later verification"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return False, "رابط غير صالح", {}
            
            # التحقق من التكرار
            cursor = await self.conn.execute(
                'SELECT id FROM pending_join_links WHERE url_hash = ?',
                (url_info['url_hash'],)
            )
            existing = await cursor.fetchone()
            
            if existing:
                # تحديث وقت الفحص
                await self.conn.execute(
                    'UPDATE pending_join_links SET last_checked = CURRENT_TIMESTAMP WHERE id = ?',
                    (existing['id'],)
                )
                await self.conn.commit()
                return False, "الرابط موجود مسبقاً في قائمة الانتظار", {'pending_id': existing['id']}
            
            # إضافة جديدة
            cursor = await self.conn.execute('''
                INSERT INTO pending_join_links 
                (url_hash, url, platform, metadata)
                VALUES (?, ?, ?, ?)
            ''', (
                url_info['url_hash'],
                url_info['normalized_url'],
                platform,
                json.dumps(metadata or {})
            ))
            
            pending_id = cursor.lastrowid
            await self.conn.commit()
            
            return True, "تمت إضافة الرابط لقائمة الانتظار", {
                'pending_id': pending_id,
                'url_hash': url_info['url_hash']
            }
            
        except Exception as e:
            logger.error(f"خطأ في إضافة رابط انتظار: {e}")
            await self.conn.rollback()
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def get_pending_join_links(self, limit: int = 50) -> List[Dict]:
        """Get pending join links for verification"""
        try:
            cursor = await self.conn.execute('''
                SELECT * FROM pending_join_links 
                WHERE status = 'pending' 
                ORDER BY last_checked ASC NULLS FIRST, added_date ASC
                LIMIT ?
            ''', (limit,))
            
            rows = await cursor.fetchall()
            pending_links = []
            for row in rows:
                pending_dict = dict(row)
                if pending_dict.get('metadata'):
                    pending_dict['metadata'] = json.loads(pending_dict['metadata'])
                pending_links.append(pending_dict)
            
            return pending_links
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على روابط الانتظار: {e}")
            return []
    
    async def update_pending_link_status(self, pending_id: int, status: str, 
                                        metadata: Dict = None, 
                                        check_attempts: int = 1) -> bool:
        """Update pending link status"""
        try:
            await self.conn.execute('''
                UPDATE pending_join_links 
                SET status = ?, 
                    last_checked = CURRENT_TIMESTAMP,
                    check_attempts = check_attempts + ?,
                    metadata = COALESCE(?, metadata)
                WHERE id = ?
            ''', (status, check_attempts, 
                 json.dumps(metadata) if metadata else None, 
                 pending_id))
            
            await self.conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"خطأ في تحديث حالة رابط الانتظار: {e}")
            await self.conn.rollback()
            return False
    
    async def get_stats_summary_enhanced(self, detailed: bool = False) -> Dict:
        """Get comprehensive database statistics with Telegram breakdown"""
        try:
            stats = {}
            
            # إحصائيات أساسية
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links")
            stats['total_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM pending_join_links WHERE status = 'pending'")
            stats['pending_join_links'] = (await cursor.fetchone())[0]
            
            # الروابط حسب المنصة
            cursor = await self.conn.execute(
                "SELECT platform, COUNT(*) FROM links GROUP BY platform ORDER BY COUNT(*) DESC"
            )
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            # تفصيل تيليجرام المتقدم
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
                    'type': row['telegram_type'] or 'unknown',
                    'is_channel': bool(row['is_channel']),
                    'is_group': bool(row['is_group']),
                    'is_supergroup': bool(row['is_supergroup']),
                    'is_join_request': bool(row['is_join_request']),
                    'count': row['count']
                })
            
            stats['telegram_details'] = telegram_details
            
            # إحصائيات الروابط النشطة
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_active = 1")
            stats['active_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE requires_join = 1")
            stats['requires_join'] = (await cursor.fetchone())[0]
            
            # النشاط حسب اليوم (آخر 7 أيام)
            cursor = await self.conn.execute('''
                SELECT DATE(collected_date) as date, COUNT(*) as count
                FROM links 
                WHERE collected_date > datetime('now', '-7 days')
                GROUP BY DATE(collected_date)
                ORDER BY date DESC
            ''')
            stats['daily_activity'] = dict(await cursor.fetchall())
            
            if detailed:
                # أفضل المستخدمين
                cursor = await self.conn.execute('''
                    SELECT u.user_id, u.username, COUNT(l.id) as link_count
                    FROM bot_users u
                    LEFT JOIN links l ON u.user_id = l.added_by_user
                    GROUP BY u.user_id
                    ORDER BY link_count DESC
                    LIMIT 10
                ''')
                rows = await cursor.fetchall()
                stats['top_users'] = [dict(row) for row in rows]
                
                # أفضل الجلسات
                cursor = await self.conn.execute('''
                    SELECT s.id, s.display_name, s.username, COUNT(l.id) as link_count
                    FROM sessions s
                    LEFT JOIN links l ON s.id = l.session_id
                    WHERE s.is_active = 1
                    GROUP BY s.id
                    ORDER BY link_count DESC
                    LIMIT 10
                ''')
                rows = await cursor.fetchall()
                stats['top_sessions'] = [dict(row) for row in rows]
                
                # إحصائيات التحقق
                cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_verified = 1")
                stats['verified_links'] = (await cursor.fetchone())[0]
                
                cursor = await self.conn.execute("SELECT AVG(validation_score) FROM links WHERE validation_score > 0")
                avg_score = (await cursor.fetchone())[0]
                stats['avg_validation_score'] = float(avg_score) if avg_score else 0
            
            return stats
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على ملخص الإحصائيات المحسن: {e}", exc_info=True)
            return {}
    
    async def export_links_enhanced(self, filters: Dict = None, limit: int = Config.MAX_EXPORT_LINKS, 
                                   offset: int = 0) -> Tuple[List[str], Dict]:
        """Export links with enhanced filtering and Telegram classification"""
        try:
            query = '''
                SELECT url, platform, link_type, telegram_type, collected_date, 
                       members_count, is_channel, is_group, is_supergroup, is_join_request
                FROM links 
                WHERE is_active = 1
            '''
            params = []
            
            if filters:
                where_clauses = []
                
                if filters.get('platform'):
                    where_clauses.append("platform = ?")
                    params.append(filters['platform'])
                
                if filters.get('link_type'):
                    where_clauses.append("link_type = ?")
                    params.append(filters['link_type'])
                
                if filters.get('telegram_type'):
                    where_clauses.append("telegram_type = ?")
                    params.append(filters['telegram_type'])
                
                if filters.get('min_members'):
                    where_clauses.append("members_count >= ?")
                    params.append(filters['min_members'])
                
                if filters.get('date_from'):
                    where_clauses.append("collected_date >= ?")
                    params.append(filters['date_from'])
                
                if filters.get('date_to'):
                    where_clauses.append("collected_date <= ?")
                    params.append(filters['date_to'])
                
                if filters.get('added_by_user'):
                    where_clauses.append("added_by_user = ?")
                    params.append(filters['added_by_user'])
                
                if filters.get('confidence'):
                    where_clauses.append("confidence = ?")
                    params.append(filters['confidence'])
                
                if filters.get('requires_join') is not None:
                    where_clauses.append("requires_join = ?")
                    params.append(1 if filters['requires_join'] else 0)
                
                if filters.get('is_verified') is not None:
                    where_clauses.append("is_verified = ?")
                    params.append(1 if filters['is_verified'] else 0)
                
                if filters.get('is_channel') is not None:
                    where_clauses.append("is_channel = ?")
                    params.append(1 if filters['is_channel'] else 0)
                
                if filters.get('is_group') is not None:
                    where_clauses.append("is_group = ?")
                    params.append(1 if filters['is_group'] else 0)
                
                if where_clauses:
                    query += " AND " + " AND ".join(where_clauses)
            
            query += " ORDER BY collected_date DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor = await self.conn.execute(query, params)
            rows = await cursor.fetchall()
            
            # الحصول على العدد الإجمالي
            count_query = query.replace(
                "SELECT url, platform, link_type, telegram_type, collected_date, members_count, is_channel, is_group, is_supergroup, is_join_request", 
                "SELECT COUNT(*)"
            )
            count_query = count_query.split("ORDER BY")[0]
            
            count_cursor = await self.conn.execute(count_query, params[:-2] if filters else [])
            total_count = (await count_cursor.fetchone())[0]
            
            links = [row['url'] for row in rows]
            
            metadata = {
                'total_count': total_count,
                'exported_count': len(links),
                'limit': limit,
                'offset': offset,
                'filters': filters or {},
                'platform_distribution': {},
                'telegram_classification': {
                    'channels': 0,
                    'groups': 0,
                    'supergroups': 0,
                    'join_requests': 0
                }
            }
            
            # تحليل التصنيف
            if rows:
                platform_counts = {}
                for row in rows:
                    platform = row['platform']
                    platform_counts[platform] = platform_counts.get(platform, 0) + 1
                    
                    # تصنيف تيليجرام
                    if platform == 'telegram':
                        if row['is_channel']:
                            metadata['telegram_classification']['channels'] += 1
                        if row['is_group']:
                            metadata['telegram_classification']['groups'] += 1
                        if row['is_supergroup']:
                            metadata['telegram_classification']['supergroups'] += 1
                        if row['is_join_request']:
                            metadata['telegram_classification']['join_requests'] += 1
                
                metadata['platform_distribution'] = platform_counts
            
            return links, metadata
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الروابط المحسن: {e}", exc_info=True)
            return [], {}
    
    async def update_user_stats(self, user_id: int, action: str, value: int = 1):
        """Update user statistics"""
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
    
    async def get_active_sessions(self, limit: int = 10):
        """Get active sessions"""
        try:
            cursor = await self.conn.execute('''
                SELECT * FROM sessions 
                WHERE is_active = 1 
                ORDER BY health_score DESC, last_used ASC
                LIMIT ?
            ''', (limit,))
            
            rows = await cursor.fetchall()
            sessions = []
            for row in rows:
                session_dict = dict(row)
                if session_dict.get('metadata'):
                    try:
                        session_dict['metadata'] = json.loads(session_dict['metadata'])
                    except:
                        session_dict['metadata'] = {}
                sessions.append(session_dict)
            
            return sessions
        except Exception as e:
            logger.error(f"خطأ في الحصول على الجلسات النشطة: {e}")
            return []
    
    async def add_or_update_user(self, user_id: int, username: str = None, 
                                first_name: str = None, last_name: str = None):
        """Add or update user"""
        try:
            cursor = await self.conn.execute('''
                SELECT user_id FROM bot_users WHERE user_id = ?
            ''', (user_id,))
            
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
        """Get user statistics"""
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
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"خطأ في الحصول على إحصائيات المستخدم: {e}")
            return None
    
    async def close(self):
        """Close database connection"""
        if hasattr(self, 'conn') and self.conn:
            await self.conn.close()
            self._initialized = False

# ======================
# Cache Manager - مدير الكاش
# ======================

class CacheManager:
    """Cache manager"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get instance"""
        if cls._instance is None:
            cls._instance = CacheManager()
        return cls._instance
    
    def __init__(self):
        self.fast_cache = OrderedDict()
        self.fast_cache_size = 10000
        
        self.slow_cache_dir = "cache_data"
        os.makedirs(self.slow_cache_dir, exist_ok=True)
        
        self.stats = {
            'fast_hits': 0,
            'slow_hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_operations': 0
        }
        
        self.lock = asyncio.Lock()
    
    async def get(self, key: str, category: str = 'general') -> Optional[Any]:
        """Get from cache"""
        async with self.lock:
            self.stats['total_operations'] += 1
            cache_key = f"{category}_{key}"
            
            if cache_key in self.fast_cache:
                self.fast_cache.move_to_end(cache_key)
                self.stats['fast_hits'] += 1
                return self.fast_cache[cache_key]
            
            file_path = os.path.join(self.slow_cache_dir, f"{hashlib.md5(cache_key.encode()).hexdigest()}.cache")
            if os.path.exists(file_path):
                try:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        data = json.loads(content)
                        
                        await self._add_to_fast_cache(cache_key, data)
                        self.stats['slow_hits'] += 1
                        return data
                except:
                    pass
            
            self.stats['misses'] += 1
            return None
    
    async def set(self, key: str, value: Any, category: str = 'general', ttl_seconds: int = 3600):
        """Set in cache"""
        async with self.lock:
            cache_key = f"{category}_{key}"
            
            await self._add_to_fast_cache(cache_key, value)
            
            file_path = os.path.join(self.slow_cache_dir, f"{hashlib.md5(cache_key.encode()).hexdigest()}.cache")
            cache_data = {
                'value': value,
                'expires_at': (datetime.now() + timedelta(seconds=ttl_seconds)).isoformat(),
                'category': category,
                'key': key
            }
            
            try:
                async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(cache_data, ensure_ascii=False))
            except Exception as e:
                logger.debug(f"خطأ في تخزين الكاش البطيء: {e}")
    
    async def _add_to_fast_cache(self, key: str, value: Any):
        """Add to fast cache"""
        if key in self.fast_cache:
            self.fast_cache.move_to_end(key)
            self.fast_cache[key] = value
        else:
            self.fast_cache[key] = value
            
            if len(self.fast_cache) > self.fast_cache_size:
                oldest_key = next(iter(self.fast_cache))
                del self.fast_cache[oldest_key]
                self.stats['evictions'] += 1
    
    async def exists(self, key: str, category: str = 'general') -> bool:
        """Check if exists"""
        cache_key = f"{category}_{key}"
        return cache_key in self.fast_cache
    
    async def delete(self, key: str, category: str = 'general'):
        """Delete from cache"""
        async with self.lock:
            cache_key = f"{category}_{key}"
            
            if cache_key in self.fast_cache:
                del self.fast_cache[cache_key]
            
            file_path = os.path.join(self.slow_cache_dir, f"{hashlib.md5(cache_key.encode()).hexdigest()}.cache")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
    
    async def cleanup_expired(self):
        """Cleanup expired"""
        async with self.lock:
            expired_count = 0
            
            for filename in os.listdir(self.slow_cache_dir):
                if filename.endswith('.cache'):
                    file_path = os.path.join(self.slow_cache_dir, filename)
                    try:
                        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                            content = await f.read()
                            data = json.loads(content)
                            
                            expires_at = datetime.fromisoformat(data['expires_at'])
                            if datetime.now() > expires_at:
                                os.remove(file_path)
                                expired_count += 1
                    except:
                        try:
                            os.remove(file_path)
                        except:
                            pass
            
            if expired_count > 0:
                logger.info(f"تم تنظيف {expired_count} عنصر منتهي من الكاش")
    
    def optimize(self):
        """Optimize"""
        current_size = len(self.fast_cache)
        if current_size > self.fast_cache_size:
            target_size = int(self.fast_cache_size * 0.8)
            while len(self.fast_cache) > target_size:
                oldest_key = next(iter(self.fast_cache))
                del self.fast_cache[oldest_key]
                self.stats['evictions'] += 1
    
    def get_stats(self) -> Dict:
        """Get stats"""
        total_hits = self.stats['fast_hits'] + self.stats['slow_hits']
        total_accesses = total_hits + self.stats['misses']
        hit_ratio = total_hits / total_accesses if total_accesses > 0 else 0
        
        return {
            **self.stats,
            'fast_cache_size': len(self.fast_cache),
            'fast_cache_max': self.fast_cache_size,
            'total_hits': total_hits,
            'hit_ratio': f"{hit_ratio:.2%}",
            'slow_cache_files': len(os.listdir(self.slow_cache_dir)) if os.path.exists(self.slow_cache_dir) else 0
        }
    
    def clear(self):
        """Clear"""
        self.fast_cache.clear()
        self.stats = {
            'fast_hits': 0,
            'slow_hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_operations': 0
        }

# ======================
# Memory Manager - مدير الذاكرة
# ======================

class MemoryManager:
    """Memory manager"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get instance"""
        if cls._instance is None:
            cls._instance = MemoryManager()
        return cls._instance
    
    def __init__(self):
        self.metrics = {
            'optimizations': 0,
            'total_saved_mb': 0.0,
            'high_memory_warnings': 0,
            'last_optimization': None
        }
        
    def get_memory_usage(self) -> float:
        """Get memory usage"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except Exception as e:
            logger.debug(f"خطأ في قراءة الذاكرة: {e}")
            return 0
    
    def get_memory_percent(self) -> float:
        """Get memory percent"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_percent()
        except:
            return 0
    
    def get_system_memory(self) -> Dict:
        """Get system memory"""
        try:
            mem = psutil.virtual_memory()
            return {
                'total_mb': mem.total / 1024 / 1024,
                'available_mb': mem.available / 1024 / 1024,
                'percent_used': mem.percent,
                'process_percent': self.get_memory_percent()
            }
        except Exception as e:
            logger.debug(f"خطأ في قراءة ذاكرة النظام: {e}")
            return {}
    
    def optimize_memory(self) -> Dict:
        """Optimize memory"""
        before = self.get_memory_usage()
        before_time = datetime.now()
        
        gc.collect()
        
        try:
            process = psutil.Process(os.getpid())
            open_files = len(process.open_files())
            if open_files > 100:
                logger.warning(f"عدد كبير من الملفات المفتوحة: {open_files}")
        except:
            pass
        
        CacheManager.get_instance().optimize()
        
        after = self.get_memory_usage()
        saved = before - after
        
        self.metrics['optimizations'] += 1
        self.metrics['total_saved_mb'] += saved if saved > 0 else 0
        self.metrics['last_optimization'] = datetime.now()
        
        logger.info(f"تحسين الذاكرة: {saved:.2f} MB")
        
        return {
            'saved_mb': saved,
            'before_mb': before,
            'after_mb': after,
            'duration_ms': (datetime.now() - before_time).total_seconds() * 1000
        }
    
    def check_and_optimize(self, threshold_percent: float = 80.0) -> Dict:
        """Check and optimize"""
        current_mb = self.get_memory_usage()
        current_percent = self.get_memory_percent()
        
        result = {
            'optimized': False,
            'current_mb': current_mb,
            'current_percent': current_percent,
            'threshold_mb': Config.MAX_MEMORY_MB,
            'threshold_percent': threshold_percent
        }
        
        if current_mb > Config.MAX_MEMORY_MB or current_percent > threshold_percent:
            logger.warning(f"استخدام عالي للذاكرة: {current_mb:.2f} MB, {current_percent:.1f}%")
            
            self.metrics['high_memory_warnings'] += 1
            optimization_result = self.optimize_memory()
            result.update(optimization_result)
            result['optimized'] = True
        
        return result
    
    def get_metrics(self) -> Dict:
        """Get metrics"""
        return {
            **self.metrics,
            'current_mb': self.get_memory_usage(),
            'current_percent': self.get_memory_percent(),
            'system_memory': self.get_system_memory()
        }

# ======================
# Encryption Manager - مدير التشفير
# ======================

class EncryptionManager:
    """Encryption manager"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get instance"""
        if cls._instance is None:
            cls._instance = EncryptionManager()
        return cls._instance
    
    def __init__(self):
        key = Config.ENCRYPTION_KEY.encode()
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'links_collector_salt',
            iterations=100000,
        )
        
        derived_key = base64.urlsafe_b64encode(kdf.derive(key))
        self.cipher = Fernet(derived_key)
    
    def encrypt(self, data: str) -> str:
        """Encrypt"""
        try:
            encrypted = self.cipher.encrypt(data.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"خطأ في التشفير: {e}")
            return data
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt"""
        try:
            decrypted = self.cipher.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"خطأ في فك التشفير: {e}")
            return encrypted_data
    
    def encrypt_session(self, session_string: str) -> str:
        """Encrypt session"""
        metadata = {
            'encrypted_at': datetime.now().isoformat(),
            'version': '2.0'
        }
        
        data = {
            'session': session_string,
            'metadata': metadata
        }
        
        return self.encrypt(json.dumps(data))
    
    def decrypt_session(self, encrypted_data: str) -> Optional[str]:
        """Decrypt session"""
        try:
            decrypted = self.decrypt(encrypted_data)
            data = json.loads(decrypted)
            return data['session']
        except Exception as e:
            logger.error(f"خطأ في فك تشفير الجلسة: {e}")
            return None

# ======================
# Session Manager - مدير الجلسات
# ======================

class SessionManager:
    """Session manager"""
    
    @staticmethod
    async def validate_session(session_string: str) -> Tuple[bool, Dict]:
        """Validate session"""
        try:
            enc_manager = EncryptionManager.get_instance()
            decrypted = enc_manager.decrypt_session(session_string)
            actual_session = decrypted or session_string
            
            client = TelegramClient(
                StringSession(actual_session),
                Config.API_ID,
                Config.API_HASH,
                timeout=15
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return False, {'error': 'غير مصرح', 'details': 'الجلسة غير مفعلة'}
            
            me = await client.get_me()
            
            user_info = {
                'id': me.id,
                'username': me.username or '',
                'phone': me.phone or '',
                'first_name': me.first_name or '',
                'last_name': me.last_name or '',
                'is_bot': me.bot if hasattr(me, 'bot') else False,
                'is_premium': me.premium if hasattr(me, 'premium') else False
            }
            
            await client.disconnect()
            
            return True, {
                'user_info': user_info,
                'session_length': len(session_string),
                'is_encrypted': decrypted is not None
            }
            
        except SessionPasswordNeededError:
            return False, {'error': 'محمية بكلمة مرور', 'details': 'الجلسة تتطلب كلمة مرور ثانوية'}
        except AuthKeyError:
            return False, {'error': 'مفتاح مصادقة غير صالح', 'details': 'الجلسة منتهية أو غير صالحة'}
        except Exception as e:
            return False, {'error': 'خطأ في التحقق', 'details': str(e)[:200]}

# ======================
# Backup Manager - مدير النسخ الاحتياطي
# ======================

class BackupManager:
    """Backup manager"""
    
    @staticmethod
    async def create_backup() -> Optional[Dict]:
        """Create backup"""
        if not Config.BACKUP_ENABLED:
            return None
        
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = "backups"
            backup_filename = f"{Config.DB_PATH}.backup_{timestamp}"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            os.makedirs(backup_dir, exist_ok=True)
            
            if not os.path.exists(Config.DB_PATH):
                logger.error("ملف قاعدة البيانات غير موجود")
                return None
            
            db_size = os.path.getsize(Config.DB_PATH)
            
            shutil.copy2(Config.DB_PATH, backup_path)
            
            metadata = {
                'backup_id': hashlib.md5(f"{timestamp}_{db_size}".encode()).hexdigest(),
                'timestamp': timestamp,
                'created_at': datetime.now().isoformat(),
                'original_path': Config.DB_PATH,
                'backup_path': backup_path,
                'size_bytes': db_size,
                'size_mb': db_size / 1024 / 1024,
                'checksum': BackupManager._calculate_checksum(Config.DB_PATH),
                'version': '2.0'
            }
            
            metadata_path = backup_path + '.meta'
            async with aiofiles.open(metadata_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(metadata, indent=2))
            
            logger.info(f"تم إنشاء نسخة احتياطية: {backup_path}")
            
            return metadata
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء نسخة احتياطية: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _calculate_checksum(file_path: str) -> str:
        """Calculate checksum"""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    @staticmethod
    async def rotate_backups():
        """Rotate backups"""
        try:
            if not os.path.exists("backups"):
                return
            
            backups = []
            for filename in os.listdir("backups"):
                if filename.startswith(Config.DB_PATH + ".backup_"):
                    path = os.path.join("backups", filename)
                    
                    if filename.endswith('.meta'):
                        continue
                    
                    try:
                        ctime = os.path.getctime(path)
                        size = os.path.getsize(path)
                        backups.append({
                            'path': path,
                            'created': ctime,
                            'size': size
                        })
                    except:
                        continue
            
            if not backups:
                return
            
            backups.sort(key=lambda x: x['created'])
            
            now = datetime.now()
            to_keep = []
            to_delete = []
            
            for backup in backups:
                backup_date = datetime.fromtimestamp(backup['created'])
                age_days = (now - backup_date).days
                
                if len(to_keep) < Config.MAX_BACKUPS:
                    to_keep.append(backup)
                    continue
                
                to_delete.append(backup)
            
            deleted_count = 0
            for backup in to_delete:
                try:
                    os.remove(backup['path'])
                    
                    meta_path = backup['path'] + '.meta'
                    if os.path.exists(meta_path):
                        os.remove(meta_path)
                    
                    deleted_count += 1
                    logger.info(f"تم حذف النسخة القديمة: {backup['path']}")
                    
                except Exception as e:
                    logger.error(f"خطأ في حذف النسخة القديمة: {e}")
            
            if deleted_count > 0:
                logger.info(f"تم تدوير {deleted_count} نسخة احتياطية قديمة")
            
            return deleted_count
                    
        except Exception as e:
            logger.error(f"خطأ في تدوير النسخ الاحتياطية: {e}", exc_info=True)
            return 0

# ======================
# Advanced Collection Manager - مدير الجمع المتقدم
# ======================

class AdvancedCollectionManager:
    """Advanced collection management"""
    
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
            'performance_score': 100.0,
            'quality_score': 100.0
        }
        
        self.whatsapp_cutoff = datetime.now() - timedelta(days=Config.WHATSAPP_DAYS_BACK)
    
    async def start_collection(self, mode: str = 'balanced'):
        """Start the advanced collection process"""
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.stats['start_time'] = datetime.now()
        self.stats['current_session'] = self.stats['start_time'].strftime('%Y%m%d_%H%M%S')
        
        logger.info(f"🚀 بدء عملية الجمع الذكية المتقدمة - mode: {mode}")
        
        try:
            while self.active and not self.stop_requested:
                if self.paused:
                    await asyncio.sleep(1)
                    continue
                
                await self._collection_cycle()
                
                if self.active and not self.stop_requested:
                    delay = Config.REQUEST_DELAYS['min_cycle_delay']
                    await asyncio.sleep(delay)
        
        except Exception as e:
            logger.error(f"❌ خطأ في عملية الجمع: {e}", exc_info=True)
        
        finally:
            await self._graceful_shutdown()
    
    async def _collection_cycle(self):
        """Execute collection cycle"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=Config.MAX_CONCURRENT_SESSIONS)
            
            if not sessions:
                logger.warning("لا توجد جلسات نشطة متاحة")
                return
            
            for session in sessions:
                if not self.active or self.stop_requested or self.paused:
                    break
                
                await self._process_session(session)
                await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
            
            self.stats['cycles_completed'] += 1
            logger.info(f"اكتملت دورة الجمع {self.stats['cycles_completed']}")
            
        except Exception as e:
            logger.error(f"خطأ في دورة الجمع: {e}", exc_info=True)
            self.stats['errors'] += 1
    
    async def _process_session(self, session: Dict):
        """Process session"""
        session_id = session.get('id')
        
        try:
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt_session(session.get('session_string', ''))
            actual_session = decrypted_session or session.get('session_string', '')
            
            if not actual_session or actual_session == '********':
                logger.error(f"جلسة {session_id} غير متاحة")
                return
            
            client = TelegramClient(
                StringSession(actual_session),
                Config.API_ID,
                Config.API_HASH,
                device_model="Link Collector Pro",
                system_version="Linux 6.5",
                app_version="4.16.30",
                timeout=30,
                connection_retries=3
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                logger.error(f"الجلسة {session_id} غير مصرح بها")
                return
            
            # جمع الروابط من الدردشات
            await self._collect_from_dialogs(client, session_id, session.get('added_by_user', 0))
            
            # تحديث استخدام الجلسة
            db = await EnhancedDatabaseManager.get_instance()
            await db.conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, total_uses = total_uses + 1 WHERE id = ?",
                (session_id,)
            )
            await db.conn.commit()
            
            await client.disconnect()
            
        except FloodWaitError as e:
            logger.warning(f"انتظار flood للجلسة {session_id}: {e.seconds} ثانية")
            await asyncio.sleep(e.seconds + Config.REQUEST_DELAYS['flood_wait'])
        except Exception as e:
            logger.error(f"خطأ في معالجة الجلسة {session_id}: {e}", exc_info=True)
            self.stats['errors'] += 1
    
    async def _collect_from_dialogs(self, client: TelegramClient, session_id: int, added_by_user: int):
        """Collect links from dialogs"""
        try:
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    await self._collect_from_dialog(client, dialog.entity, session_id, added_by_user)
                    await asyncio.sleep(Config.REQUEST_DELAYS['normal'])
                except Exception as e:
                    logger.debug(f"خطأ في جمع الروابط من الدردشة: {e}")
        
        except Exception as e:
            logger.error(f"خطأ في جمع الروابط من الدردشات: {e}")
    
    async def _collect_from_dialog(self, client: TelegramClient, entity, session_id: int, added_by_user: int):
        """Collect links from a specific dialog"""
        try:
            # جمع روابط من الوصف
            if hasattr(entity, 'about') and entity.about:
                links = self._extract_all_links(entity.about)
                for link in links:
                    await self._process_link(client, link, session_id, added_by_user)
            
            # جمع الروابط من الرسائل الحديثة
            try:
                async for message in client.iter_messages(entity, limit=5):
                    if not message.text:
                        continue
                    
                    links = self._extract_all_links(message.text)
                    for link in links:
                        await self._process_link(client, link, session_id, added_by_user, message.date)
                    
                    break
            except:
                pass
        
        except Exception as e:
            logger.debug(f"خطأ في جمع الروابط من الدردشة: {e}")
    
    async def _process_link(self, client: TelegramClient, url: str, session_id: int, added_by_user: int, message_date=None):
        """Process link"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return
            
            platform = url_info['platform']
            
            # تطبيق قيود زمنية فقط لواتساب
            if platform == 'whatsapp' and message_date:
                if message_date < self.whatsapp_cutoff:
                    return
            
            cache_manager = CacheManager.get_instance()
            cache_key = f"link_{url_info['url_hash']}"
            
            if await cache_manager.exists(cache_key, 'validated_links'):
                return
            
            # التحقق من الروابط
            if platform == 'telegram' and Config.ENABLE_ADVANCED_VALIDATION:
                validated = await EnhancedLinkProcessor.validate_telegram_link_advanced(
                    client, url, check_join_request=False
                )
            else:
                validated = {'is_valid': True, 'is_active': True}
            
            if validated.get('is_valid', False) and validated.get('is_active', True):
                link_info = self._create_link_info(url, url_info, validated, session_id, added_by_user, message_date)
                
                # إضافة الرابط إلى قاعدة البيانات
                db = await EnhancedDatabaseManager.get_instance()
                success, message, details = await db.add_link_enhanced(link_info)
                
                if success:
                    # تخزين في الكاش
                    await cache_manager.set(cache_key, {
                        'link_type': validated.get('type', 'unknown'),
                        'title': validated.get('title', ''),
                        'members': validated.get('members', 0),
                        'confidence': 'high' if validated.get('is_verified', False) else 'medium'
                    }, 'validated_links', 86400)
                    
                    # تحديث الإحصائيات
                    self._update_collection_stats(url_info, validated)
                    
                    logger.info(f"تم جمع رابط: {url}")
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الرابط {url}: {e}")
    
    def _create_link_info(self, url: str, url_info: Dict, validated: Dict, 
                         session_id: int, added_by_user: int, message_date=None) -> Dict:
        """Create link information dictionary"""
        details = url_info['details']
        
        return {
            'url': url,
            'url_hash': url_info['url_hash'],
            'platform': url_info['platform'],
            'link_type': validated.get('type', 'unknown'),
            'telegram_type': validated.get('type', 'unknown'),
            'title': validated.get('title', ''),
            'description': '',
            'members': validated.get('members', 0),
            'session_id': session_id,
            'added_by_user': added_by_user,
            'confidence': 'high' if validated.get('is_verified', False) else 'medium',
            'is_active': validated.get('is_active', True),
            'requires_join': validated.get('requires_join', False) or details.get('is_join_request', False),
            'is_verified': validated.get('is_verified', False),
            'validation_score': validated.get('validation_score', 50),
            'metadata': {
                'collected_at': datetime.now().isoformat(),
                'message_date': message_date.isoformat() if message_date else None,
                'quality_score': 80,
                'verification_method': validated.get('method', 'enhanced'),
                'is_channel': validated.get('is_channel', False),
                'is_group': validated.get('is_group', True),
                'is_supergroup': validated.get('is_supergroup', False),
                'is_join_request': details.get('is_join_request', False)
            },
            'tags': [],
            'source': 'collection'
        }
    
    def _update_collection_stats(self, url_info: Dict, validation: Dict):
        """Update collection statistics"""
        platform = url_info['platform']
        
        if platform == 'telegram':
            if validation.get('is_channel', False):
                self.stats['telegram_channels'] += 1
            elif validation.get('is_supergroup', False):
                self.stats['telegram_supergroups'] += 1
            elif validation.get('is_group', False):
                self.stats['telegram_groups'] += 1
            
            if validation.get('requires_join', False) or url_info['details'].get('is_join_request', False):
                self.stats['telegram_join'] += 1
            elif validation.get('is_public', True):
                self.stats['telegram_public'] += 1
            else:
                self.stats['telegram_private'] += 1
        
        elif platform == 'whatsapp':
            self.stats['whatsapp_groups'] += 1
        elif platform == 'discord':
            self.stats['discord_invites'] += 1
        elif platform == 'signal':
            self.stats['signal_groups'] += 1
        
        self.stats['total_collected'] += 1
    
    def _extract_all_links(self, text: str) -> List[str]:
        """Extract all links from text"""
        if not text:
            return []
        
        url_patterns = [
            r'(https?://[^\s<>"\']+)',
            r'(t\.me/[^\s<>"\']+)',
            r'(telegram\.me/[^\s<>"\']+)',
            r'(chat\.whatsapp\.com/[^\s<>"\']+)',
            r'(discord\.gg/[^\s<>"\']+)',
            r'(signal\.group/[^\s<>"\']+)',
            r'(joinchat/[^\s<>"\']+)',
            r'(\+[A-Za-z0-9_-]+)'
        ]
        
        all_links = []
        for pattern in url_patterns:
            links = re.findall(pattern, text, re.IGNORECASE)
            all_links.extend(links)
        
        filtered_links = []
        for link in all_links:
            link = link.strip()
            if link.startswith('+') and len(link) > 5:
                link = f"https://t.me/{link}"
            filtered_links.append(link)
        
        return list(set(filtered_links))
    
    async def _graceful_shutdown(self):
        """Perform graceful shutdown"""
        logger.info("بدء الإغلاق السلس لنظام الجمع...")
        
        self.active = False
        self.paused = False
        self.stats['end_time'] = datetime.now()
        
        logger.info(f"✅ اكتمل الإغلاق السلس. الإحصائيات: {self.stats}")
    
    def get_status(self) -> Dict:
        """Get collection status"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'stats': self.stats.copy()
        }
    
    async def pause(self):
        """Pause collection"""
        self.paused = True
        logger.info("⏸️ تم إوقف الجمع مؤقتاً")
    
    async def resume(self):
        """Resume collection"""
        self.paused = False
        logger.info("▶️ تم استئناف الجمع")
    
    async def stop(self):
        """Stop collection"""
        self.stop_requested = True
        logger.info("⏹️ تم طلب إيقاف الجمع")

# ======================
# Advanced Telegram Bot - بوت تيليجرام المتقدم
# ======================

class AdvancedTelegramBot:
    """Advanced Telegram bot with complete functionality"""
    
    def __init__(self):
        self.collection_manager = AdvancedCollectionManager()
        self.app = None
        self.user_states = {}
        self.bot_running = False
    
    async def initialize(self):
        """Initialize the bot"""
        if self.bot_running:
            logger.warning("البوت يعمل بالفعل")
            return
        
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        self._setup_handlers()
        self.bot_running = True
        
        logger.info("تم تهيئة البوت المتقدم")
    
    def _setup_handlers(self):
        """Setup all handlers"""
        # الأوامر الأساسية
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("addsession", self.add_session_command))
        
        # معالجة الاستدعاءات
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))
        
        # معالجة الرسائل النصية
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler))
        
        # معالج الأخطاء
        self.app.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # التحقق من صلاحيات المستخدم
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك باستخدام هذا البوت")
                return
        
        # إضافة/تحديث المستخدم في قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        await db.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        # إنشاء لوحة المفاتيح الرئيسية
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect"),
             InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="stop_collect"),
             InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status")],
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("👥 الجلسات", callback_data="list_sessions")],
            [InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_links"),
             InlineKeyboardButton("📈 الإحصائيات", callback_data="show_stats")],
            [InlineKeyboardButton("❓ المساعدة", callback_data="show_help"),
             InlineKeyboardButton("⚙️ الإعدادات", callback_data="show_settings")]
        ])
        
        welcome_text = f"""
🤖 **مرحباً {user.first_name}!**

**بوت جمع روابط المجموعات المتقدم**

✨ **المميزات:**
• جمع روابط تيليجرام (مجموعات، قنوات، دعوات)
• جمع روابط واتساب (آخر 30 يوماً)
• تصدير الروابط بصيغة TXT
• إدارة متعددة للجلسات
• إحصائيات مفصلة

🚀 **ابدأ الآن باستخدام الأزرار أدناه!**
"""
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
❓ **دليل استخدام البوت**

📋 **الأوامر المتاحة:**
/start - بدء البوت وعرض القائمة الرئيسية
/help - عرض هذه الرسالة
/status - عرض حالة النظام
/stats - عرض إحصائيات الروابط
/sessions - عرض الجلسات المضافة
/collect - بدء/إيقاف عملية الجمع
/export - تصدير الروابط
/addsession - إضافة جلسة جديدة

🎯 **كيفية الاستخدام:**
1. أضف جلسات تيليجرام باستخدام /addsession
2. ابدأ عملية الجمع باستخدام زر 🚀 بدء الجمع
3. قم بتصدير الروابط المجمعة باستخدام زر 📤 تصدير الروابط

⚡ **النصائح:**
• يمكنك إضافة حتى 20 جلسة
• النظام يجمع روابط من جميع الدردشات
• يتم تخزين الروابط المكررة تلقائياً
"""
        
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        status = self.collection_manager.get_status()
        
        memory_manager = MemoryManager.get_instance()
        memory_usage = memory_manager.get_memory_usage()
        
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary_enhanced()
        
        status_text = f"""
📊 **حالة النظام - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**

**🔧 حالة الجمع:**
{'🔄 **نشط**' if status['active'] else '🛑 **متوقف**'}
{'⏸️ **موقف مؤقتاً**' if status['paused'] else ''}

**📈 إحصائيات الجمع:**
• 📦 المجموع: {status['stats']['total_collected']:,}
• 📢 مجموعات عامة: {status['stats']['telegram_public']:,}
• 🔒 مجموعات خاصة: {status['stats']['telegram_private']:,}
• ➕ طلبات انضمام: {status['stats']['telegram_join']:,}
• 📢 قنوات: {status['stats']['telegram_channels']:,}
• ⭐ مجموعات خارقة: {status['stats']['telegram_supergroups']:,}
• 📱 واتساب: {status['stats']['whatsapp_groups']:,}
• 🔄 دورات الجمع: {status['stats']['cycles_completed']:,}

**💾 قاعدة البيانات:**
• 🔗 إجمالي الروابط: {db_stats.get('total_links', 0):,}
• 👥 الجلسات النشطة: {db_stats.get('active_sessions', 0)}
• 👤 المستخدمين: {db_stats.get('total_users', 0)}

**⚡ موارد النظام:**
• 🧠 استخدام الذاكرة: {memory_usage:.1f} MB
• 🔥 الحد الأقصى للجلسات: {Config.MAX_CONCURRENT_SESSIONS}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_status"),
             InlineKeyboardButton("📊 تفاصيل", callback_data="detailed_stats")]
        ])
        
        await update.message.reply_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        db = await EnhancedDatabaseManager.get_instance()
        stats = await db.get_stats_summary_enhanced(detailed=True)
        
        stats_text = f"""
📈 **إحصائيات شاملة - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**

**🔗 إجمالي الروابط: {stats.get('total_links', 0):,}**

**📊 التوزيع حسب المنصة:**
"""
        
        for platform, count in stats.get('links_by_platform', {}).items():
            stats_text += f"• {platform}: {count:,}\n"
        
        # تفصيل تيليجرام
        telegram_stats = stats.get('telegram_details', [])
        if telegram_stats:
            stats_text += "\n**📢 تفصيل تيليجرام:**\n"
            for item in telegram_stats[:5]:
                type_name = item.get('type', 'unknown')
                if not type_name or type_name == 'unknown':
                    if item.get('is_channel'):
                        type_name = 'قناة'
                    elif item.get('is_supergroup'):
                        type_name = 'مجموعة خارقة'
                    elif item.get('is_group'):
                        type_name = 'مجموعة'
                    else:
                        type_name = 'غير معروف'
                
                stats_text += f"• {type_name}: {item.get('count', 0):,}\n"
        
        # النشاط اليومي
        daily_activity = stats.get('daily_activity', {})
        if daily_activity:
            stats_text += "\n**📅 النشاط اليومي (آخر 7 أيام):**\n"
            for date, count in list(daily_activity.items())[:3]:
                stats_text += f"• {date}: {count:,}\n"
        
        # أفضل المستخدمين
        top_users = stats.get('top_users', [])
        if top_users:
            stats_text += "\n**🏆 أفضل المستخدمين:**\n"
            for i, user in enumerate(top_users[:3], 1):
                username = user.get('username', f"user_{user.get('user_id')}")
                stats_text += f"{i}. @{username}: {user.get('link_count', 0):,} رابط\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_stats"),
             InlineKeyboardButton("📤 تصدير", callback_data="export_stats")]
        ])
        
        await update.message.reply_text(stats_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sessions command"""
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=10)
        
        if not sessions:
            await update.message.reply_text("📭 لا توجد جلسات مضافة")
            return
        
        sessions_text = f"""
👥 **الجلسات النشطة - {len(sessions)} جلسة**

"""
        
        for i, session in enumerate(sessions, 1):
            display_name = session.get('display_name', 'غير معروف')
            username = session.get('username', 'لا يوجد')
            uses = session.get('total_uses', 0)
            links = session.get('total_links', 0)
            health = session.get('health_score', 0)
            
            sessions_text += f"""
**#{i} - {display_name}**
• المستخدم: @{username}
• الاستخدامات: {uses:,}
• الروابط: {links:,}
• الصحة: {health}/100
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("🗑️ إدارة الجلسات", callback_data="manage_sessions")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_sessions")]
        ])
        
        await update.message.reply_text(sessions_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /collect command"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]
        ])
        
        collect_text = """
🚀 **نظام الجمع المتقدم**

**المميزات:**
• 📢 جمع روابط تيليجرام بدون قيود زمنية
• 📱 جمع روابط واتساب من آخر 30 يوماً
• 🔍 كشف ذكي للمجموعات والقنوات
• ⏱️ تحقق من طلبات الانضمام

**الحدود:**
• 🔥 أقصى 20 جلسة متزامنة
• 📥 جمع متوازن مع حماية الذاكرة
• 🔄 دورات جمع ذكية

**اختر الإجراء المناسب:**
"""
        
        await update.message.reply_text(collect_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 تصدير جميع الروابط", callback_data="export_all")],
            [InlineKeyboardButton("📢 تصدير تيليجرام فقط", callback_data="export_telegram")],
            [InlineKeyboardButton("📱 تصدير واتساب فقط", callback_data="export_whatsapp")],
            [InlineKeyboardButton("⚙️ تصدير مخصص", callback_data="export_custom")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]
        ])
        
        export_text = f"""
📤 **نظام التصدير المتقدم**

**الحدود:**
• أقصى {Config.MAX_EXPORT_LINKS:,} رابط للتصدير
• تصدير بتصنيفات مختلفة
• حفظ تلقائي للملفات

**خيارات التصدير:**
1. 📤 جميع الروابط - تصدير كل الروابط المجمعة
2. 📢 تيليجرام فقط - روابط تيليجرام فقط
3. 📱 واتساب فقط - روابط واتساب فقط
4. ⚙️ مخصص - تصدير مع فلاتر متقدمة

**اختر نوع التصدير:**
"""
        
        await update.message.reply_text(export_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def add_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addsession command"""
        user = update.effective_user
        
        # التحقق من عدد الجلسات
        db = await EnhancedDatabaseManager.get_instance()
        user_stats = await db.get_user_stats(user.id)
        
        if user_stats and user_stats.get('session_count', 0) >= Config.MAX_SESSIONS_PER_USER:
            await update.message.reply_text(f"❌ لقد وصلت للحد الأقصى من الجلسات ({Config.MAX_SESSIONS_PER_USER})")
            return
        
        await update.message.reply_text(
            "➕ **إضافة جلسة جديدة**\n\n"
            "أرسل لي سلسلة الجلسة (session string) الخاصة بحساب تيليجرام.\n\n"
            "**ملاحظات:**\n"
            "• الجلسة سوف تُشفّر لحماية بياناتك\n"
            "• يمكنك إضافة حتى 20 جلسة\n"
            "• تأكد من أن الجلسة مفعلة وصالحة\n\n"
            "**لإلغاء العملية:** أرسل /cancel",
            parse_mode="Markdown"
        )
        
        # حفظ حالة المستخدم
        self.user_states[user.id] = {'awaiting_session': True}
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user = query.from_user
        
        logger.info(f"استدعاء من {user.id}: {data}")
        
        try:
            if data == "start_collect":
                await self._handle_start_collection(query)
            elif data == "pause_collect":
                await self._handle_pause_collection(query)
            elif data == "stop_collect":
                await self._handle_stop_collection(query)
            elif data == "collect_status":
                await self._handle_collect_status(query)
            elif data == "add_session":
                await self._handle_add_session(query)
            elif data == "list_sessions":
                await self._handle_list_sessions(query)
            elif data == "export_links":
                await self._handle_export_links(query)
            elif data == "show_stats":
                await self._handle_show_stats(query)
            elif data == "show_help":
                await self._handle_show_help(query)
            elif data == "show_settings":
                await self._handle_show_settings(query)
            elif data == "main_menu":
                await self._handle_main_menu(query)
            elif data == "refresh_status":
                await self._handle_refresh_status(query)
            elif data == "refresh_stats":
                await self._handle_refresh_stats(query)
            elif data == "refresh_sessions":
                await self._handle_refresh_sessions(query)
            elif data == "export_all":
                await self._handle_export_all(query)
            elif data == "export_telegram":
                await self._handle_export_telegram(query)
            elif data == "export_whatsapp":
                await self._handle_export_whatsapp(query)
            elif data == "export_custom":
                await self._handle_export_custom(query)
            elif data == "manage_sessions":
                await self._handle_manage_sessions(query)
            elif data == "detailed_stats":
                await self._handle_detailed_stats(query)
            elif data == "export_stats":
                await self._handle_export_stats(query)
            else:
                await query.edit_message_text("❌ أمر غير معروف")
        
        except Exception as e:
            logger.error(f"خطأ في معالجة الاستدعاء: {e}", exc_info=True)
            await query.edit_message_text(f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_start_collection(self, query):
        """Handle start collection"""
        if self.collection_manager.active:
            await query.edit_message_text("⏳ الجمع يعمل بالفعل")
            return
        
        # بدء الجمع في خلفية منفصلة
        asyncio.create_task(self.collection_manager.start_collection())
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
            [InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(
            "🚀 **بدأت عملية الجمع**\n\n"
            "جاري جمع الروابط من جميع الجلسات...\n\n"
            "**معلومات:**\n"
            "• سيتم جمع روابط تيليجرام بدون قيود\n"
            "• روابط واتساب من آخر 30 يوماً فقط\n"
            "• يتم التحقق من الروابط تلقائياً\n\n"
            "يمكنك مراقبة التقدم باستخدام زر 📊 حالة الجمع",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_pause_collection(self, query):
        """Handle pause collection"""
        if not self.collection_manager.active:
            await query.edit_message_text("⚠️ الجمع غير نشط")
            return
        
        if self.collection_manager.paused:
            await self.collection_manager.resume()
            status = "▶️ تم استئناف الجمع"
        else:
            await self.collection_manager.pause()
            status = "⏸️ تم إيقاف الجمع مؤقتاً"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 استئناف" if self.collection_manager.paused else "⏸️ إيقاف مؤقت", 
                                 callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(
            f"{status}\n\n"
            "**الحالة الحالية:**\n"
            f"• النشط: {'نعم' if self.collection_manager.active else 'لا'}\n"
            f"• الإيقاف المؤقت: {'نعم' if self.collection_manager.paused else 'لا'}\n"
            f"• الروابط المجمعة: {self.collection_manager.stats['total_collected']:,}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_stop_collection(self, query):
        """Handle stop collection"""
        if not self.collection_manager.active:
            await query.edit_message_text("⚠️ الجمع غير نشط")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تأكيد الإيقاف", callback_data="confirm_stop")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="collect_status")]
        ])
        
        await query.edit_message_text(
            "⏹️ **تأكيد إيقاف الجمع**\n\n"
            "هل أنت متأكد من إيقاف عملية الجمع؟\n\n"
            "**سيؤدي هذا إلى:**\n"
            "• إيقاف جمع الروابط فوراً\n"
            "• حفظ جميع الروابط المجمعة\n"
            "• إغلاق جميع اتصالات الجلسات\n\n"
            f"**الإحصائيات الحالية:**\n"
            f"• الروابط المجمعة: {self.collection_manager.stats['total_collected']:,}\n"
            f"• دورات الجمع: {self.collection_manager.stats['cycles_completed']:,}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_collect_status(self, query):
        """Handle collect status"""
        status = self.collection_manager.get_status()
        
        status_text = f"""
📊 **حالة الجمع التفصيلية**

**الحالة:** {"🔄 نشط" if status['active'] else "🛑 متوقف"}
**الإيقاف المؤقت:** {"⏸️ نعم" if status['paused'] else "▶️ لا"}

**الإحصائيات:**
• الروابط المجمعة: {status['stats']['total_collected']:,}
• دورات الجمع: {status['stats']['cycles_completed']:,}
• الأخطاء: {status['stats']['errors']:,}

**تفصيل تيليجرام:**
• المجموعات العامة: {status['stats']['telegram_public']:,}
• المجموعات الخاصة: {status['stats']['telegram_private']:,}
• طلبات الانضمام: {status['stats']['telegram_join']:,}
• القنوات: {status['stats']['telegram_channels']:,}
• المجموعات العادية: {status['stats']['telegram_groups']:,}
• المجموعات الخارقة: {status['stats']['telegram_supergroups']:,}

**المنصات الأخرى:**
• واتساب: {status['stats']['whatsapp_groups']:,}
• ديسكورد: {status['stats']['discord_invites']:,}
• سيجنال: {status['stats']['signal_groups']:,}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="collect_status")],
            [InlineKeyboardButton("⏸️ إيقاف مؤقت" if not status['paused'] else "▶️ استئناف", 
                                 callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_add_session(self, query):
        """Handle add session"""
        user = query.from_user
        
        # التحقق من عدد الجلسات
        db = await EnhancedDatabaseManager.get_instance()
        user_stats = await db.get_user_stats(user.id)
        
        if user_stats and user_stats.get('session_count', 0) >= Config.MAX_SESSIONS_PER_USER:
            await query.edit_message_text(f"❌ لقد وصلت للحد الأقصى من الجلسات ({Config.MAX_SESSIONS_PER_USER})")
            return
        
        await query.edit_message_text(
            "➕ **إضافة جلسة جديدة**\n\n"
            "أرسل لي سلسلة الجلسة (session string) الخاصة بحساب تيليجرام.\n\n"
            "**كيفية الحصول على سلسلة الجلسة:**\n"
            "1. اذهب إلى @genStr_robot على تيليجرام\n"
            "2. اتبع التعليمات للحصول على سلسلة الجلسة\n"
            "3. أرسل السلسلة هنا\n\n"
            "**ملاحظات:**\n"
            "• الجلسة سوف تُشفّر لحماية بياناتك\n"
            "• يمكنك إضافة حتى 20 جلسة\n"
            "• تأكد من أن الجلسة مفعلة وصالحة\n\n"
            "**لإلغاء العملية:** أرسل /cancel",
            parse_mode="Markdown"
        )
        
        # حفظ حالة المستخدم
        self.user_states[user.id] = {'awaiting_session': True}
    
    async def _handle_list_sessions(self, query):
        """Handle list sessions"""
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=10)
        
        if not sessions:
            await query.edit_message_text("📭 لا توجد جلسات مضافة")
            return
        
        sessions_text = f"""
👥 **الجلسات النشطة - {len(sessions)} جلسة**

"""
        
        for i, session in enumerate(sessions, 1):
            display_name = session.get('display_name', 'غير معروف')
            username = session.get('username', 'لا يوجد')
            uses = session.get('total_uses', 0)
            links = session.get('total_links', 0)
            health = session.get('health_score', 0)
            
            sessions_text += f"""
**#{i} - {display_name}**
• المستخدم: @{username}
• الاستخدامات: {uses:,}
• الروابط: {links:,}
• الصحة: {health}/100
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("🗑️ إدارة الجلسات", callback_data="manage_sessions")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="list_sessions")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(sessions_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_export_links(self, query):
        """Handle export links"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 تصدير جميع الروابط", callback_data="export_all")],
            [InlineKeyboardButton("📢 تصدير تيليجرام فقط", callback_data="export_telegram")],
            [InlineKeyboardButton("📱 تصدير واتساب فقط", callback_data="export_whatsapp")],
            [InlineKeyboardButton("⚙️ تصدير مخصص", callback_data="export_custom")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(
            f"""
📤 **نظام التصدير المتقدم**

**الحدود:**
• أقصى {Config.MAX_EXPORT_LINKS:,} رابط للتصدير
• تصدير بتصنيفات مختلفة
• حفظ تلقائي للملفات

**خيارات التصدير:**
1. 📤 جميع الروابط - تصدير كل الروابط المجمعة
2. 📢 تيليجرام فقط - روابط تيليجرام فقط
3. 📱 واتساب فقط - روابط واتساب فقط
4. ⚙️ مخصص - تصدير مع فلاتر متقدمة

**اختر نوع التصدير:**
""",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_export_all(self, query):
        """Handle export all links"""
        await query.edit_message_text("📤 جاري تصدير جميع الروابط...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links, metadata = await db.export_links_enhanced(limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await query.edit_message_text("📭 لا توجد روابط للتصدير")
                return
            
            # إنشاء ملف التصدير
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"export_all_{timestamp}.txt"
            filepath = os.path.join("exports", filename)
            
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(link + '\n')
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"""
📤 **تم تصدير الروابط بنجاح**

**تفاصيل التصدير:**
• عدد الروابط: {len(links):,}
• إجمالي الروابط في قاعدة البيانات: {metadata.get('total_count', 0):,}
• وقت التصدير: {timestamp}

**التوزيع:**
{chr(10).join(f'• {platform}: {count:,}' for platform, count in metadata.get('platform_distribution', {}).items())}
""",
                    parse_mode="Markdown"
                )
            
            await query.delete_message()
            
        except Exception as e:
            logger.error(f"خطأ في التصدير: {e}", exc_info=True)
            await query.edit_message_text(f"❌ خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_telegram(self, query):
        """Handle export telegram links"""
        await query.edit_message_text("📢 جاري تصدير روابط تيليجرام...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links, metadata = await db.export_links_enhanced(
                filters={'platform': 'telegram'},
                limit=Config.MAX_EXPORT_LINKS
            )
            
            if not links:
                await query.edit_message_text("📭 لا توجد روابط تيليجرام للتصدير")
                return
            
            # إنشاء ملف التصدير
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"export_telegram_{timestamp}.txt"
            filepath = os.path.join("exports", filename)
            
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(link + '\n')
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"""
📢 **تم تصدير روابط تيليجرام بنجاح**

**تفاصيل التصدير:**
• عدد الروابط: {len(links):,}
• وقت التصدير: {timestamp}

**تصنيف تيليجرام:**
• القنوات: {metadata.get('telegram_classification', {}).get('channels', 0):,}
• المجموعات: {metadata.get('telegram_classification', {}).get('groups', 0):,}
• المجموعات الخارقة: {metadata.get('telegram_classification', {}).get('supergroups', 0):,}
• طلبات الانضمام: {metadata.get('telegram_classification', {}).get('join_requests', 0):,}
""",
                    parse_mode="Markdown"
                )
            
            await query.delete_message()
            
        except Exception as e:
            logger.error(f"خطأ في تصدير تيليجرام: {e}", exc_info=True)
            await query.edit_message_text(f"❌ خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_whatsapp(self, query):
        """Handle export whatsapp links"""
        await query.edit_message_text("📱 جاري تصدير روابط واتساب...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links, metadata = await db.export_links_enhanced(
                filters={'platform': 'whatsapp'},
                limit=Config.MAX_EXPORT_LINKS
            )
            
            if not links:
                await query.edit_message_text("📭 لا توجد روابط واتساب للتصدير")
                return
            
            # إنشاء ملف التصدير
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"export_whatsapp_{timestamp}.txt"
            filepath = os.path.join("exports", filename)
            
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(link + '\n')
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"""
📱 **تم تصدير روابط واتساب بنجاح**

**تفاصيل التصدير:**
• عدد الروابط: {len(links):,}
• وقت التصدير: {timestamp}

**ملاحظة:** الروابط من آخر {Config.WHATSAPP_DAYS_BACK} يوم فقط
""",
                    parse_mode="Markdown"
                )
            
            await query.delete_message()
            
        except Exception as e:
            logger.error(f"خطأ في تصدير واتساب: {e}", exc_info=True)
            await query.edit_message_text(f"❌ خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_custom(self, query):
        """Handle custom export"""
        await query.edit_message_text(
            "⚙️ **التصدير المخصص**\n\n"
            "سيتم إضافة هذه الميزة قريباً...\n\n"
            "حالياً يمكنك استخدام:\n"
            "• 📤 تصدير جميع الروابط\n"
            "• 📢 تصدير تيليجرام فقط\n"
            "• 📱 تصدير واتساب فقط",
            parse_mode="Markdown"
        )
    
    async def _handle_show_stats(self, query):
        """Handle show stats"""
        await self._handle_refresh_stats(query)
    
    async def _handle_show_help(self, query):
        """Handle show help"""
        help_text = """
❓ **دليل استخدام البوت**

**الأوامر الرئيسية:**
/start - بدء البوت وعرض القائمة الرئيسية
/help - عرض رسالة المساعدة
/status - عرض حالة النظام
/stats - عرض إحصائيات الروابط
/sessions - عرض الجلسات المضافة
/collect - بدء/إيقاف عملية الجمع
/export - تصدير الروابط
/addsession - إضافة جلسة جديدة

**كيفية الاستخدام:**
1. أضف جلسات تيليجرام أولاً
2. ابدأ عملية الجمع
3. قم بتصدير الروابط المجمعة

**مميزات النظام:**
• جمع روابط تيليجرام بدون قيود
• جمع روابط واتساب من آخر 30 يوماً
• تصدير الروابط بتصنيفات مختلفة
• إدارة متعددة للجلسات
• إحصائيات مفصلة

**للتواصل والدعم:** @username
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(help_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_show_settings(self, query):
        """Handle show settings"""
        settings_text = f"""
⚙️ **إعدادات النظام**

**الإعدادات الحالية:**
• الحد الأقصى للجلسات: {Config.MAX_CONCURRENT_SESSIONS}
• أقصى تصدير روابط: {Config.MAX_EXPORT_LINKS:,}
• أقصى جلسات لكل مستخدم: {Config.MAX_SESSIONS_PER_USER}
• أيام واتساب الخلفية: {Config.WHATSAPP_DAYS_BACK}
• جمع تيليجرام: {'غير محدود' if Config.TELEGRAM_NO_TIME_LIMIT else 'محدود'}

**إعدادات الأداء:**
• تأخير الدورة: {Config.REQUEST_DELAYS['min_cycle_delay']}-{Config.REQUEST_DELAYS['max_cycle_delay']} ثانية
• تأخير بين الجلسات: {Config.REQUEST_DELAYS['between_sessions']} ثانية
• تأخير الفيضان: {Config.REQUEST_DELAYS['flood_wait']} ثانية

**ملاحظة:** هذه الإعدادات محددة في البيئة ولا يمكن تغييرها من البوت.
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(settings_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_main_menu(self, query):
        """Handle main menu"""
        user = query.from_user
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect"),
             InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="stop_collect"),
             InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status")],
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("👥 الجلسات", callback_data="list_sessions")],
            [InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_links"),
             InlineKeyboardButton("📈 الإحصائيات", callback_data="show_stats")],
            [InlineKeyboardButton("❓ المساعدة", callback_data="show_help"),
             InlineKeyboardButton("⚙️ الإعدادات", callback_data="show_settings")]
        ])
        
        await query.edit_message_text(
            f"🤖 **مرحباً {user.first_name}!**\n\n"
            "**بوت جمع روابط المجموعات المتقدم**\n\n"
            "✨ **المميزات:**\n"
            "• جمع روابط تيليجرام (مجموعات، قنوات، دعوات)\n"
            "• جمع روابط واتساب (آخر 30 يوماً)\n"
            "• تصدير الروابط بصيغة TXT\n"
            "• إدارة متعددة للجلسات\n"
            "• إحصائيات مفصلة\n\n"
            "🚀 **اختر من القائمة:**",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_refresh_status(self, query):
        """Handle refresh status"""
        await self._handle_collect_status(query)
    
    async def _handle_refresh_stats(self, query):
        """Handle refresh stats"""
        db = await EnhancedDatabaseManager.get_instance()
        stats = await db.get_stats_summary_enhanced(detailed=True)
        
        stats_text = f"""
📈 **إحصائيات شاملة - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**

**🔗 إجمالي الروابط: {stats.get('total_links', 0):,}**

**📊 التوزيع حسب المنصة:**
"""
        
        for platform, count in stats.get('links_by_platform', {}).items():
            stats_text += f"• {platform}: {count:,}\n"
        
        # النشاط اليومي
        daily_activity = stats.get('daily_activity', {})
        if daily_activity:
            stats_text += "\n**📅 النشاط اليومي (آخر 7 أيام):**\n"
            for date, count in list(daily_activity.items())[:3]:
                stats_text += f"• {date}: {count:,}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_stats"),
             InlineKeyboardButton("📤 تصدير", callback_data="export_stats")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(stats_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_refresh_sessions(self, query):
        """Handle refresh sessions"""
        await self._handle_list_sessions(query)
    
    async def _handle_manage_sessions(self, query):
        """Handle manage sessions"""
        await query.edit_message_text(
            "🗑️ **إدارة الجلسات**\n\n"
            "سيتم إضافة هذه الميزة قريباً...\n\n"
            "حالياً يمكنك:\n"
            "• عرض الجلسات الحالية\n"
            "• إضافة جلسات جديدة\n"
            "• تحديث قائمة الجلسات",
            parse_mode="Markdown"
        )
    
    async def _handle_detailed_stats(self, query):
        """Handle detailed stats"""
        db = await EnhancedDatabaseManager.get_instance()
        stats = await db.get_stats_summary_enhanced(detailed=True)
        
        detailed_text = f"""
📊 **إحصائيات مفصلة - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**

**🔗 إجمالي الروابط: {stats.get('total_links', 0):,}**
• الروابط النشطة: {stats.get('active_links', 0):,}
• الروابط المؤكدة: {stats.get('verified_links', 0):,}
• روابط تحتاج انضمام: {stats.get('requires_join', 0):,}

**📊 التوزيع حسب المنصة:**
"""
        
        for platform, count in stats.get('links_by_platform', {}).items():
            percentage = (count / max(1, stats.get('total_links', 1))) * 100
            detailed_text += f"• {platform}: {count:,} ({percentage:.1f}%)\n"
        
        # أفضل المستخدمين
        top_users = stats.get('top_users', [])
        if top_users:
            detailed_text += "\n**🏆 أفضل 5 مستخدمين:**\n"
            for i, user in enumerate(top_users[:5], 1):
                username = user.get('username', f"user_{user.get('user_id')}")
                detailed_text += f"{i}. @{username}: {user.get('link_count', 0):,} رابط\n"
        
        # أفضل الجلسات
        top_sessions = stats.get('top_sessions', [])
        if top_sessions:
            detailed_text += "\n**🔥 أفضل 5 جلسات:**\n"
            for i, session in enumerate(top_sessions[:5], 1):
                display_name = session.get('display_name', 'غير معروف')
                detailed_text += f"{i}. {display_name}: {session.get('link_count', 0):,} رابط\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="detailed_stats")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(detailed_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_export_stats(self, query):
        """Handle export stats"""
        await query.edit_message_text(
            "📊 **تصدير الإحصائيات**\n\n"
            "سيتم إضافة هذه الميزة قريباً...\n\n"
            "حالياً يمكنك:\n"
            "• عرض الإحصائيات\n"
            "• تحديث الإحصائيات\n"
            "• تصدير الروابط الفعلية",
            parse_mode="Markdown"
        )
    
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        user = update.effective_user
        message_text = update.message.text
        
        # التحقق من حالة المستخدم
        if user.id in self.user_states and self.user_states[user.id].get('awaiting_session'):
            # إلغاء إذا كان النص /cancel
            if message_text.lower() == '/cancel':
                del self.user_states[user.id]
                await update.message.reply_text("❌ تم إلغاء إضافة الجلسة")
                return
            
            # معالجة إضافة الجلسة
            await self._process_session_addition(update, message_text)
            return
        
        # رد عام على الرسائل
        await update.message.reply_text(
            "🤖 **بوت جمع روابط المجموعات**\n\n"
            "استخدم /start لرؤية القائمة الرئيسية\n"
            "أو /help لعرض دليل الاستخدام",
            parse_mode="Markdown"
        )
    
    async def _process_session_addition(self, update: Update, session_string: str):
        """Process session addition"""
        user = update.effective_user
        
        await update.message.reply_text("🔍 جاري التحقق من الجلسة...")
        
        # التحقق من الجلسة
        is_valid, validation_info = await SessionManager.validate_session(session_string)
        
        if not is_valid:
            error_msg = validation_info.get('error', 'خطأ غير معروف')
            error_details = validation_info.get('details', '')
            
            await update.message.reply_text(
                f"❌ **خطأ في التحقق من الجلسة**\n\n"
                f"**الخطأ:** {error_msg}\n"
                f"**التفاصيل:** {error_details}\n\n"
                "يرجى التأكد من صحة سلسلة الجلسة وإعادة المحاولة.",
                parse_mode="Markdown"
            )
            
            # حذف حالة المستخدم
            if user.id in self.user_states:
                del self.user_states[user.id]
            
            return
        
        # جلسة صالحة، جاري إضافتها
        user_info = validation_info.get('user_info', {})
        
        # تشفير الجلسة
        enc_manager = EncryptionManager.get_instance()
        encrypted_session = enc_manager.encrypt_session(session_string)
        session_hash = hashlib.md5(encrypted_session.encode()).hexdigest()
        
        # إضافة الجلسة إلى قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        
        try:
            await db.conn.execute('''
                INSERT INTO sessions 
                (session_string, session_hash, phone_number, user_id, username, 
                 display_name, added_by_user, is_active, added_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                encrypted_session,
                session_hash,
                user_info.get('phone', ''),
                user_info.get('id', 0),
                user_info.get('username', ''),
                f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip(),
                user.id,
                1
            ))
            
            await db.conn.commit()
            
            # تحديث إحصائيات المستخدم
            await db.update_user_stats(user.id, 'session_added')
            
            # حذف حالة المستخدم
            if user.id in self.user_states:
                del self.user_states[user.id]
            
            await update.message.reply_text(
                f"✅ **تمت إضافة الجلسة بنجاح**\n\n"
                f"**المستخدم:** {user_info.get('first_name', '')} {user_info.get('last_name', '')}\n"
                f"**اسم المستخدم:** @{user_info.get('username', 'لا يوجد')}\n"
                f"**الهاتف:** {user_info.get('phone', 'غير معروف')}\n\n"
                "يمكنك الآن بدء عملية الجمع باستخدام زر 🚀 بدء الجمع",
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الجلسة: {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ **خطأ في إضافة الجلسة**\n\n"
                f"**التفاصيل:** {str(e)[:200]}\n\n"
                "يرجى المحاولة مرة أخرى أو التواصل مع الدعم.",
                parse_mode="Markdown"
            )
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        try:
            error = context.error
            
            # التعامل مع Conflict error (تعدد نسخ البوت)
            if isinstance(error, Conflict):
                logger.warning("⚠️ تم اكتشاف نسخة أخرى من البوت تعمل. جاري إعادة التشغيل...")
                
                # محاولة إيقاف البوت الحالي بلطف
                if self.app:
                    await self.app.stop()
                
                # إعادة التشغيل بعد تأخير
                await asyncio.sleep(5)
                
                # إعادة تهيئة البوت
                await self.initialize()
                await self.app.initialize()
                await self.app.start()
                
                logger.info("✅ تم إعادة تشغيل البوت بنجاح")
                return
            
            logger.error(f"خطأ غير معالج في البوت: {error}", exc_info=True)
            
            # تسجيل الخطأ في قاعدة البيانات
            try:
                db = await EnhancedDatabaseManager.get_instance()
                await db.conn.execute('''
                    INSERT INTO error_log (error_type, error_message, stack_trace, user_id, command)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    error.__class__.__name__,
                    str(error),
                    ''.join(traceback.format_exception(type(error), error, error.__traceback__)),
                    update.effective_user.id if update and update.effective_user else 0,
                    update.message.text if update and update.message else 'unknown'
                ))
                
                await db.conn.commit()
            except Exception as db_error:
                logger.error(f"خطأ في تسجيل الخطأ في قاعدة البيانات: {db_error}")
            
            # إرسال رسالة خطأ للمستخدم
            if update and update.effective_chat:
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ **حدث خطأ غير متوقع**\n\nلقد واجهنا مشكلة فنية. تم تسجيل الخطأ وسنعمل على حله قريباً.\n\nيرجى المحاولة مرة أخرى بعد قليل.",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
            
        except Exception as e:
            logger.error(f"خطأ في معالج الأخطاء: {e}", exc_info=True)
    
    async def start_bot(self):
        """Start the bot"""
        if not self.app:
            await self.initialize()
        
        try:
            await self.app.initialize()
            await self.app.start()
            logger.info("🚀 بدأ تشغيل البوت بنجاح")
            
            # الحفاظ على البوت يعمل
            await self.app.updater.start_polling()
            
            # انتظار حتى انتهاء البوت
            await asyncio.Event().wait()
            
        except Exception as e:
            logger.error(f"❌ خطأ في تشغيل البوت: {e}", exc_info=True)
            raise
    
    async def stop_bot(self):
        """Stop the bot gracefully"""
        if self.app:
            logger.info("🧹 جاري إيقاف البوت بلطف...")
            await self.app.stop()
            self.bot_running = False
            logger.info("✅ تم إيقاف البوت بنجاح")

# ======================
# Health Check Server - خادم فحص الصحة
# ======================

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

class HealthCheckServer:
    """Health check server for Render"""
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.app = FastAPI(title="Telegram Link Collector Health")
        self._setup_routes()
        self.server_thread = None
        
    def _setup_routes(self):
        """Setup routes"""
        
        @self.app.get("/")
        async def root():
            return {"status": "running", "service": "Telegram Link Collector"}
        
        @self.app.get("/health")
        async def health():
            try:
                # التحقق من توفر البوت
                bot_ok = True  # نفترض أن البوت يعمل
                
                # التحقق من قاعدة البيانات
                db_ok = os.path.exists(Config.DB_PATH)
                
                # التحقق من الذاكرة
                memory_ok = MemoryManager.get_instance().get_memory_percent() < 90
                
                status = {
                    "status": "healthy" if all([bot_ok, db_ok, memory_ok]) else "degraded",
                    "timestamp": datetime.now().isoformat(),
                    "checks": {
                        "bot": bot_ok,
                        "database": db_ok,
                        "memory": memory_ok,
                        "memory_percent": MemoryManager.get_instance().get_memory_percent(),
                        "memory_mb": MemoryManager.get_instance().get_memory_usage()
                    }
                }
                
                if status["status"] == "healthy":
                    return JSONResponse(status_code=200, content=status)
                else:
                    return JSONResponse(status_code=503, content=status)
                
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    }
                )
        
        @self.app.get("/metrics")
        async def metrics():
            try:
                metrics_data = {
                    "timestamp": datetime.now().isoformat(),
                    "memory": MemoryManager.get_instance().get_metrics(),
                    "cache": CacheManager.get_instance().get_stats(),
                    "system": {
                        "python_version": sys.version,
                        "platform": sys.platform,
                        "uptime_seconds": (datetime.now() - datetime.fromtimestamp(psutil.boot_time())).total_seconds()
                    }
                }
                return JSONResponse(status_code=200, content=metrics_data)
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={"error": str(e)}
                )
    
    def start(self):
        """Start server"""
        def run_server():
            uvicorn.run(
                self.app,
                host="0.0.0.0",
                port=self.port,
                log_level="warning",
                access_log=False
            )
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        logger.info(f"بدأ خادم فحص الصحة على المنفذ {self.port}")
    
    def stop(self):
        """Stop server"""
        if self.server_thread:
            logger.info("إيقاف خادم فحص الصحة")

# ======================
# Signal Handlers - معالجات الإشارات
# ======================

def setup_signal_handlers():
    """Setup signal handlers"""
    def signal_handler(signum, frame):
        logger.info(f"📶 تم استقبال إشارة {signum}. جاري الإغلاق السلس...")
        
        logger.info("📊 إحصائيات النظام النهائية:")
        
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# ======================
# Main Function - الوظيفة الرئيسية
# ======================

async def main():
    """Main function"""
    setup_signal_handlers()
    
    # إعدادات النظام
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_NOFILE, (16384, 16384))
        logger.info("✅ تم تعيين حدود الملفات المفتوحة المحسنة")
    except:
        logger.warning("⚠️ لم يتمكن من تعيين حدود الملفات المفتوحة")
    
    # التحقق من المتغيرات البيئية
    required_env_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH']
    missing = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing:
        logger.error(f"❌ متغيرات بيئية مفقودة: {missing}")
        print(f"❌ خطأ: المتغيرات البيئية التالية مفقودة: {', '.join(missing)}")
        print("يرجى تعيينها قبل التشغيل:")
        for var in missing:
            print(f"export {var}=قيمتك_هنا")
        sys.exit(1)
    
    if Config.ENCRYPTION_KEY == Fernet.generate_key().decode():
        logger.warning("⚠️ استخدام مفتاح تشفير مؤقت. يوصى بتعيين ENCRYPTION_KEY دائم")
    
    # إنشاء المجلدات المطلوبة
    os.makedirs("backups", exist_ok=True)
    os.makedirs("cache_data", exist_ok=True)
    os.makedirs("exports", exist_ok=True)
    
    # بدء خادم فحص الصحة
    health_server = HealthCheckServer(port=8080)
    health_server.start()
    
    # بدء البوت
    bot = AdvancedTelegramBot()
    
    logger.info("🤖 بدء تشغيل بوت جمع الروابط الذكي المتقدم...")
    logger.info(f"🔥 الإعدادات - max_sessions: {Config.MAX_CONCURRENT_SESSIONS}, max_export_links: {Config.MAX_EXPORT_LINKS}")
    
    try:
        # تشغيل الصيانة الدورية
        asyncio.create_task(periodic_maintenance())
        
        # بدء البوت
        await bot.start_bot()
        
    except Exception as e:
        logger.error(f"❌ خطأ في البوت: {e}", exc_info=True)
        raise
        
    finally:
        logger.info("🧹 جاري التنظيف النهائي...")
        
        try:
            await bot.stop_bot()
            
            globals_instance = await GlobalInstances.get_instance()
            await globals_instance.db_manager.close()
            
            health_server.stop()
            
            logger.info("✅ اكتمل الإغلاق السلس")
            
        except Exception as e:
            logger.error(f"❌ خطأ في التنظيف النهائي: {e}")

async def periodic_maintenance():
    """Periodic maintenance"""
    while True:
        try:
            cache_manager = CacheManager.get_instance()
            await cache_manager.cleanup_expired()
            
            memory_manager = MemoryManager.get_instance()
            memory_manager.check_and_optimize()
            
            if Config.BACKUP_ENABLED:
                await BackupManager.rotate_backups()
            
            logger.debug("✅ الصيانة الدورية مكتملة")
            
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"خطأ في الصيانة الدورية: {e}")
            await asyncio.sleep(60)

# ======================
# Entry Point - نقطة الدخول
# ======================

if __name__ == "__main__":
    # 🔧 تثبيت الحزم المطلوبة
    def install_required_packages():
        """تثبيت الحزم المطلوبة"""
        required = [
            'python-telegram-bot==21.1',
            'Telethon==1.34.0',
            'aiosqlite==0.19.0',
            'aiofiles==23.2.1',
            'cryptography==42.0.5',
            'psutil==5.9.8',
            'aiohttp==3.11.3',
            'fastapi==0.104.1',
            'uvicorn==0.24.0',
            'httpx==0.25.2',
            'pytz==2023.3'
        ]
        
        for package in required:
            pkg_name = package.split('==')[0]
            try:
                __import__(pkg_name.replace('-', '_'))
            except ImportError:
                print(f"📦 تثبيت {package}...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    
    install_required_packages()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 توقف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ قاتل: {e}", exc_info=True)
        sys.exit(1)
