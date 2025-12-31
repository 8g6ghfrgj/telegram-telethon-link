FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# إنشاء المجلدات
RUN mkdir -p data exports sessions

CMD ["python", "bot.py"]
