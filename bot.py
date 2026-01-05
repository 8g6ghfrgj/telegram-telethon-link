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
from telegram.error import TelegramError
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl import functions, types
from telethon.errors import (
    FloodWaitError, ChannelPrivateError, UsernameNotOccupiedError,
    InviteHashInvalidError, InviteHashExpiredError, ChatAdminRequiredError,
    SessionPasswordNeededError, PhoneCodeInvalidError, AuthKeyError,
    UserNotParticipantError, ChatWriteForbiddenError
)

# 🔧 FIX: Install missing packages on startup
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

# ======================
# Configuration - الإعدادات
# ======================

class Config:
    # Telegram API Credentials
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH", "")
    
    # Security
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
    
    # Encryption
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    
    # Memory management
    MAX_CACHED_URLS = 20000
    CACHE_CLEAN_INTERVAL = 1000
    MAX_MEMORY_MB = 500
    
    # Performance settings
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
    
    # Collection limits
    MAX_DIALOGS_PER_SESSION = 50
    MAX_MESSAGES_PER_SEARCH = 10
    MAX_SEARCH_TERMS = 8
    MAX_LINKS_PER_CYCLE = 200
    MAX_BATCH_SIZE = 50
    
    # Database
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10
    
    # WhatsApp collection
    WHATSAPP_DAYS_BACK = 30
    
    # Link verification
    MIN_GROUP_MEMBERS = 3
    MAX_LINK_LENGTH = 200
    VALIDATION_TIMEOUT = 30
    
    # Rate limiting
    USER_RATE_LIMIT = {
        'max_requests': 15,
        'per_seconds': 60
    }
    
    # Session management
    SESSION_TIMEOUT = 600
    MAX_SESSIONS_PER_USER = 20
    
    # Export
    MAX_EXPORT_LINKS = 100000
    EXPORT_CHUNK_SIZE = 5000
    
    # Advanced settings
    TELEGRAM_NO_TIME_LIMIT = True
    JOIN_REQUEST_CHECK_DELAY = 30
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
# Enhanced Database Manager
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
        """Initialize database"""
        if self._initialized:
            return
        
        self.db_path = Config.DB_PATH
        
        # Create directory if doesn't exist
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        
        await self._create_tables()
        
        self._initialized = True
        logger.info(f"✅ تم تهيئة قاعدة البيانات: {self.db_path}")
    
    async def _get_connection(self):
        """Get database connection"""
        return self.conn
    
    async def _create_tables(self):
        """Create database tables"""
        conn = await self._get_connection()
        
        # Sessions table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_string TEXT NOT NULL,
                phone_number TEXT,
                user_id INTEGER,
                username TEXT,
                display_name TEXT,
                added_by_user INTEGER,
                is_active BOOLEAN DEFAULT 1,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                total_uses INTEGER DEFAULT 0,
                total_links INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                notes TEXT,
                metadata TEXT
            )
        ''')
        
        # Links table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                is_join_request BOOLEAN DEFAULT 0
            )
        ''')
        
        # Users table
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
        
        await conn.commit()
        logger.info("✅ تم إنشاء جداول قاعدة البيانات")
    
    async def add_session(self, session_string: str, phone_number: str = None, 
                         user_id: int = None, username: str = None, 
                         display_name: str = None, added_by_user: int = 0) -> Tuple[bool, str]:
        """Add a new session"""
        try:
            conn = await self._get_connection()
            
            # Check if session already exists
            cursor = await conn.execute(
                "SELECT id FROM sessions WHERE session_string = ?",
                (session_string,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                return False, "الجلسة موجودة مسبقاً"
            
            # Add new session
            await conn.execute('''
                INSERT INTO sessions 
                (session_string, phone_number, user_id, username, display_name, added_by_user)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session_string, phone_number, user_id, username, display_name, added_by_user))
            
            await conn.commit()
            
            # Update user stats
            if added_by_user:
                await self.update_user_stats(added_by_user, 'session_added')
            
            return True, "تمت إضافة الجلسة بنجاح"
            
        except Exception as e:
            logger.error(f"❌ خطأ في إضافة الجلسة: {e}")
            return False, f"خطأ: {str(e)}"
    
    async def add_link(self, url: str, platform: str, link_type: str = 'unknown',
                      title: str = '', members: int = 0, session_id: int = None,
                      added_by_user: int = 0) -> Tuple[bool, str]:
        """Add a new link"""
        try:
            conn = await self._get_connection()
            
            # Check if link already exists
            cursor = await conn.execute(
                "SELECT id FROM links WHERE url = ?",
                (url,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                return False, "الرابط موجود مسبقاً"
            
            # Add new link
            await conn.execute('''
                INSERT INTO links 
                (url, platform, link_type, title, members_count, session_id, added_by_user)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (url, platform, link_type, title, members, session_id, added_by_user))
            
            await conn.commit()
            
            # Update user stats
            if added_by_user:
                await self.update_user_stats(added_by_user, 'link_added')
            
            return True, "تمت إضافة الرابط بنجاح"
            
        except Exception as e:
            logger.error(f"❌ خطأ في إضافة الرابط: {e}")
            return False, f"خطأ: {str(e)}"
    
    async def update_user_stats(self, user_id: int, action: str, value: int = 1):
        """Update user statistics"""
        try:
            conn = await self._get_connection()
            
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
    
    async def add_or_update_user(self, user_id: int, username: str = None, 
                                first_name: str = None, last_name: str = None):
        """Add or update user"""
        try:
            conn = await self._get_connection()
            
            cursor = await conn.execute(
                "SELECT user_id FROM bot_users WHERE user_id = ?",
                (user_id,)
            )
            
            existing = await cursor.fetchone()
            
            if existing:
                await conn.execute('''
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
                await conn.execute('''
                    INSERT INTO bot_users (user_id, username, first_name, last_name, added_date)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    user_id,
                    username or '',
                    first_name or '',
                    last_name or ''
                ))
            
            await conn.commit()
            
        except Exception as e:
            logger.error(f"❌ خطأ في إضافة/تحديث المستخدم: {e}")
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """Get user statistics"""
        try:
            conn = await self._get_connection()
            
            cursor = await conn.execute('''
                SELECT *, 
                       (SELECT COUNT(*) FROM links WHERE added_by_user = ?) as total_links,
                       (SELECT COUNT(*) FROM sessions WHERE added_by_user = ?) as total_sessions
                FROM bot_users 
                WHERE user_id = ?
            ''', (user_id, user_id, user_id))
            
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على إحصائيات المستخدم: {e}")
            return None
    
    async def get_sessions(self, user_id: int = None) -> List[Dict]:
        """Get sessions"""
        try:
            conn = await self._get_connection()
            
            if user_id:
                cursor = await conn.execute(
                    "SELECT * FROM sessions WHERE added_by_user = ? AND is_active = 1 ORDER BY added_date DESC",
                    (user_id,)
                )
            else:
                cursor = await conn.execute(
                    "SELECT * FROM sessions WHERE is_active = 1 ORDER BY added_date DESC"
                )
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على الجلسات: {e}")
            return []
    
    async def get_links(self, user_id: int = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get links"""
        try:
            conn = await self._get_connection()
            
            if user_id:
                cursor = await conn.execute(
                    "SELECT * FROM links WHERE added_by_user = ? ORDER BY collected_date DESC LIMIT ? OFFSET ?",
                    (user_id, limit, offset)
                )
            else:
                cursor = await conn.execute(
                    "SELECT * FROM links ORDER BY collected_date DESC LIMIT ? OFFSET ?",
                    (limit, offset)
                )
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على الروابط: {e}")
            return []
    
    async def get_stats(self) -> Dict:
        """Get database statistics"""
        try:
            conn = await self._get_connection()
            
            stats = {}
            
            # Total links
            cursor = await conn.execute("SELECT COUNT(*) FROM links")
            stats['total_links'] = (await cursor.fetchone())[0]
            
            # Active sessions
            cursor = await conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            # Total users
            cursor = await conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            # Links by platform
            cursor = await conn.execute(
                "SELECT platform, COUNT(*) FROM links GROUP BY platform ORDER BY COUNT(*) DESC"
            )
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على الإحصائيات: {e}")
            return {}
    
    async def export_links(self, format: str = 'txt') -> Tuple[str, str]:
        """Export links to file"""
        try:
            conn = await self._get_connection()
            
            cursor = await conn.execute(
                "SELECT url FROM links ORDER BY collected_date DESC LIMIT ?",
                (Config.MAX_EXPORT_LINKS,)
            )
            
            rows = await cursor.fetchall()
            links = [row[0] for row in rows]
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            if format == 'txt':
                filename = f"links_export_{timestamp}.txt"
                content = "\n".join(links)
            elif format == 'json':
                filename = f"links_export_{timestamp}.json"
                content = json.dumps({
                    'export_date': datetime.now().isoformat(),
                    'total_links': len(links),
                    'links': links
                }, ensure_ascii=False, indent=2)
            else:
                filename = f"links_export_{timestamp}.csv"
                content = "url,export_date\n" + "\n".join([f'{link},{datetime.now().isoformat()}' for link in links])
            
            # Save to file
            export_dir = "exports"
            os.makedirs(export_dir, exist_ok=True)
            filepath = os.path.join(export_dir, filename)
            
            async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                await f.write(content)
            
            return filepath, filename
            
        except Exception as e:
            logger.error(f"❌ خطأ في تصدير الروابط: {e}")
            return None, None
    
    async def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            await self.conn.close()
            self._initialized = False

# ======================
# Link Collector
# ======================

class LinkCollector:
    """Link collection manager"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        self.stats = {
            'total_collected': 0,
            'telegram_public': 0,
            'telegram_private': 0,
            'telegram_channels': 0,
            'telegram_groups': 0,
            'whatsapp_groups': 0,
            'errors': 0,
            'start_time': None,
            'end_time': None
        }
        
    async def start_collection(self):
        """Start collection process"""
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.stats['start_time'] = datetime.now()
        
        logger.info(f"🚀 بدء عملية الجمع: {self.stats['start_time'].isoformat()}")
        
        try:
            while self.active and not self.stop_requested:
                if self.paused:
                    await asyncio.sleep(1)
                    continue
                
                await self._collect_cycle()
                
                if self.active and not self.stop_requested:
                    await asyncio.sleep(Config.REQUEST_DELAYS['min_cycle_delay'])
        
        except Exception as e:
            logger.error(f"❌ خطأ في عملية الجمع: {e}", exc_info=True)
            self.stats['errors'] += 1
        
        finally:
            await self._stop_collection()
    
    async def _collect_cycle(self):
        """Execute one collection cycle"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_sessions()
            
            if not sessions:
                logger.warning("⚠️ لا توجد جلسات متاحة للجمع")
                return
            
            for session in sessions[:Config.MAX_CONCURRENT_SESSIONS]:
                if not self.active or self.stop_requested or self.paused:
                    break
                
                await self._process_session(session)
                await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
            
            logger.info(f"✅ اكتملت دورة الجمع. الإحصائيات: {self.stats}")
            
        except Exception as e:
            logger.error(f"❌ خطأ في دورة الجمع: {e}")
            self.stats['errors'] += 1
    
    async def _process_session(self, session: Dict):
        """Process a single session"""
        session_id = session['id']
        session_string = session['session_string']
        
        logger.info(f"🔍 معالجة الجلسة {session_id}")
        
        try:
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH,
                device_model="Link Collector",
                system_version="Linux 6.5",
                app_version="4.16.30",
                timeout=30
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                logger.error(f"❌ الجلسة {session_id} غير مصرح بها")
                return
            
            # Collect from dialogs
            await self._collect_from_dialogs(client, session_id)
            
            # Search for links
            await self._search_for_links(client, session_id)
            
            await client.disconnect()
            
            # Update session usage
            db = await EnhancedDatabaseManager.get_instance()
            conn = await db._get_connection()
            await conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, total_uses = total_uses + 1 WHERE id = ?",
                (session_id,)
            )
            await conn.commit()
            
            logger.info(f"✅ اكتملت معالجة الجلسة {session_id}")
            
        except FloodWaitError as e:
            logger.warning(f"⏱️ انتظار flood للجلسة {session_id}: {e.seconds} ثانية")
            await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            logger.error(f"❌ خطأ في معالجة الجلسة {session_id}: {e}")
            self.stats['errors'] += 1
    
    async def _collect_from_dialogs(self, client: TelegramClient, session_id: int):
        """Collect links from dialogs"""
        try:
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # Collect from entity about/bio
                    if hasattr(entity, 'about') and entity.about:
                        await self._extract_links_from_text(entity.about, session_id, 'dialog_about')
                    
                    # Collect recent messages
                    async for message in client.iter_messages(entity, limit=5):
                        if not self.active or self.stop_requested or self.paused:
                            break
                        
                        if message.text:
                            await self._extract_links_from_text(message.text, session_id, 'message')
                        
                        await asyncio.sleep(0.1)
                    
                    await asyncio.sleep(Config.REQUEST_DELAYS['normal'])
                    
                except Exception as e:
                    logger.debug(f"خطأ في معالجة الدردشة: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"❌ خطأ في جمع الدردشات: {e}")
    
    async def _search_for_links(self, client: TelegramClient, session_id: int):
        """Search for links using keywords"""
        search_terms = [
            "مجموعة", "قناة", "انضمام", "رابط", "دعوة",
            "group", "channel", "join", "link", "invite",
            "t.me", "telegram.me", "whatsapp.com"
        ]
        
        for term in search_terms[:Config.MAX_SEARCH_TERMS]:
            if not self.active or self.stop_requested or self.paused:
                break
            
            try:
                async for dialog in client.iter_dialogs(limit=10):
                    if not self.active or self.stop_requested or self.paused:
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
                                await self._extract_links_from_text(message.text, session_id, 'search')
                            
                            if self.stats['total_collected'] >= Config.MAX_LINKS_PER_CYCLE:
                                return
                        
                        await asyncio.sleep(Config.REQUEST_DELAYS['search'])
                        
                    except Exception as e:
                        logger.debug(f"خطأ في البحث في الدردشة: {e}")
                        continue
                
            except Exception as e:
                logger.error(f"❌ خطأ في البحث عن '{term}': {e}")
                continue
    
    async def _extract_links_from_text(self, text: str, session_id: int, source: str):
        """Extract and save links from text"""
        try:
            # Extract URLs
            url_patterns = [
                r'https?://[^\s<>"\']+',
                r't\.me/[^\s<>"\']+',
                r'telegram\.me/[^\s<>"\']+',
                r'chat\.whatsapp\.com/[^\s<>"\']+',
                r'discord\.gg/[^\s<>"\']+',
                r'joinchat/[^\s<>"\']+'
            ]
            
            for pattern in url_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    if not self.active or self.stop_requested or self.paused:
                        return
                    
                    # Normalize URL
                    url = match.strip()
                    if not url.startswith('http'):
                        if url.startswith('t.me/'):
                            url = 'https://' + url
                        elif url.startswith('telegram.me/'):
                            url = 'https://' + url
                        elif url.startswith('chat.whatsapp.com/'):
                            url = 'https://' + url
                    
                    # Determine platform
                    platform = 'unknown'
                    if 't.me' in url or 'telegram.me' in url:
                        platform = 'telegram'
                    elif 'whatsapp.com' in url:
                        platform = 'whatsapp'
                    elif 'discord.gg' in url:
                        platform = 'discord'
                    
                    # Determine link type
                    link_type = 'unknown'
                    if platform == 'telegram':
                        if '/joinchat/' in url or '/+' in url:
                            link_type = 'join_request'
                            self.stats['telegram_private'] += 1
                        elif '/c/' in url:
                            link_type = 'channel'
                            self.stats['telegram_channels'] += 1
                        else:
                            link_type = 'group'
                            self.stats['telegram_groups'] += 1
                    elif platform == 'whatsapp':
                        link_type = 'group'
                        self.stats['whatsapp_groups'] += 1
                    
                    # Save to database
                    db = await EnhancedDatabaseManager.get_instance()
                    success, message = await db.add_link(
                        url=url,
                        platform=platform,
                        link_type=link_type,
                        session_id=session_id,
                        added_by_user=0  # System added
                    )
                    
                    if success:
                        self.stats['total_collected'] += 1
                        logger.debug(f"✅ تم حفظ الرابط: {url}")
                    
                    await asyncio.sleep(0.1)
        
        except Exception as e:
            logger.error(f"❌ خطأ في استخراج الروابط: {e}")
    
    async def _stop_collection(self):
        """Stop collection gracefully"""
        logger.info("🛑 إيقاف عملية الجمع...")
        
        self.active = False
        self.stats['end_time'] = datetime.now()
        
        logger.info(f"📊 إحصائيات الجمع النهائية: {self.stats}")
    
    def get_status(self) -> Dict:
        """Get collection status"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'stats': self.stats.copy(),
            'timestamp': datetime.now().isoformat()
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
        logger.info("🛑 تم طلب إيقاف الجمع")

# ======================
# Telegram Bot
# ======================

class TelegramBot:
    """Main Telegram bot"""
    
    def __init__(self):
        self.collector = LinkCollector()
        self.db_manager = EnhancedDatabaseManager()
        
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        self._setup_handlers()
        
        self.user_states = {}
    
    def _setup_handlers(self):
        """Setup command handlers"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("addsession", self.add_session_command))
        self.app.add_handler(CommandHandler("mysessions", self.my_sessions_command))
        self.app.add_handler(CommandHandler("startcollect", self.start_collect_command))
        self.app.add_handler(CommandHandler("stopcollect", self.stop_collect_command))
        self.app.add_handler(CommandHandler("collectstatus", self.collect_status_command))
        self.app.add_handler(CommandHandler("mylinks", self.my_links_command))
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("admin", self.admin_command))
        
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler))
        
        self.app.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # Check access
        if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
            await update.message.reply_text(
                "❌ **غير مصرح لك باستخدام البوت**\n\n"
                "يرجى التواصل مع المسؤول للحصول على صلاحية الوصول."
            )
            return
        
        # Add/update user in database
        await self.db_manager.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        # Welcome message
        welcome_text = f"""
🤖 **مرحباً {user.first_name}!**

**بوت جمع روابط المجموعات الذكي**

🔧 **المميزات:**
• جمع روابط مجموعات تيليجرام
• جمع روابط مجموعات واتساب
• إدارة جلسات متعددة
• تصدير الروابط بصيغ مختلفة
• إحصائيات مفصلة

🚀 **الأوامر المتاحة:**
/start - بدء البوت
/help - المساعدة
/addsession - إضافة جلسة تيليجرام
/mysessions - عرض جلساتي
/startcollect - بدء الجمع
/stopcollect - إيقاف الجمع
/collectstatus - حالة الجمع
/mylinks - روابطي
/export - تصدير الروابط
/stats - الإحصائيات

📊 **الحدود:**
• أقصى {Config.MAX_SESSIONS_PER_USER} جلسة لكل مستخدم
• أقصى {Config.MAX_EXPORT_LINKS:,} رابط للتصدير
• {Config.MAX_CONCURRENT_SESSIONS} جلسة متزامنة

👉 **ابدأ بإضافة جلستك الأولى باستخدام /addsession**
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session")],
            [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")],
            [InlineKeyboardButton("❓ المساعدة", callback_data="show_help")]
        ])
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def add_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addsession command"""
        user = update.effective_user
        
        # Check if user reached session limit
        user_stats = await self.db_manager.get_user_stats(user.id)
        if user_stats and user_stats.get('session_count', 0) >= Config.MAX_SESSIONS_PER_USER:
            await update.message.reply_text(
                f"❌ **وصلت للحد الأقصى للجلسات**\n\n"
                f"لديك {user_stats['session_count']} جلسة من أقصى {Config.MAX_SESSIONS_PER_USER}\n"
                f"يرجى حذف بعض الجلسات قبل إضافة جديدة."
            )
            return
        
        await update.message.reply_text(
            "📱 **إضافة جلسة تيليجرام**\n\n"
            "1. افتح [هذا الرابط](https://my.telegram.org) وقم بتسجيل الدخول\n"
            "2. اختر API Development Tools\n"
            "3. أنشئ تطبيقاً جديداً واحصل على:\n"
            "   • API ID\n"
            "   • API Hash\n"
            "4. افتح [هذا البوت](https://t.me/userinfobot) واحصل على:\n"
            "   • User ID\n"
            "5. أرسل لي رسالة تحتوي على:\n"
            "   `api_id api_hash phone_number`\n\n"
            "**مثال:**\n"
            "`1234567 abcdef123456789012345678901234 +966501234567`\n\n"
            "⚠️ **تنبيه:** احتفظ ببياناتك الخاصة ولا تشاركها مع أحد.",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        
        self.user_states[user.id] = {'waiting_for': 'session_data'}
    
    async def my_sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mysessions command"""
        user = update.effective_user
        
        sessions = await self.db_manager.get_sessions(user.id)
        
        if not sessions:
            await update.message.reply_text(
                "📭 **لا توجد جلسات**\n\n"
                "لم تقم بإضافة أي جلسات بعد.\n"
                "استخدم /addsession لإضافة جلستك الأولى."
            )
            return
        
        text = f"📱 **جلساتك ({len(sessions)})**\n\n"
        
        for i, session in enumerate(sessions, 1):
            text += f"**{i}. {session.get('display_name', 'بدون اسم')}**\n"
            text += f"📅 أضيفت: {session['added_date'][:10]}\n"
            text += f"🔢 الاستخدامات: {session['total_uses']}\n"
            text += f"🔗 الروابط: {session['total_links']}\n"
            text += f"📞 رقم: {session.get('phone_number', 'غير معروف')}\n"
            text += f"💼 حالة: {'✅ نشطة' if session['is_active'] else '❌ غير نشطة'}\n\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة جديدة", callback_data="add_session")],
            [InlineKeyboardButton("🗑️ حذف جلسة", callback_data="delete_session")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_sessions")]
        ])
        
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def start_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /startcollect command"""
        user = update.effective_user
        
        # Check if user has sessions
        sessions = await self.db_manager.get_sessions(user.id)
        if not sessions:
            await update.message.reply_text(
                "❌ **لا توجد جلسات**\n\n"
                "يجب عليك إضافة جلسة على الأقل قبل بدء الجمع.\n"
                "استخدم /addsession لإضافة جلستك الأولى."
            )
            return
        
        # Check if collection is already running
        status = self.collector.get_status()
        if status['active']:
            await update.message.reply_text(
                "⚠️ **الجمع يعمل بالفعل**\n\n"
                "عملية الجمع قيد التشغيل حالياً.\n"
                "استخدم /collectstatus لمشاهدة الحالة."
            )
            return
        
        # Start collection in background
        asyncio.create_task(self.collector.start_collection())
        
        await update.message.reply_text(
            "🚀 **بدأت عملية الجمع**\n\n"
            "جاري جمع الروابط من جلساتك...\n\n"
            "**المعلومات:**\n"
            f"• عدد الجلسات: {len(sessions)}\n"
            f"• السرعة: {Config.MAX_CONCURRENT_SESSIONS} جلسة متزامنة\n"
            f"• التأخير بين الدورات: {Config.REQUEST_DELAYS['min_cycle_delay']} ثانية\n\n"
            "استخدم /collectstatus لمتابعة التقدم."
        )
    
    async def stop_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stopcollect command"""
        status = self.collector.get_status()
        
        if not status['active']:
            await update.message.reply_text(
                "⚠️ **الجمع غير نشط**\n\n"
                "لا توجد عملية جمع قيد التشغيل حالياً."
            )
            return
        
        await self.collector.stop()
        
        await update.message.reply_text(
            "🛑 **تم طلب إيقاف الجمع**\n\n"
            "جاري إيقاف عملية الجمع بسلاسة...\n"
            "قد يستغرق بضع ثوانٍ لحفظ جميع البيانات."
        )
    
    async def collect_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /collectstatus command"""
        status = self.collector.get_status()
        stats = status['stats']
        
        text = "📊 **حالة الجمع**\n\n"
        
        if status['active']:
            if status['paused']:
                text += "⏸️ **موقف مؤقتاً**\n"
            else:
                text += "🔄 **نشط**\n"
            
            if stats['start_time']:
                start_time = datetime.fromisoformat(stats['start_time']) if isinstance(stats['start_time'], str) else stats['start_time']
                duration = datetime.now() - start_time
                text += f"⏱️ المدة: {self._format_duration(duration)}\n"
        else:
            text += "🛑 **متوقف**\n"
        
        text += f"""
**📈 الإحصائيات:**
• 📦 إجمالي الروابط: {stats['total_collected']:,}
• 📢 مجموعات تيليجرام عامة: {stats['telegram_groups']:,}
• 🔒 مجموعات تيليجرام خاصة: {stats['telegram_private']:,}
• 📢 قنوات تيليجرام: {stats['telegram_channels']:,}
• 📱 مجموعات واتساب: {stats['whatsapp_groups']:,}
• ❌ الأخطاء: {stats['errors']:,}

**⚙️ الإعدادات:**
• أقصى جلسات متزامنة: {Config.MAX_CONCURRENT_SESSIONS}
• أقصى روابط لكل دورة: {Config.MAX_LINKS_PER_CYCLE}
• تأخير الدورة: {Config.REQUEST_DELAYS['min_cycle_delay']} ثانية
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_status")],
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
            [InlineKeyboardButton("▶️ استئناف", callback_data="resume_collect")],
            [InlineKeyboardButton("🛑 إيقاف", callback_data="stop_collect")]
        ])
        
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def my_links_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mylinks command"""
        user = update.effective_user
        
        # Get user links
        links = await self.db_manager.get_links(user.id, limit=20)
        
        if not links:
            await update.message.reply_text(
                "📭 **لا توجد روابط**\n\n"
                "لم تقم بجمع أي روابط بعد.\n"
                "استخدم /startcollect لبدء جمع الروابط."
            )
            return
        
        text = f"🔗 **روابطك ({len(links)})**\n\n"
        
        for i, link in enumerate(links[:10], 1):
            platform_icons = {
                'telegram': '📢',
                'whatsapp': '📱',
                'discord': '🎮',
                'unknown': '❓'
            }
            
            icon = platform_icons.get(link['platform'], '❓')
            
            text += f"**{i}. {icon} {link.get('title', 'بدون عنوان')}**\n"
            text += f"🔗 {link['url'][:50]}...\n"
            text += f"📅 {link['collected_date'][:10]}\n"
            text += f"👥 أعضاء: {link['members_count']}\n"
            text += f"💼 حالة: {'✅ نشط' if link['is_active'] else '❌ غير نشط'}\n\n"
        
        if len(links) > 10:
            text += f"📋 وعرض {len(links) - 10} روابط إضافية...\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 تصدير جميع الروابط", callback_data="export_links")],
            [InlineKeyboardButton("🗑️ حذف روابط", callback_data="delete_links")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_links")]
        ])
        
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command"""
        user = update.effective_user
        
        # Get total links count
        stats = await self.db_manager.get_stats()
        total_links = stats.get('total_links', 0)
        
        if total_links == 0:
            await update.message.reply_text(
                "📭 **لا توجد روابط**\n\n"
                "لم يتم جمع أي روابط بعد.\n"
                "ابدأ الجمع أولاً باستخدام /startcollect"
            )
            return
        
        text = f"""
📤 **تصدير الروابط**

📊 **الإحصائيات:**
• إجمالي الروابط: {total_links:,}
• أقصى تصدير: {Config.MAX_EXPORT_LINKS:,} رابط

📁 **صيغ التصدير المتاحة:**
• 📝 نص (TXT) - روابط فقط
• 📊 JSON - مع معلومات إضافية
• 📈 CSV - للجداول والإكسل

⚡ **اختر الصيغة المناسبة:**
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 تصدير بصيغة TXT", callback_data="export_txt")],
            [InlineKeyboardButton("📊 تصدير بصيغة JSON", callback_data="export_json")],
            [InlineKeyboardButton("📈 تصدير بصيغة CSV", callback_data="export_csv")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_export")]
        ])
        
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        # Get database stats
        db_stats = await self.db_manager.get_stats()
        
        # Get collection stats
        collect_stats = self.collector.get_status()['stats']
        
        # Get user stats
        user = update.effective_user
        user_stats = await self.db_manager.get_user_stats(user.id) or {}
        
        text = f"""
📊 **إحصائيات النظام** - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**🗄️ قاعدة البيانات:**
• 🔗 إجمالي الروابط: {db_stats.get('total_links', 0):,}
• 👥 المستخدمون: {db_stats.get('total_users', 0):,}
• 💼 الجلسات النشطة: {db_stats.get('active_sessions', 0):,}

**📈 توزيع المنصات:**
"""
        
        for platform, count in db_stats.get('links_by_platform', {}).items():
            icons = {
                'telegram': '📢',
                'whatsapp': '📱',
                'discord': '🎮',
                'unknown': '❓'
            }
            icon = icons.get(platform, '❓')
            text += f"• {icon} {platform}: {count:,}\n"
        
        text += f"""
**🎯 إحصائيات الجمع:**
• 📦 المجموع: {collect_stats.get('total_collected', 0):,}
• 📢 تيليجرام: {collect_stats.get('telegram_groups', 0) + collect_stats.get('telegram_channels', 0) + collect_stats.get('telegram_private', 0):,}
• 📱 واتساب: {collect_stats.get('whatsapp_groups', 0):,}

**👤 إحصائياتك:**
• 🆔 المعرف: {user.id}
• 👤 الاسم: {user_stats.get('first_name', '')} {user_stats.get('last_name', '')}
• 📅 الطلبات: {user_stats.get('request_count', 0):,}
• 🔗 روابطك: {user_stats.get('total_links', 0):,}
• 💼 جلساتك: {user_stats.get('session_count', 0)} / {Config.MAX_SESSIONS_PER_USER}

**⚙️ الإعدادات:**
• أقصى جلسات: {Config.MAX_CONCURRENT_SESSIONS}
• أقصى تصدير: {Config.MAX_EXPORT_LINKS:,} رابط
• أقصى جلسات لكل مستخدم: {Config.MAX_SESSIONS_PER_USER}
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_stats")],
            [InlineKeyboardButton("📊 إحصائيات مفصلة", callback_data="detailed_stats")],
            [InlineKeyboardButton("📋 تقرير", callback_data="generate_report")]
        ])
        
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
❓ **دليل استخدام البوت**

**🔧 الأوامر الأساسية:**
/start - بدء البوت والترحيب
/help - عرض هذه الرسالة
/addsession - إضافة جلسة تيليجرام جديدة
/mysessions - عرض جلساتك
/startcollect - بدء جمع الروابط
/stopcollect - إيقاف جمع الروابط
/collectstatus - حالة عملية الجمع
/mylinks - عرض الروابط المجمعة
/export - تصدير الروابط
/stats - إحصائيات النظام

**📱 إضافة جلسة:**
1. استخدم /addsession
2. اتبع التعليمات للحصول على:
   • API ID
   • API Hash
   • رقم الهاتف
3. أرسل البيانات بالصيغة:
   `api_id api_hash phone_number`

**🚀 بدء الجمع:**
1. أضف جلسة واحدة على الأقل
2. استخدم /startcollect
3. تابع التقدم باستخدام /collectstatus
4. استخدم /stopcollect للإيقاف

**📤 التصدير:**
1. استخدم /export
2. اختر صيغة التصدير
3. انتظر حتى يتم إنشاء الملف
4. سيتم إرسال الملف لك

**⚙️ الإعدادات:**
• الحد الأقصى للجلسات: {Config.MAX_SESSIONS_PER_USER}
• الحد الأقصى للتصدير: {Config.MAX_EXPORT_LINKS:,} رابط
• الجلسات المتزامنة: {Config.MAX_CONCURRENT_SESSIONS}

**⚠️ ملاحظات:**
• احتفظ ببيانات جلساتك في مكان آمن
• لا تشارك بيانات الجلسات مع أحد
• يمكنك إضافة حتى {Config.MAX_SESSIONS_PER_USER} جلسة
• الروابط تحفظ تلقائياً في قاعدة البيانات

**🆘 الدعم:**
إذا واجهت مشكلة، راجع التعليمات أو تواصل مع المسؤول.
        """.format(
            MAX_SESSIONS_PER_USER=Config.MAX_SESSIONS_PER_USER,
            MAX_EXPORT_LINKS=Config.MAX_EXPORT_LINKS,
            MAX_CONCURRENT_SESSIONS=Config.MAX_CONCURRENT_SESSIONS
        )
        
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin command"""
        user = update.effective_user
        
        # Check if user is admin
        if user.id not in Config.ADMIN_USER_IDS:
            await update.message.reply_text("❌ هذا الأمر للمسؤولين فقط.")
            return
        
        text = """
👑 **لوحة تحكم المسؤول**

**🔧 الأوامر الإدارية:**
• عرض جميع المستخدمين
• إدارة الجلسات
• مراقبة النظام
• النسخ الاحتياطي
• الإحصائيات المتقدمة

**📊 معلومات النظام:**
• إصدار البوت: 2.0
• حالة الخادم: نشط
• تحديث آلي: مفعل
• النسخ الاحتياطي: مفعل

**⚙️ الإعدادات المتقدمة:**
• الحد الأقصى للذاكرة: {MAX_MEMORY_MB} MB
• حجم الكاش: {MAX_CACHED_URLS:,}
• النسخ الاحتياطية: {MAX_BACKUPS}
• مهلة الجلسة: {SESSION_TIMEOUT} ثانية
        """.format(
            MAX_MEMORY_MB=Config.MAX_MEMORY_MB,
            MAX_CACHED_URLS=Config.MAX_CACHED_URLS,
            MAX_BACKUPS=Config.MAX_BACKUPS,
            SESSION_TIMEOUT=Config.SESSION_TIMEOUT
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 جميع المستخدمين", callback_data="admin_all_users")],
            [InlineKeyboardButton("💼 جميع الجلسات", callback_data="admin_all_sessions")],
            [InlineKeyboardButton("📊 إحصائيات النظام", callback_data="admin_system_stats")],
            [InlineKeyboardButton("💾 نسخة احتياطية", callback_data="admin_backup")],
            [InlineKeyboardButton("🧹 تنظيف النظام", callback_data="admin_cleanup")],
            [InlineKeyboardButton("🔧 إعادة التشغيل", callback_data="admin_restart")]
        ])
        
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        data = query.data
        
        # Handle different callbacks
        if data == "add_session":
            await self.add_session_command(update, context)
        elif data == "start_collect":
            await self.start_collect_command(update, context)
        elif data == "show_stats":
            await self.stats_command(update, context)
        elif data == "show_help":
            await self.help_command(update, context)
        elif data == "refresh_status":
            await self.collect_status_command(update, context)
        elif data == "pause_collect":
            await self.collector.pause()
            await query.message.edit_text("⏸️ تم إيقاف الجمع مؤقتاً")
        elif data == "resume_collect":
            await self.collector.resume()
            await query.message.edit_text("▶️ تم استئناف الجمع")
        elif data == "stop_collect":
            await self.collector.stop()
            await query.message.edit_text("🛑 تم طلب إيقاف الجمع")
        elif data == "export_txt":
            await self._handle_export(query, 'txt')
        elif data == "export_json":
            await self._handle_export(query, 'json')
        elif data == "export_csv":
            await self._handle_export(query, 'csv')
        elif data == "refresh_stats":
            await self.stats_command(update, context)
        else:
            await query.message.edit_text(f"❌ زر غير معروف: {data}")
    
    async def _handle_export(self, query, format: str):
        """Handle export callback"""
        await query.message.edit_text(f"⏳ جاري تصدير الروابط بصيغة {format.upper()}...")
        
        filepath, filename = await self.db_manager.export_links(format)
        
        if filepath and filename:
            try:
                # Send file
                async with aiofiles.open(filepath, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename=filename,
                        caption=f"✅ تم تصدير {filename}"
                    )
                
                # Cleanup
                os.remove(filepath)
                
            except Exception as e:
                logger.error(f"❌ خطأ في إرسال الملف: {e}")
                await query.message.reply_text(f"❌ خطأ في إرسال الملف: {str(e)}")
        else:
            await query.message.reply_text("❌ فشل في تصدير الروابط")
    
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular messages"""
        user = update.effective_user
        text = update.message.text
        
        # Check if user is waiting for session data
        if user.id in self.user_states and self.user_states[user.id].get('waiting_for') == 'session_data':
            try:
                # Parse session data
                parts = text.strip().split()
                if len(parts) < 3:
                    await update.message.reply_text(
                        "❌ **صيغة خاطئة**\n\n"
                        "الرجاء إرسال البيانات بالصيغة:\n"
                        "`api_id api_hash phone_number`\n\n"
                        "**مثال:**\n"
                        "`1234567 abcdef123456789012345678901234 +966501234567`"
                    )
                    return
                
                api_id = int(parts[0])
                api_hash = parts[1]
                phone_number = parts[2]
                
                # Validate phone number
                if not re.match(r'^\+?[1-9]\d{1,14}$', phone_number):
                    await update.message.reply_text(
                        "❌ **رقم هاتف غير صالح**\n\n"
                        "الرجاء إدخال رقم هاتف صحيح مع الرمز الدولي.\n"
                        "**مثال:** +966501234567"
                    )
                    return
                
                await update.message.reply_text(
                    "⏳ **جاري إنشاء الجلسة...**\n\n"
                    "قد يستغرق هذا بضع ثوانٍ.\n"
                    "سيتم إرسال رمز التحقق إلى رقم هاتفك."
                )
                
                # Create Telegram client
                client = TelegramClient(
                    StringSession(),
                    api_id,
                    api_hash,
                    device_model="Link Collector Bot",
                    system_version="Linux 6.5",
                    app_version="4.16.30"
                )
                
                await client.connect()
                
                # Send code request
                await client.send_code_request(phone_number)
                
                await update.message.reply_text(
                    "📲 **تم إرسال رمز التحقق**\n\n"
                    "تم إرسال رمز التحقق إلى رقم هاتفك.\n"
                    "الرجاء إرسال الرمز المكون من 5 أرقام.\n\n"
                    "**مثال:** `12345`"
                )
                
                # Store client in user state
                self.user_states[user.id] = {
                    'waiting_for': 'verification_code',
                    'client': client,
                    'phone_number': phone_number,
                    'api_id': api_id,
                    'api_hash': api_hash
                }
                
            except ValueError:
                await update.message.reply_text(
                    "❌ **رقم API ID غير صالح**\n\n"
                    "API ID يجب أن يكون رقماً صحيحاً.\n"
                    "الرجاء المحاولة مرة أخرى."
                )
            except Exception as e:
                logger.error(f"❌ خطأ في معالجة بيانات الجلسة: {e}")
                await update.message.reply_text(
                    f"❌ **حدث خطأ**: {str(e)[:200]}\n\n"
                    "الرجاء التأكد من البيانات والمحاولة مرة أخرى."
                )
        
        # Check if user is waiting for verification code
        elif user.id in self.user_states and self.user_states[user.id].get('waiting_for') == 'verification_code':
            try:
                code = text.strip()
                
                if not code.isdigit() or len(code) != 5:
                    await update.message.reply_text(
                        "❌ **رمز تحقق غير صالح**\n\n"
                        "الرجاء إرسال رمز مكون من 5 أرقام.\n"
                        "**مثال:** `12345`"
                    )
                    return
                
                await update.message.reply_text("⏳ جاري التحقق من الرمز...")
                
                client = self.user_states[user.id]['client']
                phone_number = self.user_states[user.id]['phone_number']
                
                # Sign in with code
                await client.sign_in(phone_number, code)
                
                # Get session string
                session_string = client.session.save()
                
                # Get user info
                me = await client.get_me()
                
                await client.disconnect()
                
                # Save session to database
                success, message = await self.db_manager.add_session(
                    session_string=session_string,
                    phone_number=phone_number,
                    user_id=me.id,
                    username=me.username,
                    display_name=f"{me.first_name or ''} {me.last_name or ''}".strip() or phone_number,
                    added_by_user=user.id
                )
                
                if success:
                    # Clear user state
                    del self.user_states[user.id]
                    
                    await update.message.reply_text(
                        f"✅ **تمت إضافة الجلسة بنجاح!**\n\n"
                        f"**معلومات الجلسة:**\n"
                        f"• 👤 المستخدم: {me.first_name or ''} {me.last_name or ''}\n"
                        f"• 🆔 المعرف: {me.id}\n"
                        f"• 📱 رقم الهاتف: {phone_number}\n"
                        f"• 📅 تاريخ الإضافة: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"يمكنك الآن استخدام /startcollect لبدء جمع الروابط!"
                    )
                else:
                    await update.message.reply_text(
                        f"❌ **فشل في حفظ الجلسة**: {message}\n\n"
                        f"الرجاء المحاولة مرة أخرى."
                    )
                
            except Exception as e:
                logger.error(f"❌ خطأ في التحقق من الرمز: {e}")
                await update.message.reply_text(
                    f"❌ **خطأ في التحقق**: {str(e)[:200]}\n\n"
                    "الرجاء المحاولة مرة أخرى باستخدام /addsession"
                )
                
                # Cleanup
                if user.id in self.user_states:
                    client = self.user_states[user.id].get('client')
                    if client:
                        try:
                            await client.disconnect()
                        except:
                            pass
                    del self.user_states[user.id]
        
        else:
            # Default response for unknown messages
            await update.message.reply_text(
                "🤖 **أهلاً بك في بوت جمع الروابط**\n\n"
                "يمكنك استخدام الأوامر التالية:\n"
                "/start - بدء البوت\n"
                "/help - المساعدة\n"
                "/addsession - إضافة جلسة\n"
                "/startcollect - بدء الجمع\n\n"
                "أو استخدم الأزرار في الرسالة السابقة."
            )
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        try:
            error = context.error
            
            logger.error(f"❌ خطأ غير معالج: {error}", exc_info=True)
            
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ **حدث خطأ غير متوقع**\n\n"
                         "لقد واجهنا مشكلة فنية. الرجاء المحاولة مرة أخرى لاحقاً.\n"
                         "إذا استمرت المشكلة، تواصل مع المسؤول.",
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            logger.error(f"❌ خطأ في معالج الأخطاء: {e}")
    
    def _format_duration(self, duration: timedelta) -> str:
        """Format duration"""
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        parts = []
        if hours > 0:
            parts.append(f"{hours} ساعة")
        if minutes > 0:
            parts.append(f"{minutes} دقيقة")
        if seconds > 0 or not parts:
            parts.append(f"{seconds} ثانية")
        
        return " و ".join(parts)

# ======================
# FastAPI Health Check
# ======================

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
import threading

class HealthCheckServer:
    """Health check server for Render"""
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.app = FastAPI(title="Telegram Link Collector")
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
                # Check database
                db_ok = os.path.exists(Config.DB_PATH)
                
                # Check memory
                memory_ok = True
                try:
                    import psutil
                    memory_percent = psutil.virtual_memory().percent
                    memory_ok = memory_percent < 90
                except:
                    memory_ok = True
                
                status = {
                    "status": "healthy" if all([db_ok, memory_ok]) else "degraded",
                    "timestamp": datetime.now().isoformat(),
                    "checks": {
                        "database": db_ok,
                        "memory": memory_ok
                    }
                }
                
                if status["status"] == "healthy":
                    return JSONResponse(status_code=200, content=status)
                else:
                    return JSONResponse(status_code=503, content=status)
                
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    }
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
        logger.info(f"✅ بدأ خادم فحص الصحة على المنفذ {self.port}")
    
    def stop(self):
        """Stop server"""
        if self.server_thread:
            logger.info("🛑 إيقاف خادم فحص الصحة")

# ======================
# Signal Handlers
# ======================

def setup_signal_handlers():
    """Setup signal handlers"""
    def signal_handler(signum, frame):
        logger.info(f"📶 تم استقبال إشارة {signum}. جاري الإغلاق السلس...")
        logger.info("📊 إحصائيات النظام النهائية:")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# ======================
# Backup Manager
# ======================

class BackupManager:
    """Backup manager"""
    
    @staticmethod
    async def create_backup():
        """Create backup"""
        if not Config.BACKUP_ENABLED:
            return None
        
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = "backups"
            backup_filename = f"{Config.DB_PATH}.backup_{timestamp}"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            os.makedirs(backup_dir, exist_ok=True)
            
            if not os.path.exists(Config.DB_PATH):
                logger.error("❌ ملف قاعدة البيانات غير موجود")
                return None
            
            shutil.copy2(Config.DB_PATH, backup_path)
            
            logger.info(f"✅ تم إنشاء نسخة احتياطية: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء نسخة احتياطية: {e}")
            return None
    
    @staticmethod
    async def rotate_backups():
        """Rotate backups"""
        try:
            if not os.path.exists("backups"):
                return
            
            backups = []
            for filename in os.listdir("backups"):
                if filename.startswith(Config.DB_PATH + ".backup_"):
                    path = os.path.join("backups", filename)
                    try:
                        ctime = os.path.getctime(path)
                        backups.append({
                            'path': path,
                            'created': ctime
                        })
                    except:
                        continue
            
            if not backups:
                return
            
            backups.sort(key=lambda x: x['created'])
            
            now = datetime.now()
            to_delete = []
            
            # Keep only latest MAX_BACKUPS
            if len(backups) > Config.MAX_BACKUPS:
                to_delete = backups[:len(backups) - Config.MAX_BACKUPS]
            
            deleted_count = 0
            for backup in to_delete:
                try:
                    os.remove(backup['path'])
                    deleted_count += 1
                except:
                    pass
            
            if deleted_count > 0:
                logger.info(f"✅ تم تدوير {deleted_count} نسخة احتياطية قديمة")
            
            return deleted_count
                    
        except Exception as e:
            logger.error(f"❌ خطأ في تدوير النسخ الاحتياطية: {e}")
            return 0

# ======================
# Main Entry Point
# ======================

async def main():
    """Main function"""
    setup_signal_handlers()
    
    # Check required environment variables
    required_env_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH']
    missing = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing:
        logger.error(f"❌ متغيرات بيئية مفقودة: {missing}")
        print(f"❌ خطأ: المتغيرات البيئية التالية مفقودة: {', '.join(missing)}")
        sys.exit(1)
    
    # Create necessary directories
    os.makedirs("backups", exist_ok=True)
    os.makedirs("exports", exist_ok=True)
    
    # Start health check server
    health_server = HealthCheckServer(port=8080)
    health_server.start()
    
    # Initialize database
    db = await EnhancedDatabaseManager.get_instance()
    
    # Create and start bot
    bot = TelegramBot()
    
    logger.info("🤖 بدء تشغيل بوت جمع الروابط...")
    logger.info(f"⚙️ الإعدادات - جلسات: {Config.MAX_CONCURRENT_SESSIONS}, تصدير: {Config.MAX_EXPORT_LINKS:,}")
    
    try:
        # Start periodic maintenance
        asyncio.create_task(periodic_maintenance())
        
        # Start bot
        await bot.app.initialize()
        await bot.app.start()
        
        logger.info("✅ البوت يعمل بنجاح!")
        
        # Keep bot running
        await bot.app.updater.start_polling()
        
        # Wait forever
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"❌ خطأ في البوت: {e}", exc_info=True)
        raise
        
    finally:
        logger.info("🧹 جاري التنظيف النهائي...")
        
        try:
            # Stop bot
            await bot.app.stop()
            
            # Close database
            await db.close()
            
            # Stop health server
            health_server.stop()
            
            logger.info("✅ اكتمل الإغلاق السلس")
            
        except Exception as e:
            logger.error(f"❌ خطأ في التنظيف النهائي: {e}")

async def periodic_maintenance():
    """Periodic maintenance"""
    while True:
        try:
            # Create backup if enabled
            if Config.BACKUP_ENABLED:
                await BackupManager.create_backup()
                await BackupManager.rotate_backups()
            
            # Clean up old exports (older than 7 days)
            if os.path.exists("exports"):
                for filename in os.listdir("exports"):
                    filepath = os.path.join("exports", filename)
                    try:
                        file_age = datetime.now().timestamp() - os.path.getctime(filepath)
                        if file_age > 7 * 24 * 3600:  # 7 days
                            os.remove(filepath)
                            logger.debug(f"🧹 تم حذف الملف القديم: {filename}")
                    except:
                        pass
            
            logger.debug("✅ اكتملت الصيانة الدورية")
            
            await asyncio.sleep(3600)  # Run every hour
            
        except Exception as e:
            logger.error(f"❌ خطأ في الصيانة الدورية: {e}")
            await asyncio.sleep(300)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 توقف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ قاتل: {e}", exc_info=True)
        sys.exit(1)
