import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from config import BOT_TOKEN
from database import init_db, get_sessions, get_links, get_stats, delete_session, export_links
from session_manager import validate_session
from link_collector import collector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ======================
# الأزرار
# ======================

def main_menu():
    keyboard = [
        [InlineKeyboardButton("➕ إضافة جلسة", callback_data="add_session")],
        [InlineKeyboardButton("👥 عرض الجلسات", callback_data="list_sessions")],
        [InlineKeyboardButton("🚀 بدء الجمع", callback_data="start_collection")],
        [InlineKeyboardButton("⏹️ إيقاف الجمع", callback_data="stop_collection")],
        [InlineKeyboardButton("🔗 عرض الروابط", callback_data="view_links")],
        [InlineKeyboardButton("📤 تصدير الروابط", callback_data="export_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def links_menu():
    keyboard = [
        [
            InlineKeyboardButton("📢 القنوات", callback_data="links_telegram_channel"),
            InlineKeyboardButton("👥 المجموعات", callback_data="links_telegram_group")
        ],
        [
            InlineKeyboardButton("🤖 البوتات", callback_data="links_telegram_bot"),
            InlineKeyboardButton("📩 رسائل", callback_data="links_telegram_message")
        ],
        [
            InlineKeyboardButton("📞 واتساب", callback_data="links_whatsapp"),
            InlineKeyboardButton("📊 الكل", callback_data="links_all")
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def export_menu():
    keyboard = [
        [
            InlineKeyboardButton("📢 تصدير القنوات", callback_data="export_telegram_channel"),
            InlineKeyboardButton("👥 تصدير المجموعات", callback_data="export_telegram_group")
        ],
        [
            InlineKeyboardButton("🤖 تصدير البوتات", callback_data="export_telegram_bot"),
            InlineKeyboardButton("📩 تصدير الرسائل", callback_data="export_telegram_message")
        ],
        [
            InlineKeyboardButton("📞 تصدير واتساب", callback_data="export_whatsapp"),
            InlineKeyboardButton("📦 تصدير الكل", callback_data="export_all")
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================
# الأوامر
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *بوت جمع روابط التليجرام والواتساب*\n\n"
        "• إضافة جلسات متعددة\n"
        "• جمع روابط من جميع المحادثات\n"
        "• تصنيف القنوات/المجموعات/البوتات\n"
        "• تصدير النتائج\n\n"
        "اختر من القائمة:",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    try:
        # القائمة الرئيسية
        if data == "back_main":
            await query.message.edit_text("القائمة الرئيسية:", reply_markup=main_menu())
        
        # إضافة جلسة
        elif data == "add_session":
            context.user_data['awaiting_session'] = True
            await query.message.edit_text(
                "📥 *إضافة جلسة جديدة*\n\n"
                "أرسل لي Session String الآن.\n\n"
                "📌 *طريقة الحصول على Session:*\n"
                "1. اذهب إلى @StringSessionGeneratorBot\n"
                "2. أرسل /start\n"
                "3. اختر Telethon\n"
                "4. أرسل الرمز الذي تأخذه إلى هنا",
                parse_mode="Markdown"
            )
        
        # عرض الجلسات
        elif data == "list_sessions":
            sessions = get_sessions()
            if not sessions:
                await query.message.edit_text(
                    "📭 *لا توجد جلسات مضافة*\n\n"
                    "اضغط ➕ إضافة جلسة أولاً",
                    parse_mode="Markdown",
                    reply_markup=main_menu()
                )
                return
            
            text = "👥 *الجلسات المضافة:*\n\n"
            for i, s in enumerate(sessions, 1):
                username = f"@{s['username']}" if s['username'] else s['phone'] or f"جلسة {s['id']}"
                text += f"{i}. {username}\n"
            
            buttons = []
            for s in sessions[:5]:  # أول 5 فقط
                name = s['username'] or s['phone'] or f"ID{s['id']}"
                buttons.append([
                    InlineKeyboardButton(
                        f"🗑️ حذف {name[:15]}",
                        callback_data=f"delete_{s['id']}"
                    )
                ])
            
            buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
            
            await query.message.edit_text(
                text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        
        # حذف جلسة
        elif data.startswith("delete_"):
            session_id = int(data.split("_")[1])
            if delete_session(session_id):
                await query.message.edit_text("✅ تم حذف الجلسة", reply_markup=main_menu())
            else:
                await query.message.edit_text("❌ فشل حذف الجلسة", reply_markup=main_menu())
        
        # بدء الجمع
        elif data == "start_collection":
            status = collector.get_status()
            if status['is_collecting']:
                await query.message.edit_text("⏳ الجمع يعمل بالفعل!", reply_markup=main_menu())
                return
            
            await query.message.edit_text("🚀 *بدأ جمع الروابط...*\n\n⏳ جاري المسح...", parse_mode="Markdown")
            
            # تشغيل الجمع في الخلفية
            asyncio.create_task(run_collection_async(query))
        
        # إيقاف الجمع
        elif data == "stop_collection":
            if collector.stop_collection():
                await query.message.edit_text("⏹️ تم إيقاف الجمع", reply_markup=main_menu())
            else:
                await query.message.edit_text("ℹ️ الجمع غير نشط أصلاً", reply_markup=main_menu())
        
        # عرض الروابط
        elif data == "view_links":
            await query.message.edit_text("🔗 اختر نوع الروابط:", reply_markup=links_menu())
        
        # أنواع الروابط
        elif data.startswith("links_"):
            parts = data.split("_")
            if len(parts) >= 3:
                platform = parts[1]
                link_type = parts[2]
                
                links = get_links(platform if platform != 'all' else None, 
                                link_type if link_type != 'all' else None, 
                                limit=20)
                
                if not links:
                    await query.message.edit_text(
                        f"📭 لا توجد روابط {platform}/{link_type}",
                        reply_markup=links_menu()
                    )
                    return
                
                text = f"🔗 *روابط {platform}/{link_type}:*\n\n"
                for i, link in enumerate(links, 1):
                    text += f"{i}. `{link['url']}`\n"
                    if link.get('chat_title'):
                        text += f"   📍 {link['chat_title']}\n"
                
                stats = get_stats()
                text += f"\n📊 *الإحصائيات:*\n"
                text += f"• إجمالي الروابط: {stats['total_links']}\n"
                text += f"• القنوات: {stats['telegram_types'].get('channel', 0)}\n"
                text += f"• المجموعات: {stats['telegram_types'].get('private_group', 0) + stats['telegram_types'].get('public_group', 0)}\n"
                text += f"• البوتات: {stats['telegram_types'].get('bot', 0)}\n"
                text += f"• واتساب: {stats['by_platform'].get('whatsapp', 0)}\n"
                
                await query.message.edit_text(
                    text,
                    parse_mode="Markdown",
                    reply_markup=links_menu()
                )
        
        # قائمة التصدير
        elif data == "export_menu":
            await query.message.edit_text("📤 اختر ما تريد تصديره:", reply_markup=export_menu())
        
        # التصدير
        elif data.startswith("export_"):
            parts = data.split("_")
            if len(parts) >= 2:
                platform = parts[1] if parts[1] != 'all' else None
                link_type = parts[2] if len(parts) >= 3 else None
                
                await query.message.edit_text("⏳ جاري تحضير الملف...")
                
                filepath = export_links(platform, link_type)
                if filepath:
                    with open(filepath, 'rb') as f:
                        await query.message.reply_document(
                            document=f,
                            filename=filepath.split("/")[-1],
                            caption=f"📤 {platform or 'كل'} الروابط"
                        )
                    await query.message.edit_text("✅ تم التصدير بنجاح", reply_markup=main_menu())
                else:
                    await query.message.edit_text("❌ لا توجد روابط للتصدير", reply_markup=main_menu())
        
        else:
            await query.message.edit_text("❌ أمر غير معروف", reply_markup=main_menu())
    
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.message.edit_text("❌ حدث خطأ", reply_markup=main_menu())

async def run_collection_async(query):
    """تشغيل الجمع في الخلفية"""
    try:
        success = await collector.start_collection()
        
        if success:
            stats = collector.get_status()['stats']
            await query.message.edit_text(
                f"✅ *اكتمل الجمع!*\n\n"
                f"📊 *الإحصائيات:*\n"
                f"• روابط تليجرام: {stats['telegram']}\n"
                f"• روابط واتساب: {stats['whatsapp']}\n"
                f"• القنوات: {stats['channels']}\n"
                f"• المجموعات: {stats['groups']}\n"
                f"• البوتات: {stats['bots']}\n\n"
                f"اضغط 🔗 عرض الروابط لرؤية النتائج",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        else:
            await query.message.edit_text(
                "❌ فشل الجمع!\n\n"
                "تأكد من:\n"
                "1. وجود جلسات مضافة\n"
                "2. صلاحية الجلسات\n"
                "3. اتصال الإنترنت",
                reply_markup=main_menu()
            )
    except Exception as e:
        logger.error(f"Collection error: {e}")
        await query.message.edit_text("❌ حدث خطأ أثناء الجمع", reply_markup=main_menu())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    if context.user_data.get('awaiting_session'):
        context.user_data['awaiting_session'] = False
        
        session_string = update.message.text.strip()
        await update.message.reply_text("🔍 جاري التحقق من الجلسة...")
        
        success, info = await validate_session(session_string)
        
        if success:
            username = f"@{info['username']}" if info['username'] else info['phone'] or "مجهول"
            await update.message.reply_text(
                f"✅ *تمت إضافة الجلسة بنجاح!*\n\n"
                f"👤 الحساب: {username}\n"
                f"📞 الرقم: {info['phone'] or 'غير متوفر'}\n"
                f"🆔 المعرف: {info['user_id']}\n\n"
                f"يمكنك الآن بدء جمع الروابط 🚀",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        else:
            await update.message.reply_text(
                f"❌ *فشل إضافة الجلسة!*\n\n"
                f"السبب: {info.get('error', 'خطأ غير معروف')}\n\n"
                f"تأكد من:\n"
                f"1. صحة Session String\n"
                f"2. أن الحساب نشط\n"
                f"3. عدم وجود كلمة مرور ثنائية",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
    else:
        await update.message.reply_text(
            "👋 استخدم الأزرار للتحكم في البوت",
            reply_markup=main_menu()
        )

# ======================
# التشغيل الرئيسي
# ======================

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
    print("=" * 50)
    print("✅ البوت يعمل بنجاح!")
    print("📌 المميزات المتوفرة:")
    print("  1. إضافة جلسات متعددة")
    print("  2. جمع روابط من المحادثات")
    print("  3. تصنيف القنوات/المجموعات/البوتات")
    print("  4. تصدير النتائج")
    print("=" * 50)
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
