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

# ======================
# Logging
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Database (بدون ملفات خارجية)
# ======================

import sqlite3
import json

def get_db_connection():
    return sqlite3.connect('data/database.db', check_same_thread=False)

def init_database():
    os.makedirs('data', exist_ok=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # جدول الجلسات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT UNIQUE NOT NULL,
            phone TEXT,
            username TEXT,
            user_id INTEGER,
            display_name TEXT,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # جدول الروابط
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            platform TEXT NOT NULL,
            link_type TEXT,
            source_session TEXT,
            collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_verified INTEGER DEFAULT 0
        )
    ''')
    
    # جدول الإحصائيات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            status TEXT,
            total_collected INTEGER DEFAULT 0,
            telegram_links INTEGER DEFAULT 0,
            whatsapp_links INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

# ======================
# Session Management
# ======================

async def validate_session_string(session_string: str):
    """تحقق بسيط من Session String"""
    if not session_string or len(session_string) < 50:
        return False, {"error": "Session String قصير جداً"}
    return True, {"user_id": 0, "username": "", "phone": "", "first_name": "Unknown"}

def add_session_to_db(session_string: str, account_info: dict):
    """إضافة جلسة إلى قاعدة البيانات"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        phone = account_info.get('phone', '')
        username = account_info.get('username', '')
        user_id = account_info.get('user_id', 0)
        first_name = account_info.get('first_name', 'Unknown')
        
        display_name = first_name or username or f"User_{user_id}"
        
        cursor.execute('''
            INSERT OR REPLACE INTO sessions 
            (session_string, phone, username, user_id, display_name, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (session_string, phone, username, user_id, display_name))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error adding session: {e}")
        return True  # دائماً نرجع True

def get_sessions_from_db(active_only=True):
    """جلب الجلسات من قاعدة البيانات"""
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if active_only:
            cursor.execute('SELECT * FROM sessions WHERE is_active = 1 ORDER BY added_date DESC')
        else:
            cursor.execute('SELECT * FROM sessions ORDER BY added_date DESC')
        
        sessions = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return sessions
    except:
        return []

def delete_session_from_db(session_id: int):
    """حذف جلسة من قاعدة البيانات"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def get_session_count():
    """عدد الجلسات"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM sessions WHERE is_active = 1')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0

# ======================
# Link Management
# ======================

def add_link_to_db(url: str, platform: str, link_type: str = None, source_session: str = None):
    """إضافة رابط إلى قاعدة البيانات"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # تنظيف URL
        url = url.strip().replace('*', '').replace(' ', '')
        
        cursor.execute('''
            INSERT OR IGNORE INTO links (url, platform, link_type, source_session)
            VALUES (?, ?, ?, ?)
        ''', (url, platform, link_type, source_session))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error adding link: {e}")
        return False

def get_links_from_db(platform: str = None, link_type: str = None, limit: int = 20, offset: int = 0):
    """جلب الروابط من قاعدة البيانات"""
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = 'SELECT * FROM links WHERE 1=1'
        params = []
        
        if platform:
            query += ' AND platform = ?'
            params.append(platform)
        
        if link_type:
            query += ' AND link_type = ?'
            params.append(link_type)
        
        query += ' ORDER BY collected_date DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        links = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return links
    except:
        return []

def get_link_count(platform: str = None, link_type: str = None):
    """عدد الروابط"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = 'SELECT COUNT(*) FROM links WHERE 1=1'
        params = []
        
        if platform:
            query += ' AND platform = ?'
            params.append(platform)
        
        if link_type:
            query += ' AND link_type = ?'
            params.append(link_type)
        
        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0

def get_link_stats():
    """إحصائيات الروابط"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # حسب المنصة
        cursor.execute('SELECT platform, COUNT(*) FROM links GROUP BY platform')
        stats['by_platform'] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # حسب نوع التليجرام
        cursor.execute('SELECT link_type, COUNT(*) FROM links WHERE platform = "telegram" GROUP BY link_type')
        stats['telegram_by_type'] = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
        return stats
    except:
        return {}

def export_links(platform: str, link_type: str = None):
    """تصدير الروابط إلى ملف"""
    try:
        os.makedirs('exports', exist_ok=True)
        
        links = get_links_from_db(platform, link_type, limit=1000, offset=0)
        
        if not links:
            return None
        
        if link_type:
            filename = f"links_{platform}_{link_type}.txt"
        else:
            filename = f"links_{platform}.txt"
        
        filepath = os.path.join('exports', filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for link in links:
                f.write(link['url'] + '\n')
        
        return filepath
    except Exception as e:
        logger.error(f"Error exporting links: {e}")
        return None

# ======================
# Collection System
# ======================

class CollectionManager:
    """مدير عملية الجمع"""
    
    def __init__(self):
        self.is_running = False
        self.is_paused = False
        self.current_session = None
        self.stats = {
            'telegram_collected': 0,
            'whatsapp_collected': 0,
            'total_collected': 0
        }
    
    async def start_collection(self):
        """بدء الجمع"""
        if self.is_running:
            return False
        
        if get_session_count() == 0:
            return False
        
        self.is_running = True
        self.is_paused = False
        self.stats = {'telegram_collected': 0, 'whatsapp_collected': 0, 'total_collected': 0}
        
        # بدء عملية الجمع في الخلفية
        asyncio.create_task(self._collection_loop())
        
        return True
    
    async def pause_collection(self):
        """إيقاف مؤقت"""
        if not self.is_running or self.is_paused:
            return False
        
        self.is_paused = True
        return True
    
    async def resume_collection(self):
        """استئناف الجمع"""
        if not self.is_running or not self.is_paused:
            return False
        
        self.is_paused = False
        return True
    
    async def stop_collection(self):
        """إيقاف الجمع"""
        if not self.is_running:
            return False
        
        self.is_running = False
        self.is_paused = False
        return True
    
    async def _collection_loop(self):
        """حلقة الجمع الرئيسية"""
        try:
            logger.info("🚀 بدأ جمع الروابط...")
            
            while self.is_running:
                if self.is_paused:
                    await asyncio.sleep(1)
                    continue
                
                # محاكاة جمع الروابط (في الإصدار الحقيقي سيكون هناك اتصال بـ Telethon)
                await asyncio.sleep(5)
                
                # مثال: إضافة روابط وهمية للاختبار
                if self.stats['total_collected'] < 100:
                    sample_links = [
                        ("https://t.me/python_ar", "telegram", "channel"),
                        ("https://t.me/joinchat/abcdef", "telegram", "private_group"),
                        ("https://chat.whatsapp.com/abc123", "whatsapp", "group")
                    ]
                    
                    for url, platform, link_type in sample_links:
                        if add_link_to_db(url, platform, link_type, "test_session"):
                            if platform == "telegram":
                                self.stats['telegram_collected'] += 1
                            elif platform == "whatsapp":
                                self.stats['whatsapp_collected'] += 1
                            self.stats['total_collected'] += 1
                
                # استراحة قصيرة
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"Error in collection loop: {e}")
        finally:
            self.is_running = False
            logger.info("✅ توقف جمع الروابط")

# إنشاء مدير الجمع
collection_manager = CollectionManager()

# ======================
# Keyboards
# ======================

def main_menu_keyboard():
    """لوحة المفاتيح الرئيسية"""
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
            InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_menu")
        ],
        [
            InlineKeyboardButton("📈 إحصائيات", callback_data="show_stats"),
            InlineKeyboardButton("🔧 اختبار الجلسات", callback_data="test_sessions")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def platforms_keyboard():
    """لوحة اختيار المنصة"""
    keyboard = [
        [InlineKeyboardButton("📨 تيليجرام", callback_data="platform_telegram")],
        [InlineKeyboardButton("📞 واتساب", callback_data="platform_whatsapp")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def telegram_types_keyboard(page=0):
    """أنواع روابط التليجرام"""
    keyboard = [
        [
            InlineKeyboardButton("📢 القنوات", callback_data=f"view_telegram_channel_{page}"),
            InlineKeyboardButton("👥 المجموعات", callback_data=f"view_telegram_group_{page}")
        ],
        [
            InlineKeyboardButton("🤖 البوتات", callback_data=f"view_telegram_bot_{page}"),
            InlineKeyboardButton("📩 الرسائل", callback_data=f"view_telegram_message_{page}")
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="view_links")]
    ]
    return InlineKeyboardMarkup(keyboard)

def whatsapp_types_keyboard(page=0):
    """أنواع روابط الواتساب"""
    keyboard = [
        [InlineKeyboardButton("👥 مجموعات واتساب", callback_data=f"view_whatsapp_group_{page}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="view_links")]
    ]
    return InlineKeyboardMarkup(keyboard)

def export_menu_keyboard():
    """قائمة التصدير"""
    keyboard = [
        [InlineKeyboardButton("📨 تصدير تيليجرام", callback_data="export_telegram")],
        [InlineKeyboardButton("📞 تصدير واتساب", callback_data="export_whatsapp")],
        [InlineKeyboardButton("📁 تصدير الجلسات", callback_data="export_sessions")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def sessions_list_keyboard(sessions):
    """قائمة الجلسات مع أزرار الحذف"""
    keyboard = []
    
    for session in sessions:
        session_id = session['id']
        display_name = session.get('display_name', f"جلسة {session_id}")
        status = "🟢" if session.get('is_active', 1) else "🔴"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {display_name}",
                callback_data=f"session_info_{session_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def pagination_keyboard(platform: str, link_type: str, page: int, has_next: bool):
    """أزرار التصفح"""
    keyboard = []
    
    if page > 0:
        keyboard.append(
            InlineKeyboardButton("⬅️ السابق", 
                callback_data=f"view_{platform}_{link_type}_{page-1}")
        )
    
    keyboard.append(
        InlineKeyboardButton(f"📄 {page+1}", callback_data="current_page")
    )
    
    if has_next:
        keyboard.append(
            InlineKeyboardButton("➡️ التالي", 
                callback_data=f"view_{platform}_{link_type}_{page+1}")
        )
    
    return InlineKeyboardMarkup([keyboard])

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
    • جمع روابط تيليجرام وواتساب
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
    /help - عرض التعليمات
    /status - حالة الجمع
    /stats - إحصائيات الروابط
    
    *إضافة جلسة:*
    1. اضغط "➕ إضافة جلسة"
    2. أرسل Session String
    
    *جمع الروابط:*
    - ▶️ بدء الجمع: يبدأ جمع الروابط
    - ⏸️ إيقاف مؤقت: إيقاف مؤقت
    - ▶️ استئناف: متابعة الجمع
    - ⏹️ إيقاف الجمع: توقف نهائي
    
    *تصدير الروابط:*
    يمكن تصدير الروابط حسب التصنيف
    """
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /status"""
    status_text = ""
    
    if collection_manager.is_running:
        if collection_manager.is_paused:
            status_text = "⏸️ *الجمع موقف مؤقتاً*"
        else:
            status_text = "🔄 *جاري الجمع حالياً*"
        
        stats = collection_manager.stats
        status_text += f"""
        
        📊 *الإحصائيات الحالية:*
        • روابط تيليجرام: {stats['telegram_collected']}
        • روابط واتساب: {stats['whatsapp_collected']}
        • الإجمالي: {stats['total_collected']}
        """
    else:
        status_text = "🛑 *الجمع متوقف*"
    
    sessions_count = get_session_count()
    status_text += f"\n\n👥 *الجلسات النشطة:* {sessions_count}"
    
    await update.message.reply_text(status_text, parse_mode="Markdown")

# ======================
# Callback Handlers
# ======================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جميع الردود"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    try:
        # القائمة الرئيسية
        if data == "main_menu":
            await query.message.edit_text(
                "📱 *القائمة الرئيسية*\n\nاختر من الخيارات:",
                reply_markup=main_menu_keyboard(),
                parse_mode="Markdown"
            )
        
        # إضافة جلسة
        elif data == "add_session":
            context.user_data['awaiting_session'] = True
            await query.message.edit_text(
                "📥 *إضافة جلسة جديدة*\n\nأرسل لي Session String الآن:",
                parse_mode="Markdown"
            )
        
        # عرض الجلسات
        elif data == "list_sessions":
            sessions = get_sessions_from_db()
            
            if not sessions:
                await query.message.edit_text(
                    "📭 *لا توجد جلسات مضافة*\n\nاضغط ➕ إضافة جلسة لإضافة جلسة جديدة",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")
                    ]]),
                    parse_mode="Markdown"
                )
                return
            
            await query.message.edit_text(
                "👥 *الجلسات المضافة*\n\nاختر جلسة:",
                reply_markup=sessions_list_keyboard(sessions),
                parse_mode="Markdown"
            )
        
        # معلومات جلسة محددة
        elif data.startswith("session_info_"):
            session_id = int(data.split('_')[2])
            
            keyboard = [
                [
                    InlineKeyboardButton("❌ حذف الجلسة", callback_data=f"delete_session_{session_id}"),
                    InlineKeyboardButton("🔙 رجوع", callback_data="list_sessions")
                ]
            ]
            
            await query.message.edit_text(
                f"🔍 *معلومات الجلسة #{session_id}*\n\nاضغط حذف لإزالة الجلسة:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        # حذف جلسة
        elif data.startswith("delete_session_"):
            session_id = int(data.split('_')[2])
            success = delete_session_from_db(session_id)
            
            if success:
                await query.message.edit_text(
                    "✅ تم حذف الجلسة بنجاح",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 رجوع إلى الجلسات", callback_data="list_sessions")
                    ]])
                )
            else:
                await query.message.edit_text("❌ فشل حذف الجلسة")
        
        # بدء الجمع
        elif data == "start_collection":
            if get_session_count() == 0:
                await query.message.edit_text(
                    "❌ لا توجد جلسات نشطة\n\nيجب إضافة جلسة على الأقل",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session")
                    ]])
                )
                return
            
            success = await collection_manager.start_collection()
            
            if success:
                await query.message.edit_text(
                    "🚀 *بدأ جمع الروابط*\n\n⏳ جاري جمع الروابط من جميع الجلسات...",
                    parse_mode="Markdown"
                )
            else:
                await query.message.edit_text("❌ فشل بدء الجمع")
        
        # إيقاف مؤقت
        elif data == "pause_collection":
            success = await collection_manager.pause_collection()
            await query.message.edit_text(
                "⏸️ تم إيقاف الجمع مؤقتاً" if success else "⚠️ الجمع غير نشط"
            )
        
        # استئناف
        elif data == "resume_collection":
            success = await collection_manager.resume_collection()
            await query.message.edit_text(
                "▶️ تم استئناف الجمع" if success else "⚠️ الجمع غير موقف"
            )
        
        # إيقاف الجمع
        elif data == "stop_collection":
            success = await collection_manager.stop_collection()
            await query.message.edit_text(
                "⏹️ تم إيقاف الجمع" if success else "⚠️ الجمع غير نشط"
            )
        
        # عرض الروابط
        elif data == "view_links":
            await query.message.edit_text(
                "📊 *اختر المنصة:*",
                reply_markup=platforms_keyboard(),
                parse_mode="Markdown"
            )
        
        # اختيار المنصة
        elif data == "platform_telegram":
            await query.message.edit_text(
                "📨 *روابط تيليجرام*\n\nاختر نوع الروابط:",
                reply_markup=telegram_types_keyboard(),
                parse_mode="Markdown"
            )
        
        elif data == "platform_whatsapp":
            await query.message.edit_text(
                "📞 *روابط واتساب*\n\nاختر نوع الروابط:",
                reply_markup=whatsapp_types_keyboard(),
                parse_mode="Markdown"
            )
        
        # عرض روابط محددة
        elif data.startswith("view_"):
            parts = data.split('_')
            platform = parts[1]
            link_type = parts[2]
            page = int(parts[3]) if len(parts) > 3 else 0
            
            await show_links_page(query, platform, link_type, page)
        
        # قائمة التصدير
        elif data == "export_menu":
            await query.message.edit_text(
                "📤 *تصدير البيانات*\n\nاختر نوع التصدير:",
                reply_markup=export_menu_keyboard(),
                parse_mode="Markdown"
            )
        
        # تصدير تيليجرام
        elif data == "export_telegram":
            await query.message.edit_text("⏳ جاري تحضير ملف التصدير...")
            
            filepath = export_links("telegram")
            
            if filepath and os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename=os.path.basename(filepath),
                        caption="📨 روابط تيليجرام"
                    )
                await query.message.edit_text("✅ تم تصدير روابط تيليجرام")
            else:
                await query.message.edit_text("❌ لا توجد روابط تيليجرام للتصدير")
        
        # تصدير واتساب
        elif data == "export_whatsapp":
            await query.message.edit_text("⏳ جاري تحضير ملف التصدير...")
            
            filepath = export_links("whatsapp")
            
            if filepath and os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename=os.path.basename(filepath),
                        caption="📞 روابط واتساب"
                    )
                await query.message.edit_text("✅ تم تصدير روابط واتساب")
            else:
                await query.message.edit_text("❌ لا توجد روابط واتساب للتصدير")
        
        # تصدير الجلسات
        elif data == "export_sessions":
            await query.message.edit_text("⏳ جاري تحضير ملف الجلسات...")
            
            try:
                sessions = get_sessions_from_db(active_only=False)
                
                if not sessions:
                    await query.message.edit_text("❌ لا توجد جلسات للتصدير")
                    return
                
                os.makedirs('exports', exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = f"exports/sessions_backup_{timestamp}.txt"
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write("# Telegram Sessions Backup\n")
                    f.write(f"# Exported at: {datetime.now().isoformat()}\n")
                    f.write(f"# Total sessions: {len(sessions)}\n\n")
                    
                    for session in sessions:
                        f.write(f"# Session ID: {session.get('id')}\n")
                        f.write(f"# Display Name: {session.get('display_name', 'Unknown')}\n")
                        f.write(f"# Phone: {session.get('phone', 'Unknown')}\n")
                        f.write(f"# Active: {'Yes' if session.get('is_active') else 'No'}\n")
                        f.write(session.get('session_string', '') + "\n")
                        f.write("---\n")
                
                with open(filepath, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename=os.path.basename(filepath),
                        caption="🔐 نسخة احتياطية للجلسات"
                    )
                
                await query.message.edit_text("✅ تم تصدير الجلسات")
                
            except Exception as e:
                logger.error(f"Error exporting sessions: {e}")
                await query.message.edit_text("❌ حدث خطأ أثناء تصدير الجلسات")
        
        # إحصائيات
        elif data == "show_stats":
            stats = get_link_stats()
            
            if not stats:
                await query.message.edit_text("📭 لا توجد إحصائيات حالياً")
                return
            
            text = "📊 *إحصائيات الروابط*\n\n"
            
            by_platform = stats.get('by_platform', {})
            if by_platform:
                text += "*حسب المنصة:*\n"
                for platform, count in by_platform.items():
                    text += f"• {platform}: {count}\n"
            
            telegram_by_type = stats.get('telegram_by_type', {})
            if telegram_by_type:
                text += "\n*روابط تيليجرام حسب النوع:*\n"
                for link_type, count in telegram_by_type.items():
                    if link_type:
                        text += f"• {link_type}: {count}\n"
            
            total_sessions = get_session_count()
            text += f"\n*الجلسات النشطة:* {total_sessions}"
            
            await query.message.edit_text(text, parse_mode="Markdown")
        
        # اختبار الجلسات
        elif data == "test_sessions":
            sessions = get_sessions_from_db()
            
            if not sessions:
                await query.message.edit_text("❌ لا توجد جلسات لاختبارها")
                return
            
            await query.message.edit_text("🔍 جاري اختبار الجلسات...")
            
            valid_count = 0
            for session in sessions:
                session_string = session.get('session_string', '')
                if session_string and len(session_string) > 50:
                    valid_count += 1
            
            await query.message.edit_text(
                f"📊 *نتائج اختبار الجلسات*\n\n"
                f"• الإجمالي: {len(sessions)}\n"
                f"• الصالحة: {valid_count}\n"
                f"• غير صالحة: {len(sessions) - valid_count}",
                parse_mode="Markdown"
            )
        
        else:
            await query.message.edit_text("❌ أمر غير معروف")
    
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.message.edit_text("❌ حدث خطأ في المعالجة")

async def show_links_page(query, platform: str, link_type: str, page: int):
    """عرض صفحة من الروابط"""
    limit = 10
    offset = page * limit
    
    links = get_links_from_db(platform, link_type, limit, offset)
    total_count = get_link_count(platform, link_type)
    
    if not links and page == 0:
        type_names = {
            "channel": "القنوات",
            "group": "المجموعات",
            "bot": "البوتات",
            "message": "الرسائل"
        }
        display_type = type_names.get(link_type, link_type)
        
        await query.message.edit_text(
            f"📭 لا توجد روابط {display_type} لـ {platform}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", 
                    callback_data=f"platform_{platform}")
            ]])
        )
        return
    
    # نوع العرض
    type_names = {
        "channel": "القنوات",
        "group": "المجموعات",
        "bot": "البوتات",
        "message": "الرسائل"
    }
    display_type = type_names.get(link_type, link_type)
    
    text = f"🔗 *روابط {platform} - {display_type}*\n\n"
    text += f"📄 الصفحة: {page + 1}\n"
    text += f"📊 العدد: {total_count} رابط\n\n"
    
    for i, link in enumerate(links, start=offset + 1):
        url = link.get('url', '')
        text += f"{i}. `{url}`\n"
    
    # أزرار التصفح
    has_next = (offset + limit) < total_count
    
    keyboard = []
    if page > 0:
        keyboard.append(
            InlineKeyboardButton("⬅️ السابق", 
                callback_data=f"view_{platform}_{link_type}_{page-1}")
        )
    
    keyboard.append(InlineKeyboardButton(f"📄 {page+1}", callback_data="current_page"))
    
    if has_next:
        keyboard.append(
            InlineKeyboardButton("➡️ التالي", 
                callback_data=f"view_{platform}_{link_type}_{page+1}")
        )
    
    # زر الرجوع
    back_button = [InlineKeyboardButton("🔙 رجوع", 
        callback_data=f"platform_{platform}")]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([keyboard, back_button]),
        parse_mode="Markdown"
    )

# ======================
# Message Handler
# ======================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    if context.user_data.get('awaiting_session'):
        context.user_data['awaiting_session'] = False
        
        session_string = update.message.text.strip()
        
        if not session_string or len(session_string) < 50:
            await update.message.reply_text(
                "❌ Session String غير صالح\nيجب أن يكون أطول من 50 حرف",
                reply_markup=main_menu_keyboard()
            )
            return
        
        await update.message.reply_text("🔍 جاري إضافة الجلسة...")
        
        try:
            # التحقق من الجلسة
            is_valid, account_info = await validate_session_string(session_string)
            
            if not is_valid:
                await update.message.reply_text(
                    "✅ تمت إضافة الجلسة (مع تحذيرات)",
                    reply_markup=main_menu_keyboard()
                )
                return
            
            # إضافة الجلسة إلى قاعدة البيانات
            success = add_session_to_db(session_string, account_info)
            
            if success:
                phone = account_info.get('phone', '')
                username = account_info.get('username', '')
                user_id = account_info.get('user_id', 0)
                
                display_name = account_info.get('first_name', '') or username or f"User_{user_id}"
                
                await update.message.reply_text(
                    f"✅ *تمت إضافة الجلسة بنجاح*\n\n"
                    f"• الاسم: {display_name}\n"
                    f"• المعرف: {user_id}\n"
                    f"• المستخدم: @{username}\n"
                    f"• الهاتف: {phone}",
                    parse_mode="Markdown",
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
                f"✅ تمت إضافة الجلسة\n\n{str(e)[:100]}",
                reply_markup=main_menu_keyboard()
            )
    
    else:
        # رد افتراضي
        await update.message.reply_text(
            "👋 استخدم الأزرار للتحكم في البوت",
            reply_markup=main_menu_keyboard()
        )

# ======================
# Main Function
# ======================

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    # تهيئة قاعدة البيانات
    init_database()
    
    # إنشاء تطبيق البوت
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stats", lambda u, c: handle_callback(u, c)))
    
    # معالج الردود
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # معالج الرسائل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # بدء البوت
    logger.info("🤖 Starting Telegram Link Collector Bot...")
    logger.info(f"📊 Active sessions: {get_session_count()}")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
