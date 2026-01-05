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
import threading
import time
import random
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
    ApplicationBuilder,
    ConversationHandler
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

# ======================
# 🔧 FIX FOR RENDER: Install missing packages
# ======================

def ensure_packages():
    """Ensure all required packages are installed"""
    required = [
        'python-telegram-bot==20.7',
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
    
    for package in required:
        pkg_name = package.split('==')[0]
        try:
            __import__(pkg_name.replace('-', '_'))
        except ImportError:
            print(f"📦 Installing {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

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
    DB_POOL_SIZE = 10
    
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
# 🔧 Advanced Encryption Manager
# ======================

class EncryptionManager:
    """Advanced encryption manager"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = EncryptionManager()
        return cls._instance
    
    def __init__(self):
        key = Config.ENCRYPTION_KEY.encode()
        salt = b'links_collector_salt_v2'
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        derived_key = base64.urlsafe_b64encode(kdf.derive(key))
        self.cipher = Fernet(derived_key)
    
    def encrypt(self, data: str) -> str:
        try:
            encrypted = self.cipher.encrypt(data.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            return data
    
    def decrypt(self, encrypted_data: str) -> str:
        try:
            decrypted = self.cipher.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            return encrypted_data
    
    def encrypt_session(self, session_string: str) -> str:
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
        try:
            if not encrypted_data or encrypted_data == '********':
                return None
            
            decrypted = self.decrypt(encrypted_data)
            data = json.loads(decrypted)
            return data['session']
        except Exception as e:
            logger.error(f"Session decryption error: {e}")
            return None

# ======================
# 🔧 Enhanced Database Manager
# ======================

class EnhancedDatabaseManager:
    """Advanced database management"""
    
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    
    @classmethod
    async def get_instance(cls):
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = EnhancedDatabaseManager()
                    await cls._instance._initialize()
        return cls._instance
    
    async def _initialize(self):
        if self._initialized:
            return
        
        self.db_path = Config.DB_PATH
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        
        await self._create_tables()
        logger.info("Database initialized successfully")
        
        self._initialized = True
    
    async def _create_tables(self):
        await self.conn.execute('''
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
        
        await self.conn.execute('''
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
        
        await self.conn.execute('''
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
        
        await self.conn.execute('''
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
        
        await self.conn.commit()
        
        # Create indexes
        indexes = [
            ('idx_links_url_hash', 'links(url_hash)'),
            ('idx_links_platform', 'links(platform)'),
            ('idx_sessions_active', 'sessions(is_active)'),
            ('idx_users_last_active', 'bot_users(last_active)')
        ]
        
        for index_name, index_sql in indexes:
            try:
                await self.conn.execute(f'CREATE INDEX IF NOT EXISTS {index_name} ON {index_sql}')
            except Exception as e:
                logger.error(f"Index creation error {index_name}: {e}")
        
        await self.conn.commit()
    
    async def add_or_update_user(self, user_id: int, username: str = None, 
                                first_name: str = None, last_name: str = None):
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
                ''', (username or '', first_name or '', last_name or '', user_id))
            else:
                await self.conn.execute('''
                    INSERT INTO bot_users (user_id, username, first_name, last_name, added_date)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, username or '', first_name or '', last_name or ''))
            
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"User update error: {e}")
            return False
    
    async def add_session(self, session_string: str, user_id: int, 
                         phone_number: str = None, username: str = None,
                         display_name: str = None) -> Tuple[bool, str, Dict]:
        try:
            enc_manager = EncryptionManager.get_instance()
            encrypted_session = enc_manager.encrypt_session(session_string)
            session_hash = hashlib.sha256(session_string.encode()).hexdigest()
            
            cursor = await self.conn.execute(
                'SELECT id FROM sessions WHERE session_hash = ?',
                (session_hash,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                return False, "Session already exists", {'session_id': existing['id']}
            
            cursor = await self.conn.execute('''
                INSERT INTO sessions 
                (session_string, session_hash, phone_number, user_id, username, 
                 display_name, added_by_user, added_date, last_used, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            ''', (
                encrypted_session, session_hash, phone_number or '', 
                user_id, username or '', display_name or '', user_id, 'active'
            ))
            
            session_id = cursor.lastrowid
            
            await self.conn.execute('''
                UPDATE bot_users 
                SET session_count = session_count + 1,
                    last_active = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (user_id,))
            
            await self.conn.commit()
            
            return True, "Session added successfully", {
                'session_id': session_id,
                'session_hash': session_hash
            }
        except Exception as e:
            logger.error(f"Session addition error: {e}")
            return False, f"Error: {str(e)[:100]}", {}
    
    async def get_user_sessions(self, user_id: int) -> List[Dict]:
        try:
            cursor = await self.conn.execute('''
                SELECT id, session_hash, phone_number, username, display_name,
                       is_active, added_date, last_used, total_uses, total_links,
                       status, health_score
                FROM sessions 
                WHERE added_by_user = ?
                ORDER BY added_date DESC
            ''', (user_id,))
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Get user sessions error: {e}")
            return []
    
    async def get_active_sessions(self, limit: int = 10) -> List[Dict]:
        try:
            cursor = await self.conn.execute('''
                SELECT * FROM sessions 
                WHERE is_active = 1 
                ORDER BY health_score DESC, last_used ASC
                LIMIT ?
            ''', (limit,))
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Get active sessions error: {e}")
            return []
    
    async def add_link(self, link_data: Dict) -> Tuple[bool, str, Dict]:
        try:
            url = link_data.get('url', '')
            url_hash = hashlib.md5(url.encode()).hexdigest()
            
            cursor = await self.conn.execute(
                'SELECT id FROM links WHERE url_hash = ?',
                (url_hash,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                return False, "Link already exists", {'link_id': existing['id']}
            
            cursor = await self.conn.execute('''
                INSERT INTO links 
                (url_hash, url, platform, link_type, telegram_type, title,
                 members_count, session_id, added_by_user, collected_date,
                 is_active, requires_join, is_verified, validation_score,
                 is_channel, is_group, is_join_request, is_supergroup)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                url_hash,
                url,
                link_data.get('platform', 'unknown'),
                link_data.get('link_type', 'unknown'),
                link_data.get('telegram_type', 'unknown'),
                link_data.get('title', '')[:200],
                link_data.get('members', 0),
                link_data.get('session_id'),
                link_data.get('added_by_user', 0),
                link_data.get('is_active', True),
                link_data.get('requires_join', False),
                link_data.get('is_verified', False),
                link_data.get('validation_score', 0),
                link_data.get('is_channel', False),
                link_data.get('is_group', True),
                link_data.get('is_join_request', False),
                link_data.get('is_supergroup', False)
            ))
            
            link_id = cursor.lastrowid
            
            if link_data.get('session_id'):
                await self.conn.execute('''
                    UPDATE sessions 
                    SET total_links = total_links + 1,
                        last_used = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (link_data['session_id'],))
            
            if link_data.get('added_by_user'):
                await self.conn.execute('''
                    UPDATE bot_users 
                    SET link_count = link_count + 1,
                        total_links_added = total_links_added + 1,
                        last_active = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (link_data['added_by_user'],))
            
            await self.conn.commit()
            
            return True, "Link added successfully", {
                'link_id': link_id,
                'url_hash': url_hash
            }
        except Exception as e:
            logger.error(f"Link addition error: {e}")
            return False, f"Error: {str(e)[:100]}", {}
    
    async def get_user_stats(self, user_id: int) -> Dict:
        try:
            cursor = await self.conn.execute('''
                SELECT 
                    u.*,
                    (SELECT COUNT(*) FROM links WHERE added_by_user = ?) as total_links,
                    (SELECT COUNT(*) FROM sessions WHERE added_by_user = ?) as total_sessions
                FROM bot_users u
                WHERE u.user_id = ?
            ''', (user_id, user_id, user_id))
            
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return {}
        except Exception as e:
            logger.error(f"Get user stats error: {e}")
            return {}
    
    async def get_database_stats(self) -> Dict:
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
            logger.error(f"Get database stats error: {e}")
            return {}
    
    async def export_links(self, user_id: int = None, platform: str = None, 
                          limit: int = 1000) -> List[str]:
        try:
            query = "SELECT url FROM links WHERE is_active = 1"
            params = []
            
            if user_id:
                query += " AND added_by_user = ?"
                params.append(user_id)
            
            if platform:
                query += " AND platform = ?"
                params.append(platform)
            
            query += " ORDER BY collected_date DESC LIMIT ?"
            params.append(limit)
            
            cursor = await self.conn.execute(query, params)
            rows = await cursor.fetchall()
            
            return [row['url'] for row in rows]
        except Exception as e:
            logger.error(f"Export links error: {e}")
            return []
    
    async def close(self):
        if self._initialized and self.conn:
            await self.conn.close()
            self._initialized = False

# ======================
# 🔧 Advanced Link Processor
# ======================

class EnhancedLinkProcessor:
    """Advanced link processing with Telegram detection"""
    
    @staticmethod
    def normalize_url(url: str) -> str:
        if not url or not isinstance(url, str):
            return ""
        
        url = url.strip()
        url = re.sub(r'^["\'\s*]+|["\'\s*]+$', '', url)
        
        if not url.startswith(('http://', 'https://')):
            if 't.me/' in url or 'telegram.me/' in url:
                url = 'https://' + url.lstrip('/')
            elif 'chat.whatsapp.com/' in url:
                url = 'https://' + url.lstrip('/')
            elif 'discord.gg/' in url:
                url = 'https://' + url.lstrip('/')
        
        try:
            parsed = urlparse(url)
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            
            if clean_url.endswith('/'):
                clean_url = clean_url[:-1]
            
            return clean_url.lower()
        except:
            return url.lower()
    
    @staticmethod
    def extract_url_info(url: str) -> Dict:
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
            
            if 't.me' in domain or 'telegram.me' in domain:
                result['platform'] = 'telegram'
                result['details'] = EnhancedLinkProcessor._extract_telegram_info(normalized_url, parsed)
            elif 'whatsapp.com' in domain:
                result['platform'] = 'whatsapp'
                result['details'] = {'is_valid': True, 'is_group': True}
            elif 'discord.gg' in domain:
                result['platform'] = 'discord'
                result['details'] = {'is_valid': True, 'is_invite': True}
            elif 'signal.group' in domain:
                result['platform'] = 'signal'
                result['details'] = {'is_valid': True, 'is_group': True}
            
            result['is_valid'] = bool(result['details'].get('is_valid', False))
            
        except Exception as e:
            logger.debug(f"URL extraction error: {e}")
        
        return result
    
    @staticmethod
    def _extract_telegram_info(url: str, parsed) -> Dict:
        result = {
            'is_valid': False,
            'username': '',
            'invite_hash': '',
            'is_channel': False,
            'is_group': False,
            'is_join_request': False,
            'is_public': False
        }
        
        path = parsed.path.strip('/')
        if not path:
            return result
        
        # Check for join links
        join_patterns = [
            r'\+([A-Za-z0-9_-]+)',
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
            result['is_valid'] = True
            result['invite_hash'] = join_hash
            result['is_group'] = True
            return result
        
        # Check for channels
        channel_patterns = [
            r'c/([^/]+)',
            r'channel/([^/]+)'
        ]
        
        for pattern in channel_patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                result['is_channel'] = True
                result['is_valid'] = True
                result['username'] = match.group(1)
                return result
        
        # Regular username
        segments = path.split('/')
        if len(segments) == 1:
            username = segments[0].lower()
            if username and not username.startswith('+'):
                result['username'] = username
                result['is_valid'] = True
                result['is_public'] = True
                result['is_group'] = True
        
        return result

# ======================
# 🔧 Advanced Session Manager
# ======================

class AdvancedSessionManager:
    """Advanced session management"""
    
    @staticmethod
    async def validate_session(session_string: str) -> Tuple[bool, Dict]:
        try:
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
            
        except AuthKeyError:
            return False, {'error': 'مفتاح مصادقة غير صالح', 'details': 'الجلسة منتهية'}
        except Exception as e:
            return False, {'error': 'خطأ في التحقق', 'details': str(e)[:200]}
    
    @staticmethod
    async def create_client(session_string: str, session_id: int) -> Optional[TelegramClient]:
        try:
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt_session(session_string)
            actual_session = decrypted_session or session_string
            
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
                return None
            
            return client
            
        except Exception as e:
            logger.error(f"Client creation error: {e}")
            return None

# ======================
# 🔧 Advanced Collection Manager
# ======================

class AdvancedCollectionManager:
    """Advanced collection management"""
    
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
            'end_time': None,
            'cycles_completed': 0
        }
        
        self.whatsapp_cutoff = datetime.now() - timedelta(days=Config.WHATSAPP_DAYS_BACK)
    
    async def start_collection(self, mode: str = 'balanced'):
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.stats['start_time'] = datetime.now()
        self.stats['cycles_completed'] = 0
        
        logger.info(f"🚀 Starting advanced collection - mode: {mode}")
        
        try:
            while self.active and not self.stop_requested:
                if self.paused:
                    await asyncio.sleep(1)
                    continue
                
                await self._collection_cycle()
                
                if self.active and not self.stop_requested:
                    await asyncio.sleep(30)
        
        except Exception as e:
            logger.error(f"Collection error: {e}", exc_info=True)
            self.stats['errors'] += 1
        
        finally:
            await self._graceful_shutdown()
    
    async def _collection_cycle(self):
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=Config.MAX_CONCURRENT_SESSIONS)
            
            if not sessions:
                logger.warning("No active sessions available")
                return
            
            for session in sessions:
                if not self.active or self.stop_requested or self.paused:
                    break
                
                await self._process_session(session)
                await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
            
            self.stats['cycles_completed'] += 1
            logger.info(f"Cycle {self.stats['cycles_completed']} completed")
            
        except Exception as e:
            logger.error(f"Cycle error: {e}")
            self.stats['errors'] += 1
    
    async def _process_session(self, session: Dict):
        session_id = session['id']
        
        try:
            client = await AdvancedSessionManager.create_client(session['session_string'], session_id)
            
            if not client:
                logger.error(f"Session {session_id} failed to create client")
                return
            
            collected_links = await self._collect_telegram_links(client, session_id, session['added_by_user'])
            
            # Update session usage
            db = await EnhancedDatabaseManager.get_instance()
            await db.conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, total_uses = total_uses + 1 WHERE id = ?",
                (session_id,)
            )
            await db.conn.commit()
            
            await client.disconnect()
            
            logger.info(f"Session {session_id} collected {len(collected_links)} links")
            
        except FloodWaitError as e:
            logger.warning(f"Flood wait for session {session_id}: {e.seconds} seconds")
            await asyncio.sleep(e.seconds + Config.REQUEST_DELAYS['flood_wait'])
        except Exception as e:
            logger.error(f"Session processing error {session_id}: {e}")
            self.stats['errors'] += 1
    
    async def _collect_telegram_links(self, client: TelegramClient, session_id: int, user_id: int) -> List[Dict]:
        collected = []
        
        try:
            # Collect from dialogs
            dialogs = []
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                dialogs.append(dialog)
            
            for dialog in dialogs:
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # Get entity info
                    if hasattr(entity, 'title'):
                        title = entity.title
                    else:
                        title = ''
                    
                    # Check if it's a channel or group
                    is_channel = isinstance(entity, types.Channel) and entity.broadcast
                    is_group = isinstance(entity, types.Channel) and not entity.broadcast
                    
                    if is_channel or is_group:
                        link_info = {
                            'url': f"https://t.me/{getattr(entity, 'username', '')}" if hasattr(entity, 'username') and entity.username else '',
                            'platform': 'telegram',
                            'link_type': 'channel' if is_channel else 'group',
                            'telegram_type': 'channel' if is_channel else 'group',
                            'title': title,
                            'members': getattr(entity, 'participants_count', 0),
                            'session_id': session_id,
                            'added_by_user': user_id,
                            'is_active': True,
                            'is_verified': True,
                            'validation_score': 90,
                            'is_channel': is_channel,
                            'is_group': is_group,
                            'is_supergroup': isinstance(entity, types.Channel) and entity.megagroup
                        }
                        
                        if link_info['url']:
                            # Add to database
                            db = await EnhancedDatabaseManager.get_instance()
                            success, message, details = await db.add_link(link_info)
                            
                            if success:
                                collected.append(link_info)
                                
                                # Update stats
                                if is_channel:
                                    self.stats['telegram_channels'] += 1
                                else:
                                    self.stats['telegram_groups'] += 1
                                
                                if link_info['url']:
                                    self.stats['telegram_public'] += 1
                        
                        await asyncio.sleep(Config.REQUEST_DELAYS['normal'])
                
                except Exception as e:
                    logger.debug(f"Dialog processing error: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Telegram links collection error: {e}")
        
        return collected
    
    async def _graceful_shutdown(self):
        logger.info("Starting graceful shutdown...")
        
        self.active = False
        self.paused = False
        self.stats['end_time'] = datetime.now()
        
        # Save final stats
        await self._save_final_stats()
        
        logger.info(f"✅ Graceful shutdown completed. Stats: {self.stats}")
    
    async def _save_final_stats(self):
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            await db.conn.execute('''
                INSERT INTO collection_sessions 
                (session_uid, start_time, end_time, status, stats, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                f"session_{secrets.token_hex(8)}",
                self.stats['start_time'].isoformat() if self.stats['start_time'] else None,
                self.stats['end_time'].isoformat() if self.stats['end_time'] else None,
                'completed',
                json.dumps(self.stats),
                int((self.stats['end_time'] - self.stats['start_time']).total_seconds()) 
                if self.stats['start_time'] and self.stats['end_time'] else 0
            ))
            
            await db.conn.commit()
            
        except Exception as e:
            logger.error(f"Final stats save error: {e}")
    
    def get_status(self) -> Dict:
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'stats': self.stats.copy()
        }
    
    async def pause(self):
        self.paused = True
        logger.info("⏸️ Collection paused")
    
    async def resume(self):
        self.paused = False
        logger.info("▶️ Collection resumed")
    
    async def stop(self):
        self.stop_requested = True
        logger.info("⏹️ Collection stop requested")

# ======================
# 🔧 Advanced Telegram Bot
# ======================

class AdvancedTelegramBot:
    """Advanced Telegram bot with all features"""
    
    def __init__(self):
        self.collection_manager = AdvancedCollectionManager()
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        
        self._setup_handlers()
        
        self.user_states = {}
        
        logger.info("🤖 Advanced Telegram Bot initialized")
    
    def _setup_handlers(self):
        """Setup all command handlers"""
        
        # Basic commands
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        
        # Session commands
        self.app.add_handler(CommandHandler("add_session", self.add_session_command))
        self.app.add_handler(CommandHandler("my_sessions", self.my_sessions_command))
        
        # Collection commands
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("pause", self.pause_command))
        self.app.add_handler(CommandHandler("resume", self.resume_command))
        self.app.add_handler(CommandHandler("stop_collect", self.stop_collect_command))
        
        # Stats commands
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("my_stats", self.my_stats_command))
        
        # Export commands
        self.app.add_handler(CommandHandler("export", self.export_command))
        
        # Admin commands
        self.app.add_handler(CommandHandler("admin_stats", self.admin_stats_command))
        
        # Callback handler
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))
        
        # Message handler
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler))
        
        # Error handler
        self.app.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # Check access
        if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
            await update.message.reply_text("❌ غير مصرح لك باستخدام هذا البوت.")
            return
        
        # Add/update user in database
        db = await EnhancedDatabaseManager.get_instance()
        await db.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        # Welcome message
        welcome_text = f"""
🤖 **مرحباً {user.first_name}!**

🎯 **بوت جمع روابط المجموعات المتقدم**

✨ **المميزات:**
• جمع روابط تيليجرام (مجموعات وقنوات)
• إدارة جلسات متعددة
• تصدير الروابط المجمعة
• إحصائيات مفصلة
• واجهة سهلة الاستخدام

🚀 **الأوامر المتاحة:**
/start - بدء استخدام البوت
/help - عرض جميع الأوامر
/add_session - إضافة جلسة تيليجرام
/my_sessions - عرض جلساتي
/collect - بدء عملية الجمع
/status - حالة الجمع الحالية
/stats - إحصائيات البوت
/my_stats - إحصائياتي الشخصية
/export - تصدير الروابط

📊 **الحدود:**
• {Config.MAX_SESSIONS_PER_USER} جلسة لكل مستخدم
• {Config.MAX_EXPORT_LINKS:,} رابط للتصدير
• جمع غير محدود لتيليجرام

🔧 **لتبدأ:** أرسل /add_session لإضافة جلستك الأولى!
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session_btn"),
             InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect_btn")],
            [InlineKeyboardButton("📊 إحصائياتي", callback_data="my_stats_btn"),
             InlineKeyboardButton("📤 تصدير روابط", callback_data="export_btn")],
            [InlineKeyboardButton("❓ المساعدة", callback_data="help_btn")]
        ])
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
📚 **دليل استخدام البوت**

🎯 **أوامر الأساسية:**
/start - بدء استخدام البوت
/help - عرض هذه الرسالة

🔐 **أوامر الجلسات:**
/add_session - إضافة جلسة تيليجرام جديدة
/my_sessions - عرض جميع جلساتي

🚀 **أوامر الجمع:**
/collect - بدء عملية الجمع التلقائي
/status - عرض حالة الجمع الحالية
/pause - إيقاف الجمع مؤقتاً
/resume - استئناف الجمع
/stop_collect - إيقاف الجمع نهائياً

📊 **أوامر الإحصائيات:**
/stats - إحصائيات البوت العامة
/my_stats - إحصائياتي الشخصية

📤 **أوامر التصدير:**
/export - تصدير الروابط المجمعة

👑 **أوامر المدير (للمدراء فقط):**
/admin_stats - إحصائيات مفصلة للمدير

🔧 **كيفية الاستخدام:**
1. أرسل /add_session لإضافة جلستك الأولى
2. أرسل /collect لبدء الجمع
3. استخدم /export لتصدير الروابط
4. تابع /status لمعرفة حالة الجمع

💡 **نصائح:**
• يمكنك إضافة حتى {Config.MAX_SESSIONS_PER_USER} جلسة
• الجمع يعمل في الخلفية
• الروابط تحفظ تلقائياً في قاعدة البيانات
• يمكنك التصدير في أي وقت
"""
        
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def add_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_session command"""
        user = update.effective_user
        
        # Check user limit
        db = await EnhancedDatabaseManager.get_instance()
        user_sessions = await db.get_user_sessions(user.id)
        
        if len(user_sessions) >= Config.MAX_SESSIONS_PER_USER:
            await update.message.reply_text(
                f"❌ وصلت للحد الأقصى ({Config.MAX_SESSIONS_PER_USER} جلسة). "
                f"يرجى حذف جلسة قبل إضافة جديدة."
            )
            return
        
        # Ask for session string
        await update.message.reply_text(
            "📱 **إضافة جلسة تيليجرام**\n\n"
            "1. افتح https://my.telegram.org\n"
            "2. سجل الدخول بحسابك\n"
            "3. اذهب إلى API Development Tools\n"
            "4. أنشئ تطبيق جديد\n"
            "5. أرسل لي الـ session string\n\n"
            "📝 **طريقة الحصول على session string:**\n"
            "• افتح @genStr_robot في تيليجرام\n"
            "• اختر Pyrogram أو Telethon\n"
            "• أرسل الرمز الذي يصلك\n"
            "• أرسل لي الـ session string الناتج\n\n"
            "🔒 **ملاحظة:** الجلسة مشفرة وآمنة تماماً.\n\n"
            "⚠️ **تحذير:** لا تشارك session string مع أحد!\n\n"
            "أرسل session string الآن أو /cancel للإلغاء:"
        )
        
        self.user_states[user.id] = 'awaiting_session'
        return 'AWAITING_SESSION'
    
    async def my_sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /my_sessions command"""
        user = update.effective_user
        
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_user_sessions(user.id)
        
        if not sessions:
            await update.message.reply_text("📭 ليس لديك أي جلسات مضافة.\nأرسل /add_session لإضافة جلسة.")
            return
        
        text = f"📋 **جلساتي ({len(sessions)}/{Config.MAX_SESSIONS_PER_USER})**\n\n"
        
        for i, session in enumerate(sessions, 1):
            status_emoji = "✅" if session['is_active'] else "❌"
            health = session.get('health_score', 100)
            
            text += f"{i}. **{session.get('display_name', 'بدون اسم')}**\n"
            text += f"   📱 {session.get('phone_number', 'بدون رقم')}\n"
            text += f"   👤 {session.get('username', 'بدون معرف')}\n"
            text += f"   🏥 الصحة: {health}%\n"
            text += f"   🔢 الاستخدامات: {session['total_uses']}\n"
            text += f"   🔗 الروابط: {session['total_links']}\n"
            text += f"   📅 الإضافة: {session['added_date'][:10]}\n"
            text += f"   📍 الحالة: {status_emoji} {session['status']}\n\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session_btn")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_sessions")]
        ])
        
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /collect command"""
        user = update.effective_user
        
        # Check if collection is already running
        if self.collection_manager.active:
            await update.message.reply_text(
                "⏳ **الجمع يعمل بالفعل!**\n\n"
                "استخدم:\n"
                "/status - لعرض الحالة\n"
                "/pause - للإيقاف المؤقت\n"
                "/stop_collect - للإيقاف النهائي"
            )
            return
        
        # Check if user has sessions
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_user_sessions(user.id)
        
        if not sessions:
            await update.message.reply_text(
                "❌ **ليس لديك جلسات!**\n\n"
                "يجب إضافة جلسة على الأقل قبل البدء.\n"
                "أرسل /add_session لإضافة جلسة."
            )
            return
        
        # Start collection
        await update.message.reply_text(
            "🚀 **بدء عملية الجمع...**\n\n"
            "• النظام: جمع تيليجرام غير محدود\n"
            "• الجلسات النشطة: سيتم استخدام جميع الجلسات النشطة\n"
            "• المدة: مستمر حتى التوقف\n\n"
            "📊 يمكنك متابعة التقدم بـ /status"
        )
        
        # Start collection in background
        asyncio.create_task(self.collection_manager.start_collection())
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        status = self.collection_manager.get_status()
        
        status_text = f"""
📊 **حالة الجمع - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**

**الحالة:** {"🔄 نشط" if status['active'] else "🛑 متوقف"}
**الإيقاف المؤقت:** {"⏸️ نعم" if status['paused'] else "▶️ لا"}
**طلب الإيقاف:** {"✅ نعم" if status['stop_requested'] else "❌ لا"}

**📈 إحصائيات الجمع:**
• الروابط المجمعة: {status['stats']['total_collected']:,}
• الدورات المكتملة: {status['stats']['cycles_completed']:,}
• القنوات: {status['stats']['telegram_channels']:,}
• المجموعات: {status['stats']['telegram_groups']:,}
• المجموعات العامة: {status['stats']['telegram_public']:,}
• الأخطاء: {status['stats']['errors']:,}

**⏱️ المدة:** {self._format_duration(status['stats'])}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_status"),
             InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect_btn")],
            [InlineKeyboardButton("▶️ استئناف", callback_data="resume_collect_btn"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect_btn")]
        ])
        
        await update.message.reply_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command"""
        if not self.collection_manager.active:
            await update.message.reply_text("⚠️ الجمع غير نشط حالياً.")
            return
        
        await self.collection_manager.pause()
        await update.message.reply_text("⏸️ تم إيقاف الجمع مؤقتاً.")
    
    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command"""
        if not self.collection_manager.active:
            await update.message.reply_text("⚠️ الجمع غير نشط حالياً.")
            return
        
        await self.collection_manager.resume()
        await update.message.reply_text("▶️ تم استئناف الجمع.")
    
    async def stop_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop_collect command"""
        if not self.collection_manager.active:
            await update.message.reply_text("⚠️ الجمع غير نشط حالياً.")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تأكيد الإيقاف", callback_data="confirm_stop")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_stop")]
        ])
        
        await update.message.reply_text(
            "⏹️ **تأكيد إيقاف الجمع**\n\n"
            "هل أنت متأكد من إيقاف الجمع؟\n\n"
            "سيتم:\n"
            "• حفظ جميع الروابط المجمعة\n"
            "• إيقاف عملية الجمع\n"
            "• يمكنك إعادة التشغيل في أي وقت\n\n"
            f"**الإحصائيات الحالية:**\n"
            f"• الروابط: {self.collection_manager.stats['total_collected']:,}\n"
            f"• الدورات: {self.collection_manager.stats['cycles_completed']:,}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        db = await EnhancedDatabaseManager.get_instance()
        stats = await db.get_database_stats()
        
        stats_text = f"""
📊 **إحصائيات البوت العامة**

**📈 قاعدة البيانات:**
• إجمالي الروابط: {stats.get('total_links', 0):,}
• الجلسات النشطة: {stats.get('active_sessions', 0):,}
• المستخدمين: {stats.get('total_users', 0):,}

**📱 الروابط حسب المنصة:**
"""
        
        for platform, count in stats.get('links_by_platform', {}).items():
            stats_text += f"• {platform}: {count:,}\n"
        
        # Collection stats
        collection_stats = self.collection_manager.get_status()['stats']
        stats_text += f"""
**🚀 عملية الجمع:**
• الحالة: {"🔄 نشط" if self.collection_manager.active else "🛑 متوقف"}
• الروابط المجمعة: {collection_stats.get('total_collected', 0):,}
• القنوات: {collection_stats.get('telegram_channels', 0):,}
• المجموعات: {collection_stats.get('telegram_groups', 0):,}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_stats")],
            [InlineKeyboardButton("📊 إحصائياتي", callback_data="my_stats_btn")]
        ])
        
        await update.message.reply_text(stats_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def my_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /my_stats command"""
        user = update.effective_user
        
        db = await EnhancedDatabaseManager.get_instance()
        user_stats = await db.get_user_stats(user.id)
        
        if not user_stats:
            await update.message.reply_text("❌ لا توجد بيانات لك.")
            return
        
        stats_text = f"""
📊 **إحصائياتي الشخصية**

**👤 معلوماتي:**
• الاسم: {user_stats.get('first_name', '')} {user_stats.get('last_name', '')}
• المعرف: @{user_stats.get('username', 'غير معروف')}
• رقم المستخدم: {user.id}

**📈 إحصائيات الاستخدام:**
• طلباتي: {user_stats.get('request_count', 0):,}
• جلساتي: {user_stats.get('session_count', 0)} / {Config.MAX_SESSIONS_PER_USER}
• روابطي: {user_stats.get('link_count', 0):,}
• إجمالي الروابط المضافة: {user_stats.get('total_links_added', 0):,}

**📅 النشاط:**
• تاريخ الإضافة: {user_stats.get('added_date', 'غير معروف')[:10]}
• آخر نشاط: {user_stats.get('last_active', 'غير معروف')[:16]}
• آخر أمر: {user_stats.get('last_command', 'غير معروف')}

**🎯 المتبقي:**
• جلسات متبقية: {Config.MAX_SESSIONS_PER_USER - user_stats.get('session_count', 0)}
• تصدير روابط: {Config.MAX_EXPORT_LINKS:,} كحد أقصى
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_my_stats")],
            [InlineKeyboardButton("📋 جلساتي", callback_data="my_sessions_btn")]
        ])
        
        await update.message.reply_text(stats_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command"""
        user = update.effective_user
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 تيليجرام فقط", callback_data="export_telegram")],
            [InlineKeyboardButton("📱 واتساب فقط", callback_data="export_whatsapp")],
            [InlineKeyboardButton("🌐 الكل", callback_data="export_all")],
            [InlineKeyboardButton("📊 روابطي فقط", callback_data="export_mine")]
        ])
        
        await update.message.reply_text(
            "📤 **تصدير الروابط**\n\n"
            "اختر نوع التصدير:\n\n"
            "• 📢 **تيليجرام فقط** - روابط تيليجرام فقط\n"
            "• 📱 **واتساب فقط** - روابط واتساب فقط\n"
            "• 🌐 **الكل** - جميع الروابط\n"
            "• 📊 **روابطي فقط** - الروابط التي جمعتها أنت فقط\n\n"
            f"**الحد الأقصى:** {Config.MAX_EXPORT_LINKS:,} رابط\n"
            "**التنسيق:** ملف نصي (روابط فقط)",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def admin_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin_stats command"""
        user = update.effective_user
        
        # Check if admin
        if user.id not in Config.ADMIN_USER_IDS:
            await update.message.reply_text("❌ هذا الأمر للمدراء فقط.")
            return
        
        db = await EnhancedDatabaseManager.get_instance()
        stats = await db.get_database_stats()
        
        # Get system info
        import psutil
        memory = psutil.virtual_memory()
        
        admin_text = f"""
👑 **إحصائيات المدير**

**📊 النظام:**
• الذاكرة المستخدمة: {memory.percent}%
• الذاكرة المتاحة: {memory.available / 1024 / 1024:.1f} MB
• وقت التشغيل: {time.strftime('%H:%M:%S', time.gmtime(time.time() - psutil.boot_time()))}

**📈 قاعدة البيانات:**
• إجمالي الروابط: {stats.get('total_links', 0):,}
• الجلسات النشطة: {stats.get('active_sessions', 0):,}
• المستخدمين: {stats.get('total_users', 0):,}
• حجم الملف: {os.path.getsize(Config.DB_PATH) / 1024 / 1024:.2f} MB

**📱 التوزيع:**
"""
        
        for platform, count in stats.get('links_by_platform', {}).items():
            admin_text += f"• {platform}: {count:,}\n"
        
        # Get top users
        try:
            cursor = await db.conn.execute('''
                SELECT user_id, username, link_count, total_links_added
                FROM bot_users 
                ORDER BY total_links_added DESC 
                LIMIT 5
            ''')
            top_users = await cursor.fetchall()
            
            admin_text += "\n**🏆 أفضل 5 مستخدمين:**\n"
            for i, user_row in enumerate(top_users, 1):
                admin_text += f"{i}. {user_row['username'] or 'بدون معرف'} - {user_row['total_links_added']:,} رابط\n"
        except:
            pass
        
        await update.message.reply_text(admin_text, parse_mode="Markdown")
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        data = query.data
        
        try:
            if data == "add_session_btn":
                await self.add_session_command(update, context)
            
            elif data == "start_collect_btn":
                await self.collect_command(update, context)
            
            elif data == "my_stats_btn":
                await self.my_stats_command(update, context)
            
            elif data == "export_btn":
                await self.export_command(update, context)
            
            elif data == "help_btn":
                await self.help_command(update, context)
            
            elif data == "refresh_sessions":
                await self.my_sessions_command(update, context)
            
            elif data == "refresh_status":
                await self.status_command(update, context)
            
            elif data == "refresh_stats":
                await self.stats_command(update, context)
            
            elif data == "refresh_my_stats":
                await self.my_stats_command(update, context)
            
            elif data == "my_sessions_btn":
                await self.my_sessions_command(update, context)
            
            elif data == "pause_collect_btn":
                await self.pause_command(update, context)
            
            elif data == "resume_collect_btn":
                await self.resume_command(update, context)
            
            elif data == "stop_collect_btn":
                await self.stop_collect_command(update, context)
            
            elif data == "confirm_stop":
                await self.collection_manager.stop()
                await query.message.edit_text("✅ تم إيقاف الجمع بنجاح.")
            
            elif data == "cancel_stop":
                await query.message.edit_text("❌ تم إلغاء إيقاف الجمع.")
            
            elif data.startswith("export_"):
                export_type = data.split("_")[1]
                await self._handle_export(user.id, export_type, query)
            
            else:
                await query.message.edit_text("❌ أمر غير معروف")
        
        except Exception as e:
            logger.error(f"Callback error: {e}")
            await query.message.edit_text(f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_export(self, user_id: int, export_type: str, query):
        """Handle export based on type"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            if export_type == "mine":
                links = await db.export_links(user_id=user_id, limit=Config.MAX_EXPORT_LINKS)
                filename = f"export_my_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            elif export_type == "telegram":
                links = await db.export_links(platform='telegram', limit=Config.MAX_EXPORT_LINKS)
                filename = f"export_telegram_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            elif export_type == "whatsapp":
                links = await db.export_links(platform='whatsapp', limit=Config.MAX_EXPORT_LINKS)
                filename = f"export_whatsapp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            else:  # all
                links = await db.export_links(limit=Config.MAX_EXPORT_LINKS)
                filename = f"export_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            if not links:
                await query.message.edit_text("❌ لا توجد روابط للتصدير.")
                return
            
            # Save to file
            os.makedirs("exports", exist_ok=True)
            filepath = os.path.join("exports", filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(link + '\n')
            
            # Send file
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📤 تم تصدير {len(links):,} رابط"
                )
            
            # Cleanup
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"Export error: {e}")
            await query.message.edit_text(f"❌ خطأ في التصدير: {str(e)[:100]}")
    
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular messages"""
        user = update.effective_user
        text = update.message.text
        
        # Check if user is awaiting session string
        if user.id in self.user_states and self.user_states[user.id] == 'awaiting_session':
            if text.lower() == '/cancel':
                del self.user_states[user.id]
                await update.message.reply_text("❌ تم إلغاء إضافة الجلسة.")
                return
            
            # Validate session
            await update.message.reply_text("🔍 جاري التحقق من الجلسة...")
            
            valid, validation_result = await AdvancedSessionManager.validate_session(text)
            
            if not valid:
                await update.message.reply_text(
                    f"❌ **خطأ في التحقق:**\n\n"
                    f"**الخطأ:** {validation_result.get('error', 'غير معروف')}\n"
                    f"**التفاصيل:** {validation_result.get('details', 'لا توجد تفاصيل')}\n\n"
                    "يرجى إرسال session string صحيح أو /cancel للإلغاء."
                )
                return
            
            # Get user info
            user_info = validation_result.get('user_info', {})
            
            # Add to database
            db = await EnhancedDatabaseManager.get_instance()
            success, message, details = await db.add_session(
                session_string=text,
                user_id=user.id,
                phone_number=user_info.get('phone', ''),
                username=user_info.get('username', ''),
                display_name=f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
            )
            
            if success:
                del self.user_states[user.id]
                
                await update.message.reply_text(
                    f"✅ **تمت إضافة الجلسة بنجاح!**\n\n"
                    f"**المعلومات:**\n"
                    f"• الاسم: {user_info.get('first_name', '')} {user_info.get('last_name', '')}\n"
                    f"• المعرف: @{user_info.get('username', 'غير معروف')}\n"
                    f"• الهاتف: {user_info.get('phone', 'غير معروف')}\n"
                    f"• رقم الجلسة: {details.get('session_id')}\n\n"
                    f"**يمكنك الآن:**\n"
                    f"• إرسال /collect لبدء الجمع\n"
                    f"• إرسال /my_sessions لعرض جلساتك\n"
                    f"• إرسال /add_session لإضافة جلسة أخرى\n\n"
                    f"🔒 **ملاحظة:** الجلسة مشفرة وآمنة في قاعدة البيانات."
                )
            else:
                await update.message.reply_text(
                    f"❌ **خطأ في إضافة الجلسة:**\n\n"
                    f"{message}\n\n"
                    "يرجى المحاولة مرة أخرى أو /cancel للإلغاء."
                )
            
            return
        
        # Default response
        await update.message.reply_text(
            "🤖 **بوت جمع الروابط**\n\n"
            "أرسل /start للبدء\n"
            "أرسل /help للحصول على المساعدة\n"
            "أرسل /add_session لإضافة جلسة\n\n"
            "📱 **الدعم:** @username"
        )
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        try:
            error = context.error
            logger.error(f"Bot error: {error}", exc_info=True)
            
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ حدث خطأ في المعالجة. تم تسجيل الخطأ.\nيرجى المحاولة مرة أخرى."
                )
        except:
            pass
    
    def _format_duration(self, stats: Dict) -> str:
        """Format duration from stats"""
        if not stats.get('start_time'):
            return "غير معروف"
        
        start_time = stats['start_time']
        if isinstance(start_time, str):
            try:
                start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            except:
                return "غير معروف"
        
        end_time = stats.get('end_time') or datetime.now()
        if isinstance(end_time, str):
            try:
                end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            except:
                end_time = datetime.now()
        
        duration = end_time - start_time
        
        hours = duration.seconds // 3600
        minutes = (duration.seconds % 3600) // 60
        seconds = duration.seconds % 60
        
        if hours > 0:
            return f"{hours} ساعة {minutes} دقيقة"
        elif minutes > 0:
            return f"{minutes} دقيقة {seconds} ثانية"
        else:
            return f"{seconds} ثانية"
    
    async def run(self):
        """Run the bot"""
        await self.app.initialize()
        await self.app.start()
        logger.info("🤖 Bot is running...")
        
        # Keep the bot running
        await self.app.updater.start_polling()
        await asyncio.Event().wait()

# ======================
# 🔧 Health Check Server for Render
# ======================

from fastapi import FastAPI
import uvicorn

class HealthCheckServer:
    """Health check server for Render"""
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.app = FastAPI(title="Telegram Link Collector Health")
        self._setup_routes()
        self.server_thread = None
        
    def _setup_routes(self):
        @self.app.get("/")
        async def root():
            return {"status": "running", "service": "Telegram Link Collector"}
        
        @self.app.get("/health")
        async def health():
            try:
                bot_status = "healthy"
                db_status = "healthy" if os.path.exists(Config.DB_PATH) else "missing"
                
                status = {
                    "status": "healthy" if bot_status == "healthy" and db_status == "healthy" else "degraded",
                    "timestamp": datetime.now().isoformat(),
                    "checks": {
                        "bot": bot_status,
                        "database": db_status,
                        "memory": "healthy"
                    }
                }
                
                return status
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
        
        @self.app.get("/metrics")
        async def metrics():
            try:
                import psutil
                memory = psutil.virtual_memory()
                
                metrics_data = {
                    "timestamp": datetime.now().isoformat(),
                    "memory": {
                        "total_mb": memory.total / 1024 / 1024,
                        "available_mb": memory.available / 1024 / 1024,
                        "percent_used": memory.percent
                    },
                    "system": {
                        "python_version": sys.version,
                        "platform": sys.platform
                    }
                }
                return metrics_data
            except Exception as e:
                return {"error": str(e)}
    
    def start(self):
        """Start server in background thread"""
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
        logger.info(f"Health check server started on port {self.port}")
    
    def stop(self):
        """Stop server"""
        if self.server_thread:
            logger.info("Health check server stopped")

# ======================
# 🔧 Main Function
# ======================

async def main():
    """Main function"""
    
    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info(f"Signal {signum} received. Shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Check required environment variables
    required_env_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH']
    missing = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing:
        logger.error(f"Missing environment variables: {missing}")
        print(f"❌ Error: Missing environment variables: {', '.join(missing)}")
        print("Please set them before running:")
        for var in missing:
            print(f"export {var}=your_value_here")
        sys.exit(1)
    
    # Create necessary directories
    os.makedirs("backups", exist_ok=True)
    os.makedirs("exports", exist_ok=True)
    os.makedirs("cache_data", exist_ok=True)
    
    # Start health check server (for Render)
    health_server = HealthCheckServer(port=8080)
    health_server.start()
    
    # Initialize database
    db = await EnhancedDatabaseManager.get_instance()
    logger.info("Database initialized")
    
    # Start the bot
    bot = AdvancedTelegramBot()
    
    logger.info("🤖 Starting Advanced Telegram Link Collector Bot...")
    logger.info(f"🔥 Enhanced Settings - max_sessions: {Config.MAX_CONCURRENT_SESSIONS}, max_export: {Config.MAX_EXPORT_LINKS:,}")
    
    try:
        # Run bot
        await bot.run()
        
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        raise
    finally:
        logger.info("🧹 Cleaning up...")
        
        # Close database
        await db.close()
        
        # Stop health server
        health_server.stop()
        
        logger.info("✅ Cleanup completed")

# ======================
# 🔧 Entry Point
# ======================

if __name__ == "__main__":
    # Set event loop policy for better performance
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    else:
        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            logger.info("✅ Using uvloop for better performance")
        except ImportError:
            logger.info("⚠️ uvloop not installed. Using default event loop")
    
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
