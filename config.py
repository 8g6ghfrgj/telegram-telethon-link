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
    print("   على Render: اضغط على Environment → Add Environment Variable")
    print("   مفتاح: BOT_TOKEN")
    print("   قيمة: توكن_البوت_هنا")
    sys.exit(1)

# ======================
# Telegram API Configuration
# ======================

# استخدام API افتراضي عام للقراءة فقط
# هذه API عامة ولا تحتاج إلى تسجيل
API_ID = 6  # API ID عام للتطبيقات القرائية
API_HASH = "eb06d4abfb49dc3eeb1aeb98ae0f581e"  # API Hash عام

# ======================
# Paths Configuration
# ======================

# مسار قاعدة البيانات
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "database.db"))

# مسار مجلد التصدير
EXPORT_DIR = os.getenv("EXPORT_DIR", str(BASE_DIR / "exports"))

# مسار مجلد الجلسات
SESSIONS_DIR = os.getenv("SESSIONS_DIR", str(BASE_DIR / "sessions"))

# مسار مجلد البيانات
DATA_DIR = os.path.dirname(DATABASE_PATH)

# ======================
# Collector Configuration
# ======================

# أنواع الروابط التي يتم جمعها
COLLECT_TELEGRAM = True  # جمع روابط تليجرام
COLLECT_WHATSAPP = True   # جمع روابط واتساب

# فحص الروابط قبل الحفظ
VERIFY_LINKS = True  # تفعيل/تعطيل فحص الروابط

# إعدادات فحص الروابط
VERIFY_TIMEOUT = 10  # ثواني لوقت انتظار الفحص
MAX_CONCURRENT_VERIFICATIONS = 5  # الحد الأقصى للفحوصات المتزامنة

# روابط ممنوعة/تجاهل
BLACKLISTED_DOMAINS = [
    # يمكن إضافة نطاقات ممنوعة هنا
    # مثال: "telegram.me/durov",
]

# الحد الأقصى لعدد الروابط لكل جلسة
MAX_LINKS_PER_SESSION = 5000

# ======================
# Bot Interface Configuration
# ======================

# عدد الروابط لكل صفحة في العرض
LINKS_PER_PAGE = 20

# عدد الجلسات لكل صفحة
SESSIONS_PER_PAGE = 10

# رسائل حالة الجمع
COLLECTION_STATUS_MESSAGES = {
    'starting': '🚀 بدأ جمع الروابط...',
    'in_progress': '⏳ جاري جمع الروابط...',
    'paused': '⏸️ توقف جمع الروابط مؤقتاً',
    'stopped': '🛑 توقف جمع الروابط',
    'completed': '✅ اكتمل جمع الروابط'
}

# أسماء أنواع الروابط بالعربية
LINK_TYPE_NAMES = {
    # تليجرام
    'channel': '📢 القنوات',
    'public_group': '👥 المجموعات العامة',
    'private_group': '🔒 المجموعات الخاصة',
    'bot': '🤖 البوتات',
    'message': '📩 روابط رسائل',
    'unknown': '❓ غير معروف',
    
    # واتساب
    'group': '👥 مجموعات واتساب',
    'phone': '📞 روابط أرقام',
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
MAX_SESSIONS = 50

# وقت انتهاء الجلسات (بالأيام) - 0 يعني لا تنتهي
SESSION_EXPIRY_DAYS = 30

# التحقق التلقائي من صحة الجلسات عند البدء
AUTO_VALIDATE_SESSIONS = True

# ======================
# Export Configuration
# ======================

# تنسيقات التصدير المدعومة
EXPORT_FORMATS = ['txt', 'json']

# الترميز للتصدير
EXPORT_ENCODING = 'utf-8'

# الحد الأقصى للروابط في ملف تصدير واحد
MAX_LINKS_PER_EXPORT = 100000

# ======================
# Performance Configuration
# ======================

# حجم الذاكرة المؤقتة للقاعدة البيانات (بالكيلوبايت)
DATABASE_CACHE_SIZE = 2000  # 2MB

# نمط سجل قاعدة البيانات
DATABASE_JOURNAL_MODE = 'WAL'  # Write-Ahead Logging

# التزامن مع قاعدة البيانات
DATABASE_SYNCHRONOUS = 'NORMAL'

# ======================
# Logging Configuration
# ======================

# مستوى التسجيل
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# مسار سجلات الأخطاء
LOG_FILE = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "bot.log"))

# تنسيق السجلات
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# ======================
# Security Configuration
# ======================

# السماح بجلسات متعددة من نفس الحساب
ALLOW_DUPLICATE_SESSIONS = False

# التحقق من صحة الجلسات عند الإضافة
VALIDATE_SESSIONS_ON_ADD = True

# الحد الأقصى لمحاولات الاتصال الفاشلة
MAX_CONNECTION_RETRIES = 3

# وقت الانتظار بين المحاولات (بالثواني)
RETRY_DELAY = 5

# ======================
# Advanced Configuration
# ======================

# تفعيل وضع الصيانة
MAINTENANCE_MODE = False

# الرسالة في وضع الصيانة
MAINTENANCE_MESSAGE = "🔧 البوت قيد الصيانة. يرجى المحاولة لاحقًا."

# تفعيل النسخ الاحتياطي التلقائي
AUTO_BACKUP = True

# تكرار النسخ الاحتياطي (بالأيام)
BACKUP_INTERVAL_DAYS = 7

# الاحتفاظ بعدد النسخ الاحتياطية
MAX_BACKUPS = 5

# ======================
# Create Required Directories
# ======================

def create_directories():
    """إنشاء المجلدات المطلوبة"""
    directories = [
        DATA_DIR,
        EXPORT_DIR,
        SESSIONS_DIR,
        BASE_DIR / "logs",
        BASE_DIR / "backups",
    ]
    
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            print(f"⚠️  Warning: Could not create directory {directory}: {e}")

# ======================
# Validation Functions
# ======================

def validate_config():
    """التحقق من صحة الإعدادات"""
    errors = []
    
    # التحقق من BOT_TOKEN
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN غير موجود")
    elif len(BOT_TOKEN) < 30:
        errors.append("BOT_TOKEN غير صالح (قصير جداً)")
    
    # التحقق من API_ID و API_HASH
    if not API_ID or API_ID == 0:
        errors.append("API_ID غير صالح")
    
    if not API_HASH or len(API_HASH) < 10:
        errors.append("API_HASH غير صالح")
    
    # التحقق من المسارات
    for path_name, path_value in [
        ("DATABASE_PATH", DATABASE_PATH),
        ("EXPORT_DIR", EXPORT_DIR),
        ("SESSIONS_DIR", SESSIONS_DIR),
    ]:
        if not path_value:
            errors.append(f"{path_name} غير محدد")
    
    return errors

# ======================
# Print Configuration Summary
# ======================

def print_config_summary():
    """طباعة ملخص الإعدادات"""
    print("\n" + "="*50)
    print("⚙️  إعدادات البوت")
    print("="*50)
    
    print(f"\n🤖 معلومات البوت:")
    print(f"  • BOT_TOKEN: {'✅ مضبوط' if BOT_TOKEN else '❌ غير مضبوط'}")
    
    print(f"\n🔗 جمع الروابط:")
    print(f"  • تيليجرام: {'✅ مفعل' if COLLECT_TELEGRAM else '❌ معطل'}")
    print(f"  • واتساب: {'✅ مفعل' if COLLECT_WHATSAPP else '❌ معطل'}")
    print(f"  • فحص الروابط: {'✅ مفعل' if VERIFY_LINKS else '❌ معطل'}")
    
    print(f"\n📁 المسارات:")
    print(f"  • قاعدة البيانات: {DATABASE_PATH}")
    print(f"  • مجلد التصدير: {EXPORT_DIR}")
    print(f"  • مجلد الجلسات: {SESSIONS_DIR}")
    
    print(f"\n⚡ الأداء:")
    print(f"  • الحد الأقصى للجلسات: {MAX_SESSIONS}")
    print(f"  • الروابط لكل صفحة: {LINKS_PER_PAGE}")
    print(f"  • وقت فحص الروابط: {VERIFY_TIMEOUT} ثانية")
    
    print("\n" + "="*50)

# ======================
# Initialize Configuration
# ======================

def init_config():
    """تهيئة الإعدادات"""
    # إنشاء المجلدات المطلوبة
    create_directories()
    
    # التحقق من صحة الإعدادات
    errors = validate_config()
    
    if errors:
        print("❌ أخطاء في الإعدادات:")
        for error in errors:
            print(f"  • {error}")
        
        if "BOT_TOKEN" in str(errors):
            print("\n📝 كيفية إضافة BOT_TOKEN على Render:")
            print("1. اذهب إلى لوحة Render")
            print("2. اضغط على Environment")
            print("3. اضغط Add Environment Variable")
            print("4. أدخل:")
            print("   • Key: BOT_TOKEN")
            print("   • Value: توكن_البوت_هنا")
            print("5. اضغط Save Changes")
            print("6. أعد نشر البوت")
        
        sys.exit(1)
    
    # طباعة ملخص الإعدادات
    print_config_summary()
    
    return True

# ======================
# Helper Functions
# ======================

def get_telegram_link_types():
    """الحصول على أنواع روابط تليجرام"""
    return ['channel', 'public_group', 'private_group', 'bot', 'message']

def get_whatsapp_link_types():
    """الحصول على أنواع روابط واتساب"""
    return ['group', 'phone']

def get_all_link_types():
    """الحصول على جميع أنواع الروابط"""
    return get_telegram_link_types() + get_whatsapp_link_types()

def is_valid_platform(platform: str) -> bool:
    """التحقق مما إذا كانت المنصة مدعومة"""
    return platform in ['telegram', 'whatsapp']

def is_valid_link_type(platform: str, link_type: str) -> bool:
    """التحقق مما إذا كان نوع الرابط مدعوماً للمنصة"""
    if platform == 'telegram':
        return link_type in get_telegram_link_types()
    elif platform == 'whatsapp':
        return link_type in get_whatsapp_link_types()
    return False

def get_link_type_name(link_type: str) -> str:
    """الحصول على الاسم العربي لنوع الرابط"""
    return LINK_TYPE_NAMES.get(link_type, f"❓ {link_type}")

def get_platform_name(platform: str) -> str:
    """الحصول على الاسم العربي للمنصة"""
    return PLATFORM_NAMES.get(platform, f"🌐 {platform}")

def get_collection_status_message(status: str) -> str:
    """الحصول على رسالة حالة الجمع"""
    return COLLECTION_STATUS_MESSAGES.get(status, "🔄 حالة غير معروفة")

# ======================
# Export Functions
# ======================

def get_export_filename(platform: str = None, link_type: str = None, format: str = 'txt') -> str:
    """إنشاء اسم ملف للتصدير"""
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if platform and link_type:
        filename = f"links_{platform}_{link_type}_{timestamp}.{format}"
    elif platform:
        filename = f"links_{platform}_{timestamp}.{format}"
    else:
        filename = f"links_all_{timestamp}.{format}"
    
    return filename

def get_export_path(filename: str) -> str:
    """الحصول على المسار الكامل لملف التصدير"""
    return os.path.join(EXPORT_DIR, filename)

# ======================
# Session Functions
# ======================

def get_session_filepath(session_id: str) -> str:
    """الحصول على مسار ملف الجلسة"""
    return os.path.join(SESSIONS_DIR, f"session_{session_id}.session")

def get_session_backup_filepath() -> str:
    """الحصول على مسار نسخة احتياطية للجلسات"""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(SESSIONS_DIR, f"sessions_backup_{timestamp}.json")

# ======================
# Main Initialization
# ======================

if __name__ == "__main__":
    print("🔧 تهيئة إعدادات البوت...")
    if init_config():
        print("✅ تم تهيئة الإعدادات بنجاح!")
    else:
        print("❌ فشل تهيئة الإعدادات!")
        sys.exit(1)
