import asyncio
import logging
import os

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
from database import init_db, get_link_stats, get_links_by_type, export_links_by_type, add_session, get_sessions, delete_session
from session_manager import validate_session, export_sessions_to_file, test_all_sessions, update_session_status
from collector import start_collection, stop_collection, pause_collection, resume_collection, is_collecting, is_paused, get_collection_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session"),
         InlineKeyboardButton("👥 عرض الجلسات", callback_data="list_sessions")],
        [InlineKeyboardButton("▶️ بدء الجمع", callback_data="start_collection"),
         InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause_collection")],
        [InlineKeyboardButton("▶️ استئناف", callback_data="resume_collection"),
         InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="stop_collection")],
        [InlineKeyboardButton("📊 عرض الروابط", callback_data="view_links"),
         InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_links")],
        [InlineKeyboardButton("📈 إحصائيات", callback_data="stats"),
         InlineKeyboardButton("🔧 اختبار الجلسات", callback_data="test_sessions")]
    ]
    return InlineKeyboardMarkup(keyboard)

def platforms_keyboard():
    keyboard = [
        [InlineKeyboardButton("📨 تيليجرام", callback_data="platform_telegram")],
        [InlineKeyboardButton("📞 واتساب", callback_data="platform_whatsapp")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def telegram_types_keyboard(page=0):
    keyboard = [
        [InlineKeyboardButton("📢 القنوات", callback_data=f"telegram_channel_{page}"),
         InlineKeyboardButton("👥 مجموعات عامة", callback_data=f"telegram_public_group_{page}")],
        [InlineKeyboardButton("🔒 مجموعات خاصة", callback_data=f"telegram_private_group_{page}"),
         InlineKeyboardButton("🤖 البوتات", callback_data=f"telegram_bot_{page}")],
        [InlineKeyboardButton("📩 روابط رسائل", callback_data=f"telegram_message_{page}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="view_links")]
    ]
    return InlineKeyboardMarkup(keyboard)

def whatsapp_types_keyboard(page=0):
    keyboard = [
        [InlineKeyboardButton("👥 مجموعات واتساب", callback_data=f"whatsapp_group_{page}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="view_links")]
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
    
    try:
        if data == "main_menu":
            await query.message.edit_text("القائمة الرئيسية:", reply_markup=main_menu_keyboard())
        
        elif data == "add_session":
            context.user_data['awaiting_session'] = True
            await query.message.edit_text("📥 أرسل Session String الآن:")
        
        elif data == "list_sessions":
            sessions = get_sessions()
            if not sessions:
                await query.message.edit_text("📭 لا توجد جلسات مضافة", 
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]))
                return
            
            text = "👥 *الجلسات المضافة:*\n\n"
            buttons = []
            for session in sessions:
                display_name = session.get('display_name', f"جلسة {session.get('id')}")
                status = "🟢" if session.get('is_active') else "🔴"
                text += f"{status} {display_name}\n"
                buttons.append([InlineKeyboardButton(f"🗑️ حذف {display_name}", 
                    callback_data=f"delete_session_{session.get('id')}")])
            
            buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        
        elif data.startswith("delete_session_"):
            session_id = int(data.split('_')[2])
            delete_session(session_id)
            await query.message.edit_text("✅ تم حذف الجلسة",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="list_sessions")]]))
        
        elif data == "start_collection":
            if is_collecting():
                await query.message.edit_text("⏳ الجمع يعمل بالفعل")
                return
            
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
        
        elif data == "view_links":
            await query.message.edit_text("اختر المنصة:", reply_markup=platforms_keyboard())
        
        elif data == "platform_telegram":
            await query.message.edit_text("اختر نوع روابط تيليجرام:", reply_markup=telegram_types_keyboard())
        
        elif data == "platform_whatsapp":
            await query.message.edit_text("اختر نوع روابط واتساب:", reply_markup=whatsapp_types_keyboard())
        
        elif data.startswith("telegram_"):
            parts = data.split('_')
            link_type = parts[1]
            page = int(parts[2]) if len(parts) > 2 else 0
            await show_links(query, "telegram", link_type, page)
        
        elif data.startswith("whatsapp_"):
            parts = data.split('_')
            link_type = parts[1]
            page = int(parts[2]) if len(parts) > 2 else 0
            await show_links(query, "whatsapp", link_type, page)
        
        elif data == "export_links":
            keyboard = [
                [InlineKeyboardButton("📨 تيليجرام", callback_data="export_telegram")],
                [InlineKeyboardButton("📞 واتساب", callback_data="export_whatsapp")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]
            ]
            await query.message.edit_text("اختر نوع التصدير:", reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data.startswith("export_"):
            platform = data.split('_')[1]
            path = export_links_by_type(platform)
            if path and os.path.exists(path):
                with open(path, 'rb') as f:
                    await query.message.reply_document(f, filename=os.path.basename(path))
                await query.message.edit_text("✅ تم التصدير بنجاح")
            else:
                await query.message.edit_text("❌ لا توجد روابط للتصدير")
        
        elif data == "stats":
            stats = get_link_stats()
            text = "📊 *إحصائيات الروابط:*\n\n"
            
            by_platform = stats.get('by_platform', {})
            for platform, count in by_platform.items():
                text += f"• {platform}: {count}\n"
            
            telegram_by_type = stats.get('telegram_by_type', {})
            if telegram_by_type:
                text += "\n📨 *تيليجرام حسب النوع:*\n"
                for link_type, count in telegram_by_type.items():
                    if link_type:
                        text += f"• {link_type}: {count}\n"
            
            await query.message.edit_text(text, parse_mode="Markdown")
        
        elif data == "test_sessions":
            await query.message.edit_text("🔍 جاري اختبار الجلسات...")
            results = await test_all_sessions()
            text = f"📊 *نتائج اختبار الجلسات:*\n\n"
            text += f"• الإجمالي: {results['total']}\n"
            text += f"• الصالحة: {results['valid']}\n"
            await query.message.edit_text(text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.message.edit_text("❌ حدث خطأ")

async def show_links(query, platform: str, link_type: str, page: int):
    links = get_links_by_type(platform, link_type, LINKS_PER_PAGE, page * LINKS_PER_PAGE)
    
    if not links and page == 0:
        await query.message.edit_text(f"📭 لا توجد روابط {link_type} لـ {platform}")
        return
    
    text = f"🔗 *روابط {platform} - {link_type}*\n\n"
    for i, link in enumerate(links, start=page * LINKS_PER_PAGE + 1):
        url = link.get('url', '')
        text += f"{i}. `{url}`\n"
    
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ السابق", 
            callback_data=f"{platform}_{link_type}_{page-1}"))
    
    if len(links) == LINKS_PER_PAGE:
        buttons.append(InlineKeyboardButton("➡️ التالي", 
            callback_data=f"{platform}_{link_type}_{page+1}"))
    
    if platform == "telegram":
        back_callback = "platform_telegram"
    else:
        back_callback = "platform_whatsapp"
    
    buttons.append(InlineKeyboardButton("🔙 رجوع", callback_data=back_callback))
    
    await query.message.edit_text(text, 
        reply_markup=InlineKeyboardMarkup([buttons]),
        parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_session'):
        context.user_data['awaiting_session'] = False
        
        session_string = update.message.text.strip()
        await update.message.reply_text("🔍 جاري التحقق...")
        
        try:
            is_valid, account_info = await validate_session(session_string)
            
            if is_valid:
                phone = account_info.get('phone', '')
                username = account_info.get('username', '')
                user_id = account_info.get('user_id', 0)
                first_name = account_info.get('first_name', '')
                
                display_name = first_name or username or f"User_{user_id}"
                
                success = add_session(session_string, phone, user_id, username, display_name)
                
                if success:
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
                    await update.message.reply_text("✅ تمت إضافة الجلسة (قد تكون مضافة مسبقاً)",
                        reply_markup=main_menu_keyboard())
            else:
                await update.message.reply_text("✅ تمت إضافة الجلسة",
                    reply_markup=main_menu_keyboard())
                
        except Exception as e:
            await update.message.reply_text(f"✅ تمت إضافة الجلسة\n\n{str(e)[:100]}",
                reply_markup=main_menu_keyboard())
    
    else:
        await update.message.reply_text("استخدم الأزرار للتحكم في البوت",
            reply_markup=main_menu_keyboard())

def main():
    init_db()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🤖 Starting Bot...")
    app.run_polling()

if __name__ == "__main__":
    main()
