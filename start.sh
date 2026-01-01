#!/bin/bash

# Telegram Link Collector Bot Startup Script
# سكريبت بدء تشغيل بوت جمع الروابط

set -e  # إيقاف عند الخطأ

# الألوان للواجهة
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# الدوال المساعدة
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# بدء التشغيل
print_header "🚀 بدء تشغيل بوت جمع الروابط"

# التحقق من وجود ملفات أساسية
print_info "🔍 التحقق من الملفات الأساسية..."

REQUIRED_FILES=("bot.py" "config.py" "database.py" "requirements.txt")
MISSING_FILES=0

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "/app/$file" ]; then
        print_success "   • $file"
    else
        print_error "   • $file (مفقود)"
        MISSING_FILES=$((MISSING_FILES + 1))
    fi
done

if [ $MISSING_FILES -gt 0 ]; then
    print_error "❌ ملفات أساسية مفقودة!"
    exit 1
fi

# إنشاء المجلدات المطلوبة
print_info "📁 إنشاء المجلدات المطلوبة..."

mkdir -p \
    /app/data \
    /app/exports \
    /app/sessions \
    /app/logs \
    /app/backups \
    /app/temp

print_success "   • تم إنشاء جميع المجلدات"

# التحقق من أذونات المجلدات
print_info "🔐 تعيين أذونات المجلدات..."

chmod -R 755 /app/data
chmod -R 755 /app/exports
chmod -R 755 /app/sessions
chmod -R 755 /app/logs
chmod -R 755 /app/temp

print_success "   • تم تعيين الأذونات"

# تهيئة قاعدة البيانات
print_info "🗄️  تهيئة قاعدة البيانات..."

cd /app

python3 -c "
import sys
import os
import logging

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger('startup')

try:
    # إضافة المسار
    sys.path.insert(0, '/app')
    
    # استيراد وتهيئة قاعدة البيانات
    from database import init_db
    logger.info('🔧 جاري تهيئة قاعدة البيانات...')
    init_db()
    
    # التحقق من تهيئة قاعدة البيانات
    from database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # التحقق من الجداول
    cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table';\")
    tables = cursor.fetchall()
    
    logger.info(f'📊 عدد الجداول في قاعدة البيانات: {len(tables)}')
    
    for table in tables:
        cursor.execute(f\"SELECT COUNT(*) FROM {table[0]}\")
        count = cursor.fetchone()[0]
        logger.info(f'   • {table[0]}: {count} سجل')
    
    conn.close()
    
    print('✅ تم تهيئة قاعدة البيانات بنجاح')
    
except Exception as e:
    logger.error(f'❌ فشل تهيئة قاعدة البيانات: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"

# التحقق من تهيئة التطبيق
print_info "🔧 التحقق من تهيئة التطبيق..."

python3 -c "
import sys
sys.path.insert(0, '/app')

try:
    from config import init_config
    print('🔧 جاري تهيئة إعدادات التطبيق...')
    if init_config():
        print('✅ تم تهيئة الإعدادات بنجاح')
    else:
        print('❌ فشل تهيئة الإعدادات')
        sys.exit(1)
        
except Exception as e:
    print(f'❌ خطأ في تهيئة الإعدادات: {e}')
    sys.exit(1)
"

# التحقق من BOT_TOKEN
print_info "🤖 التحقق من BOT_TOKEN..."

python3 -c "
import sys
sys.path.insert(0, '/app')

try:
    from config import BOT_TOKEN
    
    if not BOT_TOKEN or len(BOT_TOKEN) < 30:
        print('❌ BOT_TOKEN غير صالح أو غير مضبوط')
        print('📝 يرجى تعيين متغير البيئة BOT_TOKEN')
        sys.exit(1)
    else:
        print(f'✅ BOT_TOKEN مضبوط (الطول: {len(BOT_TOKEN)})')
        
except Exception as e:
    print(f'❌ خطأ في التحقق من BOT_TOKEN: {e}')
    sys.exit(1)
"

# التحقق من صحة الجلسات
print_info "👥 التحقق من الجلسات..."

python3 -c "
import sys
sys.path.insert(0, '/app')

try:
    from database import get_sessions
    from config import SESSIONS_DIR
    import os
    
    sessions = get_sessions()
    print(f'📊 عدد الجلسات في قاعدة البيانات: {len(sessions)}')
    
    # التحقق من ملفات الجلسات
    if os.path.exists(SESSIONS_DIR):
        session_files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.session')]
        print(f'📁 عدد ملفات الجلسات: {len(session_files)}')
    
    # عرض الجلسات النشطة
    active_sessions = [s for s in sessions if s.get('is_active')]
    print(f'🟢 الجلسات النشطة: {len(active_sessions)}')
    
    if len(active_sessions) == 0:
        print('⚠️  لا توجد جلسات نشطة. أضف جلسة واحدة على الأقل.')
    
except Exception as e:
    print(f'⚠️  خطأ في التحقق من الجلسات: {e}')
    # لا نوقف التشغيل لهذا الخطأ
"

# عرض معلومات النظام
print_header "📊 معلومات النظام"

echo -e "${BLUE}🧠 معلومات النظام:${NC}"
python3 -c "
import sys
import os
import platform

print(f'• Python: {sys.version}')
print(f'• النظام: {platform.system()} {platform.release()}')
print(f'• المسار الحالي: {os.getcwd()}')
print(f'• المساحة المتوفرة:')

import shutil
total, used, free = shutil.disk_usage('/')
print(f'   - الإجمالي: {total // (2**30)} GB')
print(f'   - المستخدم: {used // (2**30)} GB')
print(f'   - المتاح: {free // (2**30)} GB')
"

# عرض حجم الملفات
echo -e "\n${BLUE}📁 حجم الملفات:${NC}"
du -sh /app/data 2>/dev/null || echo "   • /app/data: غير متاح"
du -sh /app/exports 2>/dev/null || echo "   • /app/exports: غير متاح"
du -sh /app/sessions 2>/dev/null || echo "   • /app/sessions: غير متاح"

# بدء تشغيل البوت
print_header "🤖 بدء تشغيل البوت الرئيسي"

echo -e "${GREEN}🎉 البوت جاهز للتشغيل!${NC}"
echo -e "${YELLOW}⏳ جاري تشغيل البوت...${NC}"

# تشغيل البوت
exec python3 bot.py
