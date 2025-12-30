import os

# ======================
# Telegram API
# ======================
API_ID = int(os.getenv("API_ID", "123456"))
API_HASH = os.getenv("API_HASH", "YOUR_API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")

# ======================
# Paths
# ======================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "data", "database.db")
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")

# ======================
# Collection Settings
# ======================
VERIFY_LINKS = True
VERIFY_TIMEOUT = 10

# ======================
# WhatsApp rules
# ======================
WHATSAPP_MAX_MONTHS = 6  # فقط آخر 6 أشهر
DISABLE_WA_ME = True     # منع wa.me

# ======================
# Limits
# ======================
MAX_VERIFY_CONCURRENCY = 5
