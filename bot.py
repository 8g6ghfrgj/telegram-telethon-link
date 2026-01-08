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

# ======================
# REMOVED FastAPI imports for Render compatibility
# ======================

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
    MAX_CONCURRENT_SESSIONS = 10
    REQUEST_DELAYS = {
        'normal': 0.5,
        'join_request': 3.0,
        'search': 1.5,
        'flood_wait': 5.0,
        'between_sessions': 1.0,
        'between_tasks': 0.2,
        'min_cycle_delay': 5.0,
        'max_cycle_delay': 15.0,
        'validation_delay': 1.0,
        'between_groups': 0.5,
        'between_messages': 0.1
    }
    
    # Collection limits - حدود الجمع
    MAX_DIALOGS_PER_SESSION = 200  # زيادة كبيرة لجمع كل المجموعات
    MAX_MESSAGES_PER_SEARCH = 100   # زيادة عدد الرسائل للبحث
    MAX_SEARCH_TERMS = 8
    MAX_LINKS_PER_CYCLE = 1000     # زيادة عدد الروابط
    MAX_BATCH_SIZE = 100
    
    # Database - قاعدة البيانات
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10
    DB_POOL_SIZE = 5
    
    # WhatsApp collection - جمع واتساب
    WHATSAPP_DAYS_BACK = 60
    TELEGRAM_YEARS_BACK = 5  # جمع روابط تيليجرام من آخر 5 سنوات
    
    # Link verification - التحقق من الروابط
    MIN_GROUP_MEMBERS = 1  # الحد الأدنى للأعضاء
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
    TELEGRAM_NO_TIME_LIMIT = False  # الآن لدينا قيود زمنية
    JOIN_REQUEST_CHECK_DELAY = 30
    ENABLE_ADVANCED_VALIDATION = True
    
    # Collection settings - إعدادات الجمع الحقيقي
    COLLECT_ONLY_GROUPS = True  # جمع المجموعات فقط
    MIN_MEMBERS_FOR_GROUP = 1   # الحد الأدنى للأعضاء
    COLLECT_ACTIVE_LINKS_ONLY = True  # ✅ جمع الروابط النشطة فقط
    ENABLE_DEEP_COLLECTION = True
    MAX_DEEP_MESSAGES = 150     # زيادة عدد الرسائل في الجمع العميق
    COLLECT_ONLY_TELEGRAM_WHATSAPP = True
    COLLECT_FROM_ALL_GROUPS = True  # جمع من جميع المجموعات
    ENABLE_MASS_COLLECTION = True   # تمكين الجمع الجماعي
    MESSAGES_PER_GROUP = 100        # عدد الرسائل لكل مجموعة
    
    # ✅ الإعدادات المحدثة حسب طلبك:
    # 1. جمع الروابط النشطة فقط (التليجرام دون تعديل، الواتساب دون تعديل)
    PRESERVE_ORIGINAL_LINKS = True  # الحفاظ على الروابط كما هي
    COLLECT_ONLY_ACTIVE = True  # جمع الروابط النشطة فقط
    CHECK_LINK_EXPIRY = True  # التحقق من انتهاء الروابط
    
    # 2. جمع روابط المجموعات ذات الأعضاء فقط
    COLLECT_MEMBER_GROUPS_ONLY = True
    
    # 3. تجاهل الروابط المحددة
    FILTER_BOT_LINKS = True  # تجاهل روابط البوتات
    FILTER_SUBSCRIPTION_GROUPS = True  # تجاهل المجموعات التي تحتوي على "مشتركين"
    FILTER_CHANNELS = True  # تجاهل القنوات
    FILTER_ME_LINKS = True  # تجاهل t.me/me
    FILTER_EXPIRED_LINKS = True  # تجاهل الروابط المنتهية
    
    # 4. منع التكرار
    PREVENT_DUPLICATES = True  # منع تجميع نفس الرابط مرتين
    
    # 5. تجميع رسالة واحدة فقط من كل مجموعة
    COLLECT_ONE_MESSAGE_PER_GROUP = True
    
    # Keywords - الكلمات المفتاحية
    TELEGRAM_KEYWORDS = ['t.me', 'telegram.me', 'telegram.dog', 'joinchat', 'join', 'addlist']
    WHATSAPP_KEYWORDS = ['chat.whatsapp.com', 'whatsapp.com']
    ALL_KEYWORDS = TELEGRAM_KEYWORDS + WHATSAPP_KEYWORDS
    
    # Target links - الروابط المستهدفة
    TARGET_MEMBER_GROUPS = True  # جمع المجموعات التي تحتوي على أعضاء فقط

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
    """معالجة الروابط مع الحفاظ على الشكل الأصلي"""
    
    @staticmethod
    def preserve_original_url(url: str) -> str:
        """الحفاظ على الرابط الأصلي كما هو"""
        if not url or not isinstance(url, str):
            return ""
        
        # تنظيف بسيط فقط
        url = url.strip()
        
        # ✅ الحفاظ على جميع أشكال روابط تيليجرام كما هي
        telegram_patterns = [
            r't\.me/[^\s<>"\']+',
            r'telegram\.me/[^\s<>"\']+',
            r'telegram\.dog/[^\s<>"\']+',
            r'https?://t\.me/[^\s<>"\']+',
            r'https?://telegram\.me/[^\s<>"\']+',
            r'https?://telegram\.dog/[^\s<>"\']+',
            r'\+\w+',  # روابط +joinchat
            r'addlist/\w+'  # روابط addlist
        ]
        
        # ✅ الحفاظ على جميع أشكال روابط واتساب كما هي
        whatsapp_patterns = [
            r'chat\.whatsapp\.com/[^\s<>"\']+',
            r'whatsapp\.com/[^\s<>"\']+',
            r'https?://chat\.whatsapp\.com/[^\s<>"\']+',
            r'https?://whatsapp\.com/[^\s<>"\']+'
        ]
        
        # البحث عن الروابط في النص
        all_patterns = telegram_patterns + whatsapp_patterns
        extracted_urls = []
        
        for pattern in all_patterns:
            matches = re.findall(pattern, url, re.IGNORECASE)
            extracted_urls.extend(matches)
        
        if extracted_urls:
            # نعيد أول رابط تم العثور عليه
            link = extracted_urls[0]
            
            # ✅ إضافة https:// إذا كان مفقوداً لروابط تيليجرام
            if any(domain in link.lower() for domain in ['t.me', 'telegram.me', 'telegram.dog']):
                if not link.startswith(('http://', 'https://')):
                    link = 'https://' + link
            # ✅ إضافة https:// إذا كان مفقوداً لروابط واتساب
            elif any(domain in link.lower() for domain in ['chat.whatsapp.com', 'whatsapp.com']):
                if not link.startswith(('http://', 'https://')):
                    link = 'https://' + link
            # ✅ معالجة خاصة لروابط joinchat بدون t.me
            elif link.startswith('+'):
                link = 'https://t.me/' + link
            
            return link
        
        return ""
    
    @staticmethod
    def extract_url_info(url: str) -> Dict:
        """استخراج معلومات الرابط"""
        preserved_url = EnhancedLinkProcessor.preserve_original_url(url)
        
        result = {
            'original_url': url,
            'preserved_url': preserved_url,
            'platform': 'unknown',
            'url_hash': hashlib.md5(preserved_url.encode()).hexdigest() if preserved_url else '',
            'is_valid': False,
            'link_type': 'unknown',
            'is_active': True,
            'is_expired': False,
            'requires_check': True,
            'details': {}
        }
        
        if not preserved_url:
            return result
        
        try:
            # ✅ تحديد المنصة
            if any(keyword in preserved_url.lower() for keyword in Config.TELEGRAM_KEYWORDS):
                result['platform'] = 'telegram'
                result['details'] = EnhancedLinkProcessor._analyze_telegram_link(preserved_url)
            elif any(keyword in preserved_url.lower() for keyword in Config.WHATSAPP_KEYWORDS):
                result['platform'] = 'whatsapp'
                result['details'] = EnhancedLinkProcessor._analyze_whatsapp_link(preserved_url)
            
            result['is_valid'] = bool(result['details'].get('is_valid', False))
            
        except Exception as e:
            logger.debug(f"خطأ في استخراج معلومات الرابط: {e}")
        
        return result
    
    @staticmethod
    def _analyze_telegram_link(url: str) -> Dict:
        """تحليل رابط تيليجرام"""
        result = {
            'is_valid': False,
            'link_type': 'unknown',
            'is_group': False,
            'is_channel': False,
            'is_bot': False,
            'is_private': False,
            'is_public': False,
            'is_join_link': False,
            'is_me_link': False,
            'is_addlist': False,
            'has_members': False,
            'is_subscription': False,
            'is_message_link': False,
            'is_active': True,
            'is_expired': False,
            'should_collect': False,
            'reason': ''
        }
        
        # ✅ التحقق من t.me/me
        if 't.me/me' in url.lower() or 'telegram.me/me' in url.lower():
            result['is_me_link'] = True
            result['reason'] = 'رابط t.me/me'
            return result
        
        # ✅ التحقق من البوتات
        if '/bot' in url.lower() or 't.me/bot' in url.lower():
            result['is_bot'] = True
            result['reason'] = 'رابط بوت'
            return result
        
        # ✅ تحليل أنواع الروابط
        url_lower = url.lower()
        
        # روابط المجموعات العامة
        if re.search(r't\.me/[a-zA-Z0-9_]+$', url_lower) or re.search(r'telegram\.me/[a-zA-Z0-9_]+$', url_lower):
            result['is_valid'] = True
            result['is_group'] = True
            result['is_public'] = True
            result['has_members'] = True  # نفترض أن المجموعات العامة لديها أعضاء
            result['should_collect'] = True
        
        # روابط الانضمام
        elif re.search(r't\.me/\+', url_lower) or re.search(r'telegram\.me/\+', url_lower):
            result['is_valid'] = True
            result['is_group'] = True
            result['is_private'] = True
            result['is_join_link'] = True
            result['has_members'] = True
            result['should_collect'] = True
        
        # روابط addlist
        elif 'addlist' in url_lower:
            result['is_valid'] = True
            result['is_addlist'] = True
            result['is_group'] = True
            result['has_members'] = True
            result['should_collect'] = True
        
        # روابط joinchat
        elif 'joinchat' in url_lower:
            result['is_valid'] = True
            result['is_group'] = True
            result['is_private'] = True
            result['is_join_link'] = True
            result['has_members'] = True
            result['should_collect'] = True
        
        # روابط القنوات (نرفضها)
        elif '/c/' in url_lower or '/channel/' in url_lower or '/s/' in url_lower:
            result['is_channel'] = True
            result['is_subscription'] = True
            result['reason'] = 'قناة'
        
        # روابط الرسائل (نقبل رسالة واحدة فقط)
        elif re.search(r't\.me/[a-zA-Z0-9_]+/\d+', url_lower):
            result['is_message_link'] = True
            result['is_valid'] = True
            result['should_collect'] = Config.COLLECT_ONE_MESSAGE_PER_GROUP
        
        return result
    
    @staticmethod
    def _analyze_whatsapp_link(url: str) -> Dict:
        """تحليل رابط واتساب"""
        return {
            'is_valid': True,
            'link_type': 'whatsapp_group',
            'is_group': True,
            'is_active': True,
            'is_expired': False,
            'should_collect': True,
            'reason': ''
        }
    
    @staticmethod
    def should_collect_link(url_info: Dict) -> Tuple[bool, str]:
        """تحديد ما إذا كان يجب جمع الرابط"""
        if not url_info['is_valid']:
            return False, "رابط غير صالح"
        
        details = url_info['details']
        
        # ✅ 1. تجاهل البوتات
        if Config.FILTER_BOT_LINKS and details.get('is_bot', False):
            return False, "رابط بوت"
        
        # ✅ 2. تجاهل t.me/me
        if Config.FILTER_ME_LINKS and details.get('is_me_link', False):
            return False, "رابط t.me/me"
        
        # ✅ 3. تجاهل القنوات
        if Config.FILTER_CHANNELS and details.get('is_channel', False):
            return False, "قناة"
        
        # ✅ 4. تجاهل مجموعات المشتركين
        if Config.FILTER_SUBSCRIPTION_GROUPS and details.get('is_subscription', False):
            return False, "مجموعة تحتوي على مشتركين"
        
        # ✅ 5. جمع المجموعات ذات الأعضاء فقط
        if Config.COLLECT_MEMBER_GROUPS_ONLY and not details.get('has_members', False):
            return False, "مجموعة بدون أعضاء"
        
        # ✅ 6. جمع الروابط النشطة فقط
        if Config.COLLECT_ONLY_ACTIVE and not details.get('is_active', True):
            return False, "رابط غير نشط"
        
        # ✅ 7. تجنب الروابط المنتهية
        if Config.FILTER_EXPIRED_LINKS and details.get('is_expired', False):
            return False, "رابط منتهي"
        
        return details.get('should_collect', False), details.get('reason', 'تم القبول')

# ======================
# Enhanced Database Manager - مدير قاعدة البيانات المحسن
# ======================

class EnhancedDatabaseManager:
    """إدارة قاعدة البيانات المتقدمة"""
    
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    
    @classmethod
    async def get_instance(cls):
        """الحصول على نسخة قاعدة البيانات"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = EnhancedDatabaseManager()
                    await cls._instance._initialize()
        return cls._instance
    
    async def _initialize(self):
        """تهيئة قاعدة البيانات"""
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
        """إنشاء جداول قاعدة البيانات"""
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
                original_url TEXT NOT NULL,
                preserved_url TEXT NOT NULL,
                platform TEXT NOT NULL,
                link_type TEXT,
                telegram_type TEXT,
                title TEXT,
                description TEXT,
                members_count INTEGER DEFAULT 0,
                session_id INTEGER,
                collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_date TIMESTAMP,
                last_checked TIMESTAMP,
                check_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                is_expired BOOLEAN DEFAULT 0,
                is_verified BOOLEAN DEFAULT 0,
                validation_score INTEGER DEFAULT 0,
                metadata TEXT,
                tags TEXT,
                added_by_user INTEGER,
                source TEXT,
                is_channel BOOLEAN DEFAULT 0,
                is_group BOOLEAN DEFAULT 1,
                is_private BOOLEAN DEFAULT 0,
                is_public BOOLEAN DEFAULT 0,
                is_join_link BOOLEAN DEFAULT 0,
                is_bot BOOLEAN DEFAULT 0,
                is_me_link BOOLEAN DEFAULT 0,
                has_members BOOLEAN DEFAULT 0,
                is_subscription BOOLEAN DEFAULT 0,
                is_message_link BOOLEAN DEFAULT 0,
                is_addlist BOOLEAN DEFAULT 0,
                filter_reason TEXT,
                collection_status TEXT DEFAULT 'pending',
                is_new BOOLEAN DEFAULT 1,
                whatsapp_code TEXT,
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
        
        # جدول إحصائيات التجميع
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS collection_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_date DATE NOT NULL,
                total_collected INTEGER DEFAULT 0,
                telegram_collected INTEGER DEFAULT 0,
                whatsapp_collected INTEGER DEFAULT 0,
                filtered_count INTEGER DEFAULT 0,
                new_links_count INTEGER DEFAULT 0,
                sessions_used INTEGER DEFAULT 0,
                groups_processed INTEGER DEFAULT 0,
                UNIQUE(collection_date)
            )
        ''')
        
        # جدول الإشعارات
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        ''')
        
        await self.conn.commit()
        
        # إنشاء فهارس
        await self._create_indexes()
    
    async def _create_indexes(self):
        """إنشاء فهارس قاعدة البيانات"""
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_links_url_hash ON links(url_hash)',
            'CREATE INDEX IF NOT EXISTS idx_links_platform ON links(platform)',
            'CREATE INDEX IF NOT EXISTS idx_links_collected_date ON links(collected_date)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_group ON links(is_group)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_new ON links(is_new)',
            'CREATE INDEX IF NOT EXISTS idx_links_has_members ON links(has_members)',
            'CREATE INDEX IF NOT EXISTS idx_links_message_date ON links(message_date)',
            'CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)',
            'CREATE INDEX IF NOT EXISTS idx_users_last_active ON bot_users(last_active)',
            'CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)',
            'CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(notification_type)',
            'CREATE INDEX IF NOT EXISTS idx_stats_date ON collection_stats(collection_date)'
        ]
        
        for index_sql in indexes:
            try:
                await self.conn.execute(index_sql)
            except Exception as e:
                logger.error(f"خطأ في إنشاء الفهرس: {e}")
        
        await self.conn.commit()
    
    async def add_link(self, link_info: Dict) -> Tuple[bool, str, Dict]:
        """إضافة رابط إلى قاعدة البيانات"""
        try:
            url = link_info.get('original_url', '')
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return False, "رابط غير صالح", {}
            
            # التحقق مما إذا كان يجب جمع الرابط
            should_collect, reason = EnhancedLinkProcessor.should_collect_link(url_info)
            if not should_collect:
                logger.info(f"⏭️ تم تجاهل الرابط: {url[:50]}... - السبب: {reason}")
                return False, reason, {}
            
            # ✅ التحقق من التكرار
            if Config.PREVENT_DUPLICATES:
                cursor = await self.conn.execute(
                    'SELECT id FROM links WHERE url_hash = ?',
                    (url_info['url_hash'],)
                )
                existing = await cursor.fetchone()
                
                if existing:
                    # تحديث الرابط الموجود فقط إذا كان جديداً
                    if link_info.get('is_new_collection', False):
                        await self.conn.execute('''
                            UPDATE links SET 
                            last_checked = CURRENT_TIMESTAMP,
                            check_count = check_count + 1,
                            is_new = 0
                            WHERE id = ?
                        ''', (existing[0],))
                        await self.conn.commit()
                    return False, "الرابط موجود مسبقاً", {'link_id': existing[0]}
            
            details = url_info['details']
            
            # ✅ إدراج الرابط الجديد
            cursor = await self.conn.execute('''
                INSERT INTO links 
                (url_hash, original_url, preserved_url, platform, link_type, telegram_type,
                 session_id, collected_date, message_date, is_active, is_verified,
                 validation_score, metadata, added_by_user, source,
                 is_channel, is_group, is_private, is_public, is_join_link,
                 is_bot, is_me_link, has_members, is_subscription, is_message_link,
                 is_addlist, filter_reason, collection_status, is_new, whatsapp_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                url_info['url_hash'],
                url_info['original_url'],
                url_info['preserved_url'],
                url_info['platform'],
                details.get('link_type', 'unknown'),
                'telegram' if url_info['platform'] == 'telegram' else '',
                link_info.get('session_id'),
                datetime.now().isoformat(),
                link_info.get('message_date', datetime.now().isoformat()),
                details.get('is_active', True),
                True,  # تم التحقق منه
                100,   # درجة تحقق عالية
                json.dumps({
                    'collected_at': datetime.now().isoformat(),
                    'platform_details': details,
                    'source_group': link_info.get('source_group', ''),
                    'source_type': link_info.get('source', 'unknown')
                }),
                link_info.get('added_by_user', 0),
                link_info.get('source', 'manual'),
                details.get('is_channel', False),
                details.get('is_group', True),
                details.get('is_private', False),
                details.get('is_public', False),
                details.get('is_join_link', False),
                details.get('is_bot', False),
                details.get('is_me_link', False),
                details.get('has_members', True),
                details.get('is_subscription', False),
                details.get('is_message_link', False),
                details.get('is_addlist', False),
                reason if not should_collect else '',
                'collected',
                True,  # جديد
                link_info.get('whatsapp_code', '')
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
            
            logger.info(f"✅ تمت إضافة رابط جديد: {url[:50]}...")
            
            return True, "تمت إضافة الرابط بنجاح", {
                'link_id': link_id,
                'url_hash': url_info['url_hash'],
                'is_new': True
            }
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الرابط: {e}")
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def add_session(self, session_data: Dict) -> Tuple[bool, str, Dict]:
        """إضافة جلسة إلى قاعدة البيانات"""
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
        """تحديث إحصائيات المستخدم"""
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
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """الحصول على إحصائيات المستخدم"""
        try:
            cursor = await self.conn.execute('''
                SELECT *, 
                       (SELECT COUNT(*) FROM links WHERE added_by_user = ? AND is_new = 1) as new_links,
                       (SELECT COUNT(*) FROM links WHERE added_by_user = ?) as total_links,
                       (SELECT COUNT(*) FROM sessions WHERE added_by_user = ?) as total_sessions
                FROM bot_users 
                WHERE user_id = ?
            ''', (user_id, user_id, user_id, user_id))
            
            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على إحصائيات المستخدم: {e}")
            return None
    
    async def get_active_sessions(self, limit: int = 10) -> List[Dict]:
        """الحصول على الجلسات النشطة"""
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
    
    async def get_links_count(self, only_new: bool = False) -> int:
        """الحصول على عدد الروابط"""
        try:
            if only_new:
                cursor = await self.conn.execute('SELECT COUNT(*) FROM links WHERE is_new = 1 AND platform IN ("telegram", "whatsapp")')
            else:
                cursor = await self.conn.execute('SELECT COUNT(*) FROM links WHERE platform IN ("telegram", "whatsapp")')
            result = await cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"خطأ في الحصول على عدد الروابط: {e}")
            return 0
    
    async def get_new_links(self, limit: int = 1000) -> List[Dict]:
        """الحصول على الروابط الجديدة"""
        try:
            cursor = await self.conn.execute('''
                SELECT original_url, platform, collected_date, filter_reason 
                FROM links 
                WHERE is_new = 1 AND platform IN ("telegram", "whatsapp")
                ORDER BY collected_date DESC 
                LIMIT ?
            ''', (limit,))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            links = []
            for row in rows:
                link_dict = dict(zip(columns, row))
                links.append(link_dict)
            
            return links
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على الروابط الجديدة: {e}")
            return []
    
    async def mark_links_as_old(self):
        """وضع علامة على جميع الروابط بأنها قديمة"""
        try:
            await self.conn.execute('UPDATE links SET is_new = 0 WHERE is_new = 1')
            await self.conn.commit()
            logger.info("✅ تم وضع علامة على جميع الروابط بأنها قديمة")
        except Exception as e:
            logger.error(f"خطأ في وضع علامة على الروابط: {e}")
    
    async def add_notification(self, user_id: int, notification_type: str, message: str, metadata: Dict = None):
        """إضافة إشعار للمستخدم"""
        try:
            await self.conn.execute('''
                INSERT INTO notifications (user_id, notification_type, message, metadata)
                VALUES (?, ?, ?, ?)
            ''', (user_id, notification_type, message, json.dumps(metadata or {})))
            await self.conn.commit()
            logger.info(f"✅ تم إضافة إشعار للمستخدم {user_id}: {notification_type}")
        except Exception as e:
            logger.error(f"خطأ في إضافة الإشعار: {e}")
    
    async def get_unread_notifications(self, user_id: int) -> List[Dict]:
        """الحصول على الإشعارات غير المقروءة"""
        try:
            cursor = await self.conn.execute('''
                SELECT * FROM notifications 
                WHERE user_id = ? AND is_read = 0
                ORDER BY created_at DESC
                LIMIT 50
            ''', (user_id,))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            notifications = []
            for row in rows:
                notification_dict = dict(zip(columns, row))
                if notification_dict.get('metadata'):
                    try:
                        notification_dict['metadata'] = json.loads(notification_dict['metadata'])
                    except:
                        notification_dict['metadata'] = {}
                notifications.append(notification_dict)
            
            return notifications
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على الإشعارات: {e}")
            return []
    
    async def mark_notifications_as_read(self, user_id: int):
        """وضع علامة على الإشعارات كمقروءة"""
        try:
            await self.conn.execute('''
                UPDATE notifications SET is_read = 1 
                WHERE user_id = ? AND is_read = 0
            ''', (user_id,))
            await self.conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تحديث الإشعارات: {e}")
    
    async def update_collection_stats(self, stats: Dict):
        """تحديث إحصائيات التجميع"""
        try:
            today = datetime.now().date().isoformat()
            
            cursor = await self.conn.execute(
                'SELECT id FROM collection_stats WHERE collection_date = ?',
                (today,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                await self.conn.execute('''
                    UPDATE collection_stats SET
                    total_collected = total_collected + ?,
                    telegram_collected = telegram_collected + ?,
                    whatsapp_collected = whatsapp_collected + ?,
                    filtered_count = filtered_count + ?,
                    new_links_count = new_links_count + ?,
                    sessions_used = sessions_used + ?,
                    groups_processed = groups_processed + ?
                    WHERE id = ?
                ''', (
                    stats.get('total_collected', 0),
                    stats.get('telegram_collected', 0),
                    stats.get('whatsapp_collected', 0),
                    stats.get('filtered_count', 0),
                    stats.get('new_links_count', 0),
                    stats.get('sessions_used', 0),
                    stats.get('groups_processed', 0),
                    existing[0]
                ))
            else:
                await self.conn.execute('''
                    INSERT INTO collection_stats 
                    (collection_date, total_collected, telegram_collected, whatsapp_collected,
                     filtered_count, new_links_count, sessions_used, groups_processed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    today,
                    stats.get('total_collected', 0),
                    stats.get('telegram_collected', 0),
                    stats.get('whatsapp_collected', 0),
                    stats.get('filtered_count', 0),
                    stats.get('new_links_count', 0),
                    stats.get('sessions_used', 0),
                    stats.get('groups_processed', 0)
                ))
            
            await self.conn.commit()
            
        except Exception as e:
            logger.error(f"خطأ في تحديث إحصائيات التجميع: {e}")
    
    async def get_stats_summary(self) -> Dict:
        """الحصول على ملخص الإحصائيات"""
        try:
            stats = {}
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE platform IN ('telegram', 'whatsapp')")
            stats['total_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_new = 1 AND platform IN ('telegram', 'whatsapp')")
            stats['new_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE has_members = 1 AND platform IN ('telegram', 'whatsapp')")
            stats['member_groups'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT platform, COUNT(*) FROM links WHERE platform IN ('telegram', 'whatsapp') GROUP BY platform")
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_verified = 1 AND platform IN ('telegram', 'whatsapp')")
            stats['verified_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE date(collected_date) = date('now') AND platform IN ('telegram', 'whatsapp')")
            stats['today_links'] = (await cursor.fetchone())[0]
            
            # إحصائيات الفلترة
            cursor = await self.conn.execute("SELECT filter_reason, COUNT(*) FROM links WHERE filter_reason IS NOT NULL AND filter_reason != '' GROUP BY filter_reason")
            stats['filtered_links'] = dict(await cursor.fetchall())
            
            # إحصائيات اليوم
            today = datetime.now().date().isoformat()
            cursor = await self.conn.execute('''
                SELECT total_collected, telegram_collected, whatsapp_collected, new_links_count 
                FROM collection_stats 
                WHERE collection_date = ?
            ''', (today,))
            today_stats = await cursor.fetchone()
            
            if today_stats:
                stats['today_stats'] = {
                    'total_collected': today_stats[0],
                    'telegram_collected': today_stats[1],
                    'whatsapp_collected': today_stats[2],
                    'new_links_count': today_stats[3]
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على ملخص الإحصائيات: {e}")
            return {}
    
    async def export_links(self, filters: Dict = None, only_new: bool = False, limit: int = 10000) -> List[str]:
        """تصدير الروابط"""
        try:
            query = 'SELECT preserved_url FROM links WHERE platform IN ("telegram", "whatsapp")'
            params = []
            
            if only_new:
                query += ' AND is_new = 1'
            
            if filters:
                where_clauses = []
                
                if filters.get('platform'):
                    where_clauses.append("platform = ?")
                    params.append(filters['platform'])
                
                if filters.get('min_members'):
                    where_clauses.append("members_count >= ?")
                    params.append(filters['min_members'])
                
                if filters.get('only_member_groups'):
                    where_clauses.append("has_members = 1")
                
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
    
    async def close(self):
        """إغلاق اتصال قاعدة البيانات"""
        if hasattr(self, 'conn'):
            await self.conn.close()
            self._initialized = False

# ======================
# Session Manager - مدير الجلسات
# ======================

class SessionManager:
    """إدارة جلسات تيليجرام"""
    
    @staticmethod
    async def validate_session(session_string: str) -> Tuple[bool, Dict]:
        """التحقق من صحة جلسة تيليجرام"""
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
        """إنشاء عميل تيليجرام من سلسلة الجلسة"""
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
# Telegram Link Validator - مدقق روابط تيليجرام
# ======================

class TelegramLinkValidator:
    """التحقق من روابط تيليجرام"""
    
    @staticmethod
    async def validate_telegram_link(client: TelegramClient, url: str) -> Dict:
        """التحقق من رابط تيليجرام"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if url_info['platform'] != 'telegram':
                return {'is_valid': False, 'reason': 'ليس رابط تيليجرام'}
            
            details = url_info['details']
            
            # ✅ التحقق من تاريخ الرابط (لروابط الرسائل فقط)
            if details.get('is_message_link', False):
                try:
                    # استخراج معرف الرسالة
                    match = re.search(r't\.me/[^/]+/(\d+)', url.lower())
                    if match:
                        message_id = int(match.group(1))
                        
                        # الحصول على معلومات المجموعة
                        entity_match = re.search(r't\.me/([^/]+)', url.lower())
                        if entity_match:
                            entity_username = entity_match.group(1)
                            
                            try:
                                entity = await client.get_entity(entity_username)
                                message = await client.get_messages(entity, ids=message_id)
                                
                                if message:
                                    # ✅ التحقق من أن الرسالة ليست أقدم من 5 سنوات
                                    message_date = message.date
                                    five_years_ago = datetime.now() - timedelta(days=Config.TELEGRAM_YEARS_BACK * 365)
                                    
                                    if message_date < five_years_ago:
                                        return {
                                            'is_valid': False,
                                            'reason': f'رسالة أقدم من {Config.TELEGRAM_YEARS_BACK} سنوات',
                                            'message_date': message_date.isoformat()
                                        }
                            except Exception:
                                pass
                except Exception:
                    pass
            
            # ✅ التحقق من أن الرابط نشط (لروابط المجموعات)
            if details.get('is_group', False) and not details.get('is_message_link', False):
                try:
                    if details.get('is_public', False):
                        # للمجموعات العامة: محاولة الحصول على الكيان
                        entity_match = re.search(r't\.me/([^/]+)', url.lower())
                        if entity_match:
                            entity_username = entity_match.group(1)
                            entity = await client.get_entity(entity_username)
                            
                            # ✅ التحقق من عدد الأعضاء
                            if hasattr(entity, 'participants_count'):
                                members_count = entity.participants_count
                                if members_count > 0:
                                    return {
                                        'is_valid': True,
                                        'has_members': True,
                                        'members_count': members_count,
                                        'is_active': True,
                                        'reason': 'مجموعة نشطة تحتوي على أعضاء'
                                    }
                    
                    elif details.get('is_private', False) or details.get('is_join_link', False):
                        # ✅ للمجموعات الخاصة: نقبلها مباشرة (لا يمكن التحقق بدون الانضمام)
                        return {
                            'is_valid': True,
                            'has_members': True,
                            'is_active': True,
                            'reason': 'رابط انضمام للمجموعة'
                        }
                    
                except Exception as e:
                    logger.debug(f"خطأ في التحقق من المجموعة {url}: {e}")
                    # ✅ إذا فشل التحقق، نرفض الرابط (لضمان النشاط)
                    return {
                        'is_valid': False,
                        'reason': 'فشل التحقق من نشاط الرابط'
                    }
            
            # ✅ للمجموعات التي تمررت جميع الاختبارات
            if details.get('should_collect', False):
                return {
                    'is_valid': True,
                    'has_members': details.get('has_members', False),
                    'is_active': True,
                    'reason': 'رابط مقبول'
                }
            
            return {
                'is_valid': False,
                'reason': 'لا ينطبق على شروط الجمع'
            }
            
        except Exception as e:
            logger.error(f"خطأ في التحقق من الرابط: {e}")
            return {
                'is_valid': False,
                'reason': f'خطأ في التحقق: {str(e)[:50]}'
            }
    
    @staticmethod
    async def extract_links_from_group(client: TelegramClient, entity, max_messages: int = 100) -> List[Dict]:
        """استخراج الروابط من مجموعة"""
        links_data = []
        message_links_collected = 0
        
        try:
            # ✅ الحصول على معلومات المجموعة
            try:
                group_info = await client.get_entity(entity)
                group_title = getattr(group_info, 'title', 'غير معروف')
                group_members = getattr(group_info, 'participants_count', 0)
            except Exception:
                group_title = 'غير معروف'
                group_members = 0
            
            # ✅ جمع الروابط من الوصف
            if hasattr(entity, 'about') and entity.about:
                extracted = TelegramLinkValidator._extract_links_from_text(entity.about)
                for link in extracted:
                    links_data.append({
                        'url': link,
                        'source': 'description',
                        'group_title': group_title,
                        'group_members': group_members,
                        'message_date': datetime.now().isoformat()
                    })
            
            # ✅ جمع الروابط من الرسائل
            messages_collected = 0
            async for message in client.iter_messages(entity, limit=max_messages):
                try:
                    messages_collected += 1
                    message_date = message.date.isoformat() if message.date else datetime.now().isoformat()
                    
                    # ✅ التحقق من تاريخ الرسالة (5 سنوات فقط لتليجرام)
                    if message.date:
                        five_years_ago = datetime.now() - timedelta(days=Config.TELEGRAM_YEARS_BACK * 365)
                        if message.date < five_years_ago:
                            continue
                    
                    # ✅ البحث عن روابط في نص الرسالة
                    if message.text:
                        extracted = TelegramLinkValidator._extract_links_from_text(message.text)
                        for link in extracted:
                            # ✅ التحقق مما إذا كان رابط رسالة
                            url_info = EnhancedLinkProcessor.extract_url_info(link)
                            details = url_info['details']
                            
                            if details.get('is_message_link', False):
                                if message_links_collected >= 1 and Config.COLLECT_ONE_MESSAGE_PER_GROUP:
                                    continue  # ✅ تجميع رسالة واحدة فقط من كل مجموعة
                                message_links_collected += 1
                            
                            links_data.append({
                                'url': link,
                                'source': 'message_text',
                                'group_title': group_title,
                                'group_members': group_members,
                                'message_date': message_date,
                                'message_id': message.id
                            })
                    
                    # ✅ البحث عن روابط في الأزرار
                    if hasattr(message, 'reply_markup') and message.reply_markup:
                        try:
                            for row in message.reply_markup.rows:
                                for button in row.buttons:
                                    if hasattr(button, 'url') and button.url:
                                        extracted = TelegramLinkValidator._extract_links_from_text(button.url)
                                        for link in extracted:
                                            links_data.append({
                                                'url': link,
                                                'source': 'button',
                                                'group_title': group_title,
                                                'group_members': group_members,
                                                'message_date': message_date,
                                                'message_id': message.id
                                            })
                        except Exception:
                            pass
                    
                    # تأخير قصير بين الرسائل
                    if messages_collected % 20 == 0:
                        await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.debug(f"خطأ في معالجة رسالة: {e}")
                    continue
            
            logger.info(f"✅ تمت معالجة {messages_collected} رسالة في مجموعة {group_title}")
            
            # ✅ إزالة التكرارات
            unique_links = []
            seen_urls = set()
            
            for link_data in links_data:
                url = link_data['url']
                url_info = EnhancedLinkProcessor.extract_url_info(url)
                
                if url_info['url_hash'] in seen_urls:
                    continue
                
                seen_urls.add(url_info['url_hash'])
                unique_links.append(link_data)
            
            logger.info(f"✅ تم استخراج {len(unique_links)} رابط فريد من مجموعة {group_title}")
            
            return unique_links
            
        except Exception as e:
            logger.error(f"خطأ في استخراج روابط المجموعة: {e}")
            return []
    
    @staticmethod
    def _extract_links_from_text(text: str) -> List[str]:
        """استخراج الروابط من النص"""
        if not text:
            return []
        
        extracted_links = []
        
        # ✅ البحث عن جميع أنماط روابط تيليجرام
        telegram_patterns = [
            r'(https?://t\.me/[^\s<>"\']+)',
            r'(https?://telegram\.me/[^\s<>"\']+)',
            r'(https?://telegram\.dog/[^\s<>"\']+)',
            r'(t\.me/[^\s<>"\']+)',
            r'(telegram\.me/[^\s<>"\']+)',
            r'(telegram\.dog/[^\s<>"\']+)',
            r'(https?://t\.me/\+[^\s<>"\']+)',
            r'(https?://t\.me/joinchat/[^\s<>"\']+)',
            r'(https?://t\.me/addlist/[^\s<>"\']+)',
            r'(\+[A-Za-z0-9_-]+)',  # روابط +joinchat
            r'(joinchat/[A-Za-z0-9_-]+)'  # روابط joinchat
        ]
        
        # ✅ البحث عن جميع أنماط روابط واتساب
        whatsapp_patterns = [
            r'(https?://chat\.whatsapp\.com/[^\s<>"\']+)',
            r'(https?://whatsapp\.com/[^\s<>"\']+)',
            r'(chat\.whatsapp\.com/[^\s<>"\']+)',
            r'(whatsapp\.com/[^\s<>"\']+)'
        ]
        
        all_patterns = telegram_patterns + whatsapp_patterns
        
        for pattern in all_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    link = match[0]
                else:
                    link = match
                
                # ✅ معالجة خاصة للروابط النسبية
                if not link.startswith(('http://', 'https://')):
                    if any(domain in link for domain in ['t.me', 'telegram.me', 'telegram.dog']):
                        link = 'https://' + link
                    elif any(domain in link for domain in ['chat.whatsapp.com', 'whatsapp.com']):
                        link = 'https://' + link
                    elif link.startswith('+'):
                        link = 'https://t.me/' + link
                    elif 'joinchat' in link:
                        link = 'https://t.me/' + link
                
                extracted_links.append(link)
        
        return extracted_links

# ======================
# WhatsApp Link Validator - مدقق روابط واتساب
# ======================

class WhatsAppLinkValidator:
    """التحقق من روابط واتساب"""
    
    @staticmethod
    async def validate_whatsapp_link(url: str) -> Dict:
        """التحقق من رابط واتساب"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if url_info['platform'] != 'whatsapp':
                return {'is_valid': False, 'reason': 'ليس رابط واتساب'}
            
            # ✅ التحقق من أن الرابط ليس أقدم من 60 يوماً
            # (سيتم التحقق من تاريخ الرسالة عند الجمع)
            
            return {
                'is_valid': True,
                'is_active': True,
                'reason': 'رابط واتساب مقبول'
            }
            
        except Exception as e:
            logger.error(f"خطأ في التحقق من رابط واتساب: {e}")
            return {
                'is_valid': False,
                'reason': f'خطأ في التحقق: {str(e)[:50]}'
            }
    
    @staticmethod
    async def extract_links_from_messages(client: TelegramClient, entity, max_messages: int = 100) -> List[Dict]:
        """استخراج روابط واتساب من الرسائل"""
        links_data = []
        
        try:
            # ✅ الحصول على معلومات المجموعة
            try:
                group_info = await client.get_entity(entity)
                group_title = getattr(group_info, 'title', 'غير معروف')
            except Exception:
                group_title = 'غير معروف'
            
            # ✅ جمع روابط واتساب من الرسائل (آخر 60 يوماً فقط)
            sixty_days_ago = datetime.now() - timedelta(days=Config.WHATSAPP_DAYS_BACK)
            messages_collected = 0
            
            async for message in client.iter_messages(entity, limit=max_messages):
                try:
                    messages_collected += 1
                    
                    # ✅ التحقق من تاريخ الرسالة (60 يوماً فقط لواتساب)
                    if message.date and message.date < sixty_days_ago:
                        continue
                    
                    message_date = message.date.isoformat() if message.date else datetime.now().isoformat()
                    
                    # ✅ البحث عن روابط واتساب فقط
                    if message.text:
                        # البحث عن روابط واتساب
                        whatsapp_patterns = [
                            r'https?://chat\.whatsapp\.com/[^\s<>"\']+',
                            r'https?://whatsapp\.com/[^\s<>"\']+',
                            r'chat\.whatsapp\.com/[^\s<>"\']+',
                            r'whatsapp\.com/[^\s<>"\']+'
                        ]
                        
                        for pattern in whatsapp_patterns:
                            matches = re.findall(pattern, message.text, re.IGNORECASE)
                            for link in matches:
                                if not link.startswith(('http://', 'https://')):
                                    link = 'https://' + link
                                
                                links_data.append({
                                    'url': link,
                                    'source': 'message_text',
                                    'group_title': group_title,
                                    'message_date': message_date,
                                    'message_id': message.id,
                                    'is_whatsapp': True
                                })
                    
                    # تأخير قصير بين الرسائل
                    if messages_collected % 20 == 0:
                        await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.debug(f"خطأ في معالجة رسالة واتساب: {e}")
                    continue
            
            logger.info(f"✅ تمت معالجة {messages_collected} رسالة للواتساب في مجموعة {group_title}")
            
            # ✅ إزالة التكرارات
            unique_links = []
            seen_urls = set()
            
            for link_data in links_data:
                url = link_data['url']
                url_info = EnhancedLinkProcessor.extract_url_info(url)
                
                if url_info['url_hash'] in seen_urls:
                    continue
                
                seen_urls.add(url_info['url_hash'])
                unique_links.append(link_data)
            
            logger.info(f"✅ تم استخراج {len(unique_links)} رابط واتساب فريد من مجموعة {group_title}")
            
            return unique_links
            
        except Exception as e:
            logger.error(f"خطأ في استخراج روابط واتساب: {e}")
            return []

# ======================
# Smart Collection Manager - مدير الجمع الذكي
# ======================

class SmartCollectionManager:
    """إدارة الجمع الذكي حسب المتطلبات"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        self.collection_completed = False
        self.stats = {
            'total_collected': 0,
            'telegram_collected': 0,
            'whatsapp_collected': 0,
            'filtered_count': 0,
            'new_links_count': 0,
            'sessions_used': 0,
            'groups_processed': 0,
            'errors': 0,
            'last_collection_time': None,
            'current_session': None,
            'current_group': None,
            'filter_reasons': defaultdict(int),
            'collection_status': 'idle',
            'completion_notification_sent': False
        }
        self.collection_task = None
        self.last_progress_update = datetime.now()
        
        # ✅ إحصائيات مفصلة حسب النوع
        self.detailed_stats = {
            'telegram': {
                'public_groups': 0,
                'private_groups': 0,
                'join_links': 0,
                'addlist_links': 0,
                'message_links': 0,
                'active_links': 0,
                'expired_links': 0
            },
            'whatsapp': {
                'active_links': 0,
                'expired_links': 0
            },
            'filtered': {
                'bots': 0,
                'channels': 0,
                'me_links': 0,
                'subscription_groups': 0,
                'no_members': 0,
                'expired': 0,
                'old_telegram': 0,
                'old_whatsapp': 0
            }
        }
    
    async def start_collection(self):
        """بدء عملية الجمع"""
        if self.active:
            return
        
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.collection_completed = False
        self.stats['completion_notification_sent'] = False
        
        logger.info("🚀 بدء عملية الجمع الذكية حسب المتطلبات...")
        
        # بدء مهمة الجمع في الخلفية
        self.collection_task = asyncio.create_task(self._smart_collection_loop())
    
    async def _smart_collection_loop(self):
        """حلقة الجمع الذكية"""
        self.stats['collection_status'] = 'starting'
        
        while self.active and not self.stop_requested:
            if self.paused:
                await asyncio.sleep(1)
                continue
            
            try:
                self.stats['collection_status'] = 'collecting'
                await self._smart_collection_cycle()
                
                # ✅ التحقق من اكتمال الجمع
                if await self._check_collection_completion():
                    self.collection_completed = True
                    self.stats['collection_status'] = 'completed'
                    
                    # ✅ إرسال إشعار اكتمال الجمع
                    await self._send_completion_notification()
                    
                    # تأخير طويل قبل الدورة التالية
                    logger.info("✅ اكتمل جمع جميع الروابط. انتظار روابط جديدة...")
                    await asyncio.sleep(300)  # انتظار 5 دقائق
                    
                    # ✅ إعادة ضبط لبدء جمع الروابط الجديدة
                    self.collection_completed = False
                    self.stats['completion_notification_sent'] = False
                    await self._mark_old_links_as_collected()
                
                else:
                    # تأخير بين الدورات
                    delay = Config.REQUEST_DELAYS['max_cycle_delay']
                    logger.info(f"⏳ تأخير {delay} ثانية قبل الدورة القادمة")
                    await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"خطأ في دورة الجمع: {e}")
                self.stats['errors'] += 1
                self.stats['collection_status'] = 'error'
                await asyncio.sleep(10)
        
        self.active = False
        self.stats['collection_status'] = 'stopped'
        logger.info("⏹️ توقفت عملية الجمع")
    
    async def _smart_collection_cycle(self):
        """دورة الجمع الذكية"""
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
                task = self._process_session_smart(session)
                tasks.append(task)
                await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # ✅ تحديث الإحصائيات
            successful = 0
            total_collected = 0
            total_filtered = 0
            
            for result in results:
                if isinstance(result, dict):
                    successful += 1
                    total_collected += result.get('collected', 0)
                    total_filtered += result.get('filtered', 0)
            
            logger.info(f"✅ اكتملت دورة الجمع الذكية: {successful}/{len(tasks)} جلسات ناجحة - {total_collected} رابط مجمع - {total_filtered} رابط مصفي")
            
            # ✅ حفظ الإحصائيات في قاعدة البيانات
            await db.update_collection_stats({
                'total_collected': total_collected,
                'telegram_collected': self.stats['telegram_collected'],
                'whatsapp_collected': self.stats['whatsapp_collected'],
                'filtered_count': total_filtered,
                'new_links_count': self.stats['new_links_count'],
                'sessions_used': self.stats['sessions_used'],
                'groups_processed': self.stats['groups_processed']
            })
            
            # ✅ حفظ الإحصائيات المحلية
            await self._save_stats()
            
        except Exception as e:
            logger.error(f"خطأ في دورة الجمع الذكية: {e}")
            self.stats['errors'] += 1
    
    async def _process_session_smart(self, session: Dict):
        """معالجة الجلسة بذكاء"""
        try:
            session_string = session.get('session_string', '')
            session_id = session.get('id')
            session_name = session.get('display_name', f'جلسة {session_id}')
            
            if not session_string or session_string == '********':
                logger.error(f"جلسة {session_id} غير متاحة")
                return {'status': 'error', 'reason': 'جلسة غير متاحة'}
            
            self.stats['current_session'] = session_name
            
            # ✅ فك تشفير الجلسة
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt(session_string)
            
            client = await SessionManager.create_client(decrypted_session)
            if not client:
                return {'status': 'error', 'reason': 'فشل إنشاء العميل'}
            
            logger.info(f"📱 بدء الجمع الذكي من جلسة: {session_name}")
            
            # ✅ جمع الروابط من جميع المجموعات
            collected, filtered_count = await self._collect_from_all_groups_smart(client, session_id, session_name)
            
            await client.disconnect()
            
            # ✅ تحديث إحصائيات الجلسة
            db = await EnhancedDatabaseManager.get_instance()
            await db.conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, last_success = CURRENT_TIMESTAMP, total_uses = total_uses + 1, total_links = total_links + ? WHERE id = ?",
                (len(collected), session_id)
            )
            await db.conn.commit()
            
            logger.info(f"✅ انتهى الجمع من جلسة {session_name}: {len(collected)} رابط مجمع - {filtered_count} رابط مصفي")
            
            return {
                'status': 'success', 
                'collected': len(collected), 
                'filtered': filtered_count,
                'session': session_name
            }
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الجلسة: {e}")
            self.stats['errors'] += 1
            return {'status': 'error', 'reason': str(e)}
    
    async def _collect_from_all_groups_smart(self, client: TelegramClient, session_id: int, session_name: str) -> Tuple[List[Dict], int]:
        """جمع الروابط من جميع المجموعات بذكاء"""
        collected = []
        filtered_count = 0
        groups_processed = 0
        
        try:
            # ✅ الحصول على جميع الدردشات
            all_dialogs = []
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                all_dialogs.append(dialog)
            
            logger.info(f"📊 جلسة {session_name}: تم العثور على {len(all_dialogs)} دردشة")
            
            for dialog in all_dialogs:
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # ✅ تخطي الرسائل الخاصة والمحادثات الشخصية
                    if not hasattr(entity, 'title'):
                        continue
                    
                    self.stats['current_group'] = getattr(entity, 'title', 'غير معروف')
                    groups_processed += 1
                    
                    logger.info(f"🔍 معالجة المجموعة {groups_processed}: {self.stats['current_group']}")
                    
                    # ✅ جمع روابط تيليجرام من المجموعة
                    telegram_links = await TelegramLinkValidator.extract_links_from_group(
                        client, entity, max_messages=Config.MESSAGES_PER_GROUP
                    )
                    
                    # ✅ جمع روابط واتساب من المجموعة
                    whatsapp_links = await WhatsAppLinkValidator.extract_links_from_messages(
                        client, entity, max_messages=Config.MESSAGES_PER_GROUP
                    )
                    
                    # ✅ معالجة روابط تيليجرام
                    for link_data in telegram_links:
                        link_info = await self._process_telegram_link(link_data, session_id, client)
                        if link_info:
                            collected.append(link_info)
                        else:
                            filtered_count += 1
                    
                    # ✅ معالجة روابط واتساب
                    for link_data in whatsapp_links:
                        link_info = await self._process_whatsapp_link(link_data, session_id)
                        if link_info:
                            collected.append(link_info)
                        else:
                            filtered_count += 1
                    
                    # ✅ تحديث الإحصائيات
                    self.stats['groups_processed'] += 1
                    
                    # ✅ إرسال تحديث التقدم كل 5 مجموعات
                    if groups_processed % 5 == 0:
                        logger.info(f"📈 التقدم: {groups_processed}/{len(all_dialogs)} مجموعة - {len(collected)} رابط مجمع - {filtered_count} رابط مصفي")
                    
                    # ✅ تأخير بين المجموعات
                    await asyncio.sleep(Config.REQUEST_DELAYS['between_groups'])
                    
                except Exception as e:
                    logger.debug(f"خطأ في جمع الروابط من المجموعة: {e}")
                    continue
            
            logger.info(f"✅ جلسة {session_name}: تمت معالجة {groups_processed} مجموعة، تم جمع {len(collected)} رابط، تم تصفية {filtered_count} رابط")
            
        except Exception as e:
            logger.error(f"خطأ في جمع الروابط من جميع المجموعات: {e}")
        
        return collected, filtered_count
    
    async def _process_telegram_link(self, link_data: Dict, session_id: int, client: TelegramClient) -> Optional[Dict]:
        """معالجة رابط تيليجرام"""
        try:
            url = link_data['url']
            
            # ✅ التحقق من الرابط
            validation_result = await TelegramLinkValidator.validate_telegram_link(client, url)
            
            if not validation_result['is_valid']:
                self.stats['filtered_count'] += 1
                self.stats['filter_reasons'][validation_result.get('reason', 'غير معروف')] += 1
                
                # ✅ تحديث الإحصائيات التفصيلية
                reason = validation_result.get('reason', '')
                if 'بوت' in reason:
                    self.detailed_stats['filtered']['bots'] += 1
                elif 'قناة' in reason:
                    self.detailed_stats['filtered']['channels'] += 1
                elif 't.me/me' in reason:
                    self.detailed_stats['filtered']['me_links'] += 1
                elif 'مشتركين' in reason:
                    self.detailed_stats['filtered']['subscription_groups'] += 1
                elif 'أعضاء' in reason:
                    self.detailed_stats['filtered']['no_members'] += 1
                elif 'سنة' in reason:
                    self.detailed_stats['filtered']['old_telegram'] += 1
                elif 'منتهي' in reason:
                    self.detailed_stats['filtered']['expired'] += 1
                
                return None
            
            # ✅ استخراج معلومات الرابط
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            details = url_info['details']
            
            # ✅ تحديث الإحصائيات التفصيلية
            if details.get('is_public', False):
                self.detailed_stats['telegram']['public_groups'] += 1
            elif details.get('is_private', False):
                self.detailed_stats['telegram']['private_groups'] += 1
            
            if details.get('is_join_link', False):
                self.detailed_stats['telegram']['join_links'] += 1
            elif details.get('is_addlist', False):
                self.detailed_stats['telegram']['addlist_links'] += 1
            elif details.get('is_message_link', False):
                self.detailed_stats['telegram']['message_links'] += 1
            
            self.detailed_stats['telegram']['active_links'] += 1
            
            # ✅ تحضير بيانات الرابط
            link_info = {
                'original_url': url,
                'url_info': url_info,
                'session_id': session_id,
                'source': link_data.get('source', 'unknown'),
                'source_group': link_data.get('group_title', ''),
                'message_date': link_data.get('message_date', ''),
                'is_new_collection': True,
                'platform': 'telegram',
                'validation_result': validation_result
            }
            
            # ✅ إضافة الرابط إلى قاعدة البيانات
            db = await EnhancedDatabaseManager.get_instance()
            success, message, details = await db.add_link(link_info)
            
            if success:
                # ✅ تحديث الإحصائيات العامة
                self.stats['total_collected'] += 1
                self.stats['telegram_collected'] += 1
                if details.get('is_new', False):
                    self.stats['new_links_count'] += 1
                
                # ✅ تسجيل بعض الروابط في اللوج
                if self.stats['total_collected'] % 50 == 0:
                    logger.info(f"✅ تم حفظ {self.stats['total_collected']} رابط حتى الآن")
                
                return link_info
            
            return None
            
        except Exception as e:
            logger.error(f"خطأ في معالجة رابط تيليجرام {url}: {e}")
            return None
    
    async def _process_whatsapp_link(self, link_data: Dict, session_id: int) -> Optional[Dict]:
        """معالجة رابط واتساب"""
        try:
            url = link_data['url']
            
            # ✅ التحقق من الرابط
            validation_result = await WhatsAppLinkValidator.validate_whatsapp_link(url)
            
            if not validation_result['is_valid']:
                self.stats['filtered_count'] += 1
                self.stats['filter_reasons'][validation_result.get('reason', 'غير معروف')] += 1
                
                # ✅ تحديث الإحصائيات التفصيلية
                reason = validation_result.get('reason', '')
                if 'منتهي' in reason:
                    self.detailed_stats['filtered']['expired'] += 1
                elif 'قديم' in reason:
                    self.detailed_stats['filtered']['old_whatsapp'] += 1
                
                return None
            
            # ✅ استخراج معلومات الرابط
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            # ✅ تحديث الإحصائيات التفصيلية
            self.detailed_stats['whatsapp']['active_links'] += 1
            
            # ✅ تحضير بيانات الرابط
            link_info = {
                'original_url': url,
                'url_info': url_info,
                'session_id': session_id,
                'source': link_data.get('source', 'unknown'),
                'source_group': link_data.get('group_title', ''),
                'message_date': link_data.get('message_date', ''),
                'is_new_collection': True,
                'platform': 'whatsapp',
                'validation_result': validation_result
            }
            
            # ✅ إضافة الرابط إلى قاعدة البيانات
            db = await EnhancedDatabaseManager.get_instance()
            success, message, details = await db.add_link(link_info)
            
            if success:
                # ✅ تحديث الإحصائيات العامة
                self.stats['total_collected'] += 1
                self.stats['whatsapp_collected'] += 1
                if details.get('is_new', False):
                    self.stats['new_links_count'] += 1
                
                return link_info
            
            return None
            
        except Exception as e:
            logger.error(f"خطأ في معالجة رابط واتساب {url}: {e}")
            return None
    
    async def _check_collection_completion(self) -> bool:
        """التحقق من اكتمال الجمع"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            # ✅ الحصول على عدد المجموعات التي تمت معالجتها مؤخراً
            cursor = await db.conn.execute('''
                SELECT COUNT(DISTINCT source_group) 
                FROM links 
                WHERE date(collected_date) = date('now')
            ''')
            today_groups = (await cursor.fetchone())[0]
            
            # ✅ الحصول على عدد الروابط الجديدة اليوم
            cursor = await db.conn.execute('''
                SELECT COUNT(*) 
                FROM links 
                WHERE date(collected_date) = date('now') AND is_new = 1
            ''')
            today_new_links = (await cursor.fetchone())[0]
            
            # ✅ إذا لم يتم جمع روابط جديدة مؤخراً، نعتبر الجمع مكتملاً
            if today_new_links == 0 and today_groups > 20:
                logger.info(f"✅ يبدو أن الجمع مكتمل: {today_groups} مجموعة معالجة اليوم، {today_new_links} روابط جديدة")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"خطأ في التحقق من اكتمال الجمع: {e}")
            return False
    
    async def _send_completion_notification(self):
        """إرسال إشعار اكتمال الجمع"""
        try:
            if self.stats['completion_notification_sent']:
                return
            
            db = await EnhancedDatabaseManager.get_instance()
            
            # ✅ الحصول على عدد الروابط الجديدة
            new_links_count = await db.get_links_count(only_new=True)
            
            # ✅ الحصول على جميع المستخدمين المسموح لهم
            cursor = await db.conn.execute('''
                SELECT user_id FROM bot_users 
                WHERE user_id IN (SELECT value FROM json_each(?))
                OR (SELECT COUNT(*) FROM json_each(?)) = 0
            ''', (
                json.dumps(list(Config.ADMIN_USER_IDS)),
                json.dumps(list(Config.ADMIN_USER_IDS))
            ))
            
            users = await cursor.fetchall()
            
            # ✅ إرسال إشعار لكل مستخدم
            for user_row in users:
                user_id = user_row[0]
                
                notification_message = (
                    f"✅ **تم اكتمال جمع جميع الرواق المتاحة!**\n\n"
                    f"**إحصائيات الجمع:**\n"
                    f"• الروابط المجمعة: {self.stats['total_collected']:,}\n"
                    f"• تيليجرام: {self.stats['telegram_collected']:,}\n"
                    f"• واتساب: {self.stats['whatsapp_collected']:,}\n"
                    f"• الروابط الجديدة: {new_links_count:,}\n"
                    f"• المجموعات المعالجة: {self.stats['groups_processed']:,}\n\n"
                    f"**يمكنك الآن تصدير الروابط الجديدة باستخدام:**\n"
                    f"/export_new - لتصدير الروابط الجديدة فقط\n"
                    f"/export_all - لتصدير جميع الروابط\n\n"
                    f"سيستمر البوت في مراقبة المجموعات لاكتشاف روابط جديدة."
                )
                
                await db.add_notification(
                    user_id=user_id,
                    notification_type='collection_completed',
                    message=notification_message,
                    metadata={
                        'total_collected': self.stats['total_collected'],
                        'telegram_collected': self.stats['telegram_collected'],
                        'whatsapp_collected': self.stats['whatsapp_collected'],
                        'new_links_count': new_links_count,
                        'timestamp': datetime.now().isoformat()
                    }
                )
            
            self.stats['completion_notification_sent'] = True
            logger.info("✅ تم إرسال إشعارات اكتمال الجمع")
            
        except Exception as e:
            logger.error(f"خطأ في إرسال إشعار اكتمال الجمع: {e}")
    
    async def _mark_old_links_as_collected(self):
        """وضع علامة على الروابط القديمة بأنها مجمعة"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            await db.mark_links_as_old()
            logger.info("✅ تم وضع علامة على جميع الروابط بأنها قديمة")
        except Exception as e:
            logger.error(f"خطأ في وضع علامة على الروابط: {e}")
    
    async def _save_stats(self):
        """حفظ الإحصائيات"""
        try:
            stats_file = "collection_stats.json"
            stats_data = {
                'stats': self.stats,
                'detailed_stats': self.detailed_stats,
                'last_updated': datetime.now().isoformat()
            }
            
            async with aiofiles.open(stats_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(stats_data, indent=2, ensure_ascii=False))
            
        except Exception as e:
            logger.error(f"خطأ في حفظ الإحصائيات: {e}")
    
    def get_status(self) -> Dict:
        """الحصول على حالة الجمع"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'collection_completed': self.collection_completed,
            'stats': self.stats.copy(),
            'detailed_stats': self.detailed_stats.copy()
        }
    
    async def pause(self):
        """إيقاف الجمع مؤقتاً"""
        self.paused = True
        self.stats['collection_status'] = 'paused'
        logger.info("⏸️ تم إيقاف الجمع مؤقتاً")
    
    async def resume(self):
        """استئناف الجمع"""
        self.paused = False
        self.stats['collection_status'] = 'collecting'
        logger.info("▶️ تم استئناف الجمع")
    
    async def stop(self):
        """إيقاف الجمع"""
        self.stop_requested = True
        self.stats['collection_status'] = 'stopping'
        logger.info("⏹️ تم طلب إيقاف الجمع")
        
        # انتظار حتى تتوقف المهمة
        if self.collection_task:
            try:
                await asyncio.wait_for(self.collection_task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("مهلة انتظار إيقاف مهمة الجمع")
        
        self.active = False
        self.stats['collection_status'] = 'stopped'

# ======================
# Encryption Manager - مدير التشفير
# ======================

class EncryptionManager:
    """مدير التشفير"""
    
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
        """تشفير البيانات"""
        try:
            encrypted = self.cipher.encrypt(data.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"خطأ في التشفير: {e}")
            return data
    
    def decrypt(self, encrypted_data: str) -> str:
        """فك تشفير البيانات"""
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
    """بوت تليجرام الرئيسي"""
    
    def __init__(self):
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        self.collection_manager = SmartCollectionManager()
        
        self._setup_handlers()
        
        self.user_states = {}
    
    def _setup_handlers(self):
        """إعداد معالجات البوت"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("export_new", self.export_new_command))
        self.app.add_handler(CommandHandler("export_all", self.export_all_command))
        self.app.add_handler(CommandHandler("backup", self.backup_command))
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        self.app.add_handler(CommandHandler("addsession", self.add_session_command))
        self.app.add_handler(CommandHandler("test_collect", self.test_collect_command))
        self.app.add_handler(CommandHandler("force_collect", self.force_collect_command))
        self.app.add_handler(CommandHandler("quick_collect", self.quick_collect_command))
        self.app.add_handler(CommandHandler("notifications", self.notifications_command))
        self.app.add_handler(CommandHandler("detailed_stats", self.detailed_stats_command))
        
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_message
        ))
        
        self.app.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /start"""
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
        
        # ✅ التحقق من وجود إشعارات جديدة
        notifications = await db.get_unread_notifications(user.id)
        has_notifications = len(notifications) > 0
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء الجمع الذكي", callback_data="start_collect"),
             InlineKeyboardButton("⚡ جمع سريع", callback_data="quick_collect")],
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("👥 الجلسات", callback_data="show_sessions")],
            [InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_links"),
             InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")],
            [InlineKeyboardButton("🔔 الإشعارات" + (" 🔴" if has_notifications else ""), callback_data="show_notifications"),
             InlineKeyboardButton("📈 إحصائيات مفصلة", callback_data="detailed_stats")]
        ])
        
        welcome_text = (
            f"🤖 **مرحباً {user.first_name}!**\n\n"
            "**بوت جمع الرواقات الذكي حسب المتطلبات**\n\n"
            "✅ **المتطلبات المطبقة:**\n"
            "1. ✅ جمع روابط تيليجرام النشطة فقط كما هي\n"
            "2. ✅ تجميع المجموعات ذات الأعضاء فقط\n"
            "3. ✅ تجاهل (بوتات + قنوات + t.me/me + مجموعات مشتركين)\n"
            "4. ✅ منع التكرار بين الجلسات\n"
            "5. ✅ رسالة واحدة فقط من كل مجموعة\n"
            "6. ✅ تيليجرام: آخر 5 سنوات فقط\n"
            "7. ✅ واتساب: آخر 60 يوماً فقط\n\n"
            "✅ **المميزات:**\n"
            "• إشعار عند اكتمال الجمع\n"
            "• قسم للروابط الجديدة\n"
            "• إحصائيات مفصلة\n"
            "• منع التكرار التلقائي\n\n"
            "**🚀 اختر من الأزرار أدناه لبدء الجمع الذكي!**"
        )
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /status"""
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
            f"**📊 حالة النظام حسب المتطلبات - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**\n\n"
            "**حالة الجمع:**\n"
        )
        
        if status['active']:
            if status['paused']:
                status_text += "⏸️ **موقف مؤقتاً**\n"
            elif status['stop_requested']:
                status_text += "🛑 **جاري الإيقاف...**\n"
            elif status['collection_completed']:
                status_text += "✅ **مكتمل - انتظار روابط جديدة**\n"
            else:
                status_text += "🔄 **نشط - جمع ذكي حسب المتطلبات**\n"
        else:
            status_text += "🛑 **متوقف**\n"
        
        status_text += f"**الحالة التفصيلية:** {status['stats']['collection_status']}\n\n"
        
        # معلومات الجمع الحالية
        if status['active'] and not status['paused'] and not status['collection_completed']:
            status_text += f"**💼 الجمع الحالي:**\n"
            if status['stats']['current_session']:
                status_text += f"• الجلسة: {status['stats']['current_session']}\n"
            if status['stats']['current_group']:
                status_text += f"• المجموعة: {status['stats']['current_group']}\n"
            status_text += "\n"
        
        status_text += (
            f"**إحصائيات الجمع الذكي:**\n"
            f"• 📦 المجموع المجمع: {status['stats']['total_collected']:,}\n"
            f"• 📢 تيليجرام: {status['stats']['telegram_collected']:,}\n"
            f"• 📱 واتساب: {status['stats']['whatsapp_collected']:,}\n"
            f"• ⭐ روابط جديدة: {status['stats']['new_links_count']:,}\n"
            f"• ⏭️ مصفاة: {status['stats']['filtered_count']:,}\n"
            f"• 👥 مجموعات معالجة: {status['stats']['groups_processed']:,}\n"
            f"• ⚡ جلسات مستخدمة: {status['stats']['sessions_used']}\n"
            f"• 🕒 آخر جمع: {status['stats']['last_collection_time'] or 'لم يبدأ'}\n\n"
            f"**إحصائيات قاعدة البيانات:**\n"
            f"• 🔗 إجمالي الروابط: {db_stats.get('total_links', 0):,}\n"
            f"• ⭐ روابط جديدة: {db_stats.get('new_links', 0):,}\n"
            f"• 👥 مجموعات أعضاء: {db_stats.get('member_groups', 0):,}\n"
            f"• 💼 جلسات نشطة: {db_stats.get('active_sessions', 0)}\n"
        )
        
        if 'today_stats' in db_stats:
            status_text += f"**إحصائيات اليوم:**\n"
            status_text += f"• مجمعة اليوم: {db_stats['today_stats']['total_collected']:,}\n"
            status_text += f"• جديدة اليوم: {db_stats['today_stats']['new_links_count']:,}\n\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_status"),
             InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("📤 تصدير الجديدة", callback_data="export_new"),
             InlineKeyboardButton("📊 إحصائيات مفصلة", callback_data="detailed_stats")],
            [InlineKeyboardButton("🔔 الإشعارات", callback_data="show_notifications"),
             InlineKeyboardButton("⚙️ الإعدادات", callback_data="show_settings")]
        ])
        
        await update.message.reply_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /stats"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        
        user_stats = await db.get_user_stats(user.id)
        
        stats_text = "**📈 إحصائيات النظام حسب المتطلبات**\n\n**إحصائيات المستخدم:**\n"
        
        if user_stats:
            stats_text += (
                f"• 🆔 المعرف: {user.id}\n"
                f"• 👤 الاسم: {user_stats.get('first_name', '')} {user_stats.get('last_name', '')}\n"
                f"• 📅 العضو منذ: {user_stats.get('added_date', 'غير معروف')}\n"
                f"• 📊 طلباتك: {user_stats.get('request_count', 0):,}\n"
                f"• 🔗 روابطك: {user_stats.get('total_links', 0):,}\n"
                f"• ⭐ روابطك الجديدة: {user_stats.get('new_links', 0):,}\n"
                f"• 💼 جلساتك: {user_stats.get('total_sessions', 0)}\n\n"
            )
        
        stats_text += (
            f"**إحصائيات النظام:**\n"
            f"• 🔗 إجمالي الروابط: {db_stats.get('total_links', 0):,}\n"
            f"• ⭐ روابط جديدة: {db_stats.get('new_links', 0):,}\n"
            f"• 👥 مجموعات أعضاء: {db_stats.get('member_groups', 0):,}\n"
            f"• 💼 جلسات نشطة: {db_stats.get('active_sessions', 0)}\n"
            f"• 👥 المستخدمين: {db_stats.get('total_users', 0)}\n"
        )
        
        # إحصائيات المنصات
        if 'links_by_platform' in db_stats:
            stats_text += "\n**توزيع المنصات:**\n"
            for platform, count in db_stats['links_by_platform'].items():
                stats_text += f"• {platform}: {count:,}\n"
        
        if 'filtered_links' in db_stats and db_stats['filtered_links']:
            stats_text += "\n**الروابط المصفاة:**\n"
            for reason, count in db_stats['filtered_links'].items():
                stats_text += f"• {reason}: {count:,}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 إحصائيات مفصلة", callback_data="detailed_stats"),
             InlineKeyboardButton("🔄 تحديث", callback_data="refresh_stats")]
        ])
        
        await update.message.reply_text(stats_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def detailed_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /detailed_stats"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        status = self.collection_manager.get_status()
        detailed_stats = status['detailed_stats']
        
        stats_text = "**📊 الإحصائيات المفصلة حسب المتطلبات**\n\n"
        
        stats_text += "**📢 روابط تيليجرام:**\n"
        stats_text += f"• مجموعات عامة: {detailed_stats['telegram']['public_groups']:,}\n"
        stats_text += f"• مجموعات خاصة: {detailed_stats['telegram']['private_groups']:,}\n"
        stats_text += f"• روابط انضمام: {detailed_stats['telegram']['join_links']:,}\n"
        stats_text += f"• روابط addlist: {detailed_stats['telegram']['addlist_links']:,}\n"
        stats_text += f"• روابط رسائل: {detailed_stats['telegram']['message_links']:,}\n"
        stats_text += f"• روابط نشطة: {detailed_stats['telegram']['active_links']:,}\n"
        stats_text += f"• روابط منتهية: {detailed_stats['telegram']['expired_links']:,}\n\n"
        
        stats_text += "**📱 روابط واتساب:**\n"
        stats_text += f"• روابط نشطة: {detailed_stats['whatsapp']['active_links']:,}\n"
        stats_text += f"• روابط منتهية: {detailed_stats['whatsapp']['expired_links']:,}\n\n"
        
        stats_text += "**⏭️ الروابط المصفاة:**\n"
        stats_text += f"• بوتات: {detailed_stats['filtered']['bots']:,}\n"
        stats_text += f"• قنوات: {detailed_stats['filtered']['channels']:,}\n"
        stats_text += f"• روابط t.me/me: {detailed_stats['filtered']['me_links']:,}\n"
        stats_text += f"• مجموعات مشتركين: {detailed_stats['filtered']['subscription_groups']:,}\n"
        stats_text += f"• بدون أعضاء: {detailed_stats['filtered']['no_members']:,}\n"
        stats_text += f"• منتهية: {detailed_stats['filtered']['expired']:,}\n"
        stats_text += f"• تيليجرام قديم: {detailed_stats['filtered']['old_telegram']:,}\n"
        stats_text += f"• واتساب قديم: {detailed_stats['filtered']['old_whatsapp']:,}\n\n"
        
        stats_text += "**⚙️ الإعدادات النشطة:**\n"
        stats_text += f"• تجميع الروابط النشطة فقط: {'✅' if Config.COLLECT_ONLY_ACTIVE else '❌'}\n"
        stats_text += f"• تجميع مجموعات الأعضاء فقط: {'✅' if Config.COLLECT_MEMBER_GROUPS_ONLY else '❌'}\n"
        stats_text += f"• منع التكرار: {'✅' if Config.PREVENT_DUPLICATES else '❌'}\n"
        stats_text += f"• رسالة واحدة لكل مجموعة: {'✅' if Config.COLLECT_ONE_MESSAGE_PER_GROUP else '❌'}\n"
        stats_text += f"• تيليجرام من آخر: {Config.TELEGRAM_YEARS_BACK} سنوات\n"
        stats_text += f"• واتساب من آخر: {Config.WHATSAPP_DAYS_BACK} يوم\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="detailed_stats"),
             InlineKeyboardButton("📤 تصدير الجديدة", callback_data="export_new")]
        ])
        
        await update.message.reply_text(stats_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /sessions"""
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
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /export"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        total_links = await db.get_links_count()
        new_links = await db.get_links_count(only_new=True)
        
        if total_links == 0:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect"),
                 InlineKeyboardButton("⚡ جمع سريع", callback_data="quick_collect")]
            ])
            await update.message.reply_text(
                "❌ **لا توجد روابط للتصدير**\n\n"
                "يمكنك البدء في جمع الروابط باستخدام:\n"
                "• /collect - بدء الجمع الذكي\n"
                "• /quick_collect - جمع سريع من 5 مجموعات\n"
                "• /test_collect - اختبار الجمع على مجموعة",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⭐ الروابط الجديدة ({new_links:,})", callback_data="export_new"),
             InlineKeyboardButton("📢 تيليجرام فقط", callback_data="export_telegram")],
            [InlineKeyboardButton("📱 واتساب فقط", callback_data="export_whatsapp"),
             InlineKeyboardButton("👥 مجموعات الأعضاء", callback_data="export_member_groups")],
            [InlineKeyboardButton("📄 جميع الروابط", callback_data="export_all"),
             InlineKeyboardButton("📊 CSV كامل", callback_data="export_csv")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="export_links")]
        ])
        
        export_text = (
            f"**📤 تصدير الروابط حسب المتطلبات**\n\n"
            f"إجمالي الروابط المجمعة: **{total_links:,}**\n"
            f"الروابط الجديدة: **{new_links:,}** ⭐\n\n"
            "**خيارات التصدير:**\n"
            f"• ⭐ الروابط الجديدة فقط ({new_links:,} رابط)\n"
            "• 📢 روابط تيليجرام فقط\n"
            "• 📱 روابط واتساب فقط\n"
            "• 👥 مجموعات ذات أعضاء فقط\n"
            "• 📄 جميع الروابط (نصي)\n"
            "• 📊 CSV كامل المعلومات\n\n"
            "**ملاحظات:**\n"
            f"• الحد الأقصى للتصدير: {Config.MAX_EXPORT_LINKS:,} رابط\n"
            "• الروابط محفوظة كما هي دون تعديل\n"
            "• كل نوع تصدير منفصل\n"
            "• الروابط جاهزة للاستخدام المباشر"
        )
        
        await update.message.reply_text(export_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def export_new_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /export_new - تصدير الروابط الجديدة فقط"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        await update.message.reply_text("⭐ **جاري تحضير الروابط الجديدة...**")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            new_links = await db.get_new_links(limit=Config.MAX_EXPORT_LINKS)
            
            if not new_links:
                await update.message.reply_text("✅ **لا توجد روابط جديدة للتصدير**")
                return
            
            # ✅ تجميع الروابط حسب المنصة
            telegram_links = []
            whatsapp_links = []
            
            for link in new_links:
                if link['platform'] == 'telegram':
                    telegram_links.append(link['original_url'])
                elif link['platform'] == 'whatsapp':
                    whatsapp_links.append(link['original_url'])
            
            total_links = len(new_links)
            
            # ✅ إنشاء الملفات
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            os.makedirs("exports", exist_ok=True)
            
            # ✅ ملف جميع الروابط الجديدة
            all_filename = f"new_links_{timestamp}.txt"
            all_filepath = os.path.join("exports", all_filename)
            
            with open(all_filepath, 'w', encoding='utf-8') as f:
                for link in new_links:
                    f.write(f"{link['original_url']}\n")
            
            # ✅ إرسال ملف جميع الروابط
            with open(all_filepath, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=all_filename,
                    caption=f"⭐ جميع الروابط الجديدة\nعدد الروابط: {total_links:,}\nتيليجرام: {len(telegram_links):,}\nواتساب: {len(whatsapp_links):,}"
                )
            
            # ✅ إنشاء ملف منفصل لتيليجرام إذا كان هناك روابط
            if telegram_links:
                telegram_filename = f"new_telegram_{timestamp}.txt"
                telegram_filepath = os.path.join("exports", telegram_filename)
                
                with open(telegram_filepath, 'w', encoding='utf-8') as f:
                    for link in telegram_links:
                        f.write(f"{link}\n")
                
                with open(telegram_filepath, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=telegram_filename,
                        caption=f"📢 روابط تيليجرام الجديدة\nعدد الروابط: {len(telegram_links):,}"
                    )
                
                try:
                    os.remove(telegram_filepath)
                except:
                    pass
            
            # ✅ إنشاء ملف منفصل لواتساب إذا كان هناك روابط
            if whatsapp_links:
                whatsapp_filename = f"new_whatsapp_{timestamp}.txt"
                whatsapp_filepath = os.path.join("exports", whatsapp_filename)
                
                with open(whatsapp_filepath, 'w', encoding='utf-8') as f:
                    for link in whatsapp_links:
                        f.write(f"{link}\n")
                
                with open(whatsapp_filepath, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=whatsapp_filename,
                        caption=f"📱 روابط واتساب الجديدة\nعدد الروابط: {len(whatsapp_links):,}\nمن آخر {Config.WHATSAPP_DAYS_BACK} يوماً فقط"
                    )
                
                try:
                    os.remove(whatsapp_filepath)
                except:
                    pass
            
            # ✅ وضع علامة على الروابط بأنها قديمة
            await db.mark_links_as_old()
            
            # ✅ حذف الملف الرئيسي
            try:
                os.remove(all_filepath)
            except:
                pass
            
            await update.message.reply_text(f"✅ **تم تصدير {total_links:,} رابط جديد**\n\nتم وضع علامة على جميع الروابط بأنها قديمة.")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الروابط الجديدة: {e}")
            await update.message.reply_text(f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def export_all_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /export_all"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        await update.message.reply_text("📦 **جاري تحضير جميع الروابط...**")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links(limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await update.message.reply_text("❌ لا توجد روابط للتصدير")
                return
            
            # حفظ في ملف نصي
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"all_links_{timestamp}.txt"
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
                    caption=f"📦 جميع الروابط (تيليجرام + واتساب)\nعدد الروابط: {len(links):,}\nجمعت حسب المتطلبات"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await update.message.reply_text(f"✅ تم تصدير {len(links):,} رابط")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير جميع الروابط: {e}")
            await update.message.reply_text(f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def notifications_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /notifications"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        notifications = await db.get_unread_notifications(user.id)
        
        if not notifications:
            await update.message.reply_text("✅ **لا توجد إشعارات جديدة**")
            return
        
        notifications_text = f"**🔔 الإشعارات الجديدة ({len(notifications)})**\n\n"
        
        for i, notification in enumerate(notifications, 1):
            notification_type = notification['notification_type']
            message = notification['message']
            created_at = notification['created_at']
            
            notifications_text += f"**{i}. {notification_type}**\n"
            notifications_text += f"الوقت: {created_at}\n"
            notifications_text += f"{message}\n\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ وضع علامة كمقروء", callback_data="mark_notifications_read"),
             InlineKeyboardButton("🔄 تحديث", callback_data="show_notifications")]
        ])
        
        await update.message.reply_text(notifications_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /collect"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        status = self.collection_manager.get_status()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء الجمع الذكي", callback_data="start_collect"),
             InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect"),
             InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status")],
            [InlineKeyboardButton("⚡ جمع سريع", callback_data="quick_collect"),
             InlineKeyboardButton("🧪 اختبار الجمع", callback_data="test_collection")]
        ])
        
        collect_text = "**🚀 إدارة عملية الجمع حسب المتطلبات**\n\n**الحالة الحالية:**\n"
        
        if status['active']:
            if status['paused']:
                collect_text += "⏸️ **موقف مؤقتاً**\n"
            elif status['collection_completed']:
                collect_text += "✅ **مكتمل - انتظار روابط جديدة**\n"
            else:
                collect_text += "🔄 **نشط - جمع ذكي حسب المتطلبات**\n"
        else:
            collect_text += "🛑 **متوقف**\n"
        
        collect_text += (
            f"\n**الإحصائيات:**\n"
            f"• الروابط المجمعة: {status['stats']['total_collected']:,}\n"
            f"• تيليجرام: {status['stats']['telegram_collected']:,}\n"
            f"• واتساب: {status['stats']['whatsapp_collected']:,}\n"
            f"• روابط جديدة: {status['stats']['new_links_count']:,}\n"
            f"• مصفاة: {status['stats']['filtered_count']:,}\n"
            f"• مجموعات معالجة: {status['stats']['groups_processed']:,}\n"
            f"• الأخطاء: {status['stats']['errors']:,}\n\n"
            "✅ **المتطلبات المطبقة:**\n"
            "1. روابط تيليجرام النشطة فقط كما هي\n"
            "2. مجموعات ذات أعضاء فقط\n"
            "3. تجاهل (بوتات + قنوات + t.me/me + مجموعات مشتركين)\n"
            "4. منع التكرار بين الجلسات\n"
            "5. رسالة واحدة فقط من كل مجموعة\n"
            f"6. تيليجرام: آخر {Config.TELEGRAM_YEARS_BACK} سنوات فقط\n"
            f"7. واتساب: آخر {Config.WHATSAPP_DAYS_BACK} يوماً فقط\n\n"
            f"**الإعدادات:**\n"
            f"• الرسائل لكل مجموعة: {Config.MESSAGES_PER_GROUP}\n"
            f"• الجلسات المتزامنة: {Config.MAX_CONCURRENT_SESSIONS}\n"
            f"• إشعار عند الاكتمال: ✅ مفعل"
        )
        
        await update.message.reply_text(collect_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def add_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /addsession"""
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
            f"• يمكنك إضافة حتى {Config.MAX_SESSIONS_PER_USER} جلسة\n"
            "• الجلسة يجب أن تكون نشطة\n"
            "• تستخدم فقط لجمع الروابط حسب المتطلبات"
        )
        
        await update.message.reply_text(add_text, parse_mode="Markdown")
    
    async def test_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /test_collect"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        await update.message.reply_text("🧪 **جاري اختبار الجمع حسب المتطلبات على مجموعة واحدة...**")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=1)
            
            if not sessions:
                await update.message.reply_text("❌ لا توجد جلسات نشطة للاختبار")
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
            
            # اختبار الجمع من أول مجموعة
            collected = []
            filtered = []
            message_links_count = 0
            
            async for dialog in client.iter_dialogs(limit=5):
                try:
                    entity = dialog.entity
                    
                    # تخطي الرسائل الخاصة
                    if not hasattr(entity, 'title'):
                        continue
                    
                    group_title = getattr(entity, 'title', 'غير معروف')
                    
                    await update.message.reply_text(f"🔍 اختبار المجموعة: {group_title}")
                    
                    # ✅ جمع روابط تيليجرام
                    telegram_links = await TelegramLinkValidator.extract_links_from_group(client, entity, max_messages=10)
                    
                    # ✅ جمع روابط واتساب
                    whatsapp_links = await WhatsAppLinkValidator.extract_links_from_messages(client, entity, max_messages=10)
                    
                    # ✅ معالجة الروابط
                    for link_data in telegram_links + whatsapp_links:
                        url = link_data['url']
                        url_info = EnhancedLinkProcessor.extract_url_info(url)
                        
                        # ✅ التحقق مما إذا كان يجب جمع الرابط
                        should_collect, reason = EnhancedLinkProcessor.should_collect_link(url_info)
                        
                        if not should_collect:
                            filtered.append({
                                'url': url,
                                'reason': reason,
                                'platform': url_info['platform']
                            })
                            continue
                        
                        # ✅ التحقق الإضافي للتليجرام
                        if url_info['platform'] == 'telegram':
                            validation_result = await TelegramLinkValidator.validate_telegram_link(client, url)
                            if not validation_result['is_valid']:
                                filtered.append({
                                    'url': url,
                                    'reason': validation_result.get('reason', 'غير معروف'),
                                    'platform': 'telegram'
                                })
                                continue
                        
                        # ✅ التحقق الإضافي للواتساب
                        elif url_info['platform'] == 'whatsapp':
                            validation_result = await WhatsAppLinkValidator.validate_whatsapp_link(url)
                            if not validation_result['is_valid']:
                                filtered.append({
                                    'url': url,
                                    'reason': validation_result.get('reason', 'غير معروف'),
                                    'platform': 'whatsapp'
                                })
                                continue
                        
                        # ✅ إضافة الرابط
                        link_item = {
                            'original_url': url,
                            'session_id': session.get('id'),
                            'added_by_user': user.id,
                            'source': link_data.get('source', ''),
                            'message_date': link_data.get('message_date', ''),
                            'source_group': group_title,
                            'is_new_collection': True
                        }
                        
                        success, message, _ = await db.add_link(link_item)
                        if success:
                            collected.append({
                                'url': url,
                                'platform': url_info['platform']
                            })
                    
                    # اختبار مجموعة واحدة فقط
                    break
                    
                except Exception as e:
                    logger.debug(f"خطأ في اختبار المجموعة: {e}")
                    continue
            
            await client.disconnect()
            
            if collected or filtered:
                result_text = f"✅ **اكتمل الاختبار بنجاح!**\n\n"
                
                if collected:
                    result_text += f"**الروابط المجمعة ({len(collected)}):**\n"
                    telegram_count = sum(1 for item in collected if item['platform'] == 'telegram')
                    whatsapp_count = sum(1 for item in collected if item['platform'] == 'whatsapp')
                    result_text += f"• تيليجرام: {telegram_count}\n"
                    result_text += f"• واتساب: {whatsapp_count}\n\n"
                
                if filtered:
                    result_text += f"**الروابط المصفاة ({len(filtered)}):**\n"
                    filter_reasons = defaultdict(int)
                    for item in filtered:
                        filter_reasons[item['reason']] += 1
                    
                    for reason, count in filter_reasons.items():
                        result_text += f"• {reason}: {count}\n"
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 بدء الجمع الذكي", callback_data="start_collect"),
                     InlineKeyboardButton("📤 تصدير العينة", callback_data="export_test")]
                ])
                
                await update.message.reply_text(
                    result_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "❌ **لم يتم العثور على رواق في المجموعة**\n\n"
                    "يمكنك إعادة المحاولة أو البدء في الجمع الذكي.",
                    parse_mode="Markdown"
                )
            
        except Exception as e:
            logger.error(f"خطأ في اختبار الجمع: {e}")
            await update.message.reply_text(f"❌ خطأ في الاختبار: {str(e)[:200]}")
    
    async def force_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /force_collect"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        await update.message.reply_text("🚀 **بدء جمع فوري حسب المتطلبات من جميع المجموعات...**")
        
        try:
            # بدء الجمع
            await self.collection_manager.start_collection()
            
            await asyncio.sleep(3)
            
            status = self.collection_manager.get_status()
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status"),
                 InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")]
            ])
            
            await update.message.reply_text(
                f"✅ **بدأ الجمع الفوري بنجاح!**\n\n"
                f"**الحالة:** {status['stats']['collection_status']}\n"
                f"**جاري جمع الروابط حسب المتطلبات...**\n\n"
                f"✅ **المتطلبات المطبقة:**\n"
                f"1. روابط تيليجرام النشطة فقط كما هي\n"
                f"2. مجموعات ذات أعضاء فقط\n"
                f"3. تجاهل (بوتات + قنوات + t.me/me + مجموعات مشتركين)\n"
                f"4. منع التكرار بين الجلسات\n"
                f"5. رسالة واحدة فقط من كل مجموعة\n"
                f"6. تيليجرام: آخر {Config.TELEGRAM_YEARS_BACK} سنوات فقط\n"
                f"7. واتساب: آخر {Config.WHATSAPP_DAYS_BACK} يوماً فقط\n\n"
                f"سيتم إعلامك عند اكتمال الجمع.",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"خطأ في بدء الجمع الفوري: {e}")
            await update.message.reply_text(f"❌ خطأ في بدء الجمع: {str(e)[:200]}")
    
    async def quick_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /quick_collect"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        await update.message.reply_text("⚡ **بدء جمع سريع حسب المتطلبات من 5 مجموعات...**")
        
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
            
            # جمع الروابط من 5 مجموعات
            collected = []
            filtered = []
            groups_processed = 0
            
            async for dialog in client.iter_dialogs(limit=10):
                try:
                    entity = dialog.entity
                    
                    # تخطي الرسائل الخاصة
                    if not hasattr(entity, 'title'):
                        continue
                    
                    groups_processed += 1
                    group_title = getattr(entity, 'title', 'غير معروف')
                    
                    await update.message.reply_text(f"🔍 جمع من المجموعة {groups_processed}: {group_title}")
                    
                    # ✅ جمع روابط تيليجرام
                    telegram_links = await TelegramLinkValidator.extract_links_from_group(client, entity, max_messages=20)
                    
                    # ✅ جمع روابط واتساب
                    whatsapp_links = await WhatsAppLinkValidator.extract_links_from_messages(client, entity, max_messages=20)
                    
                    # ✅ معالجة الروابط
                    for link_data in telegram_links + whatsapp_links:
                        url = link_data['url']
                        url_info = EnhancedLinkProcessor.extract_url_info(url)
                        
                        # ✅ التحقق مما إذا كان يجب جمع الرابط
                        should_collect, reason = EnhancedLinkProcessor.should_collect_link(url_info)
                        
                        if not should_collect:
                            filtered.append({
                                'url': url,
                                'reason': reason,
                                'platform': url_info['platform']
                            })
                            continue
                        
                        # ✅ التحقق الإضافي للتليجرام
                        if url_info['platform'] == 'telegram':
                            validation_result = await TelegramLinkValidator.validate_telegram_link(client, url)
                            if not validation_result['is_valid']:
                                filtered.append({
                                    'url': url,
                                    'reason': validation_result.get('reason', 'غير معروف'),
                                    'platform': 'telegram'
                                })
                                continue
                        
                        # ✅ التحقق الإضافي للواتساب
                        elif url_info['platform'] == 'whatsapp':
                            validation_result = await WhatsAppLinkValidator.validate_whatsapp_link(url)
                            if not validation_result['is_valid']:
                                filtered.append({
                                    'url': url,
                                    'reason': validation_result.get('reason', 'غير معروف'),
                                    'platform': 'whatsapp'
                                })
                                continue
                        
                        # ✅ إضافة الرابط
                        link_item = {
                            'original_url': url,
                            'session_id': session.get('id'),
                            'added_by_user': user.id,
                            'source': link_data.get('source', ''),
                            'message_date': link_data.get('message_date', ''),
                            'source_group': group_title,
                            'is_new_collection': True
                        }
                        
                        success, message, _ = await db.add_link(link_item)
                        if success:
                            collected.append({
                                'url': url,
                                'platform': url_info['platform']
                            })
                    
                    # توقف بعد 5 مجموعات
                    if groups_processed >= 5:
                        break
                    
                    # تأخير بين المجموعات
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.debug(f"خطأ في الجمع السريع من المجموعة: {e}")
                    continue
            
            await client.disconnect()
            
            # تحديث إحصائيات الجلسة
            await db.conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, last_success = CURRENT_TIMESTAMP, total_uses = total_uses + 1, total_links = total_links + ? WHERE id = ?",
                (len(collected), session['id'])
            )
            await db.conn.commit()
            
            if collected or filtered:
                result_text = f"✅ **اكتمل الجمع السريع بنجاح!**\n\n"
                result_text += f"**الإحصائيات:**\n"
                result_text += f"• المجموعات المعالجة: {groups_processed}\n"
                
                if collected:
                    telegram_count = sum(1 for item in collected if item['platform'] == 'telegram')
                    whatsapp_count = sum(1 for item in collected if item['platform'] == 'whatsapp')
                    result_text += f"• الروابط المجمعة: {len(collected)}\n"
                    result_text += f"  - تيليجرام: {telegram_count}\n"
                    result_text += f"  - واتساب: {whatsapp_count}\n"
                
                if filtered:
                    result_text += f"• الروابط المصفاة: {len(filtered)}\n"
                    
                    # عرض أسباب التصفية
                    filter_reasons = defaultdict(int)
                    for item in filtered:
                        filter_reasons[item['reason']] += 1
                    
                    if filter_reasons:
                        result_text += "\n**أسباب التصفية:**\n"
                        for reason, count in filter_reasons.items():
                            result_text += f"• {reason}: {count}\n"
                
                result_text += f"\n• الجلسة: {session_name}\n\n"
                result_text += "**يمكنك الآن:**\n"
                result_text += "• بدء الجمع الذكي من جميع المجموعات\n"
                result_text += "• تصدير الروابط المجمعة\n"
                result_text += "• الاستمرار في الجمع"
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 بدء الجمع الذكي", callback_data="start_collect"),
                     InlineKeyboardButton("📤 تصدير", callback_data="export_links")]
                ])
                
                await update.message.reply_text(
                    result_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "❌ **لم يتم العثور على رواق في المجموعات**\n\n"
                    "يمكنك إعادة المحاولة أو إضافة جلسة جديدة.",
                    parse_mode="Markdown"
                )
            
        except Exception as e:
            logger.error(f"خطأ في الجمع السريع: {e}")
            await update.message.reply_text(f"❌ خطأ في الجمع السريع: {str(e)[:200]}")
    
    async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /backup"""
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
        
        backup_text = (
            "**💾 إدارة النسخ الاحتياطية**\n\n"
            "**المميزات:**\n"
            "• نسخ احتياطي تلقائي\n"
            "• حفظ بيانات الجلسات والروابط\n"
            "• استعادة البيانات عند الحاجة\n"
            "• تدوير تلقائي للنسخ القديمة\n\n"
            f"**الإعدادات:**\n"
            f"• عدد النسخ المحفوظة: {Config.MAX_BACKUPS}\n"
            f"• النسخ التلقائية: {'✅ مفعل' if Config.BACKUP_ENABLED else '❌ معطل'}\n\n"
            "**الأوامر:**\n"
            "• إنشاء نسخة يدوية\n"
            "• عرض قائمة النسخ\n"
            "• تدوير النسخ القديمة"
        )
        
        await update.message.reply_text(backup_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة استعلامات الاستدعاء"""
        query = update.callback_query
        await query.answer()
        
        # استخراج معلومات المستخدم من الاستعلام
        user = query.from_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await self._edit_message_safe(query, "❌ غير مصرح لك بالوصول")
                return
        
        data = query.data
        
        try:
            if data == "detailed_stats":
                await self._handle_detailed_stats(query)
            elif data == "export_new":
                await self._handle_export_new(query)
            elif data == "export_member_groups":
                await self._handle_export_member_groups(query)
            elif data == "start_collect":
                await self._handle_start_collect(query)
            elif data == "pause_collect":
                await self._handle_pause_collect(query)
            elif data == "stop_collect":
                await self._handle_stop_collect(query)
            elif data == "collect_status":
                await self._handle_collect_status(query)
            elif data == "quick_collect":
                await self._handle_quick_collect(query)
            elif data == "test_collection":
                await self._handle_test_collection(query)
            elif data == "add_session":
                await self._handle_add_session(query)
            elif data == "show_sessions":
                await self._handle_show_sessions(query)
            elif data == "show_stats":
                await self._handle_show_stats(query)
            elif data == "show_notifications":
                await self._handle_show_notifications(query)
            elif data == "mark_notifications_read":
                await self._handle_mark_notifications_read(query)
            elif data == "export_links":
                await self._handle_export_links(query)
            elif data == "export_telegram":
                await self._handle_export_telegram(query)
            elif data == "export_whatsapp":
                await self._handle_export_whatsapp(query)
            elif data == "export_all":
                await self._handle_export_all(query)
            elif data == "export_csv":
                await self._handle_export_csv(query)
            elif data == "export_test":
                await self._handle_export_test(query)
            elif data == "create_backup":
                await self._handle_create_backup(query)
            elif data == "list_backups":
                await self._handle_list_backups(query)
            elif data == "rotate_backups":
                await self._handle_rotate_backups(query)
            elif data == "refresh_status":
                await self._handle_refresh_status(query)
            elif data == "refresh_stats":
                await self._handle_refresh_stats(query)
            elif data == "refresh_sessions":
                await self._handle_refresh_sessions(query)
            elif data == "show_settings":
                await self._handle_show_settings(query)
            elif data == "delete_session":
                await self._handle_delete_session(query)
            elif data.startswith("delete_session_"):
                await self._handle_delete_session_confirm(query, data)
            else:
                await self._edit_message_safe(query, "❌ أمر غير معروف")
        
        except Exception as e:
            logger.error(f"خطأ في معالجة الاستدعاء: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _edit_message_safe(self, query, text, reply_markup=None, parse_mode="Markdown"):
        """تعديل الرسالة بأمان مع معالجة الأخطاء"""
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
    
    async def _handle_detailed_stats(self, query):
        """معالجة إحصائيات مفصلة"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.detailed_stats_command(mock_update, None)
    
    async def _handle_export_new(self, query):
        """معالجة تصدير الروابط الجديدة"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.export_new_command(mock_update, None)
    
    async def _handle_export_member_groups(self, query):
        """معالجة تصدير مجموعات الأعضاء"""
        await self._edit_message_safe(query, "⏳ جاري تحضير مجموعات الأعضاء...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links({'only_member_groups': True}, limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد مجموعات أعضاء للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"member_groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
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
                    caption=f"👥 مجموعات الأعضاء\nعدد الروابط: {len(links):,}"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await self._edit_message_safe(query, f"✅ تم تصدير {len(links):,} مجموعة أعضاء")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير مجموعات الأعضاء: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_start_collect(self, query):
        """معالجة بدء الجمع"""
        if self.collection_manager.active:
            await self._edit_message_safe(query, "⏳ الجمع يعمل بالفعل")
            return
        
        # بدء مهمة الجمع الذكية
        await self.collection_manager.start_collection()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status"),
             InlineKeyboardButton("⭐ تصدير الجديدة", callback_data="export_new")]
        ])
        
        await self._edit_message_safe(
            query,
            "🚀 **بدأ الجمع الذكي حسب المتطلبات بنجاح!**\n\n"
            "✅ **المتطلبات المطبقة:**\n"
            "1. روابط تيليجرام النشطة فقط كما هي\n"
            "2. مجموعات ذات أعضاء فقط\n"
            "3. تجاهل (بوتات + قنوات + t.me/me + مجموعات مشتركين)\n"
            "4. منع التكرار بين الجلسات\n"
            "5. رسالة واحدة فقط من كل مجموعة\n"
            f"6. تيليجرام: آخر {Config.TELEGRAM_YEARS_BACK} سنوات فقط\n"
            f"7. واتساب: آخر {Config.WHATSAPP_DAYS_BACK} يوماً فقط\n\n"
            "**تفاصيل:**\n"
            "• جاري جمع الروابط من جميع الجلسات\n"
            "• جاري جمع الروابط من جميع المجموعات\n"
            "• جاري جمع الروابط من جميع الرسائل\n"
            "• الروابط تمر بمراحل تحقق متقدمة\n"
            "• الروابط تحفظ تلقائياً في قاعدة البيانات\n"
            "• يمكنك التصدير في أي وقت\n\n"
            "⏳ **سيتم إعلامك عند اكتمال الجمع**",
            reply_markup=keyboard
        )
    
    async def _handle_pause_collect(self, query):
        """معالجة إيقاف الجمع مؤقتاً"""
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
            "⏸️ **تم إيقاف الجمع مؤقتاً**\n\n"
            "يمكنك استئناف الجمع في أي وقت.\n"
            "الجلسات تبقى نشطة.\n\n"
            "**الإحصائيات الحالية:**\n"
            f"• الروابط المجمعة: {self.collection_manager.stats['total_collected']:,}\n"
            f"• تيليجرام: {self.collection_manager.stats['telegram_collected']:,}\n"
            f"• واتساب: {self.collection_manager.stats['whatsapp_collected']:,}\n"
            f"• روابط جديدة: {self.collection_manager.stats['new_links_count']:,}\n"
            f"• مجموعات معالجة: {self.collection_manager.stats['groups_processed']:,}",
            reply_markup=keyboard
        )
    
    async def _handle_stop_collect(self, query):
        """معالجة إيقاف الجمع"""
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
            "⏹️ **تم إيقاف الجمع الذكي**\n\n"
            "توقفت عملية الجمع بنجاح.\n"
            "تم حفظ جميع الروابط المجمعة.\n\n"
            "**الإحصائيات النهائية:**\n"
            f"• إجمالي الروابط: {self.collection_manager.stats['total_collected']:,}\n"
            f"• تيليجرام: {self.collection_manager.stats['telegram_collected']:,}\n"
            f"• واتساب: {self.collection_manager.stats['whatsapp_collected']:,}\n"
            f"• روابط جديدة: {self.collection_manager.stats['new_links_count']:,}\n"
            f"• مجموعات معالجة: {self.collection_manager.stats['groups_processed']:,}",
            reply_markup=keyboard
        )
    
    async def _handle_collect_status(self, query):
        """معالجة حالة الجمع"""
        status = self.collection_manager.get_status()
        
        status_text = (
            f"**📊 حالة الجمع حسب المتطلبات**\n\n"
            f"**الحالة:** {'🔄 نشط - جمع ذكي' if status['active'] else '🛑 متوقف'}\n"
            f"**الإيقاف المؤقت:** {'⏸️ نعم' if status['paused'] else '▶️ لا'}\n"
            f"**طلب الإيقاف:** {'✅ نعم' if status['stop_requested'] else '❌ لا'}\n"
            f"**اكتمال الجمع:** {'✅ نعم' if status['collection_completed'] else '❌ لا'}\n\n"
            f"**الإحصائيات:**\n"
            f"• الروابط المجمعة: {status['stats']['total_collected']:,}\n"
            f"• تيليجرام: {status['stats']['telegram_collected']:,}\n"
            f"• واتساب: {status['stats']['whatsapp_collected']:,}\n"
            f"• روابط جديدة: {status['stats']['new_links_count']:,}\n"
            f"• مصفاة: {status['stats']['filtered_count']:,}\n"
            f"• مجموعات معالجة: {status['stats']['groups_processed']:,}\n"
            f"• الأخطاء: {status['stats']['errors']:,}\n"
            f"• الجلسات المستخدمة: {status['stats']['sessions_used']}\n"
            f"• آخر جمع: {status['stats']['last_collection_time'] or 'لم يبدأ'}\n"
            f"• حالة التفصيلية: {status['stats']['collection_status']}"
        )
        
        if status['stats']['filter_reasons']:
            status_text += "\n\n**أسباب التصفية:**\n"
            for reason, count in status['stats']['filter_reasons'].items():
                status_text += f"• {reason}: {count:,}\n"
        
        await self._edit_message_safe(query, status_text)
    
    async def _handle_quick_collect(self, query):
        """معالجة الجمع السريع"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.quick_collect_command(mock_update, None)
    
    async def _handle_test_collection(self, query):
        """معالجة اختبار الجمع"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.test_collect_command(mock_update, None)
    
    async def _handle_add_session(self, query):
        """معالجة إضافة جلسة"""
        from_user = query.from_user
        self.user_states[from_user.id] = {'waiting_for_session': True}
        
        add_text = (
            f"**➕ إضافة جلسة جديدة**\n\n"
            f"**أرسل كود الجلسة الآن:**\n"
            f"(يمكنك نسخ الكود كاملاً وإرساله)\n\n"
            f"**ملاحظات:**\n"
            f"• الجلسة ستخزن مشفرة\n"
            f"• يمكنك إضافة حتى {Config.MAX_SESSIONS_PER_USER} جلسة\n"
            f"• الجلسة يجب أن تكون نشطة\n"
            f"• تستخدم فقط لجمع الروابط حسب المتطلبات"
        )
        
        await self._edit_message_safe(query, add_text)
    
    async def _handle_show_sessions(self, query):
        """معالجة عرض الجلسات"""
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
            links_collected = session.get('total_links', 0)
            
            sessions_text += f"**{i}. {display_name}** (@{username}) - استخدامات: {uses} - روابط: {links_collected:,}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("🗑️ حذف جلسة", callback_data="delete_session")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_sessions")]
        ])
        
        await self._edit_message_safe(query, sessions_text, reply_markup=keyboard)
    
    async def _handle_show_stats(self, query):
        """معالجة عرض الإحصائيات"""
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        
        stats_text = (
            f"**📈 إحصائيات النظام حسب المتطلبات**\n\n"
            f"**إحصائيات قاعدة البيانات:**\n"
            f"• 🔗 إجمالي الروابط: {db_stats.get('total_links', 0):,}\n"
            f"• ⭐ روابط جديدة: {db_stats.get('new_links', 0):,}\n"
            f"• 👥 مجموعات أعضاء: {db_stats.get('member_groups', 0):,}\n"
            f"• 💼 الجلسات النشطة: {db_stats.get('active_sessions', 0)}\n"
            f"• 👥 المستخدمين: {db_stats.get('total_users', 0)}\n"
            f"• نسبة النمو: {((db_stats.get('today_links', 0)/db_stats.get('total_links', 1))*100 if db_stats.get('total_links', 0) > 0 else 0):.1f}%\n\n"
            f"**توزيع المنصات:**\n"
        )
        
        for platform, count in db_stats.get('links_by_platform', {}).items():
            stats_text += f"• {platform}: {count:,}\n"
        
        if 'filtered_links' in db_stats and db_stats['filtered_links']:
            stats_text += "\n**الروابط المصفاة:**\n"
            for reason, count in db_stats['filtered_links'].items():
                stats_text += f"• {reason}: {count:,}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="show_stats"),
             InlineKeyboardButton("📈 إحصائيات مفصلة", callback_data="detailed_stats")]
        ])
        
        await self._edit_message_safe(query, stats_text, reply_markup=keyboard)
    
    async def _handle_show_notifications(self, query):
        """معالجة عرض الإشعارات"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.notifications_command(mock_update, None)
    
    async def _handle_mark_notifications_read(self, query):
        """معالجة وضع علامة على الإشعارات كمقروءة"""
        from_user = query.from_user
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            await db.mark_notifications_as_read(from_user.id)
            
            await self._edit_message_safe(query, "✅ **تم وضع علامة على جميع الإشعارات كمقروءة**")
            
        except Exception as e:
            logger.error(f"خطأ في وضع علامة على الإشعارات: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_export_links(self, query):
        """معالجة تصدير الروابط"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.export_command(mock_update, None)
    
    async def _handle_export_telegram(self, query):
        """معالجة تصدير تيليجرام"""
        await self._edit_message_safe(query, "⏳ جاري تحضير ملف تيليجرام...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links({'platform': 'telegram'}, limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد روابط تيليجرام للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"telegram_groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
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
                    caption=f"📢 روابط تيليجرام\nعدد الروابط: {len(links):,}\nآخر {Config.TELEGRAM_YEARS_BACK} سنوات فقط"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await self._edit_message_safe(query, f"✅ تم تصدير {len(links):,} رابط تيليجرام")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير تيليجرام: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_whatsapp(self, query):
        """معالجة تصدير واتساب"""
        await self._edit_message_safe(query, "⏳ جاري تحضير ملف واتساب...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links({'platform': 'whatsapp'}, limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد روابط واتساب للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"whatsapp_groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
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
                    caption=f"📱 روابط واتساب\nعدد الروابط: {len(links):,}\nآخر {Config.WHATSAPP_DAYS_BACK} يوماً فقط"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await self._edit_message_safe(query, f"✅ تم تصدير {len(links):,} رابط واتساب")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير واتساب: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_all(self, query):
        """معالجة تصدير جميع الروابط"""
        await self._edit_message_safe(query, "⏳ جاري تحضير جميع الروابط...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links(limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد روابط للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"all_groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
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
                    caption=f"📦 جميع الروابط (تيليجرام + واتساب)\nعدد الروابط: {len(links):,}\nجمعت حسب المتطلبات"
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
    
    async def _handle_export_csv(self, query):
        """معالجة التصدير كـ CSV"""
        await self._edit_message_safe(query, "⏳ جاري تحضير ملف CSV...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            cursor = await db.conn.execute('''
                SELECT preserved_url, platform, has_members, collected_date, is_new
                FROM links 
                WHERE platform IN ('telegram', 'whatsapp')
                LIMIT ?
            ''', (Config.MAX_EXPORT_LINKS,))
            
            rows = await cursor.fetchall()
            
            if not rows:
                await self._edit_message_safe(query, "❌ لا توجد روابط للتصدير")
                return
            
            # حفظ في ملف CSV
            filename = f"groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("URL,Platform,HasMembers,Date,IsNew\n")
                for row in rows:
                    url, platform, has_members, date, is_new = row
                    members_status = "Yes" if has_members else "No"
                    new_status = "Yes" if is_new else "No"
                    f.write(f'"{url}","{platform}","{members_status}","{date}","{new_status}"\n')
            
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
    
    async def _handle_export_test(self, query):
        """معالجة تصدير روابط الاختبار"""
        await self._edit_message_safe(query, "⏳ جاري تحضير روابط الاختبار...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            cursor = await db.conn.execute('''
                SELECT preserved_url FROM links 
                WHERE source LIKE '%test%' OR source LIKE '%sample%'
                ORDER BY collected_date DESC 
                LIMIT 100
            ''')
            
            rows = await cursor.fetchall()
            
            if not rows:
                await self._edit_message_safe(query, "❌ لا توجد روابط اختبار للتصدير")
                return
            
            links = [row[0] for row in rows]
            
            # حفظ في ملف نصي
            filename = f"test_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
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
                    caption=f"🧪 روابط الاختبار\nعدد الروابط: {len(links):,}"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await self._edit_message_safe(query, f"✅ تم تصدير {len(links):,} رابط اختبار")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الاختبار: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_create_backup(self, query):
        """معالجة إنشاء نسخة احتياطية"""
        await self._edit_message_safe(query, "⏳ جاري إنشاء نسخة احتياطية...")
        
        try:
            os.makedirs("backups", exist_ok=True)
            
            if not os.path.exists(Config.DB_PATH):
                await self._edit_message_safe(query, "❌ قاعدة البيانات غير موجودة")
                return
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"backup_{timestamp}.db"
            backup_path = os.path.join("backups", backup_filename)
            
            shutil.copy2(Config.DB_PATH, backup_path)
            
            metadata = {
                'backup_id': hashlib.md5(timestamp.encode()).hexdigest(),
                'timestamp': timestamp,
                'created_at': datetime.now().isoformat(),
                'file_path': backup_path,
                'size_bytes': os.path.getsize(backup_path)
            }
            
            metadata_path = os.path.join("backups", f"backup_{timestamp}.json")
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 قائمة النسخ", callback_data="list_backups"),
                 InlineKeyboardButton("🔄 تدوير النسخ", callback_data="rotate_backups")]
            ])
            
            await self._edit_message_safe(
                query,
                f"✅ **تم إنشاء نسخة احتياطية بنجاح!**\n\n"
                f"**تفاصيل النسخة:**\n"
                f"• الوقت: {timestamp}\n"
                f"• الحجم: {metadata['size_bytes'] / 1024 / 1024:.2f} MB\n"
                f"• المسار: {backup_path}",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"خطأ في إنشاء نسخة احتياطية: {e}")
            await self._edit_message_safe(query, f"❌ فشل في إنشاء نسخة احتياطية: {str(e)[:100]}")
    
    async def _handle_list_backups(self, query):
        """معالجة قائمة النسخ الاحتياطية"""
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
                list_text += (
                    f"**{i}. {backup['filename']}**\n"
                    f"• الحجم: {backup['size_mb']:.2f} MB\n"
                    f"• التاريخ: {backup['created'].strftime('%Y-%m-%d %H:%M')}\n\n"
                )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 تدوير النسخ", callback_data="rotate_backups"),
                 InlineKeyboardButton("💾 إنشاء نسخة", callback_data="create_backup")]
            ])
            
            await self._edit_message_safe(query, list_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"خطأ في عرض النسخ: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_rotate_backups(self, query):
        """معالجة تدوير النسخ القديمة"""
        await self._edit_message_safe(query, "⏳ جاري تدوير النسخ القديمة...")
        
        try:
            if not os.path.exists("backups"):
                await self._edit_message_safe(query, "✅ لا توجد نسخ قديمة")
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
                        json_path = backup['path'].replace('.db', '.json')
                        if os.path.exists(json_path):
                            os.remove(json_path)
                    except Exception as e:
                        logger.error(f"خطأ في حذف النسخة القديمة: {e}")
            
            await self._edit_message_safe(query, f"✅ تم تدوير النسخ الاحتياطية - بقي {min(len(backups), Config.MAX_BACKUPS)} نسخة")
            
        except Exception as e:
            logger.error(f"خطأ في تدوير النسخ: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_refresh_status(self, query):
        """معالجة تحديث الحالة"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.status_command(mock_update, None)
    
    async def _handle_refresh_stats(self, query):
        """معالجة تحديث الإحصائيات"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.stats_command(mock_update, None)
    
    async def _handle_refresh_sessions(self, query):
        """معالجة تحديث الجلسات"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.sessions_command(mock_update, None)
    
    async def _handle_show_settings(self, query):
        """معالجة عرض الإعدادات"""
        settings_text = (
            f"**⚙️ إعدادات النظام حسب المتطلبات**\n\n"
            f"**إعدادات الأمان:**\n"
            f"• المدراء: {len(Config.ADMIN_USER_IDS)}\n"
            f"• المستخدمون المسموحون: {len(Config.ALLOWED_USER_IDS)}\n"
            f"• التشفير: {'✅ مفعل' if Config.ENCRYPTION_KEY else '❌ معطل'}\n\n"
            f"**إعدادات الأداء:**\n"
            f"• الجلسات المتزامنة: {Config.MAX_CONCURRENT_SESSIONS}\n"
            f"• الذاكرة القصوى: {Config.MAX_MEMORY_MB} MB\n\n"
            f"**إعدادات الجمع:**\n"
            f"• جمع الروابط النشطة فقط: {'✅ مفعل' if Config.COLLECT_ONLY_ACTIVE else '❌ معطل'}\n"
            f"• جمع مجموعات الأعضاء فقط: {'✅ مفعل' if Config.COLLECT_MEMBER_GROUPS_ONLY else '❌ معطل'}\n"
            f"• منع التكرار: {'✅ مفعل' if Config.PREVENT_DUPLICATES else '❌ معطل'}\n"
            f"• رسالة واحدة لكل مجموعة: {'✅ مفعل' if Config.COLLECT_ONE_MESSAGE_PER_GROUP else '❌ معطل'}\n"
            f"• تجاهل البوتات: {'✅ مفعل' if Config.FILTER_BOT_LINKS else '❌ معطل'}\n"
            f"• تجاهل القنوات: {'✅ مفعل' if Config.FILTER_CHANNELS else '❌ معطل'}\n"
            f"• تجاهل t.me/me: {'✅ مفعل' if Config.FILTER_ME_LINKS else '❌ معطل'}\n"
            f"• تجاهل مجموعات المشتركين: {'✅ مفعل' if Config.FILTER_SUBSCRIPTION_GROUPS else '❌ معطل'}\n"
            f"• تجاهل الروابط المنتهية: {'✅ مفعل' if Config.FILTER_EXPIRED_LINKS else '❌ معطل'}\n\n"
            f"**إعدادات الوقت:**\n"
            f"• تيليجرام: آخر {Config.TELEGRAM_YEARS_BACK} سنوات فقط\n"
            f"• واتساب: آخر {Config.WHATSAPP_DAYS_BACK} يوم فقط\n\n"
            f"**إعدادات قاعدة البيانات:**\n"
            f"• المسار: {Config.DB_PATH}\n"
            f"• النسخ الاحتياطي: {'✅ مفعل' if Config.BACKUP_ENABLED else '❌ معطل'}\n"
            f"• عدد النسخ: {Config.MAX_BACKUPS}\n\n"
            f"**إعدادات الجمع:**\n"
            f"• الرسائل لكل مجموعة: {Config.MESSAGES_PER_GROUP}\n"
            f"• الجمع من جميع المجموعات: {'✅ نعم'}\n"
        )
        
        await self._edit_message_safe(query, settings_text)
    
    async def _handle_delete_session(self, query):
        """معالجة حذف الجلسة"""
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
        
        keyboard_buttons.append([InlineKeyboardButton("⬅️ رجوع", callback_data="show_sessions")])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await self._edit_message_safe(
            query,
            "**🗑️ حذف الجلسات**\n\n"
            "اختر الجلسة التي تريد حذفها:\n\n"
            "**تحذير:**\n"
            "• لا يمكن استرجاع الجلسة بعد الحذف\n"
            "• الروابط المجمعة تبقى محفوظة\n"
            "• يمكنك إضافة الجلسة مرة أخرى",
            reply_markup=keyboard
        )
    
    async def _handle_delete_session_confirm(self, query, data):
        """معالجة تأكيد حذف الجلسة"""
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
                f"• رقم الجلسة: {session_id}\n\n"
                f"**ملاحظة:**\n"
                f"تم حذف الجلسة بشكل دائم\n"
                f"الروابط التي جمعتها تبقى محفوظة\n"
                f"يمكنك إضافة جلسة جديدة في أي وقت"
            )
            
        except Exception as e:
            logger.error(f"خطأ في حذف الجلسة: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في حذف الجلسة: {str(e)[:100]}")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الرسائل النصية"""
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
                "/detailed_stats - إحصائيات مفصلة\n"
                "/test_collect - اختبار الجمع حسب المتطلبات\n"
                "/quick_collect - جمع سريع من 5 مجموعات\n"
                "/force_collect - بدء جمع فوري حسب المتطلبات\n"
                "/export_new - تصدير الروابط الجديدة فقط ⭐\n"
                "/notifications - عرض الإشعارات 🔔\n"
                "أو استخدم الأزرار من رسالة الترحيب."
            )
    
    async def _handle_session_input(self, update: Update, session_string: str):
        """معالجة إدخال سلسلة الجلسة"""
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
                'purpose': 'smart_collection_according_to_requirements'
            }
        }
        
        db = await EnhancedDatabaseManager.get_instance()
        success, message, details = await db.add_session(session_data)
        
        if success:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء الجمع الذكي", callback_data="start_collect"),
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
                f"• جاهزة للجمع حسب المتطلبات\n"
                f"• رقم الجلسة: {details.get('session_id')}\n\n"
                f"**ملاحظة:**\n"
                f"هذه الجلسة ستستخدم فقط لجمع الروابط حسب المتطلبات:\n"
                f"1. روابط تيليجرام النشطة فقط كما هي\n"
                f"2. مجموعات ذات أعضاء فقط\n"
                f"3. تجاهل (بوتات + قنوات + t.me/me + مجموعات مشتركين)\n"
                f"4. منع التكرار بين الجلسات\n"
                f"5. رسالة واحدة فقط من كل مجموعة\n"
                f"6. تيليجرام: آخر {Config.TELEGRAM_YEARS_BACK} سنوات فقط\n"
                f"7. واتساب: آخر {Config.WHATSAPP_DAYS_BACK} يوماً فقط",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ فشل في إضافة الجلسة: {message}")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الأخطاء"""
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
# Main Function - الوظيفة الرئيسية
# ======================

async def main():
    """الوظيفة الرئيسية"""
    try:
        logger.info(f"🚀 تشغيل البوت حسب المتطلبات المحددة")
        
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
        
        # تهيئة قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        
        # إنشاء البوت
        bot = TelegramBot()
        
        logger.info("🤖 بدء تشغيل بوت جمع الرواق الذكي حسب المتطلبات...")
        logger.info(f"✅ المتطلبات المطبقة:")
        logger.info(f"  1. روابط تيليجرام النشطة فقط كما هي")
        logger.info(f"  2. مجموعات ذات أعضاء فقط")
        logger.info(f"  3. تجاهل (بوتات + قنوات + t.me/me + مجموعات مشتركين)")
        logger.info(f"  4. منع التكرار بين الجلسات")
        logger.info(f"  5. رسالة واحدة فقط من كل مجموعة")
        logger.info(f"  6. تيليجرام: آخر {Config.TELEGRAM_YEARS_BACK} سنوات فقط")
        logger.info(f"  7. واتساب: آخر {Config.WHATSAPP_DAYS_BACK} يوماً فقط")
        logger.info(f"⚡ الإعدادات: {Config.MESSAGES_PER_GROUP} رسالة/مجموعة، {Config.MAX_CONCURRENT_SESSIONS} جلسة متزامنة")
        
        try:
            # تشغيل البوت
            await bot.app.initialize()
            await bot.app.start()
            await bot.app.updater.start_polling()
            
            logger.info("✅ البوت يعمل بنجاح!")
            logger.info("📋 الأوامر المتاحة: /start, /status, /detailed_stats, /test_collect, /quick_collect, /collect, /export_new, /notifications")
            
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
    """إعداد معالجات الإشارات"""
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
