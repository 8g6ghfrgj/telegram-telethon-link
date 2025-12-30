import os

# ======================
# Telegram Bot
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# ======================
# Telegram API (Telethon)
# ======================

# API قياسي للقراءة فقط
API_ID = 6
API_HASH = "eb06d4abfb49dc3eeb1aeb98ae0f581e"

# ======================
# Database
# ======================

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/database.db")

# ======================
# Runtime Directories
# ======================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# ======================
# Collector Settings
# ======================

# أنواع الروابط التي يتم جمعها
COLLECT_TELEGRAM = True
COLLECT_WHATSAPP = True

# فحص الروابط قبل التجميع
VERIFY_LINKS = True

# إعدادات الفحص
VERIFY_TIMEOUT = 10
MAX_CONCURRENT_VERIFICATIONS = 5

# روابط ممنوعة
BLACKLISTED_DOMAINS = []

# ======================
# Collection Settings
# ======================

# عدد الرسائل للجمع من التاريخ (0 = كل الرسائل)
TELEGRAM_HISTORY_LIMIT = 0  # جميع الرسائل من 2000
WHATSAPP_HISTORY_LIMIT = 5000  # ~6 أشهر من الرسائل

# تأخير بين الرسائل لمنع Flood (بالثواني)
MESSAGE_DELAY = 0.1

# ======================
# Bot Settings
# ======================

# منع Conflict - استخدام webhook بدلاً من polling
USE_WEBHOOK = False
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# إعدادات Polling لمنع Conflict
POLLING_TIMEOUT = 30
POLLING_RETRY = 10

# ======================
# Export Settings
# ======================

EXPORT_FORMATS = ['txt']

# ======================
# Bot Interface
# ======================

LINKS_PER_PAGE = 20

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

# ======================
# Ensure Directories Exist
# ======================

for directory in [EXPORT_DIR, SESSIONS_DIR, LOGS_DIR, "data"]:
    os.makedirs(directory, exist_ok=True)
