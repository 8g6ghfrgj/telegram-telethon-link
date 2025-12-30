import os

# ======================
# Telegram Bot
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# ======================
# Telegram API (Telethon)
# ======================

API_ID = 6  # API عام
API_HASH = "eb06d4abfb49dc3eeb1aeb98ae0f581e"  # API Hash عام

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
