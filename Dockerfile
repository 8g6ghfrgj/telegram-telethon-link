FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# تثبيت المتطلبات النظامية
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# نسخ الملفات أولاً
COPY . .

# تثبيت المتطلبات
RUN pip install --no-cache-dir -r requirements.txt

# إنشاء المجلدات
RUN mkdir -p data exports sessions

CMD ["python", "bot.py"]
