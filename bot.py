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

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
import threading

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
    MAX_DIALOGS_PER_SESSION = 100
    MAX_MESSAGES_PER_SEARCH = 20
    MAX_SEARCH_TERMS = 8
    MAX_LINKS_PER_CYCLE = 500
    MAX_BATCH_SIZE = 100
    
    # Database
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10
    DB_POOL_SIZE = 5
    
    # WhatsApp collection
    WHATSAPP_DAYS_BACK = 60
    
    # Link verification
    MIN_GROUP_MEMBERS = 5
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
    
    # Collection settings
    COLLECT_ONLY_GROUPS = True
    MIN_MEMBERS_FOR_GROUP = 5
    COLLECT_ACTIVE_LINKS_ONLY = True
    ENABLE_DEEP_COLLECTION = True
    MAX_DEEP_MESSAGES = 50
    
    # Enhanced collection settings
    SEARCH_KEYWORDS = [
        'whatsapp', 'telegram', 'دردشة', 'مجموعة', 'قناة',
        'انضمام', 'رابط', 'invite', 'link', 'group',
        'قنوات', 'مجموعات', 'تليجرام', 'واتساب',
        'discord', 'signal', 'سيرفر', 'سرفر', 'ديسكورد'
    ]
    
    CHECK_PINNED_MESSAGES = True
    CHECK_COMMENTS = True
    MIN_LINK_LENGTH = 15
    MAX_LINKS_PER_GROUP = 200

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
        
        # Remove spaces and unwanted characters
        url = url.strip()
        url = re.sub(r'^["\'\s*]+|["\'\s*]+$', '', url)
        url = re.sub(r'[,\s]+$', '', url)
        
        # Extract link from text
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
            
            # Rebuild link
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
            'is_active': True,
            'is_join_link': False,
            'is_subscription': False
        }
        
        path = parsed.path.strip('/')
        if not path:
            return result
        
        segments = path.split('/')
        result['path_segments'] = segments
        
        # Detect join links (joinchat)
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
            result['is_join_link'] = True
            
            if 'channel' in url.lower() or 'c/' in url.lower():
                result['is_channel'] = True
                result['is_group'] = False
                result['is_subscription'] = True
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
                result['is_subscription'] = True
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
                result['is_join_link'] = True
            else:
                if any(keyword in username for keyword in ['channel', 'official', 'news', 'tv', 'media']):
                    result['is_channel'] = True
                    result['is_subscription'] = True
                else:
                    result['is_group'] = True
                result['is_public'] = True
                result['is_valid'] = True
                result['is_supergroup'] = True
        
        # Detect groups with longer paths
        elif len(segments) >= 2:
            if segments[0].lower() in ['c', 'channel', 's']:
                result['is_channel'] = True
                result['is_broadcast'] = True
                result['is_valid'] = True
                result['is_subscription'] = True
            elif segments[0].lower() == 'joinchat':
                result['is_join_request'] = True
                result['is_private'] = True
                result['invite_hash'] = segments[1] if len(segments) > 1 else ''
                result['is_group'] = True
                result['is_valid'] = True
                result['is_join_link'] = True
            else:
                if any(keyword in segments[0].lower() for keyword in ['channel', 'official']):
                    result['is_channel'] = True
                    result['is_subscription'] = True
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
        """Initialize database asynchronously"""
        if self._initialized:
            return
        
        self.db_path = Config.DB_PATH
        
        # Create folder if it doesn't exist
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        
        # Create database connection
        self.conn = await aiosqlite.connect(self.db_path)
        
        # Initialize tables
        await self._create_tables()
        
        self._initialized = True
        logger.info(f"✅ Database initialized: {self.db_path}")
    
    async def _create_tables(self):
        """Create database tables"""
        # Sessions table
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
                health_score INTEGER DEFAULT 100,
                notes TEXT,
                metadata TEXT
            )
        ''')
        
        # Links table
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
                is_subscription BOOLEAN DEFAULT 0,
                is_valid_group BOOLEAN DEFAULT 0,
                last_validated TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE SET NULL
            )
        ''')
        
        # Users table
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
        
        # Backups table
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_id TEXT UNIQUE NOT NULL,
                timestamp TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_path TEXT,
                size_bytes INTEGER,
                checksum TEXT,
                status TEXT DEFAULT 'success',
                metadata TEXT
            )
        ''')
        
        await self.conn.commit()
        
        # Create indexes
        await self._create_indexes()
    
    async def _create_indexes(self):
        """Create database indexes"""
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_links_url_hash ON links(url_hash)',
            'CREATE INDEX IF NOT EXISTS idx_links_platform ON links(platform)',
            'CREATE INDEX IF NOT EXISTS idx_links_collected_date ON links(collected_date)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_group ON links(is_group)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_subscription ON links(is_subscription)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_valid_group ON links(is_valid_group)',
            'CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)',
            'CREATE INDEX IF NOT EXISTS idx_users_last_active ON bot_users(last_active)'
        ]
        
        for index_sql in indexes:
            try:
                await self.conn.execute(index_sql)
            except Exception as e:
                logger.error(f"Error creating index: {e}")
        
        await self.conn.commit()
    
    async def add_link(self, link_info: Dict) -> Tuple[bool, str, Dict]:
        """Add link to database"""
        try:
            url = link_info.get('url', '')
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                return False, "Invalid URL", {}
            
            details = url_info['details']
            
            # Check for duplicates
            cursor = await self.conn.execute(
                'SELECT id FROM links WHERE url_hash = ?',
                (url_info['url_hash'],)
            )
            existing = await cursor.fetchone()
            
            if existing:
                # Update existing link
                await self.conn.execute('''
                    UPDATE links SET 
                    last_checked = CURRENT_TIMESTAMP,
                    check_count = check_count + 1,
                    is_active = ?,
                    members_count = ?,
                    validation_score = ?
                    WHERE id = ?
                ''', (
                    link_info.get('is_active', True),
                    link_info.get('members', 0),
                    link_info.get('validation_score', 0),
                    existing[0]
                ))
                await self.conn.commit()
                return False, "Updated existing link", {'link_id': existing[0]}
            
            # Prepare link data
            cursor = await self.conn.execute('''
                INSERT INTO links 
                (url_hash, url, original_url, platform, link_type, telegram_type, title, 
                 description, members_count, session_id, confidence, 
                 is_active, requires_join, is_verified, validation_score, metadata, 
                 tags, added_by_user, source, is_channel, is_group, is_join_request, 
                 is_supergroup, is_subscription, is_valid_group, last_validated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                url_info['url_hash'],
                url_info['normalized_url'],
                url_info['original_url'],
                url_info['platform'],
                link_info.get('link_type', 'unknown'),
                details.get('telegram_type', ''),
                link_info.get('title', '')[:500],
                link_info.get('description', '')[:1000],
                link_info.get('members', 0),
                link_info.get('session_id'),
                link_info.get('confidence', 'medium'),
                link_info.get('is_active', True),
                details.get('is_join_request', False),
                link_info.get('is_verified', False),
                link_info.get('validation_score', 0),
                json.dumps(link_info.get('metadata', {})),
                json.dumps(link_info.get('tags', [])),
                link_info.get('added_by_user', 0),
                link_info.get('source', 'manual'),
                details.get('is_channel', False),
                details.get('is_group', True),
                details.get('is_join_request', False),
                details.get('is_supergroup', False),
                details.get('is_subscription', False),
                link_info.get('is_valid_group', False),
                link_info.get('last_validated', datetime.now().isoformat())
            ))
            
            link_id = cursor.lastrowid
            
            # Update user stats
            if link_info.get('added_by_user'):
                await self.update_user_stats(link_info['added_by_user'], 'link_added')
            
            # Update session stats
            if link_info.get('session_id'):
                await self.conn.execute(
                    "UPDATE sessions SET total_links = total_links + 1 WHERE id = ?",
                    (link_info['session_id'],)
                )
            
            await self.conn.commit()
            
            return True, "Link added successfully", {
                'link_id': link_id,
                'url_hash': url_info['url_hash']
            }
            
        except Exception as e:
            logger.error(f"Error adding link: {e}")
            return False, f"Add error: {str(e)[:100]}", {}
    
    async def add_session(self, session_data: Dict) -> Tuple[bool, str, Dict]:
        """Add session to database"""
        try:
            session_string = session_data.get('session_string', '')
            if not session_string:
                return False, "Empty session", {}
            
            session_hash = hashlib.md5(session_string.encode()).hexdigest()
            
            # Check for duplicates
            cursor = await self.conn.execute(
                'SELECT id FROM sessions WHERE session_hash = ?',
                (session_hash,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                return False, "Session already exists", {'session_id': existing[0]}
            
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
            
            # Update user stats
            if session_data.get('added_by_user'):
                await self.update_user_stats(session_data['added_by_user'], 'session_added')
            
            await self.conn.commit()
            
            return True, "Session added successfully", {
                'session_id': session_id,
                'session_hash': session_hash
            }
            
        except Exception as e:
            logger.error(f"Error adding session: {e}")
            return False, f"Add error: {str(e)[:100]}", {}
    
    async def update_user_stats(self, user_id: int, action: str, value: int = 1):
        """Update user statistics"""
        try:
            update_query = '''
                UPDATE bot_users 
                SET last_active = CURRENT_TIMESTAMP,
                    request_count = request_count + 1
            '''
            
            if action == 'session_added':
                update_query += ', session_count = session_count + 1'
            elif action == 'link_added':
                update_query += ', link_count = link_count + ?, total_links_added = total_links_added + ?'
            
            update_query += ' WHERE user_id = ?'
            
            if action == 'link_added':
                await self.conn.execute(update_query, (value, value, user_id))
            else:
                await self.conn.execute(update_query, (user_id,))
            
            await self.conn.commit()
            
        except Exception as e:
            logger.debug(f"Error updating user stats: {e}")
    
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
            logger.error(f"Error adding/updating user: {e}")
    
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
            logger.error(f"Error getting user stats: {e}")
            return None
    
    async def get_active_sessions(self, limit: int = 10) -> List[Dict]:
        """Get active sessions"""
        try:
            cursor = await self.conn.execute('''
                SELECT * FROM sessions 
                WHERE is_active = 1 
                ORDER BY last_used ASC
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
            
            return sessions
            
        except Exception as e:
            logger.error(f"Error getting active sessions: {e}")
            return []
    
    async def get_links_count(self) -> int:
        """Get total links count"""
        try:
            cursor = await self.conn.execute('SELECT COUNT(*) FROM links WHERE is_valid_group = 1')
            result = await cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting links count: {e}")
            return 0
    
    async def get_stats_summary(self) -> Dict:
        """Get database statistics summary"""
        try:
            stats = {}
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links")
            stats['total_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_valid_group = 1")
            stats['valid_groups'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_subscription = 1")
            stats['subscriptions'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT platform, COUNT(*) FROM links WHERE is_valid_group = 1 GROUP BY platform")
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_verified = 1")
            stats['verified_links'] = (await cursor.fetchone())[0]
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting stats summary: {e}")
            return {}
    
    async def export_links(self, filters: Dict = None, limit: int = 1000) -> List[str]:
        """Export links"""
        try:
            query = 'SELECT url FROM links WHERE is_valid_group = 1'
            params = []
            
            if filters:
                where_clauses = []
                
                if filters.get('platform'):
                    where_clauses.append("platform = ?")
                    params.append(filters['platform'])
                
                if filters.get('min_members'):
                    where_clauses.append("members_count >= ?")
                    params.append(filters['min_members'])
                
                if where_clauses:
                    query += " AND " + " AND ".join(where_clauses)
            
            query += " ORDER BY collected_date DESC LIMIT ?"
            params.append(limit)
            
            cursor = await self.conn.execute(query, params)
            rows = await cursor.fetchall()
            
            return [row[0] for row in rows]
            
        except Exception as e:
            logger.error(f"Error exporting links: {e}")
            return []
    
    async def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            await self.conn.close()
            self._initialized = False

# ======================
# Session Manager
# ======================

class SessionManager:
    """Manage Telegram sessions"""
    
    @staticmethod
    async def validate_session(session_string: str) -> Tuple[bool, Dict]:
        """Validate Telegram session"""
        try:
            # Clean session string
            session_string = session_string.strip()
            
            # Check session length
            if len(session_string) < 50:
                return False, {'error': 'Session too short', 'details': 'Session should be longer than 50 characters'}
            
            client = TelegramClient(
                StringSession(session_string),
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
                'session_length': len(session_string)
            }
            
        except ValueError as e:
            return False, {'error': 'Invalid session', 'details': 'Session format incorrect'}
        except Exception as e:
            return False, {'error': 'Validation error', 'details': str(e)[:200]}
    
    @staticmethod
    async def create_client(session_string: str) -> Optional[TelegramClient]:
        """Create Telegram client from session string"""
        try:
            # Clean session string
            session_string = session_string.strip()
            
            # Validate session string
            if len(session_string) < 50:
                logger.error(f"Session too short: {len(session_string)} characters")
                return None
            
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH,
                device_model="Link Collector",
                system_version="Linux 6.5",
                app_version="4.16.30",
                timeout=30,
                connection_retries=3
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                logger.error("Session not authorized")
                return None
            
            return client
            
        except ValueError as e:
            logger.error(f"Session format error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creating client: {e}")
            return None

# ======================
# Group Validator
# ======================

class GroupValidator:
    """Validate Telegram groups and channels"""
    
    @staticmethod
    def extract_links_with_keywords(text: str) -> List[str]:
        """Extract links containing specific keywords"""
        if not text:
            return []
        
        links = []
        
        # Keywords to search for
        keywords = [
            'chat.whatsapp.com',
            't.me/+',
            't.me/joinchat',
            't.me/join',
            'telegram.me/+',
            'telegram.me/joinchat',
            'discord.gg',
            'discord.com/invite',
            'signal.group',
            'whatsapp.com/invite'
        ]
        
        # Search for links in text
        url_patterns = [
            r'(https?://[^\s<>"\']+)',
            r'(t\.me/[^\s<>"\']+)',
            r'(telegram\.me/[^\s<>"\']+)',
            r'(telegram\.dog/[^\s<>"\']+)',
        ]
        
        for pattern in url_patterns:
            found_links = re.findall(pattern, text, re.IGNORECASE)
            for link in found_links:
                # Check if link contains keywords
                if any(keyword in link.lower() for keyword in keywords):
                    links.append(link)
                elif 't.me' in link.lower() and '/+' not in link.lower():
                    # Normal Telegram links (not join links)
                    links.append(link)
        
        return links
    
    @staticmethod
    async def validate_group(client: TelegramClient, entity) -> Dict:
        """Validate if entity is a valid group (not subscription/channel)"""
        try:
            result = {
                'is_valid': False,
                'is_group': False,
                'is_channel': False,
                'is_subscription': False,
                'members_count': 0,
                'title': '',
                'description': '',
                'join_type': 'unknown'
            }
            
            if not entity:
                return result
            
            # Get entity info
            try:
                full_info = await client.get_entity(entity)
                result['title'] = getattr(full_info, 'title', '')
                result['description'] = getattr(full_info, 'about', '')
                
                # Determine entity type
                if hasattr(full_info, 'megagroup') and full_info.megagroup:
                    result['is_group'] = True
                    result['is_channel'] = False
                elif hasattr(full_info, 'broadcast') and full_info.broadcast:
                    result['is_channel'] = True
                    result['is_group'] = False
                    result['is_subscription'] = True
                elif hasattr(full_info, 'gigagroup'):
                    result['is_group'] = True
                    result['is_channel'] = False
                
                # Get members count
                if hasattr(full_info, 'participants_count'):
                    result['members_count'] = full_info.participants_count
                
                # Determine join type
                if hasattr(full_info, 'join_request'):
                    result['join_type'] = 'join_request'
                elif hasattr(full_info, 'join_to_send'):
                    result['join_type'] = 'join_to_send'
                elif hasattr(full_info, 'everyone_invite'):
                    result['join_type'] = 'open_invite'
                
                # Validate group
                result['is_valid'] = (
                    result['is_group'] and 
                    not result['is_subscription'] and
                    result['members_count'] >= Config.MIN_MEMBERS_FOR_GROUP and
                    result['join_type'] in ['join_request', 'join_to_send', 'open_invite']
                )
                
            except Exception as e:
                logger.debug(f"Error getting entity info: {e}")
                return result
            
            return result
            
        except Exception as e:
            logger.error(f"Error validating group: {e}")
            return {
                'is_valid': False,
                'is_group': False,
                'is_channel': False,
                'is_subscription': False,
                'members_count': 0,
                'title': '',
                'description': '',
                'join_type': 'unknown'
            }
    
    @staticmethod
    async def extract_links_from_messages_enhanced(client: TelegramClient, entity, max_messages: int = 50) -> List[str]:
        """Extract links from messages with advanced searching"""
        links = []
        
        try:
            logger.info(f"🔍 Searching messages in {getattr(entity, 'title', '')}...")
            
            # Search for messages with keywords
            keywords = Config.SEARCH_KEYWORDS
            
            for keyword in keywords[:5]:  # Limit to 5 keywords to avoid rate limits
                try:
                    async for message in client.iter_messages(
                        entity, 
                        search=keyword,
                        limit=10
                    ):
                        if message and hasattr(message, 'text') and message.text:
                            extracted = GroupValidator.extract_links_with_keywords(message.text)
                            if extracted:
                                logger.info(f"✅ Found {len(extracted)} links with '{keyword}'")
                                links.extend(extracted)
                        
                        # Check attachments and buttons
                        if hasattr(message, 'reply_markup') and message.reply_markup:
                            for row in message.reply_markup.rows:
                                for button in row.buttons:
                                    if hasattr(button, 'url'):
                                        extracted = GroupValidator.extract_links_with_keywords(button.url)
                                        if extracted:
                                            logger.info(f"✅ Found link in button: {button.url[:50]}")
                                            links.extend(extracted)
                        
                        await asyncio.sleep(0.1)
                        
                except Exception as e:
                    logger.debug(f"Error searching for keyword {keyword}: {e}")
                    continue
            
            # If no links found with keywords, check recent messages
            if not links:
                logger.info(f"🔍 Checking last {max_messages} messages...")
                async for message in client.iter_messages(entity, limit=max_messages):
                    if message and hasattr(message, 'text') and message.text:
                        extracted = GroupValidator.extract_links_with_keywords(message.text)
                        links.extend(extracted)
                    
                    await asyncio.sleep(0.05)
            
            # Remove duplicates and clean links
            unique_links = []
            seen = set()
            for link in links:
                cleaned = EnhancedLinkProcessor.normalize_url(link)
                if cleaned and cleaned not in seen:
                    seen.add(cleaned)
                    unique_links.append(cleaned)
            
            logger.info(f"✅ Extracted {len(unique_links)} unique links")
            return unique_links
            
        except Exception as e:
            logger.error(f"❌ Error extracting enhanced links: {e}")
            return []
    
    @staticmethod
    async def extract_links_from_pinned_messages(client: TelegramClient, entity) -> List[str]:
        """Extract links from pinned messages"""
        links = []
        
        try:
            if not Config.CHECK_PINNED_MESSAGES:
                return links
            
            # Get pinned messages
            pinned_messages = await client.get_messages(entity, filter=types.InputMessagesFilterPinned)
            
            for message in pinned_messages:
                if hasattr(message, 'text') and message.text:
                    extracted = GroupValidator.extract_links_with_keywords(message.text)
                    if extracted:
                        logger.info(f"✅ Found {len(extracted)} links in pinned message")
                        links.extend(extracted)
                
                # Check buttons in pinned message
                if hasattr(message, 'reply_markup') and message.reply_markup:
                    for row in message.reply_markup.rows:
                        for button in row.buttons:
                            if hasattr(button, 'url') and button.url:
                                extracted = GroupValidator.extract_links_with_keywords(button.url)
                                if extracted:
                                    logger.info(f"✅ Found link in pinned message button: {button.url[:50]}")
                                    links.extend(extracted)
                
                await asyncio.sleep(0.1)
        
        except Exception as e:
            logger.debug(f"Error extracting links from pinned messages: {e}")
        
        return links
    
    @staticmethod
    async def extract_links_from_comments(client: TelegramClient, entity) -> List[str]:
        """Extract links from message comments"""
        links = []
        
        try:
            if not Config.CHECK_COMMENTS:
                return links
            
            # Check recent messages for comments
            async for message in client.iter_messages(entity, limit=10):
                try:
                    # Get replies to this message
                    if message.replies and message.replies.replies > 0:
                        async for reply in client.iter_messages(
                            entity,
                            reply_to=message.id,
                            limit=5
                        ):
                            if reply and hasattr(reply, 'text') and reply.text:
                                extracted = GroupValidator.extract_links_with_keywords(reply.text)
                                if extracted:
                                    logger.info(f"✅ Found {len(extracted)} links in comment")
                                    links.extend(extracted)
                            
                            await asyncio.sleep(0.1)
                except Exception as e:
                    continue
                
                await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.debug(f"Error extracting links from comments: {e}")
        
        return links

# ======================
# Collection Manager
# ======================

class CollectionManager:
    """Manage link collection"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        self.stats = {
            'total_collected': 0,
            'total_processed': 0,
            'valid_groups': 0,
            'subscriptions_skipped': 0,
            'telegram': 0,
            'whatsapp': 0,
            'discord': 0,
            'signal': 0,
            'errors': 0,
            'sessions_used': 0,
            'last_collection_time': None
        }
        self.collection_task = None
    
    async def start_collection(self):
        """Start collection process"""
        if self.active:
            return
        
        self.active = True
        self.paused = False
        self.stop_requested = False
        
        logger.info("🚀 Starting real collection process")
        
        # Start collection task in background
        self.collection_task = asyncio.create_task(self._collection_loop())
    
    async def _collection_loop(self):
        """Main collection loop"""
        while self.active and not self.stop_requested:
            if self.paused:
                await asyncio.sleep(1)
                continue
            
            try:
                await self._collection_cycle()
                
                # Delay between cycles
                delay = Config.REQUEST_DELAYS['max_cycle_delay']
                logger.info(f"⏳ Waiting {delay} seconds before next cycle")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"Error in collection cycle: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(10)
        
        self.active = False
        logger.info("⏹️ Collection stopped")
    
    async def _collection_cycle(self):
        """Single collection cycle"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=Config.MAX_CONCURRENT_SESSIONS)
            
            if not sessions:
                logger.warning("No active sessions")
                return
            
            self.stats['sessions_used'] = len(sessions)
            self.stats['last_collection_time'] = datetime.now().isoformat()
            
            tasks = []
            for session in sessions:
                task = self._process_session(session)
                tasks.append(task)
                await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful = sum(1 for r in results if not isinstance(r, Exception))
            logger.info(f"Completed collection cycle: {successful}/{len(tasks)} sessions successful")
            
            # Save stats
            await self._save_stats()
            
        except Exception as e:
            logger.error(f"Error in collection cycle: {e}")
            self.stats['errors'] += 1
    
    async def _process_session(self, session: Dict):
        """Process single session"""
        try:
            session_string = session.get('session_string', '')
            session_id = session.get('id')
            
            if not session_string or session_string == '********':
                logger.error(f"Session {session_id} not available")
                return {'status': 'error', 'reason': 'Session not available'}
            
            # Decrypt session
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt(session_string)
            
            client = await SessionManager.create_client(decrypted_session)
            if not client:
                return {'status': 'error', 'reason': 'Failed to create client'}
            
            # Collect links from dialogs
            collected = await self._collect_from_dialogs(client, session_id)
            
            await client.disconnect()
            
            # Update session stats
            db = await EnhancedDatabaseManager.get_instance()
            await db.conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, last_success = CURRENT_TIMESTAMP, total_uses = total_uses + 1, total_links = total_links + ? WHERE id = ?",
                (len(collected), session_id)
            )
            await db.conn.commit()
            
            return {'status': 'success', 'collected': len(collected)}
            
        except Exception as e:
            logger.error(f"Error processing session: {e}")
            self.stats['errors'] += 1
            return {'status': 'error', 'reason': str(e)}
    
    async def _collect_from_dialogs(self, client: TelegramClient, session_id: int) -> List[Dict]:
        """Collect links from dialogs"""
        collected = []
        
        try:
            dialog_count = 0
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                if not self.active or self.stop_requested or self.paused:
                    break
                
                dialog_count += 1
                logger.info(f"📂 Processing dialog {dialog_count}: {dialog.name}")
                
                try:
                    entity = dialog.entity
                    
                    # Validate entity
                    validation = await GroupValidator.validate_group(client, entity)
                    
                    if not validation['is_valid']:
                        if validation['is_subscription']:
                            self.stats['subscriptions_skipped'] += 1
                            logger.debug(f"⏭️ Skipping subscription channel: {validation.get('title', '')}")
                        else:
                            logger.debug(f"⏭️ Skipping invalid group: {validation.get('title', '')}")
                        continue
                    
                    # Valid group, collect links
                    logger.info(f"✅ Collecting from valid group: {validation.get('title', '')} ({validation['members_count']} members)")
                    
                    # Collect links from group
                    all_links = []
                    
                    # Get links from pinned messages
                    if Config.CHECK_PINNED_MESSAGES:
                        pinned_links = await GroupValidator.extract_links_from_pinned_messages(client, entity)
                        if pinned_links:
                            all_links.extend(pinned_links)
                            logger.info(f"📌 Found {len(pinned_links)} links in pinned messages")
                    
                    # Get links from enhanced message search
                    enhanced_links = await GroupValidator.extract_links_from_messages_enhanced(
                        client, 
                        entity, 
                        max_messages=Config.MAX_DEEP_MESSAGES
                    )
                    if enhanced_links:
                        all_links.extend(enhanced_links)
                    
                    # Get links from comments
                    if Config.CHECK_COMMENTS:
                        comment_links = await GroupValidator.extract_links_from_comments(client, entity)
                        if comment_links:
                            all_links.extend(comment_links)
                            logger.info(f"💬 Found {len(comment_links)} links in comments")
                    
                    if all_links:
                        logger.info(f"📊 Found {len(all_links)} total links in group")
                        
                        # Process collected links
                        processed_count = 0
                        for link in all_links[:Config.MAX_LINKS_PER_GROUP]:
                            link_info = await self._process_link(link, session_id, validation)
                            if link_info:
                                collected.append(link_info)
                                processed_count += 1
                        
                        logger.info(f"✅ Saved {processed_count} links from group")
                    
                    # Update statistics
                    self.stats['valid_groups'] += 1
                    self.stats['total_processed'] += 1
                    
                    # Short delay between groups
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"❌ Error collecting from dialog: {e}")
                    continue
            
            logger.info(f"📊 Finished dialog collection: {dialog_count} dialogs, {len(collected)} links")
            
        except Exception as e:
            logger.error(f"❌ Error collecting from dialogs: {e}")
        
        return collected
    
    async def _process_link(self, url: str, session_id: int, group_info: Dict) -> Optional[Dict]:
        """Process and save a single link"""
        try:
            # Skip empty links
            if not url or len(url) < Config.MIN_LINK_LENGTH:
                return None
            
            url_info = EnhancedLinkProcessor.extract_url_info(url)
            
            if not url_info['is_valid']:
                logger.debug(f"⏭️ Invalid URL: {url[:50]}...")
                return None
            
            platform = url_info['platform']
            details = url_info['details']
            
            # Skip channels if required
            if Config.COLLECT_ONLY_GROUPS and details.get('is_subscription'):
                logger.debug(f"⏭️ Skipping subscription: {url[:50]}...")
                return None
            
            # Check WhatsApp link age (last 60 days)
            if platform == 'whatsapp':
                # Age check can be implemented if we have message dates
                pass
            
            # Determine if it's a valid group link
            is_valid_group = (
                details.get('is_group', False) and 
                not details.get('is_channel', False) and
                not details.get('is_subscription', False)
            )
            
            link_info = {
                'url': url,
                'url_hash': url_info['url_hash'],
                'platform': platform,
                'link_type': 'group' if is_valid_group else 'channel',
                'telegram_type': details.get('telegram_type', ''),
                'session_id': session_id,
                'confidence': 'high' if is_valid_group else 'medium',
                'is_active': True,
                'requires_join': details.get('is_join_request', False),
                'is_verified': is_valid_group,
                'validation_score': 100 if is_valid_group else 50,
                'members': group_info.get('members_count', 0),
                'metadata': {
                    'collected_at': datetime.now().isoformat(),
                    'platform_details': url_info['details'],
                    'source_group': group_info.get('title', ''),
                    'source_members': group_info.get('members_count', 0),
                    'collected_method': 'enhanced_search'
                },
                'source': 'real_collection',
                'is_channel': details.get('is_channel', False),
                'is_group': details.get('is_group', True),
                'is_join_request': details.get('is_join_request', False),
                'is_supergroup': details.get('is_supergroup', False),
                'is_subscription': details.get('is_subscription', False),
                'is_valid_group': is_valid_group,
                'last_validated': datetime.now().isoformat()
            }
            
            db = await EnhancedDatabaseManager.get_instance()
            success, message, details = await db.add_link(link_info)
            
            if success:
                # Update statistics
                self.stats['total_collected'] += 1
                if platform == 'telegram':
                    self.stats['telegram'] += 1
                elif platform == 'whatsapp':
                    self.stats['whatsapp'] += 1
                elif platform == 'discord':
                    self.stats['discord'] += 1
                elif platform == 'signal':
                    self.stats['signal'] += 1
                
                if is_valid_group:
                    logger.info(f"✅ Saved valid group link: {url[:60]}...")
                
                return link_info
            else:
                logger.debug(f"⏭️ Duplicate link: {url[:50]}...")
                return None
            
        except Exception as e:
            logger.error(f"❌ Error processing link {url[:50]}: {e}")
            return None
    
    async def _save_stats(self):
        """Save statistics"""
        try:
            stats_file = "collection_stats.json"
            stats_data = {
                'stats': self.stats,
                'last_updated': datetime.now().isoformat()
            }
            
            async with aiofiles.open(stats_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(stats_data, indent=2, ensure_ascii=False))
            
        except Exception as e:
            logger.error(f"Error saving stats: {e}")
    
    def get_status(self) -> Dict:
        """Get collection status"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'stats': self.stats.copy()
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
        logger.info("⏹️ Stopping collection requested")
        
        # Wait for task to stop
        if self.collection_task:
            try:
                await asyncio.wait_for(self.collection_task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for collection task to stop")
        
        self.active = False

# ======================
# Encryption Manager
# ======================

class EncryptionManager:
    """Encryption manager"""
    
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
            backup_filename = f"backup_{timestamp}.db"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            os.makedirs(backup_dir, exist_ok=True)
            
            if not os.path.exists(Config.DB_PATH):
                return None
            
            shutil.copy2(Config.DB_PATH, backup_path)
            
            metadata = {
                'backup_id': hashlib.md5(timestamp.encode()).hexdigest(),
                'timestamp': timestamp,
                'created_at': datetime.now().isoformat(),
                'file_path': backup_path,
                'size_bytes': os.path.getsize(backup_path)
            }
            
            logger.info(f"Created backup: {backup_path}")
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return None
    
    @staticmethod
    async def rotate_backups():
        """Rotate old backups"""
        try:
            if not os.path.exists("backups"):
                return
            
            backups = []
            for filename in os.listdir("backups"):
                if filename.startswith("backup_") and filename.endswith(".db"):
                    path = os.path.join("backups", filename)
                    ctime = os.path.getctime(path)
                    backups.append({'path': path, 'created': ctime})
            
            backups.sort(key=lambda x: x['created'])
            
            if len(backups) > Config.MAX_BACKUPS:
                to_delete = backups[:-Config.MAX_BACKUPS]
                for backup in to_delete:
                    try:
                        os.remove(backup['path'])
                        logger.info(f"Deleted old backup: {backup['path']}")
                    except Exception as e:
                        logger.error(f"Error deleting old backup: {e}")
            
        except Exception as e:
            logger.error(f"Error rotating backups: {e}")

# ======================
# Database Repair Function
# ======================

async def check_and_repair_database():
    """Check and repair database issues"""
    try:
        db = await EnhancedDatabaseManager.get_instance()
        
        # Check number of links
        cursor = await db.conn.execute("SELECT COUNT(*) FROM links")
        total_links = (await cursor.fetchone())[0]
        
        cursor = await db.conn.execute("SELECT COUNT(*) FROM links WHERE is_valid_group = 1")
        valid_links = (await cursor.fetchone())[0]
        
        logger.info(f"📊 Database check: Total {total_links} links, {valid_links} valid")
        
        # Repair unclassified links
        if valid_links == 0 and total_links > 0:
            logger.info("🔄 Reclassifying links...")
            
            cursor = await db.conn.execute("SELECT id, url FROM links")
            all_links = await cursor.fetchall()
            
            updated = 0
            for link_id, url in all_links:
                url_info = EnhancedLinkProcessor.extract_url_info(url)
                details = url_info['details']
                
                is_valid_group = (
                    details.get('is_group', False) and 
                    not details.get('is_channel', False) and
                    not details.get('is_subscription', False)
                )
                
                if is_valid_group:
                    await db.conn.execute(
                        "UPDATE links SET is_valid_group = 1 WHERE id = ?",
                        (link_id,)
                    )
                    updated += 1
            
            await db.conn.commit()
            logger.info(f"✅ Updated {updated} links as valid groups")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database repair error: {e}")
        return False

# ======================
# Telegram Bot
# ======================

class TelegramBot:
    """Main Telegram bot"""
    
    def __init__(self):
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        self.collection_manager = CollectionManager()
        
        self._setup_handlers()
        
        self.user_states = {}
    
    def _setup_handlers(self):
        """Setup bot handlers"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("backup", self.backup_command))
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        self.app.add_handler(CommandHandler("addsession", self.add_session_command))
        self.app.add_handler(CommandHandler("test_collect", self.test_collect_command))
        self.app.add_handler(CommandHandler("validate_links", self.validate_links_command))
        self.app.add_handler(CommandHandler("repair", self.repair_command))
        
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_message
        ))
        
        self.app.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # Check access
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ Access denied")
                return
        
        # Add/update user in database
        db = await EnhancedDatabaseManager.get_instance()
        await db.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Start Real Collection", callback_data="start_collect"),
             InlineKeyboardButton("⏸️ Manage Collection", callback_data="manage_collect")],
            [InlineKeyboardButton("➕ Add Session", callback_data="add_session"),
             InlineKeyboardButton("👥 Sessions", callback_data="show_sessions")],
            [InlineKeyboardButton("📤 Export Links", callback_data="export_links"),
             InlineKeyboardButton("📊 Statistics", callback_data="show_stats")],
            [InlineKeyboardButton("🧪 Test Collection", callback_data="test_collection"),
             InlineKeyboardButton("⚙️ Settings", callback_data="show_settings")]
        ])
        
        welcome_text = (
            f"🤖 **Hello {user.first_name}!**\n\n"
            "**Real Group Links Collector Bot**\n\n"
            "**New Features:**\n"
            "• ✅ Real collection from active groups\n"
            "• ❌ Skip channels and subscription links\n"
            "• 🔍 Deep collection from messages and descriptions\n"
            "• 📊 Separate export for each platform\n"
            "• 🧪 Test collection before starting\n\n"
            "**🚀 Click buttons below to start real collection!**"
        )
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = (
            "**📖 User Guide - Real Version**\n\n"
            "**Basic Commands:**\n"
            "• /start - Start bot and welcome message\n"
            "• /help - Show this help\n"
            "• /status - Show system and collection status\n\n"
            "**Session Management:**\n"
            "• /sessions - Show active sessions\n"
            "• /addsession - Add new session\n\n"
            "**Collection and Export:**\n"
            "• /collect - Start/stop real collection\n"
            "• /test_collect - Test collection on one group\n"
            "• /validate_links - Validate stored links\n"
            "• /export - Export collected links\n\n"
            "**Management:**\n"
            "• /stats - System statistics\n"
            "• /backup - Create backup\n"
            "• /repair - Repair system issues\n\n"
            "**📌 How to Start:**\n"
            "1. Add Telegram session using /addsession\n"
            "2. Test collection using /test_collect\n"
            "3. Start real collection using /collect\n"
            "4. Export links using /export\n\n"
            "**🔒 Notes:**\n"
            "• Bot collects only active groups (join request)\n"
            "• Skips channels and subscription links\n"
            "• Collects from descriptions and messages inside groups"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        user = update.effective_user
        
        # Check access
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ Access denied")
                return
        
        status = self.collection_manager.get_status()
        
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        
        status_text = (
            f"**📊 Real System Status - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**\n\n"
            "**Collection Status:**\n"
        )
        
        if status['active']:
            if status['paused']:
                status_text += "⏸️ **Paused**\n"
            elif status['stop_requested']:
                status_text += "🛑 **Stopping...**\n"
            else:
                status_text += "🔄 **Active - Real Collection**\n"
        else:
            status_text += "🛑 **Stopped**\n"
        
        status_text += (
            f"\n**Real Collection Statistics:**\n"
            f"• 📦 Total Collected: {status['stats']['total_collected']:,}\n"
            f"• ✅ Valid Groups: {status['stats']['valid_groups']:,}\n"
            f"• ❌ Channels Skipped: {status['stats']['subscriptions_skipped']:,}\n"
            f"• 📢 Telegram: {status['stats']['telegram']:,}\n"
            f"• 📱 WhatsApp: {status['stats']['whatsapp']:,}\n"
            f"• 🎮 Discord: {status['stats']['discord']:,}\n"
            f"• 📡 Signal: {status['stats']['signal']:,}\n"
            f"• ⚡ Sessions Used: {status['stats']['sessions_used']}\n"
            f"• ❌ Errors: {status['stats']['errors']:,}\n"
            f"• 🕒 Last Collection: {status['stats']['last_collection_time'] or 'Not started'}\n\n"
            f"**Database Statistics:**\n"
            f"• 🔗 Total Links: {db_stats.get('total_links', 0):,}\n"
            f"• ✅ Valid Groups: {db_stats.get('valid_groups', 0):,}\n"
            f"• 📺 Channels: {db_stats.get('subscriptions', 0):,}\n"
            f"• 💼 Active Sessions: {db_stats.get('active_sessions', 0)}\n"
            f"• 👥 Users: {db_stats.get('total_users', 0)}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status"),
             InlineKeyboardButton("🚀 Start Collection", callback_data="start_collect")],
            [InlineKeyboardButton("⏸️ Pause", callback_data="pause_collect"),
             InlineKeyboardButton("⏹️ Stop", callback_data="stop_collect")],
            [InlineKeyboardButton("🧪 Test Collection", callback_data="test_collection")]
        ])
        
        await update.message.reply_text(status_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        user = update.effective_user
        
        # Check access
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ Access denied")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        
        user_stats = await db.get_user_stats(user.id)
        
        stats_text = "**📈 Advanced System Statistics**\n\n**User Statistics:**\n"
        
        if user_stats:
            stats_text += (
                f"• 🆔 ID: {user.id}\n"
                f"• 👤 Name: {user_stats.get('first_name', '')} {user_stats.get('last_name', '')}\n"
                f"• 📅 Member Since: {user_stats.get('added_date', 'Unknown')}\n"
                f"• 📊 Your Requests: {user_stats.get('request_count', 0):,}\n"
                f"• 🔗 Your Links: {user_stats.get('total_links', 0):,}\n"
                f"• 💼 Your Sessions: {user_stats.get('total_sessions', 0)}\n\n"
            )
        
        stats_text += (
            f"**System Statistics:**\n"
            f"• 🔗 Total Links: {db_stats.get('total_links', 0):,}\n"
            f"• ✅ Valid Groups: {db_stats.get('valid_groups', 0):,}\n"
            f"• 📺 Channels: {db_stats.get('subscriptions', 0):,}\n"
            f"• 💼 Active Sessions: {db_stats.get('active_sessions', 0)}\n"
            f"• 👥 Users: {db_stats.get('total_users', 0)}\n"
        )
        
        # Platform statistics
        if 'links_by_platform' in db_stats:
            stats_text += "\n**Platform Distribution (valid groups only):**\n"
            for platform, count in db_stats['links_by_platform'].items():
                stats_text += f"• {platform}: {count:,}\n"
        
        await update.message.reply_text(stats_text, parse_mode="Markdown")
    
    async def sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sessions command"""
        user = update.effective_user
        
        # Check access
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ Access denied")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=20)
        
        if not sessions:
            await update.message.reply_text("❌ No active sessions")
            return
        
        sessions_text = f"**👥 Active Sessions ({len(sessions)})**\n\n"
        
        for i, session in enumerate(sessions, 1):
            display_name = session.get('display_name', 'Unknown')
            username = session.get('username', 'No username')
            phone = session.get('phone_number', 'No phone')
            last_used = session.get('last_used', 'Never used')
            uses = session.get('total_uses', 0)
            links_collected = session.get('total_links', 0)
            
            sessions_text += (
                f"**{i}. {display_name}**\n"
                f"• Username: @{username}\n"
                f"• Phone: {phone}\n"
                f"• Uses: {uses}\n"
                f"• Links Collected: {links_collected:,}\n"
                f"• Last Used: {last_used}\n\n"
            )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Session", callback_data="add_session"),
             InlineKeyboardButton("🗑️ Delete Session", callback_data="delete_session")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_sessions")]
        ])
        
        await update.message.reply_text(sessions_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command"""
        user = update.effective_user
        
        # Check access
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ Access denied")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        total_links = await db.get_links_count()
        
        if total_links == 0:
            await update.message.reply_text("❌ No valid links to export")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Text", callback_data="export_txt"),
             InlineKeyboardButton("📊 CSV", callback_data="export_csv")],
            [InlineKeyboardButton("📋 JSON", callback_data="export_json"),
             InlineKeyboardButton("📦 All Links", callback_data="export_all")],
            [InlineKeyboardButton("📢 Telegram Only", callback_data="export_telegram"),
             InlineKeyboardButton("📱 WhatsApp Only", callback_data="export_whatsapp")],
            [InlineKeyboardButton("🎮 Discord Only", callback_data="export_discord"),
             InlineKeyboardButton("📡 Signal Only", callback_data="export_signal")]
        ])
        
        export_text = (
            f"**📤 Export Valid Links**\n\n"
            f"Total Valid Links: **{total_links:,}**\n\n"
            "**Export Options:**\n"
            "• 📄 Text - Links only\n"
            "• 📊 CSV - With information\n"
            "• 📋 JSON - Full information\n"
            "• 📦 All valid links\n"
            "• 📢 Telegram links only\n"
            "• 📱 WhatsApp links only\n"
            "• 🎮 Discord links only\n"
            "• 📡 Signal links only\n\n"
            "**Notes:**\n"
            f"• Maximum export: {Config.MAX_EXPORT_LINKS:,} links\n"
            "• Only valid groups\n"
            "• Each platform separately\n"
            "• Links are clean and ready to use"
        )
        
        await update.message.reply_text(export_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /backup command"""
        user = update.effective_user
        
        # Check access
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ Access denied")
                return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💾 Create Backup", callback_data="create_backup"),
             InlineKeyboardButton("📋 List Backups", callback_data="list_backups")],
            [InlineKeyboardButton("🔄 Rotate Backups", callback_data="rotate_backups")]
        ])
        
        backup_text = (
            "**💾 Backup Management**\n\n"
            "**Features:**\n"
            "• Automatic backup\n"
            "• Save session and link data\n"
            "• Restore data when needed\n"
            "• Automatic rotation of old backups\n\n"
            f"**Settings:**\n"
            f"• Backups kept: {Config.MAX_BACKUPS}\n"
            f"• Automatic backup: {'✅ Enabled' if Config.BACKUP_ENABLED else '❌ Disabled'}\n\n"
            "**Commands:**\n"
            "• Create manual backup\n"
            "• View backup list\n"
            "• Rotate old backups"
        )
        
        await update.message.reply_text(backup_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /collect command"""
        user = update.effective_user
        
        # Check access
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ Access denied")
                return
        
        status = self.collection_manager.get_status()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Start Real Collection", callback_data="start_collect"),
             InlineKeyboardButton("⏸️ Pause", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ Stop", callback_data="stop_collect"),
             InlineKeyboardButton("📊 Collection Status", callback_data="collect_status")],
            [InlineKeyboardButton("⚙️ Collection Settings", callback_data="collect_settings"),
             InlineKeyboardButton("🧪 Test Collection", callback_data="test_collection")]
        ])
        
        collect_text = "**🚀 Real Collection Management**\n\n**Current Status:**\n"
        
        if status['active']:
            if status['paused']:
                collect_text += "⏸️ **Paused**\n"
            else:
                collect_text += "🔄 **Active - Real Collection**\n"
        else:
            collect_text += "🛑 **Stopped**\n"
        
        collect_text += (
            f"\n**Real Statistics:**\n"
            f"• Links Collected: {status['stats']['total_collected']:,}\n"
            f"• Valid Groups: {status['stats']['valid_groups']:,}\n"
            f"• Channels Skipped: {status['stats']['subscriptions_skipped']:,}\n"
            f"• Errors: {status['stats']['errors']:,}\n\n"
            "**Real Features:**\n"
            "• ✅ Collect only from active groups\n"
            "• ❌ Skip channels and subscription links\n"
            "• 🔍 Deep collection from messages and descriptions\n"
            "• 📊 Separate export for each platform\n"
            "• 🧪 Test collection before starting\n\n"
            f"**Settings:**\n"
            f"• Collect groups only: {'✅ Yes' if Config.COLLECT_ONLY_GROUPS else '❌ No'}\n"
            f"• Minimum members: {Config.MIN_MEMBERS_FOR_GROUP}\n"
            f"• Deep collection: {'✅ Enabled' if Config.ENABLE_DEEP_COLLECTION else '❌ Disabled'}"
        )
        
        await update.message.reply_text(collect_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def add_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addsession command"""
        user = update.effective_user
        
        # Check access
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ Access denied")
                return
        
        self.user_states[user.id] = {'waiting_for_session': True}
        
        add_text = (
            "**➕ Add New Session**\n\n"
            "**Instructions:**\n"
            "1. Open https://my.telegram.org\n"
            "2. Login with your account\n"
            "3. Go to **API Development Tools**\n"
            "4. Create new app and get:\n"
            "   • api_id\n"
            "   • api_hash\n"
            "5. Open @GetStringBot and send /start\n"
            "6. Send it api_id and api_hash\n"
            "7. It will send you session string\n\n"
            "**Send session string now:**\n"
            "(You can copy full code and send)\n\n"
            "**Note:** Session used only for collecting links from active groups"
        )
        
        await update.message.reply_text(add_text, parse_mode="Markdown")
    
    async def test_collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /test_collect command"""
        try:
            # Get user from query if callback
            if hasattr(update, 'callback_query'):
                user = update.callback_query.from_user
                message = update.callback_query.message
            else:
                user = update.effective_user
                message = update.message
            
            # Check access
            if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
                if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                    await message.reply_text("❌ Access denied")
                    return
            
            await message.reply_text("🧪 **Testing collection...**")
            
            try:
                db = await EnhancedDatabaseManager.get_instance()
                sessions = await db.get_active_sessions(limit=1)
                
                if not sessions:
                    await message.reply_text("❌ No active sessions for testing")
                    return
                
                session = sessions[0]
                session_string = session.get('session_string', '')
                
                if not session_string or session_string == '********':
                    await message.reply_text("❌ Session not available")
                    return
                
                # Decrypt session
                enc_manager = EncryptionManager.get_instance()
                decrypted_session = enc_manager.decrypt(session_string)
                
                client = await SessionManager.create_client(decrypted_session)
                if not client:
                    await message.reply_text("❌ Failed to create client")
                    return
                
                # Test collection from first dialog
                collected = []
                async for dialog in client.iter_dialogs(limit=1):
                    try:
                        entity = dialog.entity
                        
                        # Validate entity
                        validation = await GroupValidator.validate_group(client, entity)
                        
                        test_result = (
                            "**🧪 Test Results:**\n\n"
                            "**Tested Group:**\n"
                            f"• Title: {validation.get('title', 'Unknown')}\n"
                            f"• Type: {'Group' if validation['is_group'] else 'Channel'}\n"
                            f"• Subscription: {'Yes' if validation['is_subscription'] else 'No'}\n"
                            f"• Members: {validation['members_count']}\n"
                            f"• Join Type: {validation['join_type']}\n"
                            f"• Valid for Collection: {'✅ Yes' if validation['is_valid'] else '❌ No'}"
                        )
                        
                        await message.reply_text(test_result, parse_mode="Markdown")
                        
                        if validation['is_valid']:
                            # Collect links from group
                            links = await GroupValidator.extract_links_from_messages_enhanced(client, entity, max_messages=5)
                            
                            if links:
                                links_result = f"\n**Collected Links:** {len(links)}\n\n**Sample Links:**\n"
                                for i, link in enumerate(links[:5], 1):
                                    links_result += f"{i}. {link}\n"
                                
                                await message.reply_text(links_result)
                                
                                # Save some links as sample
                                for link in links[:3]:
                                    link_info = EnhancedLinkProcessor.extract_url_info(link)
                                    if link_info['is_valid']:
                                        details = link_info['details']
                                        is_valid_group = (
                                            details.get('is_group', False) and 
                                            not details.get('is_channel', False) and
                                            not details.get('is_subscription', False)
                                        )
                                        
                                        link_data = {
                                            'url': link,
                                            'platform': link_info['platform'],
                                            'link_type': 'group' if is_valid_group else 'channel',
                                            'session_id': session.get('id'),
                                            'is_valid_group': is_valid_group,
                                            'added_by_user': user.id,
                                            'source': 'test_collection'
                                        }
                                        
                                        success, message_text, _ = await db.add_link(link_data)
                                        if success:
                                            collected.append(link)
                            
                            if collected:
                                test_result += f"\n✅ **Saved {len(collected)} links as sample**"
                            else:
                                test_result += "\n⚠️ **No valid links found**"
                        else:
                            test_result += "\n⚠️ **This is not a valid group for collection**"
                            
                            if validation['is_subscription']:
                                test_result += "\n❌ **Skipped because it's subscription channel**"
                            elif validation['members_count'] < Config.MIN_MEMBERS_FOR_GROUP:
                                test_result += f"\n❌ **Members less than {Config.MIN_MEMBERS_FOR_GROUP}**"
                        
                        await message.reply_text(test_result, parse_mode="Markdown")
                        
                    except Exception as e:
                        logger.error(f"Test collection error: {e}")
                        await message.reply_text(f"❌ Test error: {str(e)[:200]}")
                        break
                
                await client.disconnect()
                
                if collected:
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🚀 Start Real Collection", callback_data="start_collect"),
                         InlineKeyboardButton("📤 Export Sample", callback_data="export_test")]
                    ])
                    
                    await message.reply_text(
                        f"✅ **Test completed successfully!**\n\n"
                        f"Collected {len(collected)} links as sample.\n"
                        f"You can now start real collection.",
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                
            except Exception as e:
                logger.error(f"Test collection error: {e}")
                await message.reply_text(f"❌ Test error: {str(e)[:200]}")
                
        except Exception as e:
            logger.error(f"Error in test_collect_command: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")
    
    async def validate_links_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /validate_links command"""
        user = update.effective_user
        
        # Check access
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ Access denied")
                return
        
        await update.message.reply_text("🔍 **Validating stored links...**")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            # Get some links for validation
            cursor = await db.conn.execute('''
                SELECT id, url, is_valid_group, is_subscription 
                FROM links 
                ORDER BY collected_date DESC 
                LIMIT 10
            ''')
            
            rows = await cursor.fetchall()
            
            if not rows:
                await update.message.reply_text("❌ No stored links")
                return
            
            validation_text = "**🔍 Validation Results:**\n\n"
            
            for row in rows:
                link_id, url, is_valid_group, is_subscription = row
                
                url_info = EnhancedLinkProcessor.extract_url_info(url)
                details = url_info['details']
                
                status = "✅ Valid" if is_valid_group else "❌ Invalid"
                if is_subscription:
                    status = "📺 Subscription Channel"
                
                validation_text += f"**{link_id}. {url[:50]}...**\n"
                validation_text += f"• Status: {status}\n"
                validation_text += f"• Platform: {url_info['platform']}\n"
                validation_text += f"• Type: {'Group' if details.get('is_group') else 'Channel'}\n"
                validation_text += f"• Subscription: {'Yes' if details.get('is_subscription') else 'No'}\n\n"
            
            # General statistics
            cursor = await db.conn.execute("SELECT COUNT(*) FROM links WHERE is_valid_group = 1")
            valid_groups = (await cursor.fetchone())[0]
            
            cursor = await db.conn.execute("SELECT COUNT(*) FROM links WHERE is_subscription = 1")
            subscriptions = (await cursor.fetchone())[0]
            
            cursor = await db.conn.execute("SELECT COUNT(*) FROM links")
            total_links = (await cursor.fetchone())[0]
            
            validation_text += f"**📊 Statistics:**\n"
            validation_text += f"• Total Links: {total_links:,}\n"
            validation_text += f"• Valid Groups: {valid_groups:,}\n"
            validation_text += f"• Subscription Channels: {subscriptions:,}\n"
            validation_text += f"• Validity Rate: {(valid_groups/total_links*100 if total_links > 0 else 0):.1f}%\n"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Export Valid", callback_data="export_valid"),
                 InlineKeyboardButton("🗑️ Delete Invalid", callback_data="delete_invalid")]
            ])
            
            await update.message.reply_text(validation_text, reply_markup=keyboard, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Link validation error: {e}")
            await update.message.reply_text(f"❌ Validation error: {str(e)[:200]}")
    
    async def repair_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /repair command"""
        user = update.effective_user
        
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            await update.message.reply_text("❌ This command is for admins only")
            return
        
        await update.message.reply_text("🔧 **Checking and repairing system...**")
        
        try:
            # Check database
            await check_and_repair_database()
            
            # Check sessions
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions()
            
            # Create backup
            await BackupManager.create_backup()
            
            await update.message.reply_text(
                f"✅ **Repair completed successfully!**\n\n"
                f"**Statistics:**\n"
                f"• Active Sessions: {len(sessions)}\n"
                f"• Backup created\n"
                f"• System ready\n\n"
                f"You can now use /test_collect to test"
            )
            
        except Exception as e:
            logger.error(f"❌ Repair error: {e}")
            await update.message.reply_text(f"❌ Repair error: {str(e)[:200]}")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        data = query.data
        
        # Check access
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await self._edit_message_safe(query, "❌ Access denied")
                return
        
        try:
            if data == "start_collect":
                await self._handle_start_collect(query)
            elif data == "pause_collect":
                await self._handle_pause_collect(query)
            elif data == "stop_collect":
                await self._handle_stop_collect(query)
            elif data == "collect_status":
                await self._handle_collect_status(query)
            elif data == "collect_settings":
                await self._handle_collect_settings(query)
            elif data == "test_collection":
                await self.test_collect_command(update, context)
            elif data == "add_session":
                await self._handle_add_session(query)
            elif data == "show_sessions":
                await self._handle_show_sessions(query)
            elif data == "show_stats":
                await self._handle_show_stats(query)
            elif data == "export_links":
                await self._handle_export_links(query)
            elif data == "export_txt":
                await self._handle_export_txt(query)
            elif data == "export_csv":
                await self._handle_export_csv(query)
            elif data == "export_json":
                await self._handle_export_json(query)
            elif data == "export_all":
                await self._handle_export_all(query)
            elif data == "export_telegram":
                await self._handle_export_telegram(query)
            elif data == "export_whatsapp":
                await self._handle_export_whatsapp(query)
            elif data == "export_discord":
                await self._handle_export_discord(query)
            elif data == "export_signal":
                await self._handle_export_signal(query)
            elif data == "export_test":
                await self._handle_export_test(query)
            elif data == "export_valid":
                await self._handle_export_valid(query)
            elif data == "delete_invalid":
                await self._handle_delete_invalid(query)
            elif data == "create_backup":
                await self._handle_create_backup(query)
            elif data == "list_backups":
                await self._handle_list_backups(query)
            elif data == "rotate_backups":
                await self._handle_rotate_backups(query)
            elif data == "refresh_status":
                await self._handle_refresh_status(query)
            elif data == "refresh_sessions":
                await self._handle_refresh_sessions(query)
            elif data == "show_help":
                await self._handle_show_help(query)
            elif data == "show_settings":
                await self._handle_show_settings(query)
            elif data == "manage_collect":
                await self._handle_manage_collect(query)
            elif data == "delete_session":
                await self._handle_delete_session(query)
            elif data.startswith("delete_session_"):
                await self._handle_delete_session_confirm(query, data)
            else:
                await self._edit_message_safe(query, "❌ Unknown command")
        
        except Exception as e:
            logger.error(f"Callback handling error: {e}")
            await self._edit_message_safe(query, f"❌ Error: {str(e)[:100]}")
    
    async def _edit_message_safe(self, query, text, reply_markup=None, parse_mode="Markdown"):
        """Edit message safely with error handling"""
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                pass
            else:
                logger.error(f"Message edit error: {e}")
                await query.message.reply_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
        except Exception as e:
            logger.error(f"Unexpected message edit error: {e}")
            await query.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    
    async def _handle_start_collect(self, query):
        """Handle start collection"""
        if self.collection_manager.active:
            await self._edit_message_safe(query, "⏳ Collection already running")
            return
        
        # Start real collection task
        await self.collection_manager.start_collection()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ Pause", callback_data="pause_collect"),
             InlineKeyboardButton("⏹️ Stop", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 Collection Status", callback_data="collect_status"),
             InlineKeyboardButton("📤 Export Links", callback_data="export_links")]
        ])
        
        await self._edit_message_safe(
            query,
            "🚀 **Real collection started successfully!**\n\n"
            "**Active Features:**\n"
            "✅ Collect only from active groups\n"
            "❌ Skip channels and subscription links\n"
            "🔍 Deep collection from messages and descriptions\n\n"
            "**Details:**\n"
            "• Collecting links from active sessions\n"
            "• Only groups with (join request)\n"
            "• Links automatically saved to database\n"
            "• You can export anytime\n\n"
            "⏳ **Statistics will update automatically**",
            reply_markup=keyboard
        )
    
    async def _handle_pause_collect(self, query):
        """Handle pause collection"""
        if not self.collection_manager.active:
            await self._edit_message_safe(query, "⚠️ Collection not active")
            return
        
        await self.collection_manager.pause()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Resume", callback_data="start_collect"),
             InlineKeyboardButton("⏹️ Stop", callback_data="stop_collect")]
        ])
        
        await self._edit_message_safe(
            query,
            "⏸️ **Collection paused**\n\n"
            "You can resume collection anytime.\n"
            "Sessions remain active.\n\n"
            "**Current Statistics:**\n"
            f"• Links Collected: {self.collection_manager.stats['total_collected']:,}\n"
            f"• Valid Groups: {self.collection_manager.stats['valid_groups']:,}\n"
            f"• Channels Skipped: {self.collection_manager.stats['subscriptions_skipped']:,}",
            reply_markup=keyboard
        )
    
    async def _handle_stop_collect(self, query):
        """Handle stop collection"""
        if not self.collection_manager.active:
            await self._edit_message_safe(query, "⚠️ Collection not active")
            return
        
        await self.collection_manager.stop()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Restart", callback_data="start_collect"),
             InlineKeyboardButton("📊 Statistics", callback_data="show_stats")]
        ])
        
        await self._edit_message_safe(
            query,
            "⏹️ **Real collection stopped**\n\n"
            "Collection process stopped successfully.\n"
            "All collected links saved.\n\n"
            "**Final Statistics:**\n"
            f"• Total Links: {self.collection_manager.stats['total_collected']:,}\n"
            f"• Valid Groups: {self.collection_manager.stats['valid_groups']:,}\n"
            f"• Channels Skipped: {self.collection_manager.stats['subscriptions_skipped']:,}\n"
            f"• Telegram Links: {self.collection_manager.stats['telegram']:,}\n"
            f"• WhatsApp Links: {self.collection_manager.stats['whatsapp']:,}",
            reply_markup=keyboard
        )
    
    async def _handle_collect_status(self, query):
        """Handle collect status"""
        status = self.collection_manager.get_status()
        
        status_text = (
            f"**📊 Real Collection Status**\n\n"
            f"**Status:** {'🔄 Active - Real Collection' if status['active'] else '🛑 Stopped'}\n"
            f"**Paused:** {'⏸️ Yes' if status['paused'] else '▶️ No'}\n"
            f"**Stop Requested:** {'✅ Yes' if status['stop_requested'] else '❌ No'}\n\n"
            f"**Real Statistics:**\n"
            f"• Links Collected: {status['stats']['total_collected']:,}\n"
            f"• Valid Groups: {status['stats']['valid_groups']:,}\n"
            f"• Channels Skipped: {status['stats']['subscriptions_skipped']:,}\n"
            f"• Telegram: {status['stats']['telegram']:,}\n"
            f"• WhatsApp: {status['stats']['whatsapp']:,}\n"
            f"• Discord: {status['stats']['discord']:,}\n"
            f"• Signal: {status['stats']['signal']:,}\n"
            f"• Errors: {status['stats']['errors']:,}\n"
            f"• Sessions Used: {status['stats']['sessions_used']}\n"
            f"• Last Collection: {status['stats']['last_collection_time'] or 'Not started'}"
        )
        
        await self._edit_message_safe(query, status_text)
    
    async def _handle_collect_settings(self, query):
        """Handle collect settings"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Change Limits", callback_data="change_limits"),
             InlineKeyboardButton("⏱️ Adjust Delays", callback_data="adjust_delays")],
            [InlineKeyboardButton("🔄 Back", callback_data="manage_collect")]
        ])
        
        settings_text = (
            f"**⚙️ Real Collection Settings**\n\n"
            f"**Current Settings:**\n"
            f"• Max Sessions: {Config.MAX_CONCURRENT_SESSIONS}\n"
            f"• Dialogs per Session: {Config.MAX_DIALOGS_PER_SESSION}\n"
            f"• Messages per Search: {Config.MAX_MESSAGES_PER_SEARCH}\n"
            f"• Links per Cycle: {Config.MAX_LINKS_PER_CYCLE}\n\n"
            f"**Filter Settings:**\n"
            f"• Collect Groups Only: {'✅ Yes' if Config.COLLECT_ONLY_GROUPS else '❌ No'}\n"
            f"• Minimum Members: {Config.MIN_MEMBERS_FOR_GROUP}\n"
            f"• Deep Collection: {'✅ Enabled' if Config.ENABLE_DEEP_COLLECTION else '❌ Disabled'}\n"
            f"• Messages in Deep Collection: {Config.MAX_DEEP_MESSAGES}\n\n"
            f"**Delays:**\n"
            f"• Between Sessions: {Config.REQUEST_DELAYS['between_sessions']} seconds\n"
            f"• Between Tasks: {Config.REQUEST_DELAYS['between_tasks']} seconds\n"
            f"• Between Cycles: {Config.REQUEST_DELAYS['min_cycle_delay']}-{Config.REQUEST_DELAYS['max_cycle_delay']} seconds\n\n"
            f"**Result Settings:**\n"
            f"• ✅ Groups with (join request) → **Collected**\n"
            f"• ❌ Channels with (subscription) → **Skipped**\n"
            f"• ✅ Links from inside groups → **Collected**"
        )
        
        await self._edit_message_safe(query, settings_text, reply_markup=keyboard)
    
    async def _handle_add_session(self, query):
        """Handle add session"""
        user = query.from_user
        self.user_states[user.id] = {'waiting_for_session': True}
        
        add_text = (
            f"**➕ Add New Session**\n\n"
            f"**Send session string now:**\n"
            f"(You can copy full code and send)\n\n"
            f"**Notes:**\n"
            f"• Session stored encrypted\n"
            f"• You can add up to {Config.MAX_SESSIONS_PER_USER} sessions\n"
            f"• Session must be active\n"
            f"• Used only for collecting links from groups"
        )
        
        await self._edit_message_safe(query, add_text)
    
    async def _handle_show_sessions(self, query):
        """Handle show sessions"""
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=20)
        
        if not sessions:
            await self._edit_message_safe(query, "❌ No active sessions")
            return
        
        sessions_text = f"**👥 Active Sessions ({len(sessions)})**\n\n"
        
        for i, session in enumerate(sessions, 1):
            display_name = session.get('display_name', 'Unknown')
            username = session.get('username', 'No username')
            uses = session.get('total_uses', 0)
            links_collected = session.get('total_links', 0)
            
            sessions_text += f"**{i}. {display_name}** (@{username}) - Uses: {uses} - Links: {links_collected:,}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Session", callback_data="add_session"),
             InlineKeyboardButton("🗑️ Delete Session", callback_data="delete_session")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_sessions")]
        ])
        
        await self._edit_message_safe(query, sessions_text, reply_markup=keyboard)
    
    async def _handle_show_stats(self, query):
        """Handle show stats"""
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        
        stats_text = (
            f"**📈 Real System Statistics**\n\n"
            f"**Database Statistics:**\n"
            f"• 🔗 Total Links: {db_stats.get('total_links', 0):,}\n"
            f"• ✅ Valid Groups: {db_stats.get('valid_groups', 0):,}\n"
            f"• 📺 Channels: {db_stats.get('subscriptions', 0):,}\n"
            f"• 💼 Active Sessions: {db_stats.get('active_sessions', 0)}\n"
            f"• 👥 Users: {db_stats.get('total_users', 0)}\n"
            f"• Validity Rate: {(db_stats.get('valid_groups', 0)/db_stats.get('total_links', 1)*100 if db_stats.get('total_links', 0) > 0 else 0):.1f}%\n\n"
            f"**Platform Distribution (valid groups only):**\n"
        )
        
        for platform, count in db_stats.get('links_by_platform', {}).items():
            stats_text += f"• {platform}: {count:,}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="show_stats"),
             InlineKeyboardButton("📊 Collection Stats", callback_data="collect_status")]
        ])
        
        await self._edit_message_safe(query, stats_text, reply_markup=keyboard)
    
    async def _handle_export_links(self, query):
        """Handle export links"""
        db = await EnhancedDatabaseManager.get_instance()
        total_links = await db.get_links_count()
        
        if total_links == 0:
            await self._edit_message_safe(query, "❌ No valid links to export")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Text", callback_data="export_txt"),
             InlineKeyboardButton("📊 CSV", callback_data="export_csv")],
            [InlineKeyboardButton("📋 JSON", callback_data="export_json"),
             InlineKeyboardButton("📦 All Links", callback_data="export_all")],
            [InlineKeyboardButton("📢 Telegram", callback_data="export_telegram"),
             InlineKeyboardButton("📱 WhatsApp", callback_data="export_whatsapp")],
            [InlineKeyboardButton("🎮 Discord", callback_data="export_discord"),
             InlineKeyboardButton("📡 Signal", callback_data="export_signal")]
        ])
        
        export_text = (
            f"**📤 Export Valid Links**\n\n"
            f"Total Valid Links: **{total_links:,}**\n\n"
            f"Choose export format:"
        )
        
        await self._edit_message_safe(query, export_text, reply_markup=keyboard)
    
    async def _handle_export_txt(self, query):
        """Handle export as text"""
        try:
            await query.edit_message_text("⏳ Preparing file...")
            message = query.message
            
            db = await EnhancedDatabaseManager.get_instance()
            
            # Use direct SQL to ensure getting links
            cursor = await db.conn.execute('''
                SELECT url FROM links 
                WHERE is_valid_group = 1 
                ORDER BY collected_date DESC 
                LIMIT ?
            ''', (Config.MAX_EXPORT_LINKS,))
            
            rows = await cursor.fetchall()
            links = [row[0] for row in rows] if rows else []
            
            if not links:
                await message.reply_text("❌ No valid links to export")
                return
            
            # Check links actually exist
            logger.info(f"📊 Exporting {len(links)} links")
            
            # Save to text file
            filename = f"valid_groups_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📄 Text Export File\nLinks: {len(links):,}"
                )
            
            # Delete local file
            try:
                os.remove(filepath)
            except:
                pass
            
        except Exception as e:
            logger.error(f"❌ Text export error: {e}", exc_info=True)
            error_message = f"❌ Export error: {str(e)[:100]}"
            
            if 'message' in locals():
                await message.reply_text(error_message)
            else:
                await query.edit_message_text(error_message)
    
    async def _handle_export_csv(self, query):
        """Handle export as CSV"""
        try:
            await query.edit_message_text("⏳ Preparing file...")
            message = query.message
            
            db = await EnhancedDatabaseManager.get_instance()
            cursor = await db.conn.execute('''
                SELECT url, platform, link_type, members_count, collected_date 
                FROM links 
                WHERE is_valid_group = 1 
                LIMIT ?
            ''', (Config.MAX_EXPORT_LINKS,))
            
            rows = await cursor.fetchall()
            
            if not rows:
                await message.reply_text("❌ No valid links to export")
                return
            
            # Save to CSV file
            filename = f"valid_groups_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("URL,Platform,Type,Members,Date\n")
                for row in rows:
                    url, platform, link_type, members, date = row
                    f.write(f'"{url}","{platform}","{link_type}",{members},"{date}"\n')
            
            # Send file
            with open(filepath, 'rb') as f:
                await message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📊 CSV Export File\nRecords: {len(rows):,}"
                )
            
            # Delete local file
            try:
                os.remove(filepath)
            except:
                pass
            
        except Exception as e:
            logger.error(f"❌ CSV export error: {e}")
            await query.edit_message_text(f"❌ Export error: {str(e)[:100]}")
    
    async def _handle_export_json(self, query):
        """Handle export as JSON"""
        try:
            await query.edit_message_text("⏳ Preparing file...")
            message = query.message
            
            db = await EnhancedDatabaseManager.get_instance()
            cursor = await db.conn.execute('''
                SELECT url, platform, link_type, telegram_type, members_count, 
                       collected_date, is_verified, validation_score 
                FROM links 
                WHERE is_valid_group = 1 
                LIMIT ?
            ''', (Config.MAX_EXPORT_LINKS,))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            if not rows:
                await message.reply_text("❌ No valid links to export")
                return
            
            # Convert to JSON
            data = []
            for row in rows:
                item = dict(zip(columns, row))
                data.append(item)
            
            # Save to JSON file
            filename = f"valid_groups_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Send file
            with open(filepath, 'rb') as f:
                await message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📋 JSON Export File\nRecords: {len(data):,}"
                )
            
            # Delete local file
            try:
                os.remove(filepath)
            except:
                pass
            
        except Exception as e:
            logger.error(f"❌ JSON export error: {e}")
            await query.edit_message_text(f"❌ Export error: {str(e)[:100]}")
    
    async def _handle_export_all(self, query):
        """Handle export all links"""
        await self._handle_export_txt(query)
    
    async def _handle_export_telegram(self, query):
        """Handle export Telegram links"""
        try:
            await query.edit_message_text("⏳ Preparing file...")
            message = query.message
            
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links({'platform': 'telegram'}, Config.MAX_EXPORT_LINKS)
            
            if not links:
                await message.reply_text("❌ No valid Telegram links to export")
                return
            
            # Save to text file
            filename = f"telegram_groups_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📢 Telegram Links\nLinks: {len(links):,}"
                )
            
            # Delete local file
            try:
                os.remove(filepath)
            except:
                pass
            
        except Exception as e:
            logger.error(f"❌ Telegram export error: {e}")
            await query.edit_message_text(f"❌ Export error: {str(e)[:100]}")
    
    async def _handle_export_whatsapp(self, query):
        """Handle export WhatsApp links"""
        try:
            await query.edit_message_text("⏳ Preparing file...")
            message = query.message
            
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links({'platform': 'whatsapp'}, Config.MAX_EXPORT_LINKS)
            
            if not links:
                await message.reply_text("❌ No valid WhatsApp links to export")
                return
            
            # Save to text file
            filename = f"whatsapp_groups_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📱 WhatsApp Links\nLinks: {len(links):,}"
                )
            
            # Delete local file
            try:
                os.remove(filepath)
            except:
                pass
            
        except Exception as e:
            logger.error(f"❌ WhatsApp export error: {e}")
            await query.edit_message_text(f"❌ Export error: {str(e)[:100]}")
    
    async def _handle_export_discord(self, query):
        """Handle export Discord links"""
        try:
            await query.edit_message_text("⏳ Preparing file...")
            message = query.message
            
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links({'platform': 'discord'}, Config.MAX_EXPORT_LINKS)
            
            if not links:
                await message.reply_text("❌ No valid Discord links to export")
                return
            
            # Save to text file
            filename = f"discord_groups_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"🎮 Discord Links\nLinks: {len(links):,}"
                )
            
            # Delete local file
            try:
                os.remove(filepath)
            except:
                pass
            
        except Exception as e:
            logger.error(f"❌ Discord export error: {e}")
            await query.edit_message_text(f"❌ Export error: {str(e)[:100]}")
    
    async def _handle_export_signal(self, query):
        """Handle export Signal links"""
        try:
            await query.edit_message_text("⏳ Preparing file...")
            message = query.message
            
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links({'platform': 'signal'}, Config.MAX_EXPORT_LINKS)
            
            if not links:
                await message.reply_text("❌ No valid Signal links to export")
                return
            
            # Save to text file
            filename = f"signal_groups_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📡 Signal Links\nLinks: {len(links):,}"
                )
            
            # Delete local file
            try:
                os.remove(filepath)
            except:
                pass
            
        except Exception as e:
            logger.error(f"❌ Signal export error: {e}")
            await query.edit_message_text(f"❌ Export error: {str(e)[:100]}")
    
    async def _handle_export_test(self, query):
        """Handle export test links"""
        try:
            await query.edit_message_text("⏳ Preparing file...")
            message = query.message
            
            db = await EnhancedDatabaseManager.get_instance()
            cursor = await db.conn.execute('''
                SELECT url FROM links 
                WHERE source = 'test_collection' 
                ORDER BY collected_date DESC 
                LIMIT 100
            ''')
            
            rows = await cursor.fetchall()
            
            if not rows:
                await message.reply_text("❌ No test links to export")
                return
            
            links = [row[0] for row in rows]
            
            # Save to text file
            filename = f"test_collection_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"🧪 Test Links\nLinks: {len(links):,}"
                )
            
            # Delete local file
            try:
                os.remove(filepath)
            except:
                pass
            
        except Exception as e:
            logger.error(f"❌ Test export error: {e}")
            await query.edit_message_text(f"❌ Export error: {str(e)[:100]}")
    
    async def _handle_export_valid(self, query):
        """Handle export valid groups only"""
        await self._handle_export_txt(query)
    
    async def _handle_delete_invalid(self, query):
        """Handle delete invalid links"""
        await self._edit_message_safe(query, "⏳ Deleting invalid links...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            # Count before deletion
            cursor = await db.conn.execute("SELECT COUNT(*) FROM links WHERE is_valid_group = 0")
            count_before = (await cursor.fetchone())[0]
            
            if count_before == 0:
                await self._edit_message_safe(query, "✅ No invalid links to delete")
                return
            
            # Delete invalid links
            await db.conn.execute("DELETE FROM links WHERE is_valid_group = 0")
            await db.conn.commit()
            
            # Count after deletion
            cursor = await db.conn.execute("SELECT COUNT(*) FROM links")
            count_after = (await cursor.fetchone())[0]
            
            await self._edit_message_safe(
                query,
                f"✅ **Invalid links deleted successfully**\n\n"
                f"**Statistics:**\n"
                f"• Deleted Links: {count_before:,}\n"
                f"• Remaining Links: {count_after:,}\n"
                f"• Space Saved: {count_before} records\n\n"
                f"**Note:**\n"
                f"Deleted all channels and subscription links\n"
                f"Only valid groups remain for use"
            )
            
        except Exception as e:
            logger.error(f"❌ Error deleting invalid links: {e}")
            await self._edit_message_safe(query, f"❌ Deletion error: {str(e)[:100]}")
    
    async def _handle_create_backup(self, query):
        """Handle create backup"""
        await self._edit_message_safe(query, "⏳ Creating backup...")
        
        backup = await BackupManager.create_backup()
        
        if backup:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 List Backups", callback_data="list_backups"),
                 InlineKeyboardButton("🔄 Rotate Backups", callback_data="rotate_backups")]
            ])
            
            await self._edit_message_safe(
                query,
                f"✅ **Backup created successfully!**\n\n"
                f"**Backup Details:**\n"
                f"• ID: {backup['backup_id']}\n"
                f"• Time: {backup['timestamp']}\n"
                f"• Size: {backup['size_bytes'] / 1024 / 1024:.2f} MB\n"
                f"• Path: {backup['file_path']}",
                reply_markup=keyboard
            )
        else:
            await self._edit_message_safe(query, "❌ Failed to create backup")
    
    async def _handle_list_backups(self, query):
        """Handle list backups"""
        try:
            if not os.path.exists("backups"):
                await self._edit_message_safe(query, "❌ No backups")
                return
            
            backups = []
            for filename in os.listdir("backups"):
                if filename.startswith("backup_") and filename.endswith(".db"):
                    path = os.path.join("backups", filename)
                    size = os.path.getsize(path) / 1024 / 1024
                    ctime = datetime.fromtimestamp(os.path.getctime(path))
                    backups.append({
                        'filename': filename,
                        'size_mb': size,
                        'created': ctime
                    })
            
            if not backups:
                await self._edit_message_safe(query, "❌ No backups")
                return
            
            backups.sort(key=lambda x: x['created'], reverse=True)
            
            list_text = "**📋 Backup List**\n\n"
            
            for i, backup in enumerate(backups, 1):
                list_text += (
                    f"**{i}. {backup['filename']}**\n"
                    f"• Size: {backup['size_mb']:.2f} MB\n"
                    f"• Date: {backup['created'].strftime('%Y-%m-%d %H:%M')}\n\n"
                )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Rotate Backups", callback_data="rotate_backups"),
                 InlineKeyboardButton("💾 Create Backup", callback_data="create_backup")]
            ])
            
            await self._edit_message_safe(query, list_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"❌ Backup list error: {e}")
            await self._edit_message_safe(query, f"❌ Error: {str(e)[:100]}")
    
    async def _handle_rotate_backups(self, query):
        """Handle rotate backups"""
        await self._edit_message_safe(query, "⏳ Rotating old backups...")
        
        try:
            await BackupManager.rotate_backups()
            await self._edit_message_safe(query, "✅ Backups rotated successfully")
        except Exception as e:
            logger.error(f"❌ Backup rotation error: {e}")
            await self._edit_message_safe(query, f"❌ Error: {str(e)[:100]}")
    
    async def _handle_refresh_status(self, query):
        """Handle refresh status"""
        # Create a fake update object
        class FakeUpdate:
            def __init__(self, query):
                self.message = query.message
                self.effective_user = query.from_user
        
        fake_update = FakeUpdate(query)
        await self.status_command(fake_update, None)
    
    async def _handle_refresh_sessions(self, query):
        """Handle refresh sessions"""
        class FakeUpdate:
            def __init__(self, query):
                self.message = query.message
                self.effective_user = query.from_user
        
        fake_update = FakeUpdate(query)
        await self.sessions_command(fake_update, None)
    
    async def _handle_show_help(self, query):
        """Handle show help"""
        class FakeUpdate:
            def __init__(self, query):
                self.message = query.message
        
        fake_update = FakeUpdate(query)
        await self.help_command(fake_update, None)
    
    async def _handle_show_settings(self, query):
        """Handle show settings"""
        settings_text = (
            f"**⚙️ Real System Settings**\n\n"
            f"**Security Settings:**\n"
            f"• Admins: {len(Config.ADMIN_USER_IDS)}\n"
            f"• Allowed Users: {len(Config.ALLOWED_USER_IDS)}\n"
            f"• Encryption: {'✅ Enabled' if Config.ENCRYPTION_KEY else '❌ Disabled'}\n\n"
            f"**Performance Settings:**\n"
            f"• Concurrent Sessions: {Config.MAX_CONCURRENT_SESSIONS}\n"
            f"• Max Memory: {Config.MAX_MEMORY_MB} MB\n\n"
            f"**Database Settings:**\n"
            f"• Path: {Config.DB_PATH}\n"
            f"• Backup: {'✅ Enabled' if Config.BACKUP_ENABLED else '❌ Disabled'}\n"
            f"• Backups Kept: {Config.MAX_BACKUPS}\n\n"
            f"**Real Collection Settings:**\n"
            f"• Collect Groups Only: {'✅ Yes' if Config.COLLECT_ONLY_GROUPS else '❌ No'}\n"
            f"• Minimum Members: {Config.MIN_MEMBERS_FOR_GROUP}\n"
            f"• Deep Collection: {'✅ Enabled' if Config.ENABLE_DEEP_COLLECTION else '❌ Disabled'}\n"
            f"• No Time Limit: {'✅ Yes' if Config.TELEGRAM_NO_TIME_LIMIT else '❌ No'}\n"
            f"• WhatsApp Days: {Config.WHATSAPP_DAYS_BACK}"
        )
        
        await self._edit_message_safe(query, settings_text)
    
    async def _handle_manage_collect(self, query):
        """Handle manage collect"""
        class FakeUpdate:
            def __init__(self, query):
                self.message = query.message
                self.effective_user = query.from_user
        
        fake_update = FakeUpdate(query)
        await self.collect_command(fake_update, None)
    
    async def _handle_delete_session(self, query):
        """Handle delete session"""
        await self._edit_message_safe(query, "⏳ Preparing session list...")
        
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=10)
        
        if not sessions:
            await self._edit_message_safe(query, "❌ No sessions")
            return
        
        keyboard_buttons = []
        for session in sessions:
            name = session.get('display_name', f"Session {session['id']}")
            callback_data = f"delete_session_{session['id']}"
            keyboard_buttons.append([InlineKeyboardButton(f"🗑️ {name}", callback_data=callback_data)])
        
        keyboard_buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="show_sessions")])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await self._edit_message_safe(
            query,
            "**🗑️ Delete Sessions**\n\n"
            "Choose session to delete:\n\n"
            "**Warning:**\n"
            "• Cannot restore session after deletion\n"
            "• Collected links remain saved\n"
            "• You can add session again",
            reply_markup=keyboard
        )
    
    async def _handle_delete_session_confirm(self, query, data):
        """Handle delete session confirmation"""
        try:
            session_id = int(data.split('_')[2])
            
            db = await EnhancedDatabaseManager.get_instance()
            
            # Get session info
            cursor = await db.conn.execute(
                'SELECT display_name FROM sessions WHERE id = ?',
                (session_id,)
            )
            session_info = await cursor.fetchone()
            
            if not session_info:
                await self._edit_message_safe(query, "❌ Session not found")
                return
            
            # Delete session
            await db.conn.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
            await db.conn.commit()
            
            await self._edit_message_safe(
                query,
                f"✅ **Session deleted successfully**\n\n"
                f"• Session: {session_info[0]}\n"
                f"• Session ID: {session_id}\n\n"
                f"**Note:**\n"
                f"Session deleted permanently\n"
                f"Links collected remain saved\n"
                f"You can add new session anytime"
            )
            
        except Exception as e:
            logger.error(f"❌ Session deletion error: {e}")
            await self._edit_message_safe(query, f"❌ Session deletion error: {str(e)[:100]}")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        user = update.effective_user
        text = update.message.text
        
        # Check access
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ Access denied")
                return
        
        # Check user state
        user_state = self.user_states.get(user.id, {})
        
        if user_state.get('waiting_for_session'):
            await self._handle_session_input(update, text)
        else:
            await update.message.reply_text(
                "Hello! You can use these commands:\n"
                "/start - Start bot\n"
                "/help - Help\n"
                "/status - System status\n"
                "/test_collect - Test collection\n"
                "/collect - Start real collection\n"
                "Or use buttons from welcome message."
            )
    
    async def _handle_session_input(self, update: Update, session_string: str):
        """Handle session string input"""
        user = update.effective_user
        
        # Delete user state
        if user.id in self.user_states:
            del self.user_states[user.id]
        
        await update.message.reply_text("⏳ Validating session...")
        
        # Validate session
        valid, result = await SessionManager.validate_session(session_string)
        
        if not valid:
            await update.message.reply_text(f"❌ Invalid session: {result.get('error', 'Unknown error')}")
            return
        
        user_info = result.get('user_info', {})
        
        # Encrypt session
        enc_manager = EncryptionManager.get_instance()
        encrypted_session = enc_manager.encrypt(session_string)
        
        # Save session to database
        session_data = {
            'session_string': encrypted_session,
            'phone_number': user_info.get('phone', ''),
            'user_id': user_info.get('id', 0),
            'username': user_info.get('username', ''),
            'display_name': f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip(),
            'added_by_user': user.id,
            'metadata': {
                'validated_at': datetime.now().isoformat(),
                'original_length': len(session_string),
                'purpose': 'real_group_collection'
            }
        }
        
        db = await EnhancedDatabaseManager.get_instance()
        success, message, details = await db.add_session(session_data)
        
        if success:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Start Real Collection", callback_data="start_collect"),
                 InlineKeyboardButton("🧪 Test Collection", callback_data="test_collection")]
            ])
            
            await update.message.reply_text(
                f"✅ **Session added successfully!**\n\n"
                f"**User Info:**\n"
                f"• Name: {session_data['display_name']}\n"
                f"• Username: @{session_data['username']}\n"
                f"• Phone: {session_data['phone_number']}\n\n"
                f"**Session:**\n"
                f"• Encrypted and stored securely\n"
                f"• Ready for real collection\n"
                f"• Session ID: {details.get('session_id')}\n\n"
                f"**Note:**\n"
                f"This session will only collect links\n"
                f"from active groups (join request)\n"
                f"and will skip channels and subscription links",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ Failed to add session: {message}")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        try:
            error = context.error
            
            logger.error(f"Unhandled error: {error}", exc_info=True)
            
            # Handle Conflict error (duplicate bot)
            if isinstance(error, Conflict):
                logger.error("⚠️ Another bot instance detected!")
                
                await asyncio.sleep(2)
                
                try:
                    await context.application.stop()
                    await context.application.initialize()
                    await context.application.start()
                    logger.info("✅ Bot restarted after conflict resolution")
                except Exception as restart_error:
                    logger.error(f"Restart failed: {restart_error}")
                
                return
            
            if update and update.effective_chat:
                error_message = (
                    "❌ **Unexpected error occurred**\n\n"
                    "We encountered a technical issue. Try again later.\n\n"
                    "You can use /start to return to main menu."
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
            logger.error(f"Error in error handler: {e}")

# ======================
# Health Check Server
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
        logger.info(f"Started health check server on port {self.port}")
    
    def stop(self):
        """Stop server"""
        if self.server_thread:
            logger.info("Stopping health check server")

# ======================
# Single Instance Manager
# ======================

class SingleInstanceManager:
    """Prevent multiple instances of bot"""
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
        """Acquire lock to ensure single instance"""
        async with self._lock:
            if self._is_running:
                logger.error("⚠️ Another bot instance detected!")
                return False
            self._is_running = True
            return True
    
    async def release_lock(self):
        """Release lock"""
        async with self._lock:
            self._is_running = False
    
    def is_running(self) -> bool:
        """Check if bot is running"""
        return self._is_running

# ======================
# Startup Tasks
# ======================

async def startup_tasks():
    """Run startup tasks"""
    logger.info("🔄 Running startup tasks...")
    
    # Check database
    await check_and_repair_database()
    
    # Create folders if they don't exist
    os.makedirs("backups", exist_ok=True)
    os.makedirs("exports", exist_ok=True)
    os.makedirs("cache_data", exist_ok=True)
    
    logger.info("✅ Startup tasks completed")

# ======================
# Main Function
# ======================

async def main():
    """Main function"""
    try:
        # Check required environment variables
        required_env_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH']
        missing = [var for var in required_env_vars if not os.getenv(var)]
        
        if missing:
            logger.error(f"❌ Missing environment variables: {missing}")
            print(f"❌ Error: Missing environment variables: {', '.join(missing)}")
            sys.exit(1)
        
        # Check single instance
        instance_manager = await SingleInstanceManager.get_instance()
        if not await instance_manager.acquire_lock():
            logger.error("❌ Another bot instance already running!")
            print("❌ Error: Another bot instance running. Closing...")
            sys.exit(1)
        
        # Run startup tasks
        await startup_tasks()
        
        # Start health server
        health_server = HealthCheckServer(port=8080)
        health_server.start()
        
        # Initialize database
        db = await EnhancedDatabaseManager.get_instance()
        
        # Create bot
        bot = TelegramBot()
        
        logger.info("🤖 Starting Real Link Collector Bot...")
        logger.info(f"🔥 Enhanced Settings - Real collection from active groups")
        logger.info(f"⚙️ Collect Groups Only: {Config.COLLECT_ONLY_GROUPS}")
        logger.info(f"⚙️ Skip Channels: Yes")
        logger.info(f"⚙️ Minimum Members: {Config.MIN_MEMBERS_FOR_GROUP}")
        
        try:
            # Run bot
            await bot.app.initialize()
            await bot.app.start()
            await bot.app.updater.start_polling()
            
            logger.info("✅ Bot running successfully!")
            logger.info("📋 Available commands: /start, /test_collect, /collect, /status, /stats, /export")
            
            # Keep bot running
            stop_event = asyncio.Event()
            await stop_event.wait()
            
        except KeyboardInterrupt:
            logger.info("👋 Bot stopped by user")
        except Exception as e:
            logger.error(f"❌ Bot error: {e}", exc_info=True)
            raise
            
        finally:
            logger.info("🧹 Final cleanup...")
            
            try:
                # Stop bot
                if hasattr(bot, 'app'):
                    await bot.app.stop()
                
                # Close database
                await db.close()
                
                # Stop health server
                health_server.stop()
                
                # Release instance lock
                await instance_manager.release_lock()
                
                logger.info("✅ Clean shutdown completed")
                
            except Exception as e:
                logger.error(f"❌ Cleanup error: {e}")
    
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)

# ======================
# Signal Handlers
# ======================

def setup_signal_handlers():
    """Setup signal handlers"""
    def signal_handler(signum, frame):
        logger.info(f"📶 Received signal {signum}. Graceful shutdown...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# ======================
# Entry Point
# ======================

if __name__ == "__main__":
    # Setup signal handlers
    setup_signal_handlers()
    
    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
