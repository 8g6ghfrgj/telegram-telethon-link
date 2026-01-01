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

from config import BOT_TOKEN, LINKS_PER_PAGE, init_config
from database import (
    init_db, get_link_stats, get_links_by_type, export_links_by_type,
    add_session, get_sessions, delete_session, update_session_status,
    start_collection_session, update_collection_stats, end_collection_session,
    delete_all_sessions
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
            InlineKeyboardButton("🗑️ حذف جميع الجلسات", callback_data="menu_delete_all_sessions")
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
    """أنواع روابط التليجرام - فقط المجموعات"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 المجموعات العامة", callback_data=f"telegram_public_group_{page}"),
            InlineKeyboardButton("🔒 المجموعات الخاصة", callback_data=f"telegram_private_group_{page}")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_view_links")
        ]
    ])

def whatsapp_types_keyboard(page: int = 0):
    """أنواع روابط الواتساب - فقط المجموعات"""
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
        InlineKeyboardButton("🗑️ حذف جميع الجلسات", callback_data="menu_delete_all_sessions")
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
            InlineKeyboardButton("📞 مجموعات واتساب", callback_data="export_whatsapp_groups"),
            InlineKeyboardButton("📊 تصدير الكل", callback_data="export_all")
        ],
        [
            InlineKeyboardButton("💾 نسخ احتياطي للجلسات", callback_data="export_backup")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")
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

def delete_all_confirmation_keyboard():
    """تأكيد حذف جميع الجلسات"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ نعم، احذف الكل", callback_data="confirm_delete_all_sessions"),
            InlineKeyboardButton("❌ لا، إلغاء", callback_data="menu_list_sessions")
        ]
    ])

# ======================
# Command Handlers
# ======================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /start"""
    user = update.effective_user
    
    welcome_text = f"""
    🤖 *مرحباً {user.first_name}!*
    
    *بوت جمع روابط المجموعات النشطة فقط*
    
    📋 *المميزات:*
    • جمع روابط مجموعات تيليجرام العامة والخاصة النشطة فقط
    • جمع روابط مجموعات واتساب النشطة فقط
    • فحص الروابط للتأكد من وجود أعضاء وليست قنوات
    • منع تكرار الروابط بين الجلسات
    • تصدير الروابط مصنفة حسب النوع
    
    ⚠️ *ملاحظة:* البوت يجمع فقط المجموعات التي تحتوي على أعضاء
    ❌ لا يجمع القنوات (t.me/channel)
    ❌ لا يجمع الروابط غير النشطة
    
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
    
    *تصدير الروابط:*
    يمكن تصدير الروابط حسب التصنيف:
    • مجموعات عامة
    • مجموعات خاصة
    • مجموعات واتساب
    
    *ملاحظات:*
    • البوت لا يجمع القنوات
    • يجمع فقط المجموعات النشطة التي تحتوي على أعضاء
    • لا يسمح بتكرار الروابط
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
        • مجموعات واتساب: {stats.get('whatsapp_groups', 0)}
        • الإجمالي: {stats.get('total_collected', 0)}
        
        • الروابط المكررة: {stats.get('duplicate_links', 0)}
        • الروابط غير النشطة: {stats.get('inactive_links', 0)}
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
    
    stats_text = """
    📈 *إحصائيات الروابط*
    
    ⚠️ *ملاحظة:* البوت يجمع فقط:
    • المجموعات العامة النشطة (تحتوي على أعضاء)
    • المجموعات الخاصة النشطة (+invite links)
    • مجموعات واتساب النشطة
    
    ❌ *لا يجمع:* القنوات، الروابط الفارغة، الروابط غير النشطة
    
    """
    
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
            if link_type == 'public_group':
                stats_text += f"• مجموعات عامة: {count}\n"
            elif link_type == 'private_group':
                stats_text += f"• مجموعات خاصة: {count}\n"
    
    # إضافة إحصائيات خاصة
    special_stats = stats.get('special_stats', {})
    if special_stats:
        stats_text += "\n*إحصائيات خاصة:*\n"
        stats_text += f"• الروابط المكررة المحذوفة: {special_stats.get('duplicates_removed', 0)}\n"
        stats_text += f"• الروابط غير النشطة: {special_stats.get('inactive_skipped', 0)}\n"
        stats_text += f"• القنوات المتجاهلة: {special_stats.get('channels_skipped', 0)}\n"
    
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
        
        # إضافة جلسة
        elif data == "menu_add_session":
            context.user_data['awaiting_session'] = True
            await query.message.edit_text(
                "📥 *إضافة جلسة جديدة*\n\n"
                "أرسل لي Session String الآن:\n\n"
                "⚠️ *ملاحظة:* تأكد من أن الجلسة نشطة ومسجلة في تليجرام",
                parse_mode="Markdown"
            )
        
        # عرض الجلسات
        elif data == "menu_list_sessions":
            await show_sessions_list(query)
        
        # حذف جميع الجلسات
        elif data == "menu_delete_all_sessions":
            await show_delete_all_confirmation(query)
        
        elif data == "confirm_delete_all_sessions":
            await delete_all_sessions_handler(query)
        
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
            if len(parts) >= 3 and parts[2].isdigit():
                # في حالة صفحة
                link_type = f"{parts[1]}_{parts[2]}"
                page = int(parts[3]) if len(parts) > 3 else 0
                await show_telegram_links(query, link_type, page)
            else:
                link_type = parts[1]
                page = int(parts[2]) if len(parts) > 2 else 0
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
            export_type = data.split('_')[1]
            if len(data.split('_')) > 2:
                export_type += f"_{data.split('_')[2]}"
            await export_handler(query, export_type)
        
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
        await query.message.edit_text(
            f"❌ حدث خطأ في المعالجة\n\n"
            f"تفاصيل: {str(e)[:200]}",
            parse_mode="Markdown"
        )

# ======================
# Menu Handlers
# ======================

async def show_main_menu(query):
    """عرض القائمة الرئيسية"""
    await query.message.edit_text(
        "📱 *القائمة الرئيسية*\n\n"
        "⚡ *البوت يجمع فقط:*\n"
        "• مجموعات تيليجرام العامة النشطة\n"
        "• مجموعات تيليجرام الخاصة النشطة\n"
        "• مجموعات واتساب النشطة\n\n"
        "❌ *لا يجمع:* القنوات، الروابط الفارغة\n\n"
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
    """عرض أنواع روابط التليجرام - فقط المجموعات"""
    await query.message.edit_text(
        "📨 *روابط تيليجرام*\n\n"
        "⚠️ *يتم جمع فقط:*\n"
        "• المجموعات العامة النشطة\n"
        "• المجموعات الخاصة النشطة\n\n"
        "❌ *لا يتم جمع:* القنوات، البوتات، رسائل\n\n"
        "اختر نوع المجموعات:",
        reply_markup=telegram_types_keyboard(),
        parse_mode="Markdown"
    )

async def show_whatsapp_types(query):
    """عرض أنواع روابط الواتساب"""
    await query.message.edit_text(
        "📞 *روابط واتساب*\n\n"
        "⚠️ *يتم جمع فقط:*\n"
        "• مجموعات واتساب النشطة\n\n"
        "اختر نوع الروابط:",
        reply_markup=whatsapp_types_keyboard(),
        parse_mode="Markdown"
    )

async def show_export_menu(query):
    """عرض قائمة التصدير"""
    await query.message.edit_text(
        "📤 *تصدير البيانات*\n\n"
        "⚠️ *يتم تصدير فقط:*\n"
        "• مجموعات تيليجرام العامة النشطة\n"
        "• مجموعات تيليجرام الخاصة النشطة\n"
        "• مجموعات واتساب النشطة\n\n"
        "اختر نوع التصدير:",
        reply_markup=export_options_keyboard(),
        parse_mode="Markdown"
    )

async def show_stats(query):
    """عرض الإحصائيات"""
    stats = get_link_stats()
    
    if not stats:
        await query.message.edit_text("📭 لا توجد إحصائيات حالياً")
        return
    
    stats_text = """
    📈 *إحصائيات الروابط*
    
    ⚠️ *ملاحظة:* البوت يجمع فقط:
    • المجموعات العامة النشطة (تحتوي على أعضاء)
    • المجموعات الخاصة النشطة (+invite links)
    • مجموعات واتساب النشطة
    
    ❌ *لا يجمع:* القنوات، الروابط الفارغة، الروابط غير النشطة
    
    """
    
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
            if link_type == 'public_group':
                stats_text += f"• مجموعات عامة: {count}\n"
            elif link_type == 'private_group':
                stats_text += f"• مجموعات خاصة: {count}\n"
    
    # إضافة إحصائيات خاصة
    special_stats = stats.get('special_stats', {})
    if special_stats:
        stats_text += "\n*إحصائيات خاصة:*\n"
        stats_text += f"• الروابط المكررة المحذوفة: {special_stats.get('duplicates_removed', 0)}\n"
        stats_text += f"• الروابط غير النشطة: {special_stats.get('inactive_skipped', 0)}\n"
        stats_text += f"• القنوات المتجاهلة: {special_stats.get('channels_skipped', 0)}\n"
    
    await query.message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")]
        ]),
        parse_mode="Markdown"
    )

async def show_delete_all_confirmation(query):
    """عرض تأكيد حذف جميع الجلسات"""
    sessions = get_sessions()
    
    if not sessions:
        await query.message.edit_text(
            "📭 لا توجد جلسات لحذفها",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_list_sessions")]
            ])
        )
        return
    
    active_sessions = len([s for s in sessions if s.get('is_active')])
    
    await query.message.edit_text(
        f"⚠️ *تحذير: حذف جميع الجلسات*\n\n"
        f"• عدد الجلسات: {len(sessions)}\n"
        f"• الجلسات النشطة: {active_sessions}\n\n"
        f"❌ *هذا الإجراء لا يمكن التراجع عنه*\n"
        f"سيتم حذف جميع الجلسات نهائياً.\n\n"
        f"هل أنت متأكد؟",
        reply_markup=delete_all_confirmation_keyboard(),
        parse_mode="Markdown"
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
        f"• النشطة: {active_count}\n"
        f"• المعطلة: {len(sessions) - active_count}\n\n"
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

async def delete_all_sessions_handler(query):
    """حذف جميع الجلسات"""
    sessions = get_sessions()
    
    if not sessions:
        await query.message.edit_text(
            "📭 لا توجد جلسات لحذفها",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_list_sessions")]
            ])
        )
        return
    
    # حذف جميع الجلسات
    success = delete_all_sessions()
    
    if success:
        await query.message.edit_text(
            f"✅ تم حذف جميع الجلسات بنجاح\n"
            f"• عدد الجلسات المحذوفة: {len(sessions)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="menu_main")]
            ])
        )
    else:
        await query.message.edit_text(
            "❌ فشل حذف جميع الجلسات",
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
    
    test_results = test_all_sessions()
    
    result_text = f"""
    📊 *نتائج اختبار الجلسات*
    
    • الإجمالي: {test_results['total']}
    • الصالحة: ✅ {test_results['passed']}
    • غير الصالحة: ❌ {test_results['failed']}
    
    • الجلسات النشطة: {test_results['active']}
    • الجلسات المعطلة: {test_results['inactive']}
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
            "⚡ *يتم جمع فقط:*\n"
            "• مجموعات تيليجرام العامة النشطة\n"
            "• مجموعات تيليجرام الخاصة النشطة\n"
            "• مجموعات واتساب النشطة\n\n"
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
        # الحصول على إحصائيات الجمع الأخيرة
        status = get_collection_status()
        stats = status.get('stats', {})
        
        stop_text = """
        ⏹️ *تم إيقاف الجمع بنجاح*
        
        📊 *إحصائيات الجمع الأخير:*
        • مجموعات عامة: {public_groups}
        • مجموعات خاصة: {private_groups}
        • مجموعات واتساب: {whatsapp_groups}
        • الإجمالي: {total_collected}
        
        • الروابط المكررة: {duplicate_links}
        • الروابط غير النشطة: {inactive_links}
        • القنوات المتجاهلة: {channels_skipped}
        """.format(
            public_groups=stats.get('public_groups', 0),
            private_groups=stats.get('private_groups', 0),
            whatsapp_groups=stats.get('whatsapp_groups', 0),
            total_collected=stats.get('total_collected', 0),
            duplicate_links=stats.get('duplicate_links', 0),
            inactive_links=stats.get('inactive_links', 0),
            channels_skipped=stats.get('channels_skipped', 0)
        )
        
        await query.message.edit_text(stop_text, parse_mode="Markdown")
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
    message_text += f"📄 الصفحة: {page + 1}\n\n"
    
    for i, link in enumerate(links, start=page * LINKS_PER_PAGE + 1):
        url = link.get('url', '')
        # تقصير الرابط الطويل لعرض أفضل
        if len(url) > 40:
            display_url = url[:37] + "..."
        else:
            display_url = url
        
        # إضافة رمز حسب نوع الرابط
        if "t.me/+" in url:
            symbol = "🔒"
        else:
            symbol = "👥"
        
        message_text += f"{i}. {symbol} `{display_url}`\n"
    
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
    message_text += f"📄 الصفحة: {page + 1}\n\n"
    
    for i, link in enumerate(links, start=page * LINKS_PER_PAGE + 1):
        url = link.get('url', '')
        # تقصير الرابط الطويل لعرض أفضل
        if len(url) > 40:
            display_url = url[:37] + "..."
        else:
            display_url = url
        
        message_text += f"{i}. 📞 `{display_url}`\n"
    
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
            caption = "👥 مجموعات تيليجرام العامة النشطة"
        
        elif export_type == "private_groups":
            path = export_links_by_type("telegram", "private_group")
            filename = "telegram_private_groups.txt"
            caption = "🔒 مجموعات تيليجرام الخاصة النشطة"
        
        elif export_type == "whatsapp_groups":
            path = export_links_by_type("whatsapp", "group")
            filename = "whatsapp_groups.txt"
            caption = "📞 مجموعات واتساب النشطة"
        
        elif export_type == "all":
            # تصدير جميع الروابط في ملفات منفصلة
            telegram_public = export_links_by_type("telegram", "public_group")
            telegram_private = export_links_by_type("telegram", "private_group")
            whatsapp_groups = export_links_by_type("whatsapp", "group")
            
            # إرسال جميع الملفات
            files_sent = 0
            
            if telegram_public and os.path.exists(telegram_public):
                with open(telegram_public, 'rb') as f:
                    await query.message.reply_document(
                        f,
                        filename="telegram_public_groups.txt",
                        caption="👥 مجموعات تيليجرام العامة النشطة"
                    )
                    files_sent += 1
            
            if telegram_private and os.path.exists(telegram_private):
                with open(telegram_private, 'rb') as f:
                    await query.message.reply_document(
                        f,
                        filename="telegram_private_groups.txt",
                        caption="🔒 مجموعات تيليجرام الخاصة النشطة"
                    )
                    files_sent += 1
            
            if whatsapp_groups and os.path.exists(whatsapp_groups):
                with open(whatsapp_groups, 'rb') as f:
                    await query.message.reply_document(
                        f,
                        filename="whatsapp_groups.txt",
                        caption="📞 مجموعات واتساب النشطة"
                    )
                    files_sent += 1
            
            if files_sent > 0:
                await query.message.edit_text(f"✅ تم تصدير {files_sent} ملف")
            else:
                await query.message.edit_text("❌ لا توجد بيانات للتصدير")
            return
        
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
        else:
            await query.message.edit_text("❌ لا توجد بيانات للتصدير")
    
    except Exception as e:
        logger.error(f"Export error: {e}")
        await query.message.edit_text(f"❌ حدث خطأ أثناء التصدير\n\n{str(e)[:100]}")

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
            # استدعاء validate_session بشكل صحيح
            is_valid, account_info = await validate_session(text)
            
            if not is_valid:
                await message.reply_text(
                    "❌ الجلسة غير صالحة\n\n"
                    "تأكد من:\n"
                    "1. أن الجلسة صحيحة\n"
                    "2. أن الحساب نشط\n"
                    "3. أنك قمت بتسجيل الدخول مسبقاً",
                    reply_markup=main_menu_keyboard()
                )
                return
            
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
                    f"• المستخدم: @{username or 'لا يوجد'}\n"
                    f"• الهاتف: {phone or 'غير معروف'}\n\n"
                    f"⚡ *الجلسة نشطة وجاهزة للاستخدام*",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard()
                )
            else:
                await message.reply_text(
                    "⚠️ *تمت إضافة الجلسة (قد تكون مضافة مسبقاً)*\n\n"
                    "يمكنك تفعيلها من قائمة الجلسات",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard()
                )
                
        except Exception as e:
            logger.error(f"Error adding session: {e}")
            await message.reply_text(
                f"❌ *خطأ في إضافة الجلسة*\n\n"
                f"التفاصيل: {str(e)[:150]}\n\n"
                f"تأكد من صحة Session String",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
    
    else:
        await message.reply_text(
            "👋 استخدم الأزرار للتحكم في البوت",
            reply_markup=main_menu_keyboard()
        )

# ======================
# Application Initialization
# ======================

def initialize_app():
    """تهيئة التطبيق تلقائياً"""
    try:
        # تهيئة الإعدادات
        print("🔧 جاري تهيئة الإعدادات...")
        if not init_config():
            print("❌ فشل تهيئة الإعدادات")
            return False
        
        # تهيئة قاعدة البيانات
        print("🗄️  جاري تهيئة قاعدة البيانات...")
        init_db()
        
        # إنشاء المجلدات المطلوبة
        from config import DATA_DIR, EXPORT_DIR, SESSIONS_DIR
        import os
        
        directories = [DATA_DIR, EXPORT_DIR, SESSIONS_DIR]
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            print(f"📁 تم إنشاء/التحقق من: {directory}")
        
        print("✅ تم تهيئة التطبيق بنجاح")
        return True
        
    except Exception as e:
        print(f"❌ فشل تهيئة التطبيق: {e}")
        import traceback
        traceback.print_exc()
        return False

# ======================
# Main Application
# ======================

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    # تهيئة التطبيق أولاً
    if not initialize_app():
        print("❌ فشل تهيئة التطبيق، يتم إيقاف التشغيل")
        return
    
    # إنشاء تطبيق البوت
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # إضافة handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # بدء البوت
    logger.info("🤖 Starting Telegram Link Collector Bot...")
    logger.info("⚡ Bot will collect ONLY active groups (not channels)")
    
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        raise

if __name__ == "__main__":
    main()
