import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from config import BOT_TOKEN
from database import init_db
from collector import (
    start_collection,
    stop_collection,
    pause_collection,
    resume_collection,
    get_collection_status,
)
from session_manager import test_all_sessions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ======================
# Keyboards
# ======================

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ بدء الجمع", callback_data="start")],
        [InlineKeyboardButton("⏸️ إيقاف مؤقت", callback_data="pause"),
         InlineKeyboardButton("▶️ استئناف", callback_data="resume")],
        [InlineKeyboardButton("⏹️ إيقاف", callback_data="stop")],
        [InlineKeyboardButton("🧪 اختبار الجلسات", callback_data="test")],
    ])

# ======================
# Handlers
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 بوت جمع روابط تيليجرام وواتساب",
        reply_markup=main_keyboard()
    )

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "start":
        await start_collection()
        await q.message.edit_text("🚀 بدأ الجمع", reply_markup=main_keyboard())

    elif q.data == "pause":
        await pause_collection()
        await q.message.edit_text("⏸️ تم الإيقاف المؤقت", reply_markup=main_keyboard())

    elif q.data == "resume":
        await resume_collection()
        await q.message.edit_text("▶️ تم الاستئناف", reply_markup=main_keyboard())

    elif q.data == "stop":
        await stop_collection()
        await q.message.edit_text("⏹️ تم الإيقاف", reply_markup=main_keyboard())

    elif q.data == "test":
        res = await test_all_sessions()
        await q.message.edit_text(
            f"🧪 الجلسات\n"
            f"الإجمالي: {res['total']}\n"
            f"الصالحة: {res['valid']}\n"
            f"المعطلة: {res['invalid']}",
            reply_markup=main_keyboard()
        )

# ======================
# Main
# ======================

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))

    logger.info("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
