FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# تحديث النظام وتثبيت الاعتمادات الأساسية
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# نسخ ملف المتطلبات أولاً
COPY requirements.txt .

# تثبيت متطلبات Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# نسخ باقي الملفات
COPY . .

# إنشاء المجلدات المطلوبة
RUN mkdir -p data exports sessions logs backups temp

# جعل start.sh قابل للتنفيذ
RUN chmod +x start.sh

# تشغيل سكريبت البدء
CMD ["./start.sh"]
