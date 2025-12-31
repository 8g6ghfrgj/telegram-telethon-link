import os
from dotenv import load_dotenv

load_dotenv()

# إعدادات البوت
BOT_TOKEN = os.getenv("BOT_TOKEN")

# إعدادات قاعدة البيانات
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///links.db")

# إعدادات المجمع
LINKS_PER_PAGE = int(os.getenv("LINKS_PER_PAGE", 50))
COLLECTION_INTERVAL = int(os.getenv("COLLECTION_INTERVAL", 300))  # ثواني
COLLECTION_STATUS_MESSAGES = os.getenv("COLLECTION_STATUS_MESSAGES", "true").lower() == "true"
MAX_CONCURRENT_SESSIONS = int(os.getenv("MAX_CONCURRENT_SESSIONS", 3))

# المجلدات
EXPORT_DIR = os.getenv("EXPORT_DIR", "exports")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "sessions")

# إنشاء المجلدات إذا لم تكن موجودة
os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(SESSIONS_DIR, exist_ok=True)

# روابط الواتساب المسموحة
WHATSAPP_DOMAINS = [
    "chat.whatsapp.com",
    "whatsapp.com",
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
        "all": "🔍 جميع روابط التليجرام"
    },
    "whatsapp": {
        "group": "👥 مجموعات واتساب",
        "all": "🔍 جميع روابط الواتساب"
    }
}

# إعدادات التصفح
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
]

# إعدادات الرسائل
MESSAGES = {
    "welcome": "مرحباً! 👋\n\nأنا بوت لجمع الروابط من القنوات والمجموعات.\n\nاستخدم /start لرؤية الأوامر المتاحة.",
    "help": """
**الأوامر المتاحة:**
/start - بدء البوت
/collect - بدء جمع الروابط
/stop - إيقاف الجمع
/status - حالة الجمع الحالية
/export - تصدير الروابط
/stats - إحصائيات الروابط
/help - عرض هذه الرسالة
    """,
    "collection_started": "✅ بدأ جمع الروابط...",
    "collection_stopped": "🛑 توقف جمع الروابط.",
    "no_active_collection": "⚠️ لا يوجد جمع نشط حالياً.",
    "export_ready": "📁 تم تصدير الروابط بنجاح."
}
