FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    libssl-dev \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data exports sessions logs backups temp

# تهيئة القاعدة كمستخدم root
RUN python init_db.py

# خفّض الصلاحيات بعد التهيئة
RUN chown -R nobody:nogroup /app
USER nobody

CMD ["python", "-u", "bot.py"]
