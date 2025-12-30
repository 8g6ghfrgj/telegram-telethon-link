import os

# ======================
# Telegram Bot
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# ======================
# Telegram API (Telethon)
# ثوابت داخل الكود كما طلبت
# ======================

API_ID = 12345678          # ← ضع API_ID الحقيقي هنا
API_HASH = "API_HASH_HERE" # ← ضع API_HASH الحقيقي هنا

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
    "telegram.me/durov",  # مثال
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
# Validation
# ======================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

if not API_ID or not API_HASH:
    raise RuntimeError("API_ID / API_HASH are missing")

# ======================
# Ensure Directories Exist
# ======================

for directory in [EXPORT_DIR, SESSIONS_DIR]:
    os.makedirs(directory, exist_ok=True)
