import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Dict, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN, LINKS_PER_PAGE
from session_manager import (
    add_session_to_db,
    get_all_sessions,
    delete_session,
    validate_session,
    get_active_sessions
)
from database import (
    init_db,
    export_links_by_type,
    get_link_stats,
    get_links_by_type,
    save_link
)
from link_collector import collect_links_from_sessions  # سننشئ هذا الملف

# ======================
# Logging
# ======================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ======================
# Global State
# ======================

collection_status = {
    "running": False,
    "progress": 0,
    "total": 0,
    "start_time": None,
    "current_session": None
}

# ======================
# Keyboards
# ======================

def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("➕ إضافة جلسة", callback_data="menu_add_session"),
            InlineKeyboardButton("👥 عرض الجلسات", callback_data="menu_list_sessions")
        ],
        [
            InlineKeyboardButton("🚀 بدء الجمع", callback_data="menu_start_collection"),
            InlineKeyboardButton("⏹ إيقاف الجمع", callback_data="menu_stop_collection")
        ],
        [
            InlineKeyboardButton("📊 عرض الروابط", callback_data="menu_view_links"),
            InlineKeyboardButton("📤 تصدير", callback_data="menu_export")
        ],
        [
            InlineKeyboardButton("📈 إحصائيات", callback_data="menu_stats"),
            InlineKeyboardButton("🔄 تحديث", callback_data="menu_refresh")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def platforms_keyboard():
    keyboard = [
        [InlineKeyboardButton("📨 تيليجرام", callback_data="view_telegram")],
        [InlineKeyboardButton("📞 واتساب", callback_data="view_whatsapp")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def telegram_categories_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 القنوات", callback_data="cat_telegram_channel")],
        [InlineKeyboardButton("👥 المجموعات", callback_data="cat_telegram_group")],
        [InlineKeyboardButton("🤖 البوتات", callback_data="cat_telegram_bot")],
        [InlineKeyboardButton("📩 الرسائل", callback_data="cat_telegram_message")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_platforms")]
    ]
    return InlineKeyboardMarkup(keyboard)


# ======================
# Command Handlers
# ======================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 مرحباً {user.first_name}!\n\n"
        "🤖 *بوت جمع روابط التليجرام والواتساب*\n\n"
        "✅ المميزات:\n"
        "• جمع روابط من جميع الحسابات المضافة\n"
        "• جمع التاريخ الكامل منذ 2000\n"
        "• تصنيف الروابط تلقائياً\n"
        "• تصدير النتائج\n\n"
        "اختر من القائمة:",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
    🆘 *مساعدة*
    
    *كيفية العمل:*
    1. أضف جلسات الحسابات باستخدام Session String
    2. ابدأ جمع الروابط
    3. شاهد الروابط المجمعة
    4. قم بتصدير النتائج
    
    *جمع الروابط:*
    - يجمع البوت جميع الروابط من:
      • جميع المجموعات والقنوات
      • جميع المحادثات الخاصة
      • التاريخ الكامل منذ 2000
    
    *لمزيد من المساعدة:* @your_support
    """
    await update.message.reply_text(help_text, parse_mode="Markdown")


# ======================
# Collection Handlers
# ======================

async def start_collection_handler(query):
    """بدء عملية الجمع"""
    global collection_status
    
    if collection_status["running"]:
        await query.message.edit_text("⏳ الجمع يعمل بالفعل!")
        return
    
    # التحقق من وجود جلسات
    sessions = get_active_sessions()
    if not sessions:
        await query.message.edit_text(
            "❌ لا توجد جلسات نشطة!\n\n"
            "أضف جلسة أولاً باستخدام ➕ إضافة جلسة",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # بدء الجمع
    collection_status["running"] = True
    collection_status["start_time"] = datetime.now()
    collection_status["progress"] = 0
    collection_status["total"] = len(sessions)
    
    await query.message.edit_text(
        f"🚀 *بدأ جمع الروابط*\n\n"
        f"• عدد الجلسات: {len(sessions)}\n"
        f"• الوقت: {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"⏳ جاري جمع الروابط من جميع الحسابات...\n"
        f"سيتم إعلامك بانتهاء العملية.",
        parse_mode="Markdown"
    )
    
    # بدء الجمع في الخلفية
    asyncio.create_task(run_collection(sessions, query))


async def run_collection(sessions, query):
    """تشغيل عملية الجمع"""
    try:
        total_links = 0
        
        for i, session in enumerate(sessions):
            if not collection_status["running"]:
                break
            
            collection_status["current_session"] = session['display_name']
            collection_status["progress"] = i + 1
            
            # تحديث حالة التقدم
            if i % 2 == 0:  # تحديث كل جلستين
                elapsed = datetime.now() - collection_status["start_time"]
                await query.message.reply_text(
                    f"📊 *جاري الجمع...*\n\n"
                    f"• التقدم: {i+1}/{len(sessions)}\n"
                    f"• الجلسة الحالية: {session['display_name']}\n"
                    f"• الوقت المنقضي: {elapsed.seconds // 60} دقيقة\n"
                    f"• الروابط المجمعة: {total_links}",
                    parse_mode="Markdown"
                )
            
            # جمع الروابط من هذه الجلسة
            links_collected = await collect_from_session(session)
            total_links += links_collected
            
            # تأخير بين الجلسات
            await asyncio.sleep(1)
        
        # انتهاء الجمع
        collection_status["running"] = False
        elapsed = datetime.now() - collection_status["start_time"]
        
        await query.message.reply_text(
            f"✅ *اكتمل جمع الروابط!*\n\n"
            f"• عدد الجلسات: {len(sessions)}\n"
            f"• الروابط المجمعة: {total_links}\n"
            f"• الوقت المستغرق: {elapsed.seconds // 60} دقيقة\n\n"
            f"يمكنك الآن عرض الروابط من القائمة.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Collection error: {e}")
        collection_status["running"] = False
        await query.message.reply_text(
            f"❌ حدث خطأ أثناء الجمع:\n{str(e)[:200]}",
            reply_markup=main_menu_keyboard()
        )


async def collect_from_session(session_data: Dict) -> int:
    """جمع الروابط من جلسة واحدة"""
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from config import API_ID, API_HASH
    from link_utils import extract_links_from_message, clean_link
    
    session_string = session_data.get('session_string')
    if not session_string:
        return 0
    
    links_collected = 0
    
    try:
        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH
        )
        
        await client.connect()
        
        if not await client.is_user_authorized():
            logger.warning(f"Session {session_data['id']} not authorized")
            return 0
        
        # جمع من جميع الدردشات
        async for dialog in client.iter_dialogs(limit=None):  # جميع الدردشات
            if not collection_status["running"]:
                break
            
            try:
                # جمع الرسائل من هذه الدردشة
                async for message in client.iter_messages(
                    dialog.entity, 
                    limit=None,  # جميع الرسائل
                    reverse=True  # من الأقدم للأحدث
                ):
                    if not collection_status["running"]:
                        break
                    
                    # استخراج الروابط من الرسالة
                    links = extract_links_from_message(message)
                    
                    for link in links:
                        cleaned = clean_link(link)
                        if cleaned:
                            # تحديد المنصة
                            platform = "telegram" if "t.me" in cleaned else "whatsapp"
                            
                            # تحديد النوع
                            link_type = "unknown"
                            if "t.me" in cleaned:
                                if "joinchat" in cleaned:
                                    link_type = "private_group"
                                elif cleaned.startswith("https://t.me/+"):
                                    link_type = "public_group"
                                elif "/c/" in cleaned:
                                    link_type = "channel"
                                elif "/" in cleaned and cleaned.split("/")[-1].isdigit():
                                    link_type = "message"
                                else:
                                    link_type = "channel"
                            
                            # حفظ الرابط
                            save_link(
                                url=cleaned,
                                platform=platform,
                                link_type=link_type,
                                source_account=session_data['display_name'],
                                chat_id=str(dialog.id),
                                message_date=message.date,
                                is_verified=False
                            )
                            
                            links_collected += 1
                    
                    # تأخير بسيط لمنع Flood
                    await asyncio.sleep(0.01)
                    
            except Exception as e:
                logger.error(f"Error processing dialog {dialog.name}: {e}")
                continue
        
        await client.disconnect()
        
    except Exception as e:
        logger.error(f"Error collecting from session {session_data['id']}: {e}")
    
    return links_collected


async def stop_collection_handler(query):
    """إيقاف الجمع"""
    global collection_status
    
    if not collection_status["running"]:
        await query.message.edit_text("⚠️ لا توجد عملية جمع نشطة")
        return
    
    collection_status["running"] = False
    await query.message.edit_text(
        "⏹️ *تم إيقاف الجمع*\n\n"
        "تم إيقاف عملية الجمع الحالية.",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )


# ======================
# Session Handlers
# ======================

async def add_session_handler(query):
    """معالجة إضافة جلسة"""
    await query.message.edit_text(
        "📥 *إضافة جلسة جديدة*\n\n"
        "أرسل لي Session String الآن:\n\n"
        "🔍 *ملاحظة:* سأتحقق من صحة الجلسة تلقائياً",
        parse_mode="Markdown"
    )
    # سنستخدم user_data في handle_message

async def show_sessions_list(query):
    """عرض قائمة الجلسات"""
    sessions = get_all_sessions()
    
    if not sessions:
        await query.message.edit_text(
            "📭 *لا توجد جلسات مضافة*\n\n"
            "استخدم ➕ إضافة جلسة لإضافة أول جلسة",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    # عد الجلسات النشطة
    active_sessions = [s for s in sessions if s.get('is_active', True)]
    
    # بناء الرسالة
    message_text = "👥 *الجلسات المضافة*\n\n"
    message_text += f"• الإجمالي: {len(sessions)}\n"
    message_text += f"• النشطة: {len(active_sessions)}\n\n"
    
    # إنشاء أزرار
    keyboard = []
    for session in sessions:
        session_id = session['id']
        display_name = session.get('display_name', f'جلسة {session_id}')
        status = "🟢" if session.get('is_active', True) else "🔴"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {display_name}",
                callback_data=f"session_{session_id}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("➕ إضافة جلسة", callback_data="menu_add_session"),
        InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    ])
    
    await query.message.edit_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ======================
# Link Viewing Handlers
# ======================

async def view_telegram_links(query):
    """عرض روابط التليجرام"""
    links = get_links_by_type("telegram", limit=LINKS_PER_PAGE)
    
    if not links:
        await query.message.edit_text(
            "📭 *لا توجد روابط تيليجرام*\n\n"
            "ابدأ الجمع أولاً لجمع الروابط",
            reply_markup=platforms_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    message_text = "📨 *روابط تيليجرام*\n\n"
    
    for i, link in enumerate(links[:LINKS_PER_PAGE], 1):
        url = link.get('url', '')
        link_type = link.get('link_type', 'unknown')
        
        type_icons = {
            'channel': '📢',
            'group': '👥',
            'bot': '🤖',
            'message': '📩'
        }
        
        icon = type_icons.get(link_type, '🔗')
        message_text += f"{i}. {icon} `{url}`\n"
    
    keyboard = [
        [InlineKeyboardButton("📢 القنوات", callback_data="cat_telegram_channel")],
        [InlineKeyboardButton("👥 المجموعات", callback_data="cat_telegram_group")],
        [InlineKeyboardButton("🤖 البوتات", callback_data="cat_telegram_bot")],
        [InlineKeyboardButton("📩 الرسائل", callback_data="cat_telegram_message")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_platforms")]
    ]
    
    await query.message.edit_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def view_whatsapp_links(query):
    """عرض روابط الواتساب"""
    links = get_links_by_type("whatsapp", limit=LINKS_PER_PAGE)
    
    if not links:
        await query.message.edit_text(
            "📭 *لا توجد روابط واتساب*\n\n"
            "ابدأ الجمع أولاً لجمع الروابط",
            reply_markup=platforms_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    message_text = "📞 *روابط واتساب*\n\n"
    
    for i, link in enumerate(links[:LINKS_PER_PAGE], 1):
        url = link.get('url', '')
        message_text += f"{i}. 👥 `{url}`\n"
    
    keyboard = [
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_platforms")]
    ]
    
    await query.message.edit_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ======================
# Main Callback Handler
# ======================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    try:
        # القائمة الرئيسية
        if data == "back_to_main":
            await query.message.edit_text(
                "📱 *القائمة الرئيسية*",
                reply_markup=main_menu_keyboard(),
                parse_mode="Markdown"
            )
        
        elif data == "back_to_platforms":
            await query.message.edit_text(
                "📊 *اختر المنصة*",
                reply_markup=platforms_keyboard(),
                parse_mode="Markdown"
            )
        
        # إضافة جلسة
        elif data == "menu_add_session":
            context.user_data['awaiting_session'] = True
            await add_session_handler(query)
        
        # عرض الجلسات
        elif data == "menu_list_sessions":
            await show_sessions_list(query)
        
        # بدء الجمع
        elif data == "menu_start_collection":
            await start_collection_handler(query)
        
        # إيقاف الجمع
        elif data == "menu_stop_collection":
            await stop_collection_handler(query)
        
        # عرض الروابط
        elif data == "menu_view_links":
            await query.message.edit_text(
                "📊 *اختر المنصة*",
                reply_markup=platforms_keyboard(),
                parse_mode="Markdown"
            )
        
        elif data == "view_telegram":
            await view_telegram_links(query)
        
        elif data == "view_whatsapp":
            await view_whatsapp_links(query)
        
        # التصدير
        elif data == "menu_export":
            await export_handler(query)
        
        # الإحصائيات
        elif data == "menu_stats":
            await show_stats_handler(query)
        
        # التحديث
        elif data == "menu_refresh":
            await query.message.edit_text(
                "🔄 *تم التحديث*",
                reply_markup=main_menu_keyboard(),
                parse_mode="Markdown"
            )
        
        else:
            await query.message.edit_text("❌ أمر غير معروف")
    
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.message.edit_text("❌ حدث خطأ في المعالجة")


async def export_handler(query):
    """معالجة التصدير"""
    # تصدير روابط التليجرام
    telegram_path = export_links_by_type("telegram")
    whatsapp_path = export_links_by_type("whatsapp")
    
    files_sent = 0
    
    if telegram_path and os.path.exists(telegram_path):
        with open(telegram_path, 'rb') as f:
            await query.message.reply_document(
                document=f,
                filename="telegram_links.txt",
                caption="📨 روابط تيليجرام"
            )
        files_sent += 1
    
    if whatsapp_path and os.path.exists(whatsapp_path):
        with open(whatsapp_path, 'rb') as f:
            await query.message.reply_document(
                document=f,
                filename="whatsapp_links.txt",
                caption="📞 روابط واتساب"
            )
        files_sent += 1
    
    if files_sent > 0:
        await query.message.edit_text(
            f"✅ تم تصدير {files_sent} ملف",
            reply_markup=main_menu_keyboard()
        )
    else:
        await query.message.edit_text(
            "❌ لا توجد روابط للتصدير",
            reply_markup=main_menu_keyboard()
        )


async def show_stats_handler(query):
    """عرض الإحصائيات"""
    stats = get_link_stats()
    
    if not stats:
        await query.message.edit_text(
            "📭 لا توجد إحصائيات",
            reply_markup=main_menu_keyboard()
        )
        return
    
    stats_text = "📈 *الإحصائيات*\n\n"
    
    # إحصائيات حسب المنصة
    by_platform = stats.get('by_platform', {})
    if by_platform:
        stats_text += "*حسب المنصة:*\n"
        for platform, count in by_platform.items():
            if platform == 'telegram':
                stats_text += f"• 📨 تيليجرام: {count}\n"
            elif platform == 'whatsapp':
                stats_text += f"• 📞 واتساب: {count}\n"
            else:
                stats_text += f"• {platform}: {count}\n"
    
    # إحصائيات التليجرام حسب النوع
    telegram_stats = stats.get('telegram_by_type', {})
    if telegram_stats:
        stats_text += "\n*روابط تيليجرام:*\n"
        type_names = {
            'channel': '📢 القنوات',
            'group': '👥 المجموعات',
            'public_group': '👥 مجموعات عامة',
            'private_group': '🔒 مجموعات خاصة',
            'bot': '🤖 البوتات',
            'message': '📩 الرسائل'
        }
        
        for link_type, count in telegram_stats.items():
            name = type_names.get(link_type, link_type)
            stats_text += f"• {name}: {count}\n"
    
    await query.message.edit_text(
        stats_text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )


# ======================
# Message Handler
# ======================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text.strip()
    
    # إضافة جلسة جديدة
    if context.user_data.get('awaiting_session'):
        context.user_data['awaiting_session'] = False
        
        await message.reply_text("🔍 جاري التحقق من الجلسة...")
        
        try:
            is_valid, account_info = await validate_session(text)
            
            if not is_valid:
                error_msg = account_info.get('error', 'خطأ غير معروف')
                await message.reply_text(f"❌ الجلسة غير صالحة: {error_msg}")
                return
            
            # إضافة الجلسة
            success = add_session_to_db(text, account_info)
            
            if success:
                phone = account_info.get('phone', 'غير معروف')
                username = account_info.get('username', 'غير معروف')
                user_id = account_info.get('user_id', 'غير معروف')
                
                await message.reply_text(
                    f"✅ *تمت إضافة الجلسة بنجاح*\n\n"
                    f"• رقم الهاتف: `{phone}`\n"
                    f"• اسم المستخدم: @{username}\n"
                    f"• المعرف: {user_id}\n\n"
                    f"يمكنك الآن البدء في جمع الروابط!",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard()
                )
            else:
                await message.reply_text(
                    "❌ حدث خطأ في حفظ الجلسة",
                    reply_markup=main_menu_keyboard()
                )
        
        except Exception as e:
            logger.error(f"Add session error: {e}")
            await message.reply_text(
                f"❌ حدث خطأ: {str(e)[:100]}",
                reply_markup=main_menu_keyboard()
            )
    
    else:
        await message.reply_text(
            "👋 استخدم القائمة للتحكم في البوت",
            reply_markup=main_menu_keyboard()
        )


# ======================
# Main Application
# ======================

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    # تهيئة قاعدة البيانات
    init_db()
    
    # إنشاء تطبيق البوت مع إعدادات لمنع Conflict
    app = ApplicationBuilder() \
        .token(BOT_TOKEN) \
        .read_timeout(30) \
        .write_timeout(30) \
        .connect_timeout(30) \
        .pool_timeout(30) \
        .get_updates_read_timeout(30) \
        .build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    
    # معالج الردود
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # معالج الرسائل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # بدء البوت
    logger.info("🤖 Starting Bot...")
    
    # استخدام polling مع إعدادات لمنع Conflict
    app.run_polling(
        poll_interval=0.5,
        timeout=30,
        drop_pending_updates=True,  # تجاهل الرسائل القديمة
        allowed_updates=['message', 'callback_query']
    )


if __name__ == "__main__":
    main()
