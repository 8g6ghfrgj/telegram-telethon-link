import os
import sys
import subprocess

# 🔧 FIX FOR RENDER: Install missing packages on startup
def ensure_packages():
    """Ensure all required packages are installed"""
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
        'pytz==2023.3',
        'beautifulsoup4==4.12.3'
    ]
    
    for package in required:
        pkg_name = package.split('==')[0]
        try:
            __import__(pkg_name.replace('-', '_'))
        except ImportError:
            print(f"📦 Installing {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Run package check
ensure_packages()

# Now continue with the rest of your imports
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
from typing import List, Dict, Set, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import OrderedDict, defaultdict, deque
from urllib.parse import urlparse, parse_qs, urlencode
import aiohttp
from contextlib import asynccontextmanager
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from bs4 import BeautifulSoup

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
from telegram.error import TelegramError, Conflict, BadRequest
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl import functions, types
from telethon.errors import (
    FloodWaitError, ChannelPrivateError, UsernameNotOccupiedError,
    InviteHashInvalidError, InviteHashExpiredError, ChatAdminRequiredError,
    SessionPasswordNeededError, PhoneCodeInvalidError, AuthKeyError,
    UserNotParticipantError, ChatWriteForbiddenError
)

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
import threading

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
        'normal': 0.5,
        'join_request': 3.0,
        'search': 1.0,
        'flood_wait': 5.0,
        'between_sessions': 1.0,
        'between_tasks': 0.2,
        'min_cycle_delay': 5.0,
        'max_cycle_delay': 30.0,
        'validation_delay': 1.0
    }
    
    # Collection limits - حدود الجمع
    MAX_DIALOGS_PER_SESSION = 100
    MAX_MESSAGES_PER_SEARCH = 50
    MAX_SEARCH_TERMS = 10
    MAX_LINKS_PER_CYCLE = 500
    MAX_BATCH_SIZE = 100
    
    # Database - قاعدة البيانات
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10
    DB_POOL_SIZE = 5
    
    # WhatsApp collection - جمع واتساب
    WHATSAPP_DAYS_BACK = 60
    
    # Link verification - التحقق من الروابط
    MIN_GROUP_MEMBERS = 3
    MAX_LINK_LENGTH = 200
    VALIDATION_TIMEOUT = 30
    
    # Rate limiting - الحد من الطلبات
    USER_RATE_LIMIT = {
        'max_requests': 20,
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
    
    # Collection settings - إعدادات الجمع
    COLLECT_ONLY_GROUPS = False  # جمع القنوات أيضاً
    MIN_MEMBERS_FOR_GROUP = 1  # الحد الأدنى للأعضاء في المجموعة
    COLLECT_ACTIVE_LINKS_ONLY = True  # جمع الروابط النشطة فقط
    ENABLE_DEEP_COLLECTION = True  # تمكين الجمع العميق
    MAX_DEEP_MESSAGES = 50  # الحد الأقصى للرسائل في الجمع العميق
    
    # Search keywords for links - كلمات البحث للروابط
    SEARCH_KEYWORDS = [
        'chat.whatsapp.com',
        't.me/+',
        't.me/joinchat',
        'telegram.me/+',
        'telegram.me/joinchat',
        'discord.gg',
        'discord.com/invite',
        'signal.group'
    ]

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
# Single Instance Manager - مدير النسخة الواحدة
# ======================

class SingleInstanceManager:
    """منع تشغيل أكثر من نسخة واحدة من البوت"""
    _instance = None
    _lock = asyncio.Lock()
    _is_running = False
    
    @classmethod
    async def get_instance(cls):
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = SingleInstanceManager()
        return cls._instance
    
    async def acquire_lock(self) -> bool:
        """الحصول على قفل للتأكد من نسخة واحدة فقط"""
        async with self._lock:
            if self._is_running:
                logger.error("⚠️ تم اكتشاف نسخة أخرى من البوت قيد التشغيل!")
                return False
            self._is_running = True
            return True
    
    async def release_lock(self):
        """تحرير القفل"""
        async with self._lock:
            self._is_running = False
    
    def is_running(self) -> bool:
        """التحقق إذا كان البوت يعمل"""
        return self._is_running

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
        """Extract comprehensive information from URL"""
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
        """Extract Telegram specific information"""
        result = {
            'is_valid': True,  # جميع روابط تيليجرام صالحة
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
            'is_active': True,
            'is_join_link': False,
            'is_subscription': False
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
            result['is_group'] = True
            result['is_join_link'] = True
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
                result['username'] = channel_name
                result['is_subscription'] = True
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
                result['is_join_link'] = True
            else:
                result['is_group'] = True
                result['is_public'] = True
                result['is_supergroup'] = True
        
        # كشف المجموعات مع مسار أطول
        elif len(segments) >= 2:
            if segments[0].lower() in ['c', 'channel', 's']:
                result['is_channel'] = True
                result['is_broadcast'] = True
                result['is_subscription'] = True
            elif segments[0].lower() == 'joinchat':
                result['is_join_request'] = True
                result['is_private'] = True
                result['invite_hash'] = segments[1] if len(segments) > 1 else ''
                result['is_group'] = True
                result['is_join_link'] = True
            else:
                result['is_group'] = True
                result['is_public'] = True
                result['is_supergroup'] = True
        
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

# ======================
# Enhanced Database Manager - مدير قاعدة البيانات المحسن
# ======================

class EnhancedDatabaseManager:
    """Advanced database management"""
    
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    
    @classmethod
    async def get_instance(cls):
        """Get database instance"""
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
        
        # إنشاء الاتصال بقاعدة البيانات
        self.conn = await aiosqlite.connect(self.db_path)
        
        # تهيئة الجداول
        await self._create_tables()
        
        self._initialized = True
        logger.info(f"✅ تم تهيئة قاعدة البيانات بنجاح: {self.db_path}")
    
    async def _create_tables(self):
        """Create database tables"""
        # جدول الجلسات
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_string TEXT NOT NULL,
                session_hash TEXT UNIQUE NOT NULL,
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
                metadata TEXT
            )
        ''')
        
        # جدول الروابط
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
                is_subscription BOOLEAN DEFAULT 0,
                is_valid_group BOOLEAN DEFAULT 0,
                last_validated TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE SET NULL
            )
        ''')
        
        # جدول المستخدمين
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
        
        # جدول النسخ الاحتياطي
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_id TEXT UNIQUE NOT NULL,
                timestamp TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_path TEXT,
                size_bytes INTEGER,
                checksum TEXT,
                status TEXT DEFAULT 'success',
                metadata TEXT
            )
        ''')
        
        await self.conn.commit()
        
        # إنشاء فهارس
        await self._create_indexes()
    
    async def _create_indexes(self):
        """Create database indexes"""
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_links_url_hash ON links(url_hash)',
            'CREATE INDEX IF NOT EXISTS idx_links_platform ON links(platform)',
            'CREATE INDEX IF NOT EXISTS idx_links_collected_date ON links(collected_date)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_group ON links(is_group)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_subscription ON links(is_subscription)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_valid_group ON links(is_valid_group)',
            'CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)',
            'CREATE INDEX IF NOT EXISTS idx_users_last_active ON bot_users(last_active)'
        ]
        
        for index_sql in indexes:
            try:
                await self.conn.execute(index_sql)
            except Exception as e:
                logger.error(f"خطأ في إنشاء الفهرس: {e}")
        
        await self.conn.commit()
    
    async def add_link(self, link_info: Dict) -> Tuple[bool, str, Dict]:
        """Add link to database"""
        try:
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
                # تحديث الرابط الموجود
                await self.conn.execute('''
                    UPDATE links SET 
                    last_checked = CURRENT_TIMESTAMP,
                    check_count = check_count + 1,
                    is_active = ?,
                    members_count = ?,
                    validation_score = ?
                    WHERE id = ?
                ''', (
                    link_info.get('is_active', True),
                    link_info.get('members', 0),
                    link_info.get('validation_score', 0),
                    existing[0]
                ))
                await self.conn.commit()
                return False, "تم تحديث الرابط الموجود", {'link_id': existing[0]}
            
            # إعداد بيانات الرابط
            cursor = await self.conn.execute('''
                INSERT INTO links 
                (url_hash, url, original_url, platform, link_type, telegram_type, title, 
                 description, members_count, session_id, confidence, 
                 is_active, requires_join, is_verified, validation_score, metadata, 
                 tags, added_by_user, source, is_channel, is_group, is_join_request, 
                 is_supergroup, is_subscription, is_valid_group, last_validated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                url_info['url_hash'],
                url_info['normalized_url'],
                url_info['original_url'],
                url_info['platform'],
                link_info.get('link_type', 'unknown'),
                details.get('telegram_type', ''),
                link_info.get('title', '')[:500],
                link_info.get('description', '')[:1000],
                link_info.get('members', 0),
                link_info.get('session_id'),
                link_info.get('confidence', 'medium'),
                link_info.get('is_active', True),
                details.get('is_join_request', False),
                link_info.get('is_verified', False),
                link_info.get('validation_score', 0),
                json.dumps(link_info.get('metadata', {})),
                json.dumps(link_info.get('tags', [])),
                link_info.get('added_by_user', 0),
                link_info.get('source', 'manual'),
                details.get('is_channel', False),
                details.get('is_group', True),
                details.get('is_join_request', False),
                details.get('is_supergroup', False),
                details.get('is_subscription', False),
                link_info.get('is_valid_group', True),  # تلقائياً صالح
                link_info.get('last_validated', datetime.now().isoformat())
            ))
            
            link_id = cursor.lastrowid
            
            # تحديث إحصائيات المستخدم
            if link_info.get('added_by_user'):
                await self.update_user_stats(link_info['added_by_user'], 'link_added')
            
            # تحديث إحصائيات الجلسة
            if link_info.get('session_id'):
                await self.conn.execute(
                    "UPDATE sessions SET total_links = total_links + 1 WHERE id = ?",
                    (link_info['session_id'],)
                )
            
            await self.conn.commit()
            
            return True, "تمت إضافة الرابط بنجاح", {
                'link_id': link_id,
                'url_hash': url_info['url_hash']
            }
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الرابط: {e}")
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def add_session(self, session_data: Dict) -> Tuple[bool, str, Dict]:
        """Add session to database"""
        try:
            session_string = session_data.get('session_string', '')
            if not session_string:
                return False, "جلسة فارغة", {}
            
            session_hash = hashlib.md5(session_string.encode()).hexdigest()
            
            # التحقق من التكرار
            cursor = await self.conn.execute(
                'SELECT id FROM sessions WHERE session_hash = ?',
                (session_hash,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                return False, "الجلسة موجودة مسبقاً", {'session_id': existing[0]}
            
            cursor = await self.conn.execute('''
                INSERT INTO sessions 
                (session_string, session_hash, phone_number, user_id, username, 
                 display_name, added_by_user, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_string,
                session_hash,
                session_data.get('phone_number', ''),
                session_data.get('user_id', 0),
                session_data.get('username', ''),
                session_data.get('display_name', ''),
                session_data.get('added_by_user', 0),
                json.dumps(session_data.get('metadata', {}))
            ))
            
            session_id = cursor.lastrowid
            
            # تحديث إحصائيات المستخدم
            if session_data.get('added_by_user'):
                await self.update_user_stats(session_data['added_by_user'], 'session_added')
            
            await self.conn.commit()
            
            return True, "تمت إضافة الجلسة بنجاح", {
                'session_id': session_id,
                'session_hash': session_hash
            }
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الجلسة: {e}")
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def update_user_stats(self, user_id: int, action: str, value: int = 1):
        """Update user statistics"""
        try:
            update_query = '''
                UPDATE bot_users 
                SET last_active = CURRENT_TIMESTAMP,
                    request_count = request_count + 1
            '''
            
            if action == 'session_added':
                update_query += ', session_count = session_count + 1'
            elif action == 'link_added':
                update_query += ', link_count = link_count + ?, total_links_added = total_links_added + ?'
            
            update_query += ' WHERE user_id = ?'
            
            if action == 'link_added':
                await self.conn.execute(update_query, (value, value, user_id))
            else:
                await self.conn.execute(update_query, (user_id,))
            
            await self.conn.commit()
            
        except Exception as e:
            logger.debug(f"خطأ في تحديث إحصائيات المستخدم: {e}")
    
    async def add_or_update_user(self, user_id: int, username: str = None, 
                                first_name: str = None, last_name: str = None):
        """Add or update user"""
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
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """Get user statistics"""
        try:
            cursor = await self.conn.execute('''
                SELECT *, 
                       (SELECT COUNT(*) FROM links WHERE added_by_user = ?) as total_links,
                       (SELECT COUNT(*) FROM sessions WHERE added_by_user = ?) as total_sessions
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
    
    async def get_active_sessions(self, limit: int = 10) -> List[Dict]:
        """Get active sessions"""
        try:
            cursor = await self.conn.execute('''
                SELECT * FROM sessions 
                WHERE is_active = 1 
                ORDER BY last_used ASC
                LIMIT ?
            ''', (limit,))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            sessions = []
            for row in rows:
                session_dict = dict(zip(columns, row))
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
    
    async def get_links_count(self) -> int:
        """Get total links count"""
        try:
            cursor = await self.conn.execute('SELECT COUNT(*) FROM links')
            result = await cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"خطأ في الحصول على عدد الروابط: {e}")
            return 0
    
    async def get_stats_summary(self) -> Dict:
        """Get database statistics summary"""
        try:
            stats = {}
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links")
            stats['total_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_valid_group = 1")
            stats['valid_groups'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_subscription = 1")
            stats['subscriptions'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT platform, COUNT(*) FROM links WHERE is_valid_group = 1 GROUP BY platform")
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_verified = 1")
            stats['verified_links'] = (await cursor.fetchone())[0]
            
            return stats
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على ملخص الإحصائيات: {e}")
            return {}
    
    async def export_links(self, filters: Dict = None, limit: int = 1000) -> List[str]:
        """Export links"""
        try:
            query = 'SELECT url FROM links WHERE 1=1'
            params = []
            
            if filters:
                if filters.get('platform'):
                    query += " AND platform = ?"
                    params.append(filters['platform'])
                
                if filters.get('min_members'):
                    query += " AND members_count >= ?"
                    params.append(filters['min_members'])
            else:
                query += " AND is_valid_group = 1"
            
            query += " ORDER BY collected_date DESC LIMIT ?"
            params.append(limit)
            
            cursor = await self.conn.execute(query, params)
            rows = await cursor.fetchall()
            
            return [row[0] for row in rows]
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الروابط: {e}")
            return []
    
    async def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            await self.conn.close()
            self._initialized = False

# ======================
# Session Manager - مدير الجلسات
# ======================

class SessionManager:
    """Manage Telegram sessions"""
    
    @staticmethod
    async def validate_session(session_string: str) -> Tuple[bool, Dict]:
        """Validate Telegram session"""
        try:
            # تنظيف سلسلة الجلسة
            session_string = session_string.strip()
            
            # التحقق من طول الجلسة
            if len(session_string) < 50:
                return False, {'error': 'جلسة قصيرة جداً', 'details': 'يجب أن تكون الجلسة أطول من 50 حرفاً'}
            
            client = TelegramClient(
                StringSession(session_string),
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
                'last_name': me.last_name or ''
            }
            
            await client.disconnect()
            
            return True, {
                'user_info': user_info,
                'session_length': len(session_string)
            }
            
        except ValueError as e:
            return False, {'error': 'جلسة غير صالحة', 'details': 'تنسيق الجلسة خاطئ'}
        except Exception as e:
            return False, {'error': 'خطأ في التحقق', 'details': str(e)[:200]}
    
    @staticmethod
    async def create_client(session_string: str) -> Optional[TelegramClient]:
        """Create Telegram client from session string"""
        try:
            # تنظيف سلسلة الجلسة
            session_string = session_string.strip()
            
            # التحقق من صحة سلسلة الجلسة
            if len(session_string) < 50:
                logger.error(f"جلسة قصيرة جداً: {len(session_string)} حرف")
                return None
            
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH,
                device_model="Link Collector",
                system_version="Linux 6.5",
                app_version="4.16.30",
                timeout=30,
                connection_retries=3
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                logger.error("الجلسة غير مصرح بها")
                return None
            
            return client
            
        except ValueError as e:
            logger.error(f"خطأ في تنسيق الجلسة: {e}")
            return None
        except Exception as e:
            logger.error(f"خطأ في إنشاء العميل: {e}")
            return None

# ======================
# Advanced Link Collector - جامع الروابط المتقدم
# ======================

class AdvancedLinkCollector:
    """Advanced link collector with intelligent search"""
    
    @staticmethod
    async def search_links_in_dialog(client: TelegramClient, dialog, max_messages: int = 50) -> List[str]:
        """Search for links in dialog messages"""
        all_links = []
        
        try:
            entity = dialog.entity
            
            # البحث في الوصف
            if hasattr(entity, 'about') and entity.about:
                links = AdvancedLinkCollector._extract_links_from_text(entity.about)
                all_links.extend(links)
            
            # البحث في الرسائل باستخدام الكلمات المفتاحية
            for keyword in Config.SEARCH_KEYWORDS:
                try:
                    async for message in client.iter_messages(
                        entity,
                        search=keyword,
                        limit=max_messages // len(Config.SEARCH_KEYWORDS)
                    ):
                        if message.text:
                            links = AdvancedLinkCollector._extract_links_from_text(message.text)
                            all_links.extend(links)
                        
                        # البحث في المرفقات (Pin)
                        if message.media and hasattr(message.media, 'document'):
                            try:
                                if hasattr(message.media.document, 'attributes'):
                                    for attr in message.media.document.attributes:
                                        if hasattr(attr, 'file_name'):
                                            links = AdvancedLinkCollector._extract_links_from_text(attr.file_name)
                                            all_links.extend(links)
                            except:
                                pass
                        
                        await asyncio.sleep(0.05)
                        
                except Exception as e:
                    logger.debug(f"خطأ في البحث عن {keyword}: {e}")
                    continue
            
            # البحث في التعليقات (تعليقات Pin)
            try:
                async for message in client.iter_messages(entity, limit=20):
                    if message.reply_markup:
                        try:
                            for row in message.reply_markup.rows:
                                for button in row.buttons:
                                    if hasattr(button, 'url'):
                                        links = AdvancedLinkCollector._extract_links_from_text(button.url)
                                        all_links.extend(links)
                        except:
                            pass
            except:
                pass
            
            # إزالة التكرارات
            unique_links = []
            seen = set()
            for link in all_links:
                if link not in seen:
                    seen.add(link)
                    unique_links.append(link)
            
            return unique_links
            
        except Exception as e:
            logger.error(f"خطأ في البحث في الدردشة: {e}")
            return []
    
    @staticmethod
    def _extract_links_from_text(text: str) -> List[str]:
        """Extract links from text with advanced patterns"""
        if not text:
            return []
        
        # أنماط متقدمة للبحث عن الروابط
        patterns = [
            # روابط تيليجرام كاملة
            r'https?://(?:t\.me|telegram\.me|telegram\.dog)/(?:joinchat/)?\+?[A-Za-z0-9_-]+',
            # روابط واتساب كاملة
            r'https?://chat\.whatsapp\.com/[A-Za-z0-9]+',
            # روابط ديسكورد كاملة
            r'https?://(?:discord\.gg|discord\.com/invite)/[A-Za-z0-9]+',
            # روابط سيجنال كاملة
            r'https?://signal\.group/[A-Za-z0-9]+',
            # روابط مختصرة
            r't\.me/\+[A-Za-z0-9_-]+',
            r'chat\.whatsapp\.com/[A-Za-z0-9]+',
            r'discord\.gg/[A-Za-z0-9]+',
            r'signal\.group/[A-Za-z0-9]+'
        ]
        
        links = []
        for pattern in patterns:
            found = re.findall(pattern, text, re.IGNORECASE)
            links.extend(found)
        
        # تنظيف الروابط
        cleaned_links = []
        for link in links:
            if not link.startswith(('http://', 'https://')):
                if 't.me' in link:
                    link = 'https://' + link
                elif 'chat.whatsapp.com' in link:
                    link = 'https://' + link
                elif 'discord.gg' in link:
                    link = 'https://' + link
                elif 'signal.group' in link:
                    link = 'https://' + link
            
            # إزالة المسافات الزائدة
            link = link.strip()
            link = re.sub(r'\s+', '', link)
            
            cleaned_links.append(link)
        
        return cleaned_links

# ======================
# Collection Manager - مدير الجمع
# ======================

class CollectionManager:
    """Manage link collection"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        self.stats = {
            'total_collected': 0,
            'total_processed': 0,
            'valid_groups': 0,
            'subscriptions_skipped': 0,
            'telegram': 0,
            'whatsapp': 0,
            'discord': 0,
            'signal': 0,
            'errors': 0,
            'sessions_used': 0,
            'last_collection_time': None
        }
        self.collection_task = None
    
    async def start_collection(self):
        """Start collection process"""
        if self.active:
            return
        
        self.active = True
        self.paused = False
        self.stop_requested = False
        
        logger.info("🚀 بدء عملية الجمع الحقيقية")
        
        # بدء مهمة الجمع في الخلفية
        self.collection_task = asyncio.create_task(self._collection_loop())
    
    async def _collection_loop(self):
        """Main collection loop"""
        while self.active and not self.stop_requested:
            if self.paused:
                await asyncio.sleep(1)
                continue
            
            try:
                await self._collection_cycle()
                
                # تأخير بين الدورات
                delay = Config.REQUEST_DELAYS['max_cycle_delay']
                logger.info(f"⏳ تأخير {delay} ثانية قبل الدورة القادمة")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"خطأ في دورة الجمع: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(10)
        
        self.active = False
        logger.info("⏹️ توقفت عملية الجمع")
    
    async def _collection_cycle(self):
        """Single collection cycle"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=Config.MAX_CONCURRENT_SESSIONS)
            
            if not sessions:
                logger.warning("لا توجد جلسات نشطة")
                return
            
            self.stats['sessions_used'] = len(sessions)
            self.stats['last_collection_time'] = datetime.now().isoformat()
            
            tasks = []
            for session in sessions:
                task = self._process_session(session)
                tasks.append(task)
                await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful = sum(1 for r in results if not isinstance(r, Exception))
            logger.info(f"اكتملت دورة الجمع: {successful}/{len(tasks)} جلسات ناجحة")
            
            # حفظ الإحصائيات
            await self._save_stats()
            
        except Exception as e:
            logger.error(f"خطأ في دورة الجمع: {e}")
            self.stats['errors'] += 1
    
    async def _process_session(self, session: Dict):
        """Process single session"""
        try:
            session_string = session.get('session_string', '')
            session_id = session.get('id')
            
            if not session_string or session_string == '********':
                logger.error(f"جلسة {session_id} غير متاحة")
                return {'status': 'error', 'reason': 'جلسة غير متاحة'}
            
            # فك تشفير الجلسة
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt(session_string)
            
            client = await SessionManager.create_client(decrypted_session)
            if not client:
                return {'status': 'error', 'reason': 'فشل إنشاء العميل'}
            
            # جمع الروابط من الدردشات
            collected = await self._collect_from_dialogs(client, session_id)
            
            await client.disconnect()
            
            # تحديث إحصائيات الجلسة
            db = await EnhancedDatabaseManager.get_instance()
            await db.conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, last_success = CURRENT_TIMESTAMP, total_uses = total_uses + 1, total_links = total_links + ? WHERE id = ?",
                (len(collected), session_id)
            )
            await db.conn.commit()
            
            return {'status': 'success', 'collected': len(collected)}
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الجلسة: {e}")
            self.stats['errors'] += 1
            return {'status': 'error', 'reason': str(e)}
    
    async def _collect_from_dialogs(self, client: TelegramClient, session_id: int) -> List[Dict]:
        """Collect links from dialogs"""
        collected = []
        
        try:
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    # جمع الروابط من الدردشة
                    links = await AdvancedLinkCollector.search_links_in_dialog(
                        client, 
                        dialog,
                        max_messages=Config.MAX_DEEP_MESSAGES if Config.ENABLE_DEEP_COLLECTION else 30
                    )
                    
                    if links:
                        logger.info(f"✅ جمع {len(links)} روابط من {dialog.name}")
                        
                        # معالجة الروابط المجمعة
                        for link in links:
                            link_info = await self._process_link(link, session_id, dialog)
                            if link_info:
                                collected.append(link_info)
                        
                        # تحديث الإحصائيات
                        self.stats['total_processed'] += 1
                    
                    await asyncio.sleep(Config.REQUEST_DELAYS['normal'])
                    
                except Exception as e:
                    logger.debug(f"خطأ في جمع الروابط من الدردشة: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"خطأ في جمع الروابط من الدردشات: {e}")
        
        return collected
    
    async def _process_link(self, url: str, session_id: int, dialog) -> Optional[Dict]:
        """Process and save a single link"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return None
            
            platform = url_info['platform']
            details = url_info['details']
            
            # تحديد نوع الرابط
            if details.get('is_channel', False):
                link_type = 'channel'
            elif details.get('is_group', False):
                link_type = 'group'
            elif details.get('is_join_request', False):
                link_type = 'join_request'
            else:
                link_type = 'unknown'
            
            # تحقق من روابط واتساب القديمة
            if platform == 'whatsapp':
                try:
                    # يمكن إضافة تحقق من تاريخ الرابط هنا إذا كان متاحاً
                    pass
                except:
                    pass
            
            link_info = {
                'url': url,
                'url_hash': url_info['url_hash'],
                'platform': platform,
                'link_type': link_type,
                'telegram_type': details.get('telegram_type', ''),
                'session_id': session_id,
                'confidence': 'high',
                'is_active': True,
                'requires_join': details.get('is_join_request', False),
                'is_verified': True,
                'validation_score': 100,
                'members': 0,
                'metadata': {
                    'collected_at': datetime.now().isoformat(),
                    'platform_details': url_info['details'],
                    'source_dialog': dialog.name,
                    'source_type': 'real_collection'
                },
                'source': 'advanced_collection',
                'is_channel': details.get('is_channel', False),
                'is_group': details.get('is_group', True),
                'is_join_request': details.get('is_join_request', False),
                'is_supergroup': details.get('is_supergroup', False),
                'is_subscription': details.get('is_subscription', False),
                'is_valid_group': True,  # جميعها صالحة
                'last_validated': datetime.now().isoformat()
            }
            
            db = await EnhancedDatabaseManager.get_instance()
            success, message, details = await db.add_link(link_info)
            
            if success:
                # تحديث الإحصائيات
                self.stats['total_collected'] += 1
                if platform == 'telegram':
                    self.stats['telegram'] += 1
                elif platform == 'whatsapp':
                    self.stats['whatsapp'] += 1
                elif platform == 'discord':
                    self.stats['discord'] += 1
                elif platform == 'signal':
                    self.stats['signal'] += 1
                
                logger.debug(f"✅ تم حفظ الرابط: {url}")
                return link_info
            
            return None
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الرابط {url}: {e}")
            return None
    
    async def _save_stats(self):
        """Save statistics"""
        try:
            stats_file = "collection_stats.json"
            stats_data = {
                'stats': self.stats,
                'last_updated': datetime.now().isoformat()
            }
            
            async with aiofiles.open(stats_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(stats_data, indent=2, ensure_ascii=False))
            
        except Exception as e:
            logger.error(f"خطأ في حفظ الإحصائيات: {e}")
    
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
        logger.info("⏸️ تم إيقاف الجمع مؤقتاً")
    
    async def resume(self):
        """Resume collection"""
        self.paused = False
        logger.info("▶️ تم استئناف الجمع")
    
    async def stop(self):
        """Stop collection"""
        self.stop_requested = True
        logger.info("⏹️ تم طلب إيقاف الجمع")
        
        # انتظار حتى تتوقف المهمة
        if self.collection_task:
            try:
                await asyncio.wait_for(self.collection_task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("مهلة انتظار إيقاف مهمة الجمع")
        
        self.active = False

# ======================
# Encryption Manager - مدير التشفير
# ======================

class EncryptionManager:
    """Encryption manager"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
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
        """Encrypt data"""
        try:
            encrypted = self.cipher.encrypt(data.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"خطأ في التشفير: {e}")
            return data
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt data"""
        try:
            decrypted = self.cipher.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"خطأ في فك التشفير: {e}")
            return encrypted_data

# ======================
# Telegram Bot - بوت تليجرام (محسن)
# ======================

class TelegramBot:
    """Main Telegram bot"""
    
    def __init__(self):
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        self.collection_manager = CollectionManager()
        
        self._setup_handlers()
        
        self.user_states = {}
    
    def _setup_handlers(self):
        """Setup bot handlers"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("backup", self.backup_command))
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        self.app.add_handler(CommandHandler("addsession", self.add_session_command))
        self.app.add_handler(CommandHandler("test_collect", self.test_collect_command))
        self.app.add_handler(CommandHandler("validate_links", self.validate_links_command))
        self.app.add_handler(CommandHandler("add_link", self.add_link_command))
        
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_message
        ))
        
        self.app.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        # إضافة/تحديث المستخدم في قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        await db.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء الجمع الحقيقي", callback_data="start_collect"),
             InlineKeyboardButton("⏸️ إدارة الجمع", callback_data="manage_collect")],
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("👥 الجلسات", callback_data="show_sessions")],
            [InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_links"),
             InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")],
            [InlineKeyboardButton("🧪 اختبار الجمع", callback_data="test_collection"),
             InlineKeyboardButton("🔗 إضافة رابط", callback_data="add_link_direct")]
        ])
        
        welcome_text = (
            f"🤖 **مرحباً {user.first_name}!**\n\n"
            "**بوت جمع روابط المجموعات المتقدم**\n\n"
            "**المميزات الجديدة:**\n"
            "• ✅ جمع حقيقي للروابط النشطة\n"
            "• 🔍 بحث ذكي بالكلمات المفتاحية\n"
            "• 📊 جمع من جميع المنصات\n"
            "• 🚀 أداء سريع ومستقر\n"
            "• 💾 تصدير بجميع الصيغ\n\n"
            "**🚀 اختر من الأزرار أدناه لبدء الجمع!**"
        )
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def test_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /test_collect command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        await update.message.reply_text("🧪 **جاري اختبار الجمع...**")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=1)
            
            if not sessions:
                await update.message.reply_text("❌ لا توجد جلسات نشطة للاختبار")
                return
            
            session = sessions[0]
            session_string = session.get('session_string', '')
            
            if not session_string or session_string == '********':
                await update.message.reply_text("❌ الجلسة غير متاحة")
                return
            
            # فك تشفير الجلسة
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt(session_string)
            
            client = await SessionManager.create_client(decrypted_session)
            if not client:
                await update.message.reply_text("❌ فشل إنشاء العميل")
                return
            
            # اختبار الجمع من أول 3 دردشات
            collected = []
            count = 0
            
            async for dialog in client.iter_dialogs(limit=3):
                try:
                    # جمع الروابط من الدردشة
                    links = await AdvancedLinkCollector.search_links_in_dialog(client, dialog, max_messages=10)
                    
                    if links:
                        test_result = (
                            f"**✅ تم العثور على {len(links)} روابط في:** {dialog.name}\n\n"
                            f"**عينة من الروابط:**\n"
                        )
                        
                        for i, link in enumerate(links[:5], 1):
                            test_result += f"{i}. {link}\n"
                        
                        await update.message.reply_text(test_result, parse_mode="Markdown")
                        
                        # حفظ بعض الروابط كعينة
                        for link in links[:3]:
                            url_info = EnhancedLinkProcessor.extract_url_info(link)
                            if url_info['is_valid']:
                                link_data = {
                                    'url': link,
                                    'platform': url_info['platform'],
                                    'link_type': 'test',
                                    'session_id': session.get('id'),
                                    'is_valid_group': True,
                                    'added_by_user': user.id,
                                    'source': 'test_collection'
                                }
                                
                                success, message, _ = await db.add_link(link_data)
                                if success:
                                    collected.append(link)
                    
                    count += 1
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"خطأ في اختبار الدردشة: {e}")
                    await update.message.reply_text(f"⚠️ خطأ في الدردشة: {str(e)[:100]}")
                    continue
            
            await client.disconnect()
            
            if collected:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 بدء الجمع الحقيقي", callback_data="start_collect"),
                     InlineKeyboardButton("📤 تصدير العينة", callback_data="export_test")]
                ])
                
                await update.message.reply_text(
                    f"✅ **اكتمل الاختبار بنجاح!**\n\n"
                    f"**النتائج:**\n"
                    f"• الدردشات المفحوصة: {count}\n"
                    f"• الروابط المجمعة: {len(collected)}\n"
                    f"• تم حفظها في قاعدة البيانات\n\n"
                    f"**يمكنك الآن:**\n"
                    f"1. بدء الجمع الحقيقي\n"
                    f"2. تصدير الروابط المجمعة\n"
                    f"3. إضافة المزيد من الجلسات",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "⚠️ **لم يتم العثور على روابط في الدردشات المختبرة**\n\n"
                    "**نصائح:**\n"
                    "• تأكد من أن الجلسة نشطة\n"
                    "• حاول مع جلسة أخرى\n"
                    "• تأكد من وجود مجموعات بها روابط\n"
                    "• استخدم /addsession لإضافة جلسة جديدة",
                    parse_mode="Markdown"
                )
            
        except Exception as e:
            logger.error(f"خطأ في اختبار الجمع: {e}")
            await update.message.reply_text(f"❌ خطأ في الاختبار: {str(e)[:200]}")
    
    async def add_link_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_link command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        if not context.args:
            await update.message.reply_text(
                "**استخدام الأمر:**\n"
                "`/add_link [الرابط]`\n\n"
                "**أمثلة:**\n"
                "`/add_link https://t.me/joinchat/abc123`\n"
                "`/add_link https://chat.whatsapp.com/def456`\n"
                "`/add_link discord.gg/xyz789`"
            )
            return
        
        url = ' '.join(context.args)
        
        await update.message.reply_text(f"⏳ جاري إضافة الرابط: {url[:50]}...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                await update.message.reply_text("❌ رابط غير صالح")
                return
            
            link_data = {
                'url': url,
                'platform': url_info['platform'],
                'link_type': 'manual',
                'is_valid_group': True,
                'added_by_user': user.id,
                'source': 'manual_add'
            }
            
            success, message, details = await db.add_link(link_data)
            
            if success:
                await update.message.reply_text(
                    f"✅ **تمت إضافة الرابط بنجاح!**\n\n"
                    f"**المعلومات:**\n"
                    f"• الرابط: {url_info['normalized_url'][:50]}...\n"
                    f"• المنصة: {url_info['platform']}\n"
                    f"• النوع: {url_info['details'].get('telegram_type', 'عام')}\n"
                    f"• معرف الرابط: {details.get('link_id', 'N/A')}\n\n"
                    f"**الروابط الإجمالية:** {await db.get_links_count():,}",
                    parse_mode="Markdown"
                )
            else:
                if "تم تحديث" in message:
                    await update.message.reply_text(f"✅ {message}")
                else:
                    await update.message.reply_text(f"❌ {message}")
                    
        except Exception as e:
            logger.error(f"خطأ في إضافة الرابط: {e}")
            await update.message.reply_text(f"❌ خطأ في الإضافة: {str(e)[:100]}")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        total_links = await db.get_links_count()
        
        if total_links == 0:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة رابط يدوي", callback_data="add_link_direct"),
                 InlineKeyboardButton("🧪 اختبار الجمع", callback_data="test_collection")],
                [InlineKeyboardButton("🚀 بدء الجمع الحقيقي", callback_data="start_collect")]
            ])
            
            await update.message.reply_text(
                "❌ **لا توجد روابط صالحة للتصدير**\n\n"
                "**لجمع الروابط:**\n"
                "1. أضف جلسة باستخدام /addsession\n"
                "2. اختبر الجمع باستخدام /test_collect\n"
                "3. ابدأ الجمع الحقيقي باستخدام /collect\n"
                "4. أو أضف رابط يدوياً باستخدام /add_link",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 تصدير نصي", callback_data="export_txt"),
             InlineKeyboardButton("📊 تصدير CSV", callback_data="export_csv")],
            [InlineKeyboardButton("📋 تصدير JSON", callback_data="export_json"),
             InlineKeyboardButton("📦 جميع الروابط", callback_data="export_all")],
            [InlineKeyboardButton("📢 تيليجرام فقط", callback_data="export_telegram"),
             InlineKeyboardButton("📱 واتساب فقط", callback_data="export_whatsapp")],
            [InlineKeyboardButton("🎮 ديسكورد فقط", callback_data="export_discord"),
             InlineKeyboardButton("📡 سيجنال فقط", callback_data="export_signal")]
        ])
        
        export_text = (
            f"**📤 تصدير الروابط**\n\n"
            f"إجمالي الروابط: **{total_links:,}**\n\n"
            "**خيارات التصدير:**\n"
            "• 📄 نصي - روابط فقط\n"
            "• 📊 CSV - مع المعلومات\n"
            "• 📋 JSON - كامل المعلومات\n"
            "• 📦 جميع الروابط\n"
            "• 📢 روابط تيليجرام فقط\n"
            "• 📱 روابط واتساب فقط\n"
            "• 🎮 روابط ديسكورد فقط\n"
            "• 📡 روابط سيجنال فقط\n\n"
            "**ملاحظات:**\n"
            f"• الحد الأقصى للتصدير: {Config.MAX_EXPORT_LINKS:,} رابط\n"
            "• الروابط تنسيقها نظيف وجاهز للاستخدام"
        )
        
        await update.message.reply_text(export_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user  # إصلاح: استخدام query.from_user بدلاً من query.effective_user
        
        data = query.data
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await query.edit_message_text("❌ غير مصرح لك بالوصول")
                return
        
        try:
            if data == "start_collect":
                await self._handle_start_collect(query, user)
            elif data == "pause_collect":
                await self._handle_pause_collect(query)
            elif data == "stop_collect":
                await self._handle_stop_collect(query)
            elif data == "test_collection":
                await self._handle_test_collection(query, user)
            elif data == "add_session":
                await self._handle_add_session(query)
            elif data == "add_link_direct":
                await self._handle_add_link_direct(query)
            elif data == "export_txt":
                await self._handle_export_txt(query, user)
            elif data == "export_csv":
                await self._handle_export_csv(query, user)
            elif data == "export_json":
                await self._handle_export_json(query, user)
            elif data == "export_all":
                await self._handle_export_all(query, user)
            elif data == "export_telegram":
                await self._handle_export_telegram(query, user)
            elif data == "export_whatsapp":
                await self._handle_export_whatsapp(query, user)
            elif data == "export_discord":
                await self._handle_export_discord(query, user)
            elif data == "export_signal":
                await self._handle_export_signal(query, user)
            elif data == "export_test":
                await self._handle_export_test(query, user)
            elif data == "refresh_status":
                await self.status_command(query.message, query.message.reply_to_message)
            elif data == "refresh_sessions":
                await self.sessions_command(query.message, query.message.reply_to_message)
            elif data == "show_stats":
                await self._handle_show_stats(query)
            elif data == "show_sessions":
                await self._handle_show_sessions(query)
            else:
                await query.edit_message_text(f"❌ أمر غير معروف: {data}")
        
        except Exception as e:
            logger.error(f"خطأ في معالجة الاستدعاء: {e}")
            await query.edit_message_text(f"❌ حدث خطأ: {str(e)[:100]}")

    async def _handle_start_collect(self, query, user):
        """Handle start collection"""
        if self.collection_manager.active:
            await query.edit_message_text("⏳ الجمع يعمل بالفعل")
            return
        
        await query.edit_message_text("🚀 **جاري بدء الجمع...**")
        
        # بدء مهمة الجمع الحقيقية
        await self.collection_manager.start_collection()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 حالة الجمع", callback_data="refresh_status"),
             InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_links")]
        ])
        
        await query.edit_message_text(
            "🚀 **بدأ الجمع الحقيقي بنجاح!**\n\n"
            "**المميزات النشطة:**\n"
            "✅ جمع ذكي بالكلمات المفتاحية\n"
            "✅ البحث في الوصف والرسائل\n"
            "✅ جمع من جميع المنصات\n"
            "✅ أداء سريع ومستقر\n\n"
            "**تفاصيل:**\n"
            "• جاري جمع الروابط من الجلسات النشطة\n"
            "• البحث عن: chat.whatsapp.com, t.me/+, discord.gg\n"
            "• الروابط تحفظ تلقائياً في قاعدة البيانات\n"
            "• يمكنك التصدير في أي وقت\n\n"
            "⏳ **سيتم تحديث الإحصائيات تلقائياً**",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_test_collection(self, query, user):
        """Handle test collection"""
        await query.edit_message_text("🧪 **جاري اختبار الجمع...**")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=1)
            
            if not sessions:
                await query.edit_message_text("❌ لا توجد جلسات نشطة للاختبار")
                return
            
            session = sessions[0]
            session_string = session.get('session_string', '')
            
            if not session_string or session_string == '********':
                await query.edit_message_text("❌ الجلسة غير متاحة")
                return
            
            # فك تشفير الجلسة
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt(session_string)
            
            client = await SessionManager.create_client(decrypted_session)
            if not client:
                await query.edit_message_text("❌ فشل إنشاء العميل")
                return
            
            # اختبار سريع
            test_links = []
            count = 0
            
            async for dialog in client.iter_dialogs(limit=2):
                try:
                    links = await AdvancedLinkCollector.search_links_in_dialog(client, dialog, max_messages=5)
                    
                    if links:
                        for link in links[:2]:
                            url_info = EnhancedLinkProcessor.extract_url_info(link)
                            if url_info['is_valid']:
                                link_data = {
                                    'url': link,
                                    'platform': url_info['platform'],
                                    'link_type': 'test',
                                    'session_id': session.get('id'),
                                    'is_valid_group': True,
                                    'added_by_user': user.id,
                                    'source': 'test_collection'
                                }
                                
                                success, message, _ = await db.add_link(link_data)
                                if success:
                                    test_links.append(link)
                    
                    count += 1
                    
                except Exception as e:
                    logger.debug(f"خطأ في اختبار الدردشة: {e}")
                    continue
            
            await client.disconnect()
            
            if test_links:
                await query.edit_message_text(
                    f"✅ **اكتمل الاختبار بنجاح!**\n\n"
                    f"**النتائج:**\n"
                    f"• الدردشات المفحوصة: {count}\n"
                    f"• الروابط المجمعة: {len(test_links)}\n"
                    f"• تم حفظها في قاعدة البيانات\n\n"
                    f"**عينة من الروابط:**\n"
                    + "\n".join([f"• {link[:50]}..." for link in test_links[:3]]),
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(
                    "⚠️ **لم يتم العثور على روابط**\n\n"
                    "**تلميحات:**\n"
                    "• تأكد من أن الجلسة نشطة\n"
                    "• حاول مع جلسة أخرى\n"
                    "• تأكد من وجود دردشات بها روابط",
                    parse_mode="Markdown"
                )
            
        except Exception as e:
            logger.error(f"خطأ في اختبار الجمع: {e}")
            await query.edit_message_text(f"❌ خطأ في الاختبار: {str(e)[:100]}")
    
    async def _handle_add_link_direct(self, query):
        """Handle direct link addition"""
        await query.edit_message_text(
            "**🔗 إضافة رابط مباشر**\n\n"
            "أرسل الرابط الآن:\n\n"
            "**تنسيقات مقبولة:**\n"
            "• https://t.me/joinchat/...\n"
            "• https://chat.whatsapp.com/...\n"
            "• https://discord.gg/...\n"
            "• https://signal.group/...\n\n"
            "أو استخدم الأمر:\n"
            "`/add_link [الرابط]`",
            parse_mode="Markdown"
        )
    
    async def _handle_export_txt(self, query, user):
        """Handle export as text"""
        await query.edit_message_text("⏳ جاري تحضير الملف...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links(limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await query.edit_message_text("❌ لا توجد روابط للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"links_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📄 ملف التصدير النصي\nعدد الروابط: {len(links):,}"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await query.edit_message_text(f"✅ تم تصدير {len(links):,} رابط")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير النصي: {e}")
            await query.edit_message_text(f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_csv(self, query, user):
        """Handle export as CSV"""
        await query.edit_message_text("⏳ جاري تحضير الملف...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            cursor = await db.conn.execute('''
                SELECT url, platform, link_type, members_count, collected_date 
                FROM links 
                LIMIT ?
            ''', (Config.MAX_EXPORT_LINKS,))
            
            rows = await cursor.fetchall()
            
            if not rows:
                await query.edit_message_text("❌ لا توجد روابط للتصدير")
                return
            
            # حفظ في ملف CSV
            filename = f"links_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("URL,Platform,Type,Members,Date\n")
                for row in rows:
                    url, platform, link_type, members, date = row
                    f.write(f'"{url}","{platform}","{link_type}",{members},"{date}"\n')
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📊 ملف التصدير CSV\nعدد السجلات: {len(rows):,}"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await query.edit_message_text(f"✅ تم تصدير {len(rows):,} سجل")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير CSV: {e}")
            await query.edit_message_text(f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_json(self, query, user):
        """Handle export as JSON"""
        await query.edit_message_text("⏳ جاري تحضير الملف...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            cursor = await db.conn.execute('''
                SELECT url, platform, link_type, telegram_type, members_count, 
                       collected_date, is_verified, validation_score 
                FROM links 
                LIMIT ?
            ''', (Config.MAX_EXPORT_LINKS,))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            if not rows:
                await query.edit_message_text("❌ لا توجد روابط للتصدير")
                return
            
            # تحويل إلى JSON
            data = []
            for row in rows:
                item = dict(zip(columns, row))
                data.append(item)
            
            # حفظ في ملف JSON
            filename = f"links_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📋 ملف التصدير JSON\nعدد السجلات: {len(data):,}"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await query.edit_message_text(f"✅ تم تصدير {len(data):,} سجل")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير JSON: {e}")
            await query.edit_message_text(f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_all(self, query, user):
        """Handle export all links"""
        await self._handle_export_txt(query, user)
    
    async def _handle_export_telegram(self, query, user):
        """Handle export Telegram links"""
        await query.edit_message_text("⏳ جاري تحضير الملف...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links({'platform': 'telegram'}, Config.MAX_EXPORT_LINKS)
            
            if not links:
                await query.edit_message_text("❌ لا توجد روابط تيليجرام للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"telegram_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📢 روابط تيليجرام\nعدد الروابط: {len(links):,}"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await query.edit_message_text(f"✅ تم تصدير {len(links):,} رابط تيليجرام")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير تيليجرام: {e}")
            await query.edit_message_text(f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_whatsapp(self, query, user):
        """Handle export WhatsApp links"""
        await query.edit_message_text("⏳ جاري تحضير الملف...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links({'platform': 'whatsapp'}, Config.MAX_EXPORT_LINKS)
            
            if not links:
                await query.edit_message_text("❌ لا توجد روابط واتساب للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"whatsapp_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📱 روابط واتساب\nعدد الروابط: {len(links):,}"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await query.edit_message_text(f"✅ تم تصدير {len(links):,} رابط واتساب")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير واتساب: {e}")
            await query.edit_message_text(f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_discord(self, query, user):
        """Handle export Discord links"""
        await self._handle_export_txt(query, user)
    
    async def _handle_export_signal(self, query, user):
        """Handle export Signal links"""
        await self._handle_export_txt(query, user)
    
    async def _handle_export_test(self, query, user):
        """Handle export test links"""
        await self._handle_export_txt(query, user)
    
    async def _handle_show_stats(self, query):
        """Handle show stats"""
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        
        stats_text = (
            f"**📈 إحصائيات النظام**\n\n"
            f"**إحصائيات قاعدة البيانات:**\n"
            f"• 🔗 إجمالي الروابط: {db_stats.get('total_links', 0):,}\n"
            f"• ✅ الروابط الصالحة: {db_stats.get('valid_groups', 0):,}\n"
            f"• 📺 القنوات: {db_stats.get('subscriptions', 0):,}\n"
            f"• 💼 الجلسات النشطة: {db_stats.get('active_sessions', 0)}\n"
            f"• 👥 المستخدمين: {db_stats.get('total_users', 0)}\n"
        )
        
        # إحصائيات المنصات
        if 'links_by_platform' in db_stats:
            stats_text += "\n**توزيع المنصات:**\n"
            for platform, count in db_stats['links_by_platform'].items():
                stats_text += f"• {platform}: {count:,}\n"
        
        await query.edit_message_text(stats_text, parse_mode="Markdown")
    
    async def _handle_show_sessions(self, query):
        """Handle show sessions"""
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=10)
        
        if not sessions:
            await query.edit_message_text("❌ لا توجد جلسات نشطة")
            return
        
        sessions_text = f"**👥 الجلسات النشطة ({len(sessions)})**\n\n"
        
        for i, session in enumerate(sessions, 1):
            display_name = session.get('display_name', f"جلسة {session['id']}")
            username = session.get('username', 'بدون معرف')
            uses = session.get('total_uses', 0)
            links_collected = session.get('total_links', 0)
            
            sessions_text += (
                f"**{i}. {display_name}**\n"
                f"• المعرف: @{username}\n"
                f"• الاستخدامات: {uses}\n"
                f"• الروابط المجمعة: {links_collected:,}\n\n"
            )
        
        await query.edit_message_text(sessions_text, parse_mode="Markdown")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        user = update.effective_user
        text = update.message.text
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        # التحقق من حالة المستخدم
        user_state = self.user_states.get(user.id, {})
        
        if user_state.get('waiting_for_session'):
            await self._handle_session_input(update, text)
        else:
            # محاولة التعرف على الروابط في النص
            links = AdvancedLinkCollector._extract_links_from_text(text)
            
            if links:
                await update.message.reply_text(
                    f"🔍 **تم اكتشاف {len(links)} رابط في رسالتك!**\n\n"
                    "استخدم `/add_link [الرابط]` لإضافة رابط معين.\n"
                    "أو استخدم الأزرار للبدء في الجمع.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "مرحباً! يمكنك استخدام الأوامر التالية:\n"
                    "/start - بدء البوت\n"
                    "/help - المساعدة\n"
                    "/status - حالة النظام\n"
                    "/test_collect - اختبار الجمع\n"
                    "/collect - بدء الجمع الحقيقي\n"
                    "/add_link - إضافة رابط يدوي\n"
                    "أو استخدم الأزرار من رسالة الترحيب."
                )
    
    async def _handle_session_input(self, update: Update, session_string: str):
        """Handle session string input"""
        user = update.effective_user
        
        # حذف حالة المستخدم
        if user.id in self.user_states:
            del self.user_states[user.id]
        
        await update.message.reply_text("⏳ جاري التحقق من الجلسة...")
        
        # التحقق من الجلسة
        valid, result = await SessionManager.validate_session(session_string)
        
        if not valid:
            await update.message.reply_text(f"❌ جلسة غير صالحة: {result.get('error', 'خطأ غير معروف')}")
            return
        
        user_info = result.get('user_info', {})
        
        # تشفير الجلسة
        enc_manager = EncryptionManager.get_instance()
        encrypted_session = enc_manager.encrypt(session_string)
        
        # حفظ الجلسة في قاعدة البيانات
        session_data = {
            'session_string': encrypted_session,
            'phone_number': user_info.get('phone', ''),
            'user_id': user_info.get('id', 0),
            'username': user_info.get('username', ''),
            'display_name': f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip(),
            'added_by_user': user.id,
            'metadata': {
                'validated_at': datetime.now().isoformat(),
                'original_length': len(session_string),
                'purpose': 'link_collection'
            }
        }
        
        db = await EnhancedDatabaseManager.get_instance()
        success, message, details = await db.add_session(session_data)
        
        if success:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء الجمع الحقيقي", callback_data="start_collect"),
                 InlineKeyboardButton("🧪 اختبار الجمع", callback_data="test_collection")]
            ])
            
            await update.message.reply_text(
                f"✅ **تمت إضافة الجلسة بنجاح!**\n\n"
                f"**معلومات المستخدم:**\n"
                f"• الاسم: {session_data['display_name']}\n"
                f"• المعرف: @{session_data['username']}\n"
                f"• الهاتف: {session_data['phone_number']}\n\n"
                f"**الجلسة:**\n"
                f"• مشفرة ومخزنة بأمان\n"
                f"• جاهزة للجمع الحقيقي\n"
                f"• رقم الجلسة: {details.get('session_id')}\n\n"
                f"**الخطوات التالية:**\n"
                f"1. اختبر الجمع أولاً\n"
                f"2. ابدأ الجمع الحقيقي\n"
                f"3. قم بتصدير الروابط",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ فشل في إضافة الجلسة: {message}")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        try:
            error = context.error
            
            logger.error(f"خطأ غير معالج: {error}", exc_info=True)
            
            # معالجة خطأ Conflict (نسخة مزدوجة)
            if isinstance(error, Conflict):
                logger.error("⚠️ تم اكتشاف نسخة أخرى من البوت تعمل!")
                return
            
            if update and update.effective_chat:
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ حدث خطأ غير متوقع. حاول مرة أخرى.",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
                
        except Exception as e:
            logger.error(f"خطأ في معالج الأخطاء: {e}")

# ======================
# Health Check Server - خادم فحص الصحة
# ======================

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
                status = {
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat(),
                    "checks": {
                        "database": os.path.exists(Config.DB_PATH),
                        "memory": psutil.virtual_memory().percent < 90,
                        "bot": True
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
# Main Function - الوظيفة الرئيسية
# ======================

async def main():
    """Main function"""
    try:
        # التحقق من المتغيرات البيئية المطلوبة
        required_env_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH']
        missing = [var for var in required_env_vars if not os.getenv(var)]
        
        if missing:
            logger.error(f"❌ متغيرات بيئية مفقودة: {missing}")
            print(f"❌ خطأ: المتغيرات البيئية التالية مفقودة: {', '.join(missing)}")
            sys.exit(1)
        
        # التحقق من نسخة واحدة فقط
        instance_manager = await SingleInstanceManager.get_instance()
        if not await instance_manager.acquire_lock():
            logger.error("❌ تم اكتشاف نسخة أخرى من البوت تعمل بالفعل!")
            print("❌ خطأ: هناك نسخة أخرى من البوت تعمل. إغلاق...")
            sys.exit(1)
        
        # إنشاء المجلدات المطلوبة
        os.makedirs("backups", exist_ok=True)
        os.makedirs("exports", exist_ok=True)
        os.makedirs("cache_data", exist_ok=True)
        
        # بدء خادم فحص الصحة
        health_server = HealthCheckServer(port=8080)
        health_server.start()
        
        # تهيئة قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        
        # إنشاء البوت
        bot = TelegramBot()
        
        logger.info("🤖 بدء تشغيل بوت جمع الروابط المتقدم...")
        logger.info(f"🔥 الإصدار المحسن - جمع ذكي بالكلمات المفتاحية")
        logger.info(f"🔍 كلمات البحث: {Config.SEARCH_KEYWORDS}")
        logger.info(f"📊 الحد الأقصى للرسائل: {Config.MAX_MESSAGES_PER_SEARCH}")
        
        try:
            # تشغيل البوت
            await bot.app.initialize()
            await bot.app.start()
            await bot.app.updater.start_polling()
            
            logger.info("✅ البوت يعمل بنجاح!")
            logger.info("📋 الأوامر المتاحة: /start, /test_collect, /collect, /add_link, /export")
            
            # الحفاظ على البوت يعمل
            stop_event = asyncio.Event()
            await stop_event.wait()
            
        except KeyboardInterrupt:
            logger.info("👋 توقف البوت بواسطة المستخدم")
        except Exception as e:
            logger.error(f"❌ خطأ في البوت: {e}", exc_info=True)
            raise
            
        finally:
            logger.info("🧹 جاري التنظيف النهائي...")
            
            try:
                # إيقاف البوت
                if hasattr(bot, 'app'):
                    await bot.app.stop()
                
                # إغلاق قاعدة البيانات
                await db.close()
                
                # إيقاف خادم الصحة
                health_server.stop()
                
                # تحرير قفل النسخة الواحدة
                await instance_manager.release_lock()
                
                logger.info("✅ اكتمل الإغلاق السلس")
                
            except Exception as e:
                logger.error(f"❌ خطأ في التنظيف النهائي: {e}")
    
    except Exception as e:
        logger.error(f"❌ خطأ قاتل: {e}", exc_info=True)
        sys.exit(1)

# ======================
# Signal Handlers - معالجات الإشارات
# ======================

def setup_signal_handlers():
    """Setup signal handlers"""
    def signal_handler(signum, frame):
        logger.info(f"📶 تم استقبال إشارة {signum}. جاري الإغلاق السلس...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# ======================
# Entry Point - نقطة الدخول
# ======================

if __name__ == "__main__":
    # إعداد معالجات الإشارات
    setup_signal_handlers()
    
    # تشغيل البوت
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 توقف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ قاتل: {e}", exc_info=True)
        sys.exit(1)
