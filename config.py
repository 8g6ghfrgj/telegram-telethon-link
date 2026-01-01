import os
import sys
from pathlib import Path

# ======================
# الصفحة الرئيسية
# ======================

# الحصول على المسار الأساسي للمشروع
BASE_DIR = Path(__file__).parent.absolute()

# ======================
# Telegram Bot Configuration
# ======================

# الحصول على توكن البوت من متغير البيئة
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# التحقق من وجود التوكن
if not BOT_TOKEN:
    print("❌ خطأ: BOT_TOKEN غير موجود!")
    print("⚠️  يرجى تعيين متغير البيئة BOT_TOKEN")
    sys.exit(1)

# ======================
# Telegram API Configuration
# ======================

# استخدام API افتراضي عام للقراءة فقط
API_ID = 6  # API ID عام للتطبيقات القرائية
API_HASH = "eb06d4abfb49dc3eeb1aeb98ae0f581e"  # API Hash عام

# ======================
# Paths Configuration - إصلاح المسارات
# ======================

# مسار قاعدة البيانات - إصلاح المسار المطلق
DATABASE_PATH = os.path.join(BASE_DIR, "data", "database.db")

# مسار مجلد التصدير
EXPORT_DIR = os.path.join(BASE_DIR, "exports")

# مسار مجلد الجلسات
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")

# مسار مجلد البيانات
DATA_DIR = os.path.join(BASE_DIR, "data")

# ======================
# Collector Configuration
# ======================

# أنواع الروابط التي يتم جمعها - فقط المجموعات النشطة
COLLECT_TELEGRAM_PUBLIC_GROUPS = True  # جمع مجموعات تيليجرام العامة النشطة
COLLECT_TELEGRAM_PRIVATE_GROUPS = True  # جمع مجموعات تيليجرام الخاصة النشطة
COLLECT_WHATSAPP_GROUPS = True  # جمع مجموعات واتساب النشطة

# إيقاف جمع الأنواع الأخرى
COLLECT_TELEGRAM_CHANNELS = False  # لا تجمع القنوات
COLLECT_TELEGRAM_BOTS = False  # لا تجمع البوتات
COLLECT_TELEGRAM_MESSAGES = False  # لا تجمع روابط الرسائل
COLLECT_WHATSAPP_PHONE = False  # لا تجمع روابط أرقام واتساب

# فحص الروابط قبل الحفظ
VERIFY_LINKS = True  # تفعيل/تعطيل فحص الروابط

# إعدادات فحص الروابط
VERIFY_TIMEOUT = 15  # ثواني لوقت انتظار الفحص
MAX_CONCURRENT_VERIFICATIONS = 3  # الحد الأقصى للفحوصات المتزامنة

# الحد الأدنى للأعضاء للمجموعات
MIN_MEMBERS_FOR_PUBLIC_GROUP = 50  # الحد الأدنى للأعضاء في المجموعات العامة
MIN_MEMBERS_FOR_PRIVATE_GROUP = 20  # الحد الأدنى للأعضاء في المجموعات الخاصة

# روابط ممنوعة/تجاهل
BLACKLISTED_DOMAINS = [
    # يمكن إضافة نطاقات ممنوعة هنا
]

# روابط يجب تجاهلها
IGNORED_PATTERNS = [
    "t.me/c/",  # روابط القنوات الخاصة
    "t.me/bot",  # البوتات
    "t.me/share/",  # روابط المشاركة
]

# الحد الأقصى لعدد الروابط لكل جلسة
MAX_LINKS_PER_SESSION = 5000

# منع تكرار الروابط
PREVENT_DUPLICATE_LINKS = True

# ======================
# Bot Interface Configuration
# ======================

# عدد الروابط لكل صفحة في العرض
LINKS_PER_PAGE = 15

# عدد الجلسات لكل صفحة
SESSIONS_PER_PAGE = 10

# رسائل حالة الجمع
COLLECTION_STATUS_MESSAGES = {
    'starting': '🚀 بدأ جمع الروابط...',
    'in_progress': '⏳ جاري جمع الروابط النشطة فقط...',
    'paused': '⏸️ توقف جمع الروابط مؤقتاً',
    'stopped': '🛑 توقف جمع الروابط',
    'completed': '✅ اكتمل جمع الروابط النشطة'
}

# أسماء أنواع الروابط بالعربية
LINK_TYPE_NAMES = {
    'public_group': '👥 المجموعات العامة النشطة',
    'private_group': '🔒 المجموعات الخاصة النشطة',
    'group': '📞 مجموعات واتساب النشطة',
    'unknown': '❓ غير معروف',
}

# أسماء المنصات بالعربية
PLATFORM_NAMES = {
    'telegram': '📨 تيليجرام',
    'whatsapp': '📞 واتساب',
    'other': '🌐 أخرى',
}

# ======================
# Session Configuration
# ======================

# الحد الأقصى لعدد الجلسات
MAX_SESSIONS = 30

# وقت انتهاء الجلسات (بالأيام)
SESSION_EXPIRY_DAYS = 30

# التحقق التلقائي من صحة الجلسات عند البدء
AUTO_VALIDATE_SESSIONS = False  # تعطيل مؤقتاً لحل المشاكل

# السماح بجلسات متعددة من نفس الحساب
ALLOW_DUPLICATE_SESSIONS = False

# التحقق من صحة الجلسات عند الإضافة
VALIDATE_SESSIONS_ON_ADD = True

# ======================
# Export Configuration
# ======================

# تنسيقات التصدير المدعومة
EXPORT_FORMATS = ['txt']

# الترميز للتصدير
EXPORT_ENCODING = 'utf-8'

# الحد الأقصى للروابط في ملف تصدير واحد
MAX_LINKS_PER_EXPORT = 50000

# ======================
# Performance Configuration
# ======================

# حجم الذاكرة المؤقتة للقاعدة البيانات
DATABASE_CACHE_SIZE = 2000  # 2MB

# نمط سجل قاعدة البيانات
DATABASE_JOURNAL_MODE = 'WAL'

# التزامن مع قاعدة البيانات
DATABASE_SYNCHRONOUS = 'NORMAL'

# تأخير بين طلبات الجمع
COLLECTION_DELAY = 1.0  # ثانية

# الحد الأقصى لمحاولات الاتصال الفاشلة
MAX_CONNECTION_RETRIES = 3

# وقت الانتظار بين المحاولات
RETRY_DELAY = 5

# ======================
# Link Filtering Configuration
# ======================

# تصفية القنوات
FILTER_CHANNELS = True

# تصفية المجموعات الفارغة
FILTER_EMPTY_GROUPS = True

# تصفية المجموعات المقفلة
FILTER_BANNED_GROUPS = True

# تصفية الروابط الميتة
FILTER_DEAD_LINKS = True

# الحد الأدنى لحجم المجموعة
MIN_GROUP_SIZE = 1

# ======================
# Logging Configuration
# ======================

# مستوى التسجيل
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# مسار سجلات الأخطاء
LOG_FILE = os.path.join(BASE_DIR, "logs", "bot.log")

# تنسيق السجلات
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# ======================
# Advanced Configuration
# ======================

# تفعيل وضع الصيانة
MAINTENANCE_MODE = False

# الرسالة في وضع الصيانة
MAINTENANCE_MESSAGE = "🔧 البوت قيد الصيانة. يرجى المحاولة لاحقًا."

# ======================
# Create Required Directories
# ======================

def create_directories():
    """إنشاء المجلدات المطلوبة"""
    directories = [
        DATA_DIR,
        EXPORT_DIR,
        SESSIONS_DIR,
        os.path.join(BASE_DIR, "logs"),
        os.path.join(BASE_DIR, "backups"),
        os.path.join(BASE_DIR, "temp"),
    ]
    
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            print(f"📁 تم إنشاء/التحقق من: {directory}")
        except Exception as e:
            print(f"⚠️  Warning: Could not create directory {directory}: {e}")

# ======================
# Initialize Configuration
# ======================

def init_config():
    """تهيئة الإعدادات"""
    # إنشاء المجلدات المطلوبة
    create_directories()
    
    print("✅ تم تهيئة الإعدادات وإنشاء المجلدات")
    return True

# ======================
# Helper Functions
# ======================

def get_telegram_link_types():
    """الحصول على أنواع روابط تيليجرام - فقط المجموعات النشطة"""
    types = []
    if COLLECT_TELEGRAM_PUBLIC_GROUPS:
        types.append('public_group')
    if COLLECT_TELEGRAM_PRIVATE_GROUPS:
        types.append('private_group')
    return types

def get_whatsapp_link_types():
    """الحصول على أنواع روابط واتساب - فقط المجموعات النشطة"""
    if COLLECT_WHATSAPP_GROUPS:
        return ['group']
    return []

def is_valid_platform(platform: str) -> bool:
    """التحقق مما إذا كانت المنصة مدعومة"""
    if platform == 'telegram':
        return COLLECT_TELEGRAM_PUBLIC_GROUPS or COLLECT_TELEGRAM_PRIVATE_GROUPS
    elif platform == 'whatsapp':
        return COLLECT_WHATSAPP_GROUPS
    return False

def is_valid_link_type(platform: str, link_type: str) -> bool:
    """التحقق مما إذا كان نوع الرابط مدعوماً للمنصة"""
    if platform == 'telegram':
        if link_type == 'public_group':
            return COLLECT_TELEGRAM_PUBLIC_GROUPS
        elif link_type == 'private_group':
            return COLLECT_TELEGRAM_PRIVATE_GROUPS
    elif platform == 'whatsapp':
        if link_type == 'group':
            return COLLECT_WHATSAPP_GROUPS
    return False

if __name__ == "__main__":
    print("🔧 تهيئة إعدادات البوت...")
    init_config()
    print("✅ تم تهيئة الإعدادات بنجاح!")
