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
        'uvicorn[standard]==0.24.0',  # Changed to include standard
        'httpx==0.25.2',
        'pytz==2023.3'
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
from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.tl import functions, types
from telethon.errors import (
    FloodWaitError, ChannelPrivateError, UsernameNotOccupiedError,
    InviteHashInvalidError, InviteHashExpiredError, ChatAdminRequiredError,
    SessionPasswordNeededError, PhoneCodeInvalidError, AuthKeyError,
    UserNotParticipantError, ChatWriteForbiddenError,
    InviteHashEmptyError, ChannelInvalidError
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
    MAX_CONCURRENT_SESSIONS = 5
    MAX_JOIN_ATTEMPTS_PER_SESSION = 8
    MAX_MESSAGES_TO_SCAN = 150
    REQUEST_DELAYS = {
        'normal': 1.0,
        'join_request': 5.0,
        'search': 2.0,
        'flood_wait': 5.0,
        'between_sessions': 3.0,
        'between_tasks': 0.5,
        'min_cycle_delay': 15.0,
        'max_cycle_delay': 60.0,
        'validation_delay': 3.0,
        'after_join': 10.0
    }
    
    # Collection limits - حدود الجمع
    MAX_DIALOGS_PER_SESSION = 80
    MAX_MESSAGES_PER_SEARCH = 40
    MAX_SEARCH_TERMS = 12
    MAX_LINKS_PER_CYCLE = 300
    MAX_BATCH_SIZE = 40
    
    # Database - قاعدة البيانات
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10
    DB_POOL_SIZE = 5
    
    # WhatsApp collection - جمع واتساب
    WHATSAPP_DAYS_BACK = 30
    
    # Link verification - التحقق من الروابط
    MIN_GROUP_MEMBERS = 5
    MAX_LINK_LENGTH = 200
    VALIDATION_TIMEOUT = 30
    
    # Rate limiting - الحد من الطلبات
    USER_RATE_LIMIT = {
        'max_requests': 15,
        'per_seconds': 60
    }
    
    # Session management - إدارة الجلسات
    SESSION_TIMEOUT = 600
    MAX_SESSIONS_PER_USER = 15
    
    # Export - التصدير
    MAX_EXPORT_LINKS = 50000
    EXPORT_CHUNK_SIZE = 3000
    
    # Advanced settings - إعدادات متقدمة
    TELEGRAM_NO_TIME_LIMIT = True
    JOIN_REQUEST_CHECK_DELAY = 30
    ENABLE_ADVANCED_VALIDATION = True
    
    # GROUP SPECIFIC SETTINGS - إعدادات خاصة بالمجموعات فقط
    COLLECT_ONLY_GROUPS = True  # جمع المجموعات فقط (NO CHANNELS)
    SKIP_CHANNELS = True  # تخطي القنوات تماماً
    REQUIRE_JOIN_BUTTON = True  # يجب أن تحتوي على زر انضمام/طلب انضمام
    MIN_GROUP_PARTICIPANTS = 10  # الحد الأدنى للأعضاء في المجموعة
    JOIN_PUBLIC_GROUPS = True  # الانضمام للمجموعات العامة
    JOIN_PRIVATE_GROUPS = True  # الانضمام للمجموعات الخاصة (روابط دعوة)
    CHECK_IF_GROUP_ACTIVE = True  # التحقق من نشاط المجموعة
    GROUP_ACTIVITY_DAYS = 7  # المجموعة تعتبر نشطة إذا كان آخر نشاط خلال X يوم

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
                
                # إذا كان جمع المجموعات فقط، نتأكد أنها مجموعة وليست قناة
                if Config.COLLECT_ONLY_GROUPS and result['details'].get('is_channel'):
                    result['is_valid'] = False
                    result['details']['is_group'] = False
                    return result
                
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
            'is_megagroup': False,
            'path_segments': [],
            'is_active': True,
            'requires_join_button': False
        }
        
        path = parsed.path.strip('/')
        if not path:
            return result
        
        segments = path.split('/')
        result['path_segments'] = segments
        
        # كشف روابط الانضمام (joinchat) - هذه مجاميع بالتأكيد
        join_patterns = [
            r'\+(?:joinchat/)?([A-Za-z0-9_-]+)',
            r'joinchat/([A-Za-z0-9_-]+)',
            r'join/([A-Za-z0-9_-]+)',
            r'invite/([A-Za-z0-9_-]+)'
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
            result['requires_join_button'] = True
            
            # إذا كان رابط دعوة، فهو مجموعة بالتأكيد وليس قناة
            result['is_channel'] = False
            result['is_megagroup'] = True
            return result
        
        # كشف القنوات - نتخطاها إذا كان الإعداد COLLECT_ONLY_GROUPS = True
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
                result['is_valid'] = False if Config.COLLECT_ONLY_GROUPS else True
                result['username'] = channel_name
                result['is_group'] = False
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
                result['requires_join_button'] = True
                result['is_megagroup'] = True
            else:
                # اسم مستخدم عادي - يمكن أن يكون مجموعة أو قناة
                # نعتبرها مجموعة مؤقتاً حتى يتم التحقق
                result['is_group'] = True
                result['is_public'] = True
                result['is_valid'] = True
                result['is_supergroup'] = True
                result['is_megagroup'] = True
        
        # كشف المجموعات مع مسار أطول
        elif len(segments) >= 2:
            if segments[0].lower() in ['c', 'channel', 's']:
                # هذه قنوات - نتخطاها
                result['is_channel'] = True
                result['is_broadcast'] = True
                result['is_valid'] = False if Config.COLLECT_ONLY_GROUPS else True
                result['username'] = segments[1] if len(segments) > 1 else ''
                result['is_group'] = False
            elif segments[0].lower() == 'joinchat':
                # روابط انضمام - هذه مجاميع
                result['is_join_request'] = True
                result['is_private'] = True
                result['invite_hash'] = segments[1] if len(segments) > 1 else ''
                result['is_group'] = True
                result['is_valid'] = True
                result['requires_join_button'] = True
                result['is_megagroup'] = True
            else:
                # نعتبرها مجموعة مؤقتاً
                result['is_group'] = True
                result['is_public'] = True
                result['is_supergroup'] = True
                result['is_valid'] = True
                result['is_megagroup'] = True
        
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
                total_groups_joined INTEGER DEFAULT 0,
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
                participants_count INTEGER DEFAULT 0,
                online_count INTEGER DEFAULT 0,
                session_id INTEGER,
                collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                check_count INTEGER DEFAULT 0,
                confidence TEXT DEFAULT 'medium',
                is_active BOOLEAN DEFAULT 1,
                requires_join BOOLEAN DEFAULT 0,
                requires_approval BOOLEAN DEFAULT 0,
                is_verified BOOLEAN DEFAULT 0,
                validation_score INTEGER DEFAULT 0,
                metadata TEXT,
                tags TEXT,
                added_by_user INTEGER,
                source TEXT,
                is_channel BOOLEAN DEFAULT 0,
                is_group BOOLEAN DEFAULT 0,
                is_megagroup BOOLEAN DEFAULT 0,
                is_join_request BOOLEAN DEFAULT 0,
                is_supergroup BOOLEAN DEFAULT 0,
                has_join_button BOOLEAN DEFAULT 0,
                joined_successfully BOOLEAN DEFAULT 0,
                join_date TIMESTAMP,
                last_message_date TIMESTAMP,
                link_quality INTEGER DEFAULT 50,
                is_public_group BOOLEAN DEFAULT 0,
                is_private_group BOOLEAN DEFAULT 0,
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
            'CREATE INDEX IF NOT EXISTS idx_links_is_megagroup ON links(is_megagroup)',
            'CREATE INDEX IF NOT EXISTS idx_links_has_join_button ON links(has_join_button)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_active ON links(is_active)',
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
                # تحديث المعلومات إذا كانت موجودة
                await self.update_link_info(existing[0], link_info)
                return False, "الرابط موجود مسبقاً (تم تحديثه)", {'link_id': existing[0]}
            
            # إعداد بيانات الرابط
            cursor = await self.conn.execute('''
                INSERT INTO links 
                (url_hash, url, original_url, platform, link_type, telegram_type, title, 
                 description, members_count, participants_count, online_count, session_id, confidence, 
                 is_active, requires_join, requires_approval, is_verified, validation_score, metadata, 
                 tags, added_by_user, source, is_channel, is_group, is_megagroup, is_join_request, 
                 is_supergroup, has_join_button, joined_successfully, join_date, last_message_date, 
                 link_quality, is_public_group, is_private_group)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                url_info['url_hash'],
                url_info['normalized_url'],
                url_info['original_url'],
                url_info['platform'],
                link_info.get('link_type', 'unknown'),
                details.get('telegram_type', ''),
                link_info.get('title', '')[:500],
                link_info.get('description', '')[:1000],
                link_info.get('members_count', 0),
                link_info.get('participants_count', 0),
                link_info.get('online_count', 0),
                link_info.get('session_id'),
                link_info.get('confidence', 'medium'),
                link_info.get('is_active', True),
                details.get('is_join_request', False),
                link_info.get('requires_approval', False),
                link_info.get('is_verified', False),
                link_info.get('validation_score', 0),
                json.dumps(link_info.get('metadata', {})),
                json.dumps(link_info.get('tags', [])),
                link_info.get('added_by_user', 0),
                link_info.get('source', 'manual'),
                details.get('is_channel', False),
                details.get('is_group', True),
                details.get('is_megagroup', False),
                details.get('is_join_request', False),
                details.get('is_supergroup', False),
                details.get('requires_join_button', False),
                link_info.get('joined_successfully', False),
                link_info.get('join_date'),
                link_info.get('last_message_date'),
                link_info.get('link_quality', 50),
                details.get('is_public', False),
                details.get('is_private', False)
            ))
            
            link_id = cursor.lastrowid
            
            # تحديث إحصائيات الجلسة إذا كان هناك session_id
            if link_info.get('session_id'):
                await self.conn.execute(
                    "UPDATE sessions SET total_links = total_links + 1 WHERE id = ?",
                    (link_info['session_id'],)
                )
            
            # تحديث إحصائيات المستخدم
            if link_info.get('added_by_user'):
                await self.update_user_stats(link_info['added_by_user'], 'link_added')
            
            await self.conn.commit()
            
            return True, "تمت إضافة الرابط بنجاح", {
                'link_id': link_id,
                'url_hash': url_info['url_hash']
            }
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الرابط: {e}")
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def update_link_info(self, link_id: int, link_info: Dict):
        """Update existing link information"""
        try:
            updates = []
            params = []
            
            if 'title' in link_info:
                updates.append("title = ?")
                params.append(link_info['title'][:500])
            
            if 'description' in link_info:
                updates.append("description = ?")
                params.append(link_info['description'][:1000])
            
            if 'members_count' in link_info:
                updates.append("members_count = ?")
                params.append(link_info['members_count'])
            
            if 'participants_count' in link_info:
                updates.append("participants_count = ?")
                params.append(link_info['participants_count'])
            
            if 'online_count' in link_info:
                updates.append("online_count = ?")
                params.append(link_info['online_count'])
            
            if 'is_active' in link_info:
                updates.append("is_active = ?")
                params.append(link_info['is_active'])
            
            if 'is_verified' in link_info:
                updates.append("is_verified = ?")
                params.append(link_info['is_verified'])
            
            if 'validation_score' in link_info:
                updates.append("validation_score = ?")
                params.append(link_info['validation_score'])
            
            if 'joined_successfully' in link_info:
                updates.append("joined_successfully = ?")
                params.append(link_info['joined_successfully'])
            
            if 'join_date' in link_info:
                updates.append("join_date = ?")
                params.append(link_info['join_date'])
            
            if 'last_message_date' in link_info:
                updates.append("last_message_date = ?")
                params.append(link_info['last_message_date'])
            
            if 'link_quality' in link_info:
                updates.append("link_quality = ?")
                params.append(link_info['link_quality'])
            
            if 'has_join_button' in link_info:
                updates.append("has_join_button = ?")
                params.append(link_info['has_join_button'])
            
            if updates:
                updates.append("last_checked = CURRENT_TIMESTAMP, check_count = check_count + 1")
                query = f"UPDATE links SET {', '.join(updates)} WHERE id = ?"
                params.append(link_id)
                
                await self.conn.execute(query, params)
                await self.conn.commit()
                
        except Exception as e:
            logger.error(f"خطأ في تحديث معلومات الرابط: {e}")
    
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
                ORDER BY last_used ASC, health_score DESC
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
    
    async def get_links_count(self, filters: Dict = None) -> int:
        """Get total links count with optional filters"""
        try:
            query = 'SELECT COUNT(*) FROM links WHERE 1=1'
            params = []
            
            if filters:
                if filters.get('platform'):
                    query += " AND platform = ?"
                    params.append(filters['platform'])
                
                if filters.get('is_group') is not None:
                    query += " AND is_group = ?"
                    params.append(filters['is_group'])
                
                if filters.get('is_megagroup') is not None:
                    query += " AND is_megagroup = ?"
                    params.append(filters['is_megagroup'])
                
                if filters.get('has_join_button') is not None:
                    query += " AND has_join_button = ?"
                    params.append(filters['has_join_button'])
                
                if filters.get('is_active') is not None:
                    query += " AND is_active = ?"
                    params.append(filters['is_active'])
                
                if filters.get('is_verified') is not None:
                    query += " AND is_verified = ?"
                    params.append(filters['is_verified'])
            
            cursor = await self.conn.execute(query, params)
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
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT platform, COUNT(*) FROM links GROUP BY platform")
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_verified = 1")
            stats['verified_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_group = 1")
            stats['group_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_megagroup = 1")
            stats['megagroup_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_channel = 1")
            stats['channel_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE has_join_button = 1")
            stats['join_button_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE joined_successfully = 1")
            stats['joined_groups'] = (await cursor.fetchone())[0]
            
            return stats
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على ملخص الإحصائيات: {e}")
            return {}
    
    async def export_links(self, filters: Dict = None, limit: int = 1000) -> List[str]:
        """Export links"""
        try:
            query = 'SELECT url FROM links WHERE is_active = 1'
            params = []
            
            if filters:
                where_clauses = []
                
                if filters.get('platform'):
                    where_clauses.append("platform = ?")
                    params.append(filters['platform'])
                
                if filters.get('is_group') is not None:
                    where_clauses.append("is_group = ?")
                    params.append(filters['is_group'])
                
                if filters.get('is_megagroup') is not None:
                    where_clauses.append("is_megagroup = ?")
                    params.append(filters['is_megagroup'])
                
                if filters.get('has_join_button') is not None:
                    where_clauses.append("has_join_button = ?")
                    params.append(filters['has_join_button'])
                
                if filters.get('min_members'):
                    where_clauses.append("members_count >= ?")
                    params.append(filters['min_members'])
                
                if filters.get('is_verified') is not None:
                    where_clauses.append("is_verified = ?")
                    params.append(filters['is_verified'])
                
                if where_clauses:
                    query += " AND " + " AND ".join(where_clauses)
            
            query += " ORDER BY collected_date DESC LIMIT ?"
            params.append(limit)
            
            cursor = await self.conn.execute(query, params)
            rows = await cursor.fetchall()
            
            return [row[0] for row in rows]
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الروابط: {e}")
            return []
    
    async def update_session_stats(self, session_id: int, links_collected: int = 0, groups_joined: int = 0):
        """Update session statistics"""
        try:
            query = '''
                UPDATE sessions 
                SET last_used = CURRENT_TIMESTAMP,
                    total_links = total_links + ?,
                    total_groups_joined = total_groups_joined + ?,
                    last_success = CURRENT_TIMESTAMP
                WHERE id = ?
            '''
            
            await self.conn.execute(query, (links_collected, groups_joined, session_id))
            await self.conn.commit()
            
        except Exception as e:
            logger.error(f"خطأ في تحديث إحصائيات الجلسة: {e}")
    
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
    
    @staticmethod
    async def join_group(client: TelegramClient, link_info: Dict) -> Tuple[bool, Dict]:
        """Join Telegram group/channel"""
        try:
            details = link_info.get('details', {})
            url = link_info.get('normalized_url', '')
            
            if not url:
                return False, {'error': 'لا يوجد رابط'}
            
            result = {
                'joined': False,
                'is_member': False,
                'requires_approval': False,
                'error': None,
                'group_info': {}
            }
            
            # التحقق إذا كانت الجلسة عضو بالفعل
            try:
                entity = await client.get_entity(url)
                result['is_member'] = True
                result['group_info'] = {
                    'id': entity.id,
                    'title': getattr(entity, 'title', ''),
                    'username': getattr(entity, 'username', '')
                }
                return True, result
            except (ValueError, ChannelPrivateError):
                pass
            
            # محاولة الانضمام للمجموعة
            try:
                if details.get('is_join_request'):
                    # رابط دعوة خاص - هذا مجموعة بالتأكيد
                    invite_hash = details.get('invite_hash', '')
                    if invite_hash:
                        await client(functions.messages.ImportChatInviteRequest(invite_hash))
                        result['joined'] = True
                        result['requires_approval'] = False
                        logger.info(f"✅ انضممت لمجموعة دعوة: {url}")
                else:
                    # رابط عام - نحتاج للتحقق إذا كانت مجموعة أو قناة
                    entity = await client.get_entity(url)
                    
                    # التحقق إذا كانت مجموعة وليست قناة
                    if hasattr(entity, 'megagroup') and entity.megagroup:
                        # هذه مجموعة
                        await client(functions.channels.JoinChannelRequest(entity))
                        result['joined'] = True
                        result['requires_approval'] = False
                        logger.info(f"✅ انضممت لمجموعة عامة: {getattr(entity, 'title', 'unknown')}")
                    elif hasattr(entity, 'broadcast') and entity.broadcast:
                        # هذه قناة - نتخطاها
                        result['error'] = 'هذه قناة وليست مجموعة'
                        return False, result
                    else:
                        # تحتاج إلى موافقة أو غير معروفة
                        result['requires_approval'] = True
                
                if result['joined']:
                    # الحصول على معلومات المجموعة بعد الانضمام
                    try:
                        entity = await client.get_entity(url)
                        result['group_info'] = {
                            'id': entity.id,
                            'title': getattr(entity, 'title', ''),
                            'username': getattr(entity, 'username', ''),
                            'participants_count': getattr(entity, 'participants_count', 0),
                            'online_count': getattr(entity, 'online_count', 0),
                            'megagroup': getattr(entity, 'megagroup', False)
                        }
                    except:
                        pass
                
                return True, result
                
            except (InviteHashInvalidError, InviteHashExpiredError, InviteHashEmptyError):
                result['error'] = 'رابط الدعوة غير صالح أو منتهي'
                return False, result
            except UserNotParticipantError:
                result['error'] = 'المستخدم غير مشارك'
                return False, result
            except ChannelPrivateError:
                result['error'] = 'المجموعة خاصة'
                return False, result
            except FloodWaitError as e:
                result['error'] = f'انتظر {e.seconds} ثانية'
                await asyncio.sleep(e.seconds)
                return False, result
            except Exception as e:
                result['error'] = str(e)
                return False, result
            
        except Exception as e:
            logger.error(f"خطأ في الانضمام للمجموعة: {e}")
            return False, {'error': str(e)}
    
    @staticmethod
    async def collect_links_from_group(client: TelegramClient, entity, limit: int = 200) -> List[str]:
        """Collect links from group messages"""
        links = []
        try:
            async for message in client.iter_messages(entity, limit=limit):
                if message.text:
                    # استخراج الروابط من النص
                    text_links = EnhancedLinkProcessor._extract_links_from_text(message.text)
                    links.extend(text_links)
                
                # جمع الروابط من الوسائط
                if message.media:
                    # يمكن إضافة استخراج الروابط من الكابشن
                    if message.message:
                        text_links = EnhancedLinkProcessor._extract_links_from_text(message.message)
                        links.extend(text_links)
                
                if len(links) >= 50:  # حد مؤقت
                    break
                    
        except Exception as e:
            logger.error(f"خطأ في جمع الروابط من المجموعة: {e}")
        
        # إزالة التكرارات
        unique_links = list(set(links))
        return unique_links
    
    @staticmethod
    def _extract_links_from_text(text: str) -> List[str]:
        """Extract links from text"""
        if not text:
            return []
        
        patterns = [
            r'(https?://[^\s<>"\']+)',
            r'(t\.me/[^\s<>"\']+)',
            r'(telegram\.me/[^\s<>"\']+)',
            r'(chat\.whatsapp\.com/[^\s<>"\']+)',
            r'(discord\.gg/[^\s<>"\']+)',
            r'(signal\.group/[^\s<>"\']+)',
            r'(@[A-Za-z0-9_]{5,})'  # إضافة أسماء المستخدمين
        ]
        
        links = []
        for pattern in patterns:
            found = re.findall(pattern, text, re.IGNORECASE)
            links.extend(found)
        
        return links

# ======================
# Group Collection Manager - مدير جمع المجموعات فقط
# ======================

class GroupCollectionManager:
    """Manage group-only link collection"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        self.stats = {
            'total_collected': 0,
            'telegram_groups': 0,
            'whatsapp_groups': 0,
            'discord_groups': 0,
            'signal_groups': 0,
            'errors': 0,
            'groups_joined': 0,
            'groups_skipped': 0,
            'links_from_groups': 0
        }
        self.collection_task = None
        self.current_cycle = 0
    
    async def start_collection(self):
        """Start collection process"""
        if self.active:
            return
        
        self.active = True
        self.paused = False
        self.stop_requested = False
        
        logger.info("🚀 بدء عملية جمع المجموعات فقط (بدون قنوات)")
        logger.info(f"⚙️ الإعدادات: COLLECT_ONLY_GROUPS={Config.COLLECT_ONLY_GROUPS}, SKIP_CHANNELS={Config.SKIP_CHANNELS}")
        
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
                
                # تأخير عشوائي بين الدورات
                delay = Config.REQUEST_DELAYS['min_cycle_delay'] + \
                       (Config.REQUEST_DELAYS['max_cycle_delay'] - Config.REQUEST_DELAYS['min_cycle_delay']) * \
                       (self.current_cycle % 10) / 10
                
                await asyncio.sleep(delay)
                self.current_cycle += 1
                
            except Exception as e:
                logger.error(f"خطأ في دورة الجمع: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(10)
        
        self.active = False
        logger.info("⏹️ توقفت عملية جمع المجموعات")
    
    async def _collection_cycle(self):
        """Single collection cycle"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=Config.MAX_CONCURRENT_SESSIONS)
            
            if not sessions:
                logger.warning("لا توجد جلسات نشطة")
                return
            
            tasks = []
            for session in sessions:
                task = self._process_session_for_groups_only(session)
                tasks.append(task)
                await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful = sum(1 for r in results if isinstance(r, dict) and r.get('status') == 'success')
            logger.info(f"اكتملت دورة جمع المجموعات #{self.current_cycle}: {successful}/{len(tasks)} جلسات ناجحة")
            
        except Exception as e:
            logger.error(f"خطأ في دورة الجمع: {e}")
            self.stats['errors'] += 1
    
    async def _process_session_for_groups_only(self, session: Dict):
        """Process single session for groups only"""
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
            
            collected_stats = {
                'links_collected': 0,
                'groups_joined': 0,
                'groups_skipped': 0,
                'links_from_groups': 0
            }
            
            # البحث عن مجموعات للانضمام وجمع الروابط
            group_results = await self._find_and_join_groups_only(client, session_id)
            
            collected_stats['links_collected'] += group_results['links_collected']
            collected_stats['groups_joined'] += group_results['groups_joined']
            collected_stats['groups_skipped'] += group_results['groups_skipped']
            collected_stats['links_from_groups'] += group_results['links_from_groups']
            
            await client.disconnect()
            
            # تحديث إحصائيات الجلسة
            db = await EnhancedDatabaseManager.get_instance()
            await db.update_session_stats(
                session_id, 
                collected_stats['links_collected'],
                collected_stats['groups_joined']
            )
            
            # تحديث الإحصائيات العامة
            self.stats['total_collected'] += collected_stats['links_collected']
            self.stats['groups_joined'] += collected_stats['groups_joined']
            self.stats['groups_skipped'] += collected_stats['groups_skipped']
            self.stats['links_from_groups'] += collected_stats['links_from_groups']
            
            return {
                'status': 'success',
                'collected': collected_stats['links_collected'],
                'groups_joined': collected_stats['groups_joined'],
                'groups_skipped': collected_stats['groups_skipped'],
                'links_from_groups': collected_stats['links_from_groups']
            }
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الجلسة: {e}")
            self.stats['errors'] += 1
            return {'status': 'error', 'reason': str(e)[:200]}
    
    async def _find_and_join_groups_only(self, client: TelegramClient, session_id: int) -> Dict:
        """Find and join groups only (no channels)"""
        stats = {
            'groups_joined': 0,
            'groups_skipped': 0,
            'links_collected': 0,
            'links_from_groups': 0
        }
        
        try:
            # البحث عن مجموعات للانضمام
            search_terms = [
                "مجموعة", "جروب", "تليجرام", "قروب", "دردشة",
                "group", "telegram", "chat", "community",
                "تعارف", "محادثة", "نقاش", "تواصل"
            ]
            
            joined_groups = 0
            
            for term in search_terms[:Config.MAX_SEARCH_TERMS]:
                if not self.active or self.stop_requested or self.paused:
                    break
                
                if joined_groups >= Config.MAX_JOIN_ATTEMPTS_PER_SESSION:
                    break
                
                try:
                    # البحث عن مجموعات
                    search_results = await client(functions.contacts.SearchRequest(
                        q=term,
                        limit=20
                    ))
                    
                    for chat in search_results.chats:
                        if not self.active or self.stop_requested or self.paused:
                            break
                        
                        if joined_groups >= Config.MAX_JOIN_ATTEMPTS_PER_SESSION:
                            break
                        
                        try:
                            # التحقق إذا كانت مجموعة ميجا (مجموعة وليست قناة)
                            if hasattr(chat, 'megagroup') and chat.megagroup:
                                # هذه مجموعة - نحاول الانضمام
                                try:
                                    # التحقق من عدد المشاركين
                                    participants_count = getattr(chat, 'participants_count', 0)
                                    if participants_count < Config.MIN_GROUP_PARTICIPANTS:
                                        logger.info(f"⏭️ تخطيت مجموعة {getattr(chat, 'title', 'unknown')} - عدد الأعضاء قليل: {participants_count}")
                                        stats['groups_skipped'] += 1
                                        continue
                                    
                                    await client(functions.channels.JoinChannelRequest(chat))
                                    logger.info(f"✅ انضممت للمجموعة: {getattr(chat, 'title', 'unknown')} - أعضاء: {participants_count}")
                                    
                                    # جمع الروابط من المجموعة
                                    group_links = await SessionManager.collect_links_from_group(client, chat, Config.MAX_MESSAGES_TO_SCAN)
                                    
                                    for link in group_links:
                                        link_info = await self._process_group_link(link, session_id, chat)
                                        if link_info:
                                            stats['links_collected'] += 1
                                            stats['links_from_groups'] += 1
                                    
                                    stats['groups_joined'] += 1
                                    joined_groups += 1
                                    
                                    await asyncio.sleep(Config.REQUEST_DELAYS['after_join'])
                                    
                                except Exception as join_error:
                                    logger.debug(f"فشل الانضمام للمجموعة: {join_error}")
                                    stats['groups_skipped'] += 1
                                    continue
                            else:
                                # ليست مجموعة ميجا - قد تكون قناة
                                stats['groups_skipped'] += 1
                                continue
                            
                        except Exception as e:
                            logger.debug(f"خطأ في معالجة الدردشة: {e}")
                            stats['groups_skipped'] += 1
                            continue
                    
                    await asyncio.sleep(Config.REQUEST_DELAYS['search'])
                    
                except Exception as e:
                    logger.error(f"خطأ في البحث عن مجموعات: {e}")
                    continue
            
            # البحث عن مجموعات من خلال الروابط في المحادثات
            await self._collect_from_existing_groups(client, session_id, stats)
            
        except Exception as e:
            logger.error(f"خطأ في عملية جمع المجموعات: {e}")
        
        return stats
    
    async def _collect_from_existing_groups(self, client: TelegramClient, session_id: int, stats: Dict):
        """Collect from existing groups in dialogs"""
        try:
            dialogs = await client.get_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION)
            
            for dialog in dialogs:
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # التحقق إذا كانت مجموعة وليست قناة
                    if hasattr(entity, 'megagroup') and entity.megagroup:
                        # هذه مجموعة - نجمع الروابط منها
                        group_links = await SessionManager.collect_links_from_group(
                            client, entity, Config.MAX_MESSAGES_PER_SEARCH
                        )
                        
                        for link in group_links:
                            link_info = await self._process_group_link(link, session_id, entity)
                            if link_info:
                                stats['links_collected'] += 1
                                stats['links_from_groups'] += 1
                        
                        await asyncio.sleep(Config.REQUEST_DELAYS['normal'])
                    
                except Exception as e:
                    logger.debug(f"خطأ في جمع من مجموعة: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"خطأ في جمع الروابط من المجموعات الموجودة: {e}")
    
    async def _process_group_link(self, url: str, session_id: int, source_entity=None) -> Optional[Dict]:
        """Process and save a group link"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return None
            
            # تخطي القنوات تماماً
            if url_info['details'].get('is_channel') and Config.SKIP_CHANNELS:
                return None
            
            # التأكد أنها مجموعة وليست قناة
            if not url_info['details'].get('is_group'):
                return None
            
            # إعطاء أولوية لروابط الانضمام (دعوات)
            has_join_button = url_info['details'].get('is_join_request', False) or \
                             url_info['details'].get('requires_join_button', False)
            
            platform = url_info['platform']
            
            link_info = {
                'url': url,
                'url_hash': url_info['url_hash'],
                'platform': platform,
                'link_type': 'group',
                'telegram_type': url_info['details'].get('telegram_type', ''),
                'session_id': session_id,
                'confidence': 'high' if has_join_button else 'medium',
                'is_active': True,
                'requires_join': url_info['details'].get('is_join_request', False),
                'requires_approval': not url_info['details'].get('is_public', False),
                'is_verified': False,
                'validation_score': 80 if has_join_button else 50,
                'is_group': True,
                'is_megagroup': url_info['details'].get('is_megagroup', False),
                'is_channel': False,  # دائماً false لأننا نتخطى القنوات
                'is_join_request': url_info['details'].get('is_join_request', False),
                'is_supergroup': url_info['details'].get('is_supergroup', False),
                'has_join_button': has_join_button,
                'joined_successfully': False,
                'is_public_group': url_info['details'].get('is_public', False),
                'is_private_group': url_info['details'].get('is_private', False),
                'metadata': {
                    'collected_at': datetime.now().isoformat(),
                    'platform_details': url_info['details'],
                    'source': 'group_collection',
                    'source_group_title': getattr(source_entity, 'title', '') if source_entity else ''
                },
                'source': 'group_collection'
            }
            
            db = await EnhancedDatabaseManager.get_instance()
            success, message, details = await db.add_link(link_info)
            
            if success:
                # تحديث الإحصائيات
                self.stats['total_collected'] += 1
                if platform == 'telegram':
                    self.stats['telegram_groups'] += 1
                elif platform == 'whatsapp':
                    self.stats['whatsapp_groups'] += 1
                elif platform == 'discord':
                    self.stats['discord_groups'] += 1
                elif platform == 'signal':
                    self.stats['signal_groups'] += 1
                
                return link_info
            
            return None
            
        except Exception as e:
            logger.error(f"خطأ في معالجة رابط المجموعة {url}: {e}")
            return None
    
    def get_status(self) -> Dict:
        """Get collection status"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'stats': self.stats.copy(),
            'current_cycle': self.current_cycle
        }
    
    async def pause(self):
        """Pause collection"""
        self.paused = True
        logger.info("⏸️ تم إيقاف جمع المجموعات مؤقتاً")
    
    async def resume(self):
        """Resume collection"""
        self.paused = False
        logger.info("▶️ تم استئناف جمع المجموعات")
    
    async def stop(self):
        """Stop collection"""
        self.stop_requested = True
        logger.info("⏹️ تم طلب إيقاف جمع المجموعات")
        
        # انتظار حتى تتوقف المهمة
        if self.collection_task:
            try:
                await asyncio.wait_for(self.collection_task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("مهلة انتظار إيقاف مهمة الجمع")
        
        self.active = False

# ======================
# Encryption Manager
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
# Backup Manager
# ======================

class BackupManager:
    """Backup manager"""
    
    @staticmethod
    async def create_backup() -> Optional[Dict]:
        """Create database backup"""
        if not Config.BACKUP_ENABLED:
            return None
        
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = "backups"
            backup_filename = f"backup_{timestamp}.db"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            os.makedirs(backup_dir, exist_ok=True)
            
            if not os.path.exists(Config.DB_PATH):
                return None
            
            shutil.copy2(Config.DB_PATH, backup_path)
            
            metadata = {
                'backup_id': hashlib.md5(timestamp.encode()).hexdigest(),
                'timestamp': timestamp,
                'created_at': datetime.now().isoformat(),
                'file_path': backup_path,
                'size_bytes': os.path.getsize(backup_path)
            }
            
            logger.info(f"تم إنشاء نسخة احتياطية: {backup_path}")
            
            return metadata
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء نسخة احتياطية: {e}")
            return None
    
    @staticmethod
    async def rotate_backups():
        """Rotate old backups"""
        try:
            if not os.path.exists("backups"):
                return
            
            backups = []
            for filename in os.listdir("backups"):
                if filename.startswith("backup_") and filename.endswith(".db"):
                    path = os.path.join("backups", filename)
                    ctime = os.path.getctime(path)
                    backups.append({'path': path, 'created': ctime})
            
            backups.sort(key=lambda x: x['created'])
            
            if len(backups) > Config.MAX_BACKUPS:
                to_delete = backups[:-Config.MAX_BACKUPS]
                for backup in to_delete:
                    try:
                        os.remove(backup['path'])
                        logger.info(f"تم حذف النسخة القديمة: {backup['path']}")
                    except Exception as e:
                        logger.error(f"خطأ في حذف النسخة القديمة: {e}")
            
        except Exception as e:
            logger.error(f"خطأ في تدوير النسخ الاحتياطية: {e}")

# ======================
# Telegram Bot - مخصص لجمع المجموعات فقط
# ======================

class TelegramBot:
    """Main Telegram bot - Groups Only Edition"""
    
    def __init__(self):
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        self.collection_manager = GroupCollectionManager()  # استخدم مدير المجموعات فقط
        
        self._setup_handlers()
        
        self.user_states = {}
    
    def _setup_handlers(self):
        """Setup bot handlers"""
        # Basic commands
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("backup", self.backup_command))
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        self.app.add_handler(CommandHandler("addsession", self.add_session_command))
        
        # Fixed: Added sessions_command handler
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        
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
            [InlineKeyboardButton("🚀 بدء جمع المجموعات", callback_data="start_collect"),
             InlineKeyboardButton("⏸️ إدارة الجمع", callback_data="manage_collect")],
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("👥 الجلسات", callback_data="show_sessions")],
            [InlineKeyboardButton("📤 تصدير المجموعات", callback_data="export_groups"),
             InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")],
            [InlineKeyboardButton("❓ المساعدة", callback_data="show_help"),
             InlineKeyboardButton("⚙️ الإعدادات", callback_data="show_settings")]
        ])
        
        welcome_text = f"""
🤖 **مرحباً {user.first_name}!**

**بوت جمع روابط المجموعات المتقدم**

🎯 **التركيز على المجموعات فقط:**
• 📢 مجاميع تيليجرام فقط (بدون قنوات)
• ⏭️ تخطي القنوات التي تحتوي على زر "اشتراك"
• ✅ جمع المجموعات التي تحتوي على زر "انضمام"
• 👥 مجموعات تحتوي على أعضاء فعليين

**المميزات:**
• جمع روابط تيليجرام وواتساب وديسكورد
• تخطي القنوات وجمع المجموعات فقط
• تصدير المجموعات بتنسيقات مختلفة
• نسخ احتياطي تلقائي
• واجهة سهلة الاستخدام

**🚀 اختر من الأزرار أدناه لبدء الاستخدام!**
"""
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
**📖 دليل استخدام بوت جمع المجموعات**

🎯 **التركيز على المجموعات فقط:**
• البوت يجمع **المجموعات** فقط وليس القنوات
• يتخطى القنوات التي تحتوي على زر "اشتراك"
• يجمع المجموعات التي تحتوي على زر "انضمام" أو "طلب انضمام"

**الأوامر الأساسية:**
• /start - بدء البوت ورسالة الترحيب
• /help - عرض هذه المساعدة
• /status - عرض حالة النظام والجمع
• /sessions - عرض الجلسات النشطة
• /stats - إحصائيات النظام

**إدارة الجلسات:**
• /addsession - إضافة جلسة جديدة
• /sessions - عرض الجلسات النشطة

**الجمع والتصدير:**
• /collect - بدء/إيقاف جمع المجموعات
• /export - تصدير المجموعات المجمعة

**الإدارة:**
• /backup - إنشاء نسخة احتياطية

**📌 كيفية البدء:**
1. أضف جلسة تيليجرام باستخدام /addsession
2. ابدأ الجمع باستخدام /collect
3. قم بتصدير المجموعات باستخدام /export

**🔒 ملاحظات:**
• الجلسات مشفرة وتخزن بأمان
• المجموعات فقط وليس القنوات
• النسخ الاحتياطية تلقائية
"""
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        status = self.collection_manager.get_status()
        
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        
        status_text = f"""
**📊 حالة النظام - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**

**🎯 التركيز: المجموعات فقط (بدون قنوات)**
**⚙️ الإعدادات:**
• جمع المجموعات فقط: {"✅ مفعل" if Config.COLLECT_ONLY_GROUPS else "❌ معطل"}
• تخطي القنوات: {"✅ مفعل" if Config.SKIP_CHANNELS else "❌ معطل"}
• الحد الأدنى للأعضاء: {Config.MIN_GROUP_PARTICIPANTS}

**حالة الجمع:**
"""
        
        if status['active']:
            if status['paused']:
                status_text += "⏸️ **موقف مؤقتاً**\n"
            elif status['stop_requested']:
                status_text += "🛑 **جاري الإيقاف...**\n"
            else:
                status_text += "🔄 **نشط**\n"
        else:
            status_text += "🛑 **متوقف**\n"
        
        status_text += f"""
**إحصائيات جمع المجموعات:**
• 📦 المجموع: {status['stats']['total_collected']:,}
• 📢 مجموعات تيليجرام: {status['stats']['telegram_groups']:,}
• 📱 مجموعات واتساب: {status['stats']['whatsapp_groups']:,}
• 🎮 مجموعات ديسكورد: {status['stats']['discord_groups']:,}
• 📡 مجموعات سيجنال: {status['stats']['signal_groups']:,}
• ✅ مجموعات انضمت: {status['stats']['groups_joined']:,}
• ⏭️ مجموعات تخطيت: {status['stats']['groups_skipped']:,}
• 🔗 روابط من المجموعات: {status['stats']['links_from_groups']:,}
• ❌ أخطاء: {status['stats']['errors']:,}

**إحصائيات قاعدة البيانات:**
• 🔗 إجمالي المجموعات: {db_stats.get('group_links', 0):,}
• 🎯 مجموعات ميجا: {db_stats.get('megagroup_links', 0):,}
• 🚫 قنوات: {db_stats.get('channel_links', 0):,}
• ✅ مجموعات مع زر انضمام: {db_stats.get('join_button_links', 0):,}
• 💼 الجلسات النشطة: {db_stats.get('active_sessions', 0)}
• 👥 المستخدمين: {db_stats.get('total_users', 0)}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_status"),
             InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")]
        ])
        
        await update.message.reply_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        
        user_stats = await db.get_user_stats(user.id)
        
        stats_text = f"""
**📈 إحصائيات النظام المتقدمة**

🎯 **التركيز: المجموعات فقط (بدون قنوات)**

**إحصائيات المستخدم:**
"""
        
        if user_stats:
            stats_text += f"""• 🆔 المعرف: {user.id}
• 👤 الاسم: {user_stats.get('first_name', '')} {user_stats.get('last_name', '')}
• 📅 العضو منذ: {user_stats.get('added_date', 'غير معروف')}
• 📊 طلباتك: {user_stats.get('request_count', 0):,}
• 🔗 مجموعاتك: {user_stats.get('total_links', 0):,}
• 💼 جلساتك: {user_stats.get('total_sessions', 0)}
"""
        
        stats_text += f"""
**إحصائيات النظام (مجموعات فقط):**
• 🔗 إجمالي المجموعات: {db_stats.get('group_links', 0):,}
• 🎯 مجموعات ميجا: {db_stats.get('megagroup_links', 0):,}
• 🚫 القنوات: {db_stats.get('channel_links', 0):,}
• ✅ مجموعات مع زر انضمام: {db_stats.get('join_button_links', 0):,}
• 💼 الجلسات النشطة: {db_stats.get('active_sessions', 0)}
• 👥 المستخدمين: {db_stats.get('total_users', 0)}
• ✅ المجموعات المنضمة: {db_stats.get('joined_groups', 0):,}

**توزيع المنصات:**
"""
        
        for platform, count in db_stats.get('links_by_platform', {}).items():
            stats_text += f"• {platform}: {count:,}\n"
        
        await update.message.reply_text(stats_text, parse_mode="Markdown")
    
    async def sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sessions command - FIXED"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=20)
        
        if not sessions:
            await update.message.reply_text("❌ لا توجد جلسات نشطة")
            return
        
        sessions_text = f"""
**👥 الجلسات النشطة ({len(sessions)})**

"""
        
        for i, session in enumerate(sessions, 1):
            display_name = session.get('display_name', 'غير معروف')
            username = session.get('username', 'بدون معرف')
            phone = session.get('phone_number', 'بدون رقم')
            last_used = session.get('last_used', 'لم يستخدم')
            uses = session.get('total_uses', 0)
            total_links = session.get('total_links', 0)
            
            sessions_text += f"""**{i}. {display_name}**
• المعرف: @{username}
• الهاتف: {phone}
• الاستخدامات: {uses}
• الروابط المجمعة: {total_links}
• آخر استخدام: {last_used}

"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("🔄 تحديث", callback_data="refresh_sessions")]
        ])
        
        await update.message.reply_text(sessions_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        
        # الحصول على أعداد المجموعات لكل نوع
        total_groups = await db.get_links_count({'is_group': True})
        telegram_groups = await db.get_links_count({'platform': 'telegram', 'is_group': True})
        telegram_megagroups = await db.get_links_count({'platform': 'telegram', 'is_megagroup': True})
        groups_with_join = await db.get_links_count({'has_join_button': True})
        whatsapp_groups = await db.get_links_count({'platform': 'whatsapp'})
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 تصدير نصي", callback_data="export_txt"),
             InlineKeyboardButton("📊 تصدير CSV", callback_data="export_csv")],
            [InlineKeyboardButton("📋 تصدير JSON", callback_data="export_json")],
            [InlineKeyboardButton("🎯 مجموعات تيليجرام", callback_data="export_telegram_groups"),
             InlineKeyboardButton("✅ مجموعات مع زر انضمام", callback_data="export_groups_with_join")],
            [InlineKeyboardButton("👥 مجموعات ميجا", callback_data="export_megagroups"),
             InlineKeyboardButton("📱 مجموعات واتساب", callback_data="export_whatsapp")],
            [InlineKeyboardButton("📦 جميع المجموعات", callback_data="export_all_groups")]
        ])
        
        export_text = f"""
**📤 تصدير المجموعات فقط (بدون قنوات)**

**🎯 إحصائيات المجموعات:**
• 👥 إجمالي المجموعات: **{total_groups:,}**
• 📢 مجموعات تيليجرام: **{telegram_groups:,}**
• 🎯 مجموعات ميجا: **{telegram_megagroups:,}**
• ✅ مجموعات مع زر انضمام: **{groups_with_join:,}**
• 📱 مجموعات واتساب: **{whatsapp_groups:,}**

**خيارات التصدير:**
• 📄 نصي - روابط فقط
• 📊 CSV - مع المعلومات
• 📋 JSON - كامل المعلومات

**تصدير حسب النوع:**
• 🎯 مجموعات تيليجرام فقط
• ✅ مجموعات مع زر انضمام
• 👥 مجموعات ميجا (مجاميع كبيرة)
• 📱 مجموعات واتساب فقط
• 📦 جميع المجموعات

**ملاحظات:**
• الحد الأقصى للتصدير: {Config.MAX_EXPORT_LINKS:,} مجموعة
• **يتم تصدير المجموعات فقط وليس القنوات**
• المجموعات تحتوي على زر انضمام/طلب انضمام
"""
        
        await update.message.reply_text(export_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /backup command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💾 إنشاء نسخة", callback_data="create_backup"),
             InlineKeyboardButton("📋 قائمة النسخ", callback_data="list_backups")],
            [InlineKeyboardButton("🔄 تدوير النسخ", callback_data="rotate_backups")]
        ])
        
        backup_text = f"""
**💾 إدارة النسخ الاحتياطية**

**المميزات:**
• نسخ احتياطي تلقائي
• حفظ بيانات الجلسات والمجموعات
• استعادة البيانات عند الحاجة
• تدوير تلقائي للنسخ القديمة

**الإعدادات:**
• عدد النسخ المحفوظة: {Config.MAX_BACKUPS}
• النسخ التلقائية: {"✅ مفعل" if Config.BACKUP_ENABLED else "❌ معطل"}

**الأوامر:**
• إنشاء نسخة يدوية
• عرض قائمة النسخ
• تدوير النسخ القديمة
"""
        
        await update.message.reply_text(backup_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /collect command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        status = self.collection_manager.get_status()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء جمع المجموعات", callback_data="start_collect"),
             InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect"),
             InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status")],
            [InlineKeyboardButton("⚙️ إعدادات الجمع", callback_data="collect_settings")]
        ])
        
        collect_text = f"""
**🚀 إدارة عملية جمع المجموعات فقط**

🎯 **التركيز: المجموعات فقط (بدون قنوات)**
⚙️ **الإعدادات النشطة:**
• جمع المجموعات فقط: {"✅" if Config.COLLECT_ONLY_GROUPS else "❌"}
• تخطي القنوات: {"✅" if Config.SKIP_CHANNELS else "❌"}
• زر الانضمام مطلوب: {"✅" if Config.REQUIRE_JOIN_BUTTON else "❌"}

**الحالة الحالية:**
"""
        
        if status['active']:
            if status['paused']:
                collect_text += "⏸️ **موقف مؤقتاً**\n"
            else:
                collect_text += "🔄 **نشط**\n"
        else:
            collect_text += "🛑 **متوقف**\n"
        
        collect_text += f"""
**الإحصائيات:**
• المجموعات المجمعة: {status['stats']['total_collected']:,}
• مجموعات انضمت: {status['stats']['groups_joined']:,}
• مجموعات تخطيت: {status['stats']['groups_skipped']:,}
• روابط من المجموعات: {status['stats']['links_from_groups']:,}
• الأخطاء: {status['stats']['errors']:,}

**المميزات:**
• 🎯 جمع المجموعات فقط (لا قنوات)
• ⏭️ تخطي القنوات التي تحتوي على زر "اشتراك"
• ✅ جمع المجموعات التي تحتوي على زر "انضمام"
• 👥 التركيز على المجموعات التي تحتوي على أعضاء

**الحدود:**
• الجلسات المتزامنة: {Config.MAX_CONCURRENT_SESSIONS}
• محاولات الانضمام لكل جلسة: {Config.MAX_JOIN_ATTEMPTS_PER_SESSION}
• الرسائل لكل مجموعة: {Config.MAX_MESSAGES_TO_SCAN}
• الحد الأدنى للأعضاء: {Config.MIN_GROUP_PARTICIPANTS}
"""
        
        await update.message.reply_text(collect_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def add_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addsession command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        self.user_states[user.id] = {'waiting_for_session': True}
        
        add_text = """
**➕ إضافة جلسة جديدة**

**تعليمات الإضافة:**
1. افتح https://my.telegram.org
2. سجل الدخول بحسابك
3. انتقل إلى **API Development Tools**
4. أنشئ تطبيق جديد واحصل على:
   • api_id
   • api_hash
5. افتح @GetStringBot وأرسل /start
6. أرسل إليه api_id و api_hash
7. سيرسل لك كود الجلسة (session string)

**أرسل كود الجلسة الآن:**
(يمكنك نسخ الكود كاملاً وإرساله)
"""
        
        await update.message.reply_text(add_text, parse_mode="Markdown")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        data = query.data
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await self._edit_message_safe(query, "❌ غير مصرح لك بالوصول")
                return
        
        try:
            if data == "start_collect":
                await self._handle_start_collect(query)
            elif data == "pause_collect":
                await self._handle_pause_collect(query)
            elif data == "stop_collect":
                await self._handle_stop_collect(query)
            elif data == "collect_status":
                await self._handle_collect_status(query)
            elif data == "collect_settings":
                await self._handle_collect_settings(query)
            elif data == "add_session":
                await self._handle_add_session(query)
            elif data == "show_sessions":
                await self._handle_show_sessions(query)
            elif data == "show_stats":
                await self._handle_show_stats(query)
            elif data == "export_groups":
                await self._handle_export_groups(query)
            elif data == "export_txt":
                await self._handle_export_txt(query)
            elif data == "export_csv":
                await self._handle_export_csv(query)
            elif data == "export_json":
                await self._handle_export_json(query)
            elif data == "export_telegram_groups":
                await self._handle_export_telegram_groups(query)
            elif data == "export_groups_with_join":
                await self._handle_export_groups_with_join(query)
            elif data == "export_megagroups":
                await self._handle_export_megagroups(query)
            elif data == "export_whatsapp":
                await self._handle_export_whatsapp(query)
            elif data == "export_all_groups":
                await self._handle_export_all_groups(query)
            elif data == "create_backup":
                await self._handle_create_backup(query)
            elif data == "list_backups":
                await self._handle_list_backups(query)
            elif data == "rotate_backups":
                await self._handle_rotate_backups(query)
            elif data == "refresh_status":
                await self._handle_refresh_status(query)
            elif data == "refresh_sessions":
                await self._handle_refresh_sessions(query)
            elif data == "show_help":
                await self._handle_show_help(query)
            elif data == "show_settings":
                await self._handle_show_settings(query)
            elif data == "manage_collect":
                await self._handle_manage_collect(query)
            else:
                await self._edit_message_safe(query, "❌ أمر غير معروف")
        
        except Exception as e:
            logger.error(f"خطأ في معالجة الاستدعاء: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _edit_message_safe(self, query, text, reply_markup=None, parse_mode="Markdown"):
        """Edit message safely with error handling"""
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                # تجاهل الخطأ إذا الرسالة لم تتغير
                pass
            else:
                logger.error(f"خطأ في تعديل الرسالة: {e}")
                # إعادة إرسال الرسالة بدلاً من التعديل
                await query.message.reply_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
        except Exception as e:
            logger.error(f"خطأ غير متوقع في تعديل الرسالة: {e}")
            await query.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    
    async def _handle_start_collect(self, query):
        """Handle start collection"""
        if self.collection_manager.active:
            await self._edit_message_safe(query, "⏳ الجمع يعمل بالفعل")
            return
        
        # بدء مهمة الجمع
        await self.collection_manager.start_collection()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status")]
        ])
        
        await self._edit_message_safe(
            query,
            "🚀 **بدأ جمع المجموعات بنجاح!**\n\n"
            "جاري جمع روابط المجموعات فقط...\n"
            "🎯 **ملاحظة:** البوت يجمع المجموعات فقط وليس القنوات\n\n"
            "**ما يتم جمعه:**\n"
            "• ✅ مجموعات تحتوي على زر انضمام\n"
            "• ✅ مجموعات دعوة (روابط joinchat)\n"
            "• ✅ مجموعات تحتوي على أعضاء\n"
            "• ❌ **يتم تخطي القنوات تماماً**\n\n"
            "سيتم تحديث الإحصائيات تلقائياً.",
            reply_markup=keyboard
        )
    
    async def _handle_pause_collect(self, query):
        """Handle pause collection"""
        if not self.collection_manager.active:
            await self._edit_message_safe(query, "⚠️ الجمع غير نشط")
            return
        
        await self.collection_manager.pause()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ استئناف", callback_data="start_collect"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")]
        ])
        
        await self._edit_message_safe(
            query,
            "⏸️ **تم إيقاف جمع المجموعات مؤقتاً**\n\n"
            "يمكنك استئناف الجمع في أي وقت.\n"
            "الجلسات تبقى نشطة.\n\n"
            "**الإحصائيات الحالية:**\n"
            f"• المجموعات المجمعة: {self.collection_manager.stats['total_collected']:,}\n"
            f"• مجموعات انضمت: {self.collection_manager.stats['groups_joined']:,}\n"
            f"• مجموعات تخطيت: {self.collection_manager.stats['groups_skipped']:,}",
            reply_markup=keyboard
        )
    
    async def _handle_stop_collect(self, query):
        """Handle stop collection"""
        if not self.collection_manager.active:
            await self._edit_message_safe(query, "⚠️ الجمع غير نشط")
            return
        
        await self.collection_manager.stop()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 إعادة البدء", callback_data="start_collect"),
             InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")]
        ])
        
        await self._edit_message_safe(
            query,
            "⏹️ **تم إيقاف جمع المجموعات**\n\n"
            "توقفت عملية الجمع بنجاح.\n"
            "تم حفظ جميع المجموعات المجمعة.\n\n"
            "**الإحصائيات النهائية:**\n"
            f"• إجمالي المجموعات: {self.collection_manager.stats['total_collected']:,}\n"
            f"• مجموعات تيليجرام: {self.collection_manager.stats['telegram_groups']:,}\n"
            f"• مجموعات انضمت: {self.collection_manager.stats['groups_joined']:,}\n"
            f"• مجموعات تخطيت: {self.collection_manager.stats['groups_skipped']:,}\n\n"
            "🎯 **ملاحظة:** تم جمع المجموعات فقط وليس القنوات",
            reply_markup=keyboard
        )
    
    async def _handle_collect_status(self, query):
        """Handle collect status"""
        status = self.collection_manager.get_status()
        
        status_text = f"""
**📊 حالة جمع المجموعات التفصيلية**

🎯 **التركيز: المجموعات فقط (بدون قنوات)**

**الحالة:** {"🔄 نشط" if status['active'] else "🛑 متوقف"}
**الإيقاف المؤقت:** {"⏸️ نعم" if status['paused'] else "▶️ لا"}
**طلب الإيقاف:** {"✅ نعم" if status['stop_requested'] else "❌ لا"}
**الدورة الحالية:** {status['current_cycle']}

**الإحصائيات:**
• المجموعات المجمعة: {status['stats']['total_collected']:,}
• مجموعات تيليجرام: {status['stats']['telegram_groups']:,}
• مجموعات واتساب: {status['stats']['whatsapp_groups']:,}
• مجموعات ديسكورد: {status['stats']['discord_groups']:,}
• مجموعات سيجنال: {status['stats']['signal_groups']:,}
• مجموعات انضمت: {status['stats']['groups_joined']:,}
• مجموعات تخطيت: {status['stats']['groups_skipped']:,}
• روابط من المجموعات: {status['stats']['links_from_groups']:,}
• الأخطاء: {status['stats']['errors']:,}
"""
        
        await self._edit_message_safe(query, status_text)
    
    async def _handle_collect_settings(self, query):
        """Handle collect settings"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ تغيير الحدود", callback_data="change_limits"),
             InlineKeyboardButton("⏱️ ضبط التأخيرات", callback_data="adjust_delays")],
            [InlineKeyboardButton("🔄 العودة", callback_data="manage_collect")]
        ])
        
        settings_text = f"""
**⚙️ إعدادات جمع المجموعات**

🎯 **الإعدادات الأساسية:**
• جمع المجموعات فقط: {"✅ مفعل" if Config.COLLECT_ONLY_GROUPS else "❌ معطل"}
• تخطي القنوات: {"✅ مفعل" if Config.SKIP_CHANNELS else "❌ معطل"}
• زر الانضمام مطلوب: {"✅ مفعل" if Config.REQUIRE_JOIN_BUTTON else "❌ معطل"}
• الحد الأدنى للأعضاء: {Config.MIN_GROUP_PARTICIPANTS}

**الإعدادات الفنية:**
• الجلسات المتزامنة: {Config.MAX_CONCURRENT_SESSIONS}
• محاولات الانضمام: {Config.MAX_JOIN_ATTEMPTS_PER_SESSION}
• الرسائل لكل مجموعة: {Config.MAX_MESSAGES_TO_SCAN}
• الدردشات لكل جلسة: {Config.MAX_DIALOGS_PER_SESSION}

**التأخيرات:**
• بين الجلسات: {Config.REQUEST_DELAYS['between_sessions']} ثانية
• بعد الانضمام: {Config.REQUEST_DELAYS['after_join']} ثانية
• بين الدورات: {Config.REQUEST_DELAYS['min_cycle_delay']}-{Config.REQUEST_DELAYS['max_cycle_delay']} ثانية
"""
        
        await self._edit_message_safe(query, settings_text, reply_markup=keyboard)
    
    async def _handle_add_session(self, query):
        """Handle add session"""
        user = query.from_user
        self.user_states[user.id] = {'waiting_for_session': True}
        
        add_text = """
**➕ إضافة جلسة جديدة**

**أرسل كود الجلسة الآن:**
(يمكنك نسخ الكود كاملاً وإرساله)

**ملاحظات:**
• الجلسة ستخزن مشفرة
• يمكنك إضافة حتى {Config.MAX_SESSIONS_PER_USER} جلسة
• الجلسة يجب أن تكون نشطة
• تستخدم الجلسات لجمع المجموعات فقط
"""
        
        await self._edit_message_safe(query, add_text)
    
    async def _handle_show_sessions(self, query):
        """Handle show sessions"""
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=20)
        
        if not sessions:
            await self._edit_message_safe(query, "❌ لا توجد جلسات نشطة")
            return
        
        sessions_text = f"**👥 الجلسات النشطة ({len(sessions)})**\n\n"
        
        for i, session in enumerate(sessions, 1):
            display_name = session.get('display_name', 'غير معروف')
            username = session.get('username', 'بدون معرف')
            uses = session.get('total_uses', 0)
            total_links = session.get('total_links', 0)
            
            sessions_text += f"**{i}. {display_name}** (@{username}) - استخدامات: {uses} - روابط: {total_links:,}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("🔄 تحديث", callback_data="refresh_sessions")]
        ])
        
        await self._edit_message_safe(query, sessions_text, reply_markup=keyboard)
    
    async def _handle_show_stats(self, query):
        """Handle show stats"""
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        
        stats_text = f"""
**📈 إحصائيات المجموعات**

🎯 **التركيز: المجموعات فقط (بدون قنوات)**

**إحصائيات قاعدة البيانات:**
• 🔗 إجمالي المجموعات: {db_stats.get('group_links', 0):,}
• 🎯 مجموعات ميجا: {db_stats.get('megagroup_links', 0):,}
• 🚫 القنوات: {db_stats.get('channel_links', 0):,}
• ✅ مجموعات مع زر انضمام: {db_stats.get('join_button_links', 0):,}
• 💼 الجلسات النشطة: {db_stats.get('active_sessions', 0)}
• 👥 المستخدمين: {db_stats.get('total_users', 0)}
• ✅ المجموعات المنضمة: {db_stats.get('joined_groups', 0):,}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="show_stats"),
             InlineKeyboardButton("📊 إحصائيات الجمع", callback_data="collect_status")]
        ])
        
        await self._edit_message_safe(query, stats_text, reply_markup=keyboard)
    
    async def _handle_export_groups(self, query):
        """Handle export groups"""
        await self.export_command(query.message, query.message.reply_to_message)
    
    async def _handle_export_txt(self, query):
        """Handle export as text"""
        await self._edit_message_safe(query, "⏳ جاري تحضير الملف...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links(limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد مجموعات للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("🎯 **مجموعات فقط (بدون قنوات)**\n")
                f.write(f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                f.write(f"📊 عدد المجموعات: {len(links):,}\n")
                f.write("=" * 50 + "\n\n")
                
                for link in links:
                    f.write(f"{link}\n")
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📦 **ملف المجموعات النصي**\n\n"
                           f"📊 عدد المجموعات: **{len(links):,}**\n"
                           f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                           f"🎯 **ملاحظة:**\n"
                           f"• هذه مجموعات وليست قنوات\n"
                           f"• تم تخطي جميع القنوات",
                    parse_mode="Markdown"
                )
            
            # حذف الملف المحلي
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في تصدير النصي: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_csv(self, query):
        """Handle export as CSV"""
        await self._edit_message_safe(query, "⏳ جاري تحضير الملف...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            cursor = await db.conn.execute('''
                SELECT url, platform, is_group, is_megagroup, has_join_button, 
                       members_count, collected_date, is_verified
                FROM links 
                WHERE is_active = 1 AND is_group = 1
                LIMIT ?
            ''', (Config.MAX_EXPORT_LINKS,))
            
            rows = await cursor.fetchall()
            
            if not rows:
                await self._edit_message_safe(query, "❌ لا توجد مجموعات للتصدير")
                return
            
            # حفظ في ملف CSV
            filename = f"groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("URL,Platform,Is_Group,Is_Megagroup,Has_Join_Button,Members,Date,Verified\n")
                for row in rows:
                    url, platform, is_group, is_megagroup, has_join_button, members, date, verified = row
                    f.write(f'"{url}","{platform}",{is_group},{is_megagroup},{has_join_button},{members},"{date}",{verified}\n')
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📊 **ملف المجموعات CSV**\n\n"
                           f"📊 عدد السجلات: **{len(rows):,}**\n"
                           f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                           f"🎯 **يتضمن معلومات:**\n"
                           f"• الرابط والمنصة\n"
                           f"• نوع المجموعة\n"
                           f"• عدد الأعضاء\n"
                           f"• تاريخ الجمع",
                    parse_mode="Markdown"
                )
            
            # حذف الملف المحلي
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في تصدير CSV: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_json(self, query):
        """Handle export as JSON"""
        await self._edit_message_safe(query, "⏳ جاري تحضير الملف...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            cursor = await db.conn.execute('''
                SELECT url, platform, is_group, is_megagroup, has_join_button, 
                       members_count, collected_date, is_verified, validation_score,
                       is_public_group, is_private_group
                FROM links 
                WHERE is_active = 1 AND is_group = 1
                LIMIT ?
            ''', (Config.MAX_EXPORT_LINKS,))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            if not rows:
                await self._edit_message_safe(query, "❌ لا توجد مجموعات للتصدير")
                return
            
            # تحويل إلى JSON
            data = []
            for row in rows:
                item = dict(zip(columns, row))
                data.append(item)
            
            # حفظ في ملف JSON
            filename = f"groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📋 **ملف المجموعات JSON**\n\n"
                           f"📊 عدد السجلات: **{len(data):,}**\n"
                           f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                           f"🎯 **معلومات كاملة:**\n"
                           f"• كافة بيانات المجموعات\n"
                           f"• تنسيق JSON منظم\n"
                           f"• جاهز للاستخدام في البرمجة",
                    parse_mode="Markdown"
                )
            
            # حذف الملف المحلي
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في تصدير JSON: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_telegram_groups(self, query):
        """Handle export Telegram groups only"""
        await self._edit_message_safe(query, "⏳ جاري تحضير ملف مجموعات تيليجرام...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links(
                {'platform': 'telegram', 'is_group': True}, 
                Config.MAX_EXPORT_LINKS
            )
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد مجموعات تيليجرام للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"telegram_groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("🎯 **مجموعات تيليجرام فقط (بدون قنوات)**\n")
                f.write(f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                f.write(f"📊 عدد المجموعات: {len(links):,}\n")
                f.write("=" * 50 + "\n\n")
                
                for link in links:
                    f.write(f"{link}\n")
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"🎯 **مجموعات تيليجرام فقط**\n\n"
                           f"📊 عدد المجموعات: **{len(links):,}**\n"
                           f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                           f"**ملاحظات:**\n"
                           f"• هذه مجموعات وليست قنوات\n"
                           f"• تحتوي على أعضاء فعليين\n"
                           f"• معظمها تحتوي على زر انضمام\n"
                           f"• تم تخطي جميع القنوات",
                    parse_mode="Markdown"
                )
            
            # حذف الملف المحلي
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في تصدير مجموعات تيليجرام: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_groups_with_join(self, query):
        """Handle export groups with join button only"""
        await self._edit_message_safe(query, "⏳ جاري تحضير ملف المجموعات مع زر انضمام...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links(
                {'has_join_button': True}, 
                Config.MAX_EXPORT_LINKS
            )
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد مجموعات مع زر انضمام للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"groups_with_join_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("✅ **مجموعات مع زر انضمام/طلب انضمام**\n")
                f.write(f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                f.write(f"📊 عدد المجموعات: {len(links):,}\n")
                f.write("=" * 50 + "\n\n")
                
                for link in links:
                    f.write(f"{link}\n")
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"✅ **مجموعات مع زر انضمام**\n\n"
                           f"📊 عدد المجموعات: **{len(links):,}**\n"
                           f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                           f"**مميزات:**\n"
                           f"• تحتوي على زر انضمام أو طلب انضمام\n"
                           f"• ليست قنوات (تم تخطي القنوات)\n"
                           f"• جودة عالية واحتمال وجود أعضاء\n"
                           f"• جاهزة للاستخدام مباشرة",
                    parse_mode="Markdown"
                )
            
            # حذف الملف المحلي
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في تصدير مجموعات مع زر انضمام: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_megagroups(self, query):
        """Handle export mega groups only"""
        await self._edit_message_safe(query, "⏳ جاري تحضير ملف مجموعات ميجا...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links(
                {'is_megagroup': True}, 
                Config.MAX_EXPORT_LINKS
            )
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد مجموعات ميجا للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"megagroups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("👥 **مجموعات ميجا (مجاميع كبيرة)**\n")
                f.write(f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                f.write(f"📊 عدد المجموعات: {len(links):,}\n")
                f.write("=" * 50 + "\n\n")
                
                for link in links:
                    f.write(f"{link}\n")
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"👥 **مجموعات ميجا**\n\n"
                           f"📊 عدد المجموعات: **{len(links):,}**\n"
                           f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                           f"**معلومات:**\n"
                           f"• هذه مجاميع كبيرة (ميجا جروب)\n"
                           f"• تحتوي على عدد كبير من الأعضاء\n"
                           f"• نشطة وليست قنوات\n"
                           f"• جودة ممتازة",
                    parse_mode="Markdown"
                )
            
            # حذف الملف المحلي
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في تصدير مجموعات ميجا: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_whatsapp(self, query):
        """Handle export WhatsApp groups only"""
        await self._edit_message_safe(query, "⏳ جاري تحضير ملف مجموعات واتساب...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links(
                {'platform': 'whatsapp'}, 
                Config.MAX_EXPORT_LINKS
            )
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد مجموعات واتساب للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"whatsapp_groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("📱 **مجموعات واتساب**\n")
                f.write(f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                f.write(f"📊 عدد المجموعات: {len(links):,}\n")
                f.write("=" * 50 + "\n\n")
                
                for link in links:
                    f.write(f"{link}\n")
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📱 **مجموعات واتساب**\n\n"
                           f"📊 عدد المجموعات: **{len(links):,}**\n"
                           f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                           f"**مميزات:**\n"
                           f"• روابط مجموعات واتساب\n"
                           f"• روابط دعوة مباشرة\n"
                           f"• جاهزة للاستخدام",
                    parse_mode="Markdown"
                )
            
            # حذف الملف المحلي
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في تصدير مجموعات واتساب: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_all_groups(self, query):
        """Handle export all groups (all platforms)"""
        await self._edit_message_safe(query, "⏳ جاري تحضير ملف جميع المجموعات...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links(
                {'is_group': True}, 
                Config.MAX_EXPORT_LINKS
            )
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد مجموعات للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"all_groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("📦 **جميع المجموعات (جميع المنصات)**\n")
                f.write(f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                f.write(f"📊 عدد المجموعات: {len(links):,}\n")
                f.write("=" * 50 + "\n\n")
                
                for link in links:
                    f.write(f"{link}\n")
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📦 **جميع المجموعات**\n\n"
                           f"📊 عدد المجموعات: **{len(links):,}**\n"
                           f"📅 تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                           f"**يتضمن:**\n"
                           f"• 📢 مجموعات تيليجرام (بدون قنوات)\n"
                           f"• 📱 مجموعات واتساب\n"
                           f"• 🎮 مجموعات ديسكورد\n"
                           f"• 📡 مجموعات سيجنال\n\n"
                           f"🎯 **تم تخطي جميع القنوات**",
                    parse_mode="Markdown"
                )
            
            # حذف الملف المحلي
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في تصدير جميع المجموعات: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_create_backup(self, query):
        """Handle create backup"""
        await self._edit_message_safe(query, "⏳ جاري إنشاء نسخة احتياطية...")
        
        backup = await BackupManager.create_backup()
        
        if backup:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 قائمة النسخ", callback_data="list_backups"),
                 InlineKeyboardButton("🔄 تدوير النسخ", callback_data="rotate_backups")]
            ])
            
            await self._edit_message_safe(
                query,
                f"✅ **تم إنشاء نسخة احتياطية بنجاح!**\n\n"
                f"**تفاصيل النسخة:**\n"
                f"• المعرف: {backup['backup_id']}\n"
                f"• الوقت: {backup['timestamp']}\n"
                f"• الحجم: {backup['size_bytes'] / 1024 / 1024:.2f} MB\n"
                f"• المسار: {backup['file_path']}",
                reply_markup=keyboard
            )
        else:
            await self._edit_message_safe(query, "❌ فشل في إنشاء نسخة احتياطية")
    
    async def _handle_list_backups(self, query):
        """Handle list backups"""
        try:
            if not os.path.exists("backups"):
                await self._edit_message_safe(query, "❌ لا توجد نسخ احتياطية")
                return
            
            backups = []
            for filename in os.listdir("backups"):
                if filename.startswith("backup_") and filename.endswith(".db"):
                    path = os.path.join("backups", filename)
                    size = os.path.getsize(path) / 1024 / 1024
                    ctime = datetime.fromtimestamp(os.path.getctime(path))
                    backups.append({
                        'filename': filename,
                        'size_mb': size,
                        'created': ctime
                    })
            
            if not backups:
                await self._edit_message_safe(query, "❌ لا توجد نسخ احتياطية")
                return
            
            backups.sort(key=lambda x: x['created'], reverse=True)
            
            list_text = "**📋 قائمة النسخ الاحتياطية**\n\n"
            
            for i, backup in enumerate(backups, 1):
                list_text += f"""**{i}. {backup['filename']}**
• الحجم: {backup['size_mb']:.2f} MB
• التاريخ: {backup['created'].strftime('%Y-%m-%d %H:%M')}

"""
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 تدوير النسخ", callback_data="rotate_backups"),
                 InlineKeyboardButton("💾 إنشاء نسخة", callback_data="create_backup")]
            ])
            
            await self._edit_message_safe(query, list_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"خطأ في عرض النسخ: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_rotate_backups(self, query):
        """Handle rotate backups"""
        await self._edit_message_safe(query, "⏳ جاري تدوير النسخ القديمة...")
        
        try:
            await BackupManager.rotate_backups()
            await self._edit_message_safe(query, "✅ تم تدوير النسخ الاحتياطية بنجاح")
        except Exception as e:
            logger.error(f"خطأ في تدوير النسخ: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_refresh_status(self, query):
        """Handle refresh status"""
        # إعادة إنشاء الأمر /status
        await self.status_command(query.message, query.message.reply_to_message)
    
    async def _handle_refresh_sessions(self, query):
        """Handle refresh sessions"""
        # إعادة إنشاء الأمر /sessions
        await self.sessions_command(query.message, query.message.reply_to_message)
    
    async def _handle_show_help(self, query):
        """Handle show help"""
        await self.help_command(query.message, query.message.reply_to_message)
    
    async def _handle_show_settings(self, query):
        """Handle show settings"""
        settings_text = f"""
**⚙️ إعدادات النظام**

**إعدادات الأمان:**
• المدراء: {len(Config.ADMIN_USER_IDS)}
• المستخدمون المسموحون: {len(Config.ALLOWED_USER_IDS)}
• التشفير: {"✅ مفعل" if Config.ENCRYPTION_KEY else "❌ معطل"}

**إعدادات الأداء:**
• الجلسات المتزامنة: {Config.MAX_CONCURRENT_SESSIONS}
• الذاكرة القصوى: {Config.MAX_MEMORY_MB} MB

**إعدادات قاعدة البيانات:**
• المسار: {Config.DB_PATH}
• النسخ الاحتياطي: {"✅ مفعل" if Config.BACKUP_ENABLED else "❌ معطل"}
• عدد النسخ: {Config.MAX_BACKUPS}

**إعدادات الجمع:**
• جمع المجموعات فقط: {"✅ مفعل" if Config.COLLECT_ONLY_GROUPS else "❌ معطل"}
• تخطي القنوات: {"✅ مفعل" if Config.SKIP_CHANNELS else "❌ معطل"}
• الحد الأدنى للأعضاء: {Config.MIN_GROUP_PARTICIPANTS}
"""
        
        await self._edit_message_safe(query, settings_text)
    
    async def _handle_manage_collect(self, query):
        """Handle manage collect"""
        await self.collect_command(query.message, query.message.reply_to_message)
    
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
            await update.message.reply_text(
                "مرحباً! يمكنك استخدام الأوامر التالية:\n"
                "/start - بدء البوت\n"
                "/help - المساعدة\n"
                "/status - حالة النظام\n"
                "/sessions - عرض الجلسات\n"
                "/export - تصدير المجموعات\n"
                "/collect - إدارة الجمع\n"
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
                'focus': 'groups_only'
            }
        }
        
        db = await EnhancedDatabaseManager.get_instance()
        success, message, details = await db.add_session(session_data)
        
        if success:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء جمع المجموعات", callback_data="start_collect"),
                 InlineKeyboardButton("👥 عرض الجلسات", callback_data="show_sessions")]
            ])
            
            await update.message.reply_text(
                f"✅ **تمت إضافة الجلسة بنجاح!**\n\n"
                f"**معلومات المستخدم:**\n"
                f"• الاسم: {session_data['display_name']}\n"
                f"• المعرف: @{session_data['username']}\n"
                f"• الهاتف: {session_data['phone_number']}\n\n"
                f"**الجلسة:**\n"
                f"• مشفرة ومخزنة بأمان\n"
                f"• جاهزة للاستخدام في جمع المجموعات فقط\n"
                f"• رقم الجلسة: {details.get('session_id')}\n\n"
                f"🎯 **ملاحظة:** هذه الجلسة سوف تجمع المجموعات فقط وليس القنوات",
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
                
                await asyncio.sleep(2)  # انتظار قصير
                
                try:
                    await context.application.stop()
                    await context.application.initialize()
                    await context.application.start()
                    logger.info("✅ تم إعادة تشغيل البوت بعد حل التعارض")
                except Exception as restart_error:
                    logger.error(f"فشل إعادة التشغيل: {restart_error}")
                
                return
            
            if update and update.effective_chat:
                error_message = (
                    "❌ **حدث خطأ غير متوقع**\n\n"
                    "لقد واجهنا مشكلة فنية. حاول مرة أخرى بعد قليل.\n\n"
                    "يمكنك استخدام /start للعودة للقائمة الرئيسية."
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=error_message,
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
        self.app = FastAPI(title="Telegram Group Collector Health")
        self._setup_routes()
        self.server_thread = None
        
    def _setup_routes(self):
        """Setup routes"""
        
        @self.app.get("/")
        async def root():
            return {"status": "running", "service": "Telegram Group Collector (Groups Only)"}
        
        @self.app.get("/health")
        async def health():
            try:
                db = await EnhancedDatabaseManager.get_instance()
                stats = await db.get_stats_summary()
                
                status = {
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat(),
                    "focus": "groups_only",
                    "settings": {
                        "collect_only_groups": Config.COLLECT_ONLY_GROUPS,
                        "skip_channels": Config.SKIP_CHANNELS,
                        "min_group_members": Config.MIN_GROUP_PARTICIPANTS
                    },
                    "database_stats": stats,
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
        
        @self.app.get("/stats")
        async def stats():
            try:
                db = await EnhancedDatabaseManager.get_instance()
                stats = await db.get_stats_summary()
                
                return JSONResponse(status_code=200, content=stats)
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
        
        logger.info("🤖 بدء تشغيل بوت جمع المجموعات فقط (بدون قنوات)...")
        logger.info(f"🎯 التركيز: COLLECT_ONLY_GROUPS={Config.COLLECT_ONLY_GROUPS}")
        logger.info(f"⚙️ الإعدادات: SKIP_CHANNELS={Config.SKIP_CHANNELS}, MIN_GROUP_PARTICIPANTS={Config.MIN_GROUP_PARTICIPANTS}")
        logger.info(f"🔥 الحد الأقصى للجلسات: {Config.MAX_CONCURRENT_SESSIONS}")
        
        try:
            # تشغيل البوت
            await bot.app.initialize()
            await bot.app.start()
            await bot.app.updater.start_polling()
            
            logger.info("✅ البوت يعمل بنجاح! (تركيز على المجموعات فقط)")
            logger.info("📋 الأوامر المتاحة: /start, /help, /status, /stats, /sessions, /export, /collect")
            
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
