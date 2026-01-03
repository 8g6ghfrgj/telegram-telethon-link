web: gunicorn health_check:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 && python bot.py
worker: python bot.py
