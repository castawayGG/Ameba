FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей для psycopg2 и других библиотек
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --ignore-installed -r requirements.txt

COPY . .

# Создание необходимых папок для хранения данных
RUN mkdir -p sessions logs backups

# Создание непривилегированного пользователя
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app

USER appuser

ENV PYTHONPATH=/app

# Запуск Gunicorn (по умолчанию, может быть переопределён в docker-compose)
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "--forwarded-allow-ips=*", "web.app:app"]