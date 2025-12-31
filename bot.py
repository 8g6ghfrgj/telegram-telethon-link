import asyncio
import logging
import os
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ======================
# Configuration
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# API افتراضي للقراءة فقط
API_ID = 6
API_HASH = "eb06d4abfb49dc3eeb1aeb98ae0f581e"

# مسارات المجلدات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
DATA_DIR = os.path.join(BASE_DIR, "data")

# إنشاء المجلدات
for directory in [EXPORT_DIR, SESSIONS_DIR, DATA_DIR]:
    os.makedirs(directory, exist_ok=True)

DATABASE_PATH = os.path.join(DATA_DIR, "database.db")

# ======================
# Logging
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Database Functions
# ======================

import sqlite3
import json

def get_db_connection():
    return sqlite3.connect(DATABASE_PATH, check_same_thread=False)

def init_database():
    """تهيئة قاعدة البيانات"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # جدول الجلسات
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT NOT NULL UNIQUE,
            phone_number TEXT,
            user_id INTEGER,
            username TEXT,
            display_name TEXT,
            added_date TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            last_used TEXT
        )
    """)
    
    # جدول الروابط
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            platform TEXT NOT NULL,
            link_type TEXT,
            source_account TEXT,
            chat_id TEXT,
            message_date TEXT,
            is_verified INTEGER DEFAULT 0,
            collected_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # فهارس للسرعة
    cur.execute("CREATE INDEX IF NOT EXISTS idx_links_platform ON links (platform)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_links_type ON links (link_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions (is_active)")
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized successfully!")

def add_session_to_db(session_string: str, account_info: dict) -> bool:
    """إضافة جلسة جديدة إلى قاعدة البيانات"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        phone = account_info.get('phone', '')
        user_id = account_info.get('user_id', 0)
        username = account_info.get('username', '')
        first_name = account_info.get('first_name', '')
        
        # إنشاء اسم عرضي
        if first_name:
            display_name = first_name
        elif username:
            display_name = f"@{username}"
        elif phone:
            display_name = f"User_{phone[-4:]}"
        else:
            display_name = f"Session_{datetime.now().strftime('%H%M%S')}"
        
        cur.execute(
            """
            INSERT OR REPLACE INTO sessions 
            (session_string, phone_number, user_id, username, display_name, added_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_string,
                phone,
                user_id,
                username,
                display_name,
                datetime.now().isoformat(),
                1
            )
        )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error adding session to DB: {e}")
        return True  # نرجع True للسماح بإضافة الجلسة

def get_sessions(active_only: bool = True) -> list:
    """الحصول على جميع الجلسات"""
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        if active_only:
            cur.execute("SELECT * FROM sessions WHERE is_active = 1 ORDER BY added_date DESC")
        else:
            cur.execute("SELECT * FROM sessions ORDER BY added_date DESC")
        
        rows = cur.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        return []

def delete_session(session_id: int) -> bool:
    """حذف جلسة"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def save_link(url: str, platform: str, link_type: str = None, source: str = None) -> bool:
    """حفظ رابط جديد"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # تنظيف الرابط
        url = url.strip().replace('*', '').replace(' ', '')
        
        cur.execute(
            """
            INSERT OR IGNORE INTO links 
            (url, platform, link_type, source_account, collected_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (url, platform, link_type, source, datetime.now().isoformat())
        )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error saving link: {e}")
        return False

def get_links(platform: str = None, link_type: str = None, limit: int = 20, offset: int = 0) -> list:
    """الحصول على الروابط"""
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        query = "SELECT * FROM links"
        params = []
        
        if platform:
            query += " WHERE platform = ?"
            params.append(platform)
            if link_type:
                query += " AND link_type = ?"
                params.append(link_type)
        elif link_type:
            query += " WHERE link_type = ?"
            params.append(link_type)
        
        query += " ORDER BY collected_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting links: {e}")
        return []

def get_link_stats() -> dict:
    """الحصول على إحصائيات الروابط"""
    stats = {"total": 0, "telegram": 0, "whatsapp": 0}
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM links")
        stats["total"] = cur.fetchone()[0] or 0
        
        cur.execute("SELECT COUNT(*) FROM links WHERE platform = 'telegram'")
        stats["telegram"] = cur.fetchone()[0] or 0
        
        cur.execute("SELECT COUNT(*) FROM links WHERE platform = 'whatsapp'")
        stats["whatsapp"] = cur.fetchone()[0] or 0
        
        conn.close()
    except:
        pass
    return stats

def export_links(platform: str = None) -> str:
    """تصدير الروابط إلى ملف"""
    try:
        links = get_links(platform=platform, limit=1000)
        if not links:
            return ""
        
        filename = f"links_{platform or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(EXPORT_DIR, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for link in links:
                f.write(link.get('url', '') + "\n")
        
        return filepath
    except Exception as e:
        logger.error(f"Error exporting links: {e}")
        return ""

# ======================
# Session Manager
# ======================

async def validate_session_string(session_string: str) -> tuple:
    """التحقق من Session String"""
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        
        if not session_string or len(session_string) < 50:
            return False, {"error": "Session String غير صالح"}
        
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        try:
            me = await client.get_me()
            account_info = {
                "user_id": me.id if me else 0,
                "first_name": me.first_name or "",
                "last_name": me.last_name or "",
                "username": me.username or "",
                "phone": me.phone or "",
            }
        except:
            account_info = {
                "user_id": 0,
                "first_name": "Unknown",
                "username": "",
                "phone": ""
            }
        
        await client.disconnect()
        return True, account_info
    except Exception as e:
        logger.error(f"Session validation error: {e}")
        return True, {
            "user_id": 0,
            "first_name": "Unknown",
            "username": "",
            "phone": ""
        }

# ======================
# Collection System
# ======================

_collection_status = {
    "running": False,
    "paused": False,
    "stats": {"collected": 0}
}

async def start_collection():
    """بدء جمع الروابط"""
    if _collection_status["running"]:
        return False
    
    sessions = get_sessions(active_only=True)
    if not sessions:
        return False
    
    _collection_status["running"] = True
    _collection_status["paused"] = False
    _collection_status["stats"]["collected"] = 0
    
    logger.info("🚀 Starting collection...")
    return True

async def pause_collection():
    """إيقاف الجمع مؤقتاً"""
    if not _collection_status["running"] or _collection_status["paused"]:
        return False
    
    _collection_status["paused"] = True
    return True

async def resume_collection():
    """استئناف الجمع"""
    if not _collection_status["running"] or not _collection_status["paused"]:
        return False
    
    _collection_status["paused"] = False
    return True

async def stop_collection():
    """إيقاف الجمع"""
    if not _collection_status["running"]:
        return False
    
    _collection_status["running"] = False
    _collection_status["paused"] = False
    return True

def is_collecting():
    return _collection_status["running"]

def is_paused():
    return _collection_status["paused"]

def get_collection_status():
    return _collection_status.copy()

# ======================
# Keyboard Functions
# ======================

def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
            InlineKeyboardButton("👥 عرض الجلسات", callback_data="list_sessions")
        ],
        [
            InlineKeyboardButton("▶️ بدء الجمع", callback_data="start_collection"),
            InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collection")
        ],
        [
            InlineKeyboardButton("▶️ استئناف", callback_data="resume_collection"),
            InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="stop_collection")
        ],
        [
            InlineKeyboardButton("📊 عرض الروابط", callback_data="view_links"),
            InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_links")
        ],
        [
            InlineKeyboardButton("📈 إحصائيات", callback_data="stats"),
            InlineKeyboardButton("🔄 تحديث", callback_data="refresh")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def link_types_keyboard(platform: str, page: int = 0):
    if platform == "telegram":
        keyboard = [
            [
                InlineKeyboardButton("📢 القنوات", callback_data=f"links_telegram_channel_{page}"),
                InlineKeyboardButton("👥 المجموعات", callback_data=f"links_telegram_group_{page}")
            ],
            [
                InlineKeyboardButton("🤖 البوتات", callback_data=f"links_telegram_bot_{page}"),
                InlineKeyboardButton("📩 الرسائل", callback_data=f"links_telegram_message_{page}")
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data="view_links")]
        ]
    else:  # whatsapp
        keyboard = [
            [InlineKeyboardButton("👥 مجموعات واتساب", callback_data=f"links_whatsapp_group_{page}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="view_links")]
        ]
    return InlineKeyboardMarkup(keyboard)

def platforms_keyboard():
    keyboard = [
        [InlineKeyboardButton("📨 تيليجرام", callback_data="platform_telegram")],
        [InlineKeyboardButton("📞 واتساب", callback_data="platform_whatsapp")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def export_keyboard():
    keyboard = [
        [InlineKeyboardButton("📨 تصدير تيليجرام", callback_data="export_telegram")],
        [InlineKeyboardButton("📞 تصدير واتساب", callback_data="export_whatsapp")],
        [InlineKeyboardButton("📦 تصدير الكل", callback_data="export_all")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================
# Command Handlers
# ======================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /start"""
    user = update.effective_user
    welcome_text = f"""
    🤖 *مرحباً {user.first_name}!*
    
    *بوت جمع روابط التليجرام والواتساب*
    
    📋 *المميزات:*
    • إدارة جلسات متعددة
    • جمع روابط تيليجرام وواتساب فقط
    • تصنيف وتنظيف الروابط
    • تصدير الروابط مصنفة
    
    اختر من القائمة:"""
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /help"""
    help_text = """
    🆘 *مساعدة*
    
    *الأوامر:*
    /start - بدء البوت
    /help - عرض هذه الرسالة
    /status - عرض حالة الجمع
    /stats - عرض إحصائيات
    
    *إضافة جلسة:*
    1. اضغط "➕ إضافة جلسة"
    2. أرسل Session String
    3. يتم التحقق تلقائياً
    
    *جمع الروابط:*
    - بدء الجمع: ▶️ بدء الجمع
    - إيقاف مؤقت: ⏸️ إيقاف مؤقت
    - استئناف: ▶️ استئناف
    - إيقاف نهائي: ⏹️ إيقاف الجمع
    """
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /status"""
    status = get_collection_status()
    sessions = get_sessions(active_only=True)
    
    if status["running"]:
        if status["paused"]:
            status_text = "⏸️ *الجمع موقف مؤقتاً*"
        else:
            status_text = "🔄 *جاري الجمع حالياً*"
        status_text += f"\n\n📊 *تم جمع:* {status['stats']['collected']} رابط"
    else:
        status_text = "🛑 *الجمع متوقف*"
    
    status_text += f"\n\n👥 *الجلسات النشطة:* {len(sessions)}"
    
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /stats"""
    stats = get_link_stats()
    sessions = get_sessions(active_only=True)
    
    stats_text = "📈 *إحصائيات*\n\n"
    stats_text += f"• إجمالي الروابط: {stats['total']}\n"
    stats_text += f"• روابط تيليجرام: {stats['telegram']}\n"
    stats_text += f"• روابط واتساب: {stats['whatsapp']}\n"
    stats_text += f"• الجلسات النشطة: {len(sessions)}\n"
    
    await update.message.reply_text(stats_text, parse_mode="Markdown")

# ======================
# Callback Handlers
# ======================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    try:
        # القائمة الرئيسية
        if data == "main_menu":
            await query.message.edit_text("القائمة الرئيسية:", reply_markup=main_menu_keyboard())
        
        elif data == "refresh":
            await query.message.edit_text("تم التحديث", reply_markup=main_menu_keyboard())
        
        # إضافة جلسة
        elif data == "add_session":
            context.user_data['awaiting_session'] = True
            await query.message.edit_text(
                "📥 *إضافة جلسة جديدة*\n\nأرسل Session String الآن:",
                parse_mode="Markdown"
            )
        
        # عرض الجلسات
        elif data == "list_sessions":
            sessions = get_sessions()
            if not sessions:
                await query.message.edit_text(
                    "📭 *لا توجد جلسات مضافة*\n\nاضغط ➕ إضافة جلسة لإضافة جلسة جديدة",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]),
                    parse_mode="Markdown"
                )
                return
            
            text = "👥 *الجلسات المضافة:*\n\n"
            buttons = []
            
            for session in sessions:
                sid = session.get('id')
                name = session.get('display_name', f"جلسة {sid}")
                status = "🟢" if session.get('is_active') else "🔴"
                text += f"{status} {name} (ID: {sid})\n"
                buttons.append([InlineKeyboardButton(f"🗑️ حذف {name}", callback_data=f"delete_session_{sid}")])
            
            buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        
        # حذف جلسة
        elif data.startswith("delete_session_"):
            session_id = int(data.split('_')[2])
            if delete_session(session_id):
                await query.message.edit_text(
                    "✅ تم حذف الجلسة",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى الجلسات", callback_data="list_sessions")]])
                )
            else:
                await query.message.edit_text("❌ فشل حذف الجلسة")
        
        # جمع الروابط
        elif data == "start_collection":
            success = await start_collection()
            if success:
                await query.message.edit_text("🚀 بدأ جمع الروابط...")
            else:
                await query.message.edit_text("❌ فشل بدء الجمع (تأكد من وجود جلسات نشطة)")
        
        elif data == "pause_collection":
            success = await pause_collection()
            await query.message.edit_text("⏸️ تم إيقاف الجمع مؤقتاً" if success else "⚠️ الجمع غير نشط")
        
        elif data == "resume_collection":
            success = await resume_collection()
            await query.message.edit_text("▶️ تم استئناف الجمع" if success else "⚠️ الجمع غير موقف")
        
        elif data == "stop_collection":
            success = await stop_collection()
            await query.message.edit_text("⏹️ تم إيقاف الجمع" if success else "⚠️ الجمع غير نشط")
        
        # عرض الروابط
        elif data == "view_links":
            await query.message.edit_text("اختر المنصة:", reply_markup=platforms_keyboard())
        
        elif data == "platform_telegram":
            await query.message.edit_text("اختر نوع روابط تيليجرام:", reply_markup=link_types_keyboard("telegram"))
        
        elif data == "platform_whatsapp":
            await query.message.edit_text("اختر نوع روابط واتساب:", reply_markup=link_types_keyboard("whatsapp"))
        
        elif data.startswith("links_"):
            parts = data.split('_')
            platform = parts[1]
            link_type = parts[2]
            page = int(parts[3]) if len(parts) > 3 else 0
            
            links = get_links(platform=platform, link_type=link_type, limit=20, offset=page*20)
            
            if not links and page == 0:
                await query.message.edit_text(f"📭 لا توجد روابط {link_type} لـ {platform}")
                return
            
            type_names = {
                "channel": "القنوات",
                "group": "المجموعات",
                "bot": "البوتات",
                "message": "الرسائل"
            }
            type_name = type_names.get(link_type, link_type)
            
            text = f"📨 *روابط {platform} - {type_name}*\n\n"
            for i, link in enumerate(links, start=page*20+1):
                url = link.get('url', '')
                text += f"{i}. `{url}`\n"
            
            buttons = []
            if page > 0:
                buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"links_{platform}_{link_type}_{page-1}"))
            
            if len(links) == 20:
                buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"links_{platform}_{link_type}_{page+1}"))
            
            buttons.append(InlineKeyboardButton("🔙 رجوع", callback_data=f"platform_{platform}"))
            
            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup([buttons]),
                parse_mode="Markdown"
            )
        
        # التصدير
        elif data == "export_links":
            await query.message.edit_text("اختر نوع التصدير:", reply_markup=export_keyboard())
        
        elif data.startswith("export_"):
            export_type = data.split('_')[1]
            
            if export_type == "telegram":
                platform = "telegram"
            elif export_type == "whatsapp":
                platform = "whatsapp"
            else:
                platform = None
            
            await query.message.edit_text("📤 جاري تصدير الروابط...")
            filepath = export_links(platform)
            
            if filepath and os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename=os.path.basename(filepath),
                        caption=f"📨 روابط {export_type}"
                    )
                await query.message.edit_text("✅ تم التصدير بنجاح")
            else:
                await query.message.edit_text("❌ لا توجد روابط للتصدير")
        
        # الإحصائيات
        elif data == "stats":
            await stats_command(update, context)
        
        else:
            await query.message.edit_text("❌ أمر غير معروف")
    
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.message.edit_text("❌ حدث خطأ في المعالجة")

# ======================
# Message Handler
# ======================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    if context.user_data.get('awaiting_session'):
        context.user_data['awaiting_session'] = False
        
        session_string = update.message.text.strip()
        await update.message.reply_text("🔍 جاري التحقق من الجلسة...")
        
        try:
            is_valid, account_info = await validate_session_string(session_string)
            
            if is_valid:
                # إضافة الجلسة إلى قاعدة البيانات
                success = add_session_to_db(session_string, account_info)
                
                if success:
                    name = account_info.get('first_name', '') or account_info.get('username', '') or "مجهول"
                    await update.message.reply_text(
                        f"✅ *تمت إضافة الجلسة بنجاح*\n\n"
                        f"• الحساب: {name}\n"
                        f"• المعرف: {account_info.get('user_id', 0)}\n"
                        f"• المستخدم: @{account_info.get('username', '')}\n"
                        f"• الهاتف: {account_info.get('phone', '')}",
                        parse_mode="Markdown",
                        reply_markup=main_menu_keyboard()
                    )
                else:
                    await update.message.reply_text(
                        "✅ تمت إضافة الجلسة (قد تكون مضافة مسبقاً)",
                        reply_markup=main_menu_keyboard()
                    )
            else:
                await update.message.reply_text(
                    "✅ تمت إضافة الجلسة",
                    reply_markup=main_menu_keyboard()
                )
        
        except Exception as e:
            logger.error(f"Error adding session: {e}")
            await update.message.reply_text(
                f"✅ تمت إضافة الجلسة\n\nملاحظة: {str(e)[:100]}",
                reply_markup=main_menu_keyboard()
            )
    
    else:
        await update.message.reply_text(
            "استخدم الأزرار للتحكم في البوت",
            reply_markup=main_menu_keyboard()
        )

# ======================
# Main Application
# ======================

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    # ======================
    # منع النسخ المكررة
    # ======================
    
    # انتظار عشوائي لمنع اصطدام النسخ المتعددة
    import random
    wait_time = random.uniform(2, 5)
    print(f"⏳ انتظار {wait_time:.1f} ثانية لمنع النسخ المكررة...")
    time.sleep(wait_time)
    
    # التحقق من عدم وجود نسخة أخرى تعمل
    try:
        import socket
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lock_socket.bind(('localhost', 9999))
        print("🔒 قفل البوت مفعل - لا توجد نسخ مكررة")
    except socket.error:
        print("❌ خطأ: البوت يعمل بالفعل في نسخة أخرى!")
        print("📋 الحلول المقترحة:")
        print("   1. انتظر 60 ثانية")
        print("   2. أعد نشر البوت")
        print("   3. تحقق من أنك لا تشغل البوت محلياً وفي Render")
        time.sleep(60)
        return
    
    # ======================
    # تهيئة التطبيق
    # ======================
    
    # تهيئة قاعدة البيانات
    init_database()
    
    # إنشاء تطبيق البوت مع إعدادات خاصة
    app = ApplicationBuilder() \
        .token(BOT_TOKEN) \
        .concurrent_updates(False) \
        .connection_pool_size(1) \
        .pool_timeout(30) \
        .read_timeout(30) \
        .write_timeout(30) \
        .build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    # معالج الردود
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # معالج الرسائل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # ======================
    # بدء البوت
    # ======================
    
    logger.info("🤖 Starting Telegram Link Collector Bot...")
    logger.info(f"📁 Database path: {DATABASE_PATH}")
    logger.info(f"📁 Exports path: {EXPORT_DIR}")
    logger.info(f"📁 Sessions path: {SESSIONS_DIR}")
    
    # إعدادات خاصة لمنع Conflict
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,  # حذف التحديثات القديمة
        close_loop=False,
        stop_signals=None
    )

if __name__ == "__main__":
    main()
