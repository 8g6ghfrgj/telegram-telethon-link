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
    MAX_CACHED_URLS = 50000
    CACHE_CLEAN_INTERVAL = 1000
    MAX_MEMORY_MB = 500
    
    # Performance settings - إعدادات الأداء
    MAX_CONCURRENT_SESSIONS = 5
    REQUEST_DELAYS = {
        'normal': 0.3,
        'join_request': 2.0,
        'search': 1.0,
        'flood_wait': 5.0,
        'between_sessions': 1.0,
        'between_tasks': 0.1,
        'min_cycle_delay': 5.0,
        'max_cycle_delay': 30.0,
        'validation_delay': 0.5,
        'between_groups': 0.3,
        'between_messages': 0.05
    }
    
    # Collection limits - حدود الجمع
    MAX_DIALOGS_PER_SESSION = 500  # زيادة لجمع كل الدردشات
    MAX_MESSAGES_PER_SEARCH = 200   # زيادة عدد الرسائل
    MAX_LINKS_PER_CYCLE = 5000     # زيادة عدد الروابط
    MAX_BATCH_SIZE = 500
    
    # Database - قاعدة البيانات
    DB_PATH = "telegram_links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10
    DB_POOL_SIZE = 5
    
    # WhatsApp collection - جمع واتساب
    WHATSAPP_DAYS_BACK = 60  # فقط الروابط من آخر 60 يوم
    
    # Telegram collection - جمع تيليجرام
    TELEGRAM_YEARS_BACK = 5  # جمع الروابط من آخر 5 سنوات
    
    # Link verification - التحقق من الروابط
    MAX_LINK_LENGTH = 200
    VALIDATION_TIMEOUT = 30
    
    # Rate limiting - الحد من الطلبات
    USER_RATE_LIMIT = {
        'max_requests': 30,
        'per_seconds': 60
    }
    
    # Session management - إدارة الجلسات
    SESSION_TIMEOUT = 600
    MAX_SESSIONS_PER_USER = 20
    
    # Export - التصدير
    MAX_EXPORT_LINKS = 100000
    EXPORT_CHUNK_SIZE = 5000
    
    # Advanced settings - إعدادات متقدمة
    TELEGRAM_NO_TIME_LIMIT = True  # جمع تيليجرام بدون قيود زمنية
    ENABLE_ADVANCED_VALIDATION = True
    
    # Collection settings - إعدادات الجمع
    COLLECT_ACTIVE_LINKS_ONLY = True  # جمع الروابط النشطة فقط
    ENABLE_DEEP_COLLECTION = True
    MAX_DEEP_MESSAGES = 200
    COLLECT_FROM_ALL_GROUPS = True
    ENABLE_MASS_COLLECTION = True
    MESSAGES_PER_GROUP = 150
    
    # Keywords - الكلمات المفتاحية
    TELEGRAM_KEYWORDS = ['t.me', 'telegram.me', 'telegram.dog', 'joinchat', 'join']
    WHATSAPP_KEYWORDS = ['chat.whatsapp.com', 'whatsapp.com']
    ALL_KEYWORDS = TELEGRAM_KEYWORDS + WHATSAPP_KEYWORDS
    
    # Collection categories - أقسام التجميع
    COLLECT_BOT_LINKS = True  # جمع روابط البوتات
    COLLECT_SUBSCRIBER_GROUPS = True  # جمع مجموعات المشتركين
    COLLECT_JOIN_REQUEST_GROUPS = True  # جمع مجموعات طلب الانضمام
    COLLECT_MEMBER_GROUPS = True  # جمع مجموعات الأعضاء
    COLLECT_MESSAGE_LINKS = True  # جمع روابط الرسائل (واحدة من كل مجموعة)
    COLLECT_GENERAL_GROUPS = True  # جمع المجموعات العامة
    
    # Date limits - حدود التاريخ
    MIN_MESSAGE_DATE = datetime.now() - timedelta(days=365 * 5)  # 5 سنوات للتليجرام

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
# Advanced Link Processor - معالج الروابط المتقدم
# ======================

class AdvancedLinkProcessor:
    """Advanced link processing with Telegram preservation"""
    
    TRACKING_PARAMS = [
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'ref', 'source', 'campaign', 'medium', 'term', 'content',
        'fbclid', 'gclid', 'msclkid', 'dclid', 'igshid',
        'si', 's', 't', 'mibextid'
    ]
    
    ALLOWED_DOMAINS = [
        't.me', 'telegram.me', 'telegram.dog',
        'chat.whatsapp.com', 'whatsapp.com'
    ]
    
    @staticmethod
    def normalize_telegram_url(url: str) -> str:
        """Normalize Telegram URL without changing format"""
        if not url or not isinstance(url, str):
            return ""
        
        original_url = url
        
        # تنظيف أساسي
        url = url.strip()
        url = re.sub(r'^["\'\s*]+|["\'\s*]+$', '', url)
        
        # استخراج الرابط من النص
        url_patterns = [
            r'(https?://[^\s<>]+)',
            r'(t\.me/[^\s<>]+)',
            r'(telegram\.me/[^\s<>]+)',
            r'(telegram\.dog/[^\s<>]+)'
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
            if any(domain in url for domain in ['t.me', 'telegram.me', 'telegram.dog']):
                url = 'https://' + url.lstrip('/')
        
        # إزالة معاملات التتبع فقط
        try:
            parsed = urlparse(url)
            if parsed.query:
                params = parse_qs(parsed.query, keep_blank_values=True)
                filtered_params = {}
                
                for key, values in params.items():
                    key_lower = key.lower()
                    is_tracking = False
                    
                    for tracking_param in AdvancedLinkProcessor.TRACKING_PARAMS:
                        if tracking_param in key_lower:
                            is_tracking = True
                            break
                    
                    if not is_tracking and key:
                        filtered_params[key] = values[0] if values else ''
                
                if filtered_params:
                    query_string = urlencode(filtered_params, doseq=True)
                    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query_string}"
                else:
                    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                
                if parsed.fragment:
                    clean_url += f"#{parsed.fragment}"
                
                return clean_url
            
        except Exception as e:
            logger.debug(f"خطأ في توحيد الرابط {original_url}: {e}")
        
        return url
    
    @staticmethod
    def normalize_whatsapp_url(url: str) -> str:
        """Normalize WhatsApp URL - حفظ الرابط كما هو"""
        if not url or not isinstance(url, str):
            return ""
        
        # تنظيف أساسي فقط
        url = url.strip()
        url = re.sub(r'^["\'\s*]+|["\'\s*]+$', '', url)
        
        # إضافة https إذا كانت مفقودة لواتساب
        if not url.startswith(('http://', 'https://')):
            if 'chat.whatsapp.com' in url.lower() or 'whatsapp.com' in url.lower():
                url = 'https://' + url.lstrip('/')
        
        return url
    
    @staticmethod
    def extract_url_info(url: str) -> Dict:
        """Extract comprehensive information from URL"""
        # تحديد المنصة
        if any(keyword in url.lower() for keyword in Config.TELEGRAM_KEYWORDS):
            platform = 'telegram'
            normalized_url = AdvancedLinkProcessor.normalize_telegram_url(url)
        elif any(keyword in url.lower() for keyword in Config.WHATSAPP_KEYWORDS):
            platform = 'whatsapp'
            normalized_url = AdvancedLinkProcessor.normalize_whatsapp_url(url)
        else:
            platform = 'unknown'
            normalized_url = url
        
        result = {
            'original_url': url,
            'normalized_url': normalized_url,
            'platform': platform,
            'url_hash': hashlib.md5(normalized_url.encode()).hexdigest() if normalized_url else '',
            'is_valid': False,
            'details': {}
        }
        
        if not normalized_url:
            return result
        
        try:
            if platform == 'telegram':
                result['details'] = AdvancedLinkProcessor._extract_telegram_info(normalized_url)
            elif platform == 'whatsapp':
                result['details'] = AdvancedLinkProcessor._extract_whatsapp_info(normalized_url)
            
            result['is_valid'] = True
            
        except Exception as e:
            logger.debug(f"خطأ في استخراج معلومات الرابط: {e}")
        
        return result
    
    @staticmethod
    def _extract_telegram_info(url: str) -> Dict:
        """Extract Telegram specific information"""
        result = {
            'is_valid': False,
            'username': '',
            'invite_hash': '',
            'is_channel': False,
            'is_group': False,
            'is_bot': False,
            'is_join_request': False,
            'is_public': False,
            'is_private': False,
            'is_supergroup': False,
            'is_broadcast': False,
            'path_segments': [],
            'is_active': True,
            'is_join_link': False,
            'is_subscription': False,
            'is_message_link': False,
            'has_subscribers': False,
            'requires_join': False,
            'is_general_group': False
        }
        
        try:
            parsed = urlparse(url)
            path = parsed.path.strip('/')
            
            if not path:
                return result
            
            segments = path.split('/')
            result['path_segments'] = segments
            
            # كشف روابط البوتات
            if 'bot' in url.lower() or (len(segments) > 0 and 'bot' in segments[0].lower()):
                result['is_bot'] = True
                result['is_valid'] = True
                result['username'] = segments[0] if len(segments) > 0 else ''
                return result
            
            # كشف روابط الرسائل
            if len(segments) == 2 and segments[1].isdigit() and len(segments[1]) > 2:
                result['is_message_link'] = True
                result['is_valid'] = True
                result['username'] = segments[0]
                return result
            
            # كشف روابط الانضمام
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
                result['requires_join'] = True
                return result
            
            # كشف القنوات (المشتركين)
            if len(segments) == 1:
                if segments[0].startswith('+'):
                    result['is_join_request'] = True
                    result['is_private'] = True
                    result['invite_hash'] = segments[0][1:]
                    result['is_valid'] = True
                    result['requires_join'] = True
                else:
                    # قد تكون مجموعة عامة أو قناة
                    result['is_public'] = True
                    result['is_valid'] = True
                    result['username'] = segments[0]
                    
                    # تحقق من إذا كانت قناة (تحتوي على مشتركين)
                    if 'channel' in url.lower() or 'c/' in url.lower():
                        result['is_channel'] = True
                        result['is_broadcast'] = True
                        result['is_subscription'] = True
                        result['has_subscribers'] = True
                    else:
                        result['is_group'] = True
                        result['is_general_group'] = True
            
            return result
            
        except Exception as e:
            logger.debug(f"خطأ في استخراج معلومات تيليجرام: {e}")
            return result
    
    @staticmethod
    def _extract_whatsapp_info(url: str) -> Dict:
        """Extract WhatsApp specific information - حفظ الرابط كما هو"""
        result = {
            'is_valid': True,
            'invite_code': '',
            'is_group': True,
            'is_active': True,
            'requires_join': True,
            'is_recent': True  # سيتم التحقق من التاريخ لاحقاً
        }
        
        try:
            parsed = urlparse(url)
            path = parsed.path.strip('/')
            result['invite_code'] = path
        except:
            pass
        
        return result

# ======================
# Enhanced Database Manager - مدير قاعدة البيانات المحسن
# ======================

class EnhancedDatabaseManager:
    """Advanced database management with categories"""
    
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
        """Create database tables with categories"""
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
        
        # جدول الروابط مع الأقسام
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL,
                original_url TEXT,
                platform TEXT NOT NULL,
                category TEXT NOT NULL,
                telegram_type TEXT,
                title TEXT,
                description TEXT,
                members_count INTEGER DEFAULT 0,
                session_id INTEGER,
                collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                check_count INTEGER DEFAULT 0,
                confidence TEXT DEFAULT 'high',
                is_active BOOLEAN DEFAULT 1,
                requires_join BOOLEAN DEFAULT 0,
                is_verified BOOLEAN DEFAULT 0,
                validation_score INTEGER DEFAULT 0,
                metadata TEXT,
                added_by_user INTEGER,
                source TEXT,
                is_channel BOOLEAN DEFAULT 0,
                is_group BOOLEAN DEFAULT 0,
                is_join_request BOOLEAN DEFAULT 0,
                is_supergroup BOOLEAN DEFAULT 0,
                is_subscription BOOLEAN DEFAULT 0,
                is_valid_group BOOLEAN DEFAULT 1,
                last_validated TIMESTAMP,
                collected_from TEXT,
                message_date TIMESTAMP,
                group_name TEXT,
                group_id INTEGER,
                whatsapp_code TEXT,
                is_new BOOLEAN DEFAULT 1,
                is_recent BOOLEAN DEFAULT 1,
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
            'CREATE INDEX IF NOT EXISTS idx_links_category ON links(category)',
            'CREATE INDEX IF NOT EXISTS idx_links_collected_date ON links(collected_date)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_new ON links(is_new)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_recent ON links(is_recent)',
            'CREATE INDEX IF NOT EXISTS idx_links_platform_category ON links(platform, category)',
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
        """Add link to database without duplicates"""
        try:
            url = link_info.get('url', '')
            
            if not url:
                return False, "رابط فارغ", {}
            
            # استخراج معلومات الرابط
            url_info = AdvancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return False, "رابط غير صالح", {}
            
            # الحصول على التجزئة الفريدة
            url_hash = url_info['url_hash']
            
            # التحقق من التكرار
            cursor = await self.conn.execute(
                'SELECT id, category FROM links WHERE url_hash = ?',
                (url_hash,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                # تحديث الرابط الموجود
                await self.conn.execute('''
                    UPDATE links SET 
                    last_checked = CURRENT_TIMESTAMP,
                    check_count = check_count + 1,
                    is_active = ?,
                    category = ?
                    WHERE id = ?
                ''', (
                    link_info.get('is_active', True),
                    link_info.get('category', 'unknown'),
                    existing[0]
                ))
                await self.conn.commit()
                return False, "تم تحديث الرابط الموجود", {'link_id': existing[0], 'category': existing[1]}
            
            # إضافة الرابط الجديد
            details = url_info['details']
            platform = url_info['platform']
            
            # تحديد الفئة بناءً على نوع الرابط
            category = link_info.get('category', 'unknown')
            if category == 'unknown':
                if platform == 'telegram':
                    if details.get('is_bot', False):
                        category = 'bot_links'
                    elif details.get('has_subscribers', False) or details.get('is_subscription', False):
                        category = 'subscriber_groups'
                    elif details.get('is_join_request', False) or details.get('requires_join', False):
                        category = 'join_request_groups'
                    elif details.get('is_message_link', False):
                        category = 'message_links'
                    elif details.get('is_general_group', False) or details.get('is_public', False):
                        category = 'member_groups'
                    else:
                        category = 'general_groups'
                elif platform == 'whatsapp':
                    category = 'whatsapp_groups'
            
            # إضافة الرابط
            cursor = await self.conn.execute('''
                INSERT INTO links 
                (url_hash, url, original_url, platform, category, telegram_type, title, 
                 description, members_count, session_id, confidence, 
                 is_active, requires_join, is_verified, validation_score, metadata, 
                 added_by_user, source, is_channel, is_group, is_join_request, 
                 is_supergroup, is_subscription, is_valid_group, last_validated,
                 collected_from, message_date, group_name, group_id, whatsapp_code,
                 is_new, is_recent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                url_hash,
                url_info['normalized_url'],
                url_info['original_url'],
                platform,
                category,
                details.get('telegram_type', ''),
                link_info.get('title', '')[:500],
                link_info.get('description', '')[:1000],
                link_info.get('members', 0),
                link_info.get('session_id'),
                'high',
                link_info.get('is_active', True),
                details.get('requires_join', False),
                True,
                100,
                json.dumps(link_info.get('metadata', {})),
                link_info.get('added_by_user', 0),
                link_info.get('source', 'collection'),
                details.get('is_channel', False),
                details.get('is_group', False),
                details.get('is_join_request', False),
                details.get('is_supergroup', False),
                details.get('is_subscription', False),
                True,
                datetime.now().isoformat(),
                link_info.get('collected_from', ''),
                link_info.get('message_date', ''),
                link_info.get('group_name', ''),
                link_info.get('group_id', 0),
                details.get('invite_code', ''),
                True,  # is_new
                True   # is_recent
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
            
            logger.info(f"✅ تمت إضافة رابط جديد: {category} - {url[:50]}...")
            
            return True, "تمت إضافة الرابط بنجاح", {
                'link_id': link_id,
                'url_hash': url_hash,
                'category': category
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
            
            logger.info(f"✅ تمت إضافة جلسة جديدة: {session_data.get('display_name', 'غير معروف')}")
            
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
    
    async def get_category_stats(self) -> Dict:
        """Get statistics by category"""
        try:
            cursor = await self.conn.execute('''
                SELECT platform, category, COUNT(*) as count
                FROM links 
                GROUP BY platform, category
                ORDER BY platform, count DESC
            ''')
            
            rows = await cursor.fetchall()
            
            stats = defaultdict(lambda: defaultdict(int))
            for platform, category, count in rows:
                stats[platform][category] = count
            
            return dict(stats)
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على إحصائيات الفئات: {e}")
            return {}
    
    async def get_new_links_count(self) -> int:
        """Get count of new links"""
        try:
            cursor = await self.conn.execute('SELECT COUNT(*) FROM links WHERE is_new = 1')
            result = await cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"خطأ في الحصول على عدد الروابط الجديدة: {e}")
            return 0
    
    async def get_whatsapp_links_count(self) -> int:
        """Get count of WhatsApp links"""
        try:
            cursor = await self.conn.execute('SELECT COUNT(*) FROM links WHERE platform = "whatsapp"')
            result = await cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"خطأ في الحصول على عدد روابط واتساب: {e}")
            return 0
    
    async def get_stats_summary(self) -> Dict:
        """Get database statistics summary"""
        try:
            stats = {}
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links")
            stats['total_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_new = 1")
            stats['new_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE platform = 'whatsapp'")
            stats['whatsapp_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            # إحصائيات الفئات
            category_stats = await self.get_category_stats()
            stats['categories'] = category_stats
            
            # إحصائيات المنصات
            cursor = await self.conn.execute("SELECT platform, COUNT(*) FROM links GROUP BY platform")
            stats['platforms'] = dict(await cursor.fetchall())
            
            # روابط اليوم
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE date(collected_date) = date('now')")
            stats['today_links'] = (await cursor.fetchone())[0]
            
            return stats
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على ملخص الإحصائيات: {e}")
            return {}
    
    async def export_links_by_category(self, platform: str = None, category: str = None, limit: int = 10000) -> List[str]:
        """Export links by category"""
        try:
            query = 'SELECT url FROM links WHERE 1=1'
            params = []
            
            if platform:
                query += ' AND platform = ?'
                params.append(platform)
            
            if category:
                query += ' AND category = ?'
                params.append(category)
            
            query += ' ORDER BY collected_date DESC LIMIT ?'
            params.append(limit)
            
            cursor = await self.conn.execute(query, params)
            rows = await cursor.fetchall()
            
            return [row[0] for row in rows]
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الروابط: {e}")
            return []
    
    async def export_whatsapp_links(self, limit: int = 10000) -> List[str]:
        """Export WhatsApp links"""
        try:
            cursor = await self.conn.execute('''
                SELECT url FROM links 
                WHERE platform = 'whatsapp'
                ORDER BY collected_date DESC 
                LIMIT ?
            ''', (limit,))
            
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
            
        except Exception as e:
            logger.error(f"خطأ في تصدير روابط واتساب: {e}")
            return []
    
    async def mark_links_as_old(self):
        """Mark all links as not new"""
        try:
            await self.conn.execute('UPDATE links SET is_new = 0')
            await self.conn.commit()
            logger.info("✅ تم تحديث جميع الروابط كقديمة")
        except Exception as e:
            logger.error(f"خطأ في تحديث حالة الروابط: {e}")
    
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
# Category Collector - مجمع الفئات
# ======================

class CategoryCollector:
    """Collect links by category"""
    
    @staticmethod
    def categorize_telegram_link(url_info: Dict) -> str:
        """Categorize Telegram link"""
        details = url_info.get('details', {})
        
        if details.get('is_bot', False):
            return 'bot_links'
        elif details.get('has_subscribers', False) or details.get('is_subscription', False):
            return 'subscriber_groups'
        elif details.get('is_join_request', False) or details.get('requires_join', False):
            return 'join_request_groups'
        elif details.get('is_message_link', False):
            return 'message_links'
        elif details.get('is_general_group', False) or details.get('is_public', False):
            return 'member_groups'
        else:
            return 'general_groups'
    
    @staticmethod
    async def extract_links_from_message(message, group_info: Dict) -> List[Dict]:
        """Extract links from message with categorization"""
        links = []
        
        try:
            message_date = message.date if hasattr(message, 'date') else datetime.now()
            
            # جمع روابط تيليجرام
            telegram_links = CategoryCollector._extract_telegram_links(message)
            
            for link in telegram_links:
                url_info = AdvancedLinkProcessor.extract_url_info(link)
                if url_info['is_valid']:
                    category = CategoryCollector.categorize_telegram_link(url_info)
                    
                    link_data = {
                        'url': link,
                        'url_info': url_info,
                        'category': category,
                        'source': 'message',
                        'message_date': message_date.isoformat(),
                        'group_name': group_info.get('title', ''),
                        'group_id': group_info.get('id'),
                        'message_id': message.id if hasattr(message, 'id') else 0,
                        'metadata': {
                            'has_text': bool(message.text),
                            'has_media': bool(message.media)
                        }
                    }
                    
                    # التحقق من تاريخ روابط الرسائل
                    if category == 'message_links':
                        # روابط الرسائل من آخر 5 سنوات فقط
                        if message_date < Config.MIN_MESSAGE_DATE:
                            logger.debug(f"تخطي رابط رسالة قديم: {link}")
                            continue
                    
                    links.append(link_data)
            
            # جمع روابط واتساب
            whatsapp_links = CategoryCollector._extract_whatsapp_links(message)
            
            for link in whatsapp_links:
                url_info = AdvancedLinkProcessor.extract_url_info(link)
                if url_info['is_valid']:
                    # التحقق من تاريخ روابط واتساب (آخر 60 يوم فقط)
                    days_diff = (datetime.now() - message_date).days
                    if days_diff > Config.WHATSAPP_DAYS_BACK:
                        logger.debug(f"تخطي رابط واتساب قديم: {link}")
                        continue
                    
                    link_data = {
                        'url': link,
                        'url_info': url_info,
                        'category': 'whatsapp_groups',
                        'source': 'message',
                        'message_date': message_date.isoformat(),
                        'group_name': group_info.get('title', ''),
                        'group_id': group_info.get('id'),
                        'message_id': message.id if hasattr(message, 'id') else 0,
                        'metadata': {
                            'has_text': bool(message.text),
                            'has_media': bool(message.media)
                        }
                    }
                    
                    links.append(link_data)
            
            return links
            
        except Exception as e:
            logger.debug(f"خطأ في استخراج الروابط من الرسالة: {e}")
            return []
    
    @staticmethod
    def _extract_telegram_links(message) -> List[str]:
        """Extract Telegram links from message"""
        links = []
        
        try:
            # البحث في نص الرسالة
            if hasattr(message, 'text') and message.text:
                text = message.text
                
                # أنماط روابط تيليجرام
                patterns = [
                    r'https?://(?:t\.me|telegram\.me|telegram\.dog)/[^\s<>"\']+',
                    r't\.me/[^\s<>"\']+',
                    r'telegram\.me/[^\s<>"\']+',
                    r'telegram\.dog/[^\s<>"\']+',
                    r'\+[A-Za-z0-9_-]+',  # روابط الانضمام مثل +xxxx
                    r'joinchat/[A-Za-z0-9_-]+'  # روابط joinchat
                ]
                
                for pattern in patterns:
                    found = re.findall(pattern, text, re.IGNORECASE)
                    for link in found:
                        if not link.startswith(('http://', 'https://')):
                            if link.startswith('+'):
                                link = 'https://t.me/' + link
                            elif 'joinchat' in link:
                                link = 'https://t.me/' + link
                            elif 't.me' in pattern or 'telegram' in pattern:
                                link = 'https://' + link
                        
                        links.append(link)
            
            # البحث في الأزرار
            if hasattr(message, 'reply_markup') and message.reply_markup:
                try:
                    for row in message.reply_markup.rows:
                        for button in row.buttons:
                            if hasattr(button, 'url') and button.url:
                                if any(keyword in button.url.lower() for keyword in Config.TELEGRAM_KEYWORDS):
                                    links.append(button.url)
                except:
                    pass
            
            # إزالة التكرارات
            return list(set(links))
            
        except Exception as e:
            logger.debug(f"خطأ في استخراج روابط تيليجرام: {e}")
            return []
    
    @staticmethod
    def _extract_whatsapp_links(message) -> List[str]:
        """Extract WhatsApp links from message"""
        links = []
        
        try:
            # البحث في نص الرسالة
            if hasattr(message, 'text') and message.text:
                text = message.text
                
                # أنماط روابط واتساب
                patterns = [
                    r'https?://(?:chat\.whatsapp\.com|whatsapp\.com)/[^\s<>"\']+',
                    r'chat\.whatsapp\.com/[^\s<>"\']+',
                    r'whatsapp\.com/[^\s<>"\']+'
                ]
                
                for pattern in patterns:
                    found = re.findall(pattern, text, re.IGNORECASE)
                    for link in found:
                        if not link.startswith(('http://', 'https://')):
                            link = 'https://' + link
                        
                        links.append(link)
            
            # البحث في الأزرار
            if hasattr(message, 'reply_markup') and message.reply_markup:
                try:
                    for row in message.reply_markup.rows:
                        for button in row.buttons:
                            if hasattr(button, 'url') and button.url:
                                if any(keyword in button.url.lower() for keyword in Config.WHATSAPP_KEYWORDS):
                                    links.append(button.url)
                except:
                    pass
            
            # إزالة التكرارات
            return list(set(links))
            
        except Exception as e:
            logger.debug(f"خطأ في استخراج روابط واتساب: {e}")
            return []

# ======================
# Advanced Collection Manager - مدير الجمع المتقدم
# ======================

class AdvancedCollectionManager:
    """Advanced collection manager with categories"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        self.collection_complete = False
        self.new_links_detected = False
        
        self.stats = {
            'total_collected': 0,
            'categories': defaultdict(int),
            'platforms': defaultdict(int),
            'sessions_used': 0,
            'groups_processed': 0,
            'messages_scanned': 0,
            'errors': 0,
            'new_links': 0,
            'start_time': None,
            'end_time': None,
            'current_session': None,
            'current_group': None,
            'completion_notified': False,
            'new_links_notified': False
        }
        
        self.collection_task = None
        self.message_links_collected = {}  # {group_id: last_message_link_date}
    
    async def start_collection(self):
        """Start collection process"""
        if self.active:
            return
        
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.collection_complete = False
        self.new_links_detected = False
        
        self.stats['start_time'] = datetime.now().isoformat()
        self.stats['end_time'] = None
        self.stats['completion_notified'] = False
        self.stats['new_links_notified'] = False
        
        logger.info("🚀 بدء عملية الجمع المتقدم مع الفئات...")
        
        # بدء مهمة الجمع في الخلفية
        self.collection_task = asyncio.create_task(self._collection_loop())
    
    async def _collection_loop(self):
        """Main collection loop"""
        while self.active and not self.stop_requested:
            if self.paused:
                await asyncio.sleep(1)
                continue
            
            try:
                # تشغيل دورة الجمع
                new_links_found = await self._run_collection_cycle()
                
                if new_links_found:
                    self.new_links_detected = True
                    self.stats['new_links'] += new_links_found
                    
                    if not self.stats['new_links_notified']:
                        await self._notify_new_links(new_links_found)
                        self.stats['new_links_notified'] = True
                else:
                    # إذا لم يتم العثور على روابط جديدة، فقد اكتمل الجمع
                    if not self.collection_complete:
                        self.collection_complete = True
                        await self._notify_collection_complete()
                
                # تأخير بين الدورات
                delay = Config.REQUEST_DELAYS['max_cycle_delay']
                logger.info(f"⏳ تأخير {delay} ثانية قبل الدورة القادمة")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"خطأ في دورة الجمع: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(10)
        
        self.stats['end_time'] = datetime.now().isoformat()
        self.active = False
        
        if self.collection_complete and not self.stats['completion_notified']:
            await self._notify_collection_complete()
        
        logger.info("⏹️ توقفت عملية الجمع")
    
    async def _run_collection_cycle(self) -> int:
        """Run collection cycle and return number of new links found"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=Config.MAX_CONCURRENT_SESSIONS)
            
            if not sessions:
                logger.warning("لا توجد جلسات نشطة")
                return 0
            
            self.stats['sessions_used'] = len(sessions)
            
            tasks = []
            for session in sessions:
                task = self._process_session_collection(session)
                tasks.append(task)
                await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            total_new_links = 0
            successful_sessions = 0
            
            for result in results:
                if isinstance(result, dict):
                    total_new_links += result.get('new_links', 0)
                    successful_sessions += 1
            
            logger.info(f"✅ اكتملت دورة الجمع: {successful_sessions}/{len(tasks)} جلسات - {total_new_links} رابط جديد")
            
            return total_new_links
            
        except Exception as e:
            logger.error(f"خطأ في دورة الجمع: {e}")
            return 0
    
    async def _process_session_collection(self, session: Dict) -> Dict:
        """Process collection for a single session"""
        try:
            session_string = session.get('session_string', '')
            session_id = session.get('id')
            session_name = session.get('display_name', f'جلسة {session_id}')
            
            if not session_string or session_string == '********':
                logger.error(f"جلسة {session_id} غير متاحة")
                return {'status': 'error', 'new_links': 0}
            
            self.stats['current_session'] = session_name
            
            # فك تشفير الجلسة
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt(session_string)
            
            client = await SessionManager.create_client(decrypted_session)
            if not client:
                return {'status': 'error', 'new_links': 0, 'reason': 'فشل إنشاء العميل'}
            
            logger.info(f"📱 بدء الجمع من جلسة: {session_name}")
            
            # جمع الروابط من جميع المجموعات
            new_links_count = await self._collect_from_all_dialogs(client, session_id, session_name)
            
            await client.disconnect()
            
            # تحديث إحصائيات الجلسة
            db = await EnhancedDatabaseManager.get_instance()
            await db.conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, last_success = CURRENT_TIMESTAMP, total_uses = total_uses + 1, total_links = total_links + ? WHERE id = ?",
                (new_links_count, session_id)
            )
            await db.conn.commit()
            
            logger.info(f"✅ انتهى الجمع من جلسة {session_name}: {new_links_count} رابط جديد")
            
            return {
                'status': 'success', 
                'new_links': new_links_count,
                'session': session_name
            }
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الجلسة: {e}")
            self.stats['errors'] += 1
            return {'status': 'error', 'new_links': 0, 'reason': str(e)}
    
    async def _collect_from_all_dialogs(self, client: TelegramClient, session_id: int, session_name: str) -> int:
        """Collect links from all dialogs"""
        new_links_count = 0
        dialogs_processed = 0
        
        try:
            # الحصول على جميع الدردشات
            all_dialogs = []
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                all_dialogs.append(dialog)
            
            logger.info(f"📊 جلسة {session_name}: تم العثور على {len(all_dialogs)} دردشة")
            
            for dialog in all_dialogs:
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # تخطي الرسائل الخاصة
                    if not hasattr(entity, 'title'):
                        continue
                    
                    dialogs_processed += 1
                    group_title = getattr(entity, 'title', 'غير معروف')
                    group_id = getattr(entity, 'id', 0)
                    
                    self.stats['current_group'] = group_title
                    self.stats['groups_processed'] += 1
                    
                    if dialogs_processed % 10 == 0:
                        logger.info(f"🔍 معالجة المجموعة {dialogs_processed}: {group_title}")
                    
                    # جمع الروابط من المجموعة
                    new_links = await self._collect_from_group(client, entity, session_id, group_title, group_id)
                    new_links_count += new_links
                    
                    # تحديث التقدم
                    if dialogs_processed % 20 == 0:
                        logger.info(f"📈 التقدم: {dialogs_processed}/{len(all_dialogs)} مجموعة - {new_links_count} رابط جديد")
                    
                    # تأخير بين المجموعات
                    await asyncio.sleep(Config.REQUEST_DELAYS['between_groups'])
                    
                except Exception as e:
                    logger.debug(f"خطأ في جمع الروابط من المجموعة: {e}")
                    continue
            
            logger.info(f"✅ جلسة {session_name}: تمت معالجة {dialogs_processed} مجموعة، تم جمع {new_links_count} رابط جديد")
            
        except Exception as e:
            logger.error(f"خطأ في جمع الروابط من جميع المجموعات: {e}")
        
        return new_links_count
    
    async def _collect_from_group(self, client: TelegramClient, entity, session_id: int, group_title: str, group_id: int) -> int:
        """Collect links from a single group"""
        new_links_count = 0
        messages_processed = 0
        
        try:
            group_info = {
                'title': group_title,
                'id': group_id
            }
            
            # جمع الروابط من الرسائل
            async for message in client.iter_messages(entity, limit=Config.MESSAGES_PER_GROUP):
                try:
                    if not self.active or self.stop_requested or self.paused:
                        break
                    
                    messages_processed += 1
                    self.stats['messages_scanned'] += 1
                    
                    # جمع الروابط من الرسالة
                    link_data_list = await CategoryCollector.extract_links_from_message(message, group_info)
                    
                    # حفظ الروابط
                    for link_data in link_data_list:
                        success = await self._save_link(link_data, session_id, group_info)
                        if success:
                            new_links_count += 1
                            category = link_data['category']
                            platform = link_data['url_info']['platform']
                            
                            # تحديث الإحصائيات
                            self.stats['total_collected'] += 1
                            self.stats['categories'][category] += 1
                            self.stats['platforms'][platform] += 1
                    
                    # تأخير بين الرسائل
                    if messages_processed % 20 == 0:
                        await asyncio.sleep(Config.REQUEST_DELAYS['between_messages'])
                    
                except Exception as e:
                    logger.debug(f"خطأ في معالجة رسالة: {e}")
                    continue
            
            logger.debug(f"📨 تمت معالجة {messages_processed} رسالة في مجموعة {group_title}")
            
        except Exception as e:
            logger.debug(f"خطأ في جمع الروابط من المجموعة: {e}")
        
        return new_links_count
    
    async def _save_link(self, link_data: Dict, session_id: int, group_info: Dict) -> bool:
        """Save a link to database"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            link_info = {
                'url': link_data['url'],
                'category': link_data['category'],
                'session_id': session_id,
                'added_by_user': 0,  # يتم التجميع تلقائياً
                'source': link_data['source'],
                'message_date': link_data.get('message_date', ''),
                'group_name': group_info.get('title', ''),
                'group_id': group_info.get('id', 0),
                'metadata': link_data.get('metadata', {}),
                'is_active': True,
                'is_recent': True
            }
            
            success, message, details = await db.add_link(link_info)
            
            return success
            
        except Exception as e:
            logger.error(f"خطأ في حفظ الرابط: {e}")
            return False
    
    async def _notify_collection_complete(self):
        """Notify that collection is complete"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            stats = await db.get_stats_summary()
            
            notification_text = (
                f"✅ **اكتمل تجميع كل الروابط!**\n\n"
                f"**إحصائيات التجميع:**\n"
                f"• إجمالي الروابط: {stats.get('total_links', 0):,}\n"
                f"• الروابط الجديدة: {stats.get('new_links', 0):,}\n"
                f"• روابط واتساب: {stats.get('whatsapp_links', 0):,}\n"
                f"• الجلسات المستخدمة: {self.stats['sessions_used']}\n"
                f"• المجموعات المعالجة: {self.stats['groups_processed']:,}\n"
                f"• الرسائل المفحوصة: {self.stats['messages_scanned']:,}\n\n"
                f"**توزيع المنصات:**\n"
            )
            
            for platform, count in self.stats['platforms'].items():
                notification_text += f"• {platform}: {count:,}\n"
            
            notification_text += "\n**توزيع الفئات (تيليجرام):**\n"
            
            telegram_categories = {
                'bot_links': 'روابط البوتات',
                'subscriber_groups': 'مجموعات المشتركين',
                'join_request_groups': 'مجموعات طلب الانضمام',
                'message_links': 'روابط الرسائل',
                'member_groups': 'مجموعات الأعضاء',
                'general_groups': 'مجموعات عامة'
            }
            
            for category, count in self.stats['categories'].items():
                if category in telegram_categories:
                    notification_text += f"• {telegram_categories[category]}: {count:,}\n"
            
            # إرسال الإشعار (سيتم تنفيذه من قبل البوت)
            self.stats['completion_notified'] = True
            self.completion_notification = notification_text
            
            logger.info("✅ تم إعداد إشعار اكتمال التجميع")
            
        except Exception as e:
            logger.error(f"خطأ في إعداد إشعار الاكتمال: {e}")
    
    async def _notify_new_links(self, new_links_count: int):
        """Notify about new links"""
        try:
            notification_text = (
                f"🆕 **تم العثور على روابط جديدة!**\n\n"
                f"**تم جمع {new_links_count:,} رابط جديد**\n\n"
                f"يمكنك تصدير الروابط الجديدة من قسم:\n"
                f"**📦 الروابط الجديدة**\n\n"
                f"أو تصدير روابط واتساب من قسم:\n"
                f"**📱 تصدير واتساب**\n\n"
                f"سيتم استمرار الجمع للعثور على المزيد من الروابط."
            )
            
            # إرسال الإشعار (سيتم تنفيذه من قبل البوت)
            self.new_links_notification = notification_text
            self.stats['new_links_notified'] = True
            
            logger.info(f"✅ تم إعداد إشعار الروابط الجديدة: {new_links_count} رابط")
            
        except Exception as e:
            logger.error(f"خطأ في إعداد إشعار الروابط الجديدة: {e}")
    
    def get_status(self) -> Dict:
        """Get collection status"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'collection_complete': self.collection_complete,
            'new_links_detected': self.new_links_detected,
            'stats': self.stats.copy(),
            'completion_notification': getattr(self, 'completion_notification', None),
            'new_links_notification': getattr(self, 'new_links_notification', None)
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
# Telegram Bot - بوت تليجرام
# ======================

class TelegramBot:
    """Main Telegram bot"""
    
    def __init__(self):
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        self.collection_manager = AdvancedCollectionManager()
        
        self._setup_handlers()
        
        self.user_states = {}
    
    def _setup_handlers(self):
        """Setup bot handlers"""
        # الأوامر الأساسية
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("categories", self.categories_command))
        
        # إدارة الجلسات
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        self.app.add_handler(CommandHandler("addsession", self.add_session_command))
        
        # الجمع
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        self.app.add_handler(CommandHandler("quick_collect", self.quick_collect_command))
        self.app.add_handler(CommandHandler("stop_collect", self.stop_collect_command))
        
        # التصدير
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("export_new", self.export_new_command))
        self.app.add_handler(CommandHandler("export_whatsapp", self.export_whatsapp_command))
        self.app.add_handler(CommandHandler("export_category", self.export_category_command))
        
        # النسخ الاحتياطي
        self.app.add_handler(CommandHandler("backup", self.backup_command))
        
        # معالجات الاستدعاء والرسائل
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
        
        # إضافة/تحديث المستخدم
        db = await EnhancedDatabaseManager.get_instance()
        await db.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء التجميع", callback_data="start_collect"),
             InlineKeyboardButton("⚡ جمع سريع", callback_data="quick_collect")],
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats"),
             InlineKeyboardButton("📂 الفئات", callback_data="show_categories")],
            [InlineKeyboardButton("📤 تصدير", callback_data="show_export"),
             InlineKeyboardButton("📱 واتساب", callback_data="export_whatsapp")],
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session")]
        ])
        
        welcome_text = (
            f"🤖 **مرحباً {user.first_name}!**\n\n"
            "**بوت تجميع روابط تيليجرام وواتساب المتقدم**\n\n"
            "**المميزات:**\n"
            "✅ تجميع كل الروابط النشطة فقط\n"
            "📂 تنظيم الروابط في أقسام:\n"
            "   • روابط البوتات\n"
            "   • مجموعات المشتركين\n"
            "   • مجموعات طلب الانضمام\n"
            "   • روابط الرسائل\n"
            "   • مجموعات الأعضاء\n"
            "   • مجموعات واتساب\n"
            "🔄 جمع من كل الجلسات دون تكرار\n"
            "📅 تيليجرام: آخر 5 سنوات\n"
            "📱 واتساب: آخر 60 يوم فقط\n"
            "🔔 إشعارات عند اكتمال الجمع وعند وجود روابط جديدة"
        )
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    
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
        
        status_text = (
            f"**📊 حالة النظام - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**\n\n"
            "**حالة الجمع:**\n"
        )
        
        if status['active']:
            if status['paused']:
                status_text += "⏸️ **موقف مؤقتاً**\n"
            elif status['stop_requested']:
                status_text += "🛑 **جاري الإيقاف...**\n"
            else:
                status_text += "🔄 **نشط - تجميع الروابط**\n"
        else:
            status_text += "🛑 **متوقف**\n"
        
        if status['collection_complete']:
            status_text += "✅ **اكتمل التجميع**\n"
        
        if status['new_links_detected']:
            status_text += "🆕 **تم العثور على روابط جديدة**\n"
        
        # معلومات الجمع الحالية
        if status['active'] and not status['paused']:
            status_text += f"\n**💼 الجمع الحالي:**\n"
            if status['stats']['current_session']:
                status_text += f"• الجلسة: {status['stats']['current_session']}\n"
            if status['stats']['current_group']:
                status_text += f"• المجموعة: {status['stats']['current_group']}\n"
        
        status_text += (
            f"\n**إحصائيات الجمع:**\n"
            f"• 📦 المجموع المجمع: {status['stats']['total_collected']:,}\n"
            f"• 🆕 الروابط الجديدة: {status['stats']['new_links']:,}\n"
            f"• 👥 المجموعات المعالجة: {status['stats']['groups_processed']:,}\n"
            f"• 📨 الرسائل المفحوصة: {status['stats']['messages_scanned']:,}\n"
            f"• ⚡ الجلسات المستخدمة: {status['stats']['sessions_used']}\n"
            f"• ❌ أخطاء: {status['stats']['errors']:,}\n"
            f"• 🕒 بدأ في: {status['stats']['start_time'] or 'لم يبدأ'}\n\n"
            f"**إحصائيات قاعدة البيانات:**\n"
            f"• 🔗 إجمالي الروابط: {db_stats.get('total_links', 0):,}\n"
            f"• 📈 روابط اليوم: {db_stats.get('today_links', 0):,}\n"
            f"• 📱 روابط واتساب: {db_stats.get('whatsapp_links', 0):,}\n"
            f"• 💼 الجلسات النشطة: {db_stats.get('active_sessions', 0)}\n"
        )
        
        # إضافة إشعارات إذا وجدت
        if status.get('completion_notification'):
            status_text += "\n" + status['completion_notification']
        
        if status.get('new_links_notification'):
            status_text += "\n" + status['new_links_notification']
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_status"),
             InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("📦 الروابط الجديدة", callback_data="export_new"),
             InlineKeyboardButton("📱 واتساب", callback_data="export_whatsapp")]
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
        category_stats = await db.get_category_stats()
        whatsapp_count = await db.get_whatsapp_links_count()
        
        stats_text = "**📈 إحصائيات النظام**\n\n**إحصائيات عامة:**\n"
        
        stats_text += (
            f"• 🔗 إجمالي الروابط: {db_stats.get('total_links', 0):,}\n"
            f"• 🆕 الروابط الجديدة: {db_stats.get('new_links', 0):,}\n"
            f"• 📱 روابط واتساب: {whatsapp_count:,}\n"
            f"• 📈 روابط اليوم: {db_stats.get('today_links', 0):,}\n"
            f"• 💼 الجلسات النشطة: {db_stats.get('active_sessions', 0)}\n"
            f"• 👥 المستخدمين: {db_stats.get('total_users', 0)}\n"
        )
        
        # إحصائيات المنصات
        if 'platforms' in db_stats:
            stats_text += "\n**توزيع المنصات:**\n"
            for platform, count in db_stats['platforms'].items():
                stats_text += f"• {platform}: {count:,}\n"
        
        # إحصائيات الفئات
        if category_stats:
            stats_text += "\n**توزيع الفئات (تيليجرام):**\n"
            
            telegram_categories = {
                'bot_links': 'روابط البوتات',
                'subscriber_groups': 'مجموعات المشتركين',
                'join_request_groups': 'مجموعات طلب الانضمام',
                'message_links': 'روابط الرسائل',
                'member_groups': 'مجموعات الأعضاء',
                'general_groups': 'مجموعات عامة'
            }
            
            if 'telegram' in category_stats:
                for category, count in category_stats['telegram'].items():
                    if category in telegram_categories:
                        stats_text += f"• {telegram_categories[category]}: {count:,}\n"
        
        # زر تصدير واتساب
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 تصدير روابط واتساب", callback_data="export_whatsapp"),
             InlineKeyboardButton("📦 الروابط الجديدة", callback_data="export_new")]
        ])
        
        await update.message.reply_text(stats_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def categories_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /categories command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        category_stats = await db.get_category_stats()
        whatsapp_count = await db.get_whatsapp_links_count()
        
        categories_text = "**📂 أقسام الروابط**\n\n"
        
        telegram_categories = {
            'bot_links': '🤖 روابط البوتات',
            'subscriber_groups': '📢 مجموعات المشتركين',
            'join_request_groups': '🎯 مجموعات طلب الانضمام',
            'message_links': '📨 روابط الرسائل',
            'member_groups': '👥 مجموعات الأعضاء',
            'general_groups': '🌐 مجموعات عامة'
        }
        
        keyboard_buttons = []
        
        # أزرار تيليجرام
        if 'telegram' in category_stats:
            categories_text += "**تيليجرام:**\n"
            for category, count in category_stats['telegram'].items():
                if category in telegram_categories:
                    categories_text += f"• {telegram_categories[category]}: {count:,}\n"
                    keyboard_buttons.append([
                        InlineKeyboardButton(
                            f"{telegram_categories[category]} ({count:,})", 
                            callback_data=f"export_telegram_{category}"
                        )
                    ])
        
        # زر واتساب
        if whatsapp_count > 0:
            categories_text += f"\n**واتساب:**\n• 📱 مجموعات واتساب: {whatsapp_count:,}\n"
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"📱 مجموعات واتساب ({whatsapp_count:,})", 
                    callback_data="export_whatsapp"
                )
            ])
        
        # زر الروابط الجديدة
        new_links_count = await db.get_new_links_count()
        if new_links_count > 0:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"🆕 الروابط الجديدة ({new_links_count:,})", 
                    callback_data="export_new"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton("📤 تصدير جميع الروابط", callback_data="export_all"),
            InlineKeyboardButton("🔄 تحديث", callback_data="refresh_categories")
        ])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await update.message.reply_text(categories_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sessions command"""
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
        
        sessions_text = f"**👥 الجلسات النشطة ({len(sessions)})**\n\n"
        
        for i, session in enumerate(sessions, 1):
            display_name = session.get('display_name', 'غير معروف')
            username = session.get('username', 'بدون معرف')
            phone = session.get('phone_number', 'بدون رقم')
            last_used = session.get('last_used', 'لم يستخدم')
            uses = session.get('total_uses', 0)
            links_collected = session.get('total_links', 0)
            
            sessions_text += (
                f"**{i}. {display_name}**\n"
                f"• المعرف: @{username}\n"
                f"• الهاتف: {phone}\n"
                f"• الاستخدامات: {uses}\n"
                f"• الروابط المجمعة: {links_collected:,}\n"
                f"• آخر استخدام: {last_used}\n\n"
            )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("🗑️ حذف جلسة", callback_data="delete_session")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_sessions")]
        ])
        
        await update.message.reply_text(sessions_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def add_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addsession command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        self.user_states[user.id] = {'waiting_for_session': True}
        
        add_text = (
            "**➕ إضافة جلسة جديدة**\n\n"
            "**أرسل كود الجلسة الآن:**\n"
            "(يمكنك نسخ الكود كاملاً وإرساله)\n\n"
            "**ملاحظات:**\n"
            "• الجلسة ستخزن مشفرة\n"
            "• يمكنك إضافة حتى 20 جلسة\n"
            "• الجلسة يجب أن تكون نشطة\n"
            "• تستخدم لتجميع الروابط"
        )
        
        await update.message.reply_text(add_text, parse_mode="Markdown")
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /collect command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        status = self.collection_manager.get_status()
        
        if status['active']:
            await update.message.reply_text("⚠️ الجمع يعمل بالفعل")
            return
        
        await update.message.reply_text("🚀 **بدء تجميع كل الروابط...**")
        
        try:
            await self.collection_manager.start_collection()
            
            await asyncio.sleep(2)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status"),
                 InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")]
            ])
            
            await update.message.reply_text(
                f"✅ **بدأ التجميع بنجاح!**\n\n"
                f"**المميزات النشطة:**\n"
                f"✅ تجميع كل الروابط النشطة\n"
                f"📂 تنظيم في 6 أقسام\n"
                f"🔄 جمع من كل الجلسات\n"
                f"📅 تيليجرام: آخر 5 سنوات\n"
                f"📱 واتساب: آخر 60 يوم فقط\n"
                f"🔔 إشعارات عند الاكتمال وعند الروابط الجديدة\n\n"
                f"سيتم إعلامك عند اكتمال الجمع.",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"خطأ في بدء الجمع: {e}")
            await update.message.reply_text(f"❌ خطأ في بدء الجمع: {str(e)[:200]}")
    
    async def quick_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /quick_collect command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        await update.message.reply_text("⚡ **بدء جمع سريع...**")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=1)
            
            if not sessions:
                await update.message.reply_text("❌ لا توجد جلسات نشطة")
                return
            
            session = sessions[0]
            session_string = session.get('session_string', '')
            session_name = session.get('display_name', 'غير معروف')
            
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
            
            # جمع من 10 مجموعات فقط
            new_links_count = 0
            groups_processed = 0
            
            async for dialog in client.iter_dialogs(limit=15):
                try:
                    entity = dialog.entity
                    
                    if not hasattr(entity, 'title'):
                        continue
                    
                    groups_processed += 1
                    group_title = getattr(entity, 'title', 'غير معروف')
                    
                    # جمع من 20 رسالة فقط من كل مجموعة
                    group_info = {'title': group_title, 'id': getattr(entity, 'id', 0)}
                    messages_collected = 0
                    
                    async for message in client.iter_messages(entity, limit=20):
                        try:
                            link_data_list = await CategoryCollector.extract_links_from_message(message, group_info)
                            
                            for link_data in link_data_list:
                                link_info = {
                                    'url': link_data['url'],
                                    'category': link_data['category'],
                                    'session_id': session['id'],
                                    'added_by_user': user.id,
                                    'source': link_data['source'],
                                    'message_date': link_data.get('message_date', ''),
                                    'group_name': group_info.get('title', ''),
                                    'group_id': group_info.get('id', 0),
                                    'metadata': link_data.get('metadata', {}),
                                    'is_active': True,
                                    'is_recent': True
                                }
                                
                                success, message_text, details = await db.add_link(link_info)
                                if success:
                                    new_links_count += 1
                            
                            messages_collected += 1
                            
                        except Exception as e:
                            logger.debug(f"خطأ في معالجة رسالة: {e}")
                            continue
                    
                    if groups_processed >= 10:
                        break
                    
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.debug(f"خطأ في الجمع السريع من المجموعة: {e}")
                    continue
            
            await client.disconnect()
            
            # تحديث إحصائيات الجلسة
            await db.conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, last_success = CURRENT_TIMESTAMP, total_uses = total_uses + 1, total_links = total_links + ? WHERE id = ?",
                (new_links_count, session['id'])
            )
            await db.conn.commit()
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء الجمع الكامل", callback_data="start_collect"),
                 InlineKeyboardButton("📤 تصدير", callback_data="export_new")]
            ])
            
            await update.message.reply_text(
                f"✅ **اكتمل الجمع السريع!**\n\n"
                f"**الإحصائيات:**\n"
                f"• المجموعات المعالجة: {groups_processed}\n"
                f"• الروابط المجمعة: {new_links_count}\n"
                f"• الجلسة: {session_name}\n\n"
                f"يمكنك الآن:\n"
                f"• بدء الجمع الكامل من جميع المجموعات\n"
                f"• تصدير الروابط الجديدة",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"خطأ في الجمع السريع: {e}")
            await update.message.reply_text(f"❌ خطأ في الجمع السريع: {str(e)[:200]}")
    
    async def stop_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop_collect command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        if not self.collection_manager.active:
            await update.message.reply_text("⚠️ الجمع غير نشط")
            return
        
        await self.collection_manager.stop()
        
        status = self.collection_manager.get_status()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 إعادة البدء", callback_data="start_collect"),
             InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")]
        ])
        
        await update.message.reply_text(
            f"⏹️ **تم إيقاف الجمع**\n\n"
            f"**الإحصائيات النهائية:**\n"
            f"• إجمالي الروابط: {status['stats']['total_collected']:,}\n"
            f"• الروابط الجديدة: {status['stats']['new_links']:,}\n"
            f"• مجموعات معالجة: {status['stats']['groups_processed']:,}\n"
            f"• رسائل مفحوصة: {status['stats']['messages_scanned']:,}\n"
            f"• جلسات مستخدمة: {status['stats']['sessions_used']}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
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
        new_links_count = await db.get_new_links_count()
        whatsapp_count = await db.get_whatsapp_links_count()
        
        if total_links == 0:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect"),
                 InlineKeyboardButton("⚡ جمع سريع", callback_data="quick_collect")]
            ])
            await update.message.reply_text(
                "❌ **لا توجد روابط للتصدير**\n\n"
                "ابدأ في جمع الروابط أولاً.",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return
        
        keyboard_buttons = []
        
        # زر الروابط الجديدة
        if new_links_count > 0:
            keyboard_buttons.append([
                InlineKeyboardButton(f"🆕 الروابط الجديدة ({new_links_count:,})", callback_data="export_new")
            ])
        
        # زر واتساب
        if whatsapp_count > 0:
            keyboard_buttons.append([
                InlineKeyboardButton(f"📱 روابط واتساب ({whatsapp_count:,})", callback_data="export_whatsapp")
            ])
        
        # أزرار الفئات
        keyboard_buttons.append([
            InlineKeyboardButton("📂 جميع الفئات", callback_data="show_categories")
        ])
        
        keyboard_buttons.append([
            InlineKeyboardButton("📦 جميع الروابط", callback_data="export_all"),
            InlineKeyboardButton("📊 CSV كامل", callback_data="export_csv")
        ])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        export_text = (
            f"**📤 تصدير الروابط**\n\n"
            f"إجمالي الروابط: **{total_links:,}**\n"
            f"الروابط الجديدة: **{new_links_count:,}**\n"
            f"روابط واتساب: **{whatsapp_count:,}**\n\n"
            f"اختر نوع التصدير:"
        )
        
        await update.message.reply_text(export_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def export_new_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export_new command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        await update.message.reply_text("⏳ جاري تحضير الروابط الجديدة...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            cursor = await db.conn.execute('''
                SELECT url, platform, category, collected_date 
                FROM links 
                WHERE is_new = 1
                ORDER BY collected_date DESC 
                LIMIT ?
            ''', (Config.MAX_EXPORT_LINKS,))
            
            rows = await cursor.fetchall()
            
            if not rows:
                await update.message.reply_text("❌ لا توجد روابط جديدة للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"new_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for row in rows:
                    url, platform, category, date = row
                    f.write(f"{url}\n")
            
            # حفظ في ملف CSV
            csv_filename = f"new_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            csv_filepath = os.path.join("exports", csv_filename)
            
            with open(csv_filepath, 'w', encoding='utf-8') as f:
                f.write("URL,Platform,Category,Date\n")
                for row in rows:
                    url, platform, category, date = row
                    f.write(f'"{url}","{platform}","{category}","{date}"\n')
            
            # إرسال الملفات
            with open(filepath, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"🆕 الروابط الجديدة\nعدد الروابط: {len(rows):,}"
                )
            
            with open(csv_filepath, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=csv_filename,
                    caption="📊 ملف CSV مع التفاصيل"
                )
            
            # تحديث حالة الروابط كقديمة
            await db.mark_links_as_old()
            
            # حذف الملفات المحلية
            try:
                os.remove(filepath)
                os.remove(csv_filepath)
            except:
                pass
            
            await update.message.reply_text(f"✅ تم تصدير {len(rows):,} رابط جديد")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الروابط الجديدة: {e}")
            await update.message.reply_text(f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def export_whatsapp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export_whatsapp command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        await update.message.reply_text("⏳ جاري تحضير روابط واتساب...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_whatsapp_links(Config.MAX_EXPORT_LINKS)
            
            if not links:
                await update.message.reply_text("❌ لا توجد روابط واتساب للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"whatsapp_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # حفظ في ملف CSV
            csv_filename = f"whatsapp_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            csv_filepath = os.path.join("exports", csv_filename)
            
            # الحصول على معلومات إضافية لملف CSV
            cursor = await db.conn.execute('''
                SELECT url, collected_date, group_name, message_date 
                FROM links 
                WHERE platform = 'whatsapp'
                ORDER BY collected_date DESC 
                LIMIT ?
            ''', (Config.MAX_EXPORT_LINKS,))
            
            rows = await cursor.fetchall()
            
            with open(csv_filepath, 'w', encoding='utf-8') as f:
                f.write("URL,Date,Group,MessageDate\n")
                for row in rows:
                    url, date, group, message_date = row
                    f.write(f'"{url}","{date}","{group or ""}","{message_date or ""}"\n')
            
            # إرسال الملفات
            with open(filepath, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📱 روابط واتساب\nعدد الروابط: {len(links):,}\n\n"
                           f"**ملاحظة:**\n"
                           f"• تم جمع روابط واتساب من آخر {Config.WHATSAPP_DAYS_BACK} يوم فقط\n"
                           f"• الروابط محفوظة كما هي دون تغيير"
                )
            
            with open(csv_filepath, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=csv_filename,
                    caption="📊 ملف CSV مع التفاصيل"
                )
            
            # حذف الملفات المحلية
            try:
                os.remove(filepath)
                os.remove(csv_filepath)
            except:
                pass
            
            await update.message.reply_text(f"✅ تم تصدير {len(links):,} رابط واتساب")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير روابط واتساب: {e}")
            await update.message.reply_text(f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def export_category_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export_category command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        if not context.args:
            await update.message.reply_text("❌ يرجى تحديد الفئة\nمثال: /export_category bot_links")
            return
        
        category = context.args[0]
        
        await update.message.reply_text(f"⏳ جاري تحضير روابط الفئة: {category}...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links_by_category(category=category, limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await update.message.reply_text(f"❌ لا توجد روابط في الفئة: {category}")
                return
            
            # تسمية الفئات
            category_names = {
                'bot_links': 'روابط البوتات',
                'subscriber_groups': 'مجموعات المشتركين',
                'join_request_groups': 'مجموعات طلب الانضمام',
                'message_links': 'روابط الرسائل',
                'member_groups': 'مجموعات الأعضاء',
                'general_groups': 'مجموعات عامة',
                'whatsapp_groups': 'مجموعات واتساب'
            }
            
            category_name = category_names.get(category, category)
            
            # حفظ في ملف نصي
            filename = f"{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"{category_name}\nعدد الروابط: {len(links):,}"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await update.message.reply_text(f"✅ تم تصدير {len(links):,} رابط من فئة {category_name}")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الفئة: {e}")
            await update.message.reply_text(f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /backup command"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        await update.message.reply_text("⏳ جاري إنشاء نسخة احتياطية...")
        
        try:
            os.makedirs("backups", exist_ok=True)
            
            if not os.path.exists(Config.DB_PATH):
                await update.message.reply_text("❌ قاعدة البيانات غير موجودة")
                return
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"backup_{timestamp}.db"
            backup_path = os.path.join("backups", backup_filename)
            
            shutil.copy2(Config.DB_PATH, backup_path)
            
            # إرسال الملف
            with open(backup_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=backup_filename,
                    caption=f"💾 النسخة الاحتياطية\nالتاريخ: {timestamp}"
                )
            
            await update.message.reply_text(f"✅ تم إنشاء نسخة احتياطية بنجاح!\nالحجم: {os.path.getsize(backup_path) / 1024 / 1024:.2f} MB")
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء نسخة احتياطية: {e}")
            await update.message.reply_text(f"❌ فشل في إنشاء نسخة احتياطية: {str(e)[:100]}")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await self._edit_message_safe(query, "❌ غير مصرح لك بالوصول")
                return
        
        data = query.data
        
        try:
            if data == "refresh_status":
                await self._handle_refresh_status(query)
            elif data == "start_collect":
                await self._handle_start_collect_callback(query)
            elif data == "quick_collect":
                await self._handle_quick_collect_callback(query)
            elif data == "stop_collect":
                await self._handle_stop_collect_callback(query)
            elif data == "collect_status":
                await self._handle_collect_status_callback(query)
            elif data == "show_stats":
                await self._handle_show_stats_callback(query)
            elif data == "show_categories":
                await self._handle_show_categories_callback(query)
            elif data == "show_export":
                await self._handle_show_export_callback(query)
            elif data == "add_session":
                await self._handle_add_session_callback(query)
            elif data == "refresh_sessions":
                await self._handle_refresh_sessions_callback(query)
            elif data == "delete_session":
                await self._handle_delete_session_callback(query)
            elif data == "refresh_categories":
                await self._handle_refresh_categories_callback(query)
            elif data == "export_new":
                await self._handle_export_new_callback(query)
            elif data == "export_whatsapp":
                await self._handle_export_whatsapp_callback(query)
            elif data == "export_all":
                await self._handle_export_all_callback(query)
            elif data == "export_csv":
                await self._handle_export_csv_callback(query)
            elif data.startswith("export_telegram_"):
                await self._handle_export_telegram_category_callback(query, data)
            elif data.startswith("delete_session_"):
                await self._handle_delete_session_confirm_callback(query, data)
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
                pass
            elif "Can't parse entities" in str(e):
                try:
                    text_plain = re.sub(r'[\*_`\[\]()]', '', text)
                    await query.edit_message_text(
                        text=text_plain,
                        reply_markup=reply_markup
                    )
                except Exception:
                    await query.message.reply_text(
                        text=text_plain,
                        reply_markup=reply_markup
                    )
            else:
                logger.error(f"خطأ في تعديل الرسالة: {e}")
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
    
    async def _handle_refresh_status(self, query):
        """Handle refresh status callback"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.status_command(mock_update, None)
    
    async def _handle_start_collect_callback(self, query):
        """Handle start collect callback"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.collect_command(mock_update, None)
    
    async def _handle_quick_collect_callback(self, query):
        """Handle quick collect callback"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.quick_collect_command(mock_update, None)
    
    async def _handle_stop_collect_callback(self, query):
        """Handle stop collect callback"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.stop_collect_command(mock_update, None)
    
    async def _handle_collect_status_callback(self, query):
        """Handle collect status callback"""
        status = self.collection_manager.get_status()
        
        status_text = (
            f"**📊 حالة الجمع**\n\n"
            f"**الحالة:** {'🔄 نشط' if status['active'] else '🛑 متوقف'}\n"
            f"**الإيقاف المؤقت:** {'⏸️ نعم' if status['paused'] else '▶️ لا'}\n"
            f"**اكتمال التجميع:** {'✅ نعم' if status['collection_complete'] else '❌ لا'}\n"
            f"**روابط جديدة:** {'🆕 نعم' if status['new_links_detected'] else '❌ لا'}\n\n"
            f"**الإحصائيات:**\n"
            f"• الروابط المجمعة: {status['stats']['total_collected']:,}\n"
            f"• الروابط الجديدة: {status['stats']['new_links']:,}\n"
            f"• المجموعات المعالجة: {status['stats']['groups_processed']:,}\n"
            f"• الرسائل المفحوصة: {status['stats']['messages_scanned']:,}\n"
            f"• الجلسات المستخدمة: {status['stats']['sessions_used']}\n"
            f"• الأخطاء: {status['stats']['errors']:,}\n"
            f"• بدأ في: {status['stats']['start_time'] or 'لم يبدأ'}"
        )
        
        await self._edit_message_safe(query, status_text)
    
    async def _handle_show_stats_callback(self, query):
        """Handle show stats callback"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.stats_command(mock_update, None)
    
    async def _handle_show_categories_callback(self, query):
        """Handle show categories callback"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.categories_command(mock_update, None)
    
    async def _handle_show_export_callback(self, query):
        """Handle show export callback"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.export_command(mock_update, None)
    
    async def _handle_add_session_callback(self, query):
        """Handle add session callback"""
        from_user = query.from_user
        self.user_states[from_user.id] = {'waiting_for_session': True}
        
        add_text = (
            f"**➕ إضافة جلسة جديدة**\n\n"
            f"**أرسل كود الجلسة الآن:**\n"
            f"(يمكنك نسخ الكود كاملاً وإرساله)\n\n"
            f"**ملاحظات:**\n"
            f"• الجلسة ستخزن مشفرة\n"
            f"• يمكنك إضافة حتى 20 جلسة\n"
            f"• الجلسة يجب أن تكون نشطة\n"
            f"• تستخدم لتجميع الروابط"
        )
        
        await self._edit_message_safe(query, add_text)
    
    async def _handle_refresh_sessions_callback(self, query):
        """Handle refresh sessions callback"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.sessions_command(mock_update, None)
    
    async def _handle_delete_session_callback(self, query):
        """Handle delete session callback"""
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=10)
        
        if not sessions:
            await self._edit_message_safe(query, "❌ لا توجد جلسات")
            return
        
        keyboard_buttons = []
        for session in sessions:
            name = session.get('display_name', f"جلسة {session['id']}")
            callback_data = f"delete_session_{session['id']}"
            keyboard_buttons.append([InlineKeyboardButton(f"🗑️ {name}", callback_data=callback_data)])
        
        keyboard_buttons.append([InlineKeyboardButton("⬅️ رجوع", callback_data="refresh_sessions")])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await self._edit_message_safe(
            query,
            "**🗑️ حذف الجلسات**\n\n"
            "اختر الجلسة التي تريد حذفها:",
            reply_markup=keyboard
        )
    
    async def _handle_delete_session_confirm_callback(self, query, data):
        """Handle delete session confirmation callback"""
        try:
            session_id = int(data.split('_')[2])
            
            db = await EnhancedDatabaseManager.get_instance()
            
            cursor = await db.conn.execute(
                'SELECT display_name FROM sessions WHERE id = ?',
                (session_id,)
            )
            session_info = await cursor.fetchone()
            
            if not session_info:
                await self._edit_message_safe(query, "❌ الجلسة غير موجودة")
                return
            
            await db.conn.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
            await db.conn.commit()
            
            await self._edit_message_safe(
                query,
                f"✅ **تم حذف الجلسة بنجاح**\n\n"
                f"• الجلسة: {session_info[0]}\n"
                f"• رقم الجلسة: {session_id}"
            )
            
        except Exception as e:
            logger.error(f"خطأ في حذف الجلسة: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في حذف الجلسة: {str(e)[:100]}")
    
    async def _handle_refresh_categories_callback(self, query):
        """Handle refresh categories callback"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.categories_command(mock_update, None)
    
    async def _handle_export_new_callback(self, query):
        """Handle export new links callback"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.export_new_command(mock_update, None)
    
    async def _handle_export_whatsapp_callback(self, query):
        """Handle export WhatsApp callback"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.export_whatsapp_command(mock_update, None)
    
    async def _handle_export_all_callback(self, query):
        """Handle export all links callback"""
        await self._edit_message_safe(query, "⏳ جاري تحضير جميع الروابط...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links_by_category(limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد روابط للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"all_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
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
                    caption=f"📦 جميع الروابط\nعدد الروابط: {len(links):,}"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await self._edit_message_safe(query, f"✅ تم تصدير {len(links):,} رابط")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير جميع الروابط: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_csv_callback(self, query):
        """Handle export CSV callback"""
        await self._edit_message_safe(query, "⏳ جاري تحضير ملف CSV...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            cursor = await db.conn.execute('''
                SELECT url, platform, category, members_count, collected_date, group_name
                FROM links 
                LIMIT ?
            ''', (Config.MAX_EXPORT_LINKS,))
            
            rows = await cursor.fetchall()
            
            if not rows:
                await self._edit_message_safe(query, "❌ لا توجد روابط للتصدير")
                return
            
            # حفظ في ملف CSV
            filename = f"links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("URL,Platform,Category,Members,Date,Group\n")
                for row in rows:
                    url, platform, category, members, date, group = row
                    f.write(f'"{url}","{platform}","{category}",{members},"{date}","{group or ""}"\n')
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📊 ملف CSV\nعدد السجلات: {len(rows):,}"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await self._edit_message_safe(query, f"✅ تم تصدير {len(rows):,} سجل كـ CSV")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير CSV: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_telegram_category_callback(self, query, data):
        """Handle export Telegram category callback"""
        category = data.replace("export_telegram_", "")
        
        await self._edit_message_safe(query, f"⏳ جاري تحضير روابط الفئة: {category}...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links_by_category(platform='telegram', category=category, limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await self._edit_message_safe(query, f"❌ لا توجد روابط في الفئة: {category}")
                return
            
            # تسمية الفئات
            category_names = {
                'bot_links': 'روابط البوتات',
                'subscriber_groups': 'مجموعات المشتركين',
                'join_request_groups': 'مجموعات طلب الانضمام',
                'message_links': 'روابط الرسائل',
                'member_groups': 'مجموعات الأعضاء',
                'general_groups': 'مجموعات عامة'
            }
            
            category_name = category_names.get(category, category)
            
            # حفظ في ملف نصي
            filename = f"telegram_{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
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
                    caption=f"{category_name}\nعدد الروابط: {len(links):,}"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await self._edit_message_safe(query, f"✅ تم تصدير {len(links):,} رابط من فئة {category_name}")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الفئة: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
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
                "/status - حالة النظام\n"
                "/stats - الإحصائيات\n"
                "/categories - أقسام الروابط\n"
                "/collect - بدء تجميع الروابط\n"
                "/quick_collect - جمع سريع\n"
                "/stop_collect - إيقاف الجمع\n"
                "/export - تصدير الروابط\n"
                "/export_new - تصدير الروابط الجديدة\n"
                "/export_whatsapp - تصدير روابط واتساب\n"
                "/sessions - إدارة الجلسات\n"
                "/backup - نسخة احتياطية\n"
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
                'purpose': 'telegram_whatsapp_collection'
            }
        }
        
        db = await EnhancedDatabaseManager.get_instance()
        success, message, details = await db.add_session(session_data)
        
        if success:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء التجميع", callback_data="start_collect"),
                 InlineKeyboardButton("⚡ جمع سريع", callback_data="quick_collect")]
            ])
            
            await update.message.reply_text(
                f"✅ **تمت إضافة الجلسة بنجاح!**\n\n"
                f"**معلومات المستخدم:**\n"
                f"• الاسم: {session_data['display_name']}\n"
                f"• المعرف: @{session_data['username']}\n"
                f"• الهاتف: {session_data['phone_number']}\n\n"
                f"**الجلسة:**\n"
                f"• مشفرة ومخزنة بأمان\n"
                f"• جاهزة لتجميع الروابط\n"
                f"• رقم الجلسة: {details.get('session_id')}\n\n"
                f"**ملاحظة:**\n"
                f"هذه الجلسة ستستخدم لتجميع الروابط:\n"
                f"• تيليجرام: آخر 5 سنوات\n"
                f"• واتساب: آخر 60 يوم فقط\n"
                f"• تنظيم في 6 أقسام مختلفة",
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
            
            if isinstance(error, Conflict):
                logger.error("⚠️ تم اكتشاف نسخة أخرى من البوت تعمل!")
                
                await asyncio.sleep(2)
                
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
                    "لقد واجهنا مشكلة فنية. حاول مرة أخرى بعد قليل."
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
# Main Function - الوظيفة الرئيسية
# ======================

async def main():
    """Main function"""
    try:
        logger.info(f"🚀 تشغيل بوت تجميع الروابط المتقدم")
        logger.info(f"📅 تيليجرام: آخر 5 سنوات | واتساب: آخر 60 يوم")
        logger.info(f"📂 6 أقسام للروابط | 🔔 إشعارات عند الاكتمال")
        logger.info(f"📱 قسم خاص لتصدير روابط واتساب")
        
        # التحقق من المتغيرات البيئية
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
        
        # تهيئة قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        
        # إنشاء البوت
        bot = TelegramBot()
        
        logger.info("🤖 بدء تشغيل بوت تجميع الروابط...")
        logger.info("✅ تجميع تيليجرام: آخر 5 سنوات")
        logger.info("✅ تجميع واتساب: آخر 60 يوم فقط")
        logger.info("✅ 6 أقسام: بوتات، مشتركين، طلب انضمام، رسائل، أعضاء، واتساب")
        logger.info("✅ قسم تصدير واتساب خاص")
        logger.info("✅ جمع من كل الجلسات دون تكرار")
        logger.info("✅ إشعارات عند اكتمال الجمع وعند الروابط الجديدة")
        
        try:
            # تشغيل البوت
            await bot.app.initialize()
            await bot.app.start()
            await bot.app.updater.start_polling()
            
            logger.info("✅ البوت يعمل بنجاح!")
            logger.info("📋 الأوامر: /start, /collect, /stop_collect, /export, /export_new, /export_whatsapp, /categories, /stats")
            
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
