from telegram import Update
from telegram.ext import ContextTypes
from .keyboards import MAIN_MENU

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر من القائمة:", reply_markup=MAIN_MENU)
