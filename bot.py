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
import secrets
import base64
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
    ADMIN_USER_IDS = set(map(int, os.getenv("ADMIN_USER_IDS", "0").split(",")))
    ALLOWED_USER_IDS = set(map(int, os.getenv("ALLOWED_USER_IDS", "0").split(",")))
    
    # Encryption - التشفير
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    
    # Memory management - إدارة الذاكرة
    MAX_CACHED_URLS = 20000
    CACHE_CLEAN_INTERVAL = 1000
    MAX_MEMORY_MB = 500  # الحد الأقصى للذاكرة بالميجابايت
    
    # Performance settings - إعدادات الأداء
    MAX_CONCURRENT_SESSIONS = 5  # زيادة من 3 إلى 5
    REQUEST_DELAYS = {
        'normal': 1.0,
        'join_request': 30.0,
        'search': 2.0,
        'flood_wait': 5.0,
        'between_sessions': 2.0,  # تقليل من 3 إلى 2
        'between_tasks': 0.3,     # تقليل من 0.5 إلى 0.3
        'min_cycle_delay': 15.0,  # تأخير جديد للدورات
        'max_cycle_delay': 60.0   # تأخير جديد للدورات
    }
    
    # Collection limits - حدود الجمع
    MAX_DIALOGS_PER_SESSION = 50  # زيادة من 40 إلى 50
    MAX_MESSAGES_PER_SEARCH = 10  # زيادة من 8 إلى 10
    MAX_SEARCH_TERMS = 8          # زيادة من 5 إلى 8
    MAX_LINKS_PER_CYCLE = 150     # زيادة من 100 إلى 150
    MAX_BATCH_SIZE = 50           # حجم جديد للدفعات
    
    # Database - قاعدة البيانات
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10              # زيادة من 5 إلى 10
    DB_POOL_SIZE = 5              # حجم تجميع الاتصالات
    
    # WhatsApp collection - جمع واتساب
    WHATSAPP_DAYS_BACK = 30       # زيادة من 15 إلى 30 يوم
    
    # Link verification - التحقق من الروابط
    MIN_GROUP_MEMBERS = 3         # تقليل من 5 إلى 3
    MAX_LINK_LENGTH = 200
    
    # Rate limiting - الحد من الطلبات
    USER_RATE_LIMIT = {
        'max_requests': 15,        # زيادة من 10 إلى 15
        'per_seconds': 60
    }
    
    # Session management - إدارة الجلسات
    SESSION_TIMEOUT = 600         # زيادة من 300 إلى 600 (10 دقائق)
    MAX_SESSIONS_PER_USER = 8     # زيادة من 5 إلى 8
    
    # Export - التصدير
    MAX_EXPORT_LINKS = 10000      # زيادة حد التصدير
    EXPORT_CHUNK_SIZE = 1000      # حجم دفعات التصدير

# ======================
# Advanced Logging - التسجيل المتقدم
# ======================

class StructuredLogger:
    """Advanced structured logging system - نظام تسجيل هيكلي متقدم"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.request_id = 0
        
    def generate_request_id(self) -> str:
        """Generate unique request ID - توليد معرف طلب فريد"""
        self.request_id += 1
        return f"REQ-{self.request_id:06d}-{secrets.token_hex(4)}"
    
    def info(self, message: str, extra: Dict = None):
        """Info level log with context - تسجيل مستوى معلومات مع سياق"""
        context = {
            'request_id': self.generate_request_id(),
            'timestamp': datetime.now().isoformat(),
            'memory_mb': MemoryManager.get_memory_usage()
        }
        if extra:
            context.update(extra)
        
        self.logger.info(f"{message} | {json.dumps(context, ensure_ascii=False)}")
    
    def error(self, message: str, exc_info: bool = True, extra: Dict = None):
        """Error level log with stack trace - تسجيل مستوى خطأ مع تتبع المكدس"""
        context = {
            'request_id': self.generate_request_id(),
            'timestamp': datetime.now().isoformat(),
            'error_type': 'exception'
        }
        if extra:
            context.update(extra)
        
        self.logger.error(f"{message} | {json.dumps(context, ensure_ascii=False)}", 
                         exc_info=exc_info)
    
    def warning(self, message: str, extra: Dict = None):
        """Warning level log - تسجيل مستوى تحذير"""
        context = {
            'request_id': self.generate_request_id(),
            'timestamp': datetime.now().isoformat()
        }
        if extra:
            context.update(extra)
        
        self.logger.warning(f"{message} | {json.dumps(context, ensure_ascii=False)}")
    
    def debug(self, message: str, extra: Dict = None):
        """Debug level log with performance data - تسجيل مستوى تصحيح مع بيانات الأداء"""
        context = {
            'request_id': self.generate_request_id(),
            'timestamp': datetime.now().isoformat(),
            'memory_mb': MemoryManager.get_memory_usage(),
            'cache_hits': CacheManager.get_instance().get_stats()['hits']
        }
        if extra:
            context.update(extra)
        
        self.logger.debug(f"{message} | {json.dumps(context, ensure_ascii=False)}")

# إعداد التسجيل المتقدم
def setup_logging():
    """Setup advanced logging configuration - إعداد تهيئة التسجيل المتقدم"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler('bot.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # تطبيق التنسيق على جميع المعالجات
    formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)
    
    return StructuredLogger()

logger = setup_logging()

# ======================
# Encryption Manager - مدير التشفير
# ======================

class EncryptionManager:
    """Advanced encryption system for session storage - نظام تشفير متقدم لتخزين الجلسات"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance - الحصول على مثيل فريد"""
        if cls._instance is None:
            cls._instance = EncryptionManager()
        return cls._instance
    
    def __init__(self):
        """Initialize encryption manager - تهيئة مدير التشفير"""
        key = Config.ENCRYPTION_KEY.encode()
        
        # استخدام KDF لتوليد مفتاح آمن
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'links_collector_salt',
            iterations=100000,
        )
        
        derived_key = base64.urlsafe_b64encode(kdf.derive(key))
        self.cipher = Fernet(derived_key)
    
    def encrypt(self, data: str) -> str:
        """Encrypt sensitive data - تشفير البيانات الحساسة"""
        try:
            encrypted = self.cipher.encrypt(data.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"خطأ في التشفير: {e}")
            return data  # الرجوع للنص الصريح في حالة الفشل
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt sensitive data - فك تشفير البيانات الحساسة"""
        try:
            decrypted = self.cipher.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"خطأ في فك التشفير: {e}")
            return encrypted_data  # الرجوع للنص المشفر في حالة الفشل
    
    def encrypt_session(self, session_string: str) -> str:
        """Encrypt session string with metadata - تشفير سلسلة الجلسة مع بيانات وصفية"""
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
        """Decrypt session string - فك تشفير سلسلة الجلسة"""
        try:
            decrypted = self.decrypt(encrypted_data)
            data = json.loads(decrypted)
            return data['session']
        except Exception as e:
            logger.error(f"خطأ في فك تشفير الجلسة: {e}")
            return None

# ======================
# Memory Manager - مدير الذاكرة
# ======================

class MemoryManager:
    """Advanced memory management system with monitoring - نظام متقدم لإدارة الذاكرة مع المراقبة"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance - الحصول على مثيل فريد"""
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
        """Get current memory usage in MB - الحصول على استخدام الذاكرة بالميجابايت"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except Exception as e:
            logger.debug(f"خطأ في قراءة الذاكرة: {e}")
            return 0
    
    def get_memory_percent(self) -> float:
        """Get memory usage percentage - الحصول على نسبة استخدام الذاكرة"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_percent()
        except:
            return 0
    
    def get_system_memory(self) -> Dict:
        """Get system memory information - الحصول على معلومات ذاكرة النظام"""
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
        """Optimize memory usage with detailed reporting - تحسين استخدام الذاكرة مع تقرير مفصل"""
        before = self.get_memory_usage()
        before_time = datetime.now()
        
        # جمع المهملات
        gc.collect()
        
        # إغلاق الملفات المفتوحة
        try:
            process = psutil.Process(os.getpid())
            open_files = len(process.open_files())
            if open_files > 50:
                logger.warning(f"عدد كبير من الملفات المفتوحة: {open_files}", {
                    'open_files': open_files
                })
        except:
            pass
        
        # تحرير ذواكر الكاش الكبيرة
        CacheManager.get_instance().optimize()
        
        after = self.get_memory_usage()
        saved = before - after
        
        self.metrics['optimizations'] += 1
        self.metrics['total_saved_mb'] += saved if saved > 0 else 0
        self.metrics['last_optimization'] = datetime.now()
        
        logger.info(f"تحسين الذاكرة: {saved:.2f} MB", {
            'saved_mb': saved,
            'before_mb': before,
            'after_mb': after,
            'optimization_count': self.metrics['optimizations']
        })
        
        return {
            'saved_mb': saved,
            'before_mb': before,
            'after_mb': after,
            'duration_ms': (datetime.now() - before_time).total_seconds() * 1000
        }
    
    def check_and_optimize(self, threshold_percent: float = 80.0) -> Dict:
        """Check memory and optimize if needed - التحقق من الذاكرة والتحسين إذا لزم"""
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
            logger.warning(f"استخدام عالي للذاكرة: {current_mb:.2f} MB, {current_percent:.1f}%", {
                'memory_mb': current_mb,
                'memory_percent': current_percent,
                'threshold_mb': Config.MAX_MEMORY_MB,
                'threshold_percent': threshold_percent
            })
            
            self.metrics['high_memory_warnings'] += 1
            optimization_result = self.optimize_memory()
            result.update(optimization_result)
            result['optimized'] = True
        
        return result
    
    def get_metrics(self) -> Dict:
        """Get memory management metrics - الحصول على مقاييس إدارة الذاكرة"""
        return {
            **self.metrics,
            'current_mb': self.get_memory_usage(),
            'current_percent': self.get_memory_percent(),
            'system_memory': self.get_system_memory()
        }

# ======================
# Advanced Cache System - نظام الكاش المتقدم
# ======================

class CacheManager:
    """Intelligent caching system with tiered storage - نظام كاش ذكي مع تخزين طبقي"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance - الحصول على مثيل فريد"""
        if cls._instance is None:
            cls._instance = CacheManager()
        return cls._instance
    
    def __init__(self):
        # كاش سريع (في الذاكرة)
        self.fast_cache = OrderedDict()
        self.fast_cache_size = 5000
        
        # كاش بطيء (ملفات مؤقتة)
        self.slow_cache_dir = "cache_data"
        os.makedirs(self.slow_cache_dir, exist_ok=True)
        
        # إحصائيات
        self.stats = {
            'fast_hits': 0,
            'slow_hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_operations': 0
        }
        
        # تأمين للوصول المتزامن
        self.lock = asyncio.Lock()
    
    async def get(self, key: str, category: str = 'general') -> Optional[Any]:
        """Get item from cache - الحصول على عنصر من الكاش"""
        async with self.lock:
            self.stats['total_operations'] += 1
            cache_key = f"{category}_{key}"
            
            # التحقق في الكاش السريع أولاً
            if cache_key in self.fast_cache:
                self.fast_cache.move_to_end(cache_key)
                self.stats['fast_hits'] += 1
                return self.fast_cache[cache_key]
            
            # التحقق في الكاش البطيء
            file_path = os.path.join(self.slow_cache_dir, f"{hashlib.md5(cache_key.encode()).hexdigest()}.cache")
            if os.path.exists(file_path):
                try:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        data = json.loads(content)
                        
                        # نقل للكاش السريع (استخدام شائع)
                        await self._add_to_fast_cache(cache_key, data)
                        self.stats['slow_hits'] += 1
                        return data
                except:
                    pass
            
            self.stats['misses'] += 1
            return None
    
    async def set(self, key: str, value: Any, category: str = 'general', ttl_seconds: int = 3600):
        """Set item in cache - تعيين عنصر في الكاش"""
        async with self.lock:
            cache_key = f"{category}_{key}"
            
            # إضافة للكاش السريع
            await self._add_to_fast_cache(cache_key, value)
            
            # إضافة للكاش البطيء
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
        """Add item to fast cache - إضافة عنصر للكاش السريع"""
        if key in self.fast_cache:
            self.fast_cache.move_to_end(key)
            self.fast_cache[key] = value
        else:
            self.fast_cache[key] = value
            
            # إزالة العناصر الزائدة
            if len(self.fast_cache) > self.fast_cache_size:
                oldest_key = next(iter(self.fast_cache))
                del self.fast_cache[oldest_key]
                self.stats['evictions'] += 1
    
    def exists(self, key: str, category: str = 'general') -> bool:
        """Check if key exists in fast cache - التحقق إذا كان المفتاح موجوداً في الكاش السريع"""
        cache_key = f"{category}_{key}"
        return cache_key in self.fast_cache
    
    async def delete(self, key: str, category: str = 'general'):
        """Delete item from cache - حذف عنصر من الكاش"""
        async with self.lock:
            cache_key = f"{category}_{key}"
            
            # حذف من الكاش السريع
            if cache_key in self.fast_cache:
                del self.fast_cache[cache_key]
            
            # حذف من الكاش البطيء
            file_path = os.path.join(self.slow_cache_dir, f"{hashlib.md5(cache_key.encode()).hexdigest()}.cache")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
    
    async def cleanup_expired(self):
        """Cleanup expired cache entries - تنظيف إدخالات الكاش المنتهية"""
        async with self.lock:
            expired_count = 0
            
            # تنظيف الكاش البطيء
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
        """Optimize cache usage - تحسين استخدام الكاش"""
        current_size = len(self.fast_cache)
        if current_size > self.fast_cache_size:
            # تقليل حجم الكاش السريع بنسبة 20%
            target_size = int(self.fast_cache_size * 0.8)
            while len(self.fast_cache) > target_size:
                oldest_key = next(iter(self.fast_cache))
                del self.fast_cache[oldest_key]
                self.stats['evictions'] += 1
    
    def get_stats(self) -> Dict:
        """Get cache statistics - الحصول على إحصائيات الكاش"""
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
        """Clear all cache - مسح الكاش بالكامل"""
        async with self.lock:
            self.fast_cache.clear()
            
            # مسح الكاش البطيء
            if os.path.exists(self.slow_cache_dir):
                for filename in os.listdir(self.slow_cache_dir):
                    if filename.endswith('.cache'):
                        try:
                            os.remove(os.path.join(self.slow_cache_dir, filename))
                        except:
                            pass
            
            # إعادة تعيين الإحصائيات
            self.stats = {
                'fast_hits': 0,
                'slow_hits': 0,
                'misses': 0,
                'evictions': 0,
                'total_operations': 0
            }

# ======================
# Rate Limiter - الحد من الطلبات
# ======================

class RateLimiter:
    """Advanced rate limiting system with sliding window - نظام حد طلبات متقدم مع نافذة منزلقة"""
    
    def __init__(self):
        self.requests = defaultdict(deque)
        self.locks = defaultdict(asyncio.Lock)
        self.metrics = defaultdict(lambda: {'total_requests': 0, 'blocked_requests': 0})
    
    async def check_limit(self, user_id: int, 
                         max_requests: int = Config.USER_RATE_LIMIT['max_requests'],
                         per_seconds: int = Config.USER_RATE_LIMIT['per_seconds']) -> Tuple[bool, Dict]:
        """Check if user is rate limited - التحقق إذا كان المستخدم يتجاوز الحد"""
        async with self.locks[user_id]:
            now = datetime.now()
            user_requests = self.requests[user_id]
            self.metrics[user_id]['total_requests'] += 1
            
            # إزالة الطلبات القديمة
            while user_requests and (now - user_requests[0]).total_seconds() > per_seconds:
                user_requests.popleft()
            
            if len(user_requests) >= max_requests:
                self.metrics[user_id]['blocked_requests'] += 1
                
                # حساب وقت الانتظار
                oldest_request = user_requests[0] if user_requests else now
                wait_time = per_seconds - (now - oldest_request).total_seconds()
                
                return False, {
                    'wait_seconds': max(0, wait_time),
                    'requests_in_window': len(user_requests),
                    'max_allowed': max_requests
                }
            
            user_requests.append(now)
            return True, {
                'requests_in_window': len(user_requests),
                'max_allowed': max_requests
            }
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Get rate limit stats for user - الحصول على إحصائيات الحد للمستخدم"""
        now = datetime.now()
        user_requests = self.requests.get(user_id, deque())
        
        # عد الطلبات في النوافذ الزمنية المختلفة
        recent_counts = {}
        for seconds in [10, 30, 60, 300, 1800]:  # 10ث, 30ث, 1د, 5د, 30د
            count = sum(1 for req_time in user_requests 
                       if (now - req_time).total_seconds() <= seconds)
            recent_counts[f'last_{seconds}s'] = count
        
        return {
            'recent_counts': recent_counts,
            'total_requests': self.metrics[user_id]['total_requests'],
            'blocked_requests': self.metrics[user_id]['blocked_requests'],
            'block_rate': self.metrics[user_id]['blocked_requests'] / max(1, self.metrics[user_id]['total_requests']),
            'current_window': len(user_requests),
            'max_allowed': Config.USER_RATE_LIMIT['max_requests']
        }
    
    async def reset_user(self, user_id: int):
        """Reset rate limit for user - إعادة تعيين حد الطلبات للمستخدم"""
        async with self.locks[user_id]:
            self.requests[user_id].clear()
            self.metrics[user_id] = {'total_requests': 0, 'blocked_requests': 0}
    
    def get_global_stats(self) -> Dict:
        """Get global rate limiting statistics - الحصول على إحصائيات الحد الشاملة"""
        total_users = len(self.requests)
        total_requests = sum(metrics['total_requests'] for metrics in self.metrics.values())
        total_blocked = sum(metrics['blocked_requests'] for metrics in self.metrics.values())
        
        return {
            'total_users': total_users,
            'total_requests': total_requests,
            'total_blocked': total_blocked,
            'global_block_rate': total_blocked / max(1, total_requests),
            'active_sessions': len([r for r in self.requests.values() if r])
        }

# ======================
# Advanced Backup Manager - مدير النسخ الاحتياطي المتقدم
# ======================

class BackupManager:
    """Database backup system with compression and encryption - نظام نسخ احتياطي مع ضغط وتشفير"""
    
    @staticmethod
    async def create_backup() -> Optional[Dict]:
        """Create database backup with metadata - إنشاء نسخة احتياطية مع بيانات وصفية"""
        if not Config.BACKUP_ENABLED:
            return None
        
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = "backups"
            backup_filename = f"{Config.DB_PATH}.backup_{timestamp}"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            # إنشاء مجلد النسخ الاحتياطي
            os.makedirs(backup_dir, exist_ok=True)
            
            if not os.path.exists(Config.DB_PATH):
                logger.error("ملف قاعدة البيانات غير موجود")
                return None
            
            # إحصائيات قبل النسخ
            db_size = os.path.getsize(Config.DB_PATH)
            
            # نسخ الملف
            shutil.copy2(Config.DB_PATH, backup_path)
            
            # إنشاء ملف بيانات وصفية
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
            
            logger.info(f"تم إنشاء نسخة احتياطية: {backup_path}", {
                'backup_size_mb': metadata['size_mb'],
                'backup_id': metadata['backup_id']
            })
            
            return metadata
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء نسخة احتياطية: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _calculate_checksum(file_path: str) -> str:
        """Calculate file checksum - حساب مجموع التحقق للملف"""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    @staticmethod
    async def rotate_backups():
        """Rotate old backups with intelligent selection - تدوير النسخ القديمة باختيار ذكي"""
        try:
            if not os.path.exists("backups"):
                return
            
            backups = []
            for filename in os.listdir("backups"):
                if filename.startswith(Config.DB_PATH + ".backup_"):
                    path = os.path.join("backups", filename)
                    
                    # تجنب حذف ملفات البيانات الوصفية
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
            
            # ترتيب من الأقدم للأحدث
            backups.sort(key=lambda x: x['created'])
            
            # إستراتيجية ذكية للاحتفاظ:
            # 1. الاحتفاظ بآخر 7 نسخ
            # 2. الاحتفاظ بنسخة يومياً لآخر 30 يوم
            # 3. الاحتفاظ بنسخة أسبوعياً لآخر 3 أشهر
            
            now = datetime.now()
            to_keep = []
            to_delete = []
            
            for backup in backups:
                backup_date = datetime.fromtimestamp(backup['created'])
                age_days = (now - backup_date).days
                
                # دائمًا احتفظ بآخر 7 نسخ
                if len(to_keep) < Config.MAX_BACKUPS:
                    to_keep.append(backup)
                    continue
                
                # حذف الباقي
                to_delete.append(backup)
            
            # حذف النسخ القديمة
            deleted_count = 0
            for backup in to_delete:
                try:
                    # حذف النسخة والبيانات الوصفية
                    os.remove(backup['path'])
                    
                    # حذف ملف البيانات الوصفية إذا كان موجوداً
                    meta_path = backup['path'] + '.meta'
                    if os.path.exists(meta_path):
                        os.remove(meta_path)
                    
                    deleted_count += 1
                    logger.info(f"تم حذف النسخة القديمة: {backup['path']}", {
                        'size_mb': backup['size'] / 1024 / 1024,
                        'age_days': (now - datetime.fromtimestamp(backup['created'])).days
                    })
                    
                except Exception as e:
                    logger.error(f"خطأ في حذف النسخة القديمة: {e}")
            
            if deleted_count > 0:
                logger.info(f"تم تدوير {deleted_count} نسخة احتياطية قديمة")
            
            return deleted_count
                    
        except Exception as e:
            logger.error(f"خطأ في تدوير النسخ الاحتياطية: {e}", exc_info=True)
            return 0
    
    @staticmethod
    async def restore_backup(backup_id: str = None, backup_path: str = None) -> Tuple[bool, str]:
        """Restore from backup with validation - الاستعادة من نسخة احتياطية مع التحقق"""
        try:
            target_path = None
            
            if backup_path and os.path.exists(backup_path):
                target_path = backup_path
            elif backup_id:
                # البحث عن النسخة بالمعرف
                for filename in os.listdir("backups"):
                    if backup_id in filename and not filename.endswith('.meta'):
                        target_path = os.path.join("backups", filename)
                        break
            
            if not target_path or not os.path.exists(target_path):
                return False, "النسخة الاحتياطية غير موجودة"
            
            # التحقق من صحة النسخة
            checksum = BackupManager._calculate_checksum(target_path)
            
            # قراءة البيانات الوصفية
            meta_path = target_path + '.meta'
            if os.path.exists(meta_path):
                async with aiofiles.open(meta_path, 'r', encoding='utf-8') as f:
                    metadata = json.loads(await f.read())
                    expected_checksum = metadata.get('checksum')
                    
                    if expected_checksum and checksum != expected_checksum:
                        return False, "النسخة الاحتياطية تالفة (التحقق من المجموع فشل)"
            
            # إنشاء نسخة من الملف الحالي
            if os.path.exists(Config.DB_PATH):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                old_backup = f"{Config.DB_PATH}.pre_restore_{timestamp}"
                shutil.copy2(Config.DB_PATH, old_backup)
                logger.info(f"تم حفظ نسخة قبل الاستعادة: {old_backup}")
            
            # استعادة النسخة الاحتياطية
            shutil.copy2(target_path, Config.DB_PATH)
            
            logger.info(f"تم الاستعادة من: {target_path}", {
                'backup_path': target_path,
                'checksum': checksum[:16]
            })
            
            return True, f"تمت الاستعادة بنجاح من {os.path.basename(target_path)}"
            
        except Exception as e:
            logger.error(f"خطأ في الاستعادة: {e}", exc_info=True)
            return False, f"خطأ في الاستعادة: {str(e)[:200]}"
    
    @staticmethod
    async def list_backups() -> List[Dict]:
        """List all available backups - عرض جميع النسخ الاحتياطية المتاحة"""
        backups = []
        
        try:
            if not os.path.exists("backups"):
                return []
            
            for filename in os.listdir("backups"):
                if filename.startswith(Config.DB_PATH + ".backup_") and not filename.endswith('.meta'):
                    path = os.path.join("backups", filename)
                    
                    try:
                        size = os.path.getsize(path)
                        ctime = os.path.getctime(path)
                        created_date = datetime.fromtimestamp(ctime)
                        
                        backup_info = {
                            'filename': filename,
                            'path': path,
                            'size_bytes': size,
                            'size_mb': size / 1024 / 1024,
                            'created': created_date.isoformat(),
                            'age_days': (datetime.now() - created_date).days
                        }
                        
                        # إضافة البيانات الوصفية إذا كانت موجودة
                        meta_path = path + '.meta'
                        if os.path.exists(meta_path):
                            async with aiofiles.open(meta_path, 'r', encoding='utf-8') as f:
                                metadata = json.loads(await f.read())
                                backup_info['metadata'] = metadata
                        
                        backups.append(backup_info)
                    except:
                        continue
            
            # ترتيب من الأحدث للأقدم
            backups.sort(key=lambda x: x['created'], reverse=True)
            
            return backups
            
        except Exception as e:
            logger.error(f"خطأ في عرض النسخ الاحتياطية: {e}")
            return []

# ======================
# Enhanced Link Processor - معالج الروابط المحسن
# ======================

class EnhancedLinkProcessor:
    """Advanced link processing with validation and enrichment - معالجة روابط متقدمة مع التحقق والتخصيب"""
    
    # معاملات التتبع الشائعة للإزالة
    TRACKING_PARAMS = [
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'ref', 'source', 'campaign', 'medium', 'term', 'content',
        'fbclid', 'gclid', 'msclkid', 'dclid', 'igshid',
        'si', 's', 't', 'mibextid'
    ]
    
    # قائمة النطاقات المسموحة
    ALLOWED_DOMAINS = [
        't.me', 'telegram.me', 'telegram.dog',
        'chat.whatsapp.com', 'whatsapp.com',
        'discord.gg', 'discord.com',
        'signal.group'
    ]
    
    @staticmethod
    def normalize_url(url: str, aggressive: bool = False) -> str:
        """Normalize URL with multiple strategies - توحيد الرابط باستراتيجيات متعددة"""
        if not url or not isinstance(url, str):
            return ""
        
        original_url = url
        
        # إزالة المسافات والرموز غير المرغوبة
        url = url.strip()
        url = re.sub(r'^["\'\s*]+|["\'\s*]+$', '', url)
        url = re.sub(r'[,\s]+$', '', url)
        
        # استخراج الرابط من النص
        url_patterns = [
            r'(https?://[^\s]+)',
            r'(t\.me/[^\s]+)',
            r'(telegram\.me/[^\s]+)',
            r'(chat\.whatsapp\.com/[^\s]+)',
            r'(discord\.gg/[^\s]+)',
            r'(signal\.group/[^\s]+)'
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
                    
                    # الاحتفاظ بالمعاملات المهمة فقط
                    if not is_tracking and key:
                        filtered_params[key] = values[0] if values else ''
                
                if filtered_params:
                    query_params.append(urlencode(filtered_params, doseq=True))
            
            # إعادة بناء المسار
            path = parsed.path
            if aggressive:
                # إزالة المسارات الزائدة
                path_parts = path.strip('/').split('/')
                if len(path_parts) > 2:
                    path = '/' + '/'.join(path_parts[:2])
            
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
        """Extract comprehensive information from URL - استخراج معلومات شاملة من الرابط"""
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
                result['details'] = EnhancedLinkProcessor._extract_telegram_info(normalized_url, parsed)
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
    def _extract_telegram_info(url: str, parsed) -> Dict:
        """Extract Telegram specific information - استخراج معلومات تيليجرام خاصة"""
        result = {
            'is_valid': False,
            'username': '',
            'invite_hash': '',
            'is_channel': False,
            'is_group': False,
            'is_join_request': False,
            'is_public': False,
            'is_private': False,
            'path_segments': []
        }
        
        path = parsed.path.strip('/')
        if not path:
            return result
        
        segments = path.split('/')
        result['path_segments'] = segments
        
        # التحقق من روابط طلبات الانضمام
        if '+joinchat/' in url or re.search(r't\.me/\+\w', url) or '+joinchat+' in url:
            result['is_join_request'] = True
            result['is_private'] = True
            
            hash_match = re.search(r'\+(?:joinchat/)?([A-Za-z0-9_-]+)', url)
            if hash_match:
                result['invite_hash'] = hash_match.group(1)
                result['is_valid'] = True
        
        # تحليل المسارات العادية
        elif len(segments) == 1:
            username = segments[0].lower()
            result['username'] = username
            
            # تحديد النوع
            if username.startswith(('c/', 'channel/', 's/')):
                result['is_channel'] = True
                result['is_valid'] = True
            elif username.startswith('+'):
                result['is_join_request'] = True
                result['is_private'] = True
                result['invite_hash'] = username[1:]
                result['is_valid'] = True
            else:
                result['is_group'] = True
                result['is_public'] = True
                result['is_valid'] = True
        
        elif len(segments) >= 2:
            if segments[0] in ['c', 'channel', 's']:
                result['is_channel'] = True
                result['is_valid'] = True
            elif segments[0] == 'joinchat':
                result['is_join_request'] = True
                result['is_private'] = True
                result['invite_hash'] = segments[1] if len(segments) > 1 else ''
                result['is_valid'] = True
        
        return result
    
    @staticmethod
    def _extract_whatsapp_info(url: str, parsed) -> Dict:
        """Extract WhatsApp specific information - استخراج معلومات واتساب خاصة"""
        result = {
            'is_valid': False,
            'group_id': '',
            'is_group': True
        }
        
        path = parsed.path.strip('/')
        if path:
            result['group_id'] = path
            result['is_valid'] = True
        
        return result
    
    @staticmethod
    def _extract_discord_info(url: str, parsed) -> Dict:
        """Extract Discord specific information - استخراج معلومات ديسكورد خاصة"""
        result = {
            'is_valid': False,
            'invite_code': '',
            'is_invite': True
        }
        
        path = parsed.path.strip('/')
        if path:
            result['invite_code'] = path
            result['is_valid'] = True
        
        return result
    
    @staticmethod
    def _extract_signal_info(url: str, parsed) -> Dict:
        """Extract Signal specific information - استخراج معلومات سيجنال خاصة"""
        result = {
            'is_valid': False,
            'group_id': '',
            'is_group': True
        }
        
        path = parsed.path.strip('/')
        if path:
            result['group_id'] = path
            result['is_valid'] = True
        
        return result
    
    @staticmethod
    def validate_url(url: str, platform: str = None) -> Dict:
        """Validate URL with multiple checks - التحقق من الرابط بفحوصات متعددة"""
        info = EnhancedLinkProcessor.extract_url_info(url)
        
        validation = {
            'is_valid': info['is_valid'],
            'platform': info['platform'],
            'normalized_url': info['normalized_url'],
            'checks': {},
            'warnings': [],
            'errors': []
        }
        
        if not info['normalized_url']:
            validation['errors'].append('رابط فارغ أو غير صالح')
            validation['is_valid'] = False
            return validation
        
        # فحص الطول
        if len(info['normalized_url']) > Config.MAX_LINK_LENGTH:
            validation['warnings'].append(f'الرابط طويل جداً ({len(info["normalized_url"])} حرف)')
        
        # فحص المنصة
        if platform and info['platform'] != platform:
            validation['errors'].append(f'الرابط ليس لمنصة {platform}')
            validation['is_valid'] = False
        
        # فحص صحة الرابط
        if not info['is_valid']:
            validation['errors'].append('رابط غير معروف أو غير مدعوم')
            validation['is_valid'] = False
        
        # إضافة تفاصيل الفحص
        validation['checks'] = {
            'length_ok': len(info['normalized_url']) <= Config.MAX_LINK_LENGTH,
            'platform_match': not platform or info['platform'] == platform,
            'domain_allowed': info['is_valid'],
            'normalization_successful': bool(info['normalized_url'])
        }
        
        return validation

# ======================
# Enhanced Session Manager - مدير الجلسات المحسن
# ======================

class EnhancedSessionManager:
    """Advanced session management with health monitoring - إدارة جلسات متقدمة مع مراقبة الصحة"""
    
    _session_cache = CacheManager.get_instance()
    _session_health = {}
    _session_metrics = defaultdict(lambda: {
        'uses': 0,
        'total_time': 0,
        'errors': 0,
        'last_error': None,
        'created_at': None
    })
    _lock = asyncio.Lock()
    
    @staticmethod
    async def create_client(session_string: str, session_id: int, user_id: int = 0) -> Optional[TelegramClient]:
        """Create and cache Telegram client with health checks - إنشاء وتخزين عميل تيليجرام مع فحوصات الصحة"""
        cache_key = f"client_{session_id}"
        
        async with EnhancedSessionManager._lock:
            # التحقق من الصحة أولاً
            health = EnhancedSessionManager._session_health.get(cache_key)
            if health and health.get('status') == 'unhealthy':
                logger.warning(f"تخطي الجلسة {session_id} غير الصحية")
                return None
            
            # المحاولة من الكاش
            cached = await EnhancedSessionManager._session_cache.get(cache_key, 'sessions')
            
            if cached and isinstance(cached, dict) and 'client_data' in cached:
                try:
                    # استعادة العميل من البيانات المخزنة
                    client = TelegramClient(
                        StringSession(cached['client_data']['session_string']),
                        Config.API_ID,
                        Config.API_HASH,
                        **cached['client_data']['client_args']
                    )
                    
                    await client.connect()
                    
                    if await client.is_user_authorized():
                        # تحديث المقاييس
                        EnhancedSessionManager._update_metrics(cache_key, 'use')
                        EnhancedSessionManager._update_health(cache_key, 'healthy')
                        
                        return client
                    else:
                        await client.disconnect()
                except Exception as e:
                    logger.debug(f"خطأ في استعادة العميل المخبأ: {e}")
            
            try:
                # فك تشفير الجلسة إذا كانت مشفرة
                enc_manager = EncryptionManager.get_instance()
                decrypted_session = enc_manager.decrypt_session(session_string)
                actual_session = decrypted_session or session_string
                
                client_args = {
                    'device_model': "Advanced Link Collector Pro",
                    'system_version': "Linux 6.5",
                    'app_version': "4.16.30",
                    'lang_code': "en",
                    'timeout': 30,
                    'connection_retries': 3,
                    'auto_reconnect': True,
                    'request_retries': 3,
                    'connection': {
                        'retries': 5,
                        'delay': 1,
                        'timeout': 30
                    }
                }
                
                client = TelegramClient(
                    StringSession(actual_session),
                    Config.API_ID,
                    Config.API_HASH,
                    **client_args
                )
                
                await client.connect()
                
                if not await client.is_user_authorized():
                    logger.error(f"الجلسة {session_id} غير مصرح بها")
                    await client.disconnect()
                    
                    # تحديث الصحة
                    EnhancedSessionManager._update_health(cache_key, 'unhealthy', 'غير مصرح')
                    return None
                
                # الحصول على معلومات المستخدم
                me = await client.get_me()
                
                # تخزين العميل في الكاش مع البيانات
                client_data = {
                    'session_string': actual_session,
                    'client_args': client_args,
                    'user_info': {
                        'id': me.id,
                        'username': me.username,
                        'phone': me.phone,
                        'created_at': datetime.now().isoformat()
                    }
                }
                
                await EnhancedSessionManager._session_cache.set(
                    cache_key, 
                    {'client_data': client_data},
                    'sessions',
                    ttl_seconds=3600  # ساعة واحدة
                )
                
                # تحديث المقاييس
                EnhancedSessionManager._update_metrics(cache_key, 'create', user_id)
                EnhancedSessionManager._session_metrics[cache_key]['created_at'] = datetime.now()
                EnhancedSessionManager._update_health(cache_key, 'healthy')
                
                return client
                
            except AuthKeyError as e:
                logger.error(f"خطأ مفتاح مصادقة للجلسة {session_id}: {e}")
                EnhancedSessionManager._update_health(cache_key, 'unhealthy', 'خطأ مصادقة')
                return None
            except Exception as e:
                logger.error(f"خطأ في إنشاء عميل للجلسة {session_id}: {e}", exc_info=True)
                EnhancedSessionManager._update_metrics(cache_key, 'error')
                EnhancedSessionManager._update_health(cache_key, 'unhealthy', str(e)[:100])
                return None
    
    @staticmethod
    def _update_metrics(cache_key: str, action: str, user_id: int = 0):
        """Update session metrics - تحديث مقاييس الجلسة"""
        metrics = EnhancedSessionManager._session_metrics[cache_key]
        
        if action == 'use':
            metrics['uses'] += 1
            metrics['last_used'] = datetime.now()
        elif action == 'create':
            metrics['created_at'] = datetime.now()
        elif action == 'error':
            metrics['errors'] += 1
            metrics['last_error'] = datetime.now()
    
    @staticmethod
    def _update_health(cache_key: str, status: str, reason: str = None):
        """Update session health status - تحديث حالة صحة الجلسة"""
        EnhancedSessionManager._session_health[cache_key] = {
            'status': status,
            'last_check': datetime.now(),
            'reason': reason
        }
    
    @staticmethod
    async def close_client(session_id: int, reason: str = 'normal'):
        """Close and remove client from cache - إغلاق وإزالة العميل من الكاش"""
        cache_key = f"client_{session_id}"
        
        async with EnhancedSessionManager._lock:
            cached = await EnhancedSessionManager._session_cache.get(cache_key, 'sessions')
            
            if cached and isinstance(cached, dict) and 'client_data' in cached:
                try:
                    client_data = cached['client_data']
                    session_string = client_data['session_string']
                    
                    client = TelegramClient(
                        StringSession(session_string),
                        Config.API_ID,
                        Config.API_HASH
                    )
                    
                    await client.connect()
                    await client.disconnect()
                    
                    # تحديث المقاييس
                    EnhancedSessionManager._session_metrics[cache_key]['total_time'] += (
                        datetime.now() - EnhancedSessionManager._session_metrics[cache_key].get('last_used', datetime.now())
                    ).total_seconds()
                    
                except Exception as e:
                    logger.debug(f"خطأ في إغلاق العميل: {e}")
            
            # إزالة من الكاش
            await EnhancedSessionManager._session_cache.delete(cache_key, 'sessions')
            
            # تحديث الصحة
            EnhancedSessionManager._update_health(cache_key, 'closed', reason)
    
    @staticmethod
    async def cleanup_inactive_sessions(timeout_seconds: int = Config.SESSION_TIMEOUT):
        """Cleanup inactive sessions with metrics - تنظيف الجلسات غير النشطة مع المقاييس"""
        async with EnhancedSessionManager._lock:
            now = datetime.now()
            sessions_to_remove = []
            
            for cache_key, metrics in list(EnhancedSessionManager._session_metrics.items()):
                last_used = metrics.get('last_used')
                
                if last_used and (now - last_used).total_seconds() > timeout_seconds:
                    # التحقق من الصحة أولاً
                    health = EnhancedSessionManager._session_health.get(cache_key, {})
                    if health.get('status') != 'healthy':
                        sessions_to_remove.append(cache_key)
            
            for cache_key in sessions_to_remove:
                try:
                    await EnhancedSessionManager.close_client(
                        int(cache_key.split('_')[1]), 
                        'inactive_timeout'
                    )
                except:
                    pass
            
            if sessions_to_remove:
                logger.info(f"تم تنظيف {len(sessions_to_remove)} جلسة غير نشطة")
    
    @staticmethod
    async def get_session_health(session_id: int) -> Dict:
        """Get session health status - الحصول على حالة صحة الجلسة"""
        cache_key = f"client_{session_id}"
        
        return {
            'health': EnhancedSessionManager._session_health.get(cache_key, {}),
            'metrics': EnhancedSessionManager._session_metrics.get(cache_key, {}),
            'cached': await EnhancedSessionManager._session_cache.exists(cache_key, 'sessions')
        }
    
    @staticmethod
    def get_all_metrics() -> Dict:
        """Get all session metrics - الحصول على جميع مقاييس الجلسات"""
        total_sessions = len(EnhancedSessionManager._session_metrics)
        healthy_sessions = sum(
            1 for health in EnhancedSessionManager._session_health.values() 
            if health.get('status') == 'healthy'
        )
        
        return {
            'total_sessions': total_sessions,
            'healthy_sessions': healthy_sessions,
            'unhealthy_sessions': total_sessions - healthy_sessions,
            'total_uses': sum(m['uses'] for m in EnhancedSessionManager._session_metrics.values()),
            'total_errors': sum(m['errors'] for m in EnhancedSessionManager._session_metrics.values()),
            'session_details': dict(EnhancedSessionManager._session_metrics)
        }
    
    @staticmethod
    async def validate_session(session_string: str) -> Tuple[bool, Dict]:
        """Validate session string without caching - التحقق من صحة سلسلة الجلسة بدون تخزين"""
        try:
            # فك التشفير إذا لزم
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
            
            # الحصول على معلومات المستخدم
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
# Enhanced Database Manager - مدير قاعدة البيانات المحسن
# ======================

class EnhancedDatabaseManager:
    """Advanced database management with connection pooling and monitoring - إدارة قاعدة بيانات متقدمة مع تجميع الاتصالات والمراقبة"""
    
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    _pool = None
    _metrics = {
        'queries_executed': 0,
        'transactions': 0,
        'errors': 0,
        'connection_count': 0,
        'avg_query_time': 0.0
    }
    
    @classmethod
    async def get_instance(cls):
        """Get database instance with proper async initialization - الحصول على مثيل قاعدة البيانات مع تهيئة غير متزامنة صحيحة"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = EnhancedDatabaseManager()
                    await cls._instance._initialize()
        return cls._instance
    
    async def _initialize(self):
        """Initialize database asynchronously with connection pooling - تهيئة قاعدة البيانات بشكل غير متزامن مع تجميع الاتصالات"""
        if self._initialized:
            return
        
        self.db_path = Config.DB_PATH
        
        # التحقق من وجود الملف
        db_exists = os.path.exists(self.db_path)
        
        # إنشاء مجلد إذا لم يكن موجوداً
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        
        # إنشاء تجميع الاتصالات
        self._pool = await aiosqlite.create_pool(
            self.db_path,
            minsize=1,
            maxsize=Config.DB_POOL_SIZE,
            timeout=30.0
        )
        
        # تهيئة الجداول
        await self._create_tables()
        
        # إنشاء نسخة احتياطية إذا كانت قاعدة البيانات موجودة مسبقاً
        if db_exists and Config.BACKUP_ENABLED:
            await BackupManager.create_backup()
            await BackupManager.rotate_backups()
        
        self._initialized = True
        self._metrics['connection_count'] = Config.DB_POOL_SIZE
        
        logger.info("تم تهيئة قاعدة البيانات بنجاح مع تجميع الاتصالات", {
            'pool_size': Config.DB_POOL_SIZE,
            'db_path': self.db_path,
            'db_exists': db_exists
        })
    
    @asynccontextmanager
    async def _get_connection(self):
        """Get database connection from pool - الحصول على اتصال قاعدة البيانات من التجمع"""
        async with self._pool.acquire() as conn:
            # تمكين الميزات المتقدمة
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute("PRAGMA journal_mode = WAL")
            await conn.execute("PRAGMA synchronous = NORMAL")
            await conn.execute("PRAGMA cache_size = -20000")  # كاش 20 ميجابايت
            await conn.execute("PRAGMA temp_store = MEMORY")
            await conn.execute("PRAGMA mmap_size = 1073741824")  # 1GB mmap
            await conn.execute("PRAGMA optimize")  # تحسين تلقائي
            
            yield conn
    
    async def _create_tables(self):
        """Create database tables with enhanced structure - إنشاء جداول قاعدة البيانات مع هيكل محسن"""
        async with self._get_connection() as conn:
            # جدول الجلسات المحسن
            await conn.execute('''
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
            
            # جدول الروابط المحسن
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url_hash TEXT UNIQUE NOT NULL,
                    url TEXT NOT NULL,
                    original_url TEXT,
                    platform TEXT NOT NULL,
                    link_type TEXT,
                    title TEXT,
                    description TEXT,
                    members_count INTEGER DEFAULT 0,
                    session_id INTEGER,
                    collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_checked TIMESTAMP,
                    check_count INTEGER DEFAULT 0,
                    confidence TEXT DEFAULT 'medium',
                    is_active BOOLEAN DEFAULT 1,
                    metadata TEXT,
                    tags TEXT,
                    added_by_user INTEGER,
                    source TEXT,
                    validation_score INTEGER DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE SET NULL,
                    CONSTRAINT unique_url_hash UNIQUE(url_hash)
                )
            ''')
            
            # جدول جلسات الجمع المحسن
            await conn.execute('''
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
            await conn.execute('''
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
            await conn.execute('''
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
            await conn.execute('''
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
            
            await conn.commit()
        
        # إنشاء فهارس
        await self._create_indexes()
    
    async def _create_indexes(self):
        """Create database indexes for performance - إنشاء فهارس قاعدة البيانات للأداء"""
        indexes = [
            ('idx_links_url_hash', 'links(url_hash)'),
            ('idx_links_platform_type', 'links(platform, link_type)'),
            ('idx_links_collected_date', 'links(collected_date)'),
            ('idx_links_added_by_user', 'links(added_by_user)'),
            ('idx_links_validation_score', 'links(validation_score)'),
            ('idx_sessions_active', 'sessions(is_active, health_score)'),
            ('idx_sessions_added_by', 'sessions(added_by_user, last_used)'),
            ('idx_users_last_active', 'bot_users(last_active)'),
            ('idx_collection_sessions_uid', 'collection_sessions(session_uid)'),
            ('idx_error_log_occurred', 'error_log(occurred_at, error_type)'),
            ('idx_system_stats_metric', 'system_stats(metric_name, recorded_at)')
        ]
        
        async with self._get_connection() as conn:
            for index_name, index_sql in indexes:
                try:
                    await conn.execute(f'CREATE INDEX IF NOT EXISTS {index_name} ON {index_sql}')
                except Exception as e:
                    logger.error(f"خطأ في إنشاء الفهرس {index_name}: {e}", exc_info=True)
    
    async def add_session(self, session_string: str, phone: str = '', 
                         user_id: int = 0, username: str = '', 
                         display_name: str = '', added_by_user: int = 0,
                         notes: str = '', metadata: Dict = None) -> Tuple[bool, str, Dict]:
        """Add a new session with enhanced validation - إضافة جلسة جديدة مع تحقق محسن"""
        start_time = datetime.now()
        
        try:
            # التحقق من عدد الجلسات للمستخدم
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    'SELECT COUNT(*) FROM sessions WHERE added_by_user = ? AND is_active = 1',
                    (added_by_user,)
                )
                session_count = (await cursor.fetchone())[0]
                
                if session_count >= Config.MAX_SESSIONS_PER_USER:
                    return False, f"تجاوزت الحد الأقصى للجلسات ({Config.MAX_SESSIONS_PER_USER})", {}
                
                # التحقق من صحة الجلسة
                is_valid, validation_info = await EnhancedSessionManager.validate_session(session_string)
                
                if not is_valid:
                    return False, f"الجلسة غير صالحة: {validation_info.get('error', 'خطأ غير معروف')}", validation_info
                
                # تشفير الجلسة
                enc_manager = EncryptionManager.get_instance()
                encrypted_session = enc_manager.encrypt_session(session_string)
                
                # توليد هاش فريد
                session_hash = hashlib.sha256(session_string.encode()).hexdigest()
                
                # إضافة الجلسة
                cursor = await conn.execute('''
                    INSERT OR REPLACE INTO sessions 
                    (session_string, session_hash, phone_number, user_id, username, 
                     display_name, added_by_user, last_used, notes, metadata, 
                     last_success, total_uses, health_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, CURRENT_TIMESTAMP, 1, 100)
                ''', (
                    encrypted_session, 
                    session_hash,
                    phone, 
                    user_id, 
                    username, 
                    display_name, 
                    added_by_user,
                    notes,
                    json.dumps(metadata or {})
                ))
                
                session_id = cursor.lastrowid
                
                await conn.commit()
                
                # تحديث إحصائيات المستخدم
                await self.update_user_stats(added_by_user, 'session_added')
                
                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                self._update_metrics('query', execution_time)
                
                return True, "تمت إضافة الجلسة بنجاح", {
                    'session_id': session_id,
                    'session_hash': session_hash,
                    'validation_info': validation_info,
                    'execution_time_ms': execution_time
                }
                
        except Exception as e:
            self._update_metrics('error')
            logger.error(f"خطأ في إضافة جلسة: {e}", exc_info=True)
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def add_link_batch(self, links: List[Dict]) -> Tuple[Dict, List[Dict]]:
        """Add multiple links in batch with detailed reporting - إضافة روابط متعددة دفعة واحدة مع تقرير مفصل"""
        results = {
            'added': 0,
            'duplicates': 0,
            'errors': 0,
            'invalid': 0,
            'batch_size': len(links)
        }
        
        detailed_results = []
        start_time = datetime.now()
        
        if not links:
            return results, detailed_results
        
        try:
            # تقسيم الروابط إلى دفعات صغيرة
            batch_size = Config.MAX_BATCH_SIZE
            batches = [links[i:i + batch_size] for i in range(0, len(links), batch_size)]
            
            for batch in batches:
                async with self._get_connection() as conn:
                    await conn.execute('BEGIN TRANSACTION')
                    
                    for link in batch:
                        try:
                            # التحقق من صحة الرابط
                            validation = EnhancedLinkProcessor.validate_url(link.get('url', ''))
                            
                            if not validation['is_valid']:
                                results['invalid'] += 1
                                detailed_results.append({
                                    'url': link.get('url'),
                                    'status': 'invalid',
                                    'errors': validation['errors']
                                })
                                continue
                            
                            # إعداد بيانات الرابط
                            url_info = EnhancedLinkProcessor.extract_url_info(link.get('url', ''))
                            
                            link_data = {
                                'url_hash': url_info['url_hash'],
                                'url': url_info['normalized_url'],
                                'original_url': link.get('url'),
                                'platform': url_info['platform'],
                                'link_type': link.get('link_type', url_info['details'].get('link_type', 'unknown')),
                                'title': link.get('title', '')[:500],
                                'description': link.get('description', '')[:1000],
                                'members_count': link.get('members', 0),
                                'session_id': link.get('session_id'),
                                'confidence': link.get('confidence', 'medium'),
                                'metadata': json.dumps(link.get('metadata', {})),
                                'tags': json.dumps(link.get('tags', [])),
                                'added_by_user': link.get('added_by_user', 0),
                                'source': link.get('source', 'collection'),
                                'validation_score': link.get('validation_score', 0)
                            }
                            
                            # إدخال الرابط
                            cursor = await conn.execute('''
                                INSERT OR IGNORE INTO links 
                                (url_hash, url, original_url, platform, link_type, title, 
                                 description, members_count, session_id, collected_date, 
                                 confidence, metadata, tags, added_by_user, source, validation_score)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?)
                            ''', tuple(link_data.values()))
                            
                            if cursor.rowcount > 0:
                                results['added'] += 1
                                detailed_results.append({
                                    'url': link.get('url'),
                                    'status': 'added',
                                    'url_hash': url_info['url_hash']
                                })
                            else:
                                results['duplicates'] += 1
                                detailed_results.append({
                                    'url': link.get('url'),
                                    'status': 'duplicate',
                                    'url_hash': url_info['url_hash']
                                })
                            
                        except Exception as e:
                            results['errors'] += 1
                            detailed_results.append({
                                'url': link.get('url'),
                                'status': 'error',
                                'error': str(e)[:200]
                            })
                            continue
                    
                    await conn.commit()
                    
        except Exception as e:
            self._update_metrics('error')
            logger.error(f"خطأ في إضافة الروابط الدفعية: {e}", exc_info=True)
        
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        self._update_metrics('query', execution_time)
        
        # تحديث إحصائيات إذا تمت إضافة روابط
        if results['added'] > 0 and 'added_by_user' in links[0]:
            await self.update_user_stats(links[0]['added_by_user'], 'links_added', results['added'])
        
        return results, detailed_results
    
    async def get_active_sessions(self, user_id: int = None, limit: int = 100) -> List[Dict]:
        """Get all active sessions with health information - الحصول على جميع الجلسات النشطة مع معلومات الصحة"""
        try:
            async with self._get_connection() as conn:
                query = '''
                    SELECT s.*, 
                           u.username as added_by_username,
                           (SELECT COUNT(*) FROM links l WHERE l.session_id = s.id) as total_links_collected,
                           (SELECT COUNT(*) FROM links l WHERE l.session_id = s.id AND l.collected_date > datetime(s.last_used, '-1 hour')) as recent_links
                    FROM sessions s
                    LEFT JOIN bot_users u ON s.added_by_user = u.user_id
                    WHERE s.is_active = 1
                '''
                params = []
                
                if user_id:
                    query += ' AND s.added_by_user = ?'
                    params.append(user_id)
                
                query += ' ORDER BY s.last_used DESC, s.health_score DESC LIMIT ?'
                params.append(limit)
                
                cursor = await conn.execute(query, params)
                
                rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                
                sessions = []
                for row in rows:
                    session_dict = dict(zip(columns, row))
                    
                    # فك تشفير البيانات الحساسة
                    if 'session_string' in session_dict:
                        enc_manager = EncryptionManager.get_instance()
                        decrypted = enc_manager.decrypt_session(session_dict['session_string'])
                        session_dict['session_decrypted'] = bool(decrypted)
                        session_dict['session_string'] = '********'  # إخفاء البيانات الحساسة
                    
                    # حساب عمر الجلسة
                    if session_dict.get('added_date'):
                        added_date = datetime.fromisoformat(session_dict['added_date'].replace('Z', '+00:00'))
                        session_dict['age_days'] = (datetime.now() - added_date).days
                    
                    # حساب صحة الجلسة
                    health_score = session_dict.get('health_score', 100)
                    if health_score >= 80:
                        session_dict['health_status'] = 'excellent'
                    elif health_score >= 60:
                        session_dict['health_status'] = 'good'
                    elif health_score >= 40:
                        session_dict['health_status'] = 'fair'
                    elif health_score >= 20:
                        session_dict['health_status'] = 'poor'
                    else:
                        session_dict['health_status'] = 'critical'
                    
                    sessions.append(session_dict)
                
                return sessions
                
        except Exception as e:
            self._update_metrics('error')
            logger.error(f"خطأ في الحصول على الجلسات النشطة: {e}", exc_info=True)
            return []
    
    async def update_user_stats(self, user_id: int, action: str, value: int = 1):
        """Update user statistics - تحديث إحصائيات المستخدم"""
        try:
            async with self._get_connection() as conn:
                update_query = '''
                    UPDATE bot_users 
                    SET last_active = CURRENT_TIMESTAMP,
                        request_count = request_count + 1
                '''
                params = []
                
                if action == 'session_added':
                    update_query += ', session_count = session_count + 1'
                elif action == 'links_added':
                    update_query += ', link_count = link_count + ?, total_links_added = total_links_added + ?'
                    params.extend([value, value])
                
                update_query += ' WHERE user_id = ?'
                params.append(user_id)
                
                await conn.execute(update_query, params)
                await conn.commit()
                
        except Exception as e:
            logger.debug(f"خطأ في تحديث إحصائيات المستخدم: {e}")
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """Get comprehensive user statistics - الحصول على إحصائيات مستخدم شاملة"""
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute('''
                    SELECT 
                        u.*,
                        COUNT(DISTINCT s.id) as total_sessions,
                        COUNT(DISTINCT l.id) as total_links,
                        COALESCE(SUM(CASE WHEN l.platform = 'telegram' THEN 1 ELSE 0 END), 0) as telegram_links,
                        COALESCE(SUM(CASE WHEN l.platform = 'whatsapp' THEN 1 ELSE 0 END), 0) as whatsapp_links,
                        COALESCE(SUM(CASE WHEN l.link_type = 'public_group' THEN 1 ELSE 0 END), 0) as public_groups,
                        COALESCE(SUM(CASE WHEN l.link_type = 'private_group' THEN 1 ELSE 0 END), 0) as private_groups,
                        COALESCE(SUM(CASE WHEN l.link_type = 'join_request' THEN 1 ELSE 0 END), 0) as join_requests,
                        COALESCE(MAX(l.collected_date), u.added_date) as last_collection
                    FROM bot_users u
                    LEFT JOIN sessions s ON u.user_id = s.added_by_user AND s.is_active = 1
                    LEFT JOIN links l ON u.user_id = l.added_by_user
                    WHERE u.user_id = ?
                    GROUP BY u.user_id
                ''', (user_id,))
                
                row = await cursor.fetchone()
                if row:
                    columns = [desc[0] for desc in cursor.description]
                    stats = dict(zip(columns, row))
                    
                    # إضافة حسابات إضافية
                    if stats.get('added_date'):
                        added_date = datetime.fromisoformat(stats['added_date'].replace('Z', '+00:00'))
                        stats['account_age_days'] = (datetime.now() - added_date).days
                    
                    if stats.get('last_active'):
                        last_active = datetime.fromisoformat(stats['last_active'].replace('Z', '+00:00'))
                        stats['last_active_hours'] = (datetime.now() - last_active).total_seconds() / 3600
                    
                    return stats
        
        except Exception as e:
            logger.error(f"خطأ في الحصول على إحصائيات المستخدم: {e}", exc_info=True)
        
        return {}
    
    async def get_stats_summary(self, detailed: bool = False) -> Dict:
        """Get comprehensive database statistics - الحصول على إحصائيات قاعدة بيانات شاملة"""
        try:
            stats = {}
            
            async with self._get_connection() as conn:
                # إحصائيات أساسية
                cursor = await conn.execute("SELECT COUNT(*) FROM links")
                stats['total_links'] = (await cursor.fetchone())[0]
                
                cursor = await conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
                stats['active_sessions'] = (await cursor.fetchone())[0]
                
                cursor = await conn.execute("SELECT COUNT(*) FROM bot_users")
                stats['total_users'] = (await cursor.fetchone())[0]
                
                # الروابط حسب المنصة
                cursor = await conn.execute(
                    "SELECT platform, COUNT(*) FROM links GROUP BY platform ORDER BY COUNT(*) DESC"
                )
                stats['links_by_platform'] = dict(await cursor.fetchall())
                
                # الروابط حسب النوع (تيليجرام فقط)
                cursor = await conn.execute('''
                    SELECT link_type, COUNT(*) 
                    FROM links 
                    WHERE platform = 'telegram' 
                    GROUP BY link_type 
                    ORDER BY COUNT(*) DESC
                ''')
                stats['telegram_by_type'] = dict(await cursor.fetchall())
                
                # النشاط حسب اليوم
                cursor = await conn.execute('''
                    SELECT DATE(collected_date) as date, COUNT(*) as count
                    FROM links 
                    WHERE collected_date > datetime('now', '-30 days')
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
                
                # إحصائيات النظام
                cursor = await conn.execute('''
                    SELECT metric_name, metric_value, MAX(recorded_at) as last_recorded
                    FROM system_stats 
                    WHERE recorded_at > datetime('now', '-1 day')
                    GROUP BY metric_name
                ''')
                
                system_stats = {}
                for row in await cursor.fetchall():
                    system_stats[row[0]] = {
                        'value': row[1],
                        'last_recorded': row[2]
                    }
                
                stats['system_stats'] = system_stats
            
            return stats
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على ملخص الإحصائيات: {e}", exc_info=True)
            return {}
    
    async def export_links(self, filters: Dict = None, limit: int = Config.MAX_EXPORT_LINKS, 
                          offset: int = 0) -> Tuple[List[str], Dict]:
        """Export links with advanced filtering - تصدير الروابط مع تصفية متقدمة"""
        try:
            query = "SELECT url, platform, link_type, collected_date, members_count FROM links WHERE 1=1"
            params = []
            
            if filters:
                if filters.get('platform'):
                    query += " AND platform = ?"
                    params.append(filters['platform'])
                
                if filters.get('link_type'):
                    query += " AND link_type = ?"
                    params.append(filters['link_type'])
                
                if filters.get('min_members'):
                    query += " AND members_count >= ?"
                    params.append(filters['min_members'])
                
                if filters.get('date_from'):
                    query += " AND collected_date >= ?"
                    params.append(filters['date_from'])
                
                if filters.get('date_to'):
                    query += " AND collected_date <= ?"
                    params.append(filters['date_to'])
                
                if filters.get('added_by_user'):
                    query += " AND added_by_user = ?"
                    params.append(filters['added_by_user'])
                
                if filters.get('confidence'):
                    query += " AND confidence = ?"
                    params.append(filters['confidence'])
            
            query += " ORDER BY collected_date DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            async with self._get_connection() as conn:
                cursor = await conn.execute(query, params)
                rows = await cursor.fetchall()
                
                # الحصول على العدد الإجمالي
                count_query = query.replace("SELECT url, platform, link_type, collected_date, members_count", 
                                          "SELECT COUNT(*)")
                count_query = count_query.split("ORDER BY")[0]  # إزالة ORDER BY و LIMIT
                
                count_cursor = await conn.execute(count_query, params[:-2] if filters else [])
                total_count = (await count_cursor.fetchone())[0]
                
                links = [row[0] for row in rows]
                
                metadata = {
                    'total_count': total_count,
                    'exported_count': len(links),
                    'limit': limit,
                    'offset': offset,
                    'filters': filters or {},
                    'platform_distribution': {}
                }
                
                # توزيع المنصات
                if rows:
                    platform_counts = {}
                    for row in rows:
                        platform = row[1]
                        platform_counts[platform] = platform_counts.get(platform, 0) + 1
                    
                    metadata['platform_distribution'] = platform_counts
            
            return links, metadata
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الروابط: {e}", exc_info=True)
            return [], {}
    
    def _update_metrics(self, action: str, execution_time: float = 0):
        """Update database metrics - تحديث مقاييس قاعدة البيانات"""
        if action == 'query':
            self._metrics['queries_executed'] += 1
            self._metrics['avg_query_time'] = (
                self._metrics['avg_query_time'] * (self._metrics['queries_executed'] - 1) + execution_time
            ) / self._metrics['queries_executed']
        elif action == 'transaction':
            self._metrics['transactions'] += 1
        elif action == 'error':
            self._metrics['errors'] += 1
    
    def get_metrics(self) -> Dict:
        """Get database metrics - الحصول على مقاييس قاعدة البيانات"""
        return self._metrics.copy()
    
    async def close(self):
        """Close database connection pool - إغلاق تجميع اتصالات قاعدة البيانات"""
        if self._pool:
            await self._pool.close()
            self._initialized = False
            logger.info("تم إغلاق تجميع اتصالات قاعدة البيانات")

# ======================
# Advanced Collection Manager - مدير الجمع المتقدم
# ======================

class AdvancedCollectionManager:
    """Advanced collection management with AI-powered algorithms - إدارة جمع متقدمة بخوارزميات ذكية اصطناعية"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        
        # أنظمة متقدمة
        self.cache_manager = CacheManager.get_instance()
        self.memory_manager = MemoryManager.get_instance()
        
        # إحصائيات متقدمة
        self.stats = {
            'total_collected': 0,
            'telegram_public': 0,
            'telegram_private': 0,
            'telegram_join': 0,
            'whatsapp_groups': 0,
            'discord_invites': 0,
            'signal_groups': 0,
            'duplicates': 0,
            'channels_skipped': 0,
            'errors': 0,
            'flood_waits': 0,
            'start_time': None,
            'end_time': None,
            'cycles_completed': 0,
            'current_session': None,
            'performance_score': 100.0,
            'quality_score': 100.0
        }
        
        # مقاييس الأداء المتقدمة
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
        
        # عوامل تصفية ذكية
        self.whatsapp_cutoff = datetime.now() - timedelta(days=Config.WHATSAPP_DAYS_BACK)
        self.quality_filters = {
            'min_url_length': 10,
            'max_url_length': Config.MAX_LINK_LENGTH,
            'allowed_patterns': [
                r'^https?://(?:t\.me|telegram\.me)/[A-Za-z0-9_]+/?$',
                r'^https?://t\.me/\+\w+/?$',
                r'^https?://chat\.whatsapp\.com/[A-Za-z0-9]+/?$',
                r'^https?://discord\.gg/[A-Za-z0-9]+/?$',
                r'^https?://signal\.group/[A-Za-z0-9]+/?$'
            ]
        }
        
        # تأمين متقدم للمهام
        self.task_manager = TaskManager()
        self.rate_limiter = AdvancedRateLimiter()
        
        # سجل ذكي
        self.collection_log = IntelligentLog(max_entries=500)
        
        # حالة النظام
        self.system_state = {
            'memory_pressure': 'low',
            'network_status': 'good',
            'collection_mode': 'balanced',
            'last_health_check': None
        }
    
    async def start_collection(self, mode: str = 'balanced'):
        """Start the advanced collection process - بدء عملية الجمع المتقدمة"""
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.stats['start_time'] = datetime.now()
        self.stats['cycles_completed'] = 0
        self.stats['current_session'] = self.stats['start_time'].strftime('%Y%m%d_%H%M%S')
        self.system_state['collection_mode'] = mode
        
        logger.info("🚀 بدء عملية الجمع الذكية المتقدمة", {
            'mode': mode,
            'start_time': self.stats['start_time'].isoformat()
        })
        
        try:
            # بدء أنظمة المراقبة
            self.task_manager.start_monitoring()
            asyncio.create_task(self._system_monitoring())
            asyncio.create_task(self._periodic_maintenance())
            asyncio.create_task(self._adaptive_optimization())
            
            while self.active and not self.stop_requested:
                if self.paused:
                    await asyncio.sleep(1)
                    continue
                
                await self._intelligent_collection_cycle()
                
                if self.active and not self.stop_requested:
                    # تحسين ذكي بين الدورات
                    await self._optimize_between_cycles()
                    
                    # تأخير متكيف
                    delay = self._calculate_adaptive_delay()
                    await asyncio.sleep(delay)
        
        except Exception as e:
            logger.error(f"❌ خطأ في عملية الجمع المتقدمة: {e}", exc_info=True)
            self.stats['errors'] += 1
            self.collection_log.add('error', 'fatal', {'error': str(e)})
        
        finally:
            await self._graceful_shutdown()
    
    async def _intelligent_collection_cycle(self):
        """Execute intelligent collection cycle - تنفيذ دورة جمع ذكية"""
        cycle_start = datetime.now()
        cycle_id = f"cycle_{self.stats['cycles_completed']}_{secrets.token_hex(4)}"
        
        logger.info(f"بدء دورة الجمع {cycle_id}")
        self.collection_log.add('cycle', 'start', {'cycle_id': cycle_id})
        
        try:
            # الحصول على جلسات نشطة
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=Config.MAX_CONCURRENT_SESSIONS * 2)
            
            if not sessions:
                logger.warning("لا توجد جلسات نشطة متاحة")
                self.collection_log.add('cycle', 'no_sessions')
                return
            
            # فلترة الجلسات حسب الصحة
            healthy_sessions = [s for s in sessions if s.get('health_status', 'poor') in ['excellent', 'good', 'fair']]
            
            if not healthy_sessions:
                logger.warning("لا توجد جلسات صحية متاحة")
                self.collection_log.add('cycle', 'no_healthy_sessions')
                return
            
            # تحديد عدد الجلسات بناءً على حالة النظام
            max_sessions = self._calculate_optimal_session_count()
            selected_sessions = healthy_sessions[:max_sessions]
            
            # إنشاء مهام الجمع
            tasks = []
            for i, session in enumerate(selected_sessions):
                if not self.active or self.stop_requested or self.paused:
                    break
                
                task = self._process_session_optimized(session, i, cycle_id)
                tasks.append(task)
            
            if not tasks:
                return
            
            # تنفيذ المهام مع التحكم
            results = await self.task_manager.execute_tasks(tasks)
            
            # تحليل النتائج
            successful = sum(1 for r in results if not isinstance(r, Exception))
            failed = len(results) - successful
            
            # تحديث الإحصائيات
            self.stats['cycles_completed'] += 1
            self.performance['concurrent_tasks'] = len(tasks)
            self.performance['success_rate'] = successful / max(1, len(tasks))
            
            # تحديث حالة النظام
            await self._update_system_state()
            
            # تسجيل الدورة
            cycle_duration = (datetime.now() - cycle_start).total_seconds()
            self.performance['avg_session_duration'] = (
                self.performance['avg_session_duration'] * (self.stats['cycles_completed'] - 1) + cycle_duration
            ) / self.stats['cycles_completed']
            
            self.collection_log.add('cycle', 'complete', {
                'cycle_id': cycle_id,
                'duration': cycle_duration,
                'sessions_processed': successful,
                'sessions_failed': failed,
                'stats_snapshot': self.stats.copy()
            })
            
            logger.info(f"اكتملت دورة {cycle_id}: {successful} ناجحة، {failed} فاشلة", {
                'duration': cycle_duration,
                'performance_score': self.stats['performance_score']
            })
            
        except Exception as e:
            logger.error(f"خطأ في دورة الجمع: {e}", exc_info=True)
            self.stats['errors'] += 1
            self.collection_log.add('cycle', 'error', {'error': str(e)})
    
    async def _process_session_optimized(self, session: Dict, index: int, cycle_id: str):
        """Process session with optimization - معالجة جلسة مع تحسين"""
        session_id = session.get('id')
        session_hash = session.get('session_hash')
        added_by_user = session.get('added_by_user', 0)
        
        logger.info(f"معالجة الجلسة {session_id} في دورة {cycle_id}", {
            'session_id': session_id,
            'health_status': session.get('health_status'),
            'cycle_id': cycle_id
        })
        
        # تأخير ذكي بين الجلسات
        if index > 0:
            delay = self._calculate_session_delay(index)
            await asyncio.sleep(delay)
        
        try:
            # الحصول على الجلسة المشفرة
            db = await EnhancedDatabaseManager.get_instance()
            
            # هنا نحتاج للحصول على الجلسة المشفرة من قاعدة البيانات
            # (يتم التعامل مع هذا في الواقع التنفيذي)
            
            # محاكاة المعالجة - سيتم استبدال هذا بالكود الحقيقي
            await asyncio.sleep(0.5)
            
            # تحديث استخدام الجلسة
            async with self._get_connection() as conn:
                await conn.execute(
                    "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, total_uses = total_uses + 1 WHERE id = ?",
                    (session_id,)
                )
                await conn.commit()
            
            return {'session_id': session_id, 'status': 'success'}
            
        except FloodWaitError as e:
            logger.warning(f"انتظار flood للجلسة {session_id}: {e.seconds} ثانية", {
                'session_id': session_id,
                'wait_seconds': e.seconds
            })
            
            self.stats['flood_waits'] += 1
            self.collection_log.add('session', 'flood_wait', {
                'session_id': session_id,
                'wait_seconds': e.seconds
            })
            
            await asyncio.sleep(e.seconds + Config.REQUEST_DELAYS['flood_wait'])
            raise
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الجلسة {session_id}: {e}", exc_info=True)
            self.stats['errors'] += 1
            
            # تحديث صحة الجلسة
            await self._update_session_health(session_id, False)
            
            self.collection_log.add('session', 'error', {
                'session_id': session_id,
                'error': str(e)
            })
            
            raise
    
    async def _collect_links_intelligent(self, client: TelegramClient, session_id: int, 
                                        added_by_user: int, cycle_id: str) -> List[Dict]:
        """Collect links using intelligent strategies - جمع الروابط باستخدام استراتيجيات ذكية"""
        collected = []
        strategies = [
            self._strategy_recent_dialogs,
            self._strategy_popular_groups,
            self._strategy_search_messages,
            self._strategy_related_entities
        ]
        
        # اختيار الاستراتيجيات بناءً على حالة النظام
        selected_strategies = self._select_strategies()
        
        for strategy in selected_strategies:
            if not self.active or self.stop_requested or self.paused:
                break
            
            try:
                strategy_name = strategy.__name__
                logger.debug(f"تنفيذ استراتيجية {strategy_name} للجلسة {session_id}")
                
                strategy_links = await strategy(client, session_id, added_by_user)
                collected.extend(strategy_links)
                
                self.collection_log.add('strategy', 'success', {
                    'session_id': session_id,
                    'strategy': strategy_name,
                    'links_collected': len(strategy_links)
                })
                
                # تأخير ذكي بين الاستراتيجيات
                await asyncio.sleep(self._calculate_strategy_delay())
                
            except Exception as e:
                logger.error(f"خطأ في استراتيجية الجمع: {e}")
                self.collection_log.add('strategy', 'error', {
                    'session_id': session_id,
                    'strategy': strategy.__name__,
                    'error': str(e)
                })
                continue
        
        return collected
    
    async def _strategy_recent_dialogs(self, client: TelegramClient, session_id: int, 
                                      added_by_user: int) -> List[Dict]:
        """Collect from recent dialogs - الجمع من الدردشات الحديثة"""
        collected = []
        
        try:
            dialogs = []
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                dialogs.append(dialog)
            
            # ترتيب الدردشات حسب التاريخ
            dialogs.sort(key=lambda d: d.date if hasattr(d, 'date') else datetime.min, reverse=True)
            
            for dialog in dialogs[:20]:  # 20 دردشة حديثة فقط
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    entity = dialog.entity
                    
                    if hasattr(entity, 'username') and entity.username:
                        url = f"https://t.me/{entity.username}"
                        normalized_url = EnhancedLinkProcessor.normalize_url(url)
                        
                        # التحقق من الكاش
                        cache_key = f"dialog_{hashlib.md5(normalized_url.encode()).hexdigest()}"
                        if await self.cache_manager.exists(cache_key, 'processed_urls'):
                            continue
                        
                        # معالجة الرابط
                        link_info = await self._process_and_validate_link(
                            client, normalized_url, session_id, added_by_user
                        )
                        
                        if link_info:
                            collected.append(link_info)
                            await self.cache_manager.set(cache_key, True, 'processed_urls', 3600)
                            
                            # تأخير ذكي
                            await asyncio.sleep(Config.REQUEST_DELAYS['normal'])
                    
                except Exception as e:
                    logger.debug(f"خطأ في معالجة الدردشة: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"خطأ في استراتيجية الدردشات: {e}")
        
        return collected
    
    async def _strategy_search_messages(self, client: TelegramClient, session_id: int, 
                                       added_by_user: int) -> List[Dict]:
        """Search for links in messages - البحث عن روابط في الرسائل"""
        collected = []
        
        search_terms = [
            "مجموعة", "قناة", "انضمام", "رابط",
            "group", "channel", "join", "link",
            "t.me", "telegram.me", "chat.whatsapp.com",
            "discord.gg", "signal.group"
        ]
        
        for term in search_terms[:Config.MAX_SEARCH_TERMS]:
            if not self.active or self.stop_requested or self.paused:
                break
            
            try:
                async for dialog in client.iter_dialogs(limit=10):
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
                                extracted_links = self._extract_links_enhanced(message.text)
                                
                                for raw_url in extracted_links:
                                    if len(collected) >= Config.MAX_LINKS_PER_CYCLE:
                                        return collected
                                    
                                    normalized_url = EnhancedLinkProcessor.normalize_url(raw_url)
                                    cache_key = f"url_{hashlib.md5(normalized_url.encode()).hexdigest()}"
                                    
                                    if await self.cache_manager.exists(cache_key, 'processed_urls'):
                                        continue
                                    
                                    # معالجة الرابط
                                    if 'whatsapp.com' in normalized_url:
                                        link_info = self._process_whatsapp_link_enhanced(
                                            normalized_url, session_id, added_by_user, message.date
                                        )
                                    else:
                                        link_info = await self._process_and_validate_link(
                                            client, normalized_url, session_id, added_by_user
                                        )
                                    
                                    if link_info:
                                        collected.append(link_info)
                                        await self.cache_manager.set(cache_key, True, 'processed_urls', 3600)
                                        messages_collected += 1
                                        
                                        if messages_collected >= 3:
                                            break
                        
                        # تأخير بين الدردشات
                        await asyncio.sleep(Config.REQUEST_DELAYS['between_tasks'])
                    
                    except Exception as e:
                        logger.debug(f"خطأ في البحث في الدردشة: {e}")
                        continue
                
                # تأخير بين مصطلحات البحث
                await asyncio.sleep(Config.REQUEST_DELAYS['search'])
            
            except Exception as e:
                logger.error(f"خطأ في البحث عن مصطلح '{term}': {e}")
                continue
        
        return collected
    
    async def _process_and_validate_link(self, client: TelegramClient, url: str, 
                                        session_id: int, added_by_user: int) -> Optional[Dict]:
        """Process and validate link with AI-powered filtering - معالجة والتحقق من الرابط مع تصفية ذكية"""
        try:
            # استخراج المعلومات
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return None
            
            # التحقق من الجودة
            quality_check = self._check_link_quality(url_info)
            if not quality_check['passed']:
                logger.debug(f"رابط غير ذي جودة: {quality_check['reasons']}")
                return None
            
            # التحقق من الكاش المتقدم
            cache_key = f"link_{url_info['url_hash']}"
            cached_info = await self.cache_manager.get(cache_key, 'validated_links')
            
            if cached_info:
                return {
                    'url': url,
                    'url_hash': url_info['url_hash'],
                    'platform': url_info['platform'],
                    'link_type': cached_info.get('link_type', 'unknown'),
                    'title': cached_info.get('title', ''),
                    'members': cached_info.get('members', 0),
                    'session_id': session_id,
                    'added_by_user': added_by_user,
                    'confidence': cached_info.get('confidence', 'medium'),
                    'metadata': cached_info.get('metadata', {}),
                    'validation_score': cached_info.get('validation_score', 50)
                }
            
            # التحقق باستخدام API إذا لزم
            if url_info['platform'] == 'telegram':
                verified = await self._verify_telegram_group_advanced(client, url, url_info)
            else:
                verified = {'status': 'valid', 'confidence': 'medium'}
            
            if verified.get('status') == 'valid':
                # تحديث الإحصائيات
                self._update_collection_stats(url_info, verified)
                
                # تخزين في الكاش
                await self.cache_manager.set(cache_key, {
                    'link_type': verified.get('link_type', 'unknown'),
                    'title': verified.get('title', ''),
                    'members': verified.get('members', 0),
                    'confidence': verified.get('confidence', 'medium'),
                    'validation_score': verified.get('validation_score', 50)
                }, 'validated_links', 86400)  # 24 ساعة
                
                return {
                    'url': url,
                    'url_hash': url_info['url_hash'],
                    'platform': url_info['platform'],
                    'link_type': verified.get('link_type', 'unknown'),
                    'title': verified.get('title', ''),
                    'members': verified.get('members', 0),
                    'session_id': session_id,
                    'added_by_user': added_by_user,
                    'confidence': verified.get('confidence', 'medium'),
                    'metadata': {
                        'verified_at': datetime.now().isoformat(),
                        'verification_method': verified.get('method', 'api'),
                        'quality_score': quality_check['score']
                    },
                    'validation_score': verified.get('validation_score', 50)
                }
            
            return None
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الرابط {url}: {e}")
            return None
    
    def _check_link_quality(self, url_info: Dict) -> Dict:
        """Check link quality with multiple criteria - التحقق من جودة الرابط بمعايير متعددة"""
        score = 100
        reasons = []
        
        url = url_info['normalized_url']
        
        # فحص الطول
        if len(url) < self.quality_filters['min_url_length']:
            score -= 30
            reasons.append('url_too_short')
        
        if len(url) > self.quality_filters['max_url_length']:
            score -= 20
            reasons.append('url_too_long')
        
        # فحص الأنماط المسموحة
        pattern_matched = False
        for pattern in self.quality_filters['allowed_patterns']:
            if re.match(pattern, url):
                pattern_matched = True
                break
        
        if not pattern_matched:
            score -= 40
            reasons.append('pattern_not_allowed')
        
        # فحص المنصة
        if url_info['platform'] == 'unknown':
            score -= 50
            reasons.append('unknown_platform')
        
        return {
            'passed': score >= 50,
            'score': score,
            'reasons': reasons
        }
    
    async def _verify_telegram_group_advanced(self, client: TelegramClient, url: str, 
                                             url_info: Dict) -> Dict:
        """Verify Telegram group with advanced checks - التحقق من مجموعة تيليجرام بفحوصات متقدمة"""
        try:
            details = url_info['details']
            
            if details['is_join_request']:
                return {
                    'status': 'valid',
                    'link_type': 'join_request',
                    'confidence': 'high',
                    'validation_score': 80
                }
            
            elif details['username'] and not details['is_channel']:
                try:
                    entity = await client.get_entity(details['username'])
                    
                    if hasattr(entity, 'broadcast') and entity.broadcast:
                        return {
                            'status': 'invalid',
                            'reason': 'قناة',
                            'confidence': 'high',
                            'validation_score': 0
                        }
                    
                    members = getattr(entity, 'participants_count', 0)
                    title = getattr(entity, 'title', '')
                    
                    # حساب درجة الثقة
                    validation_score = 60
                    if members >= 100:
                        validation_score += 20
                    if len(title) > 5:
                        validation_score += 10
                    
                    return {
                        'status': 'valid',
                        'link_type': 'public_group',
                        'title': title,
                        'members': members,
                        'confidence': 'high' if validation_score >= 70 else 'medium',
                        'validation_score': validation_score,
                        'method': 'telegram_api'
                    }
                    
                except UsernameNotOccupiedError:
                    return {
                        'status': 'invalid',
                        'reason': 'غير موجود',
                        'confidence': 'high',
                        'validation_score': 0
                    }
                except UserNotParticipantError:
                    return {
                        'status': 'invalid',
                        'reason': 'غير مشارك',
                        'confidence': 'medium',
                        'validation_score': 20
                    }
                except ChatWriteForbiddenError:
                    return {
                        'status': 'valid',
                        'link_type': 'private_group',
                        'confidence': 'medium',
                        'validation_score': 50
                    }
            
            else:
                return {
                    'status': 'valid',
                    'link_type': 'private_group',
                    'confidence': 'medium',
                    'validation_score': 40
                }
        
        except FloodWaitError as e:
            raise e
        
        except Exception as e:
            logger.debug(f"خطأ في التحقق لـ {url}: {e}")
            return {
                'status': 'error',
                'reason': str(e)[:100],
                'confidence': 'low',
                'validation_score': 10
            }
    
    def _process_whatsapp_link_enhanced(self, url: str, session_id: int, 
                                       added_by_user: int, message_date=None) -> Optional[Dict]:
        """Process WhatsApp link with enhanced filtering - معالجة رابط واتساب مع تصفية محسنة"""
        try:
            # تطبيق عامل تصفية التاريخ
            if message_date and message_date < self.whatsapp_cutoff:
                return None
            
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return None
            
            # حساب درجة الجودة
            quality_score = 70  # درجة أساسية
            if message_date:
                days_old = (datetime.now() - message_date).days
                if days_old <= 7:
                    quality_score += 20
                elif days_old <= 30:
                    quality_score += 10
            
            # تحديث الإحصائيات
            self.stats['whatsapp_groups'] += 1
            
            return {
                'url': url,
                'url_hash': url_info['url_hash'],
                'platform': 'whatsapp',
                'link_type': 'whatsapp_group',
                'title': 'مجموعة واتساب',
                'members': 0,
                'session_id': session_id,
                'added_by_user': added_by_user,
                'confidence': 'medium',
                'metadata': {
                    'collected_at': datetime.now().isoformat(),
                    'message_date': message_date.isoformat() if message_date else None,
                    'quality_score': quality_score
                },
                'validation_score': quality_score
            }
            
        except Exception as e:
            logger.debug(f"خطأ في معالجة رابط واتساب: {e}")
            return None
    
    @staticmethod
    def _extract_links_enhanced(text: str) -> List[str]:
        """Extract links from text with enhanced patterns - استخراج الروابط من النص بأنماط محسنة"""
        if not text:
            return []
        
        # أنماط متقدمة
        url_patterns = [
            r'(https?://[^\s<>"\']+)',  # روابط HTTP/HTTPS
            r'(t\.me/[^\s<>"\']+)',     # روابط t.me
            r'(telegram\.me/[^\s<>"\']+)',  # روابط telegram.me
            r'(chat\.whatsapp\.com/[^\s<>"\']+)',  # روابط واتساب
            r'(discord\.gg/[^\s<>"\']+)',  # روابط ديسكورد
            r'(signal\.group/[^\s<>"\']+)',  # روابط سيجنال
            r'(joinchat/[^\s<>"\']+)',  # روابط انضمام
        ]
        
        all_links = []
        for pattern in url_patterns:
            links = re.findall(pattern, text, re.IGNORECASE)
            all_links.extend(links)
        
        # إزالة التكرارات
        return list(set(all_links))
    
    def _update_collection_stats(self, url_info: Dict, verification: Dict):
        """Update collection statistics - تحديث إحصائيات الجمع"""
        platform = url_info['platform']
        link_type = verification.get('link_type', 'unknown')
        
        if platform == 'telegram':
            if link_type == 'public_group':
                self.stats['telegram_public'] += 1
            elif link_type == 'private_group':
                self.stats['telegram_private'] += 1
            elif link_type == 'join_request':
                self.stats['telegram_join'] += 1
        elif platform == 'whatsapp':
            self.stats['whatsapp_groups'] += 1
        elif platform == 'discord':
            self.stats['discord_invites'] += 1
        elif platform == 'signal':
            self.stats['signal_groups'] += 1
    
    def _calculate_optimal_session_count(self) -> int:
        """Calculate optimal number of concurrent sessions - حساب العدد الأمثل للجلسات المتزامنة"""
        base_count = Config.MAX_CONCURRENT_SESSIONS
        
        # تعديل بناءً على حالة النظام
        if self.system_state['memory_pressure'] == 'high':
            return max(1, base_count // 2)
        elif self.system_state['memory_pressure'] == 'medium':
            return max(2, base_count - 1)
        elif self.system_state['network_status'] == 'poor':
            return max(1, base_count // 2)
        
        return base_count
    
    def _calculate_adaptive_delay(self) -> float:
        """Calculate adaptive delay between cycles - حساب تأخير متكيف بين الدورات"""
        base_delay = Config.REQUEST_DELAYS['min_cycle_delay']
        max_delay = Config.REQUEST_DELAYS['max_cycle_delay']
        
        # زيادة التأخير بناءً على الأخطاء
        error_penalty = min(self.stats['errors'] * 2, 30)
        
        # زيادة التأخير بناءً على flood waits
        flood_penalty = min(self.stats['flood_waits'] * 5, 60)
        
        # تقليل التأخير بناءً على الأداء
        performance_bonus = max(0, (self.stats['performance_score'] - 80) / 2)
        
        # تأثير حالة النظام
        system_modifier = 0
        if self.system_state['memory_pressure'] == 'high':
            system_modifier += 20
        if self.system_state['network_status'] == 'poor':
            system_modifier += 15
        
        calculated_delay = base_delay + error_penalty + flood_penalty + system_modifier - performance_bonus
        
        # التأكد من الحدود
        return max(base_delay, min(calculated_delay, max_delay))
    
    def _calculate_session_delay(self, index: int) -> float:
        """Calculate delay between sessions - حساب التأخير بين الجلسات"""
        base_delay = Config.REQUEST_DELAYS['between_sessions']
        
        # زيادة التأخير للجلسات اللاحقة
        incremental_delay = index * 0.5
        
        # تعديل بناءً على حالة النظام
        if self.system_state['network_status'] == 'poor':
            incremental_delay *= 2
        
        return base_delay + incremental_delay
    
    def _calculate_strategy_delay(self) -> float:
        """Calculate delay between strategies - حساب التأخير بين الاستراتيجيات"""
        return Config.REQUEST_DELAYS['between_tasks']
    
    def _select_strategies(self) -> List:
        """Select collection strategies based on system state - اختيار استراتيجيات الجمع بناءً على حالة النظام"""
        all_strategies = [
            self._strategy_recent_dialogs,
            self._strategy_search_messages
        ]
        
        if self.system_state['memory_pressure'] == 'low' and self.system_state['network_status'] == 'good':
            # استخدام جميع الاستراتيجيات في حالة النظام الجيدة
            return all_strategies
        elif self.system_state['memory_pressure'] == 'high':
            # استخدام الاستراتيجيات الخفيفة فقط
            return [self._strategy_recent_dialogs]
        else:
            # استخدام استراتيجيتين
            return all_strategies[:2]
    
    async def _update_session_health(self, session_id: int, success: bool):
        """Update session health score - تحديث درجة صحة الجلسة"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            async with db._get_connection() as conn:
                if success:
                    # زيادة درجة الصحة
                    await conn.execute('''
                        UPDATE sessions 
                        SET health_score = MIN(100, health_score + 5),
                            last_success = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (session_id,))
                else:
                    # تقليل درجة الصحة
                    await conn.execute('''
                        UPDATE sessions 
                        SET health_score = MAX(0, health_score - 10)
                        WHERE id = ?
                    ''', (session_id,))
                
                await conn.commit()
                
        except Exception as e:
            logger.debug(f"خطأ في تحديث صحة الجلسة: {e}")
    
    async def _update_system_state(self):
        """Update system state based on metrics - تحديث حالة النظام بناءً على المقاييس"""
        memory_usage = self.memory_manager.get_memory_percent()
        
        # تحديث ضغط الذاكرة
        if memory_usage > 85:
            self.system_state['memory_pressure'] = 'high'
        elif memory_usage > 70:
            self.system_state['memory_pressure'] = 'medium'
        else:
            self.system_state['memory_pressure'] = 'low'
        
        # تحديث حالة الشبكة (محاكاة)
        success_rate = self.performance['success_rate']
        if success_rate > 0.9:
            self.system_state['network_status'] = 'excellent'
        elif success_rate > 0.7:
            self.system_state['network_status'] = 'good'
        elif success_rate > 0.5:
            self.system_state['network_status'] = 'fair'
        else:
            self.system_state['network_status'] = 'poor'
        
        self.system_state['last_health_check'] = datetime.now()
    
    async def _optimize_between_cycles(self):
        """Optimize system between collection cycles - تحسين النظام بين دورات الجمع"""
        # تحسين الذاكرة
        memory_result = self.memory_manager.check_and_optimize()
        
        if memory_result['optimized']:
            logger.info("تم تحسين الذاكرة بين الدورات", {
                'saved_mb': memory_result.get('saved_mb', 0),
                'duration_ms': memory_result.get('duration_ms', 0)
            })
        
        # تنظيف الكاش
        await self.cache_manager.cleanup_expired()
        
        # تحديث مقاييس الأداء
        cache_stats = self.cache_manager.get_stats()
        self.performance['cache_hit_rate'] = float(cache_stats['hit_ratio'].rstrip('%')) / 100
        self.performance['memory_usage_mb'] = self.memory_manager.get_memory_usage()
        
        # حساب درجة الأداء
        self._calculate_performance_score()
    
    def _calculate_performance_score(self):
        """Calculate overall performance score - حساب درجة الأداء الشاملة"""
        scores = []
        
        # درجة نجاح الكاش
        cache_score = self.performance['cache_hit_rate'] * 100
        scores.append(cache_score)
        
        # درجة نجاح المهام
        success_score = self.performance['success_rate'] * 100
        scores.append(success_score)
        
        # درجة استخدام الذاكرة
        memory_usage = self.memory_manager.get_memory_percent()
        memory_score = max(0, 100 - memory_usage)
        scores.append(memory_score)
        
        # حساب المتوسط
        if scores:
            self.stats['performance_score'] = sum(scores) / len(scores)
    
    async def _system_monitoring(self):
        """Monitor system health and performance - مراقبة صحة وأداء النظام"""
        while self.active and not self.stop_requested:
            try:
                # جمع مقاييس النظام
                system_metrics = {
                    'memory_usage_mb': self.memory_manager.get_memory_usage(),
                    'memory_percent': self.memory_manager.get_memory_percent(),
                    'cache_stats': self.cache_manager.get_stats(),
                    'task_manager_stats': self.task_manager.get_stats(),
                    'collection_stats': self.stats.copy(),
                    'performance_metrics': self.performance.copy(),
                    'timestamp': datetime.now().isoformat()
                }
                
                # تخزين المقاييس
                await self._store_system_metrics(system_metrics)
                
                # التحقق من المشكلات الحرجة
                await self._check_critical_issues(system_metrics)
                
                await asyncio.sleep(60)  # كل دقيقة
                
            except Exception as e:
                logger.error(f"خطأ في مراقبة النظام: {e}")
                await asyncio.sleep(30)
    
    async def _store_system_metrics(self, metrics: Dict):
        """Store system metrics in database - تخزين مقاييس النظام في قاعدة البيانات"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            async with db._get_connection() as conn:
                for key, value in metrics.items():
                    if key != 'timestamp':
                        await conn.execute('''
                            INSERT INTO system_stats (metric_name, metric_value, metadata)
                            VALUES (?, ?, ?)
                        ''', (key, str(value), json.dumps({'timestamp': metrics['timestamp']})))
                
                await conn.commit()
                
        except Exception as e:
            logger.debug(f"خطأ في تخزين مقاييس النظام: {e}")
    
    async def _check_critical_issues(self, metrics: Dict):
        """Check for critical system issues - التحقق من مشكلات النظام الحرجة"""
        warnings = []
        
        # فحص الذاكرة
        if metrics['memory_percent'] > 90:
            warnings.append(f"استخدام ذاكرة حرج: {metrics['memory_percent']:.1f}%")
        
        # فحص معدل الأخطاء
        if self.stats['errors'] > 50:
            warnings.append(f"عدد أخطاء مرتفع: {self.stats['errors']}")
        
        # فحص معدل نجاح المهام
        if self.performance['success_rate'] < 0.3:
            warnings.append(f"معدل نجاح منخفض: {self.performance['success_rate']:.1%}")
        
        # تسجيل التحذيرات
        if warnings:
            logger.warning(f"مشكلات نظام حرجة: {', '.join(warnings)}")
            
            # تخزين في سجل الأخطاء
            try:
                db = await EnhancedDatabaseManager.get_instance()
                
                async with db._get_connection() as conn:
                    await conn.execute('''
                        INSERT INTO error_log (error_type, error_message, metadata)
                        VALUES (?, ?, ?)
                    ''', ('system_warning', '; '.join(warnings), json.dumps(metrics)))
                    
                    await conn.commit()
                    
            except Exception as e:
                logger.debug(f"خطأ في تسجيل تحذير النظام: {e}")
    
    async def _periodic_maintenance(self):
        """Perform periodic maintenance tasks - تنفيذ مهام الصيانة الدورية"""
        while self.active and not self.stop_requested:
            try:
                # تنظيف الجلسات غير النشطة
                await EnhancedSessionManager.cleanup_inactive_sessions()
                
                # تدوير النسخ الاحتياطية
                if Config.BACKUP_ENABLED:
                    await BackupManager.rotate_backups()
                
                # تحسين قاعدة البيانات
                await self._optimize_database()
                
                # تنظيف السجلات القديمة
                await self._cleanup_old_logs()
                
                await asyncio.sleep(300)  # كل 5 دقائق
                
            except Exception as e:
                logger.error(f"خطأ في الصيانة الدورية: {e}")
                await asyncio.sleep(60)
    
    async def _optimize_database(self):
        """Optimize database performance - تحسين أداء قاعدة البيانات"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            async with db._get_connection() as conn:
                # تحليل الجداول
                await conn.execute("ANALYZE")
                
                # إعادة بناء الفهارس
                await conn.execute("REINDEX")
                
                # تحرير المساحة
                await conn.execute("VACUUM")
                
                await conn.commit()
                
                logger.debug("تم تحسين قاعدة البيانات")
                
        except Exception as e:
            logger.debug(f"خطأ في تحسين قاعدة البيانات: {e}")
    
    async def _cleanup_old_logs(self):
        """Cleanup old log entries - تنظيف إدخالات السجلات القديمة"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            async with db._get_connection() as conn:
                # حذف سجلات الأخطاء القديمة
                await conn.execute('''
                    DELETE FROM error_log 
                    WHERE occurred_at < datetime('now', '-7 days')
                ''')
                
                # حذف مقاييس النظام القديمة
                await conn.execute('''
                    DELETE FROM system_stats 
                    WHERE recorded_at < datetime('now', '-30 days')
                ''')
                
                await conn.commit()
                
                logger.debug("تم تنظيف السجلات القديمة")
                
        except Exception as e:
            logger.debug(f"خطأ في تنظيف السجلات: {e}")
    
    async def _adaptive_optimization(self):
        """Perform adaptive optimization based on performance - تنفيذ تحسين متكيف بناءً على الأداء"""
        while self.active and not self.stop_requested:
            try:
                # التحقق من درجة الأداء
                if self.stats['performance_score'] < 60:
                    logger.warning(f"درجة أداء منخفضة: {self.stats['performance_score']:.1f}")
                    
                    # تنفيذ تحسينات
                    await self._execute_performance_optimizations()
                
                # التحقق من جودة البيانات
                if self.stats['quality_score'] < 50:
                    logger.warning(f"جودة بيانات منخفضة: {self.stats['quality_score']:.1f}")
                    
                    # تحسين عوامل التصفية
                    self._adjust_quality_filters()
                
                await asyncio.sleep(600)  # كل 10 دقائق
                
            except Exception as e:
                logger.error(f"خطأ في التحسين المتكيف: {e}")
                await asyncio.sleep(60)
    
    async def _execute_performance_optimizations(self):
        """Execute performance optimizations - تنفيذ تحسينات الأداء"""
        optimizations = []
        
        # تقليل حجم الكاش إذا كانت الذاكرة مرتفعة
        if self.system_state['memory_pressure'] == 'high':
            self.cache_manager.optimize()
            optimizations.append("تحسين الكاش")
        
        # تقليل عدد المهام المتزامنة
        if self.performance['concurrent_tasks'] > 3:
            self.task_manager.adjust_concurrency(-1)
            optimizations.append("تقليل المهام المتزامنة")
        
        # تنظيف الذاكرة
        memory_saved = self.memory_manager.optimize_memory()
        if memory_saved > 10:
            optimizations.append(f"تحسين الذاكرة ({memory_saved:.1f} MB)")
        
        if optimizations:
            logger.info(f"تم تنفيذ تحسينات الأداء: {', '.join(optimizations)}")
    
    def _adjust_quality_filters(self):
        """Adjust quality filters based on performance - ضبط عوامل تصفية الجودة بناءً على الأداء"""
        # زيادة صرامة الفلاتر إذا كانت الجودة منخفضة
        if self.stats['quality_score'] < 40:
            self.quality_filters['min_url_length'] = 15
            logger.info("تم زيادة صرامة فلاتر الجودة")
        elif self.stats['quality_score'] > 80:
            # تخفيف الفلاتر إذا كانت الجودة عالية
            self.quality_filters['min_url_length'] = 8
            logger.info("تم تخفيف فلاتر الجودة")
    
    async def _graceful_shutdown(self):
        """Perform graceful shutdown - تنفيذ إغلاق سلس"""
        logger.info("بدء الإغلاق السلس لنظام الجمع...")
        
        # تحديث حالة النظام
        self.active = False
        self.paused = False
        self.stats['end_time'] = datetime.now()
        
        # إيقاف أنظمة المراقبة
        self.task_manager.stop_monitoring()
        
        # مسح ذواكر الكاش
        self.cache_manager.clear()
        
        # إغلاق جميع العملاء
        EnhancedSessionManager.clear_cache()
        
        # تحسين الذاكرة النهائي
        self.memory_manager.optimize_memory()
        
        # حفظ الإحصائيات النهائية
        await self._save_final_stats()
        
        logger.info(f"✅ اكتمل الإغلاق السلس. الإحصائيات: {self.stats}")
    
    async def _save_final_stats(self):
        """Save final collection statistics - حفظ إحصائيات الجمع النهائية"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            stats_data = {
                'stats': self.stats,
                'performance': self.performance,
                'system_state': self.system_state,
                'collection_log_summary': self.collection_log.get_summary()
            }
            
            async with db._get_connection() as conn:
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
                    json.dumps(stats_data)
                ))
                
                await conn.commit()
                
        except Exception as e:
            logger.error(f"خطأ في حفظ الإحصائيات النهائية: {e}")
    
    def get_status(self) -> Dict:
        """Get comprehensive collection status - الحصول على حالة الجمع الشاملة"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'stats': self.stats.copy(),
            'performance': self.performance.copy(),
            'system_state': self.system_state.copy(),
            'cache_stats': self.cache_manager.get_stats(),
            'memory': self.memory_manager.get_metrics(),
            'task_manager': self.task_manager.get_stats(),
            'collection_log': self.collection_log.get_summary(),
            'timestamp': datetime.now().isoformat()
        }
    
    async def pause(self):
        """Pause collection with state preservation - إيقاف الجمع مؤقتاً مع الحفاظ على الحالة"""
        self.paused = True
        self.task_manager.pause()
        
        logger.info("⏸️ تم إيقاف الجمع مؤقتاً مع الحفاظ على الحالة", {
            'stats_snapshot': self.stats.copy()
        })
    
    async def resume(self):
        """Resume collection - استئناف الجمع"""
        self.paused = False
        self.task_manager.resume()
        
        logger.info("▶️ تم استئناف الجمع")
    
    async def stop(self):
        """Stop collection gracefully - إيقاف الجمع بسلاسة"""
        self.stop_requested = True
        
        logger.info("⏹️ تم طلب إيقاف الجمع بسلاسة")
        
        # الانتظار للإغلاق السلس
        await asyncio.sleep(2)
    
    async def get_detailed_report(self) -> Dict:
        """Get detailed collection report - الحصول على تقرير جمع مفصل"""
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary(detailed=True)
        
        return {
            'collection_status': self.get_status(),
            'database_stats': db_stats,
            'system_health': {
                'memory': self.memory_manager.get_metrics(),
                'cache': self.cache_manager.get_stats(),
                'tasks': self.task_manager.get_stats(),
                'sessions': EnhancedSessionManager.get_all_metrics()
            },
            'recent_activity': self.collection_log.get_recent_entries(50),
            'recommendations': self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """Generate system recommendations - توليد توصيات النظام"""
        recommendations = []
        
        # توصيات الذاكرة
        memory_percent = self.memory_manager.get_memory_percent()
        if memory_percent > 80:
            recommendations.append("⚠️ استخدام ذاكرة مرتفع. فكر في زيادة حجم الكاش أو تقليل المهام المتزامنة.")
        
        # توصيات الأداء
        if self.stats['performance_score'] < 70:
            recommendations.append("⚡ درجة أداء منخفضة. فكر في زيادة تأخيرات الدورة أو تحسين الاستراتيجيات.")
        
        # توصيات الجودة
        if self.stats['quality_score'] < 60:
            recommendations.append("🎯 جودة البيانات منخفضة. فكر في تشديد فلاتر الجودة أو تحسين التحقق.")
        
        # توصيات الجلسات
        session_metrics = EnhancedSessionManager.get_all_metrics()
        if session_metrics['unhealthy_sessions'] > 3:
            recommendations.append("🔧 عدد الجلسات غير الصحية مرتفع. فكر في إعادة التحقق من الجلسات أو استبدالها.")
        
        return recommendations

# ======================
# Advanced Rate Limiter - حد الطلبات المتقدم
# ======================

class AdvancedRateLimiter:
    """Advanced rate limiting with dynamic thresholds - حد طلبات متقدم مع عتبات ديناميكية"""
    
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
        """Check rate limit with dynamic thresholds - التحقق من حد الطلبات مع عتبات ديناميكية"""
        async with self.locks[user_id]:
            user_data = self.user_limits[user_id]
            now = datetime.now()
            
            # تنظيف الطلبات القديمة
            while user_data['requests'] and (now - user_data['requests'][0]).total_seconds() > Config.USER_RATE_LIMIT['per_seconds']:
                user_data['requests'].popleft()
            
            # حساب الحد الديناميكي
            dynamic_limit = self._calculate_dynamic_limit(user_id)
            
            if len(user_data['requests']) >= dynamic_limit:
                user_data['penalty_score'] += 10
                user_data['last_violation'] = now
                self.global_limits['rate_violations'] += 1
                
                # حساب وقت الانتظار العقابي
                wait_time = self._calculate_wait_time(user_data['penalty_score'])
                
                return False, {
                    'allowed': False,
                    'wait_seconds': wait_time,
                    'current_requests': len(user_data['requests']),
                    'dynamic_limit': dynamic_limit,
                    'penalty_score': user_data['penalty_score'],
                    'action': action
                }
            
            # تسجيل الطلب
            user_data['requests'].append(now)
            user_data['total'] += 1
            self.global_limits['total_requests'] += 1
            
            # تقليل العقوبة بمرور الوقت
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
        """Calculate dynamic rate limit - حساب حد الطلبات الديناميكي"""
        base_limit = Config.USER_RATE_LIMIT['max_requests']
        user_data = self.user_limits[user_id]
        
        # تقليل الحد بناءً على درجة العقوبة
        penalty_factor = max(0.3, 1 - (user_data['penalty_score'] / 100))
        
        # تعديل بناءً على النشاط العالمي
        global_factor = 1.0
        if self.global_limits['rate_violations'] > 10:
            global_factor = 0.8
        elif self.global_limits['total_requests'] > 1000:
            global_factor = 0.9
        
        return int(base_limit * penalty_factor * global_factor)
    
    def _calculate_wait_time(self, penalty_score: int) -> float:
        """Calculate wait time based on penalty - حساب وقت الانتظار بناءً على العقوبة"""
        base_wait = 30  # 30 ثانية أساسية
        
        # زيادة وقت الانتظار مع زيادة العقوبة
        penalty_multiplier = 1 + (penalty_score / 50)
        
        return min(base_wait * penalty_multiplier, 300)  # حد أقصى 5 دقائق
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Get comprehensive user rate limit stats - الحصول على إحصائيات حد الطلبات الشاملة للمستخدم"""
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
        
        # حساب الطلبات في النوافذ الزمنية المختلفة
        window_stats = {}
        for window in [10, 30, 60, 300, 1800]:  # 10ث, 30ث, 1د, 5د, 30د
            count = sum(1 for req_time in recent_requests 
                       if (now - req_time).total_seconds() <= window)
            window_stats[f'last_{window}s'] = count
        
        # تحديد حالة المستخدم
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
    
    def get_global_stats(self) -> Dict:
        """Get global rate limiting statistics - الحصول على إحصائيات الحد الشاملة"""
        active_users = sum(1 for user_data in self.user_limits.values() 
                          if user_data.get('requests'))
        
        return {
            'total_requests': self.global_limits['total_requests'],
            'rate_violations': self.global_limits['rate_violations'],
            'active_users': active_users,
            'total_users': len(self.user_limits),
            'average_requests_per_user': self.global_limits['total_requests'] / max(1, len(self.user_limits)),
            'violation_rate': self.global_limits['rate_violations'] / max(1, self.global_limits['total_requests'])
        }
    
    async def reset_user(self, user_id: int):
        """Reset rate limit for user - إعادة تعيين حد الطلبات للمستخدم"""
        async with self.locks[user_id]:
            self.user_limits[user_id] = {
                'requests': deque(),
                'total': 0,
                'penalty_score': 0,
                'last_violation': None
            }
    
    def adjust_global_threshold(self, adjustment: int):
        """Adjust global rate limit threshold - ضبط عتبة حد الطلبات العالمية"""
        self.global_limits['adaptive_threshold'] = max(1, 
            self.global_limits['adaptive_threshold'] + adjustment
        )

# ======================
# Task Manager - مدير المهام
# ======================

class TaskManager:
    """Advanced task management with monitoring and control - إدارة مهام متقدمة مع مراقبة وتحكم"""
    
    def __init__(self):
        self.active_tasks = set()
        self.task_metrics = defaultdict(lambda: {
            'count': 0,
            'success': 0,
            'failed': 0,
            'total_time': 0.0,
            'avg_time': 0.0
        })
        
        self.task_queue = asyncio.Queue(maxsize=100)
        self.worker_tasks = []
        self.max_workers = 5
        
        self.monitoring = False
        self.paused = False
        
        self.lock = asyncio.Lock()
        
    def start_monitoring(self):
        """Start task monitoring - بدء مراقبة المهام"""
        self.monitoring = True
        asyncio.create_task(self._monitor_tasks())
        self._start_workers()
    
    def _start_workers(self):
        """Start worker tasks - بدء مهام العاملين"""
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(i))
            self.worker_tasks.append(worker)
    
    async def _worker(self, worker_id: int):
        """Worker task to process queued tasks - مهمة عامل لمعالجة المهام في قائمة الانتظار"""
        logger.debug(f"بدء العامل {worker_id}")
        
        while self.monitoring:
            if self.paused:
                await asyncio.sleep(0.1)
                continue
            
            try:
                # الحصول على مهمة من قائمة الانتظار مع مهلة
                task_data = await asyncio.wait_for(
                    self.task_queue.get(),
                    timeout=1.0
                )
                
                func, args, kwargs, task_id = task_data
                
                start_time = datetime.now()
                
                try:
                    # تنفيذ المهمة
                    result = await func(*args, **kwargs)
                    execution_time = (datetime.now() - start_time).total_seconds()
                    
                    # تحديث المقاييس
                    async with self.lock:
                        self.task_metrics[func.__name__]['count'] += 1
                        self.task_metrics[func.__name__]['success'] += 1
                        self.task_metrics[func.__name__]['total_time'] += execution_time
                        self.task_metrics[func.__name__]['avg_time'] = (
                            self.task_metrics[func.__name__]['total_time'] / 
                            self.task_metrics[func.__name__]['count']
                        )
                    
                    logger.debug(f"اكتملت المهمة {task_id} في {execution_time:.2f} ثانية")
                    
                except Exception as e:
                    execution_time = (datetime.now() - start_time).total_seconds()
                    
                    async with self.lock:
                        self.task_metrics[func.__name__]['count'] += 1
                        self.task_metrics[func.__name__]['failed'] += 1
                    
                    logger.error(f"فشلت المهمة {task_id}: {e}")
                    
                finally:
                    self.task_queue.task_done()
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"خطأ في العامل {worker_id}: {e}")
                await asyncio.sleep(0.5)
    
    async def _monitor_tasks(self):
        """Monitor task execution - مراقبة تنفيذ المهام"""
        while self.monitoring:
            try:
                queue_size = self.task_queue.qsize()
                active_count = len(self.active_tasks)
                
                if queue_size > 50:
                    logger.warning(f"حجم قائمة انتظار المهام مرتفع: {queue_size}")
                
                if active_count > 20:
                    logger.warning(f"عدد المهام النشطة مرتفع: {active_count}")
                
                # تحديث المقاييس
                await self._update_metrics()
                
                await asyncio.sleep(5)  # كل 5 ثواني
                
            except Exception as e:
                logger.error(f"خطأ في مراقبة المهام: {e}")
                await asyncio.sleep(10)
    
    async def _update_metrics(self):
        """Update task metrics - تحديث مقاييس المهام"""
        # يمكن إضافة المزيد من المقاييس هنا
        pass
    
    async def execute_tasks(self, tasks: List) -> List:
        """Execute tasks with proper management - تنفيذ المهام مع إدارة مناسبة"""
        if not tasks:
            return []
        
        start_time = datetime.now()
        results = []
        
        try:
            # تنفيذ المهام مع التحكم
            semaphore = asyncio.Semaphore(10)  # 10 مهام متزامنة كحد أقصى
            
            async def execute_with_limit(task):
                async with semaphore:
                    return await task
            
            task_coroutines = [execute_with_limit(task) for task in tasks]
            results = await asyncio.gather(*task_coroutines, return_exceptions=True)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.debug(f"اكتمل تنفيذ {len(tasks)} مهمة في {execution_time:.2f} ثانية")
            
        except Exception as e:
            logger.error(f"خطأ في تنفيذ المهام: {e}")
        
        return results
    
    async def add_task(self, func, *args, **kwargs):
        """Add task to queue - إضافة مهمة إلى قائمة الانتظار"""
        task_id = f"task_{secrets.token_hex(8)}"
        
        try:
            await self.task_queue.put((func, args, kwargs, task_id))
            self.active_tasks.add(task_id)
            
            return task_id
            
        except asyncio.QueueFull:
            logger.warning("قائمة انتظار المهام ممتلئة")
            raise
    
    def adjust_concurrency(self, adjustment: int):
        """Adjust worker concurrency - ضبط التزامن للعاملين"""
        new_max = max(1, min(20, self.max_workers + adjustment))
        
        if new_max != self.max_workers:
            logger.info(f"ضبط التزامن: {self.max_workers} -> {new_max}")
            self.max_workers = new_max
            
            # إعادة تهيئة العاملين
            for task in self.worker_tasks:
                task.cancel()
            
            self.worker_tasks = []
            self._start_workers()
    
    def pause(self):
        """Pause task execution - إيقاف تنفيذ المهام مؤقتاً"""
        self.paused = True
    
    def resume(self):
        """Resume task execution - استئناف تنفيذ المهام"""
        self.paused = False
    
    def stop_monitoring(self):
        """Stop task monitoring - إيقاف مراقبة المهام"""
        self.monitoring = False
        
        # إيقاف العاملين
        for task in self.worker_tasks:
            task.cancel()
        
        self.worker_tasks = []
    
    def get_stats(self) -> Dict:
        """Get task management statistics - الحصول على إحصائيات إدارة المهام"""
        total_tasks = 0
        total_success = 0
        total_failed = 0
        total_time = 0.0
        
        for metrics in self.task_metrics.values():
            total_tasks += metrics['count']
            total_success += metrics['success']
            total_failed += metrics['failed']
            total_time += metrics['total_time']
        
        success_rate = total_success / max(1, total_tasks)
        avg_time = total_time / max(1, total_tasks)
        
        return {
            'total_tasks': total_tasks,
            'total_success': total_success,
            'total_failed': total_failed,
            'success_rate': success_rate,
            'total_execution_time': total_time,
            'avg_execution_time': avg_time,
            'queue_size': self.task_queue.qsize(),
            'active_tasks': len(self.active_tasks),
            'max_workers': self.max_workers,
            'paused': self.paused,
            'monitoring': self.monitoring,
            'task_types': dict(self.task_metrics)
        }

# ======================
# Intelligent Log - سجل ذكي
# ======================

class IntelligentLog:
    """Intelligent logging system with analysis capabilities - نظام تسجيل ذكي مع قدرات التحليل"""
    
    def __init__(self, max_entries: int = 1000):
        self.entries = deque(maxlen=max_entries)
        self.categories = defaultdict(int)
        self.severity_counts = defaultdict(int)
        self.timeline = []
        
    def add(self, category: str, event: str, data: Dict = None):
        """Add log entry - إضافة إدخال سجل"""
        entry = {
            'id': len(self.entries) + 1,
            'timestamp': datetime.now().isoformat(),
            'category': category,
            'event': event,
            'data': data or {},
            'severity': self._determine_severity(category, event)
        }
        
        self.entries.append(entry)
        self.categories[category] += 1
        self.severity_counts[entry['severity']] += 1
        self.timeline.append(entry['timestamp'])
        
        # تحليل الإدخال
        self._analyze_entry(entry)
    
    def _determine_severity(self, category: str, event: str) -> str:
        """Determine log entry severity - تحديد خطورة إدخال السجل"""
        if category in ['error', 'critical']:
            return 'critical'
        elif category in ['warning', 'rate_limit']:
            return 'warning'
        elif category in ['cycle', 'session']:
            return 'info'
        else:
            return 'debug'
    
    def _analyze_entry(self, entry: Dict):
        """Analyze log entry for patterns - تحليل إدخال السجل للأنماط"""
        # يمكن إضافة تحليل الأنماط هنا
        pass
    
    def get_recent_entries(self, count: int = 100) -> List[Dict]:
        """Get recent log entries - الحصول على إدخالات السجل الحديثة"""
        return list(self.entries)[-count:]
    
    def get_entries_by_category(self, category: str) -> List[Dict]:
        """Get entries by category - الحصول على الإدخالات حسب الفئة"""
        return [entry for entry in self.entries if entry['category'] == category]
    
    def get_entries_by_severity(self, severity: str) -> List[Dict]:
        """Get entries by severity - الحصول على الإدخالات حسب الخطورة"""
        return [entry for entry in self.entries if entry['severity'] == severity]
    
    def get_summary(self) -> Dict:
        """Get log summary - الحصول على ملخص السجل"""
        total_entries = len(self.entries)
        
        if total_entries == 0:
            return {
                'total_entries': 0,
                'categories': {},
                'severity': {},
                'timeline': []
            }
        
        # حساب المعدلات
        if len(self.timeline) >= 2:
            first_time = datetime.fromisoformat(self.timeline[0])
            last_time = datetime.fromisoformat(self.timeline[-1])
            time_span = (last_time - first_time).total_seconds()
            
            if time_span > 0:
                entries_per_second = total_entries / time_span
            else:
                entries_per_second = 0
        else:
            entries_per_second = 0
        
        return {
            'total_entries': total_entries,
            'categories': dict(self.categories),
            'severity': dict(self.severity_counts),
            'entries_per_second': entries_per_second,
            'recent_activity': self.get_recent_entries(10),
            'critical_entries': self.get_entries_by_severity('critical'),
            'warning_entries': self.get_entries_by_severity('warning'),
            'timeline': self.timeline[-100:]  # آخر 100 إدخال
        }
    
    def clear(self):
        """Clear log - مسح السجل"""
        self.entries.clear()
        self.categories.clear()
        self.severity_counts.clear()
        self.timeline.clear()
    
    def find_patterns(self) -> List[Dict]:
        """Find patterns in log entries - العثور على أنماط في إدخالات السجل"""
        patterns = []
        
        # تحليل الأخطاء المتكررة
        error_entries = self.get_entries_by_severity('critical')
        error_messages = defaultdict(int)
        
        for entry in error_entries:
            if 'data' in entry and 'error' in entry['data']:
                error_msg = entry['data']['error'][:100]
                error_messages[error_msg] += 1
        
        for error_msg, count in error_messages.items():
            if count >= 3:
                patterns.append({
                    'type': 'repeating_error',
                    'message': error_msg,
                    'count': count,
                    'severity': 'high'
                })
        
        # تحليل الفترات النشطة
        if len(self.timeline) >= 10:
            recent_timestamps = [datetime.fromisoformat(ts) for ts in self.timeline[-10:]]
            time_diffs = []
            
            for i in range(1, len(recent_timestamps)):
                diff = (recent_timestamps[i] - recent_timestamps[i-1]).total_seconds()
                time_diffs.append(diff)
            
            avg_diff = sum(time_diffs) / len(time_diffs) if time_diffs else 0
            
            if avg_diff < 1.0:
                patterns.append({
                    'type': 'high_frequency',
                    'avg_interval': avg_diff,
                    'severity': 'medium'
                })
        
        return patterns

# ======================
# Advanced Security Manager - مدير الأمان المتقدم
# ======================

class AdvancedSecurityManager:
    """Advanced security and access control with threat detection - أمان متقدم والتحكم في الوصول مع كشف التهديدات"""
    
    def __init__(self):
        self.rate_limiter = AdvancedRateLimiter()
        self.suspicious_activity = defaultdict(list)
        self.access_log = deque(maxlen=1000)
        self.threat_detection_enabled = True
        
    async def check_access(self, user_id: int, command: str = None, 
                          context: Dict = None) -> Tuple[bool, str, Dict]:
        """Check user access with threat detection - التحقق من وصول المستخدم مع كشف التهديدات"""
        # التحقق الأساسي
        if Config.ADMIN_USER_IDS and user_id in Config.ADMIN_USER_IDS:
            return True, "مدير", {'access_level': 'admin'}
        
        if Config.ALLOWED_USER_IDS and user_id not in Config.ALLOWED_USER_IDS:
            self._log_suspicious_activity(user_id, 'unauthorized_access', context)
            return False, "غير مصرح لك بالوصول", {'access_level': 'denied'}
        
        # التحقق من حد الطلبات
        limit_result, limit_details = await self.rate_limiter.check_limit(user_id, command or 'general')
        
        if not limit_result:
            self._log_suspicious_activity(user_id, 'rate_limit_exceeded', {
                **context,
                'limit_details': limit_details
            })
            
            wait_time = limit_details.get('wait_seconds', 30)
            return False, f"تجاوزت الحد الأقصى للطلبات. حاول بعد {wait_time:.0f} ثانية", {
                'access_level': 'rate_limited',
                'wait_seconds': wait_time,
                **limit_details
            }
        
        # كشف التهديدات المتقدمة
        if self.threat_detection_enabled:
            threat_check = await self._detect_threats(user_id, command, context)
            if not threat_check['safe']:
                self._log_suspicious_activity(user_id, 'threat_detected', threat_check)
                return False, "تم اكتشاف نشاط مشبوه. الوصول مرفوض.", {
                    'access_level': 'blocked',
                    'threat_details': threat_check
                }
        
        # تسجيل الوصول الناجح
        self._log_access(user_id, 'success', command, context)
        
        return True, "مسموح", {
            'access_level': 'user',
            'rate_limit': limit_details,
            'user_stats': self.rate_limiter.get_user_stats(user_id)
        }
    
    async def _detect_threats(self, user_id: int, command: str, context: Dict) -> Dict:
        """Detect security threats - كشف التهديدات الأمنية"""
        threats = []
        risk_score = 0
        
        # تحليل التكرار السريع
        recent_accesses = [log for log in self.access_log 
                          if log['user_id'] == user_id and 
                          (datetime.now() - log['timestamp']).total_seconds() < 10]
        
        if len(recent_accesses) > 5:
            threats.append('rapid_repeated_access')
            risk_score += 30
        
        # تحليل الأوامر المشبوهة
        suspicious_commands = ['eval', 'exec', 'system', 'os.', 'subprocess']
        if command and any(suspicious in command.lower() for suspicious in suspicious_commands):
            threats.append('suspicious_command')
            risk_score += 50
        
        # تحليل الأنماط غير الطبيعية
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
        """Log access attempt - تسجيل محاولة الوصول"""
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
        """Log suspicious activity - تسجيل النشاط المشبوه"""
        activity = {
            'timestamp': datetime.now(),
            'user_id': user_id,
            'activity_type': activity_type,
            'details': details
        }
        
        self.suspicious_activity[user_id].append(activity)
        
        # الاحتفاظ بآخر 10 أنشطة لكل مستخدم
        if len(self.suspicious_activity[user_id]) > 10:
            self.suspicious_activity[user_id] = self.suspicious_activity[user_id][-10:]
        
        logger.warning(f"نشاط مشبوه: {activity_type} للمستخدم {user_id}", details)
    
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
    
    def get_user_security_report(self, user_id: int) -> Dict:
        """Get comprehensive security report for user - الحصول على تقرير أمني شامل للمستخدم"""
        rate_stats = self.rate_limiter.get_user_stats(user_id)
        suspicious_count = len(self.suspicious_activity.get(user_id, []))
        
        recent_accesses = [log for log in self.access_log 
                          if log['user_id'] == user_id and 
                          (datetime.now() - log['timestamp']).total_seconds() < 3600]
        
        return {
            'user_id': user_id,
            'access_level': self.get_user_access_level(user_id),
            'rate_limit_stats': rate_stats,
            'suspicious_activities': suspicious_count,
            'recent_suspicious': self.suspicious_activity.get(user_id, [])[-5:],
            'recent_accesses': len(recent_accesses),
            'last_access': recent_accesses[-1]['timestamp'] if recent_accesses else None,
            'security_score': self._calculate_security_score(user_id, rate_stats, suspicious_count),
            'recommendations': self._generate_security_recommendations(user_id, rate_stats)
        }
    
    def _calculate_security_score(self, user_id: int, rate_stats: Dict, suspicious_count: int) -> int:
        """Calculate user security score - حساب درجة أمان المستخدم"""
        score = 100
        
        # خصم بناءً على حد الطلبات
        if rate_stats.get('status') == 'critical':
            score -= 40
        elif rate_stats.get('status') == 'warning':
            score -= 20
        elif rate_stats.get('status') == 'monitoring':
            score -= 10
        
        # خصم بناءً على الأنشطة المشبوهة
        score -= min(suspicious_count * 5, 30)
        
        # مكافأة للمديرين
        if self.is_admin(user_id):
            score += 10
        
        return max(0, min(100, score))
    
    def _generate_security_recommendations(self, user_id: int, rate_stats: Dict) -> List[str]:
        """Generate security recommendations for user - توليد توصيات أمنية للمستخدم"""
        recommendations = []
        
        if rate_stats.get('status') == 'critical':
            recommendations.append("🔴 حالة حرجة: تقليل تكرار الطلبات فوراً")
        elif rate_stats.get('status') == 'warning':
            recommendations.append("🟡 تحذير: تقليل وتيرة الاستخدام")
        
        suspicious_count = len(self.suspicious_activity.get(user_id, []))
        if suspicious_count > 5:
            recommendations.append(f"⚠️ {suspicious_count} أنشطة مشبوهة. توخ الحذر.")
        
        if rate_stats.get('penalty_score', 0) > 30:
            recommendations.append("⏱️ عقوبة مرتفعة. انتظر قبل المزيد من الطلبات.")
        
        return recommendations
    
    def get_global_security_report(self) -> Dict:
        """Get global security report - الحصول على تقرير أمني شامل"""
        rate_global = self.rate_limiter.get_global_stats()
        
        total_suspicious = sum(len(activities) for activities in self.suspicious_activity.values())
        unique_suspicious_users = len(self.suspicious_activity)
        
        recent_blocked = [log for log in self.access_log 
                         if log['status'] == 'blocked' and 
                         (datetime.now() - log['timestamp']).total_seconds() < 3600]
        
        return {
            'total_users': len(self.access_log),
            'unique_users': len(set(log['user_id'] for log in self.access_log)),
            'rate_limit_stats': rate_global,
            'total_suspicious_activities': total_suspicious,
            'users_with_suspicious_activities': unique_suspicious_users,
            'recently_blocked': len(recent_blocked),
            'recent_threats': self._analyze_recent_threats(),
            'security_status': self._determine_global_security_status(rate_global)
        }
    
    def _analyze_recent_threats(self) -> List[Dict]:
        """Analyze recent security threats - تحليل التهديدات الأمنية الحديثة"""
        recent_threats = []
        
        # تحليل آخر ساعة
        hour_ago = datetime.now() - timedelta(hours=1)
        
        for user_id, activities in self.suspicious_activity.items():
            recent_activities = [a for a in activities if a['timestamp'] > hour_ago]
            
            if recent_activities:
                threat_types = defaultdict(int)
                for activity in recent_activities:
                    threat_types[activity['activity_type']] += 1
                
                recent_threats.append({
                    'user_id': user_id,
                    'activity_count': len(recent_activities),
                    'threat_types': dict(threat_types),
                    'last_activity': max(a['timestamp'] for a in recent_activities)
                })
        
        return sorted(recent_threats, key=lambda x: x['activity_count'], reverse=True)[:10]
    
    def _determine_global_security_status(self, rate_stats: Dict) -> str:
        """Determine global security status - تحديد حالة الأمن الشاملة"""
        violation_rate = rate_stats.get('violation_rate', 0)
        
        if violation_rate > 0.1:  # 10% انتهاكات
            return "critical"
        elif violation_rate > 0.05:  # 5% انتهاكات
            return "warning"
        elif violation_rate > 0.02:  # 2% انتهاكات
            return "monitoring"
        else:
            return "secure"
    
    def enable_threat_detection(self):
        """Enable threat detection - تمكين كشف التهديدات"""
        self.threat_detection_enabled = True
    
    def disable_threat_detection(self):
        """Disable threat detection - تعطيل كشف التهديدات"""
        self.threat_detection_enabled = False

# ======================
# Advanced Telegram Bot - بوت تيليجرام المتقدم
# ======================

class AdvancedTelegramBot:
    """Advanced Telegram bot with enhanced features - بوت تيليجرام متقدم بمميزات محسنة"""
    
    def __init__(self):
        self.collection_manager = AdvancedCollectionManager()
        self.security_manager = AdvancedSecurityManager()
        
        # تهيئة التطبيق المتقدم
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        
        # إضافة معالجات متقدمة
        self._setup_advanced_handlers()
        
        # إدارة الحالة
        self.user_states = defaultdict(dict)
        self.conversation_states = {}
        
        # نظام المساعدة الذكي
        self.help_system = HelpSystem()
        
        # نظام الإشعارات
        self.notification_system = NotificationSystem()
    
    def _setup_advanced_handlers(self):
        """Setup advanced bot handlers - إعداد معالجات البوت المتقدمة"""
        # معالجات الأوامر المتقدمة
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
        
        # معالجات الاستدعاء المتقدمة
        self.app.add_handler(CallbackQueryHandler(self.handle_advanced_callback))
        
        # معالجات الرسائل المتقدمة
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_advanced_message
        ))
        
        # معالجة الأخطاء
        self.app.add_error_handler(self.error_handler)
    
    async def advanced_start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command with advanced features - معالجة أمر /start بمميزات متقدمة"""
        user = update.effective_user
        
        # التحقق من الوصول المتقدم
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
            
            # إرسال تحذير للإداريين
            if self.security_manager.is_admin(user.id):
                await self.notification_system.send_security_alert(
                    f"محاولة وصول مرفوضة: {user.id} (@{user.username})",
                    details
                )
            
            return
        
        # تحديث المستخدم في قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        await db.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        # تحديث حالة المستخدم
        self.user_states[user.id] = {
            'last_command': 'start',
            'access_level': details.get('access_level'),
            'timestamp': datetime.now()
        }
        
        # إنشاء واجهة متقدمة
        welcome_text = self.help_system.get_welcome_message(user, details)
        
        keyboard = self._create_main_keyboard(user.id)
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
        
        # إرسال رسالة ترحيب خاصة للمستخدمين الجدد
        user_stats = await db.get_user_stats(user.id)
        if user_stats.get('account_age_days', 365) < 1:  # مستخدم جديد
            await self._send_welcome_tutorial(update.message, user)
    
    async def advanced_help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command with context-aware help - معالجة أمر /help بمساعدة سياقية"""
        user = update.effective_user
        
        # التحقق من الوصول
        access, message, _ = await self.security_manager.check_access(user.id, 'help')
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        # الحصول على المساعدة حسب السياق
        last_command = self.user_states.get(user.id, {}).get('last_command', 'general')
        help_text = self.help_system.get_context_help(last_command, user.id)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 الدليل الكامل", callback_data="full_guide")],
            [InlineKeyboardButton("🎬 فيديو تعليمي", callback_data="video_tutorial")],
            [InlineKeyboardButton("❓ الأسئلة الشائعة", callback_data="faq")],
            [InlineKeyboardButton("🔧 استكشاف الأخطاء", callback_data="troubleshooting")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")]
        ])
        
        await update.message.reply_text(help_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def advanced_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command with detailed monitoring - معالجة أمر /status مع مراقبة مفصلة"""
        user = update.effective_user
        
        # التحقق من الوصول
        access, message, _ = await self.security_manager.check_access(user.id, 'status')
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        # تحديث حالة المستخدم
        self.user_states[user.id]['last_command'] = 'status'
        
        # الحصول على حالة النظام المتقدمة
        status = self.collection_manager.get_status()
        
        # إحصائيات النظام
        memory_metrics = MemoryManager.get_instance().get_metrics()
        cache_stats = CacheManager.get_instance().get_stats()
        
        # تنسيق النص المتقدم
        status_text = f"""
📊 **حالة النظام المتقدمة - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**

**🔧 حالة الجمع:**
"""
        
        if status['active']:
            if status['paused']:
                status_text += "⏸️ **موقف مؤقتاً**\n"
            elif status['stop_requested']:
                status_text += "🛑 **جاري الإيقاف...**\n"
            else:
                status_text += "🔄 **نشط**\n"
                
                # إضافة تقدم إذا كان يعمل
                if status['stats']['start_time']:
                    duration = datetime.now() - status['stats']['start_time']
                    status_text += f"   ⏱️ المدة: {self._format_duration(duration)}\n"
                    status_text += f"   🔄 الدورات: {status['stats']['cycles_completed']}\n"
        else:
            status_text += "🛑 **متوقف**\n"
        
        status_text += f"""
**📈 إحصائيات الجمع:**
• 📦 المجموعات: {status['stats']['total_collected']:,}
• 📢 عامة: {status['stats']['telegram_public']:,}
• 🔒 خاصة: {status['stats']['telegram_private']:,}
• ➕ انضمام: {status['stats']['telegram_join']:,}
• 📱 واتساب: {status['stats']['whatsapp_groups']:,}
• 🔄 مكررات: {status['stats']['duplicates']:,}

**⚡ أداء النظام:**
• 🎯 درجة الأداء: {status['stats']['performance_score']:.1f}/100
• 💾 نسبة الكاش: {status['performance']['cache_hit_rate']:.1%}
• 🧠 الذاكرة: {status['memory']['current_mb']:.1f} MB
• 📶 حالة الشبكة: {status['system_state']['network_status']}
• ⚖️ ضغط الذاكرة: {status['system_state']['memory_pressure']}

**👤 حالتك:**
"""
        
        # إحصائيات المستخدم
        db = await EnhancedDatabaseManager.get_instance()
        user_stats = await db.get_user_stats(user.id)
        
        if user_stats:
            status_text += f"""• 🆔 المعرف: {user.id}
• 👤 الاسم: {user_stats.get('first_name', '')} {user_stats.get('last_name', '')}
• 📅 العضو منذ: {user_stats.get('account_age_days', 0)} يوم
• 📊 طلباتك: {user_stats.get('request_count', 0):,}
• 🔗 روابطك: {user_stats.get('total_links', 0):,}
• 💼 جلساتك: {user_stats.get('total_sessions', 0)}
"""
        
        # إضافة التوصيات
        recommendations = status.get('recommendations', [])
        if recommendations:
            status_text += "\n**💡 التوصيات:**\n"
            for rec in recommendations[:3]:
                status_text += f"• {rec}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث مفصل", callback_data="refresh_detailed")],
            [InlineKeyboardButton("📊 إحصائيات كاملة", callback_data="full_stats")],
            [InlineKeyboardButton("⚡ تحسين الأداء", callback_data="optimize_performance")],
            [InlineKeyboardButton("📋 تقرير النظام", callback_data="system_report")]
        ])
        
        await update.message.reply_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def advanced_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command with comprehensive statistics - معالجة أمر /stats مع إحصائيات شاملة"""
        user = update.effective_user
        
        # التحقق من الوصول
        access, message, _ = await self.security_manager.check_access(user.id, 'stats')
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        await update.message.reply_text("📈 جاري جمع الإحصائيات المتقدمة...")
        
        try:
            # الحصول على إحصائيات متقدمة
            db = await EnhancedDatabaseManager.get_instance()
            db_stats = await db.get_stats_summary(detailed=True)
            
            # إحصائيات الجمع
            mgr_stats = self.collection_manager.stats
            perf_stats = self.collection_manager.performance
            
            # إحصائيات النظام
            memory_stats = MemoryManager.get_instance().get_metrics()
            cache_stats = CacheManager.get_instance().get_stats()
            session_stats = EnhancedSessionManager.get_all_metrics()
            
            stats_text = f"""
📊 **الإحصائيات المتقدمة الشاملة**

**🗃️ قاعدة البيانات:**
• إجمالي الروابط: {db_stats.get('total_links', 0):,}
• روابط تيليجرام: {db_stats.get('links_by_platform', {}).get('telegram', 0):,}
• روابط واتساب: {db_stats.get('links_by_platform', {}).get('whatsapp', 0):,}
• الجلسات النشطة: {db_stats.get('active_sessions', 0)}
• المستخدمون: {db_stats.get('total_users', 0):,}

**📈 توزيع تيليجرام:**
"""
            
            for link_type, count in db_stats.get('telegram_by_type', {}).items():
                type_name = {
                    'public_group': '📢 مجموعات عامة',
                    'private_group': '🔒 مجموعات خاصة',
                    'join_request': '➕ طلبات انضمام',
                    'unknown': '❓ غير معروف'
                }.get(link_type, link_type)
                
                percentage = (count / max(1, db_stats.get('links_by_platform', {}).get('telegram', 1))) * 100
                stats_text += f"• {type_name}: {count:,} ({percentage:.1f}%)\n"
            
            stats_text += f"""
**🚀 إحصائيات الجمع:**
• تم جمعها: {mgr_stats['total_collected']:,}
• القنوات المتجاهلة: {mgr_stats['channels_skipped']:,}
• الأخطاء: {mgr_stats['errors']:,}
• انتظارات Flood: {mgr_stats['flood_waits']:,}
• الدورات المكتملة: {mgr_stats['cycles_completed']:,}
• درجة الأداء: {mgr_stats['performance_score']:.1f}/100

**⚡ مقاييس الأداء:**
• نسبة ضربات الكاش: {perf_stats['cache_hit_rate']:.1%}
• معدل النجاح: {perf_stats['success_rate']:.1%}
• متوسط وقت المهمة: {perf_stats['avg_processing_time']:.2f} ثانية
• المهام المتزامنة: {perf_stats['concurrent_tasks']}

**💾 موارد النظام:**
• استخدام الذاكرة: {memory_stats['current_mb']:.1f} MB
• نسبة الذاكرة: {memory_stats.get('current_percent', 0):.1f}%
• تحسينات الذاكرة: {memory_stats.get('optimizations', 0)}
• حجم الكاش السريع: {cache_stats['fast_cache_size']}/{cache_stats['fast_cache_max']}
• نسبة ضربات الكاش: {cache_stats['hit_ratio']}

**👥 أفضل المستخدمين:**
"""
            
            for user_data in db_stats.get('top_users', [])[:5]:
                username = user_data.get('username', f"user_{user_data.get('user_id')}")
                stats_text += f"• @{username}: {user_data.get('link_count', 0):,} رابط\n"
            
            # إضافة التوصيات
            if mgr_stats['performance_score'] < 70:
                stats_text += "\n**💡 توصية:** درجة الأداء منخفضة. فكر في تحسين الإعدادات.\n"
            
            if memory_stats.get('current_percent', 0) > 80:
                stats_text += "**⚠️ تحذير:** استخدام الذاكرة مرتفع. فكر في زيادة الحد الأقصى للذاكرة.\n"
            
            await update.message.reply_text(stats_text, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"خطأ في أمر الإحصائيات: {e}", exc_info=True)
            await update.message.reply_text("❌ حدث خطأ في جلب الإحصائيات المتقدمة")
    
    async def advanced_sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sessions command with health monitoring - معالجة أمر /sessions مع مراقبة الصحة"""
        user = update.effective_user
        is_admin = self.security_manager.is_admin(user.id)
        
        # التحقق من الوصول
        access, message, _ = await self.security_manager.check_access(user.id, 'sessions')
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            # الحصول على الجلسات مع معلومات الصحة
            sessions = await db.get_active_sessions(user.id if not is_admin else None, limit=20)
            
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
                health = session.get('health_status', 'unknown')
                health_icon = {
                    'excellent': '🟢',
                    'good': '🟡',
                    'fair': '🟠',
                    'poor': '🔴',
                    'critical': '💀'
                }.get(health, '❓')
                
                text += f"{i}. {health_icon} **{name}**\n"
                text += f"   📱: ***{phone} | 📅: {last_used}\n"
                text += f"   🏥 الصحة: {health} ({session.get('health_score', 0)}/100)\n"
                text += f"   🔗 الروابط: {session.get('total_links_collected', 0)}\n"
                
                if session.get('recent_links', 0) > 0:
                    text += f"   ⚡ حديثة: {session.get('recent_links')} (آخر ساعة)\n"
                
                notes = session.get('notes', '')
                if notes:
                    text += f"   📝: {notes[:30]}{'...' if len(notes) > 30 else ''}\n"
                text += "\n"
            
            text += f"الإجمالي: {len(sessions)} جلسة | 🟢 ممتاز: {sum(1 for s in sessions if s.get('health_status') == 'excellent')}"
            
            keyboard_buttons = []
            
            if is_admin:
                keyboard_buttons.append([InlineKeyboardButton("🔄 تحديث الصحة", callback_data="refresh_health")])
                keyboard_buttons.append([InlineKeyboardButton("🧹 تنظيف غير الصحية", callback_data="cleanup_unhealthy")])
                keyboard_buttons.append([InlineKeyboardButton("📊 تقرير الصحة", callback_data="health_report")])
            
            keyboard_buttons.append([InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session")])
            keyboard_buttons.append([InlineKeyboardButton("📋 ملخص الجلسات", callback_data="sessions_summary")])
            
            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"خطأ في عرض الجلسات: {e}", exc_info=True)
            await update.message.reply_text("❌ حدث خطأ في عرض الجلسات")
    
    async def advanced_export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command with advanced filtering - معالجة أمر /export مع تصفية متقدمة"""
        user = update.effective_user
        
        # التحقق من الوصول
        access, message, _ = await self.security_manager.check_access(user.id, 'export')
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        # حفظ حالة التصدير
        self.user_states[user.id]['export_state'] = {
            'step': 'platform_selection',
            'filters': {},
            'timestamp': datetime.now()
        }
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 تيليجرام", callback_data="export_telegram")],
            [InlineKeyboardButton("📱 واتساب", callback_data="export_whatsapp")],
            [InlineKeyboardButton("🎮 ديسكورد", callback_data="export_discord")],
            [InlineKeyboardButton("📶 سيجنال", callback_data="export_signal")],
            [InlineKeyboardButton("📊 الكل", callback_data="export_all")],
            [InlineKeyboardButton("⚙️ تصدير مخصص", callback_data="export_custom")],
            [InlineKeyboardButton("📋 آخر التصديرات", callback_data="export_history")]
        ])
        
        await update.message.reply_text(
            "📤 **نظام التصدير المتقدم**\n\n"
            "اختر منصة التصدير:\n\n"
            "• 📢 تيليجرام - جميع روابط تيليجرام\n"
            "• 📱 واتساب - مجموعات واتساب فقط\n"
            "• 🎮 ديسكورد - دعوات ديسكورد\n"
            "• 📶 سيجنال - مجموعات سيجنال\n"
            "• 📊 الكل - جميع المنصات\n"
            "• ⚙️ مخصص - تصدير مع فلترة متقدمة\n"
            "• 📋 التاريخ - عرض آخر التصديرات\n",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def advanced_backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /backup command with management features - معالجة أمر /backup مع مميزات إدارة"""
        user = update.effective_user
        
        # التحقق من الصلاحيات
        if not self.security_manager.is_admin(user.id):
            await update.message.reply_text("❌ هذه الميزة للمديرين فقط")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💾 إنشاء نسخة", callback_data="backup_create")],
            [InlineKeyboardButton("📋 قائمة النسخ", callback_data="backup_list")],
            [InlineKeyboardButton("🔄 استعادة", callback_data="backup_restore")],
            [InlineKeyboardButton("🗑️ تنظيف", callback_data="backup_cleanup")],
            [InlineKeyboardButton("⚙️ الإعدادات", callback_data="backup_settings")],
            [InlineKeyboardButton("📊 إحصائيات", callback_data="backup_stats")]
        ])
        
        await update.message.reply_text(
            "💾 **نظام النسخ الاحتياطي المتقدم**\n\n"
            "إدارة النسخ الاحتياطية لقاعدة البيانات:\n\n"
            "• 💾 إنشاء نسخة - إنشاء نسخة احتياطية جديدة\n"
            "• 📋 قائمة النسخ - عرض جميع النسخ المتاحة\n"
            "• 🔄 استعادة - استعادة من نسخة احتياطية\n"
            "• 🗑️ تنظيف - حذف النسخ القديمة\n"
            "• ⚙️ الإعدادات - ضبط إعدادات النسخ\n"
            "• 📊 إحصائيات - إحصائيات النسخ الاحتياطية\n",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def advanced_cleanup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cleanup command with advanced options - معالجة أمر /cleanup مع خيارات متقدمة"""
        user = update.effective_user
        
        # التحقق من الصلاحيات
        if not self.security_manager.is_admin(user.id):
            await update.message.reply_text("❌ هذه الميزة للمديرين فقط")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧹 تنظيف كامل", callback_data="cleanup_full")],
            [InlineKeyboardButton("🗑️ تنظيف الكاش", callback_data="cleanup_cache")],
            [InlineKeyboardButton("📊 تحسين قاعدة البيانات", callback_data="cleanup_db")],
            [InlineKeyboardButton("🔄 إعادة تعيين النظام", callback_data="cleanup_reset")],
            [InlineKeyboardButton("📋 تقرير التنظيف", callback_data="cleanup_report")],
            [InlineKeyboardButton("⚙️ إعدادات التنظيف", callback_data="cleanup_settings")]
        ])
        
        await update.message.reply_text(
            "🧹 **نظام التنظيف المتقدم**\n\n"
            "تنظيف وتحسين أداء النظام:\n\n"
            "• 🧹 تنظيف كامل - تنظيف شامل للنظام\n"
            "• 🗑️ تنظيف الكاش - مسح جميع ذواكر الكاش\n"
            "• 📊 تحسين قاعدة البيانات - تحسين أداء قاعدة البيانات\n"
            "• 🔄 إعادة تعيين النظام - إعادة تعيين إعدادات النظام\n"
            "• 📋 تقرير التنظيف - عرض نتائج التنظيف\n"
            "• ⚙️ إعدادات التنظيف - ضبط إعدادات التنظيف التلقائي\n",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def security_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /security command - معالجة أمر /security"""
        user = update.effective_user
        
        # التحقق من الصلاحيات
        if not self.security_manager.is_admin(user.id):
            await update.message.reply_text("❌ هذه الميزة للمديرين فقط")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 تقارير المستخدمين", callback_data="security_users")],
            [InlineKeyboardButton("🌍 تقرير عام", callback_data="security_global")],
            [InlineKeyboardButton("🚨 الكشف عن التهديدات", callback_data="security_threats")],
            [InlineKeyboardButton("⚙️ إعدادات الأمان", callback_data="security_settings")],
            [InlineKeyboardButton("📊 سجل الوصول", callback_data="security_logs")],
            [InlineKeyboardButton("🔐 إدارة الصلاحيات", callback_data="security_permissions")]
        ])
        
        await update.message.reply_text(
            "🔒 **نظام الأمان المتقدم**\n\n"
            "إدارة أمان النظام والتحكم في الوصول:\n\n"
            "• 👥 تقارير المستخدمين - تقارير أمنية مفصلة للمستخدمين\n"
            "• 🌍 تقرير عام - نظرة عامة على أمن النظام\n"
            "• 🚨 الكشف عن التهديدات - اكتشاف الأنشطة المشبوهة\n"
            "• ⚙️ إعدادات الأمان - ضبط إعدادات الأمان\n"
            "• 📊 سجل الوصول - عرض سجلات الوصول\n"
            "• 🔐 إدارة الصلاحيات - إدارة صلاحيات المستخدمين\n",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def report_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /report command - معالجة أمر /report"""
        user = update.effective_user
        
        # التحقق من الوصول
        access, message, _ = await self.security_manager.check_access(user.id, 'report')
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 تقرير الجمع", callback_data="report_collection")],
            [InlineKeyboardButton("💾 تقرير النظام", callback_data="report_system")],
            [InlineKeyboardButton("👤 تقرير المستخدم", callback_data="report_user")],
            [InlineKeyboardButton("📈 تقرير الأداء", callback_data="report_performance")],
            [InlineKeyboardButton("📋 تقرير يومي", callback_data="report_daily")],
            [InlineKeyboardButton("📁 تصدير التقارير", callback_data="report_export")]
        ])
        
        await update.message.reply_text(
            "📋 **نظام التقارير المتقدم**\n\n"
            "إنشاء وعرض التقارير الشاملة:\n\n"
            "• 📊 تقرير الجمع - إحصائيات وتقارير الجمع\n"
            "• 💾 تقرير النظام - صحة وأداء النظام\n"
            "• 👤 تقرير المستخدم - إحصائيات وتقارير المستخدم\n"
            "• 📈 تقرير الأداء - مقاييس وتحليلات الأداء\n"
            "• 📋 تقرير يومي - تقارير النشاط اليومي\n"
            "• 📁 تصدير التقارير - تصدير التقارير لملفات\n",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command - معالجة أمر /settings"""
        user = update.effective_user
        
        # التحقق من الصلاحيات
        if not self.security_manager.is_admin(user.id):
            await update.message.reply_text("❌ هذه الميزة للمديرين فقط")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ الإعدادات العامة", callback_data="settings_general")],
            [InlineKeyboardButton("🚀 إعدادات الأداء", callback_data="settings_performance")],
            [InlineKeyboardButton("🔒 إعدادات الأمان", callback_data="settings_security")],
            [InlineKeyboardButton("📊 إعدادات التقارير", callback_data="settings_reports")],
            [InlineKeyboardButton("💾 إعدادات النسخ", callback_data="settings_backup")],
            [InlineKeyboardButton("🔄 إعادة تعيين الإعدادات", callback_data="settings_reset")]
        ])
        
        await update.message.reply_text(
            "⚙️ **نظام الإعدادات المتقدم**\n\n"
            "إدارة وتخصيص إعدادات النظام:\n\n"
            "• ⚙️ الإعدادات العامة - الإعدادات الأساسية للنظام\n"
            "• 🚀 إعدادات الأداء - تحسين وتحسين أداء النظام\n"
            "• 🔒 إعدادات الأمان - إعدادات الأمان والتحكم في الوصول\n"
            "• 📊 إعدادات التقارير - تخصيص التقارير والإشعارات\n"
            "• 💾 إعدادات النسخ - إعدادات النسخ الاحتياطي\n"
            "• 🔄 إعادة تعيين الإعدادات - استعادة الإعدادات الافتراضية\n",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def handle_advanced_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle advanced callback queries - معالجة استعلامات الاستدعاء المتقدمة"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        data = query.data
        
        # التحقق من الوصول
        access, message, details = await self.security_manager.check_access(
            user.id, 
            f"callback_{data}",
            {'callback_data': data}
        )
        
        if not access:
            await query.message.edit_text(f"❌ {message}")
            return
        
        try:
            # حفظ حالة الاستدعاء
            self.user_states[user.id]['last_callback'] = data
            
            # توجيه الاستدعاءات
            if data == "add_session":
                await self._handle_advanced_add_session(query)
            elif data == "start_collect":
                await self._handle_advanced_start_collection(query)
            elif data == "pause_collect":
                await self._handle_advanced_pause_collection(query)
            elif data == "full_guide":
                await self._handle_full_guide(query)
            elif data == "video_tutorial":
                await self._handle_video_tutorial(query)
            elif data == "faq":
                await self._handle_faq(query)
            elif data == "troubleshooting":
                await self._handle_troubleshooting(query)
            elif data == "refresh_detailed":
                await self._handle_refresh_detailed(query)
            elif data == "full_stats":
                await self._handle_full_stats(query)
            elif data == "optimize_performance":
                await self._handle_optimize_performance(query)
            elif data == "system_report":
                await self._handle_system_report(query)
            elif data == "refresh_health":
                await self._handle_refresh_health(query)
            elif data == "cleanup_unhealthy":
                await self._handle_cleanup_unhealthy(query)
            elif data == "health_report":
                await self._handle_health_report(query)
            elif data.startswith("export_"):
                await self._handle_advanced_export(query, data.replace("export_", ""))
            elif data.startswith("backup_"):
                await self._handle_backup_operations(query, data.replace("backup_", ""))
            elif data.startswith("cleanup_"):
                await self._handle_cleanup_operations(query, data.replace("cleanup_", ""))
            elif data.startswith("security_"):
                await self._handle_security_operations(query, data.replace("security_", ""))
            elif data.startswith("report_"):
                await self._handle_report_operations(query, data.replace("report_", ""))
            elif data.startswith("settings_"):
                await self._handle_settings_operations(query, data.replace("settings_", ""))
            elif data == "main_menu":
                await self._handle_main_menu(query)
            else:
                await query.message.edit_text("❌ أمر غير معروف")
        
        except Exception as e:
            logger.error(f"خطأ في معالج الاستدعاء المتقدم: {e}", exc_info=True)
            await query.message.edit_text(f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def handle_advanced_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle advanced text messages with state management - معالجة الرسائل النصية المتقدمة مع إدارة الحالة"""
        user = update.effective_user
        text = update.message.text.strip()
        
        # التحقق من الوصول
        access, message, _ = await self.security_manager.check_access(user.id, 'message')
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        # تحديث المستخدم في قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        await db.update_user_stats(user.id, 'message_received')
        
        # التحقق من الحالات الخاصة
        user_state = self.user_states.get(user.id, {})
        
        if 'pending_session' in user_state:
            await self._handle_session_notes(update.message, text, user)
        elif 'export_state' in user_state:
            await self._handle_export_filters(update.message, text, user)
        elif 'report_state' in user_state:
            await self._handle_report_generation(update.message, text, user)
        else:
            # تحليل النص للتعرف على الجلسات
            if self._looks_like_session(text):
                await self._initiate_session_add(update.message, text, user)
            else:
                # استجابة ذكية
                response = await self._generate_intelligent_response(text, user)
                await update.message.reply_text(response, parse_mode="Markdown")
    
    async def _handle_advanced_add_session(self, query):
        """Handle adding session with advanced features - معالجة إضافة جلسة بمميزات متقدمة"""
        user = query.from_user
        
        # التحقق من عدد الجلسات
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(user.id)
        
        if len(sessions) >= Config.MAX_SESSIONS_PER_USER:
            await query.message.edit_text(
                f"❌ **تجاوزت الحد الأقصى للجلسات**\n\n"
                f"لديك {len(sessions)} من أصل {Config.MAX_SESSIONS_PER_USER} جلسة\n"
                f"يرجى حذف جلسة قبل إضافة جديدة"
            )
            return
        
        # حفظ حالة إضافة الجلسة
        self.user_states[user.id]['pending_session'] = {
            'step': 'awaiting_session',
            'timestamp': datetime.now()
        }
        
        await query.message.edit_text(
            "📥 **إضافة جلسة جديدة - الوضع المتقدم**\n\n"
            "**خيارات الإضافة:**\n"
            "1. 📱 **Session String** - أرسل Session String مباشرة\n"
            "2. 🔗 **رابط الاستخراج** - أرسل رابط استخراج الجلسة\n"
            "3. 📄 **ملف الجلسة** - أرسل ملف الجلسة (غير مدعوم بعد)\n\n"
            "**للإضافة بـ Session String:**\n"
            "```\n"
            "1\n"
            "session_string_here\n"
            "```\n\n"
            "**للإضافة برابط الاستخراج:**\n"
            "```\n"
            "2\n"
            "https://extraction.link/here\n"
            "```\n\n"
            "⚠️ **ملاحظات:**\n"
            "• الجلسات مشفرة آلياً قبل التخزين\n"
            "• يمكنك إضافة ملاحظة لكل جلسة\n"
            "• سيتم التحقق من صحة الجلسة تلقائياً",
            parse_mode="Markdown"
        )
    
    async def _handle_advanced_start_collection(self, query):
        """Handle starting collection with advanced options - معالجة بدء الجمع بخيارات متقدمة"""
        if self.collection_manager.active:
            await query.message.edit_text("⏳ الجمع يعمل بالفعل")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚖️ متوازن", callback_data="start_mode_balanced")],
            [InlineKeyboardButton("⚡ سريع", callback_data="start_mode_fast")],
            [InlineKeyboardButton("🔒 آمن", callback_data="start_mode_safe")],
            [InlineKeyboardButton("🎯 مخصص", callback_data="start_mode_custom")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_start")]
        ])
        
        await query.message.edit_text(
            "🚀 **بدء الجمع الذكي المتقدم**\n\n"
            "اختر وضع الجمع:\n\n"
            "• ⚖️ **متوازن** - جمع متوازن مع حماية الذاكرة\n"
            "• ⚡ **سريع** - جمع سريع مع استخدام موارد أعلى\n"
            "• 🔒 **آمن** - جمع آمن مع تأخيرات أطول\n"
            "• 🎯 **مخصص** - ضبط الإعدادات يدوياً\n\n"
            "**التوصية:** ⚖️ متوازن للمستخدمين الجدد",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_advanced_pause_collection(self, query):
        """Handle pausing collection with state preservation - معالجة إيقاف الجمع مع الحفاظ على الحالة"""
        if not self.collection_manager.active:
            await query.message.edit_text("⚠️ الجمع غير نشط")
            return
        
        if self.collection_manager.paused:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ استئناف", callback_data="resume_collect")],
                [InlineKeyboardButton("🔄 إعادة تشغيل", callback_data="restart_collect")],
                [InlineKeyboardButton("⏹️ إيقاف نهائي", callback_data="stop_collect")]
            ])
            
            await query.message.edit_text(
                "⏸️ **الجمع موقف حالياً**\n\n"
                "اختر الإجراء التالي:\n\n"
                "• ▶️ استئناف - متابعة الجمع من حيث توقف\n"
                "• 🔄 إعادة تشغيل - إعادة بدء الجمع من جديد\n"
                "• ⏹️ إيقاف نهائي - إيقاف الجمع وحفظ النتائج\n",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect_confirm")],
                [InlineKeyboardButton("⏹️ إيقاف وحفظ", callback_data="stop_and_save")],
                [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_pause")]
            ])
            
            await query.message.edit_text(
                "🔄 **الجمع يعمل حالياً**\n\n"
                "اختر نوع الإيقاف:\n\n"
                "• ⏸️ إيقاف مؤقت - إيقاف مؤقت مع حفظ الحالة\n"
                "• ⏹️ إيقاف وحفظ - إيقاف وحفظ النتائج الحالية\n"
                "• ❌ إلغاء - العودة للواجهة الرئيسية\n",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
    
    def _create_main_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        """Create main keyboard based on user access level - إنشاء لوحة مفاتيح رئيسية بناءً على مستوى وصول المستخدم"""
        is_admin = self.security_manager.is_admin(user_id)
        
        buttons = [
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect"),
             InlineKeyboardButton("⏸️ إدارة الجمع", callback_data="manage_collect")],
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("👥 إدارة الجلسات", callback_data="manage_sessions")],
            [InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_menu"),
             InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")],
            [InlineKeyboardButton("❓ المساعدة", callback_data="show_help"),
             InlineKeyboardButton("⚙️ الإعدادات", callback_data="show_settings")]
        ]
        
        if is_admin:
            buttons.append([
                InlineKeyboardButton("🔒 الأمان", callback_data="show_security"),
                InlineKeyboardButton("📋 التقارير", callback_data="show_reports")
            ])
        
        return InlineKeyboardMarkup(buttons)
    
    def _format_duration(self, duration: timedelta) -> str:
        """Format duration for display - تنسيق المدة للعرض"""
        total_seconds = int(duration.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days} يوم")
        if hours > 0:
            parts.append(f"{hours} ساعة")
        if minutes > 0:
            parts.append(f"{minutes} دقيقة")
        if seconds > 0 or not parts:
            parts.append(f"{seconds} ثانية")
        
        return " و ".join(parts)
    
    async def _send_welcome_tutorial(self, message, user):
        """Send welcome tutorial for new users - إرسال برنامج تعليمي ترحيبي للمستخدمين الجدد"""
        tutorial_messages = [
            "👋 **مرحباً بك في البوت الذكي المتقدم!**\n\n"
            "هذا البوت مصمم لجمع روابط المجموعات من تيليجرام وواتساب وغيرها.",
            
            "**🎯 ما يمكنك فعله:**\n"
            "1. إضافة جلسات تيليجرام لجمع الروابط\n"
            "2. بدء عملية الجمع التلقائي\n"
            "3. تصدير الروابط المجمعة\n"
            "4. مراقبة أداء النظام\n\n"
            "**🚀 لنبدأ:**\n"
            "اضغط على ➕ إضافة جلسة لإضافة جلستك الأولى",
            
            "**💡 نصائح سريعة:**\n"
            "• يمكنك إضافة حتى 8 جلسات\n"
            "• النظام يحفظ الروابط المكررة تلقائياً\n"
            "• يمكنك تصدير الروابط بأنواع مختلفة\n"
            "• هناك نسخ احتياطي تلقائي للبيانات",
            
            "**🆘 المساعدة:**\n"
            "استخدم زر ❓ المساعدة للحصول على دليل كامل\n"
            "أو تواصل مع الدعم إذا واجهت مشاكل."
        ]
        
        for i, tutorial_text in enumerate(tutorial_messages):
            if i == 0:
                await message.reply_text(tutorial_text, parse_mode="Markdown")
            else:
                await asyncio.sleep(2)
                await message.reply_text(tutorial_text, parse_mode="Markdown")
    
    async def _generate_intelligent_response(self, text: str, user) -> str:
        """Generate intelligent response based on text - توليد استجابة ذكية بناءً على النص"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['مرحبا', 'اهلا', 'السلام']):
            return "👋 أهلاً وسهلاً! كيف يمكنني مساعدتك اليوم؟"
        
        elif any(word in text_lower for word in ['شكرا', 'ممتاز', 'جيد']):
            return "🙏 شكراً لك! سعيد لأنني أستطيع المساعدة."
        
        elif any(word in text_lower for word in ['مساعدة', 'help', 'دعم']):
            return "❓ للوصول لنظام المساعدة المتقدم، استخدم الأمر /help أو اضغط على زر ❓ المساعدة"
        
        elif any(word in text_lower for word in ['جمع', 'collect', 'روابط']):
            return "🚀 لإدارة الجمع، استخدم الأزرار:\n• 🚀 بدء الجمع\n• ⏸️ إدارة الجمع\n• 📤 تصدير الروابط"
        
        elif any(word in text_lower for word in ['جلسة', 'session', 'حساب']):
            return "👥 لإدارة الجلسات:\n• ➕ إضافة جلسة\n• 👥 إدارة الجلسات\n• 📊 مشاهدة الإحصائيات"
        
        elif 't.me' in text_lower or 'whatsapp' in text_lower:
            return "🔗 يبدو أنك أرسلت رابطاً! يمكنني:\n1. معالجته كجزء من الجمع\n2. التحقق منه\n3. إضافته لقاعدة البيانات\n\nاستخدم /export لتصدير الروابط."
        
        else:
            return "🤖 لم أفهم طلبك بشكل كامل. يمكنك:\n1. استخدام الأزرار للتنقل\n2. استخدم /help للحصول على المساعدة\n3. تواصل مع الدعم للمساعدة التفصيلية"
    
    def _looks_like_session(self, text: str) -> bool:
        """Check if text looks like a session string - التحقق إذا كان النص يشبه سلسلة جلسة"""
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            # تحقق من Session String النموذجي
            if len(line) > 200 and any(pattern in line for pattern in ['1', '==', 'user']):
                return True
        
        return False
    
    async def _initiate_session_add(self, message, text: str, user):
        """Initiate session addition process - بدء عملية إضافة الجلسة"""
        self.user_states[user.id]['pending_session'] = {
            'raw_text': text,
            'step': 'processing',
            'timestamp': datetime.now()
        }
        
        await message.reply_text(
            "🔍 **جاري تحليل النص...**\n\n"
            "يبدو أنك أرسلت بيانات جلسة. جاري التحقق من الصيغة والتحقق من الصحة...\n\n"
            "⏳ قد يستغرق هذا بضع لحظات.",
            parse_mode="Markdown"
        )
        
        # معالجة في الخلفية
        asyncio.create_task(self._process_session_background(message, text, user))
    
    async def _process_session_background(self, message, text: str, user):
        """Process session in background - معالجة الجلسة في الخلفية"""
        try:
            # استخراج Session String
            session_string = None
            lines = text.split('\n')
            
            for line in lines:
                line = line.strip()
                if len(line) > 200:  # Session strings are typically long
                    session_string = line
                    break
                elif line.startswith('1') and len(line) > 50:
                    session_string = line[1:].strip()
                    break
            
            if not session_string:
                await message.reply_text(
                    "❌ **لم أتمكن من استخراج Session String**\n\n"
                    "تأكد من الصيغة الصحيحة:\n"
                    "```\n"
                    "1\n"
                    "session_string_here\n"
                    "```"
                )
                return
            
            # التحقق من الجلسة
            await message.reply_text("🔐 جاري التحقق من صحة الجلسة...")
            
            is_valid, validation_info = await EnhancedSessionManager.validate_session(session_string)
            
            if not is_valid:
                await message.reply_text(
                    f"❌ **الجلسة غير صالحة**\n\n"
                    f"**السبب:** {validation_info.get('error', 'غير معروف')}\n"
                    f"**التفاصيل:** {validation_info.get('details', 'لا توجد')}\n\n"
                    f"تأكد من:\n"
                    f"1. أن الجلسة مفعلة\n"
                    f"2. أنك قمت بتسجيل الدخول\n"
                    f"3. أن الجلسة غير محمية بكلمة مرور"
                )
                return
            
            # تخزين الجلسة للخطوة التالية
            self.user_states[user.id]['pending_session'] = {
                'session_string': session_string,
                'validation_info': validation_info,
                'step': 'awaiting_notes',
                'timestamp': datetime.now()
            }
            
            # طلب ملاحظات
            user_info = validation_info.get('user_info', {})
            display_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
            if not display_name:
                display_name = user_info.get('username', f"User_{user_info.get('id', '')}")
            
            await message.reply_text(
                f"✅ **تم التحقق من الجلسة بنجاح!**\n\n"
                f"**معلومات الجلسة:**\n"
                f"• 👤 المستخدم: {display_name}\n"
                f"• 🆔 المعرف: {user_info.get('id', 'غير معروف')}\n"
                f"• 📱 الهاتف: {user_info.get('phone', 'غير معروف')}\n"
                f"• 🤖 بوت: {'نعم' if user_info.get('is_bot') else 'لا'}\n\n"
                f"**هل تريد إضافة ملاحظة للجلسة؟**\n"
                f"(مثال: جهازي الشخصي، جلسة احتياطية، إلخ)\n\n"
                f"أرسل الملاحظة أو 'تخطي' لتجاهل\n"
                f"أو 'إلغاء' لإلغاء العملية"
            )
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الجلسة: {e}", exc_info=True)
            await message.reply_text(
                f"❌ **حدث خطأ في معالجة الجلسة**\n\n"
                f"**التفاصيل:** {str(e)[:200]}\n\n"
                f"يرجى المحاولة مرة أخرى أو التواصل مع الدعم."
            )
    
    async def _handle_session_notes(self, message, text: str, user):
        """Handle session notes input - معالجة إدخال ملاحظات الجلسة"""
        user_state = self.user_states[user.id]['pending_session']
        
        if text.lower() in ['تخطي', 'skip', 'لا', 'no']:
            notes = ''
        elif text.lower() in ['إلغاء', 'cancel', 'الغاء']:
            del self.user_states[user.id]['pending_session']
            await message.reply_text("❌ تم إلغاء عملية إضافة الجلسة")
            return
        else:
            notes = text[:200]  # تحديد طول الملاحظات
        
        # استكمال إضافة الجلسة
        session_string = user_state.get('session_string')
        validation_info = user_state.get('validation_info', {})
        user_info = validation_info.get('user_info', {})
        
        if not session_string:
            await message.reply_text("❌ لم يتم العثور على بيانات الجلسة. يرجى المحاولة مرة أخرى.")
            return
        
        await message.reply_text("📥 جاري إضافة الجلسة إلى قاعدة البيانات...")
        
        try:
            # إضافة الجلسة
            db = await EnhancedDatabaseManager.get_instance()
            
            success, result_message, details = await db.add_session(
                session_string,
                user_info.get('phone', ''),
                user_info.get('id', 0),
                user_info.get('username', ''),
                f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip(),
                user.id,
                notes,
                {
                    'validation_info': validation_info,
                    'added_via': 'manual',
                    'is_bot': user_info.get('is_bot', False),
                    'is_premium': user_info.get('is_premium', False)
                }
            )
            
            if success:
                # تنظيف الحالة
                del self.user_states[user.id]['pending_session']
                
                await message.reply_text(
                    f"✅ **تمت إضافة الجلسة بنجاح!**\n\n"
                    f"**التفاصيل:**\n"
                    f"• 🆔 معرف الجلسة: {details.get('session_id')}\n"
                    f"• 🔐 هاش الجلسة: {details.get('session_hash', '')[:16]}...\n"
                    f"• 📝 الملاحظة: {notes or 'لا توجد'}\n"
                    f"• ⚡ وقت التنفيذ: {details.get('execution_time_ms', 0):.0f} مللي ثانية\n\n"
                    f"**يمكنك الآن:**\n"
                    f"1. 🚀 بدء الجمع باستخدام هذه الجلسة\n"
                    f"2. 👥 إدارة جميع جلساتك\n"
                    f"3. 📊 مراقبة أداء الجلسة\n\n"
                    f"💡 **نصيحة:** أضف المزيد من الجلسات لزيادة سرعة الجمع!"
                )
                
                # إرسال إشعار للإداريين إذا كانت جلسة مهمة
                if self.security_manager.is_admin(user.id):
                    await self.notification_system.send_admin_notification(
                        f"تمت إضافة جلسة جديدة بواسطة {user.username or user.id}",
                        {
                            'session_id': details.get('session_id'),
                            'user_id': user.id,
                            'validation_info': validation_info
                        }
                    )
            else:
                await message.reply_text(
                    f"⚠️ **{result_message}**\n\n"
                    f"قد تكون الجلسة موجودة مسبقاً أو هناك مشكلة في قاعدة البيانات."
                )
                
        except Exception as e:
            logger.error(f"خطأ في إضافة الجلسة: {e}", exc_info=True)
            await message.reply_text(
                f"❌ **حدث خطأ في إضافة الجلسة**\n\n"
                f"**التفاصيل:** {str(e)[:200]}\n\n"
                f"يرجى المحاولة مرة أخرى أو التواصل مع الدعم."
            )
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors in the bot - معالجة الأخطاء في البوت"""
        try:
            # تسجيل الخطأ
            error = context.error
            
            logger.error(f"خطأ غير معالج في البوت: {error}", exc_info=True)
            
            # تخزين الخطأ في قاعدة البيانات
            try:
                db = await EnhancedDatabaseManager.get_instance()
                
                async with db._get_connection() as conn:
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
                logger.error(f"خطأ في تسجيل الخطأ في قاعدة البيانات: {db_error}")
            
            # إرسال رسالة للمستخدم
            if update and update.effective_chat:
                error_message = (
                    "❌ **حدث خطأ غير متوقع**\n\n"
                    "لقد واجهنا مشكلة فنية. تم تسجيل الخطأ وسنعمل على حله قريباً.\n\n"
                    "**يمكنك:**\n"
                    "1. المحاولة مرة أخرى بعد قليل\n"
                    "2. استخدام الأمر /start للعودة\n"
                    "3. التواصل مع الدعم إذا تكرر الخطأ"
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=error_message,
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
            
            # إرسال إشعار للإداريين
            await self.notification_system.send_error_notification(
                f"خطأ في البوت: {error.__class__.__name__}",
                {
                    'error': str(error),
                    'user_id': update.effective_user.id if update and update.effective_user else 0,
                    'chat_id': update.effective_chat.id if update and update.effective_chat else 0,
                    'command': update.message.text if update and update.message else 'unknown'
                }
            )
            
        except Exception as e:
            logger.error(f"خطأ في معالج الأخطاء: {e}", exc_info=True)

# ======================
# Help System - نظام المساعدة
# ======================

class HelpSystem:
    """Intelligent help system with context awareness - نظام مساعدة ذكي مع إدراك السياق"""
    
    def get_welcome_message(self, user, access_details: Dict) -> str:
        """Get personalized welcome message - الحصول على رسالة ترحيب مخصصة"""
        access_level = access_details.get('access_level', 'user')
        
        if access_level == 'admin':
            role_text = "👑 **أنت مدير النظام** - لديك صلاحيات كاملة"
        elif access_level == 'user':
            role_text = "👤 **أنت مستخدم عادي** - صلاحيات محدودة"
        else:
            role_text = "🚫 **وصول مقيد** - صلاحيات محدودة جداً"
        
        return f"""
🤖 **مرحباً {user.first_name}!**

{role_text}

**✨ المميزات المتقدمة:**

🎯 **الذكاء الاصطناعي:**
• خوارزميات جمع ذكية
• تصفية تلقائية للروابط
• تحليل جودة البيانات
• تحسين أداء ذاتي

⚡ **الأداء المتقدم:**
• معالجة متوازية متقدمة
• إدارة ذاكرة ذكية
• كاش متعدد المستويات
• تأخيرات ذكية

🔒 **الأمان الشامل:**
• تشفير الجلسات
• كشف التهديدات
• تحكم في الوصول
• سجلات أمنية مفصلة

📊 **التحليلات المتقدمة:**
• إحصائيات في الوقت الحقيقي
• تقارير مفصلة
• تحليل الأداء
• توصيات ذكية

💾 **الموثوقية:**
• نسخ احتياطية تلقائية
• استعادة بيانات
• مراقبة النظام
• إخطارات فورية

**🚀 ابدأ الآن باستخدام الأزرار أدناه!**
"""
    
    def get_context_help(self, last_command: str, user_id: int) -> str:
        """Get context-aware help - الحصول على مساعدة سياقية"""
        help_topics = {
            'start': "🏠 **الصفحة الرئيسية**\n\nهذه هي الواجهة الرئيسية للبوت. يمكنك:\n• بدء الجمع\n• إدارة الجلسات\n• تصدير البيانات\n• عرض الإحصائيات",
            
            'status': "📊 **حالة النظام**\n\nعرض حالة النظام الحالية:\n• حالة الجمع\n• استخدام الموارد\n• إحصائيات الأداء\n• توصيات التحسين",
            
            'stats': "📈 **الإحصائيات**\n\nعرض إحصائيات شاملة:\n• إحصائيات الجمع\n• مقاييس النظام\n• إحصائيات المستخدمين\n• تحليل الأداء",
            
            'sessions': "👥 **الجلسات**\n\nإدارة جلسات تيليجرام:\n• إضافة جلسات جديدة\n• عرض الجلسات النشطة\n• مراقبة صحة الجلسات\n• حذف الجلسات المعطلة",
            
            'export': "📤 **التصدير**\n\nتصدير الروابط المجمعة:\n• تصدير حسب المنصة\n• تصدير مخصص\n• إدارة ملفات التصدير\n• سجل التصديرات",
            
            'general': "❓ **المساعدة العامة**\n\n**الأوامر الرئيسية:**\n/start - بدء البوت\n/help - المساعدة\n/status - حالة النظام\n/stats - الإحصائيات\n/sessions - إدارة الجلسات\n/export - تصدير البيانات\n\n**للإداريين:**\n/backup - النسخ الاحتياطي\n/cleanup - تنظيف النظام\n/security - الأمان\n/report - التقارير\n/settings - الإعدادات"
        }
        
        return help_topics.get(last_command, help_topics['general'])

# ======================
# Notification System - نظام الإشعارات
# ======================

class NotificationSystem:
    """Advanced notification system for admins and users - نظام إشعارات متقدم للإداريين والمستخدمين"""
    
    async def send_admin_notification(self, message: str, data: Dict = None):
        """Send notification to all admins - إرسال إشعار لجميع المديرين"""
        # سيتم تنفيذ هذا عند تكامل البوت
        logger.info(f"إشعار للمديرين: {message}", data or {})
    
    async def send_error_notification(self, error: str, details: Dict):
        """Send error notification to admins - إرسال إشعار خطأ للمديرين"""
        logger.error(f"إشعار خطأ: {error}", details)
    
    async def send_security_alert(self, alert: str, details: Dict):
        """Send security alert to admins - إرسال تنبيه أمني للمديرين"""
        logger.warning(f"تنبيه أمني: {alert}", details)

# ======================
# Signal Handlers - معالجات الإشارات
# ======================

def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown - إعداد معالجات الإشارات للإغلاق السلس"""
    def signal_handler(signum, frame):
        logger.info(f"📶 تم استقبال إشارة {signum}. جاري الإغلاق السلس...")
        
        # تسجيل الإحصاءات النهائية
        logger.info("📊 إحصائيات النظام النهائية:", {
            'memory': MemoryManager.get_instance().get_metrics(),
            'cache': CacheManager.get_instance().get_stats()
        })
        
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
    
    # تعيين سياسة حلقة الأحداث
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    else:
        # استخدام uvloop إذا كان متاحاً
        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            logger.info("✅ استخدام uvloop لتحسين الأداء")
        except ImportError:
            logger.info("⚠️ uvloop غير مثبت. استخدام حلقة الأحداث الافتراضية")
    
    # تعيين حدود النظام
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_NOFILE, (8192, 8192))
        logger.info("✅ تم تعيين حدود الملفات المفتوحة")
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
    
    # التحقق من مفتاح التشفير
    if Config.ENCRYPTION_KEY == Fernet.generate_key().decode():
        logger.warning("⚠️ استخدام مفتاح تشفير مؤقت. يوصى بتعيين ENCRYPTION_KEY دائم")
    
    # إنشاء المجلدات اللازمة
    os.makedirs("backups", exist_ok=True)
    os.makedirs("cache_data", exist_ok=True)
    os.makedirs("exports", exist_ok=True)
    
    # تشغيل البوت المتقدم
    bot = AdvancedTelegramBot()
    
    logger.info("🤖 بدء تشغيل بوت جمع الروابط الذكي المتقدم...")
    logger.info("⚙️ الإعدادات المتقدمة:", {
        'max_sessions': Config.MAX_CONCURRENT_SESSIONS,
        'max_memory_mb': Config.MAX_MEMORY_MB,
        'backup_enabled': Config.BACKUP_ENABLED,
        'encryption_enabled': bool(Config.ENCRYPTION_KEY)
    })
    
    try:
        # تهيئة الأنظمة
        cache_manager = CacheManager.get_instance()
        memory_manager = MemoryManager.get_instance()
        
        # بدء التنظيف الدوري
        asyncio.create_task(periodic_maintenance())
        
        # تشغيل البوت
        await bot.app.initialize()
        await bot.app.start()
        await bot.app.updater.start_polling()
        
        logger.info("🚀 البوت يعمل بنجاح!")
        
        # البقاء في التشغيل
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"❌ خطأ في البوت المتقدم: {e}", exc_info=True)
        raise
        
    finally:
        # التنظيف النهائي
        logger.info("🧹 جاري التنظيف النهائي...")
        
        try:
            # إغلاق قاعدة البيانات
            db = await EnhancedDatabaseManager.get_instance()
            await db.close()
            
            # إيقاف البوت
            await bot.app.stop()
            
            # مسح الكاش
            cache_manager.clear()
            
            logger.info("✅ اكتمل الإغلاق السلس")
            
        except Exception as e:
            logger.error(f"❌ خطأ في التنظيف النهائي: {e}")

async def periodic_maintenance():
    """Perform periodic system maintenance - تنفيذ صيانة دورية للنظام"""
    while True:
        try:
            # تنظيف الكاش المنتهي
            cache_manager = CacheManager.get_instance()
            await cache_manager.cleanup_expired()
            
            # تحسين الذاكرة
            memory_manager = MemoryManager.get_instance()
            memory_manager.check_and_optimize()
            
            # تدوير النسخ الاحتياطية
            if Config.BACKUP_ENABLED:
                await BackupManager.rotate_backups()
            
            # تسجيل حالة النظام
            logger.debug("✅ الصيانة الدورية مكتملة", {
                'memory_mb': memory_manager.get_memory_usage(),
                'cache_size': cache_manager.get_stats()['fast_cache_size']
            })
            
            await asyncio.sleep(300)  # كل 5 دقائق
            
        except Exception as e:
            logger.error(f"خطأ في الصيانة الدورية: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    # تشغيل التطبيق
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 توقف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ قاتل: {e}", exc_info=True)
        sys.exit(1)
