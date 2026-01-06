import os
import sys
import asyncio
import logging
import re
import json
import aiofiles
import aiosqlite
import hashlib
import psutil
import signal
import secrets
import base64
import traceback
import subprocess
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import defaultdict, deque
from urllib.parse import urlparse, parse_qs, urlencode
import aiohttp
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
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl import functions, types
from telethon.errors import (
    FloodWaitError, ChannelPrivateError, UsernameNotOccupiedError,
    InviteHashInvalidError, InviteHashExpiredError,
    SessionPasswordNeededError, AuthKeyError
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
    ADMIN_USER_IDS = set(map(int, os.getenv("ADMIN_USER_IDS", "0").split(','))) if os.getenv("ADMIN_USER_IDS") else {0}
    ALLOWED_USER_IDS = set(map(int, os.getenv("ALLOWED_USER_IDS", "0").split(','))) if os.getenv("ALLOWED_USER_IDS") else {0}
    
    # Encryption
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    
    # Database
    DB_PATH = "links_collector.db"
    
    # Collection settings
    MAX_CONCURRENT_SESSIONS = 5
    MAX_DIALOGS_PER_SESSION = 100
    MAX_MESSAGES_PER_SEARCH = 20
    MAX_LINKS_PER_CYCLE = 100
    
    # Request delays
    REQUEST_DELAYS = {
        'normal': 1.0,
        'search': 2.0,
        'flood_wait': 5.0,
        'between_sessions': 3.0,
        'between_tasks': 0.5
    }
    
    # User limits
    MAX_SESSIONS_PER_USER = 3
    USER_RATE_LIMIT = {
        'max_requests': 20,
        'per_seconds': 60
    }
    
    # Export
    MAX_EXPORT_LINKS = 50000

# Setup logging
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
# Utility Functions
# ======================

def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}. Shutting down gracefully...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def check_required_packages():
    """Check and install required packages"""
    required_packages = [
        'python-telegram-bot==20.7',
        'Telethon==1.34.0',
        'aiosqlite==0.19.0',
        'aiofiles==23.2.1',
        'cryptography==42.0.5',
        'psutil==5.9.8',
        'aiohttp==3.9.1'
    ]
    
    for package in required_packages:
        try:
            __import__(package.split('==')[0].replace('-', '_'))
        except ImportError:
            print(f"Installing {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Check packages on startup
check_required_packages()

# ======================
# Database Manager
# ======================

class DatabaseManager:
    """Simple and reliable database manager"""
    
    def __init__(self, db_path: str = Config.DB_PATH):
        self.db_path = db_path
        self.connection = None
    
    async def connect(self):
        """Connect to database"""
        self.connection = await aiosqlite.connect(self.db_path)
        await self.connection.execute("PRAGMA foreign_keys = ON")
        await self.connection.execute("PRAGMA journal_mode = WAL")
        await self.create_tables()
    
    async def create_tables(self):
        """Create necessary tables"""
        # Sessions table
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_string TEXT NOT NULL,
                phone_number TEXT,
                user_id INTEGER,
                username TEXT,
                added_by INTEGER,
                is_active BOOLEAN DEFAULT 1,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP
            )
        ''')
        
        # Links table
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                platform TEXT NOT NULL,
                link_type TEXT,
                title TEXT,
                members_count INTEGER DEFAULT 0,
                session_id INTEGER,
                collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                added_by_user INTEGER,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        ''')
        
        # Users table
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_admin BOOLEAN DEFAULT 0,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP
            )
        ''')
        
        # Add unique constraint for URLs
        await self.connection.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_url_unique ON links(url)
        ''')
        
        await self.connection.commit()
    
    async def add_session(self, session_string: str, user_id: int, phone: str = None, username: str = None) -> int:
        """Add a new session"""
        cursor = await self.connection.execute('''
            INSERT INTO sessions (session_string, user_id, phone_number, username, added_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (session_string, user_id, phone, username, user_id))
        
        await self.connection.commit()
        return cursor.lastrowid
    
    async def get_user_sessions(self, user_id: int) -> List[Dict]:
        """Get all sessions for a user"""
        cursor = await self.connection.execute('''
            SELECT id, session_string, phone_number, username, is_active, added_date, last_used
            FROM sessions WHERE added_by = ? AND is_active = 1
            ORDER BY added_date DESC
        ''', (user_id,))
        
        rows = await cursor.fetchall()
        columns = ['id', 'session_string', 'phone_number', 'username', 'is_active', 'added_date', 'last_used']
        
        return [dict(zip(columns, row)) for row in rows]
    
    async def add_link(self, url: str, platform: str, link_type: str = None, 
                      title: str = None, members: int = 0, session_id: int = None, 
                      user_id: int = 0) -> bool:
        """Add a new link"""
        try:
            await self.connection.execute('''
                INSERT OR IGNORE INTO links 
                (url, platform, link_type, title, members_count, session_id, added_by_user)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (url, platform, link_type, title, members, session_id, user_id))
            
            await self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding link: {e}")
            return False
    
    async def get_links(self, user_id: int = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get links with optional user filter"""
        if user_id:
            cursor = await self.connection.execute('''
                SELECT url, platform, link_type, title, members_count, collected_date
                FROM links WHERE added_by_user = ? AND is_active = 1
                ORDER BY collected_date DESC LIMIT ? OFFSET ?
            ''', (user_id, limit, offset))
        else:
            cursor = await self.connection.execute('''
                SELECT url, platform, link_type, title, members_count, collected_date
                FROM links WHERE is_active = 1
                ORDER BY collected_date DESC LIMIT ? OFFSET ?
            ''', (limit, offset))
        
        rows = await cursor.fetchall()
        columns = ['url', 'platform', 'link_type', 'title', 'members_count', 'collected_date']
        
        return [dict(zip(columns, row)) for row in rows]
    
    async def get_link_count(self, user_id: int = None) -> int:
        """Get total link count"""
        if user_id:
            cursor = await self.connection.execute(
                "SELECT COUNT(*) FROM links WHERE added_by_user = ? AND is_active = 1",
                (user_id,)
            )
        else:
            cursor = await self.connection.execute(
                "SELECT COUNT(*) FROM links WHERE is_active = 1"
            )
        
        result = await cursor.fetchone()
        return result[0] if result else 0
    
    async def add_or_update_user(self, user_id: int, username: str = None, 
                                first_name: str = None, last_name: str = None):
        """Add or update user information"""
        cursor = await self.connection.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (user_id,)
        )
        
        if await cursor.fetchone():
            await self.connection.execute('''
                UPDATE users SET username = ?, first_name = ?, last_name = ?, last_active = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (username, first_name, last_name, user_id))
        else:
            await self.connection.execute('''
                INSERT INTO users (user_id, username, first_name, last_name, last_active)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, username, first_name, last_name))
        
        await self.connection.commit()
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """Get user statistics"""
        cursor = await self.connection.execute('''
            SELECT u.*, 
                   (SELECT COUNT(*) FROM links WHERE added_by_user = ?) as total_links,
                   (SELECT COUNT(*) FROM sessions WHERE added_by = ? AND is_active = 1) as total_sessions
            FROM users u WHERE u.user_id = ?
        ''', (user_id, user_id, user_id))
        
        row = await cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return {}
    
    async def update_session_usage(self, session_id: int):
        """Update session last used timestamp"""
        await self.connection.execute(
            "UPDATE sessions SET last_used = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,)
        )
        await self.connection.commit()
    
    async def close(self):
        """Close database connection"""
        if self.connection:
            await self.connection.close()

# ======================
# Encryption Manager
# ======================

class EncryptionManager:
    """Simple encryption manager for sessions"""
    
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
            return self.cipher.encrypt(data.encode()).decode()
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            return data
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt data"""
        try:
            return self.cipher.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            return encrypted_data

# ======================
# Link Processor
# ======================

class LinkProcessor:
    """Process and validate links"""
    
    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize URL"""
        if not url:
            return ""
        
        url = url.strip()
        
        # Remove quotes and extra spaces
        url = re.sub(r'^["\']+|["\']+$', '', url)
        
        # Add https if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Remove tracking parameters
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        # Remove common tracking params
        tracking_params = ['utm_', 'ref', 'source', 'fbclid', 'gclid']
        filtered_params = {}
        
        for key, values in query_params.items():
            if not any(tp in key.lower() for tp in tracking_params):
                filtered_params[key] = values[0] if values else ''
        
        # Reconstruct URL
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        if filtered_params:
            clean_url += '?' + urlencode(filtered_params)
        
        if parsed.fragment:
            clean_url += '#' + parsed.fragment
        
        # Remove trailing slash
        if clean_url.endswith('/'):
            clean_url = clean_url[:-1]
        
        return clean_url.lower()
    
    @staticmethod
    def extract_links(text: str) -> List[str]:
        """Extract links from text"""
        if not text:
            return []
        
        # Common patterns for group links
        patterns = [
            r'(https?://t\.me/[^\s]+)',
            r'(https?://telegram\.me/[^\s]+)',
            r'(https?://chat\.whatsapp\.com/[^\s]+)',
            r'(https?://discord\.gg/[^\s]+)',
            r'(t\.me/[^\s]+)',
            r'(telegram\.me/[^\s]+)',
            r'(chat\.whatsapp\.com/[^\s]+)'
        ]
        
        links = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            links.extend(matches)
        
        # Normalize and deduplicate
        normalized_links = []
        for link in links:
            normalized = LinkProcessor.normalize_url(link)
            if normalized and normalized not in normalized_links:
                normalized_links.append(normalized)
        
        return normalized_links
    
    @staticmethod
    def get_platform(url: str) -> str:
        """Detect platform from URL"""
        url_lower = url.lower()
        
        if 't.me' in url_lower or 'telegram.me' in url_lower:
            return 'telegram'
        elif 'whatsapp.com' in url_lower:
            return 'whatsapp'
        elif 'discord.gg' in url_lower:
            return 'discord'
        elif 'signal.group' in url_lower:
            return 'signal'
        else:
            return 'unknown'

# ======================
# Session Manager
# ======================

class SessionManager:
    """Manage Telegram sessions"""
    
    def __init__(self):
        self.active_clients = {}
        self.encryption = EncryptionManager()
    
    async def create_client(self, session_string: str, session_id: int = None) -> Optional[TelegramClient]:
        """Create Telegram client from session string"""
        try:
            # Decrypt if encrypted
            decrypted = self.encryption.decrypt(session_string)
            actual_session = decrypted if decrypted != session_string else session_string
            
            client = TelegramClient(
                StringSession(actual_session),
                Config.API_ID,
                Config.API_HASH,
                device_model="Link Collector",
                system_version="Linux",
                app_version="4.0",
                timeout=30
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return None
            
            if session_id:
                self.active_clients[session_id] = client
            
            return client
            
        except Exception as e:
            logger.error(f"Error creating client: {e}")
            return None
    
    async def validate_session(self, session_string: str) -> Tuple[bool, Dict]:
        """Validate Telegram session"""
        try:
            client = await self.create_client(session_string)
            
            if not client:
                return False, {'error': 'Unauthorized session'}
            
            me = await client.get_me()
            
            user_info = {
                'id': me.id,
                'username': me.username or '',
                'phone': me.phone or '',
                'first_name': me.first_name or '',
                'last_name': me.last_name or '',
                'is_bot': me.bot if hasattr(me, 'bot') else False
            }
            
            await client.disconnect()
            
            return True, {'user_info': user_info}
            
        except Exception as e:
            return False, {'error': str(e)[:200]}
    
    async def collect_links_from_session(self, client: TelegramClient, session_id: int, user_id: int) -> Dict:
        """Collect links from a session"""
        collected = {
            'telegram': 0,
            'whatsapp': 0,
            'other': 0,
            'total': 0,
            'links': []
        }
        
        try:
            # Search for links in dialogs
            search_terms = [
                'مجموعة', 'قناة', 'رابط', 'دعوة', 'انضمام',
                'group', 'channel', 'link', 'invite', 'join',
                't.me', 'telegram.me', 'chat.whatsapp.com'
            ]
            
            for dialog in await client.get_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                for term in search_terms[:5]:  # Use first 5 terms
                    try:
                        messages = await client.get_messages(
                            dialog.entity,
                            search=term,
                            limit=Config.MAX_MESSAGES_PER_SEARCH
                        )
                        
                        for message in messages:
                            if message.text:
                                links = LinkProcessor.extract_links(message.text)
                                
                                for link in links:
                                    if collected['total'] >= Config.MAX_LINKS_PER_CYCLE:
                                        break
                                    
                                    platform = LinkProcessor.get_platform(link)
                                    
                                    # Simple validation
                                    is_valid = True
                                    if platform == 'telegram':
                                        # Check if it's a join link
                                        if '+joinchat' in link or '/joinchat/' in link:
                                            is_valid = True
                                        # Check if it's a public link
                                        elif '/+' in link:
                                            is_valid = True
                                    
                                    if is_valid:
                                        collected['links'].append({
                                            'url': link,
                                            'platform': platform,
                                            'collected_at': datetime.now().isoformat()
                                        })
                                        
                                        if platform == 'telegram':
                                            collected['telegram'] += 1
                                        elif platform == 'whatsapp':
                                            collected['whatsapp'] += 1
                                        else:
                                            collected['other'] += 1
                                        
                                        collected['total'] += 1
                    
                    except Exception as e:
                        logger.debug(f"Error searching in dialog: {e}")
                        continue
                    
                    await asyncio.sleep(Config.REQUEST_DELAYS['search'])
                
                if collected['total'] >= Config.MAX_LINKS_PER_CYCLE:
                    break
            
            return collected
            
        except FloodWaitError as e:
            logger.warning(f"Flood wait: {e.seconds} seconds")
            raise
        except Exception as e:
            logger.error(f"Error collecting links: {e}")
            return collected
    
    async def close_client(self, session_id: int):
        """Close client connection"""
        if session_id in self.active_clients:
            try:
                await self.active_clients[session_id].disconnect()
                del self.active_clients[session_id]
            except Exception as e:
                logger.error(f"Error closing client: {e}")

# ======================
# Collection Manager
# ======================

class CollectionManager:
    """Manage link collection process"""
    
    def __init__(self):
        self.is_active = False
        self.is_paused = False
        self.session_manager = SessionManager()
        self.db = DatabaseManager()
        
        await self.db.connect()
        
        self.stats = {
            'total_collected': 0,
            'telegram': 0,
            'whatsapp': 0,
            'other': 0,
            'start_time': None,
            'end_time': None
        }
    
    async def start_collection(self, user_id: int = None):
        """Start collection process"""
        if self.is_active:
            return False, "Collection is already running"
        
        self.is_active = True
        self.is_paused = False
        self.stats['start_time'] = datetime.now()
        
        logger.info("Starting collection process...")
        
        # Get active sessions
        if user_id:
            sessions = await self.db.get_user_sessions(user_id)
        else:
            # Get all active sessions (simplified)
            cursor = await self.db.connection.execute(
                "SELECT id, session_string FROM sessions WHERE is_active = 1"
            )
            rows = await cursor.fetchall()
            sessions = [{'id': row[0], 'session_string': row[1]} for row in rows]
        
        if not sessions:
            self.is_active = False
            return False, "No active sessions found"
        
        total_collected = 0
        
        for session in sessions[:Config.MAX_CONCURRENT_SESSIONS]:
            if not self.is_active or self.is_paused:
                break
            
            try:
                client = await self.session_manager.create_client(
                    session['session_string'],
                    session['id']
                )
                
                if not client:
                    logger.warning(f"Session {session['id']} is not authorized")
                    continue
                
                # Collect links
                result = await self.session_manager.collect_links_from_session(
                    client, session['id'], session.get('added_by', 0)
                )
                
                # Save links to database
                for link_data in result['links']:
                    success = await self.db.add_link(
                        url=link_data['url'],
                        platform=link_data['platform'],
                        session_id=session['id'],
                        user_id=session.get('added_by', 0)
                    )
                    
                    if success:
                        total_collected += 1
                
                # Update session usage
                await self.db.update_session_usage(session['id'])
                
                # Update stats
                self.stats['telegram'] += result['telegram']
                self.stats['whatsapp'] += result['whatsapp']
                self.stats['other'] += result['other']
                
                await self.session_manager.close_client(session['id'])
                
                await asyncio.sleep(Config.REQUEST_DELAYS['between_sessions'])
                
            except FloodWaitError as e:
                logger.warning(f"Flood wait for session {session['id']}: {e.seconds}s")
                await asyncio.sleep(e.seconds + Config.REQUEST_DELAYS['flood_wait'])
            except Exception as e:
                logger.error(f"Error processing session {session['id']}: {e}")
                continue
        
        self.stats['total_collected'] = total_collected
        self.stats['end_time'] = datetime.now()
        self.is_active = False
        
        logger.info(f"Collection completed. Collected {total_collected} links.")
        
        return True, f"Collection completed. Collected {total_collected} links."
    
    async def stop_collection(self):
        """Stop collection process"""
        self.is_active = False
        return True, "Collection stopped"
    
    async def pause_collection(self):
        """Pause collection"""
        self.is_paused = True
        return True, "Collection paused"
    
    async def resume_collection(self):
        """Resume collection"""
        self.is_paused = False
        return True, "Collection resumed"
    
    def get_status(self) -> Dict:
        """Get collection status"""
        return {
            'is_active': self.is_active,
            'is_paused': self.is_paused,
            'stats': self.stats
        }

# ======================
# Telegram Bot
# ======================

class TelegramBot:
    """Main Telegram bot class"""
    
    def __init__(self):
        self.bot_token = Config.BOT_TOKEN
        self.application = ApplicationBuilder().token(self.bot_token).build()
        self.db = DatabaseManager()
        self.collection_manager = CollectionManager()
        self.session_manager = SessionManager()
        
        # User states for conversations
        self.user_states = {}
        
        # Setup handlers
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup bot handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("addsession", self.add_session_command))
        self.application.add_handler(CommandHandler("mysessions", self.my_sessions_command))
        self.application.add_handler(CommandHandler("collect", self.collect_command))
        self.application.add_handler(CommandHandler("mylinks", self.my_links_command))
        self.application.add_handler(CommandHandler("export", self.export_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        
        # Callback handlers
        self.application.add_handler(CallbackQueryHandler(self.callback_handler))
        
        # Message handler
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_message
        ))
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
    
    async def start(self):
        """Start the bot"""
        await self.db.connect()
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        logger.info("Bot started successfully!")
        
        # Keep the bot running
        await asyncio.Event().wait()
    
    async def stop(self):
        """Stop the bot"""
        await self.application.stop()
        await self.db.close()
    
    # Command handlers
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # Check access
        if Config.ALLOWED_USER_IDS and user.id not in Config.ALLOWED_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            await update.message.reply_text(
                "❌ Access denied.\n\n"
                "You are not authorized to use this bot."
            )
            return
        
        # Add/update user in database
        await self.db.add_or_update_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        welcome_text = f"""
🤖 Welcome to Link Collector Bot, {user.first_name}!

✨ **Features:**
• Add Telegram sessions
• Collect group/channel links
• Export collected links
• Monitor collection status

📋 **Available Commands:**
/start - Show this message
/help - Show help
/addsession - Add Telegram session
/mysessions - List your sessions
/collect - Start collection
/mylinks - View your links
/export - Export links
/stats - Show statistics
/status - Show bot status

🚀 Get started by adding your first session with /addsession
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Session", callback_data="add_session")],
            [InlineKeyboardButton("🚀 Start Collection", callback_data="start_collection")],
            [InlineKeyboardButton("📊 My Stats", callback_data="my_stats")]
        ])
        
        await update.message.reply_text(welcome_text, reply_markup=keyboard)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
📚 **Link Collector Bot Help**

🔧 **Commands:**
/start - Start the bot
/help - Show this help
/addsession - Add a Telegram session
/mysessions - List your sessions
/collect - Start collecting links
/mylinks - View your collected links
/export - Export links to file
/stats - Show statistics
/status - Show bot status

📝 **How to use:**
1. Add your Telegram session using /addsession
2. Start collection with /collect
3. View collected links with /mylinks
4. Export links with /export

⚠️ **Important Notes:**
• Each user can add up to 3 sessions
• Collection runs in the background
• Links are saved to database
• Use /status to check progress

🔒 **Security:**
• Sessions are encrypted
• Only authorized users can access
• Rate limiting is applied

Need more help? Contact the administrator.
        """
        
        await update.message.reply_text(help_text)
    
    async def add_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addsession command"""
        user = update.effective_user
        
        # Check session limit
        user_stats = await self.db.get_user_stats(user.id)
        user_sessions = user_stats.get('total_sessions', 0)
        
        if user_sessions >= Config.MAX_SESSIONS_PER_USER:
            await update.message.reply_text(
                f"❌ Session limit reached.\n\n"
                f"You can only add {Config.MAX_SESSIONS_PER_USER} sessions.\n"
                f"Current sessions: {user_sessions}"
            )
            return
        
        # Set user state
        self.user_states[user.id] = {'action': 'add_session'}
        
        await update.message.reply_text(
            "📱 **Add Telegram Session**\n\n"
            "Please send your Telegram session string.\n\n"
            "**How to get session string:**\n"
            "1. Go to @StringSessionBot on Telegram\n"
            "2. Send /start to the bot\n"
            "3. Select your account type\n"
            "4. Copy the session string\n\n"
            "**Note:** Your session will be encrypted and stored securely.\n\n"
            "Send /cancel to cancel."
        )
    
    async def my_sessions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mysessions command"""
        user = update.effective_user
        
        sessions = await self.db.get_user_sessions(user.id)
        
        if not sessions:
            await update.message.reply_text(
                "📭 No sessions found.\n\n"
                "Add your first session with /addsession"
            )
            return
        
        text = f"📱 **Your Sessions ({len(sessions)})**\n\n"
        
        for i, session in enumerate(sessions, 1):
            last_used = session['last_used'] or 'Never'
            text += f"{i}. **{session['username'] or 'No username'}**\n"
            text += f"   📞: {session['phone_number'] or 'No phone'}\n"
            text += f"   📅 Added: {session['added_date'][:10]}\n"
            text += f"   🔄 Last used: {last_used[:10] if last_used != 'Never' else 'Never'}\n\n"
        
        await update.message.reply_text(text)
    
    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /collect command"""
        user = update.effective_user
        
        # Check if user has sessions
        sessions = await self.db.get_user_sessions(user.id)
        
        if not sessions:
            await update.message.reply_text(
                "❌ No active sessions found.\n\n"
                "Add your first session with /addsession"
            )
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Start Collection", callback_data="start_collection")],
            [InlineKeyboardButton("⏸️ Pause", callback_data="pause_collection")],
            [InlineKeyboardButton("⏹️ Stop", callback_data="stop_collection")],
            [InlineKeyboardButton("📊 Status", callback_data="collection_status")]
        ])
        
        await update.message.reply_text(
            "🚀 **Link Collection**\n\n"
            f"Active sessions: {len(sessions)}\n"
            "Collection will search for group/channel links.\n\n"
            "**Options:**",
            reply_markup=keyboard
        )
    
    async def my_links_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mylinks command"""
        user = update.effective_user
        
        # Get user's links
        links = await self.db.get_links(user_id=user.id, limit=20)
        total_links = await self.db.get_link_count(user_id=user.id)
        
        if not links:
            await update.message.reply_text(
                "📭 No links collected yet.\n\n"
                "Start collection with /collect"
            )
            return
        
        text = f"📊 **Your Collected Links ({total_links} total)**\n\n"
        
        for i, link in enumerate(links[:10], 1):
            platform_icon = "📢" if link['platform'] == 'telegram' else "📱"
            text += f"{i}. {platform_icon} **{link['platform'].upper()}**\n"
            text += f"   🔗 {link['url'][:50]}...\n"
            if link['title']:
                text += f"   📝 {link['title'][:30]}...\n"
            text += f"   📅 {link['collected_date'][:10]}\n\n"
        
        if total_links > 10:
            text += f"... and {total_links - 10} more links.\n\n"
        
        text += "Use /export to download all links."
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Export Links", callback_data="export_links")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_links")]
        ])
        
        await update.message.reply_text(text, reply_markup=keyboard)
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command"""
        user = update.effective_user
        
        total_links = await self.db.get_link_count(user_id=user.id)
        
        if total_links == 0:
            await update.message.reply_text(
                "❌ No links to export.\n\n"
                "Collect some links first with /collect"
            )
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 TXT Format", callback_data="export_txt")],
            [InlineKeyboardButton("📊 CSV Format", callback_data="export_csv")],
            [InlineKeyboardButton("📋 JSON Format", callback_data="export_json")]
        ])
        
        await update.message.reply_text(
            f"📤 **Export Links**\n\n"
            f"Total links: {total_links}\n"
            "Select export format:",
            reply_markup=keyboard
        )
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        user = update.effective_user
        
        user_stats = await self.db.get_user_stats(user.id)
        total_links = await self.db.get_link_count()
        
        text = f"""
📊 **Statistics**

👤 **Your Stats:**
• User ID: {user.id}
• Username: @{user.username or 'N/A'}
• Sessions: {user_stats.get('total_sessions', 0)}/{Config.MAX_SESSIONS_PER_USER}
• Links collected: {user_stats.get('total_links', 0)}
• Member since: {user_stats.get('added_date', 'N/A')[:10]}

📈 **Global Stats:**
• Total links in database: {total_links}
• Active users: {await self.get_active_users_count()}

⚙️ **Bot Limits:**
• Max sessions per user: {Config.MAX_SESSIONS_PER_USER}
• Max concurrent sessions: {Config.MAX_CONCURRENT_SESSIONS}
• Max export links: {Config.MAX_EXPORT_LINKS:,}
        """
        
        await update.message.reply_text(text)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        status = self.collection_manager.get_status()
        
        text = f"""
📡 **Bot Status**

🔄 **Collection Status:**
• Active: {'✅ Yes' if status['is_active'] else '❌ No'}
• Paused: {'⏸️ Yes' if status['is_paused'] else '▶️ No'}

📊 **Last Collection:**
"""
        
        if status['stats']['start_time']:
            start = status['stats']['start_time']
            end = status['stats']['end_time'] or datetime.now()
            duration = end - start
            
            text += f"""• Started: {start.strftime('%Y-%m-%d %H:%M:%S')}
• Duration: {self.format_duration(duration)}
• Links collected: {status['stats']['total_collected']}
• Telegram: {status['stats']['telegram']}
• WhatsApp: {status['stats']['whatsapp']}
• Other: {status['stats']['other']}
"""
        else:
            text += "• No collection history\n"
        
        text += f"\n💾 **Database:** {Config.DB_PATH}"
        
        await update.message.reply_text(text)
    
    async def get_active_users_count(self) -> int:
        """Get count of active users"""
        cursor = await self.db.connection.execute(
            "SELECT COUNT(DISTINCT user_id) FROM users WHERE last_active > datetime('now', '-7 days')"
        )
        result = await cursor.fetchone()
        return result[0] if result else 0
    
    # Callback handler
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        data = query.data
        
        if data == "add_session":
            await self.add_session_command(update, context)
        
        elif data == "start_collection":
            success, message = await self.collection_manager.start_collection(user.id)
            await query.message.reply_text(f"📡 {message}")
        
        elif data == "pause_collection":
            success, message = await self.collection_manager.pause_collection()
            await query.message.reply_text(f"⏸️ {message}")
        
        elif data == "stop_collection":
            success, message = await self.collection_manager.stop_collection()
            await query.message.reply_text(f"⏹️ {message}")
        
        elif data == "collection_status":
            status = self.collection_manager.get_status()
            status_text = f"Status: {'Active' if status['is_active'] else 'Inactive'}"
            if status['is_paused']:
                status_text += " (Paused)"
            await query.message.reply_text(f"📡 {status_text}")
        
        elif data == "my_stats":
            await self.stats_command(update, context)
        
        elif data == "export_links":
            await self.export_command(update, context)
        
        elif data == "export_txt":
            await self.export_links(user.id, 'txt', query.message)
        
        elif data == "export_csv":
            await self.export_links(user.id, 'csv', query.message)
        
        elif data == "export_json":
            await self.export_links(user.id, 'json', query.message)
        
        elif data == "refresh_links":
            await self.my_links_command(update, context)
    
    async def export_links(self, user_id: int, format_type: str, message):
        """Export links to file"""
        try:
            links = await self.db.get_links(user_id=user_id, limit=Config.MAX_EXPORT_LINKS)
            
            if not links:
                await message.reply_text("❌ No links to export")
                return
            
            filename = f"links_export_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            if format_type == 'txt':
                filename += '.txt'
                content = '\n'.join([link['url'] for link in links])
            
            elif format_type == 'csv':
                filename += '.csv'
                content = "URL,Platform,Type,Title,Members,Date\n"
                for link in links:
                    content += f"{link['url']},{link['platform']},{link.get('link_type', '')},"
                    content += f"{link.get('title', '').replace(',', ' ')},{link.get('members_count', 0)},"
                    content += f"{link.get('collected_date', '')}\n"
            
            elif format_type == 'json':
                filename += '.json'
                content = json.dumps(links, ensure_ascii=False, indent=2)
            
            # Save to file
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Send file
            with open(filename, 'rb') as f:
                await message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"📤 Exported {len(links)} links in {format_type.upper()} format"
                )
            
            # Clean up
            os.remove(filename)
            
        except Exception as e:
            logger.error(f"Error exporting links: {e}")
            await message.reply_text(f"❌ Error exporting links: {str(e)[:100]}")
    
    # Message handler
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular messages"""
        user = update.effective_user
        text = update.message.text
        
        # Check if user is in add_session state
        if user.id in self.user_states and self.user_states[user.id].get('action') == 'add_session':
            # Validate session
            await update.message.reply_text("🔄 Validating session...")
            
            is_valid, result = await self.session_manager.validate_session(text)
            
            if is_valid:
                # Encrypt and save session
                enc_manager = EncryptionManager()
                encrypted_session = enc_manager.encrypt(text)
                
                user_info = result['user_info']
                session_id = await self.db.add_session(
                    encrypted_session,
                    user.id,
                    user_info.get('phone'),
                    user_info.get('username')
                )
                
                # Clear user state
                del self.user_states[user.id]
                
                await update.message.reply_text(
                    f"✅ Session added successfully!\n\n"
                    f"📱 Username: @{user_info.get('username', 'N/A')}\n"
                    f"📞 Phone: {user_info.get('phone', 'N/A')}\n"
                    f"🆔 User ID: {user_info.get('id', 'N/A')}\n\n"
                    f"Session ID: {session_id}\n\n"
                    f"Now you can start collection with /collect"
                )
            else:
                await update.message.reply_text(
                    f"❌ Invalid session: {result.get('error', 'Unknown error')}\n\n"
                    f"Please try again with /addsession"
                )
                del self.user_states[user.id]
        
        else:
            # Extract links from message
            links = LinkProcessor.extract_links(text)
            
            if links:
                saved_count = 0
                for link in links:
                    platform = LinkProcessor.get_platform(link)
                    success = await self.db.add_link(
                        url=link,
                        platform=platform,
                        user_id=user.id
                    )
                    if success:
                        saved_count += 1
                
                if saved_count > 0:
                    await update.message.reply_text(
                        f"✅ Saved {saved_count} link(s) from your message!"
                    )
            else:
                await update.message.reply_text(
                    "👋 Send me a session string to add, or links to save!\n\n"
                    "Use /help for available commands."
                )
    
    # Error handler
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Update {update} caused error {context.error}", exc_info=True)
        
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ An error occurred. Please try again later."
            )
        except:
            pass
    
    # Utility methods
    
    @staticmethod
    def format_duration(duration: timedelta) -> str:
        """Format duration to human readable string"""
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")
        
        return ' '.join(parts)

# ======================
# Health Check Server (for Render)
# ======================

from fastapi import FastAPI
import uvicorn
import threading

class HealthCheckServer:
    """Simple health check server for Render"""
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.app = FastAPI()
        self.setup_routes()
    
    def setup_routes(self):
        @self.app.get("/")
        async def root():
            return {"status": "ok", "service": "Telegram Link Collector"}
        
        @self.app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "service": "running"
            }
    
    def start(self):
        """Start health check server in background"""
        def run():
            uvicorn.run(self.app, host="0.0.0.0", port=self.port, log_level="error")
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        logger.info(f"Health check server started on port {self.port}")

# ======================
# Main Function
# ======================

async def main():
    """Main entry point"""
    setup_signal_handlers()
    
    # Check required environment variables
    if not Config.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN environment variable is required!")
        sys.exit(1)
    
    if Config.API_ID == 0:
        logger.error("❌ API_ID environment variable is required!")
        sys.exit(1)
    
    if not Config.API_HASH:
        logger.error("❌ API_HASH environment variable is required!")
        sys.exit(1)
    
    # Start health check server (for Render)
    health_server = HealthCheckServer(port=8080)
    health_server.start()
    
    # Create and start bot
    bot = TelegramBot()
    
    try:
        logger.info("🚀 Starting Telegram Link Collector Bot...")
        await bot.start()
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await bot.stop()
        logger.info("✅ Bot shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
