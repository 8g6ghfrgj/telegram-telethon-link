import os

# ======================
# Telegram Bot
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# ======================
# Telegram API (Telethon)
# ======================

# API قياسي للقراءة فقط - لا يحتاج إلى تسجيل
API_ID = 6
API_HASH = "eb06d4abfb49dc3eeb1aeb98ae0f581e"

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

COLLECT_TELEGRAM = True
COLLECT_WHATSAPP = True
VERIFY_LINKS = True
VERIFY_TIMEOUT = 10
MAX_CONCURRENT_VERIFICATIONS = 5

BLACKLISTED_DOMAINS = []

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

for directory in [EXPORT_DIR, SESSIONS_DIR]:
    os.makedirs(directory, exist_ok=True)
