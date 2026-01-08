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
    MAX_DIALOGS_PER_SESSION = 200
    MAX_MESSAGES_PER_SEARCH = 100
    MAX_SEARCH_TERMS = 8
    MAX_LINKS_PER_CYCLE = 1000
    MAX_BATCH_SIZE = 100
    
    # Database - قاعدة البيانات
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10
    DB_POOL_SIZE = 5
    
    # WhatsApp collection - جمع واتساب
    WHATSAPP_DAYS_BACK = 60
    
    # Telegram collection - جمع تليجرام
    TELEGRAM_YEARS_BACK = 5
    
    # Link verification - التحقق من الروابط
    MIN_GROUP_MEMBERS = 1
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
    
    # Collection settings - إعدادات الجمع الجديدة
    COLLECT_TELEGRAM = True
    COLLECT_WHATSAPP = True
    COLLECT_ONLY_ACTIVE_LINKS = True
    
    # Telegram collection - تليجرام
    TELEGRAM_ONLY_GROUPS_WITH_MEMBERS = True
    TELEGRAM_SKIP_BOTS = True
    TELEGRAM_SKIP_CHANNELS = True
    TELEGRAM_SKIP_SUBSCRIPTION_GROUPS = True
    TELEGRAM_SKIP_ME_LINKS = True
    TELEGRAM_MAX_MESSAGE_LINKS_PER_GROUP = 1
    TELEGRAM_COLLECT_LAST_YEARS = 5
    
    # WhatsApp collection - واتساب
    WHATSAPP_COLLECT_LAST_DAYS = 60
    WHATSAPP_SAVE_ORIGINAL = True
    
    # Notification - التنبيهات
    NOTIFY_COLLECTION_COMPLETE = True
    NOTIFY_NEW_LINKS = True
    
    # Keywords - الكلمات المفتاحية
    TELEGRAM_KEYWORDS = ['t.me', 'telegram.me', 'telegram.dog', 'joinchat', 'join', 'addlist']
    WHATSAPP_KEYWORDS = ['chat.whatsapp.com', 'whatsapp.com']

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
    """Advanced link processing with exact preservation"""
    
    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize URL but preserve WhatsApp links exactly"""
        if not url or not isinstance(url, str):
            return ""
        
        url = url.strip()
        
        # إزالة المسافات والرموز غير المرغوبة
        url = re.sub(r'^["\'\s*]+|["\'\s*]+$', '', url)
        url = re.sub(r'[,\s]+$', '', url)
        
        # استخراج الرابط من النص
        url_patterns = [
            r'(https?://[^\s<>]+)',
            r'(t\.me/[^\s<>]+)',
            r'(telegram\.me/[^\s<>]+)',
            r'(telegram\.dog/[^\s<>]+)',
            r'(chat\.whatsapp\.com/[^\s<>]+)'
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
            if any(keyword in url.lower() for keyword in Config.TELEGRAM_KEYWORDS + Config.WHATSAPP_KEYWORDS):
                url = 'https://' + url.lstrip('/')
        
        return url
    
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
            if any(keyword in domain for keyword in ['t.me', 'telegram.me', 'telegram.dog']):
                result['platform'] = 'telegram'
                result['details'] = EnhancedLinkProcessor._extract_telegram_info(normalized_url, parsed)
            elif any(keyword in domain for keyword in ['whatsapp.com', 'chat.whatsapp.com']):
                result['platform'] = 'whatsapp'
                result['details'] = EnhancedLinkProcessor._extract_whatsapp_info(normalized_url, parsed)
            
            result['is_valid'] = bool(result['details'].get('is_valid', False))
            
        except Exception as e:
            logger.debug(f"خطأ في استخراج معلومات الرابط: {e}")
        
        return result
    
    @staticmethod
    def _extract_telegram_info(url: str, parsed) -> Dict:
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
            'is_bot': False,
            'is_me_link': False,
            'is_subscription': False,
            'is_message_link': False,
            'is_addlist': False,
            'has_members': False,
            'path_segments': []
        }
        
        path = parsed.path.strip('/')
        if not path:
            return result
        
        segments = path.split('/')
        result['path_segments'] = segments
        
        # كشف روابط t.me/me
        if len(segments) == 1 and segments[0].lower() == 'me':
            result['is_me_link'] = True
            result['is_valid'] = False
            return result
        
        # كشف روابط البوتات
        if len(segments) == 1 and ('bot' in segments[0].lower() or segments[0].endswith('bot')):
            result['is_bot'] = True
            result['is_valid'] = False
            return result
        
        # كشف روابط القنوات (تخطيها)
        if len(segments) >= 2 and segments[0].lower() in ['c', 'channel']:
            result['is_channel'] = True
            result['is_valid'] = False
            return result
        
        # كشف روابط addlist
        if len(segments) >= 2 and segments[0].lower() == 'addlist':
            result['is_addlist'] = True
            result['is_group'] = True
            result['is_valid'] = True
            result['has_members'] = True  # نفترض أن روابط addlist تحتوي على أعضاء
            return result
        
        # كشف روابط الانضمام
        if path.startswith('+') or 'joinchat' in path.lower() or 'join' in path.lower():
            result['is_join_request'] = True
            result['is_group'] = True
            result['is_valid'] = True
            result['has_members'] = True
            return result
        
        # كشف المجموعات العامة
        if len(segments) == 1:
            result['is_group'] = True
            result['is_public'] = True
            result['is_valid'] = True
            result['has_members'] = True  # سنتحقق لاحقاً
            return result
        
        # كشف روابط الرسائل
        if len(segments) == 2 and segments[1].isdigit():
            result['is_message_link'] = True
            result['is_group'] = True
            result['is_valid'] = True
            result['has_members'] = True
            return result
        
        return result
    
    @staticmethod
    def _extract_whatsapp_info(url: str, parsed) -> Dict:
        """Extract WhatsApp specific information - الحفاظ على الرابط كما هو"""
        original_url = url
        
        # فقط نتحقق من أن الرابط يحتوي على chat.whatsapp.com
        if 'chat.whatsapp.com' in original_url.lower():
            return {
                'is_valid': True,
                'invite_code': parsed.path.strip('/'),
                'is_group': True,
                'is_active': True,
                'original_url': original_url
            }
        return {
            'is_valid': False,
            'original_url': original_url
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
                telegram_type TEXT,
                title TEXT,
                members_count INTEGER DEFAULT 0,
                session_id INTEGER,
                collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                check_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                is_verified BOOLEAN DEFAULT 0,
                validation_score INTEGER DEFAULT 0,
                added_by_user INTEGER,
                source TEXT,
                is_channel BOOLEAN DEFAULT 0,
                is_group BOOLEAN DEFAULT 0,
                is_bot BOOLEAN DEFAULT 0,
                is_me_link BOOLEAN DEFAULT 0,
                is_subscription BOOLEAN DEFAULT 0,
                is_message_link BOOLEAN DEFAULT 0,
                is_addlist BOOLEAN DEFAULT 0,
                has_members BOOLEAN DEFAULT 0,
                whatsapp_code TEXT,
                message_date TIMESTAMP,
                group_name TEXT,
                group_id INTEGER,
                is_new BOOLEAN DEFAULT 1,
                UNIQUE(url_hash)
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
                last_command TEXT
            )
        ''')
        
        # جدول الإشعارات
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL,
                title TEXT,
                message TEXT,
                link_count INTEGER DEFAULT 0,
                read_status BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES bot_users (user_id)
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
            'CREATE INDEX IF NOT EXISTS idx_links_has_members ON links(has_members)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_new ON links(is_new)',
            'CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)',
            'CREATE INDEX IF NOT EXISTS idx_users_last_active ON bot_users(last_active)',
            'CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)'
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
            platform = url_info['platform']
            
            # تخطي الروابط غير المطلوبة حسب المنصة
            if platform == 'telegram':
                if Config.TELEGRAM_SKIP_BOTS and details.get('is_bot', False):
                    return False, "رابط بوت - تم تخطيه", {}
                if Config.TELEGRAM_SKIP_CHANNELS and details.get('is_channel', False):
                    return False, "رابط قناة - تم تخطيه", {}
                if Config.TELEGRAM_SKIP_ME_LINKS and details.get('is_me_link', False):
                    return False, "رابط t.me/me - تم تخطيه", {}
                if Config.TELEGRAM_SKIP_SUBSCRIPTION_GROUPS and details.get('is_subscription', False):
                    return False, "مجموعة مشتركين - تم تخطيه", {}
            
            # الحفاظ على الرابط الأصلي كما هو
            url_to_store = url_info.get('original_url', url_info['normalized_url'])
            
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
                    has_members = ?,
                    group_name = ?
                    WHERE id = ?
                ''', (
                    link_info.get('is_active', True),
                    link_info.get('members', 0),
                    link_info.get('has_members', False),
                    link_info.get('group_name', ''),
                    existing[0]
                ))
                await self.conn.commit()
                return False, "تم تحديث الرابط الموجود", {'link_id': existing[0]}
            
            # إضافة رابط جديد
            cursor = await self.conn.execute('''
                INSERT INTO links 
                (url_hash, url, original_url, platform, telegram_type, title, 
                 members_count, session_id, is_active, is_verified, validation_score,
                 added_by_user, source, is_channel, is_group, is_bot, is_me_link,
                 is_subscription, is_message_link, is_addlist, has_members, whatsapp_code,
                 message_date, group_name, group_id, is_new)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                url_info['url_hash'],
                url_to_store,
                url_info['original_url'],
                platform,
                details.get('telegram_type', ''),
                link_info.get('title', '')[:500],
                link_info.get('members', 0),
                link_info.get('session_id'),
                link_info.get('is_active', True),
                link_info.get('is_verified', False),
                link_info.get('validation_score', 0),
                link_info.get('added_by_user', 0),
                link_info.get('source', 'manual'),
                details.get('is_channel', False),
                details.get('is_group', False),
                details.get('is_bot', False),
                details.get('is_me_link', False),
                details.get('is_subscription', False),
                details.get('is_message_link', False),
                details.get('is_addlist', False),
                link_info.get('has_members', False),
                link_info.get('whatsapp_code', ''),
                link_info.get('message_date', ''),
                link_info.get('group_name', ''),
                link_info.get('group_id', 0),
                1  # is_new = True للروابط الجديدة
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
                'url_hash': url_info['url_hash']
            }
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الرابط: {e}")
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def mark_links_as_old(self):
        """Mark all links as old (not new)"""
        try:
            await self.conn.execute("UPDATE links SET is_new = 0")
            await self.conn.commit()
            logger.info("✅ تم تعليم جميع الروابط كقديمة")
        except Exception as e:
            logger.error(f"خطأ في تعليم الروابط كقديمة: {e}")
    
    async def get_new_links_count(self) -> int:
        """Get count of new links"""
        try:
            cursor = await self.conn.execute(
                "SELECT COUNT(*) FROM links WHERE is_new = 1 AND platform IN ('telegram', 'whatsapp')"
            )
            result = await cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"خطأ في الحصول على عدد الروابط الجديدة: {e}")
            return 0
    
    async def get_new_links(self, limit: int = 100) -> List[Dict]:
        """Get new links"""
        try:
            cursor = await self.conn.execute('''
                SELECT url, platform, group_name, collected_date 
                FROM links 
                WHERE is_new = 1 AND platform IN ('telegram', 'whatsapp')
                ORDER BY collected_date DESC 
                LIMIT ?
            ''', (limit,))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            links = []
            for row in rows:
                links.append(dict(zip(columns, row)))
            
            return links
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على الروابط الجديدة: {e}")
            return []
    
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
                update_query += ', link_count = link_count + ?'
            
            update_query += ' WHERE user_id = ?'
            
            if action == 'link_added':
                await self.conn.execute(update_query, (value, user_id))
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
    
    async def add_notification(self, user_id: int, notification_type: str, 
                             title: str, message: str, link_count: int = 0):
        """Add notification for user"""
        try:
            await self.conn.execute('''
                INSERT INTO notifications (user_id, notification_type, title, message, link_count)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, notification_type, title, message, link_count))
            
            await self.conn.commit()
            
            logger.info(f"✅ تمت إضافة إشعار للمستخدم {user_id}: {title}")
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الإشعار: {e}")
    
    async def get_unread_notifications_count(self, user_id: int) -> int:
        """Get count of unread notifications"""
        try:
            cursor = await self.conn.execute(
                "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_status = 0",
                (user_id,)
            )
            result = await cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"خطأ في الحصول على عدد الإشعارات غير المقروءة: {e}")
            return 0
    
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
            cursor = await self.conn.execute('SELECT COUNT(*) FROM links WHERE platform IN ("telegram", "whatsapp")')
            result = await cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"خطأ في الحصول على عدد الروابط: {e}")
            return 0
    
    async def get_stats_summary(self) -> Dict:
        """Get database statistics summary"""
        try:
            stats = {}
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE platform IN ('telegram', 'whatsapp')")
            stats['total_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE has_members = 1 AND platform IN ('telegram', 'whatsapp')")
            stats['groups_with_members'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_new = 1 AND platform IN ('telegram', 'whatsapp')")
            stats['new_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT platform, COUNT(*) FROM links WHERE platform IN ('telegram', 'whatsapp') GROUP BY platform")
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE date(collected_date) = date('now') AND platform IN ('telegram', 'whatsapp')")
            stats['today_links'] = (await cursor.fetchone())[0]
            
            # إحصائيات تيليجرام
            cursor = await self.conn.execute('''
                SELECT 
                    SUM(CASE WHEN is_bot = 1 THEN 1 ELSE 0 END) as bots,
                    SUM(CASE WHEN is_channel = 1 THEN 1 ELSE 0 END) as channels,
                    SUM(CASE WHEN is_me_link = 1 THEN 1 ELSE 0 END) as me_links,
                    SUM(CASE WHEN is_subscription = 1 THEN 1 ELSE 0 END) as subscriptions,
                    SUM(CASE WHEN is_message_link = 1 THEN 1 ELSE 0 END) as message_links,
                    SUM(CASE WHEN is_addlist = 1 THEN 1 ELSE 0 END) as addlist_links
                FROM links WHERE platform = 'telegram'
            ''')
            row = await cursor.fetchone()
            if row:
                stats['telegram_details'] = {
                    'bots': row[0],
                    'channels': row[1],
                    'me_links': row[2],
                    'subscriptions': row[3],
                    'message_links': row[4],
                    'addlist_links': row[5]
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على ملخص الإحصائيات: {e}")
            return {}
    
    async def export_links(self, filters: Dict = None, limit: int = 1000) -> List[str]:
        """Export links"""
        try:
            query = 'SELECT url FROM links WHERE platform IN ("telegram", "whatsapp")'
            params = []
            
            if filters:
                where_clauses = []
                
                if filters.get('platform'):
                    where_clauses.append("platform = ?")
                    params.append(filters['platform'])
                
                if filters.get('only_new'):
                    where_clauses.append("is_new = 1")
                
                if filters.get('only_members'):
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
            session_string = session_string.strip()
            
            if len(session_string) < 50:
                return False, {'error': 'جلسة قصيرة جداً'}
            
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH,
                timeout=15
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return False, {'error': 'غير مصرح'}
            
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
            return False, {'error': 'جلسة غير صالحة'}
        except Exception as e:
            return False, {'error': 'خطأ في التحقق', 'details': str(e)[:200]}
    
    @staticmethod
    async def create_client(session_string: str) -> Optional[TelegramClient]:
        """Create Telegram client from session string"""
        try:
            session_string = session_string.strip()
            
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
# Telegram Link Collector - جامع روابط تليجرام
# ======================

class TelegramLinkCollector:
    """Collect Telegram links with specific requirements"""
    
    @staticmethod
    async def collect_from_group(client: TelegramClient, entity, session_id: int, user_id: int) -> Tuple[List[Dict], Dict]:
        """Collect links from a single Telegram group"""
        links = []
        stats = {
            'total_found': 0,
            'added': 0,
            'skipped': 0,
            'message_links_collected': 0,
            'max_message_links_reached': False
        }
        
        try:
            group_info = await TelegramLinkCollector._get_group_info(client, entity)
            
            if not group_info['has_members']:
                logger.info(f"تخطي مجموعة بدون أعضاء: {group_info['title']}")
                return links, stats
            
            # حساب تاريخ 5 سنوات مضت
            five_years_ago = datetime.now() - timedelta(days=5*365)
            
            # جمع الروابط من الرسائل
            message_links = set()
            async for message in client.iter_messages(entity, limit=200):
                try:
                    if message.date < five_years_ago:
                        break
                    
                    if message.text:
                        found_links = TelegramLinkCollector._extract_links_from_text(message.text)
                        
                        for link in found_links:
                            stats['total_found'] += 1
                            
                            link_info = EnhancedLinkProcessor.extract_url_info(link)
                            
                            if link_info['platform'] != 'telegram':
                                stats['skipped'] += 1
                                continue
                            
                            details = link_info['details']
                            
                            # تخطي الروابط غير المطلوبة
                            if details.get('is_bot', False) or details.get('is_channel', False) or \
                               details.get('is_me_link', False) or details.get('is_subscription', False):
                                stats['skipped'] += 1
                                continue
                            
                            # التحكم بروابط الرسائل (واحد فقط لكل مجموعة)
                            if details.get('is_message_link', False):
                                if stats['message_links_collected'] >= Config.TELEGRAM_MAX_MESSAGE_LINKS_PER_GROUP:
                                    stats['max_message_links_reached'] = True
                                    stats['skipped'] += 1
                                    continue
                                stats['message_links_collected'] += 1
                            
                            # تجنب التكرار داخل المجموعة الواحدة
                            if link in message_links:
                                stats['skipped'] += 1
                                continue
                            
                            message_links.add(link)
                            
                            link_data = {
                                'url': link,
                                'platform': 'telegram',
                                'telegram_type': 'group_link',
                                'title': group_info['title'],
                                'members': group_info['members_count'],
                                'session_id': session_id,
                                'is_active': True,
                                'is_verified': True,
                                'validation_score': 100,
                                'added_by_user': user_id,
                                'source': 'telegram_group',
                                'is_group': True,
                                'has_members': group_info['has_members'],
                                'message_date': message.date.isoformat() if message.date else datetime.now().isoformat(),
                                'group_name': group_info['title'],
                                'group_id': group_info.get('id')
                            }
                            
                            links.append(link_data)
                            stats['added'] += 1
                            
                except Exception as e:
                    logger.debug(f"خطأ في معالجة رسالة: {e}")
                    continue
            
            logger.info(f"✅ تم جمع {stats['added']} رابط من مجموعة {group_info['title']}")
            
        except Exception as e:
            logger.error(f"خطأ في جمع الروابط من المجموعة: {e}")
        
        return links, stats
    
    @staticmethod
    async def _get_group_info(client: TelegramClient, entity) -> Dict:
        """Get group information"""
        try:
            full_info = await client.get_entity(entity)
            
            result = {
                'title': getattr(full_info, 'title', 'مجموعة غير معروفة'),
                'id': getattr(full_info, 'id', None),
                'has_members': False,
                'members_count': 0
            }
            
            # التحقق من وجود أعضاء
            if hasattr(full_info, 'participants_count'):
                result['members_count'] = full_info.participants_count
                result['has_members'] = result['members_count'] > 0
            elif hasattr(full_info, 'members_count'):
                result['members_count'] = full_info.members_count
                result['has_members'] = result['members_count'] > 0
            
            return result
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على معلومات المجموعة: {e}")
            return {'title': 'غير معروف', 'has_members': False, 'members_count': 0}
    
    @staticmethod
    def _extract_links_from_text(text: str) -> List[str]:
        """Extract links from text"""
        if not text:
            return []
        
        # البحث عن جميع روابط تيليجرام
        url_patterns = [
            r'(https?://t\.me/[^\s<>"\']+)',
            r'(https?://telegram\.me/[^\s<>"\']+)',
            r'(https?://telegram\.dog/[^\s<>"\']+)',
            r'(t\.me/[^\s<>"\']+)',
            r'(telegram\.me/[^\s<>"\']+)',
            r'(telegram\.dog/[^\s<>"\']+)'
        ]
        
        links = []
        for pattern in url_patterns:
            found = re.findall(pattern, text, re.IGNORECASE)
            for link in found:
                if not link.startswith(('http://', 'https://')):
                    link = 'https://' + link
                links.append(link)
        
        return links

# ======================
# WhatsApp Link Collector - جامع روابط واتساب
# ======================

class WhatsAppLinkCollector:
    """Collect WhatsApp links with specific requirements"""
    
    @staticmethod
    async def collect_from_group(client: TelegramClient, entity, session_id: int, user_id: int) -> Tuple[List[Dict], Dict]:
        """Collect WhatsApp links from a single Telegram group"""
        links = []
        stats = {
            'total_found': 0,
            'added': 0,
            'skipped': 0,
            'too_old': 0
        }
        
        try:
            group_info = await WhatsAppLinkCollector._get_group_info(client, entity)
            
            # حساب تاريخ 60 يوم مضت
            sixty_days_ago = datetime.now() - timedelta(days=Config.WHATSAPP_DAYS_BACK)
            
            # جمع روابط واتساب من الرسائل
            whatsapp_links = set()
            async for message in client.iter_messages(entity, limit=200):
                try:
                    if message.date < sixty_days_ago:
                        stats['too_old'] += 1
                        continue
                    
                    if message.text:
                        found_links = WhatsAppLinkCollector._extract_whatsapp_links(message.text)
                        
                        for link in found_links:
                            stats['total_found'] += 1
                            
                            # تجنب التكرار داخل المجموعة الواحدة
                            if link in whatsapp_links:
                                stats['skipped'] += 1
                                continue
                            
                            whatsapp_links.add(link)
                            
                            # الحفاظ على الرابط الأصلي كما هو لواتساب
                            original_link = link
                            
                            link_data = {
                                'url': original_link,
                                'platform': 'whatsapp',
                                'title': group_info['title'],
                                'session_id': session_id,
                                'is_active': True,
                                'is_verified': True,
                                'validation_score': 100,
                                'added_by_user': user_id,
                                'source': 'telegram_group',
                                'is_group': True,
                                'has_members': True,
                                'message_date': message.date.isoformat() if message.date else datetime.now().isoformat(),
                                'group_name': group_info['title'],
                                'whatsapp_code': WhatsAppLinkCollector._extract_invite_code(original_link)
                            }
                            
                            links.append(link_data)
                            stats['added'] += 1
                            
                except Exception as e:
                    logger.debug(f"خطأ في معالجة رسالة واتساب: {e}")
                    continue
            
            if stats['added'] > 0:
                logger.info(f"✅ تم جمع {stats['added']} رابط واتساب من مجموعة {group_info['title']}")
            
        except Exception as e:
            logger.error(f"خطأ في جمع روابط واتساب: {e}")
        
        return links, stats
    
    @staticmethod
    async def _get_group_info(client: TelegramClient, entity) -> Dict:
        """Get group information"""
        try:
            full_info = await client.get_entity(entity)
            
            return {
                'title': getattr(full_info, 'title', 'مجموعة غير معروفة'),
                'id': getattr(full_info, 'id', None)
            }
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على معلومات المجموعة: {e}")
            return {'title': 'غير معروف'}
    
    @staticmethod
    def _extract_whatsapp_links(text: str) -> List[str]:
        """Extract WhatsApp links from text - الحفاظ عليها كما هي"""
        if not text:
            return []
        
        # البحث عن روابط واتساب بالصيغ المختلفة
        url_patterns = [
            r'(https?://chat\.whatsapp\.com/[^\s<>"\']+)',
            r'(https?://whatsapp\.com/[^\s<>"\']+)',
            r'(chat\.whatsapp\.com/[^\s<>"\']+)',
            r'(whatsapp\.com/[^\s<>"\']+)'
        ]
        
        links = []
        for pattern in url_patterns:
            found = re.findall(pattern, text, re.IGNORECASE)
            for link in found:
                # الحفاظ على الرابط كما هو
                if not link.startswith(('http://', 'https://')):
                    link = 'https://' + link
                links.append(link)
        
        return links
    
    @staticmethod
    def _extract_invite_code(url: str) -> str:
        """Extract invite code from WhatsApp URL"""
        try:
            parsed = urlparse(url)
            return parsed.path.strip('/')
        except:
            return ''

# ======================
# Collection Manager - مدير الجمع الرئيسي
# ======================

class CollectionManager:
    """Main collection manager"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        self.stats = {
            'total_collected': 0,
            'telegram_collected': 0,
            'whatsapp_collected': 0,
            'groups_processed': 0,
            'sessions_used': 0,
            'errors': 0,
            'start_time': None,
            'end_time': None,
            'telegram_skipped': {
                'bots': 0,
                'channels': 0,
                'me_links': 0,
                'subscriptions': 0,
                'no_members': 0
            }
        }
        self.collection_task = None
    
    async def start_collection(self, user_id: int):
        """Start collection process"""
        if self.active:
            return "الجمع يعمل بالفعل"
        
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.stats['start_time'] = datetime.now()
        self.stats['telegram_collected'] = 0
        self.stats['whatsapp_collected'] = 0
        self.stats['groups_processed'] = 0
        
        logger.info("🚀 بدء عملية الجمع الجديدة...")
        
        # بدء مهمة الجمع في الخلفية
        self.collection_task = asyncio.create_task(self._collection_process(user_id))
        
        return "بدأت عملية الجمع بنجاح"
    
    async def _collection_process(self, user_id: int):
        """Main collection process"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=Config.MAX_CONCURRENT_SESSIONS)
            
            if not sessions:
                logger.warning("لا توجد جلسات نشطة")
                await self._send_notification(user_id, "خطأ", "لا توجد جلسات نشطة للجمع")
                self.active = False
                return
            
            self.stats['sessions_used'] = len(sessions)
            
            total_collected = 0
            
            for session in sessions:
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    collected = await self._process_session(session, user_id)
                    total_collected += collected
                    
                    logger.info(f"✅ انتهت جلسة {session.get('display_name')}: {collected} رابط")
                    
                    await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
                    
                except Exception as e:
                    logger.error(f"خطأ في معالجة الجلسة: {e}")
                    self.stats['errors'] += 1
            
            self.stats['end_time'] = datetime.now()
            self.stats['total_collected'] = total_collected
            
            # إرسال إشعار اكتمال الجمع
            if Config.NOTIFY_COLLECTION_COMPLETE:
                await self._send_collection_complete_notification(user_id)
            
            # تعليم جميع الروابط كقديمة بعد اكتمال الجمع
            await db.mark_links_as_old()
            
            logger.info(f"✅ اكتملت عملية الجمع: {total_collected} رابط مجمع")
            
        except Exception as e:
            logger.error(f"خطأ في عملية الجمع: {e}")
            await self._send_notification(user_id, "خطأ", f"حدث خطأ في عملية الجمع: {str(e)[:200]}")
        
        finally:
            self.active = False
    
    async def _process_session(self, session: Dict, user_id: int) -> int:
        """Process single session"""
        session_collected = 0
        session_id = session.get('id')
        session_name = session.get('display_name', f'جلسة {session_id}')
        
        try:
            session_string = session.get('session_string', '')
            if not session_string or session_string == '********':
                logger.error(f"جلسة {session_id} غير متاحة")
                return 0
            
            # فك تشفير الجلسة
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt(session_string)
            
            client = await SessionManager.create_client(decrypted_session)
            if not client:
                return 0
            
            logger.info(f"📱 بدء الجمع من جلسة: {session_name}")
            
            # الحصول على جميع المجموعات
            groups_processed = 0
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # تخطي الرسائل الخاصة والمحادثات الشخصية
                    if not hasattr(entity, 'title'):
                        continue
                    
                    groups_processed += 1
                    
                    # جمع روابط تيليجرام
                    telegram_links, telegram_stats = await TelegramLinkCollector.collect_from_group(
                        client, entity, session_id, user_id
                    )
                    
                    # جمع روابط واتساب
                    whatsapp_links, whatsapp_stats = await WhatsAppLinkCollector.collect_from_group(
                        client, entity, session_id, user_id
                    )
                    
                    # حفظ الروابط في قاعدة البيانات
                    db = await EnhancedDatabaseManager.get_instance()
                    
                    for link_data in telegram_links:
                        success, message, _ = await db.add_link(link_data)
                        if success:
                            session_collected += 1
                            self.stats['telegram_collected'] += 1
                    
                    for link_data in whatsapp_links:
                        success, message, _ = await db.add_link(link_data)
                        if success:
                            session_collected += 1
                            self.stats['whatsapp_collected'] += 1
                    
                    # تحديث إحصائيات التخطي
                    self.stats['telegram_skipped']['no_members'] += 1 if telegram_stats.get('skipped', 0) > 0 else 0
                    
                    self.stats['groups_processed'] += 1
                    
                    # إرسال تحديث كل 5 مجموعات
                    if groups_processed % 5 == 0:
                        logger.info(f"📈 التقدم: {groups_processed} مجموعة - {session_collected} رابط")
                    
                    await asyncio.sleep(Config.REQUEST_DELAYS['between_groups'])
                    
                except Exception as e:
                    logger.debug(f"خطأ في معالجة المجموعة: {e}")
                    continue
            
            await client.disconnect()
            
            # تحديث إحصائيات الجلسة
            db = await EnhancedDatabaseManager.get_instance()
            await db.conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, last_success = CURRENT_TIMESTAMP, total_uses = total_uses + 1, total_links = total_links + ? WHERE id = ?",
                (session_collected, session_id)
            )
            await db.conn.commit()
            
            logger.info(f"✅ انتهى الجمع من جلسة {session_name}: {session_collected} رابط")
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الجلسة: {e}")
        
        return session_collected
    
    async def _send_collection_complete_notification(self, user_id: int):
        """Send collection complete notification"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds() / 60
            
            message = (
                f"✅ **اكتملت عملية الجمع بنجاح!**\n\n"
                f"**الإحصائيات:**\n"
                f"• الروابط المجمعة: {self.stats['total_collected']:,}\n"
                f"• روابط تيليجرام: {self.stats['telegram_collected']:,}\n"
                f"• روابط واتساب: {self.stats['whatsapp_collected']:,}\n"
                f"• المجموعات المعالجة: {self.stats['groups_processed']:,}\n"
                f"• الجلسات المستخدمة: {self.stats['sessions_used']}\n"
                f"• المدة: {duration:.1f} دقيقة\n\n"
                f"**ملاحظات:**\n"
                f"• تم تجميع روابط تيليجرام من آخر {Config.TELEGRAM_COLLECT_LAST_YEARS} سنوات\n"
                f"• تم تجميع روابط واتساب من آخر {Config.WHATSAPP_COLLECT_LAST_DAYS} يوم\n"
                f"• تم تجاهل الروابط الميتة والمنتهية\n"
                f"• يمكنك تصدير الروابط الجديدة الآن"
            )
            
            await db.add_notification(
                user_id,
                'collection_complete',
                'اكتمال عملية الجمع',
                message,
                self.stats['total_collected']
            )
            
        except Exception as e:
            logger.error(f"خطأ في إرسال إشعار اكتمال الجمع: {e}")
    
    async def _send_notification(self, user_id: int, title: str, message: str):
        """Send notification to user"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            await db.add_notification(user_id, 'system', title, message, 0)
        except Exception as e:
            logger.error(f"خطأ في إرسال الإشعار: {e}")
    
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
        
        if self.collection_task:
            try:
                await asyncio.wait_for(self.collection_task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("مهلة انتظار إيقاف مهمة الجمع")

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
# Telegram Bot - بوت تليجرام الرئيسي
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
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        self.app.add_handler(CommandHandler("stop_collect", self.stop_collect_command))
        self.app.add_handler(CommandHandler("pause_collect", self.pause_collect_command))
        self.app.add_handler(CommandHandler("resume_collect", self.resume_collect_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("new_links", self.new_links_command))
        self.app.add_handler(CommandHandler("notifications", self.notifications_command))
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        self.app.add_handler(CommandHandler("addsession", self.add_session_command))
        
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
        
        # التحقق من الإشعارات غير المقروءة
        unread_count = await db.get_unread_notifications_count(user.id)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect"),
             InlineKeyboardButton("📊 الحالة", callback_data="status")],
            [InlineKeyboardButton("📤 تصدير الروابط الجديدة", callback_data="export_new"),
             InlineKeyboardButton("🔔 الإشعارات", callback_data="notifications")],
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("👥 الجلسات", callback_data="show_sessions")]
        ])
        
        welcome_text = (
            f"🤖 **مرحباً {user.first_name}!**\n\n"
            "**بوت جمع روابط تليجرام وواتساب المتقدم**\n\n"
            f"{'🔔 **يوجد إشعارات غير مقروءة**' if unread_count > 0 else ''}\n\n"
            "**المميزات:**\n"
            "✅ جمع روابط تليجرام النشطة فقط\n"
            "✅ روابط تيليجرام محفوظة كما هي\n"
            "✅ روابط واتساب محفوظة كما هي\n"
            "✅ تجميع روابط تيليجرام من آخر 5 سنوات\n"
            "✅ تجميع روابط واتساب من آخر 60 يوم فقط\n"
            "✅ تجاهل الروابط الميتة والمنتهية\n"
            "✅ إشعارات عند اكتمال الجمع\n"
            "✅ قسم خاص للروابط الجديدة\n\n"
            "**الروابط المستهدفة:**\n"
            "• مجموعات تيليجرام التي تحتوي على أعضاء\n"
            "• روابط واتساب النشطة فقط"
        )
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    
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
            await update.message.reply_text("⏳ الجمع يعمل بالفعل")
            return
        
        await update.message.reply_text("🚀 جاري بدء عملية الجمع...")
        
        result = await self.collection_manager.start_collection(user.id)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 متابعة الحالة", callback_data="status")]
        ])
        
        await update.message.reply_text(
            "✅ **بدأت عملية الجمع بنجاح!**\n\n"
            "**تفاصيل العملية:**\n"
            "• جاري جمع روابط تيليجرام من آخر 5 سنوات\n"
            "• جاري جمع روابط واتساب من آخر 60 يوم\n"
            "• تجاهل الروابط الميتة والمنتهية\n"
            "• جمع روابط المجموعات ذات الأعضاء فقط\n"
            "• سيتم إعلامك عند اكتمال الجمع\n\n"
            "**ملاحظات:**\n"
            "• الروابط تحفظ كما هي دون تغيير\n"
            "• تجنب تكرار الروابط\n"
            "• رابط رسالة واحد فقط من كل مجموعة",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def stop_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop_collect command"""
        user = update.effective_user
        
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        status = self.collection_manager.get_status()
        
        if not status['active']:
            await update.message.reply_text("⚠️ لا توجد عملية جمع نشطة")
            return
        
        await self.collection_manager.stop()
        
        await update.message.reply_text(
            "⏹️ **تم إيقاف عملية الجمع**\n\n"
            "تم حفظ جميع الروابط المجمعة حتى الآن.\n"
            "يمكنك تصدير الروابط الجديدة باستخدام /export"
        )
    
    async def pause_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause_collect command"""
        user = update.effective_user
        
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        status = self.collection_manager.get_status()
        
        if not status['active']:
            await update.message.reply_text("⚠️ لا توجد عملية جمع نشطة")
            return
        
        if status['paused']:
            await update.message.reply_text("⚠️ الجمع موقف مؤقتاً بالفعل")
            return
        
        await self.collection_manager.pause()
        
        await update.message.reply_text(
            "⏸️ **تم إيقاف الجمع مؤقتاً**\n\n"
            "يمكنك استئناف الجمع باستخدام /resume_collect"
        )
    
    async def resume_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume_collect command"""
        user = update.effective_user
        
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        status = self.collection_manager.get_status()
        
        if not status['active']:
            await update.message.reply_text("⚠️ لا توجد عملية جمع نشطة")
            return
        
        if not status['paused']:
            await update.message.reply_text("⚠️ الجمع يعمل بالفعل")
            return
        
        await self.collection_manager.resume()
        
        await update.message.reply_text(
            "▶️ **تم استئناف عملية الجمع**\n\n"
            "سيستمر البوت في جمع الروابط من حيث توقف."
        )
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        user = update.effective_user
        
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        status = self.collection_manager.get_status()
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        new_links_count = await db.get_new_links_count()
        
        status_text = (
            f"**📊 حالة النظام - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**\n\n"
            "**حالة الجمع:**\n"
        )
        
        if status['active']:
            if status['paused']:
                status_text += "⏸️ **موقف مؤقتاً**\n"
            else:
                status_text += "🔄 **نشط - جاري الجمع**\n"
        else:
            status_text += "🛑 **متوقف**\n"
        
        if status['active'] and status['stats']['start_time']:
            duration = (datetime.now() - status['stats']['start_time']).total_seconds() / 60
            status_text += f"• المدة: {duration:.1f} دقيقة\n"
        
        status_text += (
            f"\n**إحصائيات الجمع:**\n"
            f"• الروابط المجمعة: {status['stats']['total_collected']:,}\n"
            f"• تيليجرام: {status['stats']['telegram_collected']:,}\n"
            f"• واتساب: {status['stats']['whatsapp_collected']:,}\n"
            f"• المجموعات المعالجة: {status['stats']['groups_processed']:,}\n"
            f"• الجلسات المستخدمة: {status['stats']['sessions_used']}\n"
            f"• الأخطاء: {status['stats']['errors']:,}\n\n"
            f"**إحصائيات قاعدة البيانات:**\n"
            f"• 🔗 إجمالي الروابط: {db_stats.get('total_links', 0):,}\n"
            f"• 🆕 روابط جديدة: {new_links_count:,}\n"
            f"• 💼 الجلسات النشطة: {db_stats.get('active_sessions', 0)}\n"
            f"• 📈 روابط اليوم: {db_stats.get('today_links', 0):,}\n\n"
            f"**إعدادات الجمع:**\n"
            f"• تيليجرام: آخر {Config.TELEGRAM_COLLECT_LAST_YEARS} سنوات\n"
            f"• واتساب: آخر {Config.WHATSAPP_COLLECT_LAST_DAYS} يوم\n"
            f"• روابط الرسائل: {Config.TELEGRAM_MAX_MESSAGE_LINKS_PER_GROUP} لكل مجموعة"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="status"),
             InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("📤 تصدير الجديدة", callback_data="export_new"),
             InlineKeyboardButton("🔔 الإشعارات", callback_data="notifications")]
        ])
        
        await update.message.reply_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        user = update.effective_user
        
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        
        stats_text = "**📈 إحصائيات النظام**\n\n"
        
        stats_text += (
            f"**إحصائيات قاعدة البيانات:**\n"
            f"• 🔗 إجمالي الروابط: {db_stats.get('total_links', 0):,}\n"
            f"• 🆕 روابط جديدة: {db_stats.get('new_links', 0):,}\n"
            f"• 👥 مجموعات أعضاء: {db_stats.get('groups_with_members', 0):,}\n"
            f"• 💼 الجلسات النشطة: {db_stats.get('active_sessions', 0)}\n"
            f"• 👤 المستخدمين: {db_stats.get('total_users', 0)}\n"
            f"• 📈 روابط اليوم: {db_stats.get('today_links', 0):,}\n\n"
        )
        
        if 'links_by_platform' in db_stats:
            stats_text += "**توزيع المنصات:**\n"
            for platform, count in db_stats['links_by_platform'].items():
                stats_text += f"• {platform}: {count:,}\n"
        
        if 'telegram_details' in db_stats:
            details = db_stats['telegram_details']
            stats_text += "\n**روابط تيليجرام المتجاهلة:**\n"
            stats_text += f"• البوتات: {details.get('bots', 0):,}\n"
            stats_text += f"• القنوات: {details.get('channels', 0):,}\n"
            stats_text += f"• روابط me: {details.get('me_links', 0):,}\n"
            stats_text += f"• المشتركين: {details.get('subscriptions', 0):,}\n"
            stats_text += f"• روابط الرسائل: {details.get('message_links', 0):,}\n"
            stats_text += f"• روابط addlist: {details.get('addlist_links', 0):,}\n"
        
        await update.message.reply_text(stats_text, parse_mode="Markdown")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command"""
        user = update.effective_user
        
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        total_links = await db.get_links_count()
        new_links_count = await db.get_new_links_count()
        
        if total_links == 0:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")]
            ])
            await update.message.reply_text(
                "❌ **لا توجد روابط للتصدير**\n\n"
                "ابدأ عملية الجمع أولاً باستخدام /collect",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🆕 الروابط الجديدة فقط", callback_data="export_new"),
             InlineKeyboardButton("📢 جميع روابط تيليجرام", callback_data="export_telegram")],
            [InlineKeyboardButton("📱 جميع روابط واتساب", callback_data="export_whatsapp"),
             InlineKeyboardButton("📦 جميع الروابط", callback_data="export_all")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="export")]
        ])
        
        export_text = (
            f"**📤 تصدير الروابط**\n\n"
            f"إجمالي الروابط: **{total_links:,}**\n"
            f"الروابط الجديدة: **{new_links_count:,}**\n\n"
            f"**خيارات التصدير:**\n"
            f"• 🆕 الروابط الجديدة فقط\n"
            f"• 📢 جميع روابط تيليجرام\n"
            f"• 📱 جميع روابط واتساب\n"
            f"• 📦 جميع الروابط\n\n"
            f"**ملاحظات:**\n"
            f"• الروابط محفوظة كما هي دون تغيير\n"
            f"• كل رابط في سطر مستقل\n"
            f"• جاهزة للاستخدام المباشر"
        )
        
        await update.message.reply_text(export_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def new_links_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /new_links command"""
        user = update.effective_user
        
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        new_links_count = await db.get_new_links_count()
        
        if new_links_count == 0:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")]
            ])
            await update.message.reply_text(
                "❌ **لا توجد روابط جديدة**\n\n"
                "ابدأ عملية الجمع أولاً باستخدام /collect",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return
        
        new_links = await db.get_new_links(limit=10)
        
        new_links_text = f"**🆕 الروابط الجديدة ({new_links_count:,})**\n\n"
        
        for i, link in enumerate(new_links, 1):
            platform_icon = "📢" if link['platform'] == 'telegram' else "📱"
            new_links_text += f"{i}. {platform_icon} {link['url'][:50]}...\n"
        
        if new_links_count > 10:
            new_links_text += f"\n... و {new_links_count - 10} رابط آخر\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 تصدير الجديدة", callback_data="export_new"),
             InlineKeyboardButton("🚀 جمع المزيد", callback_data="start_collect")]
        ])
        
        await update.message.reply_text(new_links_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def notifications_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /notifications command"""
        user = update.effective_user
        
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        
        cursor = await db.conn.execute('''
            SELECT title, message, created_at 
            FROM notifications 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 5
        ''', (user.id,))
        
        notifications = await cursor.fetchall()
        
        if not notifications:
            await update.message.reply_text("📭 لا توجد إشعارات")
            return
        
        notifications_text = "**🔔 الإشعارات**\n\n"
        
        for i, (title, message, created_at) in enumerate(notifications, 1):
            date_str = datetime.fromisoformat(created_at).strftime('%Y-%m-%d %H:%M')
            notifications_text += f"**{i}. {title}**\n{message[:100]}...\n{date_str}\n\n"
        
        await update.message.reply_text(notifications_text, parse_mode="Markdown")
    
    async def sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sessions command"""
        user = update.effective_user
        
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
            uses = session.get('total_uses', 0)
            links_collected = session.get('total_links', 0)
            
            sessions_text += (
                f"**{i}. {display_name}**\n"
                f"• المعرف: @{username}\n"
                f"• الاستخدامات: {uses}\n"
                f"• الروابط المجمعة: {links_collected:,}\n\n"
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
            "• تستخدم فقط لجمع الروابط\n"
            "• يجب أن تكون الجلسة نشطة"
        )
        
        await update.message.reply_text(add_text, parse_mode="Markdown")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await query.edit_message_text("❌ غير مصرح لك بالوصول")
                return
        
        data = query.data
        
        try:
            if data == "start_collect":
                await self._handle_start_collect(query)
            elif data == "stop_collect":
                await self._handle_stop_collect(query)
            elif data == "pause_collect":
                await self._handle_pause_collect(query)
            elif data == "resume_collect":
                await self._handle_resume_collect(query)
            elif data == "status":
                await self._handle_status(query)
            elif data == "export":
                await self._handle_export(query)
            elif data == "export_new":
                await self._handle_export_new(query)
            elif data == "export_telegram":
                await self._handle_export_telegram(query)
            elif data == "export_whatsapp":
                await self._handle_export_whatsapp(query)
            elif data == "export_all":
                await self._handle_export_all(query)
            elif data == "notifications":
                await self._handle_notifications(query)
            elif data == "add_session":
                await self._handle_add_session(query)
            elif data == "show_sessions":
                await self._handle_show_sessions(query)
            elif data == "refresh_sessions":
                await self._handle_refresh_sessions(query)
            elif data == "delete_session":
                await self._handle_delete_session(query)
            elif data.startswith("delete_session_"):
                await self._handle_delete_session_confirm(query, data)
            else:
                await query.edit_message_text("❌ أمر غير معروف")
        
        except Exception as e:
            logger.error(f"خطأ في معالجة الاستدعاء: {e}")
            await query.edit_message_text(f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_start_collect(self, query):
        """Handle start collection"""
        if self.collection_manager.get_status()['active']:
            await query.edit_message_text("⏳ الجمع يعمل بالفعل")
            return
        
        await query.edit_message_text("🚀 جاري بدء عملية الجمع...")
        
        result = await self.collection_manager.start_collection(query.from_user.id)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 الحالة", callback_data="status")]
        ])
        
        await query.edit_message_text(
            "✅ **بدأت عملية الجمع بنجاح!**\n\n"
            "**تفاصيل العملية:**\n"
            "• جاري جمع روابط تيليجرام من آخر 5 سنوات\n"
            "• جاري جمع روابط واتساب من آخر 60 يوم\n"
            "• تجاهل الروابط الميتة والمنتهية\n"
            "• جمع روابط المجموعات ذات الأعضاء فقط\n"
            "• سيتم إعلامك عند اكتمال الجمع\n\n"
            "**ملاحظات:**\n"
            "• الروابط تحفظ كما هي دون تغيير\n"
            "• تجنب تكرار الروابط\n"
            "• رابط رسالة واحد فقط من كل مجموعة",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_stop_collect(self, query):
        """Handle stop collection"""
        status = self.collection_manager.get_status()
        
        if not status['active']:
            await query.edit_message_text("⚠️ لا توجد عملية جمع نشطة")
            return
        
        await self.collection_manager.stop()
        
        await query.edit_message_text(
            "⏹️ **تم إيقاف عملية الجمع**\n\n"
            "تم حفظ جميع الروابط المجمعة حتى الآن.\n"
            "يمكنك تصدير الروابط الجديدة باستخدام /export"
        )
    
    async def _handle_pause_collect(self, query):
        """Handle pause collection"""
        status = self.collection_manager.get_status()
        
        if not status['active']:
            await query.edit_message_text("⚠️ لا توجد عملية جمع نشطة")
            return
        
        if status['paused']:
            await query.edit_message_text("⚠️ الجمع موقف مؤقتاً بالفعل")
            return
        
        await self.collection_manager.pause()
        
        await query.edit_message_text(
            "⏸️ **تم إيقاف الجمع مؤقتاً**\n\n"
            "يمكنك استئناف الجمع باستخدام زر الاستئناف."
        )
    
    async def _handle_resume_collect(self, query):
        """Handle resume collection"""
        status = self.collection_manager.get_status()
        
        if not status['active']:
            await query.edit_message_text("⚠️ لا توجد عملية جمع نشطة")
            return
        
        if not status['paused']:
            await query.edit_message_text("⚠️ الجمع يعمل بالفعل")
            return
        
        await self.collection_manager.resume()
        
        await query.edit_message_text(
            "▶️ **تم استئناف عملية الجمع**\n\n"
            "سيستمر البوت في جمع الروابط من حيث توقف."
        )
    
    async def _handle_status(self, query):
        """Handle status"""
        user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.status_command(mock_update, None)
    
    async def _handle_export(self, query):
        """Handle export"""
        user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.export_command(mock_update, None)
    
    async def _handle_export_new(self, query):
        """Handle export new links"""
        await query.edit_message_text("⏳ جاري تحضير الروابط الجديدة...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links({'only_new': True}, Config.MAX_EXPORT_LINKS)
            
            if not links:
                await query.edit_message_text("❌ لا توجد روابط جديدة للتصدير")
                return
            
            # حفظ في ملف نصي
            filename = f"new_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
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
                    caption=f"🆕 الروابط الجديدة\nعدد الروابط: {len(links):,}"
                )
            
            # تعليم الروابط كقديمة بعد التصدير
            await db.mark_links_as_old()
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await query.edit_message_text(f"✅ تم تصدير {len(links):,} رابط جديد")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الروابط الجديدة: {e}")
            await query.edit_message_text(f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_telegram(self, query):
        """Handle export Telegram links"""
        await query.edit_message_text("⏳ جاري تحضير روابط تيليجرام...")
        
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
    
    async def _handle_export_whatsapp(self, query):
        """Handle export WhatsApp links"""
        await query.edit_message_text("⏳ جاري تحضير روابط واتساب...")
        
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
    
    async def _handle_export_all(self, query):
        """Handle export all links"""
        await query.edit_message_text("⏳ جاري تحضير جميع الروابط...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links(limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await query.edit_message_text("❌ لا توجد روابط للتصدير")
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
            
            await query.edit_message_text(f"✅ تم تصدير {len(links):,} رابط")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير جميع الروابط: {e}")
            await query.edit_message_text(f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_notifications(self, query):
        """Handle notifications"""
        user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.notifications_command(mock_update, None)
    
    async def _handle_add_session(self, query):
        """Handle add session"""
        user = query.from_user
        self.user_states[user.id] = {'waiting_for_session': True}
        
        add_text = (
            f"**➕ إضافة جلسة جديدة**\n\n"
            f"**أرسل كود الجلسة الآن:**\n"
            f"(يمكنك نسخ الكود كاملاً وإرساله)"
        )
        
        await query.edit_message_text(add_text, parse_mode="Markdown")
    
    async def _handle_show_sessions(self, query):
        """Handle show sessions"""
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=20)
        
        if not sessions:
            await query.edit_message_text("❌ لا توجد جلسات نشطة")
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
        
        await query.edit_message_text(sessions_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_refresh_sessions(self, query):
        """Handle refresh sessions"""
        await self._handle_show_sessions(query)
    
    async def _handle_delete_session(self, query):
        """Handle delete session"""
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=10)
        
        if not sessions:
            await query.edit_message_text("❌ لا توجد جلسات")
            return
        
        keyboard_buttons = []
        for session in sessions:
            name = session.get('display_name', f"جلسة {session['id']}")
            callback_data = f"delete_session_{session['id']}"
            keyboard_buttons.append([InlineKeyboardButton(f"🗑️ {name}", callback_data=callback_data)])
        
        keyboard_buttons.append([InlineKeyboardButton("⬅️ رجوع", callback_data="show_sessions")])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await query.edit_message_text(
            "**🗑️ حذف الجلسات**\n\n"
            "اختر الجلسة التي تريد حذفها:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_delete_session_confirm(self, query, data):
        """Handle delete session confirmation"""
        try:
            session_id = int(data.split('_')[2])
            
            db = await EnhancedDatabaseManager.get_instance()
            
            cursor = await db.conn.execute(
                'SELECT display_name FROM sessions WHERE id = ?',
                (session_id,)
            )
            session_info = await cursor.fetchone()
            
            if not session_info:
                await query.edit_message_text("❌ الجلسة غير موجودة")
                return
            
            await db.conn.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
            await db.conn.commit()
            
            await query.edit_message_text(
                f"✅ **تم حذف الجلسة بنجاح**\n\n"
                f"• الجلسة: {session_info[0]}\n"
                f"• رقم الجلسة: {session_id}"
            )
            
        except Exception as e:
            logger.error(f"خطأ في حذف الجلسة: {e}")
            await query.edit_message_text(f"❌ حدث خطأ في حذف الجلسة: {str(e)[:100]}")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        user = update.effective_user
        text = update.message.text
        
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        user_state = self.user_states.get(user.id, {})
        
        if user_state.get('waiting_for_session'):
            await self._handle_session_input(update, text)
        else:
            await update.message.reply_text(
                "استخدم الأوامر التالية:\n"
                "/start - القائمة الرئيسية\n"
                "/collect - بدء الجمع\n"
                "/status - حالة النظام\n"
                "/export - تصدير الروابط\n"
                "/new_links - الروابط الجديدة\n"
                "/sessions - الجلسات النشطة"
            )
    
    async def _handle_session_input(self, update: Update, session_string: str):
        """Handle session string input"""
        user = update.effective_user
        
        if user.id in self.user_states:
            del self.user_states[user.id]
        
        await update.message.reply_text("⏳ جاري التحقق من الجلسة...")
        
        valid, result = await SessionManager.validate_session(session_string)
        
        if not valid:
            await update.message.reply_text(f"❌ جلسة غير صالحة: {result.get('error', 'خطأ غير معروف')}")
            return
        
        user_info = result.get('user_info', {})
        
        enc_manager = EncryptionManager.get_instance()
        encrypted_session = enc_manager.encrypt(session_string)
        
        session_data = {
            'session_string': encrypted_session,
            'phone_number': user_info.get('phone', ''),
            'user_id': user_info.get('id', 0),
            'username': user_info.get('username', ''),
            'display_name': f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip(),
            'added_by_user': user.id,
            'metadata': {
                'validated_at': datetime.now().isoformat(),
                'original_length': len(session_string)
            }
        }
        
        db = await EnhancedDatabaseManager.get_instance()
        success, message, details = await db.add_session(session_data)
        
        if success:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")]
            ])
            
            await update.message.reply_text(
                f"✅ **تمت إضافة الجلسة بنجاح!**\n\n"
                f"**معلومات المستخدم:**\n"
                f"• الاسم: {session_data['display_name']}\n"
                f"• المعرف: @{session_data['username']}\n"
                f"• رقم الجلسة: {details.get('session_id')}\n\n"
                f"**ملاحظة:**\n"
                f"الجلسة جاهزة للاستخدام في جمع الروابط",
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
    """Main function"""
    try:
        logger.info(f"🚀 تشغيل بوت جمع الروابط المتقدم")
        
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
        os.makedirs("exports", exist_ok=True)
        
        # تهيئة قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        
        # إنشاء البوت
        bot = TelegramBot()
        
        logger.info("🤖 بدء تشغيل بوت جمع الروابط...")
        logger.info(f"📢 تيليجرام: جمع من آخر {Config.TELEGRAM_COLLECT_LAST_YEARS} سنوات")
        logger.info(f"📱 واتساب: جمع من آخر {Config.WHATSAPP_COLLECT_LAST_DAYS} يوم")
        logger.info(f"✅ الروابط تحفظ كما هي دون تغيير")
        logger.info(f"✅ إشعارات عند اكتمال الجمع")
        logger.info(f"✅ قسم خاص للروابط الجديدة")
        
        try:
            # تشغيل البوت
            await bot.app.initialize()
            await bot.app.start()
            await bot.app.updater.start_polling()
            
            logger.info("✅ البوت يعمل بنجاح!")
            logger.info("📋 الأوامر المتاحة: /start, /collect, /status, /export, /new_links")
            
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
    setup_signal_handlers()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 توقف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ قاتل: {e}", exc_info=True)
        sys.exit(1)
