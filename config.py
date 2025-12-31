import os
from dotenv import load_dotenv

load_dotenv()

# إعدادات البوت
BOT_TOKEN = os.getenv("BOT_TOKEN")

# إعدادات قاعدة البيانات
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///links.db")

# إعدادات المجمع
LINKS_PER_PAGE = 50
COLLECTION_INTERVAL = 300  # ثواني
MAX_CONCURRENT_SESSIONS = 3

# المجلدات
EXPORT_DIR = "exports"
SESSIONS_DIR = "sessions"

# إنشاء المجلدات إذا لم تكن موجودة
os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(SESSIONS_DIR, exist_ok=True)

# روابط الواتساب المسموحة
WHATSAPP_DOMAINS = [
    "chat.whatsapp.com",
    "whatsapp.com",
    "wa.me"
]

# روابط التليجرام المسموحة
TELEGRAM_DOMAINS = [
    "t.me",
    "telegram.me",
    "telegram.dog"
]

# إعدادات الأنواع
LINK_TYPES = {
    "telegram": {
        "channel": "📢 القنوات",
        "public_group": "👥 مجموعات عامة",
        "private_group": "🔒 مجموعات خاصة",
        "bot": "🤖 البوتات",
        "message": "📩 روابط رسائل",
        "all": "🔍 جميع روابط التليجرام"
    },
    "whatsapp": {
        "group": "👥 مجموعات واتساب",
        "phone": "📞 روابط أرقام",
        "all": "🔍 جميع روابط الواتساب"
    }
}
