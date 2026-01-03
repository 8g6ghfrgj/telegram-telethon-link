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
    MAX_MEMORY_MB = 500
    
    # Performance settings - إعدادات الأداء
    MAX_CONCURRENT_SESSIONS = 5
    REQUEST_DELAYS = {
        'normal': 1.0,
        'join_request': 5.0,  # تقليل من 30 إلى 5 ثواني
        'search': 2.0,
        'flood_wait': 5.0,
        'between_sessions': 2.0,
        'between_tasks': 0.3,
        'min_cycle_delay': 10.0,  # تقليل من 15 إلى 10
        'max_cycle_delay': 45.0,  # تقليل من 60 إلى 45
        'validation_delay': 2.0    # تأخير جديد للتحقق
    }
    
    # Collection limits - حدود الجمع
    MAX_DIALOGS_PER_SESSION = 50
    MAX_MESSAGES_PER_SEARCH = 10
    MAX_SEARCH_TERMS = 8
    MAX_LINKS_PER_CYCLE = 200      # زيادة من 150 إلى 200
    MAX_BATCH_SIZE = 50
    
    # Database - قاعدة البيانات
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10
    DB_POOL_SIZE = 5
    
    # WhatsApp collection - جمع واتساب
    WHATSAPP_DAYS_BACK = 30
    
    # Link verification - التحقق من الروابط
    MIN_GROUP_MEMBERS = 3
    MAX_LINK_LENGTH = 200
    VALIDATION_TIMEOUT = 30        # وقت انتهاء التحقق
    
    # Rate limiting - الحد من الطلبات
    USER_RATE_LIMIT = {
        'max_requests': 15,
        'per_seconds': 60
    }
    
    # Session management - إدارة الجلسات
    SESSION_TIMEOUT = 600
    MAX_SESSIONS_PER_USER = 8
    
    # Export - التصدير
    MAX_EXPORT_LINKS = 10000
    EXPORT_CHUNK_SIZE = 1000
    
    # Advanced settings - إعدادات متقدمة
    TELEGRAM_NO_TIME_LIMIT = True   # جمع تيليجرام بدون قيود زمنية
    JOIN_REQUEST_CHECK_DELAY = 30   # 30 ثانية لفحص طلبات الانضمام
    ENABLE_ADVANCED_VALIDATION = True  # تمكين التحقق المتقدم

# ======================
# Enhanced Link Processor - معالج الروابط المحسن
# ======================

class EnhancedLinkProcessor:
    """Advanced link processing with improved Telegram detection - معالجة روابط متقدمة مع تحسين كشف تيليجرام"""
    
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
        """Normalize URL with enhanced Telegram handling - توحيد الرابط مع معالجة تيليجرام محسنة"""
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
        """Extract comprehensive information from URL with enhanced Telegram detection - استخراج معلومات شاملة مع كشف تيليجرام محسن"""
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
        """Extract Telegram specific information with improved detection - استخراج معلومات تيليجرام خاصة مع كشف محسن"""
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
            'is_active': True  # افتراضي نشط
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
            result['is_group'] = True  # افتراضي مجموعة
            
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
    async def validate_telegram_link_advanced(client: TelegramClient, url: str, 
                                              check_join_request: bool = True) -> Dict:
        """Validate Telegram link with advanced checking including join requests - التحقق من رابط تيليجرام مع فحص متقدم يشمل طلبات الانضمام"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            details = url_info['details']
            
            if not url_info['is_valid']:
                return {
                    'is_valid': False,
                    'reason': 'رابط غير صالح',
                    'type': 'invalid',
                    'is_active': False
                }
            
            # التحقق من طلبات الانضمام
            if details.get('is_join_request') and check_join_request:
                return await EnhancedLinkProcessor._validate_join_request(client, url, details)
            
            # التحقق من المجموعات والقنوات العامة
            if details.get('username') and not details.get('is_channel'):
                try:
                    entity = await client.get_entity(details['username'])
                    
                    # تحديد النوع بدقة
                    if isinstance(entity, types.Channel):
                        if entity.broadcast:
                            return {
                                'is_valid': True,
                                'type': 'channel',
                                'is_channel': True,
                                'is_broadcast': True,
                                'title': entity.title,
                                'members': getattr(entity, 'participants_count', 0),
                                'is_active': True,
                                'requires_join': False
                            }
                        else:
                            return {
                                'is_valid': True,
                                'type': 'supergroup',
                                'is_group': True,
                                'is_supergroup': True,
                                'title': entity.title,
                                'members': getattr(entity, 'participants_count', 0),
                                'is_active': True,
                                'requires_join': False
                            }
                    elif isinstance(entity, types.Chat):
                        return {
                            'is_valid': True,
                            'type': 'group',
                            'is_group': True,
                            'title': entity.title,
                            'members': getattr(entity, 'participants_count', 0),
                            'is_active': True,
                            'requires_join': False
                            }
                    
                except UsernameNotOccupiedError:
                    return {
                        'is_valid': False,
                        'reason': 'المستخدم/المجموعة غير موجودة',
                        'type': 'invalid',
                        'is_active': False
                    }
                except UserNotParticipantError:
                    return {
                        'is_valid': True,
                        'type': 'private_group',
                        'is_group': True,
                        'is_private': True,
                        'requires_join': True,
                        'is_active': True
                    }
                except ChatWriteForbiddenError:
                    return {
                        'is_valid': True,
                        'type': 'private_group',
                        'is_group': True,
                        'is_private': True,
                        'requires_join': True,
                        'is_active': True
                    }
                except Exception as e:
                    logger.debug(f"خطأ في التحقق من {details['username']}: {e}")
            
            # إذا لم يكن لدينا معلومات كافية، نعتبره رابطاً صالحاً
            return {
                'is_valid': True,
                'type': details.get('is_channel', False) and 'channel' or 'group',
                'is_channel': details.get('is_channel', False),
                'is_group': details.get('is_group', True),
                'is_active': True,
                'requires_join': details.get('is_join_request', False) or details.get('is_private', False)
            }
            
        except Exception as e:
            logger.error(f"خطأ في التحقق المتقدم للرابط {url}: {e}")
            return {
                'is_valid': False,
                'reason': f'خطأ في التحقق: {str(e)[:100]}',
                'type': 'error',
                'is_active': False
            }
    
    @staticmethod
    async def _validate_join_request(client: TelegramClient, url: str, details: Dict) -> Dict:
        """Validate join request link specifically - التحقق من رابط طلب الانضمام بشكل خاص"""
        try:
            invite_hash = details.get('invite_hash', '')
            if not invite_hash:
                return {
                    'is_valid': False,
                    'reason': 'لا يوجد هاش دعوة',
                    'type': 'invalid_join',
                    'is_active': False
                }
            
            # محاولة الحصول على معلومات الدعوة
            try:
                invite = await client(functions.messages.CheckChatInviteRequest(
                    hash=invite_hash
                ))
                
                if isinstance(invite, types.ChatInviteAlready):
                    # المستخدم بالفعل في الدردشة
                    chat = invite.chat
                    is_channel = isinstance(chat, types.Channel) and chat.broadcast
                    
                    return {
                        'is_valid': True,
                        'type': 'channel' if is_channel else 'group',
                        'is_channel': is_channel,
                        'is_group': not is_channel,
                        'title': chat.title,
                        'members': getattr(chat, 'participants_count', 0),
                        'is_active': True,
                        'requires_join': False,
                        'join_request_valid': True
                    }
                    
                elif isinstance(invite, types.ChatInvite):
                    # دعوة صالحة
                    is_channel = invite.channel and invite.broadcast
                    
                    return {
                        'is_valid': True,
                        'type': 'channel' if is_channel else 'group',
                        'is_channel': is_channel,
                        'is_group': not is_channel,
                        'title': invite.title,
                        'members': invite.participants_count,
                        'is_active': True,
                        'requires_join': True,
                        'join_request_valid': True,
                        'is_megagroup': invite.megagroup
                    }
                    
                else:
                    return {
                        'is_valid': False,
                        'reason': 'نوع دعوة غير معروف',
                        'type': 'unknown_invite',
                        'is_active': False
                    }
                    
            except InviteHashInvalidError:
                return {
                    'is_valid': False,
                    'reason': 'هاش الدعوة غير صالح',
                    'type': 'invalid_hash',
                    'is_active': False
                }
            except InviteHashExpiredError:
                return {
                    'is_valid': False,
                    'reason': 'الدعوة منتهية',
                    'type': 'expired_invite',
                    'is_active': False
                }
            except Exception as e:
                logger.debug(f"خطأ في فحص الدعوة {invite_hash}: {e}")
        
        except Exception as e:
            logger.error(f"خطأ في التحقق من طلب الانضمام {url}: {e}")
        
        # إذا فشل التحقق، نعتبره رابط انضمام صالح
        return {
            'is_valid': True,
            'type': 'group',  # افتراضي مجموعة
            'is_group': True,
            'is_active': True,
            'requires_join': True,
            'join_request_valid': True
        }
    
    @staticmethod
    def _extract_whatsapp_info(url: str, parsed) -> Dict:
        """Extract WhatsApp specific information - استخراج معلومات واتساب خاصة"""
        result = {
            'is_valid': False,
            'group_id': '',
            'is_group': True,
            'is_active': True
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
            'is_invite': True,
            'is_active': True
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
            'is_group': True,
            'is_active': True
        }
        
        path = parsed.path.strip('/')
        if path:
            result['group_id'] = path
            result['is_valid'] = True
        
        return result

# ======================
# Enhanced Database Manager - مدير قاعدة البيانات المحسن
# ======================

class EnhancedDatabaseManager:
    """Advanced database management with improved link handling - إدارة قاعدة بيانات متقدمة مع معالجة روابط محسنة"""
    
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
            await conn.execute("PRAGMA cache_size = -20000")
            await conn.execute("PRAGMA temp_store = MEMORY")
            await conn.execute("PRAGMA mmap_size = 1073741824")
            await conn.execute("PRAGMA optimize")
            
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
            
            # جدول الروابط المحسن مع تفاصيل أكثر
            await conn.execute('''
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
            
            # جدول جديد: روابط الانضمام المؤقتة
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS pending_join_links (
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
        
        async with self._get_connection() as conn:
            for index_name, index_sql in indexes:
                try:
                    await conn.execute(f'CREATE INDEX IF NOT EXISTS {index_name} ON {index_sql}')
                except Exception as e:
                    logger.error(f"خطأ في إنشاء الفهرس {index_name}: {e}", exc_info=True)
    
    async def add_link_enhanced(self, link_info: Dict) -> Tuple[bool, str, Dict]:
        """Add link with enhanced Telegram information - إضافة رابط مع معلومات تيليجرام محسنة"""
        try:
            # استخراج معلومات الرابط
            url = link_info.get('url', '')
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return False, "رابط غير صالح", {}
            
            details = url_info['details']
            
            async with self._get_connection() as conn:
                # التحقق من التكرار
                cursor = await conn.execute(
                    'SELECT id FROM links WHERE url_hash = ?',
                    (url_info['url_hash'],)
                )
                existing = await cursor.fetchone()
                
                if existing:
                    return False, "الرابط موجود مسبقاً", {'link_id': existing[0]}
                
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
                ''', tuple(link_data.values()))
                
                link_id = cursor.lastrowid
                
                await conn.commit()
                
                # تحديث إحصائيات المستخدم
                if link_data['added_by_user']:
                    await self.update_user_stats(link_data['added_by_user'], 'link_added')
                
                return True, "تمت إضافة الرابط بنجاح", {
                    'link_id': link_id,
                    'url_hash': url_info['url_hash']
                }
                
        except Exception as e:
            logger.error(f"خطأ في إضافة الرابط المحسن: {e}", exc_info=True)
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def add_pending_join_link(self, url: str, platform: str = 'telegram', metadata: Dict = None) -> Tuple[bool, str, Dict]:
        """Add pending join link for later verification - إضافة رابط انضمام مؤقت للتحقق لاحقاً"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return False, "رابط غير صالح", {}
            
            async with self._get_connection() as conn:
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
                    return False, "الرابط موجود مسبقاً في قائمة الانتظار", {'pending_id': existing[0]}
                
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
                
                return True, "تمت إضافة الرابط لقائمة الانتظار", {
                    'pending_id': pending_id,
                    'url_hash': url_info['url_hash']
                }
                
        except Exception as e:
            logger.error(f"خطأ في إضافة رابط انتظار: {e}")
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def get_pending_join_links(self, limit: int = 50) -> List[Dict]:
        """Get pending join links for verification - الحصول على روابط الانضمام المؤقتة للتحقق"""
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute('''
                    SELECT * FROM pending_join_links 
                    WHERE status = 'pending' 
                    ORDER BY last_checked ASC NULLS FIRST, added_date ASC
                    LIMIT ?
                ''', (limit,))
                
                rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                
                pending_links = []
                for row in rows:
                    pending_dict = dict(zip(columns, row))
                    if pending_dict.get('metadata'):
                        pending_dict['metadata'] = json.loads(pending_dict['metadata'])
                    pending_links.append(pending_dict)
                
                return pending_links
                
        except Exception as e:
            logger.error(f"خطأ في الحصول على روابط الانتظار: {e}")
            return []
    
    async def update_pending_link_status(self, pending_id: int, status: str, 
                                        metadata: Dict = None, 
                                        check_attempts: int = 1) -> bool:
        """Update pending link status - تحديث حالة رابط الانتظار"""
        try:
            async with self._get_connection() as conn:
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
            logger.error(f"خطأ في تحديث حالة رابط الانتظار: {e}")
            return False
    
    async def get_stats_summary_enhanced(self, detailed: bool = False) -> Dict:
        """Get comprehensive database statistics with Telegram breakdown - الحصول على إحصائيات قاعدة بيانات شاملة مع تفصيل تيليجرام"""
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
            logger.error(f"خطأ في الحصول على ملخص الإحصائيات المحسن: {e}", exc_info=True)
            return {}
    
    async def export_links_enhanced(self, filters: Dict = None, limit: int = Config.MAX_EXPORT_LINKS, 
                                   offset: int = 0) -> Tuple[List[str], Dict]:
        """Export links with enhanced filtering and Telegram classification - تصدير الروابط مع تصفية محسنة وتصنيف تيليجرام"""
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
            
            async with self._get_connection() as conn:
                cursor = await conn.execute(query, params)
                rows = await cursor.fetchall()
                
                # الحصول على العدد الإجمالي
                count_query = query.replace(
                    "SELECT url, platform, link_type, telegram_type, collected_date, members_count, is_channel, is_group, is_supergroup, is_join_request", 
                    "SELECT COUNT(*)"
                )
                count_query = count_query.split("ORDER BY")[0]
                
                count_cursor = await conn.execute(count_query, params[:-2] if filters else [])
                total_count = (await count_cursor.fetchone())[0]
                
                links = [row[0] for row in rows]
                
                metadata = {
                    'total_count': total_count,
                    'exported_count': len(links),
                    'limit': limit,
                    'offset': offset,
                    'filters': filters or {},
                    'platform_distribution': {},
                    'telegram_classification': {
                        'channels': 0,
                        'groups': 0,
                        'supergroups': 0,
                        'join_requests': 0
                    }
                }
                
                # تحليل التصنيف
                if rows:
                    platform_counts = {}
                    for row in rows:
                        platform = row[1]
                        platform_counts[platform] = platform_counts.get(platform, 0) + 1
                        
                        # تصنيف تيليجرام
                        if platform == 'telegram':
                            if row[6]:  # is_channel
                                metadata['telegram_classification']['channels'] += 1
                            if row[7]:  # is_group
                                metadata['telegram_classification']['groups'] += 1
                            if row[8]:  # is_supergroup
                                metadata['telegram_classification']['supergroups'] += 1
                            if row[9]:  # is_join_request
                                metadata['telegram_classification']['join_requests'] += 1
                    
                    metadata['platform_distribution'] = platform_counts
            
            return links, metadata
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الروابط المحسن: {e}", exc_info=True)
            return [], {}
    
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
                elif action == 'link_added':
                    update_query += ', link_count = link_count + ?, total_links_added = total_links_added + ?'
                    params.extend([value, value])
                
                update_query += ' WHERE user_id = ?'
                params.append(user_id)
                
                await conn.execute(update_query, params)
                await conn.commit()
                
        except Exception as e:
            logger.debug(f"خطأ في تحديث إحصائيات المستخدم: {e}")

# ======================
# Advanced Collection Manager - مدير الجمع المتقدم
# ======================

class AdvancedCollectionManager:
    """Advanced collection management with no time limits for Telegram - إدارة جمع متقدمة بدون قيود زمنية لتيليجرام"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        
        self.cache_manager = CacheManager.get_instance()
        self.memory_manager = MemoryManager.get_instance()
        
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
        
        # بدون قيود زمنية لتيليجرام
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
        
        self.task_manager = TaskManager()
        self.rate_limiter = AdvancedRateLimiter()
        self.collection_log = IntelligentLog(max_entries=500)
        
        self.system_state = {
            'memory_pressure': 'low',
            'network_status': 'good',
            'collection_mode': 'balanced',
            'last_health_check': None
        }
        
        self.join_request_queue = asyncio.Queue()
        self.validation_tasks = set()
    
    async def start_collection(self, mode: str = 'balanced'):
        """Start the advanced collection process with improved Telegram collection - بدء عملية الجمع المتقدمة مع جمع تيليجرام محسن"""
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.stats['start_time'] = datetime.now()
        self.stats['cycles_completed'] = 0
        self.stats['current_session'] = self.stats['start_time'].strftime('%Y%m%d_%H%M%S')
        self.system_state['collection_mode'] = mode
        
        logger.info("🚀 بدء عملية الجمع الذكية المتقدمة بدون قيود زمنية لتيليجرام", {
            'mode': mode,
            'start_time': self.stats['start_time'].isoformat(),
            'telegram_no_time_limit': Config.TELEGRAM_NO_TIME_LIMIT
        })
        
        try:
            # بدء أنظمة المراقبة
            self.task_manager.start_monitoring()
            asyncio.create_task(self._system_monitoring())
            asyncio.create_task(self._periodic_maintenance())
            asyncio.create_task(self._adaptive_optimization())
            asyncio.create_task(self._process_join_requests())
            
            while self.active and not self.stop_requested:
                if self.paused:
                    await asyncio.sleep(1)
                    continue
                
                await self._enhanced_collection_cycle()
                
                if self.active and not self.stop_requested:
                    await self._optimize_between_cycles()
                    delay = self._calculate_adaptive_delay()
                    await asyncio.sleep(delay)
        
        except Exception as e:
            logger.error(f"❌ خطأ في عملية الجمع المتقدمة: {e}", exc_info=True)
            self.stats['errors'] += 1
            self.collection_log.add('error', 'fatal', {'error': str(e)})
        
        finally:
            await self._graceful_shutdown()
    
    async def _enhanced_collection_cycle(self):
        """Execute enhanced collection cycle with unlimited Telegram collection - تنفيذ دورة جمع محسنة مع جمع تيليجرام غير محدود"""
        cycle_start = datetime.now()
        cycle_id = f"cycle_{self.stats['cycles_completed']}_{secrets.token_hex(4)}"
        
        logger.info(f"بدء دورة الجمع المحسنة {cycle_id}")
        self.collection_log.add('cycle', 'start', {'cycle_id': cycle_id})
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=Config.MAX_CONCURRENT_SESSIONS * 2)
            
            if not sessions:
                logger.warning("لا توجد جلسات نشطة متاحة")
                self.collection_log.add('cycle', 'no_sessions')
                return
            
            healthy_sessions = [s for s in sessions if s.get('health_status', 'poor') in ['excellent', 'good', 'fair']]
            
            if not healthy_sessions:
                logger.warning("لا توجد جلسات صحية متاحة")
                self.collection_log.add('cycle', 'no_healthy_sessions')
                return
            
            max_sessions = self._calculate_optimal_session_count()
            selected_sessions = healthy_sessions[:max_sessions]
            
            tasks = []
            for i, session in enumerate(selected_sessions):
                if not self.active or self.stop_requested or self.paused:
                    break
                
                task = self._process_session_unlimited(session, i, cycle_id)
                tasks.append(task)
            
            if not tasks:
                return
            
            results = await self.task_manager.execute_tasks(tasks)
            
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
            
            self.collection_log.add('cycle', 'complete', {
                'cycle_id': cycle_id,
                'duration': cycle_duration,
                'sessions_processed': successful,
                'sessions_failed': failed,
                'stats_snapshot': self.stats.copy()
            })
            
            logger.info(f"اكتملت دورة {cycle_id}: {successful} ناجحة، {failed} فاشلة", {
                'duration': cycle_duration,
                'performance_score': self.stats['performance_score'],
                'telegram_collected': self.stats['telegram_public'] + self.stats['telegram_private'] + self.stats['telegram_join']
            })
            
        except Exception as e:
            logger.error(f"خطأ في دورة الجمع المحسنة: {e}", exc_info=True)
            self.stats['errors'] += 1
            self.collection_log.add('cycle', 'error', {'error': str(e)})
    
    async def _process_session_unlimited(self, session: Dict, index: int, cycle_id: str):
        """Process session with unlimited Telegram collection - معالجة جلسة مع جمع تيليجرام غير محدود"""
        session_id = session.get('id')
        session_hash = session.get('session_hash')
        added_by_user = session.get('added_by_user', 0)
        
        logger.info(f"معالجة الجلسة {session_id} في دورة {cycle_id} (جمع غير محدود)", {
            'session_id': session_id,
            'health_status': session.get('health_status'),
            'cycle_id': cycle_id
        })
        
        if index > 0:
            delay = self._calculate_session_delay(index)
            await asyncio.sleep(delay)
        
        try:
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt_session(session.get('session_string', ''))
            actual_session = decrypted_session or session.get('session_string', '')
            
            if not actual_session or actual_session == '********':
                logger.error(f"جلسة {session_id} غير متاحة")
                return {'session_id': session_id, 'status': 'error', 'reason': 'جلسة غير متاحة'}
            
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
                logger.error(f"الجلسة {session_id} غير مصرح بها")
                return {'session_id': session_id, 'status': 'error', 'reason': 'غير مصرح'}
            
            # جمع الروابط بدون قيود زمنية
            collected_links = await self._collect_all_telegram_links(client, session_id, added_by_user, cycle_id)
            
            # تحديث استخدام الجلسة
            db = await EnhancedDatabaseManager.get_instance()
            async with db._get_connection() as conn:
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
            
            await self._update_session_health(session_id, False)
            
            self.collection_log.add('session', 'error', {
                'session_id': session_id,
                'error': str(e)
            })
            
            raise
    
    async def _collect_all_telegram_links(self, client: TelegramClient, session_id: int, 
                                         added_by_user: int, cycle_id: str) -> List[Dict]:
        """Collect all Telegram links without time limits - جمع جميع روابط تيليجرام بدون قيود زمنية"""
        collected = []
        
        strategies = [
            self._strategy_all_dialogs,
            self._strategy_search_all_messages,
            self._strategy_group_messages,
            self._strategy_channel_messages
        ]
        
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
    
    async def _strategy_all_dialogs(self, client: TelegramClient, session_id: int, 
                                   added_by_user: int) -> List[Dict]:
        """Collect from all dialogs (no time limit) - الجمع من جميع الدردشات (بدون حد زمني)"""
        collected = []
        
        try:
            dialogs = []
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                dialogs.append(dialog)
            
            # ترتيب عشوائي لتجنب الأنماط
            import random
            random.shuffle(dialogs)
            
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
                    logger.debug(f"خطأ في معالجة الدردشة: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"خطأ في استراتيجية جميع الدردشات: {e}")
        
        return collected
    
    async def _strategy_search_all_messages(self, client: TelegramClient, session_id: int, 
                                           added_by_user: int) -> List[Dict]:
        """Search for all links in messages (no time limit) - البحث عن جميع الروابط في الرسائل (بدون حد زمني)"""
        collected = []
        
        search_terms = [
            "مجموعة", "قناة", "انضمام", "رابط", "دعوة",
            "group", "channel", "join", "link", "invite",
            "t.me", "telegram.me", "chat.whatsapp.com",
            "discord.gg", "signal.group",
            "https://t.me/", "https://telegram.me/"
        ]
        
        for term in search_terms[:Config.MAX_SEARCH_TERMS]:
            if not self.active or self.stop_requested or self.paused:
                break
            
            try:
                links_found = 0
                
                # البحث في جميع الدردشات
                async for dialog in client.iter_dialogs(limit=20):
                    if not self.active or self.stop_requested or self.paused:
                        break
                    
                    if links_found >= Config.MAX_LINKS_PER_CYCLE // 2:
                        break
                    
                    try:
                        async for message in client.iter_messages(
                            dialog.entity,
                            search=term,
                            limit=Config.MAX_MESSAGES_PER_SEARCH
                        ):
                            if not self.active or self.stop_requested or self.paused:
                                break
                            
                            if message.text:
                                extracted_links = self._extract_all_links(message.text)
                                
                                for raw_url in extracted_links:
                                    if len(collected) >= Config.MAX_LINKS_PER_CYCLE:
                                        return collected
                                    
                                    normalized_url = EnhancedLinkProcessor.normalize_url(raw_url)
                                    cache_key = f"url_{hashlib.md5(normalized_url.encode()).hexdigest()}"
                                    
                                    if await self.cache_manager.exists(cache_key, 'processed_urls'):
                                        continue
                                    
                                    # معالجة الرابط
                                    link_info = await self._process_link_enhanced(
                                        client, normalized_url, session_id, added_by_user, 
                                        message.date if hasattr(message, 'date') else None
                                    )
                                    
                                    if link_info:
                                        collected.append(link_info)
                                        await self.cache_manager.set(cache_key, True, 'processed_urls', 86400)
                                        links_found += 1
                                        
                                        if links_found >= 5:
                                            break
                        
                        await asyncio.sleep(Config.REQUEST_DELAYS['between_tasks'])
                    
                    except Exception as e:
                        logger.debug(f"خطأ في البحث في الدردشة: {e}")
                        continue
                
                await asyncio.sleep(Config.REQUEST_DELAYS['search'])
            
            except Exception as e:
                logger.error(f"خطأ في البحث عن مصطلح '{term}': {e}")
                continue
        
        return collected
    
    async def _strategy_group_messages(self, client: TelegramClient, session_id: int, 
                                      added_by_user: int) -> List[Dict]:
        """Collect links specifically from groups - جمع الروابط من المجموعات بشكل خاص"""
        collected = []
        
        try:
            async for dialog in client.iter_dialogs(limit=30):
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # التحقق إذا كانت مجموعة
                    if isinstance(entity, (types.Channel, types.Chat)):
                        if isinstance(entity, types.Channel) and entity.broadcast:
                            continue  # تخطي القنوات
                        
                        # جمع رسائل المجموعة
                        group_links = await self._collect_from_group_messages(
                            client, entity, session_id, added_by_user
                        )
                        collected.extend(group_links)
                        
                        await asyncio.sleep(Config.REQUEST_DELAYS['normal'] * 2)
                
                except Exception as e:
                    logger.debug(f"خطأ في معالجة المجموعة: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"خطأ في استراتيجية مجموعات الرسائل: {e}")
        
        return collected
    
    async def _strategy_channel_messages(self, client: TelegramClient, session_id: int, 
                                        added_by_user: int) -> List[Dict]:
        """Collect links specifically from channels - جمع الروابط من القنوات بشكل خاص"""
        collected = []
        
        try:
            async for dialog in client.iter_dialogs(limit=20):
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # التحقق إذا كانت قناة
                    if isinstance(entity, types.Channel) and entity.broadcast:
                        channel_links = await self._collect_from_channel_messages(
                            client, entity, session_id, added_by_user
                        )
                        collected.extend(channel_links)
                        
                        await asyncio.sleep(Config.REQUEST_DELAYS['normal'] * 2)
                
                except Exception as e:
                    logger.debug(f"خطأ في معالجة القناة: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"خطأ في استراتيجية قنوات الرسائل: {e}")
        
        return collected
    
    async def _collect_from_dialog(self, client: TelegramClient, entity, 
                                  session_id: int, added_by_user: int) -> List[Dict]:
        """Collect links from a specific dialog - جمع الروابط من دردشة محددة"""
        collected = []
        
        try:
            # جمع معلومات الكيان
            entity_info = await self._get_entity_info(client, entity)
            
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
                async for message in client.iter_messages(entity, limit=10):
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
                    
                    if len(collected) >= 5:
                        break
            except:
                pass
        
        except Exception as e:
            logger.debug(f"خطأ في جمع الروابط من الدردشة: {e}")
        
        return collected
    
    async def _collect_from_group_messages(self, client: TelegramClient, entity, 
                                          session_id: int, added_by_user: int) -> List[Dict]:
        """Collect links from group messages - جمع الروابط من رسائل المجموعة"""
        collected = []
        
        try:
            # البحث عن روابط في الرسائل
            search_terms = ['رابط', 'دعوة', 'انضمام', 'مجموعة', 'link', 'invite', 'join', 'group']
            
            for term in search_terms[:3]:
                try:
                    async for message in client.iter_messages(
                        entity,
                        search=term,
                        limit=5
                    ):
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
                
                except Exception as e:
                    logger.debug(f"خطأ في البحث في المجموعة: {e}")
                    continue
        
        except Exception as e:
            logger.debug(f"خطأ في جمع روابط المجموعة: {e}")
        
        return collected
    
    async def _collect_from_channel_messages(self, client: TelegramClient, entity, 
                                            session_id: int, added_by_user: int) -> List[Dict]:
        """Collect links from channel messages - جمع الروابط من رسائل القناة"""
        collected = []
        
        try:
            # القنوات غالباً تحتوي على روابط في الوصف والرسائل المثبتة
            if hasattr(entity, 'about') and entity.about:
                links = self._extract_all_links(entity.about)
                for link in links:
                    link_info = await self._process_link_enhanced(
                        client, link, session_id, added_by_user
                    )
                    if link_info:
                        collected.append(link_info)
            
            # التحقق من الرسائل المثبتة
            try:
                pinned = await client.get_messages(entity, ids=0)  # الرسالة المثبتة
                if pinned and hasattr(pinned, 'text') and pinned.text:
                    links = self._extract_all_links(pinned.text)
                    for link in links:
                        link_info = await self._process_link_enhanced(
                            client, link, session_id, added_by_user,
                            pinned.date if hasattr(pinned, 'date') else None
                        )
                        if link_info:
                            collected.append(link_info)
            except:
                pass
        
        except Exception as e:
            logger.debug(f"خطأ في جمع روابط القناة: {e}")
        
        return collected
    
    async def _process_link_enhanced(self, client: TelegramClient, url: str, 
                                    session_id: int, added_by_user: int,
                                    message_date=None) -> Optional[Dict]:
        """Process link with enhanced Telegram validation - معالجة الرابط مع تحقق تيليجرام محسن"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return None
            
            platform = url_info['platform']
            
            # تطبيق قيود زمنية فقط لواتساب
            if platform == 'whatsapp' and message_date:
                if message_date < self.whatsapp_cutoff:
                    return None
            
            # جودة الرابط
            quality_check = self._check_link_quality_enhanced(url_info)
            if not quality_check['passed']:
                return None
            
            cache_key = f"link_{url_info['url_hash']}"
            cached_info = await self.cache_manager.get(cache_key, 'validated_links')
            
            if cached_info:
                return self._create_link_info_from_cache(url, url_info, cached_info, session_id, added_by_user)
            
            # التحقق المتقدم لروابط تيليجرام
            if platform == 'telegram' and Config.ENABLE_ADVANCED_VALIDATION:
                validated = await EnhancedLinkProcessor.validate_telegram_link_advanced(
                    client, url, check_join_request=False
                )
            else:
                validated = {'is_valid': True, 'is_active': True}
            
            if validated.get('is_valid', False) and validated.get('is_active', True):
                link_info = self._create_link_info(url, url_info, validated, session_id, added_by_user, message_date)
                
                # تخزين في الكاش
                await self.cache_manager.set(cache_key, {
                    'link_type': validated.get('type', 'unknown'),
                    'title': validated.get('title', ''),
                    'members': validated.get('members', 0),
                    'confidence': 'high' if validated.get('is_verified', False) else 'medium',
                    'validation_score': validated.get('validation_score', 50),
                    'requires_join': validated.get('requires_join', False),
                    'is_channel': validated.get('is_channel', False),
                    'is_group': validated.get('is_group', False)
                }, 'validated_links', 172800)  # 48 ساعة
                
                # تحديث الإحصائيات
                self._update_collection_stats_enhanced(url_info, validated)
                
                # معالجة خاصة لروابط الانضمام
                if validated.get('requires_join', False) or url_info['details'].get('is_join_request', False):
                    await self._handle_join_request_link(url, url_info, validated, added_by_user)
                
                return link_info
            
            return None
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الرابط المحسن {url}: {e}")
            return None
    
    def _create_link_info(self, url: str, url_info: Dict, validated: Dict, 
                         session_id: int, added_by_user: int, message_date=None) -> Dict:
        """Create link information dictionary - إنشاء قاموس معلومات الرابط"""
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
                'quality_score': self._calculate_quality_score(url_info, validated),
                'verification_method': validated.get('method', 'enhanced'),
                'is_channel': validated.get('is_channel', False),
                'is_group': validated.get('is_group', True),
                'is_supergroup': validated.get('is_supergroup', False),
                'is_join_request': details.get('is_join_request', False)
            },
            'tags': [],
            'source': 'collection'
        }
    
    def _create_link_info_from_cache(self, url: str, url_info: Dict, cached_info: Dict,
                                    session_id: int, added_by_user: int) -> Dict:
        """Create link info from cache - إنشاء معلومات الرابط من الكاش"""
        return {
            'url': url,
            'url_hash': url_info['url_hash'],
            'platform': url_info['platform'],
            'link_type': cached_info.get('link_type', 'unknown'),
            'telegram_type': cached_info.get('link_type', 'unknown'),
            'title': cached_info.get('title', ''),
            'description': '',
            'members': cached_info.get('members', 0),
            'session_id': session_id,
            'added_by_user': added_by_user,
            'confidence': cached_info.get('confidence', 'medium'),
            'is_active': True,
            'requires_join': cached_info.get('requires_join', False),
            'is_verified': True,
            'validation_score': cached_info.get('validation_score', 50),
            'metadata': {
                'collected_at': datetime.now().isoformat(),
                'quality_score': 80,
                'verification_method': 'cached',
                'is_channel': cached_info.get('is_channel', False),
                'is_group': cached_info.get('is_group', True),
                'is_supergroup': False,
                'is_join_request': False
            },
            'tags': [],
            'source': 'collection_cached'
        }
    
    async def _handle_join_request_link(self, url: str, url_info: Dict, validated: Dict, added_by_user: int):
        """Handle join request link specifically - معالجة رابط طلب الانضمام بشكل خاص"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            # إضافة لقائمة الانتظار للتحقق لاحقاً
            await db.add_pending_join_link(url, 'telegram', {
                'validation_info': validated,
                'added_by_user': added_by_user,
                'added_at': datetime.now().isoformat()
            })
            
            self.stats['join_links_found'] += 1
            
            logger.info(f"تمت إضافة رابط انضمام للتحقق: {url}", {
                'url_hash': url_info['url_hash'],
                'requires_join': validated.get('requires_join', True)
            })
            
        except Exception as e:
            logger.error(f"خطأ في معالجة رابط الانضمام: {e}")
    
    async def _process_join_requests(self):
        """Process pending join requests - معالجة طلبات الانضمام المعلقة"""
        while self.active and not self.stop_requested:
            try:
                if self.paused:
                    await asyncio.sleep(5)
                    continue
                
                db = await EnhancedDatabaseManager.get_instance()
                pending_links = await db.get_pending_join_links(limit=10)
                
                if not pending_links:
                    await asyncio.sleep(Config.JOIN_REQUEST_CHECK_DELAY)
                    continue
                
                logger.info(f"جاري معالجة {len(pending_links)} رابط انضمام معلق")
                
                for pending_link in pending_links:
                    if not self.active or self.stop_requested or self.paused:
                        break
                    
                    await self._validate_single_join_request(pending_link)
                    await asyncio.sleep(Config.REQUEST_DELAYS['join_request'])
                
                await asyncio.sleep(Config.JOIN_REQUEST_CHECK_DELAY)
                
            except Exception as e:
                logger.error(f"خطأ في معالجة طلبات الانضمام: {e}")
                await asyncio.sleep(30)
    
    async def _validate_single_join_request(self, pending_link: Dict):
        """Validate a single join request - التحقق من طلب انضمام واحد"""
        try:
            url = pending_link['url']
            pending_id = pending_link['id']
            metadata = pending_link.get('metadata', {})
            
            # الحصول على جلسة للتحقق
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=1)
            
            if not sessions:
                await db.update_pending_link_status(pending_id, 'failed', {
                    'error': 'لا توجد جلسات متاحة للتحقق'
                })
                return
            
            session = sessions[0]
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt_session(session.get('session_string', ''))
            actual_session = decrypted_session or session.get('session_string', '')
            
            if not actual_session or actual_session == '********':
                await db.update_pending_link_status(pending_id, 'failed', {
                    'error': 'الجلسة غير متاحة'
                })
                return
            
            client = TelegramClient(
                StringSession(actual_session),
                Config.API_ID,
                Config.API_HASH,
                timeout=Config.VALIDATION_TIMEOUT
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                await db.update_pending_link_status(pending_id, 'failed', {
                    'error': 'الجلسة غير مصرح بها'
                })
                return
            
            # التحقق من رابط الانضمام
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                await client.disconnect()
                await db.update_pending_link_status(pending_id, 'invalid', {
                    'error': 'رابط غير صالح'
                })
                return
            
            # التحقق المتقدم
            validated = await EnhancedLinkProcessor.validate_telegram_link_advanced(
                client, url, check_join_request=True
            )
            
            await client.disconnect()
            
            if validated.get('is_valid', False) and validated.get('is_active', True):
                # إضافة الرابط للقاعدة الرئيسية
                link_info = {
                    'url': url,
                    'url_hash': url_info['url_hash'],
                    'platform': 'telegram',
                    'link_type': validated.get('type', 'unknown'),
                    'telegram_type': validated.get('type', 'unknown'),
                    'title': validated.get('title', ''),
                    'members': validated.get('members', 0),
                    'session_id': session['id'],
                    'added_by_user': metadata.get('added_by_user', 0),
                    'confidence': 'high',
                    'is_active': True,
                    'requires_join': validated.get('requires_join', True),
                    'is_verified': True,
                    'validation_score': 90,
                    'metadata': {
                        'verified_at': datetime.now().isoformat(),
                        'verification_method': 'join_request_validation',
                        'join_request_valid': validated.get('join_request_valid', False),
                        'is_channel': validated.get('is_channel', False),
                        'is_group': validated.get('is_group', True),
                        'is_supergroup': validated.get('is_supergroup', False)
                    },
                    'tags': ['join_request_validated'],
                    'source': 'join_request_validation'
                }
                
                success, message, details = await db.add_link_enhanced(link_info)
                
                if success:
                    await db.update_pending_link_status(pending_id, 'verified', {
                        'verified_at': datetime.now().isoformat(),
                        'link_id': details.get('link_id'),
                        'validation_info': validated
                    })
                    
                    self.stats['join_links_validated'] += 1
                    
                    logger.info(f"تم التحقق من رابط الانضمام: {url}", {
                        'link_id': details.get('link_id'),
                        'type': validated.get('type'),
                        'requires_join': validated.get('requires_join')
                    })
                else:
                    await db.update_pending_link_status(pending_id, 'failed', {
                        'error': f'فشل الإضافة: {message}'
                    })
            else:
                await db.update_pending_link_status(pending_id, 'invalid', {
                    'error': validated.get('reason', 'رابط غير صالح'),
                    'validation_info': validated
                })
            
        except Exception as e:
            logger.error(f"خطأ في التحقق من رابط الانضمام {pending_link.get('url')}: {e}")
            await db.update_pending_link_status(pending_id, 'failed', {
                'error': f'خطأ في التحقق: {str(e)[:100]}'
            })
    
    def _check_link_quality_enhanced(self, url_info: Dict) -> Dict:
        """Check link quality with enhanced criteria - التحقق من جودة الرابط بمعايير محسنة"""
        score = 100
        reasons = []
        
        url = url_info['normalized_url']
        
        # فحص الطول
        if len(url) < self.quality_filters['min_url_length']:
            score -= 20
            reasons.append('url_too_short')
        
        if len(url) > self.quality_filters['max_url_length']:
            score -= 15
            reasons.append('url_too_long')
        
        # فحص الأنماط المسموحة
        pattern_matched = False
        for pattern in self.quality_filters['allowed_patterns']:
            if re.match(pattern, url):
                pattern_matched = True
                break
        
        if not pattern_matched:
            score -= 30
            reasons.append('pattern_not_allowed')
        
        # فحص المنصة
        if url_info['platform'] == 'unknown':
            score -= 40
            reasons.append('unknown_platform')
        
        # فحص خاص لروابط تيليجرام
        if url_info['platform'] == 'telegram':
            details = url_info['details']
            
            # زيادة النقاط لروابط الانضمام
            if details.get('is_join_request'):
                score += 20
            
            # زيادة النقاط للمجموعات العامة
            if details.get('is_public'):
                score += 10
        
        return {
            'passed': score >= 40,  # تخفيض الحد الأدنى
            'score': score,
            'reasons': reasons
        }
    
    def _calculate_quality_score(self, url_info: Dict, validated: Dict) -> int:
        """Calculate quality score for link - حساب درجة الجودة للرابط"""
        base_score = 70
        
        # إضافة نقاط للمعلومات الإضافية
        if validated.get('title'):
            base_score += 10
        
        if validated.get('members', 0) > 100:
            base_score += 10
        
        if validated.get('is_verified', False):
            base_score += 20
        
        if not validated.get('requires_join', True):
            base_score += 10
        
        # روابط الانضمام تحصل على نقاط إضافية
        if url_info['details'].get('is_join_request', False):
            base_score += 15
        
        return min(100, base_score)
    
    def _update_collection_stats_enhanced(self, url_info: Dict, validation: Dict):
        """Update collection statistics with enhanced Telegram classification - تحديث إحصائيات الجمع مع تصنيف تيليجرام محسن"""
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
        """Extract all links from text - استخراج جميع الروابط من النص"""
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
            r'(\+[A-Za-z0-9_-]+)'  # روابط +joinchat
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
    
    async def _get_entity_info(self, client: TelegramClient, entity) -> Dict:
        """Get entity information - الحصول على معلومات الكيان"""
        try:
            if hasattr(entity, 'title'):
                return {
                    'title': entity.title,
                    'type': 'channel' if hasattr(entity, 'broadcast') and entity.broadcast else 'group'
                }
            elif hasattr(entity, 'username'):
                return {
                    'username': entity.username,
                    'type': 'user'
                }
        except:
            pass
        
        return {'type': 'unknown'}
    
    async def _update_session_health(self, session_id: int, success: bool):
        """Update session health score - تحديث درجة صحة الجلسة"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            async with db._get_connection() as conn:
                if success:
                    await conn.execute('''
                        UPDATE sessions 
                        SET health_score = MIN(100, health_score + 5),
                            last_success = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (session_id,))
                else:
                    await conn.execute('''
                        UPDATE sessions 
                        SET health_score = MAX(0, health_score - 10)
                        WHERE id = ?
                    ''', (session_id,))
                
                await conn.commit()
                
        except Exception as e:
            logger.debug(f"خطأ في تحديث صحة الجلسة: {e}")
    
    def _calculate_optimal_session_count(self) -> int:
        """Calculate optimal number of concurrent sessions - حساب العدد الأمثل للجلسات المتزامنة"""
        base_count = Config.MAX_CONCURRENT_SESSIONS
        
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
        
        error_penalty = min(self.stats['errors'] * 1.5, 20)
        flood_penalty = min(self.stats['flood_waits'] * 3, 30)
        performance_bonus = max(0, (self.stats['performance_score'] - 80) / 2)
        
        system_modifier = 0
        if self.system_state['memory_pressure'] == 'high':
            system_modifier += 15
        if self.system_state['network_status'] == 'poor':
            system_modifier += 10
        
        calculated_delay = base_delay + error_penalty + flood_penalty + system_modifier - performance_bonus
        
        return max(base_delay, min(calculated_delay, max_delay))
    
    def _calculate_session_delay(self, index: int) -> float:
        """Calculate delay between sessions - حساب التأخير بين الجلسات"""
        base_delay = Config.REQUEST_DELAYS['between_sessions']
        incremental_delay = index * 0.3
        
        if self.system_state['network_status'] == 'poor':
            incremental_delay *= 1.5
        
        return base_delay + incremental_delay
    
    def _calculate_strategy_delay(self) -> float:
        """Calculate delay between strategies - حساب التأخير بين الاستراتيجيات"""
        return Config.REQUEST_DELAYS['between_tasks']
    
    def _select_strategies(self) -> List:
        """Select collection strategies - اختيار استراتيجيات الجمع"""
        all_strategies = [
            self._strategy_all_dialogs,
            self._strategy_search_all_messages,
            self._strategy_group_messages,
            self._strategy_channel_messages
        ]
        
        if self.system_state['memory_pressure'] == 'low' and self.system_state['network_status'] == 'good':
            return all_strategies[:3]
        elif self.system_state['memory_pressure'] == 'high':
            return [self._strategy_all_dialogs]
        else:
            return all_strategies[:2]
    
    async def _update_system_state(self):
        """Update system state - تحديث حالة النظام"""
        memory_usage = self.memory_manager.get_memory_percent()
        
        if memory_usage > 85:
            self.system_state['memory_pressure'] = 'high'
        elif memory_usage > 70:
            self.system_state['memory_pressure'] = 'medium'
        else:
            self.system_state['memory_pressure'] = 'low'
        
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
        """Optimize system between cycles - تحسين النظام بين الدورات"""
        memory_result = self.memory_manager.check_and_optimize()
        
        if memory_result['optimized']:
            logger.info("تم تحسين الذاكرة بين الدورات", {
                'saved_mb': memory_result.get('saved_mb', 0),
                'duration_ms': memory_result.get('duration_ms', 0)
            })
        
        await self.cache_manager.cleanup_expired()
        
        cache_stats = self.cache_manager.get_stats()
        self.performance['cache_hit_rate'] = float(cache_stats['hit_ratio'].rstrip('%')) / 100
        self.performance['memory_usage_mb'] = self.memory_manager.get_memory_usage()
        
        self._calculate_performance_score()
    
    def _calculate_performance_score(self):
        """Calculate performance score - حساب درجة الأداء"""
        scores = []
        
        cache_score = self.performance['cache_hit_rate'] * 100
        scores.append(cache_score)
        
        success_score = self.performance['success_rate'] * 100
        scores.append(success_score)
        
        memory_usage = self.memory_manager.get_memory_percent()
        memory_score = max(0, 100 - memory_usage)
        scores.append(memory_score)
        
        if scores:
            self.stats['performance_score'] = sum(scores) / len(scores)
    
    async def _system_monitoring(self):
        """Monitor system health - مراقبة صحة النظام"""
        while self.active and not self.stop_requested:
            try:
                system_metrics = {
                    'memory_usage_mb': self.memory_manager.get_memory_usage(),
                    'memory_percent': self.memory_manager.get_memory_percent(),
                    'cache_stats': self.cache_manager.get_stats(),
                    'task_manager_stats': self.task_manager.get_stats(),
                    'collection_stats': self.stats.copy(),
                    'performance_metrics': self.performance.copy(),
                    'timestamp': datetime.now().isoformat()
                }
                
                await self._store_system_metrics(system_metrics)
                await self._check_critical_issues(system_metrics)
                
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"خطأ في مراقبة النظام: {e}")
                await asyncio.sleep(30)
    
    async def _store_system_metrics(self, metrics: Dict):
        """Store system metrics - تخزين مقاييس النظام"""
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
        """Check for critical issues - التحقق من المشكلات الحرجة"""
        warnings = []
        
        if metrics['memory_percent'] > 90:
            warnings.append(f"استخدام ذاكرة حرج: {metrics['memory_percent']:.1f}%")
        
        if self.stats['errors'] > 50:
            warnings.append(f"عدد أخطاء مرتفع: {self.stats['errors']}")
        
        if self.performance['success_rate'] < 0.3:
            warnings.append(f"معدل نجاح منخفض: {self.performance['success_rate']:.1%}")
        
        if warnings:
            logger.warning(f"مشكلات نظام حرجة: {', '.join(warnings)}")
            
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
        """Perform periodic maintenance - تنفيذ الصيانة الدورية"""
        while self.active and not self.stop_requested:
            try:
                await EnhancedSessionManager.cleanup_inactive_sessions()
                
                if Config.BACKUP_ENABLED:
                    await BackupManager.rotate_backups()
                
                await self._optimize_database()
                await self._cleanup_old_logs()
                
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"خطأ في الصيانة الدورية: {e}")
                await asyncio.sleep(60)
    
    async def _optimize_database(self):
        """Optimize database - تحسين قاعدة البيانات"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            async with db._get_connection() as conn:
                await conn.execute("ANALYZE")
                await conn.execute("REINDEX")
                await conn.execute("VACUUM")
                await conn.commit()
                
                logger.debug("تم تحسين قاعدة البيانات")
                
        except Exception as e:
            logger.debug(f"خطأ في تحسين قاعدة البيانات: {e}")
    
    async def _cleanup_old_logs(self):
        """Cleanup old logs - تنظيف السجلات القديمة"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            async with db._get_connection() as conn:
                await conn.execute('''
                    DELETE FROM error_log 
                    WHERE occurred_at < datetime('now', '-7 days')
                ''')
                
                await conn.execute('''
                    DELETE FROM system_stats 
                    WHERE recorded_at < datetime('now', '-30 days')
                ''')
                
                await conn.commit()
                
                logger.debug("تم تنظيف السجلات القديمة")
                
        except Exception as e:
            logger.debug(f"خطأ في تنظيف السجلات: {e}")
    
    async def _adaptive_optimization(self):
        """Perform adaptive optimization - تنفيذ التحسين المتكيف"""
        while self.active and not self.stop_requested:
            try:
                if self.stats['performance_score'] < 60:
                    logger.warning(f"درجة أداء منخفضة: {self.stats['performance_score']:.1f}")
                    await self._execute_performance_optimizations()
                
                if self.stats['quality_score'] < 50:
                    logger.warning(f"جودة بيانات منخفضة: {self.stats['quality_score']:.1f}")
                    self._adjust_quality_filters()
                
                await asyncio.sleep(600)
                
            except Exception as e:
                logger.error(f"خطأ في التحسين المتكيف: {e}")
                await asyncio.sleep(60)
    
    async def _execute_performance_optimizations(self):
        """Execute performance optimizations - تنفيذ تحسينات الأداء"""
        optimizations = []
        
        if self.system_state['memory_pressure'] == 'high':
            self.cache_manager.optimize()
            optimizations.append("تحسين الكاش")
        
        if self.performance['concurrent_tasks'] > 3:
            self.task_manager.adjust_concurrency(-1)
            optimizations.append("تقليل المهام المتزامنة")
        
        memory_saved = self.memory_manager.optimize_memory()
        if memory_saved > 10:
            optimizations.append(f"تحسين الذاكرة ({memory_saved:.1f} MB)")
        
        if optimizations:
            logger.info(f"تم تنفيذ تحسينات الأداء: {', '.join(optimizations)}")
    
    def _adjust_quality_filters(self):
        """Adjust quality filters - ضبط عوامل تصفية الجودة"""
        if self.stats['quality_score'] < 40:
            self.quality_filters['min_url_length'] = 12
            logger.info("تم زيادة صرامة فلاتر الجودة")
        elif self.stats['quality_score'] > 80:
            self.quality_filters['min_url_length'] = 8
            logger.info("تم تخفيف فلاتر الجودة")
    
    async def _graceful_shutdown(self):
        """Perform graceful shutdown - تنفيذ إغلاق سلس"""
        logger.info("بدء الإغلاق السلس لنظام الجمع...")
        
        self.active = False
        self.paused = False
        self.stats['end_time'] = datetime.now()
        
        self.task_manager.stop_monitoring()
        self.cache_manager.clear()
        EnhancedSessionManager.clear_cache()
        self.memory_manager.optimize_memory()
        
        await self._save_final_stats()
        
        logger.info(f"✅ اكتمل الإغلاق السلس. الإحصائيات: {self.stats}")
    
    async def _save_final_stats(self):
        """Save final statistics - حفظ الإحصائيات النهائية"""
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
        """Get collection status - الحصول على حالة الجمع"""
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
        """Pause collection - إيقاف الجمع مؤقتاً"""
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
        """Stop collection - إيقاف الجمع"""
        self.stop_requested = True
        
        logger.info("⏹️ تم طلب إيقاف الجمع بسلاسة")
        
        await asyncio.sleep(2)
    
    async def get_detailed_report(self) -> Dict:
        """Get detailed report - الحصول على تقرير مفصل"""
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary_enhanced(detailed=True)
        
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
        """Generate recommendations - توليد توصيات"""
        recommendations = []
        
        memory_percent = self.memory_manager.get_memory_percent()
        if memory_percent > 80:
            recommendations.append("⚠️ استخدام ذاكرة مرتفع. فكر في زيادة حجم الكاش أو تقليل المهام المتزامنة.")
        
        if self.stats['performance_score'] < 70:
            recommendations.append("⚡ درجة أداء منخفضة. فكر في زيادة تأخيرات الدورة أو تحسين الاستراتيجيات.")
        
        if self.stats['quality_score'] < 60:
            recommendations.append("🎯 جودة البيانات منخفضة. فكر في تشديد فلاتر الجودة أو تحسين التحقق.")
        
        session_metrics = EnhancedSessionManager.get_all_metrics()
        if session_metrics['unhealthy_sessions'] > 3:
            recommendations.append("🔧 عدد الجلسات غير الصحية مرتفع. فكر في إعادة التحقق من الجلسات أو استبدالها.")
        
        return recommendations

# ======================
# Advanced Telegram Bot - بوت تيليجرام المتقدم
# ======================

class AdvancedTelegramBot:
    """Advanced Telegram bot with unlimited collection features - بوت تيليجرام متقدم بمميزات جمع غير محدودة"""
    
    def __init__(self):
        self.collection_manager = AdvancedCollectionManager()
        self.security_manager = AdvancedSecurityManager()
        
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        
        self._setup_advanced_handlers()
        
        self.user_states = defaultdict(dict)
        self.conversation_states = {}
        
        self.help_system = HelpSystem()
        self.notification_system = NotificationSystem()
    
    def _setup_advanced_handlers(self):
        """Setup advanced handlers - إعداد معالجات متقدمة"""
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
        
        self.app.add_handler(CallbackQueryHandler(self.handle_advanced_callback))
        
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_advanced_message
        ))
        
        self.app.add_error_handler(self.error_handler)
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /collect command - معالجة أمر /collect"""
        user = update.effective_user
        
        access, message, _ = await self.security_manager.check_access(user.id, 'collect')
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status")],
            [InlineKeyboardButton("📋 تقرير الجمع", callback_data="collect_report")],
            [InlineKeyboardButton("⚙️ إعدادات الجمع", callback_data="collect_settings")]
        ])
        
        await update.message.reply_text(
            "🚀 **نظام الجمع المتقدم**\n\n"
            "**مميزات الجمع:**\n"
            "• 📢 تيليجرام: جمع غير محدود بدون قيود زمنية\n"
            "• 📱 واتساب: جمع من آخر 30 يوماً فقط\n"
            "• 🔍 كشف ذكي: تفريق بين المجموعات والقنوات\n"
            "• ⏱️ تحقق من طلبات الانضمام: 30 ثانية لكل رابط\n\n"
            "**أنواع الروابط المدعومة:**\n"
            "• المجموعات العامة والخاصة\n"
            "• القنوات\n"
            "• طلبات الانضمام (+\n"
            "• مجموعات واتساب\n"
            "• دعوات ديسكورد وسيجنال\n",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def advanced_start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command - معالجة أمر /start"""
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
            
            if self.security_manager.is_admin(user.id):
                await self.notification_system.send_security_alert(
                    f"محاولة وصول مرفوضة: {user.id} (@{user.username})",
                    details
                )
            
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
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
        
        user_stats = await db.get_user_stats(user.id)
        if user_stats.get('account_age_days', 365) < 1:
            await self._send_welcome_tutorial(update.message, user)
    
    async def advanced_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - معالجة أمر /status"""
        user = update.effective_user
        
        access, message, _ = await self.security_manager.check_access(user.id, 'status')
        if not access:
            await update.message.reply_text(f"❌ {message}")
            return
        
        self.user_states[user.id]['last_command'] = 'status'
        
        status = self.collection_manager.get_status()
        
        memory_metrics = MemoryManager.get_instance().get_metrics()
        cache_stats = CacheManager.get_instance().get_stats()
        
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
                
                if status['stats']['start_time']:
                    duration = datetime.now() - status['stats']['start_time']
                    status_text += f"   ⏱️ المدة: {self._format_duration(duration)}\n"
                    status_text += f"   🔄 الدورات: {status['stats']['cycles_completed']}\n"
        else:
            status_text += "🛑 **متوقف**\n"
        
        status_text += f"""
**📈 إحصائيات الجمع (تيليجرام غير محدود):**
• 📦 المجموع: {status['stats']['total_collected']:,}
• 📢 مجموعات عامة: {status['stats']['telegram_public']:,}
• 🔒 مجموعات خاصة: {status['stats']['telegram_private']:,}
• ➕ طلبات انضمام: {status['stats']['telegram_join']:,}
• 📢 قنوات: {status['stats']['telegram_channels']:,}
• 👥 مجموعات عادية: {status['stats']['telegram_groups']:,}
• ⭐ مجموعات خارقة: {status['stats']['telegram_supergroups']:,}
• 📱 واتساب: {status['stats']['whatsapp_groups']:,}
• 🔄 مكررات: {status['stats']['duplicates']:,}
• ⏱️ روابط انضمام وجدت: {status['stats']['join_links_found']:,}
• ✅ روابط انضمام تم التحقق: {status['stats']['join_links_validated']:,}

**⚡ أداء النظام:**
• 🎯 درجة الأداء: {status['stats']['performance_score']:.1f}/100
• 💾 نسبة الكاش: {status['performance']['cache_hit_rate']:.1%}
• 🧠 الذاكرة: {status['memory']['current_mb']:.1f} MB
• 📶 حالة الشبكة: {status['system_state']['network_status']}
• ⚖️ ضغط الذاكرة: {status['system_state']['memory_pressure']}
• ⏱️ تأخير الدورة: {self._calculate_adaptive_delay_info()}

**👤 حالتك:**
"""
        
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
    
    def _calculate_adaptive_delay_info(self) -> str:
        """Calculate adaptive delay info - حساب معلومات التأخير المتكيف"""
        base_delay = Config.REQUEST_DELAYS['min_cycle_delay']
        max_delay = Config.REQUEST_DELAYS['max_cycle_delay']
        
        current_delay = base_delay + min(self.collection_manager.stats['errors'] * 1.5, 20)
        
        return f"{current_delay:.1f} ثانية"
    
    async def handle_advanced_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle advanced callback - معالجة الاستدعاء المتقدم"""
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
            elif data == "add_session":
                await self._handle_advanced_add_session(query)
            else:
                await query.message.edit_text("❌ أمر غير معروف")
        
        except Exception as e:
            logger.error(f"خطأ في معالج الاستدعاء المتقدم: {e}", exc_info=True)
            await query.message.edit_text(f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_advanced_start_collection(self, query):
        """Handle start collection - معالجة بدء الجمع"""
        if self.collection_manager.active:
            await query.message.edit_text("⏳ الجمع يعمل بالفعل")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚖️ متوازن (مستحسن)", callback_data="start_mode_balanced")],
            [InlineKeyboardButton("⚡ سريع", callback_data="start_mode_fast")],
            [InlineKeyboardButton("🔒 آمن", callback_data="start_mode_safe")],
            [InlineKeyboardButton("🎯 مخصص", callback_data="start_mode_custom")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_start")]
        ])
        
        await query.message.edit_text(
            "🚀 **بدء الجمع الذكي المتقدم**\n\n"
            "**مميزات النظام:**\n"
            "• 📢 تيليجرام: جمع غير محدود\n"
            "• 📱 واتساب: آخر 30 يوماً فقط\n"
            "• ⏱️ تحقق من طلبات الانضمام: 30 ثانية\n"
            "• 🔍 تفريق ذكي بين المجموعات والقنوات\n\n"
            "اختر وضع الجمع:\n\n"
            "• ⚖️ **متوازن** - جمع متوازن مع حماية الذاكرة\n"
            "• ⚡ **سريع** - جمع سريع مع استخدام موارد أعلى\n"
            "• 🔒 **آمن** - جمع آمن مع تأخيرات أطول\n"
            "• 🎯 **مخصص** - ضبط الإعدادات يدوياً\n\n"
            "**التوصية:** ⚖️ متوازن للمستخدمين الجدد",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_stop_collection(self, query):
        """Handle stop collection - معالجة إيقاف الجمع"""
        if not self.collection_manager.active:
            await query.message.edit_text("⚠️ الجمع غير نشط")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تأكيد الإيقاف", callback_data="confirm_stop")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_stop")]
        ])
        
        await query.message.edit_text(
            "⏹️ **تأكيد إيقاف الجمع**\n\n"
            "هل أنت متأكد من إيقاف الجمع؟\n\n"
            "**ملاحظة:**\n"
            "• سيتم حفظ جميع الروابط المجمعة\n"
            "• سيتوقف الجمع فوراً\n"
            "• يمكنك إعادة التشغيل في أي وقت\n\n"
            "الإحصائيات الحالية:\n"
            f"• الروابط المجمعة: {self.collection_manager.stats['total_collected']:,}\n"
            f"• الدورات المكتملة: {self.collection_manager.stats['cycles_completed']:,}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_collect_status(self, query):
        """Handle collect status - معالجة حالة الجمع"""
        status = self.collection_manager.get_status()
        
        text = f"""
📊 **حالة الجمع التفصيلية**

**الحالة:** {"🔄 نشط" if status['active'] else "🛑 متوقف"}
**الإيقاف المؤقت:** {"⏸️ نعم" if status['paused'] else "▶️ لا"}
**طلب الإيقاف:** {"✅ نعم" if status['stop_requested'] else "❌ لا"}

**الإحصائيات:**
• الروابط المجمعة: {status['stats']['total_collected']:,}
• دورات الجمع: {status['stats']['cycles_completed']:,}
• الأخطاء: {status['stats']['errors']:,}
• انتظارات Flood: {status['stats']['flood_waits']:,}

**تيليجرام:**
• المجموعات العامة: {status['stats']['telegram_public']:,}
• المجموعات الخاصة: {status['stats']['telegram_private']:,}
• طلبات الانضمام: {status['stats']['telegram_join']:,}
• القنوات: {status['stats']['telegram_channels']:,}
• المجموعات العادية: {status['stats']['telegram_groups']:,}
• المجموعات الخارقة: {status['stats']['telegram_supergroups']:,}

**أداء النظام:**
• درجة الأداء: {status['stats']['performance_score']:.1f}/100
• نسبة نجاح المهام: {status['performance']['success_rate']:.1%}
• استخدام الذاكرة: {status['memory']['current_mb']:.1f} MB
"""
        
        await query.message.edit_text(text, parse_mode="Markdown")
    
    async def _handle_collect_report(self, query):
        """Handle collect report - معالجة تقرير الجمع"""
        try:
            report = await self.collection_manager.get_detailed_report()
            
            text = f"""
📋 **تقرير الجمع المتقدم**

**ملخص الجمع:**
• الحالة: {"🔄 نشط" if report['collection_status']['active'] else "🛑 متوقف"}
• المدة: {self._format_collection_duration(report['collection_status'])}
• الروابط المجمعة: {report['collection_status']['stats']['total_collected']:,}
• نسبة النجاح: {report['collection_status']['performance']['success_rate']:.1%}

**تفصيل تيليجرام:**
• المجموعات: {report['collection_status']['stats']['telegram_groups']:,}
• القنوات: {report['collection_status']['stats']['telegram_channels']:,}
• المجموعات الخارقة: {report['collection_status']['stats']['telegram_supergroups']:,}
• طلبات الانضمام: {report['collection_status']['stats']['telegram_join']:,}

**صحة النظام:**
• الذاكرة: {report['system_health']['memory']['current_mb']:.1f} MB
• نسبة الكاش: {report['system_health']['cache']['hit_ratio']}
• الجلسات النشطة: {report['system_health']['sessions']['healthy_sessions']}

**التوصيات:**
"""
            
            for rec in report['recommendations'][:3]:
                text += f"• {rec}\n"
            
            await query.message.edit_text(text, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"خطأ في توليد تقرير الجمع: {e}")
            await query.message.edit_text("❌ حدث خطأ في توليد التقرير")
    
    def _format_collection_duration(self, status: Dict) -> str:
        """Format collection duration - تنسيق مدة الجمع"""
        if not status['stats'].get('start_time'):
            return "غير معروف"
        
        start_time = status['stats']['start_time']
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        
        end_time = status['stats'].get('end_time')
        if end_time and isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        if not end_time:
            end_time = datetime.now()
        
        duration = end_time - start_time
        return self._format_duration(duration)
    
    async def _handle_collect_settings(self, query):
        """Handle collect settings - معالجة إعدادات الجمع"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ تغيير وضع الجمع", callback_data="change_collect_mode")],
            [InlineKeyboardButton("⏱️ ضبط التأخيرات", callback_data="adjust_delays")],
            [InlineKeyboardButton("📊 ضبط الحدود", callback_data="adjust_limits")],
            [InlineKeyboardButton("🔍 ضبط الفلاتر", callback_data="adjust_filters")],
            [InlineKeyboardButton("🔄 إعادة التعيين", callback_data="reset_settings")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="collect_menu")]
        ])
        
        text = f"""
⚙️ **إعدادات الجمع المتقدم**

**الإعدادات الحالية:**
• وضع الجمع: {self.collection_manager.system_state['collection_mode']}
• الحد الأقصى للجلسات: {Config.MAX_CONCURRENT_SESSIONS}
• الروابط لكل دورة: {Config.MAX_LINKS_PER_CYCLE}
• تأخير الدورة: {Config.REQUEST_DELAYS['min_cycle_delay']}-{Config.REQUEST_DELAYS['max_cycle_delay']} ثانية
• تحقق طلبات الانضمام: {Config.JOIN_REQUEST_CHECK_DELAY} ثانية

**مميزات خاصة:**
• تيليجرام: {"✅ جمع غير محدود" if Config.TELEGRAM_NO_TIME_LIMIT else "❌ محدود"}
• واتساب: {"✅ آخر 30 يوماً" if Config.WHATSAPP_DAYS_BACK == 30 else f"آخر {Config.WHATSAPP_DAYS_BACK} يوم"}
• التحقق المتقدم: {"✅ مفعل" if Config.ENABLE_ADVANCED_VALIDATION else "❌ معطل"}
"""
        
        await query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    def _create_main_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        """Create main keyboard - إنشاء لوحة المفاتيح الرئيسية"""
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
        """Format duration - تنسيق المدة"""
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
        """Send welcome tutorial - إرسال برنامج تعليمي ترحيبي"""
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
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors - معالجة الأخطاء"""
        try:
            error = context.error
            
            logger.error(f"خطأ غير معالج في البوت: {error}", exc_info=True)
            
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
    """Help system - نظام المساعدة"""
    
    def get_welcome_message(self, user, access_details: Dict) -> str:
        """Get welcome message - الحصول على رسالة ترحيب"""
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

# ======================
# Notification System - نظام الإشعارات
# ======================

class NotificationSystem:
    """Notification system - نظام الإشعارات"""
    
    async def send_admin_notification(self, message: str, data: Dict = None):
        """Send admin notification - إرسال إشعار للمدير"""
        logger.info(f"إشعار للمديرين: {message}", data or {})
    
    async def send_error_notification(self, error: str, details: Dict):
        """Send error notification - إرسال إشعار خطأ"""
        logger.error(f"إشعار خطأ: {error}", details)
    
    async def send_security_alert(self, alert: str, details: Dict):
        """Send security alert - إرسال تنبيه أمني"""
        logger.warning(f"تنبيه أمني: {alert}", details)

# ======================
# Signal Handlers - معالجات الإشارات
# ======================

def setup_signal_handlers():
    """Setup signal handlers - إعداد معالجات الإشارات"""
    def signal_handler(signum, frame):
        logger.info(f"📶 تم استقبال إشارة {signum}. جاري الإغلاق السلس...")
        
        logger.info("📊 إحصائيات النظام النهائية:", {
            'memory': MemoryManager.get_instance().get_metrics(),
            'cache': CacheManager.get_instance().get_stats()
        })
        
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# ======================
# Advanced Security Manager - مدير الأمان المتقدم
# ======================

class AdvancedSecurityManager:
    """Advanced security manager - مدير الأمان المتقدم"""
    
    def __init__(self):
        self.rate_limiter = AdvancedRateLimiter()
        self.suspicious_activity = defaultdict(list)
        self.access_log = deque(maxlen=1000)
        self.threat_detection_enabled = True
        
    async def check_access(self, user_id: int, command: str = None, 
                          context: Dict = None) -> Tuple[bool, str, Dict]:
        """Check access - التحقق من الوصول"""
        if Config.ADMIN_USER_IDS and user_id in Config.ADMIN_USER_IDS:
            return True, "مدير", {'access_level': 'admin'}
        
        if Config.ALLOWED_USER_IDS and user_id not in Config.ALLOWED_USER_IDS:
            self._log_suspicious_activity(user_id, 'unauthorized_access', context)
            return False, "غير مصرح لك بالوصول", {'access_level': 'denied'}
        
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
        
        if self.threat_detection_enabled:
            threat_check = await self._detect_threats(user_id, command, context)
            if not threat_check['safe']:
                self._log_suspicious_activity(user_id, 'threat_detected', threat_check)
                return False, "تم اكتشاف نشاط مشبوه. الوصول مرفوض.", {
                    'access_level': 'blocked',
                    'threat_details': threat_check
                }
        
        self._log_access(user_id, 'success', command, context)
        
        return True, "مسموح", {
            'access_level': 'user',
            'rate_limit': limit_details,
            'user_stats': self.rate_limiter.get_user_stats(user_id)
        }
    
    async def _detect_threats(self, user_id: int, command: str, context: Dict) -> Dict:
        """Detect threats - كشف التهديدات"""
        threats = []
        risk_score = 0
        
        recent_accesses = [log for log in self.access_log 
                          if log['user_id'] == user_id and 
                          (datetime.now() - log['timestamp']).total_seconds() < 10]
        
        if len(recent_accesses) > 5:
            threats.append('rapid_repeated_access')
            risk_score += 30
        
        suspicious_commands = ['eval', 'exec', 'system', 'os.', 'subprocess']
        if command and any(suspicious in command.lower() for suspicious in suspicious_commands):
            threats.append('suspicious_command')
            risk_score += 50
        
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
        """Log access - تسجيل الوصول"""
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
        
        if len(self.suspicious_activity[user_id]) > 10:
            self.suspicious_activity[user_id] = self.suspicious_activity[user_id][-10:]
        
        logger.warning(f"نشاط مشبوه: {activity_type} للمستخدم {user_id}", details)
    
    def is_admin(self, user_id: int) -> bool:
        """Check if admin - التحقق إذا كان مدير"""
        return user_id in Config.ADMIN_USER_IDS if Config.ADMIN_USER_IDS else False

# ======================
# Advanced Rate Limiter - حد الطلبات المتقدم
# ======================

class AdvancedRateLimiter:
    """Advanced rate limiter - حد الطلبات المتقدم"""
    
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
        """Check limit - التحقق من الحد"""
        async with self.locks[user_id]:
            user_data = self.user_limits[user_id]
            now = datetime.now()
            
            while user_data['requests'] and (now - user_data['requests'][0]).total_seconds() > Config.USER_RATE_LIMIT['per_seconds']:
                user_data['requests'].popleft()
            
            dynamic_limit = self._calculate_dynamic_limit(user_id)
            
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
            
            user_data['requests'].append(now)
            user_data['total'] += 1
            self.global_limits['total_requests'] += 1
            
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
        """Calculate dynamic limit - حساب الحد الديناميكي"""
        base_limit = Config.USER_RATE_LIMIT['max_requests']
        user_data = self.user_limits[user_id]
        
        penalty_factor = max(0.3, 1 - (user_data['penalty_score'] / 100))
        
        global_factor = 1.0
        if self.global_limits['rate_violations'] > 10:
            global_factor = 0.8
        elif self.global_limits['total_requests'] > 1000:
            global_factor = 0.9
        
        return int(base_limit * penalty_factor * global_factor)
    
    def _calculate_wait_time(self, penalty_score: int) -> float:
        """Calculate wait time - حساب وقت الانتظار"""
        base_wait = 30
        penalty_multiplier = 1 + (penalty_score / 50)
        
        return min(base_wait * penalty_multiplier, 300)
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Get user stats - الحصول على إحصائيات المستخدم"""
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
        
        window_stats = {}
        for window in [10, 30, 60, 300, 1800]:
            count = sum(1 for req_time in recent_requests 
                       if (now - req_time).total_seconds() <= window)
            window_stats[f'last_{window}s'] = count
        
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
# Task Manager - مدير المهام
# ======================

class TaskManager:
    """Task manager - مدير المهام"""
    
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
        """Start monitoring - بدء المراقبة"""
        self.monitoring = True
        asyncio.create_task(self._monitor_tasks())
        self._start_workers()
    
    def _start_workers(self):
        """Start workers - بدء العاملين"""
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(i))
            self.worker_tasks.append(worker)
    
    async def _worker(self, worker_id: int):
        """Worker task - مهمة العامل"""
        logger.debug(f"بدء العامل {worker_id}")
        
        while self.monitoring:
            if self.paused:
                await asyncio.sleep(0.1)
                continue
            
            try:
                task_data = await asyncio.wait_for(
                    self.task_queue.get(),
                    timeout=1.0
                )
                
                func, args, kwargs, task_id = task_data
                
                start_time = datetime.now()
                
                try:
                    result = await func(*args, **kwargs)
                    execution_time = (datetime.now() - start_time).total_seconds()
                    
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
        """Monitor tasks - مراقبة المهام"""
        while self.monitoring:
            try:
                queue_size = self.task_queue.qsize()
                active_count = len(self.active_tasks)
                
                if queue_size > 50:
                    logger.warning(f"حجم قائمة انتظار المهام مرتفع: {queue_size}")
                
                if active_count > 20:
                    logger.warning(f"عدد المهام النشطة مرتفع: {active_count}")
                
                await self._update_metrics()
                
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"خطأ في مراقبة المهام: {e}")
                await asyncio.sleep(10)
    
    async def _update_metrics(self):
        """Update metrics - تحديث المقاييس"""
        pass
    
    async def execute_tasks(self, tasks: List) -> List:
        """Execute tasks - تنفيذ المهام"""
        if not tasks:
            return []
        
        start_time = datetime.now()
        results = []
        
        try:
            semaphore = asyncio.Semaphore(10)
            
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
        """Add task - إضافة مهمة"""
        task_id = f"task_{secrets.token_hex(8)}"
        
        try:
            await self.task_queue.put((func, args, kwargs, task_id))
            self.active_tasks.add(task_id)
            
            return task_id
            
        except asyncio.QueueFull:
            logger.warning("قائمة انتظار المهام ممتلئة")
            raise
    
    def adjust_concurrency(self, adjustment: int):
        """Adjust concurrency - ضبط التزامن"""
        new_max = max(1, min(20, self.max_workers + adjustment))
        
        if new_max != self.max_workers:
            logger.info(f"ضبط التزامن: {self.max_workers} -> {new_max}")
            self.max_workers = new_max
            
            for task in self.worker_tasks:
                task.cancel()
            
            self.worker_tasks = []
            self._start_workers()
    
    def pause(self):
        """Pause - إيقاف مؤقت"""
        self.paused = True
    
    def resume(self):
        """Resume - استئناف"""
        self.paused = False
    
    def stop_monitoring(self):
        """Stop monitoring - إيقاف المراقبة"""
        self.monitoring = False
        
        for task in self.worker_tasks:
            task.cancel()
        
        self.worker_tasks = []
    
    def get_stats(self) -> Dict:
        """Get stats - الحصول على إحصائيات"""
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
    """Intelligent log - سجل ذكي"""
    
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
        
        self._analyze_entry(entry)
    
    def _determine_severity(self, category: str, event: str) -> str:
        """Determine severity - تحديد الخطورة"""
        if category in ['error', 'critical']:
            return 'critical'
        elif category in ['warning', 'rate_limit']:
            return 'warning'
        elif category in ['cycle', 'session']:
            return 'info'
        else:
            return 'debug'
    
    def _analyze_entry(self, entry: Dict):
        """Analyze entry - تحليل الإدخال"""
        pass
    
    def get_recent_entries(self, count: int = 100) -> List[Dict]:
        """Get recent entries - الحصول على الإدخالات الحديثة"""
        return list(self.entries)[-count:]
    
    def get_entries_by_category(self, category: str) -> List[Dict]:
        """Get entries by category - الحصول على الإدخالات حسب الفئة"""
        return [entry for entry in self.entries if entry['category'] == category]
    
    def get_entries_by_severity(self, severity: str) -> List[Dict]:
        """Get entries by severity - الحصول على الإدخالات حسب الخطورة"""
        return [entry for entry in self.entries if entry['severity'] == severity]
    
    def get_summary(self) -> Dict:
        """Get summary - الحصول على ملخص"""
        total_entries = len(self.entries)
        
        if total_entries == 0:
            return {
                'total_entries': 0,
                'categories': {},
                'severity': {},
                'timeline': []
            }
        
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
            'timeline': self.timeline[-100:]
        }
    
    def clear(self):
        """Clear - مسح"""
        self.entries.clear()
        self.categories.clear()
        self.severity_counts.clear()
        self.timeline.clear()
    
    def find_patterns(self) -> List[Dict]:
        """Find patterns - العثور على أنماط"""
        patterns = []
        
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
# Enhanced Session Manager - مدير الجلسات المحسن
# ======================

class EnhancedSessionManager:
    """Enhanced session manager - مدير الجلسات المحسن"""
    
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
        """Create client - إنشاء عميل"""
        cache_key = f"client_{session_id}"
        
        async with EnhancedSessionManager._lock:
            health = EnhancedSessionManager._session_health.get(cache_key)
            if health and health.get('status') == 'unhealthy':
                logger.warning(f"تخطي الجلسة {session_id} غير الصحية")
                return None
            
            cached = await EnhancedSessionManager._session_cache.get(cache_key, 'sessions')
            
            if cached and isinstance(cached, dict) and 'client_data' in cached:
                try:
                    client = TelegramClient(
                        StringSession(cached['client_data']['session_string']),
                        Config.API_ID,
                        Config.API_HASH,
                        **cached['client_data']['client_args']
                    )
                    
                    await client.connect()
                    
                    if await client.is_user_authorized():
                        EnhancedSessionManager._update_metrics(cache_key, 'use')
                        EnhancedSessionManager._update_health(cache_key, 'healthy')
                        
                        return client
                    else:
                        await client.disconnect()
                except Exception as e:
                    logger.debug(f"خطأ في استعادة العميل المخبأ: {e}")
            
            try:
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
                    
                    EnhancedSessionManager._update_health(cache_key, 'unhealthy', 'غير مصرح')
                    return None
                
                me = await client.get_me()
                
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
                    ttl_seconds=3600
                )
                
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
        """Update metrics - تحديث المقاييس"""
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
        """Update health - تحديث الصحة"""
        EnhancedSessionManager._session_health[cache_key] = {
            'status': status,
            'last_check': datetime.now(),
            'reason': reason
        }
    
    @staticmethod
    async def close_client(session_id: int, reason: str = 'normal'):
        """Close client - إغلاق العميل"""
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
                    
                    EnhancedSessionManager._session_metrics[cache_key]['total_time'] += (
                        datetime.now() - EnhancedSessionManager._session_metrics[cache_key].get('last_used', datetime.now())
                    ).total_seconds()
                    
                except Exception as e:
                    logger.debug(f"خطأ في إغلاق العميل: {e}")
            
            await EnhancedSessionManager._session_cache.delete(cache_key, 'sessions')
            
            EnhancedSessionManager._update_health(cache_key, 'closed', reason)
    
    @staticmethod
    async def cleanup_inactive_sessions(timeout_seconds: int = Config.SESSION_TIMEOUT):
        """Cleanup inactive sessions - تنظيف الجلسات غير النشطة"""
        async with EnhancedSessionManager._lock:
            now = datetime.now()
            sessions_to_remove = []
            
            for cache_key, metrics in list(EnhancedSessionManager._session_metrics.items()):
                last_used = metrics.get('last_used')
                
                if last_used and (now - last_used).total_seconds() > timeout_seconds:
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
        """Get session health - الحصول على صحة الجلسة"""
        cache_key = f"client_{session_id}"
        
        return {
            'health': EnhancedSessionManager._session_health.get(cache_key, {}),
            'metrics': EnhancedSessionManager._session_metrics.get(cache_key, {}),
            'cached': await EnhancedSessionManager._session_cache.exists(cache_key, 'sessions')
        }
    
    @staticmethod
    def get_all_metrics() -> Dict:
        """Get all metrics - الحصول على جميع المقاييس"""
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
        """Validate session - التحقق من الجلسة"""
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
                return False, {'error': 'غير مصرح', 'details': 'الجلسة غير مفعلة'}
            
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
    
    @staticmethod
    def clear_cache():
        """Clear cache - مسح الكاش"""
        EnhancedSessionManager._session_cache.clear()
        EnhancedSessionManager._session_health.clear()
        EnhancedSessionManager._session_metrics.clear()

# ======================
# Cache Manager - مدير الكاش
# ======================

class CacheManager:
    """Cache manager - مدير الكاش"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get instance - الحصول على المثيل"""
        if cls._instance is None:
            cls._instance = CacheManager()
        return cls._instance
    
    def __init__(self):
        self.fast_cache = OrderedDict()
        self.fast_cache_size = 5000
        
        self.slow_cache_dir = "cache_data"
        os.makedirs(self.slow_cache_dir, exist_ok=True)
        
        self.stats = {
            'fast_hits': 0,
            'slow_hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_operations': 0
        }
        
        self.lock = asyncio.Lock()
    
    async def get(self, key: str, category: str = 'general') -> Optional[Any]:
        """Get from cache - الحصول من الكاش"""
        async with self.lock:
            self.stats['total_operations'] += 1
            cache_key = f"{category}_{key}"
            
            if cache_key in self.fast_cache:
                self.fast_cache.move_to_end(cache_key)
                self.stats['fast_hits'] += 1
                return self.fast_cache[cache_key]
            
            file_path = os.path.join(self.slow_cache_dir, f"{hashlib.md5(cache_key.encode()).hexdigest()}.cache")
            if os.path.exists(file_path):
                try:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        data = json.loads(content)
                        
                        await self._add_to_fast_cache(cache_key, data)
                        self.stats['slow_hits'] += 1
                        return data
                except:
                    pass
            
            self.stats['misses'] += 1
            return None
    
    async def set(self, key: str, value: Any, category: str = 'general', ttl_seconds: int = 3600):
        """Set in cache - تعيين في الكاش"""
        async with self.lock:
            cache_key = f"{category}_{key}"
            
            await self._add_to_fast_cache(cache_key, value)
            
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
        """Add to fast cache - إضافة للكاش السريع"""
        if key in self.fast_cache:
            self.fast_cache.move_to_end(key)
            self.fast_cache[key] = value
        else:
            self.fast_cache[key] = value
            
            if len(self.fast_cache) > self.fast_cache_size:
                oldest_key = next(iter(self.fast_cache))
                del self.fast_cache[oldest_key]
                self.stats['evictions'] += 1
    
    def exists(self, key: str, category: str = 'general') -> bool:
        """Check if exists - التحقق من الوجود"""
        cache_key = f"{category}_{key}"
        return cache_key in self.fast_cache
    
    async def delete(self, key: str, category: str = 'general'):
        """Delete from cache - حذف من الكاش"""
        async with self.lock:
            cache_key = f"{category}_{key}"
            
            if cache_key in self.fast_cache:
                del self.fast_cache[cache_key]
            
            file_path = os.path.join(self.slow_cache_dir, f"{hashlib.md5(cache_key.encode()).hexdigest()}.cache")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
    
    async def cleanup_expired(self):
        """Cleanup expired - تنظيف المنتهي"""
        async with self.lock:
            expired_count = 0
            
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
        """Optimize - تحسين"""
        current_size = len(self.fast_cache)
        if current_size > self.fast_cache_size:
            target_size = int(self.fast_cache_size * 0.8)
            while len(self.fast_cache) > target_size:
                oldest_key = next(iter(self.fast_cache))
                del self.fast_cache[oldest_key]
                self.stats['evictions'] += 1
    
    def get_stats(self) -> Dict:
        """Get stats - الحصول على إحصائيات"""
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
        """Clear - مسح"""
        async with self.lock:
            self.fast_cache.clear()
            
            if os.path.exists(self.slow_cache_dir):
                for filename in os.listdir(self.slow_cache_dir):
                    if filename.endswith('.cache'):
                        try:
                            os.remove(os.path.join(self.slow_cache_dir, filename))
                        except:
                            pass
            
            self.stats = {
                'fast_hits': 0,
                'slow_hits': 0,
                'misses': 0,
                'evictions': 0,
                'total_operations': 0
            }

# ======================
# Memory Manager - مدير الذاكرة
# ======================

class MemoryManager:
    """Memory manager - مدير الذاكرة"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get instance - الحصول على المثيل"""
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
        """Get memory usage - الحصول على استخدام الذاكرة"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except Exception as e:
            logger.debug(f"خطأ في قراءة الذاكرة: {e}")
            return 0
    
    def get_memory_percent(self) -> float:
        """Get memory percent - الحصول على نسبة الذاكرة"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_percent()
        except:
            return 0
    
    def get_system_memory(self) -> Dict:
        """Get system memory - الحصول على ذاكرة النظام"""
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
        """Optimize memory - تحسين الذاكرة"""
        before = self.get_memory_usage()
        before_time = datetime.now()
        
        gc.collect()
        
        try:
            process = psutil.Process(os.getpid())
            open_files = len(process.open_files())
            if open_files > 50:
                logger.warning(f"عدد كبير من الملفات المفتوحة: {open_files}", {
                    'open_files': open_files
                })
        except:
            pass
        
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
        """Check and optimize - التحقق والتحسين"""
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
        """Get metrics - الحصول على المقاييس"""
        return {
            **self.metrics,
            'current_mb': self.get_memory_usage(),
            'current_percent': self.get_memory_percent(),
            'system_memory': self.get_system_memory()
        }

# ======================
# Encryption Manager - مدير التشفير
# ======================

class EncryptionManager:
    """Encryption manager - مدير التشفير"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get instance - الحصول على المثيل"""
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
        """Encrypt - تشفير"""
        try:
            encrypted = self.cipher.encrypt(data.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"خطأ في التشفير: {e}")
            return data
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt - فك التشفير"""
        try:
            decrypted = self.cipher.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"خطأ في فك التشفير: {e}")
            return encrypted_data
    
    def encrypt_session(self, session_string: str) -> str:
        """Encrypt session - تشفير الجلسة"""
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
        """Decrypt session - فك تشفير الجلسة"""
        try:
            decrypted = self.decrypt(encrypted_data)
            data = json.loads(decrypted)
            return data['session']
        except Exception as e:
            logger.error(f"خطأ في فك تشفير الجلسة: {e}")
            return None

# ======================
# Backup Manager - مدير النسخ الاحتياطي
# ======================

class BackupManager:
    """Backup manager - مدير النسخ الاحتياطي"""
    
    @staticmethod
    async def create_backup() -> Optional[Dict]:
        """Create backup - إنشاء نسخة احتياطية"""
        if not Config.BACKUP_ENABLED:
            return None
        
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = "backups"
            backup_filename = f"{Config.DB_PATH}.backup_{timestamp}"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            os.makedirs(backup_dir, exist_ok=True)
            
            if not os.path.exists(Config.DB_PATH):
                logger.error("ملف قاعدة البيانات غير موجود")
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
        """Calculate checksum - حساب مجموع التحقق"""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    @staticmethod
    async def rotate_backups():
        """Rotate backups - تدوير النسخ"""
        try:
            if not os.path.exists("backups"):
                return
            
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
                return
            
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

# ======================
# Structured Logger - مسجل هيكلي
# ======================

class StructuredLogger:
    """Structured logger - مسجل هيكلي"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.request_id = 0
        
    def generate_request_id(self) -> str:
        """Generate request ID - توليد معرف طلب"""
        self.request_id += 1
        return f"REQ-{self.request_id:06d}-{secrets.token_hex(4)}"
    
    def info(self, message: str, extra: Dict = None):
        """Info log - تسجيل معلومات"""
        context = {
            'request_id': self.generate_request_id(),
            'timestamp': datetime.now().isoformat(),
            'memory_mb': MemoryManager.get_instance().get_memory_usage()
        }
        if extra:
            context.update(extra)
        
        self.logger.info(f"{message} | {json.dumps(context, ensure_ascii=False)}")
    
    def error(self, message: str, exc_info: bool = True, extra: Dict = None):
        """Error log - تسجيل خطأ"""
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
        """Warning log - تسجيل تحذير"""
        context = {
            'request_id': self.generate_request_id(),
            'timestamp': datetime.now().isoformat()
        }
        if extra:
            context.update(extra)
        
        self.logger.warning(f"{message} | {json.dumps(context, ensure_ascii=False)}")
    
    def debug(self, message: str, extra: Dict = None):
        """Debug log - تسجيل تصحيح"""
        context = {
            'request_id': self.generate_request_id(),
            'timestamp': datetime.now().isoformat(),
            'memory_mb': MemoryManager.get_instance().get_memory_usage(),
            'cache_hits': CacheManager.get_instance().get_stats()['hits']
        }
        if extra:
            context.update(extra)
        
        self.logger.debug(f"{message} | {json.dumps(context, ensure_ascii=False)}")

# ======================
# Main Entry Point - نقطة الدخول الرئيسية
# ======================

def setup_logging():
    """Setup logging - إعداد التسجيل"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler('bot.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)
    
    return StructuredLogger()

logger = setup_logging()

async def main():
    """Main function - الوظيفة الرئيسية"""
    setup_signal_handlers()
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    else:
        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            logger.info("✅ استخدام uvloop لتحسين الأداء")
        except ImportError:
            logger.info("⚠️ uvloop غير مثبت. استخدام حلقة الأحداث الافتراضية")
    
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_NOFILE, (8192, 8192))
        logger.info("✅ تم تعيين حدود الملفات المفتوحة")
    except:
        logger.warning("⚠️ لم يتمكن من تعيين حدود الملفات المفتوحة")
    
    required_env_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH']
    missing = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing:
        logger.error(f"❌ متغيرات بيئية مفقودة: {missing}")
        print(f"❌ خطأ: المتغيرات البيئية التالية مفقودة: {', '.join(missing)}")
        print("يرجى تعيينها قبل التشغيل:")
        for var in missing:
            print(f"export {var}=قيمتك_هنا")
        sys.exit(1)
    
    if Config.ENCRYPTION_KEY == Fernet.generate_key().decode():
        logger.warning("⚠️ استخدام مفتاح تشفير مؤقت. يوصى بتعيين ENCRYPTION_KEY دائم")
    
    os.makedirs("backups", exist_ok=True)
    os.makedirs("cache_data", exist_ok=True)
    os.makedirs("exports", exist_ok=True)
    
    bot = AdvancedTelegramBot()
    
    logger.info("🤖 بدء تشغيل بوت جمع الروابط الذكي المتقدم...")
    logger.info("⚙️ الإعدادات المتقدمة:", {
        'max_sessions': Config.MAX_CONCURRENT_SESSIONS,
        'max_memory_mb': Config.MAX_MEMORY_MB,
        'backup_enabled': Config.BACKUP_ENABLED,
        'encryption_enabled': bool(Config.ENCRYPTION_KEY),
        'telegram_no_time_limit': Config.TELEGRAM_NO_TIME_LIMIT,
        'whatsapp_days_back': Config.WHATSAPP_DAYS_BACK,
        'join_request_check_delay': Config.JOIN_REQUEST_CHECK_DELAY
    })
    
    try:
        cache_manager = CacheManager.get_instance()
        memory_manager = MemoryManager.get_instance()
        
        asyncio.create_task(periodic_maintenance())
        
        await bot.app.initialize()
        await bot.app.start()
        await bot.app.updater.start_polling()
        
        logger.info("🚀 البوت يعمل بنجاح!")
        
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"❌ خطأ في البوت المتقدم: {e}", exc_info=True)
        raise
        
    finally:
        logger.info("🧹 جاري التنظيف النهائي...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            await db.close()
            
            await bot.app.stop()
            
            cache_manager.clear()
            
            logger.info("✅ اكتمل الإغلاق السلس")
            
        except Exception as e:
            logger.error(f"❌ خطأ في التنظيف النهائي: {e}")

async def periodic_maintenance():
    """Periodic maintenance - الصيانة الدورية"""
    while True:
        try:
            cache_manager = CacheManager.get_instance()
            await cache_manager.cleanup_expired()
            
            memory_manager = MemoryManager.get_instance()
            memory_manager.check_and_optimize()
            
            if Config.BACKUP_ENABLED:
                await BackupManager.rotate_backups()
            
            logger.debug("✅ الصيانة الدورية مكتملة", {
                'memory_mb': memory_manager.get_memory_usage(),
                'cache_size': cache_manager.get_stats()['fast_cache_size']
            })
            
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"خطأ في الصيانة الدورية: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 توقف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ قاتل: {e}", exc_info=True)
        sys.exit(1)
