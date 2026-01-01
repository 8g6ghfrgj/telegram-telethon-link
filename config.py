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

# أنواع الروابط التي يتم جمعها - فقط المجموعات النشطة
COLLECT_TELEGRAM_PUBLIC_GROUPS = True  # جمع مجموعات تيليجرام العامة النشطة
COLLECT_TELEGRAM_PRIVATE_GROUPS = True  # جمع مجموعات تيليجرام الخاصة النشطة
COLLECT_WHATSAPP_GROUPS = True  # جمع مجموعات واتساب النشطة

# إيقاف جمع الأنواع الأخرى
COLLECT_TELEGRAM_CHANNELS = False  # لا تجمع القنوات
COLLECT_TELEGRAM_BOTS = False  # لا تجمع البوتات
COLLECT_TELEGRAM_MESSAGES = False  # لا تجمع روابط الرسائل
COLLECT_WHATSAPP_PHONE = False  # لا تجمع روابط أرقام واتساب

# فحص الروابط قبل الحفظ - مهم للتحقق من النشاط
VERIFY_LINKS = True  # تفعيل/تعطيل فحص الروابط

# إعدادات فحص الروابط
VERIFY_TIMEOUT = 15  # ثواني لوقت انتظار الفحص (زيادة الوقت للفحص الدقيق)
MAX_CONCURRENT_VERIFICATIONS = 3  # الحد الأقصى للفحوصات المتزامنة (تقليل للاستقرار)

# الحد الأدنى للأعضاء للمجموعات
MIN_MEMBERS_FOR_PUBLIC_GROUP = 50  # الحد الأدنى للأعضاء في المجموعات العامة
MIN_MEMBERS_FOR_PRIVATE_GROUP = 20  # الحد الأدنى للأعضاء في المجموعات الخاصة

# روابط ممنوعة/تجاهل
BLACKLISTED_DOMAINS = [
    # يمكن إضافة نطاقات ممنوعة هنا
    # مثال: "telegram.me/durov",
]

# روابط يجب تجاهلها (غير نشطة، قنوات، إلخ)
IGNORED_PATTERNS = [
    "t.me/c/",  # روابط القنوات الخاصة
    "t.me/bot",  # البوتات
    "t.me/share/",  # روابط المشاركة
    "t.me/iv?rhash=",  # روابط ملفات
    "t.me/addstickers/",  # الملصقات
    "t.me/addtheme/",  # الثيمات
    "t.me/+[0-9]{12}",  # أرقام هاتف وهمية
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
    'verifying': '🔍 جاري فحص الروابط والتأكد من النشاط...',
    'filtering': '⚡ جاري تصفية القنوات والروابط غير النشطة...',
    'paused': '⏸️ توقف جمع الروابط مؤقتاً',
    'stopped': '🛑 توقف جمع الروابط',
    'completed': '✅ اكتمل جمع الروابط النشطة'
}

# أسماء أنواع الروابط بالعربية
LINK_TYPE_NAMES = {
    # تيليجرام (فقط المجموعات النشطة)
    'public_group': '👥 المجموعات العامة النشطة',
    'private_group': '🔒 المجموعات الخاصة النشطة',
    
    # واتساب (فقط المجموعات النشطة)
    'group': '📞 مجموعات واتساب النشطة',
    
    # للأخطاء
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

# وقت انتهاء الجلسات (بالأيام) - 0 يعني لا تنتهي
SESSION_EXPIRY_DAYS = 30

# التحقق التلقائي من صحة الجلسات عند البدء
AUTO_VALIDATE_SESSIONS = True

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

# أسماء ملفات التصدير
EXPORT_FILENAMES = {
    'telegram_public_group': 'مجموعات_تيليجرام_العامة',
    'telegram_private_group': 'مجموعات_تيليجرام_الخاصة',
    'whatsapp_group': 'مجموعات_واتساب',
    'all_links': 'جميع_الروابط',
    'sessions_backup': 'نسخة_احتياطية_للجلسات'
}

# ======================
# Performance Configuration
# ======================

# حجم الذاكرة المؤقتة للقاعدة البيانات (بالكيلوبايت)
DATABASE_CACHE_SIZE = 2000  # 2MB

# نمط سجل قاعدة البيانات
DATABASE_JOURNAL_MODE = 'WAL'  # Write-Ahead Logging

# التزامن مع قاعدة البيانات
DATABASE_SYNCHRONOUS = 'NORMAL'

# تأخير بين طلبات الجمع (لتفادي الحظر)
COLLECTION_DELAY = 1.0  # ثانية

# الحد الأقصى لمحاولات الاتصال الفاشلة
MAX_CONNECTION_RETRIES = 3

# وقت الانتظار بين المحاولات (بالثواني)
RETRY_DELAY = 5

# ======================
# Link Filtering Configuration
# ======================

# تصفية القنوات (t.me/channel)
FILTER_CHANNELS = True

# تصفية المجموعات الفارغة
FILTER_EMPTY_GROUPS = True

# تصفية المجموعات المقفلة/المحظورة
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
LOG_FILE = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "bot.log"))

# تنسيق السجلات
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# ======================
# Security Configuration
# ======================

# الحد الأقصى لمحاولات الاتصال الفاشلة
MAX_CONNECTION_RETRIES = 3

# وقت الانتظار بين المحاولات (بالثواني)
RETRY_DELAY = 5

# تحقق من صلاحية الجلسات قبل الجمع
VALIDATE_SESSIONS_BEFORE_COLLECT = True

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

# إشعارات التقدم أثناء الجمع
PROGRESS_NOTIFICATIONS = True

# الفاصل الزمني للإشعارات (بالثواني)
PROGRESS_INTERVAL = 30

# ======================
# WhatsApp Configuration
# ======================

# نماذج روابط واتساب المعترف بها
WHATSAPP_LINK_PATTERNS = [
    r'https?://chat\.whatsapp\.com/[A-Za-z0-9_-]+',
    r'https?://wa\.me/[0-9]+',
    r'https?://whatsapp\.com/channel/[A-Za-z0-9_-]+',
]

# ======================
# Telegram Link Patterns
# ======================

# روابط المجموعات العامة
TELEGRAM_PUBLIC_GROUP_PATTERNS = [
    r'https?://t\.me/[A-Za-z0-9_]+',
    r'https?://telegram\.me/[A-Za-z0-9_]+',
]

# روابط المجموعات الخاصة
TELEGRAM_PRIVATE_GROUP_PATTERNS = [
    r'https?://t\.me/\+[A-Za-z0-9_-]+',
    r'https?://telegram\.me/\+[A-Za-z0-9_-]+',
]

# روابط القنوات (للتجاهل)
TELEGRAM_CHANNEL_PATTERNS = [
    r'https?://t\.me/c/[0-9]+',
    r'https?://t\.me/s/[A-Za-z0-9_]+',
]

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
        BASE_DIR / "temp",
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
    
    # تحقق من إعدادات الجمع
    if not (COLLECT_TELEGRAM_PUBLIC_GROUPS or COLLECT_TELEGRAM_PRIVATE_GROUPS or COLLECT_WHATSAPP_GROUPS):
        errors.append("يجب تفعيل جمع روابط واحدة على الأقل")
    
    return errors

# ======================
# Print Configuration Summary
# ======================

def print_config_summary():
    """طباعة ملخص الإعدادات"""
    print("\n" + "="*60)
    print("⚡ إعدادات بوت جمع الروابط النشطة فقط")
    print("="*60)
    
    print(f"\n🤖 معلومات البوت:")
    print(f"  • BOT_TOKEN: {'✅ مضبوط' if BOT_TOKEN else '❌ غير مضبوط'}")
    
    print(f"\n🎯 أنواع الروابط المجمعة:")
    print(f"  • مجموعات تيليجرام العامة: {'✅ مفعل' if COLLECT_TELEGRAM_PUBLIC_GROUPS else '❌ معطل'}")
    print(f"  • مجموعات تيليجرام الخاصة: {'✅ مفعل' if COLLECT_TELEGRAM_PRIVATE_GROUPS else '❌ معطل'}")
    print(f"  • مجموعات واتساب: {'✅ مفعل' if COLLECT_WHATSAPP_GROUPS else '❌ معطل'}")
    
    print(f"\n❌ أنواع غير مجمعة:")
    print(f"  • قنوات تيليجرام: {'❌ غير مجمعة' if not COLLECT_TELEGRAM_CHANNELS else '⚠️ مجمعة'}")
    print(f"  • بوتات تيليجرام: {'❌ غير مجمعة' if not COLLECT_TELEGRAM_BOTS else '⚠️ مجمعة'}")
    print(f"  • روابط رسائل: {'❌ غير مجمعة' if not COLLECT_TELEGRAM_MESSAGES else '⚠️ مجمعة'}")
    
    print(f"\n🔍 فحص الروابط:")
    print(f"  • التحقق من النشاط: {'✅ مفعل' if VERIFY_LINKS else '❌ معطل'}")
    print(f"  • الحد الأدنى للأعضاء (عامة): {MIN_MEMBERS_FOR_PUBLIC_GROUP}")
    print(f"  • الحد الأدنى للأعضاء (خاصة): {MIN_MEMBERS_FOR_PRIVATE_GROUP}")
    print(f"  • منع التكرار: {'✅ مفعل' if PREVENT_DUPLICATE_LINKS else '❌ معطل'}")
    
    print(f"\n📁 المسارات:")
    print(f"  • قاعدة البيانات: {DATABASE_PATH}")
    print(f"  • مجلد التصدير: {EXPORT_DIR}")
    print(f"  • مجلد الجلسات: {SESSIONS_DIR}")
    
    print(f"\n👥 إدارة الجلسات:")
    print(f"  • الحد الأقصى: {MAX_SESSIONS}")
    print(f"  • التحقق التلقائي: {'✅ مفعل' if AUTO_VALIDATE_SESSIONS else '❌ معطل'}")
    print(f"  • منع التكرار: {'✅ مفعل' if not ALLOW_DUPLICATE_SESSIONS else '❌ معطل'}")
    
    print(f"\n⚡ الأداء:")
    print(f"  • الروابط لكل صفحة: {LINKS_PER_PAGE}")
    print(f"  • وقت فحص الروابط: {VERIFY_TIMEOUT} ثانية")
    print(f"  • تأخير الجمع: {COLLECTION_DELAY} ثانية")
    
    print("\n" + "="*60)

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

def get_all_link_types():
    """الحصول على جميع أنواع الروابط المجمعة"""
    return get_telegram_link_types() + get_whatsapp_link_types()

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

def get_link_type_name(link_type: str) -> str:
    """الحصول على الاسم العربي لنوع الرابط"""
    return LINK_TYPE_NAMES.get(link_type, f"❓ {link_type}")

def get_platform_name(platform: str) -> str:
    """الحصول على الاسم العربي للمنصة"""
    return PLATFORM_NAMES.get(platform, f"🌐 {platform}")

def get_collection_status_message(status: str) -> str:
    """الحصول على رسالة حالة الجمع"""
    return COLLECTION_STATUS_MESSAGES.get(status, "🔄 حالة غير معروفة")

def is_link_ignored(url: str) -> bool:
    """التحقق مما إذا كان الرابط يجب تجاهله"""
    import re
    
    # التحقق من الأنماط الممنوعة
    for pattern in IGNORED_PATTERNS:
        if re.search(pattern, url):
            return True
    
    # التحقق من النطاقات الممنوعة
    for domain in BLACKLISTED_DOMAINS:
        if domain in url:
            return True
    
    return False

def is_telegram_channel(url: str) -> bool:
    """التحقق مما إذا كان الرابط قناة تيليجرام"""
    import re
    
    for pattern in TELEGRAM_CHANNEL_PATTERNS:
        if re.match(pattern, url):
            return True
    
    # التحقق من أنماط القنوات العامة
    if re.match(r'https?://t\.me/[A-Za-z0-9_]+', url):
        # يمكن إضافة تحقق إضافي هنا
        pass
    
    return False

def is_valid_telegram_group_url(url: str) -> bool:
    """التحقق مما إذا كان رابط مجموعة تيليجرام صالحاً"""
    import re
    
    # التحقق من المجموعات العامة
    for pattern in TELEGRAM_PUBLIC_GROUP_PATTERNS:
        if re.match(pattern, url):
            return True
    
    # التحقق من المجموعات الخاصة
    for pattern in TELEGRAM_PRIVATE_GROUP_PATTERNS:
        if re.match(pattern, url):
            return True
    
    return False

def is_valid_whatsapp_url(url: str) -> bool:
    """التحقق مما إذا كان رابط واتساب صالحاً"""
    import re
    
    for pattern in WHATSAPP_LINK_PATTERNS:
        if re.match(pattern, url):
            return True
    
    return False

# ======================
# Export Functions
# ======================

def get_export_filename(platform: str = None, link_type: str = None, format: str = 'txt') -> str:
    """إنشاء اسم ملف للتصدير"""
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if platform and link_type:
        arabic_name = EXPORT_FILENAMES.get(f"{platform}_{link_type}", f"{platform}_{link_type}")
        filename = f"{arabic_name}_{timestamp}.{format}"
    elif platform:
        filename = f"روابط_{platform}_{timestamp}.{format}"
    else:
        filename = f"جميع_الروابط_{timestamp}.{format}"
    
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

def get_temp_session_filepath(session_string: str) -> str:
    """الحصول على مسار مؤقت للجلسة للتحقق"""
    import hashlib
    session_hash = hashlib.md5(session_string.encode()).hexdigest()[:8]
    return os.path.join(SESSIONS_DIR, f"temp_{session_hash}.session")

# ======================
# Collection Statistics
# ======================

def get_collection_stats_template():
    """الحصول على قالب إحصائيات الجمع"""
    return {
        'total_collected': 0,
        'telegram_collected': 0,
        'whatsapp_collected': 0,
        'public_groups': 0,
        'private_groups': 0,
        'whatsapp_groups': 0,
        'duplicate_links': 0,
        'inactive_links': 0,
        'channels_skipped': 0,
        'banned_skipped': 0,
        'empty_skipped': 0,
        'start_time': None,
        'end_time': None,
        'duration': 0,
    }

# ======================
# Main Initialization
# ======================

if __name__ == "__main__":
    print("🔧 تهيئة إعدادات البوت...")
    print("🎯 البوت مصمم لجمع الروابط النشطة فقط")
    print("❌ لا يجمع القنوات أو الروابط غير النشطة")
    
    if init_config():
        print("✅ تم تهيئة الإعدادات بنجاح!")
        print("⚡ البوت جاهز للعمل!")
    else:
        print("❌ فشل تهيئة الإعدادات!")
        sys.exit(1)
