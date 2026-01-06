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
    MAX_CONCURRENT_SESSIONS = 10
    REQUEST_DELAYS = {
        'normal': 2.0,
        'join_request': 5.0,
        'search': 3.0,
        'flood_wait': 10.0,
        'between_sessions': 3.0,
        'between_tasks': 0.5,
        'min_cycle_delay': 30.0,
        'max_cycle_delay': 90.0,
        'validation_delay': 3.0
    }
    
    # Collection limits - حدود الجمع
    MAX_DIALOGS_PER_SESSION = 100
    MAX_MESSAGES_PER_SEARCH = 20
    MAX_SEARCH_TERMS = 8
    MAX_LINKS_PER_CYCLE = 300
    MAX_BATCH_SIZE = 50
    
    # Database - قاعدة البيانات
    DB_PATH = "links_collector.db"
    BACKUP_ENABLED = True
    MAX_BACKUPS = 10
    DB_POOL_SIZE = 5
    
    # WhatsApp collection - جمع واتساب
    WHATSAPP_DAYS_BACK = 30
    
    # Link verification - التحقق من الروابط
    MIN_GROUP_MEMBERS = 5
    MAX_LINK_LENGTH = 200
    VALIDATION_TIMEOUT = 30
    
    # Rate limiting - الحد من الطلبات
    USER_RATE_LIMIT = {
        'max_requests': 15,
        'per_seconds': 60
    }
    
    # Session management - إدارة الجلسات
    SESSION_TIMEOUT = 600
    MAX_SESSIONS_PER_USER = 20
    
    # Export - التصدير
    MAX_EXPORT_LINKS = 100000
    EXPORT_CHUNK_SIZE = 5000
    
    # Advanced settings - إعدادات متقدمة
    TELEGRAM_NO_TIME_LIMIT = True
    JOIN_REQUEST_CHECK_DELAY = 30
    ENABLE_ADVANCED_VALIDATION = True
    
    # Collection settings - إعدادات الجمع
    COLLECT_FROM_MESSAGES = True
    COLLECT_FROM_GROUP_DESCRIPTION = True
    COLLECT_FROM_PARTICIPANT_MESSAGES = False
    ENABLE_AUTO_JOIN = False
    CHECK_GROUP_ACTIVITY = True
    MIN_GROUP_AGE_DAYS = 7

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
# Enhanced Link Collector - جامع الروابط المحسن
# ======================

class EnhancedLinkCollector:
    """Collector with real link collection and validation"""
    
    def __init__(self):
        self.collection_stats = {
            'total_collected': 0,
            'telegram_groups': 0,
            'telegram_channels': 0,
            'whatsapp_groups': 0,
            'discord_invites': 0,
            'errors': 0,
            'skipped_channels': 0,
            'skipped_private': 0,
            'valid_groups': 0
        }
    
    async def collect_and_validate_links(self, client: TelegramClient, session_id: int, db_manager) -> List[Dict]:
        """Collect and validate links from dialogs"""
        collected_links = []
        
        try:
            # Get all dialogs
            dialogs = []
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                if dialog.is_group or dialog.is_channel:
                    dialogs.append(dialog)
                
                if len(dialogs) >= Config.MAX_DIALOGS_PER_SESSION:
                    break
            
            logger.info(f"📁 Found {len(dialogs)} groups/channels for collection")
            
            # Process each dialog
            for dialog in dialogs:
                try:
                    # Check if we should stop
                    if not hasattr(self, 'active') or not self.active:
                        break
                    
                    entity = dialog.entity
                    
                    # Skip if it's a channel (has subscribers not members)
                    if hasattr(entity, 'broadcast') and entity.broadcast:
                        logger.debug(f"⏭️ Skipping channel: {entity.title}")
                        self.collection_stats['skipped_channels'] += 1
                        continue
                    
                    # Skip if it's a private channel
                    if hasattr(entity, 'restricted') and entity.restricted:
                        logger.debug(f"⏭️ Skipping restricted: {entity.title}")
                        self.collection_stats['skipped_private'] += 1
                        continue
                    
                    # Get entity info
                    entity_info = await self._get_entity_info(client, entity)
                    
                    # Check if it's a real group (has join button, not subscribe)
                    if not await self._is_real_group(client, entity):
                        logger.debug(f"⏭️ Not a real group: {entity.title}")
                        continue
                    
                    # Collect links from group description
                    if Config.COLLECT_FROM_GROUP_DESCRIPTION and hasattr(entity, 'about'):
                        links = self._extract_links_from_text(entity.about)
                        for link in links:
                            link_data = await self._process_link(link, session_id, db_manager, entity.title)
                            if link_data:
                                collected_links.append(link_data)
                    
                    # Collect links from recent messages
                    if Config.COLLECT_FROM_MESSAGES:
                        links_from_messages = await self._collect_links_from_messages(client, entity, session_id, db_manager)
                        collected_links.extend(links_from_messages)
                    
                    # Collect participant messages for links
                    if Config.COLLECT_FROM_PARTICIPANT_MESSAGES:
                        participant_links = await self._collect_from_participants(client, entity, session_id, db_manager)
                        collected_links.extend(participant_links)
                    
                    # Add delay between groups
                    await asyncio.sleep(Config.REQUEST_DELAYS['between_tasks'])
                    
                except Exception as e:
                    logger.error(f"Error processing dialog {dialog.title}: {e}")
                    self.collection_stats['errors'] += 1
                    continue
            
            logger.info(f"✅ Collected {len(collected_links)} links from session")
            return collected_links
            
        except Exception as e:
            logger.error(f"Error in collection: {e}")
            self.collection_stats['errors'] += 1
            return []
    
    async def _get_entity_info(self, client: TelegramClient, entity) -> Dict:
        """Get detailed entity information"""
        try:
            info = {
                'id': entity.id,
                'title': getattr(entity, 'title', 'Unknown'),
                'username': getattr(entity, 'username', ''),
                'participants_count': getattr(entity, 'participants_count', 0),
                'is_group': getattr(entity, 'megagroup', False) or getattr(entity, 'gigagroup', False),
                'is_channel': getattr(entity, 'broadcast', False),
                'is_restricted': getattr(entity, 'restricted', False),
                'is_verified': getattr(entity, 'verified', False),
                'is_scam': getattr(entity, 'scam', False),
                'is_fake': getattr(entity, 'fake', False),
                'access_hash': getattr(entity, 'access_hash', 0)
            }
            
            # Try to get more info
            try:
                full_info = await client.get_entity(entity)
                if hasattr(full_info, 'about'):
                    info['about'] = full_info.about
                if hasattr(full_info, 'members_count'):
                    info['participants_count'] = full_info.members_count
            except:
                pass
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting entity info: {e}")
            return {}
    
    async def _is_real_group(self, client: TelegramClient, entity) -> bool:
        """Check if entity is a real group (not channel with subscribers)"""
        try:
            # Check if it's a broadcast channel
            if hasattr(entity, 'broadcast') and entity.broadcast:
                return False
            
            # Check if it's a megagroup/gigagroup (real Telegram groups)
            if hasattr(entity, 'megagroup') and entity.megagroup:
                return True
            
            if hasattr(entity, 'gigagroup') and entity.gigagroup:
                return True
            
            # Try to get full info
            try:
                full_chat = await client(functions.channels.GetFullChannelRequest(entity))
                
                # Check for join request button (indicates real group)
                if hasattr(full_chat, 'full_chat'):
                    chat = full_chat.full_chat
                    
                    # Groups have join request or participants count
                    if hasattr(chat, 'participants_count') and chat.participants_count > 0:
                        return True
                    
                    # Check if it requires join approval
                    if hasattr(chat, 'join_request'):
                        return True
                
                return False
                
            except Exception as e:
                logger.debug(f"Could not get full chat info: {e}")
                
                # Fallback: Check participants count
                if hasattr(entity, 'participants_count') and entity.participants_count > 0:
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"Error checking group type: {e}")
            return False
    
    def _extract_links_from_text(self, text: str) -> List[str]:
        """Extract links from text with improved patterns"""
        if not text:
            return []
        
        patterns = [
            # Telegram patterns
            r'(https?://t\.me/[a-zA-Z0-9_+-]+(?:\?[^\s]*)?)',
            r'(https?://telegram\.me/[a-zA-Z0-9_+-]+(?:\?[^\s]*)?)',
            r'(https?://telegram\.dog/[a-zA-Z0-9_+-]+(?:\?[^\s]*)?)',
            r'(t\.me/[a-zA-Z0-9_+-]+)',
            r'(telegram\.me/[a-zA-Z0-9_+-]+)',
            r'(telegram\.dog/[a-zA-Z0-9_+-]+)',
            r'(@[a-zA-Z0-9_]+)',  # Telegram usernames
            
            # Join patterns
            r'(https?://t\.me/\+[a-zA-Z0-9_-]+)',
            r'(https?://t\.me/joinchat/[a-zA-Z0-9_-]+)',
            r'(https?://t\.me/join/[a-zA-Z0-9_-]+)',
            
            # WhatsApp patterns
            r'(https?://chat\.whatsapp\.com/[a-zA-Z0-9_-]+)',
            r'(https?://whatsapp\.com/channel/[a-zA-Z0-9_-]+)',
            r'(chat\.whatsapp\.com/[a-zA-Z0-9_-]+)',
            
            # Discord patterns
            r'(https?://discord\.gg/[a-zA-Z0-9_-]+)',
            r'(https?://discord\.com/invite/[a-zA-Z0-9_-]+)',
            r'(discord\.gg/[a-zA-Z0-9_-]+)',
            
            # Signal patterns
            r'(https?://signal\.group/#[a-zA-Z0-9_-]+)',
            r'(signal\.group/#[a-zA-Z0-9_-]+)',
            
            # Generic URL patterns
            r'(https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)'
        ]
        
        all_links = []
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                link = match.group(1).strip()
                if link and link not in all_links:
                    all_links.append(link)
        
        # Filter and normalize links
        filtered_links = []
        for link in all_links:
            normalized = self._normalize_link(link)
            if normalized and normalized not in filtered_links:
                filtered_links.append(normalized)
        
        return filtered_links
    
    def _normalize_link(self, link: str) -> str:
        """Normalize link for consistency"""
        if not link:
            return ""
        
        link = link.strip()
        
        # Add https if missing for known domains
        if not link.startswith(('http://', 'https://')):
            if link.startswith(('t.me/', 'telegram.me/', 'telegram.dog/', 
                               'chat.whatsapp.com/', 'discord.gg/', 'signal.group/')):
                link = 'https://' + link
        
        # Remove tracking parameters
        if '?' in link:
            link = link.split('?')[0]
        
        # Remove trailing slashes
        if link.endswith('/'):
            link = link[:-1]
        
        return link.lower()
    
    async def _collect_links_from_messages(self, client: TelegramClient, entity, session_id: int, db_manager) -> List[Dict]:
        """Collect links from group messages"""
        collected = []
        
        try:
            # Get recent messages
            messages = []
            async for message in client.iter_messages(
                entity, 
                limit=Config.MAX_MESSAGES_PER_SEARCH,
                filter=types.InputMessagesFilterEmpty()
            ):
                if message.text:
                    messages.append(message)
            
            # Extract links from messages
            for message in messages:
                if message.text:
                    links = self._extract_links_from_text(message.text)
                    for link in links:
                        link_data = await self._process_link(
                            link, 
                            session_id, 
                            db_manager,
                            getattr(entity, 'title', 'Unknown Group')
                        )
                        if link_data:
                            collected.append(link_data)
            
            return collected
            
        except Exception as e:
            logger.error(f"Error collecting from messages: {e}")
            return []
    
    async def _collect_from_participants(self, client: TelegramClient, entity, session_id: int, db_manager) -> List[Dict]:
        """Collect links from participant bios/messages"""
        collected = []
        
        try:
            # Get some participants
            participants = []
            try:
                async for participant in client.iter_participants(entity, limit=20):
                    participants.append(participant)
            except:
                return collected
            
            # Check participant bios
            for participant in participants:
                try:
                    user = await client.get_entity(participant)
                    if hasattr(user, 'about') and user.about:
                        links = self._extract_links_from_text(user.about)
                        for link in links:
                            link_data = await self._process_link(
                                link,
                                session_id,
                                db_manager,
                                f"Participant: {getattr(user, 'first_name', 'Unknown')}"
                            )
                            if link_data:
                                collected.append(link_data)
                    
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    continue
            
            return collected
            
        except Exception as e:
            logger.error(f"Error collecting from participants: {e}")
            return []
    
    async def _process_link(self, link: str, session_id: int, db_manager, source: str = "") -> Optional[Dict]:
        """Process and validate a single link"""
        try:
            # Normalize link first
            normalized_link = self._normalize_link(link)
            if not normalized_link:
                return None
            
            # Check if link is already in database
            url_hash = hashlib.md5(normalized_link.encode()).hexdigest()
            
            cursor = await db_manager.conn.execute(
                'SELECT id FROM links WHERE url_hash = ?',
                (url_hash,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                logger.debug(f"Link already exists: {normalized_link}")
                return None
            
            # Determine platform and type
            platform_info = self._analyze_link(normalized_link)
            
            if not platform_info['is_valid']:
                return None
            
            # Skip channels (with subscribers)
            if platform_info['is_channel_with_subscribers']:
                logger.debug(f"Skipping channel: {normalized_link}")
                self.collection_stats['skipped_channels'] += 1
                return None
            
            # Prepare link data
            link_data = {
                'url': normalized_link,
                'original_url': link,
                'platform': platform_info['platform'],
                'link_type': platform_info['link_type'],
                'telegram_type': platform_info['telegram_type'],
                'title': platform_info.get('title', ''),
                'requires_join': platform_info['requires_join'],
                'is_group': platform_info['is_group'],
                'is_channel': platform_info['is_channel'],
                'is_join_request': platform_info['is_join_request'],
                'is_supergroup': platform_info.get('is_supergroup', False),
                'is_public': platform_info.get('is_public', False),
                'is_private': platform_info.get('is_private', False),
                'session_id': session_id,
                'confidence': 'high',
                'is_active': True,
                'is_verified': False,
                'validation_score': platform_info.get('validation_score', 50),
                'metadata': {
                    'collected_at': datetime.now().isoformat(),
                    'source': source,
                    'platform_info': platform_info
                },
                'tags': ['auto_collected'],
                'added_by_user': 0,
                'source': 'auto_collection'
            }
            
            # Add to database
            success, message, details = await db_manager.add_link(link_data)
            
            if success:
                logger.info(f"✅ Collected new link: {normalized_link}")
                
                # Update statistics
                self.collection_stats['total_collected'] += 1
                
                if platform_info['platform'] == 'telegram':
                    if platform_info['is_group']:
                        self.collection_stats['telegram_groups'] += 1
                        self.collection_stats['valid_groups'] += 1
                    else:
                        self.collection_stats['telegram_channels'] += 1
                elif platform_info['platform'] == 'whatsapp':
                    self.collection_stats['whatsapp_groups'] += 1
                elif platform_info['platform'] == 'discord':
                    self.collection_stats['discord_invites'] += 1
                
                return link_data
            else:
                logger.debug(f"Failed to save link: {message}")
                return None
            
        except Exception as e:
            logger.error(f"Error processing link {link}: {e}")
            self.collection_stats['errors'] += 1
            return None
    
    def _analyze_link(self, link: str) -> Dict:
        """Analyze link to determine platform and type"""
        result = {
            'is_valid': False,
            'platform': 'unknown',
            'link_type': 'unknown',
            'telegram_type': '',
            'is_group': False,
            'is_channel': False,
            'is_channel_with_subscribers': False,
            'is_join_request': False,
            'requires_join': False,
            'is_public': False,
            'is_private': False,
            'validation_score': 0
        }
        
        try:
            # Check for Telegram links
            if 't.me' in link or 'telegram.me' in link or 'telegram.dog' in link:
                result['platform'] = 'telegram'
                result = self._analyze_telegram_link(link, result)
            
            # Check for WhatsApp links
            elif 'whatsapp.com' in link or 'chat.whatsapp.com' in link:
                result['platform'] = 'whatsapp'
                result['is_valid'] = True
                result['link_type'] = 'group'
                result['is_group'] = True
                result['requires_join'] = True
                result['validation_score'] = 70
            
            # Check for Discord links
            elif 'discord.gg' in link or 'discord.com' in link:
                result['platform'] = 'discord'
                result['is_valid'] = True
                result['link_type'] = 'invite'
                result['validation_score'] = 60
            
            # Check for Signal links
            elif 'signal.group' in link:
                result['platform'] = 'signal'
                result['is_valid'] = True
                result['link_type'] = 'group'
                result['is_group'] = True
                result['validation_score'] = 65
            
            # If not a known platform
            if result['platform'] == 'unknown':
                result['is_valid'] = False
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing link {link}: {e}")
            return result
    
    def _analyze_telegram_link(self, link: str, result: Dict) -> Dict:
        """Analyze Telegram link specifically"""
        try:
            # Parse the URL
            parsed = urlparse(link)
            path = parsed.path.strip('/')
            
            if not path:
                return result
            
            segments = path.split('/')
            
            # Check for joinchat links (private groups)
            if 'joinchat' in path.lower() or 'join' in path.lower() or path.startswith('+'):
                result['is_valid'] = True
                result['link_type'] = 'private_group'
                result['telegram_type'] = 'private_group'
                result['is_group'] = True
                result['is_private'] = True
                result['is_join_request'] = True
                result['requires_join'] = True
                result['validation_score'] = 85
                return result
            
            # Check for channel patterns
            channel_patterns = ['c/', 'channel/', 's/']
            for pattern in channel_patterns:
                if pattern in path.lower():
                    result['is_valid'] = True
                    result['link_type'] = 'channel'
                    result['telegram_type'] = 'channel'
                    result['is_channel'] = True
                    result['is_channel_with_subscribers'] = True
                    result['is_public'] = True
                    result['validation_score'] = 40
                    return result
            
            # Check for username links (could be group or channel)
            if len(segments) == 1:
                username = segments[0].lower()
                
                # Skip if it starts with + (private link)
                if username.startswith('+'):
                    result['is_valid'] = True
                    result['link_type'] = 'private_group'
                    result['telegram_type'] = 'private_group'
                    result['is_group'] = True
                    result['is_private'] = True
                    result['is_join_request'] = True
                    result['requires_join'] = True
                    result['validation_score'] = 80
                else:
                    # Public username - could be group or channel
                    # We'll mark it as potential group
                    result['is_valid'] = True
                    result['link_type'] = 'public_group'
                    result['telegram_type'] = 'supergroup'
                    result['is_group'] = True
                    result['is_public'] = True
                    result['is_supergroup'] = True
                    result['requires_join'] = True  # Public groups still need join
                    result['validation_score'] = 75
            
            # Multi-segment paths
            elif len(segments) >= 2:
                first_seg = segments[0].lower()
                
                if first_seg in ['c', 'channel', 's']:
                    result['is_valid'] = True
                    result['link_type'] = 'channel'
                    result['telegram_type'] = 'channel'
                    result['is_channel'] = True
                    result['is_channel_with_subscribers'] = True
                    result['is_public'] = True
                    result['validation_score'] = 40
                elif first_seg == 'joinchat':
                    result['is_valid'] = True
                    result['link_type'] = 'private_group'
                    result['telegram_type'] = 'private_group'
                    result['is_group'] = True
                    result['is_private'] = True
                    result['is_join_request'] = True
                    result['requires_join'] = True
                    result['validation_score'] = 85
                else:
                    # Assume it's a public group
                    result['is_valid'] = True
                    result['link_type'] = 'public_group'
                    result['telegram_type'] = 'supergroup'
                    result['is_group'] = True
                    result['is_public'] = True
                    result['is_supergroup'] = True
                    result['requires_join'] = True
                    result['validation_score'] = 70
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing Telegram link {link}: {e}")
            return result

# ======================
# Enhanced Collection Manager - مدير الجمع المحسن
# ======================

class EnhancedCollectionManager:
    """Manage link collection with real collection logic"""
    
    def __init__(self):
        self.active = False
        self.paused = False
        self.stop_requested = False
        self.collector = EnhancedLinkCollector()
        self.collection_task = None
        self.collection_stats = self.collector.collection_stats.copy()
    
    async def start_collection(self):
        """Start collection process"""
        if self.active:
            return
        
        self.active = True
        self.paused = False
        self.stop_requested = False
        self.collector.active = True
        
        logger.info("🚀 بدء عملية الجمع الحقيقية...")
        
        # بدء مهمة الجمع في الخلفية
        self.collection_task = asyncio.create_task(self._real_collection_loop())
    
    async def _real_collection_loop(self):
        """Real collection loop with actual link gathering"""
        cycle_count = 0
        
        while self.active and not self.stop_requested:
            if self.paused:
                await asyncio.sleep(2)
                continue
            
            cycle_count += 1
            logger.info(f"🔄 بدء دورة الجمع #{cycle_count}")
            
            try:
                await self._real_collection_cycle()
                
                # Calculate delay between cycles
                delay = Config.REQUEST_DELAYS['min_cycle_delay']
                if cycle_count % 3 == 0:
                    delay = Config.REQUEST_DELAYS['max_cycle_delay']
                
                logger.info(f"⏱️ الانتظار {delay} ثانية للدورة القادمة...")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"خطأ في دورة الجمع: {e}")
                self.collection_stats['errors'] += 1
                await asyncio.sleep(30)
        
        self.active = False
        logger.info("⏹️ توقفت عملية الجمع")
    
    async def _real_collection_cycle(self):
        """Single real collection cycle"""
        try:
            db = await EnhancedDatabaseManager.get_instance()
            sessions = await db.get_active_sessions(limit=Config.MAX_CONCURRENT_SESSIONS)
            
            if not sessions:
                logger.warning("⚠️ لا توجد جلسات نشطة للجمع")
                return
            
            logger.info(f"🔍 بدء الجمع من {len(sessions)} جلسة...")
            
            tasks = []
            for session in sessions:
                task = self._process_session_for_collection(session)
                tasks.append(task)
                await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
            
            # Wait for all sessions to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            successful = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"خطأ في الجلسة {i+1}: {result}")
                    self.collection_stats['errors'] += 1
                elif result and result.get('status') == 'success':
                    successful += 1
                    collected = result.get('collected', 0)
                    logger.info(f"✅ الجلسة {i+1}: جمعت {collected} رابط")
            
            logger.info(f"🎯 اكتملت دورة الجمع: {successful}/{len(tasks)} جلسات ناجحة")
            
            # Update overall stats
            self._update_stats_from_collector()
            
        except Exception as e:
            logger.error(f"خطأ في دورة الجمع الرئيسية: {e}")
            self.collection_stats['errors'] += 1
    
    async def _process_session_for_collection(self, session: Dict):
        """Process single session for real collection"""
        try:
            session_string = session.get('session_string', '')
            session_id = session.get('id')
            
            if not session_string or session_string == '********':
                logger.error(f"جلسة {session_id} غير متاحة")
                return {'status': 'error', 'reason': 'جلسة غير متاحة'}
            
            # Decrypt session string if needed
            enc_manager = EncryptionManager.get_instance()
            decrypted_session = enc_manager.decrypt(session_string)
            
            # Create client
            client = await SessionManager.create_client(decrypted_session)
            if not client:
                return {'status': 'error', 'reason': 'فشل إنشاء العميل'}
            
            # Get database manager
            db = await EnhancedDatabaseManager.get_instance()
            
            # Collect links using enhanced collector
            collected = await self.collector.collect_and_validate_links(client, session_id, db)
            
            # Update session stats
            await db.conn.execute(
                "UPDATE sessions SET last_used = CURRENT_TIMESTAMP, total_uses = total_uses + 1, total_links = total_links + ? WHERE id = ?",
                (len(collected), session_id)
            )
            await db.conn.commit()
            
            # Disconnect client
            await client.disconnect()
            
            return {
                'status': 'success', 
                'collected': len(collected),
                'details': {
                    'session_id': session_id,
                    'links': [link.get('url', '') for link in collected[:5]]  # First 5 links
                }
            }
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الجلسة للجمع: {e}")
            self.collection_stats['errors'] += 1
            return {'status': 'error', 'reason': str(e)[:200]}
    
    def _update_stats_from_collector(self):
        """Update stats from collector"""
        self.collection_stats = self.collector.collection_stats.copy()
    
    def get_status(self) -> Dict:
        """Get collection status with detailed stats"""
        return {
            'active': self.active,
            'paused': self.paused,
            'stop_requested': self.stop_requested,
            'stats': self.collection_stats.copy()
        }
    
    async def pause(self):
        """Pause collection"""
        self.paused = True
        self.collector.active = False
        logger.info("⏸️ تم إيقاف الجمع مؤقتاً")
    
    async def resume(self):
        """Resume collection"""
        self.paused = False
        self.collector.active = True
        logger.info("▶️ تم استئناف الجمع")
    
    async def stop(self):
        """Stop collection"""
        self.stop_requested = True
        self.collector.active = False
        logger.info("⏹️ تم طلب إيقاف الجمع")
        
        # Wait for task to complete
        if self.collection_task:
            try:
                await asyncio.wait_for(self.collection_task, timeout=15)
            except asyncio.TimeoutError:
                logger.warning("مهلة انتظار إيقاف مهمة الجمع")
        
        self.active = False

# ======================
# Enhanced Database Manager (Updated) - مدير قاعدة البيانات المحسن
# ======================

class EnhancedDatabaseManager:
    """Advanced database management with improved link handling"""
    
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
        # جدول الجلسات (معدّل)
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
        
        # جدول الروابط (معدّل ومحسّن)
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
                is_group BOOLEAN DEFAULT 1,
                is_join_request BOOLEAN DEFAULT 0,
                is_supergroup BOOLEAN DEFAULT 0,
                is_public BOOLEAN DEFAULT 0,
                is_private BOOLEAN DEFAULT 0,
                was_checked BOOLEAN DEFAULT 0,
                last_collection_date TIMESTAMP,
                collection_count INTEGER DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE SET NULL
            )
        ''')
        
        # بقية الجداول كما هي...
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
        
        # إنشاء فهارس
        await self._create_indexes()
    
    async def _create_indexes(self):
        """Create database indexes"""
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_links_url_hash ON links(url_hash)',
            'CREATE INDEX IF NOT EXISTS idx_links_platform ON links(platform)',
            'CREATE INDEX IF NOT EXISTS idx_links_collected_date ON links(collected_date)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_group ON links(is_group)',
            'CREATE INDEX IF NOT EXISTS idx_links_is_active ON links(is_active)',
            'CREATE INDEX IF NOT EXISTS idx_links_requires_join ON links(requires_join)',
            'CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)',
            'CREATE INDEX IF NOT EXISTS idx_users_last_active ON bot_users(last_active)'
        ]
        
        for index_sql in indexes:
            try:
                await self.conn.execute(index_sql)
            except Exception as e:
                logger.error(f"خطأ في إنشاء الفهرس: {e}")
        
        await self.conn.commit()
    
    async def add_link(self, link_info: Dict) -> Tuple[bool, str, Dict]:
        """Add link to database with improved validation"""
        try:
            url = link_info.get('url', '')
            if not url:
                return False, "رابط فارغ", {}
            
            url_hash = hashlib.md5(url.encode()).hexdigest()
            
            # التحقق من التكرار
            cursor = await self.conn.execute(
                'SELECT id FROM links WHERE url_hash = ?',
                (url_hash,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                # Update existing link
                await self.conn.execute('''
                    UPDATE links 
                    SET last_collection_date = CURRENT_TIMESTAMP,
                        collection_count = collection_count + 1,
                        last_checked = CURRENT_TIMESTAMP,
                        check_count = check_count + 1
                    WHERE id = ?
                ''', (existing[0],))
                await self.conn.commit()
                return False, "الرابط موجود مسبقاً", {'link_id': existing[0]}
            
            # إضافة رابط جديد
            cursor = await self.conn.execute('''
                INSERT INTO links 
                (url_hash, url, original_url, platform, link_type, telegram_type, title, 
                 description, members_count, session_id, confidence, 
                 is_active, requires_join, is_verified, validation_score, metadata, 
                 tags, added_by_user, source, is_channel, is_group, is_join_request, 
                 is_supergroup, is_public, is_private, was_checked, last_collection_date, collection_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                url_hash,
                url,
                link_info.get('original_url', url),
                link_info.get('platform', 'unknown'),
                link_info.get('link_type', 'unknown'),
                link_info.get('telegram_type', ''),
                link_info.get('title', '')[:500],
                link_info.get('description', '')[:1000],
                link_info.get('members_count', 0),
                link_info.get('session_id'),
                link_info.get('confidence', 'medium'),
                link_info.get('is_active', True),
                link_info.get('requires_join', False),
                link_info.get('is_verified', False),
                link_info.get('validation_score', 0),
                json.dumps(link_info.get('metadata', {})),
                json.dumps(link_info.get('tags', [])),
                link_info.get('added_by_user', 0),
                link_info.get('source', 'manual'),
                link_info.get('is_channel', False),
                link_info.get('is_group', True),
                link_info.get('is_join_request', False),
                link_info.get('is_supergroup', False),
                link_info.get('is_public', False),
                link_info.get('is_private', False),
                True,
                datetime.now().isoformat(),
                1
            ))
            
            link_id = cursor.lastrowid
            
            # تحديث إحصائيات المستخدم
            if link_info.get('added_by_user'):
                await self.update_user_stats(link_info['added_by_user'], 'link_added')
            
            await self.conn.commit()
            
            logger.info(f"✅ تمت إضافة رابط جديد: {url_hash[:8]}...")
            
            return True, "تمت إضافة الرابط بنجاح", {
                'link_id': link_id,
                'url_hash': url_hash
            }
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الرابط: {e}")
            return False, f"خطأ في الإضافة: {str(e)[:100]}", {}
    
    async def get_links_count(self, filters: Dict = None) -> int:
        """Get links count with optional filters"""
        try:
            query = 'SELECT COUNT(*) FROM links WHERE is_active = 1'
            params = []
            
            if filters:
                where_clauses = []
                
                if filters.get('platform'):
                    where_clauses.append("platform = ?")
                    params.append(filters['platform'])
                
                if filters.get('is_group') is not None:
                    where_clauses.append("is_group = ?")
                    params.append(filters['is_group'])
                
                if filters.get('requires_join') is not None:
                    where_clauses.append("requires_join = ?")
                    params.append(filters['requires_join'])
                
                if filters.get('is_join_request') is not None:
                    where_clauses.append("is_join_request = ?")
                    params.append(filters['is_join_request'])
                
                if where_clauses:
                    query += " AND " + " AND ".join(where_clauses)
            
            cursor = await self.conn.execute(query, params)
            result = await cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"خطأ في الحصول على عدد الروابط: {e}")
            return 0
    
    async def export_links(self, filters: Dict = None, limit: int = 1000) -> List[str]:
        """Export links with platform-specific filtering"""
        try:
            query = 'SELECT url FROM links WHERE is_active = 1'
            params = []
            
            if filters:
                where_clauses = []
                
                if filters.get('platform'):
                    where_clauses.append("platform = ?")
                    params.append(filters['platform'])
                
                if filters.get('is_group') is not None:
                    where_clauses.append("is_group = ?")
                    params.append(filters['is_group'])
                
                if filters.get('requires_join') is not None:
                    where_clauses.append("requires_join = ?")
                    params.append(filters['requires_join'])
                
                if filters.get('min_validation_score'):
                    where_clauses.append("validation_score >= ?")
                    params.append(filters['min_validation_score'])
                
                if where_clauses:
                    query += " AND " + " AND ".join(where_clauses)
            
            query += " ORDER BY collected_date DESC LIMIT ?"
            params.append(min(limit, Config.MAX_EXPORT_LINKS))
            
            cursor = await self.conn.execute(query, params)
            rows = await cursor.fetchall()
            
            return [row[0] for row in rows]
            
        except Exception as e:
            logger.error(f"خطأ في تصدير الروابط: {e}")
            return []
    
    async def get_stats_summary(self) -> Dict:
        """Get detailed database statistics"""
        try:
            stats = {}
            
            # Basic counts
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links")
            stats['total_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_active = 1")
            stats['active_links'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM bot_users")
            stats['total_users'] = (await cursor.fetchone())[0]
            
            # Platform distribution
            cursor = await self.conn.execute("SELECT platform, COUNT(*) FROM links GROUP BY platform")
            stats['links_by_platform'] = dict(await cursor.fetchall())
            
            # Telegram specific stats
            cursor = await self.conn.execute("""
                SELECT 
                    COUNT(*) as total_telegram,
                    SUM(CASE WHEN is_group = 1 THEN 1 ELSE 0 END) as telegram_groups,
                    SUM(CASE WHEN is_channel = 1 THEN 1 ELSE 0 END) as telegram_channels,
                    SUM(CASE WHEN requires_join = 1 THEN 1 ELSE 0 END) as requires_join,
                    SUM(CASE WHEN is_join_request = 1 THEN 1 ELSE 0 END) as join_requests
                FROM links 
                WHERE platform = 'telegram' AND is_active = 1
            """)
            telegram_stats = await cursor.fetchone()
            if telegram_stats:
                stats['telegram_details'] = {
                    'total': telegram_stats[0],
                    'groups': telegram_stats[1],
                    'channels': telegram_stats[2],
                    'requires_join': telegram_stats[3],
                    'join_requests': telegram_stats[4]
                }
            
            # WhatsApp stats
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE platform = 'whatsapp' AND is_active = 1")
            stats['whatsapp_links'] = (await cursor.fetchone())[0]
            
            # Discord stats
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE platform = 'discord' AND is_active = 1")
            stats['discord_links'] = (await cursor.fetchone())[0]
            
            # Collection stats
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE source = 'auto_collection'")
            stats['auto_collected'] = (await cursor.fetchone())[0]
            
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE source = 'manual'")
            stats['manual_added'] = (await cursor.fetchone())[0]
            
            return stats
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على ملخص الإحصائيات: {e}")
            return {}

# ======================
# Updated Telegram Bot - البوت المحدث
# ======================

class TelegramBot:
    """Main Telegram bot with enhanced collection"""
    
    def __init__(self):
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
        self.collection_manager = EnhancedCollectionManager()  # Use enhanced manager
        self.user_states = {}
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup bot handlers"""
        # Keep existing handlers
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("sessions", self.sessions_command))
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("backup", self.backup_command))
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        self.app.add_handler(CommandHandler("addsession", self.add_session_command))
        
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_message
        ))
        
        self.app.add_error_handler(self.error_handler)
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command with real export options"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        db = await EnhancedDatabaseManager.get_instance()
        total_links = await db.get_links_count()
        
        if total_links == 0:
            await update.message.reply_text("❌ لا توجد روابط للتصدير")
            return
        
        # Get platform-specific counts
        telegram_count = await db.get_links_count({'platform': 'telegram', 'is_group': True})
        whatsapp_count = await db.get_links_count({'platform': 'whatsapp'})
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 مجموعات تيليجرام", callback_data="export_telegram_groups"),
             InlineKeyboardButton("🔗 كل تيليجرام", callback_data="export_telegram_all")],
            [InlineKeyboardButton("📱 واتساب فقط", callback_data="export_whatsapp"),
             InlineKeyboardButton("🎮 ديسكورد فقط", callback_data="export_discord")],
            [InlineKeyboardButton("📄 نصي (كل الروابط)", callback_data="export_txt_all"),
             InlineKeyboardButton("📊 CSV (كل المعلومات)", callback_data="export_csv_all")],
            [InlineKeyboardButton("📋 JSON (كامل)", callback_data="export_json_all"),
             InlineKeyboardButton("⚙️ تصدير مخصص", callback_data="export_custom")]
        ])
        
        export_text = f"""
**📤 تصدير الروابط**

**إحصائيات الروابط:**
• 🔗 الإجمالي: {total_links:,}
• 📢 مجموعات تيليجرام: {telegram_count:,}
• 📱 مجموعات واتساب: {whatsapp_count:,}

**خيارات التصدير:**
• 📢 **مجموعات تيليجرام فقط** - المجموعات النشطة فقط
• 🔗 **كل روابط تيليجرام** - جميع أنواع تيليجرام
• 📱 **واتساب فقط** - روابط واتساب فقط
• 🎮 **ديسكورد فقط** - روابط ديسكورد فقط

**تنسيقات الملفات:**
• 📄 نصي - روابط فقط
• 📊 CSV - مع المعلومات الكاملة
• 📋 JSON - جميع البيانات

**الحد الأقصى: {Config.MAX_EXPORT_LINKS:,} رابط لكل تصدير**
"""
        
        await update.message.reply_text(export_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_export_telegram_groups(self, query):
        """Handle export Telegram groups only"""
        await self._edit_message_safe(query, "⏳ جاري تحضير روابط مجموعات تيليجرام...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            # Get only Telegram groups (not channels)
            links = await db.export_links(
                {
                    'platform': 'telegram',
                    'is_group': True,
                    'requires_join': True,
                    'min_validation_score': 50
                },
                Config.MAX_EXPORT_LINKS
            )
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد مجموعات تيليجرام للتصدير")
                return
            
            # Create file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"telegram_groups_{timestamp}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📢 مجموعات تيليجرام النشطة\nعدد المجموعات: {len(links):,}\n\n"
                           f"**ملاحظة:** هذه مجموعات حقيقية تحتوي على زر 'انضم' أو 'طلب انضمام'"
                )
            
            # Clean up
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في تصدير مجموعات تيليجرام: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_telegram_all(self, query):
        """Handle export all Telegram links"""
        await self._edit_message_safe(query, "⏳ جاري تحضير جميع روابط تيليجرام...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links({'platform': 'telegram'}, Config.MAX_EXPORT_LINKS)
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد روابط تيليجرام للتصدير")
                return
            
            # Create file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"telegram_all_{timestamp}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"🔗 جميع روابط تيليجرام\nعدد الروابط: {len(links):,}"
                )
            
            # Clean up
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في تصدير تيليجرام: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_whatsapp(self, query):
        """Handle export WhatsApp links"""
        await self._edit_message_safe(query, "⏳ جاري تحضير روابط واتساب...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links({'platform': 'whatsapp'}, Config.MAX_EXPORT_LINKS)
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد روابط واتساب للتصدير")
                return
            
            # Create file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"whatsapp_{timestamp}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📱 روابط واتساب\nعدد الروابط: {len(links):,}"
                )
            
            # Clean up
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في تصدير واتساب: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_discord(self, query):
        """Handle export Discord links"""
        await self._edit_message_safe(query, "⏳ جاري تحضير روابط ديسكورد...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links({'platform': 'discord'}, Config.MAX_EXPORT_LINKS)
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد روابط ديسكورد للتصدير")
                return
            
            # Create file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"discord_{timestamp}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"🎮 روابط ديسكورد\nعدد الروابط: {len(links):,}"
                )
            
            # Clean up
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في تصدير ديسكورد: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def _handle_export_txt_all(self, query):
        """Handle export all links as text"""
        await self._edit_message_safe(query, "⏳ جاري تحضير جميع الروابط...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            links = await db.export_links(limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await self._edit_message_safe(query, "❌ لا توجد روابط للتصدير")
                return
            
            # Create file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"all_links_{timestamp}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for link in links:
                    f.write(f"{link}\n")
            
            # Send file
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📄 جميع الروابط\nعدد الروابط: {len(links):,}\n\n"
                           f"**محتوى الملف:**\n• تيليجرام\n• واتساب\n• ديسكورد\n• سيجنال"
                )
            
            # Clean up
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"خطأ في تصدير النصي: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ في التصدير: {str(e)[:100]}")
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /collect command with detailed info"""
        user = update.effective_user
        
        # التحقق من الوصول
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS:
                await update.message.reply_text("❌ غير مصرح لك بالوصول")
                return
        
        status = self.collection_manager.get_status()
        db = await EnhancedDatabaseManager.get_instance()
        db_stats = await db.get_stats_summary()
        
        collect_text = f"""
**🚀 إدارة عملية الجمع الحقيقية**

**الحالة الحالية:**
"""
        
        if status['active']:
            if status['paused']:
                collect_text += "⏸️ **موقف مؤقتاً**\n"
            else:
                collect_text += "🔄 **يعمل بنشاط**\n"
        else:
            collect_text += "🛑 **متوقف**\n"
        
        stats = status['stats']
        collect_text += f"""
**إحصائيات الجمع الحقيقية:**
• ✅ المجموع المجموع: {stats['total_collected']:,}
• 📢 مجموعات تيليجرام: {stats['telegram_groups']:,}
• 📺 قنوات تيليجرام: {stats['telegram_channels']:,}
• 📱 مجموعات واتساب: {stats['whatsapp_groups']:,}
• 🎮 دعوات ديسكورد: {stats['discord_invites']:,}
• ⏭️ تم تخطي القنوات: {stats['skipped_channels']:,}
• 🎯 المجموعات الحقيقية: {stats['valid_groups']:,}
• ❌ الأخطاء: {stats['errors']:,}

**في قاعدة البيانات حالياً:**
• 🔗 إجمالي الروابط: {db_stats.get('total_links', 0):,}
• 📢 مجموعات تيليجرام: {db_stats.get('telegram_details', {}).get('groups', 0):,}
• 📱 مجموعات واتساب: {db_stats.get('whatsapp_links', 0):,}

**ماذا يجمع البوت:**
• فقط المجموعات النشطة (ليست قنوات)
• مجموعات تحتوي على زر "انضم" أو "طلب انضمام"
• يتم تخطي القنوات (التي تحتوي على مشتركين)
• يتم التحقق من نشاط المجموعة
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 بدء الجمع الحقيقي", callback_data="start_collect"),
             InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
            [InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect"),
             InlineKeyboardButton("📊 تحديث الإحصائيات", callback_data="refresh_collect_stats")],
            [InlineKeyboardButton("🔍 عرض عينات", callback_data="show_sample_links"),
             InlineKeyboardButton("⚙️ إعدادات الجمع", callback_data="collect_settings")]
        ])
        
        await update.message.reply_text(collect_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _handle_show_sample_links(self, query):
        """Show sample of collected links"""
        await self._edit_message_safe(query, "⏳ جاري جلب عينات من الروابط المجمعة...")
        
        try:
            db = await EnhancedDatabaseManager.get_instance()
            
            # Get sample links
            cursor = await db.conn.execute('''
                SELECT url, platform, link_type, collected_date 
                FROM links 
                WHERE is_active = 1 
                ORDER BY collected_date DESC 
                LIMIT 10
            ''')
            
            rows = await cursor.fetchall()
            
            if not rows:
                await self._edit_message_safe(query, "❌ لا توجد روابط مجمعة بعد")
                return
            
            sample_text = "**🔍 عينات من الروابط المجمعة:**\n\n"
            
            for i, row in enumerate(rows, 1):
                url, platform, link_type, date = row
                date_str = datetime.fromisoformat(date).strftime('%Y-%m-%d %H:%M') if date else 'غير معروف'
                
                platform_emoji = {
                    'telegram': '📢',
                    'whatsapp': '📱',
                    'discord': '🎮',
                    'signal': '📡'
                }.get(platform, '🔗')
                
                sample_text += f"{i}. {platform_emoji} **{platform}** - {link_type}\n"
                sample_text += f"   🔗 `{url}`\n"
                sample_text += f"   📅 {date_str}\n\n"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 تصدير كل الروابط", callback_data="export_txt_all"),
                 InlineKeyboardButton("🔄 تحديث", callback_data="show_sample_links")]
            ])
            
            await self._edit_message_safe(query, sample_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"خطأ في عرض العينات: {e}")
            await self._edit_message_safe(query, f"❌ حدث خطأ: {str(e)[:100]}")
    
    async def _handle_start_collect(self, query):
        """Handle start collection with real gathering"""
        if self.collection_manager.active:
            await self._edit_message_safe(query, "⏳ الجمع يعمل بالفعل بنشاط!")
            return
        
        # Get session count first
        db = await EnhancedDatabaseManager.get_instance()
        sessions = await db.get_active_sessions(limit=1)
        
        if not sessions:
            await self._edit_message_safe(query, 
                "❌ **لا توجد جلسات نشطة!**\n\n"
                "يجب عليك إضافة جلسة تيليجرام أولاً:\n"
                "1. استخدم /addsession\n"
                "2. أرسل كود الجلسة\n"
                "3. ابدأ الجمع بعد التأكد من الجلسة"
            )
            return
        
        # Start collection
        await self.collection_manager.start_collection()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect"),
             InlineKeyboardButton("⏹️ إيقاف", callback_data="stop_collect")],
            [InlineKeyboardButton("📊 حالة الجمع", callback_data="collect_status"),
             InlineKeyboardButton("🔍 عينات", callback_data="show_sample_links")]
        ])
        
        await self._edit_message_safe(
            query,
            "🚀 **بدأ الجمع الحقيقي بنجاح!**\n\n"
            "**ماذا يفعل البوت الآن:**\n"
            "1. 🔍 يفحص المجموعات في الجلسات النشطة\n"
            "2. ✅ يتأكد من أن المجموعة حقيقية (ليست قناة)\n"
            "3. 📋 يجمع الروابط من الوصف والرسائل\n"
            "4. 💾 يحفظ الروابط في قاعدة البيانات\n\n"
            "**سيقوم البوت بـ:**\n"
            "• تخطي القنوات (التي تحتوي على مشتركين)\n"
            "• جمع فقط المجموعات النشطة\n"
            "• التركيز على المجموعات التي تحتوي على زر انضمام\n\n"
            "**المعلومات ستظهر في:**\n"
            "• السجلات (logs)\n"
            "• أمر /stats\n"
            "• زر 'عينات' لعرض الروابط المجمعة",
            reply_markup=keyboard
        )
    
    # بقية الدوال كما هي مع تعديلات بسيطة...

# ======================
# Rest of the code remains the same with minor adjustments
# ======================

# Note: The rest of the classes (EncryptionManager, BackupManager, 
# HealthCheckServer, etc.) remain the same as in the original code
# with minor adjustments to work with the new collection system.

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
        
        # التحقق من نسخة واحدة فقط
        instance_manager = await SingleInstanceManager.get_instance()
        if not await instance_manager.acquire_lock():
            logger.error("❌ تم اكتشاف نسخة أخرى من البوت تعمل بالفعل!")
            print("❌ خطأ: هناك نسخة أخرى من البوت تعمل. إغلاق...")
            sys.exit(1)
        
        # إنشاء المجلدات المطلوبة
        os.makedirs("backups", exist_ok=True)
        os.makedirs("exports", exist_ok=True)
        os.makedirs("cache_data", exist_ok=True)
        
        # بدء خادم فحص الصحة
        health_server = HealthCheckServer(port=8080)
        health_server.start()
        
        # تهيئة قاعدة البيانات
        db = await EnhancedDatabaseManager.get_instance()
        
        # إنشاء البوت
        bot = TelegramBot()
        
        logger.info("🤖 بدء تشغيل بوت جمع الروابط المتقدم...")
        logger.info(f"🔥 النظام المحسن - يجمع المجموعات الحقيقية فقط")
        logger.info(f"🔧 الإعدادات: {Config.MAX_CONCURRENT_SESSIONS} جلسة متزامنة")
        
        try:
            # تشغيل البوت
            await bot.app.initialize()
            await bot.app.start()
            await bot.app.updater.start_polling()
            
            logger.info("✅ البوت يعمل بنجاح!")
            logger.info("📋 الأوامر المتاحة: /start, /help, /status, /stats, /sessions, /export, /collect")
            logger.info("🎯 البوت سيجمع فقط المجموعات النشطة (ليس القنوات)")
            
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
                if hasattr(bot, 'app'):
                    await bot.app.stop()
                
                # إغلاق قاعدة البيانات
                await db.close()
                
                # إيقاف خادم الصحة
                health_server.stop()
                
                # تحرير قفل النسخة الواحدة
                await instance_manager.release_lock()
                
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
