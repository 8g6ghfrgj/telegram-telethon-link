import os
import sys
import subprocess
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
from telegram.error import TelegramError, Conflict
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
# 🔧 FIX: تثبيت الحزم المفقودة
# ======================

def install_required_packages():
    """تثبيت الحزم المطلوبة"""
    required = [
        'python-telegram-bot==20.7',
        'Telethon==1.34.0',
        'aiosqlite==0.19.0',
        'aiofiles==23.2.1',
        'cryptography==42.0.5',
        'psutil==5.9.8',
        'aiohttp==3.11.3',
        'pytz==2023.3',
    ]
    
    for package in required:
        pkg_name = package.split('==')[0]
        try:
            __import__(pkg_name.replace('-', '_'))
        except ImportError:
            print(f"📦 تثبيت {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package, "--quiet"])

install_required_packages()

# ======================
# 🔧 Configuration - الإعدادات
# ======================

class Config:
    # بيانات API التليجرام
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH", "")
    
    # إدارة الوصول
    @staticmethod
    def parse_ids(env_var):
        value = os.getenv(env_var, "")
        if not value:
            return set()
        
        ids = set()
        for id_str in value.split(","):
            id_str = id_str.strip()
            if id_str:
                try:
                    ids.add(int(id_str))
                except ValueError:
                    continue
        return ids
    
    ADMIN_USER_IDS = parse_ids("ADMIN_USER_IDS")
    ALLOWED_USER_IDS = parse_ids("ALLOWED_USER_IDS")
    
    # الأمان
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    
    # إدارة الذاكرة والأداء
    MAX_CACHED_URLS = 20000
    MAX_MEMORY_MB = 500
    MAX_CONCURRENT_SESSIONS = 10
    REQUEST_DELAYS = {
        'normal': 1.0,
        'join_request': 5.0,
        'search': 2.0,
        'flood_wait': 5.0,
        'between_sessions': 2.0,
        'between_tasks': 0.5,
        'min_cycle_delay': 15.0,
        'max_cycle_delay': 60.0,
    }
    
    # حدود الجمع
    MAX_DIALOGS_PER_SESSION = 50
    MAX_MESSAGES_PER_SEARCH = 10
    MAX_SEARCH_TERMS = 5
    MAX_LINKS_PER_CYCLE = 100
    MAX_BATCH_SIZE = 25
    
    # قاعدة البيانات
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 5
    
    # جمع واتساب
    WHATSAPP_DAYS_BACK = 30
    
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
    MAX_SESSIONS_PER_USER = 5
    
    # التصدير
    MAX_EXPORT_LINKS = 50000
    EXPORT_CHUNK_SIZE = 5000

# ======================
# 🔧 Setup Logging - إعداد التسجيل
# ======================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# ======================
# 🔧 Database Manager - مدير قاعدة البيانات
# ======================

class DatabaseManager:
    _instance = None
    _initialized = False
    
    @classmethod
    async def get_instance(cls):
        if cls._instance is None:
            cls._instance = DatabaseManager()
            await cls._instance.initialize()
        return cls._instance
    
    async def initialize(self):
        if self._initialized:
            return
        
        self.db_path = Config.DB_PATH
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        
        # إنشاء الاتصال
        self.connection = await aiosqlite.connect(self.db_path)
        await self.create_tables()
        
        self._initialized = True
        logger.info(f"✅ تم تهيئة قاعدة البيانات: {self.db_path}")
    
    async def create_tables(self):
        """إنشاء الجداول"""
        async with self.connection.cursor() as cursor:
            # جدول الجلسات
            await cursor.execute('''
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
                    status TEXT DEFAULT 'active'
                )
            ''')
            
            # جدول الروابط
            await cursor.execute('''
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
                    check_count INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    is_verified BOOLEAN DEFAULT 0,
                    validation_score INTEGER DEFAULT 0,
                    added_by_user INTEGER,
                    source TEXT,
                    is_channel BOOLEAN DEFAULT 0,
                    is_group BOOLEAN DEFAULT 0
                )
            ''')
            
            # جدول المستخدمين
            await cursor.execute('''
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
            
            # فهارس
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_links_url_hash ON links(url_hash)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_links_platform ON links(platform)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)')
            
            await self.connection.commit()
    
    async def add_user(self, user_id: int, username: str = "", first_name: str = "", last_name: str = ""):
        """إضافة مستخدم"""
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
                INSERT OR REPLACE INTO bot_users 
                (user_id, username, first_name, last_name, last_active, request_count)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, COALESCE((SELECT request_count + 1 FROM bot_users WHERE user_id = ?), 1))
            ''', (user_id, username, first_name, last_name, user_id))
            await self.connection.commit()
    
    async def get_user(self, user_id: int):
        """الحصول على معلومات المستخدم"""
        async with self.connection.cursor() as cursor:
            await cursor.execute('SELECT * FROM bot_users WHERE user_id = ?', (user_id,))
            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
    
    async def add_session(self, session_string: str, user_id: int, phone_number: str = "", username: str = ""):
        """إضافة جلسة"""
        session_hash = hashlib.sha256(session_string.encode()).hexdigest()
        
        async with self.connection.cursor() as cursor:
            await cursor.execute('''
                INSERT OR REPLACE INTO sessions 
                (session_string, session_hash, phone_number, user_id, username, added_by_user, added_date)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (session_string, session_hash, phone_number, user_id, username, user_id))
            await self.connection.commit()
            
            await cursor.execute('SELECT last_insert_rowid()')
            session_id = (await cursor.fetchone())[0]
            
            return session_id
    
    async def get_sessions(self, active_only: bool = True, limit: int = 50):
        """الحصول على الجلسات"""
        async with self.connection.cursor() as cursor:
            if active_only:
                await cursor.execute('''
                    SELECT * FROM sessions 
                    WHERE is_active = 1 
                    ORDER BY last_used ASC, total_uses ASC
                    LIMIT ?
                ''', (limit,))
            else:
                await cursor.execute('SELECT * FROM sessions LIMIT ?', (limit,))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    
    async def add_link(self, url: str, platform: str, session_id: int = None, 
                      added_by_user: int = 0, title: str = "", members_count: int = 0):
        """إضافة رابط"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        
        async with self.connection.cursor() as cursor:
            # التحقق من التكرار
            await cursor.execute('SELECT id FROM links WHERE url_hash = ?', (url_hash,))
            if await cursor.fetchone():
                return False, "الرابط موجود مسبقاً"
            
            await cursor.execute('''
                INSERT INTO links 
                (url_hash, url, platform, session_id, added_by_user, title, members_count, collected_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (url_hash, url, platform, session_id, added_by_user, title, members_count))
            
            await self.connection.commit()
            return True, "تمت إضافة الرابط بنجاح"
    
    async def get_links(self, platform: str = None, limit: int = 100, offset: int = 0):
        """الحصول على الروابط"""
        async with self.connection.cursor() as cursor:
            if platform:
                await cursor.execute('''
                    SELECT * FROM links 
                    WHERE platform = ? AND is_active = 1
                    ORDER BY collected_date DESC
                    LIMIT ? OFFSET ?
                ''', (platform, limit, offset))
            else:
                await cursor.execute('''
                    SELECT * FROM links 
                    WHERE is_active = 1
                    ORDER BY collected_date DESC
                    LIMIT ? OFFSET ?
                ''', (limit, offset))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    
    async def get_stats(self):
        """الحصول على الإحصائيات"""
        async with self.connection.cursor() as cursor:
            stats = {}
            
            await cursor.execute('SELECT COUNT(*) FROM links')
            stats['total_links'] = (await cursor.fetchone())[0]
            
            await cursor.execute('SELECT COUNT(*) FROM sessions WHERE is_active = 1')
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            await cursor.execute('SELECT COUNT(*) FROM bot_users')
            stats['total_users'] = (await cursor.fetchone())[0]
            
            await cursor.execute('SELECT platform, COUNT(*) FROM links GROUP BY platform')
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            return stats
    
    async def close(self):
        """إغلاق الاتصال"""
        if hasattr(self, 'connection') and self.connection:
            await self.connection.close()
            self._initialized = False

# ======================
# 🔧 Link Processor - معالج الروابط
# ======================

class LinkProcessor:
    """معالج الروابط الذكي"""
    
    @staticmethod
    def normalize_url(url: str) -> str:
        """توحيد الرابط"""
        if not url:
            return ""
        
        url = url.strip()
        
        # إضافة https إذا كانت مفقودة
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # إزالة المسارات الزائدة
        url = re.sub(r'/+$', '', url)
        
        return url.lower()
    
    @staticmethod
    def extract_url_info(url: str) -> Dict:
        """استخراج معلومات الرابط"""
        normalized = LinkProcessor.normalize_url(url)
        
        if not normalized:
            return {'is_valid': False}
        
        result = {
            'original_url': url,
            'normalized_url': normalized,
            'is_valid': True,
            'platform': 'unknown',
            'url_hash': hashlib.md5(normalized.encode()).hexdigest()
        }
        
        # تحديد المنصة
        if 't.me' in normalized or 'telegram.me' in normalized:
            result['platform'] = 'telegram'
            result['telegram_info'] = LinkProcessor._extract_telegram_info(normalized)
        elif 'chat.whatsapp.com' in normalized:
            result['platform'] = 'whatsapp'
        elif 'discord.gg' in normalized:
            result['platform'] = 'discord'
        
        return result
    
    @staticmethod
    def _extract_telegram_info(url: str) -> Dict:
        """استخراج معلومات تيليجرام"""
        info = {
            'is_join_link': False,
            'is_channel': False,
            'is_group': False,
            'username': '',
            'invite_hash': ''
        }
        
        # كشف روابط الانضمام
        join_patterns = [
            r'joinchat/([A-Za-z0-9_-]+)',
            r'\+(?:joinchat/)?([A-Za-z0-9_-]+)'
        ]
        
        for pattern in join_patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                info['is_join_link'] = True
                info['invite_hash'] = match.group(1)
                info['is_group'] = True
                return info
        
        # كشف القنوات
        if '/c/' in url or '/channel/' in url or 't.me/c/' in url:
            info['is_channel'] = True
            parts = url.split('/')
            if len(parts) > 3:
                info['username'] = parts[-1]
        
        # كشف المجموعات العامة
        else:
            parts = url.split('/')
            if len(parts) >= 4:
                username = parts[-1]
                if username and not username.startswith('?'):
                    info['username'] = username
                    info['is_group'] = True
        
        return info

# ======================
# 🔧 Session Manager - مدير الجلسات
# ======================

class SessionManager:
    """مدير جلسات التليجرام"""
    
    @staticmethod
    async def create_client(session_string: str) -> Optional[TelegramClient]:
        """إنشاء عميل تيليجرام"""
        try:
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH,
                device_model="Link Collector",
                system_version="Linux",
                app_version="4.0"
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return None
            
            return client
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء العميل: {e}")
            return None
    
    @staticmethod
    async def validate_session(session_string: str) -> Tuple[bool, Dict]:
        """التحقق من صحة الجلسة"""
        try:
            client = await SessionManager.create_client(session_string)
            if not client:
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
            return True, user_info
            
        except Exception as e:
            return False, {'error': str(e)[:200]}

# ======================
# 🔧 Collection Manager - مدير الجمع
# ======================

class CollectionManager:
    """مدير جمع الروابط"""
    
    def __init__(self):
        self.is_active = False
        self.is_paused = False
        self.current_task = None
        
        self.stats = {
            'total_collected': 0,
            'telegram_links': 0,
            'whatsapp_links': 0,
            'discord_links': 0,
            'errors': 0,
            'start_time': None,
            'end_time': None
        }
    
    async def start_collection(self):
        """بدء الجمع"""
        if self.is_active:
            return False, "الجمع يعمل بالفعل"
        
        self.is_active = True
        self.is_paused = False
        self.stats['start_time'] = datetime.now()
        self.stats['total_collected'] = 0
        self.stats['errors'] = 0
        
        self.current_task = asyncio.create_task(self._collection_loop())
        
        logger.info("🚀 بدء عملية الجمع")
        return True, "بدأت عملية الجمع بنجاح"
    
    async def _collection_loop(self):
        """حلقة الجمع الرئيسية"""
        while self.is_active:
            if self.is_paused:
                await asyncio.sleep(1)
                continue
            
            try:
                await self._collect_cycle()
                await asyncio.sleep(30)  # تأخير بين الدورات
                
            except Exception as e:
                logger.error(f"خطأ في دورة الجمع: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(60)
    
    async def _collect_cycle(self):
        """دورة جمع واحدة"""
        try:
            db = await DatabaseManager.get_instance()
            sessions = await db.get_sessions(active_only=True, limit=Config.MAX_CONCURRENT_SESSIONS)
            
            if not sessions:
                logger.warning("لا توجد جلسات نشطة")
                return
            
            logger.info(f"بدء دورة جمع مع {len(sessions)} جلسة")
            
            tasks = []
            for session in sessions:
                task = self._process_session(session)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful = sum(1 for r in results if not isinstance(r, Exception))
            logger.info(f"اكتملت الدورة: {successful} ناجحة من {len(sessions)}")
            
        except Exception as e:
            logger.error(f"خطأ في دورة الجمع: {e}")
            raise
    
    async def _process_session(self, session: Dict):
        """معالجة جلسة واحدة"""
        session_id = session['id']
        session_string = session['session_string']
        
        try:
            client = await SessionManager.create_client(session_string)
            if not client:
                logger.warning(f"الجلسة {session_id} غير مصرح بها")
                return
            
            # جمع الروابط من الدردشات
            collected = await self._collect_from_dialogs(client, session_id)
            
            # تحديث إحصائيات الجلسة
            db = await DatabaseManager.get_instance()
            async with db.connection.cursor() as cursor:
                await cursor.execute('''
                    UPDATE sessions 
                    SET last_used = CURRENT_TIMESTAMP, 
                        total_uses = total_uses + 1,
                        total_links = total_links + ?
                    WHERE id = ?
                ''', (len(collected), session_id))
                await db.connection.commit()
            
            await client.disconnect()
            
            logger.info(f"الجلسة {session_id}: جمعت {len(collected)} رابط")
            return collected
            
        except FloodWaitError as e:
            logger.warning(f"انتظار flood للجلسة {session_id}: {e.seconds} ثانية")
            await asyncio.sleep(e.seconds + 5)
            raise
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الجلسة {session_id}: {e}")
            raise
    
    async def _collect_from_dialogs(self, client: TelegramClient, session_id: int) -> List[Dict]:
        """جمع الروابط من الدردشات"""
        collected = []
        
        try:
            dialogs = []
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                dialogs.append(dialog)
            
            for dialog in dialogs[:20]:  # الحد لـ 20 دردشة
                if not self.is_active or self.is_paused:
                    break
                
                try:
                    links = await self._extract_links_from_dialog(client, dialog, session_id)
                    collected.extend(links)
                    
                    await asyncio.sleep(Config.REQUEST_DELAYS['normal'])
                    
                except Exception as e:
                    logger.debug(f"خطأ في معالجة الدردشة: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"خطأ في جمع الدردشات: {e}")
        
        return collected
    
    async def _extract_links_from_dialog(self, client: TelegramClient, dialog, session_id: int) -> List[Dict]:
        """استخراج الروابط من دردشة"""
        links = []
        
        try:
            entity = dialog.entity
            
            # جمع من الوصف
            if hasattr(entity, 'about') and entity.about:
                text_links = self._extract_links_from_text(entity.about)
                for link in text_links:
                    links.append({
                        'url': link,
                        'source': 'description',
                        'session_id': session_id
                    })
            
            # جمع من الرسائل
            try:
                async for message in client.iter_messages(entity, limit=5):
                    if not message.text:
                        continue
                    
                    text_links = self._extract_links_from_text(message.text)
                    for link in text_links:
                        links.append({
                            'url': link,
                            'source': 'message',
                            'session_id': session_id,
                            'message_date': message.date.isoformat() if hasattr(message, 'date') else None
                        })
                    
                    if len(links) >= 10:  # الحد الأقصى لكل دردشة
                        break
                        
            except Exception as e:
                logger.debug(f"خطأ في قراءة الرسائل: {e}")
        
        except Exception as e:
            logger.debug(f"خطأ في استخراج الروابط: {e}")
        
        return links
    
    def _extract_links_from_text(self, text: str) -> List[str]:
        """استخراج الروابط من النص"""
        if not text:
            return []
        
        patterns = [
            r'https?://[^\s<>"\']+',
            r't\.me/[^\s<>"\']+',
            r'telegram\.me/[^\s<>"\']+',
            r'chat\.whatsapp\.com/[^\s<>"\']+',
            r'discord\.gg/[^\s<>"\']+',
            r'joinchat/[^\s<>"\']+'
        ]
        
        all_links = []
        for pattern in patterns:
            found = re.findall(pattern, text, re.IGNORECASE)
            all_links.extend(found)
        
        # تحسين الروابط
        improved_links = []
        for link in all_links:
            if link.startswith('t.me'):
                link = 'https://' + link
            elif link.startswith('joinchat'):
                link = f'https://t.me/{link}'
            
            improved_links.append(link)
        
        return list(set(improved_links))  # إزالة التكرارات
    
    async def stop_collection(self):
        """إيقاف الجمع"""
        self.is_active = False
        self.is_paused = False
        
        if self.current_task:
            self.current_task.cancel()
            try:
                await self.current_task
            except asyncio.CancelledError:
                pass
        
        self.stats['end_time'] = datetime.now()
        logger.info("⏹️ توقفت عملية الجمع")
        
        return True, "تم إيقاف الجمع بنجاح"
    
    async def pause_collection(self):
        """إيقاف الجمع مؤقتاً"""
        if not self.is_active:
            return False, "الجمع غير نشط"
        
        self.is_paused = True
        logger.info("⏸️ تم إيقاف الجمع مؤقتاً")
        return True, "تم الإيقاف المؤقت"
    
    async def resume_collection(self):
        """استئناف الجمع"""
        if not self.is_active:
            return False, "الجمع غير نشط"
        
        self.is_paused = False
        logger.info("▶️ تم استئناف الجمع")
        return True, "تم الاستئناف"
    
    def get_status(self) -> Dict:
        """الحصول على حالة الجمع"""
        return {
            'is_active': self.is_active,
            'is_paused': self.is_paused,
            'stats': self.stats.copy()
        }

# ======================
# 🔧 Telegram Bot - البوت الرئيسي
# ======================

class TelegramBot:
    """البوت الرئيسي للتليجرام"""
    
    def __init__(self):
        self.application = None
        self.collection_manager = CollectionManager()
        self.db_manager = None
        self.user_states = {}
        
    async def initialize(self):
        """تهيئة البوت"""
        # إنشاء تطبيق البوت
        self.application = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        
        # إضافة المعالجات
        self._setup_handlers()
        
        # تهيئة قاعدة البيانات
        self.db_manager = await DatabaseManager.get_instance()
        
        logger.info("✅ تم تهيئة البوت بنجاح")
    
    def _setup_handlers(self):
        """إعداد معالجات الأوامر"""
        # أوامر البداية والمساعدة
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # أوامر الجمع
        self.application.add_handler(CommandHandler("collect", self.collect_command))
        self.application.add_handler(CommandHandler("stop", self.stop_command))
        self.application.add_handler(CommandHandler("pause", self.pause_command))
        self.application.add_handler(CommandHandler("resume", self.resume_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        
        # أوامر الجلسات
        self.application.add_handler(CommandHandler("addsession", self.add_session_command))
        self.application.add_handler(CommandHandler("sessions", self.sessions_command))
        
        # أوامر الروابط
        self.application.add_handler(CommandHandler("links", self.links_command))
        self.application.add_handler(CommandHandler("export", self.export_command))
        
        # أوامر الإحصائيات
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        
        # معالج الاستدعاءات
        self.application.add_handler(CallbackQueryHandler(self.callback_handler))
        
        # معالج الرسائل النصية
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler))
        
        # معالج الأخطاء
        self.application.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /start"""
        user = update.effective_user
        
        # التحقق من الصلاحيات
        if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            await update.message.reply_text("❌ غير مصرح لك باستخدام هذا البوت.")
            return
        
        # إضافة/تحديث المستخدم
        await self.db_manager.add_user(
            user.id,
            user.username or "",
            user.first_name or "",
            user.last_name or ""
        )
        
        welcome_text = f"""
👋 أهلاً {user.first_name}!

🤖 **بوت جمع الروابط الذكي**

**المميزات:**
• جمع روابط المجموعات والقنوات من تيليجرام
• دعم واتساب وديسكورد
• إدارة متعددة للجلسات
• تصدير الروابط بصيغ مختلفة
• إحصائيات مفصلة

**الأوامر المتاحة:**

🚀 **الجمع:**
/collect - بدء جمع الروابط
/stop - إيقاف الجمع
/pause - إيقاف مؤقت
/resume - استئناف
/status - حالة الجمع

👥 **الجلسات:**
/addsession - إضافة جلسة تيليجرام
/sessions - عرض الجلسات

🔗 **الروابط:**
/links - عرض الروابط المجمعة
/export - تصدير الروابط

📊 **إحصائيات:**
/stats - عرض الإحصائيات
/help - المساعدة

💡 **نصائح:**
• يمكنك إضافة جلسات تيليجرام باستخدام /addsession
• ابدأ الجمع بـ /collect
• تصدير الروابط بـ /export
"""
        
        keyboard = [
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session")],
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")],
            [InlineKeyboardButton("❓ المساعدة", callback_data="show_help")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /help"""
        help_text = """
📚 **دليل استخدام البوت**

**١- إضافة الجلسات:**
• استخدم `/addsession` ثم أرسل كود الجلسة
• يمكنك الحصول على كود الجلسة من @SessionStringGeneratorBot
• يمكنك إضافة حتى 5 جلسات

**٢- بدء الجمع:**
• استخدم `/collect` لبدء جمع الروابط
• النظام يجمع تلقائياً من جميع جلساتك
• يمكنك إيقاف الجمع بـ `/stop`

**٣- عرض الروابط:**
• `/links` لعرض آخر الروابط المجمعة
• `/export` لتصدير جميع الروابط

**٤- الإحصائيات:**
• `/stats` لعرض إحصائيات النظام
• `/status` لعرض حالة الجمع الحالية

**٥- الإدارة:**
• `/sessions` لعرض جلساتك
• `/pause` و `/resume` للتحكم بالجمع

**📞 الدعم:**
لأي استفسارات، راسل المطور: @username
"""
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /collect"""
        user = update.effective_user
        
        # التحقق من وجود جلسات
        sessions = await self.db_manager.get_sessions(active_only=True)
        if not sessions:
            await update.message.reply_text("❌ ليس لديك جلسات نشطة. أضف جلسة أولاً باستخدام /addsession")
            return
        
        status = self.collection_manager.get_status()
        if status['is_active']:
            await update.message.reply_text("⏳ الجمع يعمل بالفعل!")
            return
        
        # بدء الجمع
        success, message = await self.collection_manager.start_collection()
        
        if success:
            keyboard = [
                [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
                [InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
                [InlineKeyboardButton("📊 الحالة", callback_data="collect_status")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🚀 {message}\n"
                f"• الجلسات النشطة: {len(sessions)}\n"
                f"• سيبدأ الجمع تلقائياً...",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(f"❌ {message}")
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /stop"""
        status = self.collection_manager.get_status()
        if not status['is_active']:
            await update.message.reply_text("⚠️ الجمع غير نشط حالياً")
            return
        
        success, message = await self.collection_manager.stop_collection()
        await update.message.reply_text(f"✅ {message}")
    
    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /pause"""
        success, message = await self.collection_manager.pause_collection()
        await update.message.reply_text(f"✅ {message}")
    
    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /resume"""
        success, message = await self.collection_manager.resume_collection()
        await update.message.reply_text(f"✅ {message}")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /status"""
        status = self.collection_manager.get_status()
        sessions = await self.db_manager.get_sessions(active_only=True)
        
        status_text = f"""
📊 **حالة النظام**

**الحالة:** {'🟢 نشط' if status['is_active'] else '🔴 متوقف'}
**الإيقاف المؤقت:** {'⏸️ نعم' if status['is_paused'] else '▶️ لا'}

**الجمع:**
• بدأ في: {status['stats']['start_time'].strftime('%Y-%m-%d %H:%M') if status['stats']['start_time'] else '---'}
• الروابط المجمعة: {status['stats']['total_collected']:,}
• الأخطاء: {status['stats']['errors']}

**الجلسات:** {len(sessions)} نشطة
"""
        
        keyboard = [
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_status")],
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(status_text, reply_markup=reply_markup)
    
    async def add_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /addsession"""
        user = update.effective_user
        
        # التحقق من الحد الأقصى للجلسات
        sessions = await self.db_manager.get_sessions(active_only=False)
        user_sessions = [s for s in sessions if s.get('added_by_user') == user.id]
        
        if len(user_sessions) >= Config.MAX_SESSIONS_PER_USER:
            await update.message.reply_text(
                f"❌ وصلت للحد الأقصى للجلسات ({Config.MAX_SESSIONS_PER_USER}). "
                f"حذف بعض الجلسات أولاً."
            )
            return
        
        self.user_states[user.id] = {
            'state': 'awaiting_session',
            'data': {}
        }
        
        help_text = """
📱 **إضافة جلسة تيليجرام**

لإضافة جلسة، اتبع الخطوات:

1. اذهب إلى @SessionStringGeneratorBot
2. أرسل /start للبوت
3. اختر Generate New Session
4. أرسل رقم هاتفك (مع رمز الدولة)
5. أدخل الكود الذي وصلك
6. احصل على كود الجلسة (String Session)

**ثم أرسل لي كود الجلسة هنا.**

❌ لإلغاء العملية، أرسل /cancel
"""
        
        await update.message.reply_text(help_text)
    
    async def sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /sessions"""
        user = update.effective_user
        sessions = await self.db_manager.get_sessions(active_only=False)
        user_sessions = [s for s in sessions if s.get('added_by_user') == user.id]
        
        if not user_sessions:
            await update.message.reply_text("❌ ليس لديك جلسات. أضف جلسة باستخدام /addsession")
            return
        
        sessions_text = f"📱 **جلساتك ({len(user_sessions)}/{Config.MAX_SESSIONS_PER_USER})**\n\n"
        
        for i, session in enumerate(user_sessions, 1):
            status = "🟢 نشط" if session['is_active'] else "🔴 غير نشط"
            last_used = session['last_used']
            if last_used:
                last_used = datetime.fromisoformat(last_used) if isinstance(last_used, str) else last_used
                last_used_str = last_used.strftime('%Y-%m-%d %H:%M')
            else:
                last_used_str = "لم يستخدم"
            
            sessions_text += f"**{i}. {session['username'] or session['phone_number'] or 'غير معروف'}**\n"
            sessions_text += f"   الحالة: {status}\n"
            sessions_text += f"   آخر استخدام: {last_used_str}\n"
            sessions_text += f"   عدد الاستخدامات: {session['total_uses']}\n"
            sessions_text += f"   الروابط المجمعة: {session['total_links']}\n\n"
        
        await update.message.reply_text(sessions_text, parse_mode="Markdown")
    
    async def links_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /links"""
        links = await self.db_manager.get_links(limit=10)
        
        if not links:
            await update.message.reply_text("❌ لا توجد روابط مجمعة بعد.")
            return
        
        links_text = "🔗 **آخر الروابط المجمعة**\n\n"
        
        for i, link in enumerate(links, 1):
            platform_icons = {
                'telegram': '📢',
                'whatsapp': '📱',
                'discord': '🎮',
                'unknown': '❓'
            }
            icon = platform_icons.get(link['platform'], '🔗')
            
            links_text += f"{icon} **{link['platform'].upper()}**\n"
            links_text += f"   {link['url'][:50]}...\n"
            
            if link['title']:
                links_text += f"   العنوان: {link['title'][:30]}...\n"
            
            if link['members_count']:
                links_text += f"   الأعضاء: {link['members_count']:,}\n"
            
            collected = link['collected_date']
            if collected:
                collected = datetime.fromisoformat(collected) if isinstance(collected, str) else collected
                links_text += f"   التاريخ: {collected.strftime('%Y-%m-%d')}\n"
            
            links_text += "\n"
        
        keyboard = [
            [InlineKeyboardButton("📤 تصدير جميع الروابط", callback_data="export_all")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_links")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(links_text, reply_markup=reply_markup, parse_mode="Markdown")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /export"""
        keyboard = [
            [InlineKeyboardButton("📋 جميع الروابط", callback_data="export_all")],
            [InlineKeyboardButton("📢 تيليجرام فقط", callback_data="export_telegram")],
            [InlineKeyboardButton("📱 واتساب فقط", callback_data="export_whatsapp")],
            [InlineKeyboardButton("🎮 ديسكورد فقط", callback_data="export_discord")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📤 **تصدير الروابط**\n\n"
            "اختر نوع التصدير:",
            reply_markup=reply_markup
        )
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /stats"""
        stats = await self.db_manager.get_stats()
        collection_status = self.collection_manager.get_status()
        
        stats_text = f"""
📈 **إحصائيات النظام**

**📊 الإحصائيات العامة:**
• المستخدمون: {stats['total_users']:,}
• الجلسات النشطة: {stats['active_sessions']:,}
• الروابط المجمعة: {stats['total_links']:,}

**📋 توزيع الروابط:**
"""
        
        for platform, count in stats['links_by_platform'].items():
            platform_name = {
                'telegram': 'تيليجرام',
                'whatsapp': 'واتساب',
                'discord': 'ديسكورد',
                'unknown': 'أخرى'
            }.get(platform, platform)
            
            stats_text += f"• {platform_name}: {count:,}\n"
        
        stats_text += f"\n**🚀 حالة الجمع:**\n"
        stats_text += f"• الحالة: {'🟢 نشط' if collection_status['is_active'] else '🔴 متوقف'}\n"
        if collection_status['is_active']:
            stats_text += f"• الروابط في هذه الدورة: {collection_status['stats']['total_collected']:,}\n"
            stats_text += f"• بدأ في: {collection_status['stats']['start_time'].strftime('%Y-%m-%d %H:%M') if collection_status['stats']['start_time'] else '---'}\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_stats")],
            [InlineKeyboardButton("📊 تفاصيل أكثر", callback_data="detailed_stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(stats_text, reply_markup=reply_markup)
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الاستدعاءات"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user = query.from_user
        
        logger.info(f"استدعاء من {user.id}: {data}")
        
        if data == "start_collect":
            # محاكاة أمر /collect
            await self.collect_command(update, context)
            
        elif data == "stop_collect":
            # محاكاة أمر /stop
            await self.stop_command(update, context)
            
        elif data == "pause_collect":
            # محاكاة أمر /pause
            await self.pause_command(update, context)
            
        elif data == "add_session":
            # محاكاة أمر /addsession
            await self.add_session_command(update, context)
            
        elif data == "show_stats":
            # محاكاة أمر /stats
            await self.stats_command(update, context)
            
        elif data == "show_help":
            # محاكاة أمر /help
            await self.help_command(update, context)
            
        elif data == "collect_status":
            # محاكاة أمر /status
            await self.status_command(update, context)
            
        elif data == "refresh_status":
            # تحديث الحالة
            await self.status_command(update, context)
            
        elif data == "refresh_stats":
            # تحديث الإحصائيات
            await self.stats_command(update, context)
            
        elif data == "refresh_links":
            # تحديث الروابط
            await self.links_command(update, context)
            
        elif data == "export_all":
            # تصدير جميع الروابط
            await self._export_links(query, platform=None)
            
        elif data == "export_telegram":
            # تصدير روابط تيليجرام فقط
            await self._export_links(query, platform='telegram')
            
        elif data == "export_whatsapp":
            # تصدير روابط واتساب فقط
            await self._export_links(query, platform='whatsapp')
            
        elif data == "export_discord":
            # تصدير روابط ديسكورد فقط
            await self._export_links(query, platform='discord')
            
        elif data == "detailed_stats":
            # إحصائيات مفصلة
            await self._show_detailed_stats(query)
    
    async def _export_links(self, query, platform: str = None):
        """تصدير الروابط"""
        await query.message.edit_text("⏳ جاري تجهيز الملف...")
        
        try:
            # الحصول على الروابط
            all_links = []
            offset = 0
            limit = 1000
            
            while True:
                links = await self.db_manager.get_links(platform=platform, limit=limit, offset=offset)
                if not links:
                    break
                
                all_links.extend([link['url'] for link in links])
                offset += limit
                
                if len(all_links) >= Config.MAX_EXPORT_LINKS:
                    break
            
            if not all_links:
                await query.message.edit_text("❌ لا توجد روابط للتصدير.")
                return
            
            # إنشاء ملف نصي
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            platform_suffix = f"_{platform}" if platform else ""
            filename = f"links_export{platform_suffix}_{timestamp}.txt"
            filepath = os.path.join("exports", filename)
            
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(all_links))
            
            # إرسال الملف
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📤 تم تصدير {len(all_links):,} رابط"
                )
            
            # حذف الملف المحلي
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في التصدير: {e}")
            await query.message.edit_text(f"❌ خطأ في التصدير: {str(e)[:100]}")
    
    async def _show_detailed_stats(self, query):
        """عرض إحصائيات مفصلة"""
        stats = await self.db_manager.get_stats()
        
        detailed_text = f"""
📊 **إحصائيات مفصلة**

**إحصائيات الروابط:**
• الإجمالي: {stats['total_links']:,}
"""
        
        for platform, count in stats['links_by_platform'].items():
            percentage = (count / stats['total_links'] * 100) if stats['total_links'] > 0 else 0
            detailed_text += f"• {platform}: {count:,} ({percentage:.1f}%)\n"
        
        # إحصائيات الجمع
        collection_stats = self.collection_manager.get_status()['stats']
        detailed_text += f"""
**إحصائيات الجمع الحالي:**
• الروابط المجمعة: {collection_stats['total_collected']:,}
• الأخطاء: {collection_stats['errors']:,}
"""
        
        if collection_stats['start_time']:
            duration = datetime.now() - collection_stats['start_time']
            hours, remainder = divmod(duration.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            detailed_text += f"• المدة: {int(hours)}س {int(minutes)}د {int(seconds)}ث\n"
        
        await query.message.edit_text(detailed_text)
    
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الرسائل النصية"""
        user = update.effective_user
        text = update.message.text.strip()
        
        # التحقق من حالة المستخدم
        if user.id in self.user_states:
            state = self.user_states[user.id]['state']
            
            if state == 'awaiting_session':
                # معالجة كود الجلسة
                await self._handle_session_input(update, text, user.id)
                return
        
        # إذا لم تكن في حالة خاصة، عرض رسالة افتراضية
        await update.message.reply_text(
            "📝 أرسلت رسالة نصية.\n\n"
            "استخدم الأوامر للتحكم بالبوت:\n"
            "/start - للبداية\n"
            "/help - للمساعدة\n"
            "/collect - لبدء الجمع"
        )
    
    async def _handle_session_input(self, update: Update, session_string: str, user_id: int):
        """معالجة إدخال كود الجلسة"""
        # التحقق من الطول
        if len(session_string) < 50:
            await update.message.reply_text("❌ كود الجلسة قصير جداً. يرجى إرسال كود صحيح.")
            return
        
        await update.message.reply_text("⏳ جاري التحقق من الجلسة...")
        
        # التحقق من صحة الجلسة
        is_valid, result = await SessionManager.validate_session(session_string)
        
        if not is_valid:
            await update.message.reply_text(f"❌ جلسة غير صالحة: {result.get('error', 'خطأ غير معروف')}")
            del self.user_states[user_id]
            return
        
        # إضافة الجلسة
        user_info = result
        session_id = await self.db_manager.add_session(
            session_string,
            user_id,
            user_info.get('phone', ''),
            user_info.get('username', '')
        )
        
        # تحديث حالة المستخدم
        del self.user_states[user_id]
        
        # إرسال تأكيد
        success_text = f"""
✅ **تمت إضافة الجلسة بنجاح!**

**معلومات الجلسة:**
• المعرف: {session_id}
• المستخدم: {user_info.get('first_name', '')} {user_info.get('last_name', '')}
• اليوزر: @{user_info.get('username', 'غير معروف')}
• الهاتف: {user_info.get('phone', 'غير معروف')}

يمكنك الآن بدء الجمع باستخدام /collect
"""
        
        keyboard = [
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("📱 عرض الجلسات", callback_data="show_sessions")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(success_text, reply_markup=reply_markup, parse_mode="Markdown")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الأخطاء"""
        error = context.error
        
        if isinstance(error, Conflict):
            logger.error("⚠️ Conflict: البوت يعمل بالفعل في مكان آخر")
            return
        
        logger.error(f"❌ خطأ في البوت: {error}", exc_info=True)
        
        try:
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ حدث خطأ غير متوقع. جاري إصلاحه تلقائياً..."
                )
        except:
            pass
    
    async def run(self):
        """تشغيل البوت"""
        await self.initialize()
        
        try:
            # بدء استقبال التحديثات
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            logger.info("🤖 البوت يعمل بنجاح!")
            
            # الحفاظ على البوت نشطاً
            await asyncio.Event().wait()
            
        except Exception as e:
            logger.error(f"❌ خطأ في تشغيل البوت: {e}", exc_info=True)
            raise
        
        finally:
            # التنظيف
            await self.shutdown()
    
    async def shutdown(self):
        """إيقاف البوت"""
        logger.info("🧹 جاري إيقاف البوت...")
        
        try:
            # إيقاف الجمع
            await self.collection_manager.stop_collection()
            
            # إيقاف البوت
            if self.application:
                await self.application.stop()
            
            # إغلاق قاعدة البيانات
            if self.db_manager:
                await self.db_manager.close()
            
            logger.info("✅ تم إيقاف البوت بنجاح")
            
        except Exception as e:
            logger.error(f"❌ خطأ في الإيقاف: {e}")

# ======================
# 🔧 Main Function - الوظيفة الرئيسية
# ======================

async def main():
    """الوظيفة الرئيسية"""
    logger.info("🚀 بدء تشغيل بوت جمع الروابط...")
    
    # التحقق من المتغيرات البيئية
    required_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH']
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        logger.error(f"❌ متغيرات بيئية مفقودة: {missing}")
        print(f"يرجى تعيين المتغيرات البيئية التالية:")
        for var in missing:
            print(f"export {var}=قيمتك_هنا")
        sys.exit(1)
    
    # إنشاء المجلدات اللازمة
    os.makedirs("exports", exist_ok=True)
    os.makedirs("backups", exist_ok=True)
    
    # إنشاء وإدارة البوت
    bot = TelegramBot()
    
    try:
        await bot.run()
        
    except KeyboardInterrupt:
        logger.info("👋 توقف البوت بواسطة المستخدم")
        
    except Exception as e:
        logger.error(f"❌ خطأ قاتل: {e}", exc_info=True)
        
    finally:
        # التأكد من إيقاف البوت بشكل صحيح
        await bot.shutdown()

# ======================
# 🔧 Entry Point - نقطة الدخول
# ======================

if __name__ == "__main__":
    # معالجة إشارات الإيقاف
    def signal_handler(signum, frame):
        logger.info(f"📶 إشارة {signum} - جاري الإغلاق...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # تشغيل البوت
    asyncio.run(main())
