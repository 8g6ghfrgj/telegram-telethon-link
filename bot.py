import asyncio
import logging
import os
from typing import Dict, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

from config import BOT_TOKEN, LINKS_PER_PAGE
from session_manager import add_session_to_db, get_all_sessions, delete_session, validate_session, test_all_sessions, export_sessions_to_file
from database import init_db, export_links_by_type, get_link_stats, get_links_by_type
from collector import start_collection, stop_collection, pause_collection, resume_collection, is_collecting, get_collection_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session")],
        [InlineKeyboardButton("👥 عرض الجلسات", callback_data="list_sessions")],
        [InlineKeyboardButton("▶️ بدء الجمع", callback_data="start_collect")],
        [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collect")],
        [InlineKeyboardButton("▶️ استئناف", callback_data="resume_collect")],
        [InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="stop_collect")],
        [InlineKeyboardButton("📊 عرض الروابط", callback_data="view_links")],
        [InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_links")],
        [InlineKeyboardButton("📈 إحصائيات", callback_data="show_stats")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *بوت جمع روابط التليجرام والواتساب*\n\nاختر من القائمة:",
        reply_markup=main_menu_keyboard(),
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
        await show_sessions_list(query)
    
    elif data == "start_collect":
        success = await start_collection()
        if success:
            await query.message.edit_text("🚀 بدأ جمع الروابط...")
        else:
            await query.message.edit_text("❌ لا توجد جلسات نشطة")
    
    elif data == "pause_collect":
        await pause_collection()
        await query.message.edit_text("⏸️ توقف الجمع مؤقتاً")
    
    elif data == "resume_collect":
        await resume_collection()
        await query.message.edit_text("▶️ استئناف الجمع")
    
    elif data == "stop_collect":
        await stop_collection()
        await query.message.edit_text("⏹️ توقف الجمع")
    
    elif data == "view_links":
        await show_links_menu(query)
    
    elif data == "export_links":
        await export_links_menu(query)
    
    elif data == "show_stats":
        await show_stats(query)
    
    elif data.startswith("delete_session_"):
        session_id = int(data.split("_")[2])
        delete_session(session_id)
        await query.message.edit_text("✅ تم حذف الجلسة")
    
    elif data.startswith("export_"):
        export_type = data.split("_")[1]
        await handle_export(query, export_type)

async def show_sessions_list(query):
    sessions = get_all_sessions()
    
    if not sessions:
        await query.message.edit_text(
            "📭 لا توجد جلسات مضافة",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
                InlineKeyboardButton("🔙 رجوع", callback_data="back_main")
            ]])
        )
        return
    
    keyboard = []
    for session in sessions:
        display_name = session.get('display_name', f"جلسة {session['id']}")
        keyboard.append([
            InlineKeyboardButton(
                f"🗑️ {display_name}",
                callback_data=f"delete_session_{session['id']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("🔙 رجوع", callback_data="back_main")
    ])
    
    await query.message.edit_text(
        f"👥 الجلسات المضافة: {len(sessions)}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_links_menu(query):
    keyboard = [
        [InlineKeyboardButton("📨 تيليجرام", callback_data="links_telegram")],
        [InlineKeyboardButton("📞 واتساب", callback_data="links_whatsapp")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ]
    
    await query.message.edit_text(
        "📊 اختر نوع الروابط:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def export_links_menu(query):
    keyboard = [
        [InlineKeyboardButton("📨 تصدير تيليجرام", callback_data="export_telegram")],
        [InlineKeyboardButton("📞 تصدير واتساب", callback_data="export_whatsapp")],
        [InlineKeyboardButton("📁 تصدير الجلسات", callback_data="export_sessions")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ]
    
    await query.message.edit_text(
        "📤 اختر نوع التصدير:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_stats(query):
    stats = get_link_stats()
    collection_stats = get_collection_status()["stats"]
    
    text = "📈 *إحصائيات*\n\n"
    
    if stats.get('by_platform'):
        text += "*الروابط المجمعة:*\n"
        for platform, count in stats['by_platform'].items():
            text += f"• {platform}: {count}\n"
    
    text += f"\n*الجمع الحالي:*\n"
    text += f"• تيليجرام: {collection_stats['telegram_collected']}\n"
    text += f"• واتساب: {collection_stats['whatsapp_collected']}\n"
    text += f"• الإجمالي: {collection_stats['total_collected']}\n"
    
    text += f"\n*الحالة:* {'🟢 يعمل' if is_collecting() else '🔴 متوقف'}"
    
    await query.message.edit_text(text, parse_mode="Markdown")

async def handle_export(query, export_type):
    await query.message.edit_text("⏳ جاري تحضير الملف...")
    
    try:
        if export_type == "telegram":
            path = export_links_by_type("telegram")
            if path:
                with open(path, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename="telegram_links.txt",
                        caption="📨 روابط تيليجرام"
                    )
                await query.message.edit_text("✅ تم تصدير روابط تيليجرام")
            else:
                await query.message.edit_text("❌ لا توجد روابط تيليجرام")
        
        elif export_type == "whatsapp":
            path = export_links_by_type("whatsapp")
            if path:
                with open(path, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename="whatsapp_links.txt",
                        caption="📞 روابط واتساب"
                    )
                await query.message.edit_text("✅ تم تصدير روابط واتساب")
            else:
                await query.message.edit_text("❌ لا توجد روابط واتساب")
        
        elif export_type == "sessions":
            path = export_sessions_to_file()
            if path:
                with open(path, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename="sessions_backup.txt",
                        caption="🔐 نسخة احتياطية للجلسات"
                    )
                await query.message.edit_text("✅ تم تصدير الجلسات")
            else:
                await query.message.edit_text("❌ لا توجد جلسات")
    
    except Exception as e:
        logger.error(f"Export error: {e}")
        await query.message.edit_text("❌ حدث خطأ في التصدير")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text.strip()
    
    if context.user_data.get('awaiting_session'):
        context.user_data['awaiting_session'] = False
        
        await message.reply_text("🔍 جاري التحقق من الجلسة...")
        
        try:
            is_valid, account_info = await validate_session(text)
            
            if not is_valid:
                await message.reply_text(f"❌ الجلسة غير صالحة")
                return
            
            success = add_session_to_db(text, account_info)
            
            if success:
                await message.reply_text(
                    f"✅ *تمت إضافة الجلسة بنجاح*\n\n"
                    f"يمكنك الآن بدء جمع الروابط.",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard()
                )
            else:
                await message.reply_text("❌ حدث خطأ في حفظ الجلسة")
        
        except Exception as e:
            logger.error(f"Error adding session: {e}")
            await message.reply_text("❌ حدث خطأ في إضافة الجلسة")
    
    else:
        await message.reply_text(
            "👋 استخدم الأزرار للتحكم في البوت",
            reply_markup=main_menu_keyboard()
        )

def main():
    init_db()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🤖 Starting bot...")
    app.run_polling()

if __name__ == "__main__":
    main()
