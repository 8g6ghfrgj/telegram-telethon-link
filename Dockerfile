FROM python:3.11-slim

WORKDIR /app

# تثبيت المتطلبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ الملفات
COPY . .

# إنشاء المجلدات
RUN mkdir -p data exports sessions

# تشغيل البوت
CMD ["python", "bot.py"]
