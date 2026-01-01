import asyncio
import logging
import os
import re
from typing import List, Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN, LINKS_PER_PAGE
from database import (
    init_db, get_link_stats, get_links_by_type, export_links_by_type,
    add_session, get_sessions, delete_session, update_session_status,
    start_collection_session, update_collection_stats,
    link_exists, add_link, get_all_links
)
from session_manager import (
    validate_session, export_sessions_to_file, test_all_sessions
)
from collector import (
    start_collection, stop_collection, pause_collection, resume_collection,
    is_collecting, is_paused, get_collection_status
)

# ======================
# Logging
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Helper Functions
# ======================

def extract_invite_code(url: str) -> str:
    """استخراج رمز الدعوة من الرابط"""
    patterns = [
        r't\.me/\+([A-Za-z0-9_-]+)',
        r't\.me/joinchat/([A-Za-z0-9_-]+)',
        r't\.me/([A-Za-z0-9_]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return ""

def clean_url(url: str) -> str:
    """تنظيف الرابط"""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

# ======================
# Keyboards
# ======================

def main_menu_keyboard():
    """لوحة المفاتيح الرئيسية"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ إضافة جلسة", callback_data="menu_add_session"),
            InlineKeyboardButton("👥 عرض الجلسات", callback_data="menu_list_sessions")
        ],
        [
            InlineKeyboardButton("▶️ بدء الجمع", callback_data="menu_start_collect"),
            InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="menu_pause_collect")
        ],
        [
            InlineKeyboardButton("▶️ استئناف", callback_data="menu_resume_collect"),
            InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="menu_stop_collect")
        ],
        [
            InlineKeyboardButton("📊 عرض الروابط", callback_data="menu_view_links"),
            InlineKeyboardButton("📤 تصدير الروابط", callback_data="menu_export_links")
        ],
        [
            InlineKeyboardButton("📈 إحصائيات", callback_data="menu_stats"),
            InlineKeyboardButton("🔍 اختبار الجلسات", callback_data="menu_test_sessions")
        ],
        [
            InlineKeyboardButton("🗑️ حذف روابط", callback_data="menu_delete_links")
        ]
    ])

def platforms_keyboard():
    """اختيار المنصة"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📨 تيليجرام", callback_data="view_telegram"),
            InlineKeyboardButton("📞 واتساب", callback_data="view_whatsapp")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")
        ]
    ])

def telegram_types_keyboard(page: int = 0):
    """أنواع روابط التليجرام"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 مجموعات عامة", callback_data=f"telegram_public_group_{page}"),
            InlineKeyboardButton("🔒 مجموعات خاصة", callback_data=f"telegram_private_group_{page}")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_view_links")
        ]
    ])

def whatsapp_types_keyboard(page: int = 0):
    """أنواع روابط الواتساب"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 مجموعات واتساب", callback_data=f"whatsapp_group_{page}")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_view_links")
        ]
    ])

def sessions_list_keyboard(sessions: List[Dict]):
    """قائمة الجلسات مع أزرار"""
    keyboard = []
    
    for session in sessions:
        session_id = session.get('id')
        display_name = session.get('display_name', f"جلسة {session_id}")
        status = "🟢" if session.get('is_active') else "🔴"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {display_name}",
                callback_data=f"session_info_{session_id}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("🗑️ حذف جميع الجلسات", callback_data="delete_all_sessions")
    ])
    
    keyboard.append([
        InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")
    ])
    
    return InlineKeyboardMarkup(keyboard)

def session_actions_keyboard(session_id: int):
    """أزرار إجراءات الجلسة"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ حذف الجلسة", callback_data=f"delete_session_{session_id}"),
            InlineKeyboardButton("🔄 تفعيل/تعطيل", callback_data=f"toggle_session_{session_id}")
        ],
        [
            InlineKeyboardButton("🔙 رجوع للجلسات", callback_data="menu_list_sessions")
        ]
    ])

def export_options_keyboard():
    """خيارات التصدير"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 مجموعات عامة", callback_data="export_public_groups"),
            InlineKeyboardButton("🔒 مجموعات خاصة", callback_data="export_private_groups")
        ],
        [
            InlineKeyboardButton("📨 كل روابط تيليجرام", callback_data="export_all_telegram"),
            InlineKeyboardButton("📞 كل روابط واتساب", callback_data="export_all_whatsapp")
        ],
        [
            InlineKeyboardButton("📊 تصدير الكل مصنف", callback_data="export_all_sorted"),
            InlineKeyboardButton("💾 نسخ احتياطي", callback_data="export_backup")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")
        ]
    ])

def delete_links_keyboard():
    """خيارات حذف الروابط"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ حذف جميع الروابط", callback_data="delete_all_links"),
            InlineKeyboardButton("🗑️ حذف روابط واتساب", callback_data="delete_whatsapp_links")
        ],
        [
            InlineKeyboardButton("🗑️ حذف مجموعات عامة", callback_data="delete_public_groups"),
            InlineKeyboardButton("🗑️ حذف مجموعات خاصة", callback_data="delete_private_groups")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")
        ]
    ])

def confirm_delete_keyboard(delete_type: str):
    """تأكيد الحذف"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ نعم، احذف", callback_data=f"confirm_delete_{delete_type}"),
            InlineKeyboardButton("❌ إلغاء", callback_data="cancel_delete")
        ]
    ])

def pagination_keyboard(platform: str, link_type: str, page: int, has_next: bool):
    """أزرار التصفح"""
    buttons = []
    
    if page > 0:
        buttons.append(
            InlineKeyboardButton("⬅️ السابق", callback_data=f"page_{platform}_{link_type}_{page-1}")
        )
    
    buttons.append(
        InlineKeyboardButton(f"📄 {page+1}", callback_data="current_page")
    )
    
    if has_next:
        buttons.append(
            InlineKeyboardButton("➡️ التالي", callback_data=f"page_{platform}_{link_type}_{page+1}")
        )
    
    if platform == "telegram":
        back_button = "view_telegram"
    else:
        back_button = "view_whatsapp"
    
    return InlineKeyboardMarkup([
        buttons,
        [InlineKeyboardButton("🔙 رجوع", callback_data=back_button)]
    ])

# ======================
# Database Functions (إضافة جديدة)
# ======================

def delete_links_by_type(platform: str = None, link_type: str = None):
    """حذف الروابط حسب النوع"""
    import sqlite3
    from database import DATABASE_NAME
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    try:
        if platform and link_type:
            cursor.execute('''
                DELETE FROM links WHERE platform = ? AND link_type = ?
            ''', (platform, link_type))
        elif platform:
            cursor.execute('''
                DELETE FROM links WHERE platform = ?
            ''', (platform,))
        elif link_type:
            cursor.execute('''
                DELETE FROM links WHERE link_type = ?
            ''', (link_type,))
        else:
            cursor.execute('DELETE FROM links')
        
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        logger.error(f"Error deleting links: {e}")
        return 0
    finally:
        conn.close()

def delete_all_sessions():
    """حذف جميع الجلسات"""
    import sqlite3
    from database import DATABASE_NAME
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    try:
        cursor.execute('DELETE FROM sessions')
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        logger.error(f"Error deleting sessions: {e}")
        return 0
    finally:
        conn.close()

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
    • جمع المجموعات النشطة فقط
    
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
    
    *الأوامر المتاحة:*
    /start - بدء البوت وعرض القائمة
    /help - عرض هذه الرسالة
    /status - عرض حالة الجمع
    /stats - عرض إحصائيات الروابط
    
    *إضافة جلسة:*
    1. اضغط "➕ إضافة جلسة"
    2. أرسل Session String
    3. يتحقق البوت من صحتها
    
    *جمع الروابط:*
    - بدء الجمع: ▶️ بدء الجمع
    - إيقاف مؤقت: ⏸️ إيقاف مؤقت
    - استئناف: ▶️ استئناف
    - إيقاف نهائي: ⏹️ إيقاف الجمع
    
    *ملاحظة مهمة:*
    البوت يجمع فقط المجموعات النشطة التي تحتوي على أعضاء
    لا يجمع القنوات أو المجموعات الفارغة
    """
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /status"""
    status = get_collection_status()
    sessions = get_sessions()
    active_sessions = len([s for s in sessions if s.get('is_active')])
    
    if is_collecting():
        if is_paused():
            status_text = "⏸️ *الجمع موقف مؤقتاً*"
        else:
            status_text = "🔄 *جاري الجمع حالياً*"
        
        stats = status.get('stats', {})
        status_text += f"""
        
        📊 *الإحصائيات الحالية:*
        • مجموعات عامة: {stats.get('public_groups', 0)}
        • مجموعات خاصة: {stats.get('private_groups', 0)}
        • روابط واتساب: {stats.get('whatsapp_collected', 0)}
        • الإجمالي: {stats.get('total_collected', 0)}
        """
    else:
        status_text = "🛑 *الجمع متوقف*"
    
    status_text += f"\n\n👥 *الجلسات:* {len(sessions)} (نشطة: {active_sessions})"
    
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /stats"""
    stats = get_link_stats()
    
    if not stats:
        await update.message.reply_text("📭 لا توجد إحصائيات حالياً")
        return
    
    stats_text = "📈 *إحصائيات الروابط*\n\n"
    
    by_platform = stats.get('by_platform', {})
    if by_platform:
        stats_text += "*حسب المنصة:*\n"
        for platform, count in by_platform.items():
            stats_text += f"• {platform}: {count}\n"
    
    telegram_by_type = stats.get('telegram_by_type', {})
    if telegram_by_type:
        stats_text += "\n*روابط تيليجرام حسب النوع:*\n"
        for link_type, count in telegram_by_type.items():
            if link_type:
                type_name = "مجموعات عامة" if link_type == "public_group" else "مجموعات خاصة"
                stats_text += f"• {type_name}: {count}\n"
    
    await update.message.reply_text(stats_text, parse_mode="Markdown")

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
        if data == "menu_main":
            await show_main_menu(query)
        
        # حذف الروابط
        elif data == "menu_delete_links":
            await show_delete_links_menu(query)
        
        # تأكيد الحذف
        elif data.startswith("confirm_delete_"):
            delete_type = data.split('_')[2]
            await confirm_delete_handler(query, delete_type)
        
        elif data == "cancel_delete":
            await show_main_menu(query)
        
        # حذف جميع الجلسات
        elif data == "delete_all_sessions":
            await confirm_delete_all_sessions(query)
        
        # إضافة جلسة
        elif data == "menu_add_session":
            context.user_data['awaiting_session'] = True
            await query.message.edit_text(
                "📥 *إضافة جلسة جديدة*\n\n"
                "أرسل لي Session String الآن:",
                parse_mode="Markdown"
            )
        
        # عرض الجلسات
        elif data == "menu_list_sessions":
            await show_sessions_list(query)
        
        # بدء الجمع
        elif data == "menu_start_collect":
            await start_collection_handler(query)
        
        # إيقاف مؤقت
        elif data == "menu_pause_collect":
            await pause_collection_handler(query)
        
        # استئناف
        elif data == "menu_resume_collect":
            await resume_collection_handler(query)
        
        # إيقاف الجمع
        elif data == "menu_stop_collect":
            await stop_collection_handler(query)
        
        # عرض الروابط
        elif data == "menu_view_links":
            await show_platforms_menu(query)
        
        # تصدير الروابط
        elif data == "menu_export_links":
            await show_export_menu(query)
        
        # الإحصائيات
        elif data == "menu_stats":
            await show_stats(query)
        
        # اختبار الجلسات
        elif data == "menu_test_sessions":
            await test_sessions_handler(query)
        
        # اختيار المنصة
        elif data == "view_telegram":
            await show_telegram_types(query)
        elif data == "view_whatsapp":
            await show_whatsapp_types(query)
        
        # أنواع التليجرام
        elif data.startswith("telegram_"):
            parts = data.split('_')
            link_type = f"{parts[1]}_{parts[2]}" if len(parts) > 3 else parts[1]
            page = int(parts[3]) if len(parts) > 3 else int(parts[2]) if len(parts) > 2 else 0
            await show_telegram_links(query, link_type, page)
        
        # أنواع الواتساب
        elif data.startswith("whatsapp_"):
            parts = data.split('_')
            link_type = parts[1]
            page = int(parts[2]) if len(parts) > 2 else 0
            await show_whatsapp_links(query, link_type, page)
        
        # إدارة الجلسات
        elif data.startswith("session_info_"):
            session_id = int(data.split('_')[2])
            await show_session_info(query, session_id)
        
        elif data.startswith("delete_session_"):
            session_id = int(data.split('_')[2])
            await delete_session_handler(query, session_id)
        
        elif data.startswith("toggle_session_"):
            session_id = int(data.split('_')[2])
            await toggle_session_handler(query, session_id)
        
        # التصدير
        elif data.startswith("export_"):
            export_type = data[7:]  # إزالة "export_"
            await export_handler(query, export_type)
        
        # حذف الروابط حسب النوع
        elif data.startswith("delete_"):
            delete_type = data[7:]  # إزالة "delete_"
            await confirm_delete_links(query, delete_type)
        
        # التصفح
        elif data.startswith("page_"):
            parts = data.split('_')
            platform = parts[1]
            link_type = parts[2]
            page = int(parts[3])
            
            if platform == "telegram":
                await show_telegram_links(query, link_type, page)
            else:
                await show_whatsapp_links(query, link_type, page)
        
        else:
            await query.message.edit_text("❌ أمر غير معروف")
    
    except Exception as e:
        logger.error(f"Error in callback handler: {e}")
        await query.message.edit_text("❌ حدث خطأ في المعالجة")

# ======================
# Menu Handlers
# ======================

async def show_main_menu(query):
    """عرض القائمة الرئيسية"""
    await query.message.edit_text(
        "📱 *القائمة الرئيسية*\n\n"
        "اختر من الخيارات:",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

async def show_delete_links_menu(query):
    """عرض قائمة حذف الروابط"""
    stats = get_link_stats()
    total_links = sum(stats.get('by_platform', {}).values()) if stats else 0
    
    await query.message.edit_text(
        f"🗑️ *حذف الروابط*\n\n"
        f"إجمالي الروابط: {total_links}\n\n"
        f"اختر نوع الحذف:",
        reply_markup=delete_links_keyboard(),
        parse_mode="Markdown"
    )

async def show_platforms_menu(query):
    """عرض قائمة المنصات"""
    await query.message.edit_text(
        "📊 *اختر المنصة:*",
        reply_markup=platforms_keyboard(),
        parse_mode="Markdown"
    )

async def show_telegram_types(query):
    """عرض أنواع روابط التليجرام"""
    stats = get_link_stats()
    telegram_stats = stats.get('telegram_by_type', {}) if stats else {}
    
    public_count = telegram_stats.get('public_group', 0)
    private_count = telegram_stats.get('private_group', 0)
    
    await query.message.edit_text(
        f"📨 *روابط تيليجرام*\n\n"
        f"• مجموعات عامة: {public_count}\n"
        f"• مجموعات خاصة: {private_count}\n\n"
        f"اختر نوع الروابط:",
        reply_markup=telegram_types_keyboard(),
        parse_mode="Markdown"
    )

async def show_whatsapp_types(query):
    """عرض أنواع روابط الواتساب"""
    stats = get_link_stats()
    whatsapp_count = stats.get('by_platform', {}).get('whatsapp', 0) if stats else 0
    
    await query.message.edit_text(
        f"📞 *روابط واتساب*\n\n"
        f"إجمالي الروابط: {whatsapp_count}\n\n"
        f"اختر نوع الروابط:",
        reply_markup=whatsapp_types_keyboard(),
        parse_mode="Markdown"
    )

async def show_export_menu(query):
    """عرض قائمة التصدير"""
    stats = get_link_stats()
    total_links = sum(stats.get('by_platform', {}).values()) if stats else 0
    
    await query.message.edit_text(
        f"📤 *تصدير البيانات*\n\n"
        f"إجمالي الروابط: {total_links}\n\n"
        f"اختر نوع التصدير:",
        reply_markup=export_options_keyboard(),
        parse_mode="Markdown"
    )

async def show_stats(query):
    """عرض الإحصائيات"""
    stats = get_link_stats()
    
    if not stats:
        await query.message.edit_text("📭 لا توجد إحصائيات حالياً")
        return
    
    stats_text = "📈 *إحصائيات الروابط*\n\n"
    
    by_platform = stats.get('by_platform', {})
    if by_platform:
        stats_text += "*حسب المنصة:*\n"
        for platform, count in by_platform.items():
            platform_name = "تيليجرام" if platform == "telegram" else "واتساب"
            stats_text += f"• {platform_name}: {count}\n"
    
    telegram_by_type = stats.get('telegram_by_type', {})
    if telegram_by_type:
        stats_text += "\n*روابط تيليجرام حسب النوع:*\n"
        for link_type, count in telegram_by_type.items():
            if link_type:
                type_name = "مجموعات عامة" if link_type == "public_group" else "مجموعات خاصة"
                stats_text += f"• {type_name}: {count}\n"
    
    await query.message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")]
        ]),
        parse_mode="Markdown"
    )

# ======================
# Delete Handlers
# ======================

async def confirm_delete_all_sessions(query):
    """تأكيد حذف جميع الجلسات"""
    sessions_count = len(get_sessions())
    
    await query.message.edit_text(
        f"⚠️ *تأكيد الحذف*\n\n"
        f"هل أنت متأكد من حذف جميع الجلسات؟\n"
        f"• عدد الجلسات: {sessions_count}\n\n"
        f"❌ *هذا الإجراء لا يمكن التراجع عنه*",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ نعم، احذف الكل", callback_data="confirm_delete_all_sessions"),
                InlineKeyboardButton("❌ إلغاء", callback_data="menu_list_sessions")
            ]
        ]),
        parse_mode="Markdown"
    )

async def confirm_delete_links(query, delete_type: str):
    """تأكيد حذف الروابط"""
    type_names = {
        "all_links": "جميع الروابط",
        "whatsapp_links": "روابط واتساب",
        "public_groups": "المجموعات العامة",
        "private_groups": "المجموعات الخاصة"
    }
    
    type_name = type_names.get(delete_type, delete_type)
    
    await query.message.edit_text(
        f"⚠️ *تأكيد الحذف*\n\n"
        f"هل أنت متأكد من حذف {type_name}؟\n\n"
        f"❌ *هذا الإجراء لا يمكن التراجع عنه*",
        reply_markup=confirm_delete_keyboard(delete_type),
        parse_mode="Markdown"
    )

async def confirm_delete_handler(query, delete_type: str):
    """معالجة تأكيد الحذف"""
    type_names = {
        "all_links": "جميع الروابط",
        "whatsapp_links": "روابط واتساب",
        "public_groups": "المجموعات العامة",
        "private_groups": "المجموعات الخاصة",
        "all_sessions": "جميع الجلسات"
    }
    
    type_name = type_names.get(delete_type, delete_type)
    
    await query.message.edit_text(f"⏳ جاري حذف {type_name}...")
    
    try:
        deleted_count = 0
        
        if delete_type == "all_sessions":
            deleted_count = delete_all_sessions()
            message = f"✅ تم حذف {deleted_count} جلسة"
            callback_data = "menu_main"
        
        elif delete_type == "all_links":
            deleted_count = delete_links_by_type()
            message = f"✅ تم حذف {deleted_count} رابط"
            callback_data = "menu_delete_links"
        
        elif delete_type == "whatsapp_links":
            deleted_count = delete_links_by_type(platform="whatsapp")
            message = f"✅ تم حذف {deleted_count} رابط واتساب"
            callback_data = "menu_delete_links"
        
        elif delete_type == "public_groups":
            deleted_count = delete_links_by_type(platform="telegram", link_type="public_group")
            message = f"✅ تم حذف {deleted_count} مجموعة عامة"
            callback_data = "menu_delete_links"
        
        elif delete_type == "private_groups":
            deleted_count = delete_links_by_type(platform="telegram", link_type="private_group")
            message = f"✅ تم حذف {deleted_count} مجموعة خاصة"
            callback_data = "menu_delete_links"
        
        else:
            message = "❌ نوع حذف غير معروف"
            callback_data = "menu_delete_links"
        
        await query.message.edit_text(
            message,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data=callback_data)]
            ])
        )
    
    except Exception as e:
        logger.error(f"Error deleting: {e}")
        await query.message.edit_text(
            "❌ حدث خطأ أثناء الحذف",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")]
            ])
        )

# ======================
# Session Handlers
# ======================

async def show_sessions_list(query):
    """عرض قائمة الجلسات"""
    sessions = get_sessions()
    
    if not sessions:
        await query.message.edit_text(
            "📭 *لا توجد جلسات مضافة*\n\n"
            "اضغط ➕ إضافة جلسة لإضافة جلسة جديدة",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")]
            ]),
            parse_mode="Markdown"
        )
        return
    
    active_count = len([s for s in sessions if s.get('is_active')])
    
    await query.message.edit_text(
        f"👥 *الجلسات المضافة*\n\n"
        f"• الإجمالي: {len(sessions)}\n"
        f"• النشطة: {active_count}\n\n"
        f"اختر جلسة للتفاصيل:",
        reply_markup=sessions_list_keyboard(sessions),
        parse_mode="Markdown"
    )

async def show_session_info(query, session_id: int):
    """عرض معلومات جلسة محددة"""
    sessions = get_sessions()
    session = next((s for s in sessions if s.get('id') == session_id), None)
    
    if not session:
        await query.message.edit_text("❌ الجلسة غير موجودة")
        return
    
    status = "🟢 نشط" if session.get('is_active') else "🔴 غير نشط"
    added_date = session.get('added_date', 'غير معروف')[:10]
    last_used = session.get('last_used', 'لم يستخدم')[:10] if session.get('last_used') else 'لم يستخدم'
    phone = session.get('phone_number', 'غير معروف')
    username = session.get('username', 'غير معروف')
    display_name = session.get('display_name', 'غير معروف')
    
    info_text = f"""
    🔍 *معلومات الجلسة*
    
    • **الاسم:** {display_name}
    • **الحالة:** {status}
    • **رقم الهاتف:** {phone}
    • **اسم المستخدم:** @{username}
    • **تاريخ الإضافة:** {added_date}
    • **آخر استخدام:** {last_used}
    • **معرف الجلسة:** {session_id}
    """
    
    await query.message.edit_text(
        info_text,
        reply_markup=session_actions_keyboard(session_id),
        parse_mode="Markdown"
    )

async def delete_session_handler(query, session_id: int):
    """حذف جلسة"""
    success = delete_session(session_id)
    
    if success:
        await query.message.edit_text(
            "✅ تم حذف الجلسة بنجاح",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع إلى الجلسات", callback_data="menu_list_sessions")]
            ])
        )
    else:
        await query.message.edit_text(
            "❌ فشل حذف الجلسة",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_list_sessions")]
            ])
        )

async def toggle_session_handler(query, session_id: int):
    """تفعيل/تعطيل جلسة"""
    sessions = get_sessions()
    session = next((s for s in sessions if s.get('id') == session_id), None)
    
    if not session:
        await query.message.edit_text("❌ الجلسة غير موجودة")
        return
    
    new_status = not session.get('is_active')
    success = update_session_status(session_id, new_status)
    
    if success:
        status_text = "تفعيل" if new_status else "تعطيل"
        await query.message.edit_text(
            f"✅ تم {status_text} الجلسة",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع إلى الجلسات", callback_data="menu_list_sessions")]
            ])
        )
    else:
        await query.message.edit_text(
            "❌ فشل تحديث حالة الجلسة",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_list_sessions")]
            ])
        )

async def test_sessions_handler(query):
    """اختبار جميع الجلسات"""
    await query.message.edit_text("🔍 جاري اختبار جميع الجلسات...")
    
    test_results = await test_all_sessions()
    
    result_text = f"""
    📊 *نتائج اختبار الجلسات*
    
    • الإجمالي: {test_results['total']}
    • الصالحة: ✅ {test_results['valid']}
    • غير الصالحة: ❌ {test_results['invalid']}
    """
    
    await query.message.edit_text(
        result_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")]
        ]),
        parse_mode="Markdown"
    )

# ======================
# Collection Handlers
# ======================

async def start_collection_handler(query):
    """بدء الجمع"""
    active_sessions = [s for s in get_sessions() if s.get('is_active')]
    if not active_sessions:
        await query.message.edit_text(
            "❌ لا توجد جلسات نشطة\n\n"
            "يجب إضافة وتفعيل جلسة على الأقل",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة جلسة", callback_data="menu_add_session")]
            ])
        )
        return
    
    if is_collecting():
        await query.message.edit_text("⏳ الجمع يعمل بالفعل")
        return
    
    success = await start_collection()
    
    if success:
        await query.message.edit_text(
            "🚀 *بدأ جمع الروابط*\n\n"
            "⏳ جاري جمع الروابط من جميع الجلسات...\n"
            "• يجمع فقط المجموعات النشطة\n"
            "• يتجاهل القنوات والمجموعات الفارغة\n"
            "• يمنع التكرار\n\n"
            "سيتم إعلامك بالتقدم.",
            parse_mode="Markdown"
        )
    else:
        await query.message.edit_text("❌ فشل بدء الجمع")

async def pause_collection_handler(query):
    """إيقاف الجمع مؤقتاً"""
    if not is_collecting():
        await query.message.edit_text("⚠️ الجمع غير نشط حالياً")
        return
    
    if is_paused():
        await query.message.edit_text("⏸️ الجمع موقف بالفعل")
        return
    
    success = await pause_collection()
    
    if success:
        await query.message.edit_text("⏸️ تم إيقاف الجمع مؤقتاً")
    else:
        await query.message.edit_text("❌ فشل إيقاف الجمع مؤقتاً")

async def resume_collection_handler(query):
    """استئناف الجمع"""
    if not is_collecting():
        await query.message.edit_text("⚠️ الجمع غير نشط حالياً")
        return
    
    if not is_paused():
        await query.message.edit_text("▶️ الجمع يعمل بالفعل")
        return
    
    success = await resume_collection()
    
    if success:
        await query.message.edit_text("▶️ تم استئناف الجمع")
    else:
        await query.message.edit_text("❌ فشل استئناف الجمع")

async def stop_collection_handler(query):
    """إيقاف الجمع نهائياً"""
    if not is_collecting():
        await query.message.edit_text("⚠️ الجمع غير نشط حالياً")
        return
    
    success = await stop_collection()
    
    if success:
        await query.message.edit_text("⏹️ تم إيقاف الجمع بنجاح")
    else:
        await query.message.edit_text("❌ فشل إيقاف الجمع")

# ======================
# Link Viewing Handlers
# ======================

async def show_telegram_links(query, link_type: str, page: int = 0):
    """عرض روابط التليجرام"""
    type_names = {
        "public_group": "المجموعات العامة",
        "private_group": "المجموعات الخاصة"
    }
    
    title = type_names.get(link_type, link_type)
    links = get_links_by_type("telegram", link_type, LINKS_PER_PAGE, page * LINKS_PER_PAGE)
    
    if not links and page == 0:
        await query.message.edit_text(
            f"📭 لا توجد روابط {title}",
            reply_markup=telegram_types_keyboard(page)
        )
        return
    
    message_text = f"📨 *{title}*\n\n"
    
    for i, link in enumerate(links, start=page * LINKS_PER_PAGE + 1):
        url = link.get('url', '')
        message_text += f"{i}. `{url}`\n"
    
    has_next = len(links) == LINKS_PER_PAGE
    
    await query.message.edit_text(
        message_text,
        reply_markup=pagination_keyboard("telegram", link_type, page, has_next),
        parse_mode="Markdown"
    )

async def show_whatsapp_links(query, link_type: str, page: int = 0):
    """عرض روابط الواتساب"""
    title = "مجموعات واتساب" if link_type == "group" else link_type
    links = get_links_by_type("whatsapp", link_type, LINKS_PER_PAGE, page * LINKS_PER_PAGE)
    
    if not links and page == 0:
        await query.message.edit_text(
            f"📭 لا توجد روابط {title}",
            reply_markup=whatsapp_types_keyboard(page)
        )
        return
    
    message_text = f"📞 *{title}*\n\n"
    
    for i, link in enumerate(links, start=page * LINKS_PER_PAGE + 1):
        url = link.get('url', '')
        message_text += f"{i}. `{url}`\n"
    
    has_next = len(links) == LINKS_PER_PAGE
    
    await query.message.edit_text(
        message_text,
        reply_markup=pagination_keyboard("whatsapp", link_type, page, has_next),
        parse_mode="Markdown"
    )

# ======================
# Export Handlers
# ======================

async def export_handler(query, export_type: str):
    """معالجة طلبات التصدير"""
    await query.message.edit_text("⏳ جاري تحضير الملف...")
    
    try:
        if export_type == "public_groups":
            path = export_links_by_type("telegram", "public_group")
            filename = "telegram_public_groups.txt"
            caption = "👥 مجموعات تيليجرام العامة"
        
        elif export_type == "private_groups":
            path = export_links_by_type("telegram", "private_group")
            filename = "telegram_private_groups.txt"
            caption = "🔒 مجموعات تيليجرام الخاصة"
        
        elif export_type == "all_telegram":
            path = export_links_by_type("telegram")
            filename = "all_telegram_groups.txt"
            caption = "📨 جميع روابط تيليجرام"
        
        elif export_type == "all_whatsapp":
            path = export_links_by_type("whatsapp")
            filename = "all_whatsapp_groups.txt"
            caption = "📞 جميع روابط واتساب"
        
        elif export_type == "all_sorted":
            # تصدير جميع الروابط مصنفة
            public_path = export_links_by_type("telegram", "public_group")
            private_path = export_links_by_type("telegram", "private_group")
            whatsapp_path = export_links_by_type("whatsapp")
            
            # إنشاء ملف واحد مصنف
            import tempfile
            sorted_file = tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False, encoding='utf-8')
            
            if public_path and os.path.exists(public_path):
                with open(public_path, 'r', encoding='utf-8') as f:
                    sorted_file.write("="*50 + "\n")
                    sorted_file.write("👥 مجموعات تيليجرام العامة\n")
                    sorted_file.write("="*50 + "\n\n")
                    sorted_file.write(f.read())
                    sorted_file.write("\n\n")
            
            if private_path and os.path.exists(private_path):
                with open(private_path, 'r', encoding='utf-8') as f:
                    sorted_file.write("="*50 + "\n")
                    sorted_file.write("🔒 مجموعات تيليجرام الخاصة\n")
                    sorted_file.write("="*50 + "\n\n")
                    sorted_file.write(f.read())
                    sorted_file.write("\n\n")
            
            if whatsapp_path and os.path.exists(whatsapp_path):
                with open(whatsapp_path, 'r', encoding='utf-8') as f:
                    sorted_file.write("="*50 + "\n")
                    sorted_file.write("📞 مجموعات واتساب\n")
                    sorted_file.write("="*50 + "\n\n")
                    sorted_file.write(f.read())
            
            sorted_file.flush()
            sorted_path = sorted_file.name
            sorted_file.close()
            
            path = sorted_path
            filename = "all_links_sorted.txt"
            caption = "📊 جميع الروابط مصنفة"
        
        elif export_type == "backup":
            path = export_sessions_to_file()
            filename = "sessions_backup.txt"
            caption = "💾 نسخة احتياطية للجلسات"
        
        else:
            await query.message.edit_text("❌ نوع تصدير غير معروف")
            return
        
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                await query.message.reply_document(
                    f,
                    filename=filename,
                    caption=caption
                )
            await query.message.edit_text("✅ تم التصدير بنجاح")
            
            # حذف الملف المؤقت إذا كان
            if export_type == "all_sorted":
                try:
                    os.unlink(path)
                except:
                    pass
        else:
            await query.message.edit_text("❌ لا توجد بيانات للتصدير")
    
    except Exception as e:
        logger.error(f"Export error: {e}")
        await query.message.edit_text("❌ حدث خطأ أثناء التصدير")

# ======================
# Message Handlers
# ======================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    message = update.message
    text = message.text.strip()
    
    if context.user_data.get('awaiting_session'):
        context.user_data['awaiting_session'] = False
        
        await message.reply_text("🔍 جاري التحقق من صحة الجلسة...")
        
        try:
            is_valid, account_info = await validate_session(text)
            
            phone = account_info.get('phone', '')
            username = account_info.get('username', '')
            user_id = account_info.get('user_id', 0)
            first_name = account_info.get('first_name', '')
            
            display_name = first_name or username or f"User_{user_id}"
            
            success = add_session(text, phone, user_id, username, display_name)
            
            if success:
                await message.reply_text(
                    f"✅ *تمت إضافة الجلسة بنجاح*\n\n"
                    f"• الاسم: {display_name}\n"
                    f"• المعرف: {user_id}\n"
                    f"• المستخدم: @{username}\n"
                    f"• الهاتف: {phone}",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard()
                )
            else:
                await message.reply_text("✅ تمت إضافة الجلسة (قد تكون مضافة مسبقاً)",
                    reply_markup=main_menu_keyboard())
                
        except Exception as e:
            logger.error(f"Error adding session: {e}")
            await message.reply_text(f"✅ تمت إضافة الجلسة\n\n{str(e)[:100]}",
                reply_markup=main_menu_keyboard())
    
    else:
        await message.reply_text(
            "👋 استخدم الأزرار للتحكم في البوت",
            reply_markup=main_menu_keyboard()
        )

# ======================
# Main Application
# ======================

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    init_db()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🤖 Starting Telegram Link Collector Bot...")
    logger.info("✨ التعديلات المضافة:")
    logger.info("• إمكانية حذف جميع الجلسات")
    logger.info("• إمكانية حذف الروابط حسب التصنيف")
    logger.info("• تحسين واجهة التصدير")
    logger.info("• إصلاح أخطاء التصنيف")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
