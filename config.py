import os

# ======================
# Telegram Bot
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# ======================
# Telegram API (Telethon)
# استخدام API افتراضي عام للقراءة فقط
# ======================

# API قياسي للقراءة فقط - لا يحتاج إلى تسجيل
API_ID = 6  # API ID عام للتطبيقات القرائية
API_HASH = "eb06d4abfb49dc3eeb1aeb98ae0f581e"  # API Hash عام

# ======================
# Database
# ======================

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "data/database.db"
)

# ======================
# Runtime Directories
# ======================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")

# ======================
# Collector Settings
# ======================

# أنواع الروابط التي يتم جمعها
COLLECT_TELEGRAM = True
COLLECT_WHATSAPP = True

# فحص الروابط قبل التجميع
VERIFY_LINKS = True

# إعدادات فحص الروابط
VERIFY_TIMEOUT = 10  # ثواني
MAX_CONCURRENT_VERIFICATIONS = 5

# روابط ممنوعة/تجاهل
BLACKLISTED_DOMAINS = [
    "telegram.me/durov",
]

# ======================
# Export Settings
# ======================

EXPORT_FORMATS = ['txt', 'json']

# ======================
# Bot Interface
# ======================

# عدد الروابط لكل صفحة في العرض
LINKS_PER_PAGE = 20

# رسائل حالة الجمع
COLLECTION_STATUS_MESSAGES = {
    'starting': '🚀 بدأ جمع الروابط...',
    'in_progress': '⏳ جاري جمع الروابط...',
    'paused': '⏸️ توقف جمع الروابط مؤقتاً',
    'stopped': '🛑 توقف جمع الروابط',
    'completed': '✅ اكتمل جمع الروابط'
}

# ======================
# Session Validation
# ======================

# لا نحتاج للتحقق من API_ID و API_HASH لأنها عامة
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ======================
# Ensure Directories Exist
# ======================

for directory in [EXPORT_DIR, SESSIONS_DIR]:
    os.makedirs(directory, exist_ok=True)
