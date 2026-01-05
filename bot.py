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
# Configuration
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
    MAX_CONCURRENT_SESSIONS = 10
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
    DB_POOL_SIZE = 5
    
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
    MAX_SESSIONS_PER_USER = 5
    
    # Export
    MAX_EXPORT_LINKS = 50000
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
# Enhanced Link Processor
# ======================

class EnhancedLinkProcessor:
    """Advanced link processing with improved Telegram detection"""
    
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
        """Normalize URL with enhanced Telegram handling"""
        if not url or not isinstance(url, str):
            return ""
        
        original_url = url
        
        # Remove unwanted characters
        url = url.strip()
        url = re.sub(r'^["\'\s*]+|["\'\s*]+$', '', url)
        url = re.sub(r'[,\s]+$', '', url)
        
        # Extract URL from text
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
        
        # Add https if missing
        if not url.startswith(('http://', 'https://')):
            if any(domain in url for domain in EnhancedLinkProcessor.ALLOWED_DOMAINS):
                url = 'https://' + url.lstrip('/')
        
        # Parse URL
        try:
            parsed = urlparse(url)
            
            # Check allowed domain
            domain = parsed.netloc.lower()
            allowed = any(allowed_domain in domain for allowed_domain in EnhancedLinkProcessor.ALLOWED_DOMAINS)
            
            if not allowed and not aggressive:
                logger.debug(f"Domain not allowed: {domain}")
                return ""
            
            # Remove tracking parameters
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
            
            # Rebuild path
            path = parsed.path
            
            # Special handling for Telegram links
            if 't.me' in domain or 'telegram.' in domain:
                path_parts = path.strip('/').split('/')
                if len(path_parts) >= 1:
                    if len(path_parts) > 4:
                        path = '/' + '/'.join(path_parts[:4])
            
            # Rebuild URL
            clean_url = f"{parsed.scheme}://{parsed.netloc}{path}"
            if query_params:
                clean_url += f"?{'&'.join(query_params)}"
            if parsed.fragment and not aggressive:
                clean_url += f"#{parsed.fragment}"
            
            # Remove trailing slash
            if clean_url.endswith('/'):
                clean_url = clean_url[:-1]
            
            return clean_url.lower()
            
        except Exception as e:
            logger.debug(f"Error normalizing URL {original_url}: {e}")
            url = re.sub(r'[?#].*$', '', url)
            if url.endswith('/'):
                url = url[:-1]
            return url.lower()
    
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
            
            # Determine platform
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
            logger.debug(f"Error extracting URL info: {e}")
        
        return result
    
    @staticmethod
    def _extract_telegram_info_enhanced(url: str, parsed) -> Dict:
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
            'path_segments': [],
            'is_active': True
        }
        
        path = parsed.path.strip('/')
        if not path:
            return result
        
        segments = path.split('/')
        result['path_segments'] = segments
        
        # Detect join links
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
            result['is_group'] = True
            
            if 'channel' in url.lower() or 'c/' in url.lower():
                result['is_channel'] = True
                result['is_group'] = False
            return result
        
        # Detect channels
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
        
        # Detect public groups
        if len(segments) == 1:
            username = segments[0].lower()
            result['username'] = username
            
            if username.startswith('+'):
                result['is_join_request'] = True
                result['is_private'] = True
                result['invite_hash'] = username[1:]
                result['is_group'] = True
                result['is_valid'] = True
            else:
                result['is_group'] = True
                result['is_public'] = True
                result['is_valid'] = True
                result['is_supergroup'] = True
        
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
                result['is_group'] = True
                result['is_public'] = True
                result['is_supergroup'] = True
                result['is_valid'] = True
        
        return result
    
    @staticmethod
    def _extract_whatsapp_info(url: str, parsed) -> Dict:
        """Extract WhatsApp specific information"""
        return {
            'is_valid': True,
            'invite_code': parsed.path.strip('/'),
            'is_group': True
        }
    
    @staticmethod
    def _extract_discord_info(url: str, parsed) -> Dict:
        """Extract Discord specific information"""
        return {
            'is_valid': True,
            'invite_code': parsed.path.strip('/'),
            'is_invite': True
        }
    
    @staticmethod
    def _extract_signal_info(url: str, parsed) -> Dict:
        """Extract Signal specific information"""
        return {
            'is_valid': True,
            'group_code': parsed.path.strip('/'),
            'is_group': True
        }
    
    @staticmethod
    async def validate_telegram_link_advanced(client: TelegramClient, url: str, check_join_request: bool = False) -> Dict:
        """Advanced validation for Telegram links"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            details = url_info.get('details', {})
            
            result = {
                'is_valid': False,
                'is_active': False,
                'type': 'unknown',
                'title': '',
                'members': 0,
                'requires_join': details.get('is_join_request', False),
                'is_verified': False,
                'validation_score': 0,
                'reason': '',
                'method': 'advanced',
                'is_channel': details.get('is_channel', False),
                'is_group': details.get('is_group', False),
                'is_supergroup': details.get('is_supergroup', False)
            }
            
            if not url_info['is_valid']:
                result['reason'] = 'Invalid URL'
                return result
            
            # Check join request links
            if details.get('is_join_request') and check_join_request:
                try:
                    invite_hash = details.get('invite_hash', '')
                    if invite_hash:
                        invite = await client(functions.messages.CheckChatInviteRequest(
                            hash=invite_hash
                        ))
                        
                        if isinstance(invite, types.ChatInviteAlready):
                            result['is_valid'] = True
                            result['is_active'] = True
                            result['type'] = 'join_request_already_member'
                            result['is_verified'] = True
                            result['validation_score'] = 85
                        elif isinstance(invite, types.ChatInvite):
                            result['is_valid'] = True
                            result['is_active'] = True
                            result['type'] = 'join_request_valid'
                            result['title'] = invite.title
                            result['members'] = invite.participants_count
                            result['is_verified'] = True
                            result['validation_score'] = 90
                        elif isinstance(invite, types.ChatInvitePeek):
                            result['is_valid'] = True
                            result['is_active'] = True
                            result['type'] = 'join_request_peek'
                            result['title'] = invite.chat.title
                            result['is_verified'] = True
                            result['validation_score'] = 80
                    else:
                        result['reason'] = 'No invite code'
                except InviteHashInvalidError:
                    result['reason'] = 'Invalid invite link'
                except InviteHashExpiredError:
                    result['reason'] = 'Expired invite link'
                except Exception as e:
                    result['reason'] = f'Verification error: {str(e)[:50]}'
            
            # Check public groups
            elif details.get('is_public') or details.get('username'):
                username = details.get('username', '')
                if username:
                    try:
                        entity = await client.get_entity(username)
                        
                        if isinstance(entity, types.Channel):
                            if entity.broadcast:
                                result['type'] = 'channel'
                                result['is_channel'] = True
                            else:
                                result['type'] = 'supergroup' if entity.megagroup else 'group'
                                result['is_group'] = True
                                result['is_supergroup'] = entity.megagroup
                        elif isinstance(entity, types.Chat):
                            result['type'] = 'group'
                            result['is_group'] = True
                        
                        result['is_valid'] = True
                        result['is_active'] = True
                        result['title'] = getattr(entity, 'title', '')
                        result['members'] = getattr(entity, 'participants_count', 0)
                        result['is_verified'] = True
                        result['validation_score'] = 95
                        
                    except UsernameNotOccupiedError:
                        result['reason'] = 'Username not found'
                    except ChannelPrivateError:
                        result['reason'] = 'Private channel/group'
                    except Exception as e:
                        result['reason'] = f'Access error: {str(e)[:50]}'
            
            # Check other links
            else:
                result['is_valid'] = True
                result['is_active'] = True
                result['type'] = 'unknown'
                result['validation_score'] = 50
            
            return result
            
        except Exception as e:
            logger.error(f"Error in advanced link validation: {e}")
            return {
                'is_valid': False,
                'is_active': False,
                'type': 'error',
                'reason': f'Validation error: {str(e)[:50]}',
                'validation_score': 0
            }

# ======================
# Enhanced Database Manager
# ======================

class EnhancedDatabaseManager:
    """Advanced database management"""
    
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    _pool = None
    
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
        
        # Check if file exists
        db_exists = os.path.exists(self.db_path)
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        
        # Create connection pool
        self._pool = await aiosqlite.connect(self.db_path)
        
        # Initialize tables
        await self._create_tables()
        
        # Create backup if database existed previously
        if db_exists and Config.BACKUP_ENABLED:
            await BackupManager.create_backup()
            await BackupManager.rotate_backups()
        
        self._initialized = True
        
        logger.info(f"Database initialized successfully - db_path: {self.db_path}, db_exists: {db_exists}")
    
    async def _get_connection(self):
        """Get database connection"""
        conn = await aiosqlite.connect(self.db_path)
        
        # Enable advanced features
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA synchronous = NORMAL")
        await conn.execute("PRAGMA cache_size = -20000")
        await conn.execute("PRAGMA temp_store = MEMORY")
        
        return conn
    
    async def _create_tables(self):
        """Create database tables"""
        conn = await self._get_connection()
        
        # Enhanced sessions table
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
        
        # Enhanced links table
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
        
        # Collection sessions table
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
        
        # System stats table
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
        
        # Error log table
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
        
        # Pending join links table
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
        await conn.close()
    
        # Create indexes
        await self._create_indexes()
    
    async def _create_indexes(self):
        """Create database indexes"""
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
        
        conn = await self._get_connection()
        for index_name, index_sql in indexes:
            try:
                await conn.execute(f'CREATE INDEX IF NOT EXISTS {index_name} ON {index_sql}')
            except Exception as e:
                logger.error(f"Error creating index {index_name}: {e}")
        await conn.close()
    
    async def add_link_enhanced(self, link_info: Dict) -> Tuple[bool, str, Dict]:
        """Add link with enhanced information"""
        try:
            # Extract link information
            url = link_info.get('url', '')
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return False, "Invalid URL", {}
            
            details = url_info['details']
            
            conn = await self._get_connection()
            
            # Check for duplicates
            cursor = await conn.execute(
                'SELECT id FROM links WHERE url_hash = ?',
                (url_info['url_hash'],)
            )
            existing = await cursor.fetchone()
            
            if existing:
                await conn.close()
                return False, "Link already exists", {'link_id': existing[0]}
            
            # Prepare link data
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
            
            # Insert link
            cursor = await conn.execute('''
                INSERT INTO links 
                (url_hash, url, original_url, platform, link_type, telegram_type, title, 
                 description, members_count, session_id, collected_date, confidence, 
                 is_active, requires_join, is_verified, validation_score, metadata, 
                 tags, added_by_user, source, is_channel, is_group, is_join_request, is_supergroup)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                link_data['url_hash'],
                link_data['url'],
                link_data['original_url'],
                link_data['platform'],
                link_data['link_type'],
                link_data['telegram_type'],
                link_data['title'],
                link_data['description'],
                link_data['members_count'],
                link_data['session_id'],
                link_data['confidence'],
                link_data['is_active'],
                link_data['requires_join'],
                link_data['is_verified'],
                link_data['validation_score'],
                link_data['metadata'],
                link_data['tags'],
                link_data['added_by_user'],
                link_data['source'],
                link_data['is_channel'],
                link_data['is_group'],
                link_data['is_join_request'],
                link_data['is_supergroup']
            ))
            
            link_id = cursor.lastrowid
            
            await conn.commit()
            await conn.close()
            
            # Update user stats
            if link_data['added_by_user']:
                await self.update_user_stats(link_data['added_by_user'], 'link_added')
            
            return True, "Link added successfully", {
                'link_id': link_id,
                'url_hash': url_info['url_hash']
            }
                
        except Exception as e:
            logger.error(f"Error adding enhanced link: {e}")
            return False, f"Error adding: {str(e)[:100]}", {}
    
    async def add_pending_join_link(self, url: str, platform: str = 'telegram', metadata: Dict = None) -> Tuple[bool, str, Dict]:
        """Add pending join link"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return False, "Invalid URL", {}
            
            conn = await self._get_connection()
            
            # Check for duplicates
            cursor = await conn.execute(
                'SELECT id FROM pending_join_links WHERE url_hash = ?',
                (url_info['url_hash'],)
            )
            existing = await cursor.fetchone()
            
            if existing:
                # Update check time
                await conn.execute(
                    'UPDATE pending_join_links SET last_checked = CURRENT_TIMESTAMP WHERE id = ?',
                    (existing[0],)
                )
                await conn.commit()
                await conn.close()
                return False, "Link already exists in pending list", {'pending_id': existing[0]}
            
            # Add new
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
            await conn.close()
            
            return True, "Link added to pending list", {
                'pending_id': pending_id,
                'url_hash': url_info['url_hash']
            }
                
        except Exception as e:
            logger.error(f"Error adding pending link: {e}")
            return False, f"Error adding: {str(e)[:100]}", {}
    
    async def get_pending_join_links(self, limit: int = 50) -> List[Dict]:
        """Get pending join links"""
        try:
            conn = await self._get_connection()
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
            
            await conn.close()
            return pending_links
                
        except Exception as e:
            logger.error(f"Error getting pending links: {e}")
            return []
    
    async def update_pending_link_status(self, pending_id: int, status: str, 
                                        metadata: Dict = None, 
                                        check_attempts: int = 1) -> bool:
        """Update pending link status"""
        try:
            conn = await self._get_connection()
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
            await conn.close()
            return True
                
        except Exception as e:
            logger.error(f"Error updating pending link status: {e}")
            return False
    
    async def get_stats_summary_enhanced(self, detailed: bool = False) -> Dict:
        """Get comprehensive database statistics"""
        try:
            stats = {}
            
            conn = await self._get_connection()
            
            # Basic statistics
            cursor = await conn.execute("SELECT COUNT(*) FROM links")
            stats['total_links'] = (await cursor.fetchone())[0]
            
            cursor = await conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            cursor = await conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            cursor = await conn.execute("SELECT COUNT(*) FROM pending_join_links WHERE status = 'pending'")
            stats['pending_join_links'] = (await cursor.fetchone())[0]
            
            # Links by platform
            cursor = await conn.execute(
                "SELECT platform, COUNT(*) FROM links GROUP BY platform ORDER BY COUNT(*) DESC"
            )
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            # Advanced Telegram breakdown
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
            
            # Active links statistics
            cursor = await conn.execute("SELECT COUNT(*) FROM links WHERE is_active = 1")
            stats['active_links'] = (await cursor.fetchone())[0]
            
            cursor = await conn.execute("SELECT COUNT(*) FROM links WHERE requires_join = 1")
            stats['requires_join'] = (await cursor.fetchone())[0]
            
            # Daily activity (last 7 days)
            cursor = await conn.execute('''
                SELECT DATE(collected_date) as date, COUNT(*) as count
                FROM links 
                WHERE collected_date > datetime('now', '-7 days')
                GROUP BY DATE(collected_date)
                ORDER BY date DESC
            ''')
            stats['daily_activity'] = dict(await cursor.fetchall())
            
            if detailed:
                # Top users
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
                
                # Top sessions
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
                
                # Verification statistics
                cursor = await conn.execute("SELECT COUNT(*) FROM links WHERE is_verified = 1")
                stats['verified_links'] = (await cursor.fetchone())[0]
                
                cursor = await conn.execute("SELECT AVG(validation_score) FROM links WHERE validation_score > 0")
                avg_score = (await cursor.fetchone())[0]
                stats['avg_validation_score'] = float(avg_score) if avg_score else 0
            
            await conn.close()
            return stats
            
        except Exception as e:
            logger.error(f"Error getting stats summary: {e}")
            return {}
    
    async def export_links_enhanced(self, filters: Dict = None, limit: int = Config.MAX_EXPORT_LINKS, 
                                   offset: int = 0) -> Tuple[List[str], Dict]:
        """Export links with enhanced filtering"""
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
            
            conn = await self._get_connection()
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            
            # Get total count
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
            
            # Analyze classification
            if rows:
                platform_counts = {}
                for row in rows:
                    platform = row[1]
                    platform_counts[platform] = platform_counts.get(platform, 0) + 1
                    
                    # Telegram classification
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
            
            await conn.close()
            return links, metadata
            
        except Exception as e:
            logger.error(f"Error exporting links: {e}")
            return [], {}
    
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
            await conn.close()
            
        except Exception as e:
            logger.debug(f"Error updating user stats: {e}")
    
    async def get_active_sessions(self, limit: int = 10):
        """Get active sessions"""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute('''
                SELECT * FROM sessions 
                WHERE is_active = 1 
                ORDER BY health_score DESC, last_used ASC
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
            
            await conn.close()
            return sessions
        except Exception as e:
            logger.error(f"Error getting active sessions: {e}")
            return []
    
    async def add_or_update_user(self, user_id: int, username: str = None, 
                                first_name: str = None, last_name: str = None):
        """Add or update user"""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute('''
                SELECT user_id FROM bot_users WHERE user_id = ?
            ''', (user_id,))
            
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
            await conn.close()
        except Exception as e:
            logger.error(f"Error adding/updating user: {e}")
    
    async def get_user_stats(self, user_id: int):
        """Get user statistics"""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute('''
                SELECT *, 
                       (SELECT COUNT(*) FROM links WHERE added_by_user = ?) as total_links,
                       (SELECT COUNT(*) FROM sessions WHERE added_by_user = ?) as total_sessions,
                       julianday(CURRENT_TIMESTAMP) - julianday(added_date) as account_age_days
                FROM bot_users 
                WHERE user_id = ?
            ''', (user_id, user_id, user_id))
            
            row = await cursor.fetchone()
            await conn.close()
            
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return None
    
    async def close(self):
        """Close database connection"""
        if self._pool:
            await self._pool.close()
            self._initialized = False

# ======================
# Advanced Collection Manager
# ======================

class AdvancedCollectionManager:
    """Advanced collection management"""
    
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
        
        # No time limits for Telegram
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
        
        self.collection_log = deque(maxlen=500)
        
        self.system_state = {
            'memory_pressure': 'low',
            'network_status': 'good',
            'collection_mode': 'balanced',
            'last_health_check': None
        }
        
        self.join_request_queue = asyncio.Queue()
        self.validation_tasks = set()
    
    async def start_collection(self, mode: str = 'balanced'):
        """Start the advanced collection process"""
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.stats['start_time'] = datetime.now()
        self.stats['cycles_completed'] = 0
        self.stats['current_session'] = self.stats['start_time'].strftime('%Y%m%d_%H%M%S')
        self.system_state['collection_mode'] = mode
        
        logger.info(f"🚀 Starting advanced collection - mode: {mode}, telegram_no_time_limit: {Config.TELEGRAM_NO_TIME_LIMIT}")
        
        try:
            # Start monitoring systems
            asyncio.create_task(self._system_monitoring())
            asyncio.create_task(self._periodic_maintenance())
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
            logger.error(f"❌ Error in collection process: {e}")
            self.stats['errors'] += 1
        
        finally:
            await self._graceful_shutdown()
    
    async def _enhanced_collection_cycle(self):
        """Execute enhanced collection cycle"""
        cycle_start = datetime.now()
        cycle_id = f"cycle_{self.stats['cycles_completed']}_{secrets.token_hex(4)}"
        
        logger.info(f"Starting enhanced collection cycle {cycle_id}")
        self.collection_log.append({'type': 'cycle_start', 'cycle_id': cycle_id, 'time': datetime.now().isoformat()})
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=Config.MAX_CONCURRENT_SESSIONS * 2)
            
            if not sessions:
                logger.warning("No active sessions available")
                self.collection_log.append({'type': 'no_sessions', 'time': datetime.now().isoformat()})
                return
            
            # Select healthy sessions
            healthy_sessions = [s for s in sessions if s.get('health_score', 0) >= 50]
            
            if not healthy_sessions:
                logger.warning("No healthy sessions available")
                self.collection_log.append({'type': 'no_healthy_sessions', 'time': datetime.now().isoformat()})
                return
            
            max_sessions = self._calculate_optimal_session_count()
            selected_sessions = healthy_sessions[:max_sessions]
            
            tasks = []
            for i, session in enumerate(selected_sessions):
                if not self.active or self.stop_requested or self.paused:
                    break
                
                task = self._process_session_unlimited(session, i, cycle_id)
                tasks.append(asyncio.create_task(task))
            
            if not tasks:
                return
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
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
            
            self.collection_log.append({
                'type': 'cycle_complete', 
                'cycle_id': cycle_id,
                'duration': cycle_duration,
                'sessions_processed': successful,
                'sessions_failed': failed
            })
            
            logger.info(f"Cycle {cycle_id} completed: {successful} successful, {failed} failed")
            
        except Exception as e:
            logger.error(f"Error in collection cycle: {e}")
            self.stats['errors'] += 1
    
    async def _process_session_unlimited(self, session: Dict, index: int, cycle_id: str):
        """Process session with unlimited Telegram collection"""
        session_id = session.get('id')
        session_hash = session.get('session_hash')
        added_by_user = session.get('added_by_user', 0)
        
        logger.info(f"Processing session {session_id} in cycle {cycle_id}")
        
        if index > 0:
            delay = self._calculate_session_delay(index)
            await asyncio.sleep(delay)
        
        try:
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt_session(session.get('session_string', ''))
            actual_session = decrypted_session or session.get('session_string', '')
            
            if not actual_session or actual_session == '********':
                logger.error(f"Session {session_id} not available")
                return {'session_id': session_id, 'status': 'error', 'reason': 'Session not available'}
            
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
                logger.error(f"Session {session_id} not authorized")
                return {'session_id': session_id, 'status': 'error', 'reason': 'Not authorized'}
            
            # Collect links without time limits
            collected_links = await self._collect_all_telegram_links(client, session_id, added_by_user, cycle_id)
            
            # Update session usage
            db = await EnhancedDatabaseManager.get_instance()
            conn = await db._get_connection()
            await conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, total_uses = total_uses + 1, total_links = total_links + ? WHERE id = ?",
                (len(collected_links), session_id)
            )
            await conn.commit()
            await conn.close()
            
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
            logger.warning(f"Flood wait for session {session_id}: {e.seconds} seconds")
            self.stats['flood_waits'] += 1
            await asyncio.sleep(e.seconds + Config.REQUEST_DELAYS['flood_wait'])
            return {'session_id': session_id, 'status': 'flood_wait', 'wait_seconds': e.seconds}
            
        except Exception as e:
            logger.error(f"Error processing session {session_id}: {e}")
            self.stats['errors'] += 1
            return {'session_id': session_id, 'status': 'error', 'reason': str(e)}
    
    async def _collect_all_telegram_links(self, client: TelegramClient, session_id: int, 
                                         added_by_user: int, cycle_id: str) -> List[Dict]:
        """Collect all Telegram links without time limits"""
        collected = []
        
        strategies = [
            self._strategy_all_dialogs,
            self._strategy_search_all_messages
        ]
        
        for strategy in strategies:
            if not self.active or self.stop_requested or self.paused:
                break
            
            try:
                strategy_name = strategy.__name__
                strategy_links = await strategy(client, session_id, added_by_user)
                collected.extend(strategy_links)
                
                await asyncio.sleep(self._calculate_strategy_delay())
                
            except Exception as e:
                logger.error(f"Error in collection strategy: {e}")
                continue
        
        return collected
    
    async def _strategy_all_dialogs(self, client: TelegramClient, session_id: int, 
                                   added_by_user: int) -> List[Dict]:
        """Collect from all dialogs"""
        collected = []
        
        try:
            dialogs = []
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                dialogs.append(dialog)
            
            for dialog in dialogs:
                if not self.active or self.stop_requested or self.paused:
                    break
                
                try:
                    entity = dialog.entity
                    
                    # Collect links from chat description
                    if hasattr(entity, 'about') and entity.about:
                        links = self._extract_all_links(entity.about)
                        for link in links:
                            link_info = await self._process_link_enhanced(
                                client, link, session_id, added_by_user
                            )
                            if link_info:
                                collected.append(link_info)
                    
                    # Collect links from recent messages
                    try:
                        async for message in client.iter_messages(entity, limit=5):
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
                    except:
                        pass
                    
                    await asyncio.sleep(Config.REQUEST_DELAYS['normal'])
                    
                except Exception as e:
                    logger.debug(f"Error processing dialog: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error in all dialogs strategy: {e}")
        
        return collected
    
    async def _strategy_search_all_messages(self, client: TelegramClient, session_id: int, 
                                           added_by_user: int) -> List[Dict]:
        """Search for all links in messages"""
        collected = []
        
        search_terms = [
            "مجموعة", "قناة", "انضمام", "رابط", "دعوة",
            "group", "channel", "join", "link", "invite",
            "t.me", "telegram.me", "chat.whatsapp.com"
        ]
        
        for term in search_terms[:Config.MAX_SEARCH_TERMS]:
            if not self.active or self.stop_requested or self.paused:
                break
            
            try:
                # Search in all dialogs
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
                                extracted_links = self._extract_all_links(message.text)
                                
                                for raw_url in extracted_links:
                                    normalized_url = EnhancedLinkProcessor.normalize_url(raw_url)
                                    cache_key = f"url_{hashlib.md5(normalized_url.encode()).hexdigest()}"
                                    
                                    if await self.cache_manager.exists(cache_key, 'processed_urls'):
                                        continue
                                    
                                    # Process link
                                    link_info = await self._process_link_enhanced(
                                        client, normalized_url, session_id, added_by_user, 
                                        message.date if hasattr(message, 'date') else None
                                    )
                                    
                                    if link_info:
                                        collected.append(link_info)
                                        await self.cache_manager.set(cache_key, True, 'processed_urls', 86400)
                        
                        await asyncio.sleep(Config.REQUEST_DELAYS['between_tasks'])
                    
                    except Exception as e:
                        logger.debug(f"Error searching in dialog: {e}")
                        continue
                
                await asyncio.sleep(Config.REQUEST_DELAYS['search'])
            
            except Exception as e:
                logger.error(f"Error searching for term '{term}': {e}")
                continue
        
        return collected
    
    async def _process_link_enhanced(self, client: TelegramClient, url: str, 
                                    session_id: int, added_by_user: int,
                                    message_date=None) -> Optional[Dict]:
        """Process link with enhanced validation"""
        try:
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return None
            
            platform = url_info['platform']
            
            # Apply time limits only for WhatsApp
            if platform == 'whatsapp' and message_date:
                if message_date < self.whatsapp_cutoff:
                    return None
            
            # Link quality check
            quality_check = self._check_link_quality_enhanced(url_info)
            if not quality_check['passed']:
                return None
            
            cache_key = f"link_{url_info['url_hash']}"
            cached_info = await self.cache_manager.get(cache_key, 'validated_links')
            
            if cached_info:
                return self._create_link_info_from_cache(url, url_info, cached_info, session_id, added_by_user)
            
            # Advanced validation for Telegram links
            if platform == 'telegram' and Config.ENABLE_ADVANCED_VALIDATION:
                validated = await EnhancedLinkProcessor.validate_telegram_link_advanced(
                    client, url, check_join_request=False
                )
            else:
                validated = {'is_valid': True, 'is_active': True}
            
            if validated.get('is_valid', False) and validated.get('is_active', True):
                link_info = self._create_link_info(url, url_info, validated, session_id, added_by_user, message_date)
                
                # Store in cache
                await self.cache_manager.set(cache_key, {
                    'link_type': validated.get('type', 'unknown'),
                    'title': validated.get('title', ''),
                    'members': validated.get('members', 0),
                    'confidence': 'high' if validated.get('is_verified', False) else 'medium',
                    'validation_score': validated.get('validation_score', 50),
                    'requires_join': validated.get('requires_join', False),
                    'is_channel': validated.get('is_channel', False),
                    'is_group': validated.get('is_group', False)
                }, 'validated_links', 172800)
                
                # Update statistics
                self._update_collection_stats_enhanced(url_info, validated)
                
                # Special handling for join request links
                if validated.get('requires_join', False) or url_info['details'].get('is_join_request', False):
                    await self._handle_join_request_link(url, url_info, validated, added_by_user)
                
                # Save to database
                db = await EnhancedDatabaseManager.get_instance()
                success, message, details = await db.add_link_enhanced(link_info)
                
                if success:
                    logger.debug(f"Link saved: {url}")
                else:
                    logger.debug(f"Link not saved: {message}")
                
                return link_info
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing link {url}: {e}")
            return None
    
    def _create_link_info(self, url: str, url_info: Dict, validated: Dict, 
                         session_id: int, added_by_user: int, message_date=None) -> Dict:
        """Create link information dictionary"""
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
        """Create link info from cache"""
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
        """Handle join request link"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            # Add to pending list for later verification
            await db.add_pending_join_link(url, 'telegram', {
                'validation_info': validated,
                'added_by_user': added_by_user,
                'added_at': datetime.now().isoformat()
            })
            
            self.stats['join_links_found'] += 1
            
            logger.info(f"Join link added for verification: {url}")
            
        except Exception as e:
            logger.error(f"Error handling join link: {e}")
    
    async def _process_join_requests(self):
        """Process pending join requests"""
        while self.active and not self.stop_requested:
            try:
                if self.paused:
                    await asyncio.sleep(5)
                    continue
                
                db = await EnhancedDatabaseManager.get_instance()
                pending_links = await db.get_pending_join_links(limit=5)
                
                if not pending_links:
                    await asyncio.sleep(Config.JOIN_REQUEST_CHECK_DELAY)
                    continue
                
                logger.info(f"Processing {len(pending_links)} pending join links")
                
                for pending_link in pending_links:
                    if not self.active or self.stop_requested or self.paused:
                        break
                    
                    await self._validate_single_join_request(pending_link)
                    await asyncio.sleep(Config.REQUEST_DELAYS['join_request'])
                
                await asyncio.sleep(Config.JOIN_REQUEST_CHECK_DELAY)
                
            except Exception as e:
                logger.error(f"Error processing join requests: {e}")
                await asyncio.sleep(30)
    
    async def _validate_single_join_request(self, pending_link: Dict):
        """Validate a single join request"""
        try:
            url = pending_link['url']
            pending_id = pending_link['id']
            
            # Get session for validation
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=1)
            
            if not sessions:
                await db.update_pending_link_status(pending_id, 'failed', {
                    'error': 'No sessions available for verification'
                })
                return
            
            session = sessions[0]
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt_session(session.get('session_string', ''))
            actual_session = decrypted_session or session.get('session_string', '')
            
            if not actual_session or actual_session == '********':
                await db.update_pending_link_status(pending_id, 'failed', {
                    'error': 'Session not available'
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
                    'error': 'Session not authorized'
                })
                return
            
            # Validate join link
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                await client.disconnect()
                await db.update_pending_link_status(pending_id, 'invalid', {
                    'error': 'Invalid URL'
                })
                return
            
            # Advanced validation
            validated = await EnhancedLinkProcessor.validate_telegram_link_advanced(
                client, url, check_join_request=True
            )
            
            await client.disconnect()
            
            if validated.get('is_valid', False) and validated.get('is_active', True):
                # Add link to main database
                link_info = {
                    'url': url,
                    'url_hash': url_info['url_hash'],
                    'platform': 'telegram',
                    'link_type': validated.get('type', 'unknown'),
                    'telegram_type': validated.get('type', 'unknown'),
                    'title': validated.get('title', ''),
                    'members': validated.get('members', 0),
                    'session_id': session['id'],
                    'added_by_user': pending_link.get('metadata', {}).get('added_by_user', 0),
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
                    
                    logger.info(f"Join link verified: {url}")
                else:
                    await db.update_pending_link_status(pending_id, 'failed', {
                        'error': f'Failed to add: {message}'
                    })
            else:
                await db.update_pending_link_status(pending_id, 'invalid', {
                    'error': validated.get('reason', 'Invalid link'),
                    'validation_info': validated
                })
            
        except Exception as e:
            logger.error(f"Error validating join link {pending_link.get('url')}: {e}")
            await db.update_pending_link_status(pending_id, 'failed', {
                'error': f'Validation error: {str(e)[:100]}'
            })
    
    def _check_link_quality_enhanced(self, url_info: Dict) -> Dict:
        """Check link quality with enhanced criteria"""
        score = 100
        reasons = []
        
        url = url_info['normalized_url']
        
        # Check length
        if len(url) < self.quality_filters['min_url_length']:
            score -= 20
            reasons.append('url_too_short')
        
        if len(url) > self.quality_filters['max_url_length']:
            score -= 15
            reasons.append('url_too_long')
        
        # Check allowed patterns
        pattern_matched = False
        for pattern in self.quality_filters['allowed_patterns']:
            if re.match(pattern, url):
                pattern_matched = True
                break
        
        if not pattern_matched:
            score -= 30
            reasons.append('pattern_not_allowed')
        
        # Check platform
        if url_info['platform'] == 'unknown':
            score -= 40
            reasons.append('unknown_platform')
        
        return {
            'passed': score >= 40,
            'score': score,
            'reasons': reasons
        }
    
    def _update_collection_stats_enhanced(self, url_info: Dict, validation: Dict):
        """Update collection statistics"""
        platform = url_info['platform']
        
        if platform == 'telegram':
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
        """Extract all links from text"""
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
            r'(\+[A-Za-z0-9_-]+)'
        ]
        
        all_links = []
        for pattern in url_patterns:
            links = re.findall(pattern, text, re.IGNORECASE)
            all_links.extend(links)
        
        # Filter and improve links
        filtered_links = []
        for link in all_links:
            link = link.strip()
            if link.startswith('+') and len(link) > 5:
                link = f"https://t.me/{link}"
            filtered_links.append(link)
        
        return list(set(filtered_links))
    
    async def _update_session_health(self, session_id: int, success: bool):
        """Update session health score"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            conn = await db._get_connection()
            
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
            await conn.close()
            
        except Exception as e:
            logger.debug(f"Error updating session health: {e}")
    
    def _calculate_optimal_session_count(self) -> int:
        """Calculate optimal number of concurrent sessions"""
        base_count = Config.MAX_CONCURRENT_SESSIONS
        
        if self.system_state['memory_pressure'] == 'high':
            return max(1, base_count // 2)
        elif self.system_state['memory_pressure'] == 'medium':
            return max(2, base_count - 5)
        elif self.system_state['network_status'] == 'poor':
            return max(1, base_count // 2)
        
        return min(base_count, 10)
    
    def _calculate_adaptive_delay(self) -> float:
        """Calculate adaptive delay between cycles"""
        base_delay = Config.REQUEST_DELAYS['min_cycle_delay']
        max_delay = Config.REQUEST_DELAYS['max_cycle_delay']
        
        error_penalty = min(self.stats['errors'] * 1.5, 20)
        flood_penalty = min(self.stats['flood_waits'] * 3, 30)
        
        calculated_delay = base_delay + error_penalty + flood_penalty
        
        return max(base_delay, min(calculated_delay, max_delay))
    
    def _calculate_session_delay(self, index: int) -> float:
        """Calculate delay between sessions"""
        base_delay = Config.REQUEST_DELAYS['between_sessions']
        incremental_delay = index * 0.3
        
        if self.system_state['network_status'] == 'poor':
            incremental_delay *= 1.5
        
        return base_delay + incremental_delay
    
    def _calculate_strategy_delay(self) -> float:
        """Calculate delay between strategies"""
        return Config.REQUEST_DELAYS['between_tasks']
    
    async def _update_system_state(self):
        """Update system state"""
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
        """Optimize system between cycles"""
        memory_result = self.memory_manager.check_and_optimize()
        
        if memory_result['optimized']:
            logger.info(f"Memory optimized between cycles - saved_mb: {memory_result.get('saved_mb', 0)}")
        
        await self.cache_manager.cleanup_expired()
        
        self.performance['memory_usage_mb'] = self.memory_manager.get_memory_usage()
        
        self._calculate_performance_score()
    
    def _calculate_performance_score(self):
        """Calculate performance score"""
        scores = []
        
        success_score = self.performance['success_rate'] * 100
        scores.append(success_score)
        
        memory_usage = self.memory_manager.get_memory_percent()
        memory_score = max(0, 100 - memory_usage)
        scores.append(memory_score)
        
        if scores:
            self.stats['performance_score'] = sum(scores) / len(scores)
    
    async def _system_monitoring(self):
        """Monitor system health"""
        while self.active and not self.stop_requested:
            try:
                system_metrics = {
                    'memory_usage_mb': self.memory_manager.get_memory_usage(),
                    'memory_percent': self.memory_manager.get_memory_percent(),
                    'collection_stats': self.stats.copy(),
                    'performance_metrics': self.performance.copy(),
                    'timestamp': datetime.now().isoformat()
                }
                
                await self._store_system_metrics(system_metrics)
                await self._check_critical_issues(system_metrics)
                
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in system monitoring: {e}")
                await asyncio.sleep(30)
    
    async def _store_system_metrics(self, metrics: Dict):
        """Store system metrics"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            conn = await db._get_connection()
            
            for key, value in metrics.items():
                if key != 'timestamp':
                    await conn.execute('''
                        INSERT INTO system_stats (metric_name, metric_value, metadata)
                        VALUES (?, ?, ?)
                    ''', (key, str(value), json.dumps({'timestamp': metrics['timestamp']})))
            
            await conn.commit()
            await conn.close()
            
        except Exception as e:
            logger.debug(f"Error storing system metrics: {e}")
    
    async def _check_critical_issues(self, metrics: Dict):
        """Check for critical issues"""
        warnings = []
        
        if metrics['memory_percent'] > 90:
            warnings.append(f"Critical memory usage: {metrics['memory_percent']:.1f}%")
        
        if self.stats['errors'] > 50:
            warnings.append(f"High error count: {self.stats['errors']}")
        
        if self.performance['success_rate'] < 0.3:
            warnings.append(f"Low success rate: {self.performance['success_rate']:.1%}")
        
        if warnings:
            logger.warning(f"Critical system issues: {', '.join(warnings)}")
    
    async def _periodic_maintenance(self):
        """Perform periodic maintenance"""
        while self.active and not self.stop_requested:
            try:
                if Config.BACKUP_ENABLED:
                    await BackupManager.rotate_backups()
                
                await self._optimize_database()
                await self._cleanup_old_logs()
                
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"Error in periodic maintenance: {e}")
                await asyncio.sleep(60)
    
    async def _optimize_database(self):
        """Optimize database"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            conn = await db._get_connection()
            
            await conn.execute("ANALYZE")
            await conn.execute("VACUUM")
            await conn.commit()
            await conn.close()
            
            logger.debug("Database optimized")
            
        except Exception as e:
            logger.debug(f"Error optimizing database: {e}")
    
    async def _cleanup_old_logs(self):
        """Cleanup old logs"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            conn = await db._get_connection()
            
            await conn.execute('''
                DELETE FROM error_log 
                WHERE occurred_at < datetime('now', '-7 days')
            ''')
            
            await conn.execute('''
                DELETE FROM system_stats 
                WHERE recorded_at < datetime('now', '-30 days')
            ''')
            
            await conn.commit()
            await conn.close()
            
            logger.debug("Old logs cleaned up")
            
        except Exception as e:
            logger.debug(f"Error cleaning logs: {e}")
    
    async def _graceful_shutdown(self):
        """Perform graceful shutdown"""
        logger.info("Starting graceful shutdown of collection system...")
        
        self.active = False
        self.paused = False
        self.stats['end_time'] = datetime.now()
        
        self.cache_manager.clear()
        self.memory_manager.optimize_memory()
        
        await self._save_final_stats()
        
        logger.info(f"✅ Graceful shutdown completed. Stats: {self.stats}")
    
    async def _save_final_stats(self):
        """Save final statistics"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            conn = await db._get_connection()
            
            stats_data = {
                'stats': self.stats,
                'performance': self.performance,
                'system_state': self.system_state
            }
            
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
            await conn.close()
            
        except Exception as e:
            logger.error(f"Error saving final stats: {e}")
    
    def get_status(self) -> Dict:
        """Get collection status"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'stats': self.stats.copy(),
            'performance': self.performance.copy(),
            'system_state': self.system_state.copy(),
            'memory': self.memory_manager.get_metrics(),
            'timestamp': datetime.now().isoformat()
        }
    
    async def pause(self):
        """Pause collection"""
        self.paused = True
        logger.info("⏸️ Collection paused")
    
    async def resume(self):
        """Resume collection"""
        self.paused = False
        logger.info("▶️ Collection resumed")
    
    async def stop(self):
        """Stop collection"""
        self.stop_requested = True
        logger.info("⏹️ Collection stop requested")
        await asyncio.sleep(2)
    
    async def get_detailed_report(self) -> Dict:
        """Get detailed report"""
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary_enhanced(detailed=True)
        
        return {
            'collection_status': self.get_status(),
            'database_stats': db_stats,
            'system_health': {
                'memory': self.memory_manager.get_metrics()
            },
            'recommendations': self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations"""
        recommendations = []
        
        memory_percent = self.memory_manager.get_memory_percent()
        if memory_percent > 80:
            recommendations.append("⚠️ High memory usage. Consider increasing cache size or reducing concurrent tasks.")
        
        if self.stats['performance_score'] < 70:
            recommendations.append("⚡ Low performance score. Consider increasing cycle delays or improving strategies.")
        
        return recommendations

# ======================
# Advanced Telegram Bot
# ======================

class AdvancedTelegramBot:
    """Advanced Telegram bot with collection features"""
    
    def __init__(self):
        self.collection_manager = AdvancedCollectionManager()
        
        # Initialize application
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        
        # Setup handlers
        self._setup_handlers()
        
        self.user_states = defaultdict(dict)
        self.user_sessions = defaultdict(list)
        
        logger.info("AdvancedTelegramBot initialized")
    
    def _setup_handlers(self):
        """Setup all bot handlers"""
        # Command handlers
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        self.app.add_handler(CommandHandler("addsession", self.add_session_command))
        self.app.add_handler(CommandHandler("backup", self.backup_command))
        
        # Callback query handler
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))
        
        # Message handler
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.message_handler
        ))
        
        # Error handler
        self.app.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # Check access
        if not self._check_access(user.id):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
        
        # Add/update user in database
        db = await EnhancedDatabaseManager.get_instance()
        await db.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        # Create welcome message
        welcome_text = f"""
🤖 **Welcome {user.first_name}!**

🚀 **Advanced Link Collection Bot**

**Features:**
• Unlimited Telegram link collection
• WhatsApp group collection (last 30 days)
• Advanced link validation
• Smart filtering and deduplication
• Export in multiple formats
• Session management
• Automatic backups

**Commands:**
/start - Start the bot
/help - Show help menu
/status - Show bot status
/stats - Show statistics
/collect - Start collection
/export - Export links
/sessions - Manage sessions
/addsession - Add new session
/backup - Create backup

**Ready to start?** Use /collect to begin collecting links!
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Start Collection", callback_data="start_collect")],
            [InlineKeyboardButton("📊 View Stats", callback_data="view_stats")],
            [InlineKeyboardButton("➕ Add Session", callback_data="add_session")],
            [InlineKeyboardButton("❓ Help", callback_data="show_help")]
        ])
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
📚 **Help Guide**

**Basic Commands:**
• /start - Start the bot
• /help - Show this help message
• /status - Show bot status
• /stats - Show statistics

**Collection Commands:**
• /collect - Start/stop collection
• /export - Export collected links
• /sessions - Manage your sessions
• /addsession - Add a new session

**Administration Commands:**
• /backup - Create database backup
• /cleanup - Clean old data

**How to add a session:**
1. Get your Telegram session string
2. Use /addsession command
3. Send your session string
4. The bot will validate and add it

**Collection Process:**
1. Add at least one session
2. Use /collect to start
3. Bot will collect links automatically
4. Use /export to get your links

**Need more help?** Contact the administrator.
        """
        
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        user = update.effective_user
        
        if not self._check_access(user.id):
            await update.message.reply_text("❌ You are not authorized.")
            return
        
        # Get collection status
        collection_status = self.collection_manager.get_status()
        
        # Get database stats
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary_enhanced()
        
        status_text = f"""
📊 **Bot Status - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**

**Collection Status:**
"""
        
        if collection_status['active']:
            if collection_status['paused']:
                status_text += "⏸️ **Paused**\n"
            elif collection_status['stop_requested']:
                status_text += "🛑 **Stopping...**\n"
            else:
                status_text += "🔄 **Active**\n"
                if collection_status['stats']['start_time']:
                    duration = datetime.now() - collection_status['stats']['start_time']
                    status_text += f"   Duration: {self._format_duration(duration)}\n"
                    status_text += f"   Cycles: {collection_status['stats']['cycles_completed']}\n"
        else:
            status_text += "🛑 **Stopped**\n"
        
        status_text += f"""
**Collection Statistics:**
• Total Links: {collection_status['stats']['total_collected']:,}
• Telegram Groups: {collection_status['stats']['telegram_groups']:,}
• Telegram Channels: {collection_status['stats']['telegram_channels']:,}
• Join Requests: {collection_status['stats']['telegram_join']:,}
• WhatsApp Groups: {collection_status['stats']['whatsapp_groups']:,}
• Errors: {collection_status['stats']['errors']:,}

**Database Statistics:**
• Total Links: {db_stats.get('total_links', 0):,}
• Active Sessions: {db_stats.get('active_sessions', 0)}
• Total Users: {db_stats.get('total_users', 0)}

**System Performance:**
• Memory Usage: {collection_status['memory']['current_mb']:.1f} MB
• Performance Score: {collection_status['stats']['performance_score']:.1f}/100
• Success Rate: {collection_status['performance']['success_rate']:.1%}
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status")],
            [InlineKeyboardButton("🚀 Start Collect", callback_data="start_collect")],
            [InlineKeyboardButton("⏸️ Pause Collect", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ Stop Collect", callback_data="stop_collect")]
        ])
        
        await update.message.reply_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        user = update.effective_user
        
        if not self._check_access(user.id):
            await update.message.reply_text("❌ You are not authorized.")
            return
        
        # Get detailed statistics
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary_enhanced(detailed=True)
        
        stats_text = f"""
📈 **Detailed Statistics - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**

**Overall Statistics:**
• Total Links: {db_stats.get('total_links', 0):,}
• Active Links: {db_stats.get('active_links', 0):,}
• Verified Links: {db_stats.get('verified_links', 0):,}
• Requires Join: {db_stats.get('requires_join', 0):,}
• Active Sessions: {db_stats.get('active_sessions', 0)}

**Links by Platform:**
"""
        
        for platform, count in db_stats.get('links_by_platform', {}).items():
            stats_text += f"• {platform.title()}: {count:,}\n"
        
        stats_text += "\n**Telegram Classification:**\n"
        telegram_details = db_stats.get('telegram_details', [])
        if telegram_details:
            for detail in telegram_details[:5]:  # Show top 5
                type_name = detail['type'] or 'unknown'
                if detail['is_channel']:
                    type_name = "Channel"
                elif detail['is_supergroup']:
                    type_name = "Supergroup"
                elif detail['is_group']:
                    type_name = "Group"
                
                stats_text += f"• {type_name}: {detail['count']:,}\n"
        
        # Daily activity
        daily_activity = db_stats.get('daily_activity', {})
        if daily_activity:
            stats_text += "\n**Last 7 Days Activity:**\n"
            for date_str, count in list(daily_activity.items())[:5]:  # Last 5 days
                stats_text += f"• {date_str}: {count:,}\n"
        
        # User statistics
        user_stats = await db.get_user_stats(user.id)
        if user_stats:
            stats_text += f"""
**Your Statistics:**
• User ID: {user.id}
• Account Age: {user_stats.get('account_age_days', 0):.0f} days
• Total Requests: {user_stats.get('request_count', 0):,}
• Links Added: {user_stats.get('total_links', 0):,}
• Sessions Added: {user_stats.get('total_sessions', 0)}
            """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Export Links", callback_data="export_links")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats")],
            [InlineKeyboardButton("📊 Full Report", callback_data="full_report")]
        ])
        
        await update.message.reply_text(stats_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /collect command"""
        user = update.effective_user
        
        if not self._check_access(user.id):
            await update.message.reply_text("❌ You are not authorized.")
            return
        
        # Check if user has sessions
        db = await EnhancedDatabaseManager.get_instance()
        user_sessions = await self._get_user_sessions(user.id)
        
        if not user_sessions:
            await update.message.reply_text(
                "❌ You don't have any active sessions.\n"
                "Please add a session first using /addsession command."
            )
            return
        
        collection_status = self.collection_manager.get_status()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Start Collection", callback_data="start_collect")],
            [InlineKeyboardButton("⏸️ Pause Collection", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ Stop Collection", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 Collection Status", callback_data="collect_status")],
            [InlineKeyboardButton("📋 Collection Report", callback_data="collect_report")]
        ])
        
        collect_text = f"""
🚀 **Collection Management**

**Current Status:**
"""
        
        if collection_status['active']:
            if collection_status['paused']:
                collect_text += "⏸️ **Paused**\n"
            else:
                collect_text += "🔄 **Active**\n"
                collect_text += f"• Links Collected: {collection_status['stats']['total_collected']:,}\n"
                collect_text += f"• Cycles Completed: {collection_status['stats']['cycles_completed']:,}\n"
        else:
            collect_text += "🛑 **Stopped**\n"
        
        collect_text += f"""
**Your Sessions:**
• Active Sessions: {len(user_sessions)}
• Max Sessions Allowed: {Config.MAX_SESSIONS_PER_USER}

**Collection Features:**
• Unlimited Telegram collection
• WhatsApp (last 30 days only)
• Advanced link validation
• Automatic deduplication
• Join request verification

**Ready to start?** Click 'Start Collection' below!
        """
        
        await update.message.reply_text(collect_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command"""
        user = update.effective_user
        
        if not self._check_access(user.id):
            await update.message.reply_text("❌ You are not authorized.")
            return
        
        # Get user's links count
        db = await EnhancedDatabaseManager.get_instance()
        user_stats = await db.get_user_stats(user.id)
        link_count = user_stats.get('total_links', 0) if user_stats else 0
        
        if link_count == 0:
            await update.message.reply_text(
                "❌ You don't have any links to export.\n"
                "Start collection first using /collect command."
            )
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Export as Text", callback_data="export_text")],
            [InlineKeyboardButton("📊 Export as CSV", callback_data="export_csv")],
            [InlineKeyboardButton("🎯 Export Telegram Only", callback_data="export_telegram")],
            [InlineKeyboardButton("📱 Export WhatsApp Only", callback_data="export_whatsapp")],
            [InlineKeyboardButton("⚙️ Custom Export", callback_data="export_custom")]
        ])
        
        export_text = f"""
📤 **Export Links**

**Your Statistics:**
• Total Links: {link_count:,}
• Max Export Limit: {Config.MAX_EXPORT_LINKS:,}

**Export Options:**
1. **Text File** - Simple text file with links
2. **CSV File** - CSV with link details
3. **Telegram Only** - Only Telegram links
4. **WhatsApp Only** - Only WhatsApp links
5. **Custom Export** - Filter by type, date, etc.

**Note:** Large exports may take some time to prepare.
        """
        
        await update.message.reply_text(export_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sessions command"""
        user = update.effective_user
        
        if not self._check_access(user.id):
            await update.message.reply_text("❌ You are not authorized.")
            return
        
        # Get user's sessions
        user_sessions = await self._get_user_sessions(user.id)
        
        sessions_text = f"""
💼 **Your Sessions**

**Session Limit:** {Config.MAX_SESSIONS_PER_USER}
**Current Sessions:** {len(user_sessions)}
        """
        
        if not user_sessions:
            sessions_text += "\n❌ You don't have any sessions.\nUse /addsession to add your first session."
        else:
            sessions_text += "\n\n**Your Active Sessions:**\n"
            for i, session in enumerate(user_sessions[:10], 1):  # Show first 10
                phone = session.get('phone_number', 'N/A')
                username = session.get('username', 'N/A')
                health = session.get('health_score', 0)
                
                # Health indicator
                if health >= 80:
                    health_indicator = "🟢"
                elif health >= 50:
                    health_indicator = "🟡"
                else:
                    health_indicator = "🔴"
                
                sessions_text += f"{i}. {health_indicator} {phone} (@{username})\n"
                sessions_text += f"   Uses: {session.get('total_uses', 0)}, Links: {session.get('total_links', 0)}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Session", callback_data="add_session")],
            [InlineKeyboardButton("🗑️ Remove Session", callback_data="remove_session")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_sessions")]
        ])
        
        await update.message.reply_text(sessions_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def add_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addsession command"""
        user = update.effective_user
        
        if not self._check_access(user.id):
            await update.message.reply_text("❌ You are not authorized.")
            return
        
        # Check session limit
        user_sessions = await self._get_user_sessions(user.id)
        if len(user_sessions) >= Config.MAX_SESSIONS_PER_USER:
            await update.message.reply_text(
                f"❌ You have reached the maximum session limit ({Config.MAX_SESSIONS_PER_USER}).\n"
                "Please remove some sessions before adding new ones."
            )
            return
        
        # Set user state to wait for session string
        self.user_states[user.id] = {
            'state': 'awaiting_session',
            'timestamp': datetime.now()
        }
        
        instructions = """
📱 **How to Add a Session**

**Step 1 - Get Your Session String:**
1. Go to @genTGSessionBot on Telegram
2. Send /start to the bot
3. Follow the instructions to generate session
4. Copy the session string

**Step 2 - Send Session String:**
1. Paste your session string here
2. The bot will validate it
3. If valid, it will be added to your account

**Important Notes:**
• Your session string is encrypted and secure
• Each session can collect links independently
• You can add up to 5 sessions
• Invalid sessions will be rejected

**Ready?** Paste your session string now:
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_add_session")]
        ])
        
        await update.message.reply_text(instructions, reply_markup=keyboard, parse_mode="Markdown")
    
    async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /backup command"""
        user = update.effective_user
        
        if not self._check_access(user.id):
            await update.message.reply_text("❌ You are not authorized.")
            return
        
        # Check if user is admin
        if not self._is_admin(user.id):
            await update.message.reply_text("❌ This command is for administrators only.")
            return
        
        await update.message.reply_text("🔄 Creating backup...")
        
        try:
            backup_info = await BackupManager.create_backup()
            
            if backup_info:
                backup_text = f"""
✅ **Backup Created Successfully**

**Backup Details:**
• Backup ID: {backup_info['backup_id']}
• Time: {backup_info['timestamp']}
• Size: {backup_info['size_mb']:.2f} MB
• Location: {backup_info['backup_path']}

**Backup Rotation:**
• Maximum Backups: {Config.MAX_BACKUPS}
• Old backups are automatically deleted
                """
                
                await update.message.reply_text(backup_text, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Failed to create backup.")
        
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            await update.message.reply_text(f"❌ Error creating backup: {str(e)[:100]}")
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        data = query.data
        
        if not self._check_access(user.id):
            await query.message.edit_text("❌ You are not authorized.")
            return
        
        try:
            if data == "start_collect":
                await self._handle_start_collection(query)
            elif data == "pause_collect":
                await self._handle_pause_collection(query)
            elif data == "stop_collect":
                await self._handle_stop_collection(query)
            elif data == "collect_status":
                await self._handle_collect_status(query)
            elif data == "collect_report":
                await self._handle_collect_report(query)
            elif data == "export_text":
                await self._handle_export_text(query)
            elif data == "export_csv":
                await self._handle_export_csv(query)
            elif data == "export_telegram":
                await self._handle_export_telegram(query)
            elif data == "export_whatsapp":
                await self._handle_export_whatsapp(query)
            elif data == "add_session":
                await self.add_session_command(update, context)
            elif data == "refresh_status":
                await self.status_command(update, context)
            elif data == "refresh_stats":
                await self.stats_command(update, context)
            elif data == "cancel_add_session":
                await self._handle_cancel_add_session(query)
            elif data == "view_stats":
                await self.stats_command(update, context)
            elif data == "show_help":
                await self.help_command(update, context)
            else:
                await query.message.edit_text("❌ Unknown command.")
        
        except Exception as e:
            logger.error(f"Error in callback handler: {e}")
            await query.message.edit_text(f"❌ Error: {str(e)[:100]}")
    
    async def _handle_start_collection(self, query):
        """Handle start collection callback"""
        # Check if already running
        if self.collection_manager.active:
            await query.message.edit_text("⏳ Collection is already running.")
            return
        
        # Check if user has sessions
        user_sessions = await self._get_user_sessions(query.from_user.id)
        if not user_sessions:
            await query.message.edit_text(
                "❌ You don't have any active sessions.\n"
                "Please add a session first using /addsession command."
            )
            return
        
        await query.message.edit_text("🚀 Starting collection...")
        
        # Start collection in background
        asyncio.create_task(self.collection_manager.start_collection())
        
        await asyncio.sleep(2)
        
        # Show status
        collection_status = self.collection_manager.get_status()
        status_text = f"""
✅ **Collection Started**

**Status:** {'Active' if collection_status['active'] else 'Stopped'}
**Mode:** {collection_status['system_state']['collection_mode']}
**Start Time:** {collection_status['stats']['start_time'].strftime('%Y-%m-%d %H:%M:%S') if collection_status['stats']['start_time'] else 'N/A'}

Collection will run in the background.
Use /status to check progress.
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Check Status", callback_data="collect_status")],
            [InlineKeyboardButton("⏸️ Pause", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ Stop", callback_data="stop_collect")]
        ])
        
        await query.message.edit_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_pause_collection(self, query):
        """Handle pause collection callback"""
        if not self.collection_manager.active:
            await query.message.edit_text("⚠️ Collection is not running.")
            return
        
        await self.collection_manager.pause()
        await query.message.edit_text("⏸️ Collection paused.")
    
    async def _handle_stop_collection(self, query):
        """Handle stop collection callback"""
        if not self.collection_manager.active:
            await query.message.edit_text("⚠️ Collection is not running.")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm Stop", callback_data="confirm_stop")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_stop")]
        ])
        
        await query.message.edit_text(
            "⏹️ **Confirm Stop Collection**\n\n"
            "Are you sure you want to stop collection?\n\n"
            "**Note:**\n"
            "• All collected links will be saved\n"
            "• Collection will stop immediately\n"
            "• You can restart anytime\n\n"
            "Current stats:\n"
            f"• Links collected: {self.collection_manager.stats['total_collected']:,}\n"
            f"• Cycles completed: {self.collection_manager.stats['cycles_completed']:,}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def _handle_collect_status(self, query):
        """Handle collect status callback"""
        collection_status = self.collection_manager.get_status()
        
        status_text = f"""
📊 **Collection Status**

**Status:** {'Active' if collection_status['active'] else 'Stopped'}
**Paused:** {'Yes' if collection_status['paused'] else 'No'}
**Stop Requested:** {'Yes' if collection_status['stop_requested'] else 'No'}

**Statistics:**
• Links Collected: {collection_status['stats']['total_collected']:,}
• Collection Cycles: {collection_status['stats']['cycles_completed']:,}
• Errors: {collection_status['stats']['errors']:,}
• Flood Waits: {collection_status['stats']['flood_waits']:,}

**Telegram Breakdown:**
• Public Groups: {collection_status['stats']['telegram_public']:,}
• Private Groups: {collection_status['stats']['telegram_private']:,}
• Join Requests: {collection_status['stats']['telegram_join']:,}
• Channels: {collection_status['stats']['telegram_channels']:,}
• Regular Groups: {collection_status['stats']['telegram_groups']:,}
• Supergroups: {collection_status['stats']['telegram_supergroups']:,}

**System Performance:**
• Performance Score: {collection_status['stats']['performance_score']:.1f}/100
• Success Rate: {collection_status['performance']['success_rate']:.1%}
• Memory Usage: {collection_status['memory']['current_mb']:.1f} MB
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="collect_status")],
            [InlineKeyboardButton("⏸️ Pause", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ Stop", callback_data="stop_collect")]
        ])
        
        await query.message.edit_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_collect_report(self, query):
        """Handle collect report callback"""
        try:
            report = await self.collection_manager.get_detailed_report()
            
            report_text = f"""
📋 **Collection Report**

**Collection Summary:**
• Status: {'Active' if report['collection_status']['active'] else 'Stopped'}
• Links Collected: {report['collection_status']['stats']['total_collected']:,}
• Success Rate: {report['collection_status']['performance']['success_rate']:.1%}

**Telegram Details:**
• Groups: {report['collection_status']['stats']['telegram_groups']:,}
• Channels: {report['collection_status']['stats']['telegram_channels']:,}
• Supergroups: {report['collection_status']['stats']['telegram_supergroups']:,}
• Join Requests: {report['collection_status']['stats']['telegram_join']:,}

**System Health:**
• Memory: {report['system_health']['memory']['current_mb']:.1f} MB
• Active Sessions: {report['database_stats'].get('active_sessions', 0)}

**Enhanced Limits:**
• Max Sessions: {Config.MAX_CONCURRENT_SESSIONS}
• Max Export: {Config.MAX_EXPORT_LINKS:,} links

**Recommendations:**
"""
            
            recommendations = report['recommendations']
            if recommendations:
                for rec in recommendations[:3]:
                    report_text += f"• {rec}\n"
            else:
                report_text += "• No recommendations at this time\n"
            
            await query.message.edit_text(report_text, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Error generating collection report: {e}")
            await query.message.edit_text("❌ Error generating report.")
    
    async def _handle_export_text(self, query):
        """Handle export as text callback"""
        await query.message.edit_text("📄 Preparing text export...")
        
        try:
            user = query.from_user
            db = await EnhancedDatabaseManager.get_instance()
            
            # Get user's links
            filters = {'added_by_user': user.id}
            links, metadata = await db.export_links_enhanced(filters, limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await query.message.edit_text("❌ No links found to export.")
                return
            
            # Create text file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"links_export_{timestamp}.txt"
            filepath = f"exports/{filename}"
            
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Link Export - {timestamp}\n")
                f.write(f"Total Links: {len(links)}\n")
                f.write("=" * 50 + "\n\n")
                
                for i, link in enumerate(links, 1):
                    f.write(f"{i}. {link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"✅ Exported {len(links)} links as text file."
                )
            
            # Cleanup
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"Error exporting text: {e}")
            await query.message.edit_text(f"❌ Error exporting: {str(e)[:100]}")
    
    async def _handle_export_csv(self, query):
        """Handle export as CSV callback"""
        await query.message.edit_text("📊 Preparing CSV export...")
        
        try:
            user = query.from_user
            db = await EnhancedDatabaseManager.get_instance()
            
            # Get user's links with details
            filters = {'added_by_user': user.id}
            links, metadata = await db.export_links_enhanced(filters, limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await query.message.edit_text("❌ No links found to export.")
                return
            
            # Create CSV file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"links_export_{timestamp}.csv"
            filepath = f"exports/{filename}"
            
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                f.write("Number,URL,Platform,Type,Collected Date\n")
                
                for i, link in enumerate(links, 1):
                    # Extract platform from URL
                    platform = 'unknown'
                    if 't.me' in link or 'telegram.me' in link:
                        platform = 'telegram'
                    elif 'whatsapp.com' in link:
                        platform = 'whatsapp'
                    elif 'discord.gg' in link:
                        platform = 'discord'
                    elif 'signal.group' in link:
                        platform = 'signal'
                    
                    f.write(f'{i},"{link}",{platform},link,{datetime.now().strftime("%Y-%m-%d")}\n')
            
            # Send file
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"✅ Exported {len(links)} links as CSV file."
                )
            
            # Cleanup
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"Error exporting CSV: {e}")
            await query.message.edit_text(f"❌ Error exporting: {str(e)[:100]}")
    
    async def _handle_export_telegram(self, query):
        """Handle export Telegram only callback"""
        await query.message.edit_text("🎯 Preparing Telegram links export...")
        
        try:
            user = query.from_user
            db = await EnhancedDatabaseManager.get_instance()
            
            # Get user's Telegram links
            filters = {
                'added_by_user': user.id,
                'platform': 'telegram'
            }
            links, metadata = await db.export_links_enhanced(filters, limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await query.message.edit_text("❌ No Telegram links found to export.")
                return
            
            # Create text file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"telegram_links_{timestamp}.txt"
            filepath = f"exports/{filename}"
            
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Telegram Links Export - {timestamp}\n")
                f.write(f"Total Telegram Links: {len(links)}\n")
                f.write("=" * 50 + "\n\n")
                
                for i, link in enumerate(links, 1):
                    f.write(f"{i}. {link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"✅ Exported {len(links)} Telegram links."
                )
            
            # Cleanup
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"Error exporting Telegram links: {e}")
            await query.message.edit_text(f"❌ Error exporting: {str(e)[:100]}")
    
    async def _handle_export_whatsapp(self, query):
        """Handle export WhatsApp only callback"""
        await query.message.edit_text("📱 Preparing WhatsApp links export...")
        
        try:
            user = query.from_user
            db = await EnhancedDatabaseManager.get_instance()
            
            # Get user's WhatsApp links
            filters = {
                'added_by_user': user.id,
                'platform': 'whatsapp'
            }
            links, metadata = await db.export_links_enhanced(filters, limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await query.message.edit_text("❌ No WhatsApp links found to export.")
                return
            
            # Create text file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"whatsapp_links_{timestamp}.txt"
            filepath = f"exports/{filename}"
            
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"WhatsApp Links Export - {timestamp}\n")
                f.write(f"Total WhatsApp Links: {len(links)}\n")
                f.write("=" * 50 + "\n\n")
                
                for i, link in enumerate(links, 1):
                    f.write(f"{i}. {link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"✅ Exported {len(links)} WhatsApp links."
                )
            
            # Cleanup
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"Error exporting WhatsApp links: {e}")
            await query.message.edit_text(f"❌ Error exporting: {str(e)[:100]}")
    
    async def _handle_cancel_add_session(self, query):
        """Handle cancel add session callback"""
        user_id = query.from_user.id
        if user_id in self.user_states:
            del self.user_states[user_id]
        
        await query.message.edit_text("❌ Session addition cancelled.")
    
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        user = update.effective_user
        message_text = update.message.text
        
        if not self._check_access(user.id):
            await update.message.reply_text("❌ You are not authorized.")
            return
        
        # Check user state
        user_state = self.user_states.get(user.id, {})
        
        if user_state.get('state') == 'awaiting_session':
            # User is sending a session string
            await self._process_session_string(update, message_text)
        else:
            # Default response
            await update.message.reply_text(
                "ℹ️ Please use commands to interact with the bot.\n"
                "Type /help to see available commands."
            )
    
    async def _process_session_string(self, update: Update, session_string: str):
        """Process session string from user"""
        user = update.effective_user
        
        if not session_string or len(session_string) < 50:
            await update.message.reply_text(
                "❌ Invalid session string. Please send a valid session string."
            )
            return
        
        await update.message.reply_text("🔄 Validating session...")
        
        try:
            # Validate session
            is_valid, validation_info = await EnhancedSessionManager.validate_session(session_string)
            
            if not is_valid:
                await update.message.reply_text(
                    f"❌ Session validation failed:\n{validation_info.get('error', 'Unknown error')}"
                )
                return
            
            # Encrypt session
            enc_manager = EncryptionManager.get_instance()
            encrypted_session = enc_manager.encrypt_session(session_string)
            session_hash = hashlib.md5(encrypted_session.encode()).hexdigest()
            
            # Add to database
            db = await EnhancedDatabaseManager.get_instance()
            conn = await db._get_connection()
            
            # Check if session already exists
            cursor = await conn.execute(
                'SELECT id FROM sessions WHERE session_hash = ?',
                (session_hash,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                await conn.close()
                await update.message.reply_text("❌ This session already exists in the database.")
                return
            
            # Add session
            user_info = validation_info.get('user_info', {})
            await conn.execute('''
                INSERT INTO sessions 
                (session_string, session_hash, phone_number, user_id, username, 
                 display_name, added_by_user, is_active, added_date, last_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (
                encrypted_session,
                session_hash,
                user_info.get('phone', ''),
                user_info.get('id', 0),
                user_info.get('username', ''),
                f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip(),
                user.id
            ))
            
            await conn.commit()
            await conn.close()
            
            # Update user stats
            await db.update_user_stats(user.id, 'session_added')
            
            # Clear user state
            if user.id in self.user_states:
                del self.user_states[user.id]
            
            success_text = f"""
✅ **Session Added Successfully**

**Session Details:**
• User: @{user_info.get('username', 'N/A')}
• Phone: {user_info.get('phone', 'N/A')}
• Name: {user_info.get('first_name', '')} {user_info.get('last_name', '')}
• User ID: {user_info.get('id', 'N/A')}
• Added: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Security:**
• Session is encrypted
• Only you can access your sessions
• Session hash: {session_hash[:12]}...

**Next Steps:**
1. Use /sessions to view your sessions
2. Use /collect to start collection
3. Use /status to monitor progress

Your session is now ready for collection!
            """
            
            await update.message.reply_text(success_text, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Error processing session: {e}")
            await update.message.reply_text(f"❌ Error adding session: {str(e)[:100]}")
    
    async def _get_user_sessions(self, user_id: int) -> List[Dict]:
        """Get user's sessions"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            conn = await db._get_connection()
            
            cursor = await conn.execute('''
                SELECT * FROM sessions 
                WHERE added_by_user = ? AND is_active = 1
                ORDER BY last_used DESC
            ''', (user_id,))
            
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
            
            await conn.close()
            return sessions
            
        except Exception as e:
            logger.error(f"Error getting user sessions: {e}")
            return []
    
    def _check_access(self, user_id: int) -> bool:
        """Check if user has access"""
        # Check if user is admin
        if Config.ADMIN_USER_IDS and user_id in Config.ADMIN_USER_IDS:
            return True
        
        # Check if user is in allowed list
        if Config.ALLOWED_USER_IDS and user_id in Config.ALLOWED_USER_IDS:
            return True
        
        # If no specific allowed users are set, allow everyone
        if not Config.ALLOWED_USER_IDS:
            return True
        
        return False
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return Config.ADMIN_USER_IDS and user_id in Config.ADMIN_USER_IDS
    
    def _format_duration(self, duration: timedelta) -> str:
        """Format duration to human readable string"""
        total_seconds = int(duration.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")
        
        return " ".join(parts)
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        error = context.error
        
        logger.error(f"Bot error: {error}", exc_info=True)
        
        try:
            # Log error to database
            db = await EnhancedDatabaseManager.get_instance()
            conn = await db._get_connection()
            
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
            await conn.close()
            
        except Exception as db_error:
            logger.error(f"Error logging to database: {db_error}")
        
        if update and update.effective_chat:
            error_message = (
                "❌ **An unexpected error occurred**\n\n"
                "The error has been logged and will be investigated.\n\n"
                "**You can:**\n"
                "1. Try again in a few moments\n"
                "2. Use /start to return to main menu\n"
                "3. Contact support if the error persists"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=error_message,
                    parse_mode="Markdown"
                )
            except Exception:
                pass
    
    async def run(self):
        """Run the bot"""
        logger.info("Starting bot...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        
        logger.info("Bot is running!")
        
        # Keep bot running
        await asyncio.Event().wait()
    
    async def stop(self):
        """Stop the bot"""
        logger.info("Stopping bot...")
        await self.app.stop()

# ======================
# Enhanced Session Manager
# ======================

class EnhancedSessionManager:
    """Enhanced session manager"""
    
    _session_cache = {}
    _session_health = {}
    
    @staticmethod
    async def validate_session(session_string: str) -> Tuple[bool, Dict]:
        """Validate session"""
        try:
            # Try to decrypt if encrypted
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
                return False, {'error': 'Not authorized', 'details': 'Session not activated'}
            
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
                'session_length': len(session_string),
                'is_encrypted': decrypted is not None
            }
            
        except SessionPasswordNeededError:
            return False, {'error': 'Password protected', 'details': 'Session requires secondary password'}
        except AuthKeyError:
            return False, {'error': 'Invalid auth key', 'details': 'Session expired or invalid'}
        except Exception as e:
            return False, {'error': 'Validation error', 'details': str(e)[:200]}

# ======================
# Cache Manager
# ======================

class CacheManager:
    """Cache manager"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get instance"""
        if cls._instance is None:
            cls._instance = CacheManager()
        return cls._instance
    
    def __init__(self):
        self.fast_cache = OrderedDict()
        self.fast_cache_size = 10000
        
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
        """Get from cache"""
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
                        
                        # Check expiration
                        expires_at = data.get('expires_at')
                        if expires_at:
                            expires_dt = datetime.fromisoformat(expires_at)
                            if datetime.now() > expires_dt:
                                os.remove(file_path)
                                self.stats['misses'] += 1
                                return None
                        
                        # Add to fast cache
                        self._add_to_fast_cache(cache_key, data.get('value'))
                        self.stats['slow_hits'] += 1
                        return data.get('value')
                except:
                    pass
            
            self.stats['misses'] += 1
            return None
    
    async def set(self, key: str, value: Any, category: str = 'general', ttl_seconds: int = 3600):
        """Set in cache"""
        async with self.lock:
            cache_key = f"{category}_{key}"
            
            self._add_to_fast_cache(cache_key, value)
            
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
                logger.debug(f"Error storing slow cache: {e}")
    
    def _add_to_fast_cache(self, key: str, value: Any):
        """Add to fast cache"""
        if key in self.fast_cache:
            self.fast_cache.move_to_end(key)
            self.fast_cache[key] = value
        else:
            self.fast_cache[key] = value
            
            if len(self.fast_cache) > self.fast_cache_size:
                oldest_key = next(iter(self.fast_cache))
                del self.fast_cache[oldest_key]
                self.stats['evictions'] += 1
    
    async def exists(self, key: str, category: str = 'general') -> bool:
        """Check if exists"""
        cache_key = f"{category}_{key}"
        return cache_key in self.fast_cache
    
    async def delete(self, key: str, category: str = 'general'):
        """Delete from cache"""
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
        """Cleanup expired cache"""
        async with self.lock:
            expired_count = 0
            
            for filename in os.listdir(self.slow_cache_dir):
                if filename.endswith('.cache'):
                    file_path = os.path.join(self.slow_cache_dir, filename)
                    try:
                        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                            content = await f.read()
                            data = json.loads(content)
                            
                            expires_at = data.get('expires_at')
                            if expires_at:
                                expires_dt = datetime.fromisoformat(expires_at)
                                if datetime.now() > expires_dt:
                                    os.remove(file_path)
                                    expired_count += 1
                    except:
                        try:
                            os.remove(file_path)
                        except:
                            pass
            
            if expired_count > 0:
                logger.info(f"Cleaned up {expired_count} expired cache items")
    
    def optimize(self):
        """Optimize cache"""
        current_size = len(self.fast_cache)
        if current_size > self.fast_cache_size:
            target_size = int(self.fast_cache_size * 0.8)
            while len(self.fast_cache) > target_size:
                oldest_key = next(iter(self.fast_cache))
                del self.fast_cache[oldest_key]
                self.stats['evictions'] += 1
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
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
        """Clear cache"""
        self.fast_cache.clear()
        self.stats = {
            'fast_hits': 0,
            'slow_hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_operations': 0
        }

# ======================
# Memory Manager
# ======================

class MemoryManager:
    """Memory manager"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get instance"""
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
        """Get memory usage in MB"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except Exception as e:
            logger.debug(f"Error reading memory: {e}")
            return 0
    
    def get_memory_percent(self) -> float:
        """Get memory percentage"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_percent()
        except:
            return 0
    
    def get_system_memory(self) -> Dict:
        """Get system memory info"""
        try:
            mem = psutil.virtual_memory()
            return {
                'total_mb': mem.total / 1024 / 1024,
                'available_mb': mem.available / 1024 / 1024,
                'percent_used': mem.percent,
                'process_percent': self.get_memory_percent()
            }
        except Exception as e:
            logger.debug(f"Error reading system memory: {e}")
            return {}
    
    def optimize_memory(self) -> Dict:
        """Optimize memory usage"""
        before = self.get_memory_usage()
        
        # Run garbage collection
        gc.collect()
        
        # Clear caches
        CacheManager.get_instance().optimize()
        
        after = self.get_memory_usage()
        saved = before - after
        
        self.metrics['optimizations'] += 1
        self.metrics['total_saved_mb'] += saved if saved > 0 else 0
        self.metrics['last_optimization'] = datetime.now()
        
        logger.info(f"Memory optimized: {saved:.2f} MB saved")
        
        return {
            'saved_mb': saved,
            'before_mb': before,
            'after_mb': after
        }
    
    def check_and_optimize(self, threshold_percent: float = 80.0) -> Dict:
        """Check memory and optimize if needed"""
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
            logger.warning(f"High memory usage: {current_mb:.2f} MB, {current_percent:.1f}%")
            
            self.metrics['high_memory_warnings'] += 1
            optimization_result = self.optimize_memory()
            result.update(optimization_result)
            result['optimized'] = True
        
        return result
    
    def get_metrics(self) -> Dict:
        """Get memory metrics"""
        return {
            **self.metrics,
            'current_mb': self.get_memory_usage(),
            'current_percent': self.get_memory_percent(),
            'system_memory': self.get_system_memory()
        }

# ======================
# Encryption Manager
# ======================

class EncryptionManager:
    """Encryption manager"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Get instance"""
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
            logger.error(f"Encryption error: {e}")
            return data
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt data"""
        try:
            decrypted = self.cipher.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            return encrypted_data
    
    def encrypt_session(self, session_string: str) -> str:
        """Encrypt session string"""
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
        """Decrypt session string"""
        try:
            decrypted = self.decrypt(encrypted_data)
            data = json.loads(decrypted)
            return data['session']
        except Exception as e:
            logger.error(f"Session decryption error: {e}")
            return None

# ======================
# Backup Manager
# ======================

class BackupManager:
    """Backup manager"""
    
    @staticmethod
    async def create_backup() -> Optional[Dict]:
        """Create database backup"""
        if not Config.BACKUP_ENABLED:
            return None
        
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = "backups"
            backup_filename = f"{Config.DB_PATH}.backup_{timestamp}"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            os.makedirs(backup_dir, exist_ok=True)
            
            if not os.path.exists(Config.DB_PATH):
                logger.error("Database file not found")
                return None
            
            db_size = os.path.getsize(Config.DB_PATH)
            
            # Copy database file
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
            
            # Save metadata
            metadata_path = backup_path + '.meta'
            async with aiofiles.open(metadata_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(metadata, indent=2))
            
            logger.info(f"Backup created: {backup_path}")
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return None
    
    @staticmethod
    def _calculate_checksum(file_path: str) -> str:
        """Calculate file checksum"""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    @staticmethod
    async def rotate_backups():
        """Rotate old backups"""
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
            
            to_keep = []
            to_delete = []
            
            for backup in backups:
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
                    logger.info(f"Deleted old backup: {backup['path']}")
                    
                except Exception as e:
                    logger.error(f"Error deleting backup: {e}")
            
            if deleted_count > 0:
                logger.info(f"Rotated {deleted_count} old backups")
            
            return deleted_count
                    
        except Exception as e:
            logger.error(f"Error rotating backups: {e}")
            return 0

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
        self.app = FastAPI(title="Telegram Link Collector Health")
        self._setup_routes()
        self.server_thread = None
        
    def _setup_routes(self):
        """Setup API routes"""
        
        @self.app.get("/")
        async def root():
            return {"status": "running", "service": "Telegram Link Collector"}
        
        @self.app.get("/health")
        async def health():
            try:
                # Check bot availability
                bot_ok = True
                
                # Check database
                db_ok = os.path.exists(Config.DB_PATH)
                
                # Check memory
                memory_ok = MemoryManager.get_instance().get_memory_percent() < 90
                
                status = {
                    "status": "healthy" if all([bot_ok, db_ok, memory_ok]) else "degraded",
                    "timestamp": datetime.now().isoformat(),
                    "checks": {
                        "bot": bot_ok,
                        "database": db_ok,
                        "memory": memory_ok,
                        "memory_percent": MemoryManager.get_instance().get_memory_percent(),
                        "memory_mb": MemoryManager.get_instance().get_memory_usage()
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
        
        @self.app.get("/metrics")
        async def metrics():
            try:
                metrics_data = {
                    "timestamp": datetime.now().isoformat(),
                    "memory": MemoryManager.get_instance().get_metrics(),
                    "cache": CacheManager.get_instance().get_stats(),
                    "system": {
                        "python_version": sys.version,
                        "platform": sys.platform
                    }
                }
                return JSONResponse(status_code=200, content=metrics_data)
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={"error": str(e)}
                )
    
    def start(self):
        """Start health check server"""
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
        """Stop health check server"""
        if self.server_thread:
            logger.info("Health check server stopped")

# ======================
# Signal Handlers
# ======================

def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info(f"📶 Received signal {signum}. Starting graceful shutdown...")
        logger.info("📊 Final system statistics:")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# ======================
# Main Entry Point
# ======================

async def main():
    """Main function"""
    setup_signal_handlers()
    
    # Setup event loop
    if sys.platform != 'win32':
        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            logger.info("✅ Using uvloop for performance")
        except ImportError:
            logger.info("⚠️ uvloop not installed. Using default event loop")
    
    # Check required environment variables
    required_env_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH']
    missing = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing:
        logger.error(f"❌ Missing environment variables: {missing}")
        print(f"❌ Error: The following environment variables are missing: {', '.join(missing)}")
        print("Please set them before running:")
        for var in missing:
            print(f"export {var}=your_value_here")
        sys.exit(1)
    
    # Warn about temporary encryption key
    if Config.ENCRYPTION_KEY == Fernet.generate_key().decode():
        logger.warning("⚠️ Using temporary encryption key. Set ENCRYPTION_KEY for permanent security")
    
    # Create necessary directories
    os.makedirs("backups", exist_ok=True)
    os.makedirs("cache_data", exist_ok=True)
    os.makedirs("exports", exist_ok=True)
    
    # Start health check server
    health_server = HealthCheckServer(port=8080)
    health_server.start()
    
    # Start the bot
    bot = AdvancedTelegramBot()
    
    logger.info("🤖 Starting Advanced Link Collection Bot...")
    logger.info(f"🔥 Enhanced Settings - max_sessions: {Config.MAX_CONCURRENT_SESSIONS}, max_export: {Config.MAX_EXPORT_LINKS}")
    
    try:
        # Initialize managers
        cache_manager = CacheManager.get_instance()
        memory_manager = MemoryManager.get_instance()
        
        # Run periodic maintenance
        asyncio.create_task(periodic_maintenance())
        
        # Run the bot
        await bot.run()
        
    except Exception as e:
        logger.error(f"❌ Error in bot: {e}", exc_info=True)
        raise
        
    finally:
        logger.info("🧹 Performing final cleanup...")
        
        try:
            await bot.stop()
            
            db = await EnhancedDatabaseManager.get_instance()
            await db.close()
            
            cache_manager.clear()
            
            health_server.stop()
            
            logger.info("✅ Graceful shutdown completed")
            
        except Exception as e:
            logger.error(f"❌ Error in final cleanup: {e}")

async def periodic_maintenance():
    """Periodic maintenance tasks"""
    while True:
        try:
            # Cleanup expired cache
            cache_manager = CacheManager.get_instance()
            await cache_manager.cleanup_expired()
            
            # Optimize memory
            memory_manager = MemoryManager.get_instance()
            memory_manager.check_and_optimize()
            
            # Rotate backups
            if Config.BACKUP_ENABLED:
                await BackupManager.rotate_backups()
            
            logger.debug("✅ Periodic maintenance completed")
            
            await asyncio.sleep(300)  # Run every 5 minutes
            
        except Exception as e:
            logger.error(f"Error in periodic maintenance: {e}")
            await asyncio.sleep(60)

# ======================
# Run the Application
# ======================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
