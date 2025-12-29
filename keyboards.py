from telegram import InlineKeyboardMarkup, InlineKeyboardButton

MAIN_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("👥 إدارة الحسابات", callback_data="accounts")],
    [InlineKeyboardButton("📂 رفع روابط", callback_data="upload")],
    [InlineKeyboardButton("🧹 تصفية الروابط", callback_data="filter")],
    [InlineKeyboardButton("📤 توزيع الروابط", callback_data="assign")],
    [InlineKeyboardButton("🚀 بدء الانضمام", callback_data="join")]
])
