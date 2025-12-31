import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import os

from config import BOT_TOKEN
from database import init_db, get_sessions, get_links, get_link_stats, delete_session, export_links, get_links_count
from session_manager import validate_and_add_session
from collector import collector

# التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ======================
# الأزرار والقوائم
# ======================

def main_menu():
    """القائمة الرئيسية"""
    keyboard = [
        [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session")],
        [InlineKeyboardButton("👥 عرض الجلسات", callback_data="list_sessions")],
        [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collect")],
        [InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="stop_collect")],
        [InlineKeyboardButton("🔗 عرض الروابط", callback_data="view_links")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="show_stats")],
        [InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def export_menu():
    """قائمة التصدير"""
    keyboard = [
        [InlineKeyboardButton("📨 تيليجرام كامل", callback_data="export_telegram")],
        [InlineKeyboardButton("📞 واتساب كامل", callback_data="export_whatsapp")],
        [
            InlineKeyboardButton("📢 قنوات تيليجرام", callback_data="export_telegram_channel"),
            InlineKeyboardButton("👥 مجموعات تيليجرام", callback_data="export_telegram_group")
        ],
        [
            InlineKeyboardButton("🤖 بوتات تيليجرام", callback_data="export_telegram_bot"),
            InlineKeyboardButton("📩 رسائل تيليجرام", callback_data="export_telegram_message")
        ],
        [InlineKeyboardButton("👥 مجموعات واتساب", callback_data="export_whatsapp_group")],
        [InlineKeyboardButton("📦 تصدير الكل", callback_data="export_all")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def links_menu():
    """قائمة عرض الروابط"""
    stats = get_link_stats()
    telegram_count = stats.get('total_links', 0)
    whatsapp_count = stats.get('by_platform', {}).get('whatsapp', 0)
    
    keyboard = [
        [InlineKeyboardButton(f"📨 تيليجرام ({telegram_count})", callback_data="view_telegram")],
        [InlineKeyboardButton(f"📞 واتساب ({whatsapp_count})", callback_data="view_whatsapp")],
        [InlineKeyboardButton("📢 القنوات", callback_data="view_telegram_channel")],
        [InlineKeyboardButton("👥 المجموعات", callback_data="view_telegram_group")],
        [InlineKeyboardButton("🤖 البوتات", callback_data="view_telegram_bot")],
        [InlineKeyboardButton("📩 الرسائل", callback_data="view_telegram_message")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================
# معالجات الأوامر
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /start"""
    await update.message.reply_text(
        "🤖 *مرحباً بك في بوت جمع الروابط الذكي*\n\n"
        "🔍 *المميزات:*\n"
        "• جمع روابط تيليجرام وواتساب فقط\n"
        "• تصنيف تلقائي (قنوات، مجموعات، بوتات...)\n"
        "• جمع من جميع الحسابات المضافة\n"
        "• تصدير مصنف للروابط\n\n"
        "📊 *الإحصائيات الحالية:*\n"
        f"• الجلسات النشطة: {len(get_sessions())}\n"
        f"• الروابط المجمعة: {get_links_count()}\n\n"
        "اختر من القائمة:",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ضغطات الأزرار"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # إضافة جلسة
    if data == "add_session":
        context.user_data['awaiting_session'] = True
        await query.message.edit_text(
            "📥 *إضافة جلسة جديدة*\n\n"
            "أرسل لي Session String الآن.\n\n"
            "💡 *طريقة الحصول على Session String:*\n"
            "1. اذهب إلى @StringSessionGeneratorBot\n"
            "2. أرسل /start\n"
            "3. اختر Pyrogram أو Telethon\n"
            "4. أرسل لي النتيجة",
            parse_mode="Markdown"
        )
    
    # عرض الجلسات
    elif data == "list_sessions":
        sessions = get_sessions()
        if not sessions:
            await query.message.edit_text(
                "📭 *لا توجد جلسات مضافة*\n\n"
                "اضغط ➕ إضافة جلسة لإضافة أول جلسة",
                reply_markup=main_menu(),
                parse_mode="Markdown"
            )
        else:
            text = "👥 *الجلسات المضافة:*\n\n"
            for i, session in enumerate(sessions, 1):
                name = session.get('username', session.get('phone', f'جلسة {i}'))
                text += f"{i}. {name}\n"
                if session.get('first_name'):
                    text += f"   👤 {session['first_name']}"
                    if session.get('last_name'):
                        text += f" {session['last_name']}"
                    text += "\n"
                if session.get('phone'):
                    text += f"   📞 {session['phone']}\n"
                text += "\n"
            
            # أزرار حذف
            buttons = []
            for session in sessions:
                name = session.get('username', session.get('phone', f'ID:{session["id"]}'))
                buttons.append([
                    InlineKeyboardButton(
                        f"🗑️ حذف {name}",
                        callback_data=f"delete_session_{session['id']}"
                    )
                ])
            
            buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
            
            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="Markdown"
            )
    
    # حذف جلسة
    elif data.startswith("delete_session_"):
        session_id = int(data.split("_")[2])
        if delete_session(session_id):
            await query.message.edit_text(
                "✅ *تم حذف الجلسة بنجاح*",
                reply_markup=main_menu(),
                parse_mode="Markdown"
            )
        else:
            await query.message.edit_text(
                "❌ فشل حذف الجلسة",
                reply_markup=main_menu()
            )
    
    # بدء الجمع
    elif data == "start_collect":
        sessions = get_sessions()
        if not sessions:
            await query.message.edit_text(
                "❌ *لا توجد جلسات نشطة*\n\n"
                "يجب إضافة جلسة على الأقل قبل البدء",
                reply_markup=main_menu(),
                parse_mode="Markdown"
            )
            return
        
        await query.message.edit_text("⏳ جاري بدء عملية الجمع...")
        
        # بدء الجمع في الخلفية
        result = await collector.start_collection()
        
        if result.get('success'):
            stats = result.get('stats', {})
            telegram_stats = stats.get('telegram', {})
            whatsapp_stats = stats.get('whatsapp', {})
            
            await query.message.edit_text(
                f"✅ *اكتمل جمع الروابط*\n\n"
                f"📊 *نتائج الجمع:*\n"
                f"• الجلسات المعالجة: {stats.get('sessions_processed', 0)}\n"
                f"• إجمالي الروابط المجمعة: {stats.get('total_collected', 0)}\n\n"
                f"📨 *تيليجرام:*\n"
                f"  ├ القنوات: {telegram_stats.get('channels', 0)}\n"
                f"  ├ المجموعات: {telegram_stats.get('groups', 0)}\n"
                f"  ├ البوتات: {telegram_stats.get('bots', 0)}\n"
                f"  └ الرسائل: {telegram_stats.get('messages', 0)}\n\n"
                f"📞 *واتساب:*\n"
                f"  ├ المجموعات: {whatsapp_stats.get('groups', 0)}\n"
                f"  └ أرقام: {whatsapp_stats.get('phones', 0)}\n\n"
                f"يمكنك الآن عرض الروابط من القائمة",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        else:
            await query.message.edit_text(
                f"❌ *فشل عملية الجمع*\n\n"
                f"{result.get('message', 'حدث خطأ غير معروف')}",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
    
    # إيقاف الجمع
    elif data == "stop_collect":
        if collector.stop_collection():
            await query.message.edit_text(
                "⏹️ *تم إيقاف عملية الجمع*",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        else:
            await query.message.edit_text(
                "⚠️ *الجمع غير نشط بالفعل*",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
    
    # عرض الروابط
    elif data == "view_links":
        await query.message.edit_text(
            "🔍 *اختر نوع الروابط للعرض:*",
            parse_mode="Markdown",
            reply_markup=links_menu()
        )
    
    # عرض روابط محددة
    elif data.startswith("view_"):
        parts = data.split("_")
        if len(parts) >= 2:
            platform = parts[1] if parts[1] in ['telegram', 'whatsapp'] else None
            link_type = parts[2] if len(parts) >= 3 else None
            
            # الحصول على الروابط
            links = get_links(platform=platform, link_type=link_type, limit=20)
            
            if not links:
                await query.message.edit_text(
                    "📭 *لا توجد روابط من هذا النوع*",
                    parse_mode="Markdown",
                    reply_markup=links_menu()
                )
                return
            
            # بناء النص
            if platform and link_type:
                title = f"{platform} - {link_type}"
            elif platform:
                title = platform
            else:
                title = "الجميع"
            
            text = f"🔗 *آخر روابط {title}:*\n\n"
            
            for i, link in enumerate(links, 1):
                text += f"{i}. `{link['url']}`\n"
                if link.get('chat_title'):
                    text += f"   📁 {link['chat_title']}\n"
                text += "\n"
            
            # إحصائيات
            total_count = get_links_count(platform, link_type)
            text += f"📊 *الإجمالي: {total_count} رابط*\n\n"
            
            await query.message.edit_text(
                text,
                parse_mode="Markdown",
                reply_markup=links_menu()
            )
    
    # الإحصائيات
    elif data == "show_stats":
        stats = get_link_stats()
        
        text = "📊 *إحصائيات شاملة:*\n\n"
        text += f"• إجمالي الروابط: {stats.get('total_links', 0)}\n"
        text += f"• آخر تحديث: {stats.get('last_update', 'غير معروف')}\n\n"
        
        # حسب المنصة
        by_platform = stats.get('by_platform', {})
        if by_platform:
            text += "*حسب المنصة:*\n"
            for platform, count in by_platform.items():
                text += f"  • {platform}: {count}\n"
        
        # أنواع التليجرام
        telegram_types = stats.get('telegram_types', {})
        if telegram_types:
            text += "\n*أنواع روابط تيليجرام:*\n"
            for link_type, count in telegram_types.items():
                text += f"  • {link_type}: {count}\n"
        
        # أنواع الواتساب
        whatsapp_types = stats.get('whatsapp_types', {})
        if whatsapp_types:
            text += "\n*أنواع روابط واتساب:*\n"
            for link_type, count in whatsapp_types.items():
                text += f"  • {link_type}: {count}\n"
        
        await query.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    
    # قائمة التصدير
    elif data == "export_menu":
        await query.message.edit_text(
            "📤 *اختر نوع التصدير:*",
            parse_mode="Markdown",
            reply_markup=export_menu()
        )
    
    # التصدير
    elif data.startswith("export_"):
        parts = data.split("_")
        if len(parts) >= 2:
            platform = parts[1] if parts[1] in ['telegram', 'whatsapp', 'all'] else None
            link_type = parts[2] if len(parts) >= 3 else None
            
            await query.message.edit_text("⏳ جاري تحضير الملف...")
            
            filepath = export_links(
                platform=None if platform == 'all' else platform,
                link_type=link_type
            )
            
            if filepath:
                filename = os.path.basename(filepath)
                with open(filepath, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename=filename,
                        caption=f"✅ *تم تصدير الروابط*\n📁 {filename}",
                        parse_mode="Markdown"
                    )
                
                await query.message.edit_text(
                    "✅ *تم إرسال الملف بنجاح*",
                    parse_mode="Markdown",
                    reply_markup=main_menu()
                )
            else:
                await query.message.edit_text(
                    "❌ *لا توجد روابط للتصدير*",
                    parse_mode="Markdown",
                    reply_markup=main_menu()
                )
    
    # العودة للقائمة الرئيسية
    elif data == "back_main":
        await query.message.edit_text(
            "🤖 *القائمة الرئيسية*",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    
    else:
        await query.message.edit_text(
            "❌ أمر غير معروف",
            reply_markup=main_menu()
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    if context.user_data.get('awaiting_session'):
        context.user_data['awaiting_session'] = False
        
        session_string = update.message.text.strip()
        await update.message.reply_text("🔍 جاري التحقق من الجلسة...")
        
        success, info = await validate_and_add_session(session_string)
        
        if success:
            await update.message.reply_text(
                f"✅ *تمت إضافة الجلسة بنجاح*\n\n"
                f"👤 *معلومات الحساب:*\n"
                f"• الاسم: {info.get('first_name', '')} {info.get('last_name', '')}\n"
                f"• المستخدم: @{info.get('username', 'غير معروف')}\n"
                f"• الرقم: `{info.get('phone', 'غير معروف')}`\n\n"
                f"يمكنك الآن بدء جمع الروابط",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        else:
            error_msg = info.get('error', 'خطأ غير معروف')
            await update.message.reply_text(
                f"❌ *فشل إضافة الجلسة*\n\n"
                f"السبب: {error_msg}\n\n"
                f"تأكد من:\n"
                f"1. صحة Session String\n"
                f"2. أن الحساب مسجل الدخول\n"
                f"3. عدم استخدام جلسة منتهية",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
    else:
        await update.message.reply_text(
            "👋 *استخدم الأزرار للتحكم في البوت*",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

# ======================
# التشغيل الرئيسي
# ======================

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    # تهيئة قاعدة البيانات
    init_db()
    
    # إنشاء تطبيق البوت
    app = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # بدء البوت
    logger.info("🤖 بدأ تشغيل بوت جمع الروابط...")
    app.run_polling(
        drop_pending_updates=True,  # حل مشكلة Conflict
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == "__main__":
    main()
