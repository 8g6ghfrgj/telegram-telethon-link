FROM python:3.11-slim

WORKDIR /app

# تحسين الأداء + منع مشاكل البايت
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# تثبيت المتطلبات النظامية
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# تثبيت المتطلبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ المشروع
COPY . .

# إنشاء المجلدات المطلوبة
RUN mkdir -p data exports sessions

# تشغيل البوت
CMD ["python", "bot.py"]
