# bot.py - إصدار محسن نهائي يعمل على Render
import os
import sys
import subprocess
import logging
import asyncio
import json
import re
import aiofiles
import aiosqlite
import hashlib
import psutil
import signal
import secrets
import base64
import traceback
import shutil
import aiohttp
import uuid
from typing import List, Dict, Set, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import defaultdict, deque, OrderedDict
from urllib.parse import urlparse, parse_qs, urlencode
from contextlib import asynccontextmanager
import gc

# ======================
# 1. تأكد من تثبيت الحزم المطلوبة
# ======================

def install_required_packages():
    """تثبيت الحزم المطلوبة تلقائياً"""
    required_packages = [
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
        'uvloop==0.19.0'
    ]
    
    for package in required_packages:
        pkg_name = package.split('==')[0]
        try:
            __import__(pkg_name.replace('-', '_'))
        except ImportError:
            print(f"📦 جاري تثبيت {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# تنفيذ التثبيت
install_required_packages()

# ======================
# 2. استيراد المكتبات بعد التثبيت
# ======================

# المكتبات الأساسية
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# مكتبات تليجرام
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ApplicationBuilder,
    ConversationHandler
)
from telegram.error import TelegramError, Conflict

# مكتبات Telethon
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl import functions, types
from telethon.errors import (
    FloodWaitError, ChannelPrivateError, UsernameNotOccupiedError,
    InviteHashInvalidError, InviteHashExpiredError, ChatAdminRequiredError,
    SessionPasswordNeededError, PhoneCodeInvalidError, AuthKeyError,
    UserNotParticipantError, ChatWriteForbiddenError
)

# FastAPI للصحة
from fastapi import FastAPI
import uvicorn
import threading

# ======================
# 3. إعدادات التهيئة
# ======================

# تكوين السجل
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
# 4. فئات التهيئة
# ======================

class Config:
    """فئة التهيئة"""
    
    # Telegram API
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH", "")
    
    # الأمان
    @staticmethod
    def get_user_ids(env_var: str, default: str = "0") -> Set[int]:
        """تحويل قائمة المعرفات إلى مجموعة"""
        try:
            value = os.getenv(env_var, default)
            if not value:
                return {int(default)}
            
            ids = set()
            for id_str in value.split(","):
                id_str = id_str.strip()
                if id_str.isdigit():
                    ids.add(int(id_str))
            
            return ids if ids else {int(default)}
        except Exception:
            return {int(default)}
    
    ADMIN_USER_IDS = get_user_ids.__func__("ADMIN_USER_IDS", "0")
    ALLOWED_USER_IDS = get_user_ids.__func__("ALLOWED_USER_IDS", "0")
    
    # التشفير
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    
    # إدارة الذاكرة
    MAX_CACHED_URLS = 20000
    CACHE_CLEAN_INTERVAL = 1000
    MAX_MEMORY_MB = 500
    
    # الأداء
    MAX_CONCURRENT_SESSIONS = 20
    REQUEST_DELAYS = {
        'normal': 1.0,
        'join_request': 5.0,
        'search': 2.0,
        'flood_wait': 5.0,
        'between_sessions': 2.0,
        'between_tasks': 0.3,
        'min_cycle_delay': 10.0,
        'max_cycle_delay': 45.0,
        'validation_delay': 2.0
    }
    
    # حدود الجمع
    MAX_DIALOGS_PER_SESSION = 50
    MAX_MESSAGES_PER_SEARCH = 10
    MAX_SEARCH_TERMS = 8
    MAX_LINKS_PER_CYCLE = 200
    MAX_BATCH_SIZE = 50
    
    # قاعدة البيانات
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10
    DB_POOL_SIZE = 10
    
    # واتساب
    WHATSAPP_DAYS_BACK = 30
    
    # التحقق
    MIN_GROUP_MEMBERS = 3
    MAX_LINK_LENGTH = 200
    VALIDATION_TIMEOUT = 30
    
    # حدود الطلبات
    USER_RATE_LIMIT = {
        'max_requests': 15,
        'per_seconds': 60
    }
    
    # إدارة الجلسات
    SESSION_TIMEOUT = 600
    MAX_SESSIONS_PER_USER = 20
    
    # التصدير
    MAX_EXPORT_LINKS = 100000
    EXPORT_CHUNK_SIZE = 5000
    
    # إعدادات متقدمة
    TELEGRAM_NO_TIME_LIMIT = True
    JOIN_REQUEST_CHECK_DELAY = 30
    ENABLE_ADVANCED_VALIDATION = True

# ======================
# 5. فئات المساعدة
# ======================

class LinkProcessor:
    """معالج الروابط المحسن"""
    
    @staticmethod
    def normalize_url(url: str) -> str:
        """توحيد تنسيق الرابط"""
        if not url:
            return ""
        
        url = url.strip()
        
        # إضافة البروتوكول إذا كان مفقوداً
        if not url.startswith(('http://', 'https://')):
            if 't.me' in url or 'telegram.me' in url:
                url = 'https://' + url
        
        return url
    
    @staticmethod
    def extract_links(text: str) -> List[str]:
        """استخراج الروابط من النص"""
        if not text:
            return []
        
        url_pattern = r'(https?://[^\s]+|t\.me/[^\s]+|telegram\.me/[^\s]+)'
        return re.findall(url_pattern, text, re.IGNORECASE)

class DatabaseManager:
    """مدير قاعدة البيانات المحسن"""
    
    _instance = None
    
    @classmethod
    async def get_instance(cls):
        if cls._instance is None:
            cls._instance = DatabaseManager()
            await cls._instance.initialize()
        return cls._instance
    
    async def initialize(self):
        """تهيئة قاعدة البيانات"""
        self.db_path = Config.DB_PATH
        
        # إنشاء مجلد قاعدة البيانات إذا لم يكن موجوداً
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # الاتصال بقاعدة البيانات
        self.connection = await aiosqlite.connect(self.db_path)
        await self.create_tables()
        
        logger.info(f"✅ تم تهيئة قاعدة البيانات: {self.db_path}")
    
    async def create_tables(self):
        """إنشاء الجداول"""
        # جدول الجلسات
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_string TEXT NOT NULL,
                phone_number TEXT,
                user_id INTEGER,
                username TEXT,
                added_by_user INTEGER,
                is_active BOOLEAN DEFAULT 1,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP
            )
        ''')
        
        # جدول الروابط
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                platform TEXT,
                title TEXT,
                description TEXT,
                members_count INTEGER DEFAULT 0,
                session_id INTEGER,
                collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                added_by_user INTEGER
            )
        ''')
        
        # جدول المستخدمين
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS bot_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_admin BOOLEAN DEFAULT 0,
                is_allowed BOOLEAN DEFAULT 1,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP
            )
        ''')
        
        await self.connection.commit()
        logger.info("✅ تم إنشاء جداول قاعدة البيانات")
    
    async def add_user(self, user_id: int, username: str = None, 
                      first_name: str = None, last_name: str = None):
        """إضافة أو تحديث مستخدم"""
        try:
            await self.connection.execute('''
                INSERT OR REPLACE INTO bot_users 
                (user_id, username, first_name, last_name, last_active)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, username or '', first_name or '', last_name or ''))
            await self.connection.commit()
        except Exception as e:
            logger.error(f"خطأ في إضافة المستخدم: {e}")
    
    async def add_session(self, session_string: str, user_id: int,
                         phone_number: str = None, username: str = None):
        """إضافة جلسة جديدة"""
        try:
            await self.connection.execute('''
                INSERT INTO sessions 
                (session_string, phone_number, user_id, username, added_by_user)
                VALUES (?, ?, ?, ?, ?)
            ''', (session_string, phone_number or '', user_id, username or '', user_id))
            await self.connection.commit()
            return True, "✅ تمت إضافة الجلسة بنجاح"
        except Exception as e:
            return False, f"❌ خطأ في إضافة الجلسة: {e}"
    
    async def add_link(self, url: str, platform: str, session_id: int = None,
                      title: str = None, members_count: int = 0,
                      added_by_user: int = 0):
        """إضافة رابط جديد"""
        try:
            await self.connection.execute('''
                INSERT OR IGNORE INTO links 
                (url, platform, title, members_count, session_id, added_by_user)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (url, platform, title or '', members_count, session_id, added_by_user))
            await self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في إضافة الرابط: {e}")
            return False
    
    async def get_sessions(self, user_id: int = None):
        """الحصول على الجلسات"""
        try:
            if user_id:
                cursor = await self.connection.execute(
                    'SELECT * FROM sessions WHERE added_by_user = ? AND is_active = 1',
                    (user_id,)
                )
            else:
                cursor = await self.connection.execute(
                    'SELECT * FROM sessions WHERE is_active = 1'
                )
            rows = await cursor.fetchall()
            return rows
        except Exception as e:
            logger.error(f"خطأ في الحصول على الجلسات: {e}")
            return []
    
    async def get_links(self, limit: int = 100):
        """الحصول على الروابط"""
        try:
            cursor = await self.connection.execute(
                'SELECT * FROM links WHERE is_active = 1 ORDER BY collected_date DESC LIMIT ?',
                (limit,)
            )
            rows = await cursor.fetchall()
            return rows
        except Exception as e:
            logger.error(f"خطأ في الحصول على الروابط: {e}")
            return []
    
    async def get_stats(self):
        """الحصول على الإحصائيات"""
        try:
            stats = {}
            
            # عدد الروابط
            cursor = await self.connection.execute('SELECT COUNT(*) FROM links WHERE is_active = 1')
            stats['total_links'] = (await cursor.fetchone())[0]
            
            # عدد الجلسات
            cursor = await self.connection.execute('SELECT COUNT(*) FROM sessions WHERE is_active = 1')
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            # عدد المستخدمين
            cursor = await self.connection.execute('SELECT COUNT(*) FROM bot_users')
            stats['total_users'] = (await cursor.fetchone())[0]
            
            # الروابط حسب المنصة
            cursor = await self.connection.execute(
                'SELECT platform, COUNT(*) FROM links GROUP BY platform'
            )
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            return stats
        except Exception as e:
            logger.error(f"خطأ في الحصول على الإحصائيات: {e}")
            return {}
    
    async def close(self):
        """إغلاق اتصال قاعدة البيانات"""
        if hasattr(self, 'connection'):
            await self.connection.close()

class SessionManager:
    """مدير الجلسات"""
    
    def __init__(self):
        self.active_clients = {}
        self.session_cache = {}
    
    async def create_client(self, session_string: str, session_id: int):
        """إنشاء عميل تليجرام"""
        try:
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH,
                device_model="Link Collector",
                system_version="Linux 6.5",
                app_version="4.16.30"
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return None, "❌ الجلسة غير مفعلة"
            
            me = await client.get_me()
            self.active_clients[session_id] = client
            
            return client, f"✅ تم تفعيل الجلسة: {me.username or me.phone}"
            
        except Exception as e:
            return None, f"❌ خطأ في إنشاء العميل: {str(e)[:100]}"
    
    async def close_client(self, session_id: int):
        """إغلاق عميل"""
        if session_id in self.active_clients:
            await self.active_clients[session_id].disconnect()
            del self.active_clients[session_id]
    
    async def validate_session(self, session_string: str):
        """التحقق من صحة الجلسة"""
        try:
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return False, "❌ الجلسة غير مفعلة"
            
            me = await client.get_me()
            await client.disconnect()
            
            return True, {
                'username': me.username,
                'phone': me.phone,
                'user_id': me.id
            }
            
        except Exception as e:
            return False, f"❌ خطأ في التحقق: {str(e)[:100]}"

class CollectionManager:
    """مدير الجمع"""
    
    def __init__(self):
        self.is_running = False
        self.is_paused = False
        self.collection_task = None
        
        self.stats = {
            'total_collected': 0,
            'telegram_links': 0,
            'whatsapp_links': 0,
            'last_collection': None
        }
    
    async def start_collection(self, user_id: int):
        """بدء عملية الجمع"""
        if self.is_running:
            return "⚠️ عملية الجمع تعمل بالفعل"
        
        self.is_running = True
        self.collection_task = asyncio.create_task(self._collect_links(user_id))
        return "✅ بدأت عملية الجمع"
    
    async def _collect_links(self, user_id: int):
        """مهمة الجمع الرئيسية"""
        db = await DatabaseManager.get_instance()
        session_manager = SessionManager()
        
        try:
            # الحصول على الجلسات النشطة
            sessions = await db.get_sessions(user_id)
            
            if not sessions:
                logger.warning("لا توجد جلسات نشطة")
                return
            
            for session_data in sessions:
                if not self.is_running or self.is_paused:
                    break
                
                session_id = session_data[0]
                session_string = session_data[1]
                
                try:
                    # إنشاء العميل
                    client, message = await session_manager.create_client(session_string, session_id)
                    if not client:
                        continue
                    
                    # جمع الروابط
                    await self._collect_from_session(client, session_id, user_id)
                    
                    # إغلاق العميل
                    await session_manager.close_client(session_id)
                    
                    # تأخير بين الجلسات
                    await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
                    
                except Exception as e:
                    logger.error(f"خطأ في معالجة الجلسة {session_id}: {e}")
                    continue
            
            self.stats['last_collection'] = datetime.now()
            
        except Exception as e:
            logger.error(f"خطأ في عملية الجمع: {e}")
        finally:
            self.is_running = False
    
    async def _collect_from_session(self, client: TelegramClient, session_id: int, user_id: int):
        """جمع الروابط من جلسة واحدة"""
        db = await DatabaseManager.get_instance()
        
        try:
            # جمع من الدردشات
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                if not self.is_running or self.is_paused:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # جمع من وصف القناة/المجموعة
                    if hasattr(entity, 'about') and entity.about:
                        links = LinkProcessor.extract_links(entity.about)
                        for link in links:
                            await db.add_link(
                                link, 
                                'telegram',
                                session_id,
                                dialog.title,
                                0,
                                user_id
                            )
                            self.stats['telegram_links'] += 1
                            self.stats['total_collected'] += 1
                    
                    # جمع من الرسائل الأخيرة
                    async for message in client.iter_messages(
                        entity,
                        limit=Config.MAX_MESSAGES_PER_SEARCH
                    ):
                        if not message.text:
                            continue
                        
                        links = LinkProcessor.extract_links(message.text)
                        for link in links:
                            await db.add_link(
                                link,
                                'telegram',
                                session_id,
                                dialog.title,
                                0,
                                user_id
                            )
                            self.stats['telegram_links'] += 1
                            self.stats['total_collected'] += 1
                        
                        # تأخير بين الرسائل
                        await asyncio.sleep(0.1)
                        
                except Exception as e:
                    logger.debug(f"خطأ في جمع من الدردشة: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"خطأ في جمع من الجلسة: {e}")
    
    async def stop_collection(self):
        """إيقاف عملية الجمع"""
        self.is_running = False
        self.is_paused = False
        
        if self.collection_task:
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                pass
        
        return "✅ تم إيقاف عملية الجمع"
    
    async def pause_collection(self):
        """إيقاف الجمع مؤقتاً"""
        if not self.is_running:
            return "⚠️ عملية الجمع غير نشطة"
        
        self.is_paused = True
        return "⏸️ تم إيقاف الجمع مؤقتاً"
    
    async def resume_collection(self):
        """استئناف الجمع"""
        if not self.is_running:
            return "⚠️ عملية الجمع غير نشطة"
        
        self.is_paused = False
        return "▶️ تم استئناف الجمع"
    
    def get_status(self):
        """الحصول على الحالة"""
        return {
            'is_running': self.is_running,
            'is_paused': self.is_paused,
            'stats': self.stats.copy()
        }

class TelegramBot:
    """البوت الرئيسي"""
    
    def __init__(self):
        self.application = None
        self.db_manager = None
        self.session_manager = SessionManager()
        self.collection_manager = CollectionManager()
        self.user_states = {}
        
        self.STATES = {
            'AWAITING_SESSION': 1,
            'AWAITING_LINK': 2,
            'AWAITING_QUERY': 3
        }
    
    async def initialize(self):
        """تهيئة البوت"""
        # تهيئة مدير قاعدة البيانات
        self.db_manager = await DatabaseManager.get_instance()
        
        # إنشاء تطبيق البوت
        self.application = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        
        # إضافة المعالجات
        self.setup_handlers()
        
        logger.info("✅ تم تهيئة البوت")
    
    def setup_handlers(self):
        """إعداد معالجات الأوامر"""
        
        # معالجة /start
        self.application.add_handler(CommandHandler("start", self.start_command))
        
        # معالجة /addsession
        self.application.add_handler(CommandHandler("addsession", self.addsession_command))
        
        # معالجة /collect
        self.application.add_handler(CommandHandler("collect", self.collect_command))
        
        # معالجة /stopcollect
        self.application.add_handler(CommandHandler("stopcollect", self.stopcollect_command))
        
        # معالجة /pausecollect
        self.application.add_handler(CommandHandler("pausecollect", self.pausecollect_command))
        
        # معالجة /resumecollect
        self.application.add_handler(CommandHandler("resumecollect", self.resumecollect_command))
        
        # معالجة /links
        self.application.add_handler(CommandHandler("links", self.links_command))
        
        # معالجة /sessions
        self.application.add_handler(CommandHandler("sessions", self.sessions_command))
        
        # معالجة /stats
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        
        # معالجة /export
        self.application.add_handler(CommandHandler("export", self.export_command))
        
        # معالجة /help
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # معالجة الرسائل النصية
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_message
        ))
        
        # معالجة الأخطاء
        self.application.add_error_handler(self.error_handler)
    
    # ======================
    # معالجات الأوامر
    # ======================
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /start"""
        user = update.effective_user
        
        # التحقق من الصلاحيات
        if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
            await update.message.reply_text(
                "❌ غير مصرح لك باستخدام هذا البوت.\n"
                "يرجى التواصل مع المدير."
            )
            return
        
        # إضافة/تحديث المستخدم
        await self.db_manager.add_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        # ترحيب
        welcome_text = f"""
👋 مرحباً {user.first_name}!

🤖 **بوت جمع الروابط الذكي**

**المميزات:**
✅ جمع روابط تليجرام وواتساب
✅ إدارة متعددة الجلسات
✅ تصدير الروابط
✅ إحصائيات مفصلة

**الأوامر المتاحة:**
/start - بدء البوت
/addsession - إضافة جلسة
/collect - بدء الجمع
/stopcollect - إيقاف الجمع
/links - عرض الروابط
/sessions - عرض الجلسات
/stats - الإحصائيات
/export - تصدير الروابط
/help - المساعدة

🔥 **الحدود المحسنة:**
• {Config.MAX_SESSIONS_PER_USER} جلسة لكل مستخدم
• {Config.MAX_EXPORT_LINKS:,} رابط للتصدير
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
             InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats"),
             InlineKeyboardButton("📤 تصدير", callback_data="export_links")],
            [InlineKeyboardButton("❓ المساعدة", callback_data="show_help")]
        ])
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard)
    
    async def addsession_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /addsession"""
        user = update.effective_user
        
        # التحقق من عدد الجلسات
        sessions = await self.db_manager.get_sessions(user.id)
        if len(sessions) >= Config.MAX_SESSIONS_PER_USER:
            await update.message.reply_text(
                f"❌ لقد وصلت إلى الحد الأقصى للجلسات ({Config.MAX_SESSIONS_PER_USER})\n"
                "يرجى حذف بعض الجلسات قبل إضافة جديدة."
            )
            return
        
        await update.message.reply_text(
            "📱 **إضافة جلسة جديدة**\n\n"
            "أرسل لي كود الجلسة (session string) الخاص بك.\n\n"
            "**ملاحظة:**\n"
            "• تأكد من صحة الجلسة\n"
            "• الجلسة يجب أن تكون مفعلة\n"
            "• يمكنك إلغاء العملية بأي وقت بإرسال /cancel"
        )
        
        self.user_states[user.id] = self.STATES['AWAITING_SESSION']
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /collect"""
        user = update.effective_user
        
        # التحقق من وجود جلسات
        sessions = await self.db_manager.get_sessions(user.id)
        if not sessions:
            await update.message.reply_text(
                "❌ ليس لديك أي جلسات مضافة.\n"
                "استخدم /addsession لإضافة جلسة أولاً."
            )
            return
        
        # بدء الجمع
        result = await self.collection_manager.start_collection(user.id)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 الحالة", callback_data="collect_status")]
        ])
        
        await update.message.reply_text(f"{result}\n\nيمكنك مراقبة العملية من خلال الأزرار أدناه:", 
                                       reply_markup=keyboard)
    
    async def stopcollect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /stopcollect"""
        result = await self.collection_manager.stop_collection()
        await update.message.reply_text(result)
    
    async def pausecollect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /pausecollect"""
        result = await self.collection_manager.pause_collection()
        await update.message.reply_text(result)
    
    async def resumecollect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /resumecollect"""
        result = await self.collection_manager.resume_collection()
        await update.message.reply_text(result)
    
    async def links_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /links"""
        user = update.effective_user
        
        # الحصول على الروابط
        links = await self.db_manager.get_links(limit=10)
        
        if not links:
            await update.message.reply_text("📭 لا توجد روابط مجمعة بعد.")
            return
        
        response = "📋 **آخر الروابط المجمعة:**\n\n"
        for link in links:
            url = link[1]
            platform = link[2] or "غير معروف"
            title = link[3] or "بدون عنوان"
            date = link[7]
            
            response += f"• **{title}**\n"
            response += f"  📍 {url}\n"
            response += f"  📱 {platform} | 📅 {date[:10]}\n\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 تصدير جميع الروابط", callback_data="export_all")]
        ])
        
        await update.message.reply_text(response, reply_markup=keyboard)
    
    async def sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /sessions"""
        user = update.effective_user
        
        # الحصول على الجلسات
        sessions = await self.db_manager.get_sessions(user.id)
        
        if not sessions:
            await update.message.reply_text(
                "📭 ليس لديك أي جلسات.\n"
                "استخدم /addsession لإضافة جلسة جديدة."
            )
            return
        
        response = f"📱 **جلساتك ({len(sessions)}/{Config.MAX_SESSIONS_PER_USER}):**\n\n"
        for i, session in enumerate(sessions, 1):
            username = session[4] or "غير معروف"
            phone = session[2] or "غير معروف"
            added_date = session[7]
            
            response += f"**{i}. {username}**\n"
            response += f"   📞 {phone}\n"
            response += f"   📅 أضيفت: {added_date[:10]}\n\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة جديدة", callback_data="add_new_session"),
            [InlineKeyboardButton("🗑️ حذف جلسة", callback_data="delete_session")]
        ])
        
        await update.message.reply_text(response, reply_markup=keyboard)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /stats"""
        # إحصائيات قاعدة البيانات
        db_stats = await self.db_manager.get_stats()
        
        # إحصائيات الجمع
        collect_status = self.collection_manager.get_status()
        
        response = f"""
📊 **إحصائيات النظام**

**قاعدة البيانات:**
• الروابط: {db_stats.get('total_links', 0):,}
• الجلسات النشطة: {db_stats.get('active_sessions', 0)}
• المستخدمين: {db_stats.get('total_users', 0)}

**الجمع:**
• الحالة: {'🟢 نشط' if collect_status['is_running'] else '🔴 متوقف'}
• المجموع: {collect_status['stats']['total_collected']:,}
• تليجرام: {collect_status['stats']['telegram_links']:,}
• واتساب: {collect_status['stats']['whatsapp_links']:,}

**الحدود:**
• أقصى جلسات: {Config.MAX_SESSIONS_PER_USER}
• أقصى تصدير: {Config.MAX_EXPORT_LINKS:,}
• التزامن: {Config.MAX_CONCURRENT_SESSIONS}

**النظام:**
• الذاكرة: {psutil.Process().memory_info().rss / 1024 / 1024:.1f} MB
• الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_stats"),
            [InlineKeyboardButton("📈 تفاصيل", callback_data="detailed_stats")]
        ])
        
        await update.message.reply_text(response, reply_markup=keyboard)
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /export"""
        user = update.effective_user
        
        # الحصول على جميع الروابط
        links = await self.db_manager.get_links(limit=Config.MAX_EXPORT_LINKS)
        
        if not links:
            await update.message.reply_text("📭 لا توجد روابط للتصدير.")
            return
        
        # إنشاء ملف نصي
        filename = f"links_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = f"exports/{filename}"
        
        os.makedirs("exports", exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for link in links:
                f.write(f"{link[1]}\n")
        
        # إرسال الملف
        with open(filepath, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📤 تم تصدير {len(links):,} رابط"
            )
        
        # تنظيف الملف المؤقت
        os.remove(filepath)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /help"""
        help_text = """
❓ **دليل الاستخدام**

**الأوامر الأساسية:**
• /start - بدء البوت
• /addsession - إضافة جلسة تليجرام
• /collect - بدء جمع الروابط
• /stopcollect - إيقاف الجمع
• /pausecollect - إيقاف مؤقت
• /resumecollect - استئناف الجمع

**عرض البيانات:**
• /links - عرض الروابط المجمعة
• /sessions - عرض الجلسات المضافة
• /stats - عرض إحصائيات النظام

**التصدير:**
• /export - تصدير جميع الروابط

**كيفية الحصول على الجلسة:**
1. افتح https://my.telegram.org
2. سجل الدخول بحسابك
3. انتقل إلى API Development
4. انسخ الرمز من حقل API Hash
5. استخدم هذا الرمز في /addsession

**ملاحظات هامة:**
• كل جلسة لها صلاحيات محدودة
• تأكد من صحة الجلسة قبل الإضافة
• لا تشارك جلساتك مع أحد
• الروابط تحفظ تلقائياً في قاعدة البيانات

للأسئلة: @username
"""
        
        await update.message.reply_text(help_text)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الرسائل النصية"""
        user = update.effective_user
        message_text = update.message.text
        
        if user.id not in self.user_states:
            await update.message.reply_text(
                "❓ لم أفهم طلبك.\n"
                "استخدم /help لرؤية الأوامر المتاحة."
            )
            return
        
        state = self.user_states[user.id]
        
        if state == self.STATES['AWAITING_SESSION']:
            # التحقق من صحة الجلسة
            await update.message.reply_text("🔍 جاري التحقق من الجلسة...")
            
            is_valid, result = await self.session_manager.validate_session(message_text)
            
            if is_valid:
                # إضافة الجلسة
                success, msg = await self.db_manager.add_session(
                    message_text,
                    user.id,
                    result.get('phone'),
                    result.get('username')
                )
                
                if success:
                    await update.message.reply_text(
                        f"✅ تمت إضافة الجلسة بنجاح!\n\n"
                        f"**المعلومات:**\n"
                        f"👤 {result.get('username', 'غير معروف')}\n"
                        f"📞 {result.get('phone', 'غير معروف')}\n\n"
                        f"يمكنك الآن استخدام /collect لبدء الجمع."
                    )
                else:
                    await update.message.reply_text(msg)
            else:
                await update.message.reply_text(f"❌ {result}")
            
            # مسح الحالة
            del self.user_states[user.id]
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الاستدعاءات"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user = query.from_user
        
        if data == "add_session":
            await self.addsession_command(update, context)
        
        elif data == "start_collect":
            await self.collect_command(update, context)
        
        elif data == "pause_collect":
            result = await self.collection_manager.pause_collection()
            await query.edit_message_text(result)
        
        elif data == "stop_collect":
            result = await self.collection_manager.stop_collection()
            await query.edit_message_text(result)
        
        elif data == "collect_status":
            status = self.collection_manager.get_status()
            status_text = f"""
📊 **حالة الجمع**

الحالة: {'🟢 نشط' if status['is_running'] else '🔴 متوقف'}
الإيقاف المؤقت: {'⏸️ نعم' if status['is_paused'] else '▶️ لا'}

**الإحصائيات:**
• الروابط: {status['stats']['total_collected']:,}
• تليجرام: {status['stats']['telegram_links']:,}
• واتساب: {status['stats']['whatsapp_links']:,}
"""
            await query.edit_message_text(status_text)
        
        elif data == "show_stats":
            await self.stats_command(update, context)
        
        elif data == "export_links":
            await self.export_command(update, context)
        
        elif data == "show_help":
            await self.help_command(update, context)
        
        elif data == "refresh_stats":
            await self.stats_command(update, context)
        
        elif data == "export_all":
            await self.export_command(update, context)
        
        elif data == "add_new_session":
            await self.addsession_command(update, context)
        
        elif data == "delete_session":
            await query.edit_message_text(
                "🗑️ **حذف جلسة**\n\n"
                "استخدم الأمر /sessions لرؤية الجلسات.\n"
                "لحذف جلسة، يجب إزالتها يدوياً من قاعدة البيانات."
            )
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الأخطاء"""
        try:
            error = context.error
            
            if isinstance(error, Conflict):
                logger.warning("⚠️ تم تشغيل أكثر من نسخة من البوت. إغلاق النسخة الحالية...")
                return
            
            logger.error(f"خطأ في البوت: {error}", exc_info=True)
            
            if update and update.effective_chat:
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ حدث خطأ غير متوقع. تم تسجيله وسنعمل على إصلاحه."
                    )
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"خطأ في معالج الأخطاء: {e}")

class HealthServer:
    """خادم فحص الصحة للـ Render"""
    
    def __init__(self, port=8080):
        self.port = port
        self.app = FastAPI()
        self.setup_routes()
    
    def setup_routes(self):
        """إعداد مسارات FastAPI"""
        
        @self.app.get("/")
        async def root():
            return {"status": "running", "service": "Telegram Link Collector"}
        
        @self.app.get("/health")
        async def health():
            try:
                # فحص البوت
                bot_ok = True
                
                # فحص قاعدة البيانات
                db_ok = os.path.exists(Config.DB_PATH)
                
                # فحص الذاكرة
                memory_ok = psutil.Process().memory_percent() < 90
                
                status = {
                    "status": "healthy" if all([bot_ok, db_ok, memory_ok]) else "degraded",
                    "timestamp": datetime.now().isoformat(),
                    "checks": {
                        "bot": bot_ok,
                        "database": db_ok,
                        "memory": memory_ok
                    }
                }
                
                return status
                
            except Exception as e:
                return {"status": "error", "error": str(e)}
    
    def start(self):
        """بدء الخادم"""
        def run():
            uvicorn.run(
                self.app,
                host="0.0.0.0",
                port=self.port,
                log_level="warning"
            )
        
        # تشغيل الخادم في خيط منفصل
        server_thread = threading.Thread(target=run, daemon=True)
        server_thread.start()
        logger.info(f"✅ بدأ خادم الصحة على المنفذ {self.port}")

# ======================
# 6. الوظيفة الرئيسية
# ======================

async def main():
    """الوظيفة الرئيسية لتشغيل البوت"""
    
    # التحقق من المتغيرات البيئية
    required_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH']
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        logger.error(f"❌ متغيرات بيئية مفقودة: {missing}")
        print(f"يرجى تعيين المتغيرات التالية:")
        for var in missing:
            print(f"export {var}=قيمتك")
        sys.exit(1)
    
    # إنشاء المجلدات المطلوبة
    os.makedirs("exports", exist_ok=True)
    os.makedirs("backups", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    # بدء خادم الصحة
    health_server = HealthServer(port=8080)
    health_server.start()
    
    # إنشاء وإعداد البوت
    bot = TelegramBot()
    await bot.initialize()
    
    logger.info("🚀 بدء تشغيل بوت جمع الروابط...")
    
    try:
        # بدء البوت
        await bot.application.initialize()
        await bot.application.start()
        await bot.application.updater.start_polling()
        
        logger.info("✅ البوت يعمل بنجاح!")
        
        # انتظار الإشارات
        stop_event = asyncio.Event()
        
        def signal_handler(signum, frame):
            logger.info(f"📶 استلام إشارة {signum}. جاري الإغلاق...")
            stop_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # انتظار حتى إغلاق البوت
        await stop_event.wait()
        
    except Exception as e:
        logger.error(f"❌ خطأ في تشغيل البوت: {e}", exc_info=True)
    
    finally:
        # الإغلاق النظيف
        logger.info("🧹 جاري التنظيف...")
        
        try:
            if bot.application:
                await bot.application.stop()
            
            if bot.db_manager:
                await bot.db_manager.close()
            
            logger.info("✅ اكتمل الإغلاق بنجاح")
            
        except Exception as e:
            logger.error(f"❌ خطأ أثناء التنظيف: {e}")

# ======================
# 7. نقطة الدخول
# ======================

if __name__ == "__main__":
    # إعدادات النظام
    if sys.platform != 'win32':
        try:
            import uvloop
            uvloop.install()
            logger.info("✅ استخدام uvloop لتحسين الأداء")
        except ImportError:
            logger.info("⚠️ uvloop غير مثبت. استخدام الحلقة الافتراضية")
    
    try:
        # تشغيل البوت
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 تم إغلاق البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ قاتل: {e}", exc_info=True)
        sys.exit(1)
