import os

# ======================
# Telegram Bot
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# ======================
# Telegram API (Telethon)
# ======================

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
# Webhook Settings (لتجنب Conflict)
# ======================

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PORT = int(os.getenv("PORT", "8080"))

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
VERIFY_LINKS = False  # تعطيل الفحص مؤقتاً

# إعدادات الجمع
MAX_HISTORY_DAYS = 3650  # 10 سنوات للتليجرام
MAX_WHATSAPP_DAYS = 180  # 6 أشهر للواتساب

# ======================
# Bot Interface
# ======================

LINKS_PER_PAGE = 20

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
