FROM python:3.11-slim

WORKDIR /app

# تثبيت المتطلبات النظامية
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# نسخ ملفات المشروع
COPY . .

# تثبيت متطلبات Python
RUN pip install --no-cache-dir -r requirements.txt

# إنشاء المجلدات اللازمة
RUN mkdir -p exports sessions

# تشغيل البوت
CMD ["python", "bot.py"]
