import os
import sys
import subprocess

# 🔧 تثبيت الحزم المطلوبة
def ensure_packages():
    """تأكد من تثبيت جميع الحزم المطلوبة"""
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
            print(f"📦 تثبيت {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# تشغيل التحقق من الحزم
ensure_packages()

# استيراد المكتبات
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
# التهيئة والإعدادات
# ======================

class Config:
    # بيانات تليجرام
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH", "")
    
    # الأمان
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
    
    # التشفير
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    
    # إدارة الذاكرة
    MAX_CACHED_URLS = 20000
    CACHE_CLEAN_INTERVAL = 1000
    MAX_MEMORY_MB = 500
    
    # إعدادات الأداء
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
    
    # حدود الجمع
    MAX_DIALOGS_PER_SESSION = 200
    MAX_MESSAGES_PER_SEARCH = 100
    MAX_SEARCH_TERMS = 8
    MAX_LINKS_PER_CYCLE = 1000
    MAX_BATCH_SIZE = 100
    
    # قاعدة البيانات
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10
    DB_POOL_SIZE = 5
    
    # جمع واتساب (60 يوماً فقط)
    WHATSAPP_DAYS_BACK = 60
    
    # جمع تليجرام (5 سنوات)
    TELEGRAM_YEARS_BACK = 5
    
    # التحقق من الروابط
    MIN_GROUP_MEMBERS = 1
    MAX_LINK_LENGTH = 200
    VALIDATION_TIMEOUT = 30
    
    # الحد من الطلبات
    USER_RATE_LIMIT = {
        'max_requests': 20,
        'per_seconds': 60
    }
    
    # إدارة الجلسات
    SESSION_TIMEOUT = 600
    MAX_SESSIONS_PER_USER = 20
    
    # التصدير
    MAX_EXPORT_LINKS = 100000
    EXPORT_CHUNK_SIZE = 5000
    
    # إعدادات متقدمة
    TELEGRAM_NO_TIME_LIMIT = False  # تم التحديد إلى 5 سنوات
    JOIN_REQUEST_CHECK_DELAY = 30
    ENABLE_ADVANCED_VALIDATION = True
    
    # إعدادات الجمع الجديدة
    COLLECT_ALL_TELEGRAM = True  # جمع كل روابط تليجرام
    TELEGRAM_COLLECTION_TYPES = {
        'bots': True,  # روابط البوتات
        'subscriptions': True,  # مجموعات المشتركين
        'join_requests': True,  # مجموعات طلب الانظمام
        'public_groups': True,  # مجموعات الأعضاء العامة
        'single_message': True  # رابط رسالة واحدة من كل مجموعة
    }
    
    # إعدادات واتساب
    WHATSAPP_COLLECTION = True  # جمع روابط واتساب
    WHATSAPP_FRESH_LINKS_ONLY = True  # روابط من آخر 60 يوماً فقط
    
    # الفلترة
    COLLECT_WITHOUT_MODIFICATION = True  # جمع الروابط كما هي بدون إضافة أو حذف
    REMOVE_DUPLICATES = True  # إزالة التكرارات بين الجلسات
    NOTIFY_COLLECTION_COMPLETE = True  # إشعار اكتمال الجمع
    NOTIFY_NEW_LINKS = True  # إشعار عند وجود روابط جديدة

# إعدادات التسجيل
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
# مدير النسخة الواحدة
# ======================

class SingleInstanceManager:
    """منع تشغيل أكثر من نسخة واحدة"""
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
        """الحصول على قفل النسخة الواحدة"""
        async with self._lock:
            if self._is_running:
                logger.error("⚠️ تم اكتشاف نسخة أخرى تعمل!")
                return False
            self._is_running = True
            return True
    
    async def release_lock(self):
        """تحرير القفل"""
        async with self._lock:
            self._is_running = False
    
    def is_running(self) -> bool:
        """التحقق من حالة التشغيل"""
        return self._is_running

# ======================
# معالج الروابط المتقدم
# ======================

class AdvancedLinkProcessor:
    """معالجة الروابط مع الحفاظ عليها كما هي"""
    
    @staticmethod
    def normalize_url(url: str) -> str:
        """تطبيع الروابط مع الحفاظ عليها كما هي"""
        if not url or not isinstance(url, str):
            return ""
        
        # تنظيف أساسي
        url = url.strip()
        
        # إضافة https:// إذا كانت مفقودة للروابط التليجرامية
        if re.search(r'^(t\.me|telegram\.me|telegram\.dog)', url, re.IGNORECASE):
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
        
        # لروابط واتساب، الحفاظ عليها كما هي
        elif re.search(r'chat\.whatsapp\.com', url, re.IGNORECASE):
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
        
        return url
    
    @staticmethod
    def extract_url_info(url: str) -> Dict:
        """استخراج معلومات الرابط"""
        normalized_url = AdvancedLinkProcessor.normalize_url(url)
        
        result = {
            'original_url': url,
            'normalized_url': normalized_url,
            'platform': 'unknown',
            'url_hash': hashlib.md5(normalized_url.encode()).hexdigest() if normalized_url else '',
            'is_valid': False,
            'category': 'unknown',
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
                result['details'] = AdvancedLinkProcessor._extract_telegram_info(normalized_url, parsed)
            elif 'whatsapp.com' in domain or 'chat.whatsapp.com' in domain:
                result['platform'] = 'whatsapp'
                result['details'] = AdvancedLinkProcessor._extract_whatsapp_info(normalized_url, parsed)
            else:
                return result
            
            result['is_valid'] = bool(result['details'].get('is_valid', False))
            
            # تحديد الفئة
            if result['platform'] == 'telegram':
                details = result['details']
                if details.get('is_bot'):
                    result['category'] = 'bot'
                elif details.get('is_subscription'):
                    result['category'] = 'subscription'
                elif details.get('is_join_request'):
                    result['category'] = 'join_request'
                elif details.get('is_public_group'):
                    result['category'] = 'public_group'
                elif details.get('is_message_link'):
                    result['category'] = 'message'
            
        except Exception as e:
            logger.debug(f"خطأ في استخراج معلومات الرابط: {e}")
        
        return result
    
    @staticmethod
    def _extract_telegram_info(url: str, parsed) -> Dict:
        """استخراج معلومات تليجرام"""
        result = {
            'is_valid': True,
            'is_bot': False,
            'is_subscription': False,
            'is_join_request': False,
            'is_public_group': False,
            'is_message_link': False,
            'is_channel': False,
            'is_group': False,
            'invite_hash': '',
            'username': '',
            'message_id': None
        }
        
        path = parsed.path.strip('/')
        if not path:
            return result
        
        segments = path.split('/')
        
        # كشف روابط البوتات
        if 'bot' in url.lower():
            result['is_bot'] = True
            return result
        
        # كشف روابط الرسائل
        if len(segments) >= 2 and segments[-1].isdigit() and len(segments[-1]) > 3:
            result['is_message_link'] = True
            result['message_id'] = int(segments[-1])
            
            # إزالة رقم الرسالة للحصول على رابط المجموعة
            if len(segments) == 2:
                result['username'] = segments[0]
                result['is_group'] = True
                result['is_public_group'] = True
        
        # كشف روابط الانضمام
        elif '+joinchat' in url.lower() or '/joinchat/' in url.lower():
            result['is_join_request'] = True
            match = re.search(r'joinchat/([A-Za-z0-9_-]+)', url, re.IGNORECASE)
            if match:
                result['invite_hash'] = match.group(1)
        
        # كشف القنوات (المشتركين)
        elif len(segments) == 1 and not path.startswith('+'):
            result['is_subscription'] = True
            result['is_channel'] = True
            result['username'] = segments[0]
        
        # كشف المجموعات العامة
        elif len(segments) == 1 or (len(segments) == 2 and not segments[-1].isdigit()):
            result['is_public_group'] = True
            result['is_group'] = True
            result['username'] = segments[0] if segments[0] else ''
        
        return result
    
    @staticmethod
    def _extract_whatsapp_info(url: str, parsed) -> Dict:
        """استخراج معلومات واتساب"""
        return {
            'is_valid': True,
            'invite_code': parsed.path.strip('/'),
            'is_group': True,
            'is_active': True,
            'original_url': url
        }

# ======================
# مدير قاعدة البيانات المتقدم
# ======================

class AdvancedDatabaseManager:
    """إدارة متقدمة لقاعدة البيانات مع الأقسام"""
    
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    
    @classmethod
    async def get_instance(cls):
        """الحصول على نسخة قاعدة البيانات"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = AdvancedDatabaseManager()
                    await cls._instance._initialize()
        return cls._instance
    
    async def _initialize(self):
        """تهيئة قاعدة البيانات"""
        if self._initialized:
            return
        
        self.db_path = Config.DB_PATH
        
        # إنشاء مجلد إذا لم يكن موجوداً
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        
        # إنشاء الاتصال
        self.conn = await aiosqlite.connect(self.db_path)
        
        # تهيئة الجداول
        await self._create_tables()
        
        self._initialized = True
        logger.info(f"✅ تم تهيئة قاعدة البيانات: {self.db_path}")
    
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
                metadata TEXT
            )
        ''')
        
        # جدول الروابط الرئيسي
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL,
                original_url TEXT,
                platform TEXT NOT NULL,
                category TEXT NOT NULL,
                collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                is_new BOOLEAN DEFAULT 1,
                is_processed BOOLEAN DEFAULT 0,
                session_id INTEGER,
                message_date TIMESTAMP,
                group_name TEXT,
                group_id INTEGER,
                metadata TEXT,
                added_by_user INTEGER,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE SET NULL
            )
        ''')
        
        # جدول الأقسام
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                platform TEXT NOT NULL,
                description TEXT,
                link_count INTEGER DEFAULT 0,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP
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
                link_count INTEGER DEFAULT 0
            )
        ''')
        
        # جدول الإشعارات
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read BOOLEAN DEFAULT 0,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES bot_users (user_id) ON DELETE CASCADE
            )
        ''')
        
        # جدول الإحصائيات
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE NOT NULL,
                total_links INTEGER DEFAULT 0,
                telegram_links INTEGER DEFAULT 0,
                whatsapp_links INTEGER DEFAULT 0,
                new_links INTEGER DEFAULT 0,
                updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await self.conn.commit()
        
        # إنشاء الفهارس
        await self._create_indexes()
        
        # تهيئة الأقسام
        await self._initialize_categories()
    
    async def _create_indexes(self):
        """إنشاء فهارس قاعدة البيانات"""
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_links_url_hash ON links(url_hash)',
            'CREATE INDEX IF NOT EXISTS idx_links_platform ON links(platform)',
            'CREATE INDEX IF NOT EXISTS idx_links_category ON links(category)',
            'CREATE INDEX IF NOT EXISTS idx_links_collected_date ON links(collected_date)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_new ON links(is_new)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_processed ON links(is_processed)',
            'CREATE INDEX IF NOT EXISTS idx_categories_name ON categories(name)',
            'CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)',
            'CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read)',
            'CREATE INDEX IF NOT EXISTS idx_statistics_date ON statistics(date)'
        ]
        
        for index_sql in indexes:
            try:
                await self.conn.execute(index_sql)
            except Exception as e:
                logger.error(f"خطأ في إنشاء الفهرس: {e}")
        
        await self.conn.commit()
    
    async def _initialize_categories(self):
        """تهيئة الأقسام المحددة"""
        categories = [
            ('telegram_bots', 'telegram', 'روابط البوتات'),
            ('telegram_subscriptions', 'telegram', 'مجموعات المشتركين'),
            ('telegram_join_requests', 'telegram', 'مجموعات طلب الانظمام'),
            ('telegram_public_groups', 'telegram', 'مجموعات الأعضاء'),
            ('telegram_messages', 'telegram', 'روابط الرسائل'),
            ('whatsapp_groups', 'whatsapp', 'مجموعات واتساب')
        ]
        
        for name, platform, description in categories:
            try:
                await self.conn.execute('''
                    INSERT OR IGNORE INTO categories (name, platform, description)
                    VALUES (?, ?, ?)
                ''', (name, platform, description))
            except Exception as e:
                logger.error(f"خطأ في إضافة القسم {name}: {e}")
        
        await self.conn.commit()
    
    async def add_link(self, link_data: Dict) -> Tuple[bool, str, Dict]:
        """إضافة رابط جديد"""
        try:
            url = link_data.get('url', '')
            url_info = AdvancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return False, "رابط غير صالح", {}
            
            url_hash = url_info['url_hash']
            
            # التحقق من التكرار
            cursor = await self.conn.execute(
                'SELECT id, is_new FROM links WHERE url_hash = ?',
                (url_hash,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                # تحديث الرابط الموجود إذا كان جديداً
                link_id = existing[0]
                is_new = existing[1]
                
                # إذا كان الرابط قديماً وأصبح جديداً (مثل رابط واتساب حديث)
                if not is_new and link_data.get('is_new', False):
                    await self.conn.execute(
                        'UPDATE links SET is_new = 1, last_checked = CURRENT_TIMESTAMP WHERE id = ?',
                        (link_id,)
                    )
                    await self.conn.commit()
                    return True, "تم تحديث الرابط إلى جديد", {'link_id': link_id, 'was_new': False}
                
                return False, "الرابط موجود مسبقاً", {'link_id': link_id}
            
            # إضافة الرابط الجديد
            cursor = await self.conn.execute('''
                INSERT INTO links 
                (url_hash, url, original_url, platform, category, 
                 session_id, message_date, group_name, group_id, 
                 metadata, added_by_user, is_new)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                url_hash,
                url_info['normalized_url'],
                url_info['original_url'],
                url_info['platform'],
                url_info['category'],
                link_data.get('session_id'),
                link_data.get('message_date'),
                link_data.get('group_name'),
                link_data.get('group_id'),
                json.dumps({
                    'url_info': url_info,
                    'collected_at': datetime.now().isoformat(),
                    'source': link_data.get('source', 'unknown')
                }),
                link_data.get('added_by_user', 0),
                link_data.get('is_new', True)
            ))
            
            link_id = cursor.lastrowid
            
            # تحديث إحصائيات القسم
            category_name = f"{url_info['platform']}_{url_info['category']}s"
            await self.conn.execute(
                'UPDATE categories SET link_count = link_count + 1, last_updated = CURRENT_TIMESTAMP WHERE name = ?',
                (category_name,)
            )
            
            # تحديث إحصائيات اليوم
            today = datetime.now().date().isoformat()
            await self.conn.execute('''
                INSERT OR REPLACE INTO statistics (date, total_links, telegram_links, whatsapp_links, new_links)
                VALUES (?, 
                    COALESCE((SELECT total_links FROM statistics WHERE date = ?), 0) + 1,
                    COALESCE((SELECT telegram_links FROM statistics WHERE date = ?), 0) + (CASE WHEN ? = 'telegram' THEN 1 ELSE 0 END),
                    COALESCE((SELECT whatsapp_links FROM statistics WHERE date = ?), 0) + (CASE WHEN ? = 'whatsapp' THEN 1 ELSE 0 END),
                    COALESCE((SELECT new_links FROM statistics WHERE date = ?), 0) + 1
                )
            ''', (today, today, today, url_info['platform'], today, url_info['platform'], today))
            
            # تحديث إحصائيات المستخدم
            if link_data.get('added_by_user'):
                await self.conn.execute(
                    'UPDATE bot_users SET link_count = link_count + 1 WHERE user_id = ?',
                    (link_data['added_by_user'],)
                )
            
            # تحديث إحصائيات الجلسة
            if link_data.get('session_id'):
                await self.conn.execute(
                    "UPDATE sessions SET total_links = total_links + 1, last_used = CURRENT_TIMESTAMP WHERE id = ?",
                    (link_data['session_id'],)
                )
            
            await self.conn.commit()
            
            logger.info(f"✅ تم إضافة رابط جديد: {url_info['category']} - {url[:50]}...")
            
            return True, "تمت إضافة الرابط بنجاح", {
                'link_id': link_id,
                'url_hash': url_hash,
                'category': url_info['category'],
                'platform': url_info['platform']
            }
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الرابط: {e}")
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def add_session(self, session_data: Dict) -> Tuple[bool, str, Dict]:
        """إضافة جلسة جديدة"""
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
                await self.conn.execute(
                    'UPDATE bot_users SET session_count = session_count + 1 WHERE user_id = ?',
                    (session_data['added_by_user'],)
                )
            
            await self.conn.commit()
            
            logger.info(f"✅ تمت إضافة جلسة جديدة: {session_data.get('display_name', 'غير معروف')}")
            
            return True, "تمت إضافة الجلسة بنجاح", {
                'session_id': session_id,
                'session_hash': session_hash
            }
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الجلسة: {e}")
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
                        last_active = CURRENT_TIMESTAMP,
                        request_count = request_count + 1
                    WHERE user_id = ?
                ''', (
                    username or '',
                    first_name or '',
                    last_name or '',
                    user_id
                ))
            else:
                await self.conn.execute('''
                    INSERT INTO bot_users (user_id, username, first_name, last_name, added_date, last_active, request_count)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                ''', (
                    user_id,
                    username or '',
                    first_name or '',
                    last_name or ''
                ))
            
            await self.conn.commit()
            
        except Exception as e:
            logger.error(f"خطأ في إضافة/تحديث المستخدم: {e}")
    
    async def add_notification(self, user_id: int, notification_type: str, message: str):
        """إضافة إشعار جديد"""
        try:
            await self.conn.execute('''
                INSERT INTO notifications (user_id, type, message)
                VALUES (?, ?, ?)
            ''', (user_id, notification_type, message))
            
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في إضافة الإشعار: {e}")
            return False
    
    async def get_user_notifications(self, user_id: int, unread_only: bool = False, limit: int = 10):
        """الحصول على إشعارات المستخدم"""
        try:
            query = '''
                SELECT id, type, message, is_read, created_date 
                FROM notifications 
                WHERE user_id = ?
            '''
            
            params = [user_id]
            
            if unread_only:
                query += ' AND is_read = 0'
            
            query += ' ORDER BY created_date DESC LIMIT ?'
            params.append(limit)
            
            cursor = await self.conn.execute(query, params)
            rows = await cursor.fetchall()
            
            notifications = []
            for row in rows:
                notifications.append({
                    'id': row[0],
                    'type': row[1],
                    'message': row[2],
                    'is_read': bool(row[3]),
                    'created_date': row[4]
                })
            
            return notifications
        except Exception as e:
            logger.error(f"خطأ في الحصول على الإشعارات: {e}")
            return []
    
    async def mark_notification_as_read(self, notification_id: int):
        """تحديد الإشعار كمقروء"""
        try:
            await self.conn.execute(
                'UPDATE notifications SET is_read = 1 WHERE id = ?',
                (notification_id,)
            )
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في تحديث الإشعار: {e}")
            return False
    
    async def get_category_stats(self):
        """الحصول على إحصائيات الأقسام"""
        try:
            cursor = await self.conn.execute('''
                SELECT c.name, c.description, c.link_count, c.last_updated,
                       COUNT(l.id) as actual_count
                FROM categories c
                LEFT JOIN links l ON (
                    CASE 
                        WHEN c.name = 'telegram_bots' THEN l.category = 'bot' AND l.platform = 'telegram'
                        WHEN c.name = 'telegram_subscriptions' THEN l.category = 'subscription' AND l.platform = 'telegram'
                        WHEN c.name = 'telegram_join_requests' THEN l.category = 'join_request' AND l.platform = 'telegram'
                        WHEN c.name = 'telegram_public_groups' THEN l.category = 'public_group' AND l.platform = 'telegram'
                        WHEN c.name = 'telegram_messages' THEN l.category = 'message' AND l.platform = 'telegram'
                        WHEN c.name = 'whatsapp_groups' THEN l.platform = 'whatsapp'
                        ELSE 0
                    END
                ) = 1
                GROUP BY c.id
                ORDER BY c.name
            ''')
            
            rows = await cursor.fetchall()
            
            stats = {}
            for row in rows:
                stats[row[0]] = {
                    'description': row[1],
                    'stored_count': row[2],
                    'actual_count': row[4],
                    'last_updated': row[3]
                }
            
            return stats
        except Exception as e:
            logger.error(f"خطأ في الحصول على إحصائيات الأقسام: {e}")
            return {}
    
    async def get_new_links_count(self) -> int:
        """الحصول على عدد الروابط الجديدة"""
        try:
            cursor = await self.conn.execute(
                'SELECT COUNT(*) FROM links WHERE is_new = 1'
            )
            result = await cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"خطأ في الحصول على عدد الروابط الجديدة: {e}")
            return 0
    
    async def mark_all_links_as_processed(self):
        """تحديد جميع الروابط كمُعالجة"""
        try:
            await self.conn.execute(
                'UPDATE links SET is_new = 0, is_processed = 1 WHERE is_new = 1'
            )
            await self.conn.commit()
            
            # تحديث إحصائيات اليوم
            today = datetime.now().date().isoformat()
            await self.conn.execute('''
                UPDATE statistics 
                SET new_links = 0 
                WHERE date = ?
            ''', (today,))
            
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في تحديث حالة الروابط: {e}")
            return False
    
    async def get_links_by_category(self, category: str, platform: str = None, 
                                   limit: int = 1000, new_only: bool = False) -> List[str]:
        """الحصول على روابط حسب الفئة"""
        try:
            query = 'SELECT url FROM links WHERE 1=1'
            params = []
            
            if platform:
                query += ' AND platform = ?'
                params.append(platform)
            
            query += ' AND category = ?'
            params.append(category)
            
            if new_only:
                query += ' AND is_new = 1'
            
            query += ' ORDER BY collected_date DESC LIMIT ?'
            params.append(limit)
            
            cursor = await self.conn.execute(query, params)
            rows = await cursor.fetchall()
            
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"خطأ في الحصول على روابط الفئة: {e}")
            return []
    
    async def get_total_stats(self) -> Dict:
        """الحصول على إحصائيات عامة"""
        try:
            stats = {}
            
            # إجمالي الروابط
            cursor = await self.conn.execute('SELECT COUNT(*) FROM links')
            stats['total_links'] = (await cursor.fetchone())[0]
            
            # الروابط الجديدة
            cursor = await self.conn.execute('SELECT COUNT(*) FROM links WHERE is_new = 1')
            stats['new_links'] = (await cursor.fetchone())[0]
            
            # الروابط حسب المنصة
            cursor = await self.conn.execute("SELECT platform, COUNT(*) FROM links GROUP BY platform")
            stats['by_platform'] = dict(await cursor.fetchall())
            
            # الروابط حسب الفئة
            cursor = await self.conn.execute("SELECT category, COUNT(*) FROM links GROUP BY category")
            stats['by_category'] = dict(await cursor.fetchall())
            
            # الجلسات النشطة
            cursor = await self.conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            # المستخدمين
            cursor = await self.conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            return stats
        except Exception as e:
            logger.error(f"خطأ في الحصول على الإحصائيات: {e}")
            return {}
    
    async def close(self):
        """إغلاق اتصال قاعدة البيانات"""
        if hasattr(self, 'conn'):
            await self.conn.close()
            self._initialized = False

# ======================
# مدير الجلسات
# ======================

class SessionManager:
    """إدارة جلسات تليجرام"""
    
    @staticmethod
    async def validate_session(session_string: str) -> Tuple[bool, Dict]:
        """التحقق من صحة الجلسة"""
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
        """إنشاء عميل تليجرام"""
        try:
            session_string = session_string.strip()
            
            if len(session_string) < 50:
                logger.error(f"جلسة قصيرة جداً: {len(session_string)} حرف")
                return None
            
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH,
                device_model="Telegram Link Collector",
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
# مدير التجميع المتقدم
# ======================

class AdvancedCollectionManager:
    """مدير تجميع متقدم مع تقسيم إلى أقسام"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        self.stats = {
            'total_collected': 0,
            'telegram_collected': 0,
            'whatsapp_collected': 0,
            'categories': defaultdict(int),
            'sessions_used': 0,
            'groups_processed': 0,
            'messages_scanned': 0,
            'errors': 0,
            'collection_start_time': None,
            'collection_end_time': None,
            'status': 'stopped'
        }
        self.collection_task = None
        self.collected_hashes = set()
    
    async def start_collection(self, user_id: int = None):
        """بدء عملية التجميع"""
        if self.active:
            return
        
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.stats['collection_start_time'] = datetime.now().isoformat()
        self.stats['status'] = 'collecting'
        
        # تحميل الهاشات المجمعة مسبقاً
        await self._load_collected_hashes()
        
        logger.info("🚀 بدء عملية التجميع المتقدم...")
        
        # إرسال إشعار البدء
        if user_id:
            db = await AdvancedDatabaseManager.get_instance()
            await db.add_notification(
                user_id,
                'collection_started',
                '🚀 بدأ التجميع المتقدم لجمع جميع روابط تليجرام وواتساب'
            )
        
        # بدء مهمة التجميع
        self.collection_task = asyncio.create_task(self._collection_process(user_id))
    
    async def _load_collected_hashes(self):
        """تحميل الهاشات المجمعة مسبقاً"""
        try:
            db = await AdvancedDatabaseManager.get_instance()
            cursor = await db.conn.execute('SELECT url_hash FROM links')
            rows = await cursor.fetchall()
            
            self.collected_hashes = set(row[0] for row in rows)
            logger.info(f"📊 تم تحميل {len(self.collected_hashes)} رابط مجمع مسبقاً")
        except Exception as e:
            logger.error(f"خطأ في تحميل الهاشات: {e}")
    
    async def _collection_process(self, user_id: int = None):
        """عملية التجميع الرئيسية"""
        try:
            db = await AdvancedDatabaseManager.get_instance()
            
            # جمع من تليجرام أولاً
            if Config.COLLECT_ALL_TELEGRAM:
                await self._collect_telegram_links(db, user_id)
            
            # جمع من واتساب
            if Config.WHATSAPP_COLLECTION:
                await self._collect_whatsapp_links(db, user_id)
            
            # إكمال التجميع
            await self._complete_collection(db, user_id)
            
        except Exception as e:
            logger.error(f"خطأ في عملية التجميع: {e}")
            self.stats['errors'] += 1
            
            # إرسال إشعار بالخطأ
            if user_id:
                db = await AdvancedDatabaseManager.get_instance()
                await db.add_notification(
                    user_id,
                    'collection_error',
                    f'❌ حدث خطأ في التجميع: {str(e)[:100]}'
                )
        
        finally:
            self.active = False
            self.stats['collection_end_time'] = datetime.now().isoformat()
            self.stats['status'] = 'stopped'
            logger.info("⏹️ توقفت عملية التجميع")
    
    async def _collect_telegram_links(self, db, user_id: int = None):
        """تجميع روابط تليجرام"""
        try:
            sessions = await db.get_active_sessions()
            
            if not sessions:
                logger.warning("لا توجد جلسات نشطة")
                return
            
            self.stats['sessions_used'] = len(sessions)
            
            for session in sessions:
                if self.stop_requested or self.paused:
                    break
                
                try:
                    await self._process_telegram_session(session, db, user_id)
                    await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
                except Exception as e:
                    logger.error(f"خطأ في معالجة الجلسة: {e}")
                    self.stats['errors'] += 1
            
            logger.info(f"✅ اكتمل تجميع تليجرام: {self.stats['telegram_collected']} رابط")
            
        except Exception as e:
            logger.error(f"خطأ في تجميع تليجرام: {e}")
    
    async def _process_telegram_session(self, session: Dict, db, user_id: int = None):
        """معالجة جلسة تليجرام"""
        try:
            session_string = session.get('session_string', '')
            session_id = session.get('id')
            
            if not session_string or session_string == '********':
                return
            
            # فك تشفير الجلسة
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt(session_string)
            
            client = await SessionManager.create_client(decrypted_session)
            if not client:
                return
            
            logger.info(f"📱 بدء التجميع من جلسة: {session.get('display_name', 'غير معروف')}")
            
            # حساب تاريخ 5 سنوات مضت
            five_years_ago = datetime.now() - timedelta(days=Config.TELEGRAM_YEARS_BACK * 365)
            
            # جمع من جميع الدردشات
            collected_in_session = 0
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                if self.stop_requested or self.paused:
                    break
                
                try:
                    await self._collect_from_telegram_dialog(client, dialog, session_id, db, user_id, five_years_ago)
                    collected_in_session += 1
                    self.stats['groups_processed'] += 1
                    
                    await asyncio.sleep(Config.REQUEST_DELAYS['between_groups'])
                    
                except Exception as e:
                    logger.debug(f"خطأ في جمع الروابط من الدردشة: {e}")
                    continue
            
            await client.disconnect()
            
            # تحديث إحصائيات الجلسة
            await db.conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, last_success = CURRENT_TIMESTAMP, total_uses = total_uses + 1 WHERE id = ?",
                (session_id,)
            )
            await db.conn.commit()
            
            logger.info(f"✅ انتهى التجميع من الجلسة: {collected_in_session} دردشة")
            
        except Exception as e:
            logger.error(f"خطأ في معالجة جلسة تليجرام: {e}")
    
    async def _collect_from_telegram_dialog(self, client, dialog, session_id: int, db, user_id: int, min_date):
        """جمع الروابط من دردشة تليجرام"""
        try:
            entity = dialog.entity
            
            # تخطي المحادثات الخاصة
            if not hasattr(entity, 'title'):
                return
            
            group_title = getattr(entity, 'title', 'غير معروف')
            group_id = getattr(entity, 'id', 0)
            
            logger.info(f"🔍 جمع من: {group_title}")
            
            # جمع الروابط من الوصف
            if hasattr(entity, 'about'):
                await self._extract_links_from_text(
                    entity.about or '', 
                    'description', 
                    group_title, 
                    group_id, 
                    session_id, 
                    db, 
                    user_id, 
                    datetime.now()
                )
            
            # جمع الروابط من الرسائل (آخر 5 سنوات)
            message_links_collected = set()  # لمنع تكرار روابط الرسائل
            
            async for message in client.iter_messages(
                entity, 
                limit=Config.MAX_MESSAGES_PER_SEARCH,
                offset_date=min_date
            ):
                if self.stop_requested or self.paused:
                    break
                
                try:
                    # جمع من نص الرسالة
                    if message.text:
                        collected = await self._extract_links_from_text(
                            message.text,
                            'message',
                            group_title,
                            group_id,
                            session_id,
                            db,
                            user_id,
                            message.date
                        )
                        
                        # إذا كان رابط رسالة، نضيفه مرة واحدة فقط
                        for link_data in collected:
                            if link_data['category'] == 'message':
                                if link_data['url_hash'] in message_links_collected:
                                    continue
                                message_links_collected.add(link_data['url_hash'])
                    
                    # جمع من أزرار الرسالة
                    if hasattr(message, 'reply_markup') and message.reply_markup:
                        await self._extract_links_from_buttons(
                            message.reply_markup,
                            group_title,
                            group_id,
                            session_id,
                            db,
                            user_id,
                            message.date
                        )
                    
                    self.stats['messages_scanned'] += 1
                    
                    # تأخير بين الرسائل
                    if self.stats['messages_scanned'] % 10 == 0:
                        await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.debug(f"خطأ في معالجة الرسالة: {e}")
                    continue
            
            logger.info(f"✅ تمت معالجة {self.stats['messages_scanned']} رسالة في {group_title}")
            
        except Exception as e:
            logger.debug(f"خطأ في جمع الروابط من الدردشة: {e}")
    
    async def _collect_whatsapp_links(self, db, user_id: int = None):
        """تجميع روابط واتساب"""
        try:
            sessions = await db.get_active_sessions()
            
            if not sessions:
                return
            
            # حساب تاريخ 60 يوماً مضت
            sixty_days_ago = datetime.now() - timedelta(days=Config.WHATSAPP_DAYS_BACK)
            
            for session in sessions:
                if self.stop_requested or self.paused:
                    break
                
                try:
                    await self._process_whatsapp_session(session, db, user_id, sixty_days_ago)
                    await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
                except Exception as e:
                    logger.error(f"خطأ في معالجة جلسة واتساب: {e}")
            
            logger.info(f"✅ اكتمل تجميع واتساب: {self.stats['whatsapp_collected']} رابط")
            
        except Exception as e:
            logger.error(f"خطأ في تجميع واتساب: {e}")
    
    async def _process_whatsapp_session(self, session: Dict, db, user_id: int, min_date):
        """معالجة جلسة واتساب"""
        try:
            session_string = session.get('session_string', '')
            session_id = session.get('id')
            
            if not session_string or session_string == '********':
                return
            
            # فك تشفير الجلسة
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt(session_string)
            
            client = await SessionManager.create_client(decrypted_session)
            if not client:
                return
            
            logger.info(f"📱 بدء تجميع واتساب من جلسة: {session.get('display_name', 'غير معروف')}")
            
            # البحث عن روابط واتساب في الرسائل
            whatsapp_keywords = ['chat.whatsapp.com', 'whatsapp.com']
            collected_in_session = 0
            
            for keyword in whatsapp_keywords:
                if self.stop_requested or self.paused:
                    break
                
                try:
                    async for message in client.iter_messages(
                        None,  # البحث في كل الدردشات
                        search=keyword,
                        limit=100
                    ):
                        if self.stop_requested or self.paused:
                            break
                        
                        # التحقق من تاريخ الرسالة (60 يوماً فقط)
                        if message.date < min_date:
                            continue
                        
                        if message.text:
                            await self._extract_whatsapp_links_from_text(
                                message.text,
                                session_id,
                                db,
                                user_id,
                                message.date
                            )
                            collected_in_session += 1
                        
                        await asyncio.sleep(0.1)
                    
                    await asyncio.sleep(Config.REQUEST_DELAYS['search'])
                    
                except Exception as e:
                    logger.debug(f"خطأ في البحث عن {keyword}: {e}")
                    continue
            
            await client.disconnect()
            
            logger.info(f"✅ انتهى تجميع واتساب من الجلسة: {collected_in_session} رابط")
            
        except Exception as e:
            logger.error(f"خطأ في معالجة جلسة واتساب: {e}")
    
    async def _extract_links_from_text(self, text: str, source: str, group_title: str, 
                                      group_id: int, session_id: int, db, user_id: int, 
                                      message_date) -> List[Dict]:
        """استخراج الروابط من النص"""
        if not text:
            return []
        
        links = []
        
        # البحث عن روابط تليجرام
        telegram_patterns = [
            r'https?://(?:t\.me|telegram\.me|telegram\.dog)/[^\s<>"\']+',
            r't\.me/[^\s<>"\']+',
            r'telegram\.me/[^\s<>"\']+',
            r'telegram\.dog/[^\s<>"\']+'
        ]
        
        for pattern in telegram_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                url = match.group(0)
                await self._process_telegram_link(
                    url, source, group_title, group_id, 
                    session_id, db, user_id, message_date, links
                )
        
        return links
    
    async def _extract_whatsapp_links_from_text(self, text: str, session_id: int, 
                                               db, user_id: int, message_date):
        """استخراج روابط واتساب من النص"""
        if not text:
            return
        
        whatsapp_patterns = [
            r'https?://(?:chat\.whatsapp\.com|whatsapp\.com)/[^\s<>"\']+',
            r'chat\.whatsapp\.com/[^\s<>"\']+',
            r'whatsapp\.com/[^\s<>"\']+'
        ]
        
        for pattern in whatsapp_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                url = match.group(0)
                await self._process_whatsapp_link(url, session_id, db, user_id, message_date)
    
    async def _extract_links_from_buttons(self, reply_markup, group_title: str, 
                                         group_id: int, session_id: int, db, 
                                         user_id: int, message_date):
        """استخراج الروابط من أزرار الرسالة"""
        try:
            for row in reply_markup.rows:
                for button in row.buttons:
                    if hasattr(button, 'url') and button.url:
                        url = button.url
                        
                        # تحديد نوع الرابط
                        if 't.me' in url or 'telegram.' in url:
                            await self._process_telegram_link(
                                url, 'button', group_title, group_id,
                                session_id, db, user_id, message_date, []
                            )
                        elif 'whatsapp.com' in url:
                            await self._process_whatsapp_link(
                                url, session_id, db, user_id, message_date
                            )
        except Exception as e:
            logger.debug(f"خطأ في استخراج الروابط من الأزرار: {e}")
    
    async def _process_telegram_link(self, url: str, source: str, group_title: str, 
                                    group_id: int, session_id: int, db, user_id: int, 
                                    message_date, links_list: List):
        """معالجة رابط تليجرام"""
        try:
            # تطبيع الرابط
            normalized_url = AdvancedLinkProcessor.normalize_url(url)
            if not normalized_url:
                return
            
            url_info = AdvancedLinkProcessor.extract_url_info(normalized_url)
            if not url_info['is_valid'] or url_info['platform'] != 'telegram':
                return
            
            # التحقق من التكرار
            url_hash = url_info['url_hash']
            if url_hash in self.collected_hashes:
                return
            
            # التحقق من أنواع التجميع المطلوبة
            category = url_info['category']
            if category == 'bot' and not Config.TELEGRAM_COLLECTION_TYPES.get('bots', True):
                return
            elif category == 'subscription' and not Config.TELEGRAM_COLLECTION_TYPES.get('subscriptions', True):
                return
            elif category == 'join_request' and not Config.TELEGRAM_COLLECTION_TYPES.get('join_requests', True):
                return
            elif category == 'public_group' and not Config.TELEGRAM_COLLECTION_TYPES.get('public_groups', True):
                return
            elif category == 'message' and not Config.TELEGRAM_COLLECTION_TYPES.get('single_message', True):
                return
            
            # إضافة الرابط
            link_data = {
                'url': normalized_url,
                'session_id': session_id,
                'message_date': message_date.isoformat() if message_date else None,
                'group_name': group_title,
                'group_id': group_id,
                'added_by_user': user_id,
                'source': source,
                'is_new': True
            }
            
            success, message, details = await db.add_link(link_data)
            
            if success:
                self.collected_hashes.add(url_hash)
                self.stats['total_collected'] += 1
                self.stats['telegram_collected'] += 1
                self.stats['categories'][category] += 1
                
                links_list.append({
                    'url': normalized_url,
                    'category': category,
                    'url_hash': url_hash
                })
                
                # تسجيل كل 50 رابط
                if self.stats['total_collected'] % 50 == 0:
                    logger.info(f"✅ تم تجميع {self.stats['total_collected']} رابط حتى الآن")
                    
        except Exception as e:
            logger.error(f"خطأ في معالجة رابط تليجرام: {e}")
    
    async def _process_whatsapp_link(self, url: str, session_id: int, db, user_id: int, message_date):
        """معالجة رابط واتساب"""
        try:
            # تطبيع الرابط
            normalized_url = AdvancedLinkProcessor.normalize_url(url)
            if not normalized_url:
                return
            
            url_info = AdvancedLinkProcessor.extract_url_info(normalized_url)
            if not url_info['is_valid'] or url_info['platform'] != 'whatsapp':
                return
            
            # التحقق من التكرار
            url_hash = url_info['url_hash']
            if url_hash in self.collected_hashes:
                return
            
            # إضافة الرابط
            link_data = {
                'url': normalized_url,
                'session_id': session_id,
                'message_date': message_date.isoformat() if message_date else None,
                'added_by_user': user_id,
                'source': 'whatsapp_collection',
                'is_new': True
            }
            
            success, message, details = await db.add_link(link_data)
            
            if success:
                self.collected_hashes.add(url_hash)
                self.stats['total_collected'] += 1
                self.stats['whatsapp_collected'] += 1
                self.stats['categories']['whatsapp'] += 1
                
                # تسجيل كل 50 رابط
                if self.stats['total_collected'] % 50 == 0:
                    logger.info(f"✅ تم تجميع {self.stats['total_collected']} رابط حتى الآن")
                    
        except Exception as e:
            logger.error(f"خطأ في معالجة رابط واتساب: {e}")
    
    async def _complete_collection(self, db, user_id: int = None):
        """إكمال عملية التجميع"""
        try:
            # تحديث حالة الروابط
            await db.mark_all_links_as_processed()
            
            # إرسال إشعار اكتمال التجميع
            if user_id and Config.NOTIFY_COLLECTION_COMPLETE:
                message = (
                    f"✅ **اكتمل التجميع بنجاح!**\n\n"
                    f"**الإحصائيات:**\n"
                    f"• إجمالي الروابط: {self.stats['total_collected']:,}\n"
                    f"• روابط تليجرام: {self.stats['telegram_collected']:,}\n"
                    f"• روابط واتساب: {self.stats['whatsapp_collected']:,}\n"
                    f"• المجموعات المعالجة: {self.stats['groups_processed']:,}\n"
                    f"• الرسائل المفحوصة: {self.stats['messages_scanned']:,}\n\n"
                    f"**توزيع تليجرام:**\n"
                )
                
                for category, count in self.stats['categories'].items():
                    if category != 'whatsapp':
                        message += f"• {category}: {count:,}\n"
                
                await db.add_notification(user_id, 'collection_complete', message)
            
            logger.info(f"🎉 اكتمل التجميع بنجاح! تم تجميع {self.stats['total_collected']} رابط")
            
        except Exception as e:
            logger.error(f"خطأ في إكمال التجميع: {e}")
    
    async def check_for_new_links(self, user_id: int):
        """التحقق من وجود روابط جديدة"""
        try:
            db = await AdvancedDatabaseManager.get_instance()
            new_count = await db.get_new_links_count()
            
            if new_count > 0:
                message = f"🆕 **تم العثور على {new_count} رابط جديد!**\n\nيمكنك تصديرها من قسم الروابط الجديدة."
                await db.add_notification(user_id, 'new_links', message)
                return True
            
            return False
        except Exception as e:
            logger.error(f"خطأ في التحقق من الروابط الجديدة: {e}")
            return False
    
    def get_status(self) -> Dict:
        """الحصول على حالة التجميع"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'stats': self.stats.copy()
        }
    
    async def pause(self):
        """إيقاف التجميع مؤقتاً"""
        self.paused = True
        self.stats['status'] = 'paused'
        logger.info("⏸️ تم إيقاف التجميع مؤقتاً")
    
    async def resume(self):
        """استئناف التجميع"""
        self.paused = False
        self.stats['status'] = 'collecting'
        logger.info("▶️ تم استئناف التجميع")
    
    async def stop(self):
        """إيقاف التجميع"""
        self.stop_requested = True
        logger.info("⏹️ تم طلب إيقاف التجميع")
        
        if self.collection_task:
            try:
                await asyncio.wait_for(self.collection_task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("مهلة انتظار إيقاف مهمة التجميع")
        
        self.active = False
        self.stats['status'] = 'stopped'

# ======================
# مدير التشفير
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
            salt=b'advanced_link_collector',
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
# البوت الرئيسي
# ======================

class AdvancedTelegramBot:
    """بوت تليجرام متقدم للتجميع"""
    
    def __init__(self):
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        self.collection_manager = AdvancedCollectionManager()
        
        self._setup_handlers()
        
        self.user_states = {}
    
    def _setup_handlers(self):
        """إعداد معالجات البوت"""
        # الأوامر الأساسية
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("notifications", self.notifications_command))
        
        # إدارة الجلسات
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        self.app.add_handler(CommandHandler("addsession", self.add_session_command))
        
        # التجميع
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        self.app.add_handler(CommandHandler("collect_all", self.collect_all_command))
        self.app.add_handler(CommandHandler("pause_collect", self.pause_collect_command))
        self.app.add_handler(CommandHandler("resume_collect", self.resume_collect_command))
        self.app.add_handler(CommandHandler("stop_collect", self.stop_collect_command))
        
        # التصدير
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("export_new", self.export_new_command))
        self.app.add_handler(CommandHandler("export_category", self.export_category_command))
        
        # الإدارة
        self.app.add_handler(CommandHandler("check_new", self.check_new_command))
        self.app.add_handler(CommandHandler("mark_read", self.mark_read_command))
        self.app.add_handler(CommandHandler("clear_new", self.clear_new_command))
        
        # معالجات الاستدعاء
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # معالجات الرسائل
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
        
        # إضافة/تحديث المستخدم
        db = await AdvancedDatabaseManager.get_instance()
        await db.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء التجميع الشامل", callback_data="start_collection"),
             InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")],
            [InlineKeyboardButton("📁 الأقسام", callback_data="show_categories"),
             InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_menu")],
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("👥 الجلسات", callback_data="show_sessions")],
            [InlineKeyboardButton("🔔 الإشعارات", callback_data="show_notifications"),
             InlineKeyboardButton("🆕 روابط جديدة", callback_data="check_new_links")]
        ])
        
        welcome_text = (
            f"🤖 **مرحباً {user.first_name}!**\n\n"
            "**بوت التجميع المتقدم لروابط تليجرام وواتساب**\n\n"
            "**المميزات:**\n"
            "✅ جمع جميع روابط تليجرام النشطة (5 سنوات)\n"
            "📱 جمع روابط واتساب النشطة (60 يوماً فقط)\n"
            "📁 تقسيم تلقائي إلى أقسام محددة\n"
            "🔄 منع التكرار بين الجلسات\n"
            "🔔 إشعارات عند اكتمال التجميع\n"
            "🆕 قسم للروابط الجديدة\n\n"
            "**أقسام تليجرام:**\n"
            "• 🤖 روابط البوتات\n"
            "• 📢 مجموعات المشتركين\n"
            "• 🎯 مجموعات طلب الانظمام\n"
            "• 👥 مجموعات الأعضاء\n"
            "• 📨 روابط الرسائل\n\n"
            "استخدم الأزرار أدناه للتحكم."
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
        
        status_text = (
            f"**📊 حالة النظام**\n\n"
            f"**حالة التجميع:** {status['stats']['status']}\n"
            f"**نشط:** {'✅ نعم' if status['active'] else '❌ لا'}\n"
            f"**مؤقت:** {'✅ نعم' if status['paused'] else '❌ لا'}\n"
            f"**طلب إيقاف:** {'✅ نعم' if status['stop_requested'] else '❌ لا'}\n\n"
            f"**الإحصائيات الحالية:**\n"
            f"• إجمالي المجموع: {status['stats']['total_collected']:,}\n"
            f"• تليجرام: {status['stats']['telegram_collected']:,}\n"
            f"• واتساب: {status['stats']['whatsapp_collected']:,}\n"
            f"• المجموعات: {status['stats']['groups_processed']:,}\n"
            f"• الرسائل: {status['stats']['messages_scanned']:,}\n"
            f"• الجلسات: {status['stats']['sessions_used']}\n"
            f"• الأخطاء: {status['stats']['errors']:,}\n\n"
        )
        
        if status['stats']['categories']:
            status_text += "**التوزيع:**\n"
            for category, count in status['stats']['categories'].items():
                status_text += f"• {category}: {count:,}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_status"),
             InlineKeyboardButton("📊 إحصائيات مفصلة", callback_data="show_stats")],
            [InlineKeyboardButton("🚀 بدء التجميع", callback_data="start_collection"),
             InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collection")]
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
        
        db = await AdvancedDatabaseManager.get_instance()
        stats = await db.get_total_stats()
        category_stats = await db.get_category_stats()
        
        stats_text = (
            f"**📈 إحصائيات النظام**\n\n"
            f"**إجمالي الروابط:** {stats.get('total_links', 0):,}\n"
            f"**الروابط الجديدة:** {stats.get('new_links', 0):,}\n"
            f"**الجلسات النشطة:** {stats.get('active_sessions', 0)}\n"
            f"**المستخدمين:** {stats.get('total_users', 0)}\n\n"
            f"**حسب المنصة:**\n"
        )
        
        for platform, count in stats.get('by_platform', {}).items():
            stats_text += f"• {platform}: {count:,}\n"
        
        stats_text += f"\n**حسب الفئة:**\n"
        for category, count in stats.get('by_category', {}).items():
            stats_text += f"• {category}: {count:,}\n"
        
        stats_text += f"\n**تفاصيل الأقسام:**\n"
        for category, details in category_stats.items():
            stats_text += f"• {details['description']}: {details['actual_count']:,}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_stats"),
             InlineKeyboardButton("📁 الأقسام", callback_data="show_categories")],
            [InlineKeyboardButton("📤 تصدير", callback_data="export_menu"),
             InlineKeyboardButton("🚀 تجميع جديد", callback_data="start_collection")]
        ])
        
        await update.message.reply_text(stats_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def notifications_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /notifications"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await AdvancedDatabaseManager.get_instance()
        notifications = await db.get_user_notifications(user.id, limit=20)
        
        if not notifications:
            await update.message.reply_text("📭 لا توجد إشعارات")
            return
        
        notifications_text = "**🔔 الإشعارات الأخيرة**\n\n"
        
        for i, notification in enumerate(notifications, 1):
            status = "✅" if notification['is_read'] else "🆕"
            date = notification['created_date'][:19] if notification['created_date'] else "غير معروف"
            notifications_text += (
                f"{i}. {status} **{notification['type']}**\n"
                f"{notification['message']}\n"
                f"📅 {date}\n\n"
            )
        
        keyboard_buttons = []
        for notification in notifications[:5]:
            if not notification['is_read']:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        f"✅ تحديد كمقروء: {notification['id']}", 
                        callback_data=f"mark_read_{notification['id']}"
                    )
                ])
        
        keyboard_buttons.append([
            InlineKeyboardButton("🗑️ مسح الكل", callback_data="clear_notifications"),
            InlineKeyboardButton("🔄 تحديث", callback_data="refresh_notifications")
        ])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await update.message.reply_text(notifications_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /sessions"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await AdvancedDatabaseManager.get_instance()
        cursor = await db.conn.execute('''
            SELECT id, display_name, username, phone_number, total_uses, total_links, 
                   last_used, status, is_active
            FROM sessions 
            WHERE is_active = 1
            ORDER BY last_used DESC
            LIMIT 20
        ''')
        
        sessions = await cursor.fetchall()
        
        if not sessions:
            await update.message.reply_text("❌ لا توجد جلسات نشطة")
            return
        
        sessions_text = "**👥 الجلسات النشطة**\n\n"
        
        for session in sessions:
            status = "✅ نشط" if session[7] == 'active' else "❌ غير نشط"
            last_used = session[6][:19] if session[6] else "لم يستخدم"
            
            sessions_text += (
                f"**{session[1]}**\n"
                f"• المعرف: @{session[2]}\n"
                f"• الهاتف: {session[3]}\n"
                f"• الاستخدامات: {session[4]}\n"
                f"• الروابط: {session[5]:,}\n"
                f"• آخر استخدام: {last_used}\n"
                f"• الحالة: {status}\n\n"
            )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("🗑️ حذف جلسة", callback_data="delete_session")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_sessions")]
        ])
        
        await update.message.reply_text(sessions_text, reply_markup=keyboard, parse_mode="Markdown")
    
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
            "**أرسل كود الجلسة الآن:**\n\n"
            "**ملاحظات:**\n"
            "• الجلسة تستخدم للتجميع فقط\n"
            "• تخزن مشفرة\n"
            "• يمكنك إضافة حتى 20 جلسة\n"
            "• يجب أن تكون الجلسة نشطة"
        )
        
        await update.message.reply_text(add_text, parse_mode="Markdown")
    
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
            [InlineKeyboardButton("🚀 بدء التجميع", callback_data="start_collection"),
             InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collection")],
            [InlineKeyboardButton("▶️ استئناف", callback_data="resume_collection"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collection")],
            [InlineKeyboardButton("📊 الحالة", callback_data="collection_status"),
             InlineKeyboardButton("🔄 فحص جديد", callback_data="check_new_links")]
        ])
        
        collect_text = (
            f"**🚀 إدارة التجميع**\n\n"
            f"**الحالة:** {status['stats']['status']}\n\n"
            f"**إعدادات تليجرام:**\n"
            f"• البوتات: {'✅' if Config.TELEGRAM_COLLECTION_TYPES['bots'] else '❌'}\n"
            f"• المشتركين: {'✅' if Config.TELEGRAM_COLLECTION_TYPES['subscriptions'] else '❌'}\n"
            f"• طلب الانظمام: {'✅' if Config.TELEGRAM_COLLECTION_TYPES['join_requests'] else '❌'}\n"
            f"• مجموعات الأعضاء: {'✅' if Config.TELEGRAM_COLLECTION_TYPES['public_groups'] else '❌'}\n"
            f"• روابط الرسائل: {'✅' if Config.TELEGRAM_COLLECTION_TYPES['single_message'] else '❌'}\n"
            f"• الفترة: {Config.TELEGRAM_YEARS_BACK} سنوات\n\n"
            f"**إعدادات واتساب:**\n"
            f"• التجميع: {'✅' if Config.WHATSAPP_COLLECTION else '❌'}\n"
            f"• الفترة: {Config.WHATSAPP_DAYS_BACK} يوم\n\n"
            f"**المميزات:**\n"
            f"• منع التكرار: {'✅' if Config.REMOVE_DUPLICATES else '❌'}\n"
            f"• إشعارات: {'✅' if Config.NOTIFY_COLLECTION_COMPLETE else '❌'}\n"
            f"• روابط جديدة: {'✅' if Config.NOTIFY_NEW_LINKS else '❌'}"
        )
        
        await update.message.reply_text(collect_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def collect_all_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /collect_all"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        if self.collection_manager.active:
            await update.message.reply_text("⚠️ التجميع يعمل بالفعل")
            return
        
        await update.message.reply_text("🚀 بدأ التجميع الشامل...")
        
        # بدء التجميع
        await self.collection_manager.start_collection(user.id)
        
        await update.message.reply_text(
            "✅ **بدأ التجميع الشامل بنجاح!**\n\n"
            "**جاري:**\n"
            "• جمع جميع روابط تليجرام النشطة\n"
            "• جمع روابط واتساب من آخر 60 يوماً\n"
            "• تقسيم الروابط إلى أقسام\n"
            "• منع التكرار بين الجلسات\n\n"
            "سيتم إعلامك عند اكتمال التجميع.",
            parse_mode="Markdown"
        )
    
    async def pause_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /pause_collect"""
        if not self.collection_manager.active:
            await update.message.reply_text("⚠️ التجميع غير نشط")
            return
        
        await self.collection_manager.pause()
        await update.message.reply_text("⏸️ تم إيقاف التجميع مؤقتاً")
    
    async def resume_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /resume_collect"""
        if not self.collection_manager.active:
            await update.message.reply_text("⚠️ التجميع غير نشط")
            return
        
        if not self.collection_manager.paused:
            await update.message.reply_text("⚠️ التجميع ليس متوقفاً مؤقتاً")
            return
        
        await self.collection_manager.resume()
        await update.message.reply_text("▶️ تم استئناف التجميع")
    
    async def stop_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /stop_collect"""
        if not self.collection_manager.active:
            await update.message.reply_text("⚠️ التجميع غير نشط")
            return
        
        await self.collection_manager.stop()
        await update.message.reply_text("⏹️ تم إيقاف التجميع")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /export"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await AdvancedDatabaseManager.get_instance()
        stats = await db.get_total_stats()
        
        if stats.get('total_links', 0) == 0:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء التجميع", callback_data="start_collection"),
                 InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session")]
            ])
            await update.message.reply_text(
                "❌ **لا توجد روابط للتصدير**\n\n"
                "ابدأ التجميع أولاً لجمع الروابط.",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📁 جميع الأقسام", callback_data="export_all_categories")],
            [InlineKeyboardButton("🤖 تليجرام - بوتات", callback_data="export_category_bot"),
             InlineKeyboardButton("📢 تليجرام - مشتركين", callback_data="export_category_subscription")],
            [InlineKeyboardButton("🎯 تليجرام - طلب انظمام", callback_data="export_category_join_request"),
             InlineKeyboardButton("👥 تليجرام - مجموعات", callback_data="export_category_public_group")],
            [InlineKeyboardButton("📨 تليجرام - رسائل", callback_data="export_category_message"),
             InlineKeyboardButton("📱 واتساب - مجموعات", callback_data="export_category_whatsapp")],
            [InlineKeyboardButton("🆕 الروابط الجديدة فقط", callback_data="export_new_links"),
             InlineKeyboardButton("📊 إحصائيات التصدير", callback_data="export_stats")]
        ])
        
        export_text = (
            f"**📤 تصدير الروابط**\n\n"
            f"**إجمالي الروابط:** {stats.get('total_links', 0):,}\n"
            f"**الروابط الجديدة:** {stats.get('new_links', 0):,}\n\n"
            f"**اختر نوع التصدير:**"
        )
        
        await update.message.reply_text(export_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def export_new_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /export_new"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await AdvancedDatabaseManager.get_instance()
        new_count = await db.get_new_links_count()
        
        if new_count == 0:
            await update.message.reply_text("📭 لا توجد روابط جديدة")
            return
        
        await update.message.reply_text(f"⏳ جاري تحضير {new_count} رابط جديد...")
        
        try:
            # الحصول على الروابط الجديدة
            cursor = await db.conn.execute('''
                SELECT url, platform, category 
                FROM links 
                WHERE is_new = 1 
                ORDER BY collected_date DESC
                LIMIT ?
            ''', (Config.MAX_EXPORT_LINKS,))
            
            rows = await cursor.fetchall()
            
            # تنظيم الروابط حسب الفئة
            links_by_category = defaultdict(list)
            for url, platform, category in rows:
                links_by_category[f"{platform}_{category}"].append(url)
            
            # تصدير كل قسم في ملف منفصل
            exported_files = []
            
            for category_key, links in links_by_category.items():
                if not links:
                    continue
                
                filename = f"new_{category_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
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
                        caption=f"🆕 {category_key} - {len(links)} رابط جديد"
                    )
                
                exported_files.append(filepath)
            
            # تحديث حالة الروابط
            await db.mark_all_links_as_processed()
            
            # حذف الملفات المحلية
            for filepath in exported_files:
                try:
                    os.remove(filepath)
                except:
                    pass
            
            await update.message.reply_text(f"✅ تم تصدير {len(rows)} رابط جديد")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الروابط الجديدة: {e}")
            await update.message.reply_text(f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def export_category_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /export_category"""
        if not context.args:
            await update.message.reply_text(
                "📁 **استخدام:** /export_category <اسم_القسم>\n\n"
                "**الأقسام المتاحة:**\n"
                "• bot - روابط البوتات\n"
                "• subscription - مجموعات المشتركين\n"
                "• join_request - مجموعات طلب الانظمام\n"
                "• public_group - مجموعات الأعضاء\n"
                "• message - روابط الرسائل\n"
                "• whatsapp - مجموعات واتساب"
            )
            return
        
        category = context.args[0].lower()
        valid_categories = ['bot', 'subscription', 'join_request', 'public_group', 'message', 'whatsapp']
        
        if category not in valid_categories:
            await update.message.reply_text("❌ قسم غير صالح")
            return
        
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        await update.message.reply_text(f"⏳ جاري تحضير روابط {category}...")
        
        try:
            db = await AdvancedDatabaseManager.get_instance()
            
            if category == 'whatsapp':
                links = await db.get_links_by_category('whatsapp', 'whatsapp', Config.MAX_EXPORT_LINKS)
            else:
                links = await db.get_links_by_category(category, 'telegram', Config.MAX_EXPORT_LINKS)
            
            if not links:
                await update.message.reply_text(f"❌ لا توجد روابط في قسم {category}")
                return
            
            # حفظ في ملف
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
                    caption=f"📁 {category} - {len(links)} رابط"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await update.message.reply_text(f"✅ تم تصدير {len(links)} رابط من قسم {category}")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير القسم {category}: {e}")
            await update.message.reply_text(f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def check_new_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /check_new"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        has_new = await self.collection_manager.check_for_new_links(user.id)
        
        if has_new:
            await update.message.reply_text("🔔 تم إرسال إشعار بالروابط الجديدة")
        else:
            await update.message.reply_text("📭 لا توجد روابط جديدة")
    
    async def mark_read_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /mark_read"""
        if not context.args:
            await update.message.reply_text("📝 **استخدام:** /mark_read <رقم_الإشعار>")
            return
        
        try:
            notification_id = int(context.args[0])
            
            user = update.effective_user
            
            # التحقق من الوصول
            if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
                if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                    await update.message.reply_text("❌ غير مصرح لك بالوصول")
                    return
            
            db = await AdvancedDatabaseManager.get_instance()
            success = await db.mark_notification_as_read(notification_id)
            
            if success:
                await update.message.reply_text("✅ تم تحديد الإشعار كمقروء")
            else:
                await update.message.reply_text("❌ فشل في تحديث الإشعار")
                
        except ValueError:
            await update.message.reply_text("❌ رقم إشعار غير صالح")
    
    async def clear_new_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /clear_new"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await AdvancedDatabaseManager.get_instance()
        success = await db.mark_all_links_as_processed()
        
        if success:
            await update.message.reply_text("✅ تم مسح جميع الروابط الجديدة")
        else:
            await update.message.reply_text("❌ فشل في مسح الروابط")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة استدعاءات الأزرار"""
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
            if data == "start_collection":
                await self._handle_start_collection(query)
            elif data == "pause_collection":
                await self._handle_pause_collection(query)
            elif data == "resume_collection":
                await self._handle_resume_collection(query)
            elif data == "stop_collection":
                await self._handle_stop_collection(query)
            elif data == "collection_status":
                await self._handle_collection_status(query)
            elif data == "show_stats":
                await self._handle_show_stats(query)
            elif data == "show_categories":
                await self._handle_show_categories(query)
            elif data == "show_sessions":
                await self._handle_show_sessions(query)
            elif data == "show_notifications":
                await self._handle_show_notifications(query)
            elif data == "add_session":
                await self._handle_add_session(query)
            elif data == "export_menu":
                await self._handle_export_menu(query)
            elif data == "export_all_categories":
                await self._handle_export_all_categories(query)
            elif data.startswith("export_category_"):
                await self._handle_export_category(query, data)
            elif data == "export_new_links":
                await self._handle_export_new_links(query)
            elif data == "export_stats":
                await self._handle_export_stats(query)
            elif data == "check_new_links":
                await self._handle_check_new_links(query)
            elif data.startswith("mark_read_"):
                await self._handle_mark_read(query, data)
            elif data == "clear_notifications":
                await self._handle_clear_notifications(query)
            elif data.startswith("refresh_"):
                await self._handle_refresh(query, data)
            else:
                await self._edit_message_safe(query, "❌ أمر غير معروف")
        
        except Exception as e:
            logger.error(f"خطأ في معالجة الاستدعاء: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _edit_message_safe(self, query, text, reply_markup=None, parse_mode="Markdown"):
        """تعديل الرسالة بأمان"""
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                logger.error(f"خطأ في تعديل الرسالة: {e}")
        except Exception as e:
            logger.error(f"خطأ غير متوقع في تعديل الرسالة: {e}")
    
    async def _handle_start_collection(self, query):
        """معالجة بدء التجميع"""
        if self.collection_manager.active:
            await self._edit_message_safe(query, "⚠️ التجميع يعمل بالفعل")
            return
        
        await self._edit_message_safe(query, "🚀 بدأ التجميع الشامل...")
        
        await self.collection_manager.start_collection(query.from_user.id)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collection"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collection")],
            [InlineKeyboardButton("📊 الحالة", callback_data="collection_status"),
             InlineKeyboardButton("🔄 تحديث", callback_data="refresh_status")]
        ])
        
        await self._edit_message_safe(
            query,
            "✅ **بدأ التجميع الشامل بنجاح!**\n\n"
            "**جاري:**\n"
            "• جمع روابط تليجرام من 5 سنوات\n"
            "• جمع روابط واتساب من 60 يوماً\n"
            "• تقسيم إلى أقسام\n"
            "• منع التكرار\n\n"
            "سيتم إعلامك عند اكتمال التجميع.",
            reply_markup=keyboard
        )
    
    async def _handle_pause_collection(self, query):
        """معالجة إيقاف التجميع مؤقتاً"""
        if not self.collection_manager.active:
            await self._edit_message_safe(query, "⚠️ التجميع غير نشط")
            return
        
        await self.collection_manager.pause()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ استئناف", callback_data="resume_collection"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collection")],
            [InlineKeyboardButton("📊 الحالة", callback_data="collection_status")]
        ])
        
        await self._edit_message_safe(
            query,
            "⏸️ **تم إيقاف التجميع مؤقتاً**\n\n"
            "يمكنك استئناف التجميع في أي وقت.",
            reply_markup=keyboard
        )
    
    async def _handle_resume_collection(self, query):
        """معالجة استئناف التجميع"""
        if not self.collection_manager.active:
            await self._edit_message_safe(query, "⚠️ التجميع غير نشط")
            return
        
        if not self.collection_manager.paused:
            await self._edit_message_safe(query, "⚠️ التجميع ليس متوقفاً مؤقتاً")
            return
        
        await self.collection_manager.resume()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collection"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collection")],
            [InlineKeyboardButton("📊 الحالة", callback_data="collection_status")]
        ])
        
        await self._edit_message_safe(
            query,
            "▶️ **تم استئناف التجميع**\n\n"
            "جاري متابعة جمع الروابط...",
            reply_markup=keyboard
        )
    
    async def _handle_stop_collection(self, query):
        """معالجة إيقاف التجميع"""
        if not self.collection_manager.active:
            await self._edit_message_safe(query, "⚠️ التجميع غير نشط")
            return
        
        await self.collection_manager.stop()
        
        status = self.collection_manager.get_status()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء جديد", callback_data="start_collection"),
             InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")]
        ])
        
        await self._edit_message_safe(
            query,
            f"⏹️ **تم إيقاف التجميع**\n\n"
            f"**الإحصائيات النهائية:**\n"
            f"• إجمالي المجموع: {status['stats']['total_collected']:,}\n"
            f"• تليجرام: {status['stats']['telegram_collected']:,}\n"
            f"• واتساب: {status['stats']['whatsapp_collected']:,}\n"
            f"• المجموعات: {status['stats']['groups_processed']:,}\n"
            f"• الرسائل: {status['stats']['messages_scanned']:,}",
            reply_markup=keyboard
        )
    
    async def _handle_collection_status(self, query):
        """معالجة عرض حالة التجميع"""
        status = self.collection_manager.get_status()
        
        status_text = (
            f"**📊 حالة التجميع**\n\n"
            f"**الحالة:** {status['stats']['status']}\n"
            f"**نشط:** {'✅ نعم' if status['active'] else '❌ لا'}\n"
            f"**مؤقت:** {'✅ نعم' if status['paused'] else '❌ لا'}\n\n"
            f"**الإحصائيات:**\n"
            f"• إجمالي المجموع: {status['stats']['total_collected']:,}\n"
            f"• تليجرام: {status['stats']['telegram_collected']:,}\n"
            f"• واتساب: {status['stats']['whatsapp_collected']:,}\n"
            f"• المجموعات: {status['stats']['groups_processed']:,}\n"
            f"• الرسائل: {status['stats']['messages_scanned']:,}\n"
            f"• الجلسات: {status['stats']['sessions_used']}\n"
            f"• الأخطاء: {status['stats']['errors']:,}\n\n"
        )
        
        if status['stats']['categories']:
            status_text += "**التوزيع:**\n"
            for category, count in status['stats']['categories'].items():
                status_text += f"• {category}: {count:,}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="collection_status"),
             InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collection")],
            [InlineKeyboardButton("▶️ استئناف", callback_data="resume_collection"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collection")]
        ])
        
        await self._edit_message_safe(query, status_text, reply_markup=keyboard)
    
    async def _handle_show_stats(self, query):
        """معالجة عرض الإحصائيات"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.stats_command(mock_update, None)
    
    async def _handle_show_categories(self, query):
        """معالجة عرض الأقسام"""
        try:
            db = await AdvancedDatabaseManager.get_instance()
            category_stats = await db.get_category_stats()
            
            categories_text = "**📁 الأقسام المتاحة**\n\n"
            
            for category_key, details in category_stats.items():
                last_updated = details['last_updated'][:19] if details['last_updated'] else "غير معروف"
                categories_text += (
                    f"**{details['description']}**\n"
                    f"• المفتاح: {category_key}\n"
                    f"• العدد: {details['actual_count']:,}\n"
                    f"• آخر تحديث: {last_updated}\n\n"
                )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 تصدير الكل", callback_data="export_all_categories"),
                 InlineKeyboardButton("🔄 تحديث", callback_data="refresh_categories")],
                [InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats"),
                 InlineKeyboardButton("🏠 الرئيسية", callback_data="go_home")]
            ])
            
            await self._edit_message_safe(query, categories_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"خطأ في عرض الأقسام: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_show_sessions(self, query):
        """معالجة عرض الجلسات"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.sessions_command(mock_update, None)
    
    async def _handle_show_notifications(self, query):
        """معالجة عرض الإشعارات"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.notifications_command(mock_update, None)
    
    async def _handle_add_session(self, query):
        """معالجة إضافة جلسة"""
        from_user = query.from_user
        self.user_states[from_user.id] = {'waiting_for_session': True}
        
        await self._edit_message_safe(
            query,
            "**➕ إضافة جلسة جديدة**\n\n"
            "**أرسل كود الجلسة الآن:**\n\n"
            "**ملاحظة:**\n"
            "• الجلسة ستستخدم للتجميع فقط\n"
            "• تخزن مشفرة\n"
            "• يجب أن تكون نشطة"
        )
    
    async def _handle_export_menu(self, query):
        """معالجة عرض قائمة التصدير"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.export_command(mock_update, None)
    
    async def _handle_export_all_categories(self, query):
        """معالجة تصدير جميع الأقسام"""
        await self._edit_message_safe(query, "⏳ جاري تحضير جميع الأقسام...")
        
        try:
            db = await AdvancedDatabaseManager.get_instance()
            category_stats = await db.get_category_stats()
            
            exported_files = []
            
            for category_key, details in category_stats.items():
                if details['actual_count'] == 0:
                    continue
                
                # تحديد الفئة والمنصة
                if category_key == 'whatsapp_groups':
                    platform, category = 'whatsapp', 'whatsapp'
                else:
                    platform = 'telegram'
                    category_map = {
                        'telegram_bots': 'bot',
                        'telegram_subscriptions': 'subscription',
                        'telegram_join_requests': 'join_request',
                        'telegram_public_groups': 'public_group',
                        'telegram_messages': 'message'
                    }
                    category = category_map.get(category_key, '')
                
                if not category:
                    continue
                
                # الحصول على الروابط
                if platform == 'whatsapp':
                    links = await db.get_links_by_category('whatsapp', 'whatsapp', Config.MAX_EXPORT_LINKS)
                else:
                    links = await db.get_links_by_category(category, 'telegram', Config.MAX_EXPORT_LINKS)
                
                if not links:
                    continue
                
                # حفظ في ملف
                filename = f"{category_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
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
                        caption=f"📁 {details['description']} - {len(links)} رابط"
                    )
                
                exported_files.append(filepath)
                
                # تأخير بين الملفات
                await asyncio.sleep(1)
            
            # حذف الملفات المحلية
            for filepath in exported_files:
                try:
                    os.remove(filepath)
                except:
                    pass
            
            if exported_files:
                await self._edit_message_safe(query, "✅ تم تصدير جميع الأقسام")
            else:
                await self._edit_message_safe(query, "❌ لا توجد روابط للتصدير")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير جميع الأقسام: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_export_category(self, query, data):
        """معالجة تصدير قسم محدد"""
        category = data.replace('export_category_', '')
        
        await self._edit_message_safe(query, f"⏳ جاري تحضير قسم {category}...")
        
        try:
            db = await AdvancedDatabaseManager.get_instance()
            
            if category == 'whatsapp':
                links = await db.get_links_by_category('whatsapp', 'whatsapp', Config.MAX_EXPORT_LINKS)
            else:
                links = await db.get_links_by_category(category, 'telegram', Config.MAX_EXPORT_LINKS)
            
            if not links:
                await self._edit_message_safe(query, f"❌ لا توجد روابط في قسم {category}")
                return
            
            # حفظ في ملف
            filename = f"{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
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
                    caption=f"📁 {category} - {len(links)} رابط"
                )
            
            # حذف الملف المحلي
            try:
                os.remove(filepath)
            except:
                pass
            
            await self._edit_message_safe(query, f"✅ تم تصدير {len(links)} رابط من قسم {category}")
            
        except Exception as e:
            logger.error(f"خطأ في تصدير القسم {category}: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_export_new_links(self, query):
        """معالجة تصدير الروابط الجديدة"""
        from_user = query.from_user
        
        class MockUpdate:
            def __init__(self, query):
                self.effective_user = query.from_user
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.export_new_command(mock_update, None)
    
    async def _handle_export_stats(self, query):
        """معالجة إحصائيات التصدير"""
        try:
            db = await AdvancedDatabaseManager.get_instance()
            stats = await db.get_total_stats()
            category_stats = await db.get_category_stats()
            
            stats_text = (
                f"**📊 إحصائيات التصدير**\n\n"
                f"**إجمالي الروابط:** {stats.get('total_links', 0):,}\n"
                f"**الروابط الجديدة:** {stats.get('new_links', 0):,}\n\n"
                f"**تفاصيل الأقسام:**\n"
            )
            
            for category_key, details in category_stats.items():
                stats_text += f"• {details['description']}: {details['actual_count']:,}\n"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 تصدير الكل", callback_data="export_all_categories"),
                 InlineKeyboardButton("🆕 تصدير الجديد", callback_data="export_new_links")],
                [InlineKeyboardButton("🔄 تحديث", callback_data="export_stats")]
            ])
            
            await self._edit_message_safe(query, stats_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"خطأ في عرض إحصائيات التصدير: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_check_new_links(self, query):
        """معالجة فحص الروابط الجديدة"""
        user = query.from_user
        
        has_new = await self.collection_manager.check_for_new_links(user.id)
        
        if has_new:
            await self._edit_message_safe(query, "🔔 تم إرسال إشعار بالروابط الجديدة")
        else:
            await self._edit_message_safe(query, "📭 لا توجد روابط جديدة")
    
    async def _handle_mark_read(self, query, data):
        """معالجة تحديد الإشعار كمقروء"""
        try:
            notification_id = int(data.replace('mark_read_', ''))
            
            user = query.from_user
            db = await AdvancedDatabaseManager.get_instance()
            success = await db.mark_notification_as_read(notification_id)
            
            if success:
                await self._edit_message_safe(query, "✅ تم تحديد الإشعار كمقروء")
            else:
                await self._edit_message_safe(query, "❌ فشل في تحديث الإشعار")
                
        except Exception as e:
            logger.error(f"خطأ في تحديد الإشعار كمقروء: {e}")
            await self._edit_message_safe(query, "❌ رقم إشعار غير صالح")
    
    async def _handle_clear_notifications(self, query):
        """معالجة مسح الإشعارات"""
        user = query.from_user
        
        # هذه تحتاج إلى تنفيذ في قاعدة البيانات
        await self._edit_message_safe(query, "⏳ جاري تطوير هذه الميزة...")
    
    async def _handle_refresh(self, query, data):
        """معالجة تحديث الصفحة"""
        refresh_type = data.replace('refresh_', '')
        
        if refresh_type == 'status':
            await self._handle_collection_status(query)
        elif refresh_type == 'stats':
            await self._handle_show_stats(query)
        elif refresh_type == 'categories':
            await self._handle_show_categories(query)
        elif refresh_type == 'sessions':
            await self._handle_show_sessions(query)
        elif refresh_type == 'notifications':
            await self._handle_show_notifications(query)
        else:
            await self._edit_message_safe(query, "🔄 تم التحديث")
    
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
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="go_home"),
                 InlineKeyboardButton("🚀 بدء التجميع", callback_data="start_collection")],
                [InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats"),
                 InlineKeyboardButton("📤 التصدير", callback_data="export_menu")]
            ])
            
            await update.message.reply_text(
                "مرحباً! يمكنك استخدام الأوامر أو الأزرار للتحكم.\n\n"
                "**الأوامر الأساسية:**\n"
                "/start - القائمة الرئيسية\n"
                "/collect_all - بدء التجميع الشامل\n"
                "/export_new - تصدير الروابط الجديدة\n"
                "/status - حالة النظام\n"
                "/notifications - الإشعارات",
                reply_markup=keyboard
            )
    
    async def _handle_session_input(self, update: Update, session_string: str):
        """معالجة إدخال الجلسة"""
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
        
        # حفظ الجلسة
        session_data = {
            'session_string': encrypted_session,
            'phone_number': user_info.get('phone', ''),
            'user_id': user_info.get('id', 0),
            'username': user_info.get('username', ''),
            'display_name': f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip(),
            'added_by_user': user.id,
            'metadata': {
                'validated_at': datetime.now().isoformat(),
                'purpose': 'advanced_link_collection'
            }
        }
        
        db = await AdvancedDatabaseManager.get_instance()
        success, message, details = await db.add_session(session_data)
        
        if success:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء التجميع", callback_data="start_collection"),
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
                f"• جاهزة للتجميع\n"
                f"• رقم الجلسة: {details.get('session_id')}\n\n"
                f"**ملاحظة:**\n"
                f"هذه الجلسة ستستخدم لجمع:\n"
                f"• جميع روابط تليجرام النشطة\n"
                f"• روابط واتساب من آخر 60 يوماً\n"
                f"• تقسيم تلقائي إلى أقسام",
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
                logger.error("⚠️ تم اكتشاف نسخة أخرى تعمل!")
                
                await asyncio.sleep(2)
                
                try:
                    await context.application.stop()
                    await context.application.initialize()
                    await context.application.start()
                    logger.info("✅ تم إعادة التشغيل بعد حل التعارض")
                except Exception as restart_error:
                    logger.error(f"فشل إعادة التشغيل: {restart_error}")
                
                return
            
            if update and update.effective_chat:
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ حدث خطأ غير متوقع. حاول مرة أخرى.",
                    )
                except Exception:
                    pass
                
        except Exception as e:
            logger.error(f"خطأ في معالج الأخطاء: {e}")

# ======================
# الوظيفة الرئيسية
# ======================

async def main():
    """الوظيفة الرئيسية"""
    try:
        logger.info("🚀 تشغيل بوت التجميع المتقدم...")
        
        # التحقق من المتغيرات البيئية
        required_env_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH']
        missing = [var for var in required_env_vars if not os.getenv(var)]
        
        if missing:
            logger.error(f"❌ متغيرات مفقودة: {missing}")
            print(f"❌ خطأ: المتغيرات التالية مفقودة: {', '.join(missing)}")
            sys.exit(1)
        
        # التحقق من نسخة واحدة فقط
        instance_manager = await SingleInstanceManager.get_instance()
        if not await instance_manager.acquire_lock():
            logger.error("❌ تم اكتشاف نسخة أخرى تعمل!")
            print("❌ خطأ: هناك نسخة أخرى تعمل. إغلاق...")
            sys.exit(1)
        
        # إنشاء المجلدات
        os.makedirs("backups", exist_ok=True)
        os.makedirs("exports", exist_ok=True)
        
        # تهيئة قاعدة البيانات
        db = await AdvancedDatabaseManager.get_instance()
        
        # إنشاء البوت
        bot = AdvancedTelegramBot()
        
        logger.info("🤖 بدء تشغيل بوت التجميع المتقدم...")
        logger.info(f"🔥 إعدادات تليجرام: جمع من {Config.TELEGRAM_YEARS_BACK} سنوات")
        logger.info(f"📱 إعدادات واتساب: جمع من {Config.WHATSAPP_DAYS_BACK} يوم")
        logger.info(f"📁 الأقسام: {len(Config.TELEGRAM_COLLECTION_TYPES)} نوع")
        logger.info(f"🔄 منع التكرار: {'نعم' if Config.REMOVE_DUPLICATES else 'لا'}")
        
        try:
            # تشغيل البوت
            await bot.app.initialize()
            await bot.app.start()
            await bot.app.updater.start_polling()
            
            logger.info("✅ البوت يعمل بنجاح!")
            logger.info("📋 جاهز للتجميع والتصدير...")
            
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
                
                # تحرير القفل
                await instance_manager.release_lock()
                
                logger.info("✅ اكتمل الإغلاق السلس")
                
            except Exception as e:
                logger.error(f"❌ خطأ في التنظيف: {e}")
    
    except Exception as e:
        logger.error(f"❌ خطأ قاتل: {e}", exc_info=True)
        sys.exit(1)

# ======================
# معالجات الإشارات
# ======================

def setup_signal_handlers():
    """إعداد معالجات الإشارات"""
    def signal_handler(signum, frame):
        logger.info(f"📶 تم استقبال إشارة {signum}. جاري الإغلاق...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# ======================
# نقطة الدخول
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
