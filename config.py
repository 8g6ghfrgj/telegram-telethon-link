import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# API للتطوير فقط - يمكن تغييرها
API_ID = 6
API_HASH = "eb06d4abfb49dc3eeb1aeb98ae0f581e"

# مسارات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "data", "database.db")
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")

# إنشاء المجلدات
for dir_path in [EXPORT_DIR, SESSIONS_DIR, os.path.dirname(DATABASE_PATH)]:
    os.makedirs(dir_path, exist_ok=True)

# التحقق
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required!")
