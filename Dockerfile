# استخدام صورة Python خفيفة الوزن
FROM python:3.11-slim

# معلومات عن الصورة
LABEL maintainer="Telegram Link Collector Bot"
LABEL version="1.0.0"
LABEL description="Telegram and WhatsApp active groups link collector bot"

# تعيين بيئة العمل
WORKDIR /app

# تعيين متغيرات البيئة
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# تحديث النظام وتثبيت الاعتمادات الأساسية
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libjpeg-dev \
    libpng-dev \
    sqlite3 \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# نسخ ملف المتطلبات أولاً (لتحسين caching)
COPY requirements.txt .

# تثبيت متطلبات Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# نسخ باقي الملفات
COPY . .

# إنشاء المجلدات المطلوبة
RUN mkdir -p \
    data \
    exports \
    sessions \
    logs \
    backups \
    temp

# تعيين أذونات للمجلدات
RUN chmod -R 755 /app

# فتح المنافذ (إذا لزم الأمر)
EXPOSE 8080

# تهيئة قاعدة البيانات قبل البدء
RUN python -c "
import sys
sys.path.insert(0, '/app')
try:
    from database import init_db
    init_db()
    print('✅ Database initialized successfully')
except Exception as e:
    print(f'❌ Database initialization failed: {e}')
    sys.exit(1)
"

# تشغيل البوت
CMD ["python", "bot.py"]
