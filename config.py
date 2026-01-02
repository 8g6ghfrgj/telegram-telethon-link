# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# إعدادات البوت
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_ID = int(os.getenv('API_ID', 2040))
API_HASH = os.getenv('API_HASH', 'b18441a1ff607e10a989891a5462e627')

# إعدادات قاعدة البيانات
DATABASE_PATH = os.getenv('DATABASE_PATH', 'links_collector.db')

# إعدادات المجمع
LINKS_PER_PAGE = 10
COLLECTION_INTERVAL = 300  # 5 دقائق بين دورات الجمع

# المجلدات
SESSIONS_DIR = "sessions"
EXPORTS_DIR = "exports"

# إنشاء المجلدات إذا لم تكن موجودة
for directory in [SESSIONS_DIR, EXPORTS_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

def init_config():
    """تهيئة الإعدادات"""
    required_vars = ['BOT_TOKEN']
    missing_vars = [var for var in required_vars if not globals().get(var)]
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {missing_vars}")
    
    return True
