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
import random
import time
from typing import List, Dict, Set, Optional, Tuple, Any, Deque
from datetime import datetime, timedelta
from collections import OrderedDict, defaultdict, deque
from urllib.parse import urlparse, parse_qs, urlencode
import aiohttp
from contextlib import asynccontextmanager
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from concurrent.futures import ThreadPoolExecutor

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
from telegram.error import TelegramError
from telegram.constants import ParseMode
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
    DB_PATH = os.getenv("DB_PATH", "links_collector.db")
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10
    DB_POOL_SIZE = 10
    
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
    
    # Webhook settings for Render
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
    WEBHOOK_PORT = int(os.getenv("PORT", 10000))
    
    # HTTPS settings
    SSL_CERT_PATH = os.getenv("SSL_CERT_PATH", "")
    SSL_KEY_PATH = os.getenv("SSL_KEY_PATH", "")

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
                logger.debug(f"Domain not allowed: {domain}")
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
            logger.debug(f"Error normalizing URL {original_url}: {e}")
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
            logger.debug(f"Error extracting URL info: {e}")
        
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
            
            # محاولة تحديد النوع من الباقي
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
            
            # استثناء الروابط الخاصة
            if username.startswith('+'):
                result['is_join_request'] = True
                result['is_private'] = True
                result['invite_hash'] = username[1:]
                result['is_group'] = True
                result['is_valid'] = True
            else:
                # افتراض مجموعة عامة
                result['is_group'] = True
                result['is_public'] = True
                result['is_valid'] = True
                result['is_supergroup'] = True
        
        # كشف المجموعات مع مسار أطول
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
                # افتراض مجموعة عامة
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
                result['reason'] = 'Invalid URL'
                return result
            
            # التحقق من روابط الانضمام
            if details.get('is_join_request') and check_join_request:
                try:
                    invite_hash = details.get('invite_hash', '')
                    if invite_hash:
                        # محاولة الانضمام لتحقق
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
                        result['reason'] = 'No invite hash'
                except InviteHashInvalidError:
                    result['reason'] = 'Invalid invite link'
                except InviteHashExpiredError:
                    result['reason'] = 'Expired invite link'
                except Exception as e:
                    result['reason'] = f'Verification error: {str(e)[:50]}'
            
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
                        result['reason'] = 'Username/channel not found'
                    except ChannelPrivateError:
                        result['reason'] = 'Channel/group is private'
                    except Exception as e:
                        result['reason'] = f'Access error: {str(e)[:50]}'
            
            # التحقق من الروابط الأخرى
            else:
                result['is_valid'] = True
                result['is_active'] = True
                result['type'] = 'unknown'
                result['validation_score'] = 50
            
            return result
            
        except Exception as e:
            logger.error(f"Error in advanced link validation: {e}")
            return {
                'is_valid': False,
                'is_active': False,
                'type': 'error',
                'reason': f'Verification error: {str(e)[:50]}',
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
        
        self.connection = await aiosqlite.connect(self.db_path)
        self.connection.row_factory = aiosqlite.Row
        
        # تهيئة الجداول
        await self._create_tables()
        
        self._initialized = True
        
        logger.info(f"Database initialized - db_path: {self.db_path}, db_exists: {db_exists}")
    
    async def _get_connection(self):
        """Get database connection"""
        if not self.connection:
            self.connection = await aiosqlite.connect(self.db_path)
        
        # تمكين الميزات المتقدمة
        await self.connection.execute("PRAGMA foreign_keys = ON")
        await self.connection.execute("PRAGMA journal_mode = WAL")
        await self.connection.execute("PRAGMA synchronous = NORMAL")
        await self.connection.execute("PRAGMA cache_size = -40000")
        await self.connection.execute("PRAGMA temp_store = MEMORY")
        
        return self.connection
    
    async def _create_tables(self):
        """Create database tables with enhanced structure"""
        conn = await self._get_connection()
        
        tables = [
            '''CREATE TABLE IF NOT EXISTS sessions (
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
            )''',
            
            '''CREATE TABLE IF NOT EXISTS links (
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
            )''',
            
            '''CREATE TABLE IF NOT EXISTS collection_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_uid TEXT UNIQUE NOT NULL,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT DEFAULT 'running',
                stats TEXT,
                duration_seconds INTEGER,
                user_id INTEGER,
                metadata TEXT
            )''',
            
            '''CREATE TABLE IF NOT EXISTS bot_users (
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
            )''',
            
            '''CREATE TABLE IF NOT EXISTS system_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                metric_value TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,
                UNIQUE(metric_name, recorded_at)
            )''',
            
            '''CREATE TABLE IF NOT EXISTS error_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_type TEXT,
                error_message TEXT,
                stack_trace TEXT,
                user_id INTEGER,
                command TEXT,
                occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved BOOLEAN DEFAULT 0,
                metadata TEXT
            )''',
            
            '''CREATE TABLE IF NOT EXISTS pending_join_links (
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
            )'''
        ]
        
        for table_sql in tables:
            try:
                await conn.execute(table_sql)
            except Exception as e:
                logger.error(f"Error creating table: {e}")
        
        await conn.commit()
        
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
        
        conn = await self._get_connection()
        for index_name, index_sql in indexes:
            try:
                await conn.execute(f'CREATE INDEX IF NOT EXISTS {index_name} ON {index_sql}')
            except Exception as e:
                logger.error(f"Error creating index {index_name}: {e}")
    
    async def add_link_enhanced(self, link_info: Dict) -> Tuple[bool, str, Dict]:
        """Add link with enhanced Telegram information"""
        try:
            # استخراج معلومات الرابط
            url = link_info.get('url', '')
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return False, "Invalid URL", {}
            
            details = url_info['details']
            
            conn = await self._get_connection()
            
            # التحقق من التكرار
            cursor = await conn.execute(
                'SELECT id FROM links WHERE url_hash = ?',
                (url_info['url_hash'],)
            )
            existing = await cursor.fetchone()
            
            if existing:
                return False, "Link already exists", {'link_id': existing[0]}
            
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
            cursor = await conn.execute('''
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
            
            await conn.commit()
            
            # تحديث إحصائيات المستخدم
            if link_data['added_by_user']:
                await self.update_user_stats(link_data['added_by_user'], 'link_added')
            
            return True, "Link added successfully", {
                'link_id': link_id,
                'url_hash': url_info['url_hash']
            }
                
        except Exception as e:
            logger.error(f"Error adding enhanced link: {e}")
            return False, f"Add error: {str(e)[:100]}", {}
    
    async def add_pending_join_link(self, url: str, platform: str = 'telegram', metadata: Dict = None) -> Tuple[bool, str, Dict]:
        """Add pending join link for later verification"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return False, "Invalid URL", {}
            
            conn = await self._get_connection()
            
            # التحقق من التكرار
            cursor = await conn.execute(
                'SELECT id FROM pending_join_links WHERE url_hash = ?',
                (url_info['url_hash'],)
            )
            existing = await cursor.fetchone()
            
            if existing:
                # تحديث وقت الفحص
                await conn.execute(
                    'UPDATE pending_join_links SET last_checked = CURRENT_TIMESTAMP WHERE id = ?',
                    (existing[0],)
                )
                await conn.commit()
                return False, "Link already in pending queue", {'pending_id': existing[0]}
            
            # إضافة جديدة
            cursor = await conn.execute('''
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
            await conn.commit()
            
            return True, "Link added to pending queue", {
                'pending_id': pending_id,
                'url_hash': url_info['url_hash']
            }
                
        except Exception as e:
            logger.error(f"Error adding pending link: {e}")
            return False, f"Add error: {str(e)[:100]}", {}
    
    async def get_pending_join_links(self, limit: int = 50) -> List[Dict]:
        """Get pending join links for verification"""
        try:
            conn = await self._get_connection()
            
            cursor = await conn.execute('''
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
            logger.error(f"Error getting pending links: {e}")
            return []
    
    async def update_pending_link_status(self, pending_id: int, status: str, 
                                        metadata: Dict = None, 
                                        check_attempts: int = 1) -> bool:
        """Update pending link status"""
        try:
            conn = await self._get_connection()
            
            await conn.execute('''
                UPDATE pending_join_links 
                SET status = ?, 
                    last_checked = CURRENT_TIMESTAMP,
                    check_attempts = check_attempts + ?,
                    metadata = COALESCE(?, metadata)
                WHERE id = ?
            ''', (status, check_attempts, 
                 json.dumps(metadata) if metadata else None, 
                 pending_id))
            
            await conn.commit()
            return True
                
        except Exception as e:
            logger.error(f"Error updating pending link status: {e}")
            return False
    
    async def get_stats_summary_enhanced(self, detailed: bool = False) -> Dict:
        """Get comprehensive database statistics with Telegram breakdown"""
        try:
            stats = {}
            
            conn = await self._get_connection()
            
            # إحصائيات أساسية
            cursor = await conn.execute("SELECT COUNT(*) FROM links")
            stats['total_links'] = (await cursor.fetchone())[0]
            
            cursor = await conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            cursor = await conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            cursor = await conn.execute("SELECT COUNT(*) FROM pending_join_links WHERE status = 'pending'")
            stats['pending_join_links'] = (await cursor.fetchone())[0]
            
            # الروابط حسب المنصة
            cursor = await conn.execute(
                "SELECT platform, COUNT(*) FROM links GROUP BY platform ORDER BY COUNT(*) DESC"
            )
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            # تفصيل تيليجرام المتقدم
            cursor = await conn.execute('''
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
            
            # إحصائيات الروابط النشطة
            cursor = await conn.execute("SELECT COUNT(*) FROM links WHERE is_active = 1")
            stats['active_links'] = (await cursor.fetchone())[0]
            
            cursor = await conn.execute("SELECT COUNT(*) FROM links WHERE requires_join = 1")
            stats['requires_join'] = (await cursor.fetchone())[0]
            
            # النشاط حسب اليوم (آخر 7 أيام)
            cursor = await conn.execute('''
                SELECT DATE(collected_date) as date, COUNT(*) as count
                FROM links 
                WHERE collected_date > datetime('now', '-7 days')
                GROUP BY DATE(collected_date)
                ORDER BY date DESC
            ''')
            stats['daily_activity'] = dict(await cursor.fetchall())
            
            if detailed:
                # أفضل المستخدمين
                cursor = await conn.execute('''
                    SELECT u.user_id, u.username, COUNT(l.id) as link_count
                    FROM bot_users u
                    LEFT JOIN links l ON u.user_id = l.added_by_user
                    GROUP BY u.user_id
                    ORDER BY link_count DESC
                    LIMIT 10
                ''')
                stats['top_users'] = [dict(zip(['user_id', 'username', 'link_count'], row)) 
                                    for row in await cursor.fetchall()]
                
                # أفضل الجلسات
                cursor = await conn.execute('''
                    SELECT s.id, s.display_name, s.username, COUNT(l.id) as link_count
                    FROM sessions s
                    LEFT JOIN links l ON s.id = l.session_id
                    WHERE s.is_active = 1
                    GROUP BY s.id
                    ORDER BY link_count DESC
                    LIMIT 10
                ''')
                stats['top_sessions'] = [dict(zip(['id', 'display_name', 'username', 'link_count'], row)) 
                                       for row in await cursor.fetchall()]
                
                # إحصائيات التحقق
                cursor = await conn.execute("SELECT COUNT(*) FROM links WHERE is_verified = 1")
                stats['verified_links'] = (await cursor.fetchone())[0]
                
                cursor = await conn.execute("SELECT AVG(validation_score) FROM links WHERE validation_score > 0")
                avg_score = (await cursor.fetchone())[0]
                stats['avg_validation_score'] = float(avg_score) if avg_score else 0
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting enhanced stats summary: {e}")
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
            
            conn = await self._get_connection()
            
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            
            links = [row[0] for row in rows]
            
            metadata = {
                'total_count': len(rows),
                'exported_count': len(links),
                'limit': limit,
                'offset': offset,
                'filters': filters or {}
            }
            
            return links, metadata
            
        except Exception as e:
            logger.error(f"Error exporting enhanced links: {e}")
            return [], {}
    
    async def update_user_stats(self, user_id: int, action: str, value: int = 1):
        """Update user statistics"""
        try:
            conn = await self._get_connection()
            
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
            
            await conn.execute(update_query, params)
            await conn.commit()
            
        except Exception as e:
            logger.debug(f"Error updating user stats: {e}")
    
    async def get_active_sessions(self, limit: int = 10) -> List[Dict]:
        """Get active sessions"""
        try:
            conn = await self._get_connection()
            
            cursor = await conn.execute('''
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
            logger.error(f"Error getting active sessions: {e}")
            return []
    
    async def add_or_update_user(self, user_id: int, username: str = None, 
                                first_name: str = None, last_name: str = None):
        """Add or update user"""
        try:
            conn = await self._get_connection()
            
            cursor = await conn.execute('''
                SELECT user_id FROM bot_users WHERE user_id = ?
            ''', (user_id,))
            
            existing = await cursor.fetchone()
            
            if existing:
                await conn.execute('''
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
                await conn.execute('''
                    INSERT INTO bot_users (user_id, username, first_name, last_name, added_date)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    user_id,
                    username or '',
                    first_name or '',
                    last_name or ''
                ))
            
            await conn.commit()
        except Exception as e:
            logger.error(f"Error adding/updating user: {e}")
    
    async def get_user_stats(self, user_id: int) -> Optional[Dict]:
        """Get user statistics"""
        try:
            conn = await self._get_connection()
            
            cursor = await conn.execute('''
                SELECT *, 
                       (SELECT COUNT(*) FROM links WHERE added_by_user = ?) as total_links,
                       (SELECT COUNT(*) FROM sessions WHERE added_by_user = ?) as total_sessions
                FROM bot_users 
                WHERE user_id = ?
            ''', (user_id, user_id, user_id))
            
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return None
    
    async def close(self):
        """Close database connection"""
        if self.connection:
            await self.connection.close()
            self._initialized = False

# ======================
# Advanced Collection Manager - مدير الجمع المتقدم
# ======================

class AdvancedCollectionManager:
    """Advanced collection management with no time limits for Telegram"""
    
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
        
        self.performance = {
            'avg_processing_time': 0.0,
            'total_operations': 0,
            'cache_hit_rate': 0.0,
            'memory_usage_mb': 0.0,
            'network_latency': 0.0,
            'success_rate': 1.0,
            'concurrent_tasks': 0,
            'avg_session_duration': 0.0
        }
        
        self.whatsapp_cutoff = datetime.now() - timedelta(days=Config.WHATSAPP_DAYS_BACK)
        
        self.quality_filters = {
            'min_url_length': 10,
            'max_url_length': Config.MAX_LINK_LENGTH,
            'allowed_patterns': [
                r'^https?://(?:t\.me|telegram\.me)/[^/]+/?$',
                r'^https?://t\.me/\+\w+/?$',
                r'^https?://t\.me/joinchat/\w+/?$',
                r'^https?://chat\.whatsapp\.com/\w+/?$',
                r'^https?://discord\.gg/\w+/?$',
                r'^https?://signal\.group/\w+/?$'
            ]
        }
        
        self.system_state = {
            'memory_pressure': 'low',
            'network_status': 'good',
            'collection_mode': 'balanced',
            'last_health_check': None
        }
    
    async def start_collection(self, mode: str = 'balanced'):
        """Start the advanced collection process with improved Telegram collection"""
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.stats['start_time'] = datetime.now()
        self.stats['cycles_completed'] = 0
        self.stats['current_session'] = self.stats['start_time'].strftime('%Y%m%d_%H%M%S')
        self.system_state['collection_mode'] = mode
        
        logger.info(f"Starting advanced collection - mode: {mode}, start_time: {self.stats['start_time'].isoformat()}")
        
        try:
            while self.active and not self.stop_requested:
                if self.paused:
                    await asyncio.sleep(1)
                    continue
                
                await self._enhanced_collection_cycle()
                
                if self.active and not self.stop_requested:
                    delay = self._calculate_adaptive_delay()
                    await asyncio.sleep(delay)
        
        except Exception as e:
            logger.error(f"Error in advanced collection process: {e}")
            self.stats['errors'] += 1
        
        finally:
            await self._graceful_shutdown()
    
    async def _enhanced_collection_cycle(self):
        """Execute enhanced collection cycle with unlimited Telegram collection"""
        cycle_start = datetime.now()
        cycle_id = f"cycle_{self.stats['cycles_completed']}_{secrets.token_hex(4)}"
        
        logger.info(f"Starting enhanced collection cycle {cycle_id}")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=Config.MAX_CONCURRENT_SESSIONS * 2)
            
            if not sessions:
                logger.warning("No active sessions available")
                return
            
            healthy_sessions = [s for s in sessions if s.get('health_score', 0) > 50]
            
            if not healthy_sessions:
                logger.warning("No healthy sessions available")
                return
            
            max_sessions = min(len(healthy_sessions), Config.MAX_CONCURRENT_SESSIONS)
            selected_sessions = healthy_sessions[:max_sessions]
            
            tasks = []
            for i, session in enumerate(selected_sessions):
                if not self.active or self.stop_requested or self.paused:
                    break
                
                task = self._process_session_unlimited(session, i, cycle_id)
                tasks.append(task)
            
            if not tasks:
                return
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful = sum(1 for r in results if not isinstance(r, Exception))
            failed = len(results) - successful
            
            self.stats['cycles_completed'] += 1
            self.performance['concurrent_tasks'] = len(tasks)
            self.performance['success_rate'] = successful / max(1, len(tasks))
            
            await self._update_system_state()
            
            cycle_duration = (datetime.now() - cycle_start).total_seconds()
            self.performance['avg_session_duration'] = (
                self.performance['avg_session_duration'] * (self.stats['cycles_completed'] - 1) + cycle_duration
            ) / self.stats['cycles_completed']
            
            logger.info(f"Completed cycle {cycle_id}: {successful} successful, {failed} failed - duration: {cycle_duration}")
            
        except Exception as e:
            logger.error(f"Error in enhanced collection cycle: {e}")
            self.stats['errors'] += 1
    
    async def _process_session_unlimited(self, session: Dict, index: int, cycle_id: str):
        """Process session with unlimited Telegram collection"""
        session_id = session.get('id')
        session_hash = session.get('session_hash')
        added_by_user = session.get('added_by_user', 0)
        
        logger.info(f"Processing session {session_id} in cycle {cycle_id}")
        
        if index > 0:
            delay = Config.REQUEST_DELAYS['between_sessions'] * index
            await asyncio.sleep(delay)
        
        try:
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt_session(session.get('session_string', ''))
            actual_session = decrypted_session or session.get('session_string', '')
            
            if not actual_session or actual_session == '********':
                logger.error(f"Session {session_id} not available")
                return {'session_id': session_id, 'status': 'error', 'reason': 'Session not available'}
            
            client = TelegramClient(
                StringSession(actual_session),
                Config.API_ID,
                Config.API_HASH,
                device_model="Link Collector Pro",
                system_version="Linux 6.5",
                app_version="4.16.30",
                timeout=30,
                connection_retries=3,
                auto_reconnect=True
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                logger.error(f"Session {session_id} not authorized")
                return {'session_id': session_id, 'status': 'error', 'reason': 'Not authorized'}
            
            # جمع الروابط
            collected_links = await self._collect_all_telegram_links(client, session_id, added_by_user, cycle_id)
            
            # تحديث استخدام الجلسة
            db = await EnhancedDatabaseManager.get_instance()
            conn = await db._get_connection()
            await conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, total_uses = total_uses + 1 WHERE id = ?",
                (session_id,)
            )
            await conn.commit()
            
            await client.disconnect()
            
            return {
                'session_id': session_id,
                'status': 'success',
                'links_collected': len(collected_links),
                'collected_details': {
                    'telegram': len([l for l in collected_links if l.get('platform') == 'telegram']),
                    'whatsapp': len([l for l in collected_links if l.get('platform') == 'whatsapp']),
                    'other': len([l for l in collected_links if l.get('platform') not in ['telegram', 'whatsapp']])
                }
            }
            
        except FloodWaitError as e:
            logger.warning(f"Flood wait for session {session_id}: {e.seconds} seconds")
            self.stats['flood_waits'] += 1
            await asyncio.sleep(e.seconds + Config.REQUEST_DELAYS['flood_wait'])
            raise
            
        except Exception as e:
            logger.error(f"Error processing session {session_id}: {e}")
            self.stats['errors'] += 1
            raise
    
    async def _collect_all_telegram_links(self, client: TelegramClient, session_id: int, 
                                         added_by_user: int, cycle_id: str) -> List[Dict]:
        """Collect all Telegram links without time limits"""
        collected = []
        
        try:
            dialogs = []
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                dialogs.append(dialog)
            
            for dialog in dialogs:
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # جمع جميع أنواع الروابط من الدردشة
                    dialog_links = await self._collect_from_dialog(client, entity, session_id, added_by_user)
                    collected.extend(dialog_links)
                    
                    await asyncio.sleep(Config.REQUEST_DELAYS['normal'])
                    
                except Exception as e:
                    logger.debug(f"Error processing dialog: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error collecting Telegram links: {e}")
        
        return collected
    
    async def _collect_from_dialog(self, client: TelegramClient, entity, 
                                  session_id: int, added_by_user: int) -> List[Dict]:
        """Collect links from a specific dialog"""
        collected = []
        
        try:
            # جمع روابط من الوصف
            if hasattr(entity, 'about') and entity.about:
                links = self._extract_all_links(entity.about)
                for link in links:
                    link_info = await self._process_link_enhanced(
                        client, link, session_id, added_by_user
                    )
                    if link_info:
                        collected.append(link_info)
            
            # جمع الروابط من الرسائل الحديثة
            try:
                async for message in client.iter_messages(entity, limit=5):
                    if not message.text:
                        continue
                    
                    links = self._extract_all_links(message.text)
                    for link in links:
                        link_info = await self._process_link_enhanced(
                            client, link, session_id, added_by_user,
                            message.date if hasattr(message, 'date') else None
                        )
                        if link_info:
                            collected.append(link_info)
                    
                    if len(collected) >= 3:
                        break
            except:
                pass
        
        except Exception as e:
            logger.debug(f"Error collecting links from dialog: {e}")
        
        return collected
    
    async def _process_link_enhanced(self, client: TelegramClient, url: str, 
                                    session_id: int, added_by_user: int,
                                    message_date=None) -> Optional[Dict]:
        """Process link with enhanced Telegram validation"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return None
            
            platform = url_info['platform']
            
            # تطبيق قيود زمنية فقط لواتساب
            if platform == 'whatsapp' and message_date:
                if message_date < self.whatsapp_cutoff:
                    return None
            
            # التحقق المتقدم لروابط تيليجرام
            if platform == 'telegram' and Config.ENABLE_ADVANCED_VALIDATION:
                validated = await EnhancedLinkProcessor.validate_telegram_link_advanced(
                    client, url, check_join_request=False
                )
            else:
                validated = {'is_valid': True, 'is_active': True}
            
            if validated.get('is_valid', False) and validated.get('is_active', True):
                link_info = self._create_link_info(url, url_info, validated, session_id, added_by_user, message_date)
                
                # تحديث الإحصائيات
                self._update_collection_stats_enhanced(url_info, validated)
                
                # إضافة الرابط للقاعدة
                db = await EnhancedDatabaseManager.get_instance()
                success, message, _ = await db.add_link_enhanced(link_info)
                
                if success:
                    return link_info
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing enhanced link {url}: {e}")
            return None
    
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
                'verification_method': validated.get('method', 'enhanced'),
                'is_channel': validated.get('is_channel', False),
                'is_group': validated.get('is_group', True),
                'is_supergroup': validated.get('is_supergroup', False),
                'is_join_request': details.get('is_join_request', False)
            },
            'tags': [],
            'source': 'collection'
        }
    
    def _update_collection_stats_enhanced(self, url_info: Dict, validation: Dict):
        """Update collection statistics with enhanced Telegram classification"""
        platform = url_info['platform']
        
        if platform == 'telegram':
            link_type = validation.get('type', 'unknown')
            
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
        
        # تصفية وتحسين الروابط
        filtered_links = []
        for link in all_links:
            link = link.strip()
            if link.startswith('+') and len(link) > 5:
                link = f"https://t.me/{link}"
            filtered_links.append(link)
        
        return list(set(filtered_links))
    
    async def _update_system_state(self):
        """Update system state"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_percent = process.memory_percent()
            
            if memory_percent > 85:
                self.system_state['memory_pressure'] = 'high'
            elif memory_percent > 70:
                self.system_state['memory_pressure'] = 'medium'
            else:
                self.system_state['memory_pressure'] = 'low'
            
            self.system_state['last_health_check'] = datetime.now()
            
        except Exception as e:
            logger.debug(f"Error updating system state: {e}")
    
    def _calculate_adaptive_delay(self) -> float:
        """Calculate adaptive delay between cycles"""
        base_delay = Config.REQUEST_DELAYS['min_cycle_delay']
        max_delay = Config.REQUEST_DELAYS['max_cycle_delay']
        
        error_penalty = min(self.stats['errors'] * 1.5, 20)
        flood_penalty = min(self.stats['flood_waits'] * 3, 30)
        
        calculated_delay = base_delay + error_penalty + flood_penalty
        
        return max(base_delay, min(calculated_delay, max_delay))
    
    async def _graceful_shutdown(self):
        """Perform graceful shutdown"""
        logger.info("Starting graceful shutdown of collection system...")
        
        self.active = False
        self.paused = False
        self.stats['end_time'] = datetime.now()
        
        await self._save_final_stats()
        
        logger.info(f"Graceful shutdown completed. Stats: {self.stats}")
    
    async def _save_final_stats(self):
        """Save final statistics"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            conn = await db._get_connection()
            await conn.execute('''
                INSERT INTO collection_sessions 
                (session_uid, start_time, end_time, status, stats, duration_seconds, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.stats['current_session'],
                self.stats['start_time'].isoformat() if self.stats['start_time'] else None,
                self.stats['end_time'].isoformat() if self.stats['end_time'] else None,
                'completed',
                json.dumps(self.stats),
                int((self.stats['end_time'] - self.stats['start_time']).total_seconds()) 
                if self.stats['start_time'] and self.stats['end_time'] else 0,
                json.dumps({
                    'stats': self.stats,
                    'performance': self.performance,
                    'system_state': self.system_state
                })
            ))
            
            await conn.commit()
                
        except Exception as e:
            logger.error(f"Error saving final stats: {e}")
    
    def get_status(self) -> Dict:
        """Get collection status"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'stats': self.stats.copy(),
            'performance': self.performance.copy(),
            'system_state': self.system_state.copy(),
            'timestamp': datetime.now().isoformat()
        }
    
    async def pause(self):
        """Pause collection"""
        self.paused = True
        logger.info("Collection paused")
    
    async def resume(self):
        """Resume collection"""
        self.paused = False
        logger.info("Collection resumed")
    
    async def stop(self):
        """Stop collection"""
        self.stop_requested = True
        logger.info("Collection stop requested")
        
        await asyncio.sleep(2)

# ======================
# Advanced Telegram Bot - بوت تيليجرام المتقدم
# ======================

class AdvancedTelegramBot:
    """Advanced Telegram bot with unlimited collection features"""
    
    def __init__(self):
        self.collection_manager = AdvancedCollectionManager()
        self.security_manager = AdvancedSecurityManager()
        
        # إنشاء التطبيق باستخدام ApplicationBuilder
        self.app = Application.builder().token(Config.BOT_TOKEN).build()
        
        self._setup_advanced_handlers()
        
        self.user_states = defaultdict(dict)
        self.conversation_states = {}
        
        self.help_system = HelpSystem()
        self.notification_system = NotificationSystem()
    
    def _setup_advanced_handlers(self):
        """Setup advanced handlers"""
        # إضافة handlers للأوامر
        self.app.add_handler(CommandHandler("start", self.advanced_start_command))
        self.app.add_handler(CommandHandler("help", self.advanced_help_command))
        self.app.add_handler(CommandHandler("status", self.advanced_status_command))
        self.app.add_handler(CommandHandler("stats", self.advanced_stats_command))
        self.app.add_handler(CommandHandler("sessions", self.advanced_sessions_command))
        self.app.add_handler(CommandHandler("export", self.advanced_export_command))
        self.app.add_handler(CommandHandler("backup", self.advanced_backup_command))
        self.app.add_handler(CommandHandler("cleanup", self.advanced_cleanup_command))
        self.app.add_handler(CommandHandler("security", self.security_command))
        self.app.add_handler(CommandHandler("report", self.report_command))
        self.app.add_handler(CommandHandler("settings", self.settings_command))
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        
        # إضافة handler لمعالجات الاستدعاء
        self.app.add_handler(CallbackQueryHandler(self.handle_advanced_callback))
        
        # إضافة handler للرسائل النصية
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_advanced_message
        ))
        
        # إضافة handler للأخطاء
        self.app.add_error_handler(self.error_handler)
    
    async def advanced_start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        access, message, details = await self.security_manager.check_access(
            user.id,
            'start',
            {
                'username': user.username,
                'first_name': user.first_name,
                'chat_id': update.effective_chat.id
            }
        )
        
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        db = await EnhancedDatabaseManager.get_instance()
        await db.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        self.user_states[user.id] = {
            'last_command': 'start',
            'access_level': details.get('access_level'),
            'timestamp': datetime.now()
        }
        
        welcome_text = self.help_system.get_welcome_message(user, details)
        
        keyboard = self._create_main_keyboard(user.id)
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    async def advanced_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        user = update.effective_user
        
        access, message, _ = await self.security_manager.check_access(user.id, 'status')
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        self.user_states[user.id]['last_command'] = 'status'
        
        status = self.collection_manager.get_status()
        
        status_text = f"""
📊 **Advanced System Status - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**

**🔧 Collection Status:**
"""
        
        if status['active']:
            if status['paused']:
                status_text += "⏸️ **Paused**\n"
            elif status['stop_requested']:
                status_text += "🛑 **Stopping...**\n"
            else:
                status_text += "🔄 **Active**\n"
                
                if status['stats']['start_time']:
                    duration = datetime.now() - datetime.fromisoformat(status['stats']['start_time'])
                    status_text += f"   ⏱️ Duration: {self._format_duration(duration)}\n"
                    status_text += f"   🔄 Cycles: {status['stats']['cycles_completed']}\n"
        else:
            status_text += "🛑 **Stopped**\n"
        
        status_text += f"""
**📈 Collection Statistics (Unlimited Telegram):**
• 📦 Total: {status['stats']['total_collected']:,}
• 📢 Public groups: {status['stats']['telegram_public']:,}
• 🔒 Private groups: {status['stats']['telegram_private']:,}
• ➕ Join requests: {status['stats']['telegram_join']:,}
• 📢 Channels: {status['stats']['telegram_channels']:,}
• 👥 Groups: {status['stats']['telegram_groups']:,}
• ⭐ Supergroups: {status['stats']['telegram_supergroups']:,}
• 📱 WhatsApp: {status['stats']['whatsapp_groups']:,}

**⚡ System Performance:**
• 🎯 Performance score: {status['stats']['performance_score']:.1f}/100
• 📶 Network status: {status['system_state']['network_status']}
• ⚖️ Memory pressure: {status['system_state']['memory_pressure']}

**🔥 Enhanced Limits:**
• Max concurrent sessions: {Config.MAX_CONCURRENT_SESSIONS}
• Max export links: {Config.MAX_EXPORT_LINKS:,}
• Max sessions per user: {Config.MAX_SESSIONS_PER_USER}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_detailed")],
            [InlineKeyboardButton("📊 Full Stats", callback_data="full_stats")],
            [InlineKeyboardButton("📋 System Report", callback_data="system_report")]
        ])
        
        await update.message.reply_text(status_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /collect command"""
        user = update.effective_user
        
        access, message, _ = await self.security_manager.check_access(user.id, 'collect')
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Start Collection", callback_data="start_collect")],
            [InlineKeyboardButton("⏸️ Pause Collection", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ Stop Collection", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 Collection Status", callback_data="collect_status")],
            [InlineKeyboardButton("📋 Collection Report", callback_data="collect_report")],
            [InlineKeyboardButton("⚙️ Collection Settings", callback_data="collect_settings")]
        ])
        
        await update.message.reply_text(
            "🚀 **Advanced Collection System**\n\n"
            "**Collection Features:**\n"
            "• 📢 Telegram: Unlimited collection without time limits\n"
            "• 📱 WhatsApp: Collection from last 30 days only\n"
            "• 🔍 Smart detection: Distinguish between groups and channels\n"
            "• ⏱️ Join request verification: 30 seconds per link\n\n"
            f"**Enhanced Limits:**\n"
            f"• 🔥 Max {Config.MAX_CONCURRENT_SESSIONS} concurrent sessions\n"
            f"• 📥 Max {Config.MAX_EXPORT_LINKS:,} links for export\n"
            f"• 👥 Max {Config.MAX_SESSIONS_PER_USER} sessions per user\n\n"
            "**Supported Link Types:**\n"
            "• Public and private groups\n"
            "• Channels\n"
            "• Join requests (+)\n"
            "• WhatsApp groups\n"
            "• Discord and Signal invites\n",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def handle_advanced_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle advanced callback"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        data = query.data
        
        access, message, details = await self.security_manager.check_access(
            user.id, 
            f"callback_{data}",
            {'callback_data': data}
        )
        
        if not access:
            await query.message.edit_text(f"❌ {message}")
            return
        
        try:
            self.user_states[user.id]['last_callback'] = data
            
            if data == "start_collect":
                await self._handle_advanced_start_collection(query)
            elif data == "pause_collect":
                await self._handle_advanced_pause_collection(query)
            elif data == "stop_collect":
                await self._handle_stop_collection(query)
            elif data == "collect_status":
                await self._handle_collect_status(query)
            elif data == "collect_report":
                await self._handle_collect_report(query)
            elif data == "collect_settings":
                await self._handle_collect_settings(query)
            elif data == "refresh_detailed":
                await self.advanced_status_command(update, context)
            elif data == "full_stats":
                await self._handle_full_stats(query)
            elif data == "system_report":
                await self._handle_system_report(query)
            else:
                await query.message.edit_text("❌ Unknown command")
        
        except Exception as e:
            logger.error(f"Error in advanced callback handler: {e}")
            await query.message.edit_text(f"❌ Error: {str(e)[:100]}")
    
    async def _handle_advanced_start_collection(self, query):
        """Handle start collection"""
        if self.collection_manager.active:
            await query.message.edit_text("⏳ Collection is already running")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚖️ Balanced (Recommended)", callback_data="start_mode_balanced")],
            [InlineKeyboardButton("⚡ Fast", callback_data="start_mode_fast")],
            [InlineKeyboardButton("🔒 Safe", callback_data="start_mode_safe")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_start")]
        ])
        
        await query.message.edit_text(
            "🚀 **Start Advanced Smart Collection**\n\n"
            "**System Features:**\n"
            "• 📢 Telegram: Unlimited collection\n"
            "• 📱 WhatsApp: Last 30 days only\n"
            "• ⏱️ Join request verification: 30 seconds\n"
            "• 🔍 Smart distinction between groups and channels\n\n"
            f"**Enhanced Limits:**\n"
            f"• 🔥 Max {Config.MAX_CONCURRENT_SESSIONS} concurrent sessions\n"
            f"• 📥 Max {Config.MAX_EXPORT_LINKS:,} links for export\n\n"
            "Choose collection mode:\n\n"
            "• ⚖️ **Balanced** - Balanced collection with memory protection\n"
            "• ⚡ **Fast** - Fast collection with higher resource usage\n"
            "• 🔒 **Safe** - Safe collection with longer delays\n\n"
            "**Recommendation:** ⚖️ Balanced for new users",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_start_mode(self, query, mode: str):
        """Handle start mode selection"""
        try:
            await query.message.edit_text(f"🚀 Starting collection with {mode} mode...")
            
            # بدء الجمع في خلفية منفصلة
            asyncio.create_task(self._start_collection_in_background(mode, query.message))
            
        except Exception as e:
            logger.error(f"Error starting collection: {e}")
            await query.message.edit_text(f"❌ Error starting collection: {str(e)[:100]}")
    
    async def _start_collection_in_background(self, mode: str, message):
        """Start collection in background"""
        try:
            await self.collection_manager.start_collection(mode)
            await message.edit_text(
                f"✅ Collection started successfully with {mode} mode\n\n"
                "You can monitor collection progress using /status command",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error in background collection: {e}")
            await message.edit_text(f"❌ Collection error: {str(e)[:100]}")
    
    async def _handle_stop_collection(self, query):
        """Handle stop collection"""
        if not self.collection_manager.active:
            await query.message.edit_text("⚠️ Collection is not active")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm Stop", callback_data="confirm_stop")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_stop")]
        ])
        
        await query.message.edit_text(
            "⏹️ **Confirm Collection Stop**\n\n"
            "Are you sure you want to stop collection?\n\n"
            "**Note:**\n"
            "• All collected links will be saved\n"
            "• Collection will stop immediately\n"
            "• You can restart anytime\n\n"
            "Current statistics:\n"
            f"• Links collected: {self.collection_manager.stats['total_collected']:,}\n"
            f"• Cycles completed: {self.collection_manager.stats['cycles_completed']:,}",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_confirm_stop(self, query):
        """Handle confirm stop"""
        await query.message.edit_text("⏹️ Stopping collection...")
        
        # إيقاف الجمع
        await self.collection_manager.stop()
        
        await asyncio.sleep(2)
        await query.message.edit_text("✅ Collection stopped successfully")
    
    async def _handle_cancel_stop(self, query):
        """Handle cancel stop"""
        await query.message.edit_text("❌ Stop operation cancelled")
    
    async def _handle_collect_status(self, query):
        """Handle collect status"""
        status = self.collection_manager.get_status()
        
        text = f"""
📊 **Detailed Collection Status**

**Status:** {"🔄 Active" if status['active'] else "🛑 Stopped"}
**Paused:** {"⏸️ Yes" if status['paused'] else "▶️ No"}
**Stop Requested:** {"✅ Yes" if status['stop_requested'] else "❌ No"}

**Statistics:**
• Links collected: {status['stats']['total_collected']:,}
• Collection cycles: {status['stats']['cycles_completed']:,}
• Errors: {status['stats']['errors']:,}
• Flood waits: {status['stats']['flood_waits']:,}

**Telegram:**
• Public groups: {status['stats']['telegram_public']:,}
• Private groups: {status['stats']['telegram_private']:,}
• Join requests: {status['stats']['telegram_join']:,}
• Channels: {status['stats']['telegram_channels']:,}
• Groups: {status['stats']['telegram_groups']:,}
• Supergroups: {status['stats']['telegram_supergroups']:,}

**System Performance:**
• Performance score: {status['stats']['performance_score']:.1f}/100
• Success rate: {status['performance']['success_rate']:.1%}
• Memory usage: {status['system_state']['memory_pressure']}
"""
        
        await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    
    async def _handle_collect_report(self, query):
        """Handle collect report"""
        try:
            status = self.collection_manager.get_status()
            
            text = f"""
📋 **Advanced Collection Report**

**Collection Summary:**
• Status: {"🔄 Active" if status['active'] else "🛑 Stopped"}
• Links collected: {status['stats']['total_collected']:,}
• Success rate: {status['performance']['success_rate']:.1%}

**Telegram Details:**
• Groups: {status['stats']['telegram_groups']:,}
• Channels: {status['stats']['telegram_channels']:,}
• Supergroups: {status['stats']['telegram_supergroups']:,}
• Join requests: {status['stats']['telegram_join']:,}

**System Health:**
• Memory pressure: {status['system_state']['memory_pressure']}
• Network status: {status['system_state']['network_status']}

**Enhanced Limits:**
• Max sessions: {Config.MAX_CONCURRENT_SESSIONS}
• Max export: {Config.MAX_EXPORT_LINKS:,} links
"""
            
            await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Error generating collection report: {e}")
            await query.message.edit_text("❌ Error generating report")
    
    async def _handle_collect_settings(self, query):
        """Handle collect settings"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Change Collection Mode", callback_data="change_collect_mode")],
            [InlineKeyboardButton("⏱️ Adjust Delays", callback_data="adjust_delays")],
            [InlineKeyboardButton("📊 Adjust Limits", callback_data="adjust_limits")],
            [InlineKeyboardButton("🔄 Reset", callback_data="reset_settings")],
            [InlineKeyboardButton("⬅️ Back", callback_data="collect_menu")]
        ])
        
        text = f"""
⚙️ **Advanced Collection Settings**

**Current Settings:**
• Collection mode: {self.collection_manager.system_state['collection_mode']}
• Max concurrent sessions: {Config.MAX_CONCURRENT_SESSIONS} 🔥
• Links per cycle: {Config.MAX_LINKS_PER_CYCLE}
• Cycle delay: {Config.REQUEST_DELAYS['min_cycle_delay']}-{Config.REQUEST_DELAYS['max_cycle_delay']} seconds
• Join request check: {Config.JOIN_REQUEST_CHECK_DELAY} seconds

**Special Features:**
• Telegram: {"✅ Unlimited collection" if Config.TELEGRAM_NO_TIME_LIMIT else "❌ Limited"}
• WhatsApp: {"✅ Last 30 days" if Config.WHATSAPP_DAYS_BACK == 30 else f"Last {Config.WHATSAPP_DAYS_BACK} days"}
• Advanced validation: {"✅ Enabled" if Config.ENABLE_ADVANCED_VALIDATION else "❌ Disabled"}

**Enhanced Limits:**
• Max concurrent sessions: {Config.MAX_CONCURRENT_SESSIONS} 🔥
• Max export links: {Config.MAX_EXPORT_LINKS:,} links 🔥
• Max sessions per user: {Config.MAX_SESSIONS_PER_USER} 🔥
"""
        
        await query.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    async def _handle_advanced_pause_collection(self, query):
        """Handle pause collection"""
        if not self.collection_manager.active:
            await query.message.edit_text("⚠️ Collection is not active")
            return
        
        if self.collection_manager.paused:
            await self.collection_manager.resume()
            await query.message.edit_text("▶️ Collection resumed")
        else:
            await self.collection_manager.pause()
            await query.message.edit_text("⏸️ Collection paused")
    
    async def _handle_full_stats(self, query):
        """Handle full stats"""
        db = await EnhancedDatabaseManager.get_instance()
        stats = await db.get_stats_summary_enhanced(detailed=True)
        
        text = f"""
📊 **Complete Statistics**

**General Statistics:**
• Total links: {stats.get('total_links', 0):,}
• Active sessions: {stats.get('active_sessions', 0)}
• Users: {stats.get('total_users', 0)}
• Pending join links: {stats.get('pending_join_links', 0)}

**Distribution by Platform:**
"""
        
        for platform, count in stats.get('links_by_platform', {}).items():
            text += f"• {platform}: {count:,}\n"
        
        text += f"""
**Detailed Telegram Links:**
"""
        
        for detail in stats.get('telegram_details', [])[:5]:
            text += f"• {detail['type']}: {detail['count']}\n"
        
        text += f"""
**Top Users:**
"""
        
        for user in stats.get('top_users', [])[:3]:
            text += f"• {user.get('username', 'Unknown')}: {user.get('link_count', 0)} links\n"
        
        await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    
    async def _handle_system_report(self, query):
        """Handle system report"""
        text = f"""
📋 **Advanced System Report**

**System Summary:**
• Python version: {sys.version.split()[0]}
• Platform: {sys.platform}
• Bot version: 2.0.0

**Resource Usage:**
"""
        
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            text += f"• Memory usage: {memory_info.rss / 1024 / 1024:.1f} MB\n"
            text += f"• Memory percent: {process.memory_percent():.1f}%\n"
        except:
            text += "• Memory info: Not available\n"
        
        text += f"""
**Enhanced Limits:**
• Max sessions: {Config.MAX_CONCURRENT_SESSIONS} 🔥
• Max export: {Config.MAX_EXPORT_LINKS:,} links 🔥
• Max sessions/user: {Config.MAX_SESSIONS_PER_USER} 🔥

**Database:**
• Path: {Config.DB_PATH}
• Backups: {"✅ Enabled" if Config.BACKUP_ENABLED else "❌ Disabled"}
• Max backups: {Config.MAX_BACKUPS}

**Security:**
• Admins: {len(Config.ADMIN_USER_IDS)}
• Allowed users: {len(Config.ALLOWED_USER_IDS)}
"""
        
        await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    
    def _create_main_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        """Create main keyboard"""
        is_admin = self.security_manager.is_admin(user_id)
        
        buttons = [
            [InlineKeyboardButton("🚀 Start Collection", callback_data="start_collect"),
             InlineKeyboardButton("⏸️ Manage Collection", callback_data="manage_collect")],
            [InlineKeyboardButton("📊 Statistics", callback_data="show_stats"),
             InlineKeyboardButton("📤 Export Links", callback_data="export_menu")],
            [InlineKeyboardButton("❓ Help", callback_data="show_help"),
             InlineKeyboardButton("⚙️ Settings", callback_data="show_settings")]
        ]
        
        if is_admin:
            buttons.append([
                InlineKeyboardButton("🔒 Security", callback_data="show_security"),
                InlineKeyboardButton("📋 Reports", callback_data="show_reports")
            ])
        
        return InlineKeyboardMarkup(buttons)
    
    def _format_duration(self, duration: timedelta) -> str:
        """Format duration"""
        total_seconds = int(duration.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days > 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
        if seconds > 0 or not parts:
            parts.append(f"{seconds} second{'s' if seconds > 1 else ''}")
        
        return " ".join(parts)
    
    async def advanced_help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        text = """
❓ **Comprehensive Help Guide**

**Basic Commands:**
• /start - Start using the bot
• /help - Show this message
• /status - Show system status
• /stats - Database statistics
• /collect - Start/manage collection

**Session Management:**
• /sessions - Show active sessions

**Export:**
• /export - Export collected links
• Can export up to 100,000 links

**Settings:**
• /settings - System settings
• /backup - Backup
• /cleanup - System cleanup

**For Admins:**
• /security - Security management
• /report - System reports

**Important Information:**
• You can add up to 20 sessions
• Unlimited collection for Telegram
• WhatsApp: Last 30 days only
• Automatic backup exists
"""
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    
    async def advanced_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        db = await EnhancedDatabaseManager.get_instance()
        stats = await db.get_stats_summary_enhanced(detailed=True)
        
        text = f"""
📊 **Advanced System Statistics**

**General Statistics:**
• Total links: {stats.get('total_links', 0):,}
• Active sessions: {stats.get('active_sessions', 0)}
• Users: {stats.get('total_users', 0)}
• Pending join links: {stats.get('pending_join_links', 0)}

**Distribution by Platform:**
"""
        
        for platform, count in stats.get('links_by_platform', {}).items():
            text += f"• {platform}: {count:,}\n"
        
        text += f"""
**Detailed Telegram Links:**
"""
        
        for detail in stats.get('telegram_details', [])[:5]:
            text += f"• {detail['type']}: {detail['count']}\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    
    async def advanced_sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sessions command"""
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=10)
        
        text = "👥 **Active Sessions**\n\n"
        
        if not sessions:
            text += "No active sessions\n"
        else:
            for i, session in enumerate(sessions[:5], 1):
                text += f"{i}. {session.get('display_name', 'Unknown')}\n"
                text += f"   📞 {session.get('phone_number', 'Unknown')}\n"
                text += f"   📊 Health: {session.get('health_score', 0)}%\n"
                text += f"   🔗 Links: {session.get('total_links', 0)}\n"
                text += f"   📅 Last used: {session.get('last_used', 'Unknown')}\n\n"
        
        text += f"\n**Max Sessions per User:** {Config.MAX_SESSIONS_PER_USER}"
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    
    async def advanced_export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Export Telegram", callback_data="export_telegram")],
            [InlineKeyboardButton("📱 Export WhatsApp", callback_data="export_whatsapp")],
            [InlineKeyboardButton("🔄 Export All", callback_data="export_all")],
            [InlineKeyboardButton("⚙️ Custom Export", callback_data="export_custom")]
        ])
        
        text = f"""
📤 **Link Export System**

You can export collected links in different formats.

**Information:**
• Maximum: {Config.MAX_EXPORT_LINKS:,} links
• Formats: TXT, JSON, CSV
• Can filter by type and date

**Choose export type:**
• Telegram only
• WhatsApp only
• All links
• Custom export (advanced filtering)
"""
        
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    async def advanced_backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /backup command"""
        await update.message.reply_text(
            "💾 **Backup System**\n\n"
            "**Features:**\n"
            "• Automatic backup\n"
            "• Store up to 10 copies\n"
            "• Automatic restore\n"
            "• Data encryption\n\n"
            "**Current Status:**\n"
            f"• Backup: {'✅ Enabled' if Config.BACKUP_ENABLED else '❌ Disabled'}\n"
            f"• Max copies: {Config.MAX_BACKUPS}\n"
            "• Frequency: Every 5 hours\n\n"
            "**To create manual backup:**\n"
            "I will create a backup now...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # إنشاء نسخة احتياطية
        backup_result = await BackupManager.create_backup()
        
        if backup_result:
            await update.message.reply_text(
                f"✅ **Backup created successfully**\n\n"
                f"**Details:**\n"
                f"• ID: {backup_result.get('backup_id', 'Unknown')}\n"
                f"• Size: {backup_result.get('size_mb', 0):.2f} MB\n"
                f"• Time: {backup_result.get('timestamp', 'Unknown')}\n\n"
                f"Backup saved in backups/ folder",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("❌ Failed to create backup")
    
    async def advanced_cleanup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cleanup command"""
        await update.message.reply_text(
            "🧹 **Cleanup and Maintenance System**\n\n"
            "**Available Tasks:**\n"
            "1. Clean old logs\n"
            "2. Optimize database\n"
            "3. Clean temporary cache\n"
            "4. Rotate backups\n"
            "5. Optimize memory\n\n"
            "**Running maintenance...**",
            parse_mode=ParseMode.MARKDOWN
        )
        
        results = []
        
        try:
            # 1. تنظيف السجلات القديمة
            db = await EnhancedDatabaseManager.get_instance()
            conn = await db._get_connection()
            
            cursor = await conn.execute('''
                DELETE FROM error_log 
                WHERE occurred_at < datetime('now', '-7 days')
            ''')
            error_cleaned = cursor.rowcount
            
            cursor = await conn.execute('''
                DELETE FROM system_stats 
                WHERE recorded_at < datetime('now', '-30 days')
            ''')
            stats_cleaned = cursor.rowcount
            
            await conn.commit()
            results.append(f"Logs: {error_cleaned + stats_cleaned}")
            
            # 2. تحسين قاعدة البيانات
            await conn.execute("ANALYZE")
            await conn.execute("REINDEX")
            await conn.execute("VACUUM")
            await conn.commit()
            results.append("Database: Optimized")
            
            # 3. تحسين الذاكرة
            try:
                import gc
                gc.collect()
                results.append("Memory: Optimized")
            except:
                results.append("Memory: Not optimized")
            
            # 4. تدوير النسخ
            rotated = await BackupManager.rotate_backups()
            results.append(f"Backups: {rotated} deleted")
            
            summary = "\n".join([f"• {result}" for result in results])
            
            await update.message.reply_text(
                f"✅ **Maintenance completed successfully**\n\n"
                f"**Results:**\n{summary}\n\n"
                f"**System now in excellent condition**",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Error in cleanup: {e}")
            await update.message.reply_text(f"❌ Error during cleanup: {str(e)[:100]}")
    
    async def security_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /security command"""
        user = update.effective_user
        
        if not self.security_manager.is_admin(user.id):
            await update.message.reply_text("❌ This command is for admins only")
            return
        
        security_stats = self.security_manager.get_security_stats()
        
        text = f"""
🔒 **Advanced Security Control Panel**

**Access Statistics:**
• Allowed users: {len(Config.ALLOWED_USER_IDS)}
• Admins: {len(Config.ADMIN_USER_IDS)}
• Access attempts denied: {security_stats.get('access_denied', 0)}
• Rate limit violations: {security_stats.get('rate_limit_violations', 0)}

**Detected Threats:**
• Suspicious activity: {security_stats.get('suspicious_activities', 0)}
• Detected attacks: {security_stats.get('detected_attacks', 0)}

**Settings:**
• Threat detection: {'✅ Enabled' if self.security_manager.threat_detection_enabled else '❌ Disabled'}
• Rate limiting: ✅ Enabled
• Event logging: ✅ Enabled

**Commands:**
• /security log - Show security log
• /security users - Manage users
• /security scan - System scan
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Security Log", callback_data="security_log")],
            [InlineKeyboardButton("👥 Manage Users", callback_data="security_users")],
            [InlineKeyboardButton("🔍 System Scan", callback_data="security_scan")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="security_settings")]
        ])
        
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    async def report_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /report command"""
        await update.message.reply_text(
            "📋 **Advanced Report System**\n\n"
            "**Available Reports:**\n"
            "1. Complete collection report\n"
            "2. Database report\n"
            "3. Performance report\n"
            "4. System report\n"
            "5. Security report\n\n"
            "**Generating reports...**",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # جمع البيانات
            collection_status = self.collection_manager.get_status()
            db = await EnhancedDatabaseManager.get_instance()
            db_stats = await db.get_stats_summary_enhanced(detailed=True)
            
            text = f"""
📋 **Comprehensive System Report**

**Collection Summary:**
• Status: {"🔄 Active" if collection_status['active'] else "🛑 Stopped"}
• Links collected: {collection_status['stats']['total_collected']:,}
• Performance score: {collection_status['stats']['performance_score']:.1f}/100

**Database:**
• Total links: {db_stats.get('total_links', 0):,}
• Active sessions: {db_stats.get('active_sessions', 0)}
• Pending join links: {db_stats.get('pending_join_links', 0)}

**Performance:**
• Memory pressure: {collection_status['system_state']['memory_pressure']}
• Network status: {collection_status['system_state']['network_status']}

**Enhanced Limits:**
• Max sessions: {Config.MAX_CONCURRENT_SESSIONS} 🔥
• Max export: {Config.MAX_EXPORT_LINKS:,} links 🔥
• Max sessions/user: {Config.MAX_SESSIONS_PER_USER} 🔥
"""
            
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            await update.message.reply_text(f"❌ Error generating report: {str(e)[:100]}")
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        text = f"""
⚙️ **Advanced System Settings**

**Collection Settings:**
• Collection mode: {self.collection_manager.system_state['collection_mode']}
• Max concurrent sessions: {Config.MAX_CONCURRENT_SESSIONS}
• Links per cycle: {Config.MAX_LINKS_PER_CYCLE}
• Telegram: {"✅ Unlimited collection" if Config.TELEGRAM_NO_TIME_LIMIT else "❌ Limited"}
• WhatsApp: Last {Config.WHATSAPP_DAYS_BACK} days

**Performance Settings:**
• Max memory: {Config.MAX_MEMORY_MB} MB
• Cache size: {Config.MAX_CACHED_URLS:,}

**Database Settings:**
• Backup: {'✅ Enabled' if Config.BACKUP_ENABLED else '❌ Disabled'}
• Max backups: {Config.MAX_BACKUPS}
• Export links: {Config.MAX_EXPORT_LINKS:,}

**Security Settings:**
• Admins: {len(Config.ADMIN_USER_IDS)}
• Allowed users: {len(Config.ALLOWED_USER_IDS)}
• Rate limiting: {Config.USER_RATE_LIMIT['max_requests']}/60 seconds

**Advanced Features:**
• Advanced validation: {"✅ Enabled" if Config.ENABLE_ADVANCED_VALIDATION else "❌ Disabled"}
• Join request check: Every {Config.JOIN_REQUEST_CHECK_DELAY} seconds
• Session timeout: {Config.SESSION_TIMEOUT} seconds
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Collection Settings", callback_data="collect_settings")],
            [InlineKeyboardButton("🔧 Performance Settings", callback_data="performance_settings")],
            [InlineKeyboardButton("💾 Database Settings", callback_data="database_settings")],
            [InlineKeyboardButton("🔒 Security Settings", callback_data="security_settings")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="settings_refresh")]
        ])
        
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    async def handle_advanced_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle advanced message"""
        user = update.effective_user
        message_text = update.message.text
        
        # التحقق من حالة انتظار الجلسة
        if self.user_states.get(user.id, {}).get('awaiting_session'):
            await self._handle_session_input(update, message_text)
            return
        
        # رد افتراضي
        await update.message.reply_text(
            "📨 **Your message received**\n\n"
            "For optimal use, please use available commands or buttons.\n\n"
            "**Main Commands:**\n"
            "/start - Start bot\n"
            "/help - Show help\n"
            "/status - System status\n"
            "/collect - Start collection",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_session_input(self, update: Update, session_string: str):
        """Handle session input"""
        user = update.effective_user
        
        # إلغاء إذا كان الأمر /cancel
        if session_string.lower() == '/cancel':
            self.user_states[user.id].pop('awaiting_session', None)
            await update.message.reply_text("❌ Session addition cancelled")
            return
        
        await update.message.reply_text("🔍 Verifying session...")
        
        # التحقق من الجلسة
        is_valid, validation_info = await EnhancedSessionManager.validate_session(session_string)
        
        if not is_valid:
            await update.message.reply_text(
                f"❌ **Session invalid**\n\n"
                f"**Error:** {validation_info.get('error', 'Unknown')}\n"
                f"**Details:** {validation_info.get('details', 'No details')}\n\n"
                "Please check the session and try again.",
                parse_mode=ParseMode.MARKDOWN
            )
            self.user_states[user.id].pop('awaiting_session', None)
            return
        
        # تشفير الجلسة
        enc_manager = EncryptionManager.get_instance()
        encrypted_session = enc_manager.encrypt_session(session_string)
        
        # حفظ الجلسة في قاعدة البيانات
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            conn = await db._get_connection()
            
            session_hash = hashlib.sha256(session_string.encode()).hexdigest()[:32]
            
            user_info = validation_info.get('user_info', {})
            
            await conn.execute('''
                INSERT INTO sessions 
                (session_string, session_hash, phone_number, user_id, username, 
                 display_name, added_by_user, is_active, status, health_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'active', 100)
            ''', (
                encrypted_session,
                session_hash,
                user_info.get('phone', ''),
                user_info.get('id', 0),
                user_info.get('username', ''),
                f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip(),
                user.id
            ))
            
            await conn.commit()
            
            # تحديث إحصائيات المستخدم
            await db.update_user_stats(user.id, 'session_added')
            
            await update.message.reply_text(
                f"✅ **Session added successfully**\n\n"
                f"**Session Information:**\n"
                f"• Name: {user_info.get('first_name', '')} {user_info.get('last_name', '')}\n"
                f"• ID: {user_info.get('id', 'Unknown')}\n"
                f"• Username: @{user_info.get('username', 'Unknown')}\n"
                f"• Phone: {user_info.get('phone', 'Unknown')}\n"
                f"• Status: {'🟢 Premium' if user_info.get('is_premium', False) else '🔵 Regular'}\n\n"
                f"**Notes:**\n"
                "• Session encrypted and stored securely\n"
                "• Will be used for link collection\n"
                f"• You can add up to {Config.MAX_SESSIONS_PER_USER - 1} more sessions",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Error saving session: {e}")
            await update.message.reply_text(
                f"❌ **Session save error**\n\n"
                f"**Error:** {str(e)[:100]}\n\n"
                "Please try again later.",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # تنظيف حالة المستخدم
        self.user_states[user.id].pop('awaiting_session', None)
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        try:
            error = context.error
            
            logger.error(f"Unhandled error in bot: {error}")
            
            try:
                db = await EnhancedDatabaseManager.get_instance()
                
                conn = await db._get_connection()
                await conn.execute('''
                    INSERT INTO error_log (error_type, error_message, stack_trace, user_id, command)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    error.__class__.__name__,
                    str(error),
                    ''.join(traceback.format_exception(type(error), error, error.__traceback__)),
                    update.effective_user.id if update and update.effective_user else 0,
                    update.message.text if update and update.message else 'unknown'
                ))
                
                await conn.commit()
            except Exception as db_error:
                logger.error(f"Error logging error to database: {db_error}")
            
            if update and update.effective_chat:
                error_message = (
                    "❌ **Unexpected error occurred**\n\n"
                    "We encountered a technical problem. The error has been logged and we will work to resolve it soon.\n\n"
                    "**You can:**\n"
                    "1. Try again after a while\n"
                    "2. Use /start command to return\n"
                    "3. Contact support if error persists"
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=error_message,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass
            
        except Exception as e:
            logger.error(f"Error in error handler: {e}")

# ======================
# Help System - نظام المساعدة
# ======================

class HelpSystem:
    """Help system"""
    
    def get_welcome_message(self, user, access_details: Dict) -> str:
        """Get welcome message"""
        access_level = access_details.get('access_level', 'user')
        
        if access_level == 'admin':
            role_text = "👑 **You are system admin** - Full permissions"
        elif access_level == 'user':
            role_text = "👤 **You are regular user** - Limited permissions"
        else:
            role_text = "🚫 **Restricted access** - Very limited permissions"
        
        return f"""
🤖 **Welcome {user.first_name}!**

{role_text}

**✨ Enhanced Advanced Features:**

🔥 **Enhanced Limits:**
• Max {Config.MAX_CONCURRENT_SESSIONS} concurrent sessions
• Max {Config.MAX_EXPORT_LINKS:,} links for export
• Max {Config.MAX_SESSIONS_PER_USER} sessions per user

⚡ **Advanced Performance:**
• Advanced parallel processing
• Smart memory management
• Multi-level cache
• Smart delays

🔒 **Comprehensive Security:**
• Session encryption
• Threat detection
• Access control
• Detailed security logs

📊 **Advanced Analytics:**
• Real-time statistics
• Detailed reports
• Performance analysis
• Smart recommendations

💾 **Reliability:**
• Automatic backups
• Data recovery
• System monitoring
• Instant notifications

**🚀 Start now using the buttons below!**
"""

# ======================
# Notification System - نظام الإشعارات
# ======================

class NotificationSystem:
    """Notification system"""
    
    async def send_admin_notification(self, message: str, data: Dict = None):
        """Send admin notification"""
        logger.info(f"Admin notification: {message}")
    
    async def send_error_notification(self, error: str, details: Dict):
        """Send error notification"""
        logger.error(f"Error notification: {error}")
        
        # تسجيل الخطأ في قاعدة البيانات
        try:
            db = await EnhancedDatabaseManager.get_instance()
            conn = await db._get_connection()
            await conn.execute('''
                INSERT INTO error_log (error_type, error_message, metadata)
                VALUES (?, ?, ?)
            ''', (
                'system_error',
                error,
                json.dumps(details)
            ))
            await conn.commit()
        except Exception as e:
            logger.error(f"Error logging error: {e}")

# ======================
# Advanced Security Manager - مدير الأمان المتقدم
# ======================

class AdvancedSecurityManager:
    """Advanced security manager"""
    
    def __init__(self):
        self.rate_limiter = AdvancedRateLimiter()
        self.suspicious_activity = defaultdict(list)
        self.access_log = deque(maxlen=1000)
        self.threat_detection_enabled = True
        
    async def check_access(self, user_id: int, command: str = None, 
                          context: Dict = None) -> Tuple[bool, str, Dict]:
        """Check access"""
        # التحقق إذا كان مدير
        if Config.ADMIN_USER_IDS and user_id in Config.ADMIN_USER_IDS:
            return True, "Admin", {'access_level': 'admin'}
        
        # التحقق إذا كان مستخدم مسموح
        if Config.ALLOWED_USER_IDS and user_id not in Config.ALLOWED_USER_IDS:
            self._log_suspicious_activity(user_id, 'unauthorized_access', context)
            return False, "Access not authorized", {'access_level': 'denied'}
        
        # التحقق من حدود الطلبات
        limit_result, limit_details = await self.rate_limiter.check_limit(user_id, command or 'general')
        
        if not limit_result:
            self._log_suspicious_activity(user_id, 'rate_limit_exceeded', {
                **context,
                'limit_details': limit_details
            })
            
            wait_time = limit_details.get('wait_seconds', 30)
            return False, f"Rate limit exceeded. Try after {wait_time:.0f} seconds", {
                'access_level': 'rate_limited',
                'wait_seconds': wait_time,
                **limit_details
            }
        
        # كشف التهديدات
        if self.threat_detection_enabled:
            threat_check = await self._detect_threats(user_id, command, context)
            if not threat_check['safe']:
                self._log_suspicious_activity(user_id, 'threat_detected', threat_check)
                return False, "Suspicious activity detected. Access denied.", {
                    'access_level': 'blocked',
                    'threat_details': threat_check
                }
        
        # تسجيل الوصول الناجح
        self._log_access(user_id, 'success', command, context)
        
        return True, "Allowed", {
            'access_level': 'user',
            'rate_limit': limit_details,
            'user_stats': self.rate_limiter.get_user_stats(user_id)
        }
    
    async def _detect_threats(self, user_id: int, command: str, context: Dict) -> Dict:
        """Detect threats"""
        threats = []
        risk_score = 0
        
        # تحليل الوصول المتكرر السريع
        recent_accesses = [log for log in self.access_log 
                          if log['user_id'] == user_id and 
                          (datetime.now() - log['timestamp']).total_seconds() < 10]
        
        if len(recent_accesses) > 5:
            threats.append('rapid_repeated_access')
            risk_score += 30
        
        # كشف الأوامر المشبوهة
        suspicious_commands = ['eval', 'exec', 'system', 'os.', 'subprocess']
        if command and any(suspicious in command.lower() for suspicious in suspicious_commands):
            threats.append('suspicious_command')
            risk_score += 50
        
        # التحقق من الأنشطة المشبوهة السابقة
        user_patterns = self.suspicious_activity.get(user_id, [])
        if len(user_patterns) > 3:
            threats.append('multiple_suspicious_activities')
            risk_score += 40
        
        return {
            'safe': risk_score < 50,
            'risk_score': risk_score,
            'threats': threats,
            'threat_count': len(threats)
        }
    
    def _log_access(self, user_id: int, status: str, command: str, context: Dict):
        """Log access"""
        log_entry = {
            'timestamp': datetime.now(),
            'user_id': user_id,
            'status': status,
            'command': command,
            'context': context or {},
            'ip': context.get('ip') if context else None
        }
        
        self.access_log.append(log_entry)
    
    def _log_suspicious_activity(self, user_id: int, activity_type: str, details: Dict):
        """Log suspicious activity"""
        activity = {
            'timestamp': datetime.now(),
            'user_id': user_id,
            'activity_type': activity_type,
            'details': details
        }
        
        self.suspicious_activity[user_id].append(activity)
        
        if len(self.suspicious_activity[user_id]) > 10:
            self.suspicious_activity[user_id] = self.suspicious_activity[user_id][-10:]
        
        logger.warning(f"Suspicious activity: {activity_type} for user {user_id}")
    
    def is_admin(self, user_id: int) -> bool:
        """Check if admin"""
        return user_id in Config.ADMIN_USER_IDS if Config.ADMIN_USER_IDS else False
    
    def get_security_stats(self) -> Dict:
        """Get security statistics"""
        return {
            'access_denied': sum(1 for log in self.access_log if log['status'] != 'success'),
            'rate_limit_violations': len([log for log in self.access_log if 'rate_limit' in str(log)]),
            'suspicious_activities': sum(len(activities) for activities in self.suspicious_activity.values()),
            'detected_attacks': sum(1 for user_activities in self.suspicious_activity.values() 
                                   for activity in user_activities if 'attack' in activity.get('activity_type', ''))
        }

# ======================
# Advanced Rate Limiter - حد الطلبات المتقدم
# ======================

class AdvancedRateLimiter:
    """Advanced rate limiter"""
    
    def __init__(self):
        self.user_limits = defaultdict(lambda: {
            'requests': deque(),
            'total': 0,
            'penalty_score': 0,
            'last_violation': None
        })
        
        self.global_limits = {
            'total_requests': 0,
            'rate_violations': 0,
            'adaptive_threshold': Config.USER_RATE_LIMIT['max_requests']
        }
        
        self.locks = defaultdict(asyncio.Lock)
        
    async def check_limit(self, user_id: int, action: str = 'general') -> Tuple[bool, Dict]:
        """Check limit"""
        async with self.locks[user_id]:
            user_data = self.user_limits[user_id]
            now = datetime.now()
            
            # تنظيف الطلبات القديمة
            while user_data['requests'] and (now - user_data['requests'][0]).total_seconds() > Config.USER_RATE_LIMIT['per_seconds']:
                user_data['requests'].popleft()
            
            # حساب الحد الديناميكي
            dynamic_limit = self._calculate_dynamic_limit(user_id)
            
            # التحقق من التجاوز
            if len(user_data['requests']) >= dynamic_limit:
                user_data['penalty_score'] += 10
                user_data['last_violation'] = now
                self.global_limits['rate_violations'] += 1
                
                wait_time = self._calculate_wait_time(user_data['penalty_score'])
                
                return False, {
                    'allowed': False,
                    'wait_seconds': wait_time,
                    'current_requests': len(user_data['requests']),
                    'dynamic_limit': dynamic_limit,
                    'penalty_score': user_data['penalty_score'],
                    'action': action
                }
            
            # إضافة الطلب الجديد
            user_data['requests'].append(now)
            user_data['total'] += 1
            self.global_limits['total_requests'] += 1
            
            # تقليل العقوبة مع الوقت
            if user_data['penalty_score'] > 0:
                hours_since_violation = (now - (user_data['last_violation'] or now)).total_seconds() / 3600
                if hours_since_violation > 1:
                    user_data['penalty_score'] = max(0, user_data['penalty_score'] - 5)
            
            return True, {
                'allowed': True,
                'current_requests': len(user_data['requests']),
                'dynamic_limit': dynamic_limit,
                'penalty_score': user_data['penalty_score'],
                'total_requests': user_data['total']
            }
    
    def _calculate_dynamic_limit(self, user_id: int) -> int:
        """Calculate dynamic limit"""
        base_limit = Config.USER_RATE_LIMIT['max_requests']
        user_data = self.user_limits[user_id]
        
        # عامل العقوبة
        penalty_factor = max(0.3, 1 - (user_data['penalty_score'] / 100))
        
        # عامل النظام العام
        global_factor = 1.0
        if self.global_limits['rate_violations'] > 10:
            global_factor = 0.8
        elif self.global_limits['total_requests'] > 1000:
            global_factor = 0.9
        
        return int(base_limit * penalty_factor * global_factor)
    
    def _calculate_wait_time(self, penalty_score: int) -> float:
        """Calculate wait time"""
        base_wait = 30
        penalty_multiplier = 1 + (penalty_score / 50)
        
        return min(base_wait * penalty_multiplier, 300)
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Get user stats"""
        user_data = self.user_limits.get(user_id, {})
        
        if not user_data:
            return {
                'total_requests': 0,
                'current_window': 0,
                'penalty_score': 0,
                'dynamic_limit': self._calculate_dynamic_limit(user_id),
                'status': 'good'
            }
        
        now = datetime.now()
        recent_requests = deque(user_data.get('requests', deque()))
        
        # إحصائيات النوافذ الزمنية
        window_stats = {}
        for window in [10, 30, 60, 300, 1800]:
            count = sum(1 for req_time in recent_requests 
                       if (now - req_time).total_seconds() <= window)
            window_stats[f'last_{window}s'] = count
        
        # تحديد الحالة
        status = 'good'
        penalty = user_data.get('penalty_score', 0)
        if penalty > 50:
            status = 'critical'
        elif penalty > 20:
            status = 'warning'
        elif penalty > 0:
            status = 'monitoring'
        
        return {
            'total_requests': user_data.get('total', 0),
            'current_window': len(recent_requests),
            'window_stats': window_stats,
            'penalty_score': penalty,
            'last_violation': user_data.get('last_violation'),
            'dynamic_limit': self._calculate_dynamic_limit(user_id),
            'status': status,
            'estimated_wait': self._calculate_wait_time(penalty) if penalty > 0 else 0
        }

# ======================
# Enhanced Session Manager - مدير الجلسات المحسن
# ======================

class EnhancedSessionManager:
    """Enhanced session manager"""
    
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
                return False, {'error': 'Not authorized', 'details': 'Session not active'}
            
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
            return False, {'error': 'Password protected', 'details': 'Session requires secondary password'}
        except AuthKeyError:
            return False, {'error': 'Invalid auth key', 'details': 'Session expired or invalid'}
        except Exception as e:
            return False, {'error': 'Verification error', 'details': str(e)[:200]}

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
            logger.error(f"Encryption error: {e}")
            return data
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt"""
        try:
            decrypted = self.cipher.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption error: {e}")
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
            logger.error(f"Session decryption error: {e}")
            return None

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
                logger.error("Database file not found")
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
            
            logger.info(f"Backup created: {backup_path}")
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
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
                return 0
            
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
                return 0
            
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
                    logger.info(f"Deleted old backup: {backup['path']}")
                    
                except Exception as e:
                    logger.error(f"Error deleting old backup: {e}")
            
            if deleted_count > 0:
                logger.info(f"Rotated {deleted_count} old backups")
            
            return deleted_count
                    
        except Exception as e:
            logger.error(f"Error rotating backups: {e}")
            return 0

# ======================
# FastAPI Health Check - فحص صحة FastAPI
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
                # التحقق من الذاكرة
                try:
                    import psutil
                    process = psutil.Process(os.getpid())
                    memory_percent = process.memory_percent()
                    memory_ok = memory_percent < 90
                except:
                    memory_ok = True
                
                status = {
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat(),
                    "checks": {
                        "database": os.path.exists(Config.DB_PATH),
                        "memory": memory_ok,
                        "bot_token": bool(Config.BOT_TOKEN)
                    }
                }
                
                return JSONResponse(status_code=200, content=status)
                
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
                    "system": {
                        "python_version": sys.version,
                        "platform": sys.platform
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
        logger.info(f"Health check server started on port {self.port}")

# ======================
# Signal Handlers - معالجات الإشارات
# ======================

def setup_signal_handlers():
    """Setup signal handlers"""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}. Graceful shutdown...")
        
        logger.info("Final system statistics:")
        
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# ======================
# Main Entry Point - نقطة الدخول الرئيسية
# ======================

async def main():
    """Main function"""
    setup_signal_handlers()
    
    # FIX: إصلاح مشكلة Windows Proactor
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    required_env_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH']
    missing = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing:
        logger.error(f"Missing environment variables: {missing}")
        print(f"Error: The following environment variables are missing: {', '.join(missing)}")
        sys.exit(1)
    
    if Config.ENCRYPTION_KEY == Fernet.generate_key().decode():
        logger.warning("Using temporary encryption key. Recommended to set permanent ENCRYPTION_KEY")
    
    os.makedirs("backups", exist_ok=True)
    os.makedirs("cache_data", exist_ok=True)
    os.makedirs("exports", exist_ok=True)
    
    # بدء خادم فحص الصحة
    health_server = HealthCheckServer(port=8080)
    health_server.start()
    
    # بدء البوت
    bot = AdvancedTelegramBot()
    
    logger.info("🤖 Starting Advanced Telegram Link Collector Bot...")
    logger.info(f"🔥 Enhanced Settings - max_sessions: {Config.MAX_CONCURRENT_SESSIONS}, max_export_links: {Config.MAX_EXPORT_LINKS}, max_sessions_per_user: {Config.MAX_SESSIONS_PER_USER}")
    
    try:
        # بدء البوت
        await bot.app.initialize()
        await bot.app.start()
        
        logger.info("🚀 Bot running successfully with enhanced limits!")
        
        # FIX: استخدام polling بدلاً من webhook للبساطة
        logger.info("📡 Starting polling...")
        
        # الحفاظ على البوت يعمل
        await bot.app.updater.start_polling()
        
        # انتظار الإشارات
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"❌ Error in advanced bot: {e}")
        raise
        
    finally:
        logger.info("🧹 Performing final cleanup...")
        
        try:
            if hasattr(bot, 'app'):
                await bot.app.stop()
            
            db = await EnhancedDatabaseManager.get_instance()
            await db.close()
            
            logger.info("✅ Graceful shutdown completed")
            
        except Exception as e:
            logger.error(f"❌ Error in final cleanup: {e}")

async def periodic_maintenance():
    """Periodic maintenance"""
    while True:
        try:
            if Config.BACKUP_ENABLED:
                await BackupManager.rotate_backups()
            
            logger.debug("✅ Periodic maintenance completed")
            
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"Error in periodic maintenance: {e}")
            await asyncio.sleep(60)

def run_main():
    """Run main function"""
    # FIX: التعامل مع asyncio.run بشكل صحيح
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_main()
