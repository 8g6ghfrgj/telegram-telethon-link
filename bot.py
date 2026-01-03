import asyncio
import logging
import os
import sys
import re
import json
import aiofiles
import aiosqlite
import gc
import shutil
import hashlib
import psutil
import signal
from typing import List, Dict, Set, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import OrderedDict, defaultdict, deque
from urllib.parse import urlparse, parse_qs, urlencode
import aiohttp
from contextlib import asynccontextmanager

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl import functions, types
from telethon.errors import (
    FloodWaitError, ChannelPrivateError, UsernameNotOccupiedError,
    InviteHashInvalidError, InviteHashExpiredError, ChatAdminRequiredError,
    SessionPasswordNeededError, PhoneCodeInvalidError, AuthKeyError
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
    ADMIN_USER_IDS = set(map(int, os.getenv("ADMIN_USER_IDS", "0").split(",")))
    ALLOWED_USER_IDS = set(map(int, os.getenv("ALLOWED_USER_IDS", "0").split(",")))
    
    # Memory management - إدارة الذاكرة
    MAX_CACHED_URLS = 20000
    CACHE_CLEAN_INTERVAL = 1000
    MAX_MEMORY_MB = 500  # الحد الأقصى للذاكرة بالميجابايت
    
    # Performance settings - إعدادات الأداء
    MAX_CONCURRENT_SESSIONS = 3
    REQUEST_DELAYS = {
        'normal': 1.0,
        'join_request': 30.0,  # خفضنا من 60 إلى 30
        'search': 2.0,        # خفضنا من 3 إلى 2
        'flood_wait': 5.0,
        'between_sessions': 3.0,  # تأخير جديد بين الجلسات
        'between_tasks': 0.5      # تأخير جديد بين المهام
    }
    
    # Collection limits - حدود الجمع
    MAX_DIALOGS_PER_SESSION = 40
    MAX_MESSAGES_PER_SEARCH = 8
    MAX_SEARCH_TERMS = 5
    MAX_LINKS_PER_CYCLE = 100
    
    # Database - قاعدة البيانات
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 5
    
    # WhatsApp collection - جمع واتساب
    WHATSAPP_DAYS_BACK = 15
    
    # Link verification - التحقق من الروابط
    MIN_GROUP_MEMBERS = 5
    MAX_LINK_LENGTH = 200
    
    # Rate limiting - الحد من الطلبات
    USER_RATE_LIMIT = {
        'max_requests': 10,
        'per_seconds': 60
    }
    
    # Session management - إدارة الجلسات
    SESSION_TIMEOUT = 300  # 5 دقائق قبل إغلاق الجلسة غير المستخدمة
    MAX_SESSIONS_PER_USER = 5

# ======================
# Advanced Logging - التسجيل المتقدم
# ======================

class ColorFormatter(logging.Formatter):
    """Colored logging formatter - منسق تسجيل ملون"""
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan - سماوي
        'INFO': '\033[32m',      # Green - أخضر
        'WARNING': '\033[33m',   # Yellow - أصفر
        'ERROR': '\033[31m',     # Red - أحمر
        'CRITICAL': '\033[35m',  # Magenta - بنفسجي
        'RESET': '\033[0m'
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# تطبيق الألوان على الـ StreamHandler فقط
for handler in logging.getLogger().handlers:
    if isinstance(handler, logging.StreamHandler):
        handler.setFormatter(ColorFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logger = logging.getLogger(__name__)

# ======================
# Memory Manager - مدير الذاكرة
# ======================

class MemoryManager:
    """Advanced memory management system - نظام متقدم لإدارة الذاكرة"""
    
    @staticmethod
    def get_memory_usage() -> float:
        """Get current memory usage in MB - الحصول على استخدام الذاكرة بالميجابايت"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except:
            return 0
    
    @staticmethod
    def optimize_memory() -> float:
        """Optimize memory usage - تحسين استخدام الذاكرة"""
        before = MemoryManager.get_memory_usage()
        
        # جمع المهملات
        gc.collect()
        
        # إغلاق الملفات المفتوحة
        import io
        open_files = psutil.Process().open_files()
        if len(open_files) > 50:
            logger.warning(f"Many open files: {len(open_files)}")
        
        after = MemoryManager.get_memory_usage()
        saved = before - after
        
        if saved > 10:  # إذا وفرنا أكثر من 10 ميجابايت
            logger.info(f"تم تحسين الذاكرة: وفرنا {saved:.2f} MB")
        
        return saved
    
    @staticmethod
    def check_and_optimize(threshold_mb: float = Config.MAX_MEMORY_MB) -> bool:
        """Check memory and optimize if needed - التحقق من الذاكرة والتحسين إذا لزم"""
        current = MemoryManager.get_memory_usage()
        
        if current > threshold_mb:
            logger.warning(f"استخدام عالي للذاكرة: {current:.2f} MB > {threshold_mb} MB")
            saved = MemoryManager.optimize_memory()
            return True
        
        return False

# ======================
# Rate Limiter - الحد من الطلبات
# ======================

class RateLimiter:
    """Rate limiting system - نظام الحد من الطلبات"""
    
    def __init__(self):
        self.requests = defaultdict(deque)
        self.locks = defaultdict(asyncio.Lock)
    
    async def check_limit(self, user_id: int, 
                         max_requests: int = Config.USER_RATE_LIMIT['max_requests'],
                         per_seconds: int = Config.USER_RATE_LIMIT['per_seconds']) -> bool:
        """Check if user is rate limited - التحقق إذا كان المستخدم يتجاوز الحد"""
        async with self.locks[user_id]:
            now = datetime.now()
            user_requests = self.requests[user_id]
            
            # إزالة الطلبات القديمة
            while user_requests and (now - user_requests[0]).total_seconds() > per_seconds:
                user_requests.popleft()
            
            if len(user_requests) >= max_requests:
                return False
            
            user_requests.append(now)
            return True
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Get rate limit stats for user - الحصول على إحصائيات الحد للمستخدم"""
        now = datetime.now()
        user_requests = self.requests.get(user_id, deque())
        
        # عد الطلبات في آخر دقيقة
        recent_requests = sum(1 for req_time in user_requests 
                             if (now - req_time).total_seconds() <= 60)
        
        return {
            'recent_requests': recent_requests,
            'total_requests': len(user_requests),
            'max_allowed': Config.USER_RATE_LIMIT['max_requests']
        }

# ======================
# Backup Manager - مدير النسخ الاحتياطي
# ======================

class BackupManager:
    """Database backup system - نظام النسخ الاحتياطي لقاعدة البيانات"""
    
    @staticmethod
    async def create_backup() -> Optional[str]:
        """Create database backup - إنشاء نسخة احتياطية"""
        if not Config.BACKUP_ENABLED:
            return None
        
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"backups/{Config.DB_PATH}.backup_{timestamp}"
            
            # إنشاء مجلد النسخ الاحتياطي إذا لم يكن موجوداً
            os.makedirs("backups", exist_ok=True)
            
            # نسخ الملف
            if os.path.exists(Config.DB_PATH):
                shutil.copy2(Config.DB_PATH, backup_path)
                logger.info(f"تم إنشاء نسخة احتياطية: {backup_path}")
                return backup_path
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء نسخة احتياطية: {e}")
        
        return None
    
    @staticmethod
    async def rotate_backups():
        """Rotate old backups - تدوير النسخ القديمة"""
        try:
            if not os.path.exists("backups"):
                return
            
            backups = []
            for filename in os.listdir("backups"):
                if filename.startswith(Config.DB_PATH + ".backup_"):
                    path = os.path.join("backups", filename)
                    backups.append((path, os.path.getctime(path)))
            
            # ترتيب من الأقدم للأحدث
            backups.sort(key=lambda x: x[1])
            
            # حذف النسخ القديمة
            while len(backups) > Config.MAX_BACKUPS:
                oldest_path, _ = backups.pop(0)
                try:
                    os.remove(oldest_path)
                    logger.info(f"تم حذف النسخة القديمة: {oldest_path}")
                except Exception as e:
                    logger.error(f"خطأ في حذف النسخة القديمة: {e}")
                    
        except Exception as e:
            logger.error(f"خطأ في تدوير النسخ الاحتياطية: {e}")
    
    @staticmethod
    async def restore_backup(backup_path: str) -> bool:
        """Restore from backup - الاستعادة من نسخة احتياطية"""
        try:
            if os.path.exists(backup_path) and os.path.exists(Config.DB_PATH):
                # نسخ الملف الأصلي للاحتفاظ به
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                old_backup = f"{Config.DB_PATH}.old_{timestamp}"
                shutil.copy2(Config.DB_PATH, old_backup)
                
                # استعادة النسخة الاحتياطية
                shutil.copy2(backup_path, Config.DB_PATH)
                logger.info(f"تم الاستعادة من: {backup_path}")
                return True
                
        except Exception as e:
            logger.error(f"خطأ في الاستعادة: {e}")
        
        return False

# ======================
# Smart Cache System - نظام الكاش الذكي
# ======================

class SmartCache:
    """Intelligent caching system with memory management - نظام كاش ذكي مع إدارة ذاكرة"""
    
    def __init__(self, max_size: int = Config.MAX_CACHED_URLS):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
        self.operations = 0
        
    def add(self, key: str, value: any) -> None:
        """Add item to cache with smart cleanup - إضافة عنصر للكاش مع تنظيف ذكي"""
        key = self._normalize_key(key)
        
        if key in self.cache:
            # نقل للنهاية (الأكثر استخداماً حديثاً)
            self.cache.move_to_end(key)
            self.cache[key] = value
        else:
            self.cache[key] = value
            self.misses += 1
            
            # إزالة الأقدم إذا كان الكاش ممتلئاً
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)
        
        self.operations += 1
        
        # تنظيف دوري
        if self.operations % Config.CACHE_CLEAN_INTERVAL == 0:
            self._cleanup()
        
        # التحقق من الذاكرة كل 100 عملية
        if self.operations % 100 == 0:
            MemoryManager.check_and_optimize()
    
    def get(self, key: str) -> Optional[any]:
        """Get item from cache - الحصول على عنصر من الكاش"""
        key = self._normalize_key(key)
        
        if key in self.cache:
            self.cache.move_to_end(key)  # تحديث كأكثر استخدام حديثاً
            self.hits += 1
            return self.cache[key]
        
        self.misses += 1
        return None
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache - التحقق إذا كان المفتاح موجوداً في الكاش"""
        return self._normalize_key(key) in self.cache
    
    def remove(self, key: str) -> None:
        """Remove item from cache - إزالة عنصر من الكاش"""
        key = self._normalize_key(key)
        if key in self.cache:
            del self.cache[key]
    
    def clear(self) -> None:
        """Clear entire cache - مسح الكاش بالكامل"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        self.operations = 0
    
    def get_stats(self) -> Dict:
        """Get cache statistics - الحصول على إحصائيات الكاش"""
        total = self.hits + self.misses
        hit_ratio = self.hits / total if total > 0 else 0
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hits,
            'misses': self.misses,
            'hit_ratio': f"{hit_ratio:.2%}",
            'operations': self.operations,
            'memory_usage_mb': MemoryManager.get_memory_usage()
        }
    
    def _normalize_key(self, key: str) -> str:
        """Normalize cache key - توحيد مفتاح الكاش"""
        return str(key).strip().lower() if key else ""
    
    def _cleanup(self) -> None:
        """Cleanup old cache entries - تنظيف إدخالات الكاش القديمة"""
        # إزالة 10% من أقدم الإدخالات إذا كان الكاش ممتلئاً بنسبة 90%
        if len(self.cache) > self.max_size * 0.9:
            items_to_remove = int(self.max_size * 0.1)
            for _ in range(items_to_remove):
                if self.cache:
                    self.cache.popitem(last=False)

# ======================
# Link Processor - معالج الروابط
# ======================

class LinkProcessor:
    """Advanced link processing and normalization - معالجة وتوحيد الروابط المتقدم"""
    
    # معاملات التتبع الشائعة للإزالة
    TRACKING_PARAMS = [
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'ref', 'source', 'campaign', 'medium', 'term', 'content',
        'fbclid', 'gclid', 'msclkid', 'dclid'
    ]
    
    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize URL with intelligent cleaning - توحيد الرابط مع تنظيف ذكي"""
        if not url or not isinstance(url, str):
            return ""
        
        # إزالة البادئات واللواحق الشائعة
        url = url.strip()
        url = re.sub(r'^["\'\s*]+|["\'\s*]+$', '', url)  # إزالة الاقتباس والنجوم
        url = re.sub(r'[,\s]+$', '', url)  # إزالة الفواصل والمسافات الزائدة
        
        # استخراج الرابط من النص
        url_match = re.search(r'(https?://[^\s]+|t\.me/[^\s]+|telegram\.me/[^\s]+|chat\.whatsapp\.com/[^\s]+)', url)
        if url_match:
            url = url_match.group(1)
        
        # إضافة https إذا كانت مفقودة
        if not url.startswith(('http://', 'https://')):
            if url.startswith(('t.me/', 'telegram.me/', 'chat.whatsapp.com/')):
                url = 'https://' + url
            else:
                # محاولة تخمين المنصة
                if 't.me' in url:
                    url = 'https://' + url.lstrip('/')
                elif 'chat.whatsapp.com' in url:
                    url = 'https://' + url.lstrip('/')
        
        # تحليل الرابط لتنظيفه
        try:
            parsed = urlparse(url)
            
            # إزالة معاملات التتبع
            query_params = []
            if parsed.query:
                params = parse_qs(parsed.query)
                
                # تصفية معاملات التتبع
                filtered_params = {}
                for key, values in params.items():
                    key_lower = key.lower()
                    is_tracking = False
                    for tracking_param in LinkProcessor.TRACKING_PARAMS:
                        if tracking_param in key_lower:
                            is_tracking = True
                            break
                    
                    if not is_tracking and key:
                        filtered_params[key] = values[0] if values else ''
                
                # إعادة بناء سلسلة الاستعلام
                if filtered_params:
                    query_params.append(urlencode(filtered_params))
            
            # إعادة بناء الرابط
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if query_params:
                clean_url += f"?{'&'.join(query_params)}"
            
            # إزالة الشرطة المائلة الأخيرة
            if clean_url.endswith('/'):
                clean_url = clean_url[:-1]
            
            return clean_url.lower()
            
        except Exception as e:
            logger.debug(f"خطأ في توحيد الرابط {url}: {e}")
            # استرجاع بسيط للتنظيف
            url = re.sub(r'[?#].*$', '', url)  # إزالة الاستعلام والجزء
            if url.endswith('/'):
                url = url[:-1]
            return url.lower()
    
    @staticmethod
    def extract_telegram_info(url: str) -> Dict:
        """Extract information from Telegram URL - استخراج معلومات من رابط تيليجرام"""
        url = LinkProcessor.normalize_url(url)
        
        result = {
            'platform': 'telegram',
            'username': '',
            'invite_hash': '',
            'is_channel': False,
            'is_join_request': False,
            'is_public': False,
            'is_private': False
        }
        
        # التحقق من روابط طلبات الانضمام
        if '+joinchat/' in url or re.search(r't\.me/\+\w', url):
            result['is_join_request'] = True
            # استخراج الهاش الخاص بالدعوة
            hash_match = re.search(r'\+(?:joinchat/)?([A-Za-z0-9_-]+)', url)
            if hash_match:
                result['invite_hash'] = hash_match.group(1)
                result['is_private'] = True
        else:
            # استخراج اسم المستخدم
            user_match = re.search(r'(?:t\.me|telegram\.me)/([A-Za-z0-9_]+)', url)
            if user_match:
                username = user_match.group(1).lower()
                result['username'] = username
                
                # التحقق إذا كانت قناة
                result['is_channel'] = any(pattern in url for pattern in [
                    '/c/', '/s/', '/channel/', 't.me/s/'
                ]) or username.startswith(('c', 'channel', 's'))
                
                result['is_public'] = not result['is_channel']
        
        return result
    
    @staticmethod
    def extract_whatsapp_info(url: str) -> Dict:
        """Extract information from WhatsApp URL - استخراج معلومات من رابط واتساب"""
        url = LinkProcessor.normalize_url(url)
        
        result = {
            'platform': 'whatsapp',
            'group_id': '',
            'is_valid': False
        }
        
        # استخراج معرف المجموعة
        id_match = re.search(r'chat\.whatsapp\.com/([A-Za-z0-9]+)', url)
        if id_match:
            result['group_id'] = id_match.group(1)
            result['is_valid'] = True
        
        return result
    
    @staticmethod
    def generate_url_hash(url: str) -> str:
        """Generate unique hash for URL - توليد هاش فريد للرابط"""
        normalized = LinkProcessor.normalize_url(url)
        return hashlib.md5(normalized.encode()).hexdigest()

# ======================
# Session Manager - مدير الجلسات
# ======================

class SessionManager:
    """Advanced session management with connection pooling - إدارة جلسات متقدمة مع تجميع الاتصالات"""
    
    _session_cache = SmartCache(max_size=100)
    _session_timestamps = {}
    _lock = asyncio.Lock()
    
    @staticmethod
    async def create_client(session_string: str, session_id: int) -> Optional[TelegramClient]:
        """Create and cache Telegram client - إنشاء وتخزين عميل تيليجرام"""
        cache_key = f"client_{session_id}"
        
        async with SessionManager._lock:
            cached = SessionManager._session_cache.get(cache_key)
            
            if cached and isinstance(cached, TelegramClient):
                try:
                    if await cached.is_user_authorized():
                        # تحديث الطابع الزمني
                        SessionManager._session_timestamps[cache_key] = datetime.now()
                        return cached
                except Exception as e:
                    logger.debug(f"خطأ في التحقق من العميل المخبأ: {e}")
            
            try:
                client = TelegramClient(
                    StringSession(session_string),
                    Config.API_ID,
                    Config.API_HASH,
                    device_model="Advanced Link Collector",
                    system_version="Linux",
                    app_version="4.16.30",
                    lang_code="en",
                    timeout=30,
                    connection_retries=3,
                    auto_reconnect=True,
                    request_retries=3
                )
                
                await client.connect()
                
                if not await client.is_user_authorized():
                    logger.error(f"الجلسة {session_id} غير مصرح بها")
                    await client.disconnect()
                    return None
                
                # تخزين العميل
                SessionManager._session_cache.add(cache_key, client)
                SessionManager._session_timestamps[cache_key] = datetime.now()
                
                return client
                
            except AuthKeyError as e:
                logger.error(f"خطأ مفتاح مصادقة للجلسة {session_id}: {e}")
                return None
            except Exception as e:
                logger.error(f"خطأ في إنشاء عميل للجلسة {session_id}: {e}")
                return None
    
    @staticmethod
    async def close_client(session_id: int) -> None:
        """Close and remove client from cache - إغلاق وإزالة العميل من الكاش"""
        cache_key = f"client_{session_id}"
        
        async with SessionManager._lock:
            client = SessionManager._session_cache.get(cache_key)
            
            if client and isinstance(client, TelegramClient):
                try:
                    await client.disconnect()
                except Exception as e:
                    logger.debug(f"خطأ في إغلاق العميل: {e}")
            
            # إزالة من الكاش والطوابع الزمنية
            SessionManager._session_cache.remove(cache_key)
            SessionManager._session_timestamps.pop(cache_key, None)
    
    @staticmethod
    async def cleanup_inactive_sessions(timeout_seconds: int = Config.SESSION_TIMEOUT):
        """Cleanup inactive sessions - تنظيف الجلسات غير النشطة"""
        async with SessionManager._lock:
            now = datetime.now()
            sessions_to_remove = []
            
            for cache_key, last_used in list(SessionManager._session_timestamps.items()):
                if (now - last_used).total_seconds() > timeout_seconds:
                    sessions_to_remove.append(cache_key)
            
            for cache_key in sessions_to_remove:
                try:
                    client = SessionManager._session_cache.get(cache_key)
                    if client and isinstance(client, TelegramClient):
                        await client.disconnect()
                except:
                    pass
                
                SessionManager._session_cache.remove(cache_key)
                SessionManager._session_timestamps.pop(cache_key, None)
            
            if sessions_to_remove:
                logger.info(f"تم تنظيف {len(sessions_to_remove)} جلسة غير نشطة")
    
    @staticmethod
    def clear_cache() -> None:
        """Clear all cached connections - مسح جميع الاتصالات المخزنة"""
        SessionManager._session_cache.clear()
        SessionManager._session_timestamps.clear()

# ======================
# Database Manager - مدير قاعدة البيانات
# ======================

class DatabaseManager:
    """Advanced database management with async operations - إدارة قاعدة بيانات متقدمة مع عمليات غير متزامنة"""
    
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    
    @classmethod
    async def get_instance(cls):
        """Get database instance with proper async initialization - الحصول على مثيل قاعدة البيانات مع تهيئة غير متزامنة صحيحة"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = DatabaseManager()
                    await cls._instance._initialize()
        return cls._instance
    
    async def _initialize(self):
        """Initialize database asynchronously - تهيئة قاعدة البيانات بشكل غير متزامن"""
        if self._initialized:
            return
        
        self.db_path = Config.DB_PATH
        
        # التحقق من وجود الملف
        db_exists = os.path.exists(self.db_path)
        
        # إنشاء مجلد إذا لم يكن موجوداً
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        
        # فتح الاتصال
        self.connection = await aiosqlite.connect(self.db_path)
        
        # تمكين المفاتيح الخارجية ووضع WAL لأداء أفضل
        await self.connection.execute("PRAGMA foreign_keys = ON")
        await self.connection.execute("PRAGMA journal_mode = WAL")
        await self.connection.execute("PRAGMA synchronous = NORMAL")
        await self.connection.execute("PRAGMA cache_size = -2000")  # كاش 2 ميجابايت
        await self.connection.execute("PRAGMA temp_store = MEMORY")
        await self.connection.execute("PRAGMA mmap_size = 268435456")  # 256MB mmap
        
        await self._create_tables()
        
        # إنشاء نسخة احتياطية إذا كانت قاعدة البيانات موجودة مسبقاً
        if db_exists and Config.BACKUP_ENABLED:
            await BackupManager.create_backup()
            await BackupManager.rotate_backups()
        
        self._initialized = True
        
        logger.info("تم تهيئة قاعدة البيانات بنجاح")
    
    async def _create_tables(self):
        """Create database tables - إنشاء جداول قاعدة البيانات"""
        # جدول الجلسات
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_string TEXT UNIQUE NOT NULL,
                phone_number TEXT,
                user_id INTEGER,
                username TEXT,
                display_name TEXT,
                added_by_user INTEGER,
                is_active BOOLEAN DEFAULT 1,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                status TEXT DEFAULT 'active',
                notes TEXT
            )
        ''')
        
        # جدول الروابط مع فهرسة مناسبة
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL,
                platform TEXT NOT NULL,
                link_type TEXT,
                title TEXT,
                members_count INTEGER DEFAULT 0,
                session_id INTEGER,
                collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                confidence TEXT DEFAULT 'medium',
                is_active BOOLEAN DEFAULT 1,
                metadata TEXT,
                added_by_user INTEGER,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE SET NULL
            )
        ''')
        
        # جدول جلسات الجمع
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS collection_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT DEFAULT 'running',
                stats TEXT,
                duration_seconds INTEGER
            )
        ''')
        
        # جدول المستخدمين (للتحكم)
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS bot_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_admin BOOLEAN DEFAULT 0,
                is_allowed BOOLEAN DEFAULT 1,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP,
                request_count INTEGER DEFAULT 0
            )
        ''')
        
        # إنشاء فهارس لأداء أفضل
        await self._create_indexes()
        
        await self.connection.commit()
    
    async def _create_indexes(self):
        """Create database indexes - إنشاء فهارس قاعدة البيانات"""
        indexes = [
            ('idx_links_url_hash', 'links(url_hash)'),
            ('idx_links_platform_type', 'links(platform, link_type)'),
            ('idx_links_collected_date', 'links(collected_date)'),
            ('idx_links_added_by_user', 'links(added_by_user)'),
            ('idx_sessions_active', 'sessions(is_active)'),
            ('idx_sessions_added_by', 'sessions(added_by_user)'),
            ('idx_users_last_active', 'bot_users(last_active)'),
        ]
        
        for index_name, index_sql in indexes:
            try:
                await self.connection.execute(f'CREATE INDEX IF NOT EXISTS {index_name} ON {index_sql}')
            except Exception as e:
                logger.error(f"خطأ في إنشاء الفهرس {index_name}: {e}")
    
    async def add_session(self, session_string: str, phone: str = '', 
                         user_id: int = 0, username: str = '', 
                         display_name: str = '', added_by_user: int = 0,
                         notes: str = '') -> Tuple[bool, str]:
        """Add a new session - إضافة جلسة جديدة"""
        try:
            # التحقق من عدد الجلسات للمستخدم
            cursor = await self.connection.execute(
                'SELECT COUNT(*) FROM sessions WHERE added_by_user = ?',
                (added_by_user,)
            )
            session_count = (await cursor.fetchone())[0]
            
            if session_count >= Config.MAX_SESSIONS_PER_USER:
                return False, f"تجاوزت الحد الأقصى للجلسات ({Config.MAX_SESSIONS_PER_USER})"
            
            # إضافة الجلسة
            await self.connection.execute('''
                INSERT OR REPLACE INTO sessions 
                (session_string, phone_number, user_id, username, display_name, 
                 added_by_user, last_used, notes)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            ''', (session_string, phone, user_id, username, display_name, 
                  added_by_user, notes))
            
            await self.connection.commit()
            
            # تحديث إحصائيات المستخدم
            await self.update_user_request_count(added_by_user)
            
            return True, "تمت إضافة الجلسة بنجاح"
            
        except Exception as e:
            logger.error(f"خطأ في إضافة جلسة: {e}")
            return False, f"خطأ في الإضافة: {str(e)[:100]}"
    
    async def add_link_batch(self, links: List[Dict]) -> Tuple[int, int]:
        """Add multiple links in batch (much faster) - إضافة روابط متعددة دفعة واحدة (أسرع بكثير)"""
        added = 0
        duplicates = 0
        
        try:
            # استخدام transaction لتحسين الأداء
            await self.connection.execute('BEGIN TRANSACTION')
            
            for link in links:
                try:
                    cursor = await self.connection.execute('''
                        INSERT OR IGNORE INTO links 
                        (url_hash, url, platform, link_type, title, members_count, 
                         session_id, collected_date, confidence, metadata, added_by_user)
                        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
                    ''', (
                        link.get('url_hash'),
                        link.get('url'),
                        link.get('platform'),
                        link.get('link_type'),
                        link.get('title', ''),
                        link.get('members', 0),
                        link.get('session_id'),
                        link.get('confidence', 'medium'),
                        json.dumps(link.get('metadata', {})),
                        link.get('added_by_user', 0)
                    ))
                    
                    if cursor.rowcount > 0:
                        added += 1
                    else:
                        duplicates += 1
                        
                except Exception as e:
                    if 'UNIQUE constraint' in str(e):
                        duplicates += 1
                    else:
                        logger.debug(f"خطأ في إضافة رابط: {e}")
            
            await self.connection.commit()
            
        except Exception as e:
            await self.connection.execute('ROLLBACK')
            logger.error(f"خطأ في إضافة الروابط الدفعية: {e}")
        
        return added, duplicates
    
    async def get_active_sessions(self, user_id: int = None) -> List[Dict]:
        """Get all active sessions - الحصول على جميع الجلسات النشطة"""
        try:
            query = '''
                SELECT id, session_string, phone_number, user_id, 
                       username, display_name, is_active, added_date, 
                       last_used, added_by_user, notes
                FROM sessions 
                WHERE is_active = 1
            '''
            params = []
            
            if user_id:
                query += ' AND added_by_user = ?'
                params.append(user_id)
            
            query += ' ORDER BY last_used DESC'
            
            cursor = await self.connection.execute(query, params)
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in rows]
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على الجلسات النشطة: {e}")
            return []
    
    async def add_or_update_user(self, user_id: int, username: str = '', 
                                first_name: str = '', last_name: str = ''):
        """Add or update user information - إضافة أو تحديث معلومات المستخدم"""
        try:
            await self.connection.execute('''
                INSERT OR REPLACE INTO bot_users 
                (user_id, username, first_name, last_name, last_active)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, username, first_name, last_name))
            
            await self.connection.commit()
            
        except Exception as e:
            logger.error(f"خطأ في إضافة/تحديث المستخدم: {e}")
    
    async def update_user_request_count(self, user_id: int):
        """Update user request count - تحديث عدد طلبات المستخدم"""
        try:
            await self.connection.execute('''
                UPDATE bot_users 
                SET request_count = request_count + 1,
                    last_active = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (user_id,))
            
            await self.connection.commit()
            
        except Exception as e:
            logger.debug(f"خطأ في تحديث عدد طلبات المستخدم: {e}")
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """Get user statistics - الحصول على إحصائيات المستخدم"""
        try:
            cursor = await self.connection.execute('''
                SELECT u.*, 
                       COUNT(DISTINCT s.id) as session_count,
                       COUNT(DISTINCT l.id) as link_count
                FROM bot_users u
                LEFT JOIN sessions s ON u.user_id = s.added_by_user
                LEFT JOIN links l ON u.user_id = l.added_by_user
                WHERE u.user_id = ?
                GROUP BY u.user_id
            ''', (user_id,))
            
            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على إحصائيات المستخدم: {e}")
        
        return {}
    
    async def get_stats_summary(self) -> Dict:
        """Get database statistics summary - الحصول على ملخص إحصائيات قاعدة البيانات"""
        try:
            stats = {}
            
            # إجمالي الروابط
            cursor = await self.connection.execute("SELECT COUNT(*) FROM links")
            stats['total_links'] = (await cursor.fetchone())[0]
            
            # الروابط حسب المنصة
            cursor = await self.connection.execute(
                "SELECT platform, COUNT(*) FROM links GROUP BY platform"
            )
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            # الروابط حسب النوع (تيليجرام فقط)
            cursor = await self.connection.execute('''
                SELECT link_type, COUNT(*) 
                FROM links 
                WHERE platform = 'telegram' 
                GROUP BY link_type
            ''')
            stats['telegram_by_type'] = dict(await cursor.fetchall())
            
            # عدد الجلسات
            cursor = await self.connection.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            # عدد المستخدمين
            cursor = await self.connection.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            return stats
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على ملخص الإحصائيات: {e}")
            return {}
    
    async def export_links(self, link_type: str = None, platform: str = None, 
                          limit: int = 1000) -> List[str]:
        """Export links to list - تصدير الروابط إلى قائمة"""
        try:
            query = "SELECT url FROM links WHERE 1=1"
            params = []
            
            if platform:
                query += " AND platform = ?"
                params.append(platform)
            
            if link_type:
                query += " AND link_type = ?"
                params.append(link_type)
            
            query += " ORDER BY collected_date DESC LIMIT ?"
            params.append(limit)
            
            cursor = await self.connection.execute(query, params)
            rows = await cursor.fetchall()
            
            return [row[0] for row in rows]
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الروابط: {e}")
            return []
    
    async def close(self):
        """Close database connection - إغلاق اتصال قاعدة البيانات"""
        if hasattr(self, 'connection') and self.connection:
            await self.connection.close()
            self._initialized = False

# ======================
# Collection Manager - مدير الجمع
# ======================

class CollectionManager:
    """Advanced collection management with smart algorithms - إدارة جمع متقدمة بخوارزميات ذكية"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        
        # ذواكر كاش ذكية
        self.url_cache = SmartCache()
        self.group_cache = SmartCache(max_size=5000)
        self.whatsapp_cache = SmartCache(max_size=2000)
        
        # إحصائيات
        self.stats = {
            'total_collected': 0,
            'telegram_public': 0,
            'telegram_private': 0,
            'telegram_join': 0,
            'whatsapp_groups': 0,
            'duplicates': 0,
            'channels_skipped': 0,
            'errors': 0,
            'flood_waits': 0,
            'start_time': None,
            'end_time': None,
            'cycles_completed': 0,
            'current_session': None
        }
        
        # تتبع الأداء
        self.performance = {
            'avg_processing_time': 0,
            'total_operations': 0,
            'cache_hit_rate': 0,
            'memory_usage_mb': 0
        }
        
        # عوامل تصفية تاريخ واتساب
        self.whatsapp_cutoff = datetime.now() - timedelta(days=Config.WHATSAPP_DAYS_BACK)
        
        # تأمين للمهام المتزامنة
        self.task_lock = asyncio.Lock()
        self.active_tasks = set()
        
        # تسجيل الدورة
        self.cycle_log = deque(maxlen=100)
    
    async def start_collection(self):
        """Start the collection process - بدء عملية الجمع"""
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.stats['start_time'] = datetime.now()
        self.stats['cycles_completed'] = 0
        self.stats['current_session'] = self.stats['start_time'].strftime('%Y%m%d_%H%M%S')
        
        logger.info("🚀 بدء عملية الجمع المتقدمة")
        
        try:
            # دورة تنظيف دورية للذاكرة
            asyncio.create_task(self._periodic_cleanup())
            
            while self.active and not self.stop_requested:
                if self.paused:
                    await asyncio.sleep(1)
                    continue
                
                await self._collection_cycle()
                
                if self.active and not self.stop_requested:
                    # انتظار قبل الدورة التالية
                    logger.info(f"⏳ اكتملت دورة الجمع {self.stats['cycles_completed']}")
                    
                    # تحسين الذاكرة بين الدورات
                    MemoryManager.optimize_memory()
                    
                    # تأخير متغير بناءً على الأداء
                    delay = self._calculate_next_cycle_delay()
                    await asyncio.sleep(delay)
        
        except Exception as e:
            logger.error(f"❌ خطأ في عملية الجمع: {e}")
            self.stats['errors'] += 1
        
        finally:
            await self._cleanup()
    
    def _calculate_next_cycle_delay(self) -> float:
        """Calculate delay for next cycle based on performance - حساب التأخير للدورة القادمة بناءً على الأداء"""
        base_delay = 30.0
        
        # زيادة التأخير إذا كان هناك أخطاء
        if self.stats['errors'] > 5:
            base_delay += 30
        
        # زيادة التأخير إذا كان هناك flood waits
        if self.stats['flood_waits'] > 3:
            base_delay += 60
        
        # تقليل التأخير إذا كان الأداء جيداً
        if self.performance['cache_hit_rate'] > 0.8:
            base_delay = max(10, base_delay - 10)
        
        return base_delay
    
    async def _periodic_cleanup(self):
        """Periodic cleanup tasks - مهام التنظيف الدورية"""
        while self.active and not self.stop_requested:
            try:
                # تنظيف الجلسات غير النشطة كل 5 دقائق
                await SessionManager.cleanup_inactive_sessions()
                
                # تدوير النسخ الاحتياطية كل ساعة
                if Config.BACKUP_ENABLED:
                    await BackupManager.rotate_backups()
                
                # تحسين الذاكرة كل 10 دقائق
                MemoryManager.check_and_optimize()
                
                # تحديث إحصائيات الأداء
                await self._update_performance_metrics()
                
                await asyncio.sleep(300)  # 5 دقائق
                
            except Exception as e:
                logger.error(f"خطأ في التنظيف الدوري: {e}")
                await asyncio.sleep(60)
    
    async def _collection_cycle(self):
        """Execute one collection cycle - تنفيذ دورة جمع واحدة"""
        try:
            # الحصول على جلسات نشطة
            db = await DatabaseManager.get_instance()
            sessions = await db.get_active_sessions()
            
            if not sessions:
                logger.warning("لا توجد جلسات نشطة متاحة")
                return
            
            # معالجة الجلسات بشكل متزامن (محدود)
            tasks = []
            for session in sessions[:Config.MAX_CONCURRENT_SESSIONS]:
                if not self.active or self.stop_requested:
                    break
                
                task = self._process_session_with_delay(session, len(tasks))
                tasks.append(task)
            
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # تسجيل النتائج
                successful = sum(1 for r in results if not isinstance(r, Exception))
                failed = len(results) - successful
                
                self.cycle_log.append({
                    'timestamp': datetime.now(),
                    'sessions_processed': successful,
                    'sessions_failed': failed,
                    'stats': self.stats.copy()
                })
                
                logger.info(f"تمت معالجة {successful} جلسات، فشل {failed}")
            
            self.stats['cycles_completed'] += 1
            
        except Exception as e:
            logger.error(f"خطأ في دورة الجمع: {e}")
            self.stats['errors'] += 1
    
    async def _process_session_with_delay(self, session: Dict, index: int):
        """Process session with initial delay - معالجة جلسة مع تأخير مبدئي"""
        # تأخير مبدئي لتجنب البدء المتزامن لجميع المهام
        initial_delay = index * Config.REQUEST_DELAYS['between_sessions']
        if initial_delay > 0:
            await asyncio.sleep(initial_delay)
        
        return await self._process_session(session)
    
    async def _process_session(self, session: Dict):
        """Process a single session - معالجة جلسة واحدة"""
        session_id = session.get('id')
        session_string = session.get('session_string')
        added_by_user = session.get('added_by_user', 0)
        
        logger.info(f"معالجة الجلسة {session_id} للمستخدم {added_by_user}")
        
        client = None
        try:
            # الحصول على أو إنشاء عميل
            client = await SessionManager.create_client(session_string, session_id)
            if not client:
                return
            
            # جمع من مصادر متعددة
            collected_links = []
            
            # 1. جمع من الدردشات
            dialog_links = await self._collect_from_dialogs(client, session_id, added_by_user)
            collected_links.extend(dialog_links)
            
            # 2. جمع من الرسائل
            message_links = await self._collect_from_messages(client, session_id, added_by_user)
            collected_links.extend(message_links)
            
            # 3. حفظ الروابط المجمعة دفعة واحدة
            if collected_links:
                db = await DatabaseManager.get_instance()
                
                added, duplicates = await db.add_link_batch(collected_links)
                
                # تحديث الإحصائيات
                self.stats['total_collected'] += added
                self.stats['duplicates'] += duplicates
                
                logger.info(f"الجلسة {session_id}: تمت إضافة {added} روابط، {duplicates} مكررات")
            
            # تحديث آخر استخدام للجلسة
            await self._update_session_last_used(session_id)
            
        except FloodWaitError as e:
            logger.warning(f"انتظار flood للجلسة {session_id}: {e.seconds} ثانية")
            self.stats['flood_waits'] += 1
            await asyncio.sleep(e.seconds + Config.REQUEST_DELAYS['flood_wait'])
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الجلسة {session_id}: {e}")
            self.stats['errors'] += 1
            
        finally:
            if client:
                await SessionManager.close_client(session_id)
    
    async def _collect_from_dialogs(self, client: TelegramClient, session_id: int, 
                                   added_by_user: int) -> List[Dict]:
        """Collect links from dialogs efficiently - جمع الروابط من الدردشات بكفاءة"""
        collected = []
        
        try:
            dialogs = []
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                dialogs.append(dialog)
            
            logger.info(f"تم العثور على {len(dialogs)} دردشة للجلسة {session_id}")
            
            for dialog in dialogs:
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # الحصول على رابط المجموعة إذا كان متاحاً
                    url = None
                    if hasattr(entity, 'username') and entity.username:
                        url = f"https://t.me/{entity.username}"
                    elif hasattr(entity, 'usernames') and entity.usernames:
                        for uname in entity.usernames:
                            if uname.editable:
                                url = f"https://t.me/{uname.username}"
                                break
                    
                    if url:
                        normalized_url = LinkProcessor.normalize_url(url)
                        
                        # التحقق من الكاش
                        if self.url_cache.exists(normalized_url):
                            continue
                        
                        # معالجة الرابط
                        link_info = await self._process_telegram_link(
                            client, normalized_url, session_id, added_by_user
                        )
                        if link_info:
                            collected.append(link_info)
                            self.url_cache.add(normalized_url, True)
                            
                            # تأخير ذكي
                            delay = (Config.REQUEST_DELAYS['join_request'] 
                                    if link_info.get('link_type') == 'join_request' 
                                    else Config.REQUEST_DELAYS['normal'])
                            await asyncio.sleep(delay)
                
                except Exception as e:
                    logger.debug(f"خطأ في معالجة الدردشة: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"خطأ في الجمع من الدردشات: {e}")
        
        return collected
    
    async def _collect_from_messages(self, client: TelegramClient, session_id: int, 
                                    added_by_user: int) -> List[Dict]:
        """Collect links from messages efficiently - جمع الروابط من الرسائل بكفاءة"""
        collected = []
        
        try:
            # مصطلحات بحث ذكية
            search_terms = [
                "t.me", "telegram.me", "مجموعة", "group",
                "رابط", "دعوة", "انضمام", "join"
            ]
            
            for term in search_terms[:Config.MAX_SEARCH_TERMS]:
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    # البحث في الدردشات الحديثة فقط
                    async for dialog in client.iter_dialogs(limit=20):
                        if not self.active or self.stop_requested or self.paused:
                            break
                        
                        try:
                            messages_collected = 0
                            async for message in client.iter_messages(
                                dialog.entity, 
                                search=term, 
                                limit=Config.MAX_MESSAGES_PER_SEARCH
                            ):
                                if not self.active or self.stop_requested or self.paused:
                                    break
                                
                                if message.text:
                                    links = self._extract_links_from_text(message.text)
                                    
                                    for raw_url in links:
                                        try:
                                            if len(collected) >= Config.MAX_LINKS_PER_CYCLE:
                                                return collected
                                            
                                            normalized_url = LinkProcessor.normalize_url(raw_url)
                                            
                                            # التحقق من الكاش
                                            if self.url_cache.exists(normalized_url):
                                                continue
                                            
                                            # التحقق إذا كان رابط واتساب
                                            if 'whatsapp.com' in normalized_url:
                                                # تخطي التحقق من واتساب كما هو مطلوب
                                                if self.whatsapp_cache.exists(normalized_url):
                                                    continue
                                                
                                                link_info = self._process_whatsapp_link(
                                                    normalized_url, 
                                                    session_id,
                                                    added_by_user,
                                                    message.date
                                                )
                                                
                                                if link_info:
                                                    collected.append(link_info)
                                                    self.whatsapp_cache.add(normalized_url, True)
                                                    self.url_cache.add(normalized_url, True)
                                            
                                            else:
                                                # رابط تيليجرام
                                                link_info = await self._process_telegram_link(
                                                    client, 
                                                    normalized_url, 
                                                    session_id,
                                                    added_by_user
                                                )
                                                
                                                if link_info:
                                                    collected.append(link_info)
                                                    self.url_cache.add(normalized_url, True)
                                            
                                            messages_collected += 1
                                            
                                            if messages_collected >= 5:
                                                break
                                            
                                        except Exception as e:
                                            logger.debug(f"خطأ في معالجة الرابط: {e}")
                                            continue
                                
                                # تأخير صغير بين الرسائل
                                await asyncio.sleep(Config.REQUEST_DELAYS['between_tasks'])
                        
                        except Exception as e:
                            logger.debug(f"خطأ في البحث في الدردشة: {e}")
                            continue
                    
                    # تأخير بين مصطلحات البحث
                    await asyncio.sleep(Config.REQUEST_DELAYS['search'])
                
                except Exception as e:
                    logger.error(f"خطأ في البحث عن مصطلح '{term}': {e}")
                    continue
        
        except Exception as e:
            logger.error(f"خطأ في الجمع من الرسائل: {e}")
        
        return collected
    
    async def _process_telegram_link(self, client: TelegramClient, url: str, 
                                    session_id: int, added_by_user: int) -> Optional[Dict]:
        """Process a Telegram link efficiently - معالجة رابط تيليجرام بكفاءة"""
        try:
            # استخراج المعلومات بدون استدعاء API إذا أمكن
            url_info = LinkProcessor.extract_telegram_info(url)
            
            if url_info['is_channel']:
                self.stats['channels_skipped'] += 1
                return None
            
            # التحقق من الكاش لهذه المجموعة
            cache_key = f"group_{url_info.get('username', url_info.get('invite_hash', url))}"
            cached_info = self.group_cache.get(cache_key)
            
            if cached_info:
                return {
                    'url': url,
                    'url_hash': LinkProcessor.generate_url_hash(url),
                    'platform': 'telegram',
                    'link_type': cached_info.get('link_type', 'unknown'),
                    'title': cached_info.get('title', ''),
                    'members': cached_info.get('members', 0),
                    'session_id': session_id,
                    'added_by_user': added_by_user,
                    'confidence': cached_info.get('confidence', 'medium'),
                    'metadata': cached_info.get('metadata', {})
                }
            
            # التحقق فقط إذا لم يكن لدينا معلومات مخبأة
            verified = await self._verify_telegram_group(client, url, url_info)
            
            if verified.get('status') == 'valid':
                # تخزين النتيجة في الكاش
                self.group_cache.add(cache_key, {
                    'link_type': verified.get('link_type'),
                    'title': verified.get('title', ''),
                    'members': verified.get('members', 0),
                    'confidence': 'high'
                })
                
                # تحديث الإحصائيات
                link_type = verified.get('link_type', 'unknown')
                if link_type == 'public_group':
                    self.stats['telegram_public'] += 1
                elif link_type == 'private_group':
                    self.stats['telegram_private'] += 1
                elif link_type == 'join_request':
                    self.stats['telegram_join'] += 1
                
                return {
                    'url': url,
                    'url_hash': LinkProcessor.generate_url_hash(url),
                    'platform': 'telegram',
                    'link_type': verified.get('link_type', 'unknown'),
                    'title': verified.get('title', ''),
                    'members': verified.get('members', 0),
                    'session_id': session_id,
                    'added_by_user': added_by_user,
                    'confidence': 'high',
                    'metadata': {
                        'verified_at': datetime.now().isoformat(),
                        'verification_method': 'telegram_api'
                    }
                }
            
            return None
            
        except Exception as e:
            logger.error(f"خطأ في معالجة رابط تيليجرام {url}: {e}")
            return None
    
    def _process_whatsapp_link(self, url: str, session_id: int, 
                              added_by_user: int, message_date=None) -> Optional[Dict]:
        """Process a WhatsApp link (no verification) - معالجة رابط واتساب (بدون تحقق)"""
        try:
            # تطبيق عامل تصفية التاريخ
            if message_date and message_date < self.whatsapp_cutoff:
                return None
            
            url_info = LinkProcessor.extract_whatsapp_info(url)
            
            if not url_info['is_valid']:
                return None
            
            self.stats['whatsapp_groups'] += 1
            
            return {
                'url': url,
                'url_hash': LinkProcessor.generate_url_hash(url),
                'platform': 'whatsapp',
                'link_type': 'whatsapp_group',
                'title': 'مجموعة واتساب',
                'members': 0,
                'session_id': session_id,
                'added_by_user': added_by_user,
                'confidence': 'low',
                'metadata': {
                    'collected_at': datetime.now().isoformat(),
                    'message_date': message_date.isoformat() if message_date else None
                }
            }
            
        except Exception as e:
            logger.debug(f"خطأ في معالجة رابط واتساب: {e}")
            return None
    
    @staticmethod
    def _extract_links_from_text(text: str) -> List[str]:
        """Extract links from text efficiently - استخراج الروابط من النص بكفاءة"""
        if not text:
            return []
        
        # البحث عن جميع الروابط
        url_pattern = r'(https?://[^\s]+|t\.me/[^\s]+|telegram\.me/[^\s]+|chat\.whatsapp\.com/[^\s]+)'
        return re.findall(url_pattern, text)
    
    async def _verify_telegram_group(self, client: TelegramClient, url: str, url_info: Dict) -> Dict:
        """Verify Telegram group with minimal API calls - التحقق من مجموعة تيليجرام بأقل استدعاءات API"""
        try:
            if url_info['is_join_request']:
                # رابط طلب انضمام
                return {
                    'status': 'valid',
                    'link_type': 'join_request',
                    'title': 'مجموعة طلب انضمام',
                    'members': 0
                }
            
            elif url_info['username'] and not url_info['is_channel']:
                # مجموعة عامة
                try:
                    entity = await client.get_entity(url_info['username'])
                    
                    # التحقق إذا كانت مجموعة (وليست قناة)
                    if hasattr(entity, 'broadcast') and entity.broadcast:
                        return {'status': 'invalid', 'reason': 'قناة'}
                    
                    # التحقق من عدد الأعضاء إذا كان متاحاً
                    members = getattr(entity, 'participants_count', 0)
                    
                    return {
                        'status': 'valid',
                        'link_type': 'public_group',
                        'title': getattr(entity, 'title', ''),
                        'members': members
                    }
                    
                except UsernameNotOccupiedError:
                    return {'status': 'invalid', 'reason': 'غير موجود'}
            
            else:
                # نوع خاص أو آخر
                return {
                    'status': 'valid',
                    'link_type': 'private_group',
                    'title': 'مجموعة خاصة',
                    'members': 0
                }
        
        except FloodWaitError as e:
            raise e
        
        except Exception as e:
            logger.debug(f"خطأ في التحقق لـ {url}: {e}")
            return {'status': 'error', 'reason': str(e)[:100]}
    
    async def _update_session_last_used(self, session_id: int):
        """Update session's last used timestamp - تحديث طابع الوقت لآخر استخدام للجلسة"""
        try:
            db = await DatabaseManager.get_instance()
            
            await db.connection.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP WHERE id = ?",
                (session_id,)
            )
            await db.connection.commit()
            
        except Exception as e:
            logger.debug(f"خطأ في تحديث آخر استخدام للجلسة: {e}")
    
    async def _update_performance_metrics(self):
        """Update performance metrics - تحديث مقاييس الأداء"""
        cache_stats = self.url_cache.get_stats()
        
        self.performance.update({
            'cache_hit_rate': cache_stats['hit_ratio'],
            'total_operations': cache_stats['operations'],
            'cache_size': cache_stats['size'],
            'memory_usage_mb': cache_stats['memory_usage_mb']
        })
    
    async def _cleanup(self):
        """Cleanup resources - تنظيف الموارد"""
        self.active = False
        self.paused = False
        self.stats['end_time'] = datetime.now()
        
        # مسح ذواكر الكاش
        self.url_cache.clear()
        self.group_cache.clear()
        self.whatsapp_cache.clear()
        
        # إغلاق جميع العملاء
        SessionManager.clear_cache()
        
        # تحسين الذاكرة النهائي
        MemoryManager.optimize_memory()
        
        logger.info(f"✅ توقف الجمع. الإحصائيات: {self.stats}")
    
    def get_status(self) -> Dict:
        """Get current collection status - الحصول على حالة الجمع الحالية"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'stats': self.stats.copy(),
            'performance': self.performance.copy(),
            'cache_stats': self.url_cache.get_stats(),
            'memory_mb': MemoryManager.get_memory_usage(),
            'cycle_log_count': len(self.cycle_log)
        }
    
    async def pause(self):
        """Pause collection - إيقاف الجمع مؤقتاً"""
        self.paused = True
        logger.info("⏸️ تم إيقاف الجمع مؤقتاً")
    
    async def resume(self):
        """Resume collection - استئناف الجمع"""
        self.paused = False
        logger.info("▶️ تم استئناف الجمع")
    
    async def stop(self):
        """Stop collection - إيقاف الجمع"""
        self.stop_requested = True
        logger.info("⏹️ تم طلب إيقاف الجمع")

# ======================
# Security & Access Control - الأمان والتحكم في الوصول
# ======================

class SecurityManager:
    """Security and access control manager - مدير الأمان والتحكم في الوصول"""
    
    def __init__(self):
        self.rate_limiter = RateLimiter()
        
    async def check_access(self, user_id: int) -> Tuple[bool, str]:
        """Check if user has access - التحقق إذا كان للمستخدم صلاحية الوصول"""
        # التحقق من الإدارة
        if Config.ADMIN_USER_IDS and user_id in Config.ADMIN_USER_IDS:
            return True, "مدير"
        
        # التحقق من المستخدمين المسموح لهم
        if Config.ALLOWED_USER_IDS and user_id not in Config.ALLOWED_USER_IDS:
            return False, "غير مصرح لك بالوصول"
        
        # التحقق من الحد الأقصى للطلبات
        if not await self.rate_limiter.check_limit(user_id):
            return False, "تجاوزت الحد الأقصى للطلبات. حاول لاحقاً"
        
        return True, "مسموح"
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin - التحقق إذا كان المستخدم مديراً"""
        return user_id in Config.ADMIN_USER_IDS if Config.ADMIN_USER_IDS else False
    
    def get_user_access_level(self, user_id: int) -> str:
        """Get user access level - الحصول على مستوى وصول المستخدم"""
        if self.is_admin(user_id):
            return "مدير"
        elif user_id in Config.ALLOWED_USER_IDS:
            return "مستخدم"
        else:
            return "غير مصرح"

# ======================
# Bot Handlers - معالجات البوت
# ======================

class TelegramBot:
    """Main Telegram bot class - الفئة الرئيسية لبوت تيليجرام"""
    
    def __init__(self):
        self.collection_manager = CollectionManager()
        self.security_manager = SecurityManager()
        self.rate_limiter = RateLimiter()
        
        # تهيئة التطبيق
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        
        # إضافة المعالجات
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup bot handlers - إعداد معالجات البوت"""
        # معالجات الأوامر
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("backup", self.backup_command))
        self.app.add_handler(CommandHandler("cleanup", self.cleanup_command))
        
        # معالجات الاستدعاء
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # معالجات الرسائل
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def _check_access(self, update: Update) -> Tuple[bool, str]:
        """Check user access with rate limiting - التحقق من وصول المستخدم مع الحد من الطلبات"""
        user = update.effective_user
        
        # تحديث المستخدم في قاعدة البيانات
        db = await DatabaseManager.get_instance()
        await db.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        # التحقق من الوصول
        return await self.security_manager.check_access(user.id)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command - معالجة أمر /start"""
        access, message = await self._check_access(update)
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        user = update.effective_user
        
        # تحديث عدد الطلبات
        db = await DatabaseManager.get_instance()
        await db.update_user_request_count(user.id)
        
        welcome_text = f"""
🤖 **مرحباً {user.first_name}!**

**بوت جمع الروابط الذكي المتقدم - الإصدار النهائي**

⚡ **المميزات المتقدمة:**
• نظام جمع ذكي متطور
• إدارة ذاكرة ذكية
• أداء عالي مع معالجة متزامنة
• أمان متكامل
• نسخ احتياطي تلقائي

📊 **حالة النظام:**
• الذاكرة: {MemoryManager.get_memory_usage():.2f} MB
• الكاش: {self.collection_manager.url_cache.get_stats()['hit_ratio']}
• الجمع: {'🟢 نشط' if self.collection_manager.active else '🔴 متوقف'}

👤 **صلاحياتك:** {self.security_manager.get_user_access_level(user.id)}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("👥 الجلسات", callback_data="list_sessions")],
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect"),
             InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
            [InlineKeyboardButton("📊 إحصائيات", callback_data="show_stats"),
             InlineKeyboardButton("📤 تصدير", callback_data="export_menu")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh"),
             InlineKeyboardButton("⚙️ إدارة", callback_data="admin_menu")]
        ])
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command - معالجة أمر /help"""
        access, message = await self._check_access(update)
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        help_text = """
🆘 **مساعدة البوت الذكي المتقدم**

**الأوامر الرئيسية:**
/start - بدء البوت
/help - هذه الرسالة
/status - حالة النظام
/stats - إحصائيات مفصلة
/sessions - إدارة الجلسات
/export - تصدير الروابط
/backup - إدارة النسخ الاحتياطي
/cleanup - تنظيف النظام

**المميزات المتقدمة:**
• نظام كاش متطور
• إدارة ذاكرة ذكية
• معالجة متزامنة متوازنة
• تأخيرات ذكية حسب النوع
• أمان متكامل مع تحكم في الوصول

**إدارة الذاكرة:**
• تخزين مؤقت لـ 20,000 رابط
• تنظيف تلقائي للذاكرة
• مراقبة استخدام الذاكرة
• تحسين تلقائي عند الحاجة

**الجمع الآمن:**
• نظام تحكم في الوصول
• حدود طلبات لكل مستخدم
• تحقق من الجلسات
• نسخ احتياطي تلقائي

**للإداريين:**
• إدارة جميع الجلسات
• تصدير كامل للبيانات
• إدارة النسخ الاحتياطي
• تنظيف النظام
"""
        
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - معالجة أمر /status"""
        access, message = await self._check_access(update)
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        status = self.collection_manager.get_status()
        
        if status['active']:
            if status['paused']:
                status_text = "⏸️ **الجمع موقف مؤقتاً**"
            elif status['stop_requested']:
                status_text = "🛑 **جاري الإيقاف...**"
            else:
                status_text = "🔄 **جاري الجمع بنشاط**"
        else:
            status_text = "🛑 **الجمع متوقف**"
        
        stats = status['stats']
        perf = status['performance']
        cache = status['cache_stats']
        
        # الحصول على إحصائيات المستخدم
        user = update.effective_user
        db = await DatabaseManager.get_instance()
        user_stats = await db.get_user_stats(user.id)
        
        status_text += f"""

📊 **إحصائيات الجمع:**
• إجمالي المجموعات: {stats['total_collected']}
• مجموعات عامة: {stats['telegram_public']}
• مجموعات خاصة: {stats['telegram_private']}
• طلبات انضمام: {stats['telegram_join']}
• مجموعات واتساب: {stats['whatsapp_groups']}
• مكررات: {stats['duplicates']}

⚡ **أداء النظام:**
• نسبة الكاش: {cache['hit_ratio']}
• حجم الكاش: {cache['size']}/{cache['max_size']}
• استخدام الذاكرة: {status['memory_mb']:.2f} MB
• دورات مكتملة: {stats['cycles_completed']}

👤 **إحصائياتك:**
• عدد طلباتك: {user_stats.get('request_count', 0)}
• جلساتك: {user_stats.get('session_count', 0)}
• روابطك: {user_stats.get('link_count', 0)}

🕒 **مدة التشغيل:**
• وقت البدء: {stats['start_time'] or 'لم يبدأ'}
• الوقت الحالي: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        await update.message.reply_text(status_text, parse_mode="Markdown")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command - معالجة أمر /stats"""
        access, message = await self._check_access(update)
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        try:
            db = await DatabaseManager.get_instance()
            
            # الحصول على إحصائيات قاعدة البيانات
            db_stats = await db.get_stats_summary()
            
            # إحصائيات مدير الجمع
            mgr_stats = self.collection_manager.stats
            perf_stats = self.collection_manager.performance
            
            stats_text = f"""
📈 **إحصائيات شاملة للنظام**

🗃️ **قاعدة البيانات:**
• إجمالي الروابط: {db_stats.get('total_links', 0)}
• روابط تيليجرام: {db_stats.get('links_by_platform', {}).get('telegram', 0)}
• روابط واتساب: {db_stats.get('links_by_platform', {}).get('whatsapp', 0)}
• الجلسات النشطة: {db_stats.get('active_sessions', 0)}
• المستخدمون: {db_stats.get('total_users', 0)}

📊 **تيليجرام حسب النوع:**
"""
            
            for link_type, count in db_stats.get('telegram_by_type', {}).items():
                type_name = {
                    'public_group': '📢 مجموعات عامة',
                    'private_group': '🔒 مجموعات خاصة',
                    'join_request': '➕ طلبات انضمام',
                    'unknown': '❓ غير معروف'
                }.get(link_type, link_type)
                
                stats_text += f"• {type_name}: {count}\n"
            
            stats_text += f"""
🚀 **إحصائيات الجمع الحالي:**
• تم جمعها: {mgr_stats['total_collected']}
• قنوات متجاهلة: {mgr_stats['channels_skipped']}
• أخطاء: {mgr_stats['errors']}
• انتظارات Flood: {mgr_stats['flood_waits']}
• دورات مكتملة: {mgr_stats['cycles_completed']}

⚡ **مقاييس الأداء:**
• نسبة ضربات الكاش: {perf_stats['cache_hit_rate']}
• العمليات الإجمالية: {perf_stats['total_operations']:,}
• استخدام الذاكرة: {perf_stats['memory_usage_mb']:.2f} MB

💾 **الذاكرة:**
• استخدام حالي: {MemoryManager.get_memory_usage():.2f} MB
• الحد الأقصى: {Config.MAX_MEMORY_MB} MB
• حالة: {'🟢 جيدة' if MemoryManager.get_memory_usage() < Config.MAX_MEMORY_MB * 0.8 else '🟡 مرتفعة'}
"""
            
            await update.message.reply_text(stats_text, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"خطأ في أمر الإحصائيات: {e}")
            await update.message.reply_text("❌ حدث خطأ في جلب الإحصائيات")
    
    async def sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sessions command - معالجة أمر /sessions"""
        access, message = await self._check_access(update)
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        user = update.effective_user
        is_admin = self.security_manager.is_admin(user.id)
        
        try:
            db = await DatabaseManager.get_instance()
            
            # الحصول على الجلسات
            sessions = await db.get_active_sessions(user.id if not is_admin else None)
            
            if not sessions:
                await update.message.reply_text(
                    "📭 **لا توجد جلسات نشطة**\n\n"
                    "استخدم زر ➕ إضافة جلسة لإضافة جلسة جديدة",
                    parse_mode="Markdown"
                )
                return
            
            text = f"👥 **{'جميع' if is_admin else 'جلساتك'} النشطة**\n\n"
            
            for i, session in enumerate(sessions, 1):
                name = session.get('display_name', f"جلسة {session['id']}")
                phone = session.get('phone_number', 'غير معروف')[-4:] if session.get('phone_number') else 'غير معروف'
                last_used = session.get('last_used', 'لم يستخدم')[:10] if session.get('last_used') else 'لم يستخدم'
                notes = session.get('notes', '')
                
                text += f"{i}. **{name}**\n"
                text += f"   📱: ***{phone} | 📅: {last_used}\n"
                if notes:
                    text += f"   📝: {notes[:30]}{'...' if len(notes) > 30 else ''}\n"
                text += "\n"
            
            text += f"الإجمالي: {len(sessions)} جلسة"
            
            keyboard = None
            if is_admin:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_sessions")],
                    [InlineKeyboardButton("🗑️ تنظيف غير النشطة", callback_data="cleanup_sessions")]
                ])
            
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"خطأ في عرض الجلسات: {e}")
            await update.message.reply_text("❌ حدث خطأ في عرض الجلسات")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command - معالجة أمر /export"""
        access, message = await self._check_access(update)
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        user = update.effective_user
        is_admin = self.security_manager.is_admin(user.id)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 تيليجرام عامة", callback_data="export_telegram_public"),
             InlineKeyboardButton("🔒 تيليجرام خاصة", callback_data="export_telegram_private")],
            [InlineKeyboardButton("➕ طلبات انضمام", callback_data="export_telegram_join"),
             InlineKeyboardButton("📱 واتساب", callback_data="export_whatsapp")],
            [InlineKeyboardButton("📊 الكل", callback_data="export_all"),
             InlineKeyboardButton("📅 اليوم", callback_data="export_today")]
        ])
        
        await update.message.reply_text(
            "📤 **نظام التصدير المتقدم**\n\n"
            "اختر نوع التصدير المطلوب:\n\n"
            "• 📢 تيليجرام عامة - المجموعات العامة\n"
            "• 🔒 تيليجرام خاصة - المجموعات الخاصة\n"
            "• ➕ طلبات انضمام - روابط طلبات الانضمام\n"
            "• 📱 واتساب - مجموعات واتساب\n"
            "• 📊 الكل - جميع الروابط\n"
            "• 📅 اليوم - روابط اليوم فقط",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /backup command - معالجة أمر /backup"""
        access, message = await self._check_access(update)
        if not access and not self.security_manager.is_admin(update.effective_user.id):
            await update.message.reply_text(f"❌ {message}")
            return
        
        if not Config.BACKUP_ENABLED:
            await update.message.reply_text("❌ النسخ الاحتياطي معطل في الإعدادات")
            return
        
        await update.message.reply_text("🔄 جاري إنشاء نسخة احتياطية...")
        
        backup_path = await BackupManager.create_backup()
        
        if backup_path:
            await update.message.reply_text(
                f"✅ **تم إنشاء نسخة احتياطية**\n\n"
                f"• الموقع: `{backup_path}`\n"
                f"• الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"• الحجم: {os.path.getsize(backup_path) / 1024:.2f} كيلوبايت",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ فشل في إنشاء نسخة احتياطية")
    
    async def cleanup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cleanup command - معالجة أمر /cleanup"""
        access, message = await self._check_access(update)
        if not access and not self.security_manager.is_admin(update.effective_user.id):
            await update.message.reply_text(f"❌ {message}")
            return
        
        await update.message.reply_text("🔄 جاري تنظيف النظام...")
        
        try:
            # تنظيف الجلسات غير النشطة
            await SessionManager.cleanup_inactive_sessions()
            
            # تحسين الذاكرة
            saved = MemoryManager.optimize_memory()
            
            # تدوير النسخ الاحتياطية
            if Config.BACKUP_ENABLED:
                await BackupManager.rotate_backups()
            
            await update.message.reply_text(
                f"✅ **تم تنظيف النظام**\n\n"
                f"• تم تحسين الذاكرة: {saved:.2f} MB\n"
                f"• تم تنظيف الجلسات غير النشطة\n"
                f"• تم تدوير النسخ الاحتياطية",
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"خطأ في التنظيف: {e}")
            await update.message.reply_text(f"❌ خطأ في التنظيف: {str(e)[:100]}")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries - معالجة استعلامات الاستدعاء"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        access, message = await self.security_manager.check_access(user.id)
        if not access:
            await query.message.edit_text(f"❌ {message}")
            return
        
        data = query.data
        
        try:
            if data == "add_session":
                await self._handle_add_session(query)
            elif data == "list_sessions":
                await self._handle_list_sessions(query)
            elif data == "start_collect":
                await self._handle_start_collection(query)
            elif data == "pause_collect":
                await self._handle_pause_collection(query)
            elif data == "show_stats":
                await self._handle_show_stats(query)
            elif data == "export_menu":
                await self._handle_export_menu(query)
            elif data == "admin_menu":
                await self._handle_admin_menu(query)
            elif data == "refresh":
                await self._handle_refresh(query)
            elif data == "refresh_sessions":
                await self._handle_refresh_sessions(query)
            elif data == "cleanup_sessions":
                await self._handle_cleanup_sessions(query)
            elif data.startswith("export_"):
                await self._handle_export(query, data.replace("export_", ""))
            else:
                await query.message.edit_text("❌ أمر غير معروف")
        
        except Exception as e:
            logger.error(f"خطأ في معالج الاستدعاء: {e}")
            await query.message.edit_text(f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_add_session(self, query):
        """Handle adding session - معالجة إضافة جلسة"""
        user = query.from_user
        
        # التحقق من عدد الجلسات
        db = await DatabaseManager.get_instance()
        sessions = await db.get_active_sessions(user.id)
        
        if len(sessions) >= Config.MAX_SESSIONS_PER_USER:
            await query.message.edit_text(
                f"❌ **تجاوزت الحد الأقصى للجلسات**\n\n"
                f"لديك {len(sessions)} من أصل {Config.MAX_SESSIONS_PER_USER} جلسة\n"
                f"يرجى حذف جلسة قبل إضافة جديدة"
            )
            return
        
        await query.message.edit_text(
            "📥 **إضافة جلسة جديدة**\n\n"
            "أرسل لي **Session String** الآن:\n\n"
            "**طريقة الحصول عليها:**\n"
            "1. من موقع `https://my.telegram.org`\n"
            "2. استخدام أدوات إنشاء الجلسات\n"
            "3. من تطبيقات Python\n\n"
            "⚠️ **ملاحظات مهمة:**\n"
            "• تأكد من أن الجلسة نشطة\n"
            "• لا تشارك الجلسة مع أحد\n"
            "• يمكنك إضافة ملاحظة بعد إرسال الجلسة\n\n"
            "**الصيغة:**\n"
            "```\n"
            "1 ثم Session String الطويل\n"
            "```",
            parse_mode="Markdown"
        )
    
    async def _handle_start_collection(self, query):
        """Handle starting collection - معالجة بدء الجمع"""
        if self.collection_manager.active:
            await query.message.edit_text("⏳ الجمع يعمل بالفعل")
            return
        
        # بدء الجمع في الخلفية
        asyncio.create_task(self.collection_manager.start_collection())
        
        await query.message.edit_text(
            "🚀 **بدأ الجمع الذكي المتقدم**\n\n"
            "⚡ **المميزات النشطة:**\n"
            "• جمع تيليجرام مع فحص ذكي\n"
            "• جمع واتساب بدون فحص\n"
            "• نظام كاش متطور\n"
            "• معالجة متزامنة متوازنة\n"
            "• إدارة ذاكرة ذكية\n\n"
            "📊 **يتم جمع:**\n"
            "• 📢 مجموعات عامة\n"
            "• 🔒 مجموعات خاصة\n"
            "• ➕ طلبات انضمام\n"
            "• 📱 مجموعات واتساب\n\n"
            "⏳ جاري البدء... قد تستغرق العملية بضع دقائق",
            parse_mode="Markdown"
        )
    
    async def _handle_pause_collection(self, query):
        """Handle pausing collection - معالجة إيقاف الجمع مؤقتاً"""
        if not self.collection_manager.active:
            await query.message.edit_text("⚠️ الجمع غير نشط")
            return
        
        if self.collection_manager.paused:
            await self.collection_manager.resume()
            await query.message.edit_text("▶️ تم استئناف الجمع")
        else:
            await self.collection_manager.pause()
            await query.message.edit_text("⏸️ تم إيقاف الجمع مؤقتاً")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages - معالجة الرسائل النصية"""
        access, message = await self._check_access(update)
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        user = update.effective_user
        text = update.message.text.strip()
        
        # تحديث عدد الطلبات
        db = await DatabaseManager.get_instance()
        await db.update_user_request_count(user.id)
        
        # التحقق إذا كان المستخدم يريد إضافة جلسة
        if len(text) > 100 and text.startswith('1'):
            await self._process_session_string(update.message, text, user)
        else:
            await update.message.reply_text(
                "👋 **مرحباً!**\n\n"
                "استخدم الأزرار للتحكم في البوت\n"
                "أو أرسل Session String لإضافة جلسة\n\n"
                "**الصيغة:**\n"
                "```\n"
                "1 ثم Session String الطويل\n"
                "```",
                parse_mode="Markdown"
            )
    
    async def _process_session_string(self, message, text: str, user):
        """Process session string - معالجة سلسلة الجلسة"""
        await message.reply_text("🔍 جاري التحقق من الجلسة...")
        
        try:
            # استخراج Session String
            lines = text.split('\n')
            session_string = None
            
            for line in lines:
                line = line.strip()
                if line.startswith('1') and len(line) > 50:
                    session_string = line[1:].strip()  # إزالة الرقم 1 من البداية
                    break
                elif len(line) > 200:  # ربما هو Session String بدون رقم
                    session_string = line
                    break
            
            if not session_string:
                await message.reply_text("❌ لم أتمكن من العثور على Session String. تأكد من الصيغة.")
                return
            
            # التحقق من الجلسة
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH,
                timeout=20
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await message.reply_text("❌ الجلسة غير مفعلة. سجل الدخول أولاً.")
                await client.disconnect()
                return
            
            # الحصول على معلومات المستخدم
            me = await client.get_me()
            
            await client.disconnect()
            
            # إضافة إلى قاعدة البيانات
            db = await DatabaseManager.get_instance()
            
            # طلب ملاحظة إضافية
            await message.reply_text(
                "✅ **تم التحقق من الجلسة بنجاح**\n\n"
                "هل تريد إضافة ملاحظة للجلسة؟\n"
                "(مثال: جهازي الشخصي، جلسة احتياطية، إلخ)\n\n"
                "أرسل الملاحظة أو 'تخطي' لتجاهل"
            )
            
            # تخزين الجلسة مؤقتاً
            context.user_data['pending_session'] = {
                'session_string': session_string,
                'phone': me.phone or '',
                'user_id': me.id,
                'username': me.username or '',
                'display_name': f"{me.first_name or ''} {me.last_name or ''}".strip() or f"User_{me.id}"
            }
            
        except SessionPasswordNeededError:
            await message.reply_text(
                "🔐 **الجلسة محمية بكلمة مرور**\n\n"
                "هذه الجلسة تتطلب كلمة مرور ثانوية.\n"
                "يرجى استخدام جلسة أخرى."
            )
            
        except PhoneCodeInvalidError:
            await message.reply_text("❌ رمز الهاتف غير صالح")
            
        except Exception as e:
            logger.error(f"خطأ في التحقق من الجلسة: {e}")
            await message.reply_text(
                f"❌ **خطأ في الجلسة**\n\n"
                f"**التفاصيل:** {str(e)[:150]}\n\n"
                f"تأكد من صحة Session String"
            )
    
    async def _handle_list_sessions(self, query):
        """Handle listing sessions - معالجة عرض الجلسات"""
        await self.sessions_command(query.update, None)
    
    async def _handle_show_stats(self, query):
        """Handle showing stats - معالجة عرض الإحصائيات"""
        await self.stats_command(query.update, None)
    
    async def _handle_export_menu(self, query):
        """Handle export menu - معالجة قائمة التصدير"""
        await self.export_command(query.update, None)
    
    async def _handle_admin_menu(self, query):
        """Handle admin menu - معالجة قائمة الإدارة"""
        user = query.from_user
        
        if not self.security_manager.is_admin(user.id):
            await query.message.edit_text("❌ ليس لديك صلاحية للوصول لهذه القائمة")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث النظام", callback_data="admin_refresh")],
            [InlineKeyboardButton("🧹 تنظيف كامل", callback_data="admin_cleanup")],
            [InlineKeyboardButton("💾 نسخة احتياطية", callback_data="admin_backup")],
            [InlineKeyboardButton("📊 إحصائيات النظام", callback_data="admin_stats")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="refresh")]
        ])
        
        await query.message.edit_text(
            "⚙️ **قائمة الإدارة المتقدمة**\n\n"
            "• 🔄 تحديث النظام - تحديث كامل للنظام\n"
            "• 🧹 تنظيف كامل - تنظيف شامل للذاكرة والجلسات\n"
            "• 💾 نسخة احتياطية - إنشاء نسخة احتياطية يدوياً\n"
            "• 📊 إحصائيات النظام - إحصائيات تفصيلية\n\n"
            "⚠️ **تحذير:** بعض الإجراءات قد تؤثر على أداء النظام",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_refresh(self, query):
        """Handle refresh request - معالجة طلب التحديث"""
        await query.message.edit_text("🔄 جاري تحديث البيانات...")
        await self.start_command(query.update, None)
    
    async def _handle_refresh_sessions(self, query):
        """Handle refresh sessions - معالجة تحديث الجلسات"""
        await self.sessions_command(query.update, None)
    
    async def _handle_cleanup_sessions(self, query):
        """Handle cleanup sessions - معالجة تنظيف الجلسات"""
        user = query.from_user
        
        if not self.security_manager.is_admin(user.id):
            await query.message.edit_text("❌ ليس لديك صلاحية لهذا الإجراء")
            return
        
        await query.message.edit_text("🔄 جاري تنظيف الجلسات غير النشطة...")
        
        await SessionManager.cleanup_inactive_sessions()
        
        await query.message.edit_text("✅ تم تنظيف الجلسات غير النشطة")
    
    async def _handle_export(self, query, export_type: str):
        """Handle export request - معالجة طلب التصدير"""
        user = query.from_user
        
        await query.message.edit_text("📤 جاري تجهيز الملف للتصدير...")
        
        try:
            db = await DatabaseManager.get_instance()
            links = []
            
            if export_type == "all":
                links = await db.export_links(limit=5000)
            elif export_type == "today":
                # هذا يحتاج لتحسين في الإصدارات القادمة
                links = await db.export_links(limit=1000)
            elif export_type == "telegram_public":
                links = await db.export_links(platform="telegram", link_type="public_group", limit=3000)
            elif export_type == "telegram_private":
                links = await db.export_links(platform="telegram", link_type="private_group", limit=3000)
            elif export_type == "telegram_join":
                links = await db.export_links(platform="telegram", link_type="join_request", limit=3000)
            elif export_type == "whatsapp":
                links = await db.export_links(platform="whatsapp", limit=3000)
            
            if not links:
                await query.message.edit_text("❌ لا توجد روابط للتصدير")
                return
            
            # حفظ في ملف مؤقت
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"export_{export_type}_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(link + '\n')
            
            # إرسال الملف
            with open(filename, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📁 **ملف التصدير**\n\n"
                           f"• النوع: {export_type}\n"
                           f"• عدد الروابط: {len(links)}\n"
                           f"• التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            
            # حذف الملف المؤقت
            os.remove(filename)
            
        except Exception as e:
            logger.error(f"خطأ في التصدير: {e}")
            await query.message.edit_text(f"❌ خطأ في التصدير: {str(e)[:100]}")
    
    async def run(self):
        """Run the bot - تشغيل البوت"""
        try:
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
            
            # تهيئة قاعدة البيانات
            db = await DatabaseManager.get_instance()
            
            logger.info("🤖 بدء تشغيل بوت جمع الروابط الذكي المتقدم...")
            logger.info(f"⚙️ الإعدادات: {Config.__dict__}")
            logger.info("🚀 البوت يعمل...")
            
            # بدء التنظيف الدوري
            asyncio.create_task(self._periodic_maintenance())
            
            await self.app.initialize()
            await self.app.start()
            await self.app.updater.start_polling()
            
            # البقاء في التشغيل
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"❌ خطأ في البوت: {e}")
            raise
        
        finally:
            # التنظيف
            db = await DatabaseManager.get_instance()
            await db.close()
            await self.app.stop()
    
    async def _periodic_maintenance(self):
        """Periodic maintenance tasks - مهام الصيانة الدورية"""
        while True:
            try:
                # تنظيف الذاكرة كل 5 دقائق
                MemoryManager.check_and_optimize()
                
                # تنظيف الجلسات كل 10 دقائق
                await SessionManager.cleanup_inactive_sessions()
                
                # تدوير النسخ الاحتياطية كل ساعة
                if Config.BACKUP_ENABLED:
                    await BackupManager.rotate_backups()
                
                await asyncio.sleep(300)  # 5 دقائق
                
            except Exception as e:
                logger.error(f"خطأ في الصيانة الدورية: {e}")
                await asyncio.sleep(60)

# ======================
# Message Handler for Session Notes - معالج الرسائل لملاحظات الجلسة
# ======================

async def handle_session_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle session notes - معالجة ملاحظات الجلسة"""
    user = update.effective_user
    text = update.message.text.strip()
    
    if 'pending_session' not in context.user_data:
        return
    
    session_data = context.user_data['pending_session']
    
    if text.lower() == 'تخطي' or text.lower() == 'skip':
        notes = ''
    else:
        notes = text[:200]  # تحديد طول الملاحظات
    
    # إضافة الجلسة
    db = await DatabaseManager.get_instance()
    success, message = await db.add_session(
        session_data['session_string'],
        session_data['phone'],
        session_data['user_id'],
        session_data['username'],
        session_data['display_name'],
        user.id,
        notes
    )
    
    if success:
        await update.message.reply_text(
            f"✅ **تمت إضافة الجلسة بنجاح**\n\n"
            f"• الاسم: {session_data['display_name']}\n"
            f"• المعرف: {session_data['user_id']}\n"
            f"• المستخدم: @{session_data['username'] or 'لا يوجد'}\n"
            f"• الملاحظة: {notes or 'لا توجد'}\n"
            f"• الحالة: 🟢 نشطة\n\n"
            f"يمكنك البدء بالجمع الآن!",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"⚠️ **{message}**\n\n"
            f"قد تكون الجلسة موجودة مسبقاً."
        )
    
    # تنظيف البيانات المؤقتة
    del context.user_data['pending_session']

# ======================
# Signal Handlers - معالجات الإشارات
# ======================

def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown - إعداد معالجات الإشارات للإغلاق السلس"""
    def signal_handler(signum, frame):
        logger.info(f"📶 تم استقبال إشارة {signum}. جاري الإغلاق السلس...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# ======================
# Main Entry Point - نقطة الدخول الرئيسية
# ======================

async def main():
    """Main async entry point - نقطة الدخول الرئيسية غير المتزامنة"""
    # إعداد معالجات الإشارات
    setup_signal_handlers()
    
    # تعيين سياسة حلقة الأحداث لأداء أفضل
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    else:
        # استخدام uvloop إذا كان متاحاً لأداء أفضل
        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            logger.info("✅ استخدام uvloop لتحسين الأداء")
        except ImportError:
            logger.info("⚠️ uvloop غير مثبت. استخدام حلقة الأحداث الافتراضية")
    
    # تعيين حدود الملفات المفتوحة
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_NOFILE, (8192, 8192))
    except:
        pass
    
    # تشغيل البوت
    bot = TelegramBot()
    
    # إضافة معالج لملاحظات الجلسة
    bot.app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_session_notes
    ))
    
    await bot.run()

if __name__ == "__main__":
    # إنشاء مجلد النسخ الاحتياطي
    os.makedirs("backups", exist_ok=True)
    
    # تشغيل التطبيق
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 توقف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ قاتل: {e}")
        sys.exit(1)
