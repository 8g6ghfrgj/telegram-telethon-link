import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler
)

from config import BOT_TOKEN, COLLECTION_STATUS_MESSAGES, LINKS_PER_PAGE, EXPORT_DIR
from session_manager import (
    add_session_to_db,
    get_all_sessions,
    get_active_sessions,
    delete_session,
    update_session_status,
    validate_session,
    test_all_sessions,
    export_sessions_to_file
)
from collector import (
    start_collection,
    stop_collection,
    pause_collection,
    resume_collection,
    is_collecting,
    is_paused,
    get_collection_status
)
from database import (
    init_db,
    export_links_by_type,
    get_link_stats,
    get_links_by_type,
    get_sessions as db_get_sessions
)
from link_utils import clean_link, verify_links_batch

# ======================
# Logging
# ======================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ======================
# Constants & States
# ======================

(
    AWAITING_SESSION,
    AWAITING_CONFIRMATION,
    VIEWING_LINKS
) = range(3)

# ======================
# Keyboards
# ======================

def main_menu_keyboard():
    """القائمة الرئيسية"""
    keyboard = [
        [
            InlineKeyboardButton("➕ إضافة جلسة", callback_data="menu_add_session"),
            InlineKeyboardButton("👥 عرض الجلسات", callback_data="menu_list_sessions")
        ],
        [
            InlineKeyboardButton("▶️ بدء الجمع", callback_data="menu_start_collection"),
            InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="menu_pause_collection")
        ],
        [
            InlineKeyboardButton("▶️ استئناف", callback_data="menu_resume_collection"),
            InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="menu_stop_collection")
        ],
        [
            InlineKeyboardButton("📊 عرض الروابط", callback_data="menu_view_links"),
            InlineKeyboardButton("📤 تصدير الروابط", callback_data="menu_export_links")
        ],
        [
            InlineKeyboardButton("📈 إحصائيات", callback_data="menu_stats"),
            InlineKeyboardButton("🔧 إعدادات", callback_data="menu_settings")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def platforms_keyboard():
    """اختيار المنصة"""
    keyboard = [
        [
            InlineKeyboardButton("📨 تيليجرام", callback_data="platform_telegram"),
            InlineKeyboardButton("📞 واتساب", callback_data="platform_whatsapp")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def telegram_types_keyboard(page: int = 0):
    """أنواع روابط التليجرام"""
    keyboard = [
        [
            InlineKeyboardButton("📢 القنوات", callback_data=f"type_telegram_channel_{page}"),
            InlineKeyboardButton("👥 مجموعات عامة", callback_data=f"type_telegram_public_group_{page}")
        ],
        [
            InlineKeyboardButton("🔒 مجموعات خاصة", callback_data=f"type_telegram_private_group_{page}"),
            InlineKeyboardButton("🤖 البوتات", callback_data=f"type_telegram_bot_{page}")
        ],
        [
            InlineKeyboardButton("📩 روابط رسائل", callback_data=f"type_telegram_message_{page}"),
            InlineKeyboardButton("🔍 جميع الروابط", callback_data=f"type_telegram_all_{page}")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_platforms")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def whatsapp_types_keyboard(page: int = 0):
    """أنواع روابط الواتساب"""
    keyboard = [
        [
            InlineKeyboardButton("👥 مجموعات واتساب", callback_data=f"type_whatsapp_group_{page}"),
        ],
        [
            InlineKeyboardButton("📞 روابط أرقام", callback_data=f"type_whatsapp_phone_{page}"),
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_platforms")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def export_keyboard():
    """خيارات التصدير"""
    keyboard = [
        [
            InlineKeyboardButton("📨 تصدير تيليجرام", callback_data="export_telegram"),
            InlineKeyboardButton("📞 تصدير واتساب", callback_data="export_whatsapp")
        ],
        [
            InlineKeyboardButton("📊 تصدير الكل", callback_data="export_all"),
            InlineKeyboardButton("📁 تصدير الجلسات", callback_data="export_sessions")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def session_management_keyboard(sessions: List[Dict]):
    """إدارة الجلسات"""
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
        InlineKeyboardButton("✅ اختبار جميع الجلسات", callback_data="test_all_sessions"),
        InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def session_actions_keyboard(session_id: int):
    """أزرار إجراءات الجلسة"""
    keyboard = [
        [
            InlineKeyboardButton("❌ حذف الجلسة", callback_data=f"delete_session_{session_id}"),
            InlineKeyboardButton("🔄 تفعيل/تعطيل", callback_data=f"toggle_session_{session_id}")
        ],
        [
            InlineKeyboardButton("🔙 رجوع إلى الجلسات", callback_data="back_to_sessions")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def pagination_keyboard(platform: str, link_type: str, page: int, total_pages: int):
    """أزرار التصفح"""
    keyboard = []
    
    if page > 0:
        keyboard.append(
            InlineKeyboardButton("⬅️ السابق", callback_data=f"page_{platform}_{link_type}_{page-1}")
        )
    
    keyboard.append(
        InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="current_page")
    )
    
    if page < total_pages - 1:
        keyboard.append(
            InlineKeyboardButton("➡️ التالي", callback_data=f"page_{platform}_{link_type}_{page+1}")
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
    • جمع روابط تيليجرام وواتساب فقط
    • تصنيف وتنظيف الروابط
    • فحص الروابط قبل التجميع
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
    
    *الأوامر المتاحة:*
    /start - بدء البوت وعرض القائمة
    /help - عرض هذه الرسالة
    /status - عرض حالة الجمع الحالية
    /stats - عرض إحصائيات الروابط
    /sessions - عرض الجلسات المضافة
    
    *إضافة جلسة:*
    1. اضغط "➕ إضافة جلسة"
    2. أرسل Session String
    3. يتحقق البوت من صحتها تلقائياً
    
    *جمع الروابط:*
    - بدء الجمع: ▶️ بدء الجمع
    - إيقاف مؤقت: ⏸️ إيقاف مؤقت
    - استئناف: ▶️ استئناف
    - إيقاف نهائي: ⏹️ إيقاف الجمع
    
    *تصدير الروابط:*
    يمكن تصدير الروابط حسب التصنيف
    """
    
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /status"""
    collection_status = get_collection_status()
    
    if is_collecting():
        if is_paused():
            status_text = "⏸️ *الجمع موقف مؤقتاً*"
        else:
            status_text = "🔄 *جاري الجمع حالياً*"
        
        stats = collection_status.get('stats', {})
        status_text += f"""
        
        📊 *الإحصائيات الحالية:*
        • روابط تيليجرام: {stats.get('telegram_collected', 0)}
        • روابط واتساب: {stats.get('whatsapp_collected', 0)}
        • الإجمالي: {stats.get('total_collected', 0)}
        • المفحوصة: {stats.get('verified_count', 0)}
        """
    else:
        status_text = "🛑 *الجمع متوقف*"
    
    # معلومات الجلسات
    active_sessions = get_active_sessions()
    status_text += f"\n\n👥 *الجلسات النشطة:* {len(active_sessions)}"
    
    await update.message.reply_text(status_text, parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /stats"""
    stats = get_link_stats()
    
    if not stats:
        await update.message.reply_text("📭 لا توجد إحصائيات حالياً")
        return
    
    stats_text = "📈 *إحصائيات الروابط*\n\n"
    
    # حسب المنصة
    by_platform = stats.get('by_platform', {})
    if by_platform:
        stats_text += "*حسب المنصة:*\n"
        for platform, count in by_platform.items():
            stats_text += f"• {platform}: {count}\n"
    
    # حسب نوع التليجرام
    telegram_by_type = stats.get('telegram_by_type', {})
    if telegram_by_type:
        stats_text += "\n*روابط تيليجرام حسب النوع:*\n"
        for link_type, count in telegram_by_type.items():
            if link_type:
                stats_text += f"• {link_type}: {count}\n"
    
    # إحصائيات الفحص
    verification = stats.get('verification', {})
    if verification.get('total', 0) > 0:
        stats_text += f"\n*الفحص:*\n"
        stats_text += f"• إجمالي الروابط: {verification.get('total', 0)}\n"
        stats_text += f"• تم فحصها: {verification.get('verified', 0)}\n"
        stats_text += f"• صالحة: {verification.get('valid', 0)}\n"
    
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
        if data == "back_to_main":
            await show_main_menu(query)
        
        # إضافة جلسة
        elif data == "menu_add_session":
            context.user_data['awaiting_session'] = True
            await query.message.edit_text(
                "📥 *إضافة جلسة جديدة*\n\n"
                "أرسل لي Session String الآن:\n\n"
                "⚠️ *ملاحظة:* سيتم التحقق من صحة الجلسة تلقائياً",
                parse_mode="Markdown"
            )
        
        # عرض الجلسات
        elif data == "menu_list_sessions":
            await show_sessions_list(query)
        
        # بدء الجمع
        elif data == "menu_start_collection":
            await start_collection_handler(query)
        
        # إيقاف مؤقت
        elif data == "menu_pause_collection":
            await pause_collection_handler(query)
        
        # استئناف
        elif data == "menu_resume_collection":
            await resume_collection_handler(query)
        
        # إيقاف الجمع
        elif data == "menu_stop_collection":
            await stop_collection_handler(query)
        
        # عرض الروابط
        elif data == "menu_view_links":
            await show_platforms_menu(query)
        
        # تصدير الروابط
        elif data == "menu_export_links":
            await show_export_menu(query)
        
        # الإحصائيات
        elif data == "menu_stats":
            await stats_command(update, context)
        
        # اختيار المنصة
        elif data == "platform_telegram":
            await show_telegram_types(query)
        elif data == "platform_whatsapp":
            await show_whatsapp_types(query)
        elif data == "back_to_platforms":
            await show_platforms_menu(query)
        
        # أنواع التليجرام
        elif data.startswith("type_telegram_"):
            parts = data.split('_')
            link_type = parts[2]
            page = int(parts[3]) if len(parts) > 3 else 0
            await show_telegram_links(query, link_type, page)
        
        # أنواع الواتساب
        elif data.startswith("type_whatsapp_"):
            parts = data.split('_')
            link_type = parts[2]
            page = int(parts[3]) if len(parts) > 3 else 0
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
        
        elif data == "test_all_sessions":
            await test_sessions_handler(query)
        
        elif data == "back_to_sessions":
            await show_sessions_list(query)
        
        # التصدير
        elif data.startswith("export_"):
            export_type = data.split('_')[1]
            await export_handler(query, export_type)
        
        # التصفح
        elif data.startswith("page_"):
            parts = data.split('_')
            platform = parts[1]
            link_type = parts[2]
            page = int(parts[3])
            
            if platform == "telegram":
                await show_telegram_links(query, link_type, page)
            elif platform == "whatsapp":
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


async def show_platforms_menu(query):
    """عرض قائمة المنصات"""
    await query.message.edit_text(
        "📊 *اختر المنصة:*",
        reply_markup=platforms_keyboard(),
        parse_mode="Markdown"
    )


async def show_telegram_types(query):
    """عرض أنواع روابط التليجرام"""
    await query.message.edit_text(
        "📨 *روابط تيليجرام*\n\n"
        "اختر نوع الروابط:",
        reply_markup=telegram_types_keyboard(),
        parse_mode="Markdown"
    )


async def show_whatsapp_types(query):
    """عرض أنواع روابط الواتساب"""
    await query.message.edit_text(
        "📞 *روابط واتساب*\n\n"
        "اختر نوع الروابط:",
        reply_markup=whatsapp_types_keyboard(),
        parse_mode="Markdown"
    )


async def show_export_menu(query):
    """عرض قائمة التصدير"""
    await query.message.edit_text(
        "📤 *تصدير البيانات*\n\n"
        "اختر نوع التصدير:",
        reply_markup=export_keyboard(),
        parse_mode="Markdown"
    )


# ======================
# Session Handlers
# ======================

async def show_sessions_list(query):
    """عرض قائمة الجلسات"""
    sessions = get_all_sessions()
    
    if not sessions:
        await query.message.edit_text(
            "📭 *لا توجد جلسات مضافة*\n\n"
            "اضغط ➕ إضافة جلسة لإضافة جلسة جديدة",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
            ]]),
            parse_mode="Markdown"
        )
        return
    
    active_count = len([s for s in sessions if s.get('is_active')])
    
    await query.message.edit_text(
        f"👥 *الجلسات المضافة*\n\n"
        f"• الإجمالي: {len(sessions)}\n"
        f"• النشطة: {active_count}\n\n"
        f"اختر جلسة للتفاصيل:",
        reply_markup=session_management_keyboard(sessions),
        parse_mode="Markdown"
    )


async def show_session_info(query, session_id: int):
    """عرض معلومات جلسة محددة"""
    from database import get_connection
    import sqlite3
    
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT * FROM sessions WHERE id = ?
    """, (session_id,))
    
    row = cur.fetchone()
    conn.close()
    
    if not row:
        await query.message.edit_text("❌ الجلسة غير موجودة")
        return
    
    session = dict(row)
    
    status = "🟢 نشط" if session.get('is_active') else "🔴 غير نشط"
    added_date = session.get('added_date', 'غير معروف')
    last_used = session.get('last_used', 'لم يستخدم')
    phone = session.get('phone_number', 'غير معروف')
    username = session.get('username', 'غير معروف')
    
    info_text = f"""
    🔍 *معلومات الجلسة*
    
    • **الحالة:** {status}
    • **رقم الهاتف:** {phone}
    • **اسم المستخدم:** @{username}
    • **تاريخ الإضافة:** {added_date[:10]}
    • **آخر استخدام:** {last_used[:10] if last_used != 'لم يستخدم' else last_used}
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
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع إلى الجلسات", callback_data="back_to_sessions")
            ]])
        )
    else:
        await query.message.edit_text("❌ فشل حذف الجلسة")


async def toggle_session_handler(query, session_id: int):
    """تفعيل/تعطيل جلسة"""
    session = get_session_by_id(session_id)
    
    if not session:
        await query.message.edit_text("❌ الجلسة غير موجودة")
        return
    
    new_status = not session.get('is_active')
    success = update_session_status(session_id, new_status)
    
    if success:
        status_text = "مفعلة" if new_status else "معطلة"
        await query.message.edit_text(
            f"✅ تم {status_text} الجلسة",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع إلى الجلسات", callback_data="back_to_sessions")
            ]])
        )
    else:
        await query.message.edit_text("❌ فشل تحديث حالة الجلسة")


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
    
    if test_results['details']:
        result_text += "\n\n*التفاصيل:*\n"
        for detail in test_results['details'][:5]:  # عرض أول 5 فقط
            session_id = detail.get('session_id')
            status = detail.get('status')
            if status == 'valid':
                result_text += f"✅ جلسة {session_id}: صالحة\n"
            else:
                error = detail.get('error', 'خطأ غير معروف')
                result_text += f"❌ جلسة {session_id}: {error}\n"
    
    await query.message.edit_text(
        result_text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_sessions")
        ]]),
        parse_mode="Markdown"
    )


# ======================
# Collection Handlers
# ======================

async def start_collection_handler(query):
    """بدء الجمع"""
    # التحقق من وجود جلسات نشطة
    active_sessions = get_active_sessions()
    if not active_sessions:
        await query.message.edit_text(
            "❌ لا توجد جلسات نشطة\n\n"
            "يجب إضافة وتفعيل جلسة على الأقل",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ إضافة جلسة", callback_data="menu_add_session")
            ]])
        )
        return
    
    if is_collecting():
        await query.message.edit_text("⏳ الجمع يعمل بالفعل")
        return
    
    # بدء الجمع
    success = await start_collection()
    
    if success:
        await query.message.edit_text(
            "🚀 *بدأ جمع الروابط*\n\n"
            "⏳ جاري جمع الروابط من جميع الجلسات...\n"
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
    if link_type == "all":
        link_type_filter = None
        title = "جميع روابط تيليجرام"
    else:
        link_type_filter = link_type
        type_names = {
            "channel": "القنوات",
            "public_group": "المجموعات العامة",
            "private_group": "المجموعات الخاصة",
            "bot": "البوتات",
            "message": "روابط الرسائل"
        }
        title = f"روابط {type_names.get(link_type, link_type)}"
    
    links = get_links_by_type(
        platform="telegram",
        link_type=link_type_filter,
        limit=LINKS_PER_PAGE,
        offset=page * LINKS_PER_PAGE
    )
    
    total_count = len(get_links_by_type(
        platform="telegram",
        link_type=link_type_filter,
        limit=1000,
        offset=0
    ))
    
    total_pages = (total_count + LINKS_PER_PAGE - 1) // LINKS_PER_PAGE
    
    if not links and page == 0:
        await query.message.edit_text(
            f"📭 لا توجد روابط {title.lower()}",
            reply_markup=telegram_types_keyboard(page)
        )
        return
    
    # بناء نص الرسالة
    message_text = f"📨 *{title}*\n\n"
    message_text += f"📄 الصفحة: {page + 1} من {max(1, total_pages)}\n"
    message_text += f"📊 العدد: {total_count} رابط\n\n"
    
    for i, link in enumerate(links, start=page * LINKS_PER_PAGE + 1):
        url = link.get('url', '')
        message_text += f"{i}. `{url}`\n"
        
        if i >= (page + 1) * LINKS_PER_PAGE:
            break
    
    keyboard = pagination_keyboard("telegram", link_type, page, total_pages)
    
    await query.message.edit_text(
        message_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


async def show_whatsapp_links(query, link_type: str, page: int = 0):
    """عرض روابط الواتساب"""
    links = get_links_by_type(
        platform="whatsapp",
        link_type=link_type,
        limit=LINKS_PER_PAGE,
        offset=page * LINKS_PER_PAGE
    )
    
    total_count = len(get_links_by_type(
        platform="whatsapp",
        link_type=link_type,
        limit=1000,
        offset=0
    ))
    
    total_pages = (total_count + LINKS_PER_PAGE - 1) // LINKS_PER_PAGE
    
    if not links and page == 0:
        await query.message.edit_text(
            f"📭 لا توجد روابط {link_type} للواتساب",
            reply_markup=whatsapp_types_keyboard(page)
        )
        return
    
    type_names = {
        "group": "مجموعات واتساب",
        "phone": "روابط أرقام واتساب"
    }
    title = type_names.get(link_type, link_type)
    
    message_text = f"📞 *{title}*\n\n"
    message_text += f"📄 الصفحة: {page + 1} من {max(1, total_pages)}\n"
    message_text += f"📊 العدد: {total_count} رابط\n\n"
    
    for i, link in enumerate(links, start=page * LINKS_PER_PAGE + 1):
        url = link.get('url', '')
        message_text += f"{i}. `{url}`\n"
        
        if i >= (page + 1) * LINKS_PER_PAGE:
            break
    
    keyboard = pagination_keyboard("whatsapp", link_type, page, total_pages)
    
    await query.message.edit_text(
        message_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


# ======================
# Export Handlers
# ======================

async def export_handler(query, export_type: str):
    """معالجة طلبات التصدير"""
    await query.message.edit_text("⏳ جاري تحضير الملف...")
    
    try:
        if export_type == "telegram":
            # تصدير جميع أنواع التليجرام
            file_paths = []
            telegram_types = ["channel", "public_group", "private_group", "bot", "message"]
            
            for link_type in telegram_types:
                path = export_links_by_type("telegram", link_type)
                if path:
                    file_paths.append((path, f"telegram_{link_type}.txt"))
            
            if not file_paths:
                await query.message.edit_text("❌ لا توجد روابط تيليجرام للتصدير")
                return
            
            # إرسال جميع الملفات
            for file_path, filename in file_paths:
                with open(file_path, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename=filename,
                        caption=f"📨 روابط تيليجرام - {filename}"
                    )
            
            await query.message.edit_text("✅ تم تصدير جميع روابط تيليجرام")
        
        elif export_type == "whatsapp":
            path = export_links_by_type("whatsapp", "group")
            
            if not path:
                await query.message.edit_text("❌ لا توجد روابط واتساب للتصدير")
                return
            
            with open(path, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename="whatsapp_groups.txt",
                    caption="📞 روابط مجموعات واتساب"
                )
            
            await query.message.edit_text("✅ تم تصدير روابط واتساب")
        
        elif export_type == "all":
            # تصدير كل شيء
            path = export_links_by_type("telegram", None)
            if path:
                with open(path, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename="all_telegram_links.txt",
                        caption="📨 جميع روابط تيليجرام"
                    )
            
            path = export_links_by_type("whatsapp", None)
            if path:
                with open(path, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename="all_whatsapp_links.txt",
                        caption="📞 جميع روابط واتساب"
                    )
            
            await query.message.edit_text("✅ تم تصدير جميع الروابط")
        
        elif export_type == "sessions":
            path = export_sessions_to_file()
            
            if not path:
                await query.message.edit_text("❌ لا توجد جلسات للتصدير")
                return
            
            with open(path, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename="sessions_backup.txt",
                    caption="🔐 نسخة احتياطية للجلسات"
                )
            
            await query.message.edit_text("✅ تم تصدير الجلسات")
        
        else:
            await query.message.edit_text("❌ نوع تصدير غير معروف")
    
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
    
    # إضافة جلسة جديدة
    if context.user_data.get('awaiting_session'):
        context.user_data['awaiting_session'] = False
        
        await message.reply_text("🔍 جاري التحقق من صحة الجلسة...")
        
        try:
            # التحقق من صحة الجلسة
            is_valid, account_info = await validate_session(text)
            
            if not is_valid:
                error_msg = account_info.get('error', 'خطأ غير معروف')
                await message.reply_text(f"❌ الجلسة غير صالحة:\n{error_msg}")
                return
            
            # إضافة الجلسة إلى قاعدة البيانات
            success = add_session_to_db(text, account_info)
            
            if success:
                phone = account_info.get('phone', 'غير معروف')
                username = account_info.get('username', 'غير معروف')
                
                await message.reply_text(
                    f"✅ *تمت إضافة الجلسة بنجاح*\n\n"
                    f"• رقم الهاتف: `{phone}`\n"
                    f"• اسم المستخدم: @{username}\n"
                    f"• المعرف: {account_info.get('user_id', 'غير معروف')}",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard()
                )
            else:
                await message.reply_text("❌ فشل إضافة الجلسة (قد تكون مضافة مسبقاً)")
        
        except Exception as e:
            logger.error(f"Error adding session: {e}")
            await message.reply_text(f"❌ حدث خطأ: {str(e)}")
    
    else:
        # رد افتراضي
        await message.reply_text(
            "👋 استخدم الأزرار للتحكم في البوت",
            reply_markup=main_menu_keyboard()
        )


# ======================
# Main Application
# ======================

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    # تهيئة قاعدة البيانات
    init_db()
    
    # إنشاء تطبيق البوت
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    # معالج الردود
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # معالج الرسائل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # بدء البوت
    logger.info("🤖 Starting Telegram Link Collector Bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
