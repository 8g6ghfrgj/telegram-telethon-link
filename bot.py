import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from config import BOT_TOKEN
from database import init_db, get_sessions, get_links, get_stats, delete_session, export_links
from session_manager import validate_and_add_session
from collector import collector

# التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# الأزرار
def main_menu():
    keyboard = [
        [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session")],
        [InlineKeyboardButton("👥 عرض الجلسات", callback_data="list_sessions")],
        [InlineKeyboardButton("▶️ بدء الجمع", callback_data="start_collect")],
        [InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="stop_collect")],
        [InlineKeyboardButton("📊 عرض الروابط", callback_data="view_links")],
        [InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_links")]
    ]
    return InlineKeyboardMarkup(keyboard)

# الأوامر
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *بوت جمع روابط التليجرام والواتساب*\n\n"
        "اختر من القائمة:",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "add_session":
        context.user_data['awaiting_session'] = True
        await query.message.edit_text("📥 أرسل Session String الآن:")
    
    elif data == "list_sessions":
        sessions = get_sessions()
        if not sessions:
            await query.message.edit_text("📭 لا توجد جلسات مضافة")
        else:
            text = "👥 *الجلسات المضافة:*\n\n"
            for s in sessions:
                text += f"• {s.get('username', s.get('phone', 'غير معروف'))} (ID: {s['id']})\n"
            
            # أزرار حذف
            buttons = []
            for s in sessions:
                buttons.append([InlineKeyboardButton(
                    f"🗑️ حذف {s.get('username', s['id'])}",
                    callback_data=f"delete_{s['id']}"
                )])
            
            buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="back")])
            
            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="Markdown"
            )
    
    elif data.startswith("delete_"):
        session_id = int(data.split("_")[1])
        if delete_session(session_id):
            await query.message.edit_text("✅ تم حذف الجلسة")
        else:
            await query.message.edit_text("❌ فشل حذف الجلسة")
    
    elif data == "start_collect":
        await query.message.edit_text("⏳ جاري بدء جمع الروابط...")
        
        # بدء الجمع في الخلفية
        asyncio.create_task(start_collection())
        await query.message.edit_text(
            "🚀 *بدأ جمع الروابط*\n\n"
            "جاري جمع الروابط من جميع الحسابات...\n"
            "سيتم جمع:\n"
            "• جميع روابط التليجرام من التاريخ\n"
            "• روابط الواتساب\n\n"
            "قد يستغرق بعض الوقت.",
            parse_mode="Markdown"
        )
    
    elif data == "stop_collect":
        collector.stop_collection()
        await query.message.edit_text("⏹️ تم إيقاف جمع الروابط")
    
    elif data == "view_links":
        links = get_links(limit=20)
        if not links:
            await query.message.edit_text("📭 لا توجد روابط مجمعة بعد")
        else:
            text = "🔗 *آخر الروابط المجمعة:*\n\n"
            for link in links:
                text += f"• `{link['url']}`\n"
            
            stats = get_stats()
            text += f"\n📊 *الإحصائيات:*\n"
            text += f"• إجمالي الروابط: {stats['links']}\n"
            text += f"• التليجرام: {stats['by_platform'].get('telegram', 0)}\n"
            text += f"• الواتساب: {stats['by_platform'].get('whatsapp', 0)}\n"
            
            await query.message.edit_text(
                text,
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
    
    elif data == "export_links":
        await query.message.edit_text("📤 اختر نوع التصدير:")
        
        keyboard = [
            [InlineKeyboardButton("📨 تصدير تيليجرام", callback_data="export_telegram")],
            [InlineKeyboardButton("📞 تصدير واتساب", callback_data="export_whatsapp")],
            [InlineKeyboardButton("📦 تصدير الكل", callback_data="export_all")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
        ]
        
        await query.message.edit_text(
            "📤 اختر نوع التصدير:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data in ["export_telegram", "export_whatsapp", "export_all"]:
        platform = None
        if data == "export_telegram":
            platform = "telegram"
        elif data == "export_whatsapp":
            platform = "whatsapp"
        
        await query.message.edit_text("⏳ جاري تحضير الملف...")
        
        filepath = export_links(platform)
        if filepath:
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=filepath.split("/")[-1]
                )
            await query.message.edit_text("✅ تم التصدير بنجاح")
        else:
            await query.message.edit_text("❌ لا توجد روابط للتصدير")
    
    elif data == "back":
        await query.message.edit_text(
            "🤖 اختر من القائمة:",
            reply_markup=main_menu()
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل"""
    if context.user_data.get('awaiting_session'):
        context.user_data['awaiting_session'] = False
        
        session_string = update.message.text.strip()
        await update.message.reply_text("🔍 جاري التحقق من الجلسة...")
        
        success, info = await validate_and_add_session(session_string)
        
        if success:
            await update.message.reply_text(
                f"✅ *تمت إضافة الجلسة بنجاح*\n\n"
                f"رقم الهاتف: `{info.get('phone', 'غير معروف')}`\n"
                f"اسم المستخدم: @{info.get('username', 'غير معروف')}",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        else:
            await update.message.reply_text(
                f"❌ فشل إضافة الجلسة: {info.get('error', 'خطأ غير معروف')}",
                reply_markup=main_menu()
            )
    else:
        await update.message.reply_text(
            "👋 استخدم الأزرار للتحكم",
            reply_markup=main_menu()
        )

async def start_collection():
    """بدء عملية الجمع"""
    try:
        await collector.start_collection()
    except Exception as e:
        logger.error(f"Error starting collection: {e}")

def main():
    """الدالة الرئيسية"""
    # تهيئة قاعدة البيانات
    init_db()
    
    # إنشاء التطبيق
    app = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # بدء البوت
    logger.info("🤖 بدأ تشغيل البوت...")
    app.run_polling(drop_pending_updates=True)  # مهم: حل مشكلة Conflict

if __name__ == "__main__":
    main()
