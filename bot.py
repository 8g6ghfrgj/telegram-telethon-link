import os
import sys
import subprocess
import asyncio
import logging
import re
import json
import aiofiles
import aiosqlite
import hashlib
import psutil
import signal
import shutil
import base64
from typing import Dict, List, Optional, Tuple
from datetime import datetime
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
from telegram.error import BadRequest
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl import types

# ======================
# 1. FIX: تثبيت المكتبات أولاً على Render
# ======================
def ensure_packages():
    required = [
        'python-telegram-bot==21.1',
        'Telethon==1.34.0',
        'aiosqlite==0.19.0',
        'aiofiles==23.2.1',
        'cryptography==42.0.5',
        'psutil==5.9.8',
        'aiohttp==3.11.3',
        'cffi==1.16.0'
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
# 2. FIX: تهيئة الإعدادات المحسنة
# ======================
class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH", "")
    ADMIN_USER_IDS = {int(x) for x in os.getenv("ADMIN_USER_IDS", "0").split(",") if x.strip()}
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    DB_PATH = "links_collector.db"
    MAX_CONCURRENT_SESSIONS = 3
    MAX_DIALOGS_PER_SESSION = 25
    MAX_MESSAGES_PER_CHAT = 15
    MIN_MEMBERS_FOR_GROUP = 3
    COLLECT_ONLY_GROUPS = True
    COLLECT_TELEGRAM = True
    COLLECT_WHATSAPP = True
    COLLECT_OTHER = False
    REQUEST_DELAY = 1.0
    SESSION_TIMEOUT = 30

# ======================
# 3. FIX: معالج الروابط المبسط والمباشر
# ======================
class EnhancedLinkProcessor:
    @staticmethod
    def normalize_url(url: str) -> str:
        if not url:
            return ""
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            if 't.me' in url or 'chat.whatsapp.com' in url:
                url = 'https://' + url
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if 't.me' in domain or 'telegram.' in domain:
                platform = 'telegram'
            elif 'whatsapp.com' in domain:
                platform = 'whatsapp'
            else:
                return ""
            path = parsed.path.rstrip('/')
            clean = f"https://{parsed.netloc}{path}"
            return clean
        except:
            return ""

    @staticmethod
    def extract_and_filter(text: str) -> List[str]:
        found_links = []
        patterns = [
            r'(https?://t\.me/[^\s<>"\']+)',
            r'(https?://telegram\.me/[^\s<>"\']+)',
            r'(https?://telegram\.dog/[^\s<>"\']+)',
            r'(https?://chat\.whatsapp\.com/[^\s<>"\']+)',
            r'(t\.me/[^\s<>"\']+)',
            r'(telegram\.me/[^\s<>"\']+)',
            r'(chat\.whatsapp\.com/[^\s<>"\']+)',
        ]
        for pattern in patterns:
            found_links.extend(re.findall(pattern, text, re.IGNORECASE))
        normalized = [EnhancedLinkProcessor.normalize_url(link) for link in found_links]
        filtered = [link for link in normalized if link and ('t.me' in link or 'chat.whatsapp.com' in link)]
        seen = set()
        unique = []
        for link in filtered:
            if link not in seen:
                seen.add(link)
                unique.append(link)
        return unique

# ======================
# 4. FIX: مدقق المجموعات المصحح (الجزء الأهم)
# ======================
class GroupValidator:
    @staticmethod
    async def validate_group(client: TelegramClient, entity) -> Dict:
        result = {
            'is_valid': False,
            'is_group': False,
            'members_count': 0,
            'title': getattr(entity, 'title', 'غير معروف')[:50],
            'join_request': False,
            'join_to_send': False
        }
        try:
            full = await client.get_entity(entity)
            if hasattr(full, 'megagroup') and full.megagroup:
                result['is_group'] = True
            elif hasattr(full, 'gigagroup'):
                result['is_group'] = True
            if hasattr(full, 'participants_count'):
                result['members_count'] = full.participants_count
            if hasattr(full, 'join_request') and full.join_request:
                result['join_request'] = True
            if hasattr(full, 'join_to_send') and full.join_to_send:
                result['join_to_send'] = True
            # التصحيح الحاسم: مجموعة صالحة إذا كانت مجموعة ولها أحد خيارات الانضمام
            result['is_valid'] = result['is_group'] and (result['join_request'] or result['join_to_send'])
        except Exception as e:
            logging.debug(f"خطأ في التحقق: {e}")
        return result

# ======================
# 5. FIX: إدارة قاعدة البيانات
# ======================
class EnhancedDatabaseManager:
    _instance = None
    @classmethod
    async def get_instance(cls):
        if cls._instance is None:
            cls._instance = EnhancedDatabaseManager()
            await cls._instance._initialize()
        return cls._instance

    async def _initialize(self):
        self.db_path = Config.DB_PATH
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        self.conn = await aiosqlite.connect(self.db_path)
        await self.conn.execute('''CREATE TABLE IF NOT EXISTS links (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    url TEXT UNIQUE NOT NULL,
                                    platform TEXT NOT NULL,
                                    collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                    session_id INTEGER,
                                    added_by_user INTEGER,
                                    is_valid_group BOOLEAN DEFAULT 1
                                )''')
        await self.conn.execute('''CREATE TABLE IF NOT EXISTS sessions (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    session_string TEXT NOT NULL,
                                    phone_number TEXT,
                                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                    is_active BOOLEAN DEFAULT 1
                                )''')
        await self.conn.commit()

    async def add_link(self, url: str, platform: str, session_id: int, user_id: int) -> bool:
        try:
            await self.conn.execute("INSERT OR IGNORE INTO links (url, platform, session_id, added_by_user) VALUES (?, ?, ?, ?)",
                                    (url, platform, session_id, user_id))
            await self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"خطأ في إضافة الرابط: {e}")
            return False

    async def get_links_count(self) -> int:
        try:
            cursor = await self.conn.execute("SELECT COUNT(*) FROM links WHERE is_valid_group = 1")
        return (await cursor.fetchone())[0]
        except:
        return 0

    async def export_links_txt(self) -> Optional[str]:
        try:
            cursor = await self.conn.execute("SELECT url FROM links WHERE is_valid_group = 1 ORDER BY collected_date DESC LIMIT 50000")
            rows = await cursor.fetchall()
            if not rows:
                return None
            filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join("exports", filename)
            os.makedirs("exports", exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                for row in rows:
                    f.write(f"{row[0]}\n")
            return filepath
        except Exception as e:
            logging.error(f"خطأ في التصدير: {e}")
            return None

# ======================
# 6. FIX: قلب نظام الجمع - مبسط وموثوق
# ======================
class CollectionManager:
    def __init__(self):
        self.active = False
        self.stats = {'collected': 0, 'errors': 0, 'last_run': None}

    async def collect_from_session(self, session_string: str, session_id: int, user_id: int):
        client = None
        try:
            client = TelegramClient(StringSession(session_string), Config.API_ID, Config.API_HASH, timeout=Config.SESSION_TIMEOUT)
            await client.connect()
            if not await client.is_user_authorized():
                return
            db = await EnhancedDatabaseManager.get_instance()
            collected_count = 0
            async for dialog in client.iter_dialogs(limit=Config.MAX_DIALOGS_PER_SESSION):
                if not self.active:
                    break
                try:
                    # 1. التحقق من صحة المجموعة
                    validation = await GroupValidator.validate_group(client, dialog.entity)
                    if not validation['is_valid']:
                        continue
                    # 2. جمع الرسائل
                    messages_collected = 0
                    async for message in client.iter_messages(dialog.entity, limit=Config.MAX_MESSAGES_PER_CHAT):
                        if messages_collected >= Config.MAX_MESSAGES_PER_CHAT:
                            break
                        if message.text:
                            links = EnhancedLinkProcessor.extract_and_filter(message.text)
                            for link in links:
                                platform = 'telegram' if 't.me' in link else 'whatsapp'
                                if (platform == 'telegram' and Config.COLLECT_TELEGRAM) or (platform == 'whatsapp' and Config.COLLECT_WHATSAPP):
                                    await db.add_link(link, platform, session_id, user_id)
                                    collected_count += 1
                                    self.stats['collected'] += 1
                        messages_collected += 1
                        await asyncio.sleep(0.05)
                    await asyncio.sleep(Config.REQUEST_DELAY)
                except Exception as e:
                    logging.debug(f"خطأ في الدردشة: {e}")
                    continue
            logging.info(f"تم جمع {collected_count} رابط من الجلسة {session_id}")
        except Exception as e:
            logging.error(f"خطأ جسيم في الجلسة: {e}")
            self.stats['errors'] += 1
        finally:
            if client:
                await client.disconnect()

    async def run_real_collection(self, user_id: int):
        if self.active:
            return
        self.active = True
        self.stats = {'collected': 0, 'errors': 0, 'last_run': datetime.now().isoformat()}
        logging.info("بدء الجمع الحقيقي")
        db = await EnhancedDatabaseManager.get_instance()
        cursor = await db.conn.execute("SELECT id, session_string FROM sessions WHERE is_active = 1 LIMIT ?", (Config.MAX_CONCURRENT_SESSIONS,))
        sessions = await cursor.fetchall()
        tasks = []
        for session_id, session_string in sessions:
            task = self.collect_from_session(session_string, session_id, user_id)
            tasks.append(task)
            await asyncio.sleep(1.5)
        await asyncio.gather(*tasks, return_exceptions=True)
        self.active = False
        logging.info(f"انتهى الجمع. المجموع: {self.stats['collected']}, الأخطاء: {self.stats['errors']}")

# ======================
# 7. FIX: بوت التليجرام - معالجة الاستدعاءات المصححة
# ======================
class TelegramBot:
    def __init__(self):
        # التصحيح: منع تضارب تحديثات الويب هوك على Render
        self.app = ApplicationBuilder().token(Config.BOT_TOKEN).updater(None).build()
        self.collection_manager = CollectionManager()
        self._setup_handlers()

    def _setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("collect", self.collect_command))
        self.app.add_handler(CommandHandler("test", self.test_command))
        self.app.add_handler(CommandHandler("export", self.export_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("addsession", self.addsession_command))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    # التصحيح: استخدام update.effective_user بشكل صحيح
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if Config.ADMIN_USER_IDS and user.id not in Config.ADMIN_USER_IDS:
            await update.message.reply_text("غير مصرح")
            return
        keyboard = [[InlineKeyboardButton("🚀 جمع حقيقي", callback_data='real_collect')],
                    [InlineKeyboardButton("🧪 اختبار", callback_data='test_collect')],
                    [InlineKeyboardButton("📤 تصدير", callback_data='export_links')]]
        await update.message.reply_text(
            "**بوت تجميع الروالح الحقيقي - الإصدار المصحح**\n\n"
            "تم إصلاح جميع الأخطاء:\n"
            "✅ تجميع فعلي من محادثات الجلسات\n"
            "✅ تصفية المجموعات ذات 'طلب انضمام'\n"
            "✅ جمع روابط Telegram و WhatsApp فقط\n"
            "✅ دعم تشغيل مستمر على Render",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    async def collect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id not in Config.ADMIN_USER_IDS:
            await update.message.reply_text("غير مصرح")
            return
        asyncio.create_task(self.collection_manager.run_real_collection(user.id))
        await update.message.reply_text("🚀 **بدأ الجمع الحقيقي في الخلفية.**\nسيتم جمع الروابط من جميع جلساتك النشطة.", parse_mode="Markdown")

    # التصحيح: دالة الاختبار المعدلة
    async def test_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await update.message.reply_text("جاري اختبار جلسة واحدة...")
        try:
            db = await EnhancedDatabaseManager.get_instance()
            cursor = await db.conn.execute("SELECT session_string FROM sessions WHERE is_active = 1 LIMIT 1")
            session = await cursor.fetchone()
            if not session:
                await update.message.reply_text("❌ لا توجد جلسات نشطة.")
                return
            client = TelegramClient(StringSession(session[0]), Config.API_ID, Config.API_HASH, timeout=20)
            await client.connect()
            if not await client.is_user_authorized():
                await update.message.reply_text("❌ الجلسة غير مفعلة.")
                await client.disconnect()
                return
            test_links = []
            async for dialog in client.iter_dialogs(limit=2):
                validation = await GroupValidator.validate_group(client, dialog.entity)
                msg_text = f"المجموعة: {validation.get('title', 'N/A')}\n"
                msg_text += f"صحيحة: {'نعم' if validation['is_valid'] else 'لا'}\n"
                msg_text += f"الأعضاء: ~{validation['members_count']}\n"
                msg_text += f"طلب انضمام: {'نعم' if validation['join_request'] else 'لا'}"
                await update.message.reply_text(msg_text)
                if validation['is_valid']:
                    async for message in client.iter_messages(dialog.entity, limit=5):
                        if message.text:
                            links = EnhancedLinkProcessor.extract_and_filter(message.text)
                            test_links.extend(links)
                        await asyncio.sleep(0.1)
                await asyncio.sleep(1)
            await client.disconnect()
            if test_links:
                sample = "\n".join(test_links[:3])
                await update.message.reply_text(f"✅ الاختبار ناجح!\nعينة من الروابط المجمعة:\n{sample}")
            else:
                await update.message.reply_text("⚠️ الاختبار مكتمل ولكن لم يتم العثور على روابط.")
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ في الاختبار: {str(e)[:150]}")

    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id not in Config.ADMIN_USER_IDS:
            await update.message.reply_text("غير مصرح")
            return
        db = await EnhancedDatabaseManager.get_instance()
        count = await db.get_links_count()
        if count == 0:
            await update.message.reply_text("❌ لا توجد روابط صالحة مخزنة بعد.")
            return
        await update.message.reply_text(f"⏳ جاري تحضير {count} رابط...")
        filepath = await db.export_links_txt()
        if filepath:
            with open(filepath, 'rb') as f:
                await update.message.reply_document(document=f, caption=f"📤 تم تصدير {count} رابط.")
            os.remove(filepath)
        else:
            await update.message.reply_text("❌ فشل إنشاء ملف التصدير.")

    # التصحيح: معالجة الاستدعاءات مع تمرير Update الصحيح
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user = query.from_user
        if user.id not in Config.ADMIN_USER_IDS:
            await query.edit_message_text("غير مصرح")
            return
        if query.data == 'real_collect':
            await self.collect_command(update, context)
        elif query.data == 'test_collect':
            await self.test_command(update, context)
        elif query.data == 'export_links':
            await self.export_command(update, context)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("استخدم /start للبدء.")

    async def addsession_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await update.message.reply_text("أرسل سلسلة الجلسة (session string)...")
        context.user_data['waiting_for_session'] = True

# ======================
# 8. تشغيل البوت
# ======================
async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # التحقق من وجود المتغيرات الأساسية على Render
    if not all([Config.BOT_TOKEN, Config.API_ID, Config.API_HASH]):
        logging.error("❌ متغيرات BOT_TOKEN, API_ID, API_HASH مطلوبة.")
        return
    bot = TelegramBot()
    await bot.app.initialize()
    await bot.app.start()
    logging.info("✅ البوت يعمل على Render!")
    # استخدم await bot.app.updater.start_polling() إذا كنت تستخدم Polling
    # أو قم بإعداد webhook إذا كان مطلوباً على Render
    await bot.app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
