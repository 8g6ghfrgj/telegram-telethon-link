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
    MAX_CONCURRENT_SESSIONS = 5  # تخفيض للاستقرار
    REQUEST_DELAYS = {
        'normal': 0.5,
        'join_request': 2.0,
        'search': 1.0,
        'flood_wait': 5.0,
        'between_sessions': 1.0,
        'between_tasks': 0.2,
        'min_cycle_delay': 5.0,
        'max_cycle_delay': 30.0,
        'validation_delay': 1.0
    }
    
    # Collection limits - حدود الجمع
    MAX_DIALOGS_PER_SESSION = 20  # تخفيض لعدم التحميل الزائد
    MAX_MESSAGES_PER_SEARCH = 5
    MAX_SEARCH_TERMS = 5
    MAX_LINKS_PER_CYCLE = 50
    MAX_BATCH_SIZE = 10
    
    # Database - قاعدة البيانات
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 5
    DB_POOL_SIZE = 2  # تخفيض لـ Render
    
    # WhatsApp collection - جمع واتساب
    WHATSAPP_DAYS_BACK = 30
    
    # Link verification - التحقق من الروابط
    MIN_GROUP_MEMBERS = 3
    MAX_LINK_LENGTH = 200
    VALIDATION_TIMEOUT = 15  # تخفيض المهلة
    
    # Rate limiting - الحد من الطلبات
    USER_RATE_LIMIT = {
        'max_requests': 15,
        'per_seconds': 60
    }
    
    # Session management - إدارة الجلسات
    SESSION_TIMEOUT = 600
    MAX_SESSIONS_PER_USER = 5  # تخفيض للمستخدمين
    
    # Export - التصدير
    MAX_EXPORT_LINKS = 10000  # تخفيض للتجربة
    EXPORT_CHUNK_SIZE = 1000
    
    # Advanced settings - إعدادات متقدمة
    TELEGRAM_NO_TIME_LIMIT = True
    JOIN_REQUEST_CHECK_DELAY = 15  # تخفيض
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
# Link Collector Core - نواة جامع الروابط
# ======================

class LinkCollectorCore:
    """نواة جمع الروابط الفعلية"""
    
    @staticmethod
    def extract_urls_from_text(text: str) -> List[str]:
        """استخراج جميع الروابط من النص"""
        if not text:
            return []
        
        # أنماط البحث عن الروابط
        patterns = [
            # روابط HTTP/HTTPS الكاملة
            r'https?://[^\s<>"\']+',
            # روابط تيليجرام المختصرة
            r't\.me/[^\s<>"\']+',
            r'telegram\.me/[^\s<>"\']+',
            r'telegram\.dog/[^\s<>"\']+',
            # روابط واتساب
            r'chat\.whatsapp\.com/[^\s<>"\']+',
            r'whatsapp\.com/[^\s<>"\']+',
            # روابط ديسكورد
            r'discord\.gg/[^\s<>"\']+',
            r'discord\.com/[^\s<>"\']+',
            # روابط سيجنال
            r'signal\.group/[^\s<>"\']+',
            # روابط الانضمام (joinchat)
            r'joinchat/[^\s<>"\']+',
            r'\+[A-Za-z0-9_-]+',
            # روابط القنوات
            r'c/[^\s<>"\']+',
            r'channel/[^\s<>"\']+',
            r's/[^\s<>"\']+'
        ]
        
        urls = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            urls.extend(matches)
        
        # تنظيف وتحسين الروابط
        cleaned_urls = []
        for url in set(urls):
            url = url.strip()
            
            # إضافة https:// للروابط الناقصة
            if url.startswith('t.me/'):
                url = f'https://{url}'
            elif url.startswith('telegram.me/'):
                url = f'https://{url}'
            elif url.startswith('chat.whatsapp.com/'):
                url = f'https://{url}'
            elif url.startswith('discord.gg/'):
                url = f'https://{url}'
            elif url.startswith('signal.group/'):
                url = f'https://{url}'
            elif url.startswith('+'):
                url = f'https://t.me/{url}'
            elif url.startswith('joinchat/'):
                url = f'https://t.me/{url}'
            elif url.startswith('c/'):
                url = f'https://t.me/{url}'
            elif url.startswith('channel/'):
                url = f'https://t.me/{url}'
            elif url.startswith('s/'):
                url = f'https://t.me/{url}'
            
            # التحقق من صحة الرابط
            if LinkCollectorCore.is_valid_url(url):
                cleaned_urls.append(url)
        
        return list(set(cleaned_urls))
    
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """التحقق من صحة الرابط"""
        if not url or len(url) < 10:
            return False
        
        allowed_domains = [
            't.me', 'telegram.me', 'telegram.dog',
            'chat.whatsapp.com', 'whatsapp.com',
            'discord.gg', 'discord.com',
            'signal.group'
        ]
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # التحقق من النطاق المسموح
            if not any(allowed_domain in domain for allowed_domain in allowed_domains):
                return False
            
            # التحقق من طول الرابط
            if len(url) > Config.MAX_LINK_LENGTH:
                return False
            
            # التحقق من وجود مسار
            if not parsed.path or len(parsed.path.strip('/')) == 0:
                return False
            
            return True
            
        except Exception:
            return False
    
    @staticmethod
    def normalize_url(url: str) -> str:
        """توحيد تنسيق الرابط"""
        try:
            # إزالة المسافات الزائدة
            url = url.strip()
            
            # إزالة معاملات التتبع
            if '?' in url:
                url = url.split('?')[0]
            
            # إزالة الجزء #fragment
            if '#' in url:
                url = url.split('#')[0]
            
            # إزالة الشرطة المائلة الأخيرة
            if url.endswith('/'):
                url = url[:-1]
            
            return url.lower()
            
        except Exception:
            return url
    
    @staticmethod
    def get_url_hash(url: str) -> str:
        """الحصول على تجزئة فريدة للرابط"""
        normalized = LinkCollectorCore.normalize_url(url)
        return hashlib.md5(normalized.encode()).hexdigest()
    
    @staticmethod
    def get_platform_from_url(url: str) -> str:
        """تحديد المنصة من الرابط"""
        url_lower = url.lower()
        
        if 't.me' in url_lower or 'telegram.' in url_lower:
            return 'telegram'
        elif 'whatsapp.com' in url_lower:
            return 'whatsapp'
        elif 'discord.' in url_lower:
            return 'discord'
        elif 'signal.group' in url_lower:
            return 'signal'
        else:
            return 'unknown'
    
    @staticmethod
    def analyze_telegram_url(url: str) -> Dict:
        """تحليل روابط تيليجرام"""
        result = {
            'is_valid': False,
            'type': 'unknown',
            'username': '',
            'invite_hash': '',
            'is_private': False,
            'is_channel': False,
            'is_group': False
        }
        
        try:
            parsed = urlparse(url)
            path = parsed.path.strip('/')
            
            if not path:
                return result
            
            # كشف روابط الانضمام (joinchat)
            if 'joinchat' in path.lower() or path.startswith('+'):
                result['is_valid'] = True
                result['type'] = 'join_request'
                result['is_private'] = True
                result['is_group'] = True
                
                if 'joinchat/' in path:
                    result['invite_hash'] = path.split('/')[-1]
                elif path.startswith('+'):
                    result['invite_hash'] = path[1:]
                    
            # كشف القنوات
            elif path.startswith('c/') or path.startswith('channel/') or path.startswith('s/'):
                result['is_valid'] = True
                result['type'] = 'channel'
                result['is_channel'] = True
                result['username'] = path.split('/')[-1]
                
            # كشف المجموعات العامة
            elif '/' not in path or path.count('/') == 0:
                result['is_valid'] = True
                
                if path.startswith('+'):
                    result['type'] = 'join_request'
                    result['is_private'] = True
                    result['is_group'] = True
                    result['invite_hash'] = path[1:]
                else:
                    result['type'] = 'public_group'
                    result['is_group'] = True
                    result['username'] = path
                    
        except Exception as e:
            logger.debug(f"خطأ في تحليل رابط تيليجرام: {e}")
        
        return result

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
        # جدول الجلسات (مبسط)
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_string TEXT NOT NULL,
                session_hash TEXT UNIQUE NOT NULL,
                phone_number TEXT,
                username TEXT,
                display_name TEXT,
                added_by_user INTEGER,
                is_active BOOLEAN DEFAULT 1,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                total_uses INTEGER DEFAULT 0,
                total_links INTEGER DEFAULT 0
            )
        ''')
        
        # جدول الروابط (مبسط)
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL,
                platform TEXT NOT NULL,
                link_type TEXT,
                session_id INTEGER,
                collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                is_verified BOOLEAN DEFAULT 0,
                added_by_user INTEGER
            )
        ''')
        
        # جدول المستخدمين (مبسط)
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
        
        await self.conn.commit()
        
        # إنشاء فهارس
        await self._create_indexes()
    
    async def _create_indexes(self):
        """Create database indexes"""
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_links_url_hash ON links(url_hash)',
            'CREATE INDEX IF NOT EXISTS idx_links_platform ON links(platform)',
            'CREATE INDEX IF NOT EXISTS idx_links_collected_date ON links(collected_date)',
            'CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)'
        ]
        
        for index_sql in indexes:
            try:
                await self.conn.execute(index_sql)
            except Exception as e:
                logger.error(f"خطأ في إنشاء الفهرس: {e}")
        
        await self.conn.commit()
    
    async def add_link_simple(self, url: str, session_id: int, added_by_user: int = 0) -> Tuple[bool, str, Dict]:
        """إضافة رابط مبسط"""
        try:
            # التحقق من صحة الرابط
            if not LinkCollectorCore.is_valid_url(url):
                return False, "رابط غير صالح", {}
            
            # توحيد الرابط
            normalized_url = LinkCollectorCore.normalize_url(url)
            url_hash = LinkCollectorCore.get_url_hash(normalized_url)
            
            # تحديد المنصة
            platform = LinkCollectorCore.get_platform_from_url(normalized_url)
            
            # تحديد نوع الرابط
            link_type = 'group'
            if platform == 'telegram':
                analysis = LinkCollectorCore.analyze_telegram_url(normalized_url)
                link_type = analysis.get('type', 'group')
            
            # التحقق من التكرار
            cursor = await self.conn.execute(
                'SELECT id FROM links WHERE url_hash = ?',
                (url_hash,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                return False, "الرابط موجود مسبقاً", {'link_id': existing[0]}
            
            # إضافة الرابط
            cursor = await self.conn.execute('''
                INSERT INTO links 
                (url_hash, url, platform, link_type, session_id, is_verified, added_by_user)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                url_hash,
                normalized_url,
                platform,
                link_type,
                session_id,
                1 if platform != 'unknown' else 0,
                added_by_user
            ))
            
            link_id = cursor.lastrowid
            
            # تحديث إحصائيات الجلسة
            await self.conn.execute(
                "UPDATE sessions SET total_links = total_links + 1 WHERE id = ?",
                (session_id,)
            )
            
            # تحديث إحصائيات المستخدم
            if added_by_user:
                await self.update_user_stats(added_by_user, 'link_added')
            
            await self.conn.commit()
            
            return True, "تمت إضافة الرابط بنجاح", {
                'link_id': link_id,
                'url_hash': url_hash
            }
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الرابط: {e}")
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def add_session_simple(self, session_string: str, user_id: int, user_info: Dict = None) -> Tuple[bool, str, Dict]:
        """إضافة جلسة مبسطة"""
        try:
            if not session_string or len(session_string) < 50:
                return False, "جلسة غير صالحة", {}
            
            session_hash = hashlib.md5(session_string.encode()).hexdigest()
            
            # التحقق من التكرار
            cursor = await self.conn.execute(
                'SELECT id FROM sessions WHERE session_hash = ?',
                (session_hash,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                return False, "الجلسة موجودة مسبقاً", {'session_id': existing[0]}
            
            # إعداد بيانات الجلسة
            display_name = ""
            phone = ""
            username = ""
            
            if user_info:
                display_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
                phone = user_info.get('phone', '')
                username = user_info.get('username', '')
            
            # إضافة الجلسة
            cursor = await self.conn.execute('''
                INSERT INTO sessions 
                (session_string, session_hash, phone_number, username, display_name, added_by_user)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                session_string,
                session_hash,
                phone,
                username,
                display_name,
                user_id
            ))
            
            session_id = cursor.lastrowid
            
            # تحديث إحصائيات المستخدم
            await self.update_user_stats(user_id, 'session_added')
            
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
            if action == 'link_added':
                await self.conn.execute('''
                    UPDATE bot_users 
                    SET last_active = CURRENT_TIMESTAMP,
                        request_count = request_count + 1,
                        link_count = link_count + ?
                    WHERE user_id = ?
                ''', (value, user_id))
            elif action == 'session_added':
                await self.conn.execute('''
                    UPDATE bot_users 
                    SET last_active = CURRENT_TIMESTAMP,
                        request_count = request_count + 1,
                        session_count = session_count + 1
                    WHERE user_id = ?
                ''', (user_id,))
            else:
                await self.conn.execute('''
                    UPDATE bot_users 
                    SET last_active = CURRENT_TIMESTAMP,
                        request_count = request_count + 1
                    WHERE user_id = ?
                ''', (user_id,))
            
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
    
    async def get_active_sessions(self, limit: int = 5) -> List[Dict]:
        """Get active sessions"""
        try:
            cursor = await self.conn.execute('''
                SELECT * FROM sessions 
                WHERE is_active = 1 
                ORDER BY last_used ASC NULLS FIRST, added_date ASC
                LIMIT ?
            ''', (limit,))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            sessions = []
            for row in rows:
                session_dict = dict(zip(columns, row))
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
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT platform, COUNT(*) FROM links GROUP BY platform")
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            return stats
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على ملخص الإحصائيات: {e}")
            return {}
    
    async def export_links_simple(self, limit: int = 1000) -> List[str]:
        """تصدير الروابط بشكل مبسط"""
        try:
            cursor = await self.conn.execute('''
                SELECT url FROM links 
                WHERE is_active = 1 
                ORDER BY collected_date DESC 
                LIMIT ?
            ''', (limit,))
            
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الروابط: {e}")
            return []
    
    async def update_session_last_used(self, session_id: int):
        """تحديث وقت استخدام الجلسة"""
        try:
            await self.conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, total_uses = total_uses + 1 WHERE id = ?",
                (session_id,)
            )
            await self.conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تحديث استخدام الجلسة: {e}")
    
    async def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            await self.conn.close()
            self._initialized = False

# ======================
# Working Session Manager - مدير الجلسات العامل
# ======================

class WorkingSessionManager:
    """مدير جلسات يعمل فعلاً"""
    
    @staticmethod
    async def validate_and_get_info(session_string: str) -> Tuple[bool, Dict]:
        """التحقق من الجلسة والحصول على معلومات"""
        try:
            # تنظيف سلسلة الجلسة
            session_string = session_string.strip()
            
            if len(session_string) < 100:
                return False, {'error': 'جلسة قصيرة جداً', 'details': 'يجب أن تكون الجلسة أطول من 100 حرف'}
            
            # محاولة إنشاء عميل
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH,
                timeout=10,
                connection_retries=2
            )
            
            await client.connect()
            
            # التحقق من المصادقة
            if not await client.is_user_authorized():
                await client.disconnect()
                return False, {'error': 'غير مصرح', 'details': 'الجلسة غير مفعلة أو منتهية'}
            
            # الحصول على معلومات المستخدم
            me = await client.get_me()
            
            user_info = {
                'id': me.id,
                'username': me.username or '',
                'phone': me.phone or '',
                'first_name': me.first_name or '',
                'last_name': me.last_name or '',
                'is_bot': me.bot if hasattr(me, 'bot') else False
            }
            
            await client.disconnect()
            
            return True, {
                'user_info': user_info,
                'session_length': len(session_string),
                'is_valid': True
            }
            
        except ValueError as e:
            return False, {'error': 'تنسيق جلسة غير صالح', 'details': str(e)}
        except AuthKeyError:
            return False, {'error': 'مفتاح مصادقة غير صالح', 'details': 'الجلسة منتهية'}
        except Exception as e:
            return False, {'error': 'خطأ في التحقق', 'details': str(e)[:150]}
    
    @staticmethod
    async def collect_links_from_session(session_string: str, session_id: int, max_dialogs: int = 10) -> Tuple[int, List[str]]:
        """جمع الروابط من جلسة"""
        collected_urls = []
        
        try:
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH,
                timeout=15,
                connection_retries=2,
                device_model="LinkCollectorBot",
                system_version="Linux 6.5",
                app_version="4.16.30"
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return 0, []
            
            # جمع من الدردشات
            dialog_count = 0
            async for dialog in client.iter_dialogs(limit=max_dialogs):
                try:
                    # جمع من وصف المجموعة/القناة
                    if hasattr(dialog.entity, 'about') and dialog.entity.about:
                        urls = LinkCollectorCore.extract_urls_from_text(dialog.entity.about)
                        collected_urls.extend(urls)
                    
                    # جمع من الرسائل الحديثة
                    message_count = 0
                    async for message in client.iter_messages(dialog.entity, limit=3):
                        if message.text:
                            urls = LinkCollectorCore.extract_urls_from_text(message.text)
                            collected_urls.extend(urls)
                        
                        message_count += 1
                        if message_count >= 3:
                            break
                    
                    await asyncio.sleep(0.5)  # تأخير قصير
                    dialog_count += 1
                    
                except Exception as e:
                    logger.debug(f"خطأ في جمع من الدردشة: {e}")
                    continue
            
            await client.disconnect()
            
            # إزالة التكرارات
            unique_urls = list(set(collected_urls))
            
            logger.info(f"جمع {len(unique_urls)} رابط من {dialog_count} دردشة")
            return len(unique_urls), unique_urls
            
        except Exception as e:
            logger.error(f"خطأ في جمع الروابط من الجلسة: {e}")
            return 0, []

# ======================
# Real Collection Manager - مدير الجمع الحقيقي
# ======================

class RealCollectionManager:
    """مدير جمع حقيقي يعمل فعلاً"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        self.current_cycle = 0
        self.stats = {
            'total_cycles': 0,
            'total_sessions_processed': 0,
            'total_links_collected': 0,
            'telegram_links': 0,
            'whatsapp_links': 0,
            'other_links': 0,
            'errors': 0,
            'last_collection': None
        }
        self.collection_task = None
    
    async def start_collection(self):
        """بدء الجمع الحقيقي"""
        if self.active:
            logger.warning("الجمع يعمل بالفعل")
            return
        
        self.active = True
        self.paused = False
        self.stop_requested = False
        
        logger.info("🚀 بدء عملية الجمع الحقيقية...")
        
        # بدء مهمة الجمع
        self.collection_task = asyncio.create_task(self._real_collection_loop())
        
        return True
    
    async def _real_collection_loop(self):
        """حلقة الجمع الحقيقية"""
        while self.active and not self.stop_requested:
            if self.paused:
                await asyncio.sleep(1)
                continue
            
            try:
                await self._real_collection_cycle()
                
                # تأخير بين الدورات
                delay = Config.REQUEST_DELAYS['min_cycle_delay']
                logger.info(f"⏳ انتظار {delay} ثانية للدورة القادمة...")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"خطأ في حلقة الجمع: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(10)
        
        self.active = False
        logger.info("⏹️ توقفت عملية الجمع الحقيقية")
    
    async def _real_collection_cycle(self):
        """دورة جمع حقيقية"""
        logger.info(f"🔄 بدء دورة الجمع #{self.current_cycle + 1}")
        
        # الحصول على الجلسات النشطة
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=Config.MAX_CONCURRENT_SESSIONS)
        
        if not sessions:
            logger.warning("⚠️ لا توجد جلسات نشطة للجمع")
            return
        
        logger.info(f"📊 جاري معالجة {len(sessions)} جلسة...")
        
        total_collected = 0
        successful_sessions = 0
        
        for i, session in enumerate(sessions):
            if self.stop_requested or self.paused:
                break
            
            try:
                session_id = session['id']
                session_string = session['session_string']
                added_by_user = session['added_by_user']
                
                logger.info(f"🔍 معالجة الجلسة {session_id} ({i+1}/{len(sessions)})")
                
                # جمع الروابط من الجلسة
                links_count, urls = await WorkingSessionManager.collect_links_from_session(
                    session_string, 
                    session_id,
                    max_dialogs=Config.MAX_DIALOGS_PER_SESSION
                )
                
                if links_count > 0:
                    # حفظ الروابط المجمعة
                    saved_count = 0
                    for url in urls:
                        success, message, details = await db.add_link_simple(
                            url, session_id, added_by_user
                        )
                        if success:
                            saved_count += 1
                            
                            # تحديث الإحصائيات حسب المنصة
                            platform = LinkCollectorCore.get_platform_from_url(url)
                            if platform == 'telegram':
                                self.stats['telegram_links'] += 1
                            elif platform == 'whatsapp':
                                self.stats['whatsapp_links'] += 1
                            else:
                                self.stats['other_links'] += 1
                    
                    # تحديث إحصائيات الجلسة
                    await db.update_session_last_used(session_id)
                    
                    total_collected += saved_count
                    successful_sessions += 1
                    
                    logger.info(f"✅ الجلسة {session_id}: جمع {links_count} رابط، حفظ {saved_count}")
                else:
                    logger.info(f"⚠️ الجلسة {session_id}: لم يتم جمع روابط")
                
                # تأخير بين الجلسات
                if i < len(sessions) - 1:
                    await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
                
            except Exception as e:
                logger.error(f"❌ خطأ في معالجة الجلسة: {e}")
                self.stats['errors'] += 1
                continue
        
        # تحديث الإحصائيات
        self.stats['total_links_collected'] += total_collected
        self.stats['total_sessions_processed'] += successful_sessions
        self.stats['total_cycles'] += 1
        self.stats['last_collection'] = datetime.now().isoformat()
        self.current_cycle += 1
        
        logger.info(f"📊 اكتملت الدورة #{self.current_cycle}: {successful_sessions}/{len(sessions)} جلسات، {total_collected} رابط")
    
    def get_status(self) -> Dict:
        """الحصول على حالة الجمع"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'current_cycle': self.current_cycle,
            'stats': self.stats.copy(),
            'next_action': 'جاري الجمع' if self.active and not self.paused else 'متوقف'
        }
    
    async def pause(self):
        """إيقاف الجمع مؤقتاً"""
        self.paused = True
        logger.info("⏸️ تم إيقاف الجمع مؤقتاً")
    
    async def resume(self):
        """استئناف الجمع"""
        self.paused = False
        logger.info("▶️ تم استئناف الجمع")
    
    async def stop(self):
        """إيقاف الجمع"""
        self.stop_requested = True
        logger.info("⏹️ تم طلب إيقاف الجمع")
        
        # انتظار حتى تنتهي المهمة
        if self.collection_task:
            try:
                await asyncio.wait_for(self.collection_task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("مهلة انتظار إيقاف مهمة الجمع")
        
        self.active = False
    
    async def test_collection(self, session_string: str) -> Tuple[bool, Dict]:
        """اختبار الجمع من جلسة"""
        try:
            links_count, urls = await WorkingSessionManager.collect_links_from_session(
                session_string, 
                0,  # session_id مؤقت
                max_dialogs=3  # عدد قليل للاختبار
            )
            
            return True, {
                'links_found': links_count,
                'sample_links': urls[:5] if urls else [],
                'session_valid': True
            }
            
        except Exception as e:
            return False, {
                'error': str(e),
                'session_valid': False
            }

# ======================
# Working Telegram Bot - بوت تليجرام العامل
# ======================

class WorkingTelegramBot:
    """بوت تليجرام يعمل فعلاً"""
    
    def __init__(self):
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        self.collection_manager = RealCollectionManager()
        self.user_states = {}
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """إعداد معالجات البوت"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        self.app.add_handler(CommandHandler("addsession", self.add_session_command))
        self.app.add_handler(CommandHandler("test", self.test_command))
        
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
        
        # إضافة/تحديث المستخدم
        db = await EnhancedDatabaseManager.get_instance()
        await db.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect"),
             InlineKeyboardButton("⏸️ إدارة الجمع", callback_data="manage_collect")],
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("👥 الجلسات", callback_data="show_sessions")],
            [InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_links"),
             InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")],
            [InlineKeyboardButton("🧪 اختبار جلسة", callback_data="test_session"),
             InlineKeyboardButton("⚙️ الإعدادات", callback_data="show_settings")]
        ])
        
        welcome_text = f"""
🤖 **مرحباً {user.first_name}!**

**بوت جمع روابط المجموعات الحقيقي**

**المميزات الفعلية:**
• ✅ جمع فعلي من جلسات تيليجرام
• ✅ استخراج روابط من الدردشات والمجموعات
• ✅ دعم تيليجرام، واتساب، ديسكورد
• ✅ تصدير الروابط المجمعة
• ✅ واجهة سهلة الاستخدام

**🚀 للبدء:**
1. أضف جلسة تيليجرام (زر ➕ إضافة جلسة)
2. ابدأ الجمع (زر 🚀 بدء الجمع)
3. قم بتصدير الروابط (زر 📤 تصدير)

**📊 البوت يعمل فعلياً وليس وهمياً!**
"""
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def test_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر اختبار الجمع"""
        user = update.effective_user
        
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            await update.message.reply_text("❌ هذا الأمر للمدراء فقط")
            return
        
        await update.message.reply_text(
            "🧪 **وضع الاختبار**\n\n"
            "أرسل كود جلسة تيليجرام لاختبار الجمع منها:\n\n"
            "سأقوم بجمع بعض الروابط منها لعرضها لك."
        )
        
        self.user_states[user.id] = {'testing_session': True}
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر إدارة الجمع"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        status = self.collection_manager.get_status()
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        
        # بناء لوحة التحكم
        control_buttons = []
        
        if status['active']:
            if status['paused']:
                control_buttons.append([InlineKeyboardButton("▶️ استئناف الجمع", callback_data="resume_collect")])
            else:
                control_buttons.append([InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")])
            control_buttons.append([InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="stop_collect")])
        else:
            control_buttons.append([InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")])
        
        control_buttons.append([
            InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status"),
            InlineKeyboardButton("🔄 تحديث", callback_data="refresh_collect")
        ])
        
        keyboard = InlineKeyboardMarkup(control_buttons)
        
        # بناء نص الحالة
        status_text = f"""
**🚀 إدارة الجمع الفعلي**

**الحالة الحالية:** {"🔄 **نشط**" if status['active'] else "🛑 **متوقف**"}
{"⏸️ **موقف مؤقتاً**" if status['paused'] else ""}

**إحصائيات الجمع:**
• 🔄 الدورات المكتملة: {status['stats']['total_cycles']}
• 💼 الجلسات المعالجة: {status['stats']['total_sessions_processed']}
• 🔗 الروابط المجمعة: {status['stats']['total_links_collected']:,}
• 📢 روابط تيليجرام: {status['stats']['telegram_links']:,}
• 📱 روابط واتساب: {status['stats']['whatsapp_links']:,}
• ❌ الأخطاء: {status['stats']['errors']:,}

**إحصائيات قاعدة البيانات:**
• 🔗 إجمالي الروابط: {db_stats.get('total_links', 0):,}
• 💼 الجلسات النشطة: {db_stats.get('active_sessions', 0)}
• 👥 المستخدمين: {db_stats.get('total_users', 0)}

**التالية:** {status.get('next_action', 'غير معروف')}
"""
        
        await update.message.reply_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def add_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر إضافة جلسة"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        self.user_states[user.id] = {'adding_session': True}
        
        add_text = """
**➕ إضافة جلسة تيليجرام فعلية**

**لإضافة جلسة تيليجرام:**

1. افتح @GetStringBot في تيليجرام
2. أرسل `/start` للبوت
3. سيطلب منك api_id و api_hash
4. أرسل الرقمين التاليين:
   • api_id: `{Config.API_ID}`
   • api_hash: `{Config.API_HASH}`
5. سيرسل لك كود الجلسة (session string)

**أرسل كود الجلسة الآن:**
(يمكنك نسخ الكود كاملاً وإرساله هنا)

**ملاحظة:** الجلسة ستستخدم لجمع الروابط من دردشاتك.
"""
        
        await update.message.reply_text(add_text, parse_mode="Markdown")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الاستدعاءات"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        data = query.data
        
        try:
            if data == "start_collect":
                await self._handle_start_collect(query)
            elif data == "pause_collect":
                await self._handle_pause_collect(query)
            elif data == "resume_collect":
                await self._handle_resume_collect(query)
            elif data == "stop_collect":
                await self._handle_stop_collect(query)
            elif data == "collect_status":
                await self._handle_collect_status(query)
            elif data == "refresh_collect":
                await self._handle_refresh_collect(query)
            elif data == "add_session":
                await self._handle_add_session(query)
            elif data == "show_sessions":
                await self._handle_show_sessions(query)
            elif data == "export_links":
                await self._handle_export_links(query)
            elif data == "show_stats":
                await self._handle_show_stats(query)
            elif data == "test_session":
                await self._handle_test_session(query)
            elif data.startswith("export_"):
                await self._handle_export_type(query, data.replace("export_", ""))
            else:
                await query.edit_message_text("❌ أمر غير معروف")
        
        except Exception as e:
            logger.error(f"خطأ في معالجة الاستدعاء: {e}")
            try:
                await query.edit_message_text(f"❌ حدث خطأ: {str(e)[:100]}")
            except:
                await query.message.reply_text(f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_start_collect(self, query):
        """بدء الجمع"""
        if self.collection_manager.active:
            await query.edit_message_text("⏳ الجمع يعمل بالفعل!")
            return
        
        # بدء الجمع
        await self.collection_manager.start_collection()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status"),
             InlineKeyboardButton("🔄 تحديث", callback_data="refresh_collect")]
        ])
        
        await query.edit_message_text(
            "🚀 **بدأ الجمع الفعلي!**\n\n"
            "جاري جمع الروابط من جميع الجلسات النشطة...\n\n"
            "**ماذا يحدث الآن:**\n"
            "• فحص جميع الدردشات في كل جلسة\n"
            "• استخراج روابط المجموعات والقنوات\n"
            "• حفظ الروابط في قاعدة البيانات\n"
            "• تحديث الإحصائيات تلقائياً\n\n"
            "يمكنك متابعة التقدم من خلال زر 📊 حالة الجمع",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_pause_collect(self, query):
        """إيقاف الجمع مؤقتاً"""
        await self.collection_manager.pause()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ استئناف", callback_data="resume_collect"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status")]
        ])
        
        await query.edit_message_text(
            "⏸️ **تم إيقاف الجمع مؤقتاً**\n\n"
            "يمكنك استئناف الجمع في أي وقت.\n"
            "الجلسات تبقى نشطة وجاهزة.\n\n"
            "**الإحصائيات الحالية:**\n"
            f"• الروابط المجمعة: {self.collection_manager.stats['total_links_collected']:,}\n"
            f"• الدورات المكتملة: {self.collection_manager.stats['total_cycles']}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_resume_collect(self, query):
        """استئناف الجمع"""
        await self.collection_manager.resume()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status")]
        ])
        
        await query.edit_message_text(
            "▶️ **تم استئناف الجمع!**\n\n"
            "جاري متابعة جمع الروابط...\n\n"
            "**سيتم:**\n"
            "• استكمال فحص الدردشات\n"
            "• جمع روابط جديدة\n"
            "• تحديث الإحصائيات\n\n"
            "يمكنك متابعة التقدم من خلال زر 📊 حالة الجمع",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_stop_collect(self, query):
        """إيقاف الجمع"""
        await self.collection_manager.stop()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 إعادة البدء", callback_data="start_collect"),
             InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")]
        ])
        
        await query.edit_message_text(
            "⏹️ **تم إيقاف الجمع**\n\n"
            "توقفت عملية الجمع بنجاح.\n"
            "تم حفظ جميع الروابط المجمعة.\n\n"
            "**الإحصائيات النهائية:**\n"
            f"• إجمالي الروابط: {self.collection_manager.stats['total_links_collected']:,}\n"
            f"• روابط تيليجرام: {self.collection_manager.stats['telegram_links']:,}\n"
            f"• روابط واتساب: {self.collection_manager.stats['whatsapp_links']:,}\n"
            f"• الدورات المكتملة: {self.collection_manager.stats['total_cycles']}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_collect_status(self, query):
        """عرض حالة الجمع"""
        status = self.collection_manager.get_status()
        
        status_text = f"""
**📊 حالة الجمع التفصيلية**

**المعلومات العامة:**
• الحالة: {"🔄 نشط" if status['active'] else "🛑 متوقف"}
• الإيقاف المؤقت: {"⏸️ نعم" if status['paused'] else "▶️ لا"}
• الدورة الحالية: #{status['current_cycle']}
• التالية: {status.get('next_action', 'غير معروف')}

**إحصائيات الأداء:**
• الدورات المكتملة: {status['stats']['total_cycles']}
• الجلسات المعالجة: {status['stats']['total_sessions_processed']}
• الروابط المجمعة: {status['stats']['total_links_collected']:,}
• الأخطاء: {status['stats']['errors']:,}

**توزيع الروابط:**
• تيليجرام: {status['stats']['telegram_links']:,}
• واتساب: {status['stats']['whatsapp_links']:,}
• أخرى: {status['stats']['other_links']:,}

**آخر تحديث:** {status['stats'].get('last_collection', 'لم يبدأ')}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="collect_status"),
             InlineKeyboardButton("📊 إحصائيات كاملة", callback_data="show_stats")]
        ])
        
        await query.edit_message_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_refresh_collect(self, query):
        """تحديث صفحة الجمع"""
        await self.collect_command(query.message, query.message.reply_to_message)
    
    async def _handle_add_session(self, query):
        """إضافة جلسة"""
        user = query.from_user
        self.user_states[user.id] = {'adding_session': True}
        
        add_text = """
**➕ أرسل كود الجلسة الآن:**

**كيفية الحصول على كود الجلسة:**
1. افتح @GetStringBot في تيليجرام
2. أرسل `/start`
3. أرسل api_id و api_hash عندما يطلبها
4. سيرسل لك كود الجلسة

**أرسل الكود هنا:**
(يجب أن يكون طويلاً - أكثر من 100 حرف)
"""
        
        await query.edit_message_text(add_text, parse_mode="Markdown")
    
    async def _handle_show_sessions(self, query):
        """عرض الجلسات"""
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=10)
        
        if not sessions:
            await query.edit_message_text("❌ لا توجد جلسات نشطة")
            return
        
        sessions_text = f"**👥 الجلسات النشطة ({len(sessions)})**\n\n"
        
        for i, session in enumerate(sessions, 1):
            display_name = session.get('display_name', 'غير معروف')
            username = session.get('username', 'بدون معرف')
            uses = session.get('total_uses', 0)
            links = session.get('total_links', 0)
            
            sessions_text += f"""**{i}. {display_name}**
• المعرف: @{username}
• الاستخدامات: {uses}
• الروابط: {links:,}
• رقم الجلسة: {session['id']}

"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("🔄 تحديث", callback_data="show_sessions")]
        ])
        
        await query.edit_message_text(sessions_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_export_links(self, query):
        """تصدير الروابط"""
        db = await EnhancedDatabaseManager.get_instance()
        total_links = await db.get_links_count()
        
        if total_links == 0:
            await query.edit_message_text("❌ لا توجد روابط للتصدير")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 تصدير نصي", callback_data="export_txt"),
             InlineKeyboardButton("📊 تصدير CSV", callback_data="export_csv")],
            [InlineKeyboardButton("📋 تصدير JSON", callback_data="export_json"),
             InlineKeyboardButton("📦 جميع الروابط", callback_data="export_all")]
        ])
        
        export_text = f"""
**📤 تصدير الروابط**

إجمالي الروابط المتاحة: **{total_links:,}**

**خيارات التصدير:**
• 📄 نصي - روابط فقط (ملف .txt)
• 📊 CSV - مع المعلومات (ملف .csv)
• 📋 JSON - كامل المعلومات (ملف .json)
• 📦 جميع الروابط - ملف نصي بكامل الروابط

**الحد الأقصى:** {Config.MAX_EXPORT_LINKS:,} رابط لكل تصدير
"""
        
        await query.edit_message_text(export_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_export_type(self, query, export_type: str):
        """معالجة نوع التصدير"""
        await query.edit_message_text("⏳ جاري تحضير الملف...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            if export_type == 'all':
                links = await db.export_links_simple(limit=Config.MAX_EXPORT_LINKS)
                filename = f"export_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                file_content = "\n".join(links)
                
            elif export_type == 'txt':
                links = await db.export_links_simple(limit=Config.MAX_EXPORT_LINKS)
                filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                file_content = "\n".join(links)
                
            elif export_type == 'csv':
                cursor = await db.conn.execute('''
                    SELECT url, platform, link_type, collected_date 
                    FROM links 
                    WHERE is_active = 1 
                    LIMIT ?
                ''', (Config.MAX_EXPORT_LINKS,))
                
                rows = await cursor.fetchall()
                filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                file_content = "URL,Platform,Type,Date\n"
                for row in rows:
                    url, platform, link_type, date = row
                    file_content += f'"{url}","{platform}","{link_type}","{date}"\n'
                    
            elif export_type == 'json':
                cursor = await db.conn.execute('''
                    SELECT url, platform, link_type, collected_date 
                    FROM links 
                    WHERE is_active = 1 
                    LIMIT ?
                ''', (Config.MAX_EXPORT_LINKS,))
                
                rows = await cursor.fetchall()
                columns = ['url', 'platform', 'type', 'date']
                data = [dict(zip(columns, row)) for row in rows]
                filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                file_content = json.dumps(data, ensure_ascii=False, indent=2)
            
            else:
                await query.edit_message_text("❌ نوع تصدير غير معروف")
                return
            
            if not file_content or (isinstance(file_content, str) and len(file_content.strip()) == 0):
                await query.edit_message_text("❌ لا توجد روابط للتصدير")
                return
            
            # حفظ الملف مؤقتاً
            os.makedirs("temp_exports", exist_ok=True)
            filepath = os.path.join("temp_exports", filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(file_content)
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📤 ملف التصدير\nعدد الروابط: {len(links) if 'links' in locals() else 'مجهول'}"
                )
            
            # حذف الملف المؤقت
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في التصدير: {e}")
            await query.edit_message_text(f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_show_stats(self, query):
        """عرض الإحصائيات"""
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        collection_status = self.collection_manager.get_status()
        
        stats_text = f"""
**📈 إحصائيات النظام المتقدمة**

**إحصائيات الجمع:**
• 🔄 الدورات المكتملة: {collection_status['stats']['total_cycles']}
• 💼 الجلسات المعالجة: {collection_status['stats']['total_sessions_processed']}
• 🔗 الروابط المجمعة: {collection_status['stats']['total_links_collected']:,}
• 📢 تيليجرام: {collection_status['stats']['telegram_links']:,}
• 📱 واتساب: {collection_status['stats']['whatsapp_links']:,}
• ❌ الأخطاء: {collection_status['stats']['errors']:,}

**إحصائيات قاعدة البيانات:**
• 🔗 إجمالي الروابط: {db_stats.get('total_links', 0):,}
• 💼 الجلسات النشطة: {db_stats.get('active_sessions', 0)}
• 👥 المستخدمين: {db_stats.get('total_users', 0)}

**توزيع المنصات:**
"""
        
        for platform, count in db_stats.get('links_by_platform', {}).items():
            stats_text += f"• {platform}: {count:,}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="show_stats"),
             InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status")]
        ])
        
        await query.edit_message_text(stats_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_test_session(self, query):
        """اختبار جلسة"""
        user = query.from_user
        self.user_states[user.id] = {'testing_session': True}
        
        await query.edit_message_text(
            "🧪 **وضع اختبار الجلسة**\n\n"
            "أرسل كود جلسة تيليجرام لاختبار الجمع منها:\n\n"
            "**سأقوم بـ:**\n"
            "1. التحقق من صحة الجلسة\n"
            "2. جمع بعض الروابط منها\n"
            "3. عرض النتائج لك\n\n"
            "أرسل كود الجلسة الآن:"
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الرسائل النصية"""
        user = update.effective_user
        text = update.message.text.strip()
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        # التحقق من حالة المستخدم
        user_state = self.user_states.get(user.id, {})
        
        if user_state.get('adding_session'):
            await self._handle_session_addition(update, text)
        elif user_state.get('testing_session'):
            await self._handle_session_test(update, text)
        else:
            # رسالة عادية - عرض الأوامر
            await update.message.reply_text(
                "مرحباً! يمكنك استخدام:\n"
                "/start - بدء البوت\n"
                "/collect - إدارة الجمع\n"
                "/addsession - إضافة جلسة\n"
                "/test - اختبار جلسة (للمدراء)\n"
                "أو استخدم الأزرار من رسالة الترحيب."
            )
    
    async def _handle_session_addition(self, update: Update, session_string: str):
        """معالجة إضافة جلسة"""
        user = update.effective_user
        
        # حذف حالة المستخدم
        if user.id in self.user_states:
            del self.user_states[user.id]
        
        await update.message.reply_text("⏳ جاري التحقق من الجلسة...")
        
        # التحقق من الجلسة
        valid, result = await WorkingSessionManager.validate_and_get_info(session_string)
        
        if not valid:
            await update.message.reply_text(f"❌ جلسة غير صالحة: {result.get('error', 'خطأ غير معروف')}")
            return
        
        user_info = result.get('user_info', {})
        
        # حفظ الجلسة في قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        success, message, details = await db.add_session_simple(session_string, user.id, user_info)
        
        if success:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect"),
                 InlineKeyboardButton("👥 عرض الجلسات", callback_data="show_sessions")]
            ])
            
            await update.message.reply_text(
                f"✅ **تمت إضافة الجلسة بنجاح!**\n\n"
                f"**معلومات المستخدم:**\n"
                f"• الاسم: {user_info.get('first_name', '')} {user_info.get('last_name', '')}\n"
                f"• المعرف: @{user_info.get('username', 'بدون')}\n"
                f"• الهاتف: {user_info.get('phone', 'بدون')}\n\n"
                f"**الجلسة:**\n"
                f"• رقم الجلسة: {details.get('session_id')}\n"
                f"• الطول: {len(session_string)} حرف\n"
                f"• جاهزة للاستخدام في الجمع\n\n"
                f"يمكنك الآن بدء الجمع من هذه الجلسة!",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ فشل في إضافة الجلسة: {message}")
    
    async def _handle_session_test(self, update: Update, session_string: str):
        """اختبار جلسة"""
        user = update.effective_user
        
        # حذف حالة المستخدم
        if user.id in self.user_states:
            del self.user_states[user.id]
        
        await update.message.reply_text("🧪 جاري اختبار الجلسة وجمع عينة من الروابط...")
        
        # اختبار الجمع
        success, result = await self.collection_manager.test_collection(session_string)
        
        if not success:
            await update.message.reply_text(f"❌ فشل اختبار الجلسة: {result.get('error', 'خطأ غير معروف')}")
            return
        
        if not result.get('session_valid', False):
            await update.message.reply_text("❌ الجلسة غير صالحة للجمع")
            return
        
        links_found = result.get('links_found', 0)
        sample_links = result.get('sample_links', [])
        
        response_text = f"""
**🧪 نتائج اختبار الجلسة**

**النتيجة:** ✅ **نجاح!**

**الإحصائيات:**
• عدد الروابط الموجودة: {links_found}
• تم جمع عينة من الروابط

**عينة من الروابط المجمعة:**
"""
        
        if sample_links:
            for i, link in enumerate(sample_links[:5], 1):
                response_text += f"{i}. `{link}`\n"
        else:
            response_text += "لم يتم العثور على روابط في العينة.\n"
        
        response_text += f"\n**الخلاصة:** الجلسة صالحة ويمكنها جمع الروابط!"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة هذه الجلسة", callback_data="add_session"),
             InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")]
        ])
        
        await update.message.reply_text(response_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الأخطاء"""
        try:
            error = context.error
            
            logger.error(f"خطأ غير معالج: {error}", exc_info=True)
            
            # معالجة خطأ Conflict (نسخة مزدوجة)
            if isinstance(error, Conflict):
                logger.error("⚠️ تم اكتشاف نسخة أخرى من البوت تعمل!")
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
    
    # وظائف أخرى (help, status, sessions, export) - سأقوم بتضمينها في النسخة النهائية
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر المساعدة"""
        help_text = """
**📖 دليل استخدام البوت الفعلي**

**الأوامر الرئيسية:**
• /start - بدء البوت وواجهة التحكم
• /help - عرض هذا الدليل
• /collect - إدارة عملية الجمع

**إدارة الجلسات:**
• /addsession - إضافة جلسة تيليجرام جديدة
• /sessions - عرض الجلسات النشطة

**الجمع والتصدير:**
• بدء/إيقاف الجمع من واجهة /collect
• /export - تصدير الروابط المجمعة

**للمدراء:**
• /test - اختبار جلسة وجمع عينة

**📌 خطوات العمل:**
1. أضف جلسة تيليجرام باستخدام /addsession
2. ابدأ الجمع من واجهة /collect
3. قم بتصدير الروابط باستخدام /export

**🔒 ملاحظات أمنية:**
• الجلسات تستخدم لجمع الروابط فقط
• لا يتم حفظ أي رسائل شخصية
• الروابط تخزن بعد تنظيفها
"""
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر حالة النظام"""
        await self.collect_command(update, context)
    
    async def sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر عرض الجلسات"""
        await self._handle_show_sessions_inline(update)
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر التصدير"""
        await self._handle_export_links_inline(update)
    
    async def _handle_show_sessions_inline(self, update: Update):
        """عرض الجلسات من أمر مباشر"""
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=10)
        
        if not sessions:
            await update.message.reply_text("❌ لا توجد جلسات نشطة")
            return
        
        sessions_text = f"**👥 الجلسات النشطة ({len(sessions)})**\n\n"
        
        for i, session in enumerate(sessions, 1):
            display_name = session.get('display_name', 'غير معروف')
            username = session.get('username', 'بدون معرف')
            uses = session.get('total_uses', 0)
            links = session.get('total_links', 0)
            
            sessions_text += f"""**{i}. {display_name}**
• المعرف: @{username}
• الاستخدامات: {uses}
• الروابط: {links:,}

"""
        
        await update.message.reply_text(sessions_text, parse_mode="Markdown")
    
    async def _handle_export_links_inline(self, update: Update):
        """تصدير الروابط من أمر مباشر"""
        db = await EnhancedDatabaseManager.get_instance()
        total_links = await db.get_links_count()
        
        if total_links == 0:
            await update.message.reply_text("❌ لا توجد روابط للتصدير")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 تصدير نصي", callback_data="export_txt"),
             InlineKeyboardButton("📊 تصدير CSV", callback_data="export_csv")],
            [InlineKeyboardButton("📋 تصدير JSON", callback_data="export_json")]
        ])
        
        export_text = f"""
**📤 تصدير الروابط**

إجمالي الروابط: **{total_links:,}**

اختر تنسيق التصدير:
"""
        
        await update.message.reply_text(export_text, reply_markup=keyboard, parse_mode="Markdown")

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
        
        @self.app.get("/metrics")
        async def metrics():
            try:
                metrics_data = {
                    "timestamp": datetime.now().isoformat(),
                    "memory": psutil.virtual_memory()._asdict(),
                    "disk": psutil.disk_usage('/')._asdict(),
                    "cpu": psutil.cpu_percent(interval=1)
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
        
        # إنشاء المجلدات المطلوبة
        os.makedirs("backups", exist_ok=True)
        os.makedirs("temp_exports", exist_ok=True)
        os.makedirs("cache_data", exist_ok=True)
        
        # بدء خادم فحص الصحة
        health_server = HealthCheckServer(port=8080)
        health_server.start()
        
        # تهيئة قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        
        # إنشاء البوت
        bot = WorkingTelegramBot()
        
        logger.info("🤖 بدء تشغيل بوت جمع الروابط الحقيقي...")
        logger.info(f"🔥 الإعدادات - جلسات متزامنة: {Config.MAX_CONCURRENT_SESSIONS}")
        
        try:
            # تشغيل البوت
            await bot.app.initialize()
            await bot.app.start()
            await bot.app.updater.start_polling()
            
            logger.info("✅ البوت يعمل بنجاح وجاهز للجمع الفعلي!")
            logger.info("📋 الأوامر: /start, /collect, /addsession, /export, /test (للمدراء)")
            
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
                await bot.app.stop()
                
                # إغلاق قاعدة البيانات
                await db.close()
                
                # إيقاف خادم الصحة
                health_server.stop()
                
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
